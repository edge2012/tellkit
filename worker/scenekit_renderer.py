from PIL.ImageColor import getrgb as design_rgb
from worker.design_tokens import PALETTE
from worker.design_tokens import PALETTE, STROKE as DESIGN_STROKE, RADIUS as DESIGN_RADIUS
from worker.design_tokens import PALETTE, STROKE, RADIUS, TYPE, LAYOUT, SHADOW
from app.response_assembly import required_first
from app.expression_contract import PhenomenonGeometryError
from worker.render_actions import RenderActionError
from app.enforcement import blocks, record, is_warn
"""Production adapter: B3 soft lighting, directional shadows, explicit geometry."""
from app.shape_vocab import SHAPES as W10_SHAPES, NEW_SHAPES
from app.shape_implementations import IMPLEMENTED, O1, B2, W18, require_shape
from dataclasses import replace
from functools import lru_cache
import math
import re
from PIL import Image, ImageDraw, ImageColor
from worker import scenekit_v9 as sk
from worker.scenekit_shapes import mask_for
from worker.overlays import body_fonts
from worker.visual import normalize, centered_text, paste_text, COLORS, draw_face

BG = ImageColor.getrgb(PALETTE['background'])
INK = sk.INK
DAY, NIGHT = design_rgb(PALETTE['accent']), design_rgb(PALETTE['neutral_900'])
STAR = design_rgb(PALETTE['ground'])
WINDOW_DAY, WINDOW_NIGHT = design_rgb(PALETTE['neutral_900']), design_rgb(PALETTE['accent'])


class SceneRenderError(ValueError):
    """Render context and the underlying failure message for task logs."""
    def __init__(self, scene, item, shape, reason):
        safe = re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff-]', '?', str(shape))[:32]
        from worker.composition_b5 import CODES
        from app.visual_thresholds import CODES as SPEC_CODES
        candidates = [code for code in SPEC_CODES if code in reason]
        self.code = min(candidates, key=reason.index) if candidates else "PIPELINE_FAILED"
        import ast
        self.scene, self.object, self.shape = scene, item, shape
        try:
            hits = ast.literal_eval(reason)
        except (ValueError, SyntaxError):
            hits = []
        self.diagnostics = [dict(scene=h.get('scene', scene), object=h.get('object', item),
                                 aspect=h.get('aspect'), code=h.get('code', self.code), expected=h.get('threshold'), actual=h.get('measured'), geometry=h.get('geometry'))
                            for h in hits if isinstance(h, dict)] if isinstance(hits, list) else []
        if not self.diagnostics:
            self.diagnostics = [dict(scene=scene, object=item, code=self.code, expected='valid render geometry/composition', actual=reason, geometry=None)]
        from app.enforcement import product_hit
        self.diagnostics = [product_hit(h) for h in self.diagnostics]
        self.failure_type = 'compliance_failure' if candidates else 'render_bug'
        self.detail = f'scene={scene} object={item} shape={safe}: {reason}'
        super().__init__(self.detail)


def split_base_area(obj, rows, metrics, scene):
    """Optional ledger lookup with explicit provenance; zero never reaches ratios."""
    from app.action_end_state import area
    parents = [r['start_bbox'] for r in rows
               if r.get('subject') == obj['id'] and r.get('start_bbox') is not None]
    children = obj.get('split_children', [])
    child_boxes = []
    for child in children:
        matches = [r['start_bbox'] for r in rows
                   if r.get('subject') == child['id'] and r.get('start_bbox') is not None]
        box = matches[0] if matches else child.get('start_bbox')
        if box is not None:
            child_boxes.append(box)
    if parents:
        value, source = area(parents[0]), 'a:parent_start_bbox'
    elif child_boxes:
        value, source = sum(area(b) for b in child_boxes), 'b:split_children_start_bbox'
    else:
        value, source = area(obj['bbox']), 'c:object_bbox'
    evidence = dict(object=obj['id'], source=source, base_area=value)
    metrics.setdefault('split_base_areas', []).append(evidence)
    if source.startswith('c:'):
        hit = dict(code='BASE_AREA_FALLBACK', tier='info', scene=scene,
                   object=obj['id'], measured=evidence, detail=source)
        metrics.setdefault('info', []).append(hit)
        record([hit], 'layout')
    if value <= 0:
        hit = dict(code='SPLIT_BASE_AREA_INVALID', tier='hard', scene=scene,
                   object=obj['id'], measured=evidence, threshold=0, detail=source)
        record([hit], 'layout')
        error = SceneRenderError(scene, obj['id'], 'split', str([hit]))
        error.metrics = dict(metrics, violations=[hit])
        raise error
    return value


def shape_for(item):
    return require_shape(item.shape)


def phrases(text):
    return re.findall(r'.+?(?:[，。！？；,!?;]+|$)', text, re.DOTALL)


@lru_cache(maxsize=512)
def sprite(shape, color, diameter, mood=None, state=None, *, depth="mid", polarity="-"):
    from copy import deepcopy
    im,mask=_sprite(shape,color,diameter,mood,state,polarity=polarity)
    from worker.depth import tint
    im=tint(im, depth).copy()
    declaration=deepcopy(im.info.get('lighting_declaration'))
    if declaration is not None:declaration['shape']=shape
    im.info['lighting_declaration']=declaration
    from worker.ambient import sprite as ambient_sprite
    if shape != 'awen': im = ambient_sprite(im, shape)
    return im,im.getchannel('A')


def _sprite(shape, color, diameter, mood=None, state=None, *, polarity="-"):
    require_shape(shape)
    from worker.shapes_w293 import SHAPES as SIMPLE, sprite as simple_sprite
    if shape in SIMPLE:
        return simple_sprite(shape, color, diameter, polarity=polarity)
    from worker.shapes_b4 import SHAPES as NATURE, sprite as nature_sprite
    if shape in NATURE:
        return nature_sprite(shape, color, diameter)
    if shape in W18:
        from worker.shapes_w18 import sprite as formal_sprite
        return formal_sprite(shape, color, diameter)
    if shape in B2:
        from worker.scenekit_shapes import b3_frozen_sprite
        return b3_frozen_sprite(shape,color,diameter)
    if shape in O1 | B2:
        from worker.shapes_o1 import sprite as concrete_sprite
        return concrete_sprite(shape, color, diameter)
    if shape in NEW_SHAPES:
        from worker.shapes_w10 import sprite as new_sprite
        return new_sprite(shape, color, diameter)
    mask = mask_for('earth' if shape == 'sun' else shape, diameter, diameter).copy()
    box = mask.getbbox()
    if not box:
        raise ValueError('empty silhouette')
    mask = mask.crop(box)
    material = sk.Material(ImageColor.getrgb(COLORS.get(color, COLORS['blue'])))
    if shape == 'sun':
        material = sk.Material(design_rgb(PALETTE['accent']))
    im = Image.new('RGBA', mask.size)
    layers = sk.material_layers(mask, material, 4)[:2]
    for layer in layers:
        im.alpha_composite(layer)
    from worker.scenekit_shapes import soft_lighting
    im = soft_lighting(im, mask, grammar_shape=shape, arc=shape in {"sun","moon","circle","earth"}, repair=shape not in {"arrow","curved_arrow"})
    w,h = mask.size
    d = ImageDraw.Draw(im)
    if shape == 'house':
        d.line((w*.1,h*.4,w*.9,h*.4), fill=INK,width=STROKE['body'])
        d.rectangle((w*.23,h*.50,w*.46,h*.70),fill=WINDOW_NIGHT,outline=INK,width=STROKE['body'])
        d.rectangle((w*.58,h*.57,w*.77,h-2),fill=INK)
    elif shape == 'book':
        d.line((w*.5,h*.14,w*.5,h*.91),fill=INK,width=STROKE['body'])
        for y in (.3,.47,.64,.81):
            for a,b in ((.12,.4),(.6,.88)):
                d.line((w*a,h*y,w*b,h*(y+.03)),fill=INK,width=STROKE['decoration'])
    elif shape == 'tooth' and state == 'decayed':
        d.polygon([(w*.6,h*.2),(w*.8,h*.22),(w*.75,h*.4),(w*.58,h*.34)],fill=INK)
    if mood:
        draw_face(d, (w*.22,h*.22,w*.78,h*.6), mood)
    im.putalpha(mask)
    im.info['rendered_shape'] = shape
    return im, mask


def shadow(size, obj, ground_y):
    # W7/e3d light direction and projected footprint, expressed in kit base units.
    bw = sk.base_width(obj)
    x = obj.bbox[0]+obj.bbox[2]/2
    dx = .06*bw
    dy = dx*math.tan(math.pi/6)
    layer = Image.new('RGBA',size)
    ImageDraw.Draw(layer).ellipse((round(x+dx-.55*bw),round(ground_y+dy-.05*bw),
                                  round(x+dx+.55*bw),round(ground_y+dy+.05*bw)),fill=INK+(36,))
    return layer


def rays(draw, sun, earth):
    sx,sy,sd=sun; ex,ey,ed=earth
    distance=math.hypot(ex-sx,ey-sy)
    ux,uy=(ex-sx)/distance,(ey-sy)/distance
    vx,vy=-uy,ux
    measures=[]
    for offset in (-ed*.16,0,ed*.16):
        start=math.sqrt((sd/2+10)**2-offset**2)
        end=distance-math.sqrt((ed/2+10)**2-offset**2)
        if end <= start:
            if blocks([dict(code='LIGHT_CAUSALITY_MISSING',scene=0,object='sun_ray',measured=end-start,threshold='positive visible ray length')], 'frame'):
                raise ValueError('insufficient space for sunlight')
            continue
        a=(sx+ux*start+vx*offset,sy+uy*start+vy*offset)
        b=(sx+ux*end+vx*offset,sy+uy*end+vy*offset)
        draw.line((*a,*b),fill=PALETTE['accent'],width=STROKE['body'])
        measures.append((math.hypot(a[0]-sx,a[1]-sy)-sd/2,
                         math.hypot(b[0]-ex,b[1]-ey)-ed/2))
    return measures


def frame(scene, title, size, local, fonts, *, debug=None, captions=None, episode_progress=None, previous_scene=None, ambient_ms=None):
    from app.expression_contract import visual_payload
    import json
    hold = scene.visual.ending_hold_ms
    if hold:
        freeze_ms = max(0, scene.duration_ms-hold)
        local = min(local, freeze_ms/scene.duration_ms)
        ambient_ms = round(local*scene.duration_ms)
        episode_progress = None
    try:
        im, metrics = stage(json.dumps(visual_payload(scene)), size, scene.index,
                            round(episode_progress*16000) if episode_progress is not None and scene.visual.layout == "narration" else round(local*scene.duration_ms), scene.duration_ms, getattr(scene,"narration",""), ambient_ms=ambient_ms, title=title)
        # A causal narration cannot pass merely because the source/receiver was omitted.
        if re.search(r'照射|晒|照到', scene.narration) and not metrics.get('light_relations') and not metrics.get('ray_gaps'):
            if blocks([dict(code='LIGHT_CAUSALITY_MISSING', scene=scene.index, object='scene', measured=0, threshold='edge ray or luma delta >=12')], 'frame'):
                raise SceneRenderError(scene.index,'scene','light','LIGHT_CAUSALITY_MISSING')
        from copy import deepcopy
        metrics = deepcopy(metrics)
        im = im.copy()
        if scene.visual.handoff and local < .22 and previous_scene is None:
            if blocks([dict(code='TRANSITION_HANDOFF',scene=scene.index,object='handoff',measured=None,threshold='previous scene required')], 'frame'):
                raise SceneRenderError(scene.index,'scene','transition','TRANSITION_HANDOFF: missing previous scene')
        if scene.visual.handoff and local < .22 and previous_scene is not None:
            old,_ = stage(json.dumps(visual_payload(previous_scene)),size,previous_scene.index,previous_scene.duration_ms,previous_scene.duration_ms,previous_scene.narration)
            f=min(1,max(0,local/.22))
            if scene.visual.handoff.action == 'transform':
                im=Image.blend(old,im,f)
            else:
                shift=round(size[0]*f); combined=im.copy()
                combined.paste(old,(-shift,0));combined.paste(im,(size[0]-shift,0));im=combined
        w,h=size
        from worker.overlays import body_fonts
        display = scene.visual.spatial_frame == 'display' or scene.visual.layout == 'narration' or any(it.shape == 'timeline_axis' for it in scene.visual.items)
        paste_text(im, centered_text(fonts,title,TYPE['title'],w*.9),w/2,h*LAYOUT['title_y'])
        if getattr(scene, 'on_screen_text', None) and local*scene.duration_ms >= getattr(scene, 'on_screen_text_start_ms', 0):
            paste_text(im,centered_text(body_fonts(),scene.on_screen_text,TYPE['explanation'],w*LAYOUT['explanation_width']),w*(LAYOUT['safe']+LAYOUT['explanation_width']/2),h*LAYOUT['explanation_y'])
        ms=local*scene.duration_ms
        if captions is None:
            parts=phrases(scene.narration)
            speech=max(1,scene.duration_ms-350)
            total=sum(map(len,parts));elapsed=0;captions=[]
            for part in parts:
                end=elapsed+speech*len(part)/max(total,1)
                captions.append(dict(text=part,start_ms=elapsed,end_ms=end));elapsed=end
        from worker.captions import paginate
        from worker.overlays import body_fonts, caption, labels
        caption_size = round(TYPE['caption']*min(w,h)/720)
        captions = paginate(captions, body_fonts(), caption_size, w-2*min(w,h)*.08-32*min(w,h)/720)
        for cap in captions:
            if cap['start_ms'] <= ms < cap['end_ms']:
                from worker.captions import measured_page
                from app.visual_spec_w27c import subtitles
                layout = caption(im,cap,metrics['objects'])
                ink_boxes = layout['ink_boxes']
                measured = [dict(p, ink_boxes=ink_boxes if p is cap else []) for p in captions]
                hits = subtitles(measured, ''.join(p['text'] for p in captions), scene.index, size)
                if blocks(hits, 'subtitle'): raise SceneRenderError(scene.index,'subtitle','ink',str(hits))
                x,y,bw,bh=layout['bbox']
                metrics.update(caption_lines=cap['lines'],caption_box=(x,y,x+bw,y+bh),caption_layout=layout,caption_gap_px=y-metrics['content_bottom'])
                break
        reserved=[(w*LAYOUT['safe'],0,w*(1-2*LAYOUT['safe']),h*.12)]
        if getattr(scene,'on_screen_text',None):
            reserved.append((w*LAYOUT['safe'],h*LAYOUT['explanation_y'],w*LAYOUT['explanation_width'],TYPE['explanation']*TYPE['line_height']))
        from worker.overlays import caption_band_top
        reserved.append((0,caption_band_top(size),w,h-caption_band_top(size)))
        caption_before = im.copy() if metrics.get('caption_layout') else None
        metrics['labels'],metrics['label_notes']=labels(im,scene.visual,metrics,reserved,scene.narration,title=title)
        from app.enforcement import record
        record(metrics['label_notes'], 'label_placement')
        if caption_before is not None:
            from worker.soft_safety import subtitle_occlusion
            if blocks(subtitle_occlusion(caption_before, im, metrics['caption_layout']['ink_boxes'], scene.index), 'subtitle_safety'):
                raise SceneRenderError(scene.index, 'subtitle', 'ink', 'SUBTITLE_FULLY_OCCLUDED')
        if debug is not None:
            debug.update(metrics)
        return im
    except (SceneRenderError, RenderActionError, PhenomenonGeometryError):
        raise
    except Exception as exc:
        raise SceneRenderError(scene.index,'scene','layout',f'layout or compositing failed: {type(exc).__name__}: {exc}') from exc


def stage(serial,size,index,t,duration_ms=2200,narration="", *, ambient_ms=None, title=""):
    from app.enforcement import cache_key
    if narration and serial.startswith('{'):
        import json
        from app.action_geometry import split_directions
        serial = json.dumps(split_directions(json.loads(serial), narration))
    from worker.ambient import enabled
    from worker.render_actions import _variant
    return _cached_stage(serial,size,index,t if enabled() or _animated(serial) else 0,duration_ms,narration,(cache_key(), enabled(), _variant.get()), ambient_ms if enabled() else None, title)


@lru_cache(maxsize=512)
def _animated(serial):
    """Only omit time from the cache when no drawing operation consumes it."""
    import json
    if not serial.startswith('{'):return True
    v=json.loads(serial)
    items=v.get('items',[])
    if v.get('expression') or v.get('phenomenon') or v.get('beats'):return True
    if v.get('poses') or (v.get('camera_motion') or {}).get('type') in {'push-in','pull-back'}:return True
    if v.get('spatial_frame')=='display':
        return any(it.get('role')=='decoration' for it in items)
    if v.get('layout')=='narration':return True
    if any(it.get('shape')=='timeline_axis' for it in items):return False
    if v.get('spatial_frame') and v.get('background'):
        return any(it.get('samples') or it.get('action')=='fall' or
                   (it.get('parent') and it.get('phase') and it.get('shape') in {'stone','wood'}) or
                   it.get('shape')=='tank_stone' for it in items)
    return any(it.get('shape')=='earth' for it in items)


# Keep only the current stage and the previous stage used by handoffs.
@lru_cache(maxsize=2)
def _cached_stage(serial,size,index,t,duration_ms,narration,scope,ambient_ms=None,title=""):
    from worker.subject_geometry import violations
    import json
    from app.visual_spec_w27b import storyboard_violations, geometry_violations
    visual_data=json.loads(serial) if serial.startswith('{') else {}
    from app.scene_budget import trim
    visual_data, budget_notes = trim(visual_data, narration, index)
    serial = json.dumps(visual_data)
    for item_index,item in enumerate(visual_data.get('items',[])):
        if item.get('shape') not in IMPLEMENTED:
            raise SceneRenderError(index,item_index+1,item.get('shape'),'UNKNOWN_SHAPE 该形状尚未实现; SHAPE_UNRECOGNIZABLE')
    declared=storyboard_violations({'scenes':[dict(index=index,narration=narration,visual=visual_data)]})
    from app.enforcement import comparison_tier
    if blocks([dict(code=c, scene=index, object='scene', measured=d, threshold='valid declaration', **comparison_tier(c)) for _,c,d in declared], 'render_declaration'):raise SceneRenderError(index,'scene','declarations',str(declared))
    from worker.ambient import clock
    from worker.size_semantics import NARRATION
    narration_token = NARRATION.set(narration)
    try:
        with clock(t if ambient_ms is None else ambient_ms):
            im,metrics=_stage(serial,size,index,t,duration_ms)
    finally:
        NARRATION.reset(narration_token)
    if visual_data.get('layout') == 'compare' and any(it.get('id') == 'item_1' for it in visual_data.get('items', [])):
        metrics['comparison_peers'] = [dict(id='item_1'), dict(id='item_2')]
    metrics.setdefault('craft', []).extend(budget_notes)
    from app.enforcement import record
    record(budget_notes, 'layout')
    metrics['layout']=visual_data.get('layout')
    metrics['narration']=narration
    metrics['scene']=index
    from app.visual_validation import check
    errors=check('frame',metrics=metrics,size=size)['hits']
    metrics['violations']=errors
    if blocks([dict(h, time_ms=t) for h in errors], 'frame'):raise SceneRenderError(index,'scene','geometry',str(errors))
    from worker.drawing_plan import DrawingPlan
    if isinstance(im,DrawingPlan):
        from worker.label_selection import suppress_empty_boxes
        suppress_empty_boxes(im, metrics, visual_data, title)
        from worker.frame_safety import protect_text_bands
        protect_text_bands(im, metrics, index)
        im=im.render()
    if visual_data.get('poses') or (visual_data.get('camera_motion') or {}).get('type') in {'push-in','pull-back'}:
        from worker.performance import apply
        from worker.visual import Visual
        base_limit=_camera_base(serial,size,index,duration_ms,scope) if (visual_data.get('camera_motion') or {}).get('type') in {'push-in','pull-back'} else None
        with clock(t if ambient_ms is None else ambient_ms):
            im,metrics=apply(im,metrics,Visual.model_validate(visual_data),t,base_limit)
        transformed_errors=check('frame',metrics=metrics,size=size)['hits']
        metrics['violations']=transformed_errors
        if blocks([dict(h, time_ms=t) for h in transformed_errors],'frame'):raise SceneRenderError(index,'scene','camera_geometry',str(transformed_errors))
    from worker.occlusion_guard import assert_not_fullscreen
    for obj in metrics['objects']:
        if obj.get('visible', True):
            assert_not_fullscreen(obj['bbox'], size)
    errors=check('frame',metrics=metrics,size=size,image=im,pixel_only=True)['hits']
    for obj in metrics['objects']:
        mask = obj.pop('pixel_mask', None)
        obj['visible'] = mask.getbbox() is not None if mask is not None else True
        if mask is not None:
            from app.action_end_state import mask_components
            obj['opacity'] = mask.getextrema()[1]/255
            obj['component_bboxes'] = mask_components(mask, obj['bbox'])
        if obj.get('material_rgb') is not None:
            obj['fill_rgb'] = obj['material_rgb']
    metrics['pixel_violations']=errors
    if blocks([dict(h, time_ms=t) for h in errors], 'pixels'):
        failure=SceneRenderError(index,'scene','pixels',str(errors))
        failure.image=im
        failure.metrics=metrics
        raise failure
    return im,metrics


@lru_cache(maxsize=128)
def _camera_base(serial,size,index,duration_ms,scope):
    """Fit all declared motion extrema once, so zoom never pumps as objects move."""
    from worker.visual import Visual
    from worker.performance import camera_geometry
    visual=Visual.model_validate_json(serial)
    times={0,duration_ms,visual.camera_motion.start_ms}
    times.update(round(sample.at*duration_ms) for it in visual.items for sample in it.samples)
    bases=[]
    for ms in sorted(times):
        _,metrics=_stage(serial,size,index,ms,duration_ms)
        geometry=camera_geometry(visual.camera_motion,metrics['objects'],size,0)
        bases.append(geometry['start_scale']/(1.2 if visual.camera_motion.kind=='pull-back' else 1))
    return min(bases)


stage.cache_clear = _cached_stage.cache_clear

def _identify(result,visual):
    im,metrics=result
    used=set()
    for obj in metrics['objects']:
        match=next(((i,it) for i,it in enumerate(visual.items) if i not in used and it.shape==obj['shape']),None)
        if match:
            i,it=match;used.add(i);obj.update(id=it.id or str(i),role=it.role)
    return im,metrics


def _solved_layout(serial, size, index, duration_ms):
    from app.enforcement import cache_key
    return _cached_solved_layout(serial, size, index, duration_ms, scope=cache_key())


@lru_cache(maxsize=128)
def _cached_solved_layout(serial, size, index, duration_ms, *, scope):
    from worker.ambient import clock
    import json
    visual = json.loads(serial)
    visibility = {it.get('id'): it.pop('visible', True) for it in visual['items']}
    from app.geometry_healing import planning
    token = planning.set(True)
    try:
        with clock(None):
            _, metrics = _stage(json.dumps(visual), size, index, 0, duration_ms)
    finally:
        planning.reset(token)
    return [dict({k:v for k,v in o.items() if k in {'id','shape','bbox','opacity','material_rgb','comparison','layout_trace','render_channel','on_surface','rests_on','semantic_band'}},
                 visible=visibility.get(o.get('id'), True)) for o in metrics['objects']]


def _solved_scene(serial, base_serial, index, duration_ms, layout_solver, variant=None, size=(1280,720)):
    from app.aspects import delivery_sizes
    sizes = tuple(dict.fromkeys([*delivery_sizes().values(), size]))
    from app.enforcement import cache_key
    return _cached_solved_scene(serial, base_serial, index, duration_ms, layout_solver, variant, scope=cache_key(), sizes=sizes)


@lru_cache(maxsize=128)
def _cached_solved_scene(serial, base_serial, index, duration_ms, layout_solver, variant=None, *, scope, sizes):
    """Both delivery canvases share a single three-adjustment scene budget."""
    import json
    from app.action_geometry import solve_scene, ActionGeometryError
    from copy import deepcopy
    visual = json.loads(serial)
    budget, results = [], {}
    for size in sizes:
        try:
            objects = layout_solver(base_serial, size, index, duration_ms)
            from worker.expression_scene import project_actions
            results[size] = project_actions(*solve_scene(visual, objects, size, index, budget=budget),
                                            visual.get('expression'), size)
        except (ActionGeometryError, SceneRenderError) as exc:
            results[size] = exc
    for solution in results.values():
        if not isinstance(solution, Exception):
            for row in solution[1]:
                row['healing'] = deepcopy(budget)
    return results


def _stage(serial,size,index,t,duration_ms=2200, *, overlap_visual=None, overlap_fraction=None):
    from worker.visual import Visual
    import json
    from app.sentence_beats import at_time
    raw = json.loads(serial)
    from app.ledger_shapes import resolve_expression_shapes
    resolve_expression_shapes(raw)
    from app.action_contract import soft_renderable_beat
    raw['beats'] = [soft_renderable_beat(b, scene=index) for b in raw.get('beats', [])]
    sampled_context = raw.pop('_overlap_context', None)
    if overlap_visual is None and sampled_context is not None:
        overlap_visual = dict(raw, beats=sampled_context['beats'])
        overlap_fraction = sampled_context['fraction']
    from worker.render_actions import require_supported
    for beat in raw.get('beats', []):
        if beat.get('change') is not None: require_supported(beat['change'])
        if beat.get('animation'): require_supported(beat['animation'].get('action'), count=beat['animation'].get('count'))
    for item in raw.get('items', []):
        if (item.get('animation_state') or {}).get('action') is not None:
            require_supported(item['animation_state']['action'])
    raw['_duration_ms'] = duration_ms
    timed = at_time(raw, t/max(1,duration_ms), scene_index=index)
    timed.pop('_duration_ms', None)
    timed.pop('_overlap_context', None)
    intents = [it for it in timed['items'] if (it.get('animation_state') or {}).get('action')]
    if raw.get('beats') or intents:
        from app.action_geometry import solve_scene, compile_render_action as compile_action
        from worker.render_actions import _variant
        base = dict(raw)
        base.pop('beats', None); base.pop('_duration_ms', None)
        base['items'] = [{k:v for k,v in it.items() if k != 'animation_state'} for it in base['items']]
        planning_visual = raw
        if not raw.get('beats'):
            planning_visual = dict(raw, beats=[dict(sentence=it['animation_state']['sentence'],
                change=it['animation_state']['action'], animation={k:v for k,v in it['animation_state'].items()
                if k in {'action','subject_id','target_id','count','direction'}}) for it in intents])
        if size in ((1280,720),(720,1280)):
            solutions = _solved_scene(json.dumps(planning_visual, sort_keys=True),
                json.dumps(base, sort_keys=True), index, duration_ms, _solved_layout,
                _variant.get(), size=size)
            solution = solutions[size]
            if isinstance(solution, Exception):
                raise solution
            base_objects, action_rows = solution
        else:
            base_objects = _solved_layout(json.dumps(base, sort_keys=True), size, index, duration_ms)
            from worker.expression_scene import project_actions
            base_objects, action_rows = project_actions(*solve_scene(planning_visual, base_objects, size, index),
                                                       raw.get('expression'), size)
        for item in intents:
            event = item['animation_state']
            row = next((r for r in action_rows if r['sentence'] == event['sentence']), None)
            if row is None:
                intent = {k:v for k,v in event.items() if k in {'action','subject_id','target_id','count','direction'}}
                row = compile_action(intent, base_objects, size, scene=index, sentence=event['sentence'])
                action_rows.append(row)
            item['animation_state'] = (dict(fixed_bbox=row['start_bbox'], opacity=1.) if row.get('relaxed_noop')
                                       else dict(row, progress=event['progress'], engine_geometry=True))
        for item in timed['items']:
            obj = required_first(((o for o in base_objects if o['id'] == item.get('id'))), path='worker/worker/scenekit_renderer.py:374')
            if not item.get('animation_state'):
                item['animation_state'] = dict(fixed_bbox=obj['bbox'], opacity=0. if item.get('visible') is False else 1.)
            item['animation_state']['relation_base_bbox'] = obj['bbox']
    stage_healing = []
    from app.geometry_healing import planning, heal
    if not raw.get('beats') and not intents and not planning.get():
        base_objects = _solved_layout(json.dumps(raw, sort_keys=True), size, index, duration_ms)
        if raw.get('expression'):
            for item in timed['items']:
                base_obj = next((o for o in base_objects if o['id'] == item.get('id')), None)
                if base_obj:
                    item['relation_base_bbox'] = list(base_obj['bbox'])
        repaired, stage_healing, failures = heal(base_objects, size, index, frame_ms=t)
        if failures and blocks(failures, 'geometry_healing'):
            error = SceneRenderError(index, 'scene', 'geometry', str(failures))
            error.metrics = dict(violations=failures, healing=stage_healing)
            raise error
        if stage_healing:
            for item in timed['items']:
                obj = next((o for o in repaired if o['id'] == item.get('id')), None)
                if obj:
                    item['animation_state'] = dict(fixed_bbox=obj['bbox'], opacity=obj.get('opacity', 1.))
    context_beats = (overlap_visual or raw).get('beats', [])
    active_sentence = 1
    fraction = t/max(1, duration_ms) if overlap_fraction is None else overlap_fraction
    for j, beat in enumerate(context_beats):
        window = beat.get('speech_window')
        lo, hi = ((window['start_ms']/duration_ms, window['end_ms']/duration_ms) if window
                  else (j/len(context_beats), (j+1)/len(context_beats)))
        if lo <= fraction < hi or (j == len(context_beats)-1 and fraction == hi):
            active_sentence = beat['sentence']
    for item in timed['items']:
        if item.get('animation_state'):
            item['animation_state']['frame_sentence'] = active_sentence
    def observed(result):
        image, metrics = result
        metrics['frame_ms'] = t
        metrics['sentence'] = active_sentence
        metrics['healing'] = stage_healing
        for row in action_rows if raw.get('beats') or intents else []:
            metrics['healing'].extend(h for h in row.get('healing', []) if h not in metrics['healing'])
        declarations = {it.get('id'): it for it in raw.get('items', [])}
        for obj in metrics.get('objects', []):
            declaration = declarations.get(obj.get('id'), {})
            if declaration.get('comparison') is not None:
                obj['comparison'] = declaration['comparison']
            obj.setdefault('label', declaration.get('label', ''))
        rows = action_rows if raw.get('beats') or intents else []
        aspect = '16x9' if size[0] >= size[1] else '9x16'
        for obj in metrics.get('objects', []):
            declaration = declarations.get(obj.get('id'), {})
            base_obj = next((o for o in base_objects if o['id'] == obj['id']), None) if raw.get('beats') or intents else None
            event = next((it.get('animation_state') for it in timed['items'] if it.get('id') == obj['id']), None) or {}
            obj['layout_trace'] = dict(item_id=obj['id'], anchor=declaration.get('target_regions', {}).get(aspect),
                slot=declaration.get('position'), offset=declaration.get('placement', {}).get(aspect, [0, 0]),
                source='action_geometry' if event.get('engine_geometry') else 'scene_aspect_cache' if base_obj else 'layout_solver',
                input=dict(position=declaration.get('position'), target_regions=declaration.get('target_regions', {}),
                           animation=event, base_bbox=base_obj['bbox'] if base_obj else None),
                base_trace=base_obj.get('layout_trace') if base_obj else None, output_bbox=list(obj['bbox']))
        # Replace the temporary union layer with independently painted crop sprites.
        # The union mask remains a logical subject observation, never a third sprite.
        from app.action_end_state import gap
        split_objects = {}
        split_tiles = {}
        if hasattr(image, 'commands'):
            commands = []
            for command in image.commands:
                tiles = command[1].info.get('split_children') if command[0] == 'paste' else None
                if not tiles:
                    commands.append(command)
                    continue
                parent_id = tiles[0][0].rsplit('__split_', 1)[0]
                children = []
                for identity, tile, px, py in tiles:
                    commands.append(('paste', tile, (px,py), tile))
                    ink = tile.getchannel('A').getbbox()
                    if ink:
                        l,top,r,b = ink
                        children.append(dict(id=identity, parent=parent_id,
                            bbox=[px+l,py+top,r-l,b-top], visible=True))
                split_objects[parent_id] = children
                split_tiles[parent_id] = tiles
            image.commands = commands
        for obj in metrics['objects']:
            if obj['id'] in split_objects:
                children = split_objects[obj['id']]
                obj['split_children'] = children
                obj['split_gap_px'] = min((gap(a['bbox'],b['bbox']) for i,a in enumerate(children)
                                          for b in children[i+1:]),default=0)
                obj['original_sprite_visible'] = False
                # Independently recover occupied pixels from the composited RGB frame.
                # Render the same commands with this subject removed as background.
                from copy import copy
                from PIL import ImageChops
                from app.action_end_state import mask_components
                background = copy(image)
                background.commands = [c for c in image.commands if not (
                    c[0] == 'paste' and any(c[1] is tile for _,tile,_,_ in split_tiles[obj['id']]))]
                delta = ImageChops.difference(image.render(), background.render())
                channels = delta.split()
                occupancy = ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
                obj['frame_component_bboxes'] = mask_components(occupancy, [0,0,*size])
                from app.action_end_state import area, intersection
                base_area = split_base_area(obj, rows, metrics, index)
                painted = [b for b in obj['frame_component_bboxes'] if area(b) >= base_area*.25]
                if len(painted) == len(children):
                    for child in children:
                        child['bbox'] = max(painted, key=lambda box: intersection(box, child['bbox']))
                    obj['split_gap_px'] = min(gap(a['bbox'],b['bbox']) for i,a in enumerate(children) for b in children[i+1:])
        from app.layout_validation import check_layout, overlap_permissions
        objects = [child for obj in metrics['objects'] for child in obj.get('split_children', [obj])]
        metrics['overlap_permissions'] = overlap_permissions(
            raw if overlap_visual is None else overlap_visual, objects,
            t/max(1, duration_ms) if overlap_fraction is None else overlap_fraction,
            duration_ms, scene=index, aspect=aspect)
        hits = check_layout(objects, scene=index, aspect=aspect,
                            overlap_permissions=metrics['overlap_permissions'], semantic_context=True)
        for hit in hits:
            hit['measured'].update(frame_ms=t, sentence=active_sentence, attempts=metrics['healing'])
        metrics['layout_violations'] = hits
        from app.geometry_healing import planning
        if hits and not planning.get():
            from app.enforcement import record
            record(hits, 'layout')
        from app.geometry_healing import planning
        from app.enforcement import partition
        hard_hits = partition(hits)['blocking'] if not planning.get() else []
        if hard_hits:
            hits = hard_hits
            error = SceneRenderError(index, 'scene', 'layout', str(hits))
            error.metrics = dict(metrics, violations=hits)
            raise error
        for row in rows:
            if row['action'] == 'highlight':
                from PIL import ImageStat
                obj = next(o for o in metrics['objects'] if o['id'] == row['subject'])
                raster = image.render() if hasattr(image, 'render') else image
                x,y,w,h = obj['bbox']
                crop = raster.convert('RGB').crop((x,y,x+w,y+h))
                mask = obj['pixel_mask'].resize(crop.size)
                obj['material_rgb'] = obj['fill_rgb'] = ImageStat.Stat(crop, mask).mean
        metrics['render_actions'] = [dict(r) for r in rows]
        # A dissolve belongs visibly inside its destination. Reorder only its
        # sprite command after the vessel; retain the solved layout and q driver.
        for row in rows:
            if row['action'] != 'dissolve' or not hasattr(image, 'commands'): continue
            obj = required_first(((o for o in metrics['objects'] if o['id'] == row['subject'])), path='worker/worker/scenekit_renderer.py:462')
            box = tuple(obj['bbox'])
            commands = [c for c in image.commands if c[0] == 'paste'
                        and tuple(c[2]) == box[:2] and c[1].size == box[2:]]
            for command in commands:
                image.commands.remove(command)
                image.commands.append(command)
        metrics['action_targets'] = [dict(sentence=r['sentence'], subject=r['subject'], target=r['target'])
                                     for r in action_rows] if raw.get('beats') or intents else []
        from app.semantic_bands import resolve
        for obj in metrics['objects']:
            obj['semantic_band'] = resolve(declarations.get(obj.get('id'), obj), raw)
            obj.get('layout_trace', {})['semantic_band'] = obj['semantic_band']
        from worker.size_semantics import apply as apply_sizes
        apply_sizes(image, metrics, raw["items"], index)
        from worker.occlusion_guard import protect
        protect(image, metrics, index, occlusion=not planning.get())
        from app.semantic_bands import validate
        band_hits = validate(metrics['objects'], raw['items'], raw, size, index)
        metrics.setdefault('craft', []).extend(band_hits)
        from app.enforcement import record
        record(band_hits, 'layout')
        return image, metrics
    visual=Visual.model_validate(timed)
    for i,it in enumerate(visual.items):
        if it.shape not in IMPLEMENTED:
            raise SceneRenderError(index,i+1,it.shape,'UNKNOWN_SHAPE 该形状尚未实现')
        if it.shape == 'stick' and it.role != 'decoration' and blocks([dict(code='SUBJECT_STICK',scene=index,object=it.id or str(i),measured=it.role,threshold='decoration only')], 'render_declaration'):
            raise SceneRenderError(index,i+1,it.shape,'SUBJECT_STICK')
    if visual.layout == 'ladder' and (not 3 <= len(visual.items) <= 5 or any(it.count != 1 for it in visual.items)):
        if blocks([dict(code='LADDER_STAGES',scene=index,object='scene',measured=[it.count for it in visual.items],threshold='3–5 single stages')], 'render_declaration'):
            raise SceneRenderError(index,'scene','ladder','LADDER_STAGES')
    from app.ledger_shapes import is_light_source
    if visual.expression:
        from worker.scene_composition import stage as compose_stage
        if not visual.background:
            visual.background = dict(horizon=True, rear='wall', support='ground', light='upper_left', contact_shadows=True)
        return observed(compose_stage(visual, size, index, t, duration_ms))
    if visual.spatial_frame == 'display':
        from worker.display_composition import stage as display_stage
        return observed(_identify(display_stage(visual, size, index, t),visual))
    if visual.layout == 'narration' or any(it.shape == 'timeline_axis' for it in visual.items):
        from worker.diagram_composition import stage as diagram_stage
        return observed(_identify(diagram_stage(visual, size, index, t),visual))
    if visual.spatial_frame and visual.background:
        from worker.scene_composition import stage as compose_stage
        return observed(compose_stage(visual, size, index, t, duration_ms))
    w,h=size; gy=round(h*.76)
    from worker.drawing_plan import DrawingPlan
    im=DrawingPlan(size,BG)
    items=[(i,it,shape_for(it)) for i,it in enumerate(visual.items)]
    # W7 light enters from the left; keep the Sun/Earth pair in that order.
    if {'sun','earth'} <= {kind for _,_,kind in items}:
        items.sort(key=lambda entry: {'sun':0,'earth':1}.get(entry[2],2))
    count=sum(min(it.count,8) for _,it,_ in items)
    cols=min(count,4 if w>h else 2); rows=math.ceil(count/cols)
    if visual.layout == 'ladder':cols=count;rows=1
    diameter=round(min(w*.80/cols,h*.46/rows)*.74)
    if visual.layout == "zoom":diameter=round(min(w,h)*.22)
    objects=[];metrics=[];j=0
    for i,it,shape in items:
        for replica in range(min(it.count,8)):
            try:
                sp,mask=sprite(shape,it.color,diameter,it.mood,it.state,polarity=it.polarity)
            except Exception as exc:
                raise SceneRenderError(index,i+1,shape,f'missing or invalid geometry/material: {type(exc).__name__}: {exc}') from exc
            row=j//cols; col=j%cols; j+=1
            cx=w*(.1+.8*(col+.5)/cols)
            ground=round(gy-(rows-1-row)*h*.46/rows)
            if visual.layout == "zoom":cx=w*.30;ground=round(h*.66)
            if visual.layout == 'ladder':ground=round(gy-col*h*.045)
            if abs(cx-w/2)<=8*w/1280:cx=w/2+16*w/1280
            if it.position is not None:
                cx = w*(.2 + .3*(it.position % 3))
                ground = round(h*(.35 + .19*(it.position//3)))
            x,y=round(cx-sp.width/2),ground-sp.height+1
            from worker.celestial import fit
            sp,x,y=fit(sp,x,y,size,shape)
            from worker.beat_animation import transform
            sp,x,y=transform(sp,x,y,it,size)
            from app.semantic_bands import place
            x,y=place(sp,x,y,it,visual,size)
            mask=sp.getchannel('A')
            ground=y+sp.height-1
            obj=sk.Object(f'item-{i+1}-{replica+1}',shape,(x,y,sp.width,sp.height),material=sk.Material(ImageColor.getrgb(COLORS[it.color])))
            objects.append((obj,sp,mask,ground,it))
    from worker.subject_geometry import violations as preflight
    planned=[dict(id=it.id or obj.name,name=obj.name,shape=obj.kind,role=it.role,bbox=obj.bbox,
                  sentence=active_sentence)
             for obj,sp,mask,ground,it in objects]
    errors=preflight(planned,size,index,frame_ms=t)
    if blocks(errors, 'frame'):raise SceneRenderError(index,'scene','geometry',str(errors))
    circles={obj.kind:(obj.bbox[0]+sp.width/2,obj.bbox[1]+sp.height/2,sp.width) for obj,sp,mask,g,it in objects if obj.kind in ('sun','earth')}
    ray_metrics=[]
    if 'sun' in circles and 'earth' in circles:
        ray_metrics=rays(ImageDraw.Draw(im),circles['sun'],circles['earth'])
    if (visual.relation not in ('none', 'count') or visual.layout == 'ladder') and not ray_metrics:
        draw=ImageDraw.Draw(im)
        for left,right in zip(objects,objects[1:]):
            a,b=left[0].bbox,right[0].bbox
            from worker.logic_w24 import bound_endpoints, draw_arrow
            start,end=bound_endpoints(a,b)
            if visual.relation=='equals':
                mx,my=(start[0]+end[0])/2,(start[1]+end[1])/2
                for offset in (-5,5):draw.line((mx-12,my+offset,mx+12,my+offset),fill=INK,width=STROKE['body'])
            else:
                draw_arrow(draw,start,end)
    for object_index,(obj,sp,mask,ground,it) in enumerate(objects):
        sp=sp.copy()
        x,y,ow,oh=obj.bbox
        from worker.size_semantics import furniture_allowed, NARRATION
        if furniture_allowed(NARRATION.get()):
            ImageDraw.Draw(im).line((x-12,ground,x+ow+12,ground),fill=INK,width=STROKE['decoration'])
            if obj.kind in NEW_SHAPES:
                # Opaque projection; no new translucent material.
                sb=shadow(size,obj,ground).getbbox()
                ImageDraw.Draw(im).ellipse(sb,fill=PALETTE['ground'])
            else:
                projected=shadow(size,obj,ground)
                im.paste(projected,(0,0),projected)
        gaze=None
        if (obj.kind!='earth' or obj.kind in NEW_SHAPES) and not (obj.kind=='awen' and (visual.poses or visual.camera_motion is not None)):im.paste(sp,(x,y),sp)
        if obj.kind=='earth' and obj.kind not in NEW_SHAPES:
            fitted=globe(im,(x+ow/2,y+oh/2,ow),-70+140*min(1,t/4000))
            obj=replace(obj,bbox=fitted)
            sp.info['lighting_declaration']=im.last_globe_declaration
        # Card text is composed with other labels after camera transforms.
        # Bottom-row mask is the support; never let contact paint outside geometry.
        support=[px for px in range(mask.width) if mask.getpixel((px,mask.height-1))]
        if support and furniture_allowed(NARRATION.get()):
            color=sp.getpixel((mask.width//2,max(0,mask.height//2)))[:3]
            if obj.kind in NEW_SHAPES:
                color=tuple(round(v*.94) for v in color)
                for px in support:im.putpixel((x+px,ground),color)
            else:
                for px in support:im.putpixel((x+px,ground),sk.contact_color(obj))
        # Object labels are composed after camera transforms in frame().
        shadow_box=shadow(size,obj,ground).getbbox()
        metrics.append(dict(id=it.id or str(int(obj.name.split("-")[1])-1),parent=it.parent,role=it.role,name=obj.name,shape=obj.kind,semantic_label=it.label,bbox=obj.bbox,pixel_mask=sp.getchannel('A'),lighting_declaration=sp.info.get('lighting_declaration'),gaze=gaze,ground=ground,white_rim_px=0,
                            ground_error_px=abs(y+oh-1-ground),
                            shadow_base_ratio=(shadow_box[2]-shadow_box[0])/sk.base_width(obj),base_width=sk.base_width(obj)))
    if visual.layout == 'zoom' and objects:
        obj,sp,mask,ground,it=objects[0]
        radius=round(min(w,h)*.19);cx=round(w*.73);cy=round(h*.33)
        # Magnify a real crop of the global object, preserving its details.
        crop=sp.crop((sp.width//3,0,sp.width, max(1,sp.height*2//3)))
        detail=crop.resize((radius*2,radius*2),Image.Resampling.NEAREST)
        circle=Image.new('L',detail.size);ImageDraw.Draw(circle).ellipse((0,0,radius*2-1,radius*2-1),fill=255)
        base=Image.new('RGB',detail.size,BG);base.paste(detail,(0,0),detail)
        im.paste(base,(cx-radius,cy-radius),circle)
        draw=ImageDraw.Draw(im);draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),outline=INK,width=STROKE['body'])
        draw.line((obj.bbox[0]+sp.width, obj.bbox[1]+sp.height//3,cx-radius,cy),fill=INK,width=STROKE['decoration'])
    return observed((im,dict(scene=index,objects=metrics,horizon=gy,planes=[],light_direction='upper_left',ray_gaps=ray_metrics,content_bottom=gy+diameter*.10)))


@lru_cache(maxsize=1)
def _stage_fonts():
    from worker.render import Fonts
    return Fonts()


def house_position(earth,a):
    cx,cy,d=earth;r=d/2;l=math.radians(a);u=.72*r*math.sin(l);v=.22*r*math.cos(l)
    return cx+u*math.cos(math.pi/12)-v*math.sin(math.pi/12),cy+u*math.sin(math.pi/12)+v*math.cos(math.pi/12)



def globe(im,e,a,sun=None):
    """Fit globe, axis and rotation arrow as a single complete celestial object."""
    from worker.celestial import fit
    cx,cy,diameter=e
    pad=math.ceil(diameter*.20)+24
    n=round(diameter)
    tile=Image.new('RGBA',(n+2*pad,n+2*pad))
    _globe(tile,(pad+n/2,pad+n/2,n),a)
    bounds=tile.getbbox()
    from worker.lighting_declaration import transform
    tile=tile.crop(bounds)
    tile.info['lighting_declaration']=transform(tile.info['lighting_declaration'],tile.size,offset=(-bounds[0],-bounds[1]))
    x,y=round(cx-n/2-pad+bounds[0]),round(cy-n/2-pad+bounds[1])
    tile,x,y=fit(tile,x,y,im.size,'earth')
    if sun is not None:
        from worker.logic_w24 import bound_endpoints
        sx,sy,sd=sun
        start,end=bound_endpoints((sx-sd/2,sy-sd/2,sd,sd),(x,y,*tile.size))
        ImageDraw.Draw(im).line((start,end),fill=PALETTE['accent'],width=STROKE['body'])
    im.paste(tile,(x,y),tile)
    im.last_globe_declaration=tile.info['lighting_declaration']
    im.last_globe_mask=tile.getchannel('A')
    return (x,y,*tile.size)


def _globe(im,e,a,sun=None):
    """Rotating land on a circular globe, one soft shade and a visible axis."""
    from worker.scenekit_shapes import soft_lighting
    cx,cy,diameter=e;n=round(diameter)
    tile=Image.new('RGBA',(n,n),design_rgb(PALETTE['primary'])+ (255,));dd=ImageDraw.Draw(tile)
    continents = [(-35,-.22,1),(45,.30,.8),(145,-.12,.65)] if sun is None else [(i*60-155, -.22 if i%2 else .26, .85) for i in range(6)]
    for lon,lat,scale in continents:
        angle=math.radians(lon+a)
        if math.cos(angle)<0:continue
        x=n*.5+math.sin(angle)*n*.36;y=n*(.5+lat)
        pts=[(-.12,-.08),(-.04,-.14),(.08,-.10),(.13,-.02),(.07,.05),(.04,.14),(-.04,.10),(-.08,.01)]
        dd.polygon([(x+u*n*scale*max(.25,math.cos(angle)),y+v*n*scale) for u,v in pts],fill=PALETTE['secondary'])
    mask=Image.new('L',(n,n));ImageDraw.Draw(mask).ellipse((0,0,n-1,n-1),fill=255)
    tile.putalpha(mask)
    tile=soft_lighting(tile,mask,arc=True)
    tile.info['lighting_declaration']['shape']='earth'
    ImageDraw.Draw(tile).ellipse((1,1,n-2,n-2),outline=INK,width=STROKE['body'])
    from worker.lighting_declaration import transform
    im.info['lighting_declaration']=transform(tile.info['lighting_declaration'],im.size,offset=(round(cx-n/2),round(cy-n/2)))
    im.paste(tile,(round(cx-n/2),round(cy-n/2)),tile)
    draw=ImageDraw.Draw(im)
    draw.line((cx-n*.16,cy-n*.56,cx+n*.16,cy+n*.56),fill=INK,width=STROKE['body'])
    turn_arrow(draw,e)



def turn_arrow(draw,e):
    cx,cy,d=e;r=d/2
    # 110-degree rim arrow, clockwise from the lit left toward the dark right.
    ar=r+9;pts=[(cx+ar*math.cos(math.radians(v)),cy+ar*math.sin(math.radians(v))) for v in range(205,316)]
    draw.line(pts,fill=INK,width=STROKE['body'])
    x,y=pts[-1];theta=math.radians(315);tx,ty=-math.sin(theta),math.cos(theta)
    draw.polygon([(x+tx*10+math.cos(theta)*3,y+ty*10+math.sin(theta)*3),(x-tx*12+math.cos(theta)*12,y-ty*12+math.sin(theta)*12),(x-tx*12-math.cos(theta)*3,y-ty*12-math.sin(theta)*3)],fill=INK)

# Preserve cache introspection used by renderer diagnostics.
_solved_layout.cache_clear = _cached_solved_layout.cache_clear
_solved_layout.cache_info = _cached_solved_layout.cache_info
_solved_scene.cache_clear = _cached_solved_scene.cache_clear
_solved_scene.cache_info = _cached_solved_scene.cache_info
