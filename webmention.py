#!/usr/bin/env python3

import asyncio
import uvloop
import os
import hashlib
import json
import urllib.parse
import frontmatter
from sanic import Sanic
import sanic.response
from sanic.log import log as logging
import validators
import arrow
from webmentiontools import urlinfo
import shared
import envelope
import bleach


class WebmentionHandler(object):
    def __init__ (self, source, target):
        self.source = source
        self.target = target
        self.now = arrow.utcnow().timestamp
        logging.info("incoming webmention %s => %s", self.source, self.target)

        self.r = sanic.response.text(
            "something went wrong on my side, could you please let me know at hello@petermolnar.eu ?",
            status=500
        )

    def run(self):
        if not self._validate():
            return

        self._parse()
        if self._save():
            self._notify()

    def _validate(self):
        test = {
            self.source: '"souce" parameter is an invalid URL',
            self.target: '"target" parameter is an invalid URL'
        }
        for url, emsg in test.items():
            logging.debug("validating URL %s", url)
            if not validators.url(url):
                self.r = sanic.response.text(
                    emsg,
                    status=400
                )
                return False

        logging.debug("checking target domain")
        _target = urllib.parse.urlparse(self.target)
        _target_domain = '{uri.netloc}'.format(uri=_target)
        _mydomains = shared.config.get('site', 'domains').split(" ")
        if not _target_domain in _mydomains:
            self.r = sanic.response.text(
                "'target' is not in the list of allowed domains",
                status=400
            )
            return False

        logging.debug("checking selfpings")
        _source = urllib.parse.urlparse(self.source)
        _source_domain = '{uri.netloc}'.format(uri=_source)
        if _source_domain in _mydomains:
            self.r = sanic.response.text(
                "selfpings are not allowed",
                status=400
            )
            return False

        return True

    def _parse(self):
        logging.debug("fetching %s", self.source)
        self._source = urlinfo.UrlInfo(self.source)
        if self._source.error:
            self.r = sanic.response.text(
                "couldn't fetch 'source' from %s" % (self.source),
                status=408
            )
            return False

        if not self._source.linksTo(self.target):
            self.r = sanic.response.text(
                "'source' (%s) does not link to 'target' (%s)" % (
                    self.source,
                    self.target
                ),
                status=400
            )
            return False

        logging.debug("fetching %s", self.target)
        self._target = urlinfo.UrlInfo(self.target)
        if self._target.error:
            self.r = sanic.response.text(
                "couldn't fetch 'target' from %s" % (self.target),
                status=408
            )
        #logging.info("parsed webmention:\n%s\n\n%s", self.meta, self.content)

    def _accepted(self):
        self.r = sanic.response.text(
            "accepted",
            status=202
        )


    def _save(self):
        target = os.path.join(
            shared.config.get('source', 'commentsdir'),
            "%s.md" % self.mhash
        )

        if os.path.isfile(target):
            with open(target) as f:
                doc = frontmatter.loads(f.read())
        else:
            doc = frontmatter.loads('')

        if self.content == doc.content:
            logging.warning('repinged target, no update needed')
            self._accepted()
            return False

        doc.metadata = self.meta
        doc.content = self.content
        if os.path.isfile(target):
            logging.warning('updating existing webmention %s', target)
        else:
            logging.warning('saving incoming webmention to %s', target)

        with open(target, 'wt') as t:
            t.write(frontmatter.dumps(doc))
            self._accepted()
            return True

    def _notify(self):
        text = "\nsource URL\n:    %s\n\ntarget URL:\n:    %s\n\ndate\n:    %s\n\nauthor name:\n:    %s\n\nauthor URL:\n:    %s\n\nauthor email:\n:    %s\n\n---\n\n%s" % (
            self.source,
            self.target,
            self._meta['date'],
            self._meta['author'].get('name', self.source),
            self._meta['author'].get('url', self.source),
            self._meta['author'].get('email', ''),
            self.content
        )

        l = envelope.Letter(
            sender=(
                shared.config.get('webmention', 'from_name'),
                shared.config.get('webmention', 'from_address')
            ),
            recipient=(
                shared.config.get('webmention', 'to_name'),
                shared.config.get('webmention', 'to_address')
            ),
            subject="[webmention] %s" % self.source,
            text=text
        )
        l.make()
        l.send()

    @property
    def mhash(self):
        return hashlib.sha1(json.dumps(self.meta, sort_keys=True).encode('utf-8')).hexdigest()

    @property
    def meta(self):
        if hasattr(self, '_meta'):
            return self._meta

        self._meta = {
            'author': bleach.clean(self._source.author, tags=[], strip_comments=True, strip=True),
            'type': self._source.relationType,
            'target': self.target,
            'source': self.source,
            'date': arrow.get(self._source.pubDate).format(shared.ARROWISO),
        }

        return self._meta

    @property
    def content(self):
        if hasattr(self, '_content'):
            return self._content

        self._content = shared.Pandoc(False).convert(self._source.content)
        return self._content


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    app = Sanic()

    @app.route("/webmention", methods=["POST"])
    async def wm(request):
        source = request.form.get('source')
        target = request.form.get('target')
        r = WebmentionHandler(source, target)
        r.run()
        return r.r

    app.run(host="127.0.0.1", port=8002, debug=True)
