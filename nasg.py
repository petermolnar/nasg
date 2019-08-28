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
import asyncio
import sqlite3
import json

# import base64
from shutil import copy2 as cp
from urllib.parse import urlparse
from collections import namedtuple
import logging

import arrow
import langdetect
import wand.image
import filetype
import jinja2
import yaml

# python-frontmatter
import frontmatter
from feedgen.feed import FeedGenerator

# unicode-slugify
from slugify import slugify
import requests

from pandoc import PandocMD2HTML, PandocMD2TXT, PandocHTML2TXT
from meta import Exif
import settings
import keys
import wayback

logger = logging.getLogger("NASG")

MarkdownImage = namedtuple(
    "MarkdownImage", ["match", "alt", "fname", "title", "css"]
)

RE_MDIMG = re.compile(
    r"(?P<match>!\[(?P<alt>[^\]]+)?\]\((?P<fname>[^\s\]]+)"
    r"(?:\s[\'\"](?P<title>[^\"\']+)[\'\"])?\)(?:{(?P<css>[^\}]+)\})?)",
    re.IGNORECASE,
)

RE_CODE = re.compile(r"^(?:[~`]{3,4}).+$", re.MULTILINE)

RE_PRECODE = re.compile(r'<pre class="([^"]+)"><code>')

RE_MYURL = re.compile(
    r'(^(%s[^"]+)$|"(%s[^"]+)")'
    % (settings.site.url, settings.site.url)
)


def mtime(path):
    """ return seconds level mtime or 0 (chomp microsecs) """
    if os.path.exists(path):
        return int(os.path.getmtime(path))
    return 0


def utfyamldump(data):
    """ dump YAML with actual UTF-8 chars """
    return yaml.dump(
        data, default_flow_style=False, indent=4, allow_unicode=True
    )


def url2slug(url, limit=200):
    """ convert URL to max 200 char ASCII string """
    url = re.sub(r"^https?://(?:www)?", "", url)
    url = slugify(url, only_ascii=True, lower=True)
    return url[:limit]


def rfc3339todt(rfc3339):
    """ nice dates for humans """
    t = arrow.get(rfc3339).format("YYYY-MM-DD HH:mm ZZZ")
    return str(t)


def extractlicense(url):
    """ extract license name """
    n, e = os.path.splitext(os.path.basename(url))
    return n.upper()


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
        if url.endswith("/") and not r.endswith("/"):
            r = "%s/%s" % (r, settings.filenames.html)
        if needsquotes:
            r = '"%s"' % r
        logger.debug("RELURL: %s => %s (base: %s)", match, r, baseurl)
        text = text.replace(match, r)
    return text


def writepath(fpath, content, mtime=0):
    """ f.write with extras """
    d = os.path.dirname(fpath)
    if not os.path.isdir(d):
        logger.debug("creating directory tree %s", d)
        os.makedirs(d)
    if isinstance(content, str):
        mode = "wt"
    else:
        mode = "wb"
    with open(fpath, mode) as f:
        logger.info("writing file %s", fpath)
        f.write(content)


def maybe_copy(source, target):
    """ copy only if target mtime is smaller, than source mtime """
    if os.path.exists(target) and mtime(source) <= mtime(target):
        return
    logger.info("copying '%s' to '%s'", source, target)
    cp(source, target)


def extractdomain(url):
    url = urlparse(url)
    return url.hostname


J2 = jinja2.Environment(
    loader=jinja2.FileSystemLoader(
        searchpath=settings.paths.get("tmpl")
    ),
    lstrip_blocks=True,
    trim_blocks=True,
)
J2.filters["relurl"] = relurl
J2.filters["url2slug"] = url2slug
J2.filters["printdate"] = rfc3339todt
J2.filters["extractlicense"] = extractlicense
J2.filters["extractdomain"] = extractdomain


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


class Gone(object):
    """
    Gone object for delete entries
    """

    def __init__(self, fpath):
        self.fpath = fpath

    @property
    def mtime(self):
        return mtime(self.fpath)

    @property
    def exists(self):
        if (
            os.path.exists(self.renderfile)
            and mtime(self.renderfile) >= self.mtime
        ):
            return True
        return False

    @property
    def renderdir(self):
        return os.path.join(settings.paths.get("build"), self.source)

    @property
    def renderfile(self):
        return os.path.join(self.renderdir, settings.filenames.html)

    @property
    def source(self):
        source, fext = os.path.splitext(os.path.basename(self.fpath))
        return source

    @property
    def template(self):
        return "%s.j2.html" % (self.__class__.__name__)

    @property
    def tmplvars(self):
        return {"source": self.source}

    async def render(self):
        """ this is disabled for now """
        return

        # if self.exists:
        # return
        # logger.info("rendering %s to %s", self.__class__, self.renderfile)
        # writepath(
        # self.renderfile, J2.get_template(self.template).render()
        # )


class Redirect(Gone):
    """
    Redirect object for entries that moved
    """

    @cached_property
    def target(self):
        target = ""
        with open(self.fpath, "rt") as f:
            target = f.read().strip()
        return target

    @property
    def tmplvars(self):
        return {"source": self.source, "target": self.target}


class MarkdownDoc(object):
    """ Base class for anything that is stored as .md """

    def __init__(self, fpath):
        self.fpath = fpath

    @property
    def mtime(self):
        return mtime(self.fpath)

    @property
    def dt(self):
        """ returns an arrow object; tries to get the published date of the
        markdown doc. The pubdate can be in the future, which is why it's
        done the way it is """
        maybe = arrow.get(self.mtime)
        for key in ["published", "date"]:
            t = self.meta.get(key, None)
            if t and "null" != t:
                try:
                    t = arrow.get(t)
                    if t.timestamp > maybe.timestamp:
                        maybe = t
                except Exception as e:
                    logger.error(
                        "failed to parse date: %s for key %s in %s",
                        t,
                        key,
                        self.fpath,
                    )
                    continue
        return maybe

    @cached_property
    def _parsed(self):
        with open(self.fpath, mode="rt") as f:
            logger.debug("parsing YAML+MD file %s", self.fpath)
            meta, txt = frontmatter.parse(f.read())
        return (meta, txt)

    @cached_property
    def meta(self):
        return self._parsed[0]

    @cached_property
    def content(self):
        maybe = self._parsed[1]
        if not maybe or not len(maybe):
            maybe = str("")
        return maybe

    @cached_property
    def html_content(self):
        if not len(self.content):
            return self.content

        c = self.content
        if hasattr(self, "images") and len(self.images):
            for match, img in self.images.items():
                c = c.replace(match, str(img))
        c = str(PandocMD2HTML(c))
        c = RE_PRECODE.sub(
            '<pre><code lang="\g<1>" class="language-\g<1>">', c
        )
        return c

    @cached_property
    def txt_content(self):
        if not len(self.content):
            return ""
        else:
            return PandocMD2TXT(self.content)


class Comment(MarkdownDoc):
    @property
    def source(self):
        return self.meta.get("source")

    @property
    def author(self):
        r = {
            "@context": "http://schema.org",
            "@type": "Person",
            "name": urlparse(self.source).hostname,
            "url": self.source,
        }
        author = self.meta.get("author")
        if not author:
            return r
        if "name" in author:
            r.update({"name": self.meta.get("author").get("name")})
        elif "url" in author:
            r.update(
                {
                    "name": urlparse(
                        self.meta.get("author").get("url")
                    ).hostname
                }
            )
        return r

    @property
    def type(self):
        return self.meta.get("type", "webmention")

    @cached_property
    def jsonld(self):
        r = {
            "@context": "http://schema.org",
            "@type": "Comment",
            "author": self.author,
            "url": self.source,
            "discussionUrl": self.meta.get("target"),
            "datePublished": str(self.dt),
            "disambiguatingDescription": self.type,
        }
        return r


class WebImage(object):
    def __init__(self, fpath, mdimg, parent):
        logger.debug("loading image: %s", fpath)
        self.mdimg = mdimg
        self.fpath = fpath
        self.parent = parent
        self.mtime = mtime(self.fpath)
        self.name = os.path.basename(self.fpath)
        self.fname, self.fext = os.path.splitext(self.name)
        self.resized_images = [
            (k, self.Resized(self, k))
            for k in settings.photo.get("sizes").keys()
            if k < max(self.width, self.height)
        ]
        if not len(self.resized_images):
            self.resized_images.append(
                (
                    max(self.width, self.height),
                    self.Resized(self, max(self.width, self.height)),
                )
            )

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
            "thumbnail": settings.nameddict(
                {
                    "@context": "http://schema.org",
                    "@type": "ImageObject",
                    "url": self.src,
                    "width": self.displayed.width,
                    "height": self.displayed.height,
                }
            ),
            "name": self.name,
            "encodingFormat": self.mime_type,
            "contentSize": self.mime_size,
            "width": self.linked.width,
            "height": self.linked.height,
            "dateCreated": self.exif.get("CreateDate"),
            "exifData": [],
            "caption": self.caption,
            "headline": self.title,
            "representativeOfPage": False,
        }
        for k, v in self.exif.items():
            r["exifData"].append(
                {"@type": "PropertyValue", "name": k, "value": v}
            )
        if self.is_photo:
            r.update(
                {
                    "creator": settings.author,
                    "copyrightHolder": settings.author,
                    "license": settings.licence["_default"],
                }
            )
        if self.is_mainimg:
            r.update({"representativeOfPage": True})

        if (
            self.exif["GPSLatitude"] != 0
            and self.exif["GPSLongitude"] != 0
        ):
            r.update(
                {
                    "locationCreated": settings.nameddict(
                        {
                            "@context": "http://schema.org",
                            "@type": "Place",
                            "geo": settings.nameddict(
                                {
                                    "@context": "http://schema.org",
                                    "@type": "GeoCoordinates",
                                    "latitude": self.exif[
                                        "GPSLatitude"
                                    ],
                                    "longitude": self.exif[
                                        "GPSLongitude"
                                    ],
                                }
                            ),
                        }
                    )
                }
            )
        return settings.nameddict(r)

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
            return self.meta.get("Description", "")

    @property
    def title(self):
        if len(self.mdimg.title):
            return self.mdimg.title
        else:
            return self.meta.get("Headline", self.fname)

    @property
    def tags(self):
        return list(set(self.meta.get("Subject", [])))

    @property
    def published(self):
        return arrow.get(
            self.meta.get("ReleaseDate", self.meta.get("ModifyDate"))
        )

    @property
    def width(self):
        return int(self.meta.get("ImageWidth"))

    @property
    def height(self):
        return int(self.meta.get("ImageHeight"))

    @property
    def mime_type(self):
        return str(self.meta.get("MIMEType", "image/jpeg"))

    @property
    def mime_size(self):
        try:
            size = os.path.getsize(self.linked.fpath)
        except Exception as e:
            logger.error(
                "Failed to get mime size of %s", self.linked.fpath
            )
            size = self.meta.get("FileSize", 0)
        return size

    @property
    def displayed(self):
        ret = self.resized_images[0][1]
        for size, r in self.resized_images:
            if size == settings.photo.get("default"):
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
        r = settings.photo.get("re_author", None)
        if not r:
            return False
        cpr = self.meta.get("Copyright", "")
        art = self.meta.get("Artist", "")
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
            "Model": "",
            "FNumber": "",
            "ExposureTime": "",
            "FocalLength": "",
            "ISO": "",
            "LensID": "",
            "CreateDate": str(arrow.get(self.mtime)),
            "GPSLatitude": 0,
            "GPSLongitude": 0,
        }
        if not self.is_photo:
            return exif

        mapping = {
            "Model": ["Model"],
            "FNumber": ["FNumber", "Aperture"],
            "ExposureTime": ["ExposureTime"],
            "FocalLength": ["FocalLength"],
            "ISO": ["ISO"],
            "LensID": ["LensID", "LensSpec", "Lens"],
            "CreateDate": ["CreateDate", "DateTimeOriginal"],
            "GPSLatitude": ["GPSLatitude"],
            "GPSLongitude": ["GPSLongitude"],
        }

        for ekey, candidates in mapping.items():
            for candidate in candidates:
                maybe = self.meta.get(candidate, None)
                if not maybe:
                    continue
                else:
                    exif[ekey] = maybe
                break
        return settings.nameddict(exif)

    def _maybe_watermark(self, img):
        if not self.is_photo:
            return img

        wmarkfile = settings.paths.get("watermark")
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
            if not resized.exists or settings.args.get("regenerate"):
                need = True
                break
        if not need:
            return

        with wand.image.Image(filename=self.fpath) as img:
            img.auto_orient()
            img = self._maybe_watermark(img)
            for size, resized in self.resized_images:
                if not resized.exists or settings.args.get(
                    "regenerate"
                ):
                    logger.info(
                        "resizing image: %s to size %d",
                        os.path.basename(self.fpath),
                        size,
                    )
                    await resized.make(img)

    class Resized:
        def __init__(self, parent, size, crop=False):
            self.parent = parent
            self.size = size
            self.crop = crop

        # @property
        # def data(self):
        # with open(self.fpath, "rb") as f:
        # encoded = base64.b64encode(f.read())
        # return "data:%s;base64,%s" % (
        # self.parent.mime_type,
        # encoded.decode("utf-8"),
        # )

        @property
        def suffix(self):
            return settings.photo.get("sizes").get(self.size, "")

        @property
        def fname(self):
            return "%s%s%s" % (
                self.parent.fname,
                self.suffix,
                self.parent.fext,
            )

        @property
        def fpath(self):
            return os.path.join(
                self.parent.parent.renderdir, self.fname
            )

        @property
        def url(self):
            return "%s/%s/%s" % (
                settings.site.get("url"),
                self.parent.parent.name,
                "%s%s%s"
                % (self.parent.fname, self.suffix, self.parent.fext),
            )

        @property
        def relpath(self):
            return "%s/%s" % (
                self.parent.parent.renderdir.replace(
                    settings.paths.get("build"), ""
                ),
                self.fname,
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

            if (horizontal and not self.crop) or (
                not horizontal and self.crop
            ):
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

                if (
                    self.parent.meta.get("FileType", "jpeg").lower()
                    == "jpeg"
                ):
                    thumb.compression_quality = 88
                    thumb.unsharp_mask(
                        radius=1, sigma=0.5, amount=0.7, threshold=0.5
                    )
                    thumb.format = "pjpeg"

                # this is to make sure pjpeg happens
                with open(self.fpath, "wb") as f:
                    logger.info("writing %s", self.fpath)
                    thumb.save(file=f)


class Singular(MarkdownDoc):
    """
    A Singular object: a complete representation of a post, including
    all it's comments, files, images, etc
    """

    def __init__(self, fpath):
        self.fpath = fpath
        self.dirpath = os.path.dirname(fpath)
        self.name = os.path.basename(self.dirpath)
        self.category = os.path.basename(os.path.dirname(self.dirpath))

    @cached_property
    def files(self):
        """
        An array of files present at the same directory level as
        the Singular object, excluding hidden (starting with .) and markdown
        (ending with .md) files
        """
        return [
            k
            for k in glob.glob(os.path.join(self.dirpath, "*.*"))
            if not k.startswith(".")
        ]

    @cached_property
    def comments(self):
        """
        An dict of Comment objects keyed with their path, populated from the
        same directory level as the Singular objects
        """
        comments = {}
        for f in [
            k
            for k in glob.glob(os.path.join(self.dirpath, "*.md"))
            if (
                os.path.basename(k) != settings.filenames.md
                and not k.startswith(".")
            )
        ]:
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
        for match, alt, fname, title, css in RE_MDIMG.findall(
            self.content
        ):
            mdimg = MarkdownImage(match, alt, fname, title, css)
            imgpath = os.path.join(self.dirpath, fname)
            if imgpath in self.files:
                kind = filetype.guess(imgpath)
                if kind and "image" in kind.mime.lower():
                    images.update(
                        {match: WebImage(imgpath, mdimg, self)}
                    )
            else:
                logger.error(
                    "Missing image: %s, referenced in %s",
                    imgpath,
                    self.fpath,
                )
                continue
        return images

    @property
    def summary(self):
        return str(self.meta.get("summary", ""))

    @cached_property
    def html_summary(self):
        if not len(self.summary):
            return ""
        else:
            return PandocMD2HTML(self.summary)

    @cached_property
    def txt_summary(self):
        if not len(self.summary):
            return ""
        else:
            return PandocMD2TXT(self.summary)

    @property
    def published(self):
        # ok, so here's a hack: because I have no idea when my older photos
        # were actually published, any photo from before 2014 will have
        # the EXIF createdate as publish date
        pub = arrow.get(self.meta.get("published"))
        if self.is_photo:
            maybe = arrow.get(self.photo.exif.get("CreateDate"))
            if maybe.year < settings.photo.earlyyears:
                pub = maybe
        return pub

    @property
    def updated(self):
        if "updated" in self.meta:
            return arrow.get(self.meta.get("updated"))
        else:
            return self.dt

    @property
    def sameas(self):
        r = {}
        for k in glob.glob(os.path.join(self.dirpath, "*.copy")):
            with open(k, "rt") as f:
                r.update({f.read(): True})
        return list(r.keys())

    @property
    def is_page(self):
        """ all the categories starting with _ are pages """
        if self.category.startswith("_"):
            return True
        return False

    @property
    def is_front(self):
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
        maybe = self.fpath.replace(
            settings.filenames.md, "%s.jpg" % (self.name)
        )
        if photo.fpath == maybe:
            return True
        return False

    @property
    def is_reply(self):
        return self.meta.get("in-reply-to", False)

    @property
    def is_future(self):
        if self.published.timestamp > arrow.utcnow().timestamp:
            return True
        return False

    @property
    def photo(self):
        if not self.is_photo:
            return None
        return next(iter(self.images.values()))

    @property
    def title(self):
        if self.is_reply:
            return "RE: %s" % self.is_reply
        return self.meta.get(
            "title", self.published.format(settings.displaydate)
        )

    @property
    def tags(self):
        return self.meta.get("tags", [])

    def baseN(
        self, num, b=36, numerals="0123456789abcdefghijklmnopqrstuvwxyz"
    ):
        """
        Creates short, lowercase slug for a number (an epoch) passed
        """
        num = int(num)
        return ((num == 0) and numerals[0]) or (
            self.baseN(num // b, b, numerals).lstrip(numerals[0])
            + numerals[num % b]
        )

    @property
    def shortslug(self):
        return self.baseN(self.published.timestamp)

    @property
    def to_syndicate(self):
        urls = self.meta.get("syndicate", [])
        if not self.is_page:
            urls.append("https://fed.brid.gy/")
        if self.is_photo:
            urls.append("https://brid.gy/publish/flickr")
        return urls

    @property
    def to_ping(self):
        webmentions = []
        for url in self.to_syndicate:
            w = Webmention(
                self.url,
                url,
                os.path.dirname(self.fpath),
                self.dt.timestamp,
            )
            webmentions.append(w)
        if self.is_reply:
            w = Webmention(
                self.url,
                self.is_reply,
                os.path.dirname(self.fpath),
                self.dt.timestamp,
            )
            webmentions.append(w)
        return webmentions

    @property
    def licence(self):
        k = "_default"
        if self.category in settings.licence:
            k = self.category
        return settings.licence[k]

    @property
    def lang(self):
        lang = "en"
        try:
            lang = langdetect.detect(
                "\n".join([self.meta.get("title", ""), self.content])
            )
        except BaseException:
            pass
        return lang

    @property
    def url(self):
        return "%s/%s/" % (settings.site.get("url"), self.name)

    @property
    def has_code(self):
        if RE_CODE.search(self.content):
            return True
        else:
            return False

    @cached_property
    def review(self):
        if "review" not in self.meta:
            return False
        review = self.meta.get("review")
        rated, outof = review.get("rating").split("/")
        r = {
            "@context": "https://schema.org/",
            "@type": "Review",
            "reviewRating": {
                "@type": "Rating",
                "@context": "http://schema.org",
                "ratingValue": rated,
                "bestRating": outof,
                "worstRating": 1,
            },
            "name": review.get("title"),
            "text": review.get("summary"),
            "url": review.get("url"),
            "author": settings.author,
        }
        return r

    @cached_property
    def event(self):
        if "event" not in self.meta:
            return False
        event = self.meta.get("event", {})
        r = {
            "@context": "http://schema.org",
            "@type": "Event",
            "endDate": str(arrow.get(event.get("end"))),
            "startDate": str(arrow.get(event.get("start"))),
            "location": {
                "@context": "http://schema.org",
                "@type": "Place",
                "address": event.get("location"),
                "name": event.get("location"),
            },
            "name": self.title,
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
            "mainEntityOfPage": f"{self.url}#article",
            "dateModified": str(self.dt),
            "datePublished": str(self.published),
            "copyrightYear": str(self.published.format("YYYY")),
            "license": f"https://spdx.org/licenses/{self.licence}.html",
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
            "keywords": self.tags,
        }

        if self.is_photo:
            r.update({"@type": "Photograph"})
        elif self.has_code:
            r.update({"@type": "TechArticle"})
        elif self.is_page:
            r.update({"@type": "WebPage"})
        if len(self.images):
            r["image"] = []
            for img in list(self.images.values()):
                r["image"].append(img.jsonld)

        if self.is_reply:
            r.update(
                {
                    "mentions": {
                        "@context": "http://schema.org",
                        "@type": "Thing",
                        "url": self.is_reply,
                    }
                }
            )

        if self.review:
            r.update({"review": self.review})

        if self.event:
            r.update({"subjectOf": self.event})

        for url in list(set(self.to_syndicate)):
            r["potentialAction"].append(
                {
                    "@context": "http://schema.org",
                    "@type": "InteractAction",
                    "url": url,
                }
            )

        for mtime in sorted(self.comments.keys()):
            r["comment"].append(self.comments[mtime].jsonld)

        return settings.nameddict(r)

    @property
    def template(self):
        return f"{self.__class__.__name__}.j2.html"

    @property
    def txttemplate(self):
        return f"{self.__class__.__name__}.j2.txt"

    @property
    def renderdir(self):
        return os.path.join(settings.paths.get("build"), self.name)

    @property
    def renderfile(self):
        return os.path.join(self.renderdir, settings.filenames.html)

    @property
    def txtfile(self):
        return os.path.join(self.renderdir, settings.filenames.txt)

    @property
    def exists(self):
        if settings.args.get("force"):
            logger.debug("rendering required: force mode on")
            return False
        maybe = self.dt.timestamp
        if len(self.files):
            for f in self.files:
                maybe = max(maybe, mtime(f))
        for f in [self.renderfile, self.txtfile]:
            if not os.path.exists(f):
                logger.debug(f"rendering required: no {f} yet")
                return False
            elif maybe > mtime(f):
                logger.debug(f"rendering required: self.dt > {f} mtime")
                return False
        logger.debug("rendering not required")
        return True

    @property
    def corpus(self):
        return "\n".join(
            [self.title, self.name, self.summary, self.content]
        )

    async def copy_files(self):
        exclude = [
            ".md",
            ".jpg",
            ".png",
            ".gif",
            ".ping",
            ".url",
            ".del",
            ".copy",
            ".cache",
        ]
        files = glob.glob(
            os.path.join(os.path.dirname(self.fpath), "*.*")
        )
        for f in files:
            fname, fext = os.path.splitext(f)
            if fext.lower() in exclude:
                continue

            t = os.path.join(
                settings.paths.get("build"),
                self.name,
                os.path.basename(f),
            )
            if os.path.exists(t) and mtime(f) <= mtime(t):
                continue
            logger.info("copying '%s' to '%s'", f, t)
            cp(f, t)

    @property
    def has_archive(self):
        return len(
            glob.glob(os.path.join(self.dirpath, f"*archiveorg*.copy"))
        )

    async def get_from_archiveorg(self):
        if self.has_archive:
            return
        if self.is_future:
            return
        if (self.published.timestamp + 86400) > arrow.utcnow().timestamp:
            return
        logger.info("archive.org .copy is missing for %s", self.name)
        if len(self.category) and not (
            settings.args.get("noservices")
            or settings.args.get("offline")
        ):
            wb = wayback.FindWaybackURL(self.name, self.category)
            wb.run()
            if len(wb.oldest):
                archiveurl = url2slug(wb.oldest)
                t = os.path.join(self.dirpath, f"{archiveurl}.copy")
                writepath(t, wb.oldest)
            del wb

    async def render(self):
        await self.get_from_archiveorg()

        if self.exists:
            return True

        logger.info("rendering %s", self.name)
        v = {
            "baseurl": self.url,
            "post": self.jsonld,
            "site": settings.site,
            "menu": settings.menu,
            "meta": settings.meta,
            "fnames": settings.filenames,
        }
        writepath(
            self.renderfile, J2.get_template(self.template).render(v)
        )
        del v

        g = {
            "post": self.jsonld,
            "summary": self.txt_summary,
            "content": self.txt_content,
        }
        writepath(
            self.txtfile, J2.get_template(self.txttemplate).render(g)
        )
        del g

        j = settings.site.copy()
        j.update({"mainEntity": self.jsonld})
        writepath(
            os.path.join(self.renderdir, settings.filenames.json),
            json.dumps(j, indent=4, ensure_ascii=False),
        )
        del j


class Home(Singular):
    def __init__(self, fpath):
        super().__init__(fpath)
        self.cdata = {}
        self.pdata = {}

    def add(self, category, post):
        if not len(category.name):
            return

        if category.name not in self.cdata:
            self.cdata[category.name] = category

        if category.name not in self.pdata:
            self.pdata[category.name] = post
        else:
            current = arrow.get(self.pdata[category.name].datePublished)
            if current > post.published:
                return
            else:
                self.pdata[category.name] = post
                return

    @property
    def posts(self):
        flattened = []
        order = {}
        for cname, post in self.pdata.items():
            order[post.published.timestamp] = cname

        for mtime in sorted(order.keys(), reverse=True):
            category = self.cdata[order[mtime]].ctmplvars
            post = self.pdata[order[mtime]].jsonld
            flattened.append((category, post))

        return flattened

    @property
    def renderdir(self):
        return settings.paths.get("build")

    @property
    def renderfile(self):
        return os.path.join(
            settings.paths.get("build"), settings.filenames.html
        )

    @property
    def dt(self):
        ts = 0
        for cat, post in self.posts:
            ts = max(ts, arrow.get(post["dateModified"]).timestamp)
        return arrow.get(ts)

    async def render_gopher(self):
        lines = ["%s's gopherhole" % (settings.site.name), "", ""]

        for category, post in self.posts:
            line = "1%s\t/%s/%s\t%s\t70" % (
                category["name"],
                settings.paths.category,
                category["name"],
                settings.site.name,
            )
            lines.append(line)
        lines.append("")
        writepath(
            self.renderfile.replace(
                settings.filenames.html, settings.filenames.gopher
            ),
            "\r\n".join(lines),
        )

    async def render(self):
        if self.exists:
            return
        logger.info("rendering %s", self.name)
        r = J2.get_template(self.template).render(
            {
                "baseurl": settings.site.get("url"),
                "post": self.jsonld,
                "site": settings.site,
                "menu": settings.menu,
                "meta": settings.meta,
                "posts": self.posts,
                "fnames": settings.filenames,
            }
        )
        writepath(self.renderfile, r)
        await self.render_gopher()


class PHPFile(object):
    @property
    def exists(self):
        if settings.args.get("force"):
            return False
        if not os.path.exists(self.renderfile):
            return False
        if self.mtime > mtime(self.renderfile):
            return False
        return True

    @property
    def mtime(self):
        return mtime(
            os.path.join(settings.paths.get("tmpl"), self.templatefile)
        )

    @property
    def renderfile(self):
        raise ValueError("Not implemented")

    @property
    def templatefile(self):
        raise ValueError("Not implemented")

    async def render(self):
        # if self.exists:
        # return
        await self._render()


class Search(PHPFile):
    def __init__(self):
        self.fpath = os.path.join(
            settings.paths.get("build"), "search.sqlite"
        )
        self.db = sqlite3.connect(self.fpath)
        self.db.execute("PRAGMA auto_vacuum = INCREMENTAL;")
        self.db.execute("PRAGMA journal_mode = MEMORY;")
        self.db.execute("PRAGMA temp_store = MEMORY;")
        self.db.execute("PRAGMA locking_mode = NORMAL;")
        self.db.execute("PRAGMA synchronous = FULL;")
        self.db.execute('PRAGMA encoding = "UTF-8";')
        self.db.execute(
            """
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
            )"""
        )
        self.is_changed = False

    def __exit__(self):
        if self.is_changed:
            self.db.commit()
            self.db.execute("PRAGMA auto_vacuum;")
        self.db.close()

    def check(self, name):
        ret = 0
        maybe = self.db.execute(
            """
            SELECT
                mtime
            FROM
                data
            WHERE
                name = ?
        """,
            (name,),
        ).fetchone()
        if maybe:
            ret = int(maybe[0])
        return ret

    def append(self, post):
        mtime = int(post.published.timestamp)
        check = self.check(post.name)
        if check and check < mtime:
            self.db.execute(
                """
            DELETE
            FROM
                data
            WHERE
                name=?""",
                (post.name,),
            )
            check = False
        if not check:
            self.db.execute(
                """
                INSERT INTO
                    data
                    (url, mtime, name, title, category, content)
                VALUES
                    (?,?,?,?,?,?);
            """,
                (
                    post.url,
                    mtime,
                    post.name,
                    post.title,
                    post.category,
                    post.content,
                ),
            )
            self.is_changed = True

    @property
    def templates(self):
        return ["Search.j2.php", "OpenSearch.j2.xml"]

    async def _render(self):
        for template in self.templates:
            r = J2.get_template(template).render(
                {
                    "post": {},
                    "site": settings.site,
                    "menu": settings.menu,
                    "meta": settings.meta,
                }
            )
            target = os.path.join(
                settings.paths.get("build"),
                template.replace(".j2", "").lower(),
            )
            writepath(target, r)


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
            if "://" not in target:
                target = "%s/%s" % (settings.site.get("url"), target)
            self.redirect[source] = target

    @property
    def renderfile(self):
        return os.path.join(settings.paths.get("build"), "index.php")

    @property
    def templatefile(self):
        return "404.j2.php"

    async def _render(self):
        r = J2.get_template(self.templatefile).render(
            {
                "post": {},
                "site": settings.site,
                "menu": settings.menu,
                "gones": self.gone,
                "redirects": self.redirect,
                "rewrites": settings.rewrites,
                "gone_re": settings.gones,
            }
        )
        writepath(self.renderfile, r)


class Category(dict):
    def __init__(self, name=""):
        self.name = name

    def __setitem__(self, key, value):
        if key in self:
            raise LookupError(
                f"key '{key}' already exists, colliding posts are: {self[key].fpath} vs {value.fpath}"
            )
        dict.__setitem__(self, key, value)

    @property
    def title(self):
        if len(self.name):
            return f"{self.name} - {settings.site.name}"
        else:
            return settings.site.headline

    @property
    def url(self):
        if len(self.name):
            url = f"{settings.site.url}/{settings.paths.category}/{self.name}/"
        else:
            url = f"{settings.site.url}/"
        return url

    @property
    def feedurl(self):
        return f"{self.url}{settings.paths.feed}/"

    @property
    def sortedkeys(self):
        return list(sorted(self.keys(), reverse=True))

    @property
    def ctmplvars(self):
        return {
            "name": self.name,
            "url": self.url,
            "feed": self.feedurl,
            "title": self.title,
        }

    @property
    def renderdir(self):
        b = settings.paths.build
        if len(self.name):
            b = os.path.join(b, settings.paths.category, self.name)
        return b

    @property
    def newest_year(self):
        return arrow.get(max(self.keys())).format("YYYY")

    @cached_property
    def years(self):
        years = {}
        for key in list(sorted(self.keys(), reverse=True)):
            year = arrow.get(int(key)).format("YYYY")
            if year in years:
                continue
            if year == self.newest_year:
                url = f"{self.url}{settings.filenames.html}"
            else:
                url = f"{self.url}{year}/{settings.filenames.html}"
            years.update({year: url})
        return years

    async def render_feeds(self):
        await self.XMLFeed(self, "rss").render()
        await self.XMLFeed(self, "atom").render()
        await self.JSONFeed(self).render()

    async def render(self):
        await self.render_feeds()
        await self.Gopher(self).render()
        if self.name in settings.flat:
            await self.Flat(self).render()
        else:
            for year in sorted(self.years.keys()):
                await self.Year(self, year).render()

    class JSONFeed(object):
        def __init__(self, parent):
            self.parent = parent

        @property
        def mtime(self):
            return max(
                list(sorted(self.parent.keys(), reverse=True))[
                    0 : settings.pagination
                ]
            )

        @property
        def renderfile(self):
            return os.path.join(
                self.parent.renderdir,
                settings.paths.feed,
                settings.filenames.json,
            )

        @property
        def exists(self):
            if settings.args.get("force"):
                return False
            if not os.path.exists(self.renderfile):
                return False
            if mtime(self.renderfile) >= self.mtime:
                return True
            return False

        async def render(self):
            if self.exists:
                logger.debug(
                    "category %s is up to date", self.parent.name
                )
                return

            logger.info(
                "rendering JSON feed for category %s", self.parent.name
            )

            js = {
                "version": "https://jsonfeed.org/version/1",
                "title": self.parent.title,
                "home_page_url": settings.site.url,
                "feed_url": f"{self.parent.url}{settings.filenames.json}",
                "author": {
                    "name": settings.author.name,
                    "url": settings.author.url,
                    "avatar": settings.author.image,
                },
                "items": [],
            }

            for key in list(sorted(self.parent.keys(), reverse=True))[
                0 : settings.pagination
            ]:
                post = self.parent[key]
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
                    pjs.update(
                        {
                            "attachment": {
                                "url": post.photo.href,
                                "mime_type": post.photo.mime_type,
                                "size_in_bytes": f"{post.photo.mime_size}",
                            }
                        }
                    )
                js["items"].append(pjs)
            writepath(
                self.renderfile,
                json.dumps(js, indent=4, ensure_ascii=False),
            )

    class XMLFeed(object):
        def __init__(self, parent, feedformat="rss"):
            self.parent = parent
            self.feedformat = feedformat

        @property
        def mtime(self):
            return max(
                list(sorted(self.parent.keys(), reverse=True))[
                    0 : settings.pagination
                ]
            )

        @property
        def renderfile(self):
            if "rss" == self.feedformat:
                fname = settings.filenames.rss
            elif "atom" == self.feedformat:
                fname = settings.filenames.atom
            else:
                fname = "index.xml"
            return os.path.join(
                self.parent.renderdir, settings.paths.feed, fname
            )

        @property
        def exists(self):
            if settings.args.get("force"):
                return False
            if not os.path.exists(self.renderfile):
                return False
            if mtime(self.renderfile) >= self.mtime:
                return True
            return False

        async def render(self):
            if self.exists:
                logger.debug(
                    "category %s is up to date", self.parent.name
                )
                return

            logger.info(
                "rendering %s feed for category %s",
                self.feedformat,
                self.parent.name,
            )

            fg = FeedGenerator()
            fg.id(self.parent.feedurl)
            fg.title(self.parent.title)
            fg.logo(settings.site.image)
            fg.updated(arrow.get(self.mtime).to("utc").datetime)
            fg.description(settings.site.headline)
            fg.author(
                {
                    "name": settings.author.name,
                    "email": settings.author.email,
                }
            )
            if self.feedformat == "rss":
                fg.link(href=self.parent.feedurl)
            elif self.feedformat == "atom":
                fg.link(href=self.parent.feedurl, rel="self")
                fg.link(href=settings.meta.get("hub"), rel="hub")

            rkeys = list(sorted(self.parent.keys(), reverse=True))
            rkeys = rkeys[0 : settings.pagination]
            rkeys = list(sorted(rkeys, reverse=False))
            # for key in list(sorted(self.parent.keys(), reverse=True))[
            #    0 : settings.pagination
            # ]:
            for key in rkeys:
                post = self.parent[key]
                fe = fg.add_entry()

                fe.id(post.url)
                fe.title(post.title)
                fe.author(
                    {
                        "name": settings.author.name,
                        "email": settings.author.email,
                    }
                )
                fe.category(
                    {
                        "term": post.category,
                        "label": post.category,
                        "scheme": f"{settings.site.url}/{settings.paths.category}/{post.category}/",
                    }
                )

                fe.published(post.published.datetime)
                fe.updated(arrow.get(post.dt).datetime)

                fe.rights(
                    "%s %s %s"
                    % (
                        post.licence.upper(),
                        settings.author.name,
                        post.published.format("YYYY"),
                    )
                )

                if self.feedformat == "rss":
                    fe.link(href=post.url)
                    fe.content(post.html_content, type="CDATA")
                    # fe.description(post.txt_content, isSummary=True)
                elif self.feedformat == "atom":
                    fe.link(
                        href=post.url,
                        rel="alternate",
                        type="text/html"
                    )
                    fe.content(src=post.url, type="text/html")
                    fe.summary(post.summary)

                if post.is_photo:
                    fe.enclosure(
                        post.photo.href,
                        "%d" % post.photo.mime_size,
                        post.photo.mime_type,
                    )
            writepath(self.renderfile, fg.atom_str(pretty=True))

    class Year(object):
        def __init__(self, parent, year):
            self.parent = parent
            self.year = str(year)

        @cached_property
        def keys(self):
            year = arrow.get(self.year, "YYYY").to("utc")
            keys = []
            for key in list(sorted(self.parent.keys(), reverse=True)):
                ts = arrow.get(int(key))
                if ts <= year.ceil("year") and ts >= year.floor("year"):
                    keys.append(int(key))
            return keys

        @property
        def posttmplvars(self):
            return [self.parent[key].jsonld for key in self.keys]

        @property
        def mtime(self):
            return max(self.keys)

        @property
        def renderfile(self):
            if self.year == self.parent.newest_year:
                return os.path.join(
                    self.parent.renderdir, settings.filenames.html
                )
            else:
                return os.path.join(
                    self.parent.renderdir,
                    self.year,
                    settings.filenames.html,
                )

        @property
        def baseurl(self):
            if self.year == self.parent.newest_year:
                return self.parent.url
            else:
                return f"{self.parent.url}{self.year}/"

        @property
        def template(self):
            return "%s.j2.html" % (self.__class__.__name__)

        @property
        def exists(self):
            if settings.args.get("force"):
                return False
            if not os.path.exists(self.renderfile):
                return False
            if mtime(self.renderfile) >= self.mtime:
                return True
            return False

        @property
        def tmplvars(self):
            return {
                "baseurl": self.baseurl,
                "site": settings.site,
                "menu": settings.menu,
                "meta": settings.meta,
                "fnames": settings.filenames,
                "category": {
                    "name": self.parent.name,
                    "url": self.parent.url,
                    "feed": self.parent.feedurl,
                    "title": self.parent.title,
                    "paginated": True,
                    "years": self.parent.years,
                    "year": self.year,
                },
                "posts": self.posttmplvars,
            }

        async def render(self):
            if self.exists:
                logger.debug(
                    "category %s is up to date", self.parent.name
                )
                return
            logger.info(
                "rendering year %s for category %s",
                self.year,
                self.parent.name,
            )
            r = J2.get_template(self.template).render(self.tmplvars)
            writepath(self.renderfile, r)
            del r

    class Flat(object):
        def __init__(self, parent):
            self.parent = parent

        @property
        def posttmplvars(self):
            return [
                self.parent[key].jsonld
                for key in list(
                    sorted(self.parent.keys(), reverse=True)
                )
            ]

        @property
        def mtime(self):
            return max(self.parent.keys())

        @property
        def renderfile(self):
            return os.path.join(
                self.parent.renderdir, settings.filenames.html
            )

        @property
        def template(self):
            return "%s.j2.html" % (self.__class__.__name__)

        @property
        def exists(self):
            if settings.args.get("force"):
                return False
            if not os.path.exists(self.renderfile):
                return False
            if mtime(self.renderfile) >= self.mtime:
                return True
            return False

        @property
        def tmplvars(self):
            return {
                "baseurl": self.parent.url,
                "site": settings.site,
                "menu": settings.menu,
                "meta": settings.meta,
                "fnames": settings.filenames,
                "category": {
                    "name": self.parent.name,
                    "url": self.parent.url,
                    "feed": self.parent.feedurl,
                    "title": self.parent.title,
                },
                "posts": self.posttmplvars,
            }

        async def render(self):
            if self.exists:
                logger.debug(
                    "category %s is up to date", self.parent.name
                )
                return
            logger.info("rendering category %s", self.parent.name)
            r = J2.get_template(self.template).render(self.tmplvars)
            writepath(self.renderfile, r)
            del r

    class Gopher(object):
        def __init__(self, parent):
            self.parent = parent

        @property
        def mtime(self):
            return max(self.parent.keys())

        @property
        def exists(self):
            if settings.args.get("force"):
                return False
            if not os.path.exists(self.renderfile):
                return False
            if mtime(self.renderfile) >= self.mtime:
                return True
            return False

        @property
        def renderfile(self):
            return os.path.join(
                self.parent.renderdir, settings.filenames.gopher
            )

        async def render(self):
            if self.exists:
                logger.debug(
                    "category %s is up to date", self.parent.name
                )
                return

            lines = [
                "%s - %s" % (self.parent.name, settings.site.name),
                "",
                "",
            ]
            for post in [
                self.parent[key]
                for key in list(
                    sorted(self.parent.keys(), reverse=True)
                )
            ]:
                line = "0%s\t/%s/%s\t%s\t70" % (
                    post.title,
                    post.name,
                    settings.filenames.txt,
                    settings.site.name,
                )
                lines.append(line)
                if len(post.txt_summary):
                    lines.extend(post.txt_summary.split("\n"))
                for img in post.images.values():
                    line = "I%s\t/%s/%s\t%s\t70" % (
                        img.title,
                        post.name,
                        img.name,
                        settings.site.name,
                    )
                    lines.append(line)
                lines.append("")
            writepath(self.renderfile, "\r\n".join(lines))


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
        return os.path.join(
            settings.paths.get("build"), settings.filenames.sitemap
        )

    async def render(self):
        if len(self) > 0:
            if self.mtime >= sorted(self.values())[-1]:
                return
            with open(self.renderfile, "wt") as f:
                f.write("\n".join(sorted(self.keys())))


#def json_decode(string):
    #r = {}
    #try:
        #r = json.loads(string)
        #for k, v in j.items():
            #if isinstance(v, str):
                #r[k] = json_decode(v)
    #except Exception as e:
        ##logger.error("failed to recursive parse JSON portion: %s", e)
        #pass
    #return r

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
            self.dpath, "%s.ping" % (url2slug(self.target))
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
            self.backfill_syndication()
            return
        elif settings.args.get("noping"):
            self.save("noping entry at %s" % arrow.now())
            return

        telegraph_url = "https://telegraph.p3k.io/webmention"
        telegraph_params = {
            "token": "%s" % (keys.telegraph.get("token")),
            "source": "%s" % (self.source),
            "target": "%s" % (self.target),
        }
        r = requests.post(telegraph_url, data=telegraph_params)
        logger.info(
            "sent webmention to telegraph from %s to %s",
            self.source,
            self.target,
        )
        if r.status_code not in [200, 201, 202]:
            logger.error("sending failed: %s %s", r.status_code, r.text)
        else:
            self.save(r.text)

    def backfill_syndication(self):
        """ this is very specific to webmention.io and brid.gy publish """

        if "fed.brid.gy" in self.target:
            return
        if "brid.gy" not in self.target:
            return
        if not self.exists:
            return

        with open(self.fpath, "rt") as f:
            txt = f.read()

        try:
            data = json.loads(txt)
        except Exception as e:
            """ if it's not a JSON, it's a manually placed file, ignore it """
            logger.debug("not a JSON webmention at %s", self.fpath)
            return

        # unprocessed webmention
        if "http_body" not in data and "location" in data:
            logger.debug(
                "fetching webmention.io respose from %s",
                data["location"]
            )
            wio = requests.get(data["location"])
            if wio.status_code != requests.codes.ok:
                logger.debug("fetching %s failed", data["location"])
                return

            try:
                wio_json = json.loads(wio.text)
                logger.debug("got response %s", wio_json)
                if "http_body" in  wio_json and isinstance(wio_json["http_body"], str):
                    wio_json.update({"http_body": json.loads("".join(wio_json["http_body"]))})
                    if "original" in wio_json["http_body"].keys():
                        wio_json.update({"http_body": wio_json["http_body"]["original"]})
                data = {**data, **wio_json}
            except Exception as e:
                logger.error("failed to JSON load webmention.io response %s because: %s", wio.text, e)
                return

            logger.debug("saving updated webmention.io data %s to %s", data, self.fpath)
            with open(self.fpath, "wt") as update:
                update.write(json.dumps(data, sort_keys=True, indent=4))

        if "http_body" in data.keys():
            # healthy and processed webmention
            if isinstance(data["http_body"], dict) and "url" in data["http_body"].keys():
                url = data["http_body"]["url"]
                sp = os.path.join(self.dpath, "%s.copy" % url2slug(url))
                if os.path.exists(sp):
                    logger.debug("syndication already exists for %s", url)
                    return
                with open(sp, "wt") as f:
                    logger.info("writing syndication copy %s to %s", url, sp)
                    f.write(url)
                    return

class WebmentionIO(object):
    def __init__(self):
        self.params = {
            "token": "%s" % (keys.webmentionio.get("token")),
            "since": "%s" % str(self.since),
            "domain": "%s" % (keys.webmentionio.get("domain")),
        }
        self.url = "https://webmention.io/api/mentions"

    @property
    def since(self):
        newest = 0
        content = settings.paths.get("content")
        for e in glob.glob(os.path.join(content, "*", "*", "*.md")):
            if os.path.basename(e) == settings.filenames.md:
                continue
            # filenames are like [received epoch]-[slugified source url].md
            try:
                mtime = int(os.path.basename(e).split("-")[0])
            except Exception as exc:
                logger.error(
                    "int conversation failed: %s, file was: %s", exc, e
                )
                continue
            if mtime > newest:
                newest = mtime
        return arrow.get(newest + 1)

    def makecomment(self, webmention):
        if "published_ts" in webmention.get("data"):
            maybe = webmention.get("data").get("published")
            if not maybe or maybe == "None":
                dt = arrow.get(webmention.get("verified_date"))
            else:
                dt = arrow.get(webmention.get("data").get("published"))

        slug = os.path.split(
            urlparse(webmention.get("target")).path.lstrip("/")
        )[0]

        # ignore selfpings
        if slug == settings.site.get("name"):
            return

        fdir = glob.glob(
            os.path.join(settings.paths.get("content"), "*", slug)
        )
        if not len(fdir):
            logger.error(
                "couldn't find post for incoming webmention: %s",
                webmention,
            )
            return
        elif len(fdir) > 1:
            logger.error(
                "multiple posts found for incoming webmention: %s",
                webmention,
            )
            return

        fdir = fdir.pop()
        fpath = os.path.join(
            fdir,
            "%d-%s.md"
            % (dt.timestamp, url2slug(webmention.get("source"))),
        )

        author = webmention.get("data", {}).get("author", None)
        if not author:
            logger.error("missing author info on webmention; skipping")
            return
        meta = {
            "author": {
                "name": author.get("name", ""),
                "url": author.get("url", ""),
                "photo": author.get("photo", ""),
            },
            "date": str(dt),
            "source": webmention.get("source"),
            "target": webmention.get("target"),
            "type": webmention.get("activity").get(
                "type", "webmention"
            ),
        }

        try:
            txt = webmention.get("data").get("content", "").strip()
        except Exception as e:
            txt = ""
            pass

        r = "---\n%s\n---\n\n%s\n" % (utfyamldump(meta), txt)
        writepath(fpath, r)

    def run(self):
        webmentions = requests.get(self.url, params=self.params)
        logger.info("queried webmention.io with: %s", webmentions.url)
        if webmentions.status_code != requests.codes.ok:
            return
        try:
            mentions = webmentions.json()
            for webmention in mentions.get("links"):
                self.makecomment(webmention)
        except ValueError as e:
            logger.error("failed to query webmention.io: %s", e)
            pass


def make():
    start = int(round(time.time() * 1000))
    last = 0

    if not (
        settings.args.get("offline") or settings.args.get("noservices")
    ):
        incoming = WebmentionIO()
        incoming.run()

    queue = AQ()
    send = []
    to_archive = []

    content = settings.paths.get("content")
    rules = IndexPHP()

    sitemap = Sitemap()
    search = Search()
    categories = {}
    frontposts = Category()
    home = Home(settings.paths.get("home"))

    for e in glob.glob(os.path.join(content, "*", "*.url")):
        post = Redirect(e)
        rules.add_redirect(post.source, post.target)

    for e in sorted(
        glob.glob(
            os.path.join(content, "*", "*", settings.filenames.md)
        )
    ):
        post = Singular(e)
        # deal with images, if needed
        for i in post.images.values():
            queue.put(i.downsize())
        if not post.is_future:
            for i in post.to_ping:
                send.append(i)

        # if not post.is_future and not post.has_archive:
        # to_archive.append(post.url)

        # render and arbitrary file copy tasks for this very post
        queue.put(post.render())
        queue.put(post.copy_files())

        # skip draft posts from anything further
        if post.is_future:
            logger.info("%s is for the future", post.name)
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
    for e in glob.glob(os.path.join(content, "*", "*.del")):
        post = Gone(e)
        rules.add_gone(post.source)
    for e in glob.glob(os.path.join(content, "*", "*.url")):
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
    queue.run()

    # copy static files
    for e in glob.glob(os.path.join(content, "*.*")):
        if e.endswith(".md"):
            continue
        t = os.path.join(
            settings.paths.get("build"), os.path.basename(e)
        )
        maybe_copy(e, t)

    end = int(round(time.time() * 1000))
    logger.info("process took %d ms" % (end - start))

    if not settings.args.get("offline"):
        # upload site
        try:
            logger.info("starting syncing")
            os.system(
                "rsync -avuhH --delete-after %s/ %s/"
                % (
                    settings.paths.get("build"),
                    "%s/%s"
                    % (
                        settings.syncserver,
                        settings.paths.get("remotewww"),
                    ),
                )
            )
            logger.info("syncing finished")
        except Exception as e:
            logger.error("syncing failed: %s", e)

        if not settings.args.get("noservices"):
            logger.info("sending webmentions")
            for wm in send:
                queue.put(wm.send())
            queue.run()
            logger.info("sending webmentions finished")


if __name__ == "__main__":
    make()
