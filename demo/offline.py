"""Offline input and diagnostic adapters; drawing and encoding stay in worker."""
import sys
from types import ModuleType
from contextlib import contextmanager
from contextvars import ContextVar
from pydantic import BaseModel, Field, ConfigDict

class Scene(BaseModel):
    model_config = ConfigDict(extra='allow')
    index: int
    narration: str
    duration_ms: int = Field(gt=0)
    on_screen_text: str | None = None
    on_screen_text_start_ms: int = 0
    subject: list[dict] = Field(default_factory=list)
    phenomenon: dict = Field(default_factory=dict)
    relation: list[dict] = Field(default_factory=list)
    visual: dict

class Storyboard(BaseModel):
    title: str
    total_duration_ms: int = Field(gt=0)
    scenes: list[Scene]

NOTES = []
def record(hits, stage):
    for hit in hits:
        row = dict(hit, stage=stage)
        if row not in NOTES:
            NOTES.append(row)

def partition(hits):
    rows = list(hits)
    hard = [h for h in rows if h.get('tier') == 'hard']
    craft = [h for h in rows if h not in hard]
    return dict(blocking=hard, craft=craft, craft_notes=craft, blocking_violations=hard, craft_violations=craft, decision='down' if hard else 'pass_with_craft_notes' if craft else 'pass')

def blocks(hits, stage):
    record(hits, stage)
    return bool(partition(hits)['blocking'])

@contextmanager
def enforcement(*args, **kwargs):
    yield {}

def fail(code, **measured):
    return dict(code=code, measured=measured, tier='craft')

def install():
    model = ModuleType('app.storyboard')
    model.Scene, model.Storyboard = Scene, Storyboard
    sys.modules[model.__name__] = model
    audit = ModuleType('app.enforcement')
    audit.__dict__.update(evidence=lambda h: dict(h), is_hard=lambda h: h.get('tier', 'hard') == 'hard', visual_relaxed=lambda: False, _state=ContextVar('offline_state', default=None), rule_mode=lambda: 'block', HARD_CODES=frozenset(), HARD_ALLOWLIST=frozenset(), record=record, blocks=blocks, partition=partition,
        enforcement=enforcement, fail=fail, product_hit=lambda hit: dict(hit),
        is_warn=lambda: False, is_soft=lambda: False, visual_gate=lambda: 'product',
        comparison_tier=lambda code: {'tier': 'craft'}, cache_key=lambda: 'offline')
    sys.modules[audit.__name__] = audit
