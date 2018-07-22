#!/usr/bin/env python3

__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2018, Peter Molnar"
__license__ = "GNU LGPLv3 "
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import glob
import os
import time
from functools import lru_cache as cached
import re
import imghdr
import logging
import asyncio
import sqlite3
from shutil import copy2 as cp
from math import ceil
from urllib.parse import urlparse
from collections import OrderedDict, namedtuple
import arrow
import langdetect
import wand.image
import jinja2
import frontmatter
import markdown
from feedgen.feed import FeedGenerator
from bleach import clean
from emoji import UNICODE_EMOJI
import exiftool
import settings

from pprint import pprint

MarkdownImage = namedtuple(
    'MarkdownImage',
    ['match', 'alt', 'fname', 'title', 'css']
)

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

RE_HTTP = re.compile(
    r'^https?://',
    re.IGNORECASE
)

MD = markdown.Markdown(
    output_format='xhtml5',
    extensions=[
        'extra',
        'codehilite',
        'headerid',
        'urlize'
    ],
)

class MarkdownDoc(object):
    @property
    @cached()
    def _parsed(self):
        with open(self.fpath, mode='rt') as f:
            logging.debug('parsing YAML+MD file %s', self.fpath)
            meta, txt = frontmatter.parse(f.read())
        return(meta, txt)

    @property
    def meta(self):
        return self._parsed[0]

    @property
    def content(self):
        return self._parsed[1]

    @property
    @cached()
    def html_content(self):
        c = "%s" % (self.content)
        if hasattr(self, 'images') and len(self.images):
            for match, img in self.images.items():
                c = c.replace(match, str(img))
        return MD.reset().convert(c)


class Comment(MarkdownDoc):
    def __init__(self, fpath):
        self.fpath = fpath

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
        self.address, self.fext = os.path.splitext(
            os.path.basename(self.fpath)
        )

    @property
    def nginx(self):
        return (self.address, 'return 410')


class Redirect(object):
    """
    Redirect object for entries that moved
    """

    def __init__(self, fpath):
        self.fpath = fpath
        self.source, self.fext = os.path.splitext(os.path.basename(self.fpath))

    @property
    @cached()
    def target(self):
        target = ''
        with open(self.fpath, 'rt') as f:
            target = f.read().strip()
        if not RE_HTTP.match(target):
            target = "%s/%s" % (settings.site.get('url'), target)
        return target

    @property
    def nginx(self):
        return (self.source, 'return 301 %s' % (self.target))


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
    @cached()
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

    @property
    @cached()
    def comments(self):
        """
        An dict of Comment objects keyed with their path, populated from the
        same directory level as the Singular objects
        """
        comments = OrderedDict()
        files = [
            k
            for k in glob.glob(os.path.join(os.path.dirname(self.fpath), '*.md'))
            if os.path.basename(k) != 'index.md'
        ]
        for f in files:
            c = Comment(f)
            comments[c.dt.timestamp] = c
        return comments

    @property
    @cached()
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
        maybe = self.fpath.replace("index.md", "%s.jpg" % (self.name))
        if maybe in self.images and self.images[maybe].is_photo:
            return True
        return False

    @property
    def summary(self):
        return self.meta.get('summary', '')

    @property
    @cached()
    def html_summary(self):
        return markdown.Markdown(
            output_format='html5',
            extensions=[
                'extra',
                'codehilite',
                'headerid',
            ],
        ).convert(self.summary)

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
        return urls

    # def baseN(self, num, b=36,
        # numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
        # """
        # Creates short, lowercase slug for a number (an epoch) passed
        # """
        #num = int(num)
        # return ((num == 0) and numerals[0]) or (
        # self.baseN(
        #num // b,
        # b,
        # numerals
        # ).lstrip(numerals[0]) + numerals[num % b]
        # )

    # @property
    # def shortslug(self):
        # return self.baseN(self.published.timestamp)

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
            if c.type in ['webmention', 'in-reply-to']:
                r[mtime] = c.tmplvars
        return r

    @property
    def reactions(self):
        r = OrderedDict()
        for mtime, c in self.comments.items():
            if c.type in ['webmention', 'in-reply-to']:
                continue
            t = "%s" % (c.type)
            if t not in r:
                r[t] = OrderedDict()
            r[t][mtime] = c.tmplvars
        return r

    @property
    @cached()
    def tmplvars(self):
        return {
            'title': self.title,
            'category': self.category,
            'lang': self.lang,
            'slug': self.name,
            'is_reply': self.is_reply,
            'summary': self.summary,
            'html_summary': self.html_summary,
            'html_content': self.html_content,
            'pubtime': self.published.format(settings.dateformat.get('iso')),
            'pubdate': self.published.format(settings.dateformat.get('display')),
            'year': int(self.published.format('YYYY')),
            'licence': self.licence,
            'replies': self.replies,
            'reactions': self.reactions,
            'syndicate': self.syndicate,
            'url': self.url,
        }

    @property
    def template(self):
        return "%s.j2.html" % (self.__class__.__name__)

    @property
    def renderdir(self):
        return os.path.join(
            settings.paths.get('build'),
            self.name
        )

    @property
    def renderfile(self):
        return os.path.join(self.renderdir, 'index.html')

    @property
    def exists(self):
        if settings.args.get('force'):
            return False
        elif not os.path.exists(self.renderfile):
            return False
        elif self.mtime > os.path.getmtime(self.renderfile):
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

    async def render(self):
        if self.exists:
            return
        r = J2.get_template(self.template).render({
            'post': self.tmplvars,
            'site': settings.site,
            'author': settings.author,
            'meta': settings.meta,
            'licence': settings.licence,
            'tips': settings.tips,
            'labels': settings.labels
        })
        if not os.path.isdir(self.renderdir):
            logging.info("creating directory: %s", self.renderdir)
            os.makedirs(self.renderdir)
        with open(self.renderfile, 'wt') as f:
            logging.info("rendering to %s", self.renderfile)
            f.write(r)


class WebImage(object):
    def __init__(self, fpath, mdimg, parent):
        logging.debug("loading image: %s", fpath)
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

    def __str__(self):
        if len(self.mdimg.css):
            return self.mdimg.match
        tmpl = J2.get_template("%s.j2.html" % (self.__class__.__name__))
        return tmpl.render({
            'src': self.displayed.relpath,
            'href': self.linked.relpath,
            'width': self.displayed.width,
            'height': self.displayed.height,
            'title': self.title,
            'caption': self.caption,
            'exif': self.exif,
            'is_photo': self.is_photo,
        })

    @property
    @cached()
    def meta(self):
        return exiftool.Exif(self.fpath)

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
                    logging.info(
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
                    thumb.compression_quality = 94
                    thumb.unsharp_mask(
                        radius=1,
                        sigma=0.5,
                        amount=0.7,
                        threshold=0.5
                    )
                    thumb.format = 'pjpeg'

                # this is to make sure pjpeg happens
                with open(self.fpath, 'wb') as f:
                    logging.info("writing %s", self.fpath)
                    thumb.save(file=f)


class AsyncWorker(object):
    def __init__(self):
        self._tasks = []
        self._loop = asyncio.get_event_loop()

    def append(self, job):
        task = self._loop.create_task(job)
        self._tasks.append(task)

    def run(self):
        w = asyncio.wait(self._tasks, return_when=asyncio.FIRST_EXCEPTION)
        self._loop.run_until_complete(w)


class NginxConf(dict):
    def __str__(self):
        r = ''
        for key in self:
            r = "%slocation /%s { %s; }\n" % (r, key, self[key])
        return r

    def save(self):
        fpath = os.path.join(
            settings.paths.get('build'),
            '.nginx.conf'
        )
        with open(fpath, 'wt') as f:
            f.write(str(self))


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
            url = "/category/%s/" % (self.name)
        else:
            url = '/'
        return url

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

    @property
    def tmplvars(self):
        return {
            'name': self.name,
            'display': self.display,
            'url': self.url,
            'feed': "%s%s/" % (self.url, 'feed'),
            'title': self.title
        }

    @property
    def mtime(self):
        return self[self.sortedkeys[0]].mtime

    @property
    def exists(self):
        if settings.args.get('force'):
            return False
        renderfile = os.path.join(self.renderdir, 'index.html')
        if not os.path.exists(renderfile):
            return False
        elif self.mtime > os.path.getmtime(renderfile):
            return False
        else:
            return True

    def ping_websub(self):
        return
        # TODO aiohttp?
        ## ping pubsub
        #r = requests.post(
            #shared.site.get('websub').get('hub'),
            #data={
                #'hub.mode': 'publish',
                #'hub.url': flink
            #}
        #)
        #logging.info(r.text)

    def render_feed(self):
        logging.info('rendering category "%s" ATOM feed', self.name)
        start = 0
        end = int(settings.site.get('pagination'))

        dirname = os.path.join(self.renderdir,'feed')
        if not os.path.isdir(dirname):
            os.makedirs(dirname)

        fg = FeedGenerator()

        flink = "%s%sfeed/" % (settings.site.get('url'), self.url)

        fg.id(flink)
        fg.link(href=flink, rel='self')
        fg.title(self.title)

        fg.author({
            'name': settings.author.get('name'),
            'email': settings.author.get('email')
        })

        fg.logo('%s/favicon.png' % settings.site.get('url'))

        fg.updated(arrow.get(self.mtime).to('utc').datetime)

        for post in self.get_posts(start,end):
            dt = arrow.get(post.get('pubtime'))
            fe = fg.add_entry()
            fe.id(post.get('url'))
            fe.link(href=post.get('url'))
            fe.title(post.get('title'))
            fe.published(dt.datetime)
            fe.content(
                post.get('html_content'),
                type='CDATA'
            )

            fe.rights('%s %s %s' % (
                post.get('licence').upper(),
                settings.author.get('name'),
                dt.format('YYYY')
            ))
            #if p.get('enclosure'):
                #enclosure = p.get('enclosure')
                #fe.enclosure(
                    #enclosure.get('url'),
                    #"%d" % enclosure.get('size'),
                    #enclosure.get('mime')
                #)
        atom = os.path.join(dirname, 'index.xml')
        with open(atom, 'wb') as f:
            logging.info('writing file: %s', atom)
            f.write(fg.atom_str(pretty=True))


    def render_page(self, pagenum=1, pages=1):
        if self.display == 'flat':
            start = 1
            end = -1
        else:
            pagination = int(settings.site.get('pagination'))
            start = int((pagenum - 1) * pagination)
            end = int(start + pagination)

        posts = self.get_posts(start, end)
        r = J2.get_template(self.template).render({
            'site': settings.site,
            'author': settings.author,
            'meta': settings.meta,
            'licence': settings.licence,
            'tips': settings.tips,
            'labels': settings.labels,
            'category': self.tmplvars,
            'pages': {
                'current': pagenum,
                'total': pages,
            },
            'posts': posts,
        })
        if pagenum > 1:
            renderdir = os.path.join(self.renderdir, 'page', str(pagenum))
        else:
            renderdir = self.renderdir
        if not os.path.isdir(renderdir):
            os.makedirs(renderdir)
        renderfile = os.path.join(renderdir, 'index.html')
        with open(renderfile, 'wt') as f:
            f.write(r)

    async def render(self):
        if self.exists:
            return

        if self.display == 'flat':
            pagination = len(self)
        else:
            pagination = int(settings.site.get('pagination'))

        pages = ceil(len(self) / pagination)
        page = 1
        while page <= pages:
            self.render_page(page, pages)
            page = page + 1
        self.render_feed()
        self.ping_websub()

class Search(object):
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

    def append(self, url, mtime, name, title, category, content):
        # TODO: delete if mtime differs
        mtime = int(mtime)
        self.db.execute('''
            INSERT OR IGNORE INTO data
            (url, mtime, name, title, category, content)
            VALUES (?,?,?,?,?,?);
        ''', (
            url,
            mtime,
            name,
            title,
            category,
            content
        ))

    async def render(self):
        r = J2.get_template('Search.j2.php').render({
            'post': {},
            'site': settings.site,
            'author': settings.author,
            'meta': settings.meta,
            'licence': settings.licence,
            'tips': settings.tips,
            'labels': settings.labels
        })
        target = os.path.join(
            settings.paths.get('build'),
            'search.php'
        )
        with open(target, 'wt') as f:
            logging.info("rendering to %s", target)
            f.write(r)


def make():
    start = int(round(time.time() * 1000))
    content = settings.paths.get('content')

    nginxrules = NginxConf()
    for e in glob.glob(os.path.join(content, '*', '*.lnk')):
        post = Redirect(e)
        location, rule = post.nginx
        nginxrules[location] = rule
    for e in glob.glob(os.path.join(content, '*', '*.ptr')):
        post = Gone(e)
        location, rule = post.nginx
        nginxrules[location] = rule
    nginxrules.save()

    worker = AsyncWorker()
    categories = {}
    categories['/'] = Category()
    sitemap = OrderedDict()
    search = Search()

    for e in sorted(glob.glob(os.path.join(content, '*', '*', 'index.md'))):
        post = Singular(e)
        if post.category not in categories:
            categories[post.category] = Category(post.category)
        c = categories[post.category]
        c[post.published.timestamp] = post
        if post.is_front:
            c = categories['/']
            c[post.published.timestamp] = post
        for i in post.images.values():
            worker.append(i.downsize())
        worker.append(post.render())
        sitemap[post.url] = post.mtime
        search.append(
            url=post.url,
            mtime=post.mtime,
            name=post.name,
            title=post.title,
            category=post.category,
            content=post.content
        )

    search.__exit__()
    worker.append(search.render())
    for category in categories.values():
        worker.append(category.render())

    worker.run()
    logging.info('worker finished')

    # copy static
    for e in glob.glob(os.path.join(content, '*.*')):
        t = os.path.join(
            settings.paths.get('build'),
            os.path.basename(e)
        )
        if os.path.exists(t) and os.path.getmtime(e) <= os.path.getmtime(t):
            continue
        cp(e, t)

    # dump sitemap
    t = os.path.join(settings.paths.get('build'), 'sitemap.txt')
    with open(t, 'wt') as f:
        f.write("\n".join(sorted(sitemap.keys())))



    end = int(round(time.time() * 1000))
    logging.info('process took %d ms' % (end - start))

if __name__ == '__main__':
    make()
