"""Job-scoped product dispositions. Recovery is explicit; logging never runs a fix.

Internal validators may still raise to their typed recovery boundary. Never classify
an arbitrary exception as a floor merely because its fallback also failed.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import json
import logging
from worker.errors import PipelineFailure

FLOORS = {
    'INPUT_REFUSED': ('child_safety', '内容不适合儿童观看，已停止制作。'),
    'SAFETY_BLOCKED': ('child_safety', '内容安全检查未通过，已停止制作。'),
    'SUBJECT_ABSENT_EPISODE': ('subject_presence', '整集画面中没有出现讲解主体，无法交付。'),
    'SUBTITLE_FULLY_OCCLUDED': ('subtitle_visibility', '字幕被完全遮挡，无法交付。'),
    'TTS_UNDER_BUDGET': ('duration', '实测语音不足15秒，无法交付。'),
    'TTS_OVER_BUDGET': ('duration', '实测语音超过45秒，无法交付。'),
    'DURATION_BELOW_FLOOR': ('duration', '实测成片不足15秒，无法交付。'),
    'DURATION_ABOVE_CEILING': ('duration', '实测成片超过45秒，无法交付。'),
    'SIZE_EXCEEDS_LIMIT': ('encoding', '成片压缩后仍超过1.5MB，无法交付。'),
    'ENCODING_FAILED': ('encoding', '视频编码未成功，无法交付。'),
    'FILE_CORRUPT': ('encoding', '编码文件损坏，无法交付。'),
    'SHAPE_UNREPAIRABLE': ('shape_unrepairable', '讲解对象的形状无法修复，无法交付。'),
}
_current = ContextVar('delivery_degradations', default=None)
LOG = logging.getLogger(__name__)


class FloorFailure(PipelineFailure):
    def __init__(self, code, message=None):
        if code not in FLOORS:
            raise ValueError('floor code must belong to the six delivery floors')
        super().__init__(code, dict(code=code, floor=FLOORS[code][0], message=message or FLOORS[code][1]))

    def __reduce__(self):
        return type(self), (self.code, str(self))


@contextmanager
def audit_scope(audit, *, journal=None):
    """Bind the actual audit object; nested stages share it unless explicitly rebound."""
    audit.setdefault('degradations', [])
    token = _current.set((audit, journal))
    try:
        yield audit
    finally:
        _current.reset(token)


def degrade(code, detail, fix, *, audit=None):
    """Append evidence and selected recovery. Never call fix, never raise a floor.

    fix describes an actual recovery chosen by the caller, not a promise of success.
    Repeated identical observations accumulate a count; distinct details are kept.
    """
    scope = _current.get()
    target = audit if audit is not None else scope[0] if scope else None
    row = dict(code=str(code), detail=deepcopy(detail), fix=str(fix))
    # JSON-safe detached evidence; callers should pass bounded, non-secret details.
    row = json.loads(json.dumps(row, ensure_ascii=False, default=lambda v: type(v).__name__))
    if target is not None:
        rows = target.setdefault('degradations', [])
        old = next((r for r in rows if all(r.get(k) == row[k] for k in ('code', 'detail', 'fix'))), None)
        if old is None:
            rows.append(row)
        else:
            old['count'] = old.get('count', 1) + 1
    # Also emit outside a bound scope: never silently discard a downgrade.
    LOG.info('delivery_degradation %s', json.dumps(row, ensure_ascii=False))
    journal = (scope[1] if scope else None) or (target.get('_degradation_journal') if target is not None else None)
    if journal is not None:
        try:
            with journal.open('a') as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        except OSError:
            LOG.error('降级审计日志写入失败，记录仍保留在任务 audit.degradations 中')
    return row


def floor(code, message=None):
    from app.enforcement import is_hard, record
    aliases = {'TTS_UNDER_BUDGET': 'DURATION_BELOW_FLOOR', 'TTS_OVER_BUDGET': 'DURATION_ABOVE_CEILING',
               'ENCODING_FAILED': 'ENCODE_FAILED'}
    code = aliases.get(code, code)
    if is_hard(dict(code=code)):
        raise PipelineFailure(code, dict(code=code, message=message))
    record([dict(code=code, reason=message or FLOORS.get(code, ('', code))[1])], 'delivery')


def merge(audit, rows):
    """Idempotent transport merge, including repeated-observation counts."""
    dest = audit.setdefault('degradations', [])
    for row in rows:
        previous = next((r for r in dest if all(r.get(k) == row.get(k) for k in ('code', 'detail', 'fix'))), None)
        if previous is None:
            dest.append(deepcopy(row))
        elif row.get('count', 1) > previous.get('count', 1):
            previous['count'] = row['count']
    return audit


def reconcile_visual_scenes(content, visuals, fallback, *, audit):
    """Content owns scene count/order. Keep unique indexed rows; repair only visuals."""
    groups = {}
    for row in visuals:
        groups.setdefault(row.index, []).append(row)
    expected = list(range(1, len(content) + 1))
    if [v.index for v in visuals] != expected:
        degrade('VISUAL_SCENE_STRUCTURE', dict(expected=expected, actual=[v.index for v in visuals]),
                '按内容场次对齐视觉；多余场删除，缺失或重复索引场单独重建', audit=audit)
    result = []
    for index, scene in enumerate(content, 1):
        candidates = groups.get(index, [])
        result.append(candidates[0] if len(candidates) == 1 else fallback(index, scene))
    return result


def current_rows():
    scope = _current.get()
    return deepcopy(scope[0].get('degradations', [])) if scope else []


def disk_notice(path):
    """5 GiB is a resource warning, not a seventh delivery floor."""
    import shutil
    free = shutil.disk_usage(path).free
    if free < 5 * 1024**3:
        message = '可用磁盘空间不足5GiB，制作继续；如写入或编码失败会明确报告。'
        scope = _current.get()
        if not scope or not any(r['code'] == 'DISK_LOW' for r in scope[0].get('degradations', [])):
            degrade('DISK_LOW', dict(message=message, free_bytes=free), '保留现有内容，继续有界制作')
            LOG.warning(message)
        return message
    return None
