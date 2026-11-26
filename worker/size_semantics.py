"""Canvas-area sizing, independent of drawing vocabulary. All findings are craft."""
import math
import re
import json
from pathlib import Path
from contextvars import ContextVar
from PIL import Image

RANGES = dict(micro=(.03, .05), small=(.08, .12), medium=(.08, .12),
              large=(.18, .24), vast=(.18, .24))
ROLES = dict(micro='detail', small='support', medium='support', large='lead', vast='lead')
# Required label vocabulary is data, not a subject-specific rendering branch.
LABEL_WORDS = json.loads(Path(__file__).with_name("size_label_words.json").read_text())
SMALL_WORDS = LABEL_WORDS["small"]
VAST_WORDS = LABEL_WORDS["vast"]
NARRATION = ContextVar('size_narration', default='')


def furniture_allowed(text):
    return bool(re.search(r'桌上|桌面|放在[^。！？\n]*上', text))


def inferred(label):
    if any(word in label for word in ('整片', '大片', '成片', '满屏')):
        return 'vast'
    return 'micro' if any(word in label for word in ('小', '微', '细')) else 'medium'


def targets(items, scene):
    rows, notes = [], []
    def note(code, identity, measured):
        notes.append(dict(code=code, tier='craft', scene=scene, object=identity, measured=measured))
    for i, item in enumerate(items):
        identity = item.get('id') or str(i)
        label = item.get('label', '')
        category = item.get('size_class')
        if category not in RANGES:
            category = inferred(label)
            note('SIZE_CLASS_INFERRED', identity, dict(size_class=category, label=label))
        original = category
        small = any(word in label for word in SMALL_WORDS)
        vast = any(word in label for word in VAST_WORDS)
        if small: category = 'micro'
        elif vast: category = 'vast'
        if category != original:
            note('SIZE_LABEL_MISMATCH', identity, dict(before=original, after=category, label=label))
        lo, hi = RANGES[category]
        rows.append(dict(id=identity, size_class=category, role=ROLES[category], lo=lo, hi=hi, area=(lo+hi)/2))
    used = set()
    for row in sorted(rows, key=lambda r: -r['area']):
        before = row['role']
        if row['role'] == 'lead' and 'lead' in used: row['role'] = 'support'
        if row['role'] == 'support' and 'support' in used: row['role'] = 'detail'
        used.add(row['role'])
        if row['role'] != before:
            row['size_class'] = dict(support='medium', detail='micro')[row['role']]
            row['lo'], row['hi'] = RANGES[row['size_class']]
            row['area'] = (row['lo']+row['hi'])/2
            note('SIZE_ROLE_DOWNGRADED', row['id'], dict(before=before, after=row['role']))
    return rows, notes


def area_box(box, size, fraction):
    x,y,w,h = box
    target = fraction*size[0]*size[1]
    factor = math.sqrt(target/max(1,w*h))
    nw,nh = w*factor,h*factor
    # Extreme aspect ratios must fit the canvas as well as satisfy area.
    if nw > size[0]: nw,nh = size[0],target/size[0]
    if nh > size[1]: nh,nw = size[1],target/size[1]
    nw,nh = max(1,math.floor(nw)),max(1,math.floor(nh))
    return (max(0,min(size[0]-nw,round(x+(w-nw)/2))),
            max(0,min(size[1]-nh,round(y+(h-nh)/2))),nw,nh)


def scene_boxes(objects, rows, size):
    """Round raster bounds within the role interval."""
    by_id = {r['id']:r for r in rows}
    boxes = {}
    total = size[0]*size[1]
    for obj in objects:
        row = by_id.get(obj.get('id'))
        if row is None or not obj.get('bbox') or not obj.get('visible', True): continue
        x,y,w,h = area_box(obj['bbox'], size, row['area'])
        h = max(h, math.ceil(row['lo']*total/w))
        h = min(h, math.floor(row['hi']*total/w), size[1])
        boxes[id(obj)] = [x,min(y,size[1]-h),w,h]
    return boxes


def apply(plan, metrics, items, scene):
    """Resolve final object raster bounds after action/relation layout, before paint."""
    rows, notes = targets(items, scene)
    by_id = {r['id']:r for r in rows}
    commands = list(plan.commands)
    claimed = set()
    boxes = scene_boxes(metrics.get('objects', []), rows, plan.size)
    occupied = set()
    for obj in metrics.get('objects', []):
        row = by_id.get(obj.get('id'))
        if row is None or not obj.get('bbox') or not obj.get('visible', True): continue
        original = tuple(obj['bbox'])
        matches = [n for n,c in enumerate(commands) if n not in claimed and c[0]=='paste'
                   and (*c[2][:2],*c[1].size)==original]
        if not matches: continue
        n = matches[-1]; claimed.add(n)
        _,sp,_,mask = commands[n]
        row = dict(row)
        before = row['role']
        if row['role'] == 'lead' and 'lead' in occupied: row['role'] = 'support'
        if row['role'] == 'support' and 'support' in occupied: row['role'] = 'detail'
        occupied.add(row['role'])
        if before != row['role']:
            row['size_class'] = dict(support='medium',detail='micro')[row['role']]
            row['lo'],row['hi'] = RANGES[row['size_class']]
            row['area'] = (row['lo']+row['hi'])/2
            boxes[id(obj)] = area_box(original,plan.size,row['area'])
            notes.append(dict(code='SIZE_ROLE_DOWNGRADED',tier='craft',scene=scene,object=obj['id'],measured=dict(before=before,after=row['role'],replica=True)))
        box = tuple(boxes[id(obj)])
        sp = sp.resize(box[2:], Image.Resampling.LANCZOS)
        if mask is not None: mask = mask.resize(box[2:], Image.Resampling.LANCZOS)
        from worker.shape_redraw import handles, paint
        declaration = next((it for i,it in enumerate(items) if (it.get('id') or str(i)) == row['id']), {})
        if handles(declaration):
            from worker.ambient import _clock
            phase = round(((_clock.get() or 0) % 1200)/1200*24)/24
            if declaration['shape'] in {'charge','vibration'}:
                side = round(math.sqrt(box[2]*box[3]))
                box = (round(box[0]+(box[2]-side)/2),round(box[1]+(box[3]-side)/2),side,side)
            sp = paint(declaration['shape'],box[2:],declaration.get('label',''),phase)
            mask = sp
        commands[n] = ('paste',sp,box[:2],mask)
        obj.update(bbox=box, pixel_mask=sp.getchannel('A'), size_class=row['size_class'], visual_role=row['role'],
                   size_area=box[2]*box[3]/(plan.width*plan.height), size_bounds=(row['lo'],row['hi']), size_semantics=True)
        if obj.get('layout_trace'): obj['layout_trace']['output_bbox']=list(box)
        if obj.get('inner_rect'):
            ix,iy,iw,ih=obj['inner_rect']; sx,sy=box[2]/original[2],box[3]/original[3]
            obj['inner_rect']=(box[0]+(ix-original[0])*sx,box[1]+(iy-original[1])*sy,iw*sx,ih*sy)
        if obj.get('lighting_declaration'):
            from worker.lighting_declaration import transform
            obj['lighting_declaration']=transform(obj['lighting_declaration'],box[2:],
                                                  scale=(box[2]/original[2],box[3]/original[3]))
    plan.commands = commands
    metrics.setdefault('craft', []).extend(notes)
    from app.enforcement import record
    record(notes, 'layout')
