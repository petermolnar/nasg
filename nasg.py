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
import getpass
import quopri
import base64
import mimetypes

import magic
import arrow
import wand.image
import similar_text
import frontmatter
from slugify import slugify
import langdetect
import requests
from whoosh import index
from whoosh import qparser
import jinja2
import urllib.parse
from webmentiontools.send import WebmentionSend
import bleach
from emoji import UNICODE_EMOJI
from bs4 import BeautifulSoup
from readability.readability import Document
import shared

def splitpath(path):
    parts = []
    (path, tail) = os.path.split(path)
    while path and tail:
        parts.insert(0,tail)
        (path,tail) = os.path.split(path)
    return parts


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


class BaseRenderable(object):
    def __init__(self):
        return


    def writerendered(self, content, mtime=None):
        mtime = mtime or self.mtime
        d = os.path.dirname(self.target)
        if not os.path.isdir(d):
            os.mkdir(d)

        with open(self.target, "w") as html:
            logging.debug('writing %s', self.target)
            html.write(content)
            html.close()
        os.utime(self.target, (mtime, mtime))


class Indexer(object):
    def __init__(self):
        self.target = os.path.abspath(os.path.join(
            shared.config.get('target', 'builddir'),
            shared.config.get('var', 'searchdb')
        ))

        if not os.path.isdir(self.target):
            os.mkdir(self.target)

        self.mtime = 0

        if index.exists_in(self.target):
            self.ix = index.open_dir(self.target)
            tocfiles = glob.glob(os.path.join(
                self.target,
                "_MAIN_*.toc"
            ))
            if len(tocfiles):
                self.mtime = int(os.path.getmtime(tocfiles[0]))
        else:
            self.ix = index.create_in(self.target, shared.schema)

        self.writer = self.ix.writer()
        self.qp = qparser.QueryParser("url", schema=shared.schema)


    async def append(self, singular):
        logging.debug("searching for existing index for %s", singular.fname)
        if self.mtime >= singular.mtime:
            logging.debug("search index is newer than post mtime (%d vs %d), skipping post", self.mtime, singular.mtime)
            return

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

        reactions = []
        for t, v in singular.reactions.items():
            if isinstance(v, list) and len(v):
                reactions = [*reactions, *v]

        content = "\n\n".join([
            "\n\n".join([
                bleach.clean(c, tags=[], strip_comments=True, strip=True)
                for c in [singular.sumhtml, singular.html]
            ]),
            "\n".join(["%s" % c for c in singular.tags]),
            "\n\n".join(reactions)
        ])

        weight = 1
        if singular.isbookmark or singular.isfav:
            weight = 10
        if singular.ispage:
            weight = 100

        if not len(singular.title):
            title = singular.fname
        else:
            title = singular.title

        if singular.photo:
            img = shared.Pandoc().convert("%s" % singular.photo)
        else:
            img = ''

        args = {
            'url': singular.url,
            'category': singular.category,
            'date': singular.published.datetime,
            'title': title,
            'weight': weight,
            'img': img,
            'content': content,
            'fuzzy': content,
            'mtime': singular.mtime
        }

        if exists:
            logging.info("updating search index with %s", singular.fname)
            self.writer.add_document(**args)
        else:
            logging.info("appending search index with %s", singular.fname)
            self.writer.update_document(**args)


    def finish(self):
        self.writer.commit()


class OfflineArchive(object):
    # keep in mind that these are frontmattered HTML files with full HTML and embedded images
    # they can get VERY large
    def __init__(self, url, content=None, decode_email=False):
        self.url = url
        self.parsed = urllib.parse.urlparse(url)
        self.fbase = shared.slugfname(url)
        self.fname = "%s.md" % self.fbase
        self.target = os.path.join(
            shared.config.get('source', 'offlinecopiesdir'),
            self.fname
        )
        self.targetd = os.path.join(
            shared.config.get('source', 'offlinecopiesdir'),
            self.fbase
        )
        if not os.path.isdir(self.targetd):
            os.mkdir(self.targetd)

        self.fm = frontmatter.loads('')
        self.fm.metadata = {
            'url': self.url,
            'date': arrow.utcnow().format("YYYY-MM-DDTHH:mm:ssZ"),
        }
        self.headers = requests.utils.default_headers()
        self.headers.update({
            'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
        })

        self.skip_fetch = False
        if content:
            self.skip_fetch = True
            if decode_email:
                content = quopri.decodestring(content)
                content = str(content, 'utf-8', errors='replace')
            self.fm.content = content
        #self.tmp = tempfile.mkdtemp(
            #'offlinearchive_',
            #dir=tempfile.gettempdir()
        #)
        #atexit.register(
            #shutil.rmtree,
            #os.path.abspath(self.tmp)
        #)
        #self.images = []

        self.exists = os.path.isfile(self.target)

    #def read(self):
        #if not self.exists:
            #return ''

        #with open(self.target, 'rt') as f:
            #self.fm = frontmatter.loads(f.read())

        #readable = ''
        #try:
            #readable = Document(self.fm.content)
            #readable = shared.Pandoc(False).convert(readable.summary())
            #readable = shared.Pandoc().convert(readable)
        #except Exception as e:
            #logging.error('Failed to readable %s', self.target)

        #return readable


    def _getimage(self, src):
        imgname, imgext = os.path.splitext(os.path.basename(src))
        imgtarget = os.path.join(
            self.targetd,
            "%s%s" % (slugify(imgname, only_ascii=True, lower=True), imgext)
        )
        try:
            logging.debug('donwloading image %s', src)
            r = requests.get(
                src,
                allow_redirects=True,
                timeout=60,
                stream=True
            )
            with open(imgtarget, 'wb') as f:
                for chunk in r.iter_content():
                    if chunk:
                        f.write(chunk)

            self.fm.content = self.fm.content.replace(
                src,
                '%s/%s' % (self.fbase, imgname)
            )
        except Exception as e:
            logging.error('pulling image %s failed: %s', src, e)
            return

    def _get_images(self):
        logging.debug("trying to save images")
        soup = BeautifulSoup(self.fm.content, 'lxml')

        embedded = re.compile(r'^data:.*')
        for img in soup.find_all('img'):
            src = img.get('src')
            if not src:
                continue
            if embedded.match(src):
                continue

            im = urllib.parse.urlparse(src)
            if not im.scheme:
                im = im._replace(scheme=self.parsed.scheme)
            if not im.netloc:
                im = im._replace(netloc=self.parsed.netloc)

            self._getimage(im.geturl())


    #def _getimage(self, src):
        #tmp = os.path.join(self.tmp, "%s" % slugify(os.path.basename(src))[:200])
        #try:
            #r = requests.get(
                #src,
                #allow_redirects=True,
                #timeout=60,
                #stream=True
            #)
            #with open(tmp, 'wb') as f:
                #for chunk in r.iter_content():
                    #if chunk:
                        #f.write(chunk)

            #logging.debug('trying to embed %s', src)
            #with open(tmp, 'rb') as imgdata:
                #data = str(base64.b64encode(imgdata.read()), 'ascii')
                #mimetype, encoding = mimetypes.guess_type(tmp)
                #self.fm.content = self.fm.content.replace(
                    #src,
                    #"data:%s;base64,%s" % (mimetype, data)
                #)
        #except Exception as e:
            #logging.error('pulling image %s failed: %s', src, e)
            #return

    #def _embed_images(self):
        #logging.debug("trying to embed images")
        #soup = BeautifulSoup(self.fm.content, 'lxml')

        #embedded = re.compile(r'^data:.*')
        #for img in soup.find_all('img'):
            #src = img.get('src')
            #if not src:
                #continue
            #if embedded.match(src):
                #continue

            #im = urllib.parse.urlparse(src)
            #if not im.scheme:
                #im = im._replace(scheme=self.parsed.scheme)
            #if not im.netloc:
                #im = im._replace(netloc=self.parsed.netloc)

            #self._getimage(im.geturl())


    def save(self):
        logging.info(
            "savig offline copy of\n\t%s to:\n\t%s",
            self.url,
            self.target
        )

        with open(self.target, 'wt') as f:
            f.write(frontmatter.dumps(self.fm))

    @property
    def archiveorgurl(self):
        logging.debug("trying archive.org for %s", self.url)
        a = self.fetch(
            "http://archive.org/wayback/available?url=%s" % self.url,
        )
        if not a:
            logging.debug("no entry for %s on archive.org", self.url)
            return None

        try:
            a = json.loads(a.text)
            aurl = a.get(
                'archived_snapshots', {}
            ).get(
                'closest', {}
            ).get(
                'url', None
            )
            logging.debug("found %s in archive.org for %s", aurl, self.url)
            self.updateurl(aurl)
            return self.fetch(aurl)
        except Exception as e:
            logging.error("archive.org parsing failed: %s", e)
            return None


    def fetch(self, url):
        try:
            r = requests.get(
                self.url,
                allow_redirects=True,
                timeout=60,
                headers=self.headers
            )
            if r.status_code == requests.codes.ok:
                return r
        except Exception as e:
            return None


    #def read():
        #if os.path.isfile(self.target):
            #with open(self.target) as f:
                #self.fm = frontmatter.loads(f.read())
                #return


    def run(self):
        if self.exists:
            logging.info("offline archive for %s already exists", self.url)
            return

        logging.info("prepairing offline copy of %s", self.url)

        if not self.skip_fetch:
            r = self.fetch(self.url)

            # in case it's not, try to look for an archive.org url:
            if not r:
                logging.warning("couldn't get live version of %s, trying archive.org", self.url)
                r = self.fetch(self.archiveorgurl)

            # no live and no archive.org entry :((
            # howver, by miracle, I may already have a copy, so skip if it's there already
            if not r:
                logging.error("no live or archive version of %s found :((", self.url)
                if not self.exists:
                    self.save()
                return

            self.fm.content = r.text

        self._get_images()
        self.save()


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
            d = arrow.now().datetime
        if form == 'c':
            return d.isoformat()
            #form = '%Y-%m-%dT%H:%M:%S%z'
        return d.strftime(form)


    @staticmethod
    def jinja_filter_slugify(s):
        return slugify(s, only_ascii=True, lower=True)


    @staticmethod
    def jinja_filter_search(s, r):
        if r in s:
            return True
        return False


# based on http://stackoverflow.com/a/10075210
class ExifTool(shared.CMDLine):
    """ Handles calling external binary `exiftool` in an efficient way """
    sentinel = "{ready}\n"


    def __init__(self):
        super().__init__('exiftool')


    def run(self, *filenames):
        return json.loads(self.execute(
            '-sort',
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


class Comment(BaseRenderable):
    def __init__(self, path):
        logging.debug("initiating comment object from %s", path)
        self.path = path
        self.fname, self.ext = os.path.splitext(os.path.basename(self.path))
        self.mtime = int(os.path.getmtime(self.path))
        self.meta = {}
        self.content = ''
        self.tmplfile = 'comment.html'
        self.__parse()


    def __repr__(self):
        return "%s" % (self.path)


    def __parse(self):
        with open(self.path, mode='rt') as f:
            self.meta, self.content = frontmatter.parse(f.read())

    @property
    def reacji(self):
        if hasattr(self, '_reacji'):
            return self._reacji

        self._reacji = ''
        maybe = bleach.clean(
            self.content,
            tags=[],
            strip_comments=True,
            strip=True,
        ).strip()

        if not len(maybe):
            self._reacji = '★'
        elif maybe in UNICODE_EMOJI:
            self._reacji = maybe

        #t = self.meta.get('type', 'webmention')
        #typemap = {
            #'like-of': '👍',
            #'bookmark-of': '🔖',
            #'favorite': '★',
        #}

        #if t in typemap.keys():
            #self._reacji = typemap[t]
        #else:

        return self._reacji


    @property
    def html(self):
        if hasattr(self, '_html'):
            return self._html

        tmp = shared.Pandoc().convert(self.content)
        self._html = bleach.clean(tmp, strip=True)
        return self._html


    @property
    def tmplvars(self):
        if hasattr(self, '_tmplvars'):
            return self._tmplvars

        self._tmplvars = {
            'published': self.published.datetime,
            'author': self.meta.get('author', {}),
            'content': self.content,
            'html': self.html,
            'source': self.source,
            'target': self.targeturl,
            'type': self.meta.get('type', 'webmention'),
            'reacji': self.reacji,
            'fname': self.fname
        }
        return self._tmplvars


    @property
    def published(self):
        if hasattr(self, '_published'):
            return self._published
        self._published = arrow.get(self.meta.get('date', self.mtime))
        return self._published


    @property
    def pubtime(self):
        return int(self.published.timestamp)


    @property
    def source(self):
        if hasattr(self, '_source'):
            return self._source
        s = self.meta.get('source', '')
        domains = shared.config.get('site', 'domains').split(' ')
        self._source = s
        for d in domains:
            if d in s:
                self._source = ''
        return self._source


    @property
    def targeturl(self):
        if hasattr(self, '_targeturl'):
            return self._targeturl
        t = self.meta.get('target', shared.config.get('site', 'url'))
        self._targeturl = '{p.path}'.format(p=urllib.parse.urlparse(t)).strip('/')
        return self._targeturl

    @property
    def target(self):
        if hasattr(self, '_target'):
            return self._target

        targetdir = os.path.abspath(os.path.join(
            shared.config.get('target', 'builddir'),
            shared.config.get('site', 'commentspath'),
            self.fname
        ))

        self._target = os.path.join(targetdir, 'index.html')
        return self._target


    async def render(self, renderer):
        logging.info("rendering and saving comment %s", self.fname)

        if not shared.config.getboolean('params', 'force') and os.path.isfile(self.target):
            ttime = int(os.path.getmtime(self.target))
            logging.debug('ttime is %d mtime is %d', ttime, self.mtime)
            if ttime == self.mtime:
                logging.debug(
                    '%s exists and up-to-date (lastmod: %d)',
                    self.target,
                    ttime
                )
                return

        tmplvars = {
            'reply': self.tmplvars,
            'site': renderer.sitevars,
            'taxonomy': {},
        }
        r = renderer.j2.get_template(self.tmplfile).render(tmplvars)
        self.writerendered(r)


class Comments(object):
    def __init__(self):
        self.files = glob.glob(os.path.join(
            shared.config.get('source', 'commentsdir'),
            "*.md"
        ))
        self.bytarget = {}


    def __getitem__(self, key):
        return self.bytarget.get(key, BaseIter())


    def populate(self):
        for fpath in self.files:
            item = Comment(fpath)
            t = item.targeturl
            if not self.bytarget.get(t):
                self.bytarget[t] = BaseIter()
            self.bytarget[t].append(item.pubtime, item)


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
            _meta = e.run(*self.files)
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
        self.cl = ''
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
        if self.is_downsizeable:
            if self.singleimage and not self.cl:
                self.cl = '.u-photo'
            elif self.singleimage:
                self.cl = '.u-photo %s' % self.cl

            return '[![%s](%s "%s%s"){.adaptimg}](%s){.adaptive %s}' % (
                self.alttext,
                self.fallback,
                self.fname,
                self.ext,
                self.target,
                self.cl
            )
        else:
            if not self.cl:
                self.cl = '.aligncenter'
            return '![%s](%s "%s%s"){%s}' % (
                self.alttext,
                self.fallback,
                self.fname,
                self.ext,
                self.cl
            )


    @property
    def exif(self):
        if not self.is_photo:
            return {}

        if hasattr(self, '_exif'):
            return self._exif

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
                maybe = self.meta.get(candidate, None)
                if maybe:
                    if 'geo_' in ekey:
                        exif[ekey] = round(float(maybe), 5)
                    else:
                        exif[ekey] = maybe
                    break

        self._exif = exif
        return self._exif


    @property
    def rssenclosure(self):
        """ Returns the largest available image for RSS to add as attachment """
        if hasattr(self, '_rssenclosure'):
            return self._rssenclosure

        target = self.sizes[-1][1]
        self._rssenclosure = {
            'mime': magic.Magic(mime=True).from_file(target['fpath']),
            'url': target['url'],
            'size':  os.path.getsize(target['fpath']),
            'fname':  self.fname
        }
        return self._rssenclosure


    @property
    def is_photo(self):
        if hasattr(self, '_is_photo'):
            return self._is_photo

        self._is_photo = False
        #if not pattern or not isinstance(pattern, str):
        #    return False
        pattern = re.compile(shared.config.get('photo', 'regex'))

        cpr = self.meta.get('Copyright', '')
        art = self.meta.get('Artist', '')
        if not cpr and not art:
            return False

        if cpr and art:
            if pattern.search(cpr) or pattern.search(art):
                self._is_photo = True

        return self._is_photo


    @property
    def is_downsizeable(self):
        if hasattr(self, '_is_downsizeable'):
            return self._is_downsizeable

        self._is_downsizeable = False
        """ Check if the image is large enough and jpeg or png in order to
        downsize it """
        fb = self.sizes[-1][0]
        ftype = self.meta.get('FileType', None)
        if not ftype:
            return self._is_downsizeable
        if ftype.lower() == 'jpeg' or ftype.lower() == 'png':
            width = int(self.meta.get('ImageWidth', 0))
            height = int(self.meta.get('ImageHeight', 0))
            if width > fb or height > fb:
                self._is_downsizeable = True

        return self._is_downsizeable


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
        if hasattr(self, '_pages'):
            return self._pages
        self._pages = math.ceil(len(self.data) / shared.config.getint('common', 'pagination'))
        return self._pages

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
        if hasattr(self, '_mtime'):
            return self._mtime
        self._mtime = int(list(sorted(self.data.keys(), reverse=True))[0])
        return self._mtime


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
        #if not self.slug or self.slug is 'None':
            #return

        self.__mkdirs()
        page = 1
        testpath = self.tpath(page)
        if not shared.config.getboolean('params', 'force') and os.path.isfile(testpath):
            ttime = int(os.path.getmtime(testpath))
            mtime = self.mtime
            if ttime == mtime:
                logging.info('taxonomy index for "%s" exists and up-to-date (lastmod: %d)', self.slug, ttime)
                return
            else:
                logging.info('taxonomy update needed: %s timestamp is %d, last post timestamp is %d (%s)',
                    testpath,
                    ttime,
                    mtime,
                    self.data[mtime].fname
                )

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
                'slug': self.slug,
                'taxonomy': self.taxonomy,
                'paged': page,
                'total': self.pages,
                'perpage': pagination,
                'lastmod': arrow.get(self.mtime).datetime
            },
            'site': renderer.sitevars,
            'posts': posttmpls,
        }

        r = renderer.j2.get_template('archive.html').render(tmplvars)
        with open(target, "wt") as html:
            html.write(r)
        os.utime(target, (self.mtime, self.mtime))

        if 1 == page:
            #target = os.path.join(self.feedp, 'index.rss')
            #logging.info("rendering RSS feed to %s", target)
            #r = renderer.j2.get_template('rss.html').render(tmplvars)
            #with open(target, "wt") as html:
                #html.write(r)
            #os.utime(target, (self.mtime, self.mtime))

            target = os.path.join(self.feedp, 'index.atom')
            logging.info("rendering Atom feed to %s", target)
            r = renderer.j2.get_template('atom.html').render(tmplvars)
            with open(target, "wt") as html:
                html.write(r)
            os.utime(target, (self.mtime, self.mtime))

        # ---
        # this is a joke
        # see http://indieweb.org/YAMLFeed
        # don't do YAMLFeeds.
        if 1 == page:
            fm = frontmatter.loads('')
            fm.metadata = {
                'site': {
                    'author': renderer.sitevars['author'],
                    'url': renderer.sitevars['url'],
                    'title': renderer.sitevars['title'],
                },
                'items': [],
            }

            for p in posttmpls:
                fm.metadata['items'].append({
                    'title': p['title'],
                    'url': "%s/%s/" % ( renderer.sitevars['url'], p['slug']),
                    'content': p['content'],
                    'summary': p['summary'],
                    'published': p['published'],
                    'updated': p['updated'],
                })

            target = os.path.join(self.feedp, 'index.yml')
            logging.info("rendering YAML feed to %s", target)
            with open(target, "wt") as html:
                html.write(frontmatter.dumps(fm))
            os.utime(target, (self.mtime, self.mtime))
        # ---

        if 1 == page:
            if not self.taxonomy or self.taxonomy == 'category':
                t = shared.config.get('site', 'websuburl')
                data = {
                    'hub.mode': 'publish',
                    'hub.url': "%s%s" % (
                        shared.config.get('site', 'url'), self.baseurl
                    )
                }
                logging.info("pinging %s with data %s", t, data)
                requests.post(t, data=data)


class Content(BaseIter):
    def __init__(self, images, comments, extensions=['md']):
        super(Content, self).__init__()
        self.images = images
        self.comments = comments
        basepath = shared.config.get('source', 'contentdir')
        self.files = []
        for ext in extensions:
            self.files += glob.glob(os.path.join(basepath, "*", "*.%s" % ext))
        self.tags = {}
        self.categories = {}
        self.front = Taxonomy()
        self.shortslugmap = {}


    def populate(self):
        now = arrow.utcnow().timestamp
        for fpath in self.files:
            item = Singular(fpath, self.images, self.comments)
            self.append(item.pubtime, item)
            #self.shortslugmap[item.shortslug] = item.fname

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
                #self.symlinktag(tslug, item.path)

    #def symlinktag(self, tslug, fpath):
        #fdir, fname = os.path.split(fpath)
        #tagpath = os.path.join(shared.config.get('source', 'tagsdir'), tslug)
        #if not os.path.isdir(tagpath):
            #os.mkdir(tagpath)
        #sympath = os.path.relpath(fdir, tagpath)
        #dst = os.path.join(tagpath, fname)
        #src = os.path.join(sympath, fname)
        #if not os.path.islink(dst):
            #os.symlink(src, dst)

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


class Singular(BaseRenderable):
    def __init__(self, path, images, comments):
        logging.debug("initiating singular object from %s", path)
        self.path = path
        self.images = images
        self.allcomments = comments
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
        #self.__filter_syndication()
        self.__filter_favs()
        self.__filter_images()
        if self.isphoto:
            self.content = "%s\n\n%s" % (
                self.photo,
                self.content,
            )
        if shared.config.getboolean('params', 'nooffline'):
            return
        trigger = self.offlinecopies

    #def __filter_syndication(self):
        #syndications = self.meta.get('syndicate', None)
        #if not syndications:
            #return
        #s = "\n\n".join(['<a href="%s" class="u-syndication"></a>' % s for s in syndications])
        #self.content = "%s\n\n%s" % (
            #s,
            #self.content
        #)

    def __filter_favs(self):
        url = self.meta.get('favorite-of',
            self.meta.get('like-of',
                self.meta.get('bookmark-of',
                    False
                )
            )
        )

        if not url:
            return

        img = self.meta.get('image', False)
        imgs = self.meta.get('images', [])
        if img:
            imgs.append(img)

        if not imgs or not len(imgs):
            return

        c = ''
        for i in imgs:
            c = '%s\n[![%s](/%s/%s)](%s){.favurl}' % (
                c,
                self.title,
                shared.config.get('source', 'files'),
                i,
                url
            )

        if self.isbookmark:
            c = "%s\n\n%s" % (c, self.content)

        self.content = c


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
    def comments(self):
        if hasattr(self, '_comments'):
            return self._comments

        # the comments could point to both the "real" url and the shortslug
        # so I need to get both
        c = {}
        for by in [self.fname, self.shortslug]:
            c = {**c, **self.allcomments[by].data}
        #self._comments = [c[k].tmplvars for k in list(sorted(c.keys(), reverse=True))]
        self._comments = [c[k] for k in list(sorted(c.keys(), reverse=True))]
        return self._comments


    @property
    def replies(self):
        if hasattr(self, '_replies'):
            return self._replies
        self._replies = [c.tmplvars for c in self.comments if not len(c.reacji)]
        return self._replies


    @property
    def reacjis(self):
        if hasattr(self, '_reacjis'):
            return self._reacjis
        reacjis = {}
        for c in self.comments:
            rj = c.reacji

            if not len(rj):
                continue

            if not reacjis.get(rj, False):
                reacjis[rj] = []

            reacjis[rj].append(c.tmplvars)

        self._reacjis = reacjis
        return self._reacjis


    @property
    def reactions(self):
        if hasattr(self, '_reactions'):
            return self._reactions
        # getting rid of '-' to avoid css trouble and similar
        convert = {
            'bookmark-of': 'bookmark',
            'repost-of': 'repost',
            'in-reply-to': 'reply',
            'favorite-of': 'fav',
            'like-of': 'like',
        }
        reactions = {}

        for k, v in convert.items():
            x = self.meta.get(k, None)
            if not x:
                continue
            if isinstance(x, str):
                x = [x]
            reactions[v] = x

        self._reactions = reactions
        return self._reactions


    @property
    def syndicate(self):
        return self.meta.get('syndicate', [])

    @property
    def urls(self):
        if hasattr(self, '_urls'):
            return self._urls

        #urls = shared.URLREGEX.findall(self.content)
        #urls = [*urls, *self.syndicate]
        urls = list(self.syndicate)

        for reactionurls in self.reactions.values():
            urls = [*urls, *reactionurls]

        #r = []
        #logging.debug('searching for urls for %s', self.fname)
        #for link in urls:
            #purl = urllib.parse.urlparse(link)
            #if purl.netloc in shared.config.get('site', 'domains'):
                #logging.debug('excluding url %s - %s matches %s', link, purl.netloc, shared.config.get('site', 'domains'))
                #continue
            #if link in r:
                #continue
            #r.append(link)

        self._urls = urls
        logging.debug('urls for %s: %s', self.fname, urls)
        return self._urls


    @property
    def lang(self):
        if hasattr(self, '_lang'):
            return self._lang

        lang = 'en'
        try:
            lang = langdetect.detect("\n".join([
                self.title,
                self.content
            ]))
        except:
            pass
        self._lang = lang
        return self._lang


    @property
    def tags(self):
        return list(self.meta.get('tags', []))


    @property
    def published(self):
        if hasattr(self, '_published'):
            return self._published
        self._published = arrow.get(
            self.meta.get('published', self.mtime)
        )
        return self._published


    @property
    def updated(self):
        if hasattr(self, '_updated'):
            return self._updated
        self._updated = arrow.get(
            self.meta.get('updated',
                self.meta.get('published', self.mtime)
            )
        )
        return self._updated


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
    def isreply(self):
        return self.meta.get('in-reply-to', False)


    # TODO
    #@property
    #def isrvsp(self):
    # r'<data class="p-rsvp" value="([^"])">([^<]+)</data>'


    @property
    def isfav(self):
        r = False
        for maybe in ['like-of', 'favorite-of']:
            maybe = self.meta.get(maybe, False)
            if maybe:
                r = maybe
                break
        return r


    @property
    def ispage(self):
        if not self.meta:
            return True
        return False


    @property
    def isonfront(self):
        if self.ispage:
            return False
        if self.isbookmark:
            return False
        if self.isfav:
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
        if hasattr(self, '_title'):
            return self._title

        self._title = ''
        for maybe in ['title', 'bookmark-of', 'in-reply-to', 'repost-of']:
            maybe = self.meta.get(maybe, False)
            if maybe:
                if isinstance(maybe, list):
                    maybe = maybe.pop()
                self._title = maybe.replace('\n', ' ').replace('\r', '')
                break
        return self._title


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
        if hasattr(self, '_html'):
            return self._html
        self._html = shared.Pandoc().convert(self.content)
        return self._html


    @property
    def sumhtml(self):
        if hasattr(self, '_sumhtml'):
            return self._sumhtml
        self._sumhtml = self.meta.get('summary', '')
        if len(self._sumhtml):
            self._sumhtml = shared.Pandoc().convert(self.summary)
        return self._sumhtml


    @property
    def offlinecopies(self):
        # stupidly simple property caching
        if hasattr(self, 'copies'):
            return self.copies

        copies = {}
        for maybe in ['bookmark-of', 'in-reply-to', 'repost-of', 'favorite-of']:
            maybe = self.meta.get(maybe, False)
            if not maybe:
                continue
            if not isinstance(maybe, list):
                maybe = [maybe]
            for url in maybe:
                arch = OfflineArchive(url)
                arch.run()
                #copies[url] = arch.read()

        #self.copies = copies
        #return copies


    @property
    def exif(self):
        if not self.isphoto:
            return {}
        return self.photo.exif


    @property
    def rssenclosure(self):
        if not self.isphoto:
            return {}
        return self.photo.rssenclosure


    @property
    def tmplvars(self):
        if hasattr(self, '_tmplvars'):
            return self._tmplvars

        self._tmplvars = {
            'title': self.title,
            'published': self.published.datetime,
            'tags': self.tags,
            'author': dict(shared.config.items('author')),
            'content': self.content,
            'html': self.html,
            'category': self.category,
            'reactions': self.reactions,
            'updated': self.updated.datetime,
            'summary': self.summary,
            'sumhtml': self.sumhtml,
            'exif': self.exif,
            'lang': self.lang,
            'syndicate': self.syndicate,
            'slug': self.fname,
            'shortslug': self.shortslug,
            'rssenclosure': self.rssenclosure,
            'comments': self.comments,
            'replies': self.replies,
            'reacjis': self.reacjis,
        }
        return self._tmplvars


    @property
    def shortslug(self):
        if hasattr(self, '_shortslug'):
            return self._shortslug
        self._shortslug = shared.baseN(self.pubtime)
        return self._shortslug


    @property
    def target(self):
        targetdir = os.path.abspath(os.path.join(
            shared.config.get('target', 'builddir'),
            self.fname
        ))
        return os.path.join(targetdir, 'index.html')


    async def rendercomments(self, renderer):
        for comment in self.comments:
            await comment.render(renderer)


    async def render(self, renderer):
        # this is only when I want salmentions and I want to include all of the comments as well
        # otherwise it affects both webmentions sending and search indexing
        #if len(self.comments):
            #lctime = self.comments[0].mtime
            #if lctime > self.mtime:
                #self.mtime = lctime
        #await self.rendercomments(renderer)

        mtime = self.mtime
        if len(self.comments):
            lctime = self.comments[0].mtime
            if lctime > self.mtime:
                mtime = lctime

        logging.info("rendering and saving %s", self.fname)
        if not shared.config.getboolean('params', 'force') and os.path.isfile(self.target):
            ttime = int(os.path.getmtime(self.target))
            logging.debug('ttime is %d mtime is %d', ttime, mtime)
            if ttime == mtime:
                logging.debug(
                    '%s exists and up-to-date (lastmod: %d)',
                    self.target,
                    ttime
                )
                return

        tmplvars = {
            'post': self.tmplvars,
            'site': renderer.sitevars,
            'taxonomy': {},
        }
        r = renderer.j2.get_template(self.tmplfile).render(tmplvars)
        self.writerendered(r, mtime)


    async def ping(self, pinger):
        logging.debug('urls in %s: %s', self.fname, self.urls)
        for target in self.urls:
            record = {
                'mtime': self.mtime,
                'source': self.url,
                'target': target
            }
            h = json.dumps(record, sort_keys=True)
            h = hashlib.sha1(h.encode('utf-8')).hexdigest()
            if pinger.db.get(h, False):
                logging.debug(
                    "%s is already pinged from %s @ %d, skipping",
                    target, self.url, self.mtime
                )
                continue

            logging.info("sending webmention from %s to %s", self.url, target)
            ws = WebmentionSend(self.url, target)
            try:
                ws.send(allow_redirects=True, timeout=30)
            except Exception as e:
                logging.error('ping failed to %s', target)

            pinger.db[h] = record


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


    def finish(self):
        with open(self.dbpath, 'wt') as f:
            f.write(json.dumps(self.db, sort_keys=True, indent=4))


class NASG(object):
    lockfile = os.path.join(tempfile.gettempdir(), 'nasg_%s.lock' % getpass.getuser())

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
            '--nooffline',
            action='store_true',
            default=False,
            help='skip offline copie checks'
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
        parser.add_argument(
            '--refetch',
            action='store_true',
            default=False,
            help='force re-fetching offline archives'
        )

        params = vars(parser.parse_args())
        shared.config.add_section('params')
        for k, v in params.items():
            shared.config.set('params', k, str(v))


        # remove the rest of the potential loggers
        while len(logging.root.handlers) > 0:
            logging.root.removeHandler(logging.root.handlers[-1])

        # --- set loglevel
        logging.basicConfig(
            level=shared.LLEVEL[shared.config.get('params', 'loglevel')],
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
            await singular.ping(pinger)

    def __atindexrender(self, content, renderer):
        m = {
            'category': content.categories,
            'tag': content.tags
        }

        for p, taxonomy in m.items():
            target = os.path.abspath(os.path.join(
                shared.config.get('target', 'builddir'),
                p,
                'index.html'
            ))

            tmplvars = {
                'site': renderer.sitevars,
                'taxonomy': {},
                'taxonomies': {}
            }

            for name, t in taxonomy.items():
                logging.debug('adding %s to taxonomyindex' % name)
                tmplvars['taxonomies'][name] = [{'title': t.data[k].title, 'url': t.data[k].url} for k in list(sorted(
        t.data.keys(), reverse=True))]

            tmplvars['taxonomies'] = sorted(tmplvars['taxonomies'].items())
            logging.debug('rendering taxonomy index to %s', target)
            r = renderer.j2.get_template('archiveindex.html').render(tmplvars)
            with open(target, "wt") as html:
                html.write(r)


    def run(self):
        if os.path.isfile(self.lockfile):
            raise ValueError(
                "Lockfile is present at %s; another instance is running." % (
                    self.lockfile
                )
            )
        else:
            atexit.register(os.remove, self.lockfile)
            with open(self.lockfile, "wt") as f:
                f.write(arrow.utcnow().format())

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

        logging.info("discovering comments")
        comments = Comments()
        comments.populate()

        logging.info("discovering content")
        content = Content(images, comments)
        content.populate()

        renderer = Renderer()
        if not shared.config.getboolean('params', 'norender'):
            logging.info("rendering content")
            loop.run_until_complete(self.__acrender(
                content, renderer
            ))

            logging.info("rendering categories and tags")
            loop.run_until_complete(self.__atrender(
                [content.categories, content.tags], renderer
            ))

            logging.info("rendering the front page elements")
            loop.run_until_complete(self.__afrender(
                content.front, renderer
            ))

            logging.info("rendering taxonomy indexes")
            self.__atindexrender(content, renderer)

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
        searchdb = Indexer()
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
