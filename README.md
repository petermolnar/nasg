# NASG - not another static generator...

## Near full circle: from static to full dynamic to semi-static

Nearly 20 years ago I did my very first website with a thing called Microsoft FrontPage. I was static, but assembled from footer, nav, etc. html parts by FrontPage, then uploaded to a free webhost, and I was very happy with it: it was extremely simple to edit and to maintain.

Years passed and first I wrote a CMS that used text files as storage, based on a PHP library that stored serialized objects in text files - basically JSON, before JSON even existed. Then I moved to MySQL, then dropped the whole thing for WordPress, which I loved, up until Gutenberg was announced, at which point I realized how nastily I tinkered and altered my WordPress already to use it with Markdown, to make image and handling a tiny bit better, etc.

So I dropped it and make a static generator, only to realize, there are things I can't make static. At that point - 2017 -, these were:

- search
- proper redirect and gone entry handling (you can't set HTTP headers from a HTML file)
- receiving webmentions

Because I wanted to learn Python, the static generator is coded in Python, so I decided to run a Python web service with Sanic. It took me 3 iterations to realize, I'm doing it wrong, because the one and only thing that is available on nearly any webhost - think of plain old Apache - is PHP.

So the abomination I'm doing right now is to generate some near-static PHP files from the Python code which handles:

- search
  still with SQLite, but due to PHP versions, with FTS4 instead of FTS5; populated from Python, read by PHP
- gone (HTTP 410) and redirect (HTTP 301)

As for webmentions, as much as I try avoiding external dependencies, I came to realize a very simple fact: webmentions are external as well. So I started using [webmention.io](http://webmention.io) to receive them and query it on build time.

## Now, about that the generator itself

The content is [StriclYAML](https://github.com/crdoconnor/strictyaml) + [MultiMarkdown](http://fletcherpenney.net/multimarkdown/features/). Except [exiftool](https://www.sno.phy.queensu.ca/~phil/exiftool/), there are no non-python dependencies any more, but `exiftool` is the only thing that parses lends data for photos.

Python libraries used:

- [arrow](https://arrow.readthedocs.io/en/latest/)
- [bleach](https://github.com/mozilla/bleach)
- [emoji](https://github.com/carpedm20/emoji/)
- [feedgen](https://github.com/lkiesow/python-feedgen)
- [Jinja2](http://jinja.pocoo.org/)
- [langdetect](https://github.com/Mimino666/langdetect)
- [Markdown](https://github.com/Python-Markdown/markdown)
- [markdown-urlize](https://github.com/r0wb0t/markdown-urlize)
- [Pygments](http://pygments.org/)
- [python-frontmatter](https://github.com/eyeseast/python-frontmatter)
- [requests](http://docs.python-requests.org/en/master/)
- [unicode-slugify](https://github.com/mozilla/unicode-slugify)
- [Wand](http://docs.wand-py.org/en/0.4.4/)
- ... and their dependencies

Most of the processing relies on the structuring of my data:

- whatever is not a directory in the root folder of the contents will be copied as is
- directories mean category
- 1 sub-directory per entry within the category, named as the post slug
- index.md as main file
- timestamp-sanitizedurl.md for webmentions and comments
- if there is a .jpg, named the same as the post directory name, the post is a photo
- all markdown image entries are replaced with `<figure>` with added visible exif data if they math the criterias that they are my photos, namely they match a regular expression in their exif Copyright or Artist field - this is produced by my camera
- all images will be downsized and, if matched as photo, watermarked on build

```
/
├── about.html
├── category-1
│   ├── article-1
│   │   └── index.md
│   │   └── extra-file.mp4
│   │   └── 1509233601-domaincomentrytitle.md
│   ├── fancy-photo
│   │   └── index.md
│   │   └── fancy-photo.jpg
```

Mostly that's all.