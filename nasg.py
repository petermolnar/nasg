import argparse
import logging
import os
import re
import arrow
import atexit
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import cpu_count
from slugify import slugify

import nasg.config as config
import nasg.singular as singular
import nasg.searchindex as searchindex
import nasg.taxonomy as taxonomy

from pprint import pprint

parser = argparse.ArgumentParser(description='Parameters for NASG')
parser.add_argument(
    '--regenerate', '-f',
    dest='regenerate',
    action='store_true',
    default=False,
    help='force regeneration of all HTML outputs'
)
parser.add_argument(
    '--downsize', '-c',
    action='store_true',
    dest='downsize',
    default=False,
    help='force re-downsizing of all suitable images'
)
parser.add_argument(
    '--debug', '-d',
    action='store_true',
    dest='debug',
    default=False,
    help='turn on debug log'
)

class Engine(object):
    def __init__(self):
        self._initdirs()
        self._lock()
        atexit.register(self._lock, action='clear')
        self.files = []
        self.categories = {}
        self.tags = {}
        self.allposts = taxonomy.TaxonomyHandler('')
        self.frontposts = taxonomy.TaxonomyHandler('')
        self.allowedpattern = re.compile(config.accept_sourcefiles)
        self.counter = {}

    def _parse_results(self, futures):
        for future in futures:
            try:
                future.result()
            except Exception as e:
                logging.error("processing failed: %s", e)


    def collect(self):
        self._setup_categories()
        self._setup_singulars()


    def render(self):
        self._render_singulars()
        #self._render_taxonomy()


    def _render_singulars(self):
        logging.warning("rendering singulars")
        pprint(self.allposts)
        #futures = []
        #with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
        for p in self.allposts:
            #futures.append(executor.submit(p.write))
            p.write()
        #for future in futures:
            #try:
                #future.result()
            #except Exception as e:
                #logging.error("processing failed: %s", e)


    def _render_taxonomy(self):
        futures = []
        with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
            for tslug, t in self.tags.items():
                #t.write()
                futures.append(executor.submit(t.write))
            for cslug, c in self.categories.items():
                #c.write()
                futures.append(executor.submit(c.write))
            #self.frontposts.write()
            futures.append(executor.submit(self.frontposts.write))
        self._parse_results(futures)


    def _setup_categories(self):
        for cat, meta in config.categories.items():
            cpath = os.path.join(config.CONTENT, cat)
            if not os.path.isdir(cpath):
                logging.error("category %s not found at: %s", cat, cpath)
                continue

            self.categories[cat] = taxonomy.TaxonomyHandler(
                meta.get('name', cat),
                taxonomy=meta.get('type', 'category'),
                slug=cat,
                render=meta.get('render', True)
            )


    def _setup_singulars(self):
        futures = []
        with ProcessPoolExecutor(max_workers=cpu_count()) as executor:
            for slug, tax in self.categories.items():
                cpath = os.path.join(config.CONTENT, slug)
                for f in os.listdir(cpath):
                    fpath = os.path.join(cpath,f)
                    if not self.allowedpattern.fullmatch(f):
                        logging.warning("unexpected file at: %s" % fpath)
                        continue
                    #self._posttype(fpath, slug)
                    futures.append(executor.submit(self._posttype, fpath, slug))
        self._parse_results(futures)

    def _posttype(self, fpath, cat):
        c = self.categories[cat]

        if re.match('.*\.jpg', fpath):
            p = singular.PhotoHandler(fpath)
        elif 'page' == c.taxonomy:
            p = singular.PageHandler(fpath)
        else:
            p = singular.ArticleHandler(fpath)

        c.append(p)
        self.allposts.append(p)

        front = config.categories[cat].get('front', True)
        if front:
            self.frontposts.append(p)

        ptags = p.vars.get('tags', [])
        for tag in ptags:
            tslug = slugify(tag, only_ascii=True, lower=True)
            if tslug not in self.tags:
                self.tags[tslug] = taxonomy.TaxonomyHandler(
                    tag,
                    taxonomy='tag',
                    slug=tslug
                )
            self.tags[tslug].append(p)


    def _initdirs(self):
        for d in [
            config.TARGET,
            config.TTHEME,
            config.TFILES,
            config.VAR,
            config.SEARCHDB,
            config.TSDB,
            config.LOGDIR
        ]:
            if not os.path.exists(d):
                os.mkdir(d)


    def _lock(self, action='set'):
        if 'set' == action:
            if os.path.exists(config.LOCKFILE):
                raise ValueError("lockfile %s present" % config.LOCKFILE)
            with open(config.LOCKFILE, "wt") as l:
                l.write("%s" % arrow.utcnow())
                l.close()
        elif 'clear' == action:
            if os.path.exists(config.LOCKFILE):
                os.unlink(config.LOCKFILE)
        else:
            return os.path.exists(config.LOCKFILE)


if __name__ == '__main__':
    config.options.update(vars(parser.parse_args()))
    loglevel = 30
    if config.options['debug']:
        loglevel = 10

    while len(logging.root.handlers) > 0:
        logging.root.removeHandler(logging.root.handlers[-1])

    logging.basicConfig(
        level=loglevel,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    engine = Engine()
    engine.collect()
    engine.render()