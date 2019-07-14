__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2019, Peter Molnar"
__license__ = "apache-2.0"
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import os
import re
import argparse
import logging
from tempfile import gettempdir


class struct(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


base = os.path.abspath(os.path.expanduser("~/Projects/petermolnar.net"))
syncserver = "liveserver:/web/petermolnar.net"

pagination = 42
notinfeed = ["note"]
flat = ["article", "journal"]
displaydate = "YYYY-MM-DD HH:mm"
mementostartime = 1560992400

licence = struct(
    {"article": "CC-BY-4.0", "journal": "CC-BY-NC-4.0", "_default": "CC-BY-NC-ND-4.0"}
)

author = struct(
    {
        "@context": "http://schema.org",
        "@type": "Person",
        "image": "https://petermolnar.net/favicon.jpg",
        "email": "mail@petermolnar.net",
        "url": "https://petermolnar.net/",
        "name": "Peter Molnar",
    }
)

site = struct(
    {
        "@context": "http://schema.org",
        "@type": "WebSite",
        "headline": "Peter Molnar",
        "url": "https://petermolnar.net",
        "name": "petermolnar.net",
        "image": "https://petermolnar.net/favicon.ico",
        "license": "https://spdx.org/licenses/%s.html" % (licence["_default"]),
        "sameAs": [],
        "author": {
            "@context": "http://schema.org",
            "@type": "Person",
            "image": "https://petermolnar.net/favicon.jpg",
            "email": "mail@petermolnar.net",
            "url": "https://petermolnar.net/",
            "name": "Peter Molnar",
            "sameAs": [
                "https://github.com/petermolnar",
                "https://petermolnar.net/cv.html",
                "xmpp:mail@petermolnar.net",
                "https://wa.me/447592011721",
                "https://t.me/petermolnar",
                "https://twitter.com/petermolnar",
            ],
            "follows": "https://petermolnar.net/following.opml",
        },
        "publisher": {
            "@context": "http://schema.org",
            "@type": "Organization",
            "logo": {
                "@context": "http://schema.org",
                "@type": "ImageObject",
                "url": "https://petermolnar.net/favicon.jpg",
            },
            "url": "https://petermolnar.net/",
            "name": "petermolnar.net",
            "email": "webmaster@petermolnar.net",
        },
        "potentialAction": [
            {
                "@context": "http://schema.org",
                "@type": "SearchAction",
                "target": "https://petermolnar.net/search.php?q={q}",
                "query-input": "required name=q",
                "url": "https://petermolnar.net/search.php",
            },
            {
                "@context": "http://schema.org",
                "@type": "FollowAction",
                "url": "https://petermolnar.net/follow/",
                "name": "follow",
            },
            {
                "@context": "http://schema.org",
                "@type": "DonateAction",
                "description": "Monzo",
                "name": "monzo",
                "url": "https://monzo.me/petermolnar/",
                "recipient": author,
            },
            {
                "@context": "http://schema.org",
                "@type": "DonateAction",
                "description": "Paypal",
                "name": "paypal",
                "url": "https://paypal.me/petermolnar/",
                "recipient": author,
            },
        ],
    }
)


menu = struct(
    {
        "home": {"url": "%s/" % site["url"], "text": "home"},
        "photo": {"url": "%s/category/photo/" % site["url"], "text": "photos"},
        "journal": {"url": "%s/category/journal/" % site["url"], "text": "journal"},
        "article": {"url": "%s/category/article/" % site["url"], "text": "IT"},
        "note": {"url": "%s/category/note/" % site["url"], "text": "notes"},
    }
)

meta = struct(
    {
        "webmention": "https://webmention.io/petermolnar.net/webmention",
        "pingback": "https://webmention.io/petermolnar.net/xmlrpc",
        "hub": "https://petermolnar.superfeedr.com/",
        "authorization_endpoint": "https://indieauth.com/auth",
        "token_endpoint": "https://tokens.indieauth.com/token",
        "micropub": "https://petermolnar.net/micropub.php",
        #'microsub': 'https://aperture.p3k.io/microsub/83'
    }
)

paths = struct(
    {
        "content": os.path.join(base, "content"),
        "tmpl": os.path.join(base, "nasg", "templates"),
        "watermark": os.path.join(base, "nasg", "templates", "watermark.png"),
        "build": os.path.join(base, "www"),
        "queue": os.path.join(base, "queue"),
        "remotewww": "web",
        "remotequeue": "queue",
        "micropub": os.path.join(base, "content", "note"),
        "home": os.path.join(base, "content", "home", "index.md"),
        "category": "category",
        "feed": "feed",
    }
)

filenames = struct(
    {
        "rss": "index.xml",
        "atom": "atom.xml",
        "json": "index.json",
        "md": "index.md",
        "txt": "index.txt",
        "html": "index.html",
        "gopher": "gophermap",
        "oembed_xml": "oembed.xml",
        "oembed_json": "oembed.json",
        "memento": "memento.html",
        "sitemap": "sitemap.txt",
    }
)

datignore = [".git", ".dat", "**.php"]

photo = struct(
    {
        "re_author": re.compile(
            r"(?:P[eé]ter Moln[aá]r)|(?:Moln[aá]r P[eé]ter)|(?:petermolnar\.(?:eu|net))"
        ),
        "default": 720,
        "sizes": {
            # 90 = s
            # 360 = m
            720: "",
            1280: "_b",
        },
        "earlyyears": 2014,
    }
)

# symlinks = {
#'files/a-view-from-barbican-1280x720.jpg':  'a-view-from-barbican/a-view-from-barbican_b.jpg',
#'files/hills_from_beachy_head-540x226.jpg': 'hills-from-beachy-head/hills-from-beachy-head.jpg',
#'files/seven_sisters_from_beachy_head-540x304.jpg': 'seven-sisters-from-beachy-head/seven-sisters-from-beachy-head.jpg',
#'files/the_countryside-540x304.jpg': 'the-countryside/the-countryside.jpg',
#'files/MGP0538-540x358.jpg': '',
#'files/IMGP0539-540x358.jpg': '',
#'files/IMGP0538-540x358.jpg': '',
# }

tmpdir = os.path.join(gettempdir(), "nasg")
if not os.path.isdir(tmpdir):
    os.makedirs(tmpdir)

_parser = argparse.ArgumentParser(description="Parameters for NASG")
_booleanparams = {
    "regenerate": "force (re)downsizing images",
    "force": "force (re)rendering HTML",
    "debug": "set logging to debug level",
    "quiet": "show only errors",
    "offline": "offline mode - no syncing, no querying services, etc.",
    "noping": "make dummy webmention entries and don't really send them",
    "noservices": "skip querying any service but do sync the website",
    "memento": "try to fetch mementos from archive.org",
}

for k, v in _booleanparams.items():
    _parser.add_argument("--%s" % (k), action="store_true", default=False, help=v)

args = vars(_parser.parse_args())

if args.get("debug", False):
    loglevel = 10
elif args.get("quiet", False):
    loglevel = 40
else:
    loglevel = 20

logger = logging.getLogger("NASG")
logger.setLevel(loglevel)

console_handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logging.getLogger("asyncio").setLevel(loglevel)
