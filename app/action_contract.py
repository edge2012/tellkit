"""W83 closed, mechanically decidable action declarations."""
from app.action_vocabulary import Action, ALLOWED, SPLIT_COUNTS, validate_capability
from pydantic_core import PydanticCustomError

FIELDS = dict(move_to='target_id', pour='into_id', sink='into_id', split='n', merge='with_id', dissolve='into_id')
EVENTS = dict(move_to='位移', pour='位移', sink='位移', split='形变', merge='位移', dissolve='形变', appear='新增元素', disappear='消失', highlight='形变', scale='形变')


def invalid(message):
    raise PydanticCustomError('CONTENT_CELL_INVALID', message)


def validate_action(value):
    if value is not None and value not in ALLOWED:
        validate_capability(value)
    return value


def validate_fields(action, fields):
    validate_action(action)
    required = FIELDS.get(action)
    for name in ('target_id', 'into_id', 'with_id', 'n'):
        value = fields.get(name)
        if name == required:
            if name == 'n':
                validate_capability(action, value)
            elif not isinstance(value, str) or not value.strip():
                invalid(f'{action} 必须提供 {name}')
        elif value is not None:
            invalid(f'{action} 不允许字段 {name}')


def resolve_target(action, subject, ref, items):
    """The sole target resolver for ledger, geometry, renderer and evidence."""
    if action not in {'move_to', 'pour', 'sink', 'merge', 'dissolve'}:
        return None
    ids = [o.get('id', o.get('object')) for o in items]
    if ref == subject:
        raise PydanticCustomError('ACTION_TARGET_SELF',
            'subject={subject}; target={target}; candidate_targets={candidates}',
            dict(subject=subject, target=ref, candidates=[i for i in ids if i != subject]))
    target = next((o for o in items if o.get('id', o.get('object')) == ref), None)
    if target is None:
        invalid(f'{action}: subject={subject}; target={ref}; candidate_targets={ids}')
    return ref


def validate_target(action, fields, items, subject):
    validate_fields(action, fields)
    intent = fields.get('animation') or {}
    ref = intent.get('target_id', fields.get(FIELDS.get(action)))
    return resolve_target(action, intent.get('subject_id', subject), ref, items)


def distribution(board):
    counts = dict.fromkeys(ALLOWED, 0)
    counts['null'] = 0
    for scene in board.get('scenes', []):
        for beat in scene.get('visual', {}).get('beats', []):
            action = beat.get('change')
            if action in ALLOWED or action is None:
                counts[action or 'null'] += 1
    return counts


def schema_rules(field):
    rules = []
    for action in (*ALLOWED, None):
        required = FIELDS.get(action)
        properties = {name: ({'enum': list(SPLIT_COUNTS)} if name == 'n' else {'type': 'string', 'minLength': 1})
                      if name == required else {'type': 'null'}
                      for name in ('target_id', 'into_id', 'with_id', 'n')}
        rules.append({'if': {'properties': {field: {'const': action}}, 'required': [field]},
                      'then': {'properties': properties, 'required': [required] if required else []}})
    return {'allOf': rules}


def soft_renderable_beat(value, *, field='change', scene=0):
    """Keep the subject drawn when an action cannot be represented; audit the no-op."""
    from app.enforcement import is_soft, record, HARD_ALLOWLIST
    if not isinstance(value, dict):
        return value
    from copy import deepcopy
    intent = value.get('animation')
    action = value.get(field)
    code = None
    if action is not None and action not in ALLOWED:
        code = 'ACTION_NOT_SUPPORTED'
    elif isinstance(intent, dict):
        requested = intent.get('action')
        if requested not in ALLOWED or (requested == 'split' and intent.get('count') not in SPLIT_COUNTS):
            code = 'ACTION_NOT_SUPPORTED'
        elif value.get('target') is not None and intent.get('subject_id') != value['target']:
            code = 'ACTION_SUBJECT_MISMATCH'
        elif intent.get('target_id') == intent.get('subject_id') and requested in FIELDS:
            code = 'ACTION_TARGET_SELF'
        elif requested in {'move_to', 'pour', 'sink', 'merge', 'dissolve'} and not intent.get('target_id'):
            code = 'ACTION_TARGET_UNREACHABLE'
    if code is None or (not is_soft() and code in HARD_ALLOWLIST):
        return value
    record([dict(code=code, tier='hard', scene=scene, sentence=value.get('sentence'),
        measured=dict(declaration=deepcopy(value), rendered_action=None, reason='unsupported action kept as stationary subject'))], 'action_declaration')
    result = dict(value, **{field: None}, animation=None)
    for name in ('target_id', 'into_id', 'with_id', 'n'):
        result.pop(name, None)
    return result
