import glob
import asyncio
import uvloop
import os
from sanic import Sanic
import sanic.response
from sanic.log import log as logging
from whoosh import index, qparser
import pynmea2
import datetime
import pytz
import re
import validators
import requests
import pypandoc
import hashlib
import time
from webmentiontools import urlinfo
import json
import calendar
import mimetypes
import singular
import urllib.parse
from ruamel import yaml
from slugify import slugify
import smtplib
import iso8601
import csv
import shutil
import collections
from git import Repo, Actor
import frontmatter
#import gzip
import arrow

class ToEmail(object):
    def __init__(self, webmention):
        self.webmention = webmention
        self.set_html()
        self.set_headers()


    def set_html(self):
        for authormeta in ['email', 'name', 'url']:
            if not authormeta in self.webmention['author']:
                self.webmention['author'][authormeta] = ''

        html = """
            <html>
                <head></head>
                <body>
                <h1>
                    New %s
                </h1>
                <dl>
                    <dt>From</dt>
                    <dd>
                        <a href="%s">%s</a><br />
                        <a href="mailto:%s">%s</a>
                    </dd>
                    <dt>Source</dt>
                    <dd><a href="%s">%s</a></dd>
                    <dt>Target</dt>
                    <dd><a href="%s">%s</a></dd>
                </dl>
                    %s
                </body>
            </html>""" % (
                self.webmention['type'],
                self.webmention['author']['url'],
                self.webmention['author']['name'],
                self.webmention['author']['email'],
                self.webmention['author']['email'],
                self.webmention['source'],
                self.webmention['source'],
                self.webmention['target'],
                self.webmention['target'],
                pypandoc.convert_text(
                    self.webmention['content'],
                    to='html5',
                    format="markdown+" + "+".join([
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
                )
            )
        self.html = html

    def set_headers(self):
        """ Create and send email from a parsed webmention """

        self.headers = {
            'Content-Type': 'text/html; charset=utf-8',
            'Content-Disposition': 'inline',
            'Content-Transfer-Encoding': '8bit',
            'Date': self.webmention['date'].strftime('%a, %d %b %Y  %H:%M:%S %Z'),
            'X-WEBMENTION-SOURCE': self.webmention['source'],
            'X-WEBMENTION-TARGET': self.webmention['target'],
            'From': glob.conf['from']['address'],
            'To': glob.conf['to']['address'],
            'Subject': "[webmention] from %s to %s" % ( self.webmention['source'], self.webmention['target'] ),
        }


    def send(self):
        msg = ''
        for key, value in self.headers.items():
            msg += "%s: %s\n" % ( key, value )

        msg += "\n%s\n"  % self.html

        try:
            s = smtplib.SMTP( glob.conf['smtp']['host'], glob.conf['smtp']['port'] )
            if glob.conf['smtp']['tls']:
                s.ehlo()
                s.starttls()
                s.ehlo()

            if glob.conf['smtp']['username'] and glob.conf['smtp']['password']:
                s.login(glob.conf['smtp']['username'], glob.conf['smtp']['password'])

            s.sendmail( self.headers['From'], [ self.headers['To'] ], msg.encode("utf8") )
            s.quit()
        except:
            print("Unexpected error:", sys.exc_info()[0])
            raise


class MicropubHandler(object):
    def __init__(self, request):
        self.request = request
        self.response = sanic.response.text("Unhandled error", status=500)

        self.slug = ''
        self.content = ''
        self.category = 'note'
        self.meta = {}
        self.dt = datetime.datetime.now().replace(tzinfo=pytz.utc)

        logging.debug("incoming micropub request:")
        logging.debug(self.request.body)

        logging.debug("** args:")
        logging.debug(self.request.args)

        logging.debug("** query string:")
        logging.debug(self.request.query_string)

        logging.debug("** headers:")
        logging.debug(self.request.headers)

        with open(os.path.join(glob.CACHE, "tags.json"), "r") as db:
            self.existing_tags = json.loads(db.read())
            db.close()

        self._parse()

    def _verify(self):
        if 'q' in self.request.args:
            if 'config' in self.request.args['q']:
                self.response = sanic.response.json({
                    'tags': self.existing_tags
                }, status=200)
                return
            if 'syndicate-to' in self.request.args['q']:
                self.response = sanic.response.json({
                    'syndicate-to': []
                }, status=200)
                return

        if not 'access_token' in self.request.form:
            self.response = sanic.response.text("Mising access token", status=401)
            return

        token = self.request.form.get('access_token')

        verify = requests.get(
            'https://tokens.indieauth.com/token',
            allow_redirects=False,
            timeout=10,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Authorization': 'Bearer %s' % (token)
            });

        if verify.status_code  != requests.codes.ok:
            self.response = sanic.response.text("Could not verify access token", status=500)
            return False

        response = urllib.parse.parse_qs(verify.text)
        logging.debug(response)
        if 'scope' not in response or 'me' not in response:
            self.response = sanic.response.text("Could not verify access token", status=401)
            return False

        if '%s/' % (glob.conf['site']['url'].rstrip()) not in response['me']:
            self.response = sanic.response.text("You can't post to this domain.", status=401)
            return False

        if 'post' not in response['scope'] and 'create' not in response['scope']:
            self.response = sanic.response.text("Invalid scope", status=401)
            return False

        return True

    def _parse(self):
        if not self._verify():
            return

        if len(self.request.files):
            self.response = sanic.response.text("File handling is not yet done", status=501)
            return
            #for ffield in self.request.files.keys():
                #logging.info("got file field: %s" % ffield)
                #f = self.request.files.get(ffield)
                #logging.info("mime is: %s" % f.type)
                #logging.info("ext should be: %s" % mimetypes.guess_extension(f.type))

                ##f.body
                ##f.type
                ##logging.info( f )

        self.meta['published'] = self.dt.strftime('%Y-%m-%dT%H:%M:%S%z')

        slug = None

        if 'content' in self.request.form and len(self.request.form.get('content')):
            self.content = self.request.form.get('content')

        if 'summary' in self.request.form and len(self.request.form.get('summary')):
            self.meta['summary'] = self.request.form.get('summary')

        if 'slug' in self.request.form and len(self.request.form.get('slug')):
            slug = self.request.form.get('slug')

        if 'name' in self.request.form and len(self.request.form.get('name')):
            self.meta['title'] = self.request.form.get('name')
            if not slug:
                slug = self.meta['title']

        if 'in-reply-to' in self.request.form and len(self.request.form.get('in-reply-to')):
            self.meta['in-reply-to'] = self.request.form.get('in-reply-to')
            if not slug:
                slug = 're: %s', self.meta['in-reply-to']

        if 'repost-of' in self.request.form and len(self.request.form.get('repost-of')):
            self.meta['repost-of'] = self.request.form.get('repost-of')
            category = 'bookmark'
            if not slug:
                slug = '%s', self.meta['repost-of']

        if 'bookmark-of' in self.request.form and len(self.request.form.get('bookmark-of')):
            self.meta['bookmark-of'] = self.request.form.get('bookmark-of')
            self.category = 'bookmark'
            if not slug:
                slug = '%s', self.meta['bookmark-of']

        if 'category[]' in self.request.form:
            self.meta['tags'] = list(self.request.form['category[]'])
            if 'summary' in self.meta and ('IT' in self.meta['tags'] or 'it' in self.meta['tags']):
                self.category = 'article'
            elif 'summary' in self.meta and ('journal' in self.meta['tags'] or 'journal' in self.meta['tags']):
                self.category = 'journal'

        if not slug:
            slug = singular.SingularHandler.baseN(calendar.timegm(self.dt.timetuple()))

        self.slug = slugify(slug, only_ascii=True, lower=True)
        self._write()

    def _write(self):
        fpath = os.path.join(glob.CONTENT, self.category,  '%s.md' % (self.slug))
        if os.path.isfile(fpath):
            self.response = sanic.response.text("Update handling is not yet done", status=501)
            return

        logfile = os.path.join(glob.LOGDIR, "micropub-%s.log" % (self.dt.strftime("%Y-%m")))
        with open (logfile, 'a') as micropublog:
            logging.debug("logging micropub request")
            micropublog.write("%s %s\n" % (self.dt.strftime('%Y-%m-%dT%H:%M:%S%z'), fpath))
            micropublog.close()

        with open (fpath, 'w') as mpf:
            logging.info("writing file to: %s", fpath)
            out = "---\n" + yaml.dump(self.meta, Dumper=yaml.RoundTripDumper, allow_unicode=True, indent=4) + "---\n\n" + self.content
            mpf.write(out)
            mpf.close()

        self._git(fpath)

        logging.info("trying to open and parse the received post")
        post = singular.ArticleHandler(fpath, category=self.category)
        post.write()
        post.pings()

        self.response = sanic.response.text(
            "Post created",
            status = 201,
            headers = {
                'Location': "%s/%s/" % (glob.conf['site']['url'], self.slug)
            }
        )

        return

    def _git(self, fpath):
        logging.info("committing to git")
        repo = Repo(glob.CONTENT)
        author = Actor(glob.conf['author']['name'], glob.conf['author']['email'])
        index = repo.index
        newfile = fpath.replace(glob.CONTENT, '').lstrip('/')
        index.add([newfile])
        message =  'new content via micropub: %s' % (newfile)
        index.commit(message, author=author, committer=author)


class SearchHandler(object):
    def __init__ (self, query):
        self.query = query
        self.response = sanic.response.text("You seem to have forgot to enter what you want to search for. Please try again.", status=400)

        if not query:
            return

        self._tmpl = glob.jinja2env.get_template('searchresults.html')
        self._ix = index.open_dir(glob.SEARCHDB)
        self._parse()

    def _parse(self):
        self.query = self.query.replace('+', ' AND ')
        self.query = self.query.replace(' -', ' NOT ')
        qp = qparser.MultifieldParser(
            ["title", "content", "tags"],
            schema = glob.schema
        )
        q = qp.parse(self.query)
        r = self._ix.searcher().search(q, sortedby="weight", limit=100)
        logging.info("results for '%s': %i", self.query, len(r))
        results = []
        for result in r:
            res = {
                'title': result['title'],
                'url': result['url'],
                'highlight': result.highlights("content"),
            }

            if 'img' in result:
                res['img'] = result['img']

            results.append(res)

        tvars = {
            'term': self.query,
            'site': glob.conf['site'],
            'posts': results,
            'taxonomy': {}
        }
        logging.info("collected %i results to render", len(results))
        html = self._tmpl.render(tvars)
        self.response = sanic.response.html(html, status=200)


class WebmentionHandler(object):
    def __init__ ( self, source, target ):
        self.source = source
        self.target = target
        self.time = arrow.utcnow().timestamp
        logging.debug("validating: from: %s; to: %s" % (self.source, self.target) )
        self.response = sanic.response.json({
            'status': 'ok','msg': 'accepted',
        }, 200)
        self._validate()
        self._parse()
        self._archive()
        self._send()

    def _validate(self):
        if not validators.url(self.source):
            self.response = sanic.response.json({
                'status': 'error','msg': '"souce" parameter is an invalid URL',
            }, 400)
            return

        if not validators.url(self.target):
            self.response = sanic.response.json({
                'status': 'error','msg': '"target" parameter is an invalid URL',
            }, 400)
            return

        _target = urllib.parse.urlparse(self.target)
        _target_domain = '{uri.netloc}'.format(uri=_target)

        if not _target_domain in glob.conf['accept_domains']:
            self.response = sanic.response.json({
                'status': 'error',
                'msg': "%s' is not in the list of allowed domains" % (
                    _target_domain
                )
            }, 400)
            return

        _source = urllib.parse.urlparse(self.source)
        _source_domain = '{uri.netloc}'.format(uri=_source)

        if _source_domain == _target_domain and not glob.conf['allow_selfmention']:
                self.response = sanic.response.json({
                    'status': 'error',
                    'msg': "selfpings are disabled"
                }, 400)
                return

        return

    def _parse(self):
        if self.response.status != 200:
            return

        self._log()
        self._source = urlinfo.UrlInfo(self.source)
        if self._source.error:
            logging.warning( "couldn't fetch %s; dropping webmention" % (self.source))
            return
        self.source = self._source.realurl
        if not self._source.linksTo(self.target):
            logging.warning( "%s is not linking to %s; dropping webmention" % (self.source, self.target))
            return

        self._target = urlinfo.UrlInfo(self.target)
        if self._target.error:
            logging.warning( "couldn't fetch %s; dropping webmention" % (self.target))
            return
        self.target = self._target.realurl

        self.webmention = {
            'author': self._source.author(),
            'type': self._source.relationType(),
            'target': self.target,
            'source': self.source,
            'date': arrow.get(self._source.pubDate()),
            'content': pypandoc.convert_text(
                self._source.content(),
                to="markdown-" + "-".join([
                    'raw_html',
                    'native_divs',
                    'native_spans',
                ]),
                format='html'
            )
        }


    def _send(self):
        if self.response.status != 200:
            return

        m = ToEmail(self.webmention)
        m.send()


    def _archive(self):
        if self.response.status != 200:
            return

        fbase = self.webmention['date'].format('YYYY-MM-DD-HH-mm-ss')
        fpath = self._archive_name(fbase)

        archive = dict(self.webmention)
        archive['date'] = archive['date'].format('YYYY-MM-DDTHH.mm.ssZ')
        content = archive['content']
        del(archive['content'])

        with open (fpath, 'w') as f:
            logging.info("writing file to: %s", fpath)
            out = "---\n" + yaml.dump(
                archive,
                Dumper=yaml.RoundTripDumper,
                allow_unicode=True,
                indent=4
            ) + "---\n\n" + content
            f.write(out)
            f.close()

    def _verify_archive(self, p):
        archive = frontmatter.load(p)

        if 'target' not in archive.metadata:
            logging.warning('missing target')
            return False

        if 'source' not in archive.metadata:
            logging.warning('missing source')
            return False

        if 'date' not in archive.metadata:
            logging.warning('missing date')
            return False

        if archive.metadata['target'] != self.webmention['target']:
            logging.warning('target different')
            return False

        if archive.metadata['source'] != self.webmention['source']:
            logging.warning('source different')
            return False

        d = arrow.get(archive.metadata['date'])

        if d.timestamp != self.webmention['date'].timestamp:
            logging.warning('date different')
            return False

        # overwrite
        return True

    def _archive_name(self, archive, ext='.md'):
        p = os.path.join(glob.COMMENTS, "%s%s" % (archive, ext))

        if not os.path.exists(p):
            logging.debug("%s doesn't exits yet" % p)
            return p

        logging.debug("%s exists, checking for update" % p)
        if self._verify_archive(p):
            return p

        # another comment with the exact same second? wy not.
        names = [x for x in os.listdir(glob.COMMENTS) if x.startswith(archive)]
        suffixes = [x.replace(archive, '').replace(ext, '').replace('.','') for x in names]
        indexes  = [int(x) for x in suffixes if x and set(x) <= set('0123456789')]
        idx = 1
        if indexes:
            idx += sorted(indexes)[-1]

        return os.path.join(glob.COMMENTS, "%s.%d%s" % (archive, idx, ext))

    def _log(self):
        if not os.path.isdir(glob.LOGDIR):
            os.mkdir (glob.LOGDIR)

        logfile = os.path.join(glob.LOGDIR, datetime.datetime.now().strftime("%Y-%m"))
        s = json.dumps({
            'time': self.time,
            'source': self.source,
            'target': self.target
        })

        with open(logfile, "a") as log:
            logging.debug( "writing logfile %s with %s" % (logfile, s))
            log.write("%s\n" % (s))
            log.close()


class TimeSeriesHandler(object):
    def __init__(self, tag):
        if not os.path.isdir(glob.TSDBDIR):
            os.mkdir(glob.TSDBDIR)

        self.tag = tag
        self.p = os.path.join(glob.TSDBDIR, '%s.csv' % (self.tag))
        self.db = {}

    #def _loaddb(self):
        #if not os.path.isfile(self.p):
            #return

        #pattern = re.compile(r'^([0-9-\+:T]+)\s+(.*)$')
        #searchfile = open(self.p, 'r')
        #for line in searchfile:
            #matched = re.match(pattern, line)
            #if not matched:
                #continue

            #epoch = int(iso8601.parse_date(matched.group(1)).replace(tzinfo=pytz.utc).strftime('%s'))
            #data = matched.group(2)
            #self.db[epoch] = data
        #searchfile.close()

    #def _dumpdb(self):
        #lines = []
        #for e in self.db.items():
            #epoch, data = e
            #tstamp = datetime.datetime.utcfromtimestamp(epoch).replace(tzinfo=pytz.utc).strftime(glob.ISODATE)
            #line = '%s %s' % (tstamp, data)
            #lines.append(line)

        #bkp = '%s.bkp' % (self.p)
        #shutil.copy(self.p, bkp)
        #with open(self.p, "w") as searchfile:

                #searchfile.write()
            #del(cr)
            #csvfile.close()
        #os.unlink(bkp)

    @staticmethod
    def _common_date_base(d1, d2):
        d1 = d1.replace(tzinfo=pytz.utc).strftime(glob.ISODATE)
        d2 = d2.replace(tzinfo=pytz.utc).strftime(glob.ISODATE)
        l = len(d1)
        common = ''
        for i in range(l):
            if d1[i] == d2[i]:
                common = common + d1[i]
            else:
                break
        return common

    def search(self, when, tolerance=1800):
        when = when.replace(tzinfo=pytz.utc)
        tolerance = int(tolerance/2)
        minwhen = when - datetime.timedelta(seconds=tolerance)
        maxwhen = when + datetime.timedelta(seconds=tolerance)

        closest = None
        mindiff = float('inf')
        common = TimeSeriesHandler._common_date_base(minwhen, maxwhen)
        pattern = re.compile(r'^(%s[0-9-\+:T]+)\s+(.*)$' % (common))
        searchfile = open(self.p, 'r')
        for line in searchfile:
            matched = re.match(pattern, line)
            if not matched:
                continue

            d = iso8601.parse_date(matched.group(1))
            diff = d - when
            diff = abs(diff.total_seconds())
            if diff >= mindiff:
                continue

            mindiff = diff
            closest = (d, matched.group(2))
        searchfile.close()
        return closest

    def append(self, data, dt=datetime.datetime.now().replace(tzinfo=pytz.utc)):
        if os.path.isfile(self.p):
            epoch = int(dt.strftime('%s'))
            stat = os.stat(self.p)
            if epoch < stat.st_mtime:
                logging.warning('Refusing to append %s with old data' % self.p)
                return

        with open(self.p, 'a') as db:
            db.write("%s %s\n" % (
                dt.strftime(glob.ISODATE),
                data
            ))


class DataHandler(object):
    def __init__(self, request):
        self.request = request
        self.dt = datetime.datetime.now().replace(tzinfo=pytz.utc)
        self.response = sanic.response.text('accepted',status=200)

        if not 'secrets' in glob.conf or \
        not 'devices' in glob.conf['secrets']:
            self.response = sanic.response.text(
                'server configuration error',
                status=501
            )
            return

        if 'id' not in self.request.args:
            self.response = sanic.response.text(
                'device id not found in request',
                status=401
            )
            return

        id = self.request.args.get('id')
        if id not in glob.conf['secrets']['devices'].keys():
            self.response = sanic.response.text(
                'device id rejected',
                status=401
            )
            return

        self.id = glob.conf['secrets']['devices'][id]

class OpenGTSHandler(DataHandler):
    def __init__(self, *args, **kwargs):
        super(OpenGTSHandler, self).__init__(*args, **kwargs)
        self.lat = 0
        self.lon = 0
        self.alt = 0
        self._parse()
        self.l = '%s 0' % (self.dt.strftime(glob.ISODATE))

    def _parse(self):
        logging.debug('--- incoming location request ---')
        logging.debug(self.request.args)

        if 'latitude' in self.request.args and 'longitude' in self.request.args:
            self.lat = float(self.request.args.get('latitude'))
            self.lon = float(self.request.args.get('longitude'))
        elif 'gprmc' in self.request.args:
            gprmc = pynmea2.parse(self.request.args.get('gprmc'))
            try:
                self.lat = float(gprmc.latitude)
                self.lon = float(gprmc.longitude)
            except:
                self.response = sanic.response.text(
                    "could not process gprmc string",
                    status=422
                )
                return
        else:
            self.response = sanic.response.text(
                "no location information found in query",
                status=401
            )
            return

        if 'exclude_coordinates' in glob.conf['secrets']:
            excl = {}
            for t in ['lat', 'lon']:
                excl[t] = []
                if t in glob.conf['secrets']['exclude_coordinates']:
                    for c in glob.conf['secrets']['exclude_coordinates'][t]:
                        excl[t].append(float(c))

            if round(self.lat,2) in excl['lat'] and round(self.lon,2) in excl['lon']:
                self.response = sanic.response.text(
                    "this location is on the excluded list",
                    status=200
                )
                return

        if 'loc_timestamp' in self.request.args and 'offset' in self.request.args:
            # this is a bit ugly: first convert the epoch to datetime
            # then append it with the offset as string
            # and convert the string back to datetime from the iso8601 string
            dt = datetime.datetime.utcfromtimestamp(int(self.request.args.get('loc_timestamp')))
            dt = dt.strftime('%Y-%m-%dT%H:%M:%S')
            dt = "%s%s" % (dt, self.request.args.get('offset'))
            try:
                self.dt = iso8601.parse_date(dt).replace(tzinfo=pytz.utc)
            except:
                pass

        if 'altitude' in self.request.args:
            self.alt = float(self.request.args.get('altitude'))
        else:
            try:
                self.alt = OpenGTSHandler.altitude_from_bing(self.lat, self.lon)
            except:
                pass

        self.lat = "{:4.6f}".format(float(self.lat))
        self.lon = "{:4.6f}".format(float(self.lon))
        self.alt = "{:4.6f}".format(float(self.alt))
        l = '%s %s %s' % (self.lat, self.lon, self.alt)

        gpsfile = TimeSeriesHandler('location')
        gpsfile.append(l, dt=self.dt)

    @staticmethod
    def altitude_from_bing(lat, lon):
        if 'bing_key' not in glob.conf['secrets']:
            return 0
        if not glob.conf['secrets']['bing_key']:
            return 0

        url = "http://dev.virtualearth.net/REST/v1/Elevation/List?points=%s,%s&key=%s" % (
            lat,
            lon,
            glob.conf['secrets']['bing_key']
        )

        bing = requests.get(url)
        bing = json.loads(bing.text)
        if 'resourceSets' not in bing or \
        'resources' not in bing['resourceSets'][0] or \
        'elevations' not in bing['resourceSets'][0]['resources'][0] or \
        not bing['resourceSets'][0]['resources'][0]['elevations']:
            return 0

        alt = float(bing['resourceSets'][0]['resources'][0]['elevations'][0])
        del(bing)
        del(url)
        return alt


class SensorHandler(DataHandler):
    def __init__(self, *args, **kwargs):
        super(SensorHandler, self).__init__(*args, **kwargs)
        self.data = 0
        self.tag = ''
        self._parse()

    def _parse(self):
        logging.debug('--- incoming sensor request ---')
        logging.debug(self.request.args)

        for tag in self.request.args:
            if tag == 'id':
                continue

            datafile = TimeSeriesHandler('%s-%s' % (self.id, tag))
            datafile.append(self.request.args.get(tag), dt=self.dt)


asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
app = Sanic()

@app.route("/webmention")
async def wm(request, methods=["POST"]):
    source = request.form.get('source')
    target = request.form.get('target')
    r = WebmentionHandler(source, target)
    return r.response

@app.route("/search")
async def search(request, methods=["GET"]):
    query = request.args.get('s')
    r = SearchHandler(query)
    return r.response

@app.route("/micropub")
async def mpub(request, methods=["POST","GET"]):
    r = MicropubHandler(request)
    return r.response

@app.route("/opengts")
async def opengts(request, methods=["GET"]):
    r = OpenGTSHandler(request)
    return r.response

@app.route("/sensor")
async def sensor(request, methods=["GET"]):
    r = SensorHandler(request)
    return r.response

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)