# NASG - not another static generator...

This is my semi-static generator, written in Python.
Semi, because it generates 2 extra PHP files:

- search.php to read and FTS4 based sqlite database for search
- index.php to properly handle HTTP 410 and 301 headers for gone/redirect content

Content is YAML + Markdown.

External requirement: exiftool, because nothing else reads Lens data yet.
