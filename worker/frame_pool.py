"""Bounded ordered frame processes, owned by the pipeline's process group.

Rendering uses fresh processes initialized with drawing inputs and rule context.
Other callers can retain the Linux fork path. The parent merges findings and
writes video in deterministic order.
"""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
import multiprocessing

_DRAW = None


def _task(item):
    from app.enforcement import _state
    state = _state.get()
    before = len(state['violations']) if state else 0
    try:
        value = _DRAW(item)
        error = None
    except Exception as exc:
        import traceback
        from worker.exception_evidence import exception_evidence
        exception_evidence(exc)
        exc.stack_first_line = traceback.format_tb(exc.__traceback__)[-1].strip().splitlines()[0]
        value = None
        error = (type(exc).__name__, str(exc), getattr(exc, 'code', None), getattr(exc, 'detail', None),
                 {key: getattr(exc, key) for key in ('image', 'metrics', 'diagnostics', 'failure_type', 'scene', 'object', 'stack_first_line', 'exception_evidence') if hasattr(exc, key)})
    hits = state['violations'][before:] if state else []
    return value, hits, error


def _initialize():
    import os
    import sys
    sys.stdout = open(os.devnull, 'w')
    from app.enforcement import _state
    state = _state.get()
    if state:
        # Findings return to the parent; no concurrent journal writes.
        state.pop('journal', None)


def _initialize_fresh(factory, args):
    global _DRAW
    _DRAW = factory(*args)
    _initialize()


def _unwrap(result):
    from app.enforcement import record
    value, hits, error = result
    for hit in hits:
        record([hit], hit.get('stage', 'render'))
    if error:
        name, message, code, detail, evidence = error
        if name == 'SceneRenderError':
            from worker.scenekit_renderer import SceneRenderError
            restored = SceneRenderError.__new__(SceneRenderError)
            ValueError.__init__(restored, detail)
            restored.code, restored.detail = code, detail
            restored.__dict__.update(evidence)
            raise restored
        if name == 'RenderActionError':
            from worker.render_actions import RenderActionError
            restored = RenderActionError(code, **detail)
        elif name == 'PipelineFailure':
            from worker.errors import PipelineFailure
            restored = PipelineFailure(code)
        else:
            import builtins
            cls = getattr(builtins, name, ValueError)
            try:
                restored = cls(message) if isinstance(cls, type) and issubclass(cls, Exception) else ValueError(message)
            except TypeError:
                restored = RuntimeError(f'{name}: {message}')
        restored.__dict__.update(evidence)
        raise restored
    return value


@contextmanager
def ordered_frames(draw, items, workers, *, initializer=None, initargs=()):
    """At most 2*workers frames in flight; terminate all children on any error."""
    if workers == 1:
        yield map(draw, items)
        return
    global _DRAW
    _DRAW = draw
    pool = ProcessPoolExecutor(max_workers=workers,
        mp_context=multiprocessing.get_context('spawn' if initializer is not None else 'fork'),
        initializer=_initialize_fresh if initializer is not None else _initialize,
        initargs=(initializer, initargs) if initializer is not None else ())
    pending = deque()
    iterator = iter(items)

    def results():
        for _ in range(2*workers):
            item = next(iterator, None)
            if item is None:
                break
            pending.append(pool.submit(_task, item))
        while pending:
            yield _unwrap(pending.popleft().result())
            item = next(iterator, None)
            if item is not None:
                pending.append(pool.submit(_task, item))
    try:
        yield results()
    except BaseException:
        pool.kill_workers()
        raise
    finally:
        pool.shutdown(wait=True, cancel_futures=True)
        _DRAW = None
