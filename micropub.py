#!/usr/bin/env python3

import os
import asyncio
import uvloop
from sanic import Sanic
import sanic.response
from sanic.log import log as logging

import os
import arrow
import frontmatter
import glob
import tempfile
from slugify import slugify
import glob
import shared
from nasg import BaseRenderable, Renderer, Singular
import requests
import urllib.parse

class NewEntry(BaseRenderable):
    metamap = {
        'summary': 'summary',
        'name': 'title',
        'in-reply-to': 'in-reply-to',
        'repost-of': 'repost-of',
        'bookmark-of': 'bookmark-of',
        'like-of': 'favorite-of',
    }

    categorymap = {
        'in-reply-to': 'note',
        'repost-of': 'note',
        'bookmark-of': 'bookmark',
        'favorite-of': 'favorite'
    }

    slugmap = [
        'slug',
        'in-reply-to',
        'repost-of',
        'bookmark-of',
        'like-of',
        'title'
    ]

    # needs self.mtime, self.target

    def __init__(self, request):
        self.dt = arrow.utcnow()
        self.fm = frontmatter.loads('')
        self.request = request
        self.response = sanic.response.text("Unhandled error", status=500)
        logging.debug(request.form)

    def __try_adding_meta(self, lookfor, kname):
        t = self.request.form.get(lookfor, None)
        if t and len(t):
            self.fm.metadata[kname] = self.request.form.get(lookfor)

    @property
    def path(self):
        return os.path.abspath(os.path.join(
            shared.config.get('source', 'contentdir'),
            self.category,
            "%s.md" % self.fname
        ))

    @property
    def target(self):
        targetdir = os.path.abspath(os.path.join(
            shared.config.get('target', 'builddir'),
            self.fname
        ))
        return os.path.join(targetdir, 'index.html')

    @property
    def category(self):
        category = 'note'
        for meta, cname in self.categorymap.items():
            if meta in self.fm.metadata:
                logging.debug('changing category to %s because we have %s', cname, meta)
                category = cname

        if 'summary' in self.fm.metadata:
            if 'IT' in self.fm.metada['tags'] or 'it' in self.fm.metada['tags']:
                category = 'article'
                logging.debug('changing category to %s', category)
            if 'journal' in self.fm.metada['tags'] or 'journal' in self.fm.metada['tags']:
                category = 'journal'
                logging.debug('changing category to %s', category)


        return category


    @property
    def existing_tags(self):
        if hasattr(self, '_existing_tags'):
            return self._existing_tags

        existing = glob.glob(os.path.join(
            shared.config.get('target', 'builddir'),
            "tag",
            "*"
        ));

        self._existing_tags = existing
        return self._existing_tags


    @property
    def existing_slugs(self):
        if hasattr(self, '_existing_slugs'):
            return self._existing_slugs

        existing = [os.path.splitext(i)[0] for i in list(map(
            os.path.basename, glob.glob(
                os.path.join(
                    shared.config.get('source', 'contentdir'),
                    "*",
                    "*.md"
                )
            )
        ))]

        self._existing_slugs = existing
        return self._existing_slugs


    @property
    def fname(self):
        if hasattr(self, '_slug'):
            return self._slug

        slug = shared.baseN(self.dt.timestamp)
        for maybe in self.slugmap:
            val = self.request.form.get(maybe, None)
            if not val:
                continue
            logging.debug('using %s for slug', maybe)
            slug = shared.slugfname(val)
            break

        self._slug = slug
        return self._slug


    @property
    def exists(self):
        if self.fname in self.existing_slugs:
            logging.warning("slug already exists: %s", slug)
            return True
        return False
            #inc = 1
            #while slug in slugs:
                #slug = "%s-%d" % (slug, inc)
                #inc = inc+1
            #logging.warning("Using %s as slug instead", slug)

    def run(self):
        if not self.verify():
            return

        self.parse()

        if self.exists:
            self.response = sanic.response.text(
                "update is not yet supported",
                status=401
            )
            return

        self.write()
        #self.render()

    def verify(self):
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
            self.response = sanic.response.text(
                "Mising access token",
                status=401
            )
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
            self.response = sanic.response.text(
                "Could not verify access token",
                status=500
            )
            return False

        response = urllib.parse.parse_qs(verify.text)
        logging.debug(response)
        if 'scope' not in response or 'me' not in response:
            self.response = sanic.response.text(
                "Could not verify access token 'me'",
                status=401
            )
            return False

        if '%s/' % (shared.config.get('site','url').rstrip()) not in response['me']:
            self.response = sanic.response.text(
                "You can't post to this domain.",
                status=401
            )
            return False

        if 'create' not in "%s" % response['scope']:
            self.response = sanic.response.text(
                "Invalid scope",
                status=401
            )
            return False
        return True

    def parse(self):
        self.fm.metadata['published'] = self.dt.format(shared.ARROWISO)

        for lookfor, kname in self.metamap.items():
            self.__try_adding_meta(lookfor, kname)

        if self.request.form.get('content', None):
            self.fm.content = self.request.form.get('content')

        if self.request.form.get('category[]', None):
            self.fm.metadata['tags'] = list(self.request.form['category[]'])

    def write(self):
        logging.info('writing incoming post to: %s', self.path)
        with open (self.path, 'wt') as f:
            f.write(frontmatter.dumps(self.fm))
            self.response = sanic.response.text(
                "Created",
                status=201
            )

    #def render(self):
        #singular = Singular(self.path)
        #singular.render()
        #self.response = sanic.response.text(
            #"Post created",
            #status = 201,
            #headers = {
                #'Location': "%s" % (singular.url)
            #}
        #)
        #return



if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    app = Sanic()

    @app.route("/micropub", methods=["POST","GET"])
    async def mpub(request):
        r = NewEntry(request)
        r.run()
        return r.response


    app.run(host="127.0.0.1", port=8004, debug=True)
