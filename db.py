import os
import json
import sqlite3
import glob
import shared
import logging

class TokenDB(object):
    def __init__(self, uuid='tokens'):
        self.db = shared.config.get('var', 'tokendb')
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

    def get_token(self, token):
        return self.tokens.get(token, None)

    def get_service(self, service):
        token = self.tokens.get(service, None)
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

class SearchDB(object):
    tmplfile = 'Search.html'

    def __init__(self):
        self.db = sqlite3.connect(
            "%s" % shared.config.get('var', 'searchdb')
        )

        cursor = self.db.cursor()
        cursor.execute('''CREATE VIRTUAL TABLE IF NOT EXISTS data USING FTS5(
                id,
                corpus,
                mtime,
                url,
                category,
                title
            )''')
        self.db.commit()

    def __exit__(self):
        self.finish()

    def finish(self):
        self.db.close()

    def append(self, id, corpus, mtime, url, category, title):
        mtime = int(mtime)
        logging.debug("adding %s to searchdb", id)
        cursor = self.db.cursor()
        cursor.execute('''DELETE FROM data WHERE id=?''', (id,))
        cursor.execute('''INSERT OR IGNORE INTO data (id, corpus, mtime, url, category, title) VALUES (?,?,?,?,?,?);''', (
            id,
            corpus,
            mtime,
            url,
            category,
            title
        ))
        self.db.commit()

    def is_uptodate(self, fname, mtime):
        mtime = int(mtime)
        ret = {}
        cursor = self.db.cursor()
        cursor.execute('''SELECT mtime
            FROM data
            WHERE id = ? AND mtime = ?''',
            (fname,mtime)
        )
        rows = cursor.fetchall()

        if len(rows):
            logging.debug("%s is up to date in searchdb", fname)
            return True

        logging.debug("%s is out of  date in searchdb", fname)
        return False

    def search_by_query(self, query):
        ret = {}
        cursor = self.db.cursor()
        cursor.execute('''SELECT
            id, category, url, title, highlight(data, 0, '<strong>', '</strong>') corpus
            FROM data
            WHERE data MATCH ?
            ORDER BY category, rank;''', (query,))
        rows = cursor.fetchall()
        for r in rows:
            r = {
                'id': r[0],
                'category': r[1],
                'url': r[2],
                'title': r[3],
                'txt': r[4],
            }

            category = r.get('category')
            if category not in ret:
                ret.update({category: {}})


            maybe_fpath = os.path.join(
                shared.config.get('dirs', 'content'),
                category,
                "%s.*" % r.get('id')
            )
            #fpath = glob.glob(maybe_fpath).pop()
            ret.get(category).update({
                r.get('id'): {
                    #'fpath': fpath,
                    'url': r.get('url'),
                    'title': r.get('title'),
                    'txt': r.get('txt')
                }
            })
        return ret


    def cli(self, query):
        results = self.search_by_query(query)
        for c, items in sorted(results.items()):
            print("%s:" % c)
            for fname, data in sorted(items.items()):
                print("  %s" % data.get('fpath'))
                print("  %s" % data.get('url'))
                print("")

    def html(self, query):
        tmplvars = {
            'results': self.search_by_query(query),
            'term': query
        }
        return shared.j2.get_template(self.tmplfile).render(tmplvars)


class WebmentionQueue(object):
    def __init__(self):
        self.db = sqlite3.connect(
            "%s" % shared.config.get('var', 'webmentiondb')
        )

        cursor = self.db.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS `archive` (
            `id` INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
            `received` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `processed` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `source` TEXT NOT NULL,
            `target` TEXT NOT NULL
        );''');

        cursor.execute('''CREATE TABLE IF NOT EXISTS `queue` (
            `id` INTEGER PRIMARY KEY AUTOINCREMENT UNIQUE,
            `timestamp` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            `source` TEXT NOT NULL,
            `target` TEXT NOT NULL
        );''');
        self.db.commit()

    def __exit__(self):
        self.finish()

    def finish(self):
        self.db.close()

    def queue(self, source, target):
        cursor = self.db.cursor()
        cursor.execute(
            '''INSERT INTO queue (source,target) VALUES (?,?);''', (
                source,
                target
            )
        )
        self.db.commit()
