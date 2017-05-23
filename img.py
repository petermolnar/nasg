import os
import re
import sys
import json
import shutil
import collections
import logging
import imghdr
from ctypes import c_void_p, c_size_t
import glob
import pyexifinfo
from similar_text import similar_text
from cache import Cached
import wand.api
import wand.image
import wand.drawing
import wand.color
from PIL import Image
#from subprocess import call

# https://stackoverflow.com/questions/34617422/how-to-optimize-image-size-using-wand-in-python
wand.api.library.MagickSetCompressionQuality.argtypes = [c_void_p, c_size_t]


class ImageHandler(object):
    def __init__(self, fpath, alttext='', title='', imgcl='', linkto=False):

        self.fpath = os.path.abspath(fpath)
        path, fname = os.path.split(self.fpath)
        fname, ext = os.path.splitext(fname)
        self.fname = fname
        self.fext = ext
        self.ftime = os.stat(self.fpath)
        self.linkto = linkto

        self.alttext = alttext
        self.title = title
        self.imgcl = imgcl

        self.c = os.path.join(glob.TFILES, self.fname)
        self.u = "%s/%s/%s" % (glob.conf['site']['url'],glob.UFILES, self.fname)

        self.what = imghdr.what(self.fpath)

        self.meta = {}

        self.exif = {}
        if self.what == 'jpeg':
            self._setexif()

        self.watermark = ''
        wfile = os.path.join(glob.SOURCE, glob.conf['watermark'])
        if os.path.isfile(wfile):
            self.watermark = wfile

        sizes = {
            90: {
                'ext': 's',
                'cropped': True,
            },
            360: {
                'ext': 'm',
            },
            #540: 'n',
            720: {
                'ext': 'z',
            },
            #980: 'c',
            1280: {
                'ext': 'b',
            }
        }
        self.sizes = collections.OrderedDict(sorted(sizes.items(), reverse=0))

        for size, meta in self.sizes.items():
            meta['path'] = "%s_%s%s" % (self.c, meta['ext'], self.fext)
            meta['url'] = "%s_%s%s" % (self.u, meta['ext'], self.fext)
            meta['mime'] = "image/%s" % (self.what)


        self._setmeta()
        self.fallbacksize = 720
        self.srcsetmin = 720

        self._is_photo()

        if self.is_photo:
            self.srcset = self.mksrcset(generate_caption=False, uphoto=False)


    def _setmeta(self):
        s = collections.OrderedDict(reversed(list(self.sizes.items())))
        for size, meta in s.items():
            if os.path.isfile(meta['path']):
                with Image.open(meta['path']) as im:
                    meta['width'], meta['height'] = im.size
                    meta['size'] = os.path.getsize(meta['path'])
                    self.meta = meta
                    break


    def downsize(self, liquidcrop=True, watermark=True):
        if not self._is_downsizeable():
            return self._copy()

        if not self._isneeded():
            logging.debug("downsizing not needed for %s", self.fpath)
            return

        logging.debug("downsizing %s", self.fpath)
        try:
            img = wand.image.Image(filename=self.fpath)
            img.auto_orient()
        except:
            print("Unexpected error:", sys.exc_info()[0])
            raise

        # watermark
        if self.is_photo and self.watermark and img.format == "JPEG" and watermark:
            img = self._watermark(img)

        elif self.linkto:
            img = self._sourceurlmark(img)

        # resize & cache
        for size, meta in self.sizes.items():
            self._intermediate(img, size, meta)

        self._setmeta()


    def _setexif(self):
        cached = Cached(text=self.fname, stime=self.ftime)
        cexif = cached.get()

        if cexif:
            self.exif = json.loads(cexif)
        else:
            exif = pyexifinfo.get_json(self.fpath)
            self.exif = exif.pop()
            cached.set(json.dumps(self.exif))


    def _is_photo(self):
        self.is_photo = False
        if 'cameras' in glob.conf:
            if 'EXIF:Model' in self.exif:
                if self.exif['EXIF:Model'] in glob.conf['cameras']:
                    self.is_photo = True

        if 'copyright' in glob.conf:
            if 'IPTC:CopyrightNotice' in self.exif:
                for s in glob.conf['copyright']:
                    pattern = re.compile(r'%s' % s)
                    if pattern.search(self.exif['IPTC:CopyrightNotice']):
                        self.is_photo = True

        if self.is_photo:
            #self.category = "photo"

            if not self.alttext:
                keywords = ['XMP:Description', 'IPTC:Caption-Abstract']
                for key in keywords:
                    if key in self.exif and self.exif[key]:
                        self.alttext = self.exif[key]
                        break

            if not self.title:
                keywords = ['XMP:Title', 'XMP:Headline', 'IPTC:Headline']
                for key in keywords:
                    if key in self.exif and self.exif[key]:
                        self.title = self.exif[key]
                        break


    def _is_downsizeable(self):
        if self.what != 'jpeg' and self.what != 'png':
            return False
        if self.imgcl:
            return False
        return True


    def _watermark(self, img):
        wmark = wand.image.Image(filename=self.watermark)

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
            draw.font = os.path.join(glob.FONT)
            draw.font_size = round((img.width)/len(self.linkto)*1.5)
            draw.gravity = 'center'
            draw.text(
                0,
                0,
                self.linkto
            )
            draw(img)
        return img


    def _copy(self):
        p = self.c + self.fext
        if not os.path.isfile(p):
            logging.debug("copying %s" % self.fpath)
            shutil.copy(self.fpath, p)
        return


    def _isneeded(self):
        # skip existing
        needed = False
        if glob.REGENERATE:
            needed = True
        else:
            for size, meta in self.sizes.items():
                if not os.path.isfile(meta['path']):
                    needed = True

        return needed


    def _intermediate_dimensions(self, img, size, meta):
        if (img.width > img.height and 'crop' not in meta) \
        or (img.width < img.height and 'crop' in meta):
            width = size
            height = int(float(size / img.width) * img.height)
        else:
            height = size
            width = int(float(size / img.height) * img.width)

        return (width, height)


    def _intermediate_symlink(self, meta):
        # create a symlink to the largest resize with the full filename;
        # this is to ensure backwards compatibility and avoid 404s
        altsrc = meta['path']
        altdst = self.c + self.fext

        if not os.path.islink(altdst):
            if os.path.isfile(altdst):
                os.unlink(altdst)
            os.symlink(altsrc, altdst)


    def _intermediate(self, img, size, meta):
        # skip existing unless regenerate needed
        if os.path.isfile(meta['path']) and not glob.REGENERATE:
            return

        # too small images: move on
        #if size > img.height and size > img.width:
        # return
        width, height = self._intermediate_dimensions(img, size, meta)

        try:
            thumb = img.clone()
            thumb.resize(width, height)
            #thumb.resize(width, height, filter='robidouxsharp')

            if 'crop' in meta and liquidcrop:
                thumb.liquid_rescale(size, size, 1, 1)
            elif 'crop' in meta:
                l = t = 0
                if width > size:
                    l = int((width - size) / 2)
                if height > size:
                    t = int((height - size) / 2)
                thumb.crop(left=l, top=t, width=size, height=size)

            if img.format == "PNG":
                library.MagickSetCompressionQuality(img.wand, 75)

            if img.format == "JPEG":
                thumb.compression_quality = 86
                thumb.unsharp_mask(radius=0, sigma=0.5, amount=1, threshold=0.03)
                thumb.format = 'pjpeg'

            # this is to make sure pjpeg happens
            with open(meta['path'], 'wb') as f:
                thumb.save(file=f)

            if size == list(self.sizes.keys())[-1]:
                self._intermediate_symlink(meta)

            #if img.format == "JPEG":
                ## this one strips the embedded little jpg
                #call(['/usr/bin/jhead', '-dt', '-q', cpath])

        except:
            print("Unexpected error:", sys.exc_info()[0])
            raise


    def mksrcset(self, generate_caption=True, uphoto=False):
        if not self._is_downsizeable():
            return False

        for size, meta in self.sizes.items():
            if 'crop' in meta:
                continue

            # increase fallback until max fallback reached
            if size <= self.fallbacksize:
                fallback = meta['url']

            # set target for the largest
            target = meta['url']

        if uphoto:
            uphotoclass=' u-photo'
        else:
            uphotoclass=''
        caption = ''

        if not self.imgcl:
            cl = ''
        else:
            cl = self.imgcl

        if self.alttext \
        and similar_text(self.alttext, self.fname) < 90 \
        and similar_text(self.alttext, self.fname + '.' + self.fext) < 90 \
        and generate_caption:
            caption = '<figcaption class=\"caption\">%s</figcaption>' % (self.alttext)

        if self.linkto:
            target = self.linkto

        return '<figure class="photo"><a target="_blank" class="adaptive%s" href="%s"><img src="%s" class="adaptimg %s" alt="%s" /></a>%s</figure>' % (uphotoclass, target, fallback, self.imgcl, self.alttext, caption)