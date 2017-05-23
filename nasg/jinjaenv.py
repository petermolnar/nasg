import arrow
import jinja2
from slugify import slugify
import nasg.config as config

JINJA2ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(
        searchpath=config.TEMPLATES
    )
)

def jinja_filter_date(d, form='%Y-%m-%d %H:%m:%S'):
    if d == 'now':
        return arrow.now().datetime.strftime(form)
    if form == 'c':
        form = '%Y-%m-%dT%H:%M:%S%z'
    return d.strftime(form)

def jinja_filter_slugify(s):
    return slugify(s, only_ascii=True, lower=True)

def jinja_filter_search(s, r):
    if r in s:
        return True
    return False

JINJA2ENV.filters['date'] = jinja_filter_date
JINJA2ENV.filters['search'] = jinja_filter_search
JINJA2ENV.filters['slugify'] = jinja_filter_slugify