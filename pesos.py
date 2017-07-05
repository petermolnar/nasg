#!/usr/bin/env python3

import json
import os
import hashlib
import glob
import frontmatter
import requests
import shared
import logging
import re
import shutil
import arrow
import bs4
from slugify import slugify
import oauth
import argparse


class Bookmark(object):
    def __init__(self, title, url, fname=None):
        self.fm = frontmatter.loads('')
        fname = fname or slugify(title)
        self.fname = "%s.md" % fname
        self.target = os.path.join(
            shared.config.get('source', 'contentdir'),
            shared.config.get('source', 'bookmarks'),
            self.fname
        )
        self.fm.metadata = {
            'published': arrow.utcnow().format(shared.ARROWISO),
            'title': title,
            'bookmark-of': url,
        }

    def write(self):
        logging.info('saving bookmark to %s', self.target)
        with open(self.target, 'wt') as t:
            t.write(frontmatter.dumps(self.fm))

class HNBookmarks(object):
    prefix = 'hn-'
    def __init__(self):
        self.url = 'https://news.ycombinator.com/favorites?id=%s' % (
            shared.config.get('hackernews', 'user_id')
        )

    @property
    def existing(self):
        if hasattr(self, '_existing'):
            return self._existing

        d = os.path.join(
            shared.config.get('source', 'contentdir'),
            "*",
            "%s*.md" % self.prefix
        )
        files = reversed(sorted(glob.glob(d)))
        self._existing = [
            os.path.basename(f.replace(self.prefix, '').replace('.md', ''))
            for f in files
        ]

        return self._existing

    def run(self):
        r = requests.get(self.url)
        soup = bs4.BeautifulSoup(r.text, "html5lib")
        rows = soup.find_all('tr', attrs={'class':'athing' })
        for row in rows:
            rid = row.get('id')
            if rid in self.existing:
                continue

            link = row.find('a', attrs={'class':'storylink' })
            url = link.get('href')
            title = " ".join(link.contents)
            fname = "%s%s" % (self.prefix, rid)

            bookmark = Bookmark(title, url, fname)
            bookmark.write()

class Fav(object):
    def __init__(self):
        self.arrow = arrow.utcnow()
        self.fm = frontmatter.loads('')

    @property
    def target(self):
        return os.path.join(
            shared.config.get('source', 'contentdir'),
            shared.config.get('source', 'favs'),
            self.fname
        )

    @property
    def exists(self):
        return os.path.isfile(self.target)

    @property
    def imgname(self):
        # the _ is to differentiate between my photos, where the md and jpg name is the same, and favs
        return self.fname.replace('.md', '_.jpg')

    @property
    def imgtarget(self):
        return os.path.join(
            shared.config.get('source', 'filesdir'),
            self.imgname
        )

    def saveimg(self, url, target=None):
        target = target or self.imgtarget
        if os.path.isfile(target):
            logging.error("%s already exists, refusing to overwrite", target)
            return

        logging.info("pulling image %s to files", url)
        r = requests.get(url, stream=True)
        if r.status_code == 200:
            with open(target, 'wb') as f:
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)

    def write(self):
        logging.info('saving fav to %s', self.target)
        with open(self.target, 'wt') as t:
            t.write(frontmatter.dumps(self.fm))
        os.utime(self.target, (self.arrow.timestamp, self.arrow.timestamp))


class PinterestFav(Fav):
    def __init__(self, url):
        super(PinterestFav, self).__init__()
        self.url = url
        self.fname = "pinterest-%s.md" % (list(filter(None, url.split('/')))[-1])

    def run(self):
        try:
            r = requests.get(self.url)
            soup = bs4.BeautifulSoup(r.text, 'lxml')
            ld = json.loads(soup.find('script', type='application/ld+json').text)
            imgurl = ld.get('image')
            self.saveimg(imgurl)

            self.fm.metadata = {
                'published': arrow.get(
                    ld.get('datePublished', arrow.utcnow().timestamp)
                ).format(shared.ARROWISO),
                'title': ld.get('headline', self.url),
                'favorite-of': self.url,
                'image': self.imgname
            }
            content = ld.get('articleBody', '')
            content = shared.Pandoc(False).convert(content)
            self.fm.content = content

        except Exception as e:
            logging.error('saving pinterest fav %s failed: %s', self.url, e)
            return


class FlickrFav(Fav):
    def __init__(self, photo):
        super(FlickrFav, self).__init__()
        self.photo = photo
        self.ownerid = photo.get('owner')
        self.photoid = photo.get('id')
        self.fname = "flickr-%s-%s.md" % (self.ownerid, self.photoid)
        self.url = "https://www.flickr.com/photos/%s/%s" % (self.ownerid, self.photoid)

    def run(self):
        img = self.photo.get('url_b', self.photo.get('url_z', False))
        if not img:
            logging.error("image url was empty for %s, skipping fav", self.url)
            return

        self.saveimg(img)
        self.arrow = arrow.get(
            self.photo.get('date_faved', arrow.utcnow().timestamp)
        )
        self.fm.metadata = {
            'published': self.arrow.format(shared.ARROWISO),
            'title': '%s' % self.photo.get('title', self.fname),
            'favorite-of': self.url,
            'flickr_tags': self.photo.get('tags', '').split(' '),
            'geo': {
                'latitude': self.photo.get('latitude', ''),
                'longitude': self.photo.get('longitude', ''),
            },
            'author': {
                'name': self.photo.get('owner_name'),
                'url': 'https://www.flickr.com/people/%s' % (
                    self.photo.get('owner')
                ),
            },
            'image': self.imgname
        }

        content = self.photo.get('description', {}).get('_content', '')
        content = shared.Pandoc(False).convert(content)
        self.fm.content = content


class FivehpxFav(Fav):
    def __init__(self, photo):
        super(FivehpxFav, self).__init__()
        self.photo = photo
        self.ownerid = photo.get('user_id')
        self.photoid = photo.get('id')
        self.fname = "500px-%s-%s.md" % (self.ownerid, self.photoid)
        self.url = "https://www.500px.com%s" % (photo.get('url'))

    def run(self):
        img = self.photo.get('images')[0].get('url')
        if not img:
            logging.error("image url was empty for %s, skipping fav", self.url)
            return

        self.saveimg(img)
        self.arrow = arrow.get(
            self.photo.get('created_at', arrow.utcnow().timestamp)
        )
        self.fm.metadata = {
            'published': self.arrow.format(shared.ARROWISO),
            'title': '%s' % self.photo.get('name', self.fname),
            'favorite-of': self.url,
            'fivehpx_tags': self.photo.get('tags', []),
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
            'image': self.imgname
        }

        content = self.photo.get('description', '')
        if content:
            content = shared.Pandoc(False).convert(content)
        else:
            content = ''
        self.fm.content = content


class TumblrFav(Fav):
    def __init__(self, like):
        super(TumblrFav, self).__init__()
        self.like = like
        self.blogname = like.get('blog_name')
        self.postid = like.get('id')
        self.fname = "tumblr-%s-%s.md" % (self.blogname, self.postid)
        self.url = like.get('post_url')
        self.images = []

    def run(self):
        icntr = 0
        for p in self.like.get('photos', []):
            i = p.get('original_size').get('url')
            logging.debug('parsing image %s', i)
            n = self.fname.replace('.md', '_%d.jpg' % icntr)
            self.images.append(n)
            nt = os.path.join(
                shared.config.get('source', 'filesdir'),
                n
            )
            self.saveimg(i, nt)
            icntr = icntr + 1

        self.arrow = arrow.get(
            self.like.get('liked_timestamp',
                self.like.get('date',
                    arrow.utcnow().timestamp
                )
            )
        )

        self.fm.content = self.like.get('caption', '')

        title = self.like.get('summary', '').strip()
        if not len(title):
            title = self.like.get('slug', '').strip()
        if not len(title):
            title = shared.slugfname(self.like.get('post_url'))

        self.fm.metadata = {
            'published': self.arrow.format(shared.ARROWISO),
            'title': title,
            'favorite-of': self.url,
            'tumblr_tags': self.like.get('tags'),
            'author': {
                'name': self.like.get('blog_name'),
                'url': 'http://%s.tumblr.com' % self.like.get('blog_name')
            },
            'images': self.images
        }


class DAFav(Fav):
    def __init__(self, fav):
        super(DAFav, self).__init__()
        self.fav = fav
        self.deviationid = fav.get('deviationid')
        self.url = fav.get('url')
        self.title = fav.get('title', False) or self.deviationid
        self.author = self.fav.get('author').get('username')
        self.fname = "deviantart-%s-by-%s.md" % (
            slugify(self.title), slugify(self.author)
        )
        self.image = fav.get('content', {}).get('src')

    def run(self):
        self.saveimg(self.image)

        self.arrow = arrow.get(
            self.fav.get('published_time', arrow.utcnow().timestamp)
        )

        self.fm.metadata = {
            'published': self.arrow.format(shared.ARROWISO),
            'title': '%s' % self.title,
            'favorite-of': self.url,
            'da_tags': [t.get('tag_name') for t in self.fav.get('meta', {}).get('tags', [])],
            'author': {
                'name': self.author,
                'url': 'https://%s.deviantart.com' % (self.author),
            },
            'image': self.imgname
        }

        content = self.fav.get('meta', {}).get('description', '')
        content = shared.Pandoc(False).convert(content)
        self.fm.content = content


class Favs(object):
    def __init__(self, confgroup):
        self.confgroup = confgroup
        self.url = shared.config.get(confgroup, 'fav_api')

    @property
    def lastpulled(self):
        mtime = 0
        d = os.path.join(
            shared.config.get('source', 'contentdir'),
            shared.config.get('source', 'favs'),
            "%s-*.md" % self.confgroup
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
    def __init__(self):
        super(FlickrFavs, self).__init__('flickr')
        self.params = {
            'method': 'flickr.favorites.getList',
            'api_key': shared.config.get('flickr', 'api_key'),
            'user_id': shared.config.get('flickr', 'user_id'),
            'extras': 'description,geo,tags,url_z,url_b,owner_name,date_upload',
            'per_page': 500, # maximim
            'format': 'json',
            'nojsoncallback': '1',
            'min_fave_date': self.lastpulled
        }

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
                fav.write()


class FivehpxFavs(Favs):
    def __init__(self):
        super(FivehpxFavs, self).__init__('500px')
        self.params = {
            'consumer_key': shared.config.get('500px', 'api_key'),
            'rpp': 100, # maximum
            'image_size': 4,
            'include_tags': 1,
            'include_geo': 1,
            'sort': 'created_at',
            'sort_direction': 'desc'
        }

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
                fav.write()


class TumblrFavs(Favs):
    def __init__(self):
        super(TumblrFavs, self).__init__('tumblr')
        self.oauth = oauth.TumblrOauth()
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
                fav.write()


class DAFavs(Favs):
    def __init__(self):
        from pprint import pprint
        super(DAFavs, self).__init__('deviantart')
        self.oauth = oauth.DAOauth()
        self.params = {
            'limit': 24,
            'mature_content': 'true',
            'username': shared.config.get('deviantart', 'username')
        }
        self.likes = []

    def getpaged(self, offset):
        self.params.update({'offset': offset})
        r = self.oauth.request(
            self.url,
            self.params
        )
        return json.loads(r.text)

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
        if 'True' == q or 'true' == q:
            return True
        return False

    def run(self):
        r = self.oauth.request(
            self.url,
            self.params
        )

        js = json.loads(r.text)
        favs = js.get('results', [])
        has_more = js.get('has_more')
        offset = js.get('next_offset')
        while True == has_more:
            logging.debug('iterating over DA results with offset %d', offset)
            paged = self.getpaged(offset)
            favs = favs + paged.get('results', [])
            has_more = paged.get('has_more')
            n = paged.get('next_offset')
            if n:
                offset = offset + n

        self.favs = favs
        for fav in self.favs:
            f = DAFav(fav)
            if f.exists:
                continue

            f.fav.update({'meta': self.getsinglemeta(fav.get('deviationid'))})
            f.run()
            f.write()

if __name__ == '__main__':

    parser = argparse.ArgumentParser(description='Parameters for NASG')
    parser.add_argument(
        '--loglevel',
        default='error',
        help='change loglevel'
    )

    params = vars(parser.parse_args())

    while len(logging.root.handlers) > 0:
        logging.root.removeHandler(logging.root.handlers[-1])

    logging.basicConfig(
        level=shared.LLEVEL[params.get('loglevel')],
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    flickr = FlickrFavs()
    flickr.run()

    hn = HNBookmarks()
    hn.run()

    fivehpx = FivehpxFavs()
    fivehpx.run()

    tumblr = TumblrFavs()
    tumblr.run()

    da = DAFavs()
    da.run()
