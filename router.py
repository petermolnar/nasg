#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017, Peter Molnar"
__license__ = "GPLv3"
__version__ = "2.0"
__maintainer__ = "Peter Molnar"
__email__ = "hello@petermolnar.eu"
__status__ = "Production"

"""
    silo archiver module of NASG
    Copyright (C) 2017 Peter Molnar

    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, write to the Free Software Foundation,
    Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
"""
from sanic import Sanic
import sanic.response
from sanic.log import log as logging
import validators
import urllib.parse
import shared

if __name__ == '__main__':
    #logging_format = "[%(asctime)s] %(process)d-%(levelname)s "
    #logging_format += "%(module)s::%(funcName)s():l%(lineno)d: "
    #logging_format += "%(message)s"

    #logging.basicConfig(
        #format=logging_format,
        #level=logging.DEBUG
    #)
    #log = logging.getLogger()

    # log_config=None prevents creation of access_log and error_log files
    # since I'm running this from systemctl it already goes into syslog
    app = Sanic('router', log_config=None)
    # this is ok to be read-only
    sdb = shared.SearchDB()

    @app.route("/oauth1", methods=["GET"])
    async def oauth1(request):
        token = request.args.get('oauth_token')
        verifier = request.args.get('oauth_verifier')
        logging.info("incoming oauth request: token was %s ; verifier was %s", token, verifier)
        tokendb = shared.TokenDB()
        tokendb.update_token(
            token,
            verifier=verifier
        )
        return sanic.response.text("OK", status=200)

    @app.route("/search", methods=["GET"])
    async def search(request):
        query = request.args.get('s')
        r = sdb.html(query)
        response = sanic.response.html(r, status=200)
        return response

    @app.route("/micropub", methods=["POST", "GET"])
    async def micropub(request):
        return sanic.response.text("Not Implemented", status=501)

    @app.route("/webmention", methods=["POST"])
    async def webmention(request):
        source = request.form.get('source')
        target = request.form.get('target')

        # validate urls
        if not validators.url(source):
            return sanic.response.text('Invalide source url', status=400)
        if not validators.url(target):
            return sanic.response.text('Invalide target url', status=400)

        # check if our site is actually the target for the webmention
        _target = urllib.parse.urlparse(target)
        if _target.hostname not in shared.config.get('site', 'domains'):
            return sanic.response.text('target domain is not me', status=400)

        # ignore selfpings
        _source = urllib.parse.urlparse(source)
        if _source.hostname in shared.config.get('site', 'domains'):
            return sanic.response.text('selfpings are not allowed', status=400)

        # it is unfortunate that I need to init this every time, but
        # otherwise it'll become read-only for reasons I'm yet to grasp
        # the actual parsing will be done at site generation time
        wdb = shared.WebmentionQueue()
        wdb.queue(source, target)

        # telegram notification, if set
        shared.notify(
            'incoming webmention from %s to %s' % (
                source,
                target
            )
        )
        response = sanic.response.text("Accepted", status=202)
        return response

    app.run(host="127.0.0.1", port=8008, log_config=None)
