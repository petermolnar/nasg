#!/usr/bin/env bash

lastmodfile="$(find /web/petermolnar.net/petermolnar.net/ -maxdepth 2 -type f -print0 | xargs -0r ls -ltr | grep -E '(content|comments|copy|files|offlinecopies|photos)' | tail -1 | awk '{print $9}')"
lastmod=$(stat -c %Y "$lastmodfile")
lastrunfile="/web/petermolnar.net/petermolnar.net/build/magic.php"
lastrun=$(stat -c %Y "$lastrunfile")


if [ "$lastrun" -lt "$lastmod" ]; then
    cd /web/petermolnar.net/petermolnar.net/nasg; python3.5 nasg.py --loglevel info
fi

exit 0
