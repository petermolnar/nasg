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
from time import sleep

logger = logging.getLogger("wayback")
logger.setLevel(10)

console_handler = logging.StreamHandler()
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

from pprint import pprint

RE_FIRST = re.compile(
    r"^\<(?P<url>[^>]+)\>; rel=\"first memento\"; datetime=\"(?P<datetime>[^\"]+).*$"
)


class FindWaybackURL(object):
    def __init__(self, path, category=""):
        self.path = path
        self.category = category
        self.epoch = int(arrow.utcnow().timestamp)
        self.oldest = ""

    def save_to_archiveorg(self):
        urls = [
            f"{settings.site.url}/{self.path}/",
            f"{settings.site.url}/{self.path}/index.html"
        ]
        for url in urls:
            logger.info("saving %s to archive.org ", url)
            r = requests.get(f"https://web.archive.org/save/{url}")

    def possible_urls(self):
        q = {}
        q[f"http://{settings.site.name}/{self.path}/"] = True
        q[f"http://{settings.site.name}/{self.path}/index.html"] = True

        domains = settings.formerdomains + [settings.site.name]
        for domain in domains:
            q[f"http://{domain}/{self.path}/"] = True
            categories = []
            if self.category in settings.formercategories:
                categories = categories + settings.formercategories[self.category]
            for category in categories:
                q[f"http://{domain}/{category}/{self.path}/"] = True
                q[
                    f"http://{domain}/category/{category}/{self.path}/"
                ] = True
        return list(q.keys())

    def get_first_memento(self, url):
        target = f"http://web.archive.org/web/timemap/link/{url}"
        logger.info("requesting %s", url)
        mementos = requests.get(target)
        if mementos.status_code == requests.codes.ok:
            if not len(mementos.text):
                logger.debug("empty memento response for %s", target)
            for memento in mementos.text.split("\n"):
                m = RE_FIRST.match(memento)
                if m:

                    r = settings.nameddict(
                        {
                            "epoch": int(
                                arrow.get(
                                    m.group("datetime"),
                                    "ddd, DD MMM YYYY HH:mm:ss ZZZ",
                                )
                                .to("utc")
                                .timestamp
                            ),
                            "url": m.group("url"),
                        }
                    )
                    logger.info("found memento candidate: %s", r)
                    return r
                else:
                    logger.debug(
                        "no first memento found at: %s", target
                    )
        else:
            logger.warning(
                "request failed: %s, status: %s, txt: %s",
                mementos,
                mementos.status_code,
                mementos.text,
            )

    def run(self):
        l = self.possible_urls()
        logger.info("running archive.org lookup for %s", self.path)
        for url in l:
            maybe = self.get_first_memento(url)
            if maybe:
                if maybe.epoch < self.epoch:
                    self.epoch = maybe.epoch
                    self.oldest = maybe.url
            sleep(.500)
        if not len(self.oldest):
            logger.error("no memento found for %s", self.path)
            self.save_to_archiveorg()
        else:
            logger.info(
                "\t\toldest found memento for %s: %s :: %s",
                self.path,
                str(arrow.get(self.epoch)),
                self.oldest,
            )
