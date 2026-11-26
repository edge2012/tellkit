"""W81: declarations select predicates; only renderer observations prove them.

All boxes are [x, y, width, height] in manifest pixel space. Missing evidence
fails closed. No narration, animation amplitude or model verdict is evidence.
"""
import math
import re

ACTIONS = {'move_to', 'pour', 'sink', 'split', 'merge', 'stack', 'dissolve', 'appear', 'disappear', 'aside'}


def visible(obj):
    return bool(obj and obj.get('bbox') and obj.get('visible', True) and obj.get('opacity', 1) > 0)


def area(b):
    return max(0, b[2])*max(0, b[3])


def center(b):
    return b[0]+b[2]/2, b[1]+b[3]/2


def intersection(a, b):
    return max(0, min(a[0]+a[2], b[0]+b[2])-max(a[0], b[0]))*max(0, min(a[1]+a[3], b[1]+b[3])-max(a[1], b[1]))


def distance(point, box):
    x, y = point
    return math.hypot(max(box[0]-x, 0, x-box[0]-box[2]), max(box[1]-y, 0, y-box[1]-box[3]))


def gap(a, b):
    return math.hypot(max(a[0]-b[0]-b[2], b[0]-a[0]-a[2], 0), max(a[1]-b[1]-b[3], b[1]-a[1]-a[3], 0))


def missing_fields(obj, prefix, fields=('bbox',)):
    """Only absent observations are unmeasurable; invalid values still raise."""
    if obj is None:
        return [prefix]
    missing = []
    if 'fill_rgb' not in fields and obj.get('fill_rgb') is not None:
        fields = (*fields, 'fill_rgb')
    for field in fields:
        value = obj.get(field)
        if value is None:
            missing.append(f'{prefix}.{field}')
        elif isinstance(value, (list, tuple)):
            missing.extend(f'{prefix}.{field}[{i}]' for i, part in enumerate(value) if part is None)
            if all(part is not None for part in value):
                expected = 4 if field == 'bbox' else 3
                if len(value) != expected or not all(math.isfinite(part) for part in value):
                    raise ValueError(f'{prefix}.{field}: invalid geometry values')
                if field == 'fill_rgb' and any(part < 0 or part > 255 for part in value):
                    raise ValueError(f'{prefix}.{field}: RGB outside 0..255')
    for field in ('opacity', 'visible'):
        if field in obj and obj[field] is None:
            missing.append(f'{prefix}.{field}')
    return missing


def predicate(action, before, after, target_before=None, target_after=None, *, n=2, pieces=()):
    a = before.get('bbox') if before else None
    b = after.get('bbox') if after else None
    t0 = target_before.get('bbox') if target_before else None
    t = target_after.get('bbox') if target_after else None
    result = dict(action=action, before_bbox=a, after_bbox=b, target_before_bbox=t0, target_bbox=t, passed=False, deficits={})
    deficits = result['deficits']
    fields = ('bbox', 'fill_rgb') if action == 'highlight' else ('bbox',)
    missing = missing_fields(before, 'before', fields) + missing_fields(after, 'after', fields)
    if action in {'move_to', 'pour', 'sink', 'merge', 'stack', 'dissolve', 'aside'} and (target_before is not None or target_after is not None):
        missing += missing_fields(target_after, 'target_after')
    if action in {'dissolve', 'aside'} and target_after is not None:
        missing += missing_fields(target_before, 'target_before')
    if action == 'split':
        if pieces is None:
            missing.append('pieces')
        for i, piece in enumerate(pieces or ()):
            missing += missing_fields(piece, f'pieces[{i}]')
        if before is not None:
            if 'component_bboxes' in before and before['component_bboxes'] is None:
                missing.append('before.component_bboxes')
            for i, box in enumerate(before.get('component_bboxes') or ()):
                if box is None or any(v is None for v in box):
                    missing.append(f'before.component_bboxes[{i}]')
    if missing:
        result.update(status='unmeasurable', missing_fields=missing)
        return result
    va, vb = visible(before), visible(after)
    if action in {'appear', 'disappear'}:
        expected = [False, True] if action == 'appear' else [True, False]
        result['visibility'] = [va, vb]
        deficits['visibility_endpoints'] = sum(x != y for x, y in zip([va, vb], expected))
        result['passed'] = deficits['visibility_endpoints'] == 0
        return result
    if action == 'split':
        boxes = [p['bbox'] for p in pieces if visible(p) and a and area(p['bbox']) >= area(a)*.25]
        overlap = sum(intersection(x,y) for i,x in enumerate(boxes) for y in boxes[i+1:])
        total = sum(map(area, boxes))/area(a) if a and area(a) else None
        minimum_gap = min((gap(x,y) for i,x in enumerate(boxes) for y in boxes[i+1:]), default=0)
        initial_count = sum(area(box) >= area(a)*.25 for box in before.get('component_bboxes', [a])) if before and a else 0
        sizes = [area(box)/area(a) for box in boxes] if a and area(a) else []
        lengths = [max(box[2:])/max(a[2:]) for box in boxes] if a and max(a[2:]) else []
        result.update(piece_bboxes=boxes, count=len(boxes), initial_count=initial_count,
                      expected_count=n, area_ratio=total, gap_px=minimum_gap, long_edge_ratios=lengths)
        deficits.update(count=max(0,2-len(boxes)), overlap_px2=overlap,
                        area_fraction=max(0,total-1.15) if total is not None else None,
                        piece_area=max(0,.25-min(sizes,default=0)), gap_px=max(0,8-minimum_gap),
                        long_edge=max(0,max(lengths,default=1)-.75), missing_start=int(not va))
        result['passed'] = bool(va and initial_count < len(boxes) and
                               all(v is not None and v <= 1e-9 for v in deficits.values()))
        return result
    if action in {'scale', 'highlight'}:
        if action == 'scale':
            result['passed'] = bool(va and vb and a and b and abs(max(b[2:])/max(a[2:])-1.25) <= .02)
        else:
            colors = [o.get('fill_rgb') for o in (before, after)]
            result['passed'] = bool(va and vb and all(c is not None for c in colors) and sum(abs(x-y) for x,y in zip(*colors)) >= 20)
        return result
    if not a or not b or not t or not visible(target_after):
        deficits['missing_geometry'] = sum(x is None for x in (a,b,t)) + int(t is not None and not visible(target_after))
        return result
    inside = distance(center(b), t)
    result.update(center_distance_px=inside, bbox_gap_px=gap(b,t), above_rim=bool(t[0] <= center(b)[0] <= t[0]+t[2] and b[1]+b[3] <= t[1]),
                  rim_vertical_gap_px=b[1]+b[3]-t[1])
    if action == 'move_to' and after.get('rests_on') == target_after.get('id') and after.get('rests_on') is not None:
        deficits.update(contact_gap_px=abs(b[1]+b[3]-t[1]),
                        horizontal_overflow_px=max(t[0]-b[0],b[0]+b[2]-t[0]-t[2],0),
                        overlap_px2=intersection(b,t), visibility=int(not vb))
    elif (action == 'move_to' and target_after.get('id') is not None
            and (after.get('comparison') or {}).get('peer_id') == target_after['id']):
        deficits.update(gap_error_px=abs(gap(b,t)-24), bottom_alignment_px=abs(b[1]+b[3]-t[1]-t[3]),
                        overlap_px2=intersection(b,t), visibility=int(not vb))
    elif action == 'move_to':
        from app.visual_thresholds import GAP
        deficits.update(gap_error_px=abs(gap(b,t)-GAP), overlap_px2=intersection(b,t), visibility=int(not vb))
    elif action == 'aside':
        start_gap = gap(a,t0) if t0 else None
        end_gap = gap(b,t)
        result.update(start_gap_px=start_gap,end_gap_px=end_gap,gap_change_px=end_gap-start_gap if start_gap is not None else None)
        # Aside means strictly farther apart and disjoint, not an arbitrary travel floor.
        deficits.update(gap_increase_px=max(0,start_gap-end_gap) if start_gap is not None else None,
                        increase_missing=int(start_gap is None or end_gap<=start_gap), separation_missing=int(end_gap<=0), visibility=int(not (va and vb)))
    elif action in {'merge','stack'}:
        overlap = intersection(b,t)/min(area(b),area(t)) if min(area(b),area(t)) else 0
        result['overlap_fraction'] = overlap
        deficits.update(overlap_fraction=max(0,.6-overlap),visibility=int(not vb))
    elif action in {'sink', 'pour'}:
        deficits.update(center_distance_px=inside, below_rim_missing=int(center(b)[1] <= t[1]),
                        visibility=int(not (va and vb)))
    elif action == 'dissolve':
        color = 0.
        if before.get('fill_rgb') is not None and after.get('fill_rgb') is not None:
            color = sum(abs(x-y) for x,y in zip(before['fill_rgb'],after['fill_rgb']))/(3*255)
        opacity = abs(before['opacity']-after['opacity']) if 'opacity' in before and 'opacity' in after else 0.
        shrink = max(0,1-area(b)/area(a)) if area(a) else 0.
        in_both = bool(t0 and distance(center(a),t0)==0 and inside==0)
        changed = in_both and (opacity >= .3 or color >= .3 or (action=='dissolve' and shrink >= .5) or (action=='pour' and va!=vb))
        result.update(opacity_change=opacity,color_change=color,area_shrink=shrink,in_container=in_both)
        deficits.update(center_distance_px=inside,opacity_fraction=max(0,.3-opacity),color_fraction=max(0,.3-color),area_fraction=max(0,.5-shrink))
        result['passed'] = bool((vb and inside==0) or changed) if action=='pour' else bool(changed and va)
        return result
    else:
        raise ValueError(action)
    result['passed'] = all(v is not None and v <= 1e-9 for v in deficits.values())
    return result


def requirements(scene, beat, claim):
    """Resolve scene-local targets conservatively; ambiguity never picks nearest geometry."""
    from app.action_contract import ALLOWED, FIELDS
    if 'change' in beat and beat['change'] is None:
        return []
    if beat.get('change') in ALLOWED:
        action = beat['change']
        intent = beat.get('animation') or {}
        from app.action_contract import resolve_target
        subject = intent.get('subject_id') or scene['visual']['items'][beat['object']]['id']
        target = resolve_target(action, subject, intent.get('target_id', beat.get(FIELDS.get(action))), scene['visual']['items'])
        return [dict(action=action, target=target,
                     target_name=None, n=intent.get('count') or beat.get('n') or 2)]
    items = scene['visual']['items']
    subject = items[beat['object']]
    identity = subject.get('id',str(beat['object']))
    peers = [o for o in items if o.get('id') != identity and o.get('role') not in {'character','decoration','tool'}]
    text = claim['narration']
    actions = list(claim['actions'])
    if beat.get('action') in ACTIONS:
        actions = [beat['action']]
    if any(w in text for w in ('叠在','叠到','重叠','堆叠','合并')):
        actions = ['stack' if '叠' in text else 'merge']
    elif any(w in text for w in ('一旁','推开','移开')):
        actions = ['aside']
    result = []
    for action in actions:
        if action=='move': action='move_to'
        if action not in ACTIONS: continue
        ref = beat.get('action_target') or beat.get('into')
        candidates = [o for o in peers if o.get('id')==ref] if ref else []
        if not ref:
            if action in {'pour','sink','dissolve','move_to'}:
                from app.container_semantics import CONTAINERS
                containers = [o for o in peers if o.get('shape') in CONTAINERS | {'water'}]
                named = [o for o in containers if o.get('label') and o['label'] in text]
                # Longest label avoids resolving 糖水 as 水 when both are mentioned.
                candidates = named or containers
                if not candidates and action=='move_to':
                    candidates = [o for o in peers if o.get('label') and o['label'] in text]
                parent = subject.get('parent')
                if parent and not named:
                    candidates = [o for o in peers if o.get('id')==parent]
                if len(candidates)>1:
                    exact_water = [o for o in candidates if o.get('shape')=='water']
                    if any(w in text for w in ('水杯','水里','水底')) and len(exact_water)==1: candidates=exact_water
            else:
                named = [o for o in peers if o.get('label') and o['label'] in text]
                candidates = named or [o for o in peers if o.get('shape')==subject.get('shape')]
        target = candidates[0] if len(candidates)==1 else None
        count = re.search(r'(\d+|两|二|三|四)个',text)
        n = beat.get('split_count') or (int(count[1]) if count and count[1].isdigit() else {'两':2,'二':2,'三':3,'四':4}.get(count[1],2) if count else 2)
        result.append(dict(action=action,target=target.get('id') if target else None,
                           target_name=target.get('label') if target else None,n=n))
    return result


def evaluate(specs, subject, maps):
    results = []
    maps = [m if m is not None else {} for m in maps]
    for spec in specs:
        pieces = [o for o in (maps[1] or {}).values() if o is not None and o.get('parent')==subject]
        obj = maps[1].get(subject) or {}
        if not pieces:
            pieces = obj.get('split_children', [])
        if not pieces:
            pieces = [dict(bbox=b,visible=visible(obj) if not missing_fields(obj, 'after') else False) for b in (obj.get('component_bboxes') or [])]
        value = predicate(spec['action'], maps[0].get(subject), maps[1].get(subject),
                          maps[0].get(spec['target']),maps[1].get(spec['target']),n=spec['n'],pieces=pieces)
        if spec['target'] is not None:
            missing = missing_fields(maps[1].get(spec['target']), 'target_after')
            if spec['action'] in {'dissolve', 'aside'}:
                missing += missing_fields(maps[0].get(spec['target']), 'target_before')
            if missing:
                value.update(passed=False, status='unmeasurable',
                             missing_fields=list(dict.fromkeys(value.get('missing_fields', []) + missing)))
        results.append(dict(value,target=spec['target'],target_name=spec['target_name']))
    return results


def mask_components(mask, bbox):
    """Map cached four-connected local bounds into this frame's bbox."""
    boxes = _mask_component_bounds(mask.mode, mask.size, mask.tobytes())
    x,y,w,h = bbox
    return [[x+a*w/mask.width,y+b*h/mask.height,(c-a)*w/mask.width,(d-b)*h/mask.height] for a,b,c,d in boxes]


from worker.raster_cache import raster_cache


@raster_cache(maxsize=128)
def _mask_component_bounds(mode, size, pixels):
    """Four-connected alpha bounds, keyed by all input mask pixels."""
    from PIL import Image
    mask = Image.frombytes(mode, size, pixels)
    import numpy as np
    pixels = np.asarray(mask) > 0
    parents, bounds, previous = [], [], []
    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for y, row in enumerate(pixels):
        edges = np.flatnonzero(np.diff(np.r_[False,row,False]))
        current = []
        for lo, hi in zip(edges[::2], edges[1::2]):
            i = len(parents); parents.append(i); bounds.append([int(lo),y,int(hi),y+1])
            current.append((lo,hi,i))
            for pl, ph, pi in previous:
                if pl >= hi: break
                if ph > lo: parents[root(pi)] = root(i)
        previous = current
    groups = {}
    for i, b in enumerate(bounds):
        k = root(i)
        if k not in groups: groups[k] = b.copy()
        else:
            old = groups[k]; groups[k] = [min(old[0],b[0]),min(old[1],b[1]),max(old[2],b[2]),max(old[3],b[3])]
    return tuple(tuple(b) for b in groups.values())
