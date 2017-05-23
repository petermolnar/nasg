from whoosh import fields
from whoosh import analysis
from whoosh import index
import tempfile
import atexit
import shutil
import nasg.config as config

class SearchIndex(object):
    schema = fields.Schema(
        url=fields.ID(
            stored=True,
        ),
        title=fields.TEXT(
            stored=True,
            analyzer=analysis.FancyAnalyzer(
            )
        ),
        date=fields.DATETIME(
            stored=True,
            sortable=True
        ),
        content=fields.TEXT(
            stored=True,
            analyzer=analysis.FancyAnalyzer(
            )
        ),
        tags=fields.TEXT(
            stored=True,
            analyzer=analysis.KeywordAnalyzer(
                lowercase=True,
                commas=True
            )
        ),
        weight=fields.NUMERIC(
            sortable=True
        ),
        img=fields.TEXT(
            stored=True
        )
    )


    def __init__(self):
        self.tmp = tempfile.mkdtemp('whooshdb_', dir=tempfile.gettempdir())
        self.ix = index.create_in(self.tmp, self.schema)
        atexit.register(self.cleanup)


    def add(self, vars):
        ix = self.ix.writer()
        ix.add_document(
            title=vars['title'],
            url=vars['url'],
            content=vars['content'],
            date=vars['published'],
            tags=vars['tags'],
            weight=1,
            img=vars['img']
        )
        ix.commit()


    def cleanup(self):
        if not os.path.exists(self.tmp):
            return

        logging.warning("cleaning up tmp whoosh")
        shutil.rmtree(self.tmp)


    def save(self):
        logging.info("deleting old searchdb")
        shutil.rmtree(config.SEARCHDB)
        logging.info("moving new searchdb")
        shutil.move(self.tmp, config.SEARCHDB)