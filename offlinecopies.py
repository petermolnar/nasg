import glob
import os
import logging
import json
import frontmatter
import requests
from urllib.parse import urlparse, urlunparse
import shared


# remove the rest of the potential loggers
while len(logging.root.handlers) > 0:
    logging.root.removeHandler(logging.root.handlers[-1])

# --- set loglevel
logging.basicConfig(
    level=10,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def find_realurl(url):
    headers = requests.utils.default_headers()
    headers.update({
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:52.0) Gecko/20100101 Firefox/52.0',
    })

    try:
        r = requests.get(
            url,
            allow_redirects=True,
            timeout=60,
            headers=headers
        )
    except Exception as e:
        logging.error('getting real url failed: %s', e)
        return (None, 400)

    finalurl = list(urlparse(r.url))
    finalurl[4] = '&'.join(
        [x for x in finalurl[4].split('&') if not x.startswith('utm_')])
    finalurl = urlunparse(finalurl)

    return (finalurl, r.status_code)

def find_archiveorgurl(url):
    url, status = find_realurl(url)
    if status == requests.codes.ok:
        return url

    try:
        a = requests.get(
            "http://archive.org/wayback/available?url=%s" % url,
        )
    except Exception as e:
        logging.error('Failed to fetch archive.org availability for %s' % url)
        return None

    if not a:
        logging.error('empty archive.org availability for %s' % url)
        return None

    try:
        a = json.loads(a.text)
        aurl = a.get(
            'archived_snapshots', {}
        ).get(
            'closest', {}
        ).get(
            'url', None
        )
        if aurl:
            logging.debug("found %s in archive.org for %s", aurl, url)
            return aurl
    except Exception as e:
        logging.error("archive.org parsing failed: %s", e)

    return None


class wget(shared.CMDLine):
    def __init__(self, url, dirname=None):
        super().__init__('wget')
        self.url = url
        self.slug = dirname or slugfname(self.url)
        self.saveto = os.path.join(
            config.get('source', 'offlinecopiesdir'),
            self.slug
        )

    def archive(self):
        cmd = (
            self.executable,
            '-e',
            'robots=off',
            '--timeout=360',
            '--no-clobber',
            '--no-directories',
            '--adjust-extension',
            '--span-hosts',
            '--wait=1',
            '--random-wait',
            '--convert-links',
            #'--backup-converted',
            '--page-requisites',
            '--directory-prefix=%s' % self.saveto,
            "%s" % self.url
        )
        logging.debug('getting URL %s with wget', self.url)
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate()
        if stderr:
            logging.error(
                "Error getting URL:\n\t%s\n\t%s",
                cmd,
                stderr
            )
        return stdout.decode('utf-8').strip()



bookmarks = glob.glob(shared.config.get('dynamic', 'bookmarks'), '*.md')
bm = {}
for b in bookmarks:
    with open(b, 'rt') as f:
        fm = frontmatter.loads(f.read())
        if not fm.metadata.get('bookmark-of'):
            continue
        bm[b] = fm

for fname, fm in bm.items():
    logging.info('dealing with %s', fname)
    url = fm.metadata.get('bookmark-of')
    f, ext = os.path.splitext(os.path.basename(fname))
    p = os.path.join(
        shared.config.get('source', 'offlinecopiesdir'),
        f
    )
    if os.path.isdir(p):
        continue

    trueurl = shared.find_archiveorgurl(url)
    w = wget(trueurl, dirname=f)
    w.archive()

    # this is to skip the failed ones next time
    if not os.path.isdir(p):
        os.mkdir(p)
