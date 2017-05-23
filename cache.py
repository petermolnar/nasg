import os
import json
import hashlib
import logging
import glob

class Cached(object):
    def __init__(self, hash='', text='', stime=0):

        if not os.path.isdir(glob.CACHE):
            os.mkdir(glob.CACHE)

        if hash:
            self._hbase = hash
        elif text:
            self._hbase = hashlib.sha1(text.encode('utf-8')).hexdigest()
        else:
            print("No identifier passed for Cached")
            raise

        self._cpath = os.path.join(glob.CACHE, self._hbase)
        self._stime = stime

        if os.path.isfile(self._cpath):
            self._ctime = os.stat(self._cpath)
        else:
            self._ctime = None

    def get(self):
        if not glob.CACHEENABLED:
            return None

        cached = ''
        if os.path.isfile(self._cpath):
            if self._stime and self._stime.st_mtime == self._ctime.st_mtime:
                logging.debug("Cache exists at %s; using it" % (self._cpath ))
                with open(self._cpath, 'r') as c:
                    cached = c.read()
                    c.close()
            # invalidate old
            elif self._stime and self._stime.st_mtime > self._ctime.st_mtime:
                logging.debug("invalidating cache at %s" % (self._cpath ))
                os.remove(self._cpath)

        return cached

    def set(self, content):
        if not glob.CACHEENABLED:
            return None

        with open(self._cpath, "w") as c:
            logging.debug("writing cache to %s" % (self._cpath ))
            c.write(content)
            c.close()
        if self._stime:
            os.utime(self._cpath, (self._stime.st_mtime, self._stime.st_mtime ))