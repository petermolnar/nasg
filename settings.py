import os
import re
import argparse
import logging

base = os.path.abspath(os.path.expanduser('~/Projects/petermolnar.net'))

site = {
    'title': 'Peter Molnar',
    'url': 'https://petermolnar.net',
    'domain': 'petermolnar.net',
    'pagination': 12,
    'on_front': [
        'article',
        'photo',
        'journal'
    ],
    'licence': 'by-nc-nd',
    'piwik': {
        'domain': 'stats.petermolnar.net',
        'id': 1
    }
}

categorydisplay = {
    'article': 'flat',
    'journal': 'flat',
    'photo': 'gallery',
}

licence = {
    'article': 'by',
    'journal': 'by-nc',
}

labels = {
    'tiptext': {
        'photo':
            "Did you like this photo?<br />"
            "Leave a tip! If you're interested in prints, please get in touch.",
        'article':
            "Did you find this article useful?<br />"
            "Support me, so I can write more like this.<br />"
            "If you want my help for your project, get in touch.",
        'journal':
            "Did you like this entry?<br />"
            "Encourage me to write more of them.",
    }
}

meta = {
    'webmention': 'https://webmention.io/petermolnar.net/webmention',
    'pingback': 'https://webmention.io/petermolnar.net/xmlrpc',
    'hub': 'https://petermolnar.superfeedr.com/'
}

author = {
    'name': 'Peter Molnar',
    'email': 'mail@petermolnar.net',
    'url': 'https://petermolnar.net/',
    'avatar': 'https://petermolnar.net/molnar_peter_avatar.jpg',
    'gpg': 'https://petermolnar.net/pgp.asc',
    'cv': 'https://petermolnar.net/about.html',
    'xmpp': 'mail@petermolnar.net',
    'flickr': 'petermolnareu',
    'github': 'petermolnar',
    'twitter': 'petermolnar'
}

paths = {
    'content': os.path.join(base, 'content'),
    'tmpl': os.path.join(base, 'nasg', 'templates'),
    'watermark': os.path.join(base, 'nasg', 'templates', 'watermark.png'),
    'build': os.path.join(base, 'www'),
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

tips = [
    {
        'name': 'paypal',
        'label': 'PayPal',
        'value': '£3',
        'url': 'https://paypal.me/petermolnar/3GBP',
    },
    {
        'name': 'monzo',
        'label': 'Monzo (UK)',
        'value': '£3',
        'url': 'https://monzo.me/petermolnar/3',
    },
]

dateformat = {
    'iso': 'YYYY-MM-DDTHH:mm:ssZZ',
    'display': 'YYYY-MM-DD HH:mm',
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

# remove the rest of the potential loggers
while len(logging.root.handlers) > 0:
    logging.root.removeHandler(logging.root.handlers[-1])

logging.basicConfig(
    level=loglevels[args.get('loglevel')],
    format='%(asctime)s - %(levelname)s - %(message)s'
)
