"""Stage RSS sampling plus explicitly labelled lifetime rusage high-water marks."""
from contextlib import ContextDecorator
import json
import os
from pathlib import Path
import resource
import threading


def process_tree_rss():
    """Read resident pages for this process and every live descendant (Linux)."""
    rows = {}
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
            rows[int(path.parent.name)] = (int(fields[1]), int(fields[21]) * os.sysconf('SC_PAGE_SIZE'))
        except (OSError, ValueError, IndexError):
            continue
    owned = {os.getpid()}
    while True:
        children = {pid for pid, (parent, _) in rows.items() if parent in owned}
        if children <= owned:
            break
        owned |= children
    return rows.get(os.getpid(), (0, 0))[1], sum(rows[p][1] for p in owned if p != os.getpid())


class PeakMemory(ContextDecorator):
    def __init__(self, stage):
        self.stage = stage

    def _recreate_cm(self):
        return type(self)(self.stage)

    def sample(self):
        own, children = process_tree_rss()
        self.own = max(self.own, own)
        self.children = max(self.children, children)
        self.total = max(self.total, own + children)

    def watch(self):
        while not self.stop.wait(.02):
            self.sample()

    def __enter__(self):
        self.own = self.children = self.total = 0
        self.stop = threading.Event()
        self.sample()
        self.thread = threading.Thread(target=self.watch, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join()
        self.sample()
        own = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        children = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024
        print('PEAK_MEM ' + json.dumps(dict(stage=self.stage,
            self_mb=round(self.own / 2**20, 3), children_mb=round(self.children / 2**20, 3),
            total_mb=round(self.total / 2**20, 3), sampling_interval_ms=20,
            lifetime_self_maxrss_mb=round(own, 3), lifetime_children_maxrss_mb=round(children, 3),
            lifetime_rusage_sum_mb=round(own + children, 3))), flush=True)
        return False
