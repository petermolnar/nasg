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
import base64
from shutil import copy2 as cp
from math import ceil
from urllib.parse import urlparse
from collections import OrderedDict, namedtuple
import logging
import csv

import arrow
import langdetect
import wand.image
import jinja2
import yaml
import frontmatter
from feedgen.feed import FeedGenerator
from slugify import slugify
import requests
import lxml.etree as etree

from pandoc import PandocMD2HTML, PandocMD2TXT, PandocHTML2TXT
from meta import Exif
import settings
from settings import struct
import keys

logger = logging.getLogger('NASG')

CATEGORY = 'category'
MDFILE = 'index.md'
TXTFILE = 'index.txt'
HTMLFILE = 'index.html'
GOPHERFILE = 'gophermap'
ATOMFILE = 'atom.xml'
RSSFILE = 'index.xml'
JSONFEEDFILE = 'index.json'

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

RE_CODE = re.compile(
    r'^(?:[~`]{3,4}).+$',
    re.MULTILINE
)

RE_PRECODE = re.compile(
    r'<pre class="([^"]+)"><code>'
)

def mtime(path):
    """ return seconds level mtime or 0 (chomp microsecs) """
    if os.path.exists(path):
        return int(os.path.getmtime(path))
    return 0


def utfyamldump(data):
    """ dump YAML with actual UTF-8 chars """
    return yaml.dump(
        data,
        default_flow_style=False,
        indent=4,
        allow_unicode=True
    )


def url2slug(url, limit=200):
    """ convert URL to max 200 char ASCII string """
    return slugify(
        re.sub(r"^https?://(?:www)?", "", url),
        only_ascii=True,
        lower=True
    )[:limit]


J2.filters['url2slug'] = url2slug


def rfc3339todt(rfc3339):
    """ nice dates for humans """
    t = arrow.get(rfc3339).format('YYYY-MM-DD HH:mm ZZZ')
    return "%s" % (t)


J2.filters['printdate'] = rfc3339todt


def extractlicense(url):
    """ extract license name """
    n, e = os.path.splitext(os.path.basename(url))
    return n.upper()

J2.filters['extractlicense'] = extractlicense

RE_MYURL = re.compile(
    r'(^(%s[^"]+)$|"(%s[^"]+)")' % (
        settings.site.url,
        settings.site.url
    )
)


def relurl(text, baseurl=None):
    if not baseurl:
        baseurl = settings.site.url
    for match, standalone, href in RE_MYURL.findall(text):
        needsquotes = False
        if len(href):
            needsquotes = True
            url = href
        else:
            url = standalone

        r = os.path.relpath(url, baseurl)
        if url.endswith('/') and not r.endswith('/'):
            r = "%s/%s" % (r, HTMLFILE)
        if needsquotes:
            r = '"%s"' % r
        logger.debug("RELURL: %s => %s (base: %s)", match, r, baseurl)
        text = text.replace(match, r)
    return text


J2.filters['relurl'] = relurl


def writepath(fpath, content, mtime=0):
    """ f.write with extras """
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
    """ Async queue which starts execution right on population """

    def __init__(self):
        self.loop = asyncio.get_event_loop()
        self.queue = asyncio.Queue(loop=self.loop)

    def put(self, task):
        self.queue.put(asyncio.ensure_future(task))

    async def consume(self):
        while not self.queue.empty():
            item = await self.queue.get()
            self.queue.task_done()
        # asyncio.gather() ?

    def run(self):
        consumer = asyncio.ensure_future(self.consume())
        self.loop.run_until_complete(consumer)


class Webmention(object):
    """ outgoing webmention class """

    def __init__(self, source, target, dpath, mtime=0):
        self.source = source
        self.target = target
        self.dpath = dpath
        if not mtime:
            mtime = arrow.utcnow().timestamp
        self.mtime = mtime

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
        elif mtime(self.fpath) > self.mtime:
            return True
        else:
            return False

    def save(self, content):
        writepath(self.fpath, content)

    async def send(self):
        if self.exists:
            return
        elif settings.args.get('noping'):
            self.save("noping entry at %" %(arrow.now()))
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
    """ Base class for anything that is stored as .md """
    @property
    def mtime(self):
        return mtime(self.fpath)

    @property
    def dt(self):
        maybe = self.mtime
        for key in ['published', 'date']:
            t = self.meta.get(key, None)
            if t and 'null' != t:
                try:
                    t = arrow.get(t)
                    if t.timestamp > maybe:
                        maybe = t.timestamp
                except Exception as e:
                    logger.error(
                        'failed to parse date: %s for key %s in %s',
                        t,
                        key,
                        self.fpath
                    )
        return maybe

    @cached_property
    def _parsed(self):
        with open(self.fpath, mode='rt') as f:
            logger.debug('parsing YAML+MD file %s', self.fpath)
            meta, txt = frontmatter.parse(f.read())
        return(meta, txt)

    @cached_property
    def meta(self):
        return self._parsed[0]

    @cached_property
    def content(self):
        return self._parsed[1]

    @cached_property
    def html_content(self):
        c = "%s" % (self.content)
        if not len(c):
            return c

        if hasattr(self, 'images') and len(self.images):
            for match, img in self.images.items():
                c = c.replace(match, str(img))
        c = str(PandocMD2HTML(c))
        c = RE_PRECODE.sub(
            '<pre><code lang="\g<1>" class="language-\g<1>">',
            c
        )
        return c


class Comment(MarkdownDoc):
    def __init__(self, fpath):
        self.fpath = fpath

    @property
    def dt(self):
        maybe = self.meta.get('date')
        if maybe and 'null' != maybe:
            dt = arrow.get(maybe)
        else:
            dt = arrow.get(mtime(self.fpath))
        return dt

    @property
    def targetname(self):
        t = urlparse(self.meta.get('target'))
        return os.path.split(t.path.lstrip('/'))[0]
        #t = urlparse(self.meta.get('target'))
        #return t.path.rstrip('/').strip('/').split('/')[-1]

    @property
    def source(self):
        return self.meta.get('source')

    @property
    def author(self):
        r = {
            "@context": "http://schema.org",
            "@type": "Person",
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
        return self.meta.get('type', 'webmention')
        # if len(self.content):
        #maybe = clean(self.content, strip=True)
        # if maybe in UNICODE_EMOJI:
        # return maybe

    @cached_property
    def jsonld(self):
        r = {
            "@context": "http://schema.org",
            "@type": "Comment",
            "author": self.author,
            "url": self.source,
            "discussionUrl": self.meta.get('target'),
            "datePublished": str(self.dt),
            "disambiguatingDescription": self.type
        }
        return r


class Gone(object):
    """
    Gone object for delete entries
    """

    def __init__(self, fpath):
        self.fpath = fpath
        self.mtime = mtime(fpath)

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
            if not k.startswith('.')
        ]

    @property
    def updated(self):
        maybe = self.dt
        if len(self.comments):
            for c in self.comments.values():

                if c.dt > maybe:
                    maybe = c.dt
        return maybe


    @property
    def dt(self):
        dt = int(MarkdownDoc.dt.fget(self))
        for maybe in self.comments.keys():
            if int(dt) < int(maybe):
                dt = int(maybe)
        return dt

    @property
    def sameas(self):
        r = []
        for k in glob.glob(
            os.path.join(
                os.path.dirname(self.fpath),
                '*.copy'
            )
        ):
            with open(k, 'rt') as f:
                r.append(f.read())
        return r

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
            if os.path.basename(k) != MDFILE
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
            else:
                logger.error("Missing image: %s, referenced in %s",
                             imgpath,
                             self.fpath
                             )
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
        if self.category in settings.notinfeed:
            return False
        return True

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
        maybe = self.fpath.replace(MDFILE, "%s.jpg" % (self.name))
        if photo.fpath == maybe:
            return True
        return False

    @property
    def photo(self):
        if not self.is_photo:
            return None
        return next(iter(self.images.values()))

    @property
    def summary(self):
        return self.meta.get('summary', '')

    @cached_property
    def html_summary(self):
        c = "%s" % (self.summary)
        return PandocMD2HTML(c)

    @cached_property
    def txt_summary(self):
        return PandocMD2TXT(self.summary)

    @cached_property
    def txt_content(self):
        return PandocMD2TXT(self.content)

    @property
    def title(self):
        if self.is_reply:
            return "RE: %s" % self.is_reply
        return self.meta.get(
            'title',
            self.published.format(settings.displaydate)
        )

    @property
    def tags(self):
        return self.meta.get('tags', [])

    @property
    def syndicate(self):
        urls = self.meta.get('syndicate', [])
        urls.append("https://fed.brid.gy/")
        if self.is_photo:
            urls.append("https://brid.gy/publish/flickr")
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
        # ok, so here's a hack: because I have no idea when my older photos
        # were actually published, any photo from before 2014 will have
        # the EXIF createdate as publish date
        pub = arrow.get(self.meta.get('published'))
        if self.is_photo:
            maybe = arrow.get(self.photo.exif.get('CreateDate'))
            if maybe.year < settings.photo.earlyyears:
                pub = maybe
        return pub

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
        if not self.is_page and self.is_front:
            w = Webmention(
                self.url,
                'https://fed.brid.gy/',
                os.path.dirname(self.fpath),
                self.dt
            )
            urls.append(w)
        if self.is_reply:
            w = Webmention(
                self.url,
                self.is_reply,
                os.path.dirname(self.fpath),
                self.dt
            )
            urls.append(w)
        elif self.is_photo:
            w = Webmention(
                self.url,
                'https://brid.gy/publish/flickr/',
                os.path.dirname(self.fpath),
                self.dt
            )
            urls.append(w)
        return urls

    @property
    def licence(self):
        k = '_default'
        if self.category in settings.licence:
            k = self.category
        return settings.licence[k]

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
    def has_code(self):
        if RE_CODE.search(self.content):
            return True
        else:
            return False

    @cached_property
    def oembed_xml(self):
        oembed = etree.Element("oembed", version="1.0")
        xmldoc = etree.ElementTree(oembed)
        for k, v in self.oembed_json.items():
            x = etree.SubElement(oembed, k).text = "%s" % (v)
        s = etree.tostring(
            xmldoc,
            encoding='utf-8',
            xml_declaration=True,
            pretty_print=True
        )
        return s

    @cached_property
    def oembed_json(self):
        r = {
          "version": "1.0",
          "provider_name": settings.site.name,
          "provider_url": settings.site.url,
          "author_name": settings.author.name,
          "author_url": settings.author.url,
          "title": self.title,
          "type": "link",
          "html": self.html_content,
        }

        img = None
        if self.is_photo:
            img = self.photo
        elif not self.is_photo and len(self.images):
            img = list(self.images.values())[0]
        if img:
            r.update({
            "type": "rich",
            "thumbnail_url": img.jsonld.thumbnail.url,
            "thumbnail_width": img.jsonld.thumbnail.width,
            "thumbnail_height": img.jsonld.thumbnail.height
            })
        return r

    @cached_property
    def review(self):
        if 'review' not in self.meta:
            return False
        review = self.meta.get('review')
        rated, outof = review.get('rating').split('/')
        r = {
            "@context": "https://schema.org/",
            "@type": "Review",
            "reviewRating": {
                "@type": "Rating",
                "@context": "http://schema.org",
                "ratingValue": rated,
                "bestRating": outof,
                "worstRating": 1
            },
            "name": review.get('title'),
            "text": review.get('summary'),
            "url": review.get('url'),
            "author": settings.author,
        }
        return r

    @cached_property
    def event(self):
        if 'event' not in self.meta:
            return False
        event = self.meta.get('event', {})
        r = {
            "@context": "http://schema.org",
            "@type": "Event",
            "endDate": str(arrow.get(event.get('end'))),
            "startDate": str(arrow.get(event.get('start'))),
            "location": {
                "@context": "http://schema.org",
                "@type": "Place",
                "address": event.get('location'),
                "name": event.get('location'),
            },
            "name": self.title
        }
        return r

    @cached_property
    def jsonld(self):
        r = {
            "@context": "http://schema.org",
            "@type": "Article",
            "@id": self.url,
            "inLanguage": self.lang,
            "headline": self.title,
            "url": self.url,
            "genre": self.category,
            "mainEntityOfPage": "%s#article" % (self.url),
            "dateModified": str(arrow.get(self.dt)),
            "datePublished": str(self.published),
            "copyrightYear": str(self.published.format('YYYY')),
            "license": "https://spdx.org/licenses/%s.html" % (self.licence),
            "image": settings.site.image,
            "author": settings.author,
            "sameAs": self.sameas,
            "publisher": settings.site.publisher,
            "name": self.name,
            "text": self.html_content,
            "description": self.html_summary,
            "potentialAction": [],
            "comment": [],
            "commentCount": len(self.comments.keys()),
        }

        if self.is_photo:
            r.update({
                "@type": "Photograph",
                #"image": self.photo.jsonld,
            })
        elif self.has_code:
            r.update({
                "@type": "TechArticle",
            })
        elif self.is_page:
            r.update({
                "@type": "WebPage",
            })
        if len(self.images):
            r["image"] = []
            for img in list(self.images.values()):
                r["image"].append(img.jsonld)
        # if not self.is_photo and len(self.images):
            # img = list(self.images.values())[0]
            # r.update({
                # "image": img.jsonld,
            # })

        if self.is_reply:
            r.update({
                "mentions": {
                    "@context": "http://schema.org",
                    "@type": "Thing",
                    "url": self.is_reply
                }
            })

        if self.review:
            r.update({"review": self.review})

        if self.event:
            r.update({"subjectOf": self.event})

        #for donation in settings.donateActions:
            #r["potentialAction"].append(donation)

        for url in list(set(self.syndicate)):
            r["potentialAction"].append({
                "@context": "http://schema.org",
                "@type": "InteractAction",
                "url": url
            })

        for mtime in sorted(self.comments.keys()):
            r["comment"].append(self.comments[mtime].jsonld)

        return struct(r)

    @property
    def template(self):
        return "%s.j2.html" % (self.__class__.__name__)

    @property
    def gophertemplate(self):
        return "%s.j2.txt" % (self.__class__.__name__)

    @property
    def renderdir(self):
        return os.path.join(
            settings.paths.get('build'),
            self.name
        )

    @property
    def renderfile(self):
        return os.path.join(
            self.renderdir,
            HTMLFILE
        )

    @property
    def gopherfile(self):
        return os.path.join(
            self.renderdir,
            TXTFILE
        )

    @property
    def exists(self):
        if settings.args.get('force'):
            logger.debug('rendering required: force mode on')
            return False
        elif not os.path.exists(self.renderfile):
            logger.debug('rendering required: no html yet')
            return False
        elif self.dt > mtime(self.renderfile):
            logger.debug('rendering required: self.dt > html mtime')
            return False
        else:
            logger.debug('rendering not required')
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
        exclude = [
            '.md',
            '.jpg',
            '.png',
            '.gif',
            '.ping',
            '.url',
            '.del',
            '.copy']
        files = glob.glob(
            os.path.join(
                os.path.dirname(self.fpath),
                '*.*'
            )
        )
        for f in files:
            fname, fext = os.path.splitext(f)
            if fext.lower() in exclude:
                continue

            t = os.path.join(
                settings.paths.get('build'),
                self.name,
                os.path.basename(f)
            )
            if os.path.exists(t) and mtime(
                    f) <= mtime(t):
                continue
            logger.info("copying '%s' to '%s'", f, t)
            cp(f, t)

    async def render(self):
        if self.exists:
            return
        logger.info("rendering %s", self.name)
        v = {
            'baseurl': self.url,
            'post': self.jsonld,
            'site': settings.site,
            'menu': settings.menu,
            'meta': settings.meta,
        }
        writepath(
            self.renderfile,
            J2.get_template(self.template).render(v)
        )

        g = {
            'post': self.jsonld,
            'summary': self.txt_summary,
            'content': self.txt_content
        }
        writepath(
            self.gopherfile,
            J2.get_template(self.gophertemplate).render(g)
        )

        j = settings.site.copy()
        j.update({
            "mainEntity": self.jsonld
        })
        writepath(
            os.path.join(self.renderdir, 'index.json'),
            json.dumps(j, indent=4, ensure_ascii=False)
        )
        del(j)

class Home(Singular):
    def __init__(self, fpath):
        super().__init__(fpath)
        self.posts = []

    def add(self, category, post):
        self.posts.append((category.ctmplvars, post.jsonld))

    @property
    def renderdir(self):
        return settings.paths.get('build')

    @property
    def renderfile(self):
        return os.path.join(
            settings.paths.get('build'),
            HTMLFILE
        )

    @property
    def dt(self):
        maybe = super().dt
        for cat, post in self.posts:
            pts = arrow.get(post['dateModified']).timestamp
            if pts > maybe:
                maybe = pts
        return maybe

    async def render_gopher(self):
        lines = [
            "%s's gopherhole - phlog, if you prefer" % (settings.site.name),
            '',
            ''
        ]

        for category, post in self.posts:
            line = "1%s\t/%s/%s\t%s\t70" % (
                category['name'],
                CATEGORY,
                category['name'],
                settings.site.name
            )
            lines.append(line)
        lines.append('')
        #lines.append('')
        #lines = lines + list(settings.bye.split('\n'))
        #lines.append('')
        writepath(self.renderfile.replace(HTMLFILE,GOPHERFILE), "\r\n".join(lines))

    async def render(self):
        if self.exists:
            return
        logger.info("rendering %s", self.name)
        r = J2.get_template(self.template).render({
            'baseurl': settings.site.get('url'),
            'post': self.jsonld,
            'site': settings.site,
            'menu': settings.menu,
            'meta': settings.meta,
            'posts': self.posts
        })
        writepath(self.renderfile, r)
        await self.render_gopher()


class WebImage(object):
    def __init__(self, fpath, mdimg, parent):
        logger.debug("loading image: %s", fpath)
        self.mdimg = mdimg
        self.fpath = fpath
        self.parent = parent
        self.mtime = mtime(self.fpath)
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

    @property
    def jsonld(self):
        r = {
            "@context": "http://schema.org",
            "@type": "ImageObject",
            "url": self.href,
            "image": self.href,
            "thumbnail": struct({
                "@context": "http://schema.org",
                "@type": "ImageObject",
                "url": self.src,
                "width": self.displayed.width,
                "height": self.displayed.height,
            }),
            "name": os.path.basename(self.fpath),
            "encodingFormat": self.mime_type,
            "contentSize": self.mime_size,
            "width": self.linked.width,
            "height": self.linked.height,
            "dateCreated": self.exif.get('CreateDate'),
            "exifData": [],
            "caption": self.caption,
            "headline": self.title,
            "representativeOfPage": False
        }
        for k, v in self.exif.items():
            r["exifData"].append({
                "@type": "PropertyValue",
                "name": k,
                "value": v
            })
        if self.is_photo:
            r.update({
                "creator": settings.author,
                "copyrightHolder": settings.author,
                "license": settings.licence['_default']
            })
        if self.is_mainimg:
            r.update({"representativeOfPage": True})
        return struct(r)

    def __str__(self):
        if len(self.mdimg.css):
            return self.mdimg.match
        tmpl = J2.get_template("%s.j2.html" % (self.__class__.__name__))
        return tmpl.render(self.jsonld)

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
        try:
            size = os.path.getsize(self.linked.fpath)
        except Exception as e:
            logger.error('Failed to get mime size of %s', self.linked.fpath)
            size = self.meta.get('FileSize', 0)
        return size

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
            'Model': '',
            'FNumber': '',
            'ExposureTime': '',
            'FocalLength': '',
            'ISO': '',
            'LensID': '',
            'CreateDate': str(arrow.get(self.mtime))
        }
        if not self.is_photo:
            return exif

        mapping = {
            'Model': ['Model'],
            'FNumber': ['FNumber', 'Aperture'],
            'ExposureTime': ['ExposureTime'],
            'FocalLength': ['FocalLength'],  # ['FocalLengthIn35mmFormat'],
            'ISO': ['ISO'],
            'LensID': ['LensID', 'LensSpec', 'Lens'],
            'CreateDate': ['CreateDate', 'DateTimeOriginal']
        }

        for ekey, candidates in mapping.items():
            for candidate in candidates:
                maybe = self.meta.get(candidate, None)
                if not maybe:
                    continue
                else:
                    exif[ekey] = maybe
                break
        return struct(exif)

    def _maybe_watermark(self, img):
        if not self.is_photo:
            return img

        wmarkfile = settings.paths.get('watermark')
        if not os.path.exists(wmarkfile):
            return img

        with wand.image.Image(filename=wmarkfile) as wmark:
            w = self.height * 0.2
            h = wmark.height * (w / wmark.width)
            if self.width > self.height:
                x = self.width - w - (self.width * 0.01)
                y = self.height - h - (self.height * 0.01)
            else:
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
        def data(self):
            with open(self.fpath, 'rb') as f:
                encoded = base64.b64encode(f.read())
            return "data:%s;base64,%s" % (
                self.parent.mime_type, encoded.decode('utf-8'))

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
                if mtime(self.fpath) >= self.parent.mtime:
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
                        sigma=1,
                        amount=0.5,
                        threshold=0.1
                    )
                    thumb.format = 'pjpeg'

                # this is to make sure pjpeg happens
                with open(self.fpath, 'wb') as f:
                    logger.info("writing %s", self.fpath)
                    thumb.save(file=f)

                # n, e = os.path.splitext(os.path.basename(self.fpath))
                # webppath = self.fpath.replace(e, '.webp')
                # with open(webppath, 'wb') as f:
                    # logger.info("writing %s", webppath)
                    # thumb.format = 'webp'
                    # thumb.compression_quality = 88
                    # thumb.save(file=f)



class PHPFile(object):
    @property
    def exists(self):
        if settings.args.get('force'):
            return False
        if not os.path.exists(self.renderfile):
            return False
        if self.mtime > mtime(self.renderfile):
            return False
        return True

    @property
    def mtime(self):
        return mtime(
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
        # if self.exists:
            # return
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
            'menu': settings.menu,
            'meta': settings.meta,
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
        return '404.j2.php'

    async def _render(self):
        r = J2.get_template(self.templatefile).render({
            'post': {},
            'site': settings.site,
            'menu': settings.menu,
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
            'menu': settings.menu,
            'paths': settings.paths
        })
        writepath(self.renderfile, r)


class Category(dict):
    def __init__(self, name=''):
        self.name = name
        #self.page = 1
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
    def is_photos(self):
        r = True
        for i in self.values():
            r = r & i.is_photo
        return r

    @property
    def is_paginated(self):
        if self.name in settings.flat:
            return False
        return True

    @property
    def title(self):
        if len(self.name):
            return "%s - %s" % (self.name, settings.site.get('name'))
        else:
            return settings.site.get('headline')

    @property
    def url(self):
        if len(self.name):
            url = "%s/%s/%s/" % (settings.site.get('url'), CATEGORY, self.name)
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
                CATEGORY,
                self.name
            )
        else:
            return settings.paths.get('build')

    @property
    def newest_year(self):
        return int(self[self.sortedkeys[0]].published.format(self.trange))

    @property
    def years(self):
        years = {}
        for k in self.sortedkeys:
            y = int(self[k].published.format(self.trange))
            if y not in years:
                if y == self.newest_year:
                    url = self.url
                else:
                    url = "%s%d/" % (self.url, y)
                years.update({
                    y: url
                })
        return years

    @property
    def mtime(self):
        if len (self.sortedkeys) > 0:
            return self[self.sortedkeys[0]].published.timestamp
        else:
            return 0

    @property
    def rssfeedfpath(self):
        return os.path.join(
            self.dpath,
            'feed',
            RSSFILE
        )

    @property
    def atomfeedfpath(self):
        return os.path.join(
            self.dpath,
            'feed',
            ATOMFILE
        )

    @property
    def jsonfeedfpath(self):
        return os.path.join(
            self.dpath,
            'feed',
            JSONFEEDFILE
        )

    def get_posts(self, start=0, end=-1):
        return [
            self[k].jsonld
            for k in self.sortedkeys[start:end]
        ]

    def is_uptodate(self, fpath, ts):
        if settings.args.get('force'):
            return False
        if not os.path.exists(fpath):
            return False
        if mtime(fpath) >= ts:
            return True
        return False

    def newest(self, start=0, end=-1):
        if start == end:
            end = -1
        s = sorted(
            [self[k].dt for k in self.sortedkeys[start:end]],
            reverse=True
        )
        if len(s) > 0:
            return s[0] # Timestamp in seconds since epoch
        else:
            return 0

    @property
    def ctmplvars(self):
        return {
            'name': self.name,
            'url': self.url,
            'feed': self.feedurl,
            'title': self.title,
        }

    def tmplvars(self, posts=[], year=None):
        baseurl = self.url
        if year:
            baseurl = '%s%s/' % (baseurl, year)
        return {
            'baseurl': baseurl,
            'site': settings.site,
            'menu': settings.menu,
            'meta': settings.meta,
            'category': {
                'name': self.name,
                'paginated': self.is_paginated,
                'url': self.url,
                'feed': self.feedurl,
                'title': self.title,
                'year': year,
                'years': self.years,
            },
            'posts': posts,
        }

    def indexfpath(self, subpath=None, fname=HTMLFILE):
        if subpath:
            return os.path.join(
                self.dpath,
                subpath,
                fname
            )
        else:
            return os.path.join(
                self.dpath,
                fname
            )

    async def render_feed(self, xmlformat):
        logger.info(
            'rendering category "%s" %s feed',
            self.name,
            xmlformat
        )
        start = 0
        end = int(settings.pagination)

        fg = FeedGenerator()
        fg.id(self.feedurl)
        fg.title(self.title)
        fg.author({
            'name': settings.author.name,
            'email': settings.author.email
        })
        fg.logo('%s/favicon.png' % settings.site.get('url'))
        fg.updated(arrow.get(self.mtime).to('utc').datetime)
        fg.description(settings.site.get('headline'))

        for k in reversed(self.sortedkeys[start:end]):
            post = self[k]
            fe = fg.add_entry()

            fe.id(post.url)
            fe.title(post.title)
            fe.author({
                'name': settings.author.name,
                'email': settings.author.email
            })
            fe.category({
                'term': post.category,
                'label': post.category,
                'scheme': "%s/%s/%s/" % (
                    settings.site.get('url'),
                    CATEGORY,
                    post.category
                )
            })

            fe.published(post.published.datetime)
            fe.updated(arrow.get(post.dt).datetime)

            fe.rights('%s %s %s' % (
                post.licence.upper(),
                settings.author.name,
                post.published.format('YYYY')
            ))

            if xmlformat == 'rss':
                fe.link(href=post.url)
                fe.content(post.html_content, type='CDATA')
                if post.is_photo:
                    fe.enclosure(
                        post.photo.href,
                        "%d" % post.photo.mime_size,
                        post.photo.mime_type,
                    )
            elif xmlformat == 'atom':
                fe.link(
                    href=post.url,
                    rel='alternate',
                    type='text/html'
                )
                fe.content(src=post.url, type='text/html')
                fe.summary(post.summary)

        if xmlformat == 'rss':
            fg.link(href=self.feedurl)
            writepath(self.rssfeedfpath, fg.rss_str(pretty=True))
        elif xmlformat == 'atom':
            fg.link(href=self.feedurl, rel='self')
            fg.link(href=settings.meta.get('hub'), rel='hub')
            writepath(self.atomfeedfpath, fg.atom_str(pretty=True))

    async def render_json(self):
        logger.info(
            'rendering category "%s" JSON feed',
            self.name,
        )
        start = 0
        end = int(settings.pagination)

        js = {
            "version": "https://jsonfeed.org/version/1",
            "title": self.title,
            "home_page_url": settings.site.url,
            "feed_url": "%s%s" % (self.url, JSONFEEDFILE),
            "author": {
                "name": settings.author.name,
                "url": settings.author.url,
                "avatar": settings.author.image,
            },
            "items": []
        }

        for k in reversed(self.sortedkeys[start:end]):
            post = self[k]
            pjs = {
                "id": post.url,
                "content_text": post.txt_content,
                "content_html": post.html_content,
                "url": post.url,
                "date_published": str(post.published),
            }
            if len(post.summary):
                pjs.update({"summary": post.txt_summary})
            if post.is_photo:
                pjs.update({"attachment": {
                    "url": post.photo.href,
                    "mime_type": post.photo.mime_type,
                    "size_in_bytes": "%d" % post.photo.mime_size
                }})
            js["items"].append(pjs)
        writepath(
            self.jsonfeedfpath,
            json.dumps(js, indent=4, ensure_ascii=False)
        )

    async def render_flat(self):
        r = J2.get_template(self.template).render(
            self.tmplvars(self.get_posts())
        )
        writepath(self.indexfpath(), r)

    async def render_gopher(self):
        lines = [
            '%s - %s' % (self.name, settings.site.name),
            '',
            ''
        ]
        for post in self.get_posts():
            line = "0%s\t/%s/%s\t%s\t70" % (
                post.headline,
                post.name,
                TXTFILE,
                settings.site.name
            )
            lines.append(line)
            #lines.append(post.datePublished)
            if (len(post.description)):
                lines.extend(str(PandocHTML2TXT(post.description)).split("\n"))
            if isinstance(post['image'], list):
                for img in post['image']:
                    line = "I%s\t/%s/%s\t%s\t70" % (
                        img.headline,
                        post.name,
                        img.name,
                        settings.site.name
                    )
                    lines.append(line)
            lines.append('')
        writepath(self.indexfpath(fname=GOPHERFILE), "\r\n".join(lines))

    async def render_archives(self):
        for year in self.years.keys():
            if year == self.newest_year:
                fpath = self.indexfpath()
                tyear = None
            else:
                fpath = self.indexfpath("%d" % (year))
                tyear = year
            y = arrow.get("%d" % year, self.trange).to('utc')
            tsmin = y.floor('year').timestamp
            tsmax = y.ceil('year').timestamp
            start = len(self.sortedkeys)
            end = 0

            for index, value in enumerate(self.sortedkeys):
                if value <= tsmax and index < start:
                    start = index
                if value >= tsmin and index > end:
                    end = index

            if self.is_uptodate(fpath, self[self.sortedkeys[start]].dt):
                logger.info("%s / %d is up to date", self.name, year)
            else:
                logger.info("updating %s / %d", self.name, year)
                logger.info("getting posts from %d to %d", start, end)
                r = J2.get_template(self.template).render(
                    self.tmplvars(
                        # I don't know why end needs the +1, but without that
                        # some posts disappear
                        # TODO figure this out...
                        self.get_posts(start, end + 1),
                        tyear
                    )
                )
                writepath(fpath, r)

    async def render_feeds(self):
        if not self.is_uptodate(self.rssfeedfpath, self.newest()):
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

        if not self.is_uptodate(self.atomfeedfpath, self.newest()):
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

        if not self.is_uptodate(self.jsonfeedfpath, self.newest()):
            logger.info(
                '%s JSON feed outdated, generating new',
                self.name
            )
            await self.render_json()
        else:
            logger.info(
                '%s JSON feed up to date',
                self.name
            )


    async def render(self):
        await self.render_feeds()
        if not self.is_uptodate(self.indexfpath(), self.newest()):
            await self.render_gopher()
        if not self.is_paginated:
            if not self.is_uptodate(self.indexfpath(), self.newest()):
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
            r = mtime(self.renderfile)
        return r

    def append(self, post):
        self[post.url] = post.mtime

    @property
    def renderfile(self):
        return os.path.join(settings.paths.get('build'), 'sitemap.txt')

    async def render(self):
        if len(self) > 0:
            if self.mtime >= sorted(self.values())[-1]:
                return
            with open(self.renderfile, 'wt') as f:
                f.write("\n".join(sorted(self.keys())))


class WebmentionIO(object):
    def __init__(self):
        self.params = {
            'token': '%s' % (keys.webmentionio.get('token')),
            'since': '%s' % str(self.since),
            'domain': '%s' % (keys.webmentionio.get('domain'))
        }
        self.url = 'https://webmention.io/api/mentions'

    @property
    def since(self):
        newest = 0
        content = settings.paths.get('content')
        for e in glob.glob(os.path.join(content, '*', '*', '*.md')):
            if os.path.basename(e) == MDFILE:
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
        return arrow.get(newest + 1)

    def makecomment(self, webmention):
        if 'published_ts' in webmention.get('data'):
            maybe = webmention.get('data').get('published')
            if not maybe or maybe == 'None':
                dt = arrow.get(webmention.get('verified_date'))
            else:
                dt = arrow.get(webmention.get('data').get('published'))

        slug = os.path.split(urlparse(webmention.get('target')).path.lstrip('/'))[0]

        # ignore selfpings
        if slug == settings.site.get('name'):
            return

        fdir = glob.glob(
            os.path.join(
                settings.paths.get('content'),
                '*',
                slug
            )
        )
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

        author = webmention.get('data', {}).get('author', None)
        if not author:
            logger.error('missing author info on webmention; skipping')
            return
        meta = {
            'author': {
                'name': author.get('name', ''),
                'url': author.get('url', ''),
                'photo': author.get('photo', '')
            },
            'date': str(dt),
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


# class GranaryIO(dict):
    # granary = 'https://granary.io/url'
    # convert_to = ['as2', 'mf2-json', 'jsonfeed']

    # def __init__(self, source):
        # self.source = source

    # def run(self):
        # for c in self.convert_to:
            # p = {
                # 'url': self.source,
                # 'input': html,
                # 'output': c
            # }
            # r = requests.get(self.granary, params=p)
            # logger.info("queried granary.io for %s for url: %s", c, self.source)
            # if r.status_code != requests.codes.ok:
                # continue
            # try:
                # self[c] = webmentions.text
            # except ValueError as e:
                # logger.error('failed to query granary.io: %s', e)
                # pass


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
    home = Home(settings.paths.get('home'))

    for e in sorted(glob.glob(os.path.join(content, '*', '*', MDFILE))):
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
            logger.info('%s is for the future', post.name)
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
        home.add(category, category.get(category.sortedkeys[0]))
        queue.put(category.render())

    queue.put(frontposts.render_feeds())
    queue.put(home.render())
    # actually run all the render & copy tasks
    queue.run()

    # copy static files
    for e in glob.glob(os.path.join(content, '*.*')):
        if e.endswith('.md'):
            continue
        t = os.path.join(settings.paths.get('build'), os.path.basename(e))
        if os.path.exists(t) and mtime(e) <= mtime(t):
            continue
        cp(e, t)

    # ...
    #for url in settings.site.sameAs:
        #if "dat://" in url:
            #p = os.path.join(settings.paths.build, '.well-known', 'dat')
            #if not os.path.exists(p):
                #writepath(p, "%s\nTTL=3600" % (url))

    end = int(round(time.time() * 1000))
    logger.info('process took %d ms' % (end - start))

    if not settings.args.get('nosync'):
        # upload site
        try:
            logger.info('starting syncing')
            os.system(
                "rsync -avuhH --delete-after %s/ %s/" % (
                    settings.paths.get('build'),
                    '%s/%s' % (settings.syncserver,
                            settings.paths.get('remotewww'))
                )
            )
            logger.info('syncing finished')
        except Exception as e:
            logger.error('syncing failed: %s', e)

    if not settings.args.get('nosync'):
        logger.info('sending webmentions')
        for wm in send:
            queue.put(wm.send())
        queue.run()
        logger.info('sending webmentions finished')


if __name__ == '__main__':
    make()
