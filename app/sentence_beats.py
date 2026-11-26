"""Sentence-bound changes, shared by generation, rendering and evidence."""
from app.response_assembly import required_first
import re
import math
from copy import deepcopy
from typing import Literal, Annotated
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator, ValidationError, model_serializer
from pydantic_core import PydanticCustomError
from app.action_vocabulary import Action, SplitCount, SPLIT_COUNTS, validate_capability


def sentences(text):
    return [s.strip() for s in re.findall(r'[^。！？!?；;\n]+[。！？!?；;\n]*', text) if s.strip()]


def drop_legacy_slots(data, *, scene=None):
    if not isinstance(data, dict): return data
    data = deepcopy(data)
    dropped = {}
    for name in ('before', 'after'):
        state = data.get(name)
        if not isinstance(state, dict): continue
        keys = set(state) if data.get('animation') is not None else set(state) & {'position', 'scale'}
        if keys:
            dropped[name] = {key: state.pop(key) for key in sorted(keys)}
        if not state: data.pop(name, None)
    if dropped:
        from app.enforcement import record
        record([dict(code='LEGACY_SLOT_FIELD_DROPPED', scene=scene, object=data.get('object', data.get('target')),
                     measured=dict(sentence=data.get('sentence'), fields=dropped))], 'generation')
    return data


class BeatState(BaseModel):
    model_config = ConfigDict(extra='forbid')
    color: Literal['red','orange','yellow','green','blue','indigo','violet','brown','gray','white'] | None = None
    visible: bool | None = None


class AnimationEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    type: Literal['位移', '形变', '新增元素', '消失']
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    duration_ms: int = Field(gt=0)
    scene_duration_ms: int | None = Field(default=None, gt=0)
    from_xy: tuple[Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)], Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]] = (0., 0.)
    to_xy: tuple[Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)], Annotated[float, Field(ge=-1, le=1, allow_inf_nan=False)]] = (0., 0.)
    from_scale: float = Field(default=1., gt=0, allow_inf_nan=False)
    to_scale: float = Field(default=1., gt=0, allow_inf_nan=False)
    from_opacity: float = Field(default=1., ge=0, le=1)
    to_opacity: float = Field(default=1., ge=0, le=1)
    from_shape: str | None = None
    to_shape: str | None = None

    @model_validator(mode='after')
    def window(self):
        if not self.start_ms < self.end_ms <= (self.scene_duration_ms or self.duration_ms):
            raise ValueError('animation must have a nonempty window inside scene')
        if self.scene_duration_ms is not None and self.duration_ms != self.end_ms-self.start_ms:
            raise ValueError('animation duration must equal its window length')
        from app.visual_spec_w27b import VOCABULARY
        if any(shape is not None and shape not in VOCABULARY for shape in (self.from_shape,self.to_shape)):
            raise ValueError('animation replacement requires a registered shape')
        if self.type == '位移':
            dx, dy = (b-a for a,b in zip(self.from_xy, self.to_xy))
            actual = {aspect: math.hypot(dx*w, dy*h)/min(w,h)
                      for aspect,(w,h) in {'16x9':(1280,720), '9x16':(720,1280)}.items()}
            measured = dict(property='position', actual=actual, threshold=.02, unit='canvas_short_side')
            enough = all(value >= .02-1e-12 for value in actual.values())
        elif self.type == '形变':
            actual = abs(self.to_scale/self.from_scale-1)
            measured = dict(property='scale', actual=actual, threshold=.05, unit='relative_to_before')
            enough = actual >= .05-1e-12
        elif self.type in {'新增元素', '消失'}:
            expected = (0.,1.) if self.type == '新增元素' else (1.,0.)
            measured = dict(property='opacity', actual=[self.from_opacity,self.to_opacity], threshold=list(expected))
            enough = (self.from_opacity,self.to_opacity) == expected
        else:
            enough = bool(self.from_shape and self.to_shape and self.from_shape != self.to_shape)
            measured = dict(property='shape', actual=[self.from_shape,self.to_shape], threshold='different registered shapes')
        from app.enforcement import is_soft, record
        if not enough:
            record([dict(code='UNIT_CHANGE_TOO_SMALL', tier='hard', scene=0, measured=measured)], 'animation')
        return self


class ActionIntent(BaseModel):
    model_config = ConfigDict(extra='forbid', json_schema_extra={
        'allOf': [
            {'if': {'properties': {'action': {'enum': ['move_to','pour','sink','merge','dissolve']}}, 'required': ['action']},
             'then': {'required': ['target_id'], 'properties': {'target_id': {'type': 'string','minLength': 1}}},
             'else': {'properties': {'target_id': {'type': 'null'}}}},
            {'if': {'properties': {'action': {'const': 'split'}}, 'required': ['action']},
             'then': {'required': ['count'], 'properties': {'count': {'enum': list(SPLIT_COUNTS)}}},
             'else': {'properties': {'count': {'type': 'null'}}}}
        ]})
    action: Action
    subject_id: str = Field(min_length=1)
    target_id: str | None = Field(default=None, min_length=1)
    count: SplitCount | None = None
    direction: Literal['horizontal', 'vertical'] | None = None
    start_opacity: Literal[0.] | None = Field(default=None, exclude_if=lambda value: value is None)
    end_opacity: Literal[0.] | None = Field(default=None, exclude_if=lambda value: value is None)

    @model_validator(mode='before')
    @classmethod
    def fields(cls, data):
        from app.action_contract import invalid
        if isinstance(data, dict):
            forbidden = set(data) & {'x','y','from_xy','to_xy','scale','from_scale','to_scale','width','height'}
            if forbidden:
                invalid('几何由引擎计算，不要填坐标：' + ', '.join(sorted(forbidden)))
            action = data.get('action')
            validate_capability(action, data.get('count'))
            if action != 'split' and data.get('direction') is not None:
                invalid('direction 仅允许用于 split')
            targeted = action in {'move_to','pour','sink','merge','dissolve'}
            if targeted != (data.get('target_id') is not None):
                invalid(f'{action} 的 target_id 必填且仅目标动作允许')
            if (action == 'split') != (data.get('count') is not None):
                invalid('split 必填 count（2），其他动作不允许 count')
        return data


def validate_intent(intent, items, action=None, subject=None):
    from app.action_contract import invalid
    value = ActionIntent.model_validate(intent).model_dump(exclude_none=True)
    from app.action_contract import resolve_target
    resolve_target(value['action'], value['subject_id'], value.get('target_id'), items)
    ids = [o.get('id') for o in items]
    for key in ('subject_id', 'target_id'):
        if key in value and value[key] not in ids:
            invalid(f'{key}={value[key]} 不存在；可用 id：{ids}')
    if action is not None and value['action'] != action:
        invalid('animation.action 与 beat 动作不一致')
    if subject is not None and value['subject_id'] != subject:
        invalid('animation.subject_id 与 beat 执行对象不一致；可用 id：' + str(ids))
    return value


class SpeechWindow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    start_ms: float = Field(ge=0)
    end_ms: float = Field(ge=0)


from app.action_contract import Action, EVENTS, validate_action, validate_fields, validate_target, schema_rules


def beat_schema(schema, model=None, *, field='change'):
    schema.update(schema_rules(field))
    # Only statements expose non-geometric state; animated beats forbid slot states.
    states = {k: schema['properties'].pop(k) for k in ('before', 'after')}
    schema['properties'].update(before={}, after={})
    schema['allOf'].append({'if': {'properties': {'animation': {'type': 'object'}}, 'required': ['animation']},
        'then': {'properties': {'before': False, 'after': False}},
        'else': {'properties': states}})


class SentenceBeat(BaseModel):
    allow_overlap: bool = False
    model_config = ConfigDict(json_schema_extra=beat_schema, extra='forbid')
    speech_window: SpeechWindow | None = None
    at: float | None = Field(default=None, gt=0, lt=1)
    sentence: int = Field(ge=1)
    change: Action | None
    target_id: str | None = None
    into_id: str | None = None
    with_id: str | None = None
    n: SplitCount | None = None

    _action = field_validator('change', mode='before')(validate_action)
    object: int = Field(ge=0)
    animation: ActionIntent | None = None
    animation_source: Literal["model", "code", "failed"] | None = None
    animation_error: str | None = None
    before: BeatState = Field(default_factory=BeatState)
    after: BeatState = Field(default_factory=BeatState)

    @model_validator(mode='before')
    @classmethod
    def drop_slots(cls, data):
        from app.action_contract import soft_renderable_beat
        data = soft_renderable_beat(data)
        if isinstance(data, dict) and data.get('change') == 'split' and data.get('n') is not None:
            validate_capability('split', data['n'])
        return drop_legacy_slots(data)


    @model_serializer(mode='wrap')
    def serialize(self, handler):
        value = handler(self)
        if self.animation is not None:
            value.pop('before', None); value.pop('after', None)
        return value

    @model_validator(mode='after')
    def meaningful(self):
        validate_fields(self.change, self.model_dump())
        a=self.before.model_dump(exclude_none=True); b=self.after.model_dump(exclude_none=True)
        if self.animation is not None:
            if self.change is None or self.animation.action != self.change:
                raise ValueError("animation requires the matching semantic action")
            return self
        if self.change is None:
            return self
        elif self.change in {'appear', 'disappear'}:
            expected = (False, True) if self.change == 'appear' else (True, False)
            if (a.get('visible'), b.get('visible')) != expected:
                raise ValueError('visibility direction does not match change')
        elif a == b and self.animation is None:
            raise ValueError('action requires changed states or explicit animation')
        return self


def declarations(scene):
    compile_events(scene, missing_only=True)
    lines = sentences(scene.get('narration', ''))
    visual = scene['visual']
    beats = visual.get('beats', [])
    hits = []

    def reject(sentence, slot, expected, actual, **details):
        hits.append(dict(code='STATIC_IMAGE_MULTI_NARRATION', scene=scene.get('index'),
            object='beats', measured=dict(sentence=sentence, slot=slot,
                expected=expected, actual=actual, **details), threshold=expected))

    def craft(sentence, slot, expected, actual, **details):
        hits.append(dict(code='BEAT_TARGET_REUSED' if 'same_target' in details else 'BEAT_CHANGE_TYPE_REPEATED',
            scene=scene.get('index'), object='beats', measured=dict(sentence=sentence, slot=slot,
            expected=expected, actual=actual, **details)))

    order = [b.get('sentence') if isinstance(b, dict) else None for b in beats]
    if order != list(range(1, len(lines)+1)):
        reject(list(range(1, len(lines)+1)), 'beats',
               'one ordered beat per sentence; preserve narration', order)
    used = {}
    prev = None
    for b in beats:
        sentence = b.get('sentence') if isinstance(b, dict) else None
        target = b.get('object') if isinstance(b, dict) else None
        slot = target
        event = b.get('animation') if isinstance(b, dict) else None
        try:
            SentenceBeat.model_validate(b)
            validate_target(b['change'], b, visual['items'], visual['items'][target].get('id'))
            if b['change'] is None:
                if prev is not None and prev.get('change') is None:
                    raise ValueError('同一场不得连续两句 change=null')
                prev = b
                continue
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            small = [e for e in exc.errors() if e['type'] == 'UNIT_CHANGE_TOO_SMALL'] if isinstance(exc, ValidationError) else []
            if small:
                for error in small:
                    hits.append(dict(code='UNIT_CHANGE_TOO_SMALL', scene=scene.get('index'), object=target,
                        measured=dict(sentence=sentence, slot=target, **error['ctx']['measured']),
                        threshold=error['ctx']['measured']['threshold']))
                prev = b
                continue
            hits.append(dict(code='ACTION_TARGET_SELF' if getattr(exc, 'type', None) == 'ACTION_TARGET_SELF' else 'CONTENT_CELL_INVALID', scene=scene.get('index'), object=target,
                measured=dict(sentence=sentence, action=b.get('change') if isinstance(b, dict) else None, target=(b.get('target_id') or b.get('into_id') or b.get('with_id')) if isinstance(b, dict) else None),
                detail=str(exc)))
            prev = b
            continue
        try:
            validate_intent(event, visual['items'], b['change'], visual['items'][target].get('id'))
        except (ValueError, TypeError, KeyError) as exc:
            hits.append(dict(code='ACTION_TARGET_SELF' if getattr(exc, 'type', None) == 'ACTION_TARGET_SELF' else 'CONTENT_CELL_INVALID', scene=scene.get('index'), object=target,
                             measured=dict(sentence=sentence), detail=str(exc)))
        try:
            SentenceBeat.model_validate(b)
            item = visual['items'][target]
            slot = item.get('id', target)
            if slot in used:
                craft(sentence, slot, 'target reuse allowed; statistic only', slot,
                       sentence_a=used[slot], sentence_b=sentence, same_target=slot)
            used[slot] = sentence
            if prev and b['change'] == prev['change']:
                craft(sentence, slot, 'adjacent same change type allowed; statistic only', b['change'],
                       change_type=b['change'], prev_change_type=prev['change'])
            if item.get('role') not in {'subject', 'tool', 'result'}:
                reject(sentence, slot, 'teaching object role: subject/tool/result', item.get('role'))
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            reject(sentence, slot, 'valid target index and meaningful before/after change',
                   dict(beat=b, error=str(exc)))
        prev = b if isinstance(b, dict) and 'change' in b else None
    return sorted(hits, key=lambda h: h['code']=='BEAT_NOT_ANIMATED')


def at_time(visual, fraction, scene_index=None, duration_ms=None):
    """Sample semantic intents without changing the scene layout or item membership."""
    v=deepcopy(visual); beats=v.pop('beats',[])
    if not beats:return _visible_items(v)
    # Preserve the sampled sentence, including statement beats that revoke permission.
    v['_overlap_context'] = dict(beats=deepcopy(beats), fraction=fraction)
    for i, b in enumerate(beats):
        for name in ('before', 'after'):
            state = b.get(name) or {}
            assert not (set(state) & {'position', 'scale'}), 'LEGACY_SLOT_FIELD_READ'
            assert not b.get('animation') or not any(v is not None for v in state.values()), 'LEGACY_SLOT_FIELD_READ'
        duration = visual.get('_duration_ms', duration_ms or 1)
        lo, hi = animation_window(dict(visual, beats=beats), b, i, duration)
        lo, hi = lo/duration, hi/duration
        start, end = lo+(hi-lo)*.2, lo+(hi-lo)*.8
        if b.get('animation') is None:
            assert b.get('change') is None, 'semantic animation required'
            item = v['items'][b['object']]
            state = b.get('after' if fraction >= (b.get('at') or (lo+hi)/2) else 'before') or {}
            item.update({k:x for k,x in state.items() if x is not None})
            continue
        intent = validate_intent(b['animation'], v['items'])
        if fraction < lo and intent['action'] != 'appear':
            continue
        q = min(1., max(0., (fraction-start)/max(1e-9,end-start)))
        item = required_first(((it for it in v['items'] if it.get('id') == intent['subject_id'])), path='worker/app/sentence_beats.py:306')
        if 'animation_state' not in item or fraction >= start:
            item['animation_state'] = dict(intent, progress=q, sentence=b['sentence'], scene=scene_index)
    v.pop('_duration_ms', None)
    return v


def _visible_items(v):
    # Keep original indices for gaze and arrows after removing invisible entities.
    kept=[i for i,o in enumerate(v['items']) if o.pop('visible',True)]
    mapping={old:new for new,old in enumerate(kept)}
    v['items']=[v['items'][i] for i in kept]
    for o in v['items']:
        for field in ('gaze_target','from','to'):
            if o.get(field) is not None:o[field]=mapping.get(o[field])
    return v


def bind_timing(scene, captions, *, align_words=False):
    """Use decoded clause audio boundaries, never estimate final movie timing."""
    from app.word_timing import word_spans
    words = word_spans(scene.narration, [w for c in captions for w in c.get('word_boundaries', [])])
    lines=sentences(scene.narration); offset=0; spans=[]; windows=[]
    for cap in captions:
        spans.append((offset,offset+len(cap['text']),cap));offset+=len(cap['text'])
    offset=0
    for beat,line in zip(scene.visual.beats,lines):
        end=offset+len(line)
        covered=[c for a,b,c in spans if b>offset and a<end]
        if not covered:raise ValueError('missing TTS sentence timing')
        window = (covered[0]['start_ms'], covered[-1]['end_ms'])
        matched = [w for a,b,w in words if b > offset and a < end]
        beat.speech_window = (SpeechWindow(start_ms=matched[0]['offset_ms'],
            end_ms=matched[-1]['offset_ms']+matched[-1]['duration_ms']) if matched else None)
        if align_words and beat.speech_window:
            window = (beat.speech_window.start_ms, beat.speech_window.end_ms)
        windows.append(window)
        beat.at=sum(window)/2/scene.duration_ms
        offset=end


def compile_events(scene, *, windows=None, missing_only=False):
    """Normalize intent only. Geometry is compiled after the layout pass."""
    from app.action_contract import FIELDS
    visual = scene['visual']
    for beat in visual.get('beats', []):
        if not isinstance(beat, dict): continue
        clean = drop_legacy_slots(beat, scene=scene.get('index'))
        beat.clear(); beat.update(clean)
        if beat.get('change') is None: continue
        if beat.get('animation') is not None: continue
        try:
            subject = visual['items'][beat['object']]['id']
        except (KeyError, IndexError, TypeError):
            continue
        intent = dict(action=beat['change'], subject_id=subject)
        field = FIELDS.get(beat['change'])
        if field: intent['count' if field == 'n' else 'target_id'] = beat.get(field)
        beat['animation'] = intent
        beat['animation_source'] = 'code'
        clean = drop_legacy_slots(beat, scene=scene.get('index'))
        beat.clear(); beat.update(clean)


def animation_counts(scene):
    counts = dict(model=0, code=0, failed=0)
    for beat in scene['visual'].get('beats', []):
        if beat.get('change') is None: continue
        source = 'failed' if beat.get('animation_error') or not beat.get('animation') else beat.get('animation_source') or 'model'
        counts[source] += 1
    return counts


def animation_window(visual, beat, index, duration):
    n = len(visual['beats'])
    window = beat.get('speech_window') or dict(start_ms=index*duration/n, end_ms=(index+1)*duration/n)
    lo = window['start_ms']
    hi = min(window['end_ms'], max(0, duration-visual.get('ending_hold_ms', 0)))
    if hi <= lo and beat.get('animation'):
        from app.enforcement import record
        record([dict(code='ENDING_ACTION_OVERLAP', object=beat.get('object'), sentence=beat.get('sentence'), reason='no action window before closing hold')], 'animation')
        lo = min(lo, max(0, duration-1))
        hi = max(lo+1, min(duration, window['end_ms']))
    return lo, hi
