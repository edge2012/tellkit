"""Appendix B is the public performance contract; properties adapt to rendering."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

class Trigger(BaseModel):
    model_config = ConfigDict(extra='forbid')
    object: str = Field(min_length=1)
    event: Literal['appear', 'change', 'move', 'disappear', 'speak']
    at_ms: int = Field(ge=0, strict=True)

class CameraMotion(BaseModel):
    model_config = ConfigDict(extra='forbid', serialize_by_alias=True)
    type: Literal['push-in', 'pull-back']
    anchor: str = Field(min_length=1)
    scene: int | None = Field(default=None, ge=1)
    from_scale: float = Field(default=1.0, alias='from')
    to: float = 1.2
    start_ms: int = Field(default=0, ge=0)
    duration_ms: int = Field(default=600, ge=400, le=800)

    @model_validator(mode='after')
    def bounds(self):
        if self.type == 'push-in' and not (self.from_scale == 1.0 and 1.15 <= self.to <= 1.25):
            raise ValueError('push-in requires 1.0 to 1.15–1.25')
        if self.type == 'pull-back' and (self.from_scale, self.to) != (1.2, 1.0):
            raise ValueError('pull-back requires 1.2 to 1.0')
        return self

    @property
    def kind(self): return self.type
    @property
    def target(self): return self.anchor
    @property
    def scale(self): return self.to if self.type == 'push-in' else self.from_scale

class PoseEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    item: str = Field(min_length=1)
    pose: Literal['idle', 'look_at', 'point', 'wonder', 'nod', 'walk_in']
    duration_ms: int = Field(default=1200, ge=600)
    transition_ms: int = Field(default=250, ge=200, le=300)
    target: str = Field(min_length=1)
    trigger: Trigger

    @property
    def start_ms(self): return self.trigger.at_ms






