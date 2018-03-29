# NASG (Not Another Static Generator...)

This is a tiny static site generator, written in Python, to scratch my own itches.
It is most probably not suitable for anyone else, but feel free to use it for ideas. Keep in mind that the project is licenced under GPL.

## Why not [insert static generator here]?

- I'm using embedded XMP metadata in photos, which most of the ones availabe don't handle well;
- writing plugins to existing generators - Pelican, Nicola, etc - might have taken longer and I wanted to extend my Python knowledge
- I wanted to use the best available utilities for some tasks, like `Pandoc` and  `exiftool` instead of Python libraries trying to achive the same
- I needed to handle webmentions and comments

Don't expect anything fancy: my Python Fu has much to learn.

## Install

### External dependencies

PHP is in order to use [XRay](https://github.com/aaronpk/XRay/). Besides that, the rest is for `pandoc` and `exiftool`.

```
apt-get install pandoc exiftool php7.0-bcmath php7.0-bz2 php7.0-cli php7.0-common php7.0-curl php7.0-gd php7.0-imap php7.0-intl php7.0-json php7.0-mbstring php7.0-mcrypt php7.0-mysql php7.0-odbc php7.0-opcache php7.0-readline php7.0-sqlite3 php7.0-xml php7.0-zip python3 python3-pip python3-dev
```

Get XRay:
```
mkdir /usr/local/lib/php
cd /usr/local/lib/php
wget https://github.com/aaronpk/XRay/releases/download/v1.3.1/xray-app.zip
unzip xray-app.zip
rm xray-app.zip
```

## How content is organized

The directory structure of the "source" is something like this:
```
├── content
│   ├── category1 (containing YAML + MD files)
│   ├── category2 (containing YAML + MD files)
│   ├── photo (containing jpg files)
│   ├── _category_excluded_from_listing_1 (containing YAML + MD files)

├── files
│   ├── image (my own pictures)
│   ├── photo -> ../content/photo
│   └── pic (random images)
├── nasg
│   ├── archive.py
│   ├── config.ini
│   ├── db.py
│   ├── LICENSE
│   ├── nasg.py
│   ├── README.md
│   ├── requirements.txt
│   ├── router.py
│   ├── shared.py
│   └── templates
├── static
│   ├── favicon.ico
│   ├── favicon.png
│   └── pgp.asc
└── var
    ├── gone.tsv
    ├── redirects.tsv
    ├── s.sqlite
    ├── tokens.json
    └── webmention.sqlite
```

Content files can be in either YAML and Markdown, with `.md` extension, or JPG with metadata, with `.jpg` extension.

Inline images in the content are checked against all subdirectories in `files` ; they get their EXIF read and displayed as well if they match the regex in the configuration for the Artist and/or Copyright EXIF fields.

`gone.tsv` is a simple list of URIs that should return a `410 Gone` message while `redirect.tsv` is a tab separated file of `from to` entries that should be `301` redirected. These go into a magic.php file, so if the host supports executing PHP, it will take care of this.

## Output

`nasg.py` generates a `build` directory which will have an directory per entry, with an `index.html`, so urls can be `https://domain.com/filename/`.

Categories are rendered into `category/category_name`. Pagination is under `category/category_name/page/X`. They include a feed as well, `category/category_name/feed`, in form if an `index.atom` ATOM feed.

## Webserver configuration

A minimal nginx configuration for the virtualhost:
```
# --- Virtual Host ---
upstream {{ domain }} {
    server unix:/var/run/php/{{ domain }}.sock;
}

server {
    listen 80;
    server_name .{{ domain }};
    rewrite ^ https://$server_name$request_uri redirect;
    access_log  /dev/null;
    error_log /dev/null;
}

server {
    listen 443 ssl http2;
    server_name .{{ domain }};
    ssl_certificate /etc/letsencrypt/live/{{ domain }}/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/{{ domain }}/privkey.pem;
    ssl_dhparam dh.pem;
    add_header X-Frame-Options "SAMEORIGIN";
    add_header X-Content-Type-Options "nosniff";
    add_header X-XSS-Protection "1; mode=block";
    add_header Strict-Transport-Security "max-age=31536000; includeSubdomains;";

    root /[path to root]/{{ domain }};

    location = /favicon.ico {
        log_not_found off;
        access_log off;
    }

    location = /robots.txt {
        log_not_found off;
        access_log off;
    }

    location ~ ^(?<script_name>.+?\.php)(?<path_info>.*)$ {
        try_files $uri $script_name =404;
        fastcgi_param SCRIPT_FILENAME $document_root$script_name;
        fastcgi_param SCRIPT_NAME $script_name;
        fastcgi_param PATH_INFO $path_info;
        fastcgi_param PATH_TRANSLATED $document_root$path_info;
        fastcgi_param QUERY_STRING $query_string;
        fastcgi_param REQUEST_METHOD $request_method;
        fastcgi_param CONTENT_TYPE $content_type;
        fastcgi_param CONTENT_LENGTH $content_length;
        fastcgi_param SCRIPT_NAME $script_name;
        fastcgi_param REQUEST_URI $request_uri;
        fastcgi_param DOCUMENT_URI $document_uri;
        fastcgi_param DOCUMENT_ROOT $document_root;
        fastcgi_param SERVER_PROTOCOL $server_protocol;
        fastcgi_param GATEWAY_INTERFACE CGI/1.1;
        fastcgi_param SERVER_SOFTWARE nginx;
        fastcgi_param REMOTE_ADDR $remote_addr;
        fastcgi_param REMOTE_PORT $remote_port;
        fastcgi_param SERVER_ADDR $server_addr;
        fastcgi_param SERVER_PORT $server_port;
        fastcgi_param SERVER_NAME $server_name;
        fastcgi_param HTTP_PROXY "";
        fastcgi_param HTTPS $https if_not_empty;
        fastcgi_param SSL_PROTOCOL $ssl_protocol if_not_empty;
        fastcgi_param SSL_CIPHER $ssl_cipher if_not_empty;
        fastcgi_param SSL_SESSION_ID $ssl_session_id if_not_empty;
        fastcgi_param SSL_CLIENT_VERIFY $ssl_client_verify if_not_empty;
        fastcgi_param REDIRECT_STATUS 200;
        fastcgi_index index.php;
        fastcgi_connect_timeout 10;
        fastcgi_send_timeout 360;
        fastcgi_read_timeout 3600;
        fastcgi_buffer_size 512k;
        fastcgi_buffers 512 512k;
        fastcgi_keep_conn on;
        fastcgi_intercept_errors on;
        fastcgi_split_path_info ^(?<script_name>.+?\.php)(?<path_info>.*)$;
        fastcgi_pass {{ domain }};
    }

    location / {
        try_files $uri $uri/ $uri.html $uri/index.html $uri/index.xml $uri/index.atom index.php @rewrites;
    }

    location @rewrites {
        rewrite ^ /magic.php?$args last;
    }

    location ~* \.(css|js|eot|woff|ttf|woff2)$ {
        expires 1d;
        add_header Cache-Control "public, must-revalidate, proxy-revalidate";
        add_header "Vary" "Accept-Encoding";
    }

    location ~* \.(png|ico|gif|svg|jpg|jpeg|webp|avi|mpg|mpeg|mp4|mp3)$ {
        expires 7d;
        add_header Cache-Control "public, must-revalidate, proxy-revalidate";
        add_header "Vary" "Accept-Encoding";
    }
}

```
