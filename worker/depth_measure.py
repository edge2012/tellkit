from worker.raster_cache import raster_cache
"""Pixel measurements: D65 CIE L*, HSL saturation and edge Michelson contrast."""
import colorsys
import itertools
from functools import lru_cache

@lru_cache(maxsize=16384)
def lightness(rgb):
    linear = [v/3294.6 if v <= 10.31475 else ((v/255+.055)/1.055)**2.4 for v in rgb]
    y = sum(v*c for v,c in zip(linear,(.2126729,.7151522,.0721750)))
    return 116*y**(1/3)-16 if y > (6/29)**3 else (29/3)**3*y

def saturation(rgb):
    return colorsys.rgb_to_hls(*(v/255 for v in rgb))[2]

def contrast(fill, outline):
    a,b=lightness(tuple(fill)),lightness(tuple(outline))
    return abs(a-b)/(a+b) if a+b else 0

def at_lightness(hue, sat, target):
    low,high=0.,1.
    for _ in range(24):
        value=(low+high)/2
        rgb=tuple(round(v*255) for v in colorsys.hls_to_rgb(hue,value,sat))
        if lightness(rgb)<target: low=value
        else: high=value
    return rgb

def aerial_palette(base, reference, background=(251,246,236)):
    # Fog first, preserve vegetation hue; calibrate against the actual mid material.
    mixed=tuple((a*.7+b*.3)/255 for a,b in zip(base,background))
    hue=colorsys.rgb_to_hls(*mixed)[0]
    target_s=saturation(reference)*.725
    target_l=min(98.,lightness(reference)+11)
    fill=at_lightness(hue,target_s,target_l)
    # Quantization near white is large in HSL S; select an actual 8-bit colour.
    candidates=itertools.product(*(range(max(0,c-5),min(255,c+5)+1) for c in fill))
    valid=[c for c in candidates if .70*saturation(reference)<=saturation(c)<=.75*saturation(reference) and c[1]>=c[0]>=c[2]]
    if valid:
        fill=min(valid,key=lambda c: abs(lightness(c)-target_l)+10*abs(saturation(c)-target_s))
    target=contrast(reference,(43,33,24))*.75
    ink_l=lightness(fill)*(1-target)/(1+target)
    ink=at_lightness(hue,saturation(fill),ink_l)
    return fill,ink

def contour_width(image, ink):
    """Median top-contour dark core over the central 40% of a raster."""
    import statistics
    from PIL import Image
    if image.mode=='RGBA':
        canvas=Image.new('RGBA',image.size,(251,246,236,255))
        image=Image.alpha_composite(canvas,image)
    rgb=image.convert('RGB')
    return _contour_pixels(rgb.size, rgb.tobytes(), tuple(ink))


@raster_cache(maxsize=128)
def _contour_pixels(size, pixels, ink):
    # Same full contour calculation, keyed by every source pixel and threshold
    # input. Moving/changed sprites cannot reuse a stale measurement.
    import statistics
    from PIL import Image
    import numpy as np
    rgb=np.asarray(Image.frombytes('RGB',size,pixels))
    threshold=lightness(ink)
    threshold+=8
    columns=rgb[:,round(size[0]*.3):round(size[0]*.7)].transpose(1,0,2)
    if not columns.size:return None
    packed=(columns[:,:,0].astype(np.int32)<<16)|(columns[:,:,1].astype(np.int32)<<8)|columns[:,:,2]
    colors,inverse=np.unique(packed,return_inverse=True)
    levels=np.array([lightness((int(c)>>16,(int(c)>>8)&255,int(c)&255)) for c in colors])
    values=levels[inverse].reshape(packed.shape)
    dark=values<=threshold
    starts=np.argmax(dark,axis=1)
    positions=np.arange(size[1])[None,:]
    ends=np.argmax((positions>=starts[:,None])&~dark,axis=1)
    legal=(starts>0)&(ends>starts)&(ends<size[1])&(ends-starts<=30)
    rows=np.flatnonzero(legal);start=starts[legal];end=ends[legal]
    if not len(rows):return None
    left=start-1+(values[rows,start-1]-threshold)/(values[rows,start-1]-values[rows,start])
    right=end-1+(threshold-values[rows,end-1])/(values[rows,end]-values[rows,end-1])
    return statistics.median((right-left).tolist())
