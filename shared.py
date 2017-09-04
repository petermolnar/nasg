import configparser
import os
import re
import glob
import logging
import subprocess
import json
import requests
from urllib.parse import urlparse, urlunparse

from whoosh import fields
from whoosh import analysis
from slugify import slugify

LLEVEL = {
    'critical': 50,
    'error': 40,
    'warning': 30,
    'info': 20,
    'debug': 10
}


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
    config.set('target', 'commentsdir', os.path.join(
        config.get('target', 'builddir'),
        config.get('site', 'commentspath'),
    ))
    return config


def baseN(num, b=36, numerals="0123456789abcdefghijklmnopqrstuvwxyz"):
    """ Used to create short, lowercase slug for a number (an epoch) passed """
    num = int(num)
    return ((num == 0) and numerals[0]) or (
        baseN(
            num // b,
            b,
            numerals
        ).lstrip(numerals[0]) + numerals[num % b]
    )

def slugfname(url):
    return "%s" % slugify(
        re.sub(r"^https?://(?:www)?", "", url),
        only_ascii=True,
        lower=True
    )[:200]

ARROWISO = 'YYYY-MM-DDTHH:mm:ssZ'
STRFISO = '%Y-%m-%dT%H:%M:%S%z'

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
    category=fields.TEXT(
        stored=True,
    ),
    date=fields.DATETIME(
        stored=True,
        sortable=True
    ),
    title=fields.TEXT(
        stored=True,
        analyzer=analysis.FancyAnalyzer()
    ),
    weight=fields.NUMERIC(
        sortable=True
    ),
    img=fields.TEXT(
        stored=True
    ),
    content=fields.TEXT(
        stored=True,
        analyzer=analysis.FancyAnalyzer()
    ),
    fuzzy=fields.NGRAMWORDS(
        tokenizer=analysis.NgramTokenizer(4)
    ),
    mtime=fields.NUMERIC(
        stored=True
    )
    #slug=fields.NGRAMWORDS(
        #tokenizer=analysis.NgramTokenizer(4)
    #),
    #reactions=fields.NGRAMWORDS(
        #tokenizer=analysis.NgramTokenizer(4)
    #),
    #tags=fields.TEXT(
        #stored=False,
        #analyzer=analysis.KeywordAnalyzer(
            #lowercase=True,
            #commas=True
        #),
    #),
)

config = configparser.ConfigParser(
    interpolation=configparser.ExtendedInterpolation(),
    allow_no_value=True
)
config.read('config.ini')
config = __expandconfig(config)

class CMDLine(object):
    def __init__(self, executable):
        self.executable = self._which(executable)
        if self.executable is None:
            raise OSError('No %s found in PATH!' % executable)
            return


    @staticmethod
    def _which(name):
        for d in os.environ['PATH'].split(':'):
            which = glob.glob(os.path.join(d, name), recursive=True)
            if which:
                return which.pop()
        return None


    def __enter__(self):
        self.process = subprocess.Popen(
            [self.executable, "-stay_open", "True",  "-@", "-"],
            universal_newlines=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return self


    def  __exit__(self, exc_type, exc_value, traceback):
        self.process.stdin.write("-stay_open\nFalse\n")
        self.process.stdin.flush()


    def execute(self, *args):
        args = args + ("-execute\n",)
        self.process.stdin.write(str.join("\n", args))
        self.process.stdin.flush()
        output = ""
        fd = self.process.stdout.fileno()
        while not output.endswith(self.sentinel):
            output += os.read(fd, 4096).decode('utf-8', errors='ignore')
        return output[:-len(self.sentinel)]


class Pandoc(CMDLine):
    """ Pandoc command line call with piped in- and output """

    def __init__(self, md2html=True):
        super().__init__('pandoc')
        if True == md2html:
            self.i = "markdown+" + "+".join([
                'backtick_code_blocks',
                'auto_identifiers',
                'fenced_code_attributes',
                'definition_lists',
                'grid_tables',
                'pipe_tables',
                'strikeout',
                'superscript',
                'subscript',
                'markdown_in_html_blocks',
                'shortcut_reference_links',
                'autolink_bare_uris',
                'raw_html',
                'link_attributes',
                'header_attributes',
                'footnotes',
            ])
            self.o = 'html5'
        elif 'plain' == md2html:
            self.i = "markdown+" + "+".join([
                'backtick_code_blocks',
                'auto_identifiers',
                'fenced_code_attributes',
                'definition_lists',
                'grid_tables',
                'pipe_tables',
                'strikeout',
                'superscript',
                'subscript',
                'markdown_in_html_blocks',
                'shortcut_reference_links',
                'autolink_bare_uris',
                'raw_html',
                'link_attributes',
                'header_attributes',
                'footnotes',
            ])
            self.o = "plain"
        else:
            self.o = "markdown-" + "-".join([
                'raw_html',
                'native_divs',
                'native_spans',
            ])
            self.i = 'html'


    def convert(self, text):
        cmd = (
            self.executable,
            '-o-',
            '--from=%s' % self.i,
            '--to=%s' % self.o
        )
        logging.debug('converting string with Pandoc')
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate(input=text.encode())
        if stderr:
            logging.error(
                "Error during pandoc covert:\n\t%s\n\t%s",
                cmd,
                stderr
            )
        return stdout.decode('utf-8').strip()


class HeadlessChromium(CMDLine):
    def __init__(self, url):
        super().__init__('chromium-browser')
        self.url = url

    def get(self):
        cmd = (
            self.executable,
            '--headless',
            '--disable-gpu',
            '--disable-preconnect',
            '--dump-dom',
            '--timeout 60',
            '--save-page-as-mhtml',
            "%s" % self.url
        )
        logging.debug('getting URL %s with headless chrome', self.url)
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate()
        if stderr:
            logging.error(
                "Error getting URL:\n\t%s\n\t%s",
                cmd,
                stderr
            )
        return stdout.decode('utf-8').strip()


class wget(CMDLine):
    def __init__(self, url, dirname=None):
        super().__init__('wget')
        self.url = url
        self.slug = dirname or slugfname(self.url)
        self.saveto = os.path.join(
            config.get('source', 'offlinecopiesdir'),
            self.slug
        )

    def archive(self):
        cmd = (
            self.executable,
            '-e',
            'robots=off',
            '--timeout=360',
            '--no-clobber',
            '--no-directories',
            '--adjust-extension',
            '--span-hosts',
            '--wait=1',
            '--random-wait',
            '--convert-links',
            #'--backup-converted',
            '--page-requisites',
            '--directory-prefix=%s' % self.saveto,
            "%s" % self.url
        )
        logging.debug('getting URL %s with wget', self.url)
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate()
        if stderr:
            logging.error(
                "Error getting URL:\n\t%s\n\t%s",
                cmd,
                stderr
            )
        return stdout.decode('utf-8').strip()

def find_realurl(url):
    headers = requests.utils.default_headers()
    headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
    })

    try:
        r = requests.get(
            url,
            allow_redirects=True,
            timeout=60,
            headers=headers
        )
    except Exception as e:
        logging.error('getting real url failed: %s', e)
        return (None, 400)

    finalurl = list(urlparse(r.url))
    finalurl[4] = '&'.join(
        [x for x in finalurl[4].split('&') if not x.startswith('utm_')])
    finalurl = urlunparse(finalurl)

    return (finalurl, r.status_code)

def find_archiveorgurl(url):
    url, status = find_realurl(url)
    if status == requests.codes.ok:
        return url

    try:
        a = requests.get(
            "http://archive.org/wayback/available?url=%s" % url,
        )
    except Exception as e:
        logging.error('Failed to fetch archive.org availability for %s' % url)
        return None

    if not a:
        logging.error('empty archive.org availability for %s' % url)
        return None

    try:
        a = json.loads(a.text)
        aurl = a.get(
            'archived_snapshots', {}
        ).get(
            'closest', {}
        ).get(
            'url', None
        )
        if aurl:
            logging.debug("found %s in archive.org for %s", aurl, url)
            return aurl
    except Exception as e:
        logging.error("archive.org parsing failed: %s", e)

    return None
