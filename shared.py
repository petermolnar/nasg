import configparser
import os
import re
import glob
import logging
import subprocess
import json
import sqlite3
import requests

from slugify import slugify
import jinja2

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


class XRay(CMDLine):
    xraypath = '/usr/local/lib/php/xray'

    def __init__(self, url):
        super().__init__('php')
        self.url = url

    def parse(self):
        cmd = (
            self.executable,
            '-r',
            '''chdir("%s"); include("vendor/autoload.php"); $xray = new p3k\XRay(); echo(json_encode($xray->parse("%s")));''' % (self.xraypath, self.url)
        )
        logging.debug('pulling %s with XRay', self.url)
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate()
        if stderr:
            logging.error("Error with XRay: %s", stderr)

        return json.loads(stdout.decode('utf-8').strip())


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


class ExifTool(CMDLine):
    def __init__(self, fpath):
        self.fpath = fpath
        super().__init__('exiftool')

    @staticmethod
    def exifdate2iso(value):
        """ converts and EXIF date string to ISO 8601 format

        :param value: EXIF date (2016:05:01 00:08:24)
        :type arg1: str
        :return: ISO 8601 string with UTC timezone 2016-05-01T00:08:24+0000
        :rtype: str
        """
        if not isinstance(value, str):
            return value
        match = REGEX['exifdate'].match(value)
        if not match:
            return value
        return "%s-%s-%sT%s+0000" % (
            match.group('year'),
            match.group('month'),
            match.group('day'),
            match.group('time')
        )

    def read(self):
        cmd = (
            self.executable,
            '-sort',
            '-json',
            '-MIMEType',
            '-FileType',
            '-FileName',
            '-ModifyDate',
            '-CreateDate',
            '-DateTimeOriginal',
            '-ImageHeight',
            '-ImageWidth',
            '-Aperture',
            '-FOV',
            '-ISO',
            '-FocalLength',
            '-FNumber',
            '-FocalLengthIn35mmFormat',
            '-ExposureTime',
            '-Copyright',
            '-Artist',
            '-Model',
            '-GPSLongitude#',
            '-GPSLatitude#',
            '-LensID',
            '-LensSpec',
            '-Lens',
            '-ReleaseDate',
            '-Description',
            '-Headline',
            '-HierarchicalSubject',
            self.fpath
        )

        logging.debug('reading EXIF from %s', self.fpath)
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate()
        if stderr:
            logging.error("Error reading EXIF:\n\t%s\n\t%s", cmd, stderr)

        exif = json.loads(stdout.decode('utf-8').strip()).pop()
        if 'ReleaseDate' in exif and 'ReleaseTime' in exif:
            exif['DateTimeRelease'] = "%s %s" % (exif.get('ReleaseDate'), exif.get('ReleaseTime')[:8])
            del(exif['ReleaseDate'])
            del(exif['ReleaseTime'])

        for k, v in exif.items():
            exif[k] = self.exifdate2iso(v)

        return exif

def __expandconfig():
    c = configparser.ConfigParser(
        interpolation=configparser.ExtendedInterpolation(),
        allow_no_value=True
    )
    c.read('config.ini')
    for s in c.sections():
        for o in c.options(s):
            curr = c.get(s, o)
            if 'photo' == s and 'regex' == o:
                REGEX.update({'photo': re.compile(curr)})
            c.set(s, o, os.path.expanduser(curr))
    return c

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

def __setup_sitevars():
    SiteVars = {}
    section = 'site'
    for o in config.options(section):
        SiteVars.update({o: config.get(section, o)})

    # add site author
    section = 'author'
    SiteVars.update({section: {}})
    for o in config.options(section):
        SiteVars[section].update({o: config.get(section, o)})

    # add extra sections to author
    for sub in config.get('author', 'appendwith').split():
        SiteVars[section].update({sub: {}})
        for o in config.options(sub):
            SiteVars[section][sub].update({o: config.get(sub, o)})

    # push the whole thing into cache
    return SiteVars


def notify(msg):
    # telegram notification, if set
    if not shared.config.has_section('api_telegram'):
        return

    url = "https://api.telegram.org/bot%s/sendMessage" % (
        shared.config.get('api_telegram', 'api_token')
    )
    data = {
        'chat_id': shared.config.get('api_telegram', 'chat_id'),
        'text': msg
    }
    # fire and forget
    try:
        requests.post(url, data=data)
    except:
        pass


ARROWFORMAT = {
    'iso': 'YYYY-MM-DDTHH:mm:ssZ',
    'display': 'YYYY-MM-DD HH:mm',
    'rcf': 'ddd, DD MMM YYYY HH:mm:ss Z'
}

LLEVEL = {
    'critical': 50,
    'error': 40,
    'warning': 30,
    'info': 20,
    'debug': 10
}

REGEX = {
    'exifdate': re.compile(
        r'^(?P<year>[0-9]{4}):(?P<month>[0-9]{2}):(?P<day>[0-9]{2})\s+'
        r'(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})$'
    ),
    'cleanurl': re.compile(r"^https?://(?:www)?"),
    'urls': re.compile(
        r'\s+https?\:\/\/?[a-zA-Z0-9\.\/\?\:@\-_=#]+'
        r'\.[a-zA-Z0-9\.\/\?\:@\-_=#]*'
    ),
    'mdimg': re.compile(
        r'(?P<shortcode>\!\[(?P<alt>[^\]]+)\]\((?P<fname>[^\s]+)'
        r'(?:\s[\'\"](?P<title>[^\"\']+)[\'\"])?\)(?:\{(?P<css>[^\}]+)\})?)',
        re.IGNORECASE
    )
}

config = __expandconfig()

j2 = jinja2.Environment(
    loader=jinja2.FileSystemLoader(
        searchpath=config.get('dirs', 'tmpl')
    ),
    lstrip_blocks=True
)

site = __setup_sitevars()
