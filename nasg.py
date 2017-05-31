#!/usr/bin/env python3

import os
import re
import configparser
import argparse
import shutil
import logging
import json
import glob
import tempfile
import atexit
import re
import hashlib
import math
import asyncio
import csv
import operator

import magic
import arrow
import wand.image
import similar_text
import frontmatter
from slugify import slugify
import langdetect
import requests
from breadability.readable import Article
from whoosh import index
from whoosh import qparser
import jinja2
import urllib.parse
import shared
from webmentiontools.send import WebmentionSend

import time

def splitpath(path):
    parts = []
    (path, tail) = os.path.split(path)
    while path and tail:
        parts.insert(0,tail)
        (path,tail) = os.path.split(path)
    return parts


class SmartIndexer(object):

    def __init__(self):
        self.target = os.path.abspath(os.path.join(
            shared.config.get('target', 'builddir'),
            shared.config.get('var', 'searchdb')
        ))
        if not os.path.isdir(self.target):
            os.mkdir(self.target)

        if index.exists_in(self.target):
            self.ix = index.open_dir(self.target)
        else:
            self.ix = index.create_in(self.target, shared.schema)
        self.writer = self.ix.writer()
        self.qp = qparser.QueryParser("url", schema=shared.schema)

    async def append(self, singular):
        logging.debug("searching for existing index for %s", singular.fname)
        exists = False

        q = self.qp.parse(singular.url)
        r = self.ix.searcher().search(q, limit=1)
        if r:
            r = r[0]
            # nothing to do, the entry is present and is up to date
            ixtime = r['mtime']
            if  int(ixtime) == int(singular.mtime):
                logging.info("search index is up to date for %s", singular.fname)
                return
            else:
                logging.info("search index is out of date: %d (indexed) vs %d", ixtime, singular.mtime)
                exists = True

        content_real = [
            singular.fname,
            singular.summary,
            singular.content,
        ]

        content_remote = []
        for url, offlinecopy in singular.offlinecopies.items():
            content_remote.append("%s" % offlinecopy)

        weight = 1
        if singular.isbookmark:
            weight = 10
        if singular.ispage:
            weight = 100

        if exists:
            logging.info("updating search index with %s", singular.fname)
            self.writer.add_document(
                title=singular.title,
                url=singular.url,
                content=" ".join(list(map(str,[*content_real, *content_remote]))),
                date=singular.published.datetime,
                tags=",".join(list(map(str, singular.tags))),
                weight=weight,
                img="%s" % singular.photo,
                mtime=singular.mtime,
            )
        else:
            logging.info("appending search index with %s", singular.fname)
            self.writer.update_document(
                title=singular.title,
                url=singular.url,
                content=" ".join(list(map(str,[*content_real, *content_remote]))),
                date=singular.published.datetime,
                tags=",".join(list(map(str, singular.tags))),
                weight=weight,
                img="%s" % singular.photo,
                mtime=singular.mtime
            )

    def finish(self):
        self.writer.commit()

class OfflineCopy(object):
    def __init__(self, url):
        self.url = url
        self.fname = hashlib.sha1(url.encode('utf-8')).hexdigest()
        self.targetdir = os.path.abspath(
            shared.config.get('source', 'offlinecopiesdir')
        )
        self.target = os.path.join(
            self.targetdir,
            self.fname
        )
        self.fm = frontmatter.loads('')
        self.fm.metadata = {
            'url': self.url,
            'date': arrow.utcnow().format("YYYY-MM-DDTHH:mm:ssZ"),
        }

    def __repr__(self):
        return self.fm.content

    def write(self):
        logging.info(
            "savig offline copy of\n\t%s to:\n\t%s",
            self.url,
            self.target
        )
        with open(self.target, 'wt') as f:
            f.write(frontmatter.dumps(self.fm))

    def run(self):
        if os.path.isfile(self.target):
            with open(self.target) as f:
                self.fm = frontmatter.loads(f.read())
                return

        logging.info("prepairing offline copy of %s", self.url)
        headers = requests.utils.default_headers()
        headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        })

        try:
            r = requests.get(
                self.url,
                allow_redirects=True,
                timeout=60,
                headers=headers
            )
        except Exception as e:
            logging.error("%s failed:\n%s", self.url, e)
            self.write()
            return

        if r.status_code != requests.codes.ok:
            logging.warning("%s returned %s", self.url, r.status_code)
            self.write()
            return

        if not len(r.text):
            logging.warning("%s was empty", self.url)
            self.write()
            return

        doc = Article(r.text, url=self.url)
        self.fm.metadata['title'] = doc._original_document.title
        self.fm.metadata['realurl'] = r.url
        self.fm.content = shared.Pandoc(False).convert(doc.readable)
        self.write()


class Renderer(object):
    def __init__(self):
        self.sitevars = dict(shared.config.items('site'))
        self.sitevars['author'] = dict(shared.config.items('author'))
        self.sitevars['author']['socials'] = dict(shared.config.items('socials'))

        self.jinjaldr = jinja2.FileSystemLoader(
            searchpath=shared.config.get('source', 'templatesdir')
        )
        self.j2 = jinja2.Environment(loader=self.jinjaldr)
        self.j2.filters['date'] = Renderer.jinja_filter_date
        self.j2.filters['search'] = Renderer.jinja_filter_search
        self.j2.filters['slugify'] = Renderer.jinja_filter_slugify

    @staticmethod
    def jinja_filter_date(d, form='%Y-%m-%d %H:%m:%S'):
        if d == 'now':
            return arrow.now().strftime(form)
        if form == 'c':
            form = '%Y-%m-%dT%H:%M:%S%z'
        return d.strftime(form)

    @staticmethod
    def jinja_filter_slugify(s):
        return slugify(s, only_ascii=True, lower=True)

    @staticmethod
    def jinja_filter_search(s, r):
        if r in s:
            return True
        return False


class BaseIter(object):
    def __init__(self):
        self.data = {}

    def append(self, key, value):
        if key in self.data:
            logging.warning("duplicate key: %s, using existing instead", key)
            existing = self.data.get(key)
            if hasattr(value, 'fname') and hasattr(existing, 'fname'):
                logging.warning(
                    "%s collides with existing %s",
                    value.fname,
                    existing.fname
                )
            return
        self.data[key] = value

    def __getitem__(self, key):
        return self.data.get(key, {})

    def __repr__(self):
        return json.dumps(list(self.data.values()))

    def __next__(self):
        try:
            r = self.data.next()
        except:
            raise StopIteration()
        return r

    def __iter__(self):
        for k, v in self.data.items():
            yield (k, v)
        return

# based on http://stackoverflow.com/a/10075210
class ExifTool(shared.CMDLine):
    """ Handles calling external binary `exiftool` in an efficient way """
    sentinel = "{ready}\n"

    def __init__(self):
        super().__init__('exiftool')

    def get_metadata(self, *filenames):
        return json.loads(self.execute(
            '-sort',
            #'-quiet',
            '-json',
            '-MIMEType',
            '-FileType',
            '-FileName',
            '-ModifyDate',
            '-CreateDate',
            '-DateTimeOriginal',
            '-ImageHeight',
            '-ImageWidth',
            '-Aperture',
            '-FOV',
            '-ISO',
            '-FocalLength',
            '-FNumber',
            '-FocalLengthIn35mmFormat',
            '-ExposureTime',
            '-Copyright',
            '-Artist',
            '-Model',
            '-GPSLongitude#',
            '-GPSLatitude#',
            '-LensID',
            *filenames))

class Images(BaseIter):
    def __init__(self, extensions=['jpg', 'gif', 'png']):
        super(Images, self).__init__()
        logging.info(
            "initiating images with extensions: %s",
            extensions
        )
        self.files = []
        self.data = {}
        # if anyone knows how to do this in a more pythonic way, please tell me
        paths = [
            shared.config.get('source', 'filesdir'),
            shared.config.get('source', 'photosdir')
        ]
        for p in paths:
            for ext in extensions:
                self.files += glob.glob(os.path.join(p, "*.%s" % ext))


    def populate(self):
        with ExifTool() as e:
            _meta = e.get_metadata(*self.files)
            # parsing the returned meta into a dict of [filename]={meta}
            for e in _meta:
                if 'FileName' not in e:
                    logging.error("missing 'FileName' in element %s", e)
                    continue
                fname = os.path.basename(e['FileName'])
                del(e['FileName'])
                # duplicate files are going to be a problem, so don't send it
                # away with a simple error log entry
                if fname in self.data:
                    raise ValueError('filename collision: %s', fname)
                # convert dates
                for k, v in e.items():
                    e[k] = self.exifdate(v)

                self.data[fname] = WebImage(fname, e)

    def exifdate(self, value):
        """ converts and EXIF date string to ISO 8601 format

        :param value: EXIF date (2016:05:01 00:08:24)
        :type arg1: str
        :return: ISO 8601 string with UTC timezone 2016-05-01T00:08:24+0000
        :rtype: str
        """
        if not isinstance(value, str):
            return value
        match = shared.EXIFREXEG.match(value)
        if not match:
            return value
        return "%s-%s-%sT%s+0000" % (
            match.group('year'),
            match.group('month'),
            match.group('day'),
            match.group('time')
        )

class WebImage(object):
    def __init__(self, fname, meta):
        logging.info(
            "parsing image: %s",
            fname
        )
        self.meta = meta
        self.fpath = os.path.abspath(meta.get('SourceFile', fname))
        self.fname, self.ext = os.path.splitext(fname)
        self.alttext = ''
        self.sizes = []
        self.fallbacksize = int(shared.config.get('common','fallbackimg', fallback='720'))
        self.cl = None
        self.singleimage = False

        for size in shared.config.options('downsize'):
            sizeext = shared.config.get('downsize', size)
            fname = "%s_%s%s" % (self.fname, sizeext, self.ext)
            self.sizes.append((
                int(size),
                {
                    'fpath': os.path.join(
                        shared.config.get('target', 'filesdir'),
                        fname
                    ),
                    'url': "%s/%s/%s" % (
                        shared.config.get('site', 'url'),
                        shared.config.get('source', 'files'),
                        fname
                    ),
                    'crop': shared.config.getboolean('crop', size, fallback=False),
                }
            ))

        self.sizes = sorted(self.sizes, reverse=False)

        self.target = False
        if self.is_downsizeable:
            self.fallback = [e for e in self.sizes if e[0] == self.fallbacksize][0][1]['url']
            self.target = self.sizes[-1][1]['url']
        else:
            self.fallback = "%s/%s/%s" % (
                shared.config.get('site', 'url'),
                shared.config.get('source', 'files'),
                "%s%s" % (self.fname, self.ext)
            )

    def __str__(self):
        if self.is_downsizeable and not self.cl:
            uphoto = ''
            if self.singleimage:
                uphoto = ' u-photo'
            return '\n<figure class="photo"><a target="_blank" class="adaptive%s" href="%s"><img src="%s" class="adaptimg" alt="%s" /></a><figcaption class=\"caption\">%s%s</figcaption></figure>\n' % (
                uphoto,
                self.target,
                self.fallback,
                self.alttext,
                self.fname,
                self.ext
            )
        elif self.cl:
            self.cl = self.cl.replace('.', ' ')
            return '<img src="%s" class="%s" alt="%s" title="%s%s" />' % (
                self.fallback,
                self.cl,
                self.alttext,
                self.fname,
                self.ext
            )

        else:
            return '<img src="%s" class="aligncenter" alt="%s" title="%s%s" />' % (
                self.fallback,
                self.alttext,
                self.fname,
                self.ext
            )

    @property
    def rssenclosure(self):
        """ Returns the largest available image for RSS to add as attachment """
        target = self.sizes[-1][1]
        return {
            'mime': magic.Magic(mime=True).from_file(target['fpath']),
            'url': target['url'],
            'bytes':  os.path.getsize(target['fpath'])
        }

    @property
    def is_photo(self):
        """ Match image meta against config artist regex to see if the file is
        a photo or just a regular image """
        pattern = shared.config.get('photo', 'regex', fallback=None)
        if not pattern or not isinstance(pattern, str):
            return False
        pattern = re.compile(pattern)

        cpr = self.meta.get('Copyright', '')
        art = self.meta.get('Artist', '')
        if not cpr and not art:
            return False

        if pattern.search(cpr) \
        or pattern.search(art):
            return True

        return False

    @property
    def is_downsizeable(self):
        """ Check if the image is large enough and jpeg or png in order to
        downsize it """
        fb = self.sizes[-1][0]
        ftype = self.meta.get('FileType', None)
        if not ftype:
            return False
        if ftype.lower() == 'jpeg' or ftype.lower() == 'png':
            width = int(self.meta.get('ImageWidth', 0))
            height = int(self.meta.get('ImageHeight', 0))
            if width > fb or height > fb:
                return True
        return False

    def _copy(self):
        target = os.path.join(
            shared.config.get('target', 'filesdir'),
            "%s%s" % (self.fname, self.ext)
        )
        if not os.path.isfile(target):
            logging.debug("can't downsize %s, copying instead" % self.fname)
            shutil.copy(self.fpath, target)

    def _watermark(self, img):
        """ Composite image by adding watermark file over it """
        wmarkfile = os.path.join(
            shared.config.get('common', 'basedir'),
            shared.config.get('common', 'watermark')
        )
        if not os.path.isfile(wmarkfile):
            return img

        with wand.image.Image(filename=wmarkfile) as wmark:
            if img.width > img.height:
                w = img.width * 0.16
                h = wmark.height * (w / wmark.width)
                x = img.width - w - (img.width * 0.01)
                y = img.height - h - (img.height * 0.01)
            else:
                w = img.height * 0.16
                h = wmark.height * (w / wmark.width)
                x = img.width - h - (img.width * 0.01)
                y = img.height - w - (img.height * 0.01)

            w = round(w)
            h = round(h)
            x = round(x)
            y = round(y)

            wmark.resize(w, h)
            if img.width <= img.height:
                wmark.rotate(-90)
            img.composite(image=wmark, left=x, top=y)
        return img


    def _intermediate_dimensions(self, size, width, height, crop = False):
        size = int(size)
        w = width
        h = height
        if (width > height and not crop) \
        or (width < height and crop):
            w = size
            h = int(float(size / width) * height)
        else:
            h = size
            w = int(float(size / height) * width)
        return (w, h)


    def _intermediate(self, img, size, meta, existing = []):
        if img.width <= size and img.height <= size:
            return False

        crop = meta.get('crop', False)
        with img.clone() as thumb:
            width, height = self._intermediate_dimensions(
                size,
                img.width,
                img.height,
                crop
            )
            thumb.resize(width, height)

            if crop:
                thumb.liquid_rescale(size, size, 1, 1)

            if self.meta.get('FileType', 'jpeg').lower() == 'jpeg':
                thumb.compression_quality = 86
                thumb.unsharp_mask(
                    radius=0,
                    sigma=0.5,
                    amount=1,
                    threshold=0.03
                )
                thumb.format = 'pjpeg'

            # this is to make sure pjpeg happens
            with open(meta['fpath'], 'wb') as f:
                thumb.save(file=f)

        return True


    async def downsize(self, existing = []):
        if not self.is_downsizeable:
            self._copy()
            return

        logging.info("checking downsizing for %s", self.fname)
        needed = shared.config.getboolean('params', 'regenerate', fallback=False)

        if not needed:
            for (size, meta) in self.sizes:
                if meta['fpath'] not in existing:
                    needed = True

        if not needed:
            logging.debug("downsizing not needed for %s", self.fname)
            return

        with wand.image.Image(filename=self.fpath) as img:
            img.auto_orient()

            if self.is_photo:
                logging.info("%s is a photo", self.fpath)
                img = self._watermark(img)

            for (size, meta) in self.sizes:
                self._intermediate(img, size, meta, existing)

class Taxonomy(BaseIter):
    def __init__(self, name = None, taxonomy = None, slug = None):
        super(Taxonomy, self).__init__()
        self.name = name
        if name and not slug:
            self.slug = slugify(name, only_ascii=True, lower=True)
        else:
            self.slug = slug
        self.taxonomy = taxonomy

    @property
    def pages(self):
        return math.ceil(len(self.data) / shared.config.getint('common', 'pagination'))

    def __repr__(self):
        return "taxonomy %s with %d items" % (self.taxonomy, len(self.data))

    @property
    def basep(self):
        p = shared.config.get('target', 'builddir')
        if self.taxonomy:
            p = os.path.join(p, self.taxonomy)
        return p

    @property
    def myp(self):
        p = self.basep
        if self.slug:
            return os.path.join(p,self.slug)
        return p

    @property
    def feedp(self):
        return os.path.join(self.myp, 'feed')

    @property
    def pagep(self):
        return os.path.join(self.myp, 'page')

    @property
    def baseurl(self):
        if self.taxonomy and self.slug:
            return "/%s/%s/" % (self.taxonomy, self.slug)
        else:
            return '/'

    @property
    def mtime(self):
        return int(list(sorted(self.data.keys(), reverse=True))[0])

    def __mkdirs(self):
        check = [self.basep, self.myp, self.feedp]

        if self.pages > 1:
            check.append(self.pagep)
            for i in range(2, self.pages+1):
                subpagep = os.path.abspath(os.path.join(
                    self.pagep,
                    '%d' % i
                ))
                check.append(subpagep)

        for p in check:
            if not os.path.isdir(p):
                logging.debug("creating dir %s", p)
                os.mkdir(p)

    def tpath(self, page):
        if page == 1:
            return "%s/index.html" % (self.myp)
        else:
            return "%s/%d/index.html" % (self.pagep, page)


    async def render(self, renderer):
        self.__mkdirs()
        page = 1
        testpath = self.tpath(page)
        if not shared.config.getboolean('params', 'force') and os.path.isfile(testpath):
            ttime = int(os.path.getmtime(testpath))
            if ttime == self.mtime:
                logging.info('taxonomy index for "%s" exists and up-to-date (lastmod: %d)', self.slug, ttime)
                return

        while page <= self.pages:
            self.renderpage(renderer, page)
            page = page+1

    def renderpage(self, renderer, page):
        pagination = int(shared.config.get('common', 'pagination'))
        start = int((page-1) * pagination)
        end = int(start + pagination)

        posttmpls = [self.data[k].tmplvars for k in list(sorted(
            self.data.keys(), reverse=True))[start:end]]

        target = self.tpath(page)
        logging.info("rendering taxonomy page %d to %s", page, target)
        tmplvars = {
            'taxonomy': {
                'url': self.baseurl,
                'name': self.name,
                'taxonomy': self.taxonomy,
                'paged': page,
                'total': self.pages,
                'perpage': pagination
            },
            'site': renderer.sitevars,
            'posts': posttmpls,
        }

        r = renderer.j2.get_template('archive.html').render(tmplvars)
        with open(target, "wt") as html:
            html.write(r)
            os.utime(target, (self.mtime, self.mtime))

        if 1 == page:
            target = os.path.join(self.feedp, 'index.xml')
            logging.info("rendering RSS feed to %s", target)
            r = renderer.j2.get_template('rss.html').render(tmplvars)
            with open(target, "wt") as html:
                html.write(r)
            os.utime(target, (self.mtime, self.mtime))

class Content(BaseIter):
    def __init__(self, images, extensions=['md']):
        super(Content, self).__init__()
        self.images = images
        basepath = shared.config.get('source', 'contentdir')
        self.files = []
        for ext in extensions:
            self.files += glob.glob(os.path.join(basepath, "*", "*.%s" % ext))
        self.tags = {}
        self.categories = {}
        self.front = Taxonomy()

    def populate(self):
        now = arrow.utcnow().timestamp
        for fpath in self.files:
            item = Singular(fpath, self.images)
            self.append(item.pubtime, item)

            if item.pubtime > now:
                logging.warning("skipping future post %s", item.fname)
                continue

            if item.isonfront:
                self.front.append(item.pubtime, item)

            if item.iscategorised:
                if item.category not in self.categories:
                    self.categories[item.category] = Taxonomy(item.category, 'category')
                self.categories[item.category].append(item.pubtime, item)

            for tag in item.tags:
                tslug = slugify(tag, only_ascii=True, lower=True)
                if tslug not in self.tags:
                    self.tags[tslug] = Taxonomy(tag, 'tag', tslug)
                self.tags[tslug].append(item.pubtime, item)
                self.symlinktag(tslug, item.path)

    def symlinktag(self, tslug, fpath):
        fdir, fname = os.path.split(fpath)
        tagpath = os.path.join(shared.config.get('source', 'tagsdir'), tslug)
        if not os.path.isdir(tagpath):
            os.mkdir(tagpath)
        sympath = os.path.relpath(fdir, tagpath)
        dst = os.path.join(tagpath, fname)
        src = os.path.join(sympath, fname)
        if not os.path.islink(dst):
            os.symlink(src, dst)

    def sitemap(self):
        target = os.path.join(
            shared.config.get('target', 'builddir'),
            'sitemap.txt'
        )
        urls = []
        for item in self.data.values():
            urls.append( "%s/%s/" % (
                shared.config.get('site', 'url'),
                item.fname
            ))

        with open(target, "wt") as f:
            logging.info("writing sitemap to %s" % (target))
            f.write("\n".join(urls))

    def magicphp(self, renderer):
        redirects = []
        gones = []
        rfile = os.path.join(
            shared.config.get('common', 'basedir'),
            shared.config.get('common', 'redirects')
        )
        if os.path.isfile(rfile):
            with open(rfile, newline='') as csvfile:
                r = csv.reader(csvfile, delimiter=' ')
                for row in r:
                    redirects.append((row[0], row[1]))
        for item in self.data.values():
            redirects.append((item.shortslug, item.fname))

        rfile = os.path.join(
            shared.config.get('common', 'basedir'),
            shared.config.get('common', 'gone')
        )
        if os.path.isfile(rfile):
            with open(rfile, newline='') as csvfile:
                r = csv.reader(csvfile, delimiter=' ')
                for row in r:
                    gones.append(row[0])

        tmplvars = {
            'site': renderer.sitevars,
            'redirects': redirects,
            'gones': gones
        }

        r = renderer.j2.get_template("magic.php").render(tmplvars)
        target = os.path.abspath(os.path.join(
            shared.config.get('target', 'builddir'),
            'magic.php'
        ))

        with open(target, "w") as html:
            logging.debug('writing %s', target)
            html.write(r)
            html.close()

class Singular(object):
    def __init__(self, path, images):
        logging.debug("initiating singular object from %s", path)
        self.path = path
        self.images = images
        self.category = splitpath(path)[-2]
        self.mtime = int(os.path.getmtime(self.path))
        self.fname, self.ext = os.path.splitext(os.path.basename(self.path))
        self.meta = {}
        self.content = ''
        self.photo = self.images.data.get("%s.jpg" % self.fname, None)
        if self.photo:
            self.photo.singleimage = True
        self.__parse()

    def __repr__(self):
        return "%s (lastmod: %s)" % (self.fname, self.published)

    def __parse(self):
        with open(self.path, mode='rt') as f:
            self.meta, self.content = frontmatter.parse(f.read())
            self.__filter_images()
        if self.isphoto:
            self.content = "%s\n%s" % (
                self.content,
                self.photo
            )

    #@property
    #def isrepost(self):
        #isrepost = False

        #if len(self.reactions.keys()):
            #isrepost = list(self.reactions.keys())[0]

        #if isrepost:
            #if len(self.reactions[isrepost]) == 1:
                #linkto = self.reactions[isrepost][0]


    def __filter_images(self):
        linkto = False
        isrepost = None

        if len(self.reactions.keys()):
            isrepost = list(self.reactions.keys())[0]
            if isrepost and \
            len(self.reactions[isrepost]) == 1:
                linkto = self.reactions[isrepost][0]

        m = shared.MDIMGREGEX.findall(self.content)
        if not m:
            logging.debug("no images found")
            return

        for shortcode, alt, fname, title, cl in m:
            image = self.images.data.get(fname, None)
            if not image:
                logging.debug("%s not found in images", fname)
                continue

            if cl:
                image.cl = cl

            logging.debug(
                "replacing %s in content with %s",
                shortcode,
                "%s" % image
            )
            self.content = self.content.replace(
                shortcode,
                "%s" % image
            )

    @property
    def reactions(self):
        # getting rid of '-' to avoid css trouble and similar
        convert = {
            'bookmark-of': 'bookmark',
            'repost-of': 'repost',
            'in-reply-to': 'reply',
        }
        reactions = {}

        for k, v in convert.items():
            x = self.meta.get(k, None)
            if not x:
                continue
            if isinstance(x, str):
                x = [x]
            reactions[v] = x

        return reactions

    @property
    def urls(self):
        urls = shared.URLREGEX.findall(self.content)

        for reactionurls in self.reactions.values():
            urls = [*urls, *reactionurls]

        r = []
        for link in urls:
            domain = '{uri.netloc}'.format(uri=urllib.parse.urlparse(link))
            if domain in shared.config.get('site', 'domains'):
                continue
            if link in r:
                continue
            r.append(link)

        return r

    @property
    def lang(self):
        lang = 'en'
        try:
            lang = langdetect.detect("\n".join([
                self.title,
                self.content
            ]))
        except:
            pass
        return lang

    @property
    def tags(self):
        return list(self.meta.get('tags', []))

    @property
    def published(self):
        return arrow.get(
            self.meta.get('published', self.mtime)
        )

    @property
    def updated(self):
        return arrow.get(
            self.meta.get('updated',
                self.meta.get('published', self.mtime)
            )
        )

    @property
    def pubtime(self):
        return int(self.published.timestamp)

    @property
    def isphoto(self):
        if not self.photo:
            return False
        return self.photo.is_photo

    @property
    def isbookmark(self):
        return self.meta.get('bookmark-of', False)

    @property
    def ispage(self):
        if not self.meta:
            return True
        return False

    @property
    def isonfront(self):
        if self.ispage or self.isbookmark:
            return False
        return True

    @property
    def iscategorised(self):
        if self.ispage:
            return False
        return True

    @property
    def summary(self):
        return self.meta.get('summary', '')

    @property
    def title(self):
        for maybe in ['title', 'bookmark-of', 'in-reply-to', 'repost-of']:
            maybe = self.meta.get(maybe, False)
            if maybe:
                return maybe
        return ''

    @property
    def url(self):
        return "%s/%s/" % (shared.config.get('site', 'url'), self.fname)

    @property
    def tmplfile(self):
        if self.ispage:
            return 'page.html'
        else:
            return 'singular.html'

    @property
    def html(self):
        return shared.Pandoc().convert(self.content)

    @property
    def offlinecopies(self):
        # stupidly simple property caching
        if hasattr(self, 'copies'):
            return self.copies

        copies = {}
        for maybe in ['bookmark-of', 'in-reply-to', 'repost-of']:
            maybe = self.meta.get(maybe, False)
            if not maybe:
                continue
            if not isinstance(maybe, list):
                maybe = [maybe]
            for url in maybe:
                copies[url] = OfflineCopy(url)
                copies[url].run()

        self.copies = copies
        return copies

    @property
    def exif(self):
        if not self.isphoto:
            return None

        exif = {}
        mapping = {
            'camera': [
                'Model'
            ],
            'aperture': [
                'FNumber',
                'Aperture'
            ],
            'shutter_speed': [
                'ExposureTime'
            ],
            'focallength35mm': [
                'FocalLengthIn35mmFormat',
            ],
            'focallength': [
                'FocalLength',
            ],
            'iso': [
                'ISO'
            ],
            'lens': [
                'LensID',
            ],
            'date': [
                'CreateDate',
                'DateTimeOriginal',
            ],
            'geo_latitude': [
                'GPSLatitude'
            ],
            'geo_longitude': [
                'GPSLongitude'
            ],
        }

        for ekey, candidates in mapping.items():
            for candidate in candidates:
                maybe = self.photo.meta.get(candidate, None)
                if maybe:
                    if 'geo_' in ekey:
                        exif[ekey] = round(float(maybe), 5)
                    else:
                        exif[ekey] = maybe
                    break

        return exif

    @property
    def rssenclosure(self):
        if not self.isphoto:
            return {}
        return self.photo.rssenclosure

    @property
    def tmplvars(self):
        return {
            'title': self.title,
            'published': self.published.datetime,
            'tags': self.tags,
            'author': dict(shared.config.items('author')),
            'content': self.content,
            'html': self.html,
            'category': self.category,
            'reactions': self.reactions,
            'updated': self.updated.datetime,
            'summary': self.meta.get('summary', ''),
            'exif': self.exif,
            'lang': self.lang,
            'syndicate': '',
            'slug': self.fname,
            'shortslug': self.shortslug,
            'rssenclosure': self.rssenclosure,
            'copies': self.offlinecopies,
        }

    @property
    def shortslug(self):
        return self.baseN(self.pubtime)

    @staticmethod
    def baseN(num, b=36, numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
        """ Used to create short, lowecase slug for a number (an epoch) passed """
        num = int(num)
        return ((num == 0) and numerals[0]) or (
            Singular.baseN(
                num // b,
                b,
                numerals
            ).lstrip(numerals[0]) + numerals[num % b]
        )

    async def render(self, renderer):
        logging.info("rendering and saving %s", self.fname)
        targetdir = os.path.abspath(os.path.join(
            shared.config.get('target', 'builddir'),
            self.fname
        ))
        target = os.path.join(targetdir, 'index.html')

        if not shared.config.getboolean('params', 'force') and os.path.isfile(target):
            ttime = int(os.path.getmtime(target))
            logging.debug('ttime is %d mtime is %d', ttime, self.mtime)
            if ttime == self.mtime:
                logging.debug('%s exists and up-to-date (lastmod: %d)', target, ttime)
                return

        if not os.path.isdir(targetdir):
            os.mkdir(targetdir)

        tmplvars = {
            'post': self.tmplvars,
            'site': renderer.sitevars,
            'taxonomy': {},
        }
        r = renderer.j2.get_template(self.tmplfile).render(tmplvars)
        with open(target, "w") as html:
            logging.debug('writing %s', target)
            html.write(r)
            html.close()
            os.utime(target, (self.mtime, self.mtime))


class Webmentioner(object):
    def __init__(self):
        self.dbpath = os.path.abspath(os.path.join(
            shared.config.get('target', 'builddir'),
            shared.config.get('var', 'webmentions')
        ))

        if os.path.isfile(self.dbpath):
            with open(self.dbpath, 'rt') as f:
                self.db = json.loads(f.read())
        else:
            self.db = {}

    async def ping(self, singular, dry_run = False):
        for target in singular.urls:
            record = {
                'mtime': singular.mtime,
                'source': singular.url,
                'target': target
            }
            h = json.dumps(record, sort_keys=True)
            h = hashlib.sha1(h.encode('utf-8')).hexdigest()
            if self.db.get(h, False):
                logging.debug("%s is already pinged from %s @ %d, skipping",
                    target, singular.url, singular.mtime)
                continue

            logging.info("sending webmention from %s to %s", singular, target)
            if not dry_run:
                ws = WebmentionSend(source, target)
                await ws.send(allowredirect=True, timeout=30)
            self.db[h] = record

    def finish(self):
        with open(self.dbpath, 'wt') as f:
            f.write(json.dumps(self.db, sort_keys=True, indent=4))


class NASG(object):
    def __init__(self):
        # --- set params
        parser = argparse.ArgumentParser(description='Parameters for NASG')
        parser.add_argument(
            '--clear',
            action='store_true',
            default=False,
            help='clear build directory in advance'
        )
        parser.add_argument(
            '--regenerate',
            action='store_true',
            default=False,
            help='force downsizing images'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            default=False,
            help='force rendering HTML'
        )
        parser.add_argument(
            '--loglevel',
            default='error',
            help='change loglevel'
        )
        parser.add_argument(
            '--nodownsize',
            action='store_true',
            default=False,
            help='skip image downsizing'
        )
        parser.add_argument(
            '--norender',
            action='store_true',
            default=False,
            help='skip rendering'
        )

        params = vars(parser.parse_args())
        shared.config.add_section('params')
        for k, v in params.items():
            shared.config.set('params', k, str(v))


        # remove the rest of the potential loggers
        while len(logging.root.handlers) > 0:
            logging.root.removeHandler(logging.root.handlers[-1])

        # --- set loglevel
        llevel = {
            'critical': 50,
            'error': 40,
            'warning': 30,
            'info': 20,
            'debug': 10
        }
        logging.basicConfig(
            level=llevel[shared.config.get('params', 'loglevel')],
            format='%(asctime)s - %(levelname)s - %(message)s'
        )

    async def __adownsize(self, images, existing):
        for fname, img in images:
            await img.downsize(existing)

    async def __acrender(self, content, renderer):
        for (pubtime, singular) in content:
            await singular.render(renderer)

    async def __atrender(self, taxonomies, renderer):
        for e in taxonomies:
            for name, t in e.items():
                await t.render(renderer)

    async def __afrender(self, front, renderer):
        await front.render(renderer)

    async def __aindex(self, content, searchdb):
        for (pubtime, singular) in content:
            await searchdb.append(singular)

    async def __aping(self, content, pinger):
        for (pubtime, singular) in content:
            await pinger.ping(singular)

    def run(self):

        if shared.config.getboolean('params', 'clear'):
            input('about to clear build directory, press enter to continue')
            shutil.rmtree(os.path.abspath(
                shared.config.get('target', 'builddir')
            ))

        loop = asyncio.get_event_loop()

        for d in shared.config.options('target'):
            if 'dir' in d and not os.path.isdir(shared.config.get('target', d)):
                os.mkdir(shared.config.get('target', d))

        logging.info("discovering images")
        images = Images()
        images.populate()
        existing = glob.glob(os.path.join(
            shared.config.get('target', 'filesdir'),
            "*"
        ))
        if not shared.config.getboolean('params', 'nodownsize'):
            logging.info("downsizing images")
            loop.run_until_complete(self.__adownsize(images, existing))

        logging.info("discovering content")
        content = Content(images)
        content.populate()

        renderer = Renderer()
        if not shared.config.getboolean('params', 'norender'):
            logging.info("rendering content")
            loop.run_until_complete(self.__acrender(content, renderer))

            logging.info("rendering categories and tags")
            loop.run_until_complete(self.__atrender([content.categories, content.tags], renderer))

            logging.info("rendering the front page elements")
            loop.run_until_complete(self.__afrender(content.front, renderer))

            logging.info("rendering sitemap")
            content.sitemap()

        logging.info("render magic.php")
        content.magicphp(renderer)

        logging.info("copy the static bits")
        src = shared.config.get('source', 'staticdir')
        for item in os.listdir(src):
            s = os.path.join(src, item)
            d = os.path.join(shared.config.get('target', 'builddir'), item)
            logging.debug("copying %s to %s", s, d)
            shutil.copy2(s, d)

        logging.info("pouplating searchdb")
        searchdb = SmartIndexer()
        loop.run_until_complete(self.__aindex(content, searchdb))
        searchdb.finish()

        logging.info("webmentioning urls")
        pinger = Webmentioner()
        loop.run_until_complete(self.__aping(content, pinger))
        pinger.finish()

        loop.close()

if __name__ == '__main__':
    worker = NASG()
    worker.run()
