"""Request-local, cumulative scene review deadlines (not delivery criteria)."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import json
import logging
import signal
import threading
import time

LIMIT_SECONDS = 8.0  # Per scene, cumulative across retries: N scenes => 8*N seconds.
CHECKS = ('visual_validation', 'sentence_beat_pixels', 'layout_solver.prepare')
current = ContextVar('self_check_budget', default=None)


class Expired(BaseException):
    def __init__(self, owner):
        self.owner = owner


class Budgets:
    def __init__(self):
        self.rows = {}
        self.active = {}
        self.notes = []

    @contextmanager
    def scene(self, check, scene, hits, *, limit=None):
        limit = LIMIT_SECONDS if limit is None else limit
        key = (check, scene)
        row = self.rows.setdefault(key, dict(spent=0.0, timed_out=False))
        row['limit'] = limit
        if key in self.active:
            yield True
            return
        if row.get('skipped') or row['timed_out']:
            hits.append(dict(row['note']))
            from app.enforcement import record
            record([row['note']], 'self_check_budget')
            yield False
            return
        started = time.perf_counter()
        remaining = max(0.000001, limit-row['spent'])
        owner = object()
        self.active[key] = owner
        # All production review entrypoints execute synchronously on the main
        # thread (including process workers). Never replace a thread's timer.
        main = threading.current_thread() is threading.main_thread()
        previous_handler = signal.getsignal(signal.SIGALRM) if main else None
        previous_timer = signal.getitimer(signal.ITIMER_REAL) if main else (0, 0)
        deadline = started + remaining
        def alarm(signum, frame):
            if previous_timer[0] and previous_timer[0] < remaining:
                previous_handler(signum, frame)
            raise Expired(owner)
        old_trace = None
        if main:
            signal.signal(signal.SIGALRM, alarm)
            signal.setitimer(signal.ITIMER_REAL, min(remaining, previous_timer[0]) if previous_timer[0] else remaining)
        else:
            # Python-thread callers use cooperative interruption; production's
            # main-thread timer also interrupts blocking I/O.
            import sys
            old_trace = sys.gettrace()
            def trace(frame, event, arg):
                if time.perf_counter() >= deadline:
                    raise Expired(owner)
                return trace
            sys.settrace(trace)
        timed_out = False
        error = None
        try:
            yield True
        except Expired as exc:
            if exc.owner is not owner:
                raise
            timed_out = True
        except Exception as exc:
            from worker.scenekit_renderer import SceneRenderError
            if not isinstance(exc, (SceneRenderError, TimeoutError)):
                raise
            error = exc
            timed_out = isinstance(exc, TimeoutError)
            # An unavailable measurement cannot erase a previously observed floor.
            from app.enforcement import partition
            hits.extend(partition(getattr(exc, 'diagnostics', []))['blocking'])
        finally:
            elapsed = time.perf_counter()-started
            if main:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous_handler)
                if previous_timer[0] > elapsed:
                    signal.setitimer(signal.ITIMER_REAL, previous_timer[0]-elapsed, previous_timer[1])
            else:
                import sys
                sys.settrace(old_trace)
            self.active.pop(key)
            row['spent'] += elapsed
            timed_out = timed_out or row['spent'] >= limit
            if timed_out or error is not None:
                row['timed_out'] = timed_out
                row['skipped'] = True
                note = dict(code='SELF_CHECK_SKIPPED', tier='craft', scene=scene,
                            check=check, spent_ms=round(row['spent']*1000, 3),
                            budget_ms=round(limit*1000),
                            error_type=type(error).__name__ if error else 'TimeoutError',
                            reason=str(error) if error else 'self-check budget exhausted')
                row['note'] = note
                hits.append(note)
                self.notes.append(note)
                from app.enforcement import record
                record([note], 'self_check_budget')

    def summary(self):
        return [dict(check=check, scenes=sum(v.get('scene_count', 1) for k,v in self.rows.items() if k[0] == check),
                     spent_ms=round(sum(v['spent'] for k,v in self.rows.items() if k[0] == check)*1000, 3),
                     budget_ms=round(sum(v.get('limit', LIMIT_SECONDS) for k,v in self.rows.items() if k[0] == check)*1000),
                     timed_out=any(v['timed_out'] for k,v in self.rows.items() if k[0] == check))
                for check in CHECKS]


@contextmanager
def session():
    if current.get() is not None:
        yield current.get()
        return
    budget = Budgets()
    token = current.set(budget)
    try:
        yield budget
    finally:
        summaries = budget.summary()
        from app.storyboard_trace import current_trace
        trace = current_trace.get()
        if trace is not None:
            trace.self_check_budgets = summaries
        for row in summaries:
            logging.getLogger('tellkit.content').info('SELF_CHECK_BUDGET %s', json.dumps(row),
                extra={'safe_fields': dict(event='SELF_CHECK_BUDGET', **row)})
        current.reset(token)


def episode_budgets(fn):
    @wraps(fn)
    async def call(*args, **kwargs):
        with session():
            return await fn(*args, **kwargs)
    return call


@contextmanager
def scene_budget(check, scene, hits, *, limit=None):
    budget = current.get()
    budget = budget or Budgets()
    with budget.scene(check, scene, hits, limit=limit) as allowed:
        yield allowed


def sync_session(fn):
    @wraps(fn)
    def call(*args, **kwargs):
        with session():
            return fn(*args, **kwargs)
    return call


@contextmanager
def review_errors(check, hits, *, scenes):
    """Catch setup/aggregation failures outside the timed per-scene review.

    Do not add an overlapping episode timer or double-count nested scene time.
    """
    started = time.perf_counter()
    try:
        yield
    except Exception as exc:
        from worker.scenekit_renderer import SceneRenderError
        if not isinstance(exc, (SceneRenderError, TimeoutError)):
            raise
        from app.enforcement import partition, record
        hits.extend(partition(getattr(exc, 'diagnostics', []))['blocking'])
        note = dict(code='SELF_CHECK_SKIPPED', tier='craft', check=check,
                    scene=getattr(exc, 'scene', 0), spent_ms=round((time.perf_counter()-started)*1000, 3),
                    budget_ms=round(LIMIT_SECONDS*scenes*1000),
                    error_type=type(exc).__name__, reason=str(exc))
        hits.append(note)
        record([note], 'self_check_budget')
