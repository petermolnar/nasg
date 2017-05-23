import os
import re
import sys
import collections
import logging
import glob
import img
import pypandoc
import langdetect
from cache import Cached
from slugify import slugify
from ruamel import yaml
from bs4 import BeautifulSoup
import frontmatter
from webmentiondb import WebmentionDB
import arrow
import json
import socket
import requests
import hashlib
import shutil


class SingularHandler(object):

    def __init__(self, fpath, pingdb=WebmentionDB(), category='note'):
        self.fpath = os.path.abspath(fpath)
        path, fname = os.path.split(self.fpath)
        fname, ext = os.path.splitext(fname)
        self.fname = fname
        self.fext = ext
        self.ftime = os.stat(self.fpath)
        self.target = os.path.join(glob.TARGET, "%s.html" % (self.fname))

        basedir = os.path.join(glob.TARGET, "%s" % (self.fname))
        if not os.path.isdir(basedir):
            os.mkdir(basedir)

        self.saved = os.path.join(glob.TARGET, "%s" % (self.fname), "saved.html")

        self.pingdb = pingdb
        self.title = ''
        self.content = ''
        self._content = ''
        self.summary = ''
        self.html = ''
        self.sumhtml = ''
        self.category = category
        self.tags = []
        self.reactions = {}
        #self.date = datetime.datetime(1970, 1, 1).replace(tzinfo=pytz.utc)
        self.date = arrow.get(0)
        self.updated = None
        self.dtime = 0
        self.utime = 0
        self.redirect = {}

        self.exifmin = {}
        self.lang = glob.conf['site']['lang']
        self.syndicate = {}
        self.syndications = []
        self.template = 'singular.html'

        self.slug = slugify(self.fname, only_ascii=True, lower=True)
        self.shortslug = slugify(self.fname, only_ascii=True, lower=True)
        self.img = None
        self.srcset = ''

    def __repr__(self):
        return "Post '%s' (%s), category: %s" % (self.title,self.fname,self.category)


    def _postsetup(self):
        """ Shared post-setup - the initial thing, such at title, should be
        set by the classes inheriting this one; these are only the common,
        shared variables """

        # set published epoch
        #self.dtime = calendar.timegm(self.date.timetuple())
        self.dtime = self.date.timestamp

        # set updated epoch, if any and set the original file date according
        # to either the updated or the published time
        if self.updated:
            #self.utime = calendar.timegm(self.updated.timetuple())
            self.utime = self.updated.timestamp
            if self.utime > 0 and self.utime != self.ftime.st_mtime:
                os.utime(self.fpath, (self.utime, self.utime))
        elif self.dtime > 0 and self.dtime != self.ftime.st_mtime:
            os.utime(self.fpath, (self.dtime, self.dtime))

        # generate shortslug from dtime if possible
        if self.dtime > 0:
            self.shortslug = SingularHandler.baseN(self.dtime)
            self.redirect[self.shortslug] = 1

        # detect post content language if possible
        try:
            self.lang = langdetect.detect("%s\n\n%s" % (self.title, self.content))
        except:
            pass

        # make HTML from markdown via pandoc for the content and the summary
        self.html = SingularHandler.pandoc_md2html(
            self.content,
            time=self.ftime
        )
        self.sumhtml = SingularHandler.pandoc_md2html(
            self.summary,
            time=self.ftime
        )

        self.url = "%s/%s" % (glob.conf['site']['url'], self.slug)
        self.syndications = self.pingdb.posses(self.url)

    #def urlsvg(self):
        # import pyqrcode
        # import tempfile
        ## generate qr code to the url
        #qrname = tempfile.NamedTemporaryFile(prefix='pyqr_')
        #qr = pyqrcode.create(self.url, error='L')
        #qr.svg(
            #qrname.name,
            #xmldecl=False,
            #omithw=True,
            #scale=1,
            #quiet_zone=0,
            #svgclass='qr',
            #lineclass='qrline'
        #)
        #with open(qrname.name) as f:
            #qrsvg = f.read()
            #f.close()
        #return qrsvg

    @staticmethod
    def pandoc_md2html(t, time=None):
        if len(t) == 0:
            return t

        cached = Cached(text="%s" % t, stime=time)
        c = cached.get()

        if c:
            return c
        else:
            extras = [
                'backtick_code_blocks',
                'auto_identifiers',
                'fenced_code_attributes',
                'definition_lists',
                'grid_tables',
                'pipe_tables',
                'strikeout',
                'superscript',
                'subscript',
                'markdown_in_html_blocks',
                'shortcut_reference_links',
                'autolink_bare_uris',
                'raw_html',
                'link_attributes',
                'header_attributes',
                'footnotes',
            ]
            md = "markdown+" + "+".join(extras)

            t = pypandoc.convert_text(t, to='html5', format=md)
            cached.set(t)
            return t

    @staticmethod
    def pandoc_html2md(t, time=None):
        if len(t) == 0:
            return t

        cached = Cached(text="%s" % t, stime=time)
        c = cached.get()

        if c:
            return c
        else:
            t = pypandoc.convert_text(
                    t,
                    to="markdown-" + "-".join([
                        'raw_html',
                        'native_divs',
                        'native_spans',
                    ]),
                    format='html'
                )

            cached.set(t)
            return t


    def tmpl(self):
        return {
            'title': self.title,
            'published': self.date,
            'tags': self.tags,
            'author': glob.conf['author'],
            'content': self.content,
            'html': self.html,
            'category': self.category,
            'reactions': self.reactions,
            'updated': self.updated,
            'summary': self.sumhtml,
            'exif': self.exifmin,
            'lang': self.lang,
            'syndicate': self.syndicate,
            'slug': self.slug,
            'shortslug': self.shortslug,
            'srcset': self.srcset,
        }

    @staticmethod
    def write_redirect(sslug, target, tstamp=arrow.utcnow().timestamp):

        tmpl = glob.jinja2env.get_template('redirect.html')
        jvars = {
            'url': target
        }
        r = tmpl.render(jvars)
        # this is to support / ending urls even for the redirects
        dirs = [
            os.path.join(glob.TARGET, sslug)
        ]

        for d in dirs:
            if not os.path.exists(d):
                os.mkdir(d)

        files = [
            os.path.join(glob.TARGET, "%s.html" % (sslug)),
            os.path.join(glob.TARGET, sslug, "index.html")
        ]
        for f in files:
            if os.path.isfile(f):
                rtime = os.stat(f)
                if tstamp == rtime.st_mtime:
                    logging.debug(
                        "Unchanged dates on redirect file %s", f
                    )
                continue

            with open(f, "w") as html:
                logging.info("writing redirect file %s", f)
                html.write(r)
                html.close()
            os.utime(f, (tstamp,tstamp))


    def redirects(self):
        """ Write redirect HTMLs """

        if self.category == 'page':
            return

        for sslug in self.redirect.keys():
            SingularHandler.write_redirect(sslug, self.url, self.ftime.st_mtime)

    def write(self):
        """ Write HTML file """

        if os.path.isfile(self.target):
            ttime = os.stat(self.target)
            if self.ftime.st_mtime == ttime.st_mtime and not glob.FORCEWRITE:
                logging.debug(
                    "Unchanged dates on %s; skipping rendering and writing",
                    self.fname
                )
                return

        tmpl = glob.jinja2env.get_template(self.template)
        logging.info("rendering %s", self.fname)
        tmplvars = {
            'post': self.tmpl(),
            'site': glob.conf['site'],
            'taxonomy': {},
        }
        r = tmpl.render(tmplvars)
        soup = BeautifulSoup(r,"html5lib")
        r = soup.prettify()

        targets = [self.target]
        for target in targets:
            with open(target, "w") as html:
                logging.info("writing %s", target)
                html.write(r)
                html.close()
            os.utime(target, (self.ftime.st_mtime, self.ftime.st_mtime))

        rdir = os.path.join(glob.TARGET, self.slug)
        if not os.path.isdir(rdir):
            os.mkdir(rdir)

        altdst = os.path.join(glob.TARGET, self.slug, 'index.html')
        altsrc = os.path.join('..', self.target)

        if not os.path.islink(altdst):
            if os.path.isfile(altdst):
                os.unlink(altdst)
            os.symlink(altsrc, altdst)

        #links = []
        #for r in self.reactions.items():
            #reactiontype, urls = r
            #if isinstance(urls, str):
                #links.append(urls)
            #elif isinstance(urls, list):
                #links = [*links, *urls]

        #if 1 == len(links):
            #saved = os.path.join(glob.TARGET, self.slug, 'saved.html')
            #if not os.path.isfile(saved):
                #h, p = _localcopy_hashpath(links[0])
                #c = self._get_localcopy(links[0], h, p)
                #with open(saved, 'w') as f:
                    #f.write(c)
                    #f.close()

    def index(self, ix):
        """ Write search index """

        writer = ix.writer()

        c = "%s %s %s %s %s" % (
            self.slug,
            self.summary,
            self._content,
            yaml.dump(self.reactions, Dumper=yaml.RoundTripDumper),
            yaml.dump(self.exifmin, Dumper=yaml.RoundTripDumper)
        )

        c = "%s %s" % (c, self._localcopy_include())

        if self.img:
            imgstr = self.img.mksrcset(generate_caption=False)
        else:
            imgstr = ''

        writer.add_document(
            title=self.title,
            url=self.url,
            content=c,
            date=self.date.datetime,
            tags=",".join(self.tags),
            weight=1,
            img=imgstr
        )
        writer.commit()


    def pings(self):
        """ Ping (webmention) all URLs found in the post """

        links = []
        urlregex = re.compile(
            r'\s+https?\:\/\/?[a-zA-Z0-9\.\/\?\:@\-_=#]+'
            r'\.[a-zA-Z0-9\.\/\?\:@\-_=#]*'
        )
        matches = re.findall(urlregex, self.content)

        for r in self.reactions.items():
            reactiontype, urls = r
            if isinstance(urls, str):
                matches.append(urls)
            elif isinstance(urls, list):
                matches = [*matches, *urls]

        #for s in self.syndicate.keys():
            #matches.append('https://brid.gy/publish/%s' % (s))

        if self.utime and self.utime > 0:
            time = self.utime
        else:
            time = self.dtime

        if len(matches) > 0:
            for link in matches:
                if glob.conf['site']['domain'] in link:
                    continue

                if link in links:
                    continue

                #self._localcopy(link)
                self.pingdb.ping(self.url, link, time)
                links.append(link)


    def _localcopy_hashpath(self,url):
        h = hashlib.md5(url.encode('utf-8')).hexdigest()
        p = os.path.join(glob.LOCALCOPIES, "%s.html" % (h))
        return (h, p)


    def _localcopy_include(self):
        links = []
        md = ''
        for r in self.reactions.items():
            reactiontype, urls = r
            if isinstance(urls, str):
                links.append(urls)
            elif isinstance(urls, list):
                links = [*links, *urls]

        for url in links:
            h, p = self._localcopy_hashpath(url)
            html = self._get_localcopy(url, h, p)
            md = "%s %s" % (
                md,
                SingularHandler.pandoc_html2md(html, os.stat(p))
            )

        return md


    def _get_localcopy(self, url, h, p):
        html = ''

        if os.path.isfile(p):
            with open(p, 'r') as f:
                html = f.read()
                f.close()
        else:
            html = self._make_localcopy(url, h, p)

        return html


    def _make_localcopy(self, url, h, p):
        post = self._pull_localcopy(url)
        tmpl = glob.jinja2env.get_template('localcopy.html')
        html = tmpl.render({'post': post})
        soup = BeautifulSoup(html,"html5lib")
        html = soup.prettify()

        with open(p, "w") as f:
            logging.info("saving readable copy of %s to %s", url, p)
            f.write(html)
            f.close()

        return html


    def _pull_localcopy(self, url):

        # find the true URL
        # MAYBE: add fallback to archive.org?
        realurl = url
        try:
            pretest = requests.head(url, allow_redirects=True, timeout=30)
            realurl = pretest.url
        except:
            pass

        parsed = {
            'lang': 'en',
            'url': url,
            'realurl': realurl,
            'html': '',
            'title': '',
            'excerpt': '',
            'byline': '',
        }

        if 'readable' in glob.conf and \
        'port' not in glob.conf['readable'] and \
        'host' not in glob.conf['readable']:

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            socktest = sock.connect_ex((
                glob.conf['readable']['host'], int(glob.conf['readable']['port'])
            ))
            if 0 == socktest:
                text = self._localcopy_via_proxy(realurl)
                parsed['html'] = text.get('content','')
                parsed['title'] = text.get('title',url)
                parsed['excerpt'] = text.get('excerpt', '')
                parsed['byline'] = text.get('byline', '')

                try:
                    parsed['lang'] = langdetect.detect(parsed['html'])
                except:
                    pass

                return parsed

        # TODO: fallback to full-python solution if the previous failed
        return parsed


    def _localcopy_via_proxy(self, url):
        r = "http://%s:%s/api/get?url=%s&sanitize=y" % (
            glob.conf['readable']['host'],
            glob.conf['readable']['port'],
            url
        )

        try:
            req = requests.get(r,allow_redirects=False,timeout=60);
        except:
            return None

        text = {}
        try:
            text = json.loads(req.text)
        except:
            pass

        return text


    def _adaptify(self):
        """ Generate srcset for all images possible """

        linkto = False
        isrepost = None

        if len(self.reactions.keys()):
            isrepost = list(self.reactions.keys())[0]

        if isrepost:
            if len(self.reactions[isrepost]) == 1:
                linkto = self.reactions[isrepost][0]

        mdmatch = re.compile(
            r'!\[.*\]\(.*?\.(?:jpe?g|png|gif)'
            r'(?:\s+[\'\"]?.*?[\'\"]?)?\)(?:\{.*?\})?'
        )
        mdsplit = re.compile(
            r'!\[(.*)\]\((?:\/(?:files|cache)'
            r'(?:\/[0-9]{4}\/[0-9]{2})?\/(.*\.(?:jpe?g|png|gif)))'
            r'(?:\s+[\'\"]?(.*?)[\'\"]?)?\)(?:\{(.*?)\})?'
        )
        mdimg = re.findall(mdmatch, self.content)
        for i in mdimg:
            m = re.match(mdsplit, i)
            if m:
                #logging.info(m.groups())
                imgpath = os.path.join(glob.SFILES, m.group(2))

                if not os.path.isfile(imgpath):
                    for c in glob.conf['category'].items():
                        catn, catd = c
                        catp = os.path.abspath(os.path.join(glob.CONTENT, catn))

                        if not os.path.exists(catp) \
                        or not 'type' in catd \
                        or catd['type'] != 'photo':
                            continue

                        imgpath = os.path.join(catp, m.group(2))
                        break

                if os.path.isfile(imgpath):

                    t = ''
                    if m.group(3):
                        t = m.group(3)

                    cl = ''
                    if m.group(4):
                        cl = m.group(4)

                    a = ''
                    if m.group(1):
                        a = m.group(1)

                    im = img.ImageHandler(
                        imgpath,
                        alttext=a,
                        title=t,
                        imgcl=cl,
                        linkto=linkto
                    )

                    im.downsize()
                    logging.debug("replacing image %s with srcset", imgpath)
                    srcset = im.mksrcset()
                    if srcset:
                        self.content = self.content.replace(i, srcset)
                    del(im)
                else:
                    logging.error("%s missing %s", m.group(2), self.fpath)

    def _video(self):
        """ [video] shortcode extractor """

        match = re.compile(r'\[video mp4=\"/(?:files|cache).*?\"\]\[/video\]')
        split = re.compile(r'\[video mp4=\"(/(?:files|cache)\/(.*?))\"\]\[/video\]')
        videos = re.findall(match, self.content)
        for vid in videos:
            v = re.match(split, vid)
            video = """
            <video controls>
                <source src="%s" type="video/mp4">
                Your browser does not support the video tag.
            </video>""" % (v.group(1))
            self.content = self.content.replace(vid, video)

    #def _files(self):
        #""" Copy misc files referenced """

        #match = re.compile(
            #r'\s(?:%s)?/(?:files|cache)'
            #r'/.*\.(?:(?!jpe?g|png|gif).*)\s' % (glob.conf['site']['domain'])
        #)
        #split = re.compile(
            #r'\s(?:%s)?/((?:files|cache)'
            #r'/(.*\.(?:(?!jpe?g|png|gif).*)))\s' % (glob.conf['site']['domain'])
        #)
        ##files = re.findall(match, self.content)
        ##print(files)

    def _snippets(self):
        """ Replaces [git:(repo)/(file.ext)] with corresponding code snippet """

        snmatch = re.compile(r'\[git:[^\/]+\/(?:.*\..*)\]')
        snsplit = re.compile(r'\[git:([^\/]+)\/((?:.*)\.(.*))\]')
        snippets = re.findall(snmatch, self.content)
        isconf = re.compile(r'conf', re.IGNORECASE)
        for snippet in snippets:
            sn = re.match(snsplit, snippet)
            if sn:
                fpath = os.path.join(glob.SOURCE, sn.group(1), sn.group(2))
                if not os.path.isfile(fpath):
                    logging.error(
                        "missing blogsnippet in %s: %s",
                        self.fpath,
                        fpath
                    )
                    continue

                if re.match(isconf, sn.group(3)):
                    lang = 'apache'
                else:
                    lang = sn.group(3)

                with open(fpath, "r") as snip:
                    c = snip.read()
                    snip.close

                c = "\n\n```%s\n%s\n```\n" % (lang, c)
                logging.debug("replacing blogsnippet %s", fpath)
                self.content = self.content.replace(snippet, c)

    @staticmethod
    def baseN(num, b=36, numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
        """ Used to create short, lowecase slug for a number (an epoch) passed """
        num = int(num)
        return ((num == 0) and numerals[0]) or (
            SingularHandler.baseN(
                num // b,
                b,
                numerals
            ).lstrip(numerals[0]) + numerals[num % b]
        )



class ArticleHandler(SingularHandler):

    def __init__(self, *args, **kwargs):
        super(ArticleHandler, self).__init__(*args, **kwargs)
        self.dctype = 'Text'
        self._setup()

    def _setup(self):
        post = frontmatter.load(self.fpath)
        self.meta = post.metadata
        self.content = post.content
        self._content = '%s' % (self.content)

        if 'tags' in post.metadata:
            self.tags = post.metadata['tags']

        if 'title' in post.metadata:
            self.title = post.metadata['title']

        if 'published' in post.metadata:
            self.date = arrow.get(post.metadata['published'])

        if 'updated' in post.metadata:
            self.updated = arrow.get(post.metadata['updated'])

        if 'summary' in post.metadata:
            self.summary = post.metadata['summary']

        if 'redirect' in post.metadata and \
        isinstance(post.metadata['redirect'], list):
            for r in post.metadata['redirect']:
                self.redirect[r] = 1

        if 'syndicate' in post.metadata:
            z = post.metadata['syndicate']
            if isinstance(z, str):
                self.syndicate[z] = ''
            elif isinstance(z, dict):
                for s, c in z.items():
                    self.syndicate[s] = c
            elif isinstance(z, list):
                for s in z:
                    self.syndicate[s] = ''

        self.reactions = {}

        # getting rid of '-' to avoid css trouble and similar
        rmap = {
            'bookmark-of': 'bookmark',
            'repost-of': 'repost',
            'in-reply-to': 'reply',
        }

        for x in rmap.items():
            key, replace = x
            if key in self.meta:
                if isinstance(self.meta[key], str):
                    self.reactions[replace] = [self.meta[key]]
                elif isinstance(self.meta[key], list):
                    self.reactions[replace] = self.meta[key]

        self._adaptify()
        self._snippets()
        self._video()
        #self._files()
        super(ArticleHandler, self)._postsetup()


class PhotoHandler(SingularHandler):

    def __init__(self, *args, **kwargs):
        super(PhotoHandler, self).__init__(*args, **kwargs)
        self.dctype = 'Image'
        self.img = img.ImageHandler(self.fpath)
        self.exif = self.img.exif
        self._setup()

    def _setup(self):
        self.syndicate = {
            'flickr': '',
        }

        keywords = [
            'XMP:Keywords',
            'IPTC:Keywords'
        ]
        tags = {}
        for key in keywords:
            if key in self.exif and self.exif[key]:

                if isinstance(self.exif[key], str):
                    self.exif[key] = self.exif[key].split(",")

                if isinstance(self.exif[key], list):
                    for tag in self.exif[key]:
                        tags[str(tag).strip()] = 1

        self.tags = list(tags.keys())

        # content
        keywords = [
            'XMP:Description',
            'IPTC:Caption-Abstract'
        ]
        for key in keywords:
            if key in self.exif and self.exif[key]:
                self.content = self.exif[key]
                break
        self._content = '%s' % (self.content)

        # title
        keywords = [
            'XMP:Title',
            'XMP:Headline',
            'IPTC:Headline'
        ]
        for key in keywords:
            if key in self.exif and self.exif[key]:
                self.title = self.exif[key]
                break

        # datetime
        keywords = [
            'XMP:DateTimeDigitized',
            'XMP:CreateDate',
            'EXIF:CreateDate',
            'EXIF:ModifyDate'
        ]

        pattern = re.compile(
            "(?P<Y>[0-9]{4}):(?P<M>[0-9]{2}):(?P<D>[0-9]{2})\s+"
            "(?P<T>[0-9]{2}:[0-9]{2}:[0-9]{2})Z?"
        )

        for key in keywords:
            if key not in self.exif or not self.exif[key]:
                continue

            date = None
            v = pattern.match(self.exif[key]).groupdict()
            if not v:
                continue

            try:
                date = arrow.get('%s-%s-%s %s' % (v['Y'], v['M'], v['D'], v['T']))
            except:
                continue

            if date:
                self.date = date
                logging.debug("date for %s is set to %s from key %s", self.fname, self.date, key)
                break

        self.img.title = self.title
        self.img.alttext = self.content
        self.content = self.content + "\n\n" + self.img.mksrcset(generate_caption=False, uphoto=True)

        self.img.downsize()
        self.srcset = self.img.mksrcset(generate_caption=False, uphoto=False)
        super(PhotoHandler, self)._postsetup()


    def tmpl(self):
        tmpl = super(PhotoHandler, self).tmpl()
        tmpl['exif'] = {}

        mapping = {
            'camera': [
                'EXIF:Model'
            ],
            'aperture': [
                'EXIF:FNumber',
                'Composite:Aperture'
            ],
            'shutter_speed': [
                'EXIF:ExposureTime'
            ],
            'focallength': [
                'EXIF:FocalLength',
                'Composite:FocalLength35efl',
            ],
            'iso': [
                'EXIF:ISO'
            ],
            'lens': [
                'Composite:LensID',
                'MakerNotes:Lens',
                'Composite:LensSpec'
            ]
        }

        for ekey, candidates in mapping.items():
            for candidate in candidates:
                if candidate in self.exif:
                    tmpl['exif'][ekey] = self.exif[candidate]
                    break

        gps = ['Latitude', 'Longitude']
        for g in gps:
            gk = 'EXIF:GPS%s' % (g)
            if gk not in self.exif:
                continue

            r = 'EXIF:GPS%sRef' % (g)
            ref = None
            if r in self.exif:
                ref = self.exif[r]

            tmpl['exif']['geo_%s' % (g.lower())] = self.gps2dec(
                self.exif[gk],
                ref
            )

        ##tmpl['imgurl'] = ''
        #sizes = collections.OrderedDict(reversed(list(self.img.sizes.items())))
        #for size, meta in sizes.items():
            #if os.path.isfile(meta['path']):
                #with Image.open(meta['path']) as im:
                    #meta['width'], meta['height'] = im.size
                #meta['size'] = os.path.getsize(meta['path'])
                #tmpl['img'] = meta
                #break

        tmpl['img'] = self.img.meta
        return tmpl


    @staticmethod
    def gps2dec(exifgps, ref=None):
        pattern = re.compile(r"(?P<deg>[0-9.]+)\s+deg\s+(?P<min>[0-9.]+)'\s+(?P<sec>[0-9.]+)\"(?:\s+(?P<dir>[NEWS]))?")
        v = pattern.match(exifgps).groupdict()

        dd = float(v['deg']) + (((float(v['min']) * 60) + (float(v['sec']))) / 3600)
        if ref == 'West' or ref == 'South' or v['dir'] == "S" or v['dir'] == "W":
            dd = dd * -1
        return round(dd, 6)



class PageHandler(SingularHandler):

    def __init__(self, *args, **kwargs):
        super(PageHandler, self).__init__(*args, **kwargs)
        self._setup()

    def _setup(self):
        with open(self.fpath) as c:
            self.content = c.read()
            c.close()

        self._content = '%s' % (self.content)
        self._adaptify()
        super(PageHandler, self)._postsetup()
        self.template = 'page.html'