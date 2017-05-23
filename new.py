#!/home/petermolnar.net/.venv/bin/python3.5

"""Usage: new.py [-h] [-t TAGS] [-d DATE] [-s SLUG] [-l TITLE] [-b BOOKMARK] [-r REPLY] [-p REPOST] [-c CONTENT] [-u SUMMARY] [-i REDIRECT] [-a CATEGORY]

-h --help                 show this
-t --tags TAGS            ';' separated, quoted list of tags
-d --date DATE            YYYY-mm-ddTHH:MM:SS+TZTZ formatted date, if not now
-s --slug SLUG            slug (normally autogenerated from title or pubdate)
-l --title TITLE          title of new entry
-b --bookmark BOOKMARK    URL to bookmark
-r --reply REPLY          URL to reply to
-p --repost REPOST        URL to repost
-c --content CONTENT      content of entry
-u --summary SUMMARY      summary of entry
-i --redirect REDIRECT    ';' separated, quoted list of redirects
-a --category CATEGORY    to put the content in this category
"""

import os
import sys
import datetime
import calendar
import logging
import json
import glob
import iso8601
import pytz
from docopt import docopt
from slugify import slugify
from ruamel import yaml
import singular

class ContentCreator(object):
    def __init__(
            self,
            category='note',
            tags=[],
            date='',
            slug='',
            title='',
            bookmark='',
            reply='',
            repost='',
            content='',
            summary='',
            redirect=[]
    ):
        self.category = category

        if date:
            self.date = iso8601.parse_date(date)
        else:
            self.date = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
        self.time = calendar.timegm(self.date.timetuple())

        self.title = title

        if slug:
            self.slug = slug
        elif title:
            self.slug = slugify(title, only_ascii=True, lower=True)
        else:
            self.slug = singular.SingularHandler.baseN(self.time)

        self.tags = tags
        self.bookmark = bookmark
        self.reply = reply
        self.repost = repost
        if content:
            self.content = content
        else:
            self.content = ''
        self.summary = summary
        self.redirect = redirect

        self._makeyaml()
        self._write()


    def _makeyaml(self):
        self.yaml = {
            'published': self.date.strftime("%Y-%m-%dT%H:%M:%S%z")
        }

        if self.title:
            self.yaml['title'] = self.title

        if self.tags:
            self.yaml['tags'] = self.tags

        if self.bookmark:
            self.yaml['bookmark-of'] = self.bookmark

        if self.repost:
            self.yaml['repost-of'] = self.repost

        if self.reply:
            self.yaml['in-reply-to'] = self.reply

        if self.summary:
            self.yaml['summary'] = self.summary

        if self.redirect:
            self.yaml['redirect'] = self.redirect

    def _write(self):
        fdir = os.path.join(glob.CONTENT, self.category)
        if not os.path.isdir(fdir):
            sys.exit("there is no category %s" % (self.category))

        self.fpath = os.path.join(glob.CONTENT, self.category, "%s.md" % (self.slug))
        self.out = "---\n" + yaml.dump(self.yaml, Dumper=yaml.RoundTripDumper) + "---\n\n" + self.content
        with open(self.fpath, "w") as archive:
            logging.info("writing %s", self.fpath)
            logging.info("contents: %s", self.out)
            archive.write(self.out)
            archive.close()


class ParseCMDLine(object):
    def __init__(self, arguments):
        for x in ['--redirect', '--tags']:
            if x in arguments and arguments[x]:
                arguments[x] = arguments[x].split(";")

        self.entry = ContentCreator(
            category=arguments['--category'],
            tags=arguments['--tags'],
            date=arguments['--date'],
            slug=arguments['--slug'],
            title=arguments['--title'],
            bookmark=arguments['--bookmark'],
            reply=arguments['--reply'],
            repost=arguments['--repost'],
            content=arguments['--content'],
            summary=arguments['--summary'],
            redirect=arguments['--redirect']
        )

if __name__ == '__main__':
    args = docopt(__doc__, version='new.py 0.1')

    with open(os.path.join(glob.CACHE, "slugs.json")) as sf:
        slugs = json.loads(sf.read())
        sf.close()

    if not args['--category']:
        c = 'note'
        args['--category'] = input('Category [%s]: ' % (c)) or c

    if not args['--date']:
        d = datetime.datetime.utcnow().replace(tzinfo=pytz.utc).strftime("%Y-%m-%dT%H:%M:%S%z")
        args['--date'] = input('Date [%s]' % (d)) or d

    if not args['--title']:
        args['--title'] = input('Title []:') or ''

    if not args['--tags']:
        args['--tags'] = input('Tags (separated by ;, no whitespace) []:') or []

    if not args['--bookmark']:
        args['--bookmark'] = input('Bookmark of URL []:') or ''

    if not args['--reply']:
        args['--reply'] = input('Reply to URL []:') or ''

    if not args['--repost']:
        args['--repost'] = input('Repost of URL []:') or ''

    if not args['--slug']:
        if args['--title']:
            slug = slugify(args['--title'], only_ascii=True, lower=True)
        elif args['--bookmark']:
            slug = slugify("re: %s" % (args['--bookmark']), only_ascii=True, lower=True)
        elif args['--reply']:
            slug = slugify("re: %s" % (args['--reply']), only_ascii=True, lower=True)
        elif args['--repost']:
            slug = slugify("re: %s" % (args['--repost']), only_ascii=True, lower=True)
        else:
            d = iso8601.parse_date(args['--date'])
            t = calendar.timegm(d.timetuple())
            slug = singular.SingularHandler.baseN(t)
        args['--slug'] = input('Slug [%s]:' % (slug)) or slug

        if args['--slug'] in slugs:
            logging.warning("This slug already exists: %s", args['--slug'])
            slugbase = args['--slug']
            inc = 1
            while args['--slug'] in slugs:
                args['--slug'] = "%s-%d" % (slugbase, inc)
                inc = inc+1
            logging.warning("Using %s as slug", args['--slug'])

    if not args['--summary']:
        args['--summary'] = input('Summary []:') or ''

    if not args['--content']:
        args['--content'] = input('Content []:') or ''

    if not args['--redirect']:
        args['--reditect'] = input('Additional slugs (separated by ;, no whitespace) []:') or []

    p = ParseCMDLine(args)