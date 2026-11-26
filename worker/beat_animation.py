"""Apply sentence events to the sprite before painting and measuring geometry."""
from PIL import Image, ImageChops
from worker.design_tokens import STROKE, EMPHASIS
import math


def transform(sp, x, y, item, size):
    from app.geometry_healing import normalize_sprite
    sp, x, y = _transform(sp, x, y, item, size)
    return normalize_sprite(sp, x, y, size, item.shape)


def _transform(sp, x, y, item, size):
    e = item.animation_state
    if e and 'fixed_bbox' in e:
        x,y,w,h = e['fixed_bbox']
        sp = sp.resize((round(w),round(h)), Image.Resampling.BICUBIC)
        if e.get('opacity', 1.) == 0:
            sp = sp.copy(); sp.putalpha(0)
        return sp, round(x), round(y)
    if e and e.get('engine_geometry'):
        return apply_geometry(sp, e)
    box = item.repair_bboxes.get('16x9' if size[0] >= size[1] else '9x16')
    if box:
        x,y,w,h = [v*d for v,d in zip(box, (*size,*size))]
        return sp.resize((max(1,round(w)),max(1,round(h))), Image.Resampling.BICUBIC), round(x), round(y)
    # Resolve ledger cells before animation; both orientations use their own bounds.
    w,h = size
    margin = math.ceil(min(size)*.04)
    region = getattr(item, 'target_regions', {}).get('16x9' if w>=h else '9x16')
    bounds = tuple(round(v*d) for v,d in zip(region, (w,h,w,h))) if region else (margin,margin,w-margin,h-margin)
    if region:
        left,top,right,bottom = bounds
        ratio = min(1., (right-left)/sp.width, (bottom-top)/sp.height)
        if ratio < 1:
            sp = sp.resize((max(1,math.floor(sp.width*ratio)),max(1,math.floor(sp.height*ratio))), Image.Resampling.BICUBIC)
        x = round((left+right-sp.width)/2)
        y = max(top,min(y,bottom-sp.height))
    e = item.animation_state
    if e and (e.get('source') == 'code' or region):
        e = safe_event(e, (x,y,sp.width,sp.height), size, bounds, getattr(item,'id',None))
    if not e:
        return sp, x, y
    q = e['progress']
    lerp = lambda a, b: a+(b-a)*q
    scale = lerp(e['from_scale'], e['to_scale'])
    if e['type'] == '状态切换':
        from worker.scenekit_renderer import sprite
        replacement = sprite(e['to_shape'], item.color, max(12, min(sp.size)), item.mood, item.state)[0]
        layer = Image.new('RGBA', sp.size)
        replacement.thumbnail(sp.size)
        layer.paste(replacement, ((sp.width-replacement.width)//2, sp.height-replacement.height))
        sp = Image.blend(sp.convert('RGBA'), layer, q)
    old_w, old_h = sp.size
    if scale != 1:
        sp = sp.resize((max(1, round(old_w*scale)), max(1, round(old_h*scale))), Image.Resampling.BICUBIC)
    x += (old_w-sp.width)/2 + lerp(e['from_xy'][0],e['to_xy'][0])*size[0]
    y += old_h-sp.height + lerp(e['from_xy'][1],e['to_xy'][1])*size[1]
    alpha = lerp(e['from_opacity'], e['to_opacity'])
    if alpha != 1:
        sp = sp.copy()
        sp.putalpha(sp.getchannel('A').point(lambda a: round(a*alpha)))
    return sp, round(x), round(y)


def safe_event(event, bbox, size, bounds, subject=None):
    """Constrain both endpoints; linear interpolation stays inside the same box."""
    e = dict(event)
    x,y,bw,bh = bbox
    w,h = size
    left,top,right,bottom = bounds
    for key in ('from_xy','to_xy'):
        dx,dy = e[key]
        e[key] = (max((left-x)/w,min(dx,(right-x-bw)/w)),
                  max((top-y)/h,min(dy,(bottom-y-bh)/h)))
    requested = event['from_xy'] != event['to_xy']
    travel = max(abs(e['to_xy'][0]-e['from_xy'][0]),abs(e['to_xy'][1]-e['from_xy'][1]))
    if requested and travel < .02:
        e.update(from_xy=(0.,0.),to_xy=(0.,0.),from_scale=.9,to_scale=1.)
        from app.enforcement import record
        record([dict(code='ANIMATION_TRANSLATION_TO_SCALE', scene=e.get('scene'), object=subject,
            measured=dict(sentence=e.get('sentence'), source=e.get('source'), size=size, bbox=bbox, bounds=bounds,
                          available_fraction=travel, reason='safe displacement below 2% of canvas'))], 'animation_completion')
    # Self-check the same full-bbox safe-margin predicate used by geometry_budget.
    # Repair rounding/base placement locally instead of handing clipping to final review.
    for key,scale_key in [('from_xy','from_scale'),('to_xy','to_scale')]:
        scale=min(e[scale_key], (right-left)/bw, (bottom-top)/bh)
        e[scale_key]=scale
        sw,sh=max(1,round(bw*scale)),max(1,round(bh*scale))
        dx,dy=e[key]
        px=x+(bw-sw)/2+dx*w; py=y+bh-sh+dy*h
        px=max(left,min(px,right-sw));py=max(top,min(py,bottom-sh))
        e[key]=((px-x-(bw-sw)/2)/w,(py-y-bh+sh)/h)
        assert bbox_inside((round(px),round(py),sw,sh), bounds)
    return e


def bbox_inside(bbox, bounds):
    x,y,w,h = bbox
    left,top,right,bottom = bounds
    return left <= x and top <= y and x+w <= right and y+h <= bottom


def apply_geometry(sp, event):
    q = event['progress']; frames = event['keyframes']
    a,b = next(((a,b) for a,b in zip(frames,frames[1:]) if q <= b['at']), (frames[-2],frames[-1]))
    f = max(0., min(1., (q-a['at'])/(b['at']-a['at'])))
    box = [u+(v-u)*f for u,v in zip(a['bbox'],b['bbox'])]
    if event['action'] == 'highlight':
        original = sp
        ink = ImageChops.multiply(sp.convert('L').point(
            lambda value: 255 if value < STROKE['detail_luma_max'] else 0), sp.getchannel('A'))
        colored = Image.new('RGBA', sp.size, EMPHASIS['color'])
        colored.putalpha(sp.getchannel('A'))
        sp = Image.blend(sp, colored, EMPHASIS['mix']*q)
        sp.paste(original, (0,0), ink)
    if event['action'] == 'dissolve' and event.get('variant') == 'color':
        colored = Image.new('RGBA', sp.size, tuple(event['target_rgb'])+(255,))
        colored.putalpha(sp.getchannel('A'))
        sp = Image.blend(sp, colored, q)
    if event['action'] == 'dissolve' and event.get('variant') == 'split':
        # Four shrinking copies separate inside the original extent; one driver q.
        x,y,w,h = event['start_bbox']
        layer = Image.new('RGBA', (round(w),round(h)))
        ratio = 1.-.75*q
        tile = sp.resize((max(1,round(w*ratio)),max(1,round(h*ratio))),Image.Resampling.LANCZOS)
        for dx,dy in ((0,0),(1,0),(0,1),(1,1)):
            layer.alpha_composite(tile,(round(dx*(w-tile.width)),round(dy*(h-tile.height))))
        return layer,round(x),round(y)
    if event['action'] == 'split':
        sx,sy,sw,sh = event['start_bbox']
        # Crop at solved resolution; the incoming sprite may have another size.
        source_sprite = sp.resize((round(sw),round(sh)), Image.Resampling.BICUBIC)
        tiles = []
        for identity, source, dest in zip(event['child_ids'], event['parts_start'], event['parts']):
            crop = (round(source[0]-sx), round(source[1]-sy),
                    round(source[0]+source[2]-sx), round(source[1]+source[3]-sy))
            tile = source_sprite.crop(crop)
            def offset(delta):
                return int(math.copysign(max(1,round(abs(delta)*q)),delta)) if q > 0 and delta else 0
            px = round(sx)+crop[0]+offset(dest[0]-source[0])
            py = round(sy)+crop[1]+offset(dest[1]-source[1])
            width = max(1,round(tile.width*(1+(dest[2]/source[2]-1)*q)))
            height = max(1,round(tile.height*(1+(dest[3]/source[3]-1)*q)))
            if (width,height) != tile.size:
                tile = tile.resize((width,height), Image.Resampling.BICUBIC)
            tiles.append((identity, tile, px, py))
        x,y = min(p[2] for p in tiles),min(p[3] for p in tiles)
        right = max(px+tile.width for _,tile,px,py in tiles)
        bottom = max(py+tile.height for _,tile,px,py in tiles)
        layer = Image.new('RGBA',(right-x,bottom-y))
        for _,tile,px,py in tiles:
            layer.alpha_composite(tile,(px-x,py-y))
        layer.info['split_children'] = tiles
        return layer,x,y
    x,y,w,h = box
    sp = sp.resize((max(1,round(w)),max(1,round(h))),Image.Resampling.BICUBIC)
    alpha = a['opacity']+(b['opacity']-a['opacity'])*f
    if alpha != 1:
        sp = sp.copy(); sp.putalpha(sp.getchannel('A').point(lambda p: round(p*alpha)))
    return sp,round(x),round(y)
