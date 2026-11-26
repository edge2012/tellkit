"""Compile declarative actions against solved pixel geometry, independently per canvas."""
from app.response_assembly import required_first
import math
from app.sentence_beats import validate_intent
from worker.errors import PipelineFailure
from app.action_vocabulary import SUPPORTED


class ActionGeometryError(ValueError, PipelineFailure):
    def __init__(self, row):
        self.row = row
        self.code = row['status']
        self.breakdown = row
        self.diagnostics = [dict(code=self.code, measured=row)]
        ValueError.__init__(self, f"{self.code}: {row}")


def compile_action(intent, objects, size, *, aspect=None, scene=None, sentence=None):
    from worker.render_actions import require_supported, _variant
    require_supported(intent.get('action'), count=intent.get('count'))
    objects = {o.get('id', o.get('object')): o for o in objects}
    value = validate_intent(intent, list(objects.values()))
    action, subject = value['action'], objects[value['subject_id']]
    a = list(subject['bbox']); x,y,w,h = a
    cx,cy = x+w/2,y+h/2
    threshold = max(16., .03*min(size))
    row = dict(scene=scene, sentence=sentence, aspect=aspect, action=action,
               subject=value['subject_id'], target=value.get('target_id'),
               start_bbox=a, end_bbox=a[:], displacement_px=0., threshold_px=threshold,
               status='pass', keyframes=[])
    def fail(code, **detail):
        row.update(status=code, **detail)
        raise ActionGeometryError(row)
    target = objects.get(value.get('target_id'))
    if target:
        tx,ty,tw,th = target['bbox']
        state = dict(bbox=target['bbox'], visible=target.get('visible', True), opacity=target.get('opacity', 1))
        if not state['visible'] or state['opacity'] <= 0 or tx < 0 or ty < 0 or tx+tw > size[0] or ty+th > size[1]:
            fail('ACTION_TARGET_UNREACHABLE', target_state=state)
    frames = [dict(at=0., bbox=a[:], opacity=1.)]
    end = a[:]
    if action in {'move_to','merge','pour','sink'}:
        ex,ey = tx+tw/2,ty+th/2
        if action == 'move_to':
            from app.visual_thresholds import GAP
            from app.action_end_state import gap
            margin = math.ceil(min(size)*.04)
            left, top, right, bottom = margin, margin, size[0]-margin, size[1]-margin
            peer = (subject.get('comparison') or {}).get('peer_id') == value['target_id']
            yy = ty+th-h if peer else ty+(th-h)/2
            yy = max(top, min(yy, bottom-h))
            xx = max(left, min(tx+(tw-w)/2, right-w))
            candidates = dict(right=[tx+tw+GAP, yy, w, h], left=[tx-GAP-w, yy, w, h],
                              up=[xx, ty-GAP-h, w, h], down=[xx, ty+th+GAP, w, h])
            available = dict(right=[max(0,right-tx-tw-GAP), bottom-top],
                             left=[max(0,tx-GAP-left), bottom-top],
                             up=[right-left,max(0,ty-GAP-top)],
                             down=[right-left,max(0,bottom-ty-th-GAP)])
            sides = {}
            for side, box in candidates.items():
                bx, by, bw, bh = box
                blockers = [identity for identity, obj in objects.items()
                            if identity not in {value['subject_id'], value['target_id']}
                            and obj.get('visible', True) and obj.get('opacity', 1) > 0
                            and gap(box, obj['bbox']) < GAP-1e-9]
                fits = bx >= left and by >= top and bx+bw <= right and by+bh <= bottom
                sides[side] = dict(available_size=available[side], candidate_bbox=box,
                                   fits_safe_area=fits, blocked_by=blockers)
            valid = [side for side in candidates if sides[side]['fits_safe_area'] and not sides[side]['blocked_by']]
            if peer:
                valid = [side for side in valid if side in {'left','right'} and yy+h == ty+th]
            if not valid:
                fail('ACTION_TARGET_NO_ROOM', placement='beside', source='engine_geometry',
                     overlap_allowed=False, required_size=[w,h], safe_bounds=[left,top,right,bottom], sides=sides)
            # Prefer the nearest feasible side, avoiding a journey through the target.
            side = min(valid, key=lambda side: math.hypot(candidates[side][0]-x, candidates[side][1]-y))
            bx, by, _, _ = candidates[side]
            ex, ey = bx+w/2, by+h/2
            row.update(placement='beside', side=side, gap_px=gap(candidates[side], target['bbox']),
                       overlap_allowed=False, allow_overlap=False, source='engine_geometry', sides=sides)
            if peer:
                row['endpoint_semantics'] = 'comparison_adjacent'
        else:
            row.update(placement='inside', side=None, gap_px=0., overlap_allowed=True,
                       allow_overlap=True, source='engine_geometry')
        if action in {'pour', 'sink'}:
            from app.action_end_state import intersection, area
            overlap = intersection(a, target['bbox']) / min(area(a), area(target['bbox']))
            row['overlap_fraction'] = overlap
            if overlap > .5:
                fail('ACTION_TARGET_UNREACHABLE', target_state=dict(bbox=target['bbox'],
                     overlap_fraction=overlap, reason=f'initial bbox overlap {overlap:.1%} exceeds 50%'))
            lift = max(th*.6, size[1]*.08)
            apex = ty-lift
            frames.extend([dict(at=1/3, bbox=[cx-w/2,apex-h/2,w,h], opacity=1.),
                           dict(at=2/3, bbox=[ex-w/2,apex-h/2,w,h], opacity=1.)])
            ey = ty+th*.6
        end = [ex-w/2,ey-h/2,w,h]
        row['displacement_px'] = math.hypot(ex-cx,ey-cy)
        if action == 'merge' and min(w,tw)*min(h,th)/(w*h) < .6:
            fail('ACTION_TARGET_UNREACHABLE', target_state=dict(bbox=target['bbox'], reason='overlap below 60%'))
    elif action == 'split':
        n = value['count']; row['count'] = n; distance = .06*min(size)
        # Cut the longest dimension so neither fragment retains the full long edge.
        axis = 0 if w >= h else 1
        starts = [[x+w*i/n,y,w/n,h] if axis == 0 else [x,y+h*i/n,w,h/n]
                  for i in range(n)]
        direction = intent.get('direction') or ('horizontal' if axis == 0 else 'vertical')
        move_axis = 0 if direction == 'horizontal' else 1
        parts = [p[:] for p in starts]
        for i, p in enumerate(parts):
            offset = 2*i/(n-1)-1
            p[move_axis] += distance*offset
            if move_axis != axis:
                # Retain an opening along the cut while travelling left/right or up/down.
                p[axis] += 4*(n-1)*offset
                p[move_axis] += (w if move_axis == 0 else h)*offset/2
        row.update(direction=direction, child_ids=[f"{value['subject_id']}__split_{i+1}" for i in range(n)])
        # Preserve each crop's aspect ratio while respecting the explicit long-edge
        # cap (a square cut in half otherwise still has one original-length edge).
        for p in parts:
            scale = min(1., .75*max(w,h)/max(p[2:]))
            p[0] += p[2]*(1-scale)/2
            p[1] += p[3]*(1-scale)/2
            p[2] *= scale
            p[3] *= scale
        row['parts_start'] = starts
        left,top = min(p[0] for p in parts),min(p[1] for p in parts)
        end = [left,top,max(p[0]+p[2] for p in parts)-left,max(p[1]+p[3] for p in parts)-top]
        row['parts'] = parts
        row['displacement_px'] = distance
    elif action == 'dissolve':
        # A stationary dissolve starts inside its container. This is initial
        # semantic placement, shared by rendering and auditing, not a move.
        if not (tx <= cx <= tx+tw and ty < cy <= ty+th):
            a = [tx+tw/2-w/2, ty+th*.6-h/2, w, h]
            row['layout_start_bbox'] = row['start_bbox']
            row['start_bbox'] = a
            frames[0]['bbox'] = a[:]
            end = a[:]
        frames[0]['opacity'] = subject.get('opacity', 1.)
        row['threshold_px'] = 0.
    if action in {'move_to','pour','sink','split','merge'} and row['displacement_px'] < threshold-1e-9:
        row['end_bbox'] = end
        fail('ACTION_TOO_SHORT')
    if action == 'scale':
        factor = SUPPORTED['scale']['factor']
        end = [x-w*(factor-1)/2, y-h*(factor-1)/2, w*factor, h*factor]
    if action == 'appear': frames[0]['opacity'] = 0.
    frames.append(dict(at=1., bbox=end, opacity=0. if action in {'disappear','dissolve'} else 1.))
    if action == 'appear' and intent.get('start_opacity') == 0:
        frames[0]['opacity'] = 0.
    if action == 'disappear' and intent.get('end_opacity') == 0:
        frames[-1]['opacity'] = 0.
    if action == 'dissolve':
        variant = _variant.get()
        row.update(variant=variant, **{'from': 1., 'to': 0.})
        if variant == 'scale':
            row['to'] = .25
            end = [a[0]+a[2]*.375,a[1]+a[3]*.375,a[2]*.25,a[3]*.25]
            frames[-1].update(bbox=end, opacity=1.)
        elif variant == 'split':
            row.update(to=4, fragment_ratio=.25)
            frames[-1]['opacity'] = 1.
        elif variant == 'color':
            rgb = target.get('material_rgb') or target.get('fill_rgb')
            source_rgb = subject.get('material_rgb') or subject.get('fill_rgb')
            if rgb is None or source_rgb is None:
                from worker.render_actions import RenderActionError
                raise RenderActionError('RENDER_UNSUPPORTED_ACTION',action=action,variant=variant,
                                        reason='renderer path has no measured material color',supported=SUPPORTED)
            row.update(to=0., target_rgb=rgb)
            row['from'] = sum((u-v)**2 for u,v in zip(source_rgb,rgb))**.5/(255*3**.5)
            frames[-1]['opacity'] = 1.
        from app.action_end_state import predicate
        row['measured'] = predicate(action, dict(bbox=a, opacity=frames[0]['opacity']),
            dict(bbox=end, opacity=frames[-1]['opacity']), target, target)
        if variant == 'opacity' and not row['measured']['passed']:
            fail('ACTION_CHANGE_TOO_SMALL')
    for f in frames:
        bx,by,bw,bh = f['bbox']
        if bx < 0 or by < 0 or bx+bw > size[0] or by+bh > size[1]:
            fail('ACTION_TARGET_UNREACHABLE', target_state=dict(bbox=target['bbox'] if target else None, reason='action path leaves canvas'))
    if action == 'split':
        for frame, boxes in zip(frames, (row['parts_start'], row['parts'])):
            frame['children'] = [dict(id=identity, bbox=box) for identity,box in zip(row['child_ids'],boxes)]
    row.update(end_bbox=end, keyframes=frames)
    return row


HEALABLE = {'ACTION_TARGET_UNREACHABLE', 'ACTION_TARGET_NO_ROOM', 'ACTION_TARGET_NOT_VISIBLE'}


def _compile_scene(visual, initial, size, scene):
    from copy import deepcopy
    state = deepcopy(initial)
    rows = []
    for beat in visual.get('beats', []):
        if beat.get('change') is None:
            continue
        row = compile_action(beat['animation'], state, size,
            aspect='16x9' if size[0] >= size[1] else '9x16', scene=scene, sentence=beat['sentence'])
        rows.append(row)
        obj = required_first((o for o in state if o['id'] == row['subject']), path='action_geometry.scene')
        obj.update(bbox=row['end_bbox'], opacity=row['keyframes'][-1]['opacity'])
    return rows


def compile_render_action(intent, objects, size, *, scene=None, sentence=None):
    """Frame-only fallback keeps the subject visible when semantic motion fails."""
    try:
        return compile_action(intent, objects, size, scene=scene, sentence=sentence)
    except ValueError as exc:
        from app.enforcement import HARD_ALLOWLIST, record
        if not isinstance(exc, ActionGeometryError):
            subject = next((o for o in objects if o.get('id', o.get('object')) == intent.get('subject_id')), None)
            if subject is None:
                raise
            exc = ActionGeometryError(dict(status=getattr(exc, 'code', getattr(exc, 'type', 'CONTENT_CELL_INVALID')),
                subject=intent.get('subject_id'), start_bbox=list(subject['bbox']), action=intent.get('action'),
                reason=str(exc), scene=scene, sentence=sentence))
        if exc.code in HARD_ALLOWLIST:
            raise
        record([dict(code=exc.code, scene=scene, sentence=sentence,
                     object=exc.row.get('subject'), reason=str(exc), measured=exc.row)], 'render_action')
        box = list(exc.row['start_bbox'])
        return dict(exc.row, end_bbox=box, relaxed_noop=True, keyframes=[
            dict(at=0., bbox=box, opacity=1.), dict(at=1., bbox=box, opacity=1.)])


def solve_scene(visual, objects, size, scene, *, budget=None):
    try:
        return _solve_scene(visual, objects, size, scene, budget=budget)
    except ValueError as exc:
        from app.enforcement import visual_relaxed as is_soft, record, HARD_ALLOWLIST
        if not isinstance(exc, ActionGeometryError):
            exc = ActionGeometryError(dict(status=getattr(exc, 'code', getattr(exc, 'type', 'CONTENT_CELL_INVALID')),
                reason=str(exc), scene=scene))
        if not is_soft() and exc.code in HARD_ALLOWLIST:
            raise
        record([dict(code=exc.code, tier='hard', scene=scene, sentence=exc.row.get('sentence'), measured=exc.row)], 'geometry')
        rows = []
        for beat in visual.get('beats', []):
            intent = beat.get('animation')
            if not intent:
                continue
            obj = next((o for o in objects if o.get('id') == intent['subject_id']), None)
            if obj is None:
                continue
            box = list(obj['bbox'])
            rows.append(dict(scene=scene, sentence=beat['sentence'], action=intent['action'],
                subject=intent['subject_id'], target=intent.get('target_id'), start_bbox=box,
                end_bbox=box, status=exc.code, relaxed_noop=True, keyframes=[
                    dict(at=0., bbox=box, opacity=1.), dict(at=1., bbox=box, opacity=1.)]))
        return objects, rows


def _solve_scene(visual, objects, size, scene, *, budget=None):
    """Transactional scene solve: at most three adjustments, then compile every beat again.

    Never changes visibility, narration, identities or action declarations. All
    attempts share a budget, including failures on later beats. Cached callers
    receive copies, so a failed attempt cannot corrupt another frame.
    """
    from copy import deepcopy
    original = deepcopy(objects)
    candidate = deepcopy(objects)
    attempts = [] if budget is None else budget
    from app.geometry_healing import heal
    candidate, _, layout_hits = heal(candidate, size, scene, attempts=attempts,
                                     sentence=next(iter(visual.get('beats') or []), {}).get('sentence', 1))
    from app.enforcement import blocks
    if layout_hits and blocks(layout_hits, 'geometry_healing'):
        hit=layout_hits[0]
        raise ActionGeometryError(dict(hit['measured'], status=hit['code']))
    starting_attempts = len(attempts)
    pending = None
    for iteration in range(4):
        try:
            rows = _compile_scene(visual, candidate, size, scene)
            if pending is not None:
                pending.update(success=True, reason='all scene actions compile')
            for row in rows:
                row['healing'] = deepcopy(attempts)
            return candidate, rows
        except ActionGeometryError as exc:
            if pending is not None:
                pending.update(success=False, reason=str(exc), failure=exc.code)
            if exc.code not in HEALABLE and len(attempts) == starting_attempts:
                raise
            if sum(a.get('strategy') != 'normalize_canvas' for a in attempts) >= 3:
                row = dict(exc.row, status='ACTION_UNRESOLVABLE', attempts=attempts,
                           original_objects=original, final_objects=deepcopy(candidate),
                           reason='three adjustments exhausted; no semantically valid geometry')
                raise ActionGeometryError(row) from exc
            before = deepcopy(candidate)
            W,H = size
            margin = math.ceil(min(size)*.04)
            subject = next(o for o in candidate if o['id'] == exc.row['subject'])
            target = next((o for o in candidate if o['id'] == exc.row.get('target')), None)
            if iteration == 0:
                strategy = 'translate_scene'
                # Include lift headroom and the split endpoint envelope.
                left = min(o['bbox'][0] for o in candidate)
                top = min(o['bbox'][1] for o in candidate)
                right = max(o['bbox'][0]+o['bbox'][2] for o in candidate)
                bottom = max(o['bbox'][1]+o['bbox'][3] for o in candidate)
                if target and exc.row['action'] in {'sink','pour'}:
                    top = min(top, target['bbox'][1]-max(target['bbox'][3]*.6,H*.08)-subject['bbox'][3]/2)
                if exc.row['action'] == 'split':
                    top -= .06*min(size); left -= .06*min(size)
                    right += .06*min(size); bottom += .06*min(size)
                dx = max(margin-left, min(0, W-margin-right))
                dy = max(margin-top, min(0, H-margin-bottom))
                for obj in candidate:
                    x,y,w,h = obj['bbox']; obj['bbox'] = [x+dx,y+dy,w,h]
            elif iteration == 1:
                strategy = 'scale_scene'
                # Preserve comparison proportions. An unrelated merge may instead
                # shrink its actor to fit the declared target's real extent.
                if target and exc.row['action'] == 'merge' and not subject.get('comparison'):
                    strategy = 'scale_subject'
                    x,y,w,h = subject['bbox']
                    factor = min(.75, target['bbox'][2]/w, target['bbox'][3]/h)
                    subject['bbox'] = [x+w*(1-factor)/2,y+h*(1-factor)/2,w*factor,h*factor]
                else:
                    for obj in candidate:
                        x,y,w,h = obj['bbox']
                        obj['bbox'] = [W/2+(x-W/2)*.75,H/2+(y-H/2)*.75,w*.75,h*.75]
            else:
                strategy = 'neighboring_space'
                # Reposition the acting object (or its target for move_to), not its action.
                moving = target if target and exc.row['action'] == 'move_to' else subject
                w,h = moving['bbox'][2:]
                from app.action_end_state import gap
                from app.visual_thresholds import GAP
                options = [[x,y,w,h] for y in (H*.35,H*.5,H*.65)
                           for x in (margin,W-w-margin,W/2-w/2)]
                legal = [box for box in options if box[0]>=margin and box[1]>=margin
                         and box[0]+w<=W-margin and box[1]+h<=H-margin
                         and all(gap(box,o['bbox']) >= GAP for o in candidate if o is not moving)]
                if legal:
                    moving['bbox'] = min(legal, key=lambda box: math.dist(box[:2],moving['bbox'][:2]))
            from app.geometry_healing import normalize_bbox
            for obj in candidate:
                if obj.get('shape') != 'ground' and obj.get('visible') is not False:
                    obj['bbox'] = normalize_bbox(obj['bbox'], size)
            pending = dict(code=exc.code, scene=scene, aspect=exc.row['aspect'],
                           adjustment=len(attempts)+1, strategy=strategy,
                           original_parameters=before, corrected_parameters=deepcopy(candidate),
                           success=False, reason='pending validation')
            attempts.append(pending)
    raise AssertionError('bounded solver')


def resolve_visual(visual, objects, size, scene):
    return solve_scene(visual, objects, size, scene)[1]


from app.storyboard_trace import traced

@traced('self_check.action_geometry')
def audit_geometry(board):
    """Audit the same healed starting layout and action sequence used for painting."""
    import json
    from worker.scenekit_renderer import _solved_scene, _solved_layout
    from worker.render_actions import _variant
    rows, hits = [], []
    for scene in board['scenes']:
        visual = split_directions(scene['visual'], scene.get('narration', ''))
        base = dict(visual); base.pop('beats', None)
        solutions = _solved_scene(json.dumps(visual, sort_keys=True), json.dumps(base, sort_keys=True),
                                 scene['index'], scene['duration_ms'], _solved_layout,
                                 _variant.get())
        for size, solution in solutions.items():
            if isinstance(solution, ActionGeometryError):
                exc = solution
                rows.append(exc.row)
                hits.append(dict(code=exc.code, tier='hard', scene=scene['index'], object=exc.row.get('subject', exc.row.get('object_id')),
                                 measured=exc.row, threshold=exc.row.get('threshold_px', exc.row.get('threshold')), detail=str(exc)))
            elif isinstance(solution, Exception):
                raise solution
            else:
                rows.extend(solution[1])
    return rows,hits


def split_directions(visual, narration):
    """Explicit sentence semantics override the aspect-independent fallback."""
    from copy import deepcopy
    from app.sentence_beats import sentences
    visual = deepcopy(visual)
    lines = sentences(narration)
    for beat in visual.get('beats', []):
        intent = beat.get('animation') or {}
        if intent.get('action') != 'split':
            continue
        if intent.get('direction') and any(i.get('repair_bboxes') for i in visual.get('items', []) if i.get('id') == intent.get('subject_id')):
            continue
        index = beat['sentence']-1
        text = lines[index] if 0 <= index < len(lines) else ''
        if '横切' in text:
            intent['direction'] = 'horizontal'
        elif '纵切' in text:
            intent['direction'] = 'vertical'
    return visual
