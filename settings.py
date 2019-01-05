__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2019, Peter Molnar"
__license__ = "apache-2.0"
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import os
import re
import argparse
import logging

base = os.path.abspath(os.path.expanduser('~/Projects/petermolnar.net'))
syncserver = 'liveserver:/web/petermolnar.net'

site = {
    'title': 'Peter Molnar',
    'url': 'https://petermolnar.net',
    'domain': 'petermolnar.net',
    'pagination': 42,
    'on_front': [
        'article',
        'photo',
        'journal'
    ],
    'licence': 'CC-BY-NC-ND-4.0',
}

categorydisplay = {
    'article': 'flat',
    'journal': 'flat',
}

licence = {
    'article': 'CC-BY-4.0',
    'journal': 'CC-BY-NC-4.0',
}

meta = {
    'webmention': 'https://webmention.io/petermolnar.net/webmention',
    'pingback': 'https://webmention.io/petermolnar.net/xmlrpc',
    'hub': 'https://petermolnar.superfeedr.com/',
    'authorization_endpoint': 'https://indieauth.com/auth',
    'token_endpoint': 'https://tokens.indieauth.com/token',
    'micropub': 'https://petermolnar.net/micropub.php',
    'microsub': 'https://aperture.p3k.io/microsub/83'
}

author = {
    'name': 'Peter Molnar',
    'email': 'mail@petermolnar.net',
    'url': 'https://petermolnar.net/',
    'avatar': 'https://petermolnar.net/molnar_peter_avatar.jpg',
    'gpg': 'https://petermolnar.net/pgp.asc',
    'cv': 'https://petermolnar.net/about.html',
    'contact': {
        'xmpp': 'xmpp:mail@petermolnar.net?message',
        'flickr': 'https://flickr.com/people/petermolnareu',
        'github': 'https://github.com/petermolnar',
        'whatsapp': 'https://wa.me/447592011721',
        'telegram': 'https://t.me/petermolnar',
    }
}

paths = {
    'content': os.path.join(base, 'content'),
    'tmpl': os.path.join(base, 'nasg', 'templates'),
    'watermark': os.path.join(base, 'nasg', 'templates', 'watermark.png'),
    'build': os.path.join(base, 'www'),
    'queue': os.path.join(base, 'queue'),
    'remotewww': 'web',
    'remotequeue': 'queue',
    'micropub': os.path.join(base, 'content', 'note'),
    'tmp': os.path.join(base, 'tmp'),
}

photo = {
    're_author': re.compile(r'(?:P[eé]ter Moln[aá]r)|(?:Moln[aá]r P[eé]ter)|(?:petermolnar\.(?:eu|net))'),
    'default': 720,
    'sizes': {
        #90 = s
        #360 = m
        720: '',
        1280: '_b',
    },
}

tips = {
    'paypal': 'https://paypal.me/petermolnar/3GBP',
    'monzo': 'https://monzo.me/petermolnar/3',
}

dateformat = {
    'iso': 'YYYY-MM-DDTHH:mm:ssZZ',
    'display': 'YYYY-MM-DD HH:mm',
    'fname': 'YYYYMMDDHHmmssZ',
}

loglevels = {
    'critical': 50,
    'error': 40,
    'warning': 30,
    'info': 20,
    'debug': 10
}

_parser = argparse.ArgumentParser(description='Parameters for NASG')
_booleanparams = {
    'regenerate': 'force downsizing images',
    'force': 'force rendering HTML',
    'nosync': 'skip sync to live server',
}

for k, v in _booleanparams.items():
    _parser.add_argument(
        '--%s' % (k),
        action='store_true',
        default=False,
        help=v
    )

_parser.add_argument(
    '--loglevel',
    default='info',
    help='change loglevel'
)

args = vars(_parser.parse_args())

loglevel = loglevels.get(args.get('loglevel'))

logger = logging.getLogger('NASG')
logger.setLevel(loglevel)
console_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)
logging.getLogger('asyncio').setLevel(loglevel)
