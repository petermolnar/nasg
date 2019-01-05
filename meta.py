__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2019, Peter Molnar"
__license__ = "apache-2.0"
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import re
import subprocess
import json
import os
import logging
import requests
import keys
import settings

from pprint import pprint

EXIFDATE = re.compile(
    r'^(?P<year>[0-9]{4}):(?P<month>[0-9]{2}):(?P<day>[0-9]{2})\s+'
    r'(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})$'
)

class CachedMeta(dict):
    def __init__(self, fpath):
        self.fpath = fpath

    @property
    def cfile(self):
        fname = os.path.basename(self.fpath)
        if fname  == 'index.md':
            fname = os.path.basename(os.path.dirname(self.fpath))

        return os.path.join(
            settings.paths.get('tmp', 'tmp'),
            "%s.%s.json" % (
                fname,
                self.__class__.__name__,
            )
        )

    @property
    def _is_cached(self):
        if os.path.exists(self.cfile):
            mtime = os.path.getmtime(self.fpath)
            ctime = os.path.getmtime(self.cfile)
            if ctime >= mtime:
                return True
        return False

    def _read(self):
        if not self._is_cached:
            self._call_tool()
            self._cache_update()
        else:
            self._cache_read()

    def _cache_update(self):
        with open(self.cfile, 'wt') as f:
            logging.debug(
                "writing cached meta file of %s to %s",
                self.fpath,
                self.cfile
            )
            f.write(json.dumps(self, indent=4, sort_keys=True))

    def _cache_read(self):
        with open(self.cfile, 'rt') as f:
            data = json.loads(f.read())
            for k, v in data.items():
                self[k] = v

class GoogleClassifyText(CachedMeta):
    def __init__(self, fpath, txt, lang='en'):
        self.fpath = fpath
        self.txt = txt
        self.lang = lang
        self._read()

    def _call_tool(self):
        params = {
            "document": {
                "type": "PLAIN_TEXT",
                "content": self.txt,
                "language": self.lang,
            }
        }

        url = "https://language.googleapis.com/v1beta2/documents:classifyText?key=%s" % (
            keys.gcloud.get('key')
        )
        logging.info(
            "calling Google classifyText for %s",
            self.fpath
        )
        r = requests.post(url, json=params)
        try:
            resp = r.json()
            for cat in resp.get('categories', []):
                self[cat.get('name')] = cat.get('confidence')
        except Exception as e:
            logging.error(
                'failed to call Google Vision API on: %s, reason: %s',
                self.fpath,
                e
            )

class GoogleVision(CachedMeta):
    def __init__(self, fpath, imgurl):
        self.fpath = fpath
        self.imgurl = imgurl
        self._read()

    @property
    def response(self):
        if 'responses' not in self:
            return {}
        if not len(self['responses']):
            return {}
        if 'labelAnnotations' not in self['responses'][0]:
            return {}
        return self['responses'][0]

    @property
    def tags(self):
        tags = []

        if 'labelAnnotations' in self.response:
            for label in self.response['labelAnnotations']:
                tags.append(label['description'])

        if 'webDetection' in self.response:
            if 'webEntities' in self.response['webDetection']:
                for label in self.response['webDetection']['webEntities']:
                    tags.append(label['description'])
        return tags

    @property
    def landmark(self):
        landmark = None
        if 'landmarkAnnotations' in self.response:
            if len(self.response['landmarkAnnotations']):
                match = self.response['landmarkAnnotations'].pop()
                landmark = {
                    'name': match['description'],
                    'latitude': match['locations'][0]['latLng']['latitude'],
                    'longitude': match['locations'][0]['latLng']['longitude']
                }
        return landmark

    @property
    def onlinecopies(self):
        copies = []
        if 'webDetection' in self.response:
            if 'pagesWithMatchingImages' in self.response['webDetection']:
                for match in self.response['webDetection']['pagesWithMatchingImages']:
                    copies.append(match['url'])
        return copies

    def _call_tool(self):
        params = {
            "requests": [{
                "image": {"source": {"imageUri": self.imgurl}},
                "features": [
                    {
                      "type": "LANDMARK_DETECTION",
                    },
                    {
                      "type": "WEB_DETECTION",
                    },
                    {
                      "type": "LABEL_DETECTION",
                    }
                ]
            }]
        }

        url = "https://vision.googleapis.com/v1/images:annotate?key=%s" % (
            keys.gcloud.get('key')
        )
        logging.info(
            "calling Google Vision for %s",
            self.fpath
        )
        r = requests.post(url, json=params)
        try:
            resp = r.json()
            for k, v in resp.items():
                self[k] = v
        except Exception as e:
            logging.error(
                'failed to call Google Vision API on: %s, reason: %s',
                self.fpath,
                e
            )

class Exif(CachedMeta):
    def __init__(self, fpath):
        self.fpath = fpath
        self._read()

    def _call_tool(self):
        """
        Why like this: the # on some of the params forces exiftool to
        display values like decimals, so the latitude / longitude params
        can be used and parsed in a sane way

        If only -json is passed, it gets everything nicely, but in the default
        format, which would require another round to parse

        """
        cmd = (
            "exiftool",
            '-sort',
            '-json',
            '-MIMEType',
            '-FileType',
            '-FileName',
            '-FileSize#',
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
            '-Copyright',
            '-Artist',
            self.fpath
        )

        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate()
        if stderr:
            raise OSError("Error reading EXIF:\n\t%s\n\t%s", cmd, stderr)

        exif = json.loads(stdout.decode('utf-8').strip()).pop()
        if 'ReleaseDate' in exif and 'ReleaseTime' in exif:
            exif['DateTimeRelease'] = "%s %s" % (
                exif.get('ReleaseDate'), exif.get('ReleaseTime')[:8]
            )
            del(exif['ReleaseDate'])
            del(exif['ReleaseTime'])

        for k, v in exif.items():
            self[k] = self.exifdate2rfc(v)

    def exifdate2rfc(self, value):
        """ converts and EXIF date string to RFC 3339 format

        :param value: EXIF date (2016:05:01 00:08:24)
        :type arg1: str
        :return: RFC 3339 string with UTC timezone 2016-05-01T00:08:24+00:00
        :rtype: str
        """
        if not isinstance(value, str):
            return value
        match = EXIFDATE.match(value)
        if not match:
            return value
        return "%s-%s-%sT%s+00:00" % (
            match.group('year'),
            match.group('month'),
            match.group('day'),
            match.group('time')
        )
