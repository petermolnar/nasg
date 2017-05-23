import os
import logging
from ruamel import yaml
from whoosh import fields
from whoosh import analysis
import jinja2
from slugify import slugify
import arrow

schema = fields.Schema(
    url=fields.ID(
        stored=True,
    ),
    title=fields.TEXT(
        stored=True,
        analyzer=analysis.FancyAnalyzer(
        )
    ),
    date=fields.DATETIME(
        stored=True,
        sortable=True
    ),
    content=fields.TEXT(
        stored=True,
        analyzer=analysis.FancyAnalyzer(
        )
    ),
    tags=fields.TEXT(
        stored=True,
        analyzer=analysis.KeywordAnalyzer(
            lowercase=True,
            commas=True
        )
    ),
    weight=fields.NUMERIC(
        sortable=True
    ),
    img=fields.TEXT(
        stored=True
    )
)

BASEDIR = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.abspath(os.path.join(BASEDIR, 'config.yml'))

with open(CONFIG, 'r') as c:
    conf = yaml.safe_load(c)
    conf['site']['author'] = conf['author']
    c.close()

secrets = os.path.abspath(os.path.join(BASEDIR, 'secret.yml'))
if os.path.isfile(secrets):
    with open(secrets, 'r') as c:
        conf['secrets'] = yaml.safe_load(c)
        c.close()

CACHEENABLED = True
REGENERATE = False
FORCEWRITE = False

ISODATE = '%Y-%m-%dT%H:%M:%S%z'

SOURCE = os.path.abspath(conf['dirs']['source']['root'])
CONTENT = os.path.abspath(conf['dirs']['source']['content'])
FONT = os.path.abspath(conf['dirs']['font'])
STHEME = os.path.abspath(conf['dirs']['source']['theme'])
SFILES = os.path.abspath(conf['dirs']['source']['files'])
TEMPLATES = os.path.abspath(conf['dirs']['source']['templates'])
COMMENTS = os.path.abspath(conf['dirs']['source']['comments'])

TARGET = os.path.abspath(conf['dirs']['target']['root'])
TTHEME = os.path.abspath(conf['dirs']['target']['theme'])
TFILES = os.path.abspath(conf['dirs']['target']['files'])
UFILES = conf['dirs']['target']['furl']

CACHE = os.path.abspath(conf['dirs']['cache'])
SEARCHDB = os.path.abspath(conf['dirs']['searchdb'])

WEBMENTIONDB = os.path.abspath(conf['webmentiondb'])
LOGDIR = os.path.abspath(conf['dirs']['log'])
GPSDIR = os.path.abspath(conf['dirs']['gps'])
TSDBDIR = os.path.abspath(conf['dirs']['tsdb'])
LOCALCOPIES = os.path.abspath(conf['dirs']['localcopies'])

lastrun = '/tmp/generator_last_run'

os.environ.setdefault('PYPANDOC_PANDOC', '/usr/bin/pandoc')

def jinja_filter_date(d, form='%Y-%m-%d %H:%m:%S'):
    if d == 'now':
        return arrow.now().strftime(form)
    if form == 'c':
        form = '%Y-%m-%dT%H:%M:%S%z'
    return d.strftime(form)

def jinja_filter_slugify(s):
    return slugify(s, only_ascii=True, lower=True)

def jinja_filter_search(s, r):
    if r in s:
        return True
    return False

jinjaldr = jinja2.FileSystemLoader(searchpath=TEMPLATES)
jinja2env = jinja2.Environment(loader=jinjaldr)

jinja2env.filters['date'] = jinja_filter_date
jinja2env.filters['search'] = jinja_filter_search
jinja2env.filters['slugify'] = jinja_filter_slugify