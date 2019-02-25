__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2019, Peter Molnar"
__license__ = "apache-2.0"
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

import subprocess
import logging


class PandocBase(str):
    in_format = 'html'
    in_options = []
    out_format = 'plain'
    out_options = []
    columns = None

    def __init__(self, text):
        self.source = text
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

        cmd = [
            'pandoc',
            '-o-',
            conv_to,
            conv_from,
            '--quiet',
            '--no-highlight'
        ]
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

    def __str__(self):
        return str(self.result)

    def __repr__(self):
        return str(self.result)


class PandocMarkdown(PandocBase):
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


class PandocHTML(PandocBase):
    in_format = 'html'
    in_options = []
    out_format = 'markdown'
    out_options = [
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


class PandocTXT(PandocBase):
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
    out_format = 'plain'
    out_options = []
    columns = '--columns=72'


#class PandocMarkdown(str):
    #def __new__(cls, text):
        #""" Pandoc command line call with piped in- and output """
        #cmd = (
            #'pandoc',
            #'-o-',
            #'--from=markdown+%s' % (
                #'+'.join([
                    #'footnotes',
                    #'pipe_tables',
                    #'strikeout',
                    ## 'superscript',
                    ## 'subscript',
                    #'raw_html',
                    #'definition_lists',
                    #'backtick_code_blocks',
                    #'fenced_code_attributes',
                    #'shortcut_reference_links',
                    #'lists_without_preceding_blankline',
                    #'autolink_bare_uris',
                #])
            #),
            #'--to=html5',
            #'--quiet',
            #'--no-highlight'
        #)
        #p = subprocess.Popen(
            #cmd,
            #stdin=subprocess.PIPE,
            #stdout=subprocess.PIPE,
            #stderr=subprocess.PIPE,
        #)

        #stdout, stderr = p.communicate(input=text.encode())
        #if stderr:
            #logging.warning(
                #"Error during pandoc covert:\n\t%s\n\t%s",
                #cmd,
                #stderr
            #)
        #r = stdout.decode('utf-8').strip()
        #return str.__new__(cls, r)


#class PandocHTML(str):
    #def __new__(cls, text):
        #""" Pandoc command line call with piped in- and output """
        #cmd = (
            #'pandoc',
            #'-o-',
            #'--to=markdown+%s' % (
                #'+'.join([
                    #'footnotes',
                    #'pipe_tables',
                    #'strikeout',
                    ## 'superscript',
                    ## 'subscript',
                    #'raw_html',
                    #'definition_lists',
                    #'backtick_code_blocks',
                    #'fenced_code_attributes',
                    #'shortcut_reference_links',
                    #'lists_without_preceding_blankline',
                    #'autolink_bare_uris',
                #])
            #),
            #'--from=html',
            #'--quiet',
        #)
        #p = subprocess.Popen(
            #cmd,
            #stdin=subprocess.PIPE,
            #stdout=subprocess.PIPE,
            #stderr=subprocess.PIPE,
        #)

        #stdout, stderr = p.communicate(input=text.encode())
        #if stderr:
            #logging.warning(
                #"Error during pandoc covert:\n\t%s\n\t%s",
                #cmd,
                #stderr
            #)
        #r = stdout.decode('utf-8').strip()
        #return str.__new__(cls, r)
