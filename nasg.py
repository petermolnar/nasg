#!/usr/bin/env python3
import _json

__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2018, Peter Molnar"
__license__ = "GNU LGPLv3 "
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
from shutil import copy2 as cp
from math import ceil
from urllib.parse import urlparse
from collections import OrderedDict, namedtuple
import arrow
import langdetect
import wand.image
import jinja2
import frontmatter
from feedgen.feed import FeedGenerator
from bleach import clean
from emoji import UNICODE_EMOJI
from slugify import slugify
import requests
from pandoc import Pandoc
from exiftool import Exif
import settings
import keys

from pprint import pprint

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

#def relurl(url,base=settings.site.get('url')):
    #url =urlparse(url)
    #base = urlparse(base)

    #if base.netloc != url.netloc:
        #raise ValueError('target and base netlocs do not match')

    #base_dir='.%s' % (os.path.dirname(base.path))
    #url = '.%s' % (url.path)
    #return os.path.relpath(url,start=base_dir)

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

class Webmention(object):
    def __init__(self, source, target, stime):
        self.source = source
        self.target = target
        self.stime = stime

    @property
    def fpath(self):
        return os.path.join(
            settings.paths.get('webmentions'),
            '%s => %s.txt' % (
                url2slug(self.source, 100),
                url2slug(self.target, 100)
            )
        )

    @property
    def exists(self):
        if not os.path.isfile(self.fpath):
            return False
        elif os.path.getmtime(self.fpath) > self.stime:
            return True
        else:
            return False

    async def save(self, content):
        d = os.path.dirname(self.fpath)
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(self.fpath, 'wt') as f:
            f.write(content)

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
        settings.logger.info(
            "sent webmention to telegraph from %s to %s",
            self.source,
            self.target
        )
        if r.status_code not in [200, 201, 202]:
            settings.logger.error('sending failed: %s %s', r.status_code, r.text)
        else:
            await self.save(r.text)


class MarkdownDoc(object):
    @cached_property
    def _parsed(self):
        with open(self.fpath, mode='rt') as f:
            settings.logger.debug('parsing YAML+MD file %s', self.fpath)
            meta, txt = frontmatter.parse(f.read())
        return(meta, txt)

    @property
    def meta(self):
        return self._parsed[0]

    @property
    def content(self):
        return self._parsed[1]

    def __pandoc(self, c):
        c = Pandoc(c)
        c = RE_PRECODE.sub('<pre><code lang="\g<1>" class="language-\g<1>">', c)
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
        if maybe:
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
            if not k.endswith('.md') and not k.startswith('.')
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
        # return MD.reset().convert(self.summary)
        return Pandoc(self.summary)

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
            w = Webmention(self.url, self.is_reply, self.mtime)
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

    @cached_property
    def tmplvars(self):
        v = {
            'title': self.title,
            'category': self.category,
            'lang': self.lang,
            'slug': self.name,
            'is_reply': self.is_reply,
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

    @cached_property
    def renderdir(self):
        d = os.path.join(
            settings.paths.get('build'),
            self.name
        )
        if not os.path.isdir(d):
            os.makedirs(d)
        return d

    @property
    def renderfile(self):
        return os.path.join(self.renderdir, 'index.html')

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

    #async def update(self):
        #fm = frontmatter.loads('')
        #fm.metadata = self.meta
        #fm.content = self.content
        #with open(fpath, 'wt') as f:
            #settings.logger.info("updating %s", fpath)
            #f.write(frontmatter.dumps(fm))

    async def copyfiles(self):
        exclude=['.md', '.jpg', '.png', '.gif'];
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
            if os.path.exists(t) and os.path.getmtime(f) <= os.path.getmtime(t):
                continue
            settings.logger.info("copying '%s' to '%s'", f, t)
            cp(f, t)

    async def render(self):
        if self.exists:
            return
        settings.logger.info("rendering %s", self.name)
        r = J2.get_template(self.template).render({
            'post': self.tmplvars,
            'site': settings.site,
            'author': settings.author,
            'meta': settings.meta,
            'licence': settings.licence,
            'tips': settings.tips,
        })
        if not os.path.isdir(self.renderdir):
            settings.logger.info("creating directory: %s", self.renderdir)
            os.makedirs(self.renderdir)
        with open(self.renderfile, 'wt') as f:
            settings.logger.info("saving to %s", self.renderfile)
            f.write(r)


class WebImage(object):
    def __init__(self, fpath, mdimg, parent):
        settings.logger.debug("loading image: %s", fpath)
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
            'is_mainimg': self.is_mainimg
        }

    def __str__(self):
        if len(self.mdimg.css):
            return self.mdimg.match
        tmpl = J2.get_template("%s.j2.html" % (self.__class__.__name__))
        return tmpl.render(self.tmplvars)

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
                    settings.logger.info(
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
                    settings.logger.info("writing %s", self.fpath)
                    thumb.save(file=f)


class AsyncWorker(object):
    def __init__(self):
        self._tasks = []
        self._loop = asyncio.get_event_loop()

    def add(self, job):
        task = self._loop.create_task(job)
        self._tasks.append(task)

    def run(self):
        self._loop.run_until_complete(asyncio.wait(self._tasks))

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

    def __exit__(self):
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

    def append(self, url, mtime, name, title, category, content):
        mtime = int(mtime)
        check = self.check(name)
        if (check and check < mtime):
            self.db.execute('''
            DELETE
            FROM
                data
            WHERE
                name=?''', (name,))
            check = False
        if not check:
            self.db.execute('''
                INSERT INTO
                    data
                    (url, mtime, name, title, category, content)
                VALUES
                    (?,?,?,?,?,?);
            ''', (
                url,
                mtime,
                name,
                title,
                category,
                content
            ))

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
        with open(self.renderfile, 'wt') as f:
            settings.logger.info("rendering to %s", self.renderfile)
            f.write(r)


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
        with open(self.renderfile, 'wt') as f:
            settings.logger.info("rendering to %s", self.renderfile)
            f.write(r)


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
        with open(self.renderfile, 'wt') as f:
            settings.logger.info("rendering to %s", self.renderfile)
            f.write(r)


class Category(dict):
    def __init__(self, name=''):
        self.name = name
        self.page = 1

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

    # TODO
    # - find all months posts were made on
    # - use this to iterate
    # - make a function to query per month
    # - make archives based on this
    # - instead of plain numbers, use YYYY-MM
    # - feed still needs last X

    def get_posts(self, start=0, end=-1):
        return [
            self[k].tmplvars
            for k in self.sortedkeys[start:end]
        ]

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
    def feed(self):
        return "%sfeed/" % (self.url)

    @property
    def template(self):
        return "%s.j2.html" % (self.__class__.__name__)

    @property
    def renderdir(self):
        if len(self.name):
            return os.path.join(
                settings.paths.get('build'),
                'category',
                self.name
            )
        else:
            return settings.paths.get('build')

    def tmplvars(self, posts=[], c=False, p=False, n=False):
        if p:
            p = {
                'url': "%s%s/" % (self.url, p.format('YYYY')),
                'label': p.format('YYYY')
            }

        if n:
            n = {
                'url': "%s%s/" % (self.url, n.format('YYYY')),
                'label': n.format('YYYY')
            }

        if not c:
            c = self[0].published.format('YYYY')

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
                'feed': "%s%s/" % (self.url, 'feed'),
                #'jsonfeed': "%s%s/index.json" % (self.url, 'feed'),
                'title': self.title,
                'current': c,
                'previous': p,
                'next': n,
            },
            'posts': posts,
        }

    @property
    def mtime(self):
        return arrow.get(self[self.sortedkeys[0]].published).timestamp

    @property
    def exists(self):
        if settings.args.get('force'):
            return False
        ismissing = False
        for f in [
            os.path.join(self.renderdir, 'feed', 'index.xml'),
        ]:
            if not os.path.exists(f):
                ismissing = True
            elif self.mtime > os.path.getmtime(f):
                ismissing = True
        if ismissing:
            return False
        else:
            return True

    async def render_feeds(self):
        await self.render_rss();
        await self.render_atom();

    async def render_rss(self):
        await self.render_feed('rss')

    async def render_atom(self):
        await self.render_feed('atom')

    async def render_feed(self, xmlformat):
        settings.logger.info(
            'rendering category "%s" %s feed',
            self.name,
            xmlformat
        )
        start = 0
        end = int(settings.site.get('pagination'))

        dirname = os.path.join(self.renderdir, 'feed')
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

        fg = FeedGenerator()
        fg.id(self.feed)
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
                'email':settings.author.get('email')
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
                fe.link(href=post.get('url'), rel='alternate', type='text/html')
                fe.content(src=post.get('url'), type='text/html')
                fe.summary(post.get('summary'))

        if xmlformat == 'rss':
            fg.link(href=self.feed)
            feedfile = os.path.join(dirname, 'index.xml')
        elif xmlformat == 'atom':
            fg.link(href=self.feed, rel='self')
            fg.link(href=settings.meta.get('hub'), rel='hub')

            feedfile = os.path.join(dirname, 'atom.xml')

        with open(feedfile, 'wb') as f:
            settings.logger.info('writing file: %s', feedfile)
            if xmlformat == 'rss':
                f.write(fg.rss_str(pretty=True))
            elif xmlformat == 'atom':
                f.write(fg.atom_str(pretty=True))

    async def render_flat(self):
        r = J2.get_template(self.template).render(
            self.tmplvars([self[k].tmplvars for k in self.sortedkeys])
        )

        renderfile = os.path.join(self.renderdir, 'index.html')
        with open(renderfile, 'wt') as f:
            f.write(r)


    #async def render_page(self, tmplvars):


    # async def render_page(self, pagenum=1, pages=1):
        # if self.display == 'flat':
            # start = 0
            # end = -1
        # else:
            # pagination = int(settings.site.get('pagination'))
            # start = int((pagenum - 1) * pagination)
            # end = int(start + pagination)

        # posts = self.get_posts(start, end)
        # r = J2.get_template(self.template).render({
            # 'site': settings.site,
            # 'author': settings.author,
            # 'meta': settings.meta,
            # 'licence': settings.licence,
            # 'tips': settings.tips,
            # 'category': self.tmplvars,
            # 'pages': {
                # 'current': pagenum,
                # 'total': pages,
            # },
            # 'posts': posts,
        # })
        # if pagenum > 1:
            # renderdir = os.path.join(self.renderdir, 'page', str(pagenum))
        # else:
            # renderdir = self.renderdir
        # if not os.path.isdir(renderdir):
            # os.makedirs(renderdir)
        # renderfile = os.path.join(renderdir, 'index.html')
        # with open(renderfile, 'wt') as f:
            # f.write(r)

    async def render(self):
        if self.exists:
            return

        await self.render_feeds()
        if self.display == 'flat':
            await self.render_flat()
            return

        time_format = 'YYYY'
        by_time = {}
        for key in self.sortedkeys:
            trange = arrow.get(key).format(time_format)
            if trange not in by_time:
                by_time.update({
                    trange: []
                })
            by_time[trange].append(key)

        keys = list(by_time.keys())
        for p, c, n in zip([None]+keys[:-1], keys, keys[1:]+[None]):
            if arrow.utcnow().format(time_format) == c.format(time_format):
                renderdir = self.renderdir
            else:
                renderdir = os.path.join(
                    self.renderdir,
                    c.format(time_format)
                )
            #
            if not os.path.isdir(renderdir):
                os.makedirs(renderdir)
            renderfile = os.path.join(
                renderdir,
                'index.html'
            )

            r = J2.get_template(self.template).render(
                self.tmplvars(
                    [self[k].tmplvars for k in by_time[c]],
                    c=c,
                    p=p,
                    n=n
                )
            )
            with open(renderfile, 'wt') as f:
                settings.logger.info('writing category archive to: %s', renderfile)
                f.write(r)

class Sitemap(dict):
    @property
    def mtime(self):
        r = 0
        if os.path.exists(self.renderfile):
            r = os.path.getmtime(self.renderfile)
        return r

    @property
    def renderfile(self):
        return os.path.join(settings.paths.get('build'), 'sitemap.txt')

    async def render(self):
        if self.mtime >= sorted(self.values())[-1]:
            return
        with open(self.renderfile, 'wt') as f:
            f.write("\n".join(sorted(self.keys())))

def mkcomment(webmention):
    if 'published_ts' in webmention.get('data'):
        maybe = webmention.get('data').get('published')
        if not maybe or maybe == 'None':
            dt = arrow.get(webmention.get('verified_date'))
        else:
            dt = arrow.get(webmention.get('data').get('published'))

    slug = webmention.get('target').strip('/').split('/')[-1]

    fdir = glob.glob(os.path.join(settings.paths.get('content'), '*', slug))
    if not len(fdir):
        settings.logger.error(
            "couldn't find post for incoming webmention: %s",
            webmention
            )
        return
    elif len(fdir) > 1:
        settings.logger.error(
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

    fm = frontmatter.loads('')
    fm.metadata = {
        'author': webmention.get('data').get('author'),
        'date': dt.format(settings.dateformat.get('iso')),
        'source': webmention.get('source'),
        'target': webmention.get('target'),
        'type': webmention.get('activity').get('type', 'webmention')
    }
    c = webmention.get('data').get('content')
    if not c:
        fm.content = ''
    else:
        fm.content = c
    with open(fpath, 'wt') as f:
        settings.logger.info("saving webmention to %s", fpath)
        f.write(frontmatter.dumps(fm))


def makecomments():
    newest = 0
    content = settings.paths.get('content')
    for e in glob.glob(os.path.join(content, '*', '*', '*.md')):
        if os.path.basename(e) == 'index.md':
            continue
        # filenames are like [received epoch]-[slugified source url].md
        mtime = int(os.path.basename(e).split('-')[0])
        if mtime > newest:
            newest = mtime
    newest = arrow.get(newest)
    wio_params = {
        'token': '%s' % (keys.webmentionio.get('token')),
        'since': '%s' % newest.format(settings.dateformat.get('iso')),
        'domain': '%s' % (keys.webmentionio.get('domain'))
    }
    wio_url = "https://webmention.io/api/mentions"
    webmentions = requests.get(wio_url, params=wio_params)
    settings.logger.info("queried webmention.io with: %s", webmentions.url)
    if webmentions.status_code != requests.codes.ok:
        return
    try:
        mentions = webmentions.json()
        for webmention in mentions.get('links'):
            mkcomment(webmention)
    except ValueError as e:
        settings.logger.error('failed to query webmention.io: %s', e)
        pass


def url2slug(url, limit=200):
    return slugify(
        re.sub(r"^https?://(?:www)?", "", url),
        only_ascii=True,
        lower=True
    )[:limit]


def make():
    start = int(round(time.time() * 1000))
    last = 0

    makecomments()

    content = settings.paths.get('content')
    worker = AsyncWorker()
    webmentions = AsyncWorker()
    rules = IndexPHP()

    webhook = WebhookPHP()
    worker.add(webhook.render())

    sitemap = Sitemap()
    search = Search()
    categories = {}
    categories['/'] = Category()

    for e in sorted(glob.glob(os.path.join(content, '*', '*', 'index.md'))):
        post = Singular(e)
        for i in post.images.values():
            worker.add(i.downsize())
        for i in post.to_ping:
            webmentions.add(i.send())

        worker.add(post.render())
        worker.add(post.copyfiles())
        if post.is_future:
            continue
        search.append(
            url=post.url,
            mtime=post.mtime,
            name=post.name,
            title=post.title,
            category=post.category,
            content=post.content
        )
        sitemap[post.url] = post.mtime
        rules.add_redirect(post.shortslug, post.url)
        if post.category.startswith('_'):
            continue
        if post.category not in categories:
            categories[post.category] = Category(post.category)
        categories[post.category][post.published.timestamp] = post
        if post.is_front:
            categories['/'][post.published.timestamp] = post
        if post.ctime > last:
            last = post.ctime

    search.__exit__()
    worker.add(search.render())
    worker.add(sitemap.render())


    for e in glob.glob(os.path.join(content, '*', '*.ptr')):
        post = Gone(e)
        if post.mtime > last:
            last = post.mtime
        rules.add_gone(post.source)
    for e in glob.glob(os.path.join(content, '*', '*.url')):
        post = Redirect(e)
        if post.mtime > last:
            last = post.mtime
        rules.add_redirect(post.source, post.target)
    worker.add(rules.render())


    for category in categories.values():
        worker.add(category.render())

    worker.run()
    settings.logger.info('worker finished')

    # copy static
    staticfiles = []
    staticpaths = [
        os.path.join(content, '*.*'),
        #os.path.join(settings.paths.get('tmpl'), '*.js'),
        #os.path.join(settings.paths.get('tmpl'), '*.css')
    ]
    for p in staticpaths:
        staticfiles = staticfiles + glob.glob(p)
    for e in staticfiles:
        t = os.path.join(
            settings.paths.get('build'),
            os.path.basename(e)
        )
        if os.path.exists(t) and os.path.getmtime(e) <= os.path.getmtime(t):
            continue
        cp(e, t)

    end = int(round(time.time() * 1000))
    settings.logger.info('process took %d ms' % (end - start))

    if not settings.args.get('nosync'):
        settings.logger.info('starting syncing')
        os.system(
            "rsync -avuhH --delete-after %s/ %s/" % (
                settings.paths.get('build'),
                settings.syncserver
            )
        )
        settings.logger.info('syncing finished')

    settings.logger.info('sending webmentions')
    webmentions.run()
    settings.logger.info('sending webmentions finished')


if __name__ == '__main__':
    make()
