from worker.design_tokens import PALETTE, STROKE as DESIGN_STROKE, RADIUS as DESIGN_RADIUS
from worker.design_tokens import PALETTE, STROKE, RADIUS, SHADOW
"""Explicit kit geometry, migrated from visual grammar; no sticker surfaces.

Unknown shapes fail closed. Earth/house/arrow are additive kit primitives;
wire-format cards may resolve to these without changing the API contract.
"""
import math
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from worker.visual import SHAPES, ABSTRACT_SHAPES, LAYOUTS

@lru_cache(maxsize=512)
def mask_for(shape, width, height, phase=0):
    from app.shape_vocab import NEW_SHAPES
    if shape in NEW_SHAPES and shape not in SHAPES | {'earth', 'house', 'arrow'}:
        from worker.shapes_w10 import mask
        return mask(shape, (width, height))
    if shape not in SHAPES | {'earth', 'house', 'arrow'}:
        raise ValueError(f'UNKNOWN_SHAPE shape={shape}: 该形状尚未实现')
    if shape == 'earth':
        mask = Image.new('L', (width, height))
        ImageDraw.Draw(mask).ellipse((0, 0, width-1, height-1), fill=255)
        return mask
    if shape in ('house', 'arrow'):
        mask = Image.new('L', (width, height))
        points = ([(0,.4),(.5,0),(1,.4),(.88,.4),(.88,1),(.12,1),(.12,.4)]
                  if shape == 'house' else [(0,.35),(.65,.35),(.65,0),(1,.5),(.65,1),(.65,.65),(0,.65)])
        ImageDraw.Draw(mask).polygon([(round(x*(width-1)), round(y*(height-1))) for x,y in points], fill=255)
        return mask
    s = LAYOUTS['style']
    pad = 0
    w,h = max(12,width),max(12,height)
    mask = Image.new('L',(w,h))
    d = ImageDraw.Draw(mask)
    def xy(x,y): return (round(pad+x*(w-1)), round(pad+y*(h-1)))
    def polygon(points): d.polygon([xy(x,y) for x,y in points],fill=255)
    def curve(points):
        # Cubic Bezier segments share endpoints.
        result = []
        for a,b,c,e in points:
            for step in range(33):
                t=step/32; u=1-t
                result.append(tuple(u**3*a[k]+3*u*u*t*b[k]+3*u*t*t*c[k]+t**3*e[k] for k in (0,1)))
        polygon(result)
    bounds = (*xy(0,0),*xy(1,1))
    if shape in ABSTRACT_SHAPES:
        # All sampled curves and coordinates are rasterized only on cache misses.
        # Leave room inside the silhouette for the small local animation offsets.
        def xy(x,y):
            return (round(pad+(.08+.84*x)*(w-1)), round(pad+(.08+.84*y)*(h-1)))
        pen = max(22, round(min(w,h)*.09))
        def line(points, thickness=pen):
            pts = [xy(*pt) for pt in points]
            d.line(pts, fill=255, width=thickness, joint='curve')
            r = thickness//2
            for x,y in (pts[0],pts[-1]):
                d.ellipse((x-r,y-r,x+r,y+r),fill=255)
        def arc(cx,cy,r,start,end):
            return [(cx+r*math.cos(a),cy+r*math.sin(a))
                    for a in (math.radians(start+(end-start)*i/64) for i in range(65))]
        if shape == 'sound':
            for r in (.25,.49,.73):
                line(arc(.10,.5,r+phase/max(.84*(w-1),1),-40,40))
        elif shape == 'vibration':
            dx=phase/max(.84*(w-1),1)
            d.rounded_rectangle((*xy(.32+dx,.28),*xy(.68+dx,.72)),radius=RADIUS['small'],fill=255)
            for y in (.14,.86):
                line([(.27,y),(.73,y)],max(16,pen-8))
                polygon([(.07,y),(.30,y-.13),(.30,y+.13)])
                polygon([(.93,y),(.70,y-.13),(.70,y+.13)])
        elif shape == 'heat':
            for x in (.20,.50,.80):
                line([(x+.065*math.sin(t*math.tau*1.25),.88-.76*t)
                      for t in (i/64 for i in range(65))])
        elif shape == 'cold':
            for i in range(6):
                a=-math.pi/2+i*math.pi/3
                def radial(r,side=0):
                    return (.5+r*math.cos(a)+side*math.cos(a+math.pi/2),
                            .5+r*math.sin(a)+side*math.sin(a+math.pi/2))
                line([(.5,.5),radial(.42)])
                for side in (-.12,.12):
                    line([radial(.25),radial(.34,side)],max(16,pen-4))
        elif shape == 'wind':
            line([(.10,.25),(.67,.25)]+arc(.67,.15,.10,90,-190))
            line([(.08,.50),(.90,.50)])
            line([(.18,.75),(.76,.75)])
        elif shape == 'force':
            polygon([(.08,.39),(.48,.39),(.48,.23),(.73,.50),(.48,.77),(.48,.61),(.08,.61)])
            for a,b in [((.80,.22),(.86,.10)),((.89,.38),(.98,.32)),
                        ((.89,.62),(.98,.68)),((.80,.78),(.86,.90))]:
                line([a,b])
        elif shape == 'time':
            # Two trapezoid chambers, a narrow neck, and a small sand pile.
            line([(.18,.10),(.82,.10),(.55,.46),(.45,.46),(.18,.10)])
            line([(.45,.54),(.55,.54),(.82,.90),(.18,.90),(.45,.54)])
            line([(.50,.46),(.50,.54)])
            polygon([(.35,.84),(.50,.69),(.65,.84)])
        elif shape == 'many':
            for x,y in [(.30,.20),(.70,.20),(.19,.65),(.50,.65),(.81,.65)]:
                d.ellipse((*xy(x-.12,y-.12),*xy(x+.12,y+.12)),fill=255)
    elif shape == 'circle': d.ellipse(bounds,fill=255)
    elif shape in ('square','block'): d.rounded_rectangle(bounds, radius=RADIUS['small'],fill=255)
    elif shape == 'triangle': polygon([(.5,0),(1,1),(0,1)])
    elif shape == 'star':
        polygon([(.5+(.5 if i%2==0 else .24)*math.cos(-math.pi/2+i*math.pi/5),
                  .5+(.5 if i%2==0 else .24)*math.sin(-math.pi/2+i*math.pi/5)) for i in range(10)])
    elif shape == 'drop':
        # Smooth cubic outline: narrow tip, round belly, no polygonal flat base.
        curves = [((.5,0),(.42,.24),(0,.48),(0,.7)),
                  ((0,.7),(0,1.1),(1,1.1),(1,.7)),
                  ((1,.7),(1,.48),(.58,.24),(.5,0))]
        points=[]
        for curve in curves:
            for step in range(41):
                t=step/40; u=1-t
                points.append(tuple(u**3*curve[0][k]+3*u*u*t*curve[1][k]+3*u*t*t*curve[2][k]+t**3*curve[3][k] for k in (0,1)))
        polygon(points)
    elif shape == 'lightning': polygon([(.42,0),(.94,0),(.62,.36),(.98,.36),(.13,1),(.36,.57),(.02,.57)])
    elif shape == 'stick':
        d.ellipse((*xy(.21,0),*xy(.79,.30)),fill=255)
        polygon([(.36,.29),(.64,.29),(.73,.62),(.62,.66),(.78,.94),(.62,1),
                 (.5,.73),(.38,1),(.22,.94),(.38,.66),(.27,.62)])
        for points in [[(.38,.36),(.12,.55),(.02,.49)],[(.62,.36),(.88,.55),(.98,.49)]]:
            d.line([xy(*pt) for pt in points],fill=255,width=max(12,round(w*.17)))
    elif shape == 'bacteria':
        # Seven soft lobes, with unequal radii: an organic, rounded silhouette.
        polygon([(.5 + (.43 + .055*math.cos(7*a) + .018*math.sin(3*a))*math.cos(a),
                  .5 + (.43 + .055*math.cos(7*a) + .018*math.sin(3*a))*math.sin(a))
                 for a in (i*math.tau/280 for i in range(280))])
    elif shape == 'tooth':
        curve([((.5,.07),(.12,-.12),(-.04,.08),(.09,.44)),
               ((.09,.44),(.15,.62),(.14,1),(.29,1)),
               ((.29,1),(.42,1),(.36,.57),(.5,.58)),
               ((.5,.58),(.64,.57),(.58,1),(.71,1)),
               ((.71,1),(.86,1),(.85,.62),(.91,.44)),
               ((.91,.44),(1.04,.08),(.88,-.12),(.5,.07))])
    elif shape == 'toothbrush':
        # Rotate the handle and bristles 30 degrees from vertical.
        def brush(x,y):
            return (.5+(x*.866+y*.5)/.7, .5-x*.5+y*.866)
        polygon([brush(x,y) for x,y in [(-.065,-.46),(.065,-.46),(.065,.46),(-.065,.46)]])
        polygon([brush(x,y) for x,y in [(-.07,-.46),(.20,-.46),(.20,-.19),(-.07,-.19)]])
    elif shape == 'moon':
        d.ellipse(bounds,fill=255)
    elif shape == 'candy':
        polygon([(0,.15),(.35,.4),(.35,.6),(0,.85),(.08,.5)])
        polygon([(1,.15),(.65,.4),(.65,.6),(1,.85),(.92,.5)])
        d.ellipse((*xy(.22,.08),*xy(.78,.92)),fill=255)
    elif shape == 'apple':
        curve([((.5,.23),(.05,.02),(-.12,.54),(.22,.91)),
               ((.22,.91),(.35,1.05),(.44,.94),(.5,.94)),
               ((.5,.94),(.56,.94),(.65,1.05),(.78,.91)),
               ((.78,.91),(1.12,.54),(.95,.02),(.5,.23))])
        d.line([xy(.5,.26),xy(.48,.04)],fill=255,width=max(12,w//18))
        curve([((.51,.15),(.56,-.02),(.8,-.03),(.82,.02)),
               ((.82,.02),(.77,.18),(.62,.21),(.51,.15))])
    elif shape == 'book':
        polygon([(0,.08),(.12,0),(.5,.12),(.88,0),(1,.08),(1,.91),(.87,.91),(.5,1),(.13,.91),(0,.91)])
    elif shape == 'sun':
        for i in range(12):
            a=i*math.pi/6
            points=[(.5+r*math.cos(a+t),.5+r*math.sin(a+t)) for r,t in [(.34,-.13),(.5,0),(.34,.13)]]
            polygon(points)
        d.ellipse((*xy(.18,.18),*xy(.82,.82)),fill=255)
    elif shape == 'cloud':
        for box in [(0,.3,.58,1),(.2,0,.8,1),(.47,.27,1,1)]:
            d.ellipse((*xy(*box[:2]),*xy(*box[2:])),fill=255)
        d.rectangle((*xy(.25,.55),*xy(.75,.98)),fill=255)
    elif shape == 'rainbow':
        d.pieslice((*xy(0,0),*xy(1,2)),180,360,fill=255)
        d.pieslice((*xy(.34,.68),*xy(.66,1.32)),180,360,fill=0)
    elif shape == 'heart':
        polygon([(0,.3),(.5,1),(1,.3)])
        d.ellipse((*xy(0,0),*xy(.52,.57)),fill=255)
        d.ellipse((*xy(.48,0),*xy(1,.57)),fill=255)
    elif shape in {'card', 'diagram_box'}: d.rounded_rectangle(bounds,radius=RADIUS['small'],fill=255)
    else: raise ValueError(f'UNKNOWN_SHAPE shape={shape}: 该形状尚未实现')
    return mask


def soft_lighting(im, mask, *, arc=False, box=None, character=False, repair=False, strip_width=.15, strip_height=.38, grammar_shape=None):
    """Compatibility entry for flat materials; the compositor owns hard shadows."""
    from worker.visual_style import solid
    from worker.lighting_declaration import unlit
    im = solid(im.convert('RGBA'))
    im.putalpha(mask)
    im.info['lighting_declaration'] = unlit(grammar_shape, im)
    return im


def b3_frozen_sprite(shape, color, diameter, stone_y=None):
    """Retain the authored silhouette and material partitions with shared styling."""
    import types
    from worker import shapes_b2 as b2
    class Drawing(b2.Drawing):
        def stone(self, box, shadow=True):
            if shape == 'tank_stone' and stone_y is not None:
                x,y,r,bottom = box
                box = (x,stone_y,r,stone_y+bottom-y)
            super().stone(box, shadow)
    draw = types.FunctionType(b2.sprite.__code__, dict(b2.sprite.__globals__, Drawing=Drawing))
    im, mask = draw(shape, color, diameter)
    im = soft_lighting(im, mask, grammar_shape=shape)
    return im, mask
