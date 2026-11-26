from PIL.ImageColor import getrgb as design_rgb
from worker.design_tokens import PALETTE
from worker.design_tokens import PALETTE, STROKE as DESIGN_STROKE, RADIUS as DESIGN_RADIUS
from worker.design_tokens import PALETTE, STROKE, RADIUS, SHADOW
"""Concrete O1 parts, using opaque fills and ink outlines. No sticker rings."""
from PIL import Image, ImageDraw, ImageColor
from worker.visual import COLORS
from app.shape_implementations import O1, B2, require_shape
INK=design_rgb(PALETTE['neutral_900'])

def sprite(shape,color,diameter):
 # Local geometry backend only; dispatcher selects this inventory from
 # app.shape_implementations. Full union is checked in test_w294.py.
 require_shape(shape, O1 | B2)
 if shape in B2:
  from worker.shapes_b2 import sprite as draw_b2
  return draw_b2(shape,color,diameter)
 if shape in {'foot_left','foot_right','knife','ear_section'}:
  from worker.shapes_w42 import sprite as concrete_w42
  return concrete_w42(shape,color,diameter)
 if shape=='awen':
  im,mask=awen_sprite(diameter)[:2];im.info['rendered_shape']='awen'
  return im,mask
 n=diameter; im=Image.new('RGBA',(n,n)); d=ImageDraw.Draw(im); w=STROKE['body']
 main=ImageColor.getrgb(COLORS[color]);water=design_rgb(PALETTE['primary']);pale=design_rgb(PALETTE['neutral_300'])
 def box(v):return tuple(round(x*(n-1)) for x in v)
 def poly(points,fill):d.polygon([(round(x*(n-1)),round(y*(n-1))) for x,y in points],fill=fill,outline=INK,width=w)
 def ellipse(b,fill):d.ellipse(box(b),fill=fill,outline=INK,width=w)
 def line(p,fill=INK,width=None):d.line([(round(x*(n-1)),round(y*(n-1))) for x,y in p],fill=fill,width=width or w,joint='curve')
 if shape.startswith('water_cup'):
  tall=shape.endswith('tall');left,right,top=(.30,.70,.04) if tall else (.06,.94,.36)
  d.rounded_rectangle(box((left,top,right,.96)),radius=RADIUS['small'],fill=pale,outline=INK,width=w)
  level=.23 if tall else .63
  d.rectangle(box((left+.025,level,right-.025,.93)),fill=water)
  line([(left,level),(right,level)])
 elif shape.startswith('cookie'):
  if shape=='cookie_whole':ellipse((.04,.04,.96,.96),main)
  else:
   start,end=(90,270) if shape=='cookie_half' else (0,90) if shape=='cookie_small' else (90,360)
   d.pieslice(box((.04,.04,.96,.96)),start,end,fill=main,outline=INK,width=w)
  for x,y in [( .22,.36),(.34,.64),(.40,.23),(.70,.35),(.65,.70)]:
   if shape=='cookie_whole' or shape=='cookie_half' and x<.5:ellipse((x-.025,y-.025,x+.025,y+.025),design_rgb(PALETTE['neutral_600']))
 elif shape.startswith('shoe'):
  # Side view: toe extends left; heel and ankle rise on the right.
  # Mirror the complete upper, sole and laces, before applying world lighting.
  poly([(.04,.70),(.10,.58),(.40,.51),(.57,.33),(.59,.12),
        (.83,.10),(.91,.25),(.93,.80),(.85,.88),(.12,.88),(.04,.82)],main)
  poly([(.04,.76),(.44,.78),(.93,.76),(.93,.88),(.83,.94),
        (.12,.94),(.04,.88)],design_rgb(PALETTE['ground']))
  line([(.60,.17),(.65,.31),(.83,.33),(.87,.20)],design_rgb(PALETTE['neutral_900']),max(w,round(n*.05)))
  for x,y in ((.47,.48),(.53,.41),(.58,.34)):
   line([(x,y),(x+.14,y+.06)],design_rgb(PALETTE['ground']))
  if shape=='shoe_right':im=im.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
 elif shape.startswith('route'):
  # Same endpoints and equally spaced distance marks; route_long has an actual detour.
  points=[(.12,.80),(.88,.20)] if shape=='route_short' else [(.12,.80),(.12,.20),(.88,.80),(.88,.20)]
  line(points,INK,max(w,round(n*.12)));line(points,main,max(w,round(n*.075)))
  ellipse((.02,.70,.22,.90),design_rgb(PALETTE['accent']));ellipse((.78,.10,.98,.30),design_rgb(PALETTE['secondary']))
 elif shape.startswith('tank'):
  d.rectangle(box((.03,.08,.97,.97)),fill=pale,outline=INK,width=w)
  d.rectangle(box((.06,.36,.94,.94)),fill=water);line([(.03,.36),(.97,.36)])
  if shape=='tank_stone':poly([(.33,.92),(.26,.81),(.37,.68),(.55,.64),(.68,.79),(.64,.92)],design_rgb(PALETTE['neutral_600']))
  else:
   d.rounded_rectangle(box((.19,.24,.80,.46)),radius=RADIUS['small'],fill=PALETTE['accent'],outline=INK,width=w)
   line([(.29,.30),(.68,.32)]);line([(.36,.39),(.72,.39)])
 elif shape=='drum':
  d.rectangle(box((.09,.28,.91,.82)),fill=main,outline=INK,width=w)
  ellipse((.09,.10,.91,.43),design_rgb(PALETTE['ground']));d.arc(box((.09,.66,.91,.96)),0,180,fill=INK,width=w)
  for x in (.22,.45,.68):line([(x,.44),(x+.1,.79)])
 elif shape=='ear_section':
  d.arc(box((.04,.03,.86,.97)),45,320,fill=INK,width=max(w,round(n*.11)))
  d.arc(box((.16,.13,.74,.85)),35,300,fill=main,width=max(w,round(n*.08)))
  line([(.42,.43),(.28,.52),(.45,.64),(.84,.64)],main,max(w,round(n*.09)))
  line([(.86,.46),(.91,.74)],design_rgb(PALETTE['accent']),max(w,round(n*.055)))
 elif shape=='sugar_grains':
  for x,y in [(.2,.67),(.47,.68),(.72,.67),(.34,.42),(.59,.42),(.46,.17)]:
   poly([(x-.1,y),(x,y-.05),(x+.12,y),(x+.12,y+.18),(x-.1,y+.18)],design_rgb(PALETTE['ground']))
 elif shape=='sugar_solution':
  d.rounded_rectangle(box((.09,.05,.91,.97)),radius=RADIUS['small'],fill=pale,outline=INK,width=w)
  d.rectangle(box((.12,.25,.88,.94)),fill=water)
  # Symbolic dissolved particles, explicitly identified as magnified schematic in scene label.
  for x,y in [(.25,.35),(.64,.40),(.43,.58),(.73,.71),(.26,.82)]:
   ellipse((x-.025,y-.025,x+.025,y+.025),design_rgb(PALETTE['ground']))
 elif shape.startswith('ice'):
  if shape=='ice_melting':ellipse((.02,.72,.98,.98),water)
  poly([(.18,.28),(.40,.10),(.83,.19),(.83,.72),(.62,.91),(.18,.79)],pale)
  line([(.18,.28),(.62,.40),(.83,.19)]);line([(.62,.40),(.62,.91)])
 elif shape=='rotation_globe':
  ellipse((.03,.03,.97,.97),water)
  poly([(.19,.26),(.39,.14),(.52,.32),(.37,.49),(.43,.72),(.27,.84),(.19,.56)],design_rgb(PALETTE['secondary']))
  # W33: use the shared feathered dark side, never an opaque navy half-disc.
 elif shape=='vapor_particles':
  for x,y in [(.13,.17),(.72,.12),(.40,.44),(.12,.81),(.82,.79)]:ellipse((x-.045,y-.045,x+.045,y+.045),pale)
 elif shape=='rain_basin':
  poly([(.02,.28),(.23,.48),(.38,.69),(.68,.69),(.85,.43),(.98,.28),(.93,.97),(.07,.97)],design_rgb(PALETTE['neutral_600']))
  poly([(.30,.67),(.70,.67),(.84,.82),(.68,.92),(.28,.91),(.15,.82)],water)
  from worker.shapes_b4 import sprite as nature_sprite
  rain=nature_sprite('rain',color,n)[0]
  im.alpha_composite(rain,(0,round(n*.08)))
 else:raise ValueError(f'UNKNOWN_SHAPE shape={shape}: 该形状尚未实现')
 mask=im.getchannel('A');bounds=mask.getbbox()
 if not bounds:raise ValueError('empty shape')
 im=im.crop(bounds)
 from worker.scenekit_shapes import soft_lighting
 im=soft_lighting(im,mask.crop(bounds),grammar_shape=shape,arc=shape in {'rotation_globe','cookie_whole','cookie_half','cookie_small'},repair=True)
 im.info['rendered_shape']=shape
 return im,mask.crop(bounds)


def _soft_character_body(obj):
    # Reuse the frozen contour and eyes, replacing the old diagonal lighting only.
    import types
    from worker import scenekit_v9 as sk
    from worker.scenekit_shapes import soft_lighting
    declarations=[]
    def layers(mask, material, *args):
        mask=mask.point(lambda a:255 if a>=128 else 0)
        fill=Image.new('RGBA',mask.size,material.color+(255,))
        fill.putalpha(mask)
        _,stroke,*_=sk.material_layers(mask,material,*args)
        stroke.putalpha(stroke.getchannel('A').point(lambda a:255 if a>=128 else 0))
        lit=fill
        from worker.lighting_declaration import unlit
        lit.info['lighting_declaration']=unlit('awen',lit)
        declarations.append(lit.info['lighting_declaration'])
        return lit,stroke
    def silhouette(obj):
        return sk.silhouette(obj).point(lambda a:255 if a>=128 else 0)
    draw=types.FunctionType(sk.sprite.__code__,dict(sk.sprite.__globals__,material_layers=layers,silhouette=silhouette))
    im,mask=draw(obj)
    im.info['lighting_declaration']=declarations[0]
    return im,mask



def awen_sprite(diameter, direction=(1,0), *, point=0., wonder=0., float_y=0.):
    from worker.ambient import blinking, sprite as animate
    im, mask, eyes = _awen_sprite(diameter, direction, point=point, wonder=wonder, float_y=float_y, blink=blinking())
    out = animate(im, 'awen')
    sx, sy = out.width/im.width, out.height/im.height
    return out, out.getchannel('A'), {k:(v[0]*sx,v[1]*sy) for k,v in eyes.items()}


from functools import lru_cache
@lru_cache(maxsize=256)
def _awen_sprite(diameter, direction=(1,0), *, point=0., wonder=0., float_y=0., blink=False):
    """Frozen B character body/eyes, hands and question tail; eyes follow the teaching target."""
    import json, math
    from pathlib import Path
    from PIL import ImageFont
    from worker import scenekit_v9 as sk
    p=json.loads(Path(__file__).with_name('awen_o1.json').read_text())
    if blink:
        p['eye_height_D'] = .008
    if point:
        length=max(1,math.hypot(*direction))
        old=p['hands_fixed_xy_D'][0]
        p['hands_fixed_xy_D'][0]=[old[i]*(1-point)+direction[i]/length*.70*point for i in (0,1)]
    n=diameter; pad=math.ceil(n*.18); body=round(n*.64); x=round(n*.10); y=n-body+pad
    dx,dy=direction; norm=max(1,math.hypot(dx,dy));offset=(dx/norm*body*.045,dy/norm*body*.045)
    obj=sk.Object('awen','awen',(x,y,body,body),material=sk.Material(design_rgb(PALETTE['accent'])),data=('neutral',p,offset,direction,0))
    sp,_=_soft_character_body(obj); im=Image.new('RGBA',(n,n+pad));d=ImageDraw.Draw(im)
    for hand_index,(hx,hy) in enumerate(p['hands_fixed_xy_D']):
        cx=x+body/2+hx*body;cy=y+body/2+hy*body;r=body*.09
        if point and hand_index==0:
            start=(x+body*.5,y+body*.58)
            d.line((start,(cx,cy)),fill=INK,width=max(3,round(n*.055)))
            d.line((start,(cx,cy)),fill=PALETTE['accent'],width=max(1,round(n*.025)))
        d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=PALETTE['accent'],outline=INK,width=max(2,n//45))
    # Use bundled latin glyph coverage, avoiding a host-only font dependency.
    from worker.render import Fonts
    fonts=Fonts();font=fonts.font('?',round(n*.46))
    question=Image.new('RGBA',im.size)
    glyph_canvas=Image.new('RGBA',(n,n))
    _question_mark(glyph_canvas,n,font)
    question.alpha_composite(glyph_canvas,(0,pad))
    if wonder:
        bounds=question.getbbox();glyph=question.crop(bounds)
        glyph=glyph.resize((round(glyph.width*(1+.2*wonder)),round(glyph.height*(1+.2*wonder))),Image.Resampling.BICUBIC)
        im.alpha_composite(glyph,(round((bounds[0]+bounds[2]-glyph.width)/2),round(bounds[3]-glyph.height+float_y)))
    else:im.alpha_composite(question)
    im.paste(sp,(x,y),sp)
    mask=im.getchannel('A').point(lambda a:255 if a>=128 else 0);im.putalpha(mask);bounds=mask.getbbox()
    from worker.lighting_declaration import transform
    from worker.scenekit_shapes import soft_lighting
    im=soft_lighting(im.crop(bounds),mask.crop(bounds),grammar_shape='awen')
    mask=mask.crop(bounds)
    center=(x+body/2-bounds[0],y+body/2-bounds[1])
    return im,mask,dict(eye=center,pupil=(center[0]+offset[0],center[1]+offset[1]))


def pointing_awen(diameter, direction=(1,0)):
    from worker.ambient import blinking, sprite as animate
    im, mask, eyes = _pointing_awen(diameter, direction, blinking())
    out = animate(im, 'awen')
    sx, sy = out.width/im.width, out.height/im.height
    return out, out.getchannel('A'), {k:(v[0]*sx,v[1]*sy) for k,v in eyes.items()}


from functools import lru_cache
@lru_cache(maxsize=16)
def _pointing_awen(diameter, direction=(1,0), blink=False):
    """Frozen B character body/eyes, hands and question tail; eyes follow the teaching target."""
    import json, math
    from pathlib import Path
    from PIL import ImageFont
    from worker import scenekit_v9 as sk
    p=json.loads((Path(__file__).with_name('awen_o1.json')).read_text())
    if blink: p['eye_height_D'] = .008
    length=max(1,math.hypot(*direction))
    p['hands_fixed_xy_D'][0]=[direction[0]/length*.54,direction[1]/length*.54]
    n=diameter; body=round(n*.64); x=round(n*.10); y=n-body
    dx,dy=direction; norm=max(1,math.hypot(dx,dy));offset=(dx/norm*body*.045,dy/norm*body*.045)
    obj=sk.Object('awen','awen',(x,y,body,body),material=sk.Material(design_rgb(PALETTE['accent'])),data=('neutral',p,offset,direction,0))
    sp,_=_soft_character_body(obj); im=Image.new('RGBA',(n,n));d=ImageDraw.Draw(im)
    for hx,hy in p['hands_fixed_xy_D']:
        cx=x+body/2+hx*body;cy=y+body/2+hy*body;r=body*.09
        d.ellipse((cx-r,cy-r,cx+r,cy+r),fill=PALETTE['accent'],outline=INK,width=max(2,n//45))
    # Use bundled latin glyph coverage, avoiding a host-only font dependency.
    from worker.render import Fonts
    fonts=Fonts();font=fonts.font('?',round(n*.46))
    _question_mark(im,n,font)
    im.paste(sp,(x,y),sp)
    mask=im.getchannel('A').point(lambda a:255 if a>=128 else 0);im.putalpha(mask);bounds=mask.getbbox()
    from worker.lighting_declaration import transform
    from worker.scenekit_shapes import soft_lighting
    im=soft_lighting(im.crop(bounds),mask.crop(bounds),grammar_shape='awen')
    mask=mask.crop(bounds)
    center=(x+body/2-bounds[0],y+body/2-bounds[1])
    return im,mask,dict(eye=center,pupil=(center[0]+offset[0],center[1]+offset[1]))



def _question_mark(im,n,font):
    # Rasterize coverage separately so antialiased ink is not baked into paint.
    for color,width in ((INK,max(2,n//60)),(design_rgb(PALETTE['accent']),0)):
        mask=Image.new('L',im.size)
        ImageDraw.Draw(mask).text((n*.47,-n*.045),'?',font=font,fill=255,stroke_width=width,stroke_fill=255)
        mask=mask.point(lambda a:255 if a>=128 else 0)
        im.paste(color,(0,0,*im.size),mask)
