"""Screen-space W38 typography; boxes use xywh, leaders use endpoint pairs."""
import math
from functools import lru_cache
from PIL import Image, ImageDraw, ImageColor
from worker.design_tokens import PALETTE, STROKE, RADIUS, TYPE, LAYOUT
from worker.visual import centered_text, paste_text

INK=ImageColor.getrgb(STROKE['color'])

@lru_cache(maxsize=1)
def body_fonts():
    from worker.render import Fonts
    fonts=Fonts()
    fonts.paths=fonts.paths[1:]
    fonts.maps=fonts.maps[1:]
    return fonts


def overlap(a,b):
    return a[0]<b[0]+b[2] and b[0]<a[0]+a[2] and a[1]<b[1]+b[3] and b[1]<a[1]+a[3]


def inside(b,safe):
    x,y,w,h=b;l,t,r,bt=safe
    return x>=l and y>=t and x+w<=r and y+h<=bt


def intersects(a,b,c,d):
    def cross(p,q,r):return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on(p,q,r):return min(p[0],q[0])-1e-8<=r[0]<=max(p[0],q[0])+1e-8 and min(p[1],q[1])-1e-8<=r[1]<=max(p[1],q[1])+1e-8
    v=[cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)]
    return (v[0]*v[1]<0 and v[2]*v[3]<0) or any(abs(z)<1e-8 and on(p,q,r) for z,p,q,r in [(v[0],a,b,c),(v[1],a,b,d),(v[2],c,d,a),(v[3],c,d,b)])


def line_box(line,box):
    x,y,w,h=box;corners=[(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
    return any(x<=p[0]<=x+w and y<=p[1]<=y+h for p in line) or any(intersects(*line,corners[i],corners[(i+1)%4]) for i in range(4))


def sticker(im,box,radius,opacity,scale,outline=False,drop=False):
    layer=_sticker_layer(im.size,tuple(box),radius,opacity,scale,outline,drop)
    im.paste(Image.alpha_composite(im.convert('RGBA'),layer))




def caption_band_top(size):
    w,h=size;s=min(w,h)/720
    return round(h*.92-5*s-(round(TYPE['caption']*s)*TYPE['line_height']*2+24*s))


def caption(im,page,objects):
    w,h=im.size;s=min(w,h)/720;fs=round(TYPE['caption']*s);lh=fs*TYPE['line_height']
    bitmaps=[centered_text(body_fonts(),line,fs,w-2*min(w,h)*.08-32*s) for line in page['lines']]
    # The safety band stays fixed; only the visible sticker hugs actual ink.
    gap=max(6,round(fs*.3))
    bw=max(b.width for b in bitmaps)+32*s
    bh=sum(b.height for b in bitmaps)+gap*(len(bitmaps)-1)+24*s
    bottom=caption_band_top(im.size)+lh*2+24*s
    safe=(min(w,h)*.08,min(w,h)*.08,w-min(w,h)*.08,h-h*.08)
    x=(w-bw)/2;y=bottom-bh
    box=(x,y,bw,bh)
    sticker(im,box,RADIUS['large']*s,.88,s,drop=False)
    ink=[]
    top=y+12*s
    for bitmap in bitmaps:
        b=paste_text(im,bitmap,w/2,top)
        top+=bitmap.height+gap
        ink.append((b[0],b[1],b[2]-b[0],b[3]-b[1]))
    return dict(bbox=box,ink_boxes=ink,font_size=fs,line_height=lh,font='body',opacity=.88,radius=RADIUS['large']*s,padding=[16*s,12*s],safe=safe)


def labels(im,visual,metrics,reserved,narration,*,title=""):
    w,h=im.size;s=min(w,h)/720;safe=(w*.05,h*.05,w*.95,h*.95)
    objects=[o for o in metrics['objects'] if o.get('bbox') and o.get('visible',True)];out=[];notes=[]
    reserved=list(reserved)+[(0,caption_band_top(im.size),w,h-caption_band_top(im.size))]
    rear=[o['bbox'] for o in metrics.get('rear_objects',[]) if o.get('bbox')]
    items={it.id or str(i):it for i,it in enumerate(visual.items)}
    horizontal=w>=h
    fs=round(TYPE['label']*s)
    px,py=(14*s,8*s) if horizontal else (10*s,6*s)
    gap=(12 if horizontal else 8)*s
    from worker.label_selection import select_labels, text_key, intersection, area
    used_texts=metrics.setdefault('used_texts', set())
    used_texts.add(text_key(title))
    pending=[(obj, items[obj['id']].label) for obj in objects
             if obj.get('id') in items and items[obj['id']].label]
    drawn_ids={o.get('id') for o in objects}
    pending.extend((dict(id=ref), it.label) for ref,it in items.items()
                   if it.label and ref not in drawn_ids)
    def covers_subject(box):
        return any(intersection(dict(bbox=box), other) > .4*area(other)
                   for other in objects if area(other) > 0)
    for obj,text in select_labels(objects,pending,title,notes=notes,used_texts=used_texts):
        it=items.get(obj.get('id'))
        if it and it.shape == 'timeline_axis':continue
        if obj.get('inline_label'):
            x,y,ow,oh=obj['bbox']
            from worker.scenekit_renderer import _stage_fonts
            bitmap=centered_text(_stage_fonts(),text,TYPE['label'],ow*.82)
            box=(x+(ow-bitmap.width)/2,y+(oh-bitmap.height)/2,bitmap.width,bitmap.height)
            if not covers_subject(box) and inside(box,safe) and not any(overlap(box,r) for r in reserved+[row['bbox'] for row in out]):
                ink=paste_text(im,bitmap,x+ow/2,box[1])
                out.append(dict(owner=obj['id'],text=text,bbox=(ink[0],ink[1],ink[2]-ink[0],ink[3]-ink[1]),font_size=TYPE['label']))
                continue
        if it and it.shape == 'card' and len(out)<1:
            x,y,ow,oh=obj['bbox']
            bitmap=centered_text(body_fonts(),text,TYPE['label'],ow*.85)
            box=(x+(ow-bitmap.width)/2,y+oh*.42,bitmap.width,bitmap.height)
            if not covers_subject(box) and inside(box,safe) and not any(overlap(box,r) for r in reserved+[row['bbox'] for row in out]):
                ink=paste_text(im,bitmap,x+ow/2,box[1])
                out.append(dict(owner=obj['id'],text=text,bbox=(ink[0],ink[1],ink[2]-ink[0],ink[3]-ink[1]),font_size=TYPE['label']))
                continue
        bitmap=centered_text(body_fonts(),text,fs,100000)
        bw,bh=bitmap.width+2*px,bitmap.height+2*py
        x,y,ow,oh=obj['bbox'];chosen=None
        # A role's maximum envelope follows translation but ignores scale pulses.
        if obj.get('size_bounds'):
            factor=math.sqrt(obj['size_bounds'][1]*w*h/(ow*oh))
            nw,nh=ow*factor,oh*factor
            x+=(ow-nw)/2;y+=(oh-nh)/2;ow,oh=nw,nh
        for right,upper in [(True,True),(False,True),(True,False),(False,False)]:
            bx=x+ow+gap if right else x-bw-gap
            by=y-bh-gap if upper else y+oh+gap
            box=(bx,by,bw,bh)
            a=(bx if right else bx+bw,by+bh if upper else by)
            b=(x+ow if right else x,y if upper else y+oh)
            line=(a,b)
            blockers=[o['bbox'] for o in objects if o is not obj]+rear
            occupied=reserved+rear+[r['bbox'] for r in out]
            if len(out)>=1 or not inside(box,safe) or math.dist(a,b)>LAYOUT['leader_max']*s:continue
            if any(overlap(box,o['bbox']) for o in objects) or any(overlap(box,r) for r in occupied):continue
            if any(line_box(line,r) for r in blockers+occupied):continue
            if any(intersects(*line,*r['leader']) or line_box(r['leader'],box) for r in out if 'leader' in r):continue
            chosen=dict(owner=obj['id'],text=text,bbox=box,leader=line,font_size=fs,padding=[px,py],leader_width=STROKE['decoration']*s,dot_radius=3*s,length=math.dist(a,b),slot=('right' if right else 'left')+('-upper' if upper else '-lower'))
            break
        if chosen is None:
            notes.append(dict(code='LABEL_DROPPED',tier='craft',object=obj['id'],text=text,reason='no free slot within safe margin or one-label limit',narration=narration,narration_mentions_label=text in narration,severity='info'))
            continue
        layer=_leader_layer((w,h),tuple(chosen['leader'][0]),tuple(chosen['leader'][1]),s)
        im.paste(Image.alpha_composite(im.convert('RGBA'),layer))
        sticker(im,chosen['bbox'],RADIUS['small']*s,.92,s,outline=True)
        bx,by,bw,bh=chosen['bbox'];paste_text(im,bitmap,bx+bw/2,by+py)
        out.append(chosen)
    used_texts.update(text_key(row['text']) for row in out)
    return out,notes


# Cache only the painted rectangle. Eight output pixels of transparent padding
# preserve the original 4x LANCZOS support and integer sampling phase exactly.
def _overlay_bounds(size, box):
    l,t,r,b=box
    l=max(0,min(size[0],math.floor(l)-8));t=max(0,min(size[1],math.floor(t)-8))
    r=max(l,min(size[0],math.ceil(r)+8));b=max(t,min(size[1],math.ceil(b)+8))
    return l,t,r,b


def _expand_layer(size, result):
    tile,xy=result
    image=Image.new('RGBA',size)
    image.paste(tile,xy)
    return image


@lru_cache(maxsize=16)
def _sticker_tile(size,box,radius,opacity,scale,outline,drop):
    q=4;x,y,w,h=box;shift=0
    l,t,r,b=_overlay_bounds(size,(x,y,x+w+shift,y+h+shift))
    if r==l or b==t:return Image.new('RGBA',(1,1)),(0,0)
    layer=Image.new('RGBA',((r-l)*q,(b-t)*q));d=ImageDraw.Draw(layer)
    rect=[(x-l)*q,(y-t)*q,(x+w-l)*q,(y+h-t)*q]
    d.rounded_rectangle(rect,radius=radius*q,fill=(255,255,255,round(255*opacity)),outline=INK+(255,) if outline else None,width=round(STROKE['decoration']*scale*q))
    return layer.resize((r-l,b-t),Image.Resampling.LANCZOS),(l,t)


def _sticker_layer(size,box,radius,opacity,scale,outline,drop):
    return _expand_layer(size,_sticker_tile(size,box,radius,opacity,scale,outline,drop))


@lru_cache(maxsize=16)
def _leader_tile(size,a,b,scale):
    q=4;radius=3*scale
    l,t,r,bot=_overlay_bounds(size,(min(a[0],b[0])-radius,min(a[1],b[1])-radius,max(a[0],b[0])+radius,max(a[1],b[1])+radius))
    if r==l or bot==t:return Image.new('RGBA',(1,1)),(0,0)
    layer=Image.new('RGBA',((r-l)*q,(bot-t)*q));d=ImageDraw.Draw(layer)
    d.line([((a[0]-l)*q,(a[1]-t)*q),((b[0]-l)*q,(b[1]-t)*q)],fill=INK,width=round(STROKE['decoration']*scale*q))
    d.ellipse(((b[0]-l-radius)*q,(b[1]-t-radius)*q,(b[0]-l+radius)*q,(b[1]-t+radius)*q),fill=INK)
    return layer.resize((r-l,bot-t),Image.Resampling.LANCZOS),(l,t)


def _leader_layer(size,a,b,scale):
    return _expand_layer(size,_leader_tile(size,a,b,scale))


_sticker_layer.cache_clear=_sticker_tile.cache_clear
_sticker_layer.cache_info=_sticker_tile.cache_info
_leader_layer.cache_clear=_leader_tile.cache_clear
_leader_layer.cache_info=_leader_tile.cache_info

