#!/usr/bin/env python3

import asyncio
import uvloop
import os

from sanic import Sanic
import sanic.response
from sanic.log import log as logging
#import jinja2
import requests
import shared
import json


def locationtags_500px(lat, lon, radius=0.5, num=10):

    tags = []
    if not lat or not lon:
        return tags

    logging.info("requesting locationtags from 500px for '%s, %s'", lat, lon)
    params = {
        'rpp': 100,
        'geo': "%s,%s,%skm" % (lat, lon, radius),
        'consumer_key': shared.config.get('500px', 'api_key'),
        'tags': 1,
    }

    r = requests.get('https://api.500px.com/v1/photos/search',params=params)
    try:
        results = json.loads(r.text)
    except Exception as e:
        logging.error('failed to load results for 500px request: %s', e)
        logging.error('request was: %s', r.url)
        return tags, r.status_code

    _temp = {}
    for p in results.get('photos', []):
        for t in p.get('tags', []):
            if not t or not len(t):
                continue

            curr = _temp.get(t, 1)
            _temp[t] = curr+1

    for w in sorted(_temp, key=_temp.get, reverse=True):
        tags.append(w)

    return tags[:num], 200


def locationtags_flickr(lat, lon, radius=0.5, num=10):

    tags = []
    if not lat or not lon:
        return tags

    logging.info("requesting locationtags from Flickr for '%s, %s'", lat, lon)
    params = {
        'method': 'flickr.photos.search',
        'api_key': shared.config.get('flickr', 'api_key'),
        'has_geo': 1,
        'lat': lat,
        'lon': lon,
        'radius': radius,
        'extras': ','.join(['tags','machine_tags']),
        'per_page': 500,
        'format': 'json',
        'nojsoncallback': 1
    }

    r = requests.get('https://api.flickr.com/services/rest/',params=params)
    try:
        results = json.loads(r.text)
        #logging.debug("flickr response: %s", results)
    except Exception as e:
        logging.error('failed to load results for Flickr request: %s', e)
        logging.error('request was: %s', r.url)
        return tags, r.status_code

    _temp = {}
    for p in results.get('photos', {}).get('photo', {}):
        for t in p.get('tags', '').split(' '):
            if not t or not len(t):
                continue

            curr = _temp.get(t, 1)
            _temp[t] = curr+1

    for w in sorted(_temp, key=_temp.get, reverse=True):
        tags.append(w)

    return tags[:num], 200
    #return tags


def RequestHandler(lat, lon, rad, num=20):
    ftags, status = locationtags_flickr(lat, lon, rad, num)
    fivehtags, status = locationtags_500px(lat, lon, rad, num)

    return sanic.response.json({
        'flickr': ftags,
        '500px': fivehtags,
    }, status=status)

if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    app = Sanic()

    @app.route("/tagmyloc")
    async def search(request, methods=["GET"]):
        lat = request.args.get('lat')
        lon = request.args.get('lon')
        rad = request.args.get('rad')
        return RequestHandler(lat, lon, rad)

    app.run(host="127.0.0.1", port=8003, debug=True)
