#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017, Peter Molnar"
__license__ = "GPLv3"
__version__ = "2.0"
__maintainer__ = "Peter Molnar"
__email__ = "hello@petermolnar.eu"
__status__ = "Production"

"""
    silo archiver module of NASG
    Copyright (C) 2017 Peter Molnar

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software Foundation,
    Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
"""

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
    cmd_prefix = 'chdir("/usr/local/lib/php/xray"); include("vendor/autoload.php"); $xray = new p3k\XRay();'

    def __init__(self, url):
        super().__init__('php')
        self.url = url
        self.target = ''
        self.cmd = (
            self.executable,
            '-r',
            '%s; echo(json_encode($xray->parse("%s")));' % (
                self.cmd_prefix,
                self.url
            )
        )

    def set_receive(self, target):
        self.cmd = (
            self.executable,
            '-r',
            '%s; echo(json_encode($xray->parse("%s")));' % (
                self.cmd_prefix,
                self.url,
                target
            )
        )
        return self

    def set_discover(self):
        self.cmd = (
            self.executable,
            '-r',
            '%s; echo(json_encode($xray->rels("%s")));' % (
                self.cmd_prefix,
                self.url,
            )
        )
        return self

    def parse(self):
        logging.debug('pulling %s with XRay', self.url)
        p = subprocess.Popen(
            self.cmd,
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
            exif['DateTimeRelease'] = "%s %s" % (
                exif.get('ReleaseDate'), exif.get('ReleaseTime')[:8])
            del(exif['ReleaseDate'])
            del(exif['ReleaseTime'])

        for k, v in exif.items():
            exif[k] = self.exifdate2iso(v)

        return exif


class BaseDB(object):
    def __init__(self, fpath):
        self.db = sqlite3.connect(fpath)
        self.db.execute('PRAGMA auto_vacuum = INCREMENTAL;')
        self.db.execute('PRAGMA journal_mode = MEMORY;')
        self.db.execute('PRAGMA temp_store = MEMORY;')
        self.db.execute('PRAGMA locking_mode = NORMAL;')
        self.db.execute('PRAGMA synchronous = FULL;')
        self.db.execute('PRAGMA encoding = "UTF-8";')

    def __exit__(self):
        self.finish()

    def finish(self):
        cursor = self.db.cursor()
        cursor.execute('PRAGMA auto_vacuum;')
        self.db.close()


class TokenDB(object):
    def __init__(self, uuid='tokens'):
        self.db = config.get('var', 'tokendb')
        self.tokens = {}
        self.refresh()

    def refresh(self):
        self.tokens = {}
        if os.path.isfile(self.db):
            with open(self.db, 'rt') as f:
                self.tokens = json.loads(f.read())

    def save(self):
        with open(self.db, 'wt') as f:
            f.write(json.dumps(
                self.tokens, indent=4, sort_keys=True
            ))

    def get_token(self, token):
        return self.tokens.get(token, None)

    def get_service(self, service):
        token = self.tokens.get(service, None)
        return token

    def set_service(self, service, tokenid):
        self.tokens.update({
            service: tokenid
        })
        self.save()

    def update_token(self,
                     token,
                     oauth_token_secret=None,
                     access_token=None,
                     access_token_secret=None,
                     verifier=None):

        t = self.tokens.get(token, {})
        if oauth_token_secret:
            t.update({
                'oauth_token_secret': oauth_token_secret
            })
        if access_token:
            t.update({
                'access_token': access_token
            })
        if access_token_secret:
            t.update({
                'access_token_secret': access_token_secret
            })
        if verifier:
            t.update({
                'verifier': verifier
            })

        self.tokens.update({
            token: t
        })
        self.save()

    def clear(self):
        self.tokens = {}
        self.save()

    def clear_service(self, service):
        t = self.tokens.get(service)
        if t:
            del(self.tokens[t])
        del(self.tokens[service])
        self.save()


class SearchDB(BaseDB):
    tmplfile = 'Search.html'

    def __init__(self):
        self.fpath = "%s" % config.get('var', 'searchdb')
        super().__init__(self.fpath)
        cursor = self.db.cursor()
        cursor.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS data USING FTS5(
                id,
                corpus,
                mtime,
                url,
                category,
                title,
                tokenize = 'porter'
            )''')
        self.db.commit()

    def __exit__(self):
        self.finish()

    def finish(self):
        cursor = self.db.cursor()
        cursor.execute('''PRAGMA auto_vacuum;''')
        self.db.close()

    def append(self, id, corpus, mtime, url, category, title):
        mtime = int(mtime)
        logging.debug("adding %s to searchdb", id)
        cursor = self.db.cursor()
        cursor.execute('''DELETE FROM data WHERE id=?''', (id,))
        cursor.execute('''INSERT OR IGNORE INTO data (id, corpus, mtime, url, category, title) VALUES (?,?,?,?,?,?);''', (
            id,
            corpus,
            mtime,
            url,
            category,
            title
        ))
        self.db.commit()

    def is_uptodate(self, fname, mtime):
        mtime = int(mtime)
        ret = {}
        cursor = self.db.cursor()
        cursor.execute('''SELECT mtime
            FROM data
            WHERE id = ? AND mtime = ?''',
                       (fname, mtime)
                       )
        rows = cursor.fetchall()

        if len(rows):
            logging.debug("%s is up to date in searchdb", fname)
            return True

        logging.debug("%s is out of  date in searchdb", fname)
        return False

    def search_by_query(self, query):
        ret = {}
        cursor = self.db.cursor()
        cursor.execute('''SELECT
            id, category, url, title, snippet(data, 1, '', '', '[...]', 24)
            FROM data
            WHERE data MATCH ?
            ORDER BY category, rank;''', (query,))
        rows = cursor.fetchall()
        for r in rows:
            r = {
                'id': r[0],
                'category': r[1],
                'url': r[2],
                'title': r[3],
                'txt': r[4],
            }

            category = r.get('category')
            if category not in ret:
                ret.update({category: {}})

            maybe_fpath = os.path.join(
                config.get('dirs', 'content'),
                category,
                "%s.*" % r.get('id')
            )
            #fpath = glob.glob(maybe_fpath).pop()
            ret.get(category).update({
                r.get('id'): {
                    #'fpath': fpath,
                    'url': r.get('url'),
                    'title': r.get('title'),
                    'txt': r.get('txt')
                }
            })
        return ret

    def cli(self, query):
        results = self.search_by_query(query)
        for c, items in sorted(results.items()):
            print("%s:" % c)
            for fname, data in sorted(items.items()):
                print("  %s" % data.get('fpath'))
                print("  %s" % data.get('url'))
                print("")

    def html(self, query):
        tmplvars = {
            'results': self.search_by_query(query),
            'term': query
        }
        return j2.get_template(self.tmplfile).render(tmplvars)


class WebmentionQueue(BaseDB):
    def __init__(self):
        self.fpath = "%s" % config.get('var', 'webmentiondb')
        super().__init__(self.fpath)
        cursor = self.db.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS  `queue` (
                `id` INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
                `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                `source` TEXT NOT NULL,
                `target` TEXT NOT NULL,
                `status` INTEGER NOT NULL DEFAULT 0,
                `mtime` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        self.db.commit()

    def __exit__(self):
        self.finish()

    def finish(self):
        self.db.close()

    def exists(self, source, target):
        logging.debug(
            'checking webmention existence for source: %s ; target: %s',
            source,
            target
        )
        cursor = self.db.cursor()
        cursor.execute(
            '''SELECT id FROM queue WHERE source=? AND target=? LIMIT 1''',
            (source,target)
        )
        rows = cursor.fetchall()
        if not rows:
            return False
        return int(rows.pop()[0])

    def queue(self, source, target):
        cursor = self.db.cursor()
        cursor.execute(
            '''INSERT INTO queue (source,target) VALUES (?,?);''', (
                source,
                target
            )
        )
        r = cursor.lastrowid
        self.db.commit()
        return r

    def requeue(self, id):
        logging.debug('setting %s webmention to undone', id)
        cursor = self.db.cursor()
        cursor.execute("UPDATE queue SET status = 0 where ID=?", (id,))
        self.db.commit()

    def get_queued(self, fname=None):
        logging.debug('getting queued webmentions for %s', fname)
        ret = []
        cursor = self.db.cursor()
        if fname:
            cursor.execute(
                '''SELECT * FROM queue WHERE target LIKE ? AND status = 0''',
                ('%' + fname + '%',)
            )
        else:
            cursor.execute(
                '''SELECT * FROM queue WHERE status = 0'''
            )

        rows = cursor.fetchall()
        for r in rows:
            ret.append({
                'id': r[0],
                'dt': r[1],
                'source': r[2],
                'target': r[3],
            })
        return ret

    def entry_done(self, id):
        logging.debug('setting %s webmention to done', id)
        cursor = self.db.cursor()
        cursor.execute("UPDATE queue SET status = 1 where ID=?", (id,))
        self.db.commit()

    def maybe_queue(self, source, target):
        exists = self.exists(source, target)
        cursor = self.db.cursor()
        if exists:
            self.requeue(exists)
            return exists

        return self.queue(source, target)

    def get_outbox(self):
        logging.debug('getting queued outgoing webmentions')
        cursor = self.db.cursor()
        ret = []
        cursor.execute(
            '''SELECT * FROM queue WHERE source LIKE ? AND status = 0''',
            ('%' + config.get('common', 'domain') + '%',)
        )
        rows = cursor.fetchall()
        for r in rows:
            ret.append({
                'id': r[0],
                'dt': r[1],
                'source': r[2],
                'target': r[3],
            })
        return ret


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

    # this should be a nice recursive function instead
    # extra site section - nope, because it relies on order
    # and author won't get appended
    for section in config.get('site', 'appendwith').split():
        SiteVars.update({section: {}})
        for o in config.options(section):
            SiteVars[section].update({o: config.get(section, o)})
        if not config.get(section, 'appendwith', fallback=False):
            continue
        # subsections
        for sub in config.get(section, 'appendwith').split():
            SiteVars[section].update({sub: {}})
            for o in config.options(sub):
                SiteVars[section][sub].update({o: config.get(sub, o)})

    tips = {}
    for s in config.sections():
        if s.startswith('tip_'):
            for key in config.options(s):
                if key not in tips:
                    tips.update({key: {}})
                tips[key].update({s.replace('tip_', ''): config.get(s, key)})

    SiteVars.update({'tips': tips})
    return SiteVars


def notify(msg):
    # telegram notification, if set
    if not config.has_section('api_telegram'):
        return

    url = "https://api.telegram.org/bot%s/sendMessage" % (
        config.get('api_telegram', 'api_token')
    )
    data = {
        'chat_id': config.get('api_telegram', 'chat_id'),
        'text': msg
    }
    # fire and forget
    try:
        requests.post(url, data=data)
    except BaseException:
        pass


ARROWFORMAT = {
    'iso': 'YYYY-MM-DDTHH:mm:ssZ',
    'display': 'YYYY-MM-DD HH:mm',
    'rcf': 'ddd, DD MMM YYYY HH:mm:ss Z',
    'twitter': 'ddd MMM DD HH:mm:ss Z YYYY'
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
