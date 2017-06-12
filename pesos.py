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

from pprint import pprint

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
        return False
        #return os.path.isfile(self.target)

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

    def saveimg(self, url):
        target = self.imgtarget
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

class Favs(object):
    def __init__(self, confgroup):
        self.confgroup = confgroup
        self.url = shared.config.get(confgroup, 'fav_api')

    @property
    def lastpulled(self):
        return 0

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
            'per_page': 500,
            'format': 'json',
            'nojsoncallback': '1',
            'min_fave_date': self.lastpulled
        }

    def run(self):
        r = requests.get(self.url,params=self.params)
        js = json.loads(r.text)
        for photo in js.get('photos', {}).get('photo', []):
            fav = FlickrFav(photo)
            fav.run()
            fav.write()


class FivehpxFavs(Favs):
    def __init__(self):
        super(FivehpxFavs, self).__init__('500px')
        self.params = {
            'consumer_key': shared.config.get('500px', 'api_key'),
            'rpp': 100,
            'image_size': 4,
            'include_tags': 1,
            'include_geo': 1
        }

    def run(self):
        r = requests.get(self.url,params=self.params)
        js = json.loads(r.text)
        for photo in js.get('photos', []):
            fav = FivehpxFav(photo)
            if not fav.exists:
                fav.run()
                fav.write()


if __name__ == '__main__':
    while len(logging.root.handlers) > 0:
        logging.root.removeHandler(logging.root.handlers[-1])

    logging.basicConfig(
        level=20,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    flickr = FlickrFavs()
    flickr.run()

    hn = HNBookmarks()
    hn.run()

    fivehpx = FivehpxFavs()
    fivehpx.run()
