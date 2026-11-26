"""Final sprite bounds and opaque-pixel occlusion protection, in paint order."""
import math
from PIL import Image, ImageChops
from app.canvas_bounds import normalize_bbox

MAX_AREA = .45


def fit_box(box, size, *, raster=True):
    x, y, w, h = box
    factor = min(1., math.sqrt(MAX_AREA*size[0]*size[1]/max(1, w*h)),
                 size[0]/max(1, w), size[1]/max(1, h))
    nw, nh = (max(1, math.floor(w*factor)), max(1, math.floor(h*factor))) if raster else (w*factor, h*factor)
    position = round if raster else float
    bounded = normalize_bbox((position(x+(w-nw)/2), position(y+(h-nh)/2), nw, nh), size)
    return tuple(round(v) for v in bounded) if raster else tuple(bounded)


def assert_not_fullscreen(box, size):
    x,y,w,h = box
    covered = max(0, min(size[0],x+w)-max(0,x))*max(0,min(size[1],y+h)-max(0,y))
    if covered >= .8*size[0]*size[1]:
        raise AssertionError('SINGLE_PRIMITIVE_FULLSCREEN: coverage >= 80%')


def blocked(mask, box, peers):
    """Opaque pixels covering >50% of any earlier subject's visible ink."""
    opaque = mask.point(lambda a: 255 if a >= 250 else 0)
    x,y,w,h = box
    hits = []
    for peer in peers:
        px,py,pw,ph = peer['bbox']
        left,top,right,bottom = max(x,px),max(y,py),min(x+w,px+pw),min(y+h,py+ph)
        if left >= right or top >= bottom: continue
        victim = peer['mask'].point(lambda a: 255 if a else 0)
        area = sum(victim.histogram()[1:])
        overlap = ImageChops.multiply(opaque.crop((left-x,top-y,right-x,bottom-y)),
                                     victim.crop((left-px,top-py,right-px,bottom-py)))
        if sum(overlap.histogram()[1:]) > area*.5:
            hits.append(peer['id'])
    return hits


def protect(plan, metrics, scene, *, occlusion=True):
    """Include unlabelled temporary/background sprites, without changing backdrop paint."""
    if not hasattr(plan, 'commands'): return
    peers, commands, notes = [], [], []
    roots = metrics.get('objects', [])
    objects = [child for obj in roots for child in obj.get('split_children', [obj])]
    claimed = set()
    for number, command in enumerate(plan.commands):
        if command[0] != 'paste':
            commands.append(command); continue
        _, sp, pos, mask = command
        if mask is None:
            mask = sp.getchannel('A') if sp.mode == 'RGBA' else Image.new('L',sp.size,255)
        elif mask.mode == 'RGBA': mask = mask.getchannel('A')
        original = (*pos[:2], *sp.size)
        matches = [o for o in objects if id(o) not in claimed and tuple(o['bbox']) == original][:1]
        claimed.update(id(o) for o in matches)
        identity = matches[0].get('id', f'primitive_{number}') if matches else f'primitive_{number}'
        box = fit_box(original, plan.size)
        sp = sp.resize(box[2:], Image.Resampling.LANCZOS)
        mask = mask.resize(box[2:], Image.Resampling.LANCZOS)
        hit = blocked(mask, box, peers) if occlusion and not any(o.get('magnified_view') for o in matches) else []
        strategy = 'area_cap' if box != original else None
        if hit:
            base, base_mask, base_box = sp, mask, box
            # Bounded shrink preserves legibility: never reduce below half the input.
            semantic = any(o.get('size_semantics') for o in matches)
            for factor in (() if semantic else (.85, .7, .5)):
                x,y,w,h = base_box
                nw,nh = max(1,int(w*factor)),max(1,int(h*factor))
                box = (x+(w-nw)//2,y+(h-nh)//2,nw,nh)
                sp = base.resize((nw,nh), Image.Resampling.LANCZOS)
                mask = base_mask.resize((nw,nh), Image.Resampling.LANCZOS)
                if not blocked(mask,box,peers):
                    strategy = 'shrink'; break
            else:
                x,y,w,h = box
                candidates = []
                for peer in peers:
                    px,py,pw,ph = peer['bbox']
                    candidates.extend(((x,py-h),(x,py+ph),(px-w,y),(px+pw,y)))
                candidates.extend(((x,0),(x,plan.height-h),(0,y),(plan.width-w,y)))
                for nx,ny in candidates:
                    trial = (nx,ny,w,h)
                    from app.semantic_bands import BANDS
                    band = matches[0].get('semantic_band', {}).get('band') if matches else None
                    if band in BANDS and not BANDS[band][0] <= (ny+h/2)/plan.height <= BANDS[band][1]:
                        continue
                    if 0 <= nx <= plan.width-w and 0 <= ny <= plan.height-h and not blocked(mask,trial,peers):
                        box = trial; strategy = 'move'; break
                else:
                    strategy = 'preserve_size' if semantic else 'drop'
        if strategy:
            notes.append(dict(code='OCCLUDER_DROPPED' if strategy == 'drop' else 'PRIMITIVE_GUARD',
                              tier='craft', scene=scene, object=identity,
                              measured=dict(id=identity, blocked_objects=hit, strategy=strategy,
                                            before=original, after=box)))
        if strategy == 'drop':
            for obj in matches:
                obj.update(visible=False, opacity=0., pixel_mask=Image.new('L',box[2:]), bbox=box)
            continue
        assert_not_fullscreen(box, plan.size)
        for obj in matches:
            obj.update(bbox=box, pixel_mask=mask)
            if obj.get('layout_trace'):
                obj['layout_trace']['output_bbox'] = list(box)
            if obj.get('inner_rect') and box != original:
                ix,iy,iw,ih = obj['inner_rect']
                sx,sy = box[2]/original[2],box[3]/original[3]
                obj['inner_rect'] = (box[0]+(ix-original[0])*sx, box[1]+(iy-original[1])*sy, iw*sx, ih*sy)
            if obj.get('lighting_declaration') and box != original:
                from worker.lighting_declaration import transform
                obj['lighting_declaration'] = transform(obj['lighting_declaration'],box[2:],
                                                       scale=(box[2]/original[2],box[3]/original[3]))
        commands.append(('paste',sp,box[:2],mask))
        if matches and any(o.get('role') != 'decoration' for o in matches) and mask.getbbox():
            peers.append(dict(id=identity,bbox=box,mask=mask))
    plan.commands = commands
    metrics.setdefault('primitive_guard', []).extend(notes)
    from app.enforcement import record
    record(notes, 'frame')
