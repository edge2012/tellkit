"""Episode-independent immutable scene construction and deterministic rasterization."""
from worker.design_tokens import TYPE as DESIGN_TYPE, RADIUS as DESIGN_RADIUS
from PIL.ImageColor import getrgb as design_rgb
from worker.design_tokens import PALETTE
from worker.design_tokens import PALETTE, STROKE as DESIGN_STROKE, RADIUS as DESIGN_RADIUS
from dataclasses import dataclass, replace
import math
from PIL import Image, ImageDraw, ImageFilter, ImageChops, ImageFont

LIGHT = (-math.cos(math.pi/6), -math.sin(math.pi/6))
INK = design_rgb(PALETTE['neutral_900'])
BG = design_rgb(PALETTE['background'])
TONE_KEY = INK

SHADOW_ALPHA = 0.14
SHADOW_H_RATIO = 0.10
SHADOW_W_RATIO = 1.10
CONTACT_TINT = 0.88
CONTACT_H_PX = 2
CONTACT_W_RATIO = 1.00

@dataclass(frozen=True)
class Material:
    color: tuple = design_rgb(PALETTE['neutral_300'])
    stroke: float = 6
    allow_sticker_ring: bool = True
    glow: bool = False

MAT_STICKER = Material()

@dataclass(frozen=True)
class Object:
    name: str
    kind: str
    bbox: tuple
    depth: float = 0
    material: Material = MAT_STICKER
    data: tuple = ()
    standing: bool = True

@dataclass(frozen=True)
class Canvas:
    size: tuple
    ground_y: float
    objects: tuple = ()
    labels: tuple = ()
    lines: tuple = ()
    focus: tuple | None = None
    awen_params: tuple = ()


def ground(scene, obj):
    x,y,w,h = obj.bbox
    return replace(obj, bbox=(x, scene.ground_y-h, w,h), standing=True)


def add(canvas, obj):
    if obj.kind in ('background','volcano','crater'):
        obj=replace(obj,material=replace(obj.material,allow_sticker_ring=False))
    obj = ground(canvas, obj) if obj.standing else obj
    return replace(canvas, objects=canvas.objects+(obj,))


def draw_cup(canvas, x, y, w, h, *, fill_ratio=1., rim=True, material=MAT_STICKER,
             depth=0, name='cup', standing=True):
    if not 0 <= fill_ratio <= 1: raise ValueError('fill_ratio must be 0..1')
    return add(canvas, Object(name,'cup',(x,y,w,h),depth,material,(fill_ratio,rim),standing))


def draw_bowl(canvas, x, y, w, h, *, fill_ratio=1., rim=True, rim_thickness=6,
              material=MAT_STICKER, depth=0, name='bowl'):
    if not 0 <= fill_ratio <= 1: raise ValueError('fill_ratio must be 0..1')
    return add(canvas,Object(name,'bowl',(x,y,w,h),depth,material,(fill_ratio,rim,rim_thickness)))


def draw_ground_line(canvas, x0, x1, y, *, fade_right=True):
    return replace(canvas,lines=canvas.lines+((x0,x1,y,fade_right),))


def draw_label(canvas, text, anchor, *, arrow=0, tone=TONE_KEY):
    x,y=anchor
    if abs(y-canvas.ground_y)<.04*canvas.size[1]+2: raise ValueError('label too close to ground')
    return replace(canvas,labels=canvas.labels+((text,anchor,arrow,tone),))


def draw_awen(canvas, x, ground_y, *, state='neutral', gaze=None):
    params=dict(canvas.awen_params)[state]
    d=canvas.size[1]*.22
    jump=params['jump_D']*d if state=='happy' else 0
    cy=ground_y-jump-d/2
    target=gaze or canvas.focus
    if target is None: raise ValueError('Awen needs a focus or explicit gaze')
    dx,dy=target[0]-x,target[1]-cy
    scale=min(.06*d/max(abs(dx),1e-9),.04*d/max(abs(dy),1e-9))
    offset=(dx*scale,dy*scale)
    return add(canvas,Object('awen','awen',(x-d/2,cy-d/2,d,d),2,
        Material(design_rgb(PALETTE['accent'])),(state,params,offset,target,jump),not jump))


def silhouette(obj):
    _,_,w,h=obj.bbox; w,h=round(w),round(h)
    m=Image.new('L',(w,h));d=ImageDraw.Draw(m)
    if obj.kind=='bowl':
        r=.12*w;left=round(.15*w);right=w-1-left
        pts=[(0,0),(w-1,0)]
        for i in range(21):
            t=i/20
            pts.append(((1-t)**2*(w-1)+2*(1-t)*t*(w-1)+t*t*right,
                        (1-t)**2*r/2+2*(1-t)*t*(h*.75)+t*t*(h-4)))
        pts.extend([(right-1,h-2),(right-3,h-1),(left+3,h-1),(left+1,h-2),(left,h-4)])
        for i in range(20,-1,-1):
            t=i/20
            pts.append((t*t*left,(1-t)**2*r/2+2*(1-t)*t*(h*.75)+t*t*(h-4)))
        d.polygon(pts,fill=255)
    elif obj.kind=='cup':
        r=.12*w
        d.rounded_rectangle((0,r/2,w-1,h-1),radius=DESIGN_RADIUS['small'],fill=255)
        d.ellipse((0,0,w-1,r),fill=255)
    else: d.ellipse((0,0,w-1,h-1),fill=255)
    return m


def material_layers(mask, material, inner_stroke=None):
    w,h=mask.size;c=material.color
    fill=Image.new('RGBA',mask.size,c+(255,));fill.putalpha(mask)
    # Pad erosion so silhouette boundaries at the local canvas edge are included.
    pen=round(1.2*material.stroke if inner_stroke is None else inner_stroke);pad=pen+1
    padded=Image.new('L',(w+2*pad,h+2*pad));padded.paste(mask,(pad,pad))
    eroded=padded.filter(ImageFilter.MinFilter(2*pen+1)).crop((pad,pad,w+pad,h+pad))
    inner=ImageChops.subtract(mask,eroded)
    stroke=Image.new('RGBA',mask.size,tuple(round(v*.82) for v in c)+(255,));stroke.putalpha(inner)
    hi=Image.new('RGBA',mask.size);d=ImageDraw.Draw(hi)
    cx=w*.23;cy=h*.25;length=h*.48;half=w*.11
    vx,vy=-LIGHT[1],LIGHT[0]
    pts=[(cx+vx*length*s+LIGHT[0]*half*t,cy+vy*length*s+LIGHT[1]*half*t) for s,t in [(-.5,-1),(.5,-1),(.5,1),(-.5,1)]]
    d.polygon(pts,fill=design_rgb(PALETTE['neutral_050'])+ (140,));hi.putalpha(ImageChops.multiply(hi.getchannel('A'),eroded))
    sh=Image.new('RGBA',mask.size)
    shifted=Image.new('L',mask.size);shifted.paste(mask,(-round(.03*w),-round(.03*h)))
    edge=ImageChops.subtract(mask,shifted)
    sh.paste(INK+(46,),(0,0,w,h),edge)
    return fill,stroke,hi,sh


def sprite(obj):
    mask=silhouette(obj);w,h=mask.size
    im=Image.new('RGBA',(w,h))
    layers=material_layers(mask,obj.material,inner_stroke_px(obj))
    for layer in (layers[:1] if obj.kind in ('cup','bowl') else layers): im.alpha_composite(layer)
    d=ImageDraw.Draw(im)
    if obj.kind in ('cup','bowl'):
        level,rim,*rest=obj.data; r=.12*w; inset=9
        d.ellipse((inset,2,w-inset-1,r+2),fill=PALETTE['background'])
        top=6+(h-r-18)*(1-level)
        if level>0:
            water=Image.new('RGBA',im.size);wd=ImageDraw.Draw(water)
            wd.rectangle((inset+2,top+r/2,w-inset-3,h-9),fill=PALETTE['primary'])
            wd.ellipse((inset+2,top,w-inset-3,min(h-9,top+r-4)),fill=PALETTE['neutral_300'])
            water.putalpha(ImageChops.multiply(water.getchannel('A'),mask));im.alpha_composite(water)
        for layer in layers[1:]: im.alpha_composite(layer)
        if rim:
            d=ImageDraw.Draw(im)
            d.arc((3,0,w-4,r),0,180,fill=tuple(round(v*.82) for v in obj.material.color),width=round(rest[0] if rest else 6))
        if level > 0:
            d=ImageDraw.Draw(im)
            d.line((inset,round(r/2),inset,round(r/2)+3),fill=PALETTE['background'],width=DESIGN_STROKE['decoration'])
            d.line((w-inset-1,round(r/2),w-inset-1,round(r/2)+3),fill=PALETTE['background'],width=DESIGN_STROKE['decoration'])
    if obj.kind=='awen':
        state,p,(dx,dy),target,jump=obj.data
        for ex,ey in p['eyes_xy_D']:
            cx=w/2+ex*w+dx;cy=h/2+ey*h+dy
            ew=p['eye_width_D']*w;eh=p['eye_height_D']*h
            if state=='happy':d.arc((cx-ew/2,cy-eh/2,cx+ew/2,cy+eh/2),185,355,fill=INK,width=max(2,round(w*.025)))
            else:
                pts=[(cx+ew/2*math.cos(t)*(1+.035*math.sin(3*t)),cy+eh/2*math.sin(t)) for t in (i*math.tau/48 for i in range(48))]
                d.polygon(pts,fill=INK)
                d.ellipse((cx-ew*.22,cy-eh*.30,cx-ew*.02,cy-eh*.17),fill='white')
    return im,mask


def base_width(obj):
    w=round(obj.bbox[2])
    if obj.kind=='awen':return w
    return w-2*round(.15*w)-6 if obj.kind=='bowl' else w-6


def contact_box(canvas, obj):
    # Clip the shared nominal contact width to the actual straight support row.
    mask = silhouette(obj)
    last = [x for x in range(mask.width) if mask.getpixel((x, mask.height-1))]
    width = min(round(base_width(obj)*CONTACT_W_RATIO), len(last))
    left = round(obj.bbox[0]) + (last[0]+last[-1]+1-width)//2
    gy = round(canvas.ground_y)
    return left, gy-CONTACT_H_PX+1, left+width-1, gy


def contact_color(obj):
    # Round toward the main color so 8-bit quantization never exceeds 12%.
    return tuple(math.ceil(v*CONTACT_TINT) for v in obj.material.color)


def inner_stroke_px(obj):
    return max(4, min(7, base_width(obj)*.03)) if obj.kind in ('cup','bowl') else 1.2*obj.material.stroke


def ground_shadow(canvas, obj):
    x,y,w,h = obj.bbox
    bw = base_width(obj)
    sw, sh = bw*SHADOW_W_RATIO, bw*SHADOW_H_RATIO
    cx, gy = x+w/2, canvas.ground_y + sh*0.32
    layer = Image.new('RGBA', canvas.size)
    ImageDraw.Draw(layer).ellipse(
        (round(cx-sw/2), round(gy-sh/2), round(cx+sw/2), round(gy+sh/2)),
        fill=INK+(round(255*SHADOW_ALPHA),))
    return layer


def render(canvas, fonts=None):
    for lava in (o for o in canvas.objects if o.kind=='lava'):
        lx,ly,lw,lh=lava.bbox
        craters=[o for o in canvas.objects if o.kind=='crater']
        if not craters:raise ValueError('lava requires a final crater occluder')
        covered=0
        for yy in range(round(ly),round(ly+lh)):
            for crater in craters:
                cx,cy,cw,ch=crater.bbox;px=round(lx+lw/2-cx);py=round(yy-cy)
                mask=silhouette(crater)
                if 0<=px<mask.width and 0<=py<mask.height and mask.getpixel((px,py)):
                    covered+=1;break
            else:break
        if covered/lh<.25:raise ValueError('crater must cover at least 25% of lava from its top')
    im=Image.new('RGB',canvas.size,BG);d=ImageDraw.Draw(im)
    for x0,x1,y,fade in canvas.lines:
        for x in range(round(x0),round(x1)):
            a=(x-x0)/(x1-x0);a=a if fade else 1-a
            d.line((x,y,x,y),fill=tuple(round(c+(b-c)*a) for c,b in zip(INK,BG)))
    # Opaque ground footprints cover the horizon before the translucent shadows.
    # The footprint is the object's projected bounding width on the ground plane.
    for obj in canvas.objects:
        if obj.standing:
            x,y,w,h=obj.bbox
            ImageDraw.Draw(im).line((round(x),round(canvas.ground_y),round(x)+round(w)-1,round(canvas.ground_y)),fill=BG)
    for obj in canvas.objects:
        shadow=ground_shadow(canvas,obj)
        im.paste(shadow,(0,0),shadow)
    for obj in sorted(canvas.objects,key=lambda o:(o.kind=='crater',o.depth)):
        x,y,w,h=obj.bbox;x,y=round(x),round(y)
        sp,mask=sprite(obj)
        if obj.material.glow:
            radius=.015*w;pad=math.ceil(radius*3)
            halo=Image.new('L',(round(w)+2*pad,round(h)+2*pad));halo.paste(mask,(pad,pad))
            halo=halo.filter(ImageFilter.GaussianBlur(radius)).point(lambda a:round(a*.25))
            im.paste(obj.material.color,(x-pad,y-pad),halo)
        if obj.material.allow_sticker_ring:

            ring=Image.new('L',(round(w)+12,round(h)+12));ring.paste(mask,(6,6));ring=ring.filter(ImageFilter.MaxFilter(11))
            # The ring is clipped at the grounding plane.
            rd=ImageDraw.Draw(ring);rd.rectangle((0,round(h)+6,ring.width,ring.height),fill=0)
            im.paste('white',(x-6,y-6),ring)
        if obj.kind=='awen':
            p=obj.data[1];dd=ImageDraw.Draw(im)
            for hx,hy in p['hands_fixed_xy_D']:
                cx=x+w/2+hx*w;cy=y+h/2+hy*h;r=w*.09
                hand=Object('hand','hand',(cx-r,cy-r,r*2,r*2),material=obj.material)
                hs,_=sprite(hand);im.paste(hs,(round(cx-r),round(cy-r)),hs)
            # Solid question-mark glyph; curvature/tilt comes from the selected B state.
            tail=Image.new('RGBA',(round(w*.65),round(w*.7)))
            td=ImageDraw.Draw(tail)
            font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',round(w*.58))
            td.text((w*.08,0),'?',font=font,fill=obj.material.color,stroke_width=0)
            angle=p['tilt_deg']+p['tail_curvature_D']*75
            tail=tail.rotate(angle,resample=Image.Resampling.BICUBIC,expand=True)
            tail_mask=tail.getchannel('A');tail=Image.new('RGBA',tail.size)
            for layer in material_layers(tail_mask,obj.material):tail.alpha_composite(layer)
            im.paste(tail,(round(x+w*.48),round(y-w*.48)),tail)
        im.paste(sp,(x,y),sp)
        if obj.standing:
            ImageDraw.Draw(im).rectangle(contact_box(canvas,obj),fill=contact_color(obj))
    if fonts:
        from worker.visual import centered_text,paste_text
        for text,(x,y),arrow,tone in canvas.labels:
            bitmap=centered_text(fonts,text,DESIGN_TYPE['label'],canvas.size[0]*.92)
            if tone!=TONE_KEY:
                tint=Image.new('RGBA',bitmap.size,tone);tint.putalpha(bitmap.getchannel('A'));bitmap=tint
            paste_text(im,bitmap,x,y)
            if arrow:
                tip=(x+arrow*20,y-20);dd=ImageDraw.Draw(im)
                dd.line((x,y-4,*tip),fill=tone,width=DESIGN_STROKE['decoration'])
                dd.polygon([tip,(tip[0]-arrow*8,tip[1]+2),(tip[0]-arrow*2,tip[1]+8)],fill=tone)
    return im
