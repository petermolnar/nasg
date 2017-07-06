#!/usr/bin/env python3

import asyncio
import uvloop
import os
import json
from sanic import Sanic
import sanic.response
from sanic.log import log as logging
import shared
import requests
from requests_oauthlib import OAuth1Session, oauth1_session, OAuth2Session, oauth2_session
from oauthlib.oauth2 import BackendApplicationClient
import json
import tempfile

from pprint import pprint

class TokenDB(object):
    def __init__(self, uuid='tokens'):
        self.db = os.path.abspath(os.path.join(
            tempfile.gettempdir(),
            "%s.json" % uuid
        ))
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
        self.refresh()

    def get_token(self, token):
        return self.tokens.get(token, None)

    def get_service(self, service):
        token = self.tokens.get(service, None)
        #if token:
            #token = self.get_token(token)
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


class Oauth2Flow(object):
    token_url = ''

    def __init__(self, service):
        self.service = service
        self.key = shared.config.get(service, 'api_key')
        self.secret = shared.config.get(service, 'api_secret')
        client = BackendApplicationClient(
            client_id=self.key
        )
        client.prepare_request_body(scope=['browse'])
        oauth = OAuth2Session(client=client)
        token = oauth.fetch_token(
            token_url=self.token_url,
            client_id=self.key,
            client_secret=self.secret
        )
        self.client = OAuth2Session(
            self.key,
            token=token
        )

    def request(self, url, params={}):
        return self.client.get(url, params=params)



class DAOauth(Oauth2Flow):
    token_url = 'https://www.deviantart.com/oauth2/token'

    def __init__(self):
        super(DAOauth, self).__init__('deviantart')


class Oauth1Flow(object):
    request_token_url = ''
    access_token_url = ''
    authorize_url = ''

    def __init__(self, service):
        self.service = service
        self.key = shared.config.get(service, 'api_key')
        self.secret = shared.config.get(service, 'api_secret')
        self.tokendb = TokenDB()
        self.t = self.tokendb.get_service(self.service)
        self.oauth_init()

    def oauth_init(self):
        if not self.t:
            self.request_oauth_token()

        t = self.tokendb.get_token(self.t)
        if not t.get('access_token', None) or not t.get('access_token_secret', None):
            self.request_access_token()

    def request_oauth_token(self):
        client = OAuth1Session(
            self.key,
            client_secret=self.secret,
            callback_uri="%s/oauth1/" % shared.config.get('site', 'url')
        )
        r = client.fetch_request_token(self.request_token_url)
        logging.debug('setting token to %s', r.get('oauth_token'))
        self.t = r.get('oauth_token')
        logging.debug('updating secret to %s', r.get('oauth_token_secret'))
        self.tokendb.update_token(
            self.t,
            oauth_token_secret=r.get('oauth_token_secret')
        )
        self.tokendb.set_service(
            self.service,
            self.t
        )

        existing = self.tokendb.get_token(self.t)
        verified = existing.get('verifier', None)
        while not verified:
            logging.debug('verifier missing for %s', self.t)
            self.auth_url(existing)
            self.tokendb.refresh()
            existing = self.tokendb.get_token(self.t)
            verified = existing.get('verifier', None)

    def auth_url(self, existing):
        t = self.tokendb.get_token(self.t)
        client = OAuth1Session(
            self.key,
            client_secret=self.secret,
            resource_owner_key=self.t,
            resource_owner_secret=t.get('oauth_token_secret'),
            callback_uri="%s/oauth1/" % shared.config.get('site', 'url')
        )
        input('Visit: %s and press any key after' % (
            client.authorization_url(self.authorize_url)
        ))

    def request_access_token(self):
        try:
            t = self.tokendb.get_token(self.t)
            client = OAuth1Session(
                self.key,
                client_secret=self.secret,
                callback_uri="%s/oauth1/" % shared.config.get('site', 'url'),
                resource_owner_key=self.t,
                resource_owner_secret=t.get('oauth_token_secret'),
                verifier=t.get('verifier')
            )
            r = client.fetch_access_token(self.access_token_url)
            self.tokendb.update_token(
                self.t,
                access_token=r.get('oauth_token'),
                access_token_secret=r.get('oauth_token_secret')
            )
        except oauth1_session.TokenRequestDenied as e:
            logging.error('getting access token was denied, clearing former oauth tokens and re-running everyting')
            self.tokendb.clear_service(self.service)
            self.oauth_init()


    def request(self, url, params):
        t = self.tokendb.get_token(self.t)
        client = OAuth1Session(
            self.key,
            client_secret=self.secret,
            resource_owner_key=t.get('access_token'),
            resource_owner_secret=t.get('access_token_secret')
        )
        return client.get(url, params=params)


class FivehpxOauth(Oauth1Flow):
    request_token_url = 'https://api.500px.com/v1/oauth/request_token'
    access_token_url = 'https://api.500px.com/v1/oauth/access_token'
    authorize_url = 'https://api.500px.com/v1/oauth/authorize'

    def __init__(self):
        super(FivehpxOauth, self).__init__('500px')


class FlickrOauth(Oauth1Flow):
    request_token_url = 'https://www.flickr.com/services/oauth/request_token'
    access_token_url = 'https://www.flickr.com/services/oauth/access_token'
    authorize_url = 'https://www.flickr.com/services/oauth/authorize'

    def __init__(self):
        super(FlickrOauth, self).__init__('flickr')


class TumblrOauth(Oauth1Flow):
    request_token_url = 'https://www.tumblr.com/oauth/request_token'
    access_token_url = 'https://www.tumblr.com/oauth/access_token'
    authorize_url = 'https://www.tumblr.com/oauth/authorize'

    def __init__(self):
        super(TumblrOauth, self).__init__('tumblr')

#class WPOauth(Oauth1Flow):
    #request_token_url = 'https://public-api.wordpress.com/oauth2/token'
    #access_token_url = 'https://public-api.wordpress.com/oauth2/authenticate'
    #authorize_url = 'https://public-api.wordpress.com/oauth2/authorize'

    #def __init__(self):
        #super(WPOauth, self).__init__('wordpress.com')


if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    app = Sanic()

    @app.route("/oauth1", methods=["GET"])
    async def oa(request):
        token = request.args.get('oauth_token')
        verifier = request.args.get('oauth_verifier')
        tokendb = TokenDB()
        tokendb.update_token(
            token,
            verifier=verifier
        )
        return sanic.response.text(
            "OK",
            status=200
        )

    #@app.route("/oauth2", methods=["GET"])
    #async def oa2(request):
        ##token = request.args.get('oauth_token')
        ##verifier = request.args.get('oauth_verifier')
        ##tokendb = TokenDB()
        ##tokendb.update_token(
            ##token,
            ##verifier=verifier
        ##)
        #return sanic.response.text(
            #json.dumps(request.args),
            #status=200
        #)

    app.run(host="127.0.0.1", port=8006, debug=True)
