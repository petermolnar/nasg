import math
import logging
import os
import collections
import json
import glob
from slugify import slugify
from bs4 import BeautifulSoup
from pprint import pprint

class TaxonomyHandler(object):

    def __init__(self, taxonomy='', name='', description='', exclude=False):
        self.taxonomy = taxonomy
        self.name = name
        self.description = description
        self.exclude = exclude
        self.slug = slugify(self.name, only_ascii=True, lower=True)
        self.posts = collections.OrderedDict()

        self.taxp = os.path.join(glob.TARGET, self.taxonomy)
        self.simplepath = os.path.join(self.taxp, 'index.html')
        self.basep = os.path.join(self.taxp, self.slug)
        self.pagedp = os.path.join(self.basep, 'page')
        self.indexpath = os.path.join(self.basep, 'index.html')

        self.lptime = 0

    def __getitem__(self, key):
        return self.posts[key]

    def __repr__(self):
        return 'Taxonomy %s (name: %s, slug: %s) with %i posts' % (
            self.taxonomy,
            self.name,
            self.slug,
            len(self.posts)
        )

    def __next__(self):
        try:
            r = self.posts.next()
        except:
            raise StopIteration()
        return r

    def __iter__(self):
        for ix, post in self.posts.items():
            yield post
        return


    def append(self, post):
        k = int(post.date.timestamp)
        if k in self.posts:
            inc = 1
            while k in self.posts:
                k = int(k+1)

        self.posts[k] = post
        self.posts = collections.OrderedDict(sorted(self.posts.items(), reverse=True))


    def index(self, ix):
        """ Write search index """

        writer = ix.writer()

        t, lp = list(self.posts.items())[0]

        writer.add_document(
            title=self.name,
            url="%s/%s/%s" % (glob.conf['site']['url'], self.taxonomy, self.slug),
            content="%s %s" % (self.name, self.slug),
            date=lp.date.datetime,
            tags=",".join([self.name]),
            weight=10
        )
        writer.commit()


    def _test_freshness(self):
        t, lp = list(self.posts.items())[0]
        self.lptime = lp.ftime.st_mtime

        if os.path.isfile(self.indexpath):
            p = self.indexpath
        elif os.path.isfile(self.simplepath):
            p = self.simplepath
        else:
            return False

        itime = os.stat(p)
        if itime.st_mtime == self.lptime and not glob.FORCEWRITE:
            logging.debug(
                'Taxonomy tree is fresh for %s' % (self.name)
            )
            return True

        return False


    def _test_dirs(self):
        if not os.path.isdir(self.taxp):
            os.mkdir(self.taxp)
        if not os.path.isdir(self.basep):
            os.mkdir(self.basep)


    def write_paginated(self):

        if self._test_freshness():
            return

        self._test_dirs()

        taxp = os.path.join(glob.TARGET, self.taxonomy)
        basep = os.path.join(glob.TARGET, self.taxonomy, self.slug)

        if not os.path.isdir(taxp):
            os.mkdir(taxp)
        if not os.path.isdir(basep):
            os.mkdir(basep)


        pages = math.ceil(len(self.posts) / glob.conf['perpage'])
        page = 1


        if len(self.taxonomy) and len(self.slug):
            base_url = "/%s/%s/" % (self.taxonomy, self.slug)
        else:
            base_url = '/'


        while page <= pages:
            start = int((page-1) * int(glob.conf['perpage']))
            end = int(start + int(glob.conf['perpage']))
            dorss = False
            posttmpls = [self.posts[k].tmpl() for k in list(sorted(
                self.posts.keys(), reverse=True))[start:end]]

            if page == 1:
                tpath = self.indexpath
                do_rss = True
                # RSS

            else:
                do_rss = False
                if not os.path.isdir(self.pagedp):
                    os.mkdir(self.pagedp)

                tdir = os.path.join(self.pagedp, "%d" % page)

                if not os.path.isdir(tdir):
                    os.mkdir(tdir)
                tpath = os.path.join(tdir, "index.html")

            tvars = {
                'taxonomy': {
                    'url': base_url,
                    'name': self.name,
                    'taxonomy': self.taxonomy,
                    'description': self.description,
                    'paged': page,
                    'total': pages,
                    'perpage': glob.conf['perpage'],
                },
                'site': glob.conf['site'],
                'posts': posttmpls,
            }


            tmpl = glob.jinja2env.get_template('archive.html')
            logging.info("rendering %s" % (tpath))
            with open(tpath, "w") as html:
                r = tmpl.render(tvars)
                soup = BeautifulSoup(r, "html5lib")
                r = soup.prettify()
                logging.info("writing %s" % (tpath))
                html.write(r)
                html.close()
            os.utime(tpath, (self.lptime, self.lptime))

            if do_rss:
                feeddir = os.path.join(self.basep, 'feed')
                if not os.path.isdir(feeddir):
                    os.mkdir(feeddir)
                feedpath = os.path.join(feeddir, "index.xml")
                tmpl = glob.jinja2env.get_template('rss.html')
                logging.info("rendering %s" % (feedpath))
                with open(feedpath, "w") as html:
                    r = tmpl.render(tvars)
                    logging.info("writing %s" % (feedpath))
                    html.write(r)
                    html.close()
                os.utime(feedpath, (self.lptime, self.lptime))

            page = page+1

    def write_simple(self, template='archive.html'):

        if self._test_freshness():
            return

        self._test_dirs()

        base_url = "/%s/" % (self.slug)

        posttmpls = [self.posts[k].tmpl() for k in list(sorted(
                self.posts.keys(), reverse=True))]

        tvars = {
            'taxonomy': {
                'url': base_url,
                'name': self.name,
                'taxonomy': self.taxonomy,
                'description': self.description,
                'paged': 0,
                'total': 0,
                'perpage': glob.conf['perpage'],
            },
            'site': glob.conf['site'],
            'posts': posttmpls,
        }

        with open(os.path.join(self.simplepath), "w") as html:
            html.write(json.dumps(tvars, indent=4, sort_keys=True, default=str))
            html.close()

        #tmpl = glob.jinja2env.get_template('gallery.html')
        #logging.info("rendering %s" % (indexpath))
        #with open(indexpath, "w") as html:
            #r = tmpl.render(tvars)
            #soup = BeautifulSoup(r, "html5lib")
            #r = soup.prettify()
            #logging.info("writing %s" % (indexpath))
            #html.write(r)
            #html.close()
        #os.utime(indexpath, (lptime, lptime))


    def writesitemap(self):
        sitemap = "%s/sitemap.txt" % (glob.TARGET)
        urls = []
        for p in self.posts.items():
            t, data = p
            urls.append( "%s/%s" % ( glob.conf['site']['url'], data.slug ) )

        with open(sitemap, "w") as f:
            logging.info("writing %s" % (sitemap))
            f.write("\n".join(urls))
            f.close()