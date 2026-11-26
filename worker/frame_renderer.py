"""Fresh frame workers receive drawing inputs, never the pipeline audit heap."""
from pathlib import Path
import time

_CONFIG = None
_FONTS = None
_SCOPE = None
_ACTIVE = None
_NOTES = None


def configuration(board, captions, size, kind, out, spool):
    from app.enforcement import _state, rule_mode
    from app.geometry_healing import planning
    from worker.render_actions import _variant
    state = _state.get() or {}
    # Pydantic's field values are already validated. Preserve them when pickling,
    # while omitting the private, non-rendering audit attachment.
    drawing_board = board.model_copy()
    drawing_board._audit = {}
    return dict(board=drawing_board, captions=captions, size=size, kind=kind,
        out=str(out), spool=str(spool), mode=state.get('mode', 'block'),
        rule_mode=rule_mode(), job_id=state.get('job_id'),
        worker_stage=state.get('worker_stage'), variant=_variant.get(), planning=planning.get())


def initialize(config):
    global _CONFIG, _FONTS, _SCOPE, _ACTIVE, _NOTES
    from app.enforcement import enforcement
    from app.geometry_healing import planning
    from worker.render_actions import _variant
    from worker.render import Fonts
    _SCOPE = enforcement(config['mode'], rule_mode=config['rule_mode'], job_id=config['job_id'])
    state = _SCOPE.__enter__()
    state['worker_stage'] = config['worker_stage']
    _variant.set(config['variant'])
    planning.set(config['planning'])
    _CONFIG = config
    _FONTS = Fonts()
    _ACTIVE = None
    _NOTES = {}
    return draw


def draw(task):
    global _ACTIVE
    from worker.render_resources import release_scene
    from worker.scenekit_renderer import frame
    f, ms, index, local = task
    board = _CONFIG['board']
    scene = next(s for s in board.scenes if s.index == index)
    if _ACTIVE != index:
        release_scene()
        _ACTIVE = index
    started = time.monotonic()
    debug = {}
    elapsed = sum(s.duration_ms for s in board.scenes if s.index < index) + local*scene.duration_ms
    im = frame(scene, board.title, _CONFIG['size'], local, _FONTS, debug=debug,
        ambient_ms=elapsed, captions=(_CONFIG['captions'] or {}).get(index),
        previous_scene=next((s for s in board.scenes if s.index == index-1), None),
        episode_progress=elapsed/board.total_duration_ms)
    for note in debug.get('label_notes', []):
        key = (index, _CONFIG['size'], note['object'], note['text'])
        _NOTES[key] = dict(note, scene=index, size=_CONFIG['size'])
    path = Path(_CONFIG['spool'])/f'{f:08d}.rgb'
    try:
        if _CONFIG['kind'] == '16x9' and f == 0:
            im.save(Path(_CONFIG['out'])/'cover.jpg', quality=92, subsampling=0)
        path.write_bytes(im.tobytes())
    finally:
        im.close()
    return f, ms, index, path, debug, dict(_NOTES), time.monotonic()-started
