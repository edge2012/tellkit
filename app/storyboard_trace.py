"""Request-local observational spans; never changes generation or gate decisions.

Exclusive milliseconds partition parent wall time; child process CPU/check totals
must not be added to wall time. No prompts, credentials or response bodies stored.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import inspect
import os
import time

current_trace = ContextVar('storyboard_trace', default=None)
current_span = ContextVar('storyboard_span', default=None)


class StoryboardTrace:
    def __init__(self, request_id):
        self.request_id = request_id
        self.started = time.perf_counter_ns()
        self.pid = os.getpid()
        self.spans = []

    @contextmanager
    def span(self, name, **details):
        # Forked pixel workers report their own checks through pixel_audit. They
        # must not copy the parent timeline or charge concurrent CPU as wall time.
        if os.getpid() != self.pid:
            yield
            return
        row = dict(id=len(self.spans), parent=current_span.get(), name=name,
                   start_ms=(time.perf_counter_ns()-self.started)/1e6, **details)
        self.spans.append(row)
        token = current_span.set(row['id'])
        try:
            yield
        except BaseException as exc:
            row['error_type'] = type(exc).__name__
            raise
        finally:
            row['end_ms'] = (time.perf_counter_ns()-self.started)/1e6
            current_span.reset(token)

    def snapshot(self):
        end = (time.perf_counter_ns()-self.started)/1e6
        rows = [dict(row) for row in self.spans]
        totals = {}
        for row in rows:
            stop = row.get('end_ms', end)
            # Union handles overlapping child calls without double-counting.
            intervals = sorted((c['start_ms'], min(c.get('end_ms', end), stop))
                               for c in rows if c['parent'] == row['id'])
            covered = 0
            cursor = row['start_ms']
            for lo, hi in intervals:
                covered += max(0, hi-max(lo, cursor))
                cursor = max(cursor, hi)
            row['duration_ms'] = round(stop-row['start_ms'], 3)
            row['exclusive_ms'] = round(max(0, stop-row['start_ms']-covered), 3)
            row['start_ms'] = round(row['start_ms'], 3)
            if 'end_ms' in row:
                row['end_ms'] = round(row['end_ms'], 3)
            bucket = totals.setdefault(row['name'], dict(calls=0, exclusive_ms=0))
            bucket['calls'] += 1
            bucket['exclusive_ms'] = round(bucket['exclusive_ms']+row['exclusive_ms'], 3)
        return dict(schema_version=1, request_id=self.request_id,
                    spent_ms=round(end, 3), spans=rows, by_stage=totals,
                    self_check_budgets=getattr(self, 'self_check_budgets', []))


@contextmanager
def span(name, **details):
    trace = current_trace.get()
    if trace is None:
        yield
    else:
        with trace.span(name, **details):
            yield


def traced(name):
    def decorate(fn):
        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_call(*args, **kwargs):
                with span(name):
                    return await fn(*args, **kwargs)
            return async_call
        @wraps(fn)
        def call(*args, **kwargs):
            with span(name):
                return fn(*args, **kwargs)
        return call
    return decorate
