"""Single compatibility boundary: author shorthand becomes a relation graph."""
from copy import deepcopy

# No subject identities or descriptive kinds participate in migration.
MIGRATION = (
    ('source', 'comes_from', 'actor', 'source'),
    ('receiver', 'goes_to', 'actor', 'receiver'),
    ('on_surface', 'rests_on', 'actor', 'on_surface'),
)
PROJECTION = ('casts_on', 'actor', 'receiver')


def migrate(scene):
    expression = {k: deepcopy(scene.get(k)) for k in ('subject', 'phenomenon', 'relation')}
    p = expression['phenomenon'] if isinstance(expression['phenomenon'], dict) else {}
    rels = expression['relation'] if isinstance(expression['relation'], list) else []
    # Explicit graphs are authoritative; legacy input is converted once on read.
    if not p.get('relations_migrated'):
        for field, typ, left, right in MIGRATION:
            if p.get(field) is not None:
                row = {'type': typ, 'from': p.get(left), 'to': p.get(right)}
                if row not in rels: rels.append(row)
        if p.get('light_position') is not None or p.get('projection'):
            typ, left, right = PROJECTION
            row = {'type': typ, 'from': p.get(left), 'to': p.get(right)}
            if row not in rels: rels.append(row)
        for path in p.get('paths', []) if isinstance(p.get('paths', []), list) else []:
            if isinstance(path, dict):
                row = dict(path, type='goes_to')
                if not any(isinstance(r, dict) and all(r.get(k) == row.get(k) for k in ('type', 'from', 'to')) for r in rels):
                    rels.append(row)
        if p.get('listener') is not None:
            for left, right, start, end in ((p.get('actor'), p.get('receiver'), 0, .5),
                                           (p.get('receiver'), p.get('listener'), .5, 1)):
                row = {'type': 'goes_to', 'from': left, 'to': right, 'start': start, 'end': end}
                rels = [r for r in rels if not (isinstance(r, dict) and r.get('type') == 'goes_to' and r.get('from') == left and r.get('to') == right)]
                rels.append(row)
    # Drawing configuration is separate from assertions. The gate receives only
    # graph + rendered evidence; it never reads the descriptive phenomenon.
    expression['render'] = deepcopy(scene.get('render', p.get('render', {})))
    if p.get('on_surface') is not None and not p.get('relations_migrated'):
        expression['render'].setdefault('surfaces', [p['on_surface']])
    if 'light_position' in p:
        expression['render']['light_position'] = deepcopy(p['light_position'])
    if p.get('source') is not None:
        expression['render']['light_ref'] = p['source']
    expression['render'].setdefault('light_alignment', p.get('light_alignment'))
    expression['render']['carriers'] = p.get('carriers', [])
    expression['relation'] = rels
    expression['phenomenon'] = dict(p, relations_migrated=True, render=deepcopy(expression['render']))
    return expression
