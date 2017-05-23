import os
import hashlib
import logging
import glob
from webmentiontools.send import WebmentionSend
import requests
import json

class WebmentionDB(object):
    dbpath = glob.WEBMENTIONDB

    def __init__(self):
        self.sent = {}
        self._loaddb()

    def _loaddb(self):
        if os.path.isfile(self.dbpath):
            logging.info("loading pinged database")
            with open(self.dbpath, 'r') as db:
                self.sent = json.loads(db.read())

    def _dumpdb(self):
        with open(self.dbpath, "w") as db:
            logging.info("writing pinged database")
            db.write(json.dumps(self.sent, indent=4, sort_keys=True))
            db.close()

    def _refreshdb(self):
        self._dumpdb()
        self._loaddb()

    def __getitem__(self, key):
        r = {}
        for i in self.sent.items():
            h, data = i
            if data['source'] == key:
                r[data['target']] = {
                    'time': data['time'],
                    'response': data['response']
                }

        return r


    def __len__(self):
        return len(self.sent)


    def posses(self, key):
        r = []
        for i in self.sent.items():
            h, data = i

            if data['source'] != key:
                continue

            if not len(data['response']):
                continue

            if 'url' not in data['response']:
                continue

            r.append(data['response']['url'])

        return r


    def ping(self, source, target, time=0, posse=False):
        resp = {}
        source = source.strip()
        target = target.strip()

        h = source + target + "%i" % (int(time))
        h = h.encode('utf-8')
        h = hashlib.sha1(h).hexdigest()
        if h in self.sent.keys():
            logging.debug("already pinged: %s" % (target))
            return True

        logging.debug("pinging: %s" % (target))

        wm = WebmentionSend(source, target)
        if hasattr(wm, 'response'):
            resp = wm.response

        # fire and forget archive.org call
        try:
            verify = requests.get(
                '%s%s' % ('https://web.archive.org/save/', target),
                allow_redirects=False,
                timeout=30,
            )
        except:
            pass

        self.sent[h] = {
            'source': source,
            'target': target,
            'time': time,
            'response': resp
        }

        self._refreshdb()