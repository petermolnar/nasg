__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2019, Peter Molnar"
__license__ = "apache-2.0"
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import subprocess
import logging
from tempfile import gettempdir
import hashlib
import os
import settings

class Pandoc(str):
    in_format = 'html'
    in_options = []
    out_format = 'plain'
    out_options = []
    columns = None

    @property
    def hash(self):
        return str(hashlib.sha1(self.source.encode()).hexdigest())

    @property
    def cachefile(self):
        return os.path.join(
            settings.tmpdir,
            "%s_%s.pandoc" % (
                self.__class__.__name__,
                self.hash
            )
        )

    @property
    def cache(self):
        if not os.path.exists(self.cachefile):
            return False
        with open(self.cachefile, 'rt') as f:
            self.result = f.read()
            return True

    def __init__(self, text):
        self.source = text
        if self.cache:
            return
        conv_to = '--to=%s' % (self.out_format)
        if (len(self.out_options)):
            conv_to = '%s+%s' % (
                conv_to,
                '+'.join(self.out_options)
            )

        conv_from = '--from=%s' % (self.in_format)
        if (len(self.in_options)):
            conv_from = '%s+%s' % (
                conv_from,
                '+'.join(self.in_options)
            )
    
        is_pandoc_version2 = False
        try:
            version = subprocess.check_output(['pandoc', '-v'])
            if version.startswith(b'pandoc 2'):
                is_pandoc_version2 = True
        except OSError:
            print("Error: pandoc is not installed!")
        
        cmd = [
            'pandoc',
            '-o-',
            conv_to,
            conv_from,
            '--no-highlight'
        ]
        if is_pandoc_version2:
            # Only pandoc v2 and higher support quiet param
            cmd.append('--quiet')

        if self.columns:
            cmd.append(self.columns)

        p = subprocess.Popen(
            tuple(cmd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        stdout, stderr = p.communicate(input=text.encode())
        if stderr:
            logging.warning(
                "Error during pandoc covert:\n\t%s\n\t%s",
                cmd,
                stderr
            )
        r = stdout.decode('utf-8').strip()
        self.result = r
        with open(self.cachefile, 'wt') as f:
            f.write(self.result)

    def __str__(self):
        return str(self.result)

    def __repr__(self):
        return str(self.result)


class PandocMD2HTML(Pandoc):
    in_format = 'markdown'
    in_options = [
        'footnotes',
        'pipe_tables',
        'strikeout',
        # 'superscript',
        # 'subscript',
        'raw_html',
        'definition_lists',
        'backtick_code_blocks',
        'fenced_code_attributes',
        'shortcut_reference_links',
        'lists_without_preceding_blankline',
        'autolink_bare_uris',
    ]
    out_format = 'html5'
    out_options = []


class PandocHTML2MD(Pandoc):
    in_format = 'html'
    in_options = []
    out_format = 'markdown'
    out_options = [
        'footnotes',
        'pipe_tables',
        'strikeout',
        'raw_html',
        'definition_lists',
        'backtick_code_blocks',
        'fenced_code_attributes',
        'shortcut_reference_links',
        'lists_without_preceding_blankline',
        'autolink_bare_uris',
    ]


class PandocMD2TXT(Pandoc):
    in_format = 'markdown'
    in_options = [
        'footnotes',
        'pipe_tables',
        'strikeout',
        'raw_html',
        'definition_lists',
        'backtick_code_blocks',
        'fenced_code_attributes',
        'shortcut_reference_links',
        'lists_without_preceding_blankline',
        'autolink_bare_uris',
    ]
    out_format = 'plain'
    out_options = []
    columns = '--columns=80'


class PandocHTML2TXT(Pandoc):
    in_format = 'html'
    in_options = []
    out_format = 'plain'
    out_options = []
    columns = '--columns=80'
