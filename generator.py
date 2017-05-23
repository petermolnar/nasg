#!/home/petermolnar.net/.venv/bin/python3.5

"""Usage: generator.py [-h] [-f] [-g] [-p] [-d] [-s FILE]

-h --help                 show this
-f --force                force HTML file rendering
-p --pandoc               force re-rendering content HTML
-g --regenerate           regenerate images
-s --single FILE          only (re)generate a single entity
-d --debug                set logging level
"""

import os
import shutil
import logging
import atexit
import json
import sys
import tempfile
import glob
from whoosh import index
from docopt import docopt
from ruamel import yaml
from webmentiontools.send import WebmentionSend
import taxonomy
import singular
from slugify import slugify
import arrow


class Engine(object):
    lockfile = "/tmp/petermolnar.net.generator.lock"

    def __init__(self):
        if os.path.isfile(self.lockfile):
            raise ValueError("Lockfile %s is present; generator won't run.")
        else:
            with open(self.lockfile, "w") as lock:
                lock.write(arrow.utcnow().format())
                lock.close()

        atexit.register(self.removelock)
        atexit.register(self.removetmp)

        self._mkdirs()
        self.tags = {}
        self.category = {}
        self.allposts = None
        self.frontposts = None

        self.slugsdb = os.path.join(glob.CACHE, "slugs.json")
        if os.path.isfile(self.slugsdb):
            with open(self.slugsdb) as slugsdb:
                self.allslugs = json.loads(slugsdb.read())
                slugsdb.close()
        else:
            self.allslugs = []

        self.tmpwhoosh = tempfile.mkdtemp('whooshdb_', dir=tempfile.gettempdir())
        self.whoosh = index.create_in(self.tmpwhoosh, glob.schema)


    def removelock(self):
        os.unlink(self.lockfile)


    def removetmp(self):
        if os.path.isdir(self.tmpwhoosh):
            for root, dirs, files in os.walk(self.tmpwhoosh, topdown=False):
                for f in files:
                    os.remove(os.path.join(root, f))
                for d in dirs:
                    os.rmdir(os.path.join(root, d))


    def initbuilder(self):
        self._copy_and_compile()


    def cleanup(self):
        with open(os.path.join(glob.CACHE, "slugs.json"), "w") as db:
            logging.info("updating slugs database")
            db.write(json.dumps(self.allslugs))
            db.close()

        tags = []
        for tslug, taxonomy in self.tags.items():
            tags.append(taxonomy.name)

        with open(os.path.join(glob.CACHE, "tags.json"), "w") as db:
            logging.info("updating tags database")
            db.write(json.dumps(tags))
            db.close()

        logging.info("deleting old searchdb")
        shutil.rmtree(glob.SEARCHDB)
        logging.info("moving new searchdb")
        shutil.move(self.tmpwhoosh, glob.SEARCHDB)


    def _mkdirs(self):
        for d in [glob.TARGET, glob.TFILES, glob.TTHEME, glob.CACHE]:
            if not os.path.isdir(d):
                os.mkdir(d)


    def _copy_and_compile(self):
        for f in os.listdir(glob.STHEME):
            p = os.path.join(glob.STHEME, f)
            if os.path.isdir(p):
                try:
                    shutil.copytree(p, os.path.join(glob.TTHEME, f))
                except FileExistsError:
                    pass
            else:
                path, fname = os.path.split(p)
                fname, ext = os.path.splitext(fname)
                logging.debug("copying %s", p)
                shutil.copy(p, os.path.join(glob.TTHEME, f))

    @staticmethod
    def postbycategory(fpath, catd=None, catn=None):
        if catd == 'photo':
            post = singular.PhotoHandler(fpath, category=catn)
        elif catd == 'page':
            post = singular.PageHandler(fpath)
        else:
            post = singular.ArticleHandler(fpath, category=catn)

        return post

    def collect(self):
        self.allposts = taxonomy.TaxonomyHandler()
        #self.gallery = taxonomy.TaxonomyHandler(taxonomy="photography", name="Photography")
        self.frontposts = taxonomy.TaxonomyHandler()

        for category in glob.conf['category'].items():
            catn, catd = category
            catp = os.path.abspath(os.path.join(glob.CONTENT, catn))

            if not os.path.exists(catp):
                continue

            logging.debug("getting posts for category %s from %s", catn, catp)

            cat = taxonomy.TaxonomyHandler(taxonomy='category', name=catn)
            self.category[catn] = cat

            for f in os.listdir(catp):
                fpath = os.path.join(catp, f)

                if not os.path.isfile(fpath):
                    continue

                logging.debug("parsing %s", fpath)
                exclude = False
                if 'exclude' in catd:
                    exclude = bool(catd['exclude'])

                ct = None
                if 'type' in catd:
                    ct = catd['type']

                post = Engine.postbycategory(fpath, catd=ct, catn=catn)

                self.allposts.append(post)
                if post.dtime > arrow.utcnow().timestamp:
                    logging.warning(
                        "Post '%s' will be posted in the future; "
                        "skipping it from Taxonomies for now", fpath
                    )
                else:
                    cat.append(post)
                    if not exclude:
                        self.frontposts.append(post)
                    if hasattr(post, 'tags') and isinstance(post.tags, list):
                        for tag in post.tags:
                            tslug = slugify(tag, only_ascii=True, lower=True)
                            if not tslug in self.tags.keys():
                                t = taxonomy.TaxonomyHandler(taxonomy='tag', name=tag)
                                self.tags[tslug] = t
                            else:
                                t = self.tags[tslug]
                            t.append(post)
                    elif not hasattr(post, 'tags'):
                        logging.error("%s post does not have tags", post.fname)
                    elif not isinstance(post.tags, list):
                        logging.error(
                            "%s tags are not a list, it's %s ",
                            post.fname,
                            type(post.tags)
                        )


                for r in post.redirect.keys():
                    self.allslugs.append(r)
                self.allslugs.append(post.fname)


    def renderposts(self):
        for p in self.allposts.posts.items():
            time, post = p
            post.write()
            post.redirects()
            post.pings()
            post.index(self.whoosh)


    def rendertaxonomies(self):
        for t in [self.tags, self.category]:
            for tname, tax in t.items():
                if glob.conf['category'].get(tname, False):
                    if glob.conf['category'][tname].get('nocollection', False):

                        logging.info("skipping taxonomy '%s' due to config nocollections", tname)
                        continue

                tax.write_paginated()
                tax.index(self.whoosh)
        self.frontposts.write_paginated()
        #self.gallery.write_simple(template='gallery.html')
        self.allposts.writesitemap()

    def globredirects(self):
        redirects = os.path.join(glob.CONTENT,'redirects.yml')

        if not os.path.isfile(redirects):
            return

        ftime = os.stat(redirects)
        rdb = {}
        with open(redirects, 'r') as db:
            rdb = yaml.safe_load(db)
            db.close()

        for r_ in rdb.items():
            target, slugs = r_
            for slug in slugs:
                singular.SingularHandler.write_redirect(
                    slug,
                    "%s/%s" % (glob.conf['site']['url'], target),
                    ftime.st_mtime
                )

    def recordlastrun(self):
        if os.path.exists(glob.lastrun):
            t = arrow.utcnow().timestamp
            os.utime(glob.lastrun, (t,t))
        else:
            open(glob.lastrun, 'a').close()


if __name__ == '__main__':

    args = docopt(__doc__, version='generator.py 0.2')

    if args['--pandoc']:
        glob.CACHEENABLED = False

    if args['--force']:
        glob.FORCEWRITE = True

    if args['--regenerate']:
        glob.REGENERATE = True

    logform = '%(asctime)s - %(levelname)s - %(message)s'
    if args['--debug']:
        loglevel = 10
    else:
        loglevel = 40


    while len(logging.root.handlers) > 0:
        logging.root.removeHandler(logging.root.handlers[-1])
    logging.basicConfig(level=loglevel, format=logform)

    if args['--single']:
        logging.info("(re)generating a single item only")
        path = args['--single'].split('/')
        fpath = os.path.join(glob.CONTENT, path[0], path[1])
        post = Engine.postbycategory(fpath, catd=path[0])
        post.pings()
        post.write()
        sys.exit(0)
    else:
        eng = Engine()
        eng.initbuilder()
        eng.collect()
        eng.renderposts()
        eng.globredirects()
        eng.rendertaxonomies()
        eng.recordlastrun()
        eng.cleanup()