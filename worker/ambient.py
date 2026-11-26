"""Deterministic renderer-only motion. Semantic geometry never consumes this clock."""
from contextlib import contextmanager
from contextvars import ContextVar
import math
import os
from PIL import Image, ImageColor

_clock = ContextVar('ambient_ms', default=None)


def enabled():
    return os.environ.get('RENDER_AMBIENT_MOTION', '1').lower() not in {'0', 'false', 'off'}


@contextmanager
def clock(ms):
    token = _clock.set(ms if enabled() else None)
    try:
        yield
    finally:
        _clock.reset(token)


def phase(period):
    ms = _clock.get()
    return 0. if ms is None else math.sin(2*math.pi*ms/(period*1000))


def blinking():
    ms = _clock.get()
    return ms is not None and 5000 <= ms % 5040 < 5040


def background(color):
    if _clock.get() is None or isinstance(color, int): return color
    rgb = ImageColor.getrgb(color) if isinstance(color, str) else color
    return tuple(min(255, max(0, round(c*(1+.03*phase(8))))) for c in rgb[:3]) + tuple(rgb[3:])


def sprite(image, shape):
    if _clock.get() is None or image.info.get('ambient_ms') == _clock.get(): return image
    info = image.info.copy()
    if shape == 'awen':
        scale = 1+.015*phase(3.2)
        image = image.resize(tuple(max(1, round(n*scale)) for n in image.size), Image.Resampling.BICUBIC)
    elif shape in {'water', 'river', 'water_drop', 'sugar_solution', 'water_cup_tall', 'water_cup_wide', 'tank_stone', 'tank_wood', 'rain_basin', 'ice_melting'}:
        # Warp only a narrow surface band; vessel walls stay fixed.
        source = image
        image = source.copy()
        level = {'water_cup_tall': .23, 'water_cup_wide': .63, 'sugar_solution': .25, 'tank_stone': .36, 'tank_wood': .36, 'rain_basin': .67, 'ice_melting': .72}.get(shape, 0.)
        top = round(source.height*level)
        bottom = min(source.height, top+16)
        left = round(source.width*.12) if level else 0
        right = source.width-left
        for x in range(left, right, 4):
            end = min(right, x+4)
            dy = 2*math.sin(2*math.pi*x/max(1,source.width)+2*math.pi*(_clock.get()/2400))
            tile = source.transform((end-x, bottom-top), Image.Transform.QUAD,
                (x,top-dy,x,bottom,end,bottom,end,top-dy), Image.Resampling.BICUBIC)
            image.paste(tile, (x,top))
    elif shape in {'vapor_particles', 'sun_ray'}:
        # 2px amplitude / 8s: maximum 0.053px per frame at 30fps.
        dx = 2*phase(8)
        image = image.transform(image.size, Image.Transform.AFFINE, (1,0,-dx,0,1,0), Image.Resampling.BICUBIC)
    image.info.update(info)
    image.info['ambient_ms'] = _clock.get()
    return image
