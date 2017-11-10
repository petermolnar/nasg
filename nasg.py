#!/usr/bin/env python3

import os
import re
import logging
import json
import glob
import argparse
import shutil
from urllib.parse import urlparse
import asyncio
from math import ceil
import csv
import frontmatter
import arrow
import langdetect
import wand.image
from emoji import UNICODE_EMOJI
import shared


class MagicPHP(object):
    ''' router PHP generator '''
    name = 'index.php'

    def __init__(self):
        # init 'gone 410' array
        self.gones = []
        f_gone = shared.config.get('var', 'gone')
        if os.path.isfile(f_gone):
            with open(f_gone) as csvfile:
                reader = csv.reader(csvfile, delimiter=' ')
                for row in reader:
                    self.gones.append(row[0])
        # init manual redirects array
        self.redirects = []
        f_redirect = shared.config.get('var', 'redirects')
        if os.path.isfile(f_redirect):
            with open(f_redirect) as csvfile:
                reader = csv.reader(csvfile, delimiter=' ')
                for row in reader:
                    self.redirects.append((row[0], row[1]))

    @property
    def phpfile(self):
        return os.path.join(
            shared.config.get('common', 'build'),
            self.name
        )

    async def render(self):
        logging.info('saving %s', self.name)
        o = self.phpfile
        tmplfile = "%s.html" % (self.__class__.__name__)
        r = shared.j2.get_template(tmplfile).render({
            'site': shared.site,
            'redirects': self.redirects,
            'gones': self.gones
        })
        with open(o, 'wt') as out:
            logging.debug('writing file %s', o)
            out.write(r)


class NoDupeContainer(object):
    ''' Base class to hold keys => data dicts with errors on dupes '''
    def __init__(self):
        self.data = {}
        self.default = None

    def append(self, key, value):
        # all clear
        if key not in self.data:
            self.data.update({key: value})
            return

        # problem
        logging.error(
            "duplicate key error when populating %s: %s",
            self.__class__.__name__,
            key
        )
        logging.error(
            "current: %s",
            self.data.get(key)
        )
        logging.error(
            "problem: %s",
            value
        )

        return

    # TODO: return ordered version of data

    def __getitem__(self, key):
        return self.data.get(key, self.default)

    def __setitem__(self, key, value):
        return self.append(key, value)

    def __contains__(self, key):
        if key in self.data.keys():
            return True
        return False

    def __len__(self):
        return len(self.data.keys())

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


class FContainer(NoDupeContainer):
    """ This is a container that holds a lists of files based on Container so
    it errors on duplicate slugs and is popolated with recorsive glob """
    def __init__(self, dirs, extensions=['*']):
        super().__init__()
        files = []
        for ext in extensions:
            for p in dirs:
                files.extend(glob.iglob(
                    os.path.join(p, '*.%s' % (ext)),
                    recursive=True
                ))
        # eliminate duplicates
        files = list(set(files))
        for fpath in files:
            fname = os.path.basename(fpath)
            self.append(fname, fpath)


class Content(FContainer):
    """ This is a container that holds markdown files that are parsed when the
    container is populated on the fly; based on FContainer which is a Container
    """
    def __init__(self):
        dirs = [os.path.join(shared.config.get('dirs', 'content'), "**")]
        extensions = ['md', 'jpg']
        super().__init__(dirs, extensions)
        for fname, fpath in self.data.items():
            self.data.update({fname: Singular(fpath)})


class Category(NoDupeContainer):
    """ A Category which holds pubtime (int) => Singular data """
    indexfile = 'index.html'
    feedfile = 'index.xml'
    feeddir = 'feed'
    pagedir = 'page'
    taxonomy = 'category'

    def __init__(self, name=''):
        self.name = name
        super().__init__()

    def append(self, post):
        return super().append(post.pubtime, post)

    @property
    def mtime(self):
        return int(sorted(self.data.keys(), reverse=True)[0])

    @property
    def is_uptodate(self):
        index = os.path.join(self.path_paged(), self.indexfile)
        if not os.path.isfile(index):
            return False
        mtime = os.path.getmtime(index)
        if mtime == self.mtime:
            return True
        return False

    @property
    def title(self):
        return self.name

    @property
    def url(self):
        if self.name:
            url = "/%s/%s/" % (
                self.taxonomy,
                self.name,
            )
        else:
            url = '/'
        return url

    def path_paged(self, page=1, feed=False):
        x = shared.config.get('common', 'build')

        if self.name:
            x = os.path.join(
                x,
                self.taxonomy,
                self.name,
            )

        if page == 1:
            if feed:
                x = os.path.join(x, self.feeddir)
        else:
            x = os.path.join(x, self.pagedir, "%s" % page)

        if not os.path.isdir(x):
            os.makedirs(x)
        return x

    def write_html(self, path, content):
        with open(path, 'wt') as out:
            logging.debug('writing file %s', path)
            out.write(content)
        os.utime(path, (self.mtime, self.mtime))

    async def render(self):
        pagination = shared.config.getint('display', 'pagination')
        pages = ceil(len(self.data) / pagination)
        page = 1
        while page <= pages:
            # list relevant post templates
            start = int((page-1) * pagination)
            end = int(start + pagination)
            posttmpls = [
                self.data[k].tmplvars
                for k in list(sorted(
                    self.data.keys(),
                    reverse=True
                ))[start:end]
            ]
            # define data for template
            tmplvars = {
                'taxonomy': {
                    'title': self.title,
                    'name': self.name,
                    'page': page,
                    'total': pages,
                    'perpage': pagination,
                    'lastmod': arrow.get(self.mtime).format(
                        shared.ARROWFORMAT['rcf']
                    ),
                    'url': self.url,
                    'feed': "%s/%s/" % (
                        self.url,
                        shared.config.get('site', 'feed')
                    ),
                },
                'site': shared.site,
                'posts': posttmpls,
            }
            # render HTML
            dirname = self.path_paged(page)
            o = os.path.join(dirname, self.indexfile)
            logging.info(
                "Rendering page %d/%d of category %s to %s",
                page,
                pages,
                self.name,
                o
            )
            tmplfile = "%s.html" % (self.__class__.__name__)
            r = shared.j2.get_template(tmplfile).render(tmplvars)
            self.write_html(o, r)
            # render feed
            if page == 1:
                dirname = self.path_paged(page, feed=True)
                o = os.path.join(dirname, self.feedfile)
                logging.info(
                    "Rendering feed of category %s to  %s",
                    self.name,
                    o
                )
                tmplfile = "%s_%s.html" % (
                    self.__class__.__name__,
                    self.feeddir
                )
                r = shared.j2.get_template(tmplfile).render(tmplvars)
                self.write_html(o, r)
            # inc. page counter
            page = page+1


class Singular(object):
    indexfile = 'index.html'

    def __init__(self, fpath):
        logging.debug("initiating singular object from %s", fpath)
        self.fpath = fpath
        self.mtime = os.path.getmtime(self.fpath)
        self.stime = self.mtime
        self.fname, self.fext = os.path.splitext(os.path.basename(self.fpath))
        self.category = os.path.basename(os.path.dirname(self.fpath))
        self._images = NoDupeContainer()

        if self.fext == '.md':
            with open(self.fpath, mode='rt') as f:
                self.fm = frontmatter.parse(f.read())
            self.meta, self.content = self.fm
            self.photo = None
        elif self.fext == '.jpg':
            self.photo = WebImage(self.fpath)
            self.meta = self.photo.fm_meta
            self.content = self.photo.fm_content
            self.photo.inline = False
            self.photo.cssclass = 'u-photo'

    def init_extras(self):
        self.receive_webmentions()
        c = self.comments

    # note: due to SQLite locking, this will not be async for now
    def receive_webmentions(self):
        wdb = shared.WebmentionQueue()
        queued = wdb.get_queued(self.url)
        for incoming in queued:
            wm = Webmention(
                incoming.get('source'),
                incoming.get('target'),
                incoming.get('dt')
            )
            wm.receive()
            wdb.entry_done(incoming.get('id'))
        wdb.finish()

    # note: due to SQLite locking, this will not be async for now
    def send_webmentions(self):
        if not self.is_reply:
            return
        wdb = shared.WebmentionQueue()
        wid = wdb.queue(self.url, self.is_reply)
        wm = Webmention(
            self.url,
            self.is_reply
        )
        wm.send()
        wdb.entry_done(wid)
        wdb.finish()

    @property
    def redirects(self):
        r = self.meta.get('redirect', [])
        r.append(self.shortslug)
        return list(set(r))

    @property
    def is_uptodate(self):
        if not os.path.isfile(self.htmlfile):
            return False
        mtime = os.path.getmtime(self.htmlfile)
        if mtime >= self.stime:
            return True
        return False

    @property
    def htmlfile(self):
        return os.path.join(
            shared.config.get('common', 'build'),
            self.fname,
            self.indexfile
        )

    @property
    def images(self):
        if self.photo:
            self._images.append(self.fname, self.photo)
        # add inline images
        for shortcode, alt, fname, title, css in self.inline_images:
            # this does the appending automatically
            im = self._find_image(fname)

        return self._images

    @property
    def comments(self):
        comments = NoDupeContainer()
        cfiles = []
        lookin = [*self.redirects, self.fname]
        for d in lookin:
            maybe = glob.glob(
                os.path.join(
                    shared.config.get('dirs', 'comment'),
                    d,
                    '*.md'
                )
            )
            cfiles = [*cfiles, *maybe]
        for cpath in cfiles:
            cmtime = os.path.getmtime(cpath)
            if cmtime > self.stime:
                self.stime = cmtime

            c = Comment(cpath)
            comments.append(c.mtime, c)
        return comments

    @property
    def replies(self):
        r = {}
        for mtime, c in self.comments:
            if c.type == 'webmention':
                r.update({mtime:c.tmplvars})
        return sorted(r.items())

    @property
    def reactions(self):
        r = {}
        for mtime, c in self.comments:
            if c.type == 'webmention':
                continue
            if c.type not in r:
                r[c.type] = {}
            r[c.type].update({mtime:c.tmplvars})

        for icon, comments in r.items():
            r[icon] = sorted(comments.items())
        return r

    @property
    def exif(self):
        if not self.photo:
            return {}
        return self.photo.exif

    @property
    def published(self):
        return arrow.get(self.meta.get('published', self.mtime))

    @property
    def updated(self):
        u = self.meta.get('updated', False)
        if u:
            u = arrow.get(u)
        return u

    @property
    def pubtime(self):
        return int(self.published.timestamp)

    @property
    def is_reply(self):
        return self.meta.get('in-reply-to', False)

    @property
    def is_future(self):
        now = arrow.utcnow().timestamp
        if self.pubtime > now:
            return True
        return False

    @property
    def licence(self):
        l = shared.config.get(
            'licence',
            self.category,
            fallback=shared.config.get('licence', 'default',)
        )
        return {
            'text': 'CC %s 4.0' % l.upper(),
            'url': 'https://creativecommons.org/licenses/%s/4.0/' % l,
        }

    @property
    def corpus(self):
        corpus = "\n".join([
            "%s" % self.meta.get('title', ''),
            "%s" % self.fname,
            "%s" % self.meta.get('summary', ''),
            "%s" % self.content,
        ])

        if self.photo:
            corpus = corpus + "\n".join(self.meta.get('tags', []))

        return corpus

    @property
    def lang(self):
        # default is English, this will only be changed if the try
        # succeeds and actually detects a language
        lang = 'en'
        try:
            lang = langdetect.detect("\n".join([
                self.fname,
                self.meta.get('title', ''),
                self.content
            ]))
        except:
            pass
        return lang

    def _find_image(self, fname):
        fname = os.path.basename(fname)
        pattern = os.path.join(
            shared.config.get('dirs', 'files'),
            '**',
            fname
        )
        logging.debug('trying to locate image %s in %s', fname, pattern)
        maybe = glob.glob(pattern)

        if not maybe:
            logging.error('image not found: %s', fname)
            return None

        maybe = maybe.pop()
        logging.debug('image found: %s', maybe)
        if fname not in self._images:
            im = WebImage(maybe)
            self._images.append(fname, im)
        return self._images[fname]

    @property
    def inline_images(self):
        return shared.REGEX['mdimg'].findall(self.content)

    @property
    def url(self):
        return "%s/%s" % (shared.config.get('site', 'url'), self.fname)

    @property
    def body(self):
        body = "%s" % (self.content)
        # get inline images, downsize them and convert them to figures
        for shortcode, alt, fname, title, css in self.inline_images:
            #fname = os.path.basename(fname)
            im = self._find_image(fname)
            if not im:
                continue

            im.alt = alt
            im.title = title
            im.cssclass = css
            body = body.replace(shortcode, str(im))
        return body

    @property
    def html(self):
        html = "%s" % (self.body)

        # add photo
        if self.photo:
            html = "%s\n%s" % (str(self.photo), html)

        return shared.Pandoc().convert(html)

    @property
    def title(self):
        maybe = self.meta.get('title', False)
        if maybe:
            return maybe
        if self.is_reply:
            return "RE: %s" % self.is_reply
        return self.published.format(shared.ARROWFORMAT['display'])

    @property
    def summary(self):
        s = self.meta.get('summary', '')
        if not s:
            return s
        return shared.Pandoc().convert(s)

    @property
    def shortslug(self):
        return shared.baseN(self.pubtime)

    @property
    def syndicate(self):
        urls = []
        if self.photo and self.photo.is_photo:
            urls.append("https://brid.gy/publish/flickr")
        return urls

    @property
    def tmplvars(self):
        # very simple caching because we might use this 4 times:
        # post HTML, category, front posts and atom feed
        if not hasattr(self, '_tmplvars'):
            self._tmplvars = {
                'title': self.title,
                'pubtime': self.published.format(
                    shared.ARROWFORMAT['iso']
                ),
                'pubdate': self.published.format(
                    shared.ARROWFORMAT['display']
                ),
                'pubrfc': self.published.format(
                    shared.ARROWFORMAT['rcf']
                ),
                'category': self.category,
                'html': self.html,
                'lang': self.lang,
                'slug': self.fname,
                'shortslug': self.shortslug,
                'licence': self.licence,
                'is_reply': self.is_reply,
                'age': int(self.published.format('YYYY')) - int(arrow.utcnow().format('YYYY')),
                'summary': self.summary,
                'replies': self.replies,
                'reactions': self.reactions,
                'syndicate': self.syndicate
            }
        return self._tmplvars

    async def render(self):
        logging.info('rendering %s', self.fname)
        o = self.htmlfile

        tmplfile = "%s.html" % (self.__class__.__name__)
        r = shared.j2.get_template(tmplfile).render({
            'post': self.tmplvars,
            'site': shared.site,
        })

        d = os.path.dirname(o)
        if not os.path.isdir(d):
            logging.debug('creating directory %s', d)
            os.makedirs(d)
        with open(o, 'wt') as out:
            logging.debug('writing file %s', o)
            out.write(r)
        # use the comment time, not the source file time for this
        os.utime(o, (self.stime, self.stime))

    def __repr__(self):
        return "%s/%s" % (self.category, self.fname)


class WebImage(object):
    def __init__(self, fpath):
        logging.info("parsing image: %s", fpath)
        self.fpath = fpath
        self.mtime = os.path.getmtime(self.fpath)
        bname = os.path.basename(fpath)
        self.fname, self.fext = os.path.splitext(bname)
        self.title = ''
        self.alt = bname
        self.target = ''
        self.cssclass = ''

    @property
    def fm_content(self):
        return self.meta.get('Description', '')

    @property
    def fm_meta(self):
        return {
            'published': self.meta.get(
                'ReleaseDate',
                self.meta.get('ModifyDate')
            ),
            'title': self.meta.get('Headline', self.fname),
            'tags': list(set(self.meta.get('Subject', []))),
        }

    @property
    def href(self):
        if len(self.target):
            return self.target

        if not self.is_downsizeable:
            return False

        return self.sizes[-1][1]['url']

    @property
    def src(self):
        # is the image is too small to downsize, it will be copied over
        # so the link needs to point at
        src = "/%s/%s" % (
            shared.config.get('common', 'files'),
            "%s%s" % (self.fname, self.fext)
        )

        if self.is_downsizeable:
            try:
                src = [
                    e for e in self.sizes \
                    if e[0] == shared.config.getint('photo', 'default')
                ][0][1]['url']
            except:
                pass
        return src

    @property
    def meta(self):
        if not hasattr(self, '_exif'):
            # reading EXIF is expensive enough even with a static generator
            # to consider caching it, so I'll do that here
            cpath = os.path.join(
                shared.config.get('var', 'cache'),
                "%s.exif.json" % self.fname
            )

            if os.path.exists(cpath):
                cmtime = os.path.getmtime(cpath)
                if cmtime >= self.mtime:
                    with open(cpath, 'rt') as f:
                        self._exif = json.loads(f.read())
                        return self._exif

            self._exif = shared.ExifTool(self.fpath).read()
            if not os.path.isdir(shared.config.get('var', 'cache')):
                os.makedirs(shared.config.get('var', 'cache'))
            with open(cpath, 'wt') as f:
                f.write(json.dumps(self._exif))
        return self._exif

    @property
    def is_photo(self):
        # missing regex from config
        if 'photo' not in shared.REGEX:
            logging.debug('%s photo regex missing from config')
            return False

        cpr = self.meta.get('Copyright', '')
        art = self.meta.get('Artist', '')

        # both Artist and Copyright missing from EXIF
        if not cpr and not art:
            logging.debug('%s Artist or Copyright missing from EXIF')
            return False

        # we have regex, Artist and Copyright, try matching them
        pattern = re.compile(shared.config.get('photo', 'regex'))
        if pattern.search(cpr) or pattern.search(art):
            return True

        logging.debug('%s patterns did not match')
        return False

    @property
    def exif(self):
        exif = {}
        if not self.is_photo:
            return exif

        mapping = {
            'camera':           ['Model'],
            'aperture':         ['FNumber', 'Aperture'],
            'shutter_speed':    ['ExposureTime'],
            #'focallength':      ['FocalLengthIn35mmFormat', 'FocalLength'],
            'focallength':      ['FocalLength'],
            'iso':              ['ISO'],
            'lens':             ['LensID', 'LensSpec', 'Lens'],
            'geo_latitude':     ['GPSLatitude'],
            'geo_longitude':    ['GPSLongitude'],
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

    @property
    def sizes(self):
        sizes = []
        _max = max(
            int(self.meta.get('ImageWidth')),
            int(self.meta.get('ImageHeight'))
        )

        for size in shared.config.options('downsize'):
            if _max < int(size):
                continue

            name = '%s_%s%s' % (
                self.fname,
                shared.config.get('downsize', size),
                self.fext
            )

            fpath = os.path.join(
                shared.config.get('common', 'build'),
                shared.config.get('common', 'files'),
                name
            )

            exists = os.path.isfile(fpath)
            # in case there is a downsized image compare against the main
            # file's mtime and invalidate the existing if it's older
            if exists:
                mtime = os.path.getmtime(fpath)
                if self.mtime > mtime:
                    exists = False

            sizes.append((
                int(size),
                {
                    'fpath': fpath,
                    'exists': os.path.isfile(fpath),
                    'url': "%s/%s/%s" % (
                        shared.config.get('site', 'url'),
                        shared.config.get('common', 'files'),
                        name
                    ),
                    'crop': shared.config.getboolean(
                        'crop',
                        size,
                        fallback=False
                    )
                }
            ))
        return sorted(sizes, reverse=False)

    @property
    def is_downsizeable(self):
        """ Check if the image is large enought to downsize it """
        ftype = self.meta.get('FileType', None)
        if not ftype:
            return False
        elif ftype.lower() != 'jpeg' and ftype.lower() != 'png':
            return False

        _max = max(
            int(self.meta.get('ImageWidth')),
            int(self.meta.get('ImageHeight'))
        )
        _min = shared.config.getint('photo', 'default')
        if _max > _min:
            return True

        return False

    def _maybe_watermark(self, img):
        """ Composite image by adding watermark file over it """

        if not self.is_photo:
            logging.debug("not watermarking: not a photo")
            return img

        wmarkfile = shared.config.get('photo', 'watermark')
        if not os.path.isfile(wmarkfile):
            logging.debug("not watermarking: watermark not found")
            return img

        logging.debug("%s is a photo, applying watermarking", self.fpath)
        with wand.image.Image(filename=wmarkfile) as wmark:
            if img.width > img.height:
                w = img.width * 0.2
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

    def _copy(self):
        fname = "%s%s" % (self.fname, self.fext)
        fpath = os.path.join(
            shared.config.get('common', 'build'),
            shared.config.get('common', 'files'),
            fname
        )
        if os.path.isfile(fpath):
            mtime = os.path.getmtime(fpath)
            if self.mtime <= mtime:
                return
        logging.info("copying %s to build dir", fname)
        shutil.copy(self.fpath, fpath)

    def _intermediate_dimension(self, size, width, height, crop=False):
        """ Calculate intermediate resize dimension and return a tuple of width, height """
        size = int(size)
        if (width > height and not crop) \
        or (width < height and crop):
            w = size
            h = int(float(size / width) * height)
        else:
            h = size
            w = int(float(size / height) * width)
        return (w, h)

    def _intermediate(self, img, size, target, crop=False):
        if img.width < size and img.height < size:
            return False

        with img.clone() as thumb:
            width, height = self._intermediate_dimension(
                size,
                img.width,
                img.height,
                crop
            )
            thumb.resize(width, height)

            if crop:
                thumb.liquid_rescale(size, size, 1, 1)

            if self.meta.get('FileType', 'jpeg').lower() == 'jpeg':
                thumb.compression_quality = 94
                thumb.unsharp_mask(
                    radius=1,
                    sigma=0.5,
                    amount=0.7,
                    threshold=0.5
                )
                thumb.format = 'pjpeg'

            # this is to make sure pjpeg happens
            with open(target, 'wb') as f:
                logging.info("writing %s", target)
                thumb.save(file=f)

    @property
    def needs_downsize(self):
        needed = False
        for (size, downsized) in self.sizes:
            if downsized.get('exists', False):
                logging.debug(
                    "size %d exists: %s",
                    size,
                    downsized.get('fpath')
                )
                continue
            logging.debug(
                "size %d missing: %s",
                size,
                downsized.get('fpath')
            )
            needed = True
        return needed

    async def downsize(self):
        if not self.is_downsizeable:
            return self._copy()

        if not self.needs_downsize and not shared.config.getboolean('params', 'regenerate'):
            return

        build_files = os.path.join(
            shared.config.get('common', 'build'),
            shared.config.get('common', 'files'),
        )

        if not os.path.isdir(build_files):
            os.makedirs(build_files)

        logging.info("downsizing %s%s", self.fname, self.fext)
        with wand.image.Image(filename=self.fpath) as img:
            img.auto_orient()
            img = self._maybe_watermark(img)
            for (size, downsized) in self.sizes:
                self._intermediate(
                    img,
                    size,
                    downsized['fpath'],
                    downsized['crop']
                )

    @property
    def tmplvars(self):
        return {
            'src': self.src,
            'target': self.href,
            'css': self.cssclass,
            'title': self.title,
            'alt': self.alt,
            'exif': self.exif,
            'is_photo': self.is_photo,
            'author': self.meta.get('Artist', ''),
        }

    def __repr__(self):
        return "Image: %s, photo: %r, EXIF: %s" % (
            self.fname, self.is_photo, self.exif
        )

    def __str__(self):
        tmplfile = "%s.html" % (self.__class__.__name__)
        return shared.j2.get_template(tmplfile).render({
            'photo': self.tmplvars
        })


class Comment(object):
    def __init__(self, fpath):
        logging.debug("initiating comment object from %s", fpath)
        self.fpath = fpath
        self.mtime = os.path.getmtime(self.fpath)
        with open(self.fpath, mode='rt') as f:
            self.fm = frontmatter.parse(f.read())
            self.meta, self.content = self.fm

    @property
    def dt(self):
        return arrow.get(self.meta.get('date'))

    @property
    def html(self):
        html = "%s" % (self.content)
        return shared.Pandoc().convert(html)

    @property
    def target(self):
        t = urlparse(self.meta.get('target'))
        return t.path.rstrip('/').strip('/').split('/')[-1]

    @property
    def source(self):
        return self.meta.get('source')

    @property
    def author(self):
        url = self.meta.get('author').get('url', self.source)
        name = self.meta.get('author').get('name', urlparse(url).hostname)

        return {
            'name': name,
            'url': url
        }

    @property
    def type(self):
        # caching, because calling Pandoc is expensive
        if not hasattr(self, '_type'):
            self._type = 'webmention'
            t = self.meta.get('type', 'webmention')
            if t != 'webmention':
                self._type = '★'

            if len(self.content):
                maybe = shared.Pandoc('plain').convert(self.content)
                if maybe in UNICODE_EMOJI:
                    self._type = maybe
        return self._type

    @property
    def tmplvars(self):
        if not hasattr(self, '_tmplvars'):
            self._tmplvars = {
                'author': self.author,
                'source': self.source,
                'pubtime': self.dt.format(shared.ARROWFORMAT['iso']),
                'pubdate': self.dt.format(shared.ARROWFORMAT['display']),
                'html': self.html,
                'type': self.type
            }
        return self._tmplvars

    def __repr__(self):
        return "Comment from %s for %s" % (
            self.source, self.target
        )

    def __str__(self):
        tmplfile = "%s.html" % (__class__.__name__)
        return shared.j2.get_template(tmplfile).render({
            'comment': self.tmplvars
        })


class Webmention(object):
    def __init__(self, source, target, dt=arrow.utcnow().timestamp):
        self.source = source
        self.target = target
        self.dt = arrow.get(dt).to('utc')
        logging.info(
            "processing webmention %s => %s",
            self.source,
            self.target
        )

    def _fetch(self):
        self._source = shared.XRay(self.source).parse()

    def _save(self):
        fm = frontmatter.loads('')
        fm.content = self.content
        fm.metadata = self.meta
        with open(self.fpath, 'wt') as f:
            f.write(frontmatter.dumps(fm))
        return

    def send(self):
        rels = shared.XRay(self.source).set_discover().parse()
        endpoint = False
        if 'rels' not in rels:
            return
        for k in rels.get('rels').keys():
            if 'webmention' in k:
                endpoint = rels.get('rels').get(k)
                break
        if not endpoint:
            return
        requests.post(
            self.target,
            data={
                'source': self.source,
                'target': self.target
            }
        )

    def receive(self):
        self._fetch()
        if 'data' not in self._source:
            return
        self._save()

    @property
    def relation(self):
        r = 'webmention'
        k = self._source.get('data').keys()
        for maybe in ['in-reply-to', 'repost-of', 'bookmark-of', 'like-of']:
            if maybe in k:
                r = maybe
                break
        return r

    @property
    def meta(self):
        if not hasattr(self, '_meta'):
            self._meta = {
                'author': self._source.get('data').get('author'),
                'type': self.relation,
                'target': self.target,
                'source': self.source,
                'date': self._source.get('data').get('published'),
            }
        return self._meta

    @property
    def content(self):
        if 'content' not in self._source.get('data'):
            return ''
        elif 'html' in self._source.get('data').get('content'):
            what = self._source.get('data').get('content').get('html')
        elif 'text' in self._source.get('data').get('content'):
            what = self._source.get('data').get('content').get('text')
        else:
            return ''
        return shared.Pandoc('html').convert(what)

    @property
    def fname(self):
        return "%d-%s.md" % (
            self.dt.timestamp,
            shared.slugfname(self.source)
        )

    @property
    def fpath(self):
        tdir = os.path.join(
            shared.config.get('dirs', 'comment'),
            self.target.rstrip('/').strip('/').split('/')[-1]
        )
        if not os.path.isdir(tdir):
            os.makedirs(tdir)
        return os.path.join(
            tdir,
            self.fname
        )


class Worker(object):
    def __init__(self):
        self._tasks = []
        self._loop = asyncio.get_event_loop()

    def append(self, job):
        task = self._loop.create_task(job)
        self._tasks.append(task)

    def run(self):
        w = asyncio.wait(self._tasks)
        self._loop.run_until_complete(w)
        self._loop.close()


def setup():
    """ parse input parameters and add them as params section to config """
    parser = argparse.ArgumentParser(description='Parameters for NASG')

    booleanparams = {
        'regenerate': 'force downsizing images',
        'force': 'force rendering HTML',
    }

    for k, v in booleanparams.items():
        parser.add_argument(
            '--%s' % (k),
            action='store_true',
            default=False,
            help=v
        )

    parser.add_argument(
        '--loglevel',
        default='warning',
        help='change loglevel'
    )

    if not shared.config.has_section('params'):
        shared.config.add_section('params')

    params = vars(parser.parse_args())
    for k, v in params.items():
        shared.config.set('params', k, str(v))

    # remove the rest of the potential loggers
    while len(logging.root.handlers) > 0:
        logging.root.removeHandler(logging.root.handlers[-1])

    logging.basicConfig(
        level=shared.LLEVEL[shared.config.get('params', 'loglevel')],
        format='%(asctime)s - %(levelname)s - %(message)s'
    )


def youngest_mtime(root):
    youngest = 0
    files = glob.glob(os.path.join(root, '**'), recursive=True)
    for f in files:
        mtime = os.path.getmtime(f)
        if mtime > youngest:
            youngest = mtime
    return youngest


def build():
    setup()

    worker = Worker()
    content = Content()
    sdb = shared.SearchDB()
    magic = MagicPHP()

    collector_front = Category()
    collector_categories = NoDupeContainer()

    for f, post in content:
        logging.info("PARSING %s", f)
        post.init_extras()

        # extend redirects
        for r in post.redirects:
            magic.redirects.append((r, post.fname))

        # add post to search, if needed
        if not sdb.is_uptodate(post.fname, post.mtime):
            sdb.append(
                post.fname,
                post.corpus,
                post.mtime,
                post.url,
                post.category,
                post.title
            )

        # add render task, if needed
        if not post.is_uptodate or shared.config.getboolean('params', 'force'):
            worker.append(post.render())

        # collect images to downsize
        for fname, im in post.images:
            worker.append(im.downsize())

        # skip adding future posts to any category
        if post.is_future:
            continue

        # skip categories starting with _
        if post.category.startswith('_'):
            continue

        # get the category otherwise
        if post.category not in collector_categories:
            c = Category(post.category)
            collector_categories.append(post.category, c)
        else:
            c = collector_categories[post.category]

        # add post to category
        c.append(post)

        # add post to front
        collector_front.append(post)

    # write search db
    sdb.finish()

    # render front
    if not collector_front.is_uptodate or \
    shared.config.getboolean('params', 'force'):
        worker.append(collector_front.render())

    # render categories
    for name, c in collector_categories:
        if not c.is_uptodate or shared.config.getboolean('params', 'force'):
            worker.append(c.render())

    # add magic.php rendering
    worker.append(magic.render())

    # TODO: send webmentions

    # do all the things!
    worker.run()

    # copy static
    logging.info('copying static files')
    src = shared.config.get('dirs', 'static')
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(shared.config.get('common', 'build'), item)
        if not os.path.exists(d):
            logging.debug("copying static file %s to %s", s, d)
            shutil.copy2(s, d)

if __name__ == '__main__':
    build()
