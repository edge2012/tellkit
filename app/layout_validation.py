"""Final pixel-layout invariants, before a DrawingPlan can be rasterized."""
from itertools import combinations

CODES = {'LAYOUT_IDENTICAL_POSITION', 'LAYOUT_OVERLAP', 'OVERLAP_TARGET_UNKNOWN', 'SPLIT_BASE_AREA_INVALID', 'OVERLAP_SEMANTICS_DENIED', 'OVERLAP_SEVERE'}

# The only action-to-overlap policy. Missing actions fail closed.
ACTION_SEMANTICS = {
    'merge': 'merge', 'sink': 'container', 'pour': 'container',
    'dissolve': 'container_or_medium', 'move_to': 'deny', 'split': 'deny',
    'appear': 'deny', 'disappear': 'deny',
}


def target_kind(item):
    from app.container_semantics import CONTAINERS
    # water is a vessel-backed water sprite in shapes_b2 (the W112 target).
    shape = item.get('shape')
    if shape in CONTAINERS | {'water'}:
        return 'container', f'container shape={shape}'
    label = (item.get('label') or '').strip().lower()
    if label in {'杯', '杯子', '水杯', '碗', '水槽', '容器', 'cup', 'bowl', 'tank', 'beaker'}:
        return 'container', f'container label={label}'
    if shape in {'liquid', 'solution'} or label in {'水', '糖水', '盐水', '清水', 'water', 'sugar water', 'solution'}:
        return 'medium', f'medium shape={shape}, label={label}'
    return None, f'no recognized container/medium shape or exact label: shape={shape!r}, label={label!r}'


def check_layout(objects, *, scene=None, aspect=None, overlap_permissions=(), semantic_context=False):
    allowed = set(frozenset((r['subject'], r['target'])) for r in overlap_permissions
                   if r.get('overlap_allowed') is True and ACTION_SEMANTICS.get(r.get('action'), 'deny') != 'deny'
                   and r.get('scene') == scene and r.get('aspect') == aspect)
    hits = [dict(code='OVERLAP_TARGET_UNKNOWN', tier='hard', scene=scene, aspect=aspect if aspect in {'16x9', '9x16'} else '16x9',
                 object=r['subject'], measured=r, detail=r['reason'])
            for r in overlap_permissions if r.get('code') == 'OVERLAP_TARGET_UNKNOWN'
            and r.get('scene') == scene and r.get('aspect') == aspect]
    for a, b in combinations(objects, 2):
        if any(o.get('visible') is False or o.get('opacity', 1) <= 0 for o in (a, b)):
            continue
        if any(o.get('render_channel') == 'surface_region' and o.get('on_surface') == peer['id']
               for o, peer in ((a,b),(b,a))):
            continue
        pair = frozenset((a['id'], b['id']))
        if pair in allowed:
            continue
        x, y, w, h = a['bbox']; u, v, s, t = b['bbox']
        overlap = max(0, min(x+w, u+s)-max(x, u))*max(0, min(y+h, v+t)-max(y, v))
        ratios = [overlap/(w*h) if w*h else 0, overlap/(s*t) if s*t else 0]
        union = w*h+s*t-overlap
        iou = overlap/union if union > 0 else 0
        same_origin = list(a['bbox'][:2]) == list(b['bbox'][:2])
        identical = same_origin or iou >= .98
        if not overlap and not identical:
            continue
        character = next((i for i,o in enumerate((a,b)) if o['id'] == 'awen'), None)
        if identical:
            code, hard = 'LAYOUT_IDENTICAL_POSITION', True
        elif character is not None:
            hard = ratios[character] >= .95
            code = 'OVERLAP_SEVERE' if hard else 'OVERLAP_NOTED'
        else:
            hard = min(ratios) >= .9
            code = 'OVERLAP_SEVERE' if hard else 'OVERLAP_NOTED'
        measured = dict(ids=[a['id'], b['id']], bboxes=[list(a['bbox']), list(b['bbox'])],
                        overlap_area=overlap, overlap_rates=ratios, iou=iou,
                        solver_inputs=[a.get('layout_trace'), b.get('layout_trace')],
                        scene=scene, sentence=1, object_id=a['id'], check='pair_overlap',
                        actual=dict(same_origin=same_origin,iou=iou) if identical else ratios[character] if character is not None else min(ratios),
                        threshold=dict(same_origin=True, iou_gte=.98, operator='or') if identical else .95 if character is not None else .9,
                        basis='identical origin or IoU >= .98' if identical else 'character overlap >= .95' if character is not None else 'min pair overlap >= .9')
        unknown = next((r for r in overlap_permissions if r.get('code') == 'OVERLAP_TARGET_UNKNOWN'
                        and frozenset((r['subject'],r['target'])) == pair
                        and r.get('scene') == scene and r.get('aspect') == aspect), None)
        if unknown:
            hits = [h for h in hits if h.get('measured') != unknown]
            measured['permission'] = unknown
            code, hard = 'OVERLAP_TARGET_UNKNOWN', True
        hits.append(dict(code=code, tier='hard' if hard else 'craft', scene=scene, aspect=aspect if aspect in {'16x9', '9x16'} else '16x9',
                         object=a['id'], measured=measured, threshold=measured['threshold'] if hard else .30,
                         detail=f"{code}: {a['id']} {a['bbox']} / {b['id']} {b['bbox']}; overlap={ratios}"))
    return hits


def _permitted_beats(visual, fraction, duration):
    """Only the active declared pair; never inherit permission across sentences."""
    beats = visual.get('beats', [])
    for i, beat in enumerate(beats):
        window = beat.get('speech_window')
        lo, hi = ((window['start_ms']/duration, window['end_ms']/duration) if window
                  else (i/len(beats), (i+1)/len(beats)))
        active = lo <= fraction < hi or (i == len(beats)-1 and fraction == hi)
        intent = beat.get('animation') or {}
        action = intent.get('action')
        if (active and ACTION_SEMANTICS.get(action, 'deny') != 'deny'
                and action == beat.get('change') and intent.get('subject_id')
                and intent.get('target_id') and intent['subject_id'] != intent['target_id']):
            yield beat


def overlap_permissions(visual, objects, fraction, duration, *, scene=None, aspect=None):
    """Frame-local decisions; ratio is intersection / smaller bbox area."""
    from app.action_end_state import intersection, area
    objects = {o['id']: o for o in objects}
    items = {o.get('id'): o for o in visual.get('items', [])}
    records = []
    for beat in _permitted_beats(visual, fraction, duration):
        intent = beat['animation']
        subject, target = intent['subject_id'], intent['target_id']
        if subject not in objects or target not in objects:
            continue
        a, b = objects[subject]['bbox'], objects[target]['bbox']
        denominator = min(area(a), area(b))
        ratio = intersection(a, b) / denominator if denominator else 0.
        policy = ACTION_SEMANTICS[intent['action']]
        code = None
        if policy == 'merge':
            allowed = ratio >= .6 or beat.get('allow_overlap') is True
            reason = 'merge ratio >= 0.60 or explicit allow_overlap=true' if allowed else 'merge ratio < 0.60 without explicit allow_overlap=true'
        else:
            kind, reason = target_kind(items.get(target, {}))
            allowed = kind == 'container' or (kind == 'medium' and policy == 'container_or_medium')
            if not allowed:
                code = 'OVERLAP_TARGET_UNKNOWN'
                reason += f'; required {policy}'
        row = dict(scene=scene, aspect=aspect, sentence=beat['sentence'],
                   action=intent['action'], subject=subject, target=target,
                   overlap_allowed=allowed, ratio=ratio, reason=reason,
                   target_shape=items.get(target, {}).get('shape'),
                   target_label=items.get(target, {}).get('label'))
        if code: row['code'] = code
        records.append(row)
    return records


def overlap_craft(records, scene_ids):
    """Count distinct scenes with actual exempted overlap, never frames/aspects."""
    scenes = set(scene_ids)
    exempt = {r['scene'] for r in records if r.get('overlap_allowed') and r.get('ratio', 0) > .30} & scenes
    ratio = len(exempt)/len(scenes) if scenes else 0
    if ratio <= .5:
        return []
    return [dict(code='OVERLAP_EXEMPTION_FREQUENT', tier='craft',
                 measured=dict(scenes=sorted(exempt), total_scenes=len(scenes), ratio=ratio),
                 threshold=.5, detail='超过半数场次使用重叠豁免，布局可能整体未给动作留空间')]
