import glob
import shared
import os
import logging
import frontmatter

# remove the rest of the potential loggers
while len(logging.root.handlers) > 0:
    logging.root.removeHandler(logging.root.handlers[-1])

# --- set loglevel
logging.basicConfig(
    level=10,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

bookmarks = glob.glob('/web/petermolnar.net/petermolnar.net/content/bookmark/*.md')
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
    w = shared.wget(trueurl, dirname=f)
    w.archive()
