# NASG - not another static generator...

Nearly 20 years ago I did my very first website with a thing called Microsoft FrontPage. I loved it. Times changed, and I wrote a CMS in PHP, first with flat files, then with MySQL, then moved on to WordPress. 

Now I'm back on a static generator. I love it.

**WARNING: this is a personal project, scratching my itches. No warranties. If you want to deploy it on your own, feel free to, but not all the things are documented.**

## ## What does it do

- content is structured in folders
- content files are YAML frontmatter + Multimarkdown
- EXIF from images are read via [exiftool](https://www.sno.phy.queensu.ca/~phil/exiftool/) _this is an external dependency_
- Markdown is converted with [pandoc](https://pandoc.org/) _this is an external dependency_

How it works

- pulls in webmentions from https://webmention.io and stores them in .md files next to the index.md of a post (see later) as: `[unix epoch]-[slugified source url].md`
- pulls in micropub from the queue received by the micropub receiver PHP (see later)
- finds 'redirect' files:
    - anything with a `.url` extension
    - content is the URL to redirect to
    - filename without extension is the slug to redirect from
    - for `HTTP 302` 
- finds 'gone' files:

    - anything with a `.del` extension
    - filename without extension is the slug deleted
    - for `HTTP 410` 
- finds content:

    - all `index.md` files
    - corresponding comment `.md` file next to it
    - the parent directory name is the post slug
    - finds all images in the same directory (`.jpg`, `.png`, `.gif`)
        - reads EXIF data into a hidden, `.[filename].json` file next to the original file
        - generates downsized and watermarked images into the `build/post slug` directory
        - if a `.jpg` if found with the same slug as the parent dir, the post will be a special photo post
    - anything else in the same directory will be copies to `build/post slug`
- send webmentions via https://telegraph.p3k.io/

```
/
├── about.html -> will be copied
├── category-1
│   ├── article-1 -> slug
│   │   └── index.md -> content file
│   │   └── extra-file.mp4 -> will be copied
│   │   └── 1509233601-domaincomentrytitle.md -> comment
│   ├── fancy-photo -> slug of photo post
│   │   └── index.md -> content
│   │   └── fancy-photo.jpg -> to downsize, watermark, get EXIF
```



Special features:

- complete `microformats2` and schema.org markup in templates
- has light/dark theme, dark by default, but supports experimental prefers-color-scheme media query
- generates 3 special PHP files:
    - search - uses and SQLite DB which is populated by Python on build
    - fallback - 404 handler to do redirects/gones, gets populated with an array of both
    - micropub - a micropub endpoint that accepts micropub content and puts the incoming payload into a json file, nothing else

## Why GPL

Because I want believe.