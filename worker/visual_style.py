"""Apply the shared palette and native-pixel outline after sprite sizing."""
from functools import lru_cache
from PIL import Image, ImageColor, ImageChops, ImageFilter
from worker.design_tokens import PALETTE, STROKE, SHADOW


@lru_cache(maxsize=1)
def palette():
    colors=[ImageColor.getrgb(value) for value in PALETTE.values()]
    tile=Image.new('P',(1,1))
    tile.putpalette([channel for color in colors for channel in color]+list(colors[0])*(256-len(colors)))
    return tile


def solid(sprite):
    """Preserve the alpha contour; quantize materials without dithering."""
    alpha=sprite.getchannel('A')
    result=sprite.convert('RGB').quantize(palette=palette(),dither=Image.Dither.NONE).convert('RGBA')
    width=STROKE['body']
    padded=Image.new('L',(sprite.width+2*width,sprite.height+2*width))
    padded.paste(alpha,(width,width))
    # A square minimum is separable. Preserve the padded zero edge and every
    # alpha value; avoid Pillow's general rank-sort kernel for each pixel.
    import numpy as np
    pixels=np.asarray(padded)
    horizontal=np.minimum.reduce([pixels[:,i:i+sprite.width] for i in range(2*width+1)])
    inner=Image.fromarray(np.minimum.reduce([horizontal[i:i+sprite.height] for i in range(2*width+1)]))
    result.paste(STROKE['color'],(0,0,result.width,result.height),ImageChops.subtract(alpha,inner))
    result.putalpha(alpha)
    return result


def cast(plan,sprite,xy):
    shade=Image.new('RGBA',sprite.size,SHADOW['color'])
    shade.putalpha(sprite.getchannel('A'))
    dx,dy=SHADOW['offset']
    plan.paste(shade,(xy[0]+dx,xy[1]+dy),shade)
