#!/usr/bin/env python3

__author__ = "Peter Molnar"
__copyright__ = "Copyright 2017-2018, Peter Molnar"
__license__ = "GNU LGPLv3 "
__maintainer__ = "Peter Molnar"
__email__ = "mail@petermolnar.net"

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.header import Header
import email.charset
from email.generator import Generator
from io import StringIO
import mimetypes
from email.mime.base import MIMEBase
from email.encoders import encode_base64
import email.utils

import time
import getpass
import socket
import shutil
import requests
import tempfile
import atexit
import os
import re
import smtplib
import logging
from shared import Pandoc


class Letter(object):
    def __init__(self, sender=None, recipient=None, subject='', text=''):
        self.sender = sender or (getpass.getuser(), socket.gethostname())
        self.recipient = recipient or self.sender

        self.tmp = tempfile.mkdtemp(
            'envelope_',
            dir=tempfile.gettempdir()
        )
        atexit.register(
            shutil.rmtree,
            os.path.abspath(self.tmp)
        )
        self.text = text
        self.subject = subject
        self.images = []
        self.ready = None
        self.time = time.time()
        self.headers = {}

    @property
    def _html(self):
        return Pandoc().convert(self.text)

    @property
    def _tmpl(self):
        return "<html><head></head><body>%s</body></html>" % (self._html)

    def __pull_image(self, img):
        fname = os.path.basename(img)
        i = {
            'url': img,
            'name': fname,
            'tmp': os.path.join(self.tmp, fname),
        }

        logging.debug("pulling image %s", i['url'])
        r = requests.get(i['url'], stream=True)
        if r.status_code == 200:
            with open(i['tmp'], 'wb') as f:
                logging.debug("writing image %s", i['tmp'])
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)
                if not isinstance(self.images, list):
                    self.images = []
                self.images.append(i)

    def __pull_images(self):
        mdmatch = re.compile(
            r'!\[.*\]\((.*?\.(?:jpe?g|png|gif)(?:\s+[\'\"]?.*?[\'\"]?)?)\)'
            r'(?:\{.*?\})?'
        )
        [self.__pull_image(img) for img in mdmatch.findall(self.text)]

    def __attach_images(self):
        self.__pull_images()
        for i in self.images:
            cid = 'cid:%s' % (i['name'])
            logging.debug("replacing %s with %s", i['url'], cid)
            self.text = self.text.replace(i['url'], cid)

    def make(self, inline_images=True):
        if inline_images:
            self.__attach_images()

        # Python, by default, encodes utf-8 in base64, which makes plain text
        # mail painful; this overrides and forces Quoted Printable.
        # Quoted Printable is still awful, but better, and we're going to
        # force the mail to be 8bit encoded.
        # Note: enforcing 8bit breaks compatibility with ancient mail clients.
        email.charset.add_charset(
            'utf-8',
            email.charset.QP,
            email.charset.QP,
            'utf-8'
        )

        mail = MIMEMultipart('alternative')

        # --- setting headers ---
        self.headers = {
            'Subject': Header(re.sub(r"\r?\n?$", "", self.subject, 1), 'utf-8').encode(),
            'To': email.utils.formataddr(self.recipient),
            'From': email.utils.formataddr(self.sender),
            'Date': email.utils.formatdate(self.time, localtime=True)
        }

        for k, v in self.headers.items():
            mail.add_header(k, "%s" % v)
        logging.debug("headers: %s", self.headers)

        # --- adding plain text ---
        text = self.text
        _text = MIMEText(text, 'text', _charset='utf-8')
        # ---
        # this is the part where we overwrite the way Python thinks:
        # force the text to be the actual, unencoded, utf-8.
        # Note:these steps breaks compatibility with ancient mail clients.
        _text.replace_header('Content-Transfer-Encoding', '8bit')
        _text.replace_header('Content-Type', 'text/plain; charset=utf-8')
        _text.set_payload(self.text)
        # ---
        logging.debug("text: %s", _text)
        mail.attach(_text)

        # --- HTML bit ---
        # this is where it gets tricky: the HTML part should be a 'related'
        # wrapper, in which the text and all the related images are sitting
        _envelope = MIMEMultipart('related')

        html = self._tmpl
        _html = MIMEText(html, 'html', _charset='utf-8')
        # ---
        # see above under 'adding plain text'
        _html.replace_header('Content-Transfer-Encoding', '8bit')
        _html.replace_header('Content-Type', 'text/html; charset=utf-8')
        _html.set_payload(html)
        # ---
        logging.debug("HTML: %s", _html)
        _envelope.attach(_html)

        for i in self.images:
            mimetype, encoding = mimetypes.guess_type(i['tmp'])
            mimetype = mimetype or 'application/octet-stream'
            mimetype = mimetype.split('/', 1)
            attachment = MIMEBase(mimetype[0], mimetype[1])
            with open(i['tmp'], 'rb') as img:
                attachment.set_payload(img.read())
                img.close()
            os.unlink(i['tmp'])

            encode_base64(attachment)
            attachment.add_header(
                'Content-Disposition',
                'inline',
                filename=i['name']
            )
            attachment.add_header(
                'Content-ID',
                '<%s>' % (i['name'])
            )

            _envelope.attach(attachment)

        # add the whole html + image pack to the mail
        mail.attach(_envelope)

        str_io = StringIO()
        g = Generator(str_io, False)
        g.flatten(mail)

        self.ready = str_io.getvalue().encode('utf-8')

    def send(self):
        if not self.ready:
            logging.error('this mail is not ready')
            return

        try:
            s = smtplib.SMTP('127.0.0.1', 25)
            # unless you do the encode, you'll get:
            #   File "/usr/local/lib/python3.5/smtplib.py", line 850, in sendmail
            #   msg = _fix_eols(msg).encode('ascii')
            # UnicodeEncodeError: 'ascii' codec can't encode character '\xa0'
            # in position 1073: ordinal not in range(128)
            s.sendmail(self.headers['From'], self.headers['To'], self.ready)
            s.quit()
        except Exception as e:
            logging.error('sending mail failed with error: %s', e)
