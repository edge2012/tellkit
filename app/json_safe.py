"""Strict JSON boundary for measurement evidence; never stringify opaque objects."""
import hashlib
import json
import math
from app.response_assembly import ResponseAssemblyError

from PIL import Image
import numpy as np


class UnsafeJSON(ResponseAssemblyError, TypeError):
    pass


def can_serialize(payload):
    try:
        json.dumps(payload, ensure_ascii=False, allow_nan=False)
        return True
    except (TypeError, ValueError, OverflowError, RecursionError):
        return False


def _walk(value, path, changed, issues, active, *, sanitize):
    try:
        return _walk_value(value, path, changed, issues, active, sanitize=sanitize)
    except (ResponseAssemblyError, RecursionError):
        raise
    except Exception as exc:
        raise UnsafeJSON(path, 'JSON traversal failed: ' + type(exc).__name__) from exc


def _walk_value(value, path, changed, issues, active, *, sanitize):
    kind = type(value)
    if value is None or kind in (str, bool, int):
        return value
    if kind is float and math.isfinite(value):
        return value
    if kind in (dict, list, tuple):
        if id(value) in active:
            issues.append({'path': path, 'type': 'circular_reference'})
            if sanitize:
                raise UnsafeJSON(path, 'circular reference')
            return None
        active.add(id(value))
        try:
            if kind is dict:
                result = {}
                for key, item in value.items():
                    if type(key) is not str:
                        issues.append({'path': path + '[<key>]', 'type': type(key).__name__})
                        if sanitize:
                            raise UnsafeJSON(path + '[<key>]', 'non-string key')
                        continue
                    result[key] = _walk(item, path + '[' + json.dumps(key, ensure_ascii=False) + ']', changed, issues, active, sanitize=sanitize)
                return result
            if kind is tuple:
                changed.append(path)
            return [_walk(item, f'{path}[{i}]', changed, issues, active, sanitize=sanitize) for i, item in enumerate(value)]
        finally:
            active.remove(id(value))
    issues.append({'path': path, 'type': kind.__module__ + '.' + kind.__qualname__})
    if not sanitize:
        return None
    changed.append(path)
    if isinstance(value, Image.Image):
        return dict(type='image_summary', width=value.width, height=value.height,
                    mode=value.mode, sha256_12=hashlib.sha256(value.tobytes()).hexdigest()[:12])
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise UnsafeJSON(path, 'object array')
        summary = dict(type='array_summary', shape=list(value.shape), dtype=str(value.dtype),
                       sha256_12=hashlib.sha256(value.tobytes(order='C')).hexdigest()[:12])
        if value.ndim in (2, 3):
            channels = 1 if value.ndim == 2 else value.shape[2]
            summary.update(type='image_summary', width=value.shape[1], height=value.shape[0],
                           mode={1: 'L', 3: 'RGB', 4: 'RGBA'}.get(channels, f'{channels}-channel'))
        return summary
    if isinstance(value, np.generic):
        return _walk(value.item(), path, changed, issues, active, sanitize=True)
    if kind is float:
        return None  # Non-finite measurements have no JSON numeric representation.
    raise UnsafeJSON(path, 'unsupported type: ' + kind.__name__)


def serialization_issues(payload):
    issues = []
    try:
        _walk(payload, '$', [], issues, set(), sanitize=False)
    except RecursionError:
        issues.append({'path': '$', 'type': 'maximum_depth'})
    return issues


def sanitize_audit(audit):
    """Return a detached native JSON tree with all replacement paths recorded."""
    changed = []
    result = _walk(audit, '$', changed, [], set(), sanitize=True)
    if isinstance(result, dict) and changed:
        previous = result.get('audit_sanitized', [])
        if not isinstance(previous, list) or not all(isinstance(p, str) for p in previous):
            previous = []
        result['audit_sanitized'] = list(dict.fromkeys(previous + changed))
    return result
