__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2019, Peter Molnar"
__license__ = "apache-2.0"
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import re
import json
import os
import logging
import requests
from collections import deque
from urllib.parse import urlparse
import settings
import arrow

logger = logging.getLogger("wayback")
logger.setLevel(10)

console_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

from pprint import pprint

RE_FIRST = re.compile(r"^\<(?P<url>[^>]+)\>; rel=\"first memento\"; datetime=\"(?P<datetime>[^\"]+).*$")

class FindWaybackURL(object):

    def __init__(self, path, category="", redirects=[]):
        self.path = path
        self.category = category
        self.redirects = redirects
        self.epoch = int(arrow.utcnow().timestamp)
        self.oldest = ""

    def possible_urls(self):
        q = {}
        paths = self.redirects
        paths.append(self.path)
        for path in paths:
            q[f"http://{settings.site.name}/{path}/"] = True
            q[f"http://{settings.site.name}/{path}/index.html"] = True

            domains = settings.formerdomains
            domains.append(settings.site.name)

            for domain in domains:
                q[f"http://{domain}/{path}/"] = True
                if self.category in settings.formercategories:
                    categories = settings.formercategories[self.category]
                else:
                    categories = []
                categories.append(self.category)
                for category in categories:
                    q[f"http://{domain}/{category}/{path}/"] = True
                    q[f"http://{domain}/category/{category}/{path}/"] = True
        #logger.info("possible urls: %s", json.dumps(list(q.keys()), indent=4, ensure_ascii=False))
        return list(q.keys())

    def get_first_memento(self, url):
        target = f"http://web.archive.org/web/timemap/link/{url}"
        mementos = requests.get(target)
        if not mementos.text:
            return None
        for memento in mementos.text.split("\n"):
            m = RE_FIRST.match(memento)
            if m:
                return settings.nameddict({
                    'epoch': int(arrow.get(m.group('datetime'), "ddd, DD MMM YYYY HH:mm:ss ZZZ").to("utc").timestamp),
                    'url': m.group('url')
                })

    def run(self):
        l = self.possible_urls()
        logging.info("running archive.org lookup for %s", self.path)
        for url in l:
            maybe = self.get_first_memento(url)
            if maybe:
                if maybe.epoch < self.epoch:
                    self.epoch = maybe.epoch
                    self.oldest = maybe.url
        if not len(self.oldest):
            logger.error("no memento found for %s", self.path)
        else:
            logger.info("\t\toldest found memento for %s: %s :: %s", self.path, str(arrow.get(self.epoch)), self.oldest)
