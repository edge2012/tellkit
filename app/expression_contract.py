"""Relation-level structure, logic, physical evidence, and bounded recovery."""
from copy import deepcopy
from app.relation_migration import migrate

RELATIONS = ('attached_to', 'rests_on', 'casts_on', 'inside', 'blocks', 'comes_from', 'goes_to')


class PhenomenonGeometryError(ValueError):
    """Compatibility import only; author geometry findings do not raise this."""
    def __init__(self, reason, measured=None):
        self.reasons = [dict(code='RELATION_CONTRADICTION', tier='hard',
                             reason=reason, measured=measured, exhausted=True)]
        super().__init__('RELATION_CONTRADICTION: '+reason)


def geometry_findings(scene):
    """Author input diagnostics; never raise for incomplete geometry declarations."""
    import math
    p = scene.get('phenomenon')
    p = p if isinstance(p, dict) else {}
    refs = {i.get('id') for i in scene.get('visual', {}).get('items', [])
            if isinstance(i, dict) and isinstance(i.get('id'), str)}
    hits = []
    def valid_ref(value):
        return isinstance(value, str) and value in refs
    def add(obj, rel, missing, reason):
        hits.append(dict(code='PHENOMENON_GEOMETRY', scene=scene.get('index', 0),
                         object=obj, relation=deepcopy(rel), missing_refs=missing,
                         reason=reason, tier='craft', degraded=False))
    if not p.get('relations_migrated') and (p.get('projection') or p.get('light_position') is not None):
        rel = dict(type='casts_on', **{'from': p.get('actor'), 'to': p.get('receiver')})
        missing = [role for role, key in (('source','source'), ('occluder','actor'),
                   ('region','receiver'), ('surface','on_surface')) if not valid_ref(p.get(key))]
        if missing:
            add(p.get('actor') or 'phenomenon.projection', rel, missing,
                'projection 需要 source/occluder/region/surface 四个引用（字段 source/actor/receiver/on_surface）；缺失或无法解析：' + '/'.join(missing))
    graph = migrate(scene)
    config = graph['render']
    for i, rel in enumerate(graph['relation']):
        if not isinstance(rel, dict) or rel.get('degraded'): continue
        if rel.get('type') == 'casts_on':
            missing = [key for key in ('from','to') if not valid_ref(rel.get(key))]
            if config.get('light_ref') is not None and not valid_ref(config['light_ref']): missing.append('light_ref')
            if missing: add(rel.get('from') or f'relation.{i}', rel, missing, 'projection 引用缺失或无法解析：' + '/'.join(missing))
            position = config.get('light_position')
            if position is not None and (not isinstance(position, (list, tuple)) or len(position) != 2 or
                    not all(isinstance(v, (int,float)) and not isinstance(v,bool) and math.isfinite(v) and 0 <= v <= 1 for v in position)):
                add(rel.get('from'), rel, [], 'light_position 必须是两个 0–1 有限数值')
            if config.get('light_alignment') not in (None, 'position', 'overhead'):
                add(rel.get('from'), rel, [], 'light_alignment 必须为 position 或 overhead')
        if rel.get('type') in ('comes_from', 'goes_to'):
            start, end = rel.get('start', 0), rel.get('end', 1)
            if not all(isinstance(v, (int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in (start,end)) or not 0 <= start < end <= 1:
                add(rel.get('from'), rel, [], '路径 start/end 必须满足 0 <= start < end <= 1')
    return hits


def geometry_detail(notes):
    """JSON-safe, searchable job result detail, also used for successful degradation."""
    return [deepcopy({key: h.get(key) for key in ('code','scene','object','relation','missing_refs','reason')})
            for h in notes if h.get('code') == 'PHENOMENON_GEOMETRY_DEGRADED']




def visual_payload(scene):
    if hasattr(scene, 'model_dump'): scene = scene.model_dump(mode='json')
    visual = deepcopy(scene['visual'])
    safe = deepcopy(scene)
    geometry_hits = geometry_findings(scene)
    if geometry_hits: symbolic_fallback(safe, geometry_hits)
    graph = migrate(safe)
    # Render all resolvable assertions even when a different relation is broken.
    subjects = graph['subject'] if isinstance(graph['subject'], list) else []
    refs = {s.get('ref') for s in subjects if isinstance(s, dict) and isinstance(s.get('ref'), str)}
    graph['subject'] = [s for s in subjects if isinstance(s,dict) and s.get('ref') in refs]
    graph['relation'] = [r for r in graph['relation'] if isinstance(r,dict) and r.get('type') in RELATIONS
                         and isinstance(r.get('from'),str) and isinstance(r.get('to'),str)
                         and r['from'] in refs and r['to'] in refs]
    if graph['subject'] or graph['relation']:
        visual['expression'] = graph
    return visual




def symbolic_fallback(scene, hits):
    graph = migrate(scene)
    bad = [h.get('relation') for h in hits if h.get('relation')]
    for rel in graph['relation']:
        if isinstance(rel,dict) and any(all(rel.get(k)==r.get(k) for k in ('type','from','to')) for r in bad):
            rel['degraded'] = True
    geometry_bad = [h['relation'] for h in hits if h['code'] == 'PHENOMENON_GEOMETRY']
    scene['relation'] = [r for r in graph['relation'] if not any(
        isinstance(r, dict) and all(r.get(k) == bad.get(k) for k in ('type','from','to')) for bad in geometry_bad)]
    p = scene.get('phenomenon')
    # 降级只表示「这条关系不画」，不得把调试文字画到画面上。
    scene['phenomenon'] = dict(p if isinstance(p,dict) else {}, relations_migrated=True,
                               render=dict(graph['render'], symbols=[]))



