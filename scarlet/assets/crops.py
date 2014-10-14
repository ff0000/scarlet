import os
import urllib
import tempfile
from collections import namedtuple

from django.core.files.storage import default_storage
from django.core.files import File

try:
    from PIL import Image, ImageFile
except ImportError:
    import Image, ImageFile
ImageFile.MAXBLOCK = 1024*1024

from . import utils
from . import signals
from . import settings

class CropSpec(namedtuple('CropSpec', ['name','editable', 'width',
                                   'height','x', 'x2', 'y', 'y2'])):
    def to_dict(self):
        return self._asdict()

class CropConfig(object):
    def __init__(self, name, width=None, height=None,
                 quality=90, editable=True, upscale=False):
        self.name = name
        self.width=width
        self.height=height
        self.upscale=upscale
        self.quality=quality
        self.editable=editable

    def _adjust_coordinates(self, ratio, current_size, needed_size):
        diff = current_size - (needed_size / ratio)
        if diff:
            adjust = int(diff / 2)
        else:
            adjust = 0
        return adjust

    def get_crop_spec(self, im, x=None, x2=None, y=None, y2=None):
        """
        Returns the default crop points for this image.
        """
        w, h = [float(v) for v in im.size]
        upscale = self.upscale
        if x != None and x2 and y != None and y2:
            upscale = True
            w = float(x2)-x
            h = float(y2)-y
        else:
            x = 0
            x2 = w
            y = 0
            y2 = h

        if self.width and self.height:
            ry = self.height / h
            rx = self.width / w
            if rx < ry:
                ratio = ry
                adjust = self._adjust_coordinates(ratio, w, self.width)
                x = x + adjust
                x2 = x2 - adjust
            else:
                ratio = rx
                adjust = self._adjust_coordinates(ratio, h, self.height)
                y = y + adjust
                y2 = y2 - adjust

            width = self.width
            height = self.height
        elif self.width:
            ratio = self.width / w
            width = self.width
            height = int(h * ratio)
        else:
            ratio = self.height / h
            width = int(w * ratio)
            height = self.height

        if ratio > 1 and not upscale:
            return

        x, x2, y, y2 = int(x),int(x2),int(y),int(y2)
        return CropSpec(name=self.name,
                        editable=self.editable,
                        width=width,height=height,
                        x=x,x2=x2,y=y,y2=y2)

    def rotate_by_exif(self, im):
        if 'exif' in im.info:
            try:
                exifinfo = im._getexif()
            except (IOError, KeyError, IndexError):
                return im

            if exifinfo != None:
                # 274 is exif code for orientation
                orientation = exifinfo.get(274, None)
                if orientation == 3:
                    # flip 180
                    im = im.rotate(180)
                elif orientation == 6:
                    # flip -90
                    im = im.rotate(-90)
                elif orientation == 8:
                    # flip 90
                    im = im.rotate(90)
        return im

    def process_image(self, im, crop_spec=None):
        if not crop_spec:
            crop_spec = self.get_crop_spec(im)

        if crop_spec:
            return scale_and_crop(im, crop_spec)

class Cropper(object):
    _registry = {}

    def __init__(self, storage=None):
        self.storage = storage or default_storage
        self._required_crops = []
        for k, v in settings.IMAGE_SIZES.items():
            if v and isinstance(v, dict):
                self.register(CropConfig(k, **v))
                self._required_crops.append(k)

    def get_crop_config(self, name):
        return self._registry.get(name)

    def required_crops(self):
        return self._required_crops

    def register(self, config):
        assert isinstance(config, CropConfig)
        if config.name in self._registry:
            seen = self._registry[config.name]
            for attr in ('name', 'width', 'height',
                'upscale', 'quality', 'editable'):
                if getattr(seen, attr) != getattr(config, attr):
                    raise ValueError(
                        "{0} is already registered as a different crop".format(
                            config.name))
        self._registry[config.name] = config

    def unregister(self, name):
        if name in self._registry:
            del self._registry[name]

    def create_crop(self, name, file_obj,
                    x=None, x2=None, y=None, y2=None):
        """
        Generate Version for an Image.
        value has to be a serverpath relative to MEDIA_ROOT.

        Returns the spec for the crop that was created.
        """

        if not name in self._registry:
            return

        file_obj.seek(0)
        im = Image.open(file_obj)
        config = self._registry[name]

        if x != None and x2 and y != None and y2 and not config.editable:
            # You can't ask for something special
            # for non editable images
            return

        im = config.rotate_by_exif(im)
        crop_spec = config.get_crop_spec(im, x=x, x2=x2, y=y, y2=y2 )
        image = config.process_image(im, crop_spec=crop_spec)
        if image:
            crop_name = utils.get_size_filename(file_obj.name, name)
            self._save_file(image, crop_name)
            return crop_spec

    def replace_image(self, file_obj,
                    x=None, x2=None, y=None, y2=None):
        assert x != None and x2 and y != None and y2

        file_obj.seek(0)
        im = Image.open(file_obj)

        crop_spec = CropSpec(x=x,x2=x2,y=y,y2=y2,
                             width=x2-x,height=y2-y,name='original',
                             editable=False)
        image = scale_and_crop(im, crop_spec=crop_spec)
        if image:
            self._save_file(image, file_obj.name)
            return crop_spec

    def _save_file(self, im, filename, quality=90):
        tmpfile = File(tempfile.NamedTemporaryFile())
        try:
            root, ext = os.path.splitext(filename)
            try:
                im.save(tmpfile, format=Image.EXTENSION[ext.lower()], quality=quality,
                             optimize=(ext != '.gif'))
            except IOError:
                im.save(tmpfile, format=Image.EXTENSION[ext.lower()], quality=quality)

            if filename != self.storage.get_available_name(filename):
                self.storage.delete(filename)

            self.storage.save(filename, tmpfile)
            url = self.storage.url(filename)
            utils.update_cache_bust_version(url)
            signals.file_saved.send(filename)
        finally:
            tmpfile.close()

def scale_and_crop(im, crop_spec):
    """
    Scale and Crop.
    """
    im = im.crop((crop_spec.x, crop_spec.y, crop_spec.x2, crop_spec.y2))

    if crop_spec.width and crop_spec.height:
        im = im.resize((crop_spec.width, crop_spec.height),
                   resample=Image.ANTIALIAS)

    return im

cropper = Cropper()
