__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2018, Peter Molnar"
__license__ = "apache-2.0"
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import subprocess
import logging

class Pandoc(str):
   def __new__(cls, text):
        """ Pandoc command line call with piped in- and output """
        cmd = (
            'pandoc',
            '-o-',
            '--from=markdown+%s' % (
                '+'.join([
                    'footnotes',
                    'pipe_tables',
                    'strikeout',
                    #'superscript',
                    #'subscript',
                    'raw_html',
                    'definition_lists',
                    'backtick_code_blocks',
                    'fenced_code_attributes',
                    'shortcut_reference_links',
                    'lists_without_preceding_blankline',
                    'autolink_bare_uris',
                ])
            ),
            '--to=html5',
            '--quiet',
            '--no-highlight'
        )
        p = subprocess.Popen(
            cmd,
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
        return str.__new__(cls, r)
