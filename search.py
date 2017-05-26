#!/usr/bin/env python3

import asyncio
import uvloop
import os

from sanic import Sanic
import sanic.response
from sanic.log import log as logging
from whoosh import index
from whoosh import qparser
from whoosh import fields
from whoosh import analysis
import jinja2
import shared

def SearchHandler(query, tmpl):
    response = sanic.response.text(
        "You seem to have forgot to enter what you want to search for. Please try again.",
        status=400
    )

    if not query:
        return response

    query = query.replace('+', ' AND ').replace(' -', ' NOT ')
    ix = index.open_dir(os.path.abspath(os.path.join(
            shared.config.get('target', 'builddir'),
            shared.config.get('var', 'searchdb')
    )))

    qp = qparser.MultifieldParser(
        ["title", "content", "tags"],
        schema = shared.schema
    )

    q = qp.parse(query)
    r = ix.searcher().search(q, sortedby="weight", limit=100)
    logging.info("results for '%s': %i", query, len(r))
    results = []
    for result in r:
        res = {
            'title': result['title'],
            'url': result['url'],
            'highlight': result.highlights("content"),
        }
        if 'img' in result:
            res['img'] = result['img']
        results.append(res)

    tvars = {
        'term': query,
        'posts': results,
    }

    logging.info("collected %i results to render", len(results))
    response = sanic.response.html(tmpl.render(tvars), status=200)
    return response

if __name__ == '__main__':
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    app = Sanic()


    jldr = jinja2.FileSystemLoader(
        searchpath=shared.config.get('source', 'templatesdir')
    )
    jenv = jinja2.Environment(loader=jldr)
    tmpl = jenv.get_template('searchresults.html')

    @app.route("/search")
    async def search(request, methods=["GET"]):
        query = request.args.get('s')
        r = SearchHandler(query, tmpl)
        return r

    app.run(host="127.0.0.1", port=8001, debug=True)
