import os
import json
import requests
import glob
import logging
import shutil
import subprocess
import arrow

from requests_oauthlib import OAuth1Session, oauth1_session, OAuth2Session, oauth2_session
from oauthlib.oauth2 import BackendApplicationClient

import shared


class Favs(object):
    def __init__(self, confgroup):
        self.confgroup = confgroup

    @property
    def lastpulled(self):
        mtime = 0
        d = os.path.join(
            shared.config.get('archive', 'favorite'),
            "%s-*" % self.confgroup
        )
        files = glob.glob(d)
        for f in files:
            ftime = int(os.path.getmtime(f))
            if ftime > mtime:
                mtime = ftime

        mtime = mtime + 1
        logging.debug("last flickr fav timestamp: %s", mtime)
        return mtime


class FlickrFavs(Favs):
    url = 'https://api.flickr.com/services/rest/'

    def __init__(self):
        super(FlickrFavs, self).__init__('flickr')
        self.get_uid()
        self.params = {
            'method': 'flickr.favorites.getList',
            'api_key': shared.config.get('api_flickr', 'api_key'),
            'user_id': self.uid,
            'extras': 'description,geo,tags,owner_name,date_upload,url_o,url_k,url_h,url_b,url_c,url_z',
            'per_page': 500, # maximim
            'format': 'json',
            'nojsoncallback': '1',
            'min_fave_date': self.lastpulled
        }

    def get_uid(self):
        params = {
            'method': 'flickr.people.findByUsername',
            'api_key': shared.config.get('api_flickr', 'api_key'),
            'format': 'json',
            'nojsoncallback': '1',
            'username': shared.config.get('api_flickr', 'username'),
        }
        r = requests.get(
            self.url,
            params=params
        )
        parsed = json.loads(r.text)
        self.uid = parsed.get('user', {}).get('id')


    def getpaged(self, offset):
        logging.info('requesting page #%d of paginated results', offset)
        self.params.update({
            'page': offset
        })
        r = requests.get(
            self.url,
            params=self.params
        )
        parsed = json.loads(r.text)
        return parsed.get('photos', {}).get('photo', [])

    def run(self):
        r = requests.get(self.url,params=self.params)
        js = json.loads(r.text)
        js = js.get('photos', {})

        photos = js.get('photo', [])

        total = int(js.get('pages', 1))
        current = int(js.get('page', 1))
        cntr = total - current

        while cntr > 0:
            current = current + 1
            paged = self.getpaged(current)
            photos = photos + paged
            cntr = total - current

        for photo in photos:
            fav = FlickrFav(photo)
            if not fav.exists:
                fav.run()

class FivehpxFavs(Favs):
    def __init__(self):
        super(FivehpxFavs, self).__init__('500px')
        self.params = {
            'consumer_key': shared.config.get('api_500px', 'api_key'),
            'rpp': 100, # maximum
            'image_size': 4,
            'include_tags': 1,
            'include_geo': 1,
            'sort': 'created_at',
            'sort_direction': 'desc'
        }
        self.oauth = FivehpxOauth()
        self.uid = None
        self.galid = None

    def get_uid(self):
        r = self.oauth.request(
            'https://api.500px.com/v1/users',
            params={}
        )
        js = json.loads(r.text)
        self.uid = js.get('user', {}).get('id')

    def get_favgalid(self):
        r = self.oauth.request(
            'https://api.500px.com/v1/users/%s/galleries' % (self.uid),
            params={
                'kinds': 5 # see https://github.com/500px/api-documentation/blob/master/basics/formats_and_terms.md#gallery-kinds
            }
        )
        js = json.loads(r.text)
        g = js.get('galleries', []).pop()
        self.galid = g.get('id')


    @property
    def url(self):
        return 'https://api.500px.com/v1/users/%s/galleries/%s/items' % (
            self.uid,
            self.galid
        )

    def getpaged(self, offset):
        logging.info('requesting page #%d of paginated results', offset)
        self.params.update({
            'page': offset
        })
        r = requests.get(
            self.url,
            params=self.params
        )
        parsed = json.loads(r.text)
        return parsed.get('photos')

    def run(self):
        self.get_uid()
        self.get_favgalid()

        r = requests.get(self.url,params=self.params)
        js = json.loads(r.text)
        photos = js.get('photos')

        total = int(js.get('total_pages', 1))
        current = int(js.get('current_page', 1))
        cntr = total - current

        while cntr > 0:
            current = current + 1
            paged = self.getpaged(current)
            photos = photos + paged
            cntr = total - current

        for photo in photos:
            fav = FivehpxFav(photo)
            if not fav.exists:
                fav.run()


class TumblrFavs(Favs):
    url = 'https://api.tumblr.com/v2/user/likes'

    def __init__(self):
        super(TumblrFavs, self).__init__('tumblr')
        self.oauth = TumblrOauth()
        self.params = {
            'after': self.lastpulled
        }
        self.likes = []

    def getpaged(self, offset):
        r = self.oauth.request(
            self.url,
            params={'offset': offset}
        )
        return json.loads(r.text)

    def run(self):
        r = self.oauth.request(
            self.url,
            params=self.params
        )

        js = json.loads(r.text)
        total = int(js.get('response', {}).get('liked_count', 20))
        offset = 20
        cntr = total - offset
        likes = js.get('response', {}).get('liked_posts', [])
        while cntr > 0:
            paged = self.getpaged(offset)
            likes = likes + paged.get('response', {}).get('liked_posts', [])
            offset = offset + 20
            cntr = total - offset

        self.likes = likes
        for like in self.likes:
            fav = TumblrFav(like)
            if not fav.exists:
                fav.run()


class DAFavs(Favs):
    def __init__(self):
        from pprint import pprint
        super(DAFavs, self).__init__('deviantart')
        self.username = shared.config.get('api_deviantart', 'username'),
        self.oauth = DAOauth()
        self.likes = []
        self.galid = None
        self.params = {
            'limit': 24, # this is the max as far as I can tell
            'mature_content': 'true',
            'username': self.username
        }

    def get_favgalid(self):
        r = self.oauth.request(
            'https://www.deviantart.com/api/v1/oauth2/collections/folders',
            params={
                'username': self.username,
                'calculate_size': 'false',
                'ext_preload': 'false',
                'mature_content': 'true'
            }
        )
        js = json.loads(r.text)
        for g in js.get('results', []):
            if 'Featured' == g.get('name'):
                self.galid = g.get('folderid')
                break

    @property
    def url(self):
         return 'https://www.deviantart.com/api/v1/oauth2/collections/%s' % (self.galid)


    def getpaged(self, offset):
        self.params.update({'offset': offset})
        r = self.oauth.request(
            self.url,
            self.params
        )
        js = json.loads(r.text)
        return js

    def getsinglemeta(self, daid):
        r = self.oauth.request(
            'https://www.deviantart.com/api/v1/oauth2/deviation/metadata',
            params={
                'deviationids[]': daid,
                'ext_submission': False,
                'ext_camera': False,
                'ext_stats': False,
                'ext_collection': False,
                'mature_content': True,
            }
        )
        meta = {}
        try:
            meta = json.loads(r.text)
            return meta.get('metadata', []).pop()
        except:
            return meta

    def has_more(self, q):
        if True == q or 'True' == q or 'true' == q:
            return True
        return False

    def run(self):
        self.get_favgalid()

        r = self.oauth.request(
            self.url,
            self.params
        )

        js = json.loads(r.text)
        favs = js.get('results', [])
        has_more = self.has_more(js.get('has_more'))
        offset = js.get('next_offset')
        while True == has_more:
            logging.info('iterating over DA results with offset %d', offset)
            paged = self.getpaged(offset)
            new = paged.get('results', [])
            if not len(new):
                #logging.error('empty results from deviantART, breaking loop')
                break
            favs = favs + new
            has_more = self.has_more(paged.get('has_more'))
            if not has_more:
                break
            n = int(paged.get('next_offset'))
            if not n:
                break
            offset = offset + n

        self.favs = favs
        for fav in self.favs:
            f = DAFav(fav)
            if f.exists:
                continue

            f.fav.update({'meta': self.getsinglemeta(fav.get('deviationid'))})
            f.run()

class ImgFav(object):
    def __init__(self):
        self.imgurl = ''
        self.meta = {
            'dt': arrow.utcnow(),
            'title': '',
            'favorite-of': '',
            'tags': [],
            'geo': {
                'latitude': '',
                'longitude': '',
            },
            'author': {
                'name': '',
                'url': '',
            },
        }
        self.content = ''

    @property
    def exists(self):
        return os.path.exists(self.target)

    def pull_image(self):
        logging.info("pulling image %s to %s", self.imgurl, self.target)
        r = requests.get(self.imgurl, stream=True)
        if r.status_code == 200:
            with open(self.target, 'wb') as f:
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)


    def write_exif(self):
        logging.info('populating EXIF data of %s' % self.target)
        tags = list(set(self.meta.get('tags',[])))
        dt = self.meta.get('dt').to('utc')

        geo_lat = False
        geo_lon = False
        if self.meta.get('geo', None):
            geo = self.meta.get('geo', None)
            lat = geo.get('latitude', None)
            lon = geo.get('longitude', None)
            if lat and lon and 'null' != lat and 'null' != lon:
                geo_lat = lat
                geo_lon = lon

        author_name = ''
        author_url = ''
        if self.meta.get('author', None):
            a = self.meta.get('author')
            author_name = a.get('name', '')
            author_url = a.get('url', '')
        author_name = "%s" % author_name
        author_url = "%s" % author_url

        params = [
            'exiftool',
            '-overwrite_original',
            '-EXIF:Artist=%s' % author_name[:64],
            '-XMP:Copyright=Copyright %s %s (%s)' % (
                dt.format('YYYY'),
                author_name,
                author_url,
            ),
            '-XMP:Source=%s' % self.meta.get('favorite-of'),
            '-XMP:ReleaseDate=%s' % dt.format('YYYY:MM:DD HH:mm:ss'),
            '-XMP:Headline=%s' % self.meta.get('title'),
            '-XMP:Description=%s' % self.content,
        ];
        for t in tags:
            params.append('-XMP:HierarchicalSubject+=%s' % t)
            params.append('-XMP:Subject+=%s' % t)
        if geo_lat and geo_lon:
            geo_lat = round(float(geo_lat),6)
            geo_lon = round(float(geo_lon),6)

            if geo_lat < 0:
                GPSLatitudeRef = 'S'
            else:
                GPSLatitudeRef = 'N'

            if geo_lon < 0:
                GPSLongitudeRef = 'W'
            else:
                GPSLongitudeRef = 'E'

            params.append('-GPSLongitude=%s' % abs(geo_lon))
            params.append('-GPSLatitude=%s' % abs(geo_lat))
            params.append('-GPSLongitudeRef=%s' % GPSLongitudeRef)
            params.append('-GPSLatitudeRef=%s' % GPSLatitudeRef)
        params.append(self.target);

        p = subprocess.Popen(
            params,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = p.communicate()
        _original = '%s_original' % self.target
        if os.path.exists(_original):
            os.unlink(_original)


class FlickrFav(ImgFav):
    url = 'https://api.flickr.com/services/rest/'

    def __init__(self, photo):
        self.photo = photo
        self.ownerid = photo.get('owner')
        self.photoid = photo.get('id')
        self.url = "https://www.flickr.com/photos/%s/%s" % (self.ownerid, self.photoid)
        self.target = os.path.join(
            shared.config.get('archive', 'favorite'),
            "flickr-%s-%s.jpg" % (self.ownerid, self.photoid)
        )

    def run(self):

        if self.exists:
            logging.warning("%s already exists, skipping", self.target)
            return

        # the bigger the better, see
        # https://www.flickr.com/services/api/misc.urls.html
        img = self.photo.get(
            'url_o',
            self.photo.get('url_k',
                self.photo.get('url_h',
                    self.photo.get('url_b',
                        self.photo.get('url_c',
                            self.photo.get('url_z',
                                False
                            )
                        )
                    )
                )
            )
        )

        if not img:
            logging.error("image url was empty for %s, skipping fav", self.url)
            return
        self.imgurl = img
        self.pull_image()
        self.meta = {
            'dt': arrow.get(
                self.photo.get('date_faved',
                    arrow.utcnow().timestamp
                )
            ),
            'title': '%s' % shared.Pandoc('plain').convert(
                self.photo.get('title', '')
            ).rstrip(),
            'favorite-of': self.url,
            'tags': self.photo.get('tags', '').split(' '),
            'geo': {
                'latitude': self.photo.get('latitude', ''),
                'longitude': self.photo.get('longitude', ''),
            },
            'author': {
                'name': self.photo.get('ownername'),
                'url': 'https://www.flickr.com/people/%s' % (
                    self.photo.get('owner')
                ),
            },
        }

        self.content = shared.Pandoc('plain').convert(
            self.photo.get('description', {}).get('_content', '')
        )

        self.write_exif()

class FivehpxFav(ImgFav):
    def __init__(self, photo):
        self.photo = photo
        self.ownerid = photo.get('user_id')
        self.photoid = photo.get('id')
        self.target = os.path.join(
            shared.config.get('archive', 'favorite'),
            "500px-%s-%s.jpg" % (self.ownerid, self.photoid)
        )
        self.url = "https://www.500px.com%s" % (photo.get('url'))

    def run(self):
        img = self.photo.get('images')[0].get('url')
        if not img:
            logging.error("image url was empty for %s, skipping fav", self.url)
            return
        self.imgurl = img
        self.pull_image()

        self.meta = {
            'dt': arrow.get(
                self.photo.get('created_at',
                    arrow.utcnow().timestamp
                )
            ),
            'title': '%s' % shared.Pandoc('plain').convert(
                self.photo.get('name', '')
            ).rstrip(),
            'favorite-of': self.url,
            'tags': self.photo.get('tags', []),
            'geo': {
                'latitude': self.photo.get('latitude', ''),
                'longitude': self.photo.get('longitude', ''),
            },
            'author': {
                'name': self.photo.get('user').get('fullname', self.ownerid),
                'url': 'https://www.500px.com/%s' % (
                    self.photo.get('user').get('username', self.ownerid)
                ),
            },
        }
        c = "%s" % self.photo.get('description', '')
        self.content = shared.Pandoc('plain').convert(c)
        self.write_exif()

class DAFav(ImgFav):
    def __init__(self, fav):
        self.fav = fav
        self.deviationid = fav.get('deviationid')
        self.url = fav.get('url')
        self.title = fav.get('title', False) or self.deviationid
        self.author = self.fav.get('author').get('username')
        self.target = os.path.join(
            shared.config.get('archive', 'favorite'),
            "deviantart-%s-%s.jpg" % (
                shared.slugfname(self.title),
                shared.slugfname(self.author)
            )
        )
        self.imgurl = fav.get('content', {}).get('src')

    def run(self):
        self.pull_image()

        self.meta = {
            'dt': arrow.get(
                self.fav.get('published_time',
                    arrow.utcnow().timestamp
                )
            ),
            'title': '%s' % shared.Pandoc('plain').convert(self.title).rstrip(),
            'favorite-of': self.url,
            'tags': [t.get('tag_name') for t in self.fav.get('meta', {}).get('tags', [])],
            'author': {
                'name': self.author,
                'url': 'https://%s.deviantart.com' % (self.author),
            },
        }
        c = "%s" % self.fav.get('meta', {}).get('description', '')
        self.content = shared.Pandoc('plain').convert(c)
        self.write_exif()


class TumblrFav(object):
    def __init__(self, like):
        self.like = like
        self.blogname = like.get('blog_name')
        self.postid = like.get('id')
        self.target = os.path.join(
            shared.config.get('archive', 'favorite'),
            "tumblr-%s-%s.jpg" % (self.blogname, self.postid)
        )
        self.url = like.get('post_url')
        self.images = []

    @property
    def exists(self):
        return os.path.exists(self.target.replace('.jpg', '_0.jpg'))

    def run(self):
        content = "%s" % self.like.get('caption', '')
        title = self.like.get('summary', '').strip()
        if not len(title):
            title = self.like.get('slug', '').strip()
        if not len(title):
            title = shared.slugfname(self.like.get('post_url'))

        meta = {
            'dt': arrow.get(
                self.like.get('liked_timestamp',
                    self.like.get('date',
                        arrow.utcnow().timestamp
                    )
                )
            ),
            'title': title,
            'favorite-of': self.url,
            'tags': self.like.get('tags'),
            'author': {
                'name': self.like.get('blog_name'),
                'url': 'http://%s.tumblr.com' % self.like.get('blog_name')
            },
        }

        icntr = 0
        for p in self.like.get('photos', []):
            img = ImgFav()
            img.target = self.target.replace('.jpg', '_%d.jpg' % icntr)
            img.imgurl = p.get('original_size').get('url')
            img.content = content
            img.meta = meta
            img.pull_image()
            img.write_exif()
            icntr = icntr + 1


class Oauth2Flow(object):
    token_url = ''

    def __init__(self, service):
        self.service = service
        self.key = shared.config.get("api_%s" % service, 'api_key')
        self.secret = shared.config.get("api_%s" % service, 'api_secret')
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
        self.key = shared.config.get("api_%s" % service, 'api_key')
        self.secret = shared.config.get("api_%s" % service, 'api_secret')
        self.tokendb = shared.TokenDB()
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


if __name__ == '__main__':
    logging.basicConfig(level=10)

    flickr = FlickrFavs()
    flickr.run()

    fivehpx = FivehpxFavs()
    fivehpx.run()

    tumblr = TumblrFavs()
    tumblr.run()

    da = DAFavs()
    da.run()
