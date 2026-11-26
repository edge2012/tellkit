"""W117: action consistency from painted sprite masks and engine endpoint ledgers."""
from itertools import combinations
import math
import unicodedata
from app.action_end_state import area, intersection, mask_components

CODES = {'SPLIT_START_ALREADY_SPLIT', 'COMPONENT_COUNT_UNCHANGED', 'PREBAKED_OUTCOME_ITEM',
         'APPEAR_TARGET_ALREADY_VISIBLE', 'DISAPPEAR_TARGET_STILL_VISIBLE'}
SUGGESTION = '交代码执行一次确定性整块合并；保留 split、旁白和时长。后置校验不通过则拒绝整题。'
OUTCOME_SUGGESTION = '交代码删除证据指定的结局 item 并重绑过程前目标；不得改旁白或时长。后置校验不通过则拒绝整题。'


def normalized_label(label):
    return ''.join(unicodedata.normalize('NFKC', label or '').casefold().split())


def outcome_items(visual, beat, metrics, scene):
    intent = beat.get('animation') or {}
    refs = {intent.get('subject_id'), intent.get('target_id')} - {None}
    painted = {o['id']: o for o in metrics['objects']
               if o.get('pixel_mask') is not None and o['pixel_mask'].getbbox()}
    hits = []
    for a, b in combinations(visual['items'], 2):
        la, lb = normalized_label(a.get('label')), normalized_label(b.get('label'))
        if not la or not lb or la == lb or not (la in lb or lb in la):
            continue
        evidence = dict(scene=scene, sentence=beat['sentence'], object_id=intent.get('subject_id') or a['id'],
                        check='outcome_items', actual=all(i['id'] in painted for i in (a,b)), threshold=False,
                        basis='action references a pair with strict substring labels and both painted at start',
                        action=intent.get('action'), subject_id=intent.get('subject_id'),
                        target_id=intent.get('target_id'), source='painted_sprite_masks',
                        components=[dict(id=i['id'], label=i.get('label'),
                            normalized_label=normalized_label(i.get('label')),
                            bbox=list(painted[i['id']]['bbox']) if i['id'] in painted else None,
                            mask_visible=i['id'] in painted) for i in (a, b)])
        base = dict(scene=scene, sentence=beat['sentence'], object=intent.get('subject_id') or a['id'], measured=evidence)
        if len(visual['items']) >= 3:
            hits.append(dict(base, code='OUTCOME_ITEM_CROWDING', tier='craft',
                             detail='同场至少三个 item，两个 label 有严格子串关系；建议合并叙述对象。'))
        if intent.get('action') and refs & {a['id'], b['id']} and all(i['id'] in painted for i in (a,b)):
            hits.append(dict(base, code='PREBAKED_OUTCOME_ITEM', tier='hard',
                             detail='动作引用的前后状态候选对象在起始 alpha 掩膜中同时可见。'+OUTCOME_SUGGESTION,
                             instruction=OUTCOME_SUGGESTION))
    return hits


def split_start(visual, beat, metrics, scene):
    intent = beat.get('animation') or {}
    if intent.get('action') != 'split':
        return []
    painted = {o['id']: o for o in metrics['objects']
               if o.get('pixel_mask') is not None and o['pixel_mask'].getbbox()}
    items = [dict(i, bbox=list(painted[i['id']]['bbox'])) for i in visual['items'] if i['id'] in painted]
    hits = []
    def half(item):
        label = unicodedata.normalize('NFKC', item.get('label') or '').casefold()
        return '半' in label or 'half' in label
    for a, b in combinations(items, 2):
        aa, ab = area(a['bbox']), area(b['bbox'])
        same = (a.get('shape') == b.get('shape') and min(aa, ab) > 0
                and min(aa, ab)/max(aa, ab) >= .8
                and intersection(a['bbox'], b['bbox']) < min(aa, ab))
        if not ((half(a) and half(b)) or same):
            continue
        evidence = dict(scene=scene, sentence=beat['sentence'], object_id=intent['subject_id'],
                        check='split_start', actual=2, threshold=1,
                        basis='two visible half labels or same-shape peers with area ratio >= .8 and distinct occupied areas',
                        frame_ms=metrics.get('frame_ms'), action='split', components=[{k: i.get(k) for k in ('id','bbox','label','shape')} for i in (a,b)])
        hits.append(dict(code='SPLIT_START_ALREADY_SPLIT', tier='hard', scene=scene,
                         sentence=beat['sentence'], object=intent['subject_id'], measured=evidence,
                         detail='split 起始帧已同时存在同族组件。'+SUGGESTION, instruction=SUGGESTION))
    return hits


def components(metrics, ids=None, size=None):
    """Count painted connected components; merge uses the actual union of both masks."""
    objects = [o for o in metrics['objects'] if ids is None or o['id'] in ids]
    if size is not None:
        from PIL import Image, ImageChops
        union = Image.new('L', size)
        for o in objects:
            layer = Image.new('L', size)
            layer.paste(o['pixel_mask'], tuple(round(x) for x in o['bbox'][:2]))
            union = ImageChops.lighter(union, layer)
        return mask_components(union, [0,0,*size])
    return [box for o in objects for box in mask_components(o['pixel_mask'], o['bbox'])]


def endpoint_findings(declaration, before, after, size, scene=None, sentence=None):
    action = declaration['action']
    ids = {declaration['subject']}
    if action == 'merge':
        ids.add(declaration.get('target'))
    a = components(before, ids, size if action == 'merge' else None)
    b = components(after, ids, size if action == 'merge' else None)
    scene = scene if scene is not None else declaration.get('scene')
    sentence = sentence if sentence is not None else declaration.get('sentence')
    evidence = dict(scene=scene, sentence=sentence, object_id=declaration['subject'],
                    check='action_components', actual=[len(a),len(b)],
                    threshold='appear starts at 0; disappear ends at 0; split/merge component counts differ',
                    basis='connected components from painted sprite alpha masks',
                    action=action, before_count=len(a), after_count=len(b), before_bboxes=a, after_bboxes=b,
                    source='painted_sprite_masks')
    base = dict(scene=scene, sentence=sentence, object=declaration['subject'], measured=evidence)
    hits = []
    if (action == 'appear' and a) or (action == 'disappear' and b):
        hits.append(dict(base, code=('APPEAR_TARGET_ALREADY_VISIBLE' if action == 'appear'
                                    else 'DISAPPEAR_TARGET_STILL_VISIBLE'), tier='hard',
                         detail='appear 对象起始已可见' if action == 'appear' else 'disappear 对象终态仍可见',
                         instruction='交代码固定 appear 起始不可见、disappear 终态不可见。'))
    if action in {'split','merge','appear','disappear'} and len(a) == len(b):
        hits.append(dict(base, code='COMPONENT_COUNT_UNCHANGED', tier='hard',
                         detail='动作前后组件数未变化', instruction='交代码核验组件数量；一次确定性修正后仍不变化则拒绝整题。'))
    a, b = components(before), components(after)
    if len(a) == len(b) and all(math.dist(x, y) < .02*min(size) for x,y in zip(sorted(a),sorted(b))):
        hits.append(dict(base, code='ACTION_NO_VISIBLE_CHANGE', tier='craft',
                         detail='组件数相同且 bbox 位移不足短边 2%', instruction='重写动作与起始状态，确保画面有可见变化；保持原旁白和时长。'))
    return hits, evidence


def inspect_scene(scene, size=(1280,720)):
    import json
    from worker.scenekit_renderer import _stage
    from app.action_geometry import split_directions
    from app.expression_contract import visual_payload
    visual = split_directions(visual_payload(scene), scene.get('narration',''))
    duration = scene['duration_ms']; hits = []; receipts = []
    for i, beat in enumerate(visual.get('beats', [])):
        intent = beat.get('animation') or {}
        if not intent.get('action'):
            metrics = _stage(json.dumps(visual), size, scene['index'], 0, duration)[1]
            hits.extend(outcome_items(visual, beat, metrics, scene['index']))
            continue
        from app.sentence_beats import animation_window
        lo, hi = animation_window(visual, beat, i, duration)
        # Exact q=0/q=1 boundaries used by the production action driver.
        states = [_stage(json.dumps(visual),size,scene['index'],lo+q*(hi-lo),duration)[1] for q in (.2,.8)]
        hits.extend(outcome_items(visual, beat, states[0], scene['index']))
        hits.extend(split_start(visual, beat, states[0], scene['index']))
        declaration = dict(action=intent['action'], subject=intent['subject_id'], target=intent.get('target_id'))
        findings, evidence = endpoint_findings(declaration,*states,size,scene['index'],beat['sentence'])
        evidence['before_components_by_item'] = {o['id']: len(components(states[0], {o['id']})) for o in states[0]['objects']}
        evidence['after_components_by_item'] = {o['id']: len(components(states[1], {o['id']})) for o in states[1]['objects']}
        hits.extend(findings); receipts.append(dict(evidence))
    return hits, receipts


def failures(board, scene_ids):
    rows = []
    for scene in board.model_dump(mode='json')['scenes']:
        if scene['index'] not in scene_ids:
            continue
        for aspect, size in (('16x9', (1280,720)), ('9x16', (720,1280))):
            hits, _ = inspect_scene(scene, size)
            for hit in hits:
                rows.append(dict(hit, aspect=aspect, item=hit['object'], checklist_id=10, **{'pass':False},
                                 evidence=hit['detail'], action_evidence=hit['detail'],
                                 start_already_final=hit['code'] in {'SPLIT_START_ALREADY_SPLIT', 'PREBAKED_OUTCOME_ITEM'}))
    from app.enforcement import partition
    checked = partition(rows)
    return checked['blocking'] + checked['craft']
