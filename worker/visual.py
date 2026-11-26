from worker.design_tokens import PALETTE, STROKE as DESIGN_STROKE, RADIUS as DESIGN_RADIUS
from worker.design_tokens import PALETTE, STROKE, RADIUS, SHADOW, TYPE
from app.performance import CameraMotion, PoseEvent
"""Pillow visual grammar. Coordinates and animation depend only on scene time."""
from functools import lru_cache
import math
import re
from typing import Literal, Annotated
from PIL import Image, ImageDraw, ImageChops
from pydantic import BaseModel, Field, model_validator, ConfigDict
from app.logic_w24 import Sample, Handoff
from app.storyboard import Scene as ContentScene, Storyboard as ContentStoryboard

BG, INK, BLUE = PALETTE['background'], STROKE['color'], PALETTE['primary']
COLORS = {name: PALETTE[key] for name,key in dict(
    red='accent', orange='accent', yellow='accent', green='secondary',
    blue='primary', indigo='primary', violet='primary', brown='neutral_600',
    gray='neutral_600', white='neutral_050').items()}

ABSTRACT_SHAPES = set('sound vibration heat cold wind force time many'.split())
CONCEPT_SHAPES = ABSTRACT_SHAPES | set('stick tooth bacteria toothbrush moon candy apple book card diagram_box lightning'.split())
SHAPES = CONCEPT_SHAPES | set('circle square triangle star drop stick sun cloud rainbow block heart'.split())
STICKER_INK = STROKE['body']

# All layout geometry in one place, in native frame pixels or relative fractions.
LAYOUTS = {
    '16x9': dict(margin=96, title_top=56, title_font=TYPE['title'], label_font=TYPE['label'],
                caption_font=TYPE['caption'], count_font=TYPE['label'], bottom=72, center_y=.49,
                heights=dict(single=252, compare=252, sequence=238, stack=340)),
    '9x16': dict(margin=48, title_top=72, title_font=TYPE['title'], label_font=TYPE['label'],
                caption_font=TYPE['caption'], count_font=TYPE['label'], bottom=48, center_y=.55,
                heights=dict(single=760, compare=420, sequence=260, stack=820)),
    'single': dict(centers=(.5,), initial_scale=.62, fill_boost=.19,
                   satellite_x=(.14,.86), satellite_y=-.22, satellite_width=.22, satellite_height=.32),
    'compare': dict(centers=(.28,.72), cell_fraction=.42),
    'sequence': dict(centers=(1/6,.5,5/6), cell_fraction=.29),
    'stack': dict(centers=(.25,.75), cell_fraction=.43),
    'style': dict(label_gap=16, label_height=36, title_pad=40, title_height=1.7,
                  radius=RADIUS['large'], white=10, ink=STICKER_INK, shadow=SHADOW['offset'][1], title_shadow=0,
                  min_subject_area=.55, shape_fill=.97, tile_gap=12,
                  caption_line=8, caption_line_width=80, caption_gap=16,
                  decoration_size=44, decoration_gap=22,
                  relation_overlap=8, relation_width=8, equals_half=16, equals_gap=9,
                  arrow_head=17, arrow_angle=.55, branch_gap=24, branch_width=5),
}
MOTION = dict(appear_fraction=.30, appear_cap=600, appear_start=.86,
              rise_fraction=.35, rise_cap=700, rise_px=40, count_ms=250,
              draw_fraction=.5, move_start=.3, move_fraction=.4, move_px=80,
              merge_fraction=.45, merge_px=60, glow_start=.6, glow_cycles=2)


class Item(BaseModel):
    model_config = ConfigDict(serialize_by_alias=True, populate_by_name=True)
    semantic_category: str | None = None
    spatial_frame: str | None = None
    anchor: str | dict | None = None
    region: str | dict | None = None
    shape: str = 'block'
    color: str = 'blue'
    count: int = Field(default=1, ge=1)
    label: str = ''
    role: str = 'subject'
    id: str | None = Field(default=None, min_length=1)
    parent: str | None = Field(default=None, min_length=1)
    subject_id: str | None = None
    comparison: dict[str, str] | None = None
    from_: int | None = Field(default=None, alias="from", serialization_alias="from", ge=0)
    to: int | None = Field(default=None, ge=0)
    causal_role: Literal["source", "target"] | None = None
    action: Literal["fall"] | None = None
    samples: list[Sample] = Field(default_factory=list)
    animation_state: dict | None = None
    relation_base_bbox: list[float] | None = None
    position: int | None = None
    repair_bboxes: dict[Literal["16x9", "9x16"], Annotated[list[Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]], Field(min_length=4, max_length=4)]] = Field(default_factory=dict, exclude_if=lambda value: not value)
    target_regions: dict[Literal["16x9", "9x16"], Annotated[list[Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]], Field(min_length=4, max_length=4)]] = Field(default_factory=dict)
    placement: dict[Literal["16x9", "9x16"], Annotated[list[Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]], Field(min_length=2, max_length=2)]] = Field(default_factory=dict)
    depth: float = Field(default=0, ge=0)
    size_class: Literal["micro", "small", "medium", "large", "vast"] | None = None
    scale: str = "normal"
    phase: str | None = None
    polarity: Literal["+", "-"] = "-"
    gaze_target: int | None = None
    # None preserves whether mood was supplied; its rendered expression is happy.
    mood: Literal['happy', 'worried', 'sad', 'scared'] | None = None

    state: Literal['decayed'] | None = None

    @model_validator(mode='before')
    @classmethod
    def bacteria_color(cls, value):
        if isinstance(value, dict) and value.get('shape') == 'bacteria' and 'color' not in value:
            return dict(value, color='green')
        return value


from app.sentence_beats import SentenceBeat


class Visual(BaseModel):
    expression: dict | None = None
    ending_hold_ms: int = Field(default=0, ge=0)
    beats: list[SentenceBeat] = Field(default_factory=list)
    camera_motion: CameraMotion | None = None
    poses: list[PoseEvent] = Field(default_factory=list)
    handoff: Handoff | None = None
    spatial_frame: str | None = None
    background: dict | None = None
    layout: str = 'single'
    items: list[Item] = Field(default_factory=lambda: [Item()])
    relation: str = 'none'
    motion: str = 'appear'

    @model_validator(mode='after')
    def parents(self):
        from app.container_semantics import validate_parents
        validate_parents(self.items)
        if any(it.parent is not None for it in self.items) and (not self.background or self.spatial_frame not in {'tank','table','ground'} or self.layout=='narration'):
            for it in self.items:
                it.parent = None
            from app.enforcement import record
            record([dict(code='PARENT_SCOPE_DROPPED', measured=self.spatial_frame,
                         object='scene')], 'storyboard')
        return self

    @model_validator(mode='before')
    @classmethod
    def legacy(cls, value):
        if hasattr(value, 'model_dump'):
            value = value.model_dump()
        if isinstance(value, dict) and (value.get('kind') or
                (value.get('items') and isinstance(value['items'][0], str))):
            return dict(items=[dict(shape='block', label=value.get('items', [''])[0])])
        return value


class Scene(ContentScene):
    visual: Visual

    @model_validator(mode='after')
    def distinct_caption(self):
        # Existing storyboards may repeat captions; rendering removes group labels.
        return self


class Storyboard(ContentStoryboard):
    scenes: list[Scene] = Field(min_length=6, max_length=12)


def normalize(visual):
    return visual if isinstance(visual, Visual) else Visual.model_validate(visual)


def label_for(item):
    # Legacy prose is reduced to its noun phrase; motion never becomes a caption.
    label = re.split(r'缓缓|慢慢|逐渐|向上|向右|上升|下降|移动|靠近|碰到|变成|出现|飘|发光', item.label)[0]
    if item.count > 8 and str(item.count) not in label:
        label = f'{item.count}个{label}'
    return label


def centered_text(fonts, text, size, max_width):
    """Cache a tight ink bitmap: centering uses glyph bounds, not advances."""
    return _text_bitmap(fonts, text, size, int(max_width))


@lru_cache(maxsize=512)
def _text_bitmap(fonts, text, size, max_width):
    if not text:
        return Image.new('RGBA', (1,1))
    size = min((TYPE[key] for key in ('title','explanation','label','caption')),
               key=lambda value: abs(value-size))
    lines=['']; widths=[0.]
    for c in text:
        advance=fonts.font(c,size).getlength(c)
        if c=='\n' or (lines[-1] and widths[-1]+advance>max_width):
            lines.append('');widths.append(0.)
        if c!='\n':
            lines[-1]+=c;widths[-1]+=advance
    width=math.ceil(max(widths))+size*2
    line_height=round(size*TYPE['line_height'])
    im=Image.new('RGBA',(width,size*3+line_height*(len(lines)-1)))
    d=ImageDraw.Draw(im)
    for row,(line,length) in enumerate(zip(lines,widths)):
        x=(width-length)/2
        for c in line:
            font=fonts.font(c,size)
            d.text((x,size+row*line_height),c,font=font,fill=INK,anchor='ls')
            x+=font.getlength(c)
    box=im.getbbox()
    return im.crop(box) if box else Image.new('RGBA',(1,1))



def paste_text(im, bitmap, cx, top):
    x, y = round(cx-bitmap.width/2), round(top)
    im.paste(bitmap, (x,y), bitmap)
    return (x,y,x+bitmap.width,y+bitmap.height)


def union(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def dilate(mask, radius):
    """Separable square dilation in O(log radius) Pillow operations."""
    for axis in (0, 1):
        remaining = radius
        reach = 0
        while remaining:
            step = min(remaining, reach + 1)
            dx, dy = (step, 0) if axis == 0 else (0, step)
            mask = ImageChops.lighter(mask, ImageChops.lighter(
                ImageChops.offset(mask, dx, dy), ImageChops.offset(mask, -dx, -dy)))
            remaining -= step
            reach += step
    return mask


def sticker_surface(mask):
    """Shared sticker ink, white rim and hard shadow for arbitrary silhouettes."""
    s = LAYOUTS['style']
    # Ink is on the silhouette, white is outside it; shadow is a hard (0,8) offset.
    outer = dilate(mask,s['white'])
    shadow = Image.new('L',mask.size)
    shadow.paste(outer,(0,s['shadow']))
    out=Image.new('RGBA',mask.size)
    out.paste(INK,(0,0),shadow)
    out.paste('white',(0,0),outer)
    out.paste(INK,(0,0),mask)
    inner=ImageChops.invert(dilate(ImageChops.invert(mask),s['ink']))
    return out, inner


@lru_cache(maxsize=512)
def sticker(shape, color, width, height, mood=None, phase=0):
    """Silhouette masks give every shape the same outside white rim and shadow."""
    from app.shape_implementations import BASE, require_shape
    require_shape(shape)
    # BASE keeps its original sticker geometry. Other implemented shapes use
    # the existing kit dispatcher, avoiding a second implementation registry.
    if shape not in BASE:
        from worker.scenekit_renderer import sprite
        return sprite(shape, color, max(12, min(width, height)), mood, None)[0]
    if shape in CONCEPT_SHAPES:
        aspect = {'stick': .52, 'toothbrush': .7, 'card': 1.5, 'book': 1.25, 'candy': 1.5}.get(shape, 1.)
        width, height = round(min(width, height*aspect)), round(min(height, width/aspect))
    s = LAYOUTS['style']
    pad = s['white'] + s['ink']
    w,h = max(12,width),max(12,height)
    mask = Image.new('L',(w+2*pad,h+2*pad+s['shadow']))
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
            d.rounded_rectangle((*xy(.32+dx,.28),*xy(.68+dx,.72)),radius=DESIGN_RADIUS['large'],fill=255)
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
    elif shape in ('square','block'): d.rounded_rectangle(bounds, radius=s['radius'] if shape=='block' else RADIUS['square'],fill=255)
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
        d.ellipse((*xy(.34,-.10),*xy(1.12,.77)),fill=0)
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
    elif shape in {'card', 'diagram_box'}: d.rounded_rectangle(bounds,radius=s['radius'],fill=255)
    else: raise ValueError(f'UNKNOWN_SHAPE shape={shape}: 该形状尚未实现')
    out, inner = sticker_surface(mask)
    fill = COLORS.get(color,BLUE)
    if shape in ('tooth','book'): fill='white'
    if shape=='lightning': fill=COLORS['yellow']
    if shape=='moon': fill=PALETTE['secondary']
    if shape=='cold': fill=PALETTE['neutral_300']
    if shape=='drop': fill=PALETTE['neutral_300']  # transmitted light, not an opaque blue ball
    out.paste(fill,(0,0),inner)
    od=ImageDraw.Draw(out)
    if shape=='stick':
        od.ellipse((*xy(.25,.03),*xy(.75,.27)),fill=PALETTE['ground'])
    elif shape=='toothbrush':
        for y in (-.42,-.36,-.30,-.24):
            od.line([xy(*brush(.025,y)),xy(*brush(.17,y))],fill='white',width=max(3,w//40))
    elif shape=='candy':
        od.ellipse((*xy(.22,.08),*xy(.78,.92)),outline=INK,width=DESIGN_STROKE['body'])
        od.arc((*xy(.32,.2),*xy(.68,.8)),180,300,fill='white',width=max(4,w//30))
    elif shape=='apple':
        od.line([xy(.5,.24),xy(.48,.05)],fill=INK,width=DESIGN_STROKE['body'])
        od.polygon([xy(.54,.14),xy(.65,.04),xy(.78,.03),xy(.68,.14)],fill=COLORS['green'])
        od.arc((*xy(.12,.30),*xy(.45,.72)),130,220,fill='white',width=max(4,w//30))
    elif shape=='book':
        od.line([xy(.5,.14),xy(.5,.91)],fill=INK,width=DESIGN_STROKE['body'])
        for y in (.3,.47,.64,.81):
            for a,b in ((.12,.4),(.6,.88)):
                od.line([xy(a,y),xy(b,y+.03 if a<.5 else y-.03)],fill=COLORS['gray'],width=max(3,w//70))
    if shape=='drop':
        # Refraction belongs to scene relations; the drop only has a highlight.
        od.arc((*xy(.12,.43),*xy(.86,.91)),100,175,fill='white',width=max(6,w//25))
    if shape=='sun':
        od.ellipse((*xy(.2,.2),*xy(.8,.8)),fill=fill,outline=INK,width=s['ink'])
    if shape=='rainbow':
        bands=Image.new('RGBA',out.size)
        bd=ImageDraw.Draw(bands)
        for i,c in enumerate('red orange yellow green blue indigo violet'.split()):
            inset=i*.045
            bd.pieslice((*xy(inset,2*inset),*xy(1-inset,2-2*inset)),180,360,fill=COLORS[c])
        out.paste(bands,(0,0),inner)
    if shape in ('stick', 'tooth', 'bacteria', 'candy', 'apple') or (shape == 'lightning' and mood):
        face_box = {'stick': (.27,.035,.73,.26), 'tooth': (.19,.12,.81,.53),
                    'bacteria': (.18,.12,.82,.69), 'candy': (.30,.23,.70,.77),
                    'apple': (.20,.32,.80,.79), 'lightning': (.38,.07,.73,.29)}[shape]
        draw_face(od, (*xy(*face_box[:2]), *xy(*face_box[2:])), mood or 'happy')
    return out


@lru_cache(maxsize=512)
def _legacy_relation_sticker(dx, dy, relation, target, progress=1.):
    """Local, deterministic marker paths; no rotation or change to item geometry."""
    length = math.hypot(dx, dy)
    if length < 1 or progress <= 0:
        return Image.new('RGBA', (1, 1)), (0, 0)
    ux, uy = dx/length, dy/length
    nx, ny = -uy, ux
    polygons = []

    def point(x, y):
        return (ux*x+nx*y, uy*x+ny*y)

    def stroke(a, control, b, width):
        # Quadratic Bezier ribbon, with a 12px belly and narrower marker ends.
        sides = [[], []]
        for i in range(25):
            t=i/24; u=1-t
            x=u*u*a[0]+2*u*t*control[0]+t*t*b[0]
            y=u*u*a[1]+2*u*t*control[1]+t*t*b[1]
            vx=2*(u*(control[0]-a[0])+t*(b[0]-control[0]))
            vy=2*(u*(control[1]-a[1])+t*(b[1]-control[1]))
            norm=max(.001, math.hypot(vx,vy))
            r=width/2*(.68+.32*math.sin(math.pi*t))
            for side, sign in zip(sides, (-1,1)):
                side.append(point(x-sign*vy/norm*r,y+sign*vx/norm*r))
        polygons.append(sides[0]+sides[1][::-1])

    if relation == 'cause' and target in ('sound', 'vibration'):
        # Four separated, unequal rays share a virtual source behind their starts.
        for angle, reach in [(-.52,.62),(-.18,.88),(.20,.74),(.55,.54)]:
            start=min(20,length*.18)
            stop=max(start+1,length*reach*progress)
            if length*reach*progress <= start:
                continue
            a=(start*math.cos(angle),start*math.sin(angle))
            b=(stop*math.cos(angle),stop*math.sin(angle))
            stroke(a,((a[0]+b[0])/2,(a[1]+b[1])/2-2),b,10)
    else:
        end=length*progress
        bend=-.10*length
        # Restrict the original quadratic to [0, progress] for draw motion.
        tip=(end,2*(1-progress)*progress*bend)
        stroke((0,0),(end/2,bend*progress),tip,7 if relation=='arrow' else 12)
        # Rounded, asymmetric triangle with a gently concave base.
        tangent=math.atan2(2*bend*(1-2*progress),length)
        head=min(23,end*.65); half=head*.65
        def hp(x,y):
            return point(tip[0]+x*math.cos(tangent)-y*math.sin(tangent),
                         tip[1]+x*math.sin(tangent)+y*math.cos(tangent))
        polygons.append([hp(0,-2),hp(0,2),hp(-head+2,half),
                         hp(-head,half-2),hp(-head+5,1),
                         hp(-head-1,-half+3),hp(-head+1,-half)])
        if relation=='cause':
            for a,b in [((4,-18),(0,-36)),((20,-15),(31,-30)),((10,18),(17,36))]:
                stroke(a,((a[0]+b[0])/2-1,(a[1]+b[1])/2),b,8)
        if relation in ('split','merge'):
            for off in (-24,24):
                a=(0,off if relation=='merge' else 0)
                b=(end,off if relation=='split' else 0)
                stroke(a,(end/2,(a[1]+b[1])/2+bend),b,7)
    if not polygons:
        return Image.new('RGBA', (1,1)), (0,0)
    points=[p for polygon in polygons for p in polygon]
    rim=LAYOUTS['style']['white']; shadow=LAYOUTS['style']['shadow']
    left=math.floor(min(x for x,y in points))-rim-2
    top=math.floor(min(y for x,y in points))-rim-2
    right=math.ceil(max(x for x,y in points))+rim+3
    bottom=math.ceil(max(y for x,y in points))+rim+shadow+3
    mask=Image.new('L',(right-left,bottom-top))
    draw=ImageDraw.Draw(mask)
    for polygon in polygons:
        draw.polygon([(round(x-left),round(y-top)) for x,y in polygon],fill=255)
    outer=dilate(mask,rim)
    out=Image.new('RGBA',mask.size)
    out.paste(INK,(0,shadow),outer)
    out.paste('white',(0,0),outer)
    out.paste(INK,(0,0),mask)
    return out,(left,top)


@lru_cache(maxsize=512)
def relation_sticker(dx, dy, relation, target, progress=1., radii=()):
    """70% of contour clearance; white underneath constant-width ink."""
    if relation not in ('flow', 'arrow', 'cause'):
        return _legacy_relation_sticker(dx, dy, relation, target, progress)
    distance = math.hypot(dx, dy)
    if distance < 1 or progress <= 0:
        return Image.new('RGBA', (1, 1)), (0, 0)
    ux, uy = dx/distance, dy/distance
    nx, ny = -uy, ux
    # In screen coordinates the normal must point upward for either x direction.
    bend_sign = -1 if ny >= 0 else 1
    lines, polygons = [], []
    def pt(x, y):
        return ux*x+nx*y, uy*x+ny*y
    burst = relation == 'cause' and target in ('sound', 'vibration')
    if burst:
        # Seven rays strictly inside the rear half-plane, never in the gap.
        for i, (degrees, reach) in enumerate(zip((105,130,155,180,205,230,255),
                                                (18,32,24,40,21,35,27))):
            angle = math.radians(degrees)
            radius = radii[i] if radii else 0
            start = radius+12+3  # round cap's nearest edge is 12px off silhouette
            end = start+max(0, reach*progress-6)
            lines.append(([pt(start*math.cos(angle),start*math.sin(angle)),
                           pt(end*math.cos(angle),end*math.sin(angle))],6))
    else:
        length = .70*distance
        origin = .15*distance
        bend = bend_sign*.10*length
        points=[]
        for i in range(49):
            t=progress*i/48
            x=origin+length*t
            y=2*(1-t)*t*bend
            vx,vy=length,2*(1-2*t)*bend
            norm=math.hypot(vx,vy)
            # Smooth one-cycle normal wobble; phase distinguishes arrow/flow.
            wobble=1.5*math.sin(2*math.pi*t)*( -1 if relation=='arrow' else 1)
            points.append(pt(x-vy/norm*wobble,y+vx/norm*wobble))
        lines.append((points,11))
        tip=points[-1]
        angle=math.atan2(uy,ux)+math.atan2(2*(1-2*progress)*bend,length)
        head=min(24,length*progress*.65)
        half=11*2.6/2*min(1,progress*4)
        def hp(x,y):
            return (tip[0]+x*math.cos(angle)-y*math.sin(angle),
                    tip[1]+x*math.sin(angle)+y*math.cos(angle))
        polygons.append([hp(0,0),hp(-head+1,half),hp(-head*.88,0),hp(-head-1,-half)])
        if relation=='cause':
            for a,b in [((origin+3,-20),(origin-2,-38)),
                        ((origin+20,-19),(origin+30,-34)),
                        ((origin+7,20),(origin+12,38))]:
                lines.append(([pt(*a),pt(*b)],6))
    all_points=[p for points,width in lines for p in points]+[p for poly in polygons for p in poly]
    left=math.floor(min(p[0] for p in all_points))-12
    top=math.floor(min(p[1] for p in all_points))-12
    right=math.ceil(max(p[0] for p in all_points))+13
    bottom=math.ceil(max(p[1] for p in all_points))+13
    mask=Image.new('L',(right-left,bottom-top))
    draw=ImageDraw.Draw(mask)
    for points,width in lines:
        local=[(round(x-left),round(y-top)) for x,y in points]
        draw.line(local,fill=255,width=width,joint='curve')
        for x,y in (local[0],local[-1]):
            r=(width-1)/2
            draw.ellipse((x-r,y-r,x+r,y+r),fill=255)
    for poly in polygons:
        draw.polygon([(round(x-left),round(y-top)) for x,y in poly],fill=255)
    out=Image.new('RGBA',mask.size)
    out.paste('white',(0,0),dilate(mask,5))
    out.paste(INK,(0,0),mask)
    return out,(left,top)


def _silhouette_radius(sprite, ux, uy):
    """Outermost visible pixel on a ray from the icon's visible center."""
    # Nominal icon size is its shorter canvas dimension; 0.45 is a last-resort
    # radius so a missing silhouette cannot abort the episode.
    fallback = .45 * min(sprite.size)
    try:
        bounds = sprite.getbbox()
    except Exception:
        bounds = None
    try:
        alpha = sprite.getchannel('A')
        if bounds is None:
            # Retry once by drawing the alpha mask onto a fresh measuring canvas.
            canvas = Image.new('L', sprite.size)
            ImageDraw.Draw(canvas).bitmap((0, 0), alpha, fill=255)
            bounds = canvas.getbbox()
        if bounds is None:
            return fallback
        cx,cy=(bounds[0]+bounds[2])/2,(bounds[1]+bounds[3])/2
        radius=0
        for step in range(math.ceil(math.hypot(sprite.width,sprite.height))*2):
            r=step/2
            x,y=round(cx+ux*r),round(cy+uy*r)
            if not (0<=x<sprite.width and 0<=y<sprite.height):
                break
            if alpha.getpixel((x,y)):
                radius=r
        return radius
    except Exception:
        # Measurement is best-effort, including Pillow failures during the retry.
        return fallback


def draw_face(draw, box, mood):
    x0,y0,x1,y1 = box
    fw,fh = x1-x0,y1-y0
    def pt(x,y): return (round(x0+x*fw), round(y0+y*fh))
    def rect(a,b,c,d): return (*pt(a,b),*pt(c,d))
    pen=max(2,round(min(fw,fh)*.045))
    for x in (.25,.75):
        if mood == 'sad':
            draw.ellipse(rect(x-.19,.22,x+.19,.54),fill='white',outline=INK,width=pen)
            draw.arc(rect(x-.19,.05,x+.19,.49),0,180,fill=INK,width=pen*2)
            draw.ellipse(rect(x-.07,.36,x+.07,.49),fill=INK)
        else:
            top,bottom = ((.02,.62) if mood == 'scared' else (.13,.55))
            draw.ellipse(rect(x-.19,top,x+.19,bottom),fill='white',outline=INK,width=pen)
            draw.ellipse(rect(x-.09,.25,x+.09,.49),fill=INK)
            draw.ellipse(rect(x-.065,.26,x-.015,.32),fill='white')
            if mood == 'worried':
                draw.line([pt(x-.20,-.09 if x<.5 else .15),
                           pt(x+.20,.04 if x<.5 else .08)],fill=INK,width=pen*2)
    if mood == 'happy':
        draw.arc(rect(.24,.46,.76,.96),0,180,fill=INK,width=pen*2)
    elif mood == 'worried':
        # Closed crescent sweat bead on the forehead, in the same ink/white style.
        bead = []
        for a,b,c in [((.84,-.08),(1.23,.24),(.94,.30)),
                      ((.94,.30),(.98,.12),(.84,-.08))]:
            for i in range(25):
                t=i/24; u=1-t
                bead.append(pt(u*u*a[0]+2*u*t*b[0]+t*t*c[0],
                               u*u*a[1]+2*u*t*b[1]+t*t*c[1]))
        draw.polygon(bead,fill='white')
        draw.line(bead+[bead[0]],fill=INK,width=pen,joint='curve')
        draw.line([pt(.28+i*.44/24,.78+.045*math.sin(i*math.tau/12))
                   for i in range(25)],fill=INK,width=pen, joint='curve')
    elif mood == 'sad':
        draw.arc(rect(.24,.73,.76,1.12),180,360,fill=INK,width=pen*2)
    else:
        draw.ellipse(rect(.37,.68,.63,.99),fill=INK)


@lru_cache(maxsize=512)
def item_sticker(shape, color, width, height, label, fonts, mood=None, state=None):
    from app.shape_implementations import require_shape
    require_shape(shape)
    sprite = sticker(shape, color, width, height, mood)
    if shape == 'card' and label:
        sprite = sprite.copy()
        bitmap = centered_text(fonts, label, TYPE['label'], max(12, sprite.width-64))
        paste_text(sprite, bitmap, sprite.width/2, (sprite.height-8-bitmap.height)/2)
    elif shape == 'tooth' and state == 'decayed':
        sprite = sprite.copy()
        d = ImageDraw.Draw(sprite)
        x,y = sprite.width*.77,sprite.height*.57
        r = max(4,min(sprite.size)*.055)
        d.ellipse((x-r,y-r,x+r,y+r),fill=INK)
    return sprite


@lru_cache(maxsize=64)
def abstract_frames(shape, color, width, height):
    """Prepare a finite bank before playback; never rebuild paths per frame."""
    if shape == 'sound':
        return tuple(sticker(shape,color,width,height,phase=p) for p in range(9))
    if shape == 'vibration':
        return tuple(sticker(shape,color,width,height,phase=p) for p in range(-2,3))
    base=sticker(shape,color,width,height)
    frames=[]
    for p in range(17):
        sprite=Image.new('RGBA',base.size)
        sprite.paste(base,(0,-round(4*p/16)))
        sprite.putalpha(sprite.getchannel('A').point(lambda v: round(v*(1-p/16))))
        frames.append(sprite)
    return tuple(frames)


def abstract_phase(shape, ms):
    if shape == 'sound':
        return round(8*math.sin(math.pi*(ms%1200)/1200)**2)
    if shape == 'vibration':
        return 2+round(2*math.sin(math.tau*(ms%150)/150))
    return round(16*(ms%1600)/1600)


def motion_state(motion, local, duration):
    t=max(0,min(1,local)); ms=t*duration
    state=dict(scale=1.,dy=0.,dx=0.,alpha=1.,draw=1.,merge=0.,glow=0.,visible=10**9)
    if motion=='appear':
        p=min(1,ms/min(MOTION['appear_fraction']*duration,MOTION['appear_cap']))
        ease=1+2.70158*(p-1)**3+1.70158*(p-1)**2
        state['scale']=MOTION['appear_start']+(1-MOTION['appear_start'])*ease
    elif motion=='rise':
        p=min(1,ms/min(MOTION['rise_fraction']*duration,MOTION['rise_cap']))
        state.update(dy=MOTION['rise_px']*(1-p)**2,alpha=p)
    elif motion=='count': state['visible']=1+int(ms//MOTION['count_ms'])
    elif motion=='draw': state['draw']=min(1,t/MOTION['draw_fraction'])
    elif motion=='move_right':
        p=max(0,min(1,(t-MOTION['move_start'])/MOTION['move_fraction']))
        state['dx']=MOTION['move_px']*math.sin(math.pi*p)**2
    elif motion=='merge': state['merge']=MOTION['merge_px']*min(1,t/MOTION['merge_fraction'])
    elif motion=='glow' and t>=MOTION['glow_start']:
        p=(t-MOTION['glow_start'])/(1-MOTION['glow_start'])
        state['glow']=math.sin(math.pi*MOTION['glow_cycles']*p)**2
    return state


def breathing_scale(item, local, duration):
    if item.shape not in ('stick', 'bacteria') and not (item.shape == 'tooth' and item.mood is not None):
        return 1.
    seconds = max(0., min(1., local))*duration/1000
    return 1. + .0075*(1.-math.cos(math.tau*seconds/1.6))


def frame(scene, title, size, local, fonts, *, debug=None):
    w,h=size; fmt='16x9' if w>h else '9x16'; cfg=LAYOUTS[fmt]; s=LAYOUTS['style']
    visual=normalize(scene.visual); layout=visual.layout if visual.layout in ('single','compare','sequence','stack') else 'single'
    items=[v for v in visual.items if v.role!='decoration'] or [Item()]
    decorations=[v for v in visual.items if v.role=='decoration'][:2]
    im=Image.new('RGB',size,BG); d=ImageDraw.Draw(im)
    margin=cfg['margin']; area_w=w-2*margin; area_h=cfg['heights'][layout]
    vertical = layout == 'stack' or (fmt == '9x16' and layout in ('compare', 'sequence'))
    if fmt == '9x16':
        if layout in ('compare', 'sequence'):
            # Per-item heights plus label space, capped to the portrait band.
            area_h = min(cfg['heights']['stack'],
                         max(cfg['heights']['single'], area_h*len(items))
                         + s['label_height'] + s['label_gap'])
        # Keep the content band in the lower safe area in every portrait layout.
        cy = max(h*cfg['center_y'], h-128-area_h/2)
        cy = min(cy, h-cfg['bottom']-area_h/2)
    else:
        cy = h*cfg['center_y']
    area=(margin,round(cy-area_h/2),w-margin,round(cy+area_h/2))
    title_im=centered_text(fonts,title,cfg['title_font'],area_w-2*s['title_pad'])
    tw=title_im.width+2*s['title_pad']; th=cfg['title_font']*s['title_height']
    left=round((w-tw)/2)
    tb=(left,cfg['title_top'],left+tw,round(cfg['title_top']+th))
    shadow=tuple(v+(s['title_shadow'] if i%2 else 0) for i,v in enumerate(tb))
    d.rounded_rectangle(shadow,s['radius'],fill=PALETTE['ground'])
    d.rounded_rectangle((tb[0]-s['white'],tb[1]-s['white'],tb[2]+s['white'],tb[3]+s['white']),s['radius'],fill='white')
    d.rounded_rectangle(tb,s['radius'],fill='white',outline=INK,width=s['ink'])
    title_box=paste_text(im,title_im,w/2,(tb[1]+tb[3]-title_im.height)/2)
    state=motion_state(visual.motion,local,scene.duration_ms)
    if visual.relation == 'count':
        state['visible']=1+int(max(0,local)*scene.duration_ms//MOTION['count_ms'])
    groups=[]; labels=[]; sprites=[]; budget=state['visible']
    for i,item in enumerate(items):
        from app.shape_implementations import require_shape
        n=min(item.count,8); shape=require_shape(item.shape)
        if layout=='single':
            # Primary group dominates; secondary tools are small satellites.
            primary=next((j for j,it in enumerate(items) if it.role in ('subject','result')),0)
            main=i==primary
            cx=w/2 if main else margin+area_w*LAYOUTS['single']['satellite_x'][i%2]
            gy=cy if main else cy+area_h*LAYOUTS['single']['satellite_y']
            cw,ch=(area_w,area_h) if main else (area_w*LAYOUTS['single']['satellite_width'],area_h*LAYOUTS['single']['satellite_height'])
        elif vertical:
            cx=w/2; gy=area[1]+area_h*(i+.5)/len(items)
            cw,ch=area_w,area_h/len(items)-s['label_height']-s['label_gap']
            if fmt == '9x16':
                counted = visual.motion == 'count' or visual.relation == 'count'
                text = f'{min(n, budget)} / {item.count} {label_for(item)}' if counted else label_for(item)
                label_h = centered_text(fonts, text, cfg['count_font'] if counted else cfg['label_font'], area_w).height
                ch = area_h/len(items)-label_h-s['label_gap']
        else:
            centers=LAYOUTS[layout]['centers']; cx=margin+area_w*centers[i%len(centers)]; gy=cy
            cw,ch=area_w*LAYOUTS[layout]['cell_fraction'],area_h
        cx+=state['dx']
        if len(items)>1: cx+=state['merge']*(1 if i==0 else -1 if i==len(items)-1 else 0)
        gy+=state['dy']
        cols=min(n,max(1,round(math.sqrt(n*cw/max(ch,1)))))
        rows=math.ceil(n/cols)
        tile_w=(cw-(cols-1)*s['tile_gap'])/cols
        tile_h=(ch-(rows-1)*s['tile_gap'])/rows
        # Start with §2's 62%; enlarge against actual visible silhouette bounds.
        scale=LAYOUTS['single']['initial_scale'] if layout=='single' and main else s['shape_fill']
        if fmt == '9x16' and vertical:
            scale = .99
        if layout=='single' and main:
            scale=max(scale,math.sqrt(s['min_subject_area'])+LAYOUTS['single']['fill_boost'])
        boxes=[]; group_visible=min(n,budget)
        for j in range(n):
            sw=max(12,round(tile_w*scale-2*s['white'])); sh=max(12,round(tile_h*scale-2*s['white']-s['shadow']))
            sprite=item_sticker(shape,item.color,sw,sh,item.label,fonts,item.mood,item.state)
            static_sprite=sprite
            if shape in ('sound','heat','vibration'):
                bank=abstract_frames(shape,item.color,sw,sh)
                sprite=bank[abstract_phase(shape,max(0,local)*scene.duration_ms)]
            breath=breathing_scale(item,local,scene.duration_ms)
            if state['scale'] != 1 or breath != 1:
                sprite=sprite.resize((round(sprite.width*state['scale']), round(sprite.height*state['scale']*breath)))
            x=round(cx-cw/2+(j%cols+.5)*tile_w+(j%cols)*s['tile_gap']-sprite.width/2)
            y=round(gy-ch/2+(j//cols+.5)*tile_h+(j//cols)*s['tile_gap']-sprite.height/2)
            bounds_sprite = static_sprite if shape in ('sound','heat','vibration') else sprite
            if bounds_sprite is static_sprite and state['scale'] != 1:
                bounds_sprite=static_sprite.resize(sprite.size)
            b=bounds_sprite.getbbox(); box=(x+b[0],y+b[1],x+b[2],y+b[3]); boxes.append(box)
            if j < budget:
                sprites.append((sprite,x,y,item))
        budget=max(0,budget-n)
        box=union(boxes)
        groups.append(dict(box=box,center_x=(box[0]+box[2])/2,role=item.role,item=item,visible=group_visible))
    # Geometric subjects fill the area; concept icons retain their natural aspect
    # ratio and fit the role's cell, even when a person or brush is narrow.
    if layout=='single':
        g=groups[primary]; b=g['box']; ratio=(b[2]-b[0])*(b[3]-b[1])/(area_w*area_h)
        if ratio < s['min_subject_area'] and g['item'].shape in SHAPES-CONCEPT_SHAPES:
            factor=math.sqrt(s['min_subject_area']/ratio)
            adjusted=[]
            for sprite,x,y,item in sprites:
                if item is g['item']:
                    sprite=sprite.resize((math.ceil(sprite.width*factor),math.ceil(sprite.height*factor)))
                    x=round(w/2+(x-w/2)*factor); y=round(cy+(y-cy)*factor)
                adjusted.append((sprite,x,y,item))
            sprites=adjusted
            boxes=[]
            for sprite,x,y,item in sprites:
                if item is g['item']:
                    bb=sprite.getbbox(); boxes.append((x+bb[0],y+bb[1],x+bb[2],y+bb[3]))
            if boxes: g['box']=union(boxes); g['center_x']=(g['box'][0]+g['box'][2])/2
    if fmt == '9x16':
        # Clamp each complete group (including its label) before compositing.
        # Count labels can be taller than the ordinary 36px reservation.
        label_bottom = h-cfg['bottom']
        if scene.on_screen_text:
            caption = centered_text(fonts, scene.on_screen_text, cfg['caption_font'], area_w)
            label_bottom -= caption.height+s['caption_gap']+s['caption_line']+8
        lowest = max(g['box'][3] for g in groups)
        shift = max(0, h-128-lowest)
        if shift:
            for g in groups:
                b = g['box']
                g['box'] = (b[0], b[1]+shift, b[2], b[3]+shift)
            sprites = [(sp, x, y+shift, it) for sp, x, y, it in sprites]
        for g in groups:
            item = g['item']
            text = label_for(item)
            counted = visual.motion == 'count' or visual.relation == 'count'
            if counted:
                text = f'{g["visible"]} / {item.count} {text}'
            has_label = text and item.shape in SHAPES and item.shape != 'card' and item.label != scene.on_screen_text
            b = g['box']
            label_height = centered_text(fonts, text, cfg['count_font'] if counted else cfg['label_font'],
                                         min(area_w, max(60, b[2]-b[0]))).height if has_label else 0
            extra = s['label_gap']+label_height if has_label else 0
            dx = max(margin-b[0], min(0, w-margin-b[2]))
            dy = min(0, label_bottom-extra-b[3])
            g['box'] = (b[0]+dx, b[1]+dy, b[2]+dx, b[3]+dy)
            g['center_x'] += dx
            sprites = [(sp, x+dx if it is item else x, y+dy if it is item else y, it)
                       for sp, x, y, it in sprites]
    # Relationship marks are actual graphics in the gaps, underneath the stickers.
    d=ImageDraw.Draw(im)
    for a,b in zip(groups,groups[1:]):
        if visual.relation=='none' and layout!='sequence': continue
        ba,bb=a['box'],b['box']
        if vertical:
            label_h = s['label_height']
            if fmt == '9x16':
                label_h = centered_text(fonts, label_for(a['item']), cfg['label_font'], area_w).height
            start=((ba[0]+ba[2])/2,ba[3]+label_h+s['label_gap']); end=((bb[0]+bb[2])/2,bb[1])
        else: start=(ba[2]-s['relation_overlap'],cy); end=(bb[0]+s['relation_overlap'],cy)
        if visual.relation=='equals':
            mx=(start[0]+end[0])/2
            my=(start[1]+end[1])/2 if fmt == '9x16' and vertical else cy
            for dy in (-s['equals_gap'],s['equals_gap']):
                d.line((mx-s['equals_half'],my+dy,mx+s['equals_half'],my+dy),fill=INK,width=s['ink'])
        else:
            radii=()
            if visual.relation in ('flow','arrow','cause'):
                ac=((ba[0]+ba[2])/2,(ba[1]+ba[3])/2)
                bc=((bb[0]+bb[2])/2,(bb[1]+bb[3])/2)
                dx,dy=bc[0]-ac[0],bc[1]-ac[1]
                distance=max(1,math.hypot(dx,dy)); ux,uy=dx/distance,dy/distance
                source=next((sp for sp,x,y,it in sprites if it is a['item']),None)
                target=next((sp for sp,x,y,it in sprites if it is b['item']),None)
                if source is not None and target is not None and not (fmt == '9x16' and vertical):
                    if visual.relation=='cause' and b['item'].shape in ('sound','vibration'):
                        start=ac; end=bc
                        radii=tuple(_silhouette_radius(source,
                            ux*math.cos(math.radians(deg))-uy*math.sin(math.radians(deg)),
                            uy*math.cos(math.radians(deg))+ux*math.sin(math.radians(deg)))
                            for deg in (105,130,155,180,205,230,255))
                    else:
                        ra=_silhouette_radius(source,ux,uy)
                        rb=_silhouette_radius(target,-ux,-uy)
                        start=(ac[0]+ux*ra,ac[1]+uy*ra)
                        end=(bc[0]-ux*rb,bc[1]-uy*rb)
            mark, offset = relation_sticker(round(end[0]-start[0]), round(end[1]-start[1]),
                                            visual.relation, b['item'].shape, state['draw'], radii)
            im.paste(mark, (round(start[0])+offset[0], round(start[1])+offset[1]), mark)
    for sprite,x,y,item in sprites:
        if state['glow'] and item.role=='result':
            alpha=dilate(sprite.getchannel('A'),8)
            glow=Image.new('RGB',sprite.size,COLORS['yellow'])
            im.paste(glow,(x,y),alpha.point(lambda v:round(v*state['glow'])))
        if state['alpha']<1:
            sprite=sprite.copy(); sprite.putalpha(sprite.getchannel('A').point(lambda v:round(v*state['alpha'])))
        if item.shape in ('rainbow','lightning') and state['draw']<1:
            sprite=sprite.crop((0,0,max(1,round(sprite.width*state['draw'])),sprite.height))
        im.paste(sprite,(x,y),sprite)
    for g in groups:
        item=g['item']
        if item.shape == 'card' or item.shape not in SHAPES or (scene.on_screen_text and item.label == scene.on_screen_text):
            continue
        text=label_for(item)
        if visual.motion=='count' or visual.relation=='count':
            text=f'{g['visible']} / {g["item"].count} {text}'
        if text:
            label_size=cfg['count_font'] if visual.motion=='count' or visual.relation=='count' else cfg['label_font']
            bitmap=centered_text(fonts,text,label_size,min(area_w,max(60,g['box'][2]-g['box'][0])) if fmt == '9x16' else max(60,g['box'][2]-g['box'][0]))
            box=paste_text(im,bitmap,g['center_x'],g['box'][3]+s['label_gap'])
            labels.append(dict(box=box,group_center_x=g['center_x'],text=text))
    for i,item in enumerate(decorations):
        dec=item_sticker(item.shape,item.color,s['decoration_size'],s['decoration_size'],item.label,fonts,item.mood,item.state)
        im.paste(dec,(margin if i==0 else w-margin-dec.width,area[1]-dec.height-s['decoration_gap']),dec)
    caption_box=None
    if scene.on_screen_text:
        caption=centered_text(fonts,scene.on_screen_text,cfg['caption_font'],area_w)
        caption_box=paste_text(im,caption,w/2,h-cfg['bottom']-caption.height)
        d=ImageDraw.Draw(im); y=caption_box[1]-s['caption_gap']-s['caption_line']
        d.rectangle((w/2-s['caption_line_width']/2,y,w/2+s['caption_line_width']/2,y+s['caption_line']-1),fill=BLUE)
    if debug is not None:
        debug.update(area=area,title_box=title_box,title_sticker=tb,groups=groups,labels=labels,
                     caption_box=caption_box,text_regions=int(bool(title))+int(bool(labels))+int(bool(caption_box)),text_boxes=[title_box]+[v['box'] for v in labels]+([caption_box] if caption_box else []))
    return im
