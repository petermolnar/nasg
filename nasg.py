#!/usr/bin/env python3

__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2019, Peter Molnar"
__license__ = "apache-2.0"
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import glob
import os
import time
import re
import imghdr
import asyncio
import sqlite3
import json
import queue
from shutil import copy2 as cp
from math import ceil
from urllib.parse import urlparse
from collections import OrderedDict, namedtuple
import logging
import arrow
import langdetect
import wand.image
import jinja2
import yaml
from feedgen.feed import FeedGenerator
from bleach import clean
from emoji import UNICODE_EMOJI
from slugify import slugify
import requests
from pandoc import Pandoc
from meta import Exif, GoogleVision, GoogleClassifyText
import settings
import keys

from pprint import pprint

logger = logging.getLogger('NASG')

MarkdownImage = namedtuple(
    'MarkdownImage',
    ['match', 'alt', 'fname', 'title', 'css']
)

REPLY_TYPES = ['webmention', 'in-reply-to', 'reply']

J2 = jinja2.Environment(
    loader=jinja2.FileSystemLoader(searchpath=settings.paths.get('tmpl')),
    lstrip_blocks=True,
    trim_blocks=True
)

RE_MDIMG = re.compile(
    r'(?P<match>!\[(?P<alt>[^\]]+)?\]\((?P<fname>[^\s]+)'
    r'(?:\s[\'\"](?P<title>[^\"\']+)[\'\"])?\)(?:{(?P<css>[^\}]+)\})?)',
    re.IGNORECASE
)

RE_CODE = re.compile(
    r'^(?:[~`]{3}).+$',
    re.MULTILINE
)

RE_PRECODE = re.compile(
    r'<pre class="([^"]+)"><code>'
)

def utfyamldump(data):
    return yaml.dump(
        data,
        default_flow_style=False,
        indent=4,
        allow_unicode=True
    )

def url2slug(url, limit=200):
    return slugify(
        re.sub(r"^https?://(?:www)?", "", url),
        only_ascii=True,
        lower=True
    )[:limit]


def writepath(fpath, content, mtime=0):
    d = os.path.dirname(fpath)
    if not os.path.isdir(d):
        logger.debug('creating directory tree %s', d)
        os.makedirs(d)

    if isinstance(content, str):
        mode = 'wt'
    else:
        mode = 'wb'

    with open(fpath, mode) as f:
        logger.info('writing file %s', fpath)
        f.write(content)


class cached_property(object):
    """ extermely simple cached_property decorator:
    whenever something is called as @cached_property, on first run, the
    result is calculated, then the class method is overwritten to be
    a property, contaning the result from the method
    """

    def __init__(self, method, name=None):
        self.method = method
        self.name = name or method.__name__

    def __get__(self, inst, cls):
        if inst is None:
            return self
        result = self.method(inst)
        setattr(inst, self.name, result)
        return result


class AQ:
    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.queue = asyncio.Queue(loop=self.loop)

    def put(self, task):
        self.queue.put(asyncio.ensure_future(task))

    async def consume(self):
        while not self.queue.empty():
            item = await self.queue.get()
            self.queue.task_done()
        #asyncio.gather() ?

    def run(self):
        consumer = asyncio.ensure_future(self.consume())
        self.loop.run_until_complete(consumer)


class Webmention(object):
    def __init__(self, parent):
        self.dpath = os.path.dirname(parent.fpath)
        self.source = parent.url
        self.target = parent.is_reply
        self.mtime = parent.mtime

    @property
    def fpath(self):
        return os.path.join(
            self.dpath,
            '%s.ping' % (
                url2slug(self.target, 200)
            )
        )

    @property
    def exists(self):
        if not os.path.isfile(self.fpath):
            return False
        elif os.path.getmtime(self.fpath) > self.mtime:
            return True
        else:
            return False

    def save(self, content):
        writepath(self.fpath, content)

    async def send(self):
        if self.exists:
            return
        telegraph_url = 'https://telegraph.p3k.io/webmention'
        telegraph_params = {
            'token': '%s' % (keys.telegraph.get('token')),
            'source': '%s' % (self.source),
            'target': '%s' % (self.target)
        }
        r = requests.post(telegraph_url, data=telegraph_params)
        logger.info(
            "sent webmention to telegraph from %s to %s",
            self.source,
            self.target
        )
        if r.status_code not in [200, 201, 202]:
            logger.error('sending failed: %s %s', r.status_code, r.text)
        else:
            self.save(r.text)


class MarkdownDoc(object):
    mdregex = re.compile(
        r'^---\s?[\r\n](?P<meta>.+?)[\r\n]---(?:\s?[\r\n](?P<content>.+))?',
        flags=re.MULTILINE|re.DOTALL
    )

    @cached_property
    def _parsed(self):
        logger.debug('parsing file %s', self.fpath)
        with open(self.fpath, mode='r') as f:
            txt = f.read()
        txt = self.mdregex.match(txt)
        if not txt:
            logger.error('failed to match YAML + MD doc: %s', self.fpath)
        if txt.group('content'):
            t = txt.group('content').strip()
        else:
            t = ''
        return (yaml.load(txt.group('meta')), t)

    @property
    def meta(self):
        return self._parsed[0]

    @property
    def content(self):
        return self._parsed[1]

    def __pandoc(self, c):
        if c and len(c):
            c = Pandoc(c)
            c = RE_PRECODE.sub(
                '<pre><code lang="\g<1>" class="language-\g<1>">', c)
        return c

    @cached_property
    def html_content(self):
        c = "%s" % (self.content)
        if hasattr(self, 'images') and len(self.images):
            for match, img in self.images.items():
                c = c.replace(match, str(img))
        return self.__pandoc(c)

    @cached_property
    def html_content_noimg(self):
        c = "%s" % (self.content)
        if hasattr(self, 'images') and len(self.images):
            for match, img in self.images.items():
                c = c.replace(match, '')
        return self.__pandoc(c)


class Comment(MarkdownDoc):
    def __init__(self, fpath):
        self.fpath = fpath
        self.mtime = os.path.getmtime(fpath)

    @property
    def dt(self):
        maybe = self.meta.get('date')
        if maybe and 'null' != maybe:
            dt = arrow.get(maybe)
        else:
            dt = arrow.get(os.path.getmtime(self.fpath))
        return dt

    @property
    def target(self):
        t = urlparse(self.meta.get('target'))
        return t.path.rstrip('/').strip('/').split('/')[-1]

    @property
    def source(self):
        return self.meta.get('source')

    @property
    def author(self):
        r = {
            'name': urlparse(self.source).hostname,
            'url': self.source
        }
        author = self.meta.get('author')
        if not author:
            return r
        if 'name' in author:
            r.update({
                'name': self.meta.get('author').get('name')
            })
        elif 'url' in author:
            r.update({
                'name': urlparse(self.meta.get('author').get('url')).hostname
            })
        return r

    @property
    def type(self):
        if len(self.content):
            maybe = clean(self.content, strip=True)
            if maybe in UNICODE_EMOJI:
                return maybe
        return self.meta.get('type', 'webmention')

    @property
    def tmplvars(self):
        return {
            'author': self.author,
            'source': self.source,
            'pubtime': self.dt.format(settings.dateformat.get('iso')),
            'pubdate': self.dt.format(settings.dateformat.get('display')),
            'html': self.html_content,
            'type': self.type
        }


class Gone(object):
    """
    Gone object for delete entries
    """

    def __init__(self, fpath):
        self.fpath = fpath
        self.mtime = os.path.getmtime(fpath)

    @property
    def source(self):
        source, fext = os.path.splitext(os.path.basename(self.fpath))
        return source


class Redirect(Gone):
    """
    Redirect object for entries that moved
    """

    @cached_property
    def target(self):
        target = ''
        with open(self.fpath, 'rt') as f:
            target = f.read().strip()
        return target


class Singular(MarkdownDoc):
    """
    A Singular object: a complete representation of a post, including
    all it's comments, files, images, etc
    """

    def __init__(self, fpath):
        self.fpath = fpath
        n = os.path.dirname(fpath)
        self.name = os.path.basename(n)
        self.category = os.path.basename(os.path.dirname(n))
        self.mtime = os.path.getmtime(self.fpath)

    @property
    def ctime(self):
        ret = self.mtime
        if len(self.comments):
            for mtime, c in self.comments.items():
                if c.mtime > ret:
                    ret = c.mtime
        return ret

    @cached_property
    def files(self):
        """
        An array of files present at the same directory level as
        the Singular object, excluding hidden (starting with .) and markdown
        (ending with .md) files
        """
        return [
            k
            for k in glob.glob(os.path.join(os.path.dirname(self.fpath), '*.*'))
            if
                not k.startswith('.')
                and not k.endswith('.md')
                and not k.endswith('.ping')
                and not k.endswith('.url')
                and not k.endswith('.del')
        ]

    @cached_property
    def comments(self):
        """
        An dict of Comment objects keyed with their path, populated from the
        same directory level as the Singular objects
        """
        comments = {}
        files = [
            k
            for k in glob.glob(os.path.join(os.path.dirname(self.fpath), '*.md'))
            if os.path.basename(k) != 'index.md'
        ]
        for f in files:
            c = Comment(f)
            comments[c.dt.timestamp] = c
        return comments

    @cached_property
    def images(self):
        """
        A dict of WebImage objects, populated by:
        - images that are present in the Markdown content
        - and have an actual image file at the same directory level as
        the Singular object
        """
        images = {}
        for match, alt, fname, title, css in RE_MDIMG.findall(self.content):
            mdimg = MarkdownImage(match, alt, fname, title, css)
            imgpath = os.path.join(
                os.path.dirname(self.fpath),
                fname
            )
            if imgpath in self.files:
                if imghdr.what(imgpath):
                    images.update({match: WebImage(imgpath, mdimg, self)})
        return images

    @property
    def is_page(self):
        if self.category.startswith('_'):
            return True
        return False

    @property
    def is_front(self):
        """
        Returns if the post should be displayed on the front
        """
        if self.category in settings.site.get('on_front'):
            return True
        return False

    @property
    def is_photo(self):
        """
        This is true if there is a file, with the same name as the entry's
        directory - so, it's slug -, and that that image believes it's a a
        photo.
        """
        if len(self.images) != 1:
            return False
        photo = next(iter(self.images.values()))
        maybe = self.fpath.replace("index.md", "%s.jpg" % (self.name))
        if photo.fpath == maybe:
            return True
        return False

    @property
    def photo(self):
        if not self.is_photo:
            return None
        return next(iter(self.images.values()))

    @property
    def enclosure(self):
        if not self.is_photo:
            return None
        else:
            return {
                'mime': self.photo.mime_type,
                'size': self.photo.mime_size,
                'url': self.photo.href
            }

    @property
    def summary(self):
        return self.meta.get('summary', '')

    @cached_property
    def html_summary(self):
        c = self.summary
        if c and len(c):
            c = Pandoc(self.summary)
        return c

    @property
    def title(self):
        if self.is_reply:
            return "RE: %s" % self.is_reply
        return self.meta.get(
            'title',
            arrow.get(
                self.published).format(
                settings.dateformat.get('display'))
        )

    @property
    def tags(self):
        return self.meta.get('tags', [])

    @property
    def syndicate(self):
        urls = self.meta.get('syndicate', [])
        if self.is_photo:
            urls.append("https://brid.gy/publish/flickr")
        urls.append("https://fed.brid.gy/")
        return urls

    def baseN(self, num, b=36,
              numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
        """
        Creates short, lowercase slug for a number (an epoch) passed
        """
        num = int(num)
        return ((num == 0) and numerals[0]) or (
            self.baseN(
                num // b,
                b,
                numerals
            ).lstrip(numerals[0]) + numerals[num % b]
        )

    @property
    def shortslug(self):
        return self.baseN(self.published.timestamp)

    @property
    def published(self):
        return arrow.get(self.meta.get('published'))

    @property
    def is_reply(self):
        return self.meta.get('in-reply-to', False)

    @property
    def is_future(self):
        if self.published.timestamp > arrow.utcnow().timestamp:
            return True
        return False

    @property
    def to_ping(self):
        urls = []
        if self.is_reply:
            w = Webmention(self)
            urls.append(w)
        return urls

    @property
    def licence(self):
        if self.category in settings.licence:
            return settings.licence[self.category]
        return settings.site.get('licence')

    @property
    def lang(self):
        lang = 'en'
        try:
            lang = langdetect.detect("\n".join([
                self.meta.get('title', ''),
                self.content
            ]))
        except BaseException:
            pass
        return lang

    @property
    def classification(self):
        c = GoogleClassifyText(self.fpath, self.content, self.lang)
        k = '/Arts & Entertainment/Visual Art & Design/Photographic & Digital Arts'
        if self.is_photo and k not in c.keys():
            c.update({
                k : '1.0'
            })
        return c

    @property
    def url(self):
        return "%s/%s/" % (
            settings.site.get('url'),
            self.name
        )

    @property
    def replies(self):
        r = OrderedDict()
        for mtime, c in self.comments.items():
            if c.type not in REPLY_TYPES:
                continue
            r[mtime] = c.tmplvars
        return r

    @property
    def reactions(self):
        r = OrderedDict()
        for mtime, c in self.comments.items():
            if c.type in REPLY_TYPES:
                continue
            t = "%s" % (c.type)
            if t not in r:
                r[t] = OrderedDict()
            r[t][mtime] = c.tmplvars
        return r

    @property
    def has_code(self):
        if RE_CODE.search(self.content):
            return True
        else:
            return False

    @property
    def event(self):
        if 'event' not in self.meta:
            return False

        event = self.meta.get('event', {})
        event.update({
            'startdate': arrow.get(event.get('start')).format(settings.dateformat.get('display')),
            'starttime': arrow.get(event.get('start')).format(settings.dateformat.get('iso')),
            'enddate': arrow.get(event.get('end')).format(settings.dateformat.get('display')),
            'endtime': arrow.get(event.get('end')).format(settings.dateformat.get('iso')),
        })
        return event

    @cached_property
    def tmplvars(self):
        v = {
            'title': self.title,
            'category': self.category,
            'lang': self.lang,
            'slug': self.name,
            'is_reply': self.is_reply,
            'is_page': self.is_page,
            'summary': self.summary,
            'html_summary': self.html_summary,
            'html_content': self.html_content,
            'mtime': self.mtime,
            'pubtime': self.published.format(settings.dateformat.get('iso')),
            'pubdate': self.published.format(settings.dateformat.get('display')),
            'year': int(self.published.format('YYYY')),
            'licence': self.licence,
            'replies': self.replies,
            'reactions': self.reactions,
            'syndicate': self.syndicate,
            'url': self.url,
            'review': self.review,
            'has_code': self.has_code,
            'event': self.event,
            'classification': self.classification.keys()
        }
        if (self.is_photo):
            v.update({
                'enclosure': self.enclosure,
                'photo': self.photo
            })
        return v

    @property
    def review(self):
        if 'review' not in self.meta:
            return False
        r = self.meta.get('review')
        rated, outof = r.get('rating').split('/')
        r.update({
            'rated': rated,
            'outof': outof
        })
        return r

    @property
    def template(self):
        return "%s.j2.html" % (self.__class__.__name__)

    @property
    def renderdir(self):
        return os.path.dirname(self.renderfile)

    @property
    def renderfile(self):
        return os.path.join(
            settings.paths.get('build'),
            self.name,
            'index.html'
        )

    @property
    def exists(self):
        if settings.args.get('force'):
            return False
        elif not os.path.exists(self.renderfile):
            return False
        elif self.ctime > os.path.getmtime(self.renderfile):
            return False
        else:
            return True

    @property
    def corpus(self):
        return "\n".join([
            self.title,
            self.name,
            self.summary,
            self.content,
        ])

    async def copyfiles(self):
        exclude = ['.md', '.jpg', '.png', '.gif', '.ping']
        files = glob.glob(os.path.join(
            os.path.dirname(self.fpath),
            '*.*'
        ))
        for f in files:
            fname, fext = os.path.splitext(f)
            if fext.lower() in exclude:
                continue

            t = os.path.join(
                settings.paths.get('build'),
                self.name,
                os.path.basename(f)
            )
            if os.path.exists(t) and os.path.getmtime(
                    f) <= os.path.getmtime(t):
                continue
            logger.info("copying '%s' to '%s'", f, t)
            cp(f, t)

    async def render(self):
        if self.exists:
            return
        logger.info("rendering %s", self.name)
        r = J2.get_template(self.template).render({
            'post': self.tmplvars,
            'site': settings.site,
            'author': settings.author,
            'meta': settings.meta,
            'licence': settings.licence,
            'tips': settings.tips,
        })
        writepath(self.renderfile, r)


class WebImage(object):
    def __init__(self, fpath, mdimg, parent):
        logger.debug("loading image: %s", fpath)
        self.mdimg = mdimg
        self.fpath = fpath
        self.parent = parent
        self.mtime = os.path.getmtime(self.fpath)
        self.fname, self.fext = os.path.splitext(os.path.basename(fpath))
        self.resized_images = [
            (k, self.Resized(self, k))
            for k in settings.photo.get('sizes').keys()
            if k < max(self.width, self.height)
        ]
        if not len(self.resized_images):
            self.resized_images.append((
                max(self.width, self.height),
                self.Resized(self, max(self.width, self.height))
            ))

    @property
    def is_mainimg(self):
        if self.fname == self.parent.name:
            return True
        return False

    @cached_property
    def tmplvars(self):
        return {
            'src': self.src,
            'href': self.href,
            'width': self.displayed.width,
            'height': self.displayed.height,
            'title': self.title,
            'caption': self.caption,
            'exif': self.exif,
            'is_photo': self.is_photo,
            'is_mainimg': self.is_mainimg,
            'onlinecopies': self.onlinecopies
        }

    def __str__(self):
        if len(self.mdimg.css):
            return self.mdimg.match
        tmpl = J2.get_template("%s.j2.html" % (self.__class__.__name__))
        return tmpl.render(self.tmplvars)

    @cached_property
    def visionapi(self):
        return GoogleVision(self.fpath, self.src)

    @property
    def onlinecopies(self):
        copies = {}
        for m in self.visionapi.onlinecopies:
            if settings.site.get('domain') not in m:
                copies[m] = True
        return copies.keys()

    @cached_property
    def meta(self):
        return Exif(self.fpath)

    @property
    def caption(self):
        if len(self.mdimg.alt):
            return self.mdimg.alt
        else:
            return self.meta.get('Description', '')

    @property
    def title(self):
        if len(self.mdimg.title):
            return self.mdimg.title
        else:
            return self.meta.get('Headline', self.fname)

    @property
    def tags(self):
        return list(set(self.meta.get('Subject', [])))

    @property
    def published(self):
        return arrow.get(
            self.meta.get('ReleaseDate', self.meta.get('ModifyDate'))
        )

    @property
    def width(self):
        return int(self.meta.get('ImageWidth'))

    @property
    def height(self):
        return int(self.meta.get('ImageHeight'))

    @property
    def mime_type(self):
        return str(self.meta.get('MIMEType', 'image/jpeg'))

    @property
    def mime_size(self):
        return os.path.getsize(self.linked.fpath)

    @property
    def displayed(self):
        ret = self.resized_images[0][1]
        for size, r in self.resized_images:
            if size == settings.photo.get('default'):
                ret = r
        return ret

    @property
    def linked(self):
        m = 0
        ret = self.resized_images[0][1]
        for size, r in self.resized_images:
            if size > m:
                m = size
                ret = r
        return ret

    @property
    def src(self):
        return self.displayed.url

    @property
    def href(self):
        return self.linked.url

    @property
    def is_photo(self):
        r = settings.photo.get('re_author', None)
        if not r:
            return False
        cpr = self.meta.get('Copyright', '')
        art = self.meta.get('Artist', '')
        # both Artist and Copyright missing from EXIF
        if not cpr and not art:
            return False
        # we have regex, Artist and Copyright, try matching them
        if r.search(cpr) or r.search(art):
            return True
        return False

    @property
    def exif(self):
        exif = {
            'camera': '',
            'aperture': '',
            'shutter_speed': '',
            'focallength': '',
            'iso': '',
            'lens': '',
            'geo_latitude': '',
            'geo_longitude': '',
        }
        if not self.is_photo:
            return exif

        mapping = {
            'camera': ['Model'],
            'aperture': ['FNumber', 'Aperture'],
            'shutter_speed': ['ExposureTime'],
            # 'focallength':      ['FocalLengthIn35mmFormat', 'FocalLength'],
            'focallength': ['FocalLength'],
            'iso': ['ISO'],
            'lens': ['LensID', 'LensSpec', 'Lens'],
            'geo_latitude': ['GPSLatitude'],
            'geo_longitude': ['GPSLongitude'],
        }

        for ekey, candidates in mapping.items():
            for candidate in candidates:
                maybe = self.meta.get(candidate, None)
                if not maybe:
                    continue
                elif 'geo_' in ekey:
                    exif[ekey] = round(float(maybe), 5)
                else:
                    exif[ekey] = maybe
                break
        return exif

    def _maybe_watermark(self, img):
        if not self.is_photo:
            return img

        wmarkfile = settings.paths.get('watermark')
        if not os.path.exists(wmarkfile):
            return img

        with wand.image.Image(filename=wmarkfile) as wmark:
            if self.width > self.height:
                w = self.width * 0.2
                h = wmark.height * (w / wmark.width)
                x = self.width - w - (self.width * 0.01)
                y = self.height - h - (self.height * 0.01)
            else:
                w = self.height * 0.16
                h = wmark.height * (w / wmark.width)
                x = self.width - h - (self.width * 0.01)
                y = self.height - w - (self.height * 0.01)

            w = round(w)
            h = round(h)
            x = round(x)
            y = round(y)

            wmark.resize(w, h)
            if self.width <= self.height:
                wmark.rotate(-90)
            img.composite(image=wmark, left=x, top=y)
        return img

    async def downsize(self):
        need = False
        for size, resized in self.resized_images:
            if not resized.exists or settings.args.get('regenerate'):
                need = True
                break
        if not need:
            return

        with wand.image.Image(filename=self.fpath) as img:
            img.auto_orient()
            img = self._maybe_watermark(img)
            for size, resized in self.resized_images:
                if not resized.exists or settings.args.get('regenerate'):
                    logger.info(
                        "resizing image: %s to size %d",
                        os.path.basename(self.fpath),
                        size
                    )
                    await resized.make(img)

    class Resized:
        def __init__(self, parent, size, crop=False):
            self.parent = parent
            self.size = size
            self.crop = crop

        @property
        def suffix(self):
            return settings.photo.get('sizes').get(self.size, '')

        @property
        def fname(self):
            return "%s%s%s" % (
                self.parent.fname,
                self.suffix,
                self.parent.fext
            )

        @property
        def fpath(self):
            return os.path.join(
                self.parent.parent.renderdir,
                self.fname
            )

        @property
        def url(self):
            return "%s/%s/%s" % (
                settings.site.get('url'),
                self.parent.parent.name,
                "%s%s%s" % (
                    self.parent.fname,
                    self.suffix,
                    self.parent.fext
                )
            )

        @property
        def relpath(self):
            return "%s/%s" % (
                self.parent.parent.renderdir.replace(
                    settings.paths.get('build'), ''
                ),
                self.fname
            )

        @property
        def exists(self):
            if os.path.isfile(self.fpath):
                if os.path.getmtime(self.fpath) >= self.parent.mtime:
                    return True
            return False

        @property
        def width(self):
            return self.dimensions[0]

        @property
        def height(self):
            return self.dimensions[1]

        @property
        def dimensions(self):
            width = self.parent.width
            height = self.parent.height
            size = self.size

            ratio = max(width, height) / min(width, height)
            horizontal = True if (width / height) >= 1 else False

            # panorama: reverse "horizontal" because the limit should be on
            # the shorter side, not the longer, and make it a bit smaller, than
            # the actual limit
            # 2.39 is the wide angle cinematic view: anything wider, than that
            # is panorama land
            if ratio > 2.4 and not self.crop:
                size = int(size * 0.6)
                horizontal = not horizontal

            if (horizontal and not self.crop) \
                    or (not horizontal and self.crop):
                w = size
                h = int(float(size / width) * height)
            else:
                h = size
                w = int(float(size / height) * width)
            return (w, h)

        async def make(self, original):
            if not os.path.isdir(os.path.dirname(self.fpath)):
                os.makedirs(os.path.dirname(self.fpath))

            with original.clone() as thumb:
                thumb.resize(self.width, self.height)

                if self.crop:
                    thumb.liquid_rescale(self.size, self.size, 1, 1)

                if self.parent.meta.get('FileType', 'jpeg').lower() == 'jpeg':
                    thumb.compression_quality = 88
                    thumb.unsharp_mask(
                        radius=1,
                        sigma=0.5,
                        amount=0.7,
                        threshold=0.5
                    )
                    thumb.format = 'pjpeg'

                # this is to make sure pjpeg happens
                with open(self.fpath, 'wb') as f:
                    logger.info("writing %s", self.fpath)
                    thumb.save(file=f)


class PHPFile(object):
    @property
    def exists(self):
        if settings.args.get('force'):
            return False
        if not os.path.exists(self.renderfile):
            return False
        if self.mtime > os.path.getmtime(self.renderfile):
            return False
        return True

    @property
    def mtime(self):
        return os.path.getmtime(
            os.path.join(
                settings.paths.get('tmpl'),
                self.templatefile
            )
        )

    @property
    def renderfile(self):
        raise ValueError('Not implemented')

    @property
    def templatefile(self):
        raise ValueError('Not implemented')

    async def render(self):
        if self.exists:
            return
        await self._render()


class Search(PHPFile):
    def __init__(self):
        self.fpath = os.path.join(
            settings.paths.get('build'),
            'search.sqlite'
        )
        self.db = sqlite3.connect(self.fpath)
        self.db.execute('PRAGMA auto_vacuum = INCREMENTAL;')
        self.db.execute('PRAGMA journal_mode = MEMORY;')
        self.db.execute('PRAGMA temp_store = MEMORY;')
        self.db.execute('PRAGMA locking_mode = NORMAL;')
        self.db.execute('PRAGMA synchronous = FULL;')
        self.db.execute('PRAGMA encoding = "UTF-8";')
        self.db.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS data USING fts4(
                url,
                mtime,
                name,
                title,
                category,
                content,
                notindexed=category,
                notindexed=url,
                notindexed=mtime,
                tokenize=porter
            )'''
        )
        self.is_changed = False

    def __exit__(self):
        if self.is_changed:
            self.db.commit()
            self.db.execute('PRAGMA auto_vacuum;')
        self.db.close()

    def check(self, name):
        ret = 0
        maybe = self.db.execute('''
            SELECT
                mtime
            FROM
                data
            WHERE
                name = ?
        ''', (name,)).fetchone()
        if maybe:
            ret = int(maybe[0])
        return ret

    def append(self, post):
        mtime = int(post.mtime)
        check = self.check(post.name)
        if (check and check < mtime):
            self.db.execute('''
            DELETE
            FROM
                data
            WHERE
                name=?''', (post.name,))
            check = False
        if not check:
            self.db.execute('''
                INSERT INTO
                    data
                    (url, mtime, name, title, category, content)
                VALUES
                    (?,?,?,?,?,?);
            ''', (
                post.url,
                mtime,
                post.name,
                post.title,
                post.category,
                post.content
            ))
            self.is_changed = True

    @property
    def renderfile(self):
        return os.path.join(
            settings.paths.get('build'),
            'search.php'
        )

    @property
    def templatefile(self):
        return 'Search.j2.php'

    async def _render(self):
        r = J2.get_template(self.templatefile).render({
            'post': {},
            'site': settings.site,
            'author': settings.author,
            'meta': settings.meta,
            'licence': settings.licence,
            'tips': settings.tips,
        })
        writepath(self.renderfile, r)


class IndexPHP(PHPFile):
    def __init__(self):
        self.gone = {}
        self.redirect = {}

    def add_gone(self, uri):
        self.gone[uri] = True

    def add_redirect(self, source, target):
        if target in self.gone:
            self.add_gone(source)
        else:
            if '://' not in target:
                target = "%s/%s" % (settings.site.get('url'), target)
            self.redirect[source] = target

    @property
    def renderfile(self):
        return os.path.join(
            settings.paths.get('build'),
            'index.php'
        )

    @property
    def templatefile(self):
        return 'Index.j2.php'

    async def _render(self):
        r = J2.get_template(self.templatefile).render({
            'post': {},
            'site': settings.site,
            'gones': self.gone,
            'redirects': self.redirect
        })
        writepath(self.renderfile, r)


class WebhookPHP(PHPFile):
    @property
    def renderfile(self):
        return os.path.join(
            settings.paths.get('build'),
            'webhook.php'
        )

    @property
    def templatefile(self):
        return 'Webhook.j2.php'

    async def _render(self):
        r = J2.get_template(self.templatefile).render({
            'author': settings.author,
            'webmentionio': keys.webmentionio,
            'zapier': keys.zapier,
        })
        writepath(self.renderfile, r)


class MicropubPHP(PHPFile):
    @property
    def renderfile(self):
        return os.path.join(
            settings.paths.get('build'),
            'micropub.php'
        )

    @property
    def templatefile(self):
        return 'Micropub.j2.php'

    async def _render(self):
        r = J2.get_template(self.templatefile).render({
            'site': settings.site,
            'paths': settings.paths
        })
        writepath(self.renderfile, r)


class Category(dict):
    def __init__(self, name=''):
        self.name = name
        self.page = 1
        self.trange = 'YYYY'

    def __setitem__(self, key, value):
        if key in self:
            raise LookupError(
                "key '%s' already exists, colliding posts are: %s vs %s" % (
                    key,
                    self[key].fpath,
                    value.fpath,
                )
            )
        dict.__setitem__(self, key, value)

    @property
    def sortedkeys(self):
        return list(sorted(self.keys(), reverse=True))

    @property
    def display(self):
        return settings.categorydisplay.get(self.name, '')

    @property
    def title(self):
        if len(self.name):
            return "%s - %s" % (self.name, settings.site.get('domain'))
        else:
            return settings.site.get('title')

    @property
    def url(self):
        if len(self.name):
            url = "%s/category/%s/" % (settings.site.get('url'), self.name)
        else:
            url = '%s/' % (settings.site.get('url'))
        return url

    @property
    def feedurl(self):
        return "%sfeed/" % (self.url)

    @property
    def template(self):
        return "%s.j2.html" % (self.__class__.__name__)

    @property
    def dpath(self):
        if len(self.name):
            return os.path.join(
                settings.paths.get('build'),
                'category',
                self.name
            )
        else:
            return settings.paths.get('build')

    @property
    def mtime(self):
        return arrow.get(self[self.sortedkeys[0]].published).timestamp

    @property
    def rssfeedfpath(self):
        return os.path.join(
            self.dpath,
            'feed',
            'index.xml'
        )

    @property
    def atomfeedfpath(self):
        return os.path.join(
            self.dpath,
            'feed',
            'atom.xml'
        )

    def get_posts(self, start=0, end=-1):
        return [
            self[k].tmplvars
            for k in self.sortedkeys[start:end]
        ]

    def is_uptodate(self, fpath, ts):
        if settings.args.get('force'):
            return False
        if not os.path.exists(fpath):
            return False
        if os.path.getmtime(fpath) >= ts:
            return True
        return False

    def newest(self, start=0, end=-1):
        if start == end:
            end = -1
        s = sorted(
            [self[k].mtime for k in self.sortedkeys[start:end]],
            reverse=True
        )
        return s[0]

    def navlink(self, ts):
        label = ts.format(self.trange)
        if arrow.utcnow().format(self.trange) == label:
            url = self.url
        else:
            url = "%s%s/" % (self.url, label)
        return {
            'url': url,
            'label': label
        }

    def tmplvars(self, posts=[], c=False, p=False, n=False):
        if p:
            p = self.navlink(p)

        if n:
            n = self.navlink(n)

        if not c:
            post = self[list(self.keys()).pop()]
            c = post.published.format(self.trange)

        return {
            'site': settings.site,
            'author': settings.author,
            'meta': settings.meta,
            'licence': settings.licence,
            'tips': settings.tips,
            'category': {
                'name': self.name,
                'display': self.display,
                'url': self.url,
                'feed': self.feedurl,
                'title': self.title,
                'current': c,
                'previous': p,
                'next': n,
                'currentyear': arrow.utcnow().format('YYYY')
            },
            'posts': posts,
        }

    def indexfpath(self, subpath=None):
        if subpath:
            return os.path.join(
                self.dpath,
                subpath,
                'index.html'
            )
        else:
            return os.path.join(
                self.dpath,
                'index.html'
            )

    async def render_feed(self, xmlformat):
        logger.info(
            'rendering category "%s" %s feed',
            self.name,
            xmlformat
        )
        start = 0
        end = int(settings.site.get('pagination'))

        fg = FeedGenerator()
        fg.id(self.feedurl)
        fg.title(self.title)
        fg.author({
            'name': settings.author.get('name'),
            'email': settings.author.get('email')
        })
        fg.logo('%s/favicon.png' % settings.site.get('url'))
        fg.updated(arrow.get(self.mtime).to('utc').datetime)
        fg.description(settings.site.get('title'))

        for post in reversed(self.get_posts(start, end)):
            dt = arrow.get(post.get('pubtime'))
            mtime = arrow.get(post.get('mtime'))
            fe = fg.add_entry()

            fe.id(post.get('url'))
            fe.title(post.get('title'))

            fe.author({
                'name': settings.author.get('name'),
                'email': settings.author.get('email')
            })

            fe.category({
                'term': post.get('category'),
                'label': post.get('category'),
                'scheme': "%s/category/%s/" % (
                    settings.site.get('url'),
                    post.get('category')
                )
            })

            fe.published(dt.datetime)
            fe.updated(mtime.datetime)

            fe.rights('%s %s %s' % (
                post.get('licence').upper(),
                settings.author.get('name'),
                dt.format('YYYY')
            ))

            if xmlformat == 'rss':
                fe.link(href=post.get('url'))
                fe.content(post.get('html_content'), type='CDATA')
                #fe.description(post.get('summary'), isSummary=True)
                if 'enclosure' in post:
                    enc = post.get('enclosure')
                    fe.enclosure(
                        enc.get('url'),
                        "%d" % enc.get('size'),
                        enc.get('mime')
                    )
            elif xmlformat == 'atom':
                fe.link(
                    href=post.get('url'),
                    rel='alternate',
                    type='text/html')
                fe.content(src=post.get('url'), type='text/html')
                fe.summary(post.get('summary'))

        if xmlformat == 'rss':
            fg.link(href=self.feedurl)
            writepath(self.rssfeedfpath, fg.rss_str(pretty=True))
        elif xmlformat == 'atom':
            fg.link(href=self.feedurl, rel='self')
            fg.link(href=settings.meta.get('hub'), rel='hub')
            writepath(self.atomfeedfpath, fg.atom_str(pretty=True))

    async def render_flat(self):
        r = J2.get_template(self.template).render(
            self.tmplvars(self.get_posts())
        )
        writepath(self.indexfpath(), r)

    async def render_archives(self):
        by_time = {}
        for key in self.sortedkeys:
            trange = arrow.get(key).format(self.trange)
            if trange not in by_time:
                by_time.update({
                    trange: []
                })
            by_time[trange].append(key)

        keys = list(by_time.keys())
        for p, c, n in zip([None] + keys[:-1], keys, keys[1:] + [None]):
            form = c.format(self.trange)
            if arrow.utcnow().format(self.trange) == form:
                fpath = self.indexfpath()
            else:
                fpath = self.indexfpath(form)

            try:
                findex = self.sortedkeys.index(by_time[c][0])
                lindex = self.sortedkeys.index(by_time[c][-1])
                newest = self.newest(findex, lindex)
            except Exception as e:
                logger.error(
                    'calling newest failed with %s for %s',
                    self.name,
                    c
                )
                continue

            if self.is_uptodate(fpath, newest):
                logger.info(
                    '%s/%s index is up to date',
                    self.name,
                    form
                )
                continue
            else:
                logger.info(
                    '%s/%s index is outdated, generating new',
                    self.name,
                    form
                )
                r = J2.get_template(self.template).render(
                    self.tmplvars(
                        [self[k].tmplvars for k in by_time[c]],
                        c=c,
                        p=p,
                        n=n
                    )
                )
                writepath(fpath, r)

    async def render(self):
        newest = self.newest()
        if not self.is_uptodate(self.rssfeedfpath, newest):
            logger.info(
                '%s RSS feed outdated, generating new',
                self.name
            )
            await self.render_feed('rss')
        else:
            logger.info(
                '%s RSS feed up to date',
                self.name
            )

        if not self.is_uptodate(self.atomfeedfpath, newest):
            logger.info(
                '%s ATOM feed outdated, generating new',
                self.name
            )
            await self.render_feed('atom')
        else:
            logger.info(
                '%s ATOM feed up to date',
                self.name
            )

        if self.display == 'flat':
            if not self.is_uptodate(self.indexfpath(), newest):
                logger.info(
                    '%s flat index outdated, generating new',
                    self.name
                )
                await self.render_flat()
            else:
                logger.info(
                    '%s flat index is up to date',
                    self.name
                )
            return
        else:
            await self.render_archives()


class Sitemap(dict):
    @property
    def mtime(self):
        r = 0
        if os.path.exists(self.renderfile):
            r = os.path.getmtime(self.renderfile)
        return r

    def append(self, post):
        self[post.url] = post.mtime

    @property
    def renderfile(self):
        return os.path.join(settings.paths.get('build'), 'sitemap.txt')

    async def render(self):
        if self.mtime >= sorted(self.values())[-1]:
            return
        with open(self.renderfile, 'wt') as f:
            f.write("\n".join(sorted(self.keys())))


class WebmentionIO(object):
    def __init__(self):
        self.params = {
            'token': '%s' % (keys.webmentionio.get('token')),
            'since': '%s' % self.since.format(settings.dateformat.get('iso')),
            'domain': '%s' % (keys.webmentionio.get('domain'))
        }
        self.url = 'https://webmention.io/api/mentions'

    @property
    def since(self):
        newest = 0
        content = settings.paths.get('content')
        for e in glob.glob(os.path.join(content, '*', '*', '*.md')):
            if os.path.basename(e) == 'index.md':
                continue
            # filenames are like [received epoch]-[slugified source url].md
            try:
                mtime = int(os.path.basename(e).split('-')[0])
            except Exception as exc:
                logger.error(
                    'int conversation failed: %s, file was: %s',
                    exc,
                    e
                )
                continue
            if mtime > newest:
                newest = mtime
        return arrow.get(newest+1)

    def makecomment(self, webmention):
        if 'published_ts' in webmention.get('data'):
            maybe = webmention.get('data').get('published')
            if not maybe or maybe == 'None':
                dt = arrow.get(webmention.get('verified_date'))
            else:
                dt = arrow.get(webmention.get('data').get('published'))

        slug = webmention.get('target').strip('/').split('/')[-1]
        # ignore selfpings
        if slug == settings.site.get('domain'):
            return

        fdir = glob.glob(os.path.join(settings.paths.get('content'), '*', slug))
        if not len(fdir):
            logger.error(
                "couldn't find post for incoming webmention: %s",
                webmention
            )
            return
        elif len(fdir) > 1:
            logger.error(
                "multiple posts found for incoming webmention: %s",
                webmention
            )
            return

        fdir = fdir.pop()
        fpath = os.path.join(
            fdir,
            "%d-%s.md" % (
                dt.timestamp,
                url2slug(webmention.get('source'))
            )
        )

        meta = {
            'author': {
                'name': webmention.get('data').get('author').get('name', ''),
                'url': webmention.get('data').get('author').get('url', ''),
                'photo': webmention.get('data').get('author').get('photo', '')
            },
            'date': dt.format(settings.dateformat.get('iso')),
            'source': webmention.get('source'),
            'target': webmention.get('target'),
            'type': webmention.get('activity').get('type', 'webmention')
        }

        r = "---\n%s\n---\n\n%s\n" % (
            utfyamldump(meta),
            webmention.get('data').get('content', '').strip()
        )
        writepath(fpath, r)

    def run(self):
        webmentions = requests.get(self.url, params=self.params)
        logger.info("queried webmention.io with: %s", webmentions.url)
        if webmentions.status_code != requests.codes.ok:
            return
        try:
            mentions = webmentions.json()
            for webmention in mentions.get('links'):
                self.makecomment(webmention)
        except ValueError as e:
            logger.error('failed to query webmention.io: %s', e)
            pass

def make():
    start = int(round(time.time() * 1000))
    last = 0

    # this needs to be before collecting the 'content' itself
    if not settings.args.get('nosync'):
        incoming = WebmentionIO()
        incoming.run()

    queue = AQ()
    send = []

    content = settings.paths.get('content')
    rules = IndexPHP()

    micropub = MicropubPHP()
    queue.put(micropub.render())

    webhook = WebhookPHP()
    queue.put(webhook.render())

    sitemap = Sitemap()
    search = Search()
    categories = {}
    frontposts = Category()
    categories['/'] = frontposts

    for e in sorted(glob.glob(os.path.join(content, '*', '*', 'index.md'))):
        post = Singular(e)
        # deal with images, if needed
        for i in post.images.values():
            queue.put(i.downsize())
        for i in post.to_ping:
            send.append(i)

        # render and arbitrary file copy tasks for this very post
        queue.put(post.render())
        queue.put(post.copyfiles())

        # skip draft posts from anything further
        if post.is_future:
            continue

        # add post to search database
        search.append(post)

        # start populating sitemap
        sitemap.append(post)

        # populate redirects, if any
        rules.add_redirect(post.shortslug, post.url)

        # any category starting with '_' are special: they shouldn't have a
        # category archive page
        if post.is_page:
            continue

        # populate the category with the post
        if post.category not in categories:
            categories[post.category] = Category(post.category)
        categories[post.category][post.published.timestamp] = post

        # add to front, if allowed
        if post.is_front:
            frontposts[post.published.timestamp] = post

    # commit to search database - this saves quite a few disk writes
    search.__exit__()

    # render search and sitemap
    queue.put(search.render())
    queue.put(sitemap.render())

    # make gone and redirect arrays for PHP
    for e in glob.glob(os.path.join(content, '*', '*.del')):
        post = Gone(e)
        rules.add_gone(post.source)
    for e in glob.glob(os.path.join(content, '*', '*.url')):
        post = Redirect(e)
        rules.add_redirect(post.source, post.target)
    # render 404 fallback PHP
    queue.put(rules.render())

    # render categories
    for category in categories.values():
        queue.put(category.render())

    # actually run all the render & copy tasks
    queue.run()

    # copy static files
    for e in glob.glob(os.path.join(content, '*.*')):
        t = os.path.join(settings.paths.get('build'),os.path.basename(e))
        if os.path.exists(t) and os.path.getmtime(e) <= os.path.getmtime(t):
            continue
        cp(e, t)

    end = int(round(time.time() * 1000))
    logger.info('process took %d ms' % (end - start))

    if not settings.args.get('nosync'):
        # upload site
        logger.info('starting syncing')
        os.system(
            "rsync -avuhH --delete-after %s/ %s/" % (
                settings.paths.get('build'),
                '%s/%s' % (settings.syncserver,
                           settings.paths.get('remotewww'))
            )
        )
        logger.info('syncing finished')

    if not settings.args.get('nosync'):
        logger.info('sending webmentions')
        for wm in send:
            queue.put(wm.send())
        queue.run()
        logger.info('sending webmentions finished')


if __name__ == '__main__':
    make()
