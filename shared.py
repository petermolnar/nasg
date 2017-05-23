import configparser
import os
from whoosh import fields
from whoosh import analysis
import re

def __expandconfig(config):
    """ add the dirs to the config automatically """
    basepath = os.path.expanduser(config.get('common','base'))
    config.set('common', 'basedir', basepath)
    for section in ['source', 'target']:
        for option in config.options(section):
            opt = config.get(section, option)
            config.set(section, "%sdir" % option, os.path.join(basepath,opt))
    config.set('target', 'filesdir', os.path.join(
        config.get('target', 'builddir'),
        config.get('source', 'files'),
    ))
    return config

URLREGEX = re.compile(
    r'\s+https?\:\/\/?[a-zA-Z0-9\.\/\?\:@\-_=#]+'
    r'\.[a-zA-Z0-9\.\/\?\:@\-_=#]*'
)

EXIFREXEG = re.compile(
    r'^(?P<year>[0-9]{4}):(?P<month>[0-9]{2}):(?P<day>[0-9]{2})\s+'
    r'(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})$'
)

MDIMGREGEX = re.compile(
    r'(!\[(.*)\]\((?:\/(?:files|cache)'
    r'(?:\/[0-9]{4}\/[0-9]{2})?\/(.*\.(?:jpe?g|png|gif)))'
    r'(?:\s+[\'\"]?(.*?)[\'\"]?)?\)(?:\{(.*?)\})?)'
, re.IGNORECASE)

schema = fields.Schema(
    url=fields.ID(
        stored=True,
        unique=True
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

config = configparser.ConfigParser(
    interpolation=configparser.ExtendedInterpolation(),
    allow_no_value=True
)
config.read('config.ini')
config = __expandconfig(config)
