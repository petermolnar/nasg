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


base = os.path.abspath(os.path.expanduser('~/Projects/petermolnar.net'))
syncserver = 'liveserver:/web/petermolnar.net'

pagination = 42
notinfeed = ['note']
flat = ['article', 'journal']
displaydate = 'YYYY-MM-DD HH:mm'

licence = struct({
    'article': 'CC-BY-4.0',
    'journal': 'CC-BY-NC-4.0',
    '_default': 'CC-BY-NC-ND-4.0'
})

author = struct({
    "@context": "http://schema.org",
    "@type": "Person",
    "image": "https://petermolnar.net/favicon.jpg",
    "email": "mail@petermolnar.net",
    "url": "https://petermolnar.net/",
    "name": "Peter Molnar"
})

site = struct({
    "@context": "http://schema.org",
    "@type": "WebSite",
    "headline": "Peter Molnar",
    "url": "https://petermolnar.net",
    "name": "petermolnar.net",
    "image": "https://petermolnar.net/favicon.ico",
    "license": "https://spdx.org/licenses/%s.html" % (licence['_default']),
    #"sameAs": [
        #"dat://8d03735af11d82fff82028e0f830f9ac470f5e9fbe10ab5eb6feb877232714a2"
    #],
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
        ],
        "follows": "https://petermolnar.net/following.opml"
    },
    "publisher": {
        "@context": "http://schema.org",
        "@type": "Organization",
        "logo": {
            "@context": "http://schema.org",
            "@type": "ImageObject",
            "url": "https://petermolnar.net/favicon.jpg"
        },
        "url": "https://petermolnar.net/",
        "name": "petermolnar.net",
        "email": "webmaster@petermolnar.net"
    },
    "potentialAction": [
        {
            "@context": "http://schema.org",
            "@type": "SearchAction",
            "target": "https://petermolnar.net/search.php?q={q}",
            "query-input": "required name=q",
            "url": "https://petermolnar.net/search.php"
        },
        {
            "@context": "http://schema.org",
            "@type": "FollowAction",
            "url": "https://petermolnar.net/follow/",
            "name": "follow"
        },
        #{
            #"@context": "http://schema.org",
            #"@type": "DonateAction",
            #"description": "Monzo (only in the UK or via Google Pay)",
            #"name": "monzo",
            #"price": "3GBP",
            #"url": "https://monzo.me/petermolnar/3",
            #"recipient": author
        #},
        #{
            #"@context": "http://schema.org",
            #"@type": "DonateAction",
            #"description": "Paypal",
            #"name": "paypal",
            #"price": "3GBP",
            #"url": "https://paypal.me/petermolnar/3GBP",
            #"recipient": author
        #}
    ]
})


menu = {
    'home': {
        'url': '%s/' %  site['url'],
        'text': 'home',
    },
    'photo': {
        'url': '%s/category/photo/' %  site['url'],
        'text': 'photos',
    },
    'journal': {
        'url': '%s/category/journal/' %  site['url'],
        'text': 'journal',
    },
    'article': {
        'url': '%s/category/article/' %  site['url'],
        'text': 'IT',
    },
    'note': {
        'url': '%s/category/note/' %  site['url'],
        'text': 'notes'
    }
}

meta = struct({
    'webmention': 'https://webmention.io/petermolnar.net/webmention',
    'pingback': 'https://webmention.io/petermolnar.net/xmlrpc',
    'hub': 'https://petermolnar.superfeedr.com/',
    'authorization_endpoint': 'https://indieauth.com/auth',
    'token_endpoint': 'https://tokens.indieauth.com/token',
    'micropub': 'https://petermolnar.net/micropub.php',
    #'microsub': 'https://aperture.p3k.io/microsub/83'
})

paths = struct({
    'content': os.path.join(base, 'content'),
    'tmpl': os.path.join(base, 'nasg', 'templates'),
    'watermark': os.path.join(base, 'nasg', 'templates', 'watermark.png'),
    'build': os.path.join(base, 'www'),
    'queue': os.path.join(base, 'queue'),
    'remotewww': 'web',
    'remotequeue': 'queue',
    'micropub': os.path.join(base, 'content', 'note'),
    'home': os.path.join(base, 'content', 'home', 'index.md'),
})

photo = struct({
    're_author': re.compile(r'(?:P[eé]ter Moln[aá]r)|(?:Moln[aá]r P[eé]ter)|(?:petermolnar\.(?:eu|net))'),
    'default': 720,
    'sizes': {
        #90 = s
        #360 = m
        720: '',
        1280: '_b',
    },
    'earlyyears': 2014
})

tmpdir = os.path.join(gettempdir(),'nasg')
if not os.path.isdir(tmpdir):
    os.makedirs(tmpdir)

_parser = argparse.ArgumentParser(description='Parameters for NASG')
_booleanparams = {
    'regenerate': 'force downsizing images',
    'force': 'force rendering HTML',
    'nosync': 'skip sync to live server',
    'debug': 'set logging to debug level',
    'quiet': 'show only errors',
    'noping': 'don\'t send webmentions but save a dummy that it was done'
}

for k, v in _booleanparams.items():
    _parser.add_argument(
        '--%s' % (k),
        action='store_true',
        default=False,
        help=v
    )

args = vars(_parser.parse_args())

if args.get('debug', False):
    loglevel = 10
elif args.get('quiet', False):
    loglevel = 40
else:
    loglevel = 20

logger = logging.getLogger('NASG')
logger.setLevel(loglevel)

console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

logging.getLogger('asyncio').setLevel(loglevel)
