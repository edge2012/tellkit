"""Explicit failures at iterator and HTTP response assembly boundaries."""


class ResponseAssemblyError(ValueError):
    def __init__(self, path, reason, *, status=500):
        self.path = path
        self.reason = reason
        self.status = status
        super().__init__(reason + ' at ' + path)


def required_first(iterator, *, path):
    """Required lookup: exhaustion is data failure, never control flow leakage."""
    missing = object()
    value = next(iterator, missing)
    if value is missing:
        raise ResponseAssemblyError('$', 'required iterator is empty or has no matching item: ' + path)
    return value


def validate_delivery_audit(audit):
    path = '$["storyboard_audit"]'
    if type(audit) is not dict:
        raise ResponseAssemblyError(path, 'expected audit object')
    for name, expected in (('generation_id', str), ('rewrite_count', int)):
        field = path + '["' + name + '"]'
        if name not in audit:
            raise ResponseAssemblyError(field, 'missing required audit section: ' + name)
        if type(audit[name]) is not expected:
            raise ResponseAssemblyError(field, 'expected ' + expected.__name__)
        if name == 'generation_id' and not audit[name]:
            raise ResponseAssemblyError(field, 'required generation_id is empty')
    for name in ('decision', 'verdict'):
        if name in audit and type(audit[name]) is not str:
            raise ResponseAssemblyError(path + '["' + name + '"]', 'expected decision string')
    for name in ('violations', 'blocking_violations', 'craft_violations'):
        if name in audit:
            if type(audit[name]) is not list:
                raise ResponseAssemblyError(path + '["' + name + '"]', 'expected list')
            for index, value in enumerate(audit[name]):
                if type(value) is not dict:
                    raise ResponseAssemblyError(path + f'["{name}"][{index}]', 'expected finding object')
