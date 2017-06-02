import configparser
import os
import re
import glob
import logging
import subprocess
from whoosh import fields
from whoosh import analysis

def __expandconfig(config):
    """ add the dirs to the config automatically """
    basepath = os.path.expanduser(config.get('common','base'))
    config.set('common', 'basedir', basepath)
    for section in ['source', 'target']:
        for option in config.options(section):
            opt = config.get(section, option)
            config.set(section, "%sdir" % option, os.path.join(basepath,opt))
    config.set('target', 'filesdir', os.path.join(
        config.get('target', 'builddir'),
        config.get('source', 'files'),
    ))
    return config

ARROWISO = 'YYYY-MM-DDTHH:mm:ssZ'
STRFISO = '%Y-%m-%dT%H:%M:%S%z'

URLREGEX = re.compile(
    r'\s+https?\:\/\/?[a-zA-Z0-9\.\/\?\:@\-_=#]+'
    r'\.[a-zA-Z0-9\.\/\?\:@\-_=#]*'
)

EXIFREXEG = re.compile(
    r'^(?P<year>[0-9]{4}):(?P<month>[0-9]{2}):(?P<day>[0-9]{2})\s+'
    r'(?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})$'
)

MDIMGREGEX = re.compile(
    r'(!\[(.*)\]\((?:\/(?:files|cache)'
    r'(?:\/[0-9]{4}\/[0-9]{2})?\/(.*\.(?:jpe?g|png|gif)))'
    r'(?:\s+[\'\"]?(.*?)[\'\"]?)?\)(?:\{(.*?)\})?)'
, re.IGNORECASE)

schema = fields.Schema(
    url=fields.ID(
        stored=True,
        unique=True
    ),
    title=fields.TEXT(
        stored=True,
        analyzer=analysis.FancyAnalyzer()
    ),
    date=fields.DATETIME(
        stored=True,
        sortable=True
    ),
    content=fields.TEXT(
        stored=True,
        analyzer=analysis.FancyAnalyzer()
    ),
    fuzzy=fields.NGRAMWORDS(
        tokenizer=analysis.NgramTokenizer(4)
    ),
    tags=fields.TEXT(
        stored=True,
        analyzer=analysis.KeywordAnalyzer(
            lowercase=True,
            commas=True
        ),
    ),
    weight=fields.NUMERIC(
        sortable=True
    ),
    img=fields.TEXT(
        stored=True
    ),
    mtime=fields.NUMERIC(
        stored=True
    )
)

config = configparser.ConfigParser(
    interpolation=configparser.ExtendedInterpolation(),
    allow_no_value=True
)
config.read('config.ini')
config = __expandconfig(config)

class CMDLine(object):
    def __init__(self, executable):
        self.executable = self._which(executable)
        if self.executable is None:
            raise OSError('No %s found in PATH!' % executable)
            return

    @staticmethod
    def _which(name):
        for d in os.environ['PATH'].split(':'):
            which = glob.glob(os.path.join(d, name), recursive=True)
            if which:
                return which.pop()
        return None

    def __enter__(self):
        self.process = subprocess.Popen(
            [self.executable, "-stay_open", "True",  "-@", "-"],
            universal_newlines=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return self

    def  __exit__(self, exc_type, exc_value, traceback):
        self.process.stdin.write("-stay_open\nFalse\n")
        self.process.stdin.flush()

    def execute(self, *args):
        args = args + ("-execute\n",)
        self.process.stdin.write(str.join("\n", args))
        self.process.stdin.flush()
        output = ""
        fd = self.process.stdout.fileno()
        while not output.endswith(self.sentinel):
            output += os.read(fd, 4096).decode('utf-8', errors='ignore')
        return output[:-len(self.sentinel)]

class Pandoc(CMDLine):
    """ Pandoc command line call with piped in- and output """
    def __init__(self, md2html=True):
        super().__init__('pandoc')
        if md2html:
            self.i = "markdown+" + "+".join([
                'backtick_code_blocks',
                'auto_identifiers',
                'fenced_code_attributes',
                'definition_lists',
                'grid_tables',
                'pipe_tables',
                'strikeout',
                'superscript',
                'subscript',
                'markdown_in_html_blocks',
                'shortcut_reference_links',
                'autolink_bare_uris',
                'raw_html',
                'link_attributes',
                'header_attributes',
                'footnotes',
            ])
            self.o = 'html5'
        else:
            self.o = "markdown-" + "-".join([
                'raw_html',
                'native_divs',
                'native_spans',
            ])
            self.i = 'html'

    def convert(self, text):
        cmd = (
            self.executable,
            '-o-',
            '--from=%s' % self.i,
            '--to=%s' % self.o
        )
        logging.debug('converting string with Pandoc')
        p = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate(input=text.encode())
        if stderr:
            logging.error(
                "Error during pandoc covert:\n\t%s\n\t%s",
                cmd,
                stderr
            )
        return stdout.decode('utf-8').strip()
