import os
import re
import logging
import arrow
import frontmatter
import langdetect
from slugify import slugify

import nasg.config as config
import nasg.func as func
import nasg.cmdline as cmdline
from nasg.img import ImageHandler
import nasg.jinjaenv as jinjaenv

class SingularHandler(object):
    def __init__(self, fpath):
        logging.info("setting up singular from %s", fpath)
        self.fpath= os.path.abspath(fpath)
        self.fname, self.ext = os.path.splitext(os.path.basename(self.fpath))
        self.target = os.path.join(
            config.TARGET, "%s" % (self.fname), "index.html"
        )

        slug = slugify(self.fname, only_ascii=True, lower=True)
        self.modtime = int(os.path.getmtime(self.fpath))
        self.category = os.path.dirname(self.fpath).replace(config.CONTENT, '').strip('/')

        self.vars =  {
            'category': self.category,
            'tags': [],
            'published': arrow.get(self.modtime),
            'updated': arrow.get(0),
            'author': config.author,
            'title': '',
            'raw_summary': '',
            'raw_content': '',
            'content': '',
            'summary': '',
            'reactions': {},
            'exif': {},
            'lang': config.site['lang'],
            #'syndicate': [],
            'slug': slug,
            'shortslug': slug,
            'srcset': '',
            'url': "%s/%s/" % (config.site['url'], slug),
        }

        self.redirects = {}
        self.pings = {}
        self.template = 'singular.html'
        self.img = None
        self.rendered = ''


    def __repr__(self):
        return "Post '%s' (%s @ %s)" % (
            self.vars['title'],
            self.fname,
            self.fpath
        )


    def _modtime(self):
        """ Set file mtime in case it doesn't match the in-file publish or updated time """

        use = 'published'
        if self.vars['updated'].timestamp > self.vars['published'].timestamp:
            use = 'updated'

        self.modtime = int(self.vars[use].timestamp)
        stattime = int(os.path.getmtime(self.fpath))
        if stattime != self.modtime:
            os.utime(self.fpath, (self.modtime, self.modtime))


    def _detect_lang(self):
        # try to detect language, ignore failures
        try:
            self.vars['lang'] = langdetect.detect(
                "%s %s" % (
                    self.vars['title'],
                    self.vars['raw_content']
                )
            )
        except:
            pass


    def _redirects(self):
        if self.category in config.categories and \
        'nocollection' in config.categories[self.category] and \
        config.categories[self.category]['nocollection']:
            return

        self.redirects[self.vars['shortslug']] = 1


    def _shortslug(self):
        shortslug = func.baseN(self.vars['published'].timestamp)
        self.vars['shortslug'] = shortslug


    def _prerender(self):
        for s in ['content', 'summary']:
            self.vars[s] = cmdline.Pandoc(self.vars[s]).md2html().get()


    def _postsetup(self):
        for s in ['content', 'summary']:
            if not self.vars[s]:
                self.vars[s] = self.vars['raw_%s' % s]

        self._modtime()
        self._shortslug()
        self._detect_lang()
        self._redirects()
        self._pings()


    def _render(self):
        self._prerender()
        tmpl = jinjaenv.JINJA2ENV.get_template(self.template)
        logging.info("rendering %s", self.fname)
        tmplvars = {
            'post': self.vars,
            'site': config.site,
            'taxonomy': {},
        }
        self.rendered = tmpl.render(tmplvars)


    def _exists(self):
        """ check if target exists and up to date """

        if config.options['regenerate']:
            logging.debug('REGENERATE active')
            return False

        if not os.path.isfile(self.target):
            logging.debug('%s missing', self.target)
            return False

        ttime = os.stat(self.target)
        if self.modtime == ttime.st_mtime:
            logging.debug('%s exist and up to date', self.target)
            return True

        return False


    def write(self):
        """ Write HTML file """

        if self._exists():
            logging.info("skipping existing %s", self.target)
            return

        self._render()
        d = os.path.dirname(self.target)
        if not os.path.isdir(d):
            os.mkdir(d)

        with open(self.target, "wt") as html:
            logging.info("writing %s", self.target)
            html.write(self.rendered)
            html.close()
        os.utime(self.target, (self.modtime, self.modtime))


    def indexvars(self):
        """ Return values formatter for search index """

        c = "%s %s %s %s %s" % (
            self.vars['slug'],
            self.vars['raw_summary'],
            self.vars['raw_content'],
            self.vars['reactions'],
            self.vars['exif']
        )

        #c = "%s %s" % (c, self._localcopy_include())

        imgstr = ''
        if self.img:
            imgstr = self.img.mksrcset(generate_caption=False)

        ivars = {
            'title': self.vars['title'],
            'url': self.vars['url'],
            'content': c,
            'date': self.vars['published'].datetime,
            'tags': ",".join(self.vars['tags']),
            'img': imgstr
        }

        return ivars

    def _pings(self):
        """ Extract all URLs that needs pinging """

        urlregex = re.compile(
            r'\s+https?\:\/\/?[a-zA-Z0-9\.\/\?\:@\-_=#]+'
            r'\.[a-zA-Z0-9\.\/\?\:@\-_=#]*'
        )
        urls = re.findall(urlregex, self.vars['raw_content'])

        for r in self.vars['reactions'].items():
            reactiontype, reactions = r
            if isinstance(reactions, str):
                urls.append(reactions)
            elif isinstance(reactions, list):
                urls = [*reactions, *urls]

        #for s in self.syndicate.keys():
            #matches.append('https://brid.gy/publish/%s' % (s))

        urlredux = {}
        for url in urls:
            # exclude local matches
            if config.site['domain'] in url:
                continue
            urlredux[url] = 1

        self.pings = urlredux


    def _c_adaptify_altfpath(self, fname):
        for c, cmeta in config.categories.items():
            tpath = os.path.join(config.CONTENT, c, fname)
            if os.path.isfile(tpath):
                return tpath
        return None


    def _c_adaptify(self):
        """ Generate srcset for all suitable images """

        linkto = False
        isrepost = None

        if len(self.vars['reactions'].keys()):
            isrepost = list(self.vars['reactions'].keys())[0]
            if isrepost and \
            len(self.vars['reactions'][isrepost]) == 1:
                linkto = self.vars['reactions'][isrepost][0]

        p = re.compile(
            r'(!\[(.*)\]\((?:\/(?:files|cache)'
            r'(?:\/[0-9]{4}\/[0-9]{2})?\/(.*\.(?:jpe?g|png|gif)))'
            r'(?:\s+[\'\"]?(.*?)[\'\"]?)?\)(?:\{(.*?)\})?)'
        , re.IGNORECASE)

        m = p.findall(self.vars['content'])
        if not m:
            return

        for shortcode, alt, fname, title, cl in m:
            fpath = os.path.join(config.SFILES, fname)
            if not os.path.isfile(fpath):
                fpath = self._c_adaptify_altfpath(fname)
            if not fpath:
                logging.error("missing image in %s: %s", self.fpath, fname)
                continue

            im = ImageHandler(
                fpath,
                alttext=alt,
                title=title,
                imgcl=cl,
                linkto=linkto
            )

            im.downsize()
            srcset = im.srcset()
            if srcset:
                self.vars['content'] = self.vars['content'].replace(
                    shortcode, srcset
                )

            del(im)


    def _c_video(self):
        """ [video] shortcode extractor """

        p = re.compile(
            r'(\[video mp4=\"(?:/(?:files|cache)\/(?P<vname>.*?))\"\]'
            r'(?:\[/video\])?)'
        )

        videos = p.findall(self.vars['content'])
        if not videos:
            return

        for shortcode, vidf in videos:
            video = '<video controls><source src="%s/%s" type="video/mp4">Your browser does not support the video tag :(</video>' % (
                config.site['url'],
                vidf
            )
            self.vars['content'] = self.vars['content'].replace(shortcode, video)


    def _c_snippets(self):
        """ Replaces [git:(repo)/(file.ext)] with corresponding code snippet """

        p = re.compile(r'(\[git:([^\/]+)\/([^\]]+\.([^\]]+))\])')
        snippets = p.findall(self.vars['content'])
        if not snippets:
            return

        for shortcode, d, f, ext in snippets:
            fpath = os.path.join(config.SOURCE, d, f)
            if not os.path.isfile(fpath):
                logging.error("missing blogsnippet: %s", self.fpath)
                continue

            if re.compile(r'conf', re.IGNORECASE).match(ext):
                lang = 'apache'
            else:
                lang = ext

            with open(fpath, "rt") as snip:
                c = snip.read()
                snip.close

            c = "\n\n```%s\n%s\n```\n" % (lang, c)
            logging.debug("replacing blogsnippet %s", self.fpath)
            self.vars['content'] = self.vars['content'].replace(
                shortcode, c
            )


    #def _c_files(self):
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


class ArticleHandler(SingularHandler):
    def __init__(self, *args, **kwargs):
        super(ArticleHandler, self).__init__(*args, **kwargs)
        self._setup()

    def _setup(self):
        post = frontmatter.load(self.fpath)
        self.vars['raw_content'] = "%s" % post.content
        self.vars['content'] = "%s" % post.content

        if 'tags' in post.metadata:
            self.vars['tags'] = post.metadata['tags']

        if 'title' in post.metadata:
            self.vars['title'] = post.metadata['title']

        if 'published' in post.metadata:
            self.vars['published'] = arrow.get(post.metadata['published'])

        if 'updated' in post.metadata:
            self.vars['updated'] = arrow.get(post.metadata['updated'])

        if 'summary' in post.metadata:
            self.vars['raw_summary'] = post.metadata['summary']
            self.vars['summary'] = "%s" % post.metadata['summary']

        if 'redirect' in post.metadata and \
        isinstance(post.metadata['redirect'], list):
            for r in post.metadata['redirect']:
                self.redirects[r.strip().strip('/')] = 1

        #if 'syndicate' in post.metadata:
            #z = post.metadata['syndicate']
            #if isinstance(z, str):
                #self.syndicate[z] = ''
            #elif isinstance(z, dict):
                #for s, c in z.items():
                    #self.syndicate[s] = c
            #elif isinstance(z, list):
                #for s in z:
                    #self.syndicate[s] = ''

        self.vars['reactions'] = {}
        # getting rid of '-' to avoid css trouble and similar
        rmap = {
            'bookmark-of': 'bookmark',
            'repost-of': 'repost',
            'in-reply-to': 'reply',
        }

        for x in rmap.items():
            key, replace = x
            if key in post.metadata:
                if isinstance(post.metadata[key], str):
                    self.vars['reactions'][replace] = [post.metadata[key]]
                elif isinstance(post.metadata[key], list):
                    self.vars['reactions'][replace] = post.metadata[key]

        self._c_adaptify()
        self._c_snippets()
        self._c_video()
        #self._files()
        super(ArticleHandler, self)._postsetup()


class PhotoHandler(SingularHandler):
    def __init__(self, *args, **kwargs):
        super(PhotoHandler, self).__init__(*args, **kwargs)
        self.img = ImageHandler(self.fpath)
        self._setup()

    def _setvars(self):
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
                val = self.img.exif.get(candidate, None)
                if val:
                    self.vars['exif'][ekey] = val
                    break

        gps = ['Latitude', 'Longitude']
        for g in gps:
            gk = 'EXIF:GPS%s' % (g)
            if gk not in self.img.exif:
                continue

            r = 'EXIF:GPS%sRef' % (g)
            ref = None
            if r in self.img.exif:
                ref = self.img.exif[r]

            self.vars['exif']['geo_%s' % (g.lower())] = func.gps2dec(
                self.img.exif[gk],
                ref
            )


    def _setfromexif_str(self, varkey, exifkeys):
        for key in exifkeys:
            val = self.img.exif.get(key, None)
            if not val:
                continue
            self.vars[varkey] = val.strip()
            return


    def _setfromexif_lst(self, varkey, exifkeys):
        collected = {}
        for key in exifkeys:
            val = self.img.exif.get(key, None)
            if not val:
                continue
            if isinstance(val, str):
                self.img.exif[key] = val.split(",")
            # not elif: the previous one converts all string to list
            # we rely on that
            if isinstance(val, list):
                for v in val:
                    collected[slugify(str(v).strip())] = str(v).strip()

        self.vars[varkey] = collected.values()
        return


    def _setfromexif_date(self, varkey, exifkeys):
        pattern = re.compile(
            "(?P<Y>[0-9]{4}):(?P<M>[0-9]{2}):(?P<D>[0-9]{2})\s+"
            "(?P<T>[0-9]{2}:[0-9]{2}:[0-9]{2})Z?"
        )

        for key in exifkeys:
            if key not in self.img.exif:
                continue

            if not self.img.exif[key]:
                continue

            date = None
            v = pattern.match(self.img.exif[key]).groupdict()
            if not v:
                continue

            try:
                date = arrow.get('%s-%s-%s %s' % (v['Y'], v['M'], v['D'], v['T']))
            except:
                continue

            if not date:
                continue


            self.vars['published'] = date
            logging.debug("'published' set to %s from key %s", self.vars['published'], key)
            return


    def _setup(self):
        self._setfromexif_str('title', [
            'XMP:Title',
            'XMP:Headline',
            'IPTC:Headline'
        ])

        self._setfromexif_str('raw_content', [
            'XMP:Description',
            'IPTC:Caption-Abstract'
        ])

        self._setfromexif_lst('tags', [
            'XMP:Keywords',
            'IPTC:Keywords'
        ])

        self._setfromexif_date('published', [
            'XMP:DateTimeDigitized',
            'XMP:CreateDate',
            'EXIF:CreateDate',
            'EXIF:ModifyDate'
        ])

        self._setvars()
        self.img.title = self.vars['title']
        self.img.alttext = self.vars['title']

        self.vars['content'] = "%s\n\n%s" % (
            self.vars['raw_content'],
            self.img.srcset(generate_caption=False, uphoto=True)
        )

        self.img.downsize()
        self.vars['img'] = self.img.featured()
        super(PhotoHandler, self)._postsetup()


class PageHandler(SingularHandler):
    def __init__(self, *args, **kwargs):
        super(PageHandler, self).__init__(*args, **kwargs)
        self.template = 'page.html'
        self._setup()


    def _setup(self):
        with open(self.fpath) as c:
            self.vars['raw_content'] = c.read()
            c.close()

        self._c_adaptify()
        super(PageHandler, self)._postsetup()