import os
import re
import shutil
import logging
import imghdr
from similar_text import similar_text
import wand.api
import wand.image
import wand.drawing
import wand.color

import nasg.config as config
from nasg.cmdline import Exiftool


class ImageHandler(object):

    sizes = {
        90: {
            'ext': 's',
            'crop': True,
        },
        360: {
            'ext': 'm',
        },
        720: {
            'ext': 'z',
            'fallback': True
        },
        1280: {
            'ext': 'b',
        }
    }

    def __init__(self, fpath, alttext='', title='', imgcl='', linkto=False):
        logging.info("parsing image: %s" % fpath)
        self.fpath = os.path.abspath(fpath)
        self.fname, self.ext = os.path.splitext(os.path.basename(fpath))

        self.linkto = linkto
        self.alttext = alttext
        self.title = title
        self.imgcl = imgcl
        self.what = imghdr.what(self.fpath)
        self.mime = "image/%s" % (self.what)
        self.exif = {}
        self.is_photo = False
        if self.what == 'jpeg':
            self._setexif()
            self._is_photo()
        self.is_downsizeable = False
        if not self.imgcl:
            if self.what == 'jpeg' or self.what == 'png':
                self.is_downsizeable = True
        self.sizes = sorted(self.sizes.items())
        for size, meta in self.sizes:
            meta['fname'] = "%s_%s%s" % (
                self.fname,
                meta['ext'],
                self.ext
            )
            meta['fpath'] = os.path.join(
                config.TFILES,
                meta['fname']
            )
            meta['url'] = "%s/%s/%s" % (
                config.site['url'],
                config.UFILES,
                meta['fname']
            )
            if 'fallback' in meta:
                self.fallback = meta['url']
            self.targeturl = meta['url']


    def featured(self):
        # sizes elements are tuples: size, meta
        return {
            'mime': self.mime,
            'url': self.sizes[-1][1]['url'],
            'bytes':  os.path.getsize(self.sizes[-1][1]['fpath'])
        }


    def _setexif(self):
        self.exif = Exiftool(self.fpath).get()


    def _is_photo(self):
        model = self.exif.get('EXIF:Model', None)
        if hasattr(config, 'cameras') and \
        model in config.cameras:
            self.is_photo = True
            return

        cprght = self.exif.get('IPTC:CopyrightNotice', '')
        if hasattr(config, 'copyr'):
            for s in config.copyr:
                pattern = re.compile(r'%s' % s)
                if pattern.match(cprght):
                    self.is_photo = True
                    return


    def _watermark(self, img):
        if 'watermark' not in config.options:
            return img
        if not os.path.isfile(config.options['watermark']):
            return img

        wmark = wand.image.Image(filename=config.options['watermark'])

        if img.width > img.height:
            w = img.width * 0.16
            h = wmark.height * (w / wmark.width)
            x = img.width - w - (img.width * 0.01)
            y = img.height - h - (img.height * 0.01)
        else:
            w = img.height * 0.16
            h = wmark.height * (w / wmark.width)
            x = img.width - h - (img.width * 0.01)
            y = img.height - w - (img.height * 0.01)

        w = round(w)
        h = round(h)
        x = round(x)
        y = round(y)

        wmark.resize(w, h)
        if img.width < img.height:
            wmark.rotate(-90)
        img.composite(image=wmark, left=x, top=y)
        return img


    def _sourceurlmark(self, img):
        with wand.drawing.Drawing() as draw:
            draw.fill_color = wand.color.Color('#fff')
            draw.fill_opacity = 0.8
            draw.stroke_color = wand.color.Color('#fff')
            draw.stroke_opacity = 0.8
            r_h = round(img.height * 0.3)
            r_top = round((img.height/2) - (r_h/2))

            draw.rectangle(
                left=0,
                top=r_top,
                width=img.width,
                height=r_h
            )

            draw(img)

        with wand.drawing.Drawing() as draw:
            draw.font = config.FONT
            draw.font_size = round((img.width)/len(self.linkto)*1.5)
            draw.gravity = 'center'
            draw.text(
                0,
                0,
                self.linkto
            )
            draw(img)
        return img

    def downsize(self):
        if not self.is_downsizeable:
            return self._copy()
        if not self._isneeded():
            logging.debug("downsizing not needed for %s", self.fpath)
            return

        logging.debug("downsizing %s", self.fpath)
        try:
            img = wand.image.Image(filename=self.fpath)
            img.auto_orient()
        except ValueError as e:
            logging.error("opening %s with wand failed: %s", self.fpath, e)
            return

        if self.is_photo:
            img = self._watermark(img)
        elif self.linkto:
            img = self._sourceurlmark(img)

        for size, meta in self.sizes:
            self._intermediate(img, size, meta)

        #self._setmeta()


    def _copy(self):
        target = os.path.join(
            config.TFILES,
            "%s%s" % (self.fname, self.ext)
        )
        if os.path.isfile(target) and \
        not config.options['downsize']:
            return

        logging.debug("copying %s to %s", self.fpath, target)
        shutil.copy(self.fpath, target)


    def _isneeded(self):
        if config.options['downsize']:
            return True
        for size, meta in self.sizes:
            if not os.path.isfile(meta['fpath']):
                return True


    def _intermediate_dimensions(self, img, size, meta):
        if (img.width > img.height and 'crop' not in meta) \
        or (img.width < img.height and 'crop' in meta):
            width = size
            height = int(float(size / img.width) * img.height)
        else:
            height = size
            width = int(float(size / img.height) * img.width)

        return (width, height)


    def _intermediate(self, img, size, meta):
        if os.path.isfile(meta['fpath']) and \
        not config.options['downsize']:
            return

        try:
            thumb = img.clone()
            width, height = self._intermediate_dimensions(img, size, meta)
            thumb.resize(width, height)

            if 'crop' in meta:
                if 'liquidcrop' in config.options and \
                config.options['liquidcrop']:
                    thumb.liquid_rescale(size, size, 1, 1)
                else:
                    l = t = 0
                    if width > size:
                        l = int((width - size) / 2)
                    if height > size:
                        t = int((height - size) / 2)
                    thumb.crop(left=l, top=t, width=size, height=size)

            if img.format == "JPEG":
                thumb.compression_quality = 86
                thumb.unsharp_mask(
                    radius=0,
                    sigma=0.5,
                    amount=1,
                    threshold=0.03
                )
                thumb.format = 'pjpeg'


            # this is to make sure pjpeg happens
            with open(meta['fpath'], 'wb') as f:
                thumb.save(file=f)

        except ValueError as e:
            logging.error("error while downsizing %s: %s", self.fpath, e)
            return


    def srcset(self, generate_caption=True, uphoto=False):
        if not self.is_downsizeable:
            return False

        uphotoclass=''
        if uphoto:
            uphotoclass=' u-photo'

        cl = ''
        if self.imgcl:
            cl = self.imgcl

        caption = ''
        if self.alttext \
        and similar_text(self.alttext, self.fname) < 90 \
        and similar_text(self.alttext, self.fname + '.' + self.ext) < 90 \
        and generate_caption:
            caption = '<figcaption class=\"caption\">%s</figcaption>' % (self.alttext)

        if self.linkto:
            target = self.linkto

        # don't put linebreaks in this: Pandoc tends to evaluate them
        return '<figure class="photo"><a target="_blank" class="adaptive%s" href="%s"><img src="%s" class="adaptimg %s" alt="%s" /></a>%s</figure>' % (
            uphotoclass,
            self.targeturl,
            self.fallback,
            self.imgcl,
            self.alttext,
            caption
        )