"""
This is a simplified FencedBlockPreprocessor which outputs "proper" <code>
naming, eg. language-python, instead of just python, so prism.js understands
it.

It doesn't deal with CodeHilite.

"""

from markdown.preprocessors import Preprocessor
from markdown.extensions import Extension
from markdown.extensions.fenced_code import FencedBlockPreprocessor

class HTML5FencedBlockPreprocessor(Preprocessor):
    FENCED_BLOCK_RE = FencedBlockPreprocessor.FENCED_BLOCK_RE
    CODE_WRAP = '<pre><code%s>%s</code></pre>'
    LANG_TAG = ' class="language-%s"'

    def __init__(self, md):
        super(HTML5FencedBlockPreprocessor, self).__init__(md)

    def run(self, lines):
        text = "\n".join(lines)
        while 1:
            m = self.FENCED_BLOCK_RE.search(text)
            if m:
                lang = ''
                if m.group('lang'):
                    lang = self.LANG_TAG % (m.group('lang'))

                code = self.CODE_WRAP % (
                    lang,
                    m.group('code')
                )

                placeholder = self.markdown.htmlStash.store(code)
                text = '%s\n%s\n%s' % (
                    text[:m.start()],
                    placeholder,
                    text[m.end():]
                )
            else:
                break
        return text.split("\n")


class HTML5FencedCodeExtension(Extension):
    def extendMarkdown(self, md, md_globals):
        md.registerExtension(self)
        md.preprocessors.add(
            'html5_fenced_code',
            HTML5FencedBlockPreprocessor(md),
            ">normalize_whitespace"
        )

def makeExtension(*args, **kwargs):
    return HTML5FencedCodeExtension(*args, **kwargs)
