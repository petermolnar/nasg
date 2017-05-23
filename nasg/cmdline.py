import subprocess
import os
import json
import logging


class CommandLine(object):
    def __init__(self, cmd, stdin=''):
        self.cmd = cmd.split(' ')
        self.stdin = stdin
        self.stdout = ''
        self.binary = None
        self._which()

        if not self.binary:
            raise ValueError('%s binary was not found in PATH' % self.cmd[0])

    # based on: http://stackoverflow.com/a/377028/673576
    def _which(self):
        if self._is_exe(self.cmd[0]):
            self.binary = self.cmd[0]
            return

        for path in os.environ["PATH"].split(os.pathsep):
            path = path.strip('"')
            fpath = os.path.join(path, self.cmd[0])
            if self._is_exe(fpath):
                self.binary = self.cmd[0] = fpath
                return

    def _is_exe(self, fpath):
        return os.path.isfile(fpath) and os.access(fpath, os.X_OK)

    def run(self):
        p = subprocess.Popen(
            self.cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ.copy()
        )
        stdout, stderr = p.communicate(self.stdin.encode('utf-8'))
        self.stdout = stdout.decode('utf-8').strip()
        return self


class Exiftool(CommandLine):
    def __init__(self, fpath = ''):
        self.fpath = fpath
        cmd ="/usr/local/bin/exiftool -json -sort -groupNames %s" % (fpath)
        super(Exiftool, self).__init__(cmd)

    def get(self):
        self.run()
        exif = {}
        try:
            exif = json.loads(self.stdout)[0]
        except json.JSONDecodeError as e:
            logging.error("Error when decoding JSON returned from exiftool: %s" % e)
            pass

        return exif


class Pandoc(CommandLine):
    """ Use: Pandoc.[formatter function].get()
        available formatter functions:
        - md2html: from markdown extra to html5
        - html2md: from html5 to simple markdown

        The default is plain markdown to html5 (if no formatter function added)
    """

    def __init__(self, text):
        self.stdin = text
        self.format_in = 'markdown'
        self.format_out = 'html5'
        self.stdout = ''

    def md2html(self):
        self.format_in = "markdown+" + "+".join([
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
        return self


    def html2md(self):
        self.format_out = "markdown-" + "-".join([
            'raw_html',
            'native_divs',
            'native_spans',
        ])
        return self


    def get(self):
        cmd = "/usr/bin/pandoc -o- --from=%s --to=%s" % (self.format_in, self.format_out)
        super(Pandoc, self).__init__(cmd, stdin=self.stdin)
        self.run()
        return self.stdout