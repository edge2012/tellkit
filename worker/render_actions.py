from worker.process_evidence import run as run_process
"""Renderer capabilities and evidence from painted action endpoints (W104)."""
from app.response_assembly import required_first
from contextlib import contextmanager
from contextvars import ContextVar
import json
from PIL import ImageChops, ImageStat

from app.action_vocabulary import SUPPORTED, validate_capability
_variant = ContextVar('dissolve_variant', default='opacity')


from worker.errors import PipelineFailure


class RenderActionError(ValueError, PipelineFailure):
    def __init__(self, code, **detail):
        self.code = code
        self.detail = detail
        self.breakdown = detail
        self.diagnostics = detail.get('findings') or [dict(code=code, measured=detail)]
        ValueError.__init__(self, f'{code}: {json.dumps(detail, ensure_ascii=False)}')


def reject(code, **detail):
    from app.enforcement import is_hard, record
    if is_hard(dict(code=code, measured=detail)):
        raise RenderActionError(code, **detail)
    declaration = detail.get('declaration', {})
    record([dict(code=code, tier='hard', scene=detail.get('scene', declaration.get('scene', 0)),
        sentence=declaration.get('sentence'), measured=detail)], 'render_action')


def require_supported(action, renderer='scenekit', count=None):
    if action == 'split' and count is not None:
        try:
            validate_capability(action, count)
        except ValueError as exc:
            reject('ACTION_NOT_SUPPORTED', action=action, count=count, supported=SUPPORTED, hint=str(exc))
    if action not in SUPPORTED or renderer != 'scenekit':
        statuses = SUPPORTED if renderer == 'scenekit' else dict.fromkeys(SUPPORTED, 'not implemented in '+renderer)
        reject('ACTION_NOT_SUPPORTED', action=action, renderer=renderer, supported=statuses)


@contextmanager
def dissolve_variant(variant):
    if variant not in ('opacity', 'scale', 'color', 'split'):
        reject('RENDER_UNSUPPORTED_ACTION', action='dissolve', variant=variant, supported=SUPPORTED)
    token = _variant.set(variant)
    try:
        yield
    finally:
        _variant.reset(token)


def pixel_change(a, b):
    delta = ImageChops.difference(a.convert('RGB'), b.convert('RGB'))
    r,g,b = delta.split()
    hist = ImageChops.lighter(ImageChops.lighter(r,g),b).histogram()
    return dict(changed_pixel_fraction=sum(hist[9:])/(delta.width*delta.height),
                mean_rgb_difference=sum(ImageStat.Stat(delta).mean)/(3*255))


def verify(declaration, samples):
    """Samples contain actual rasterized RGB and sprite masks, never keyframe values."""
    from app.action_end_state import mask_components, predicate
    action = declaration['action']; require_supported(action)
    if declaration.get('relaxed_noop'):
        reject('RENDER_ACTION_NOT_APPLIED', declaration=declaration, reason='unresolvable geometry rendered stationary')
        return dict(declaration=declaration, measured={}, difference={}, passed=False)
    subject = declaration['subject']
    observations = []
    for im, metrics in samples:
        obj = required_first(((o for o in metrics['objects'] if o['id'] == subject)), path='worker/worker/render_actions.py:58')
        mask = obj['pixel_mask']
        observations.append(dict(bbox=list(obj['bbox']), rests_on=obj.get('rests_on'), opacity=mask.getextrema()[1]/255,
            component_bboxes=(obj.get('frame_component_bboxes') if action == 'split' and obj.get('frame_component_bboxes') is not None
                              else mask_components(mask,obj['bbox'])), fill_rgb=obj.get('material_rgb'),
            children=obj.get('split_children', []), gap_px=obj.get('split_gap_px'),
            frame_component_bboxes=obj.get('frame_component_bboxes'),
            original_sprite_visible=obj.get('original_sprite_visible')))
    if action == 'split':
        from app.action_end_state import area
        minimum_area = area(declaration['start_bbox'])*.25
        for obs in observations:
            # Only components meeting the specified 25% area can be split pieces.
            obs['component_bboxes'] = [box for box in obs['component_bboxes'] if area(box) >= minimum_area]
    a,b = observations[0],observations[-1]
    pixels = pixel_change(samples[0][0], samples[-1][0])
    # Attribute visible change to the subject's occupied region. Observer gaze,
    # shadows elsewhere, captions and other objects cannot satisfy the contract.
    boxes=[o['bbox'] for o in observations]
    import math
    region=(max(0,math.floor(min(b[0] for b in boxes))),max(0,math.floor(min(b[1] for b in boxes))),
            min(samples[0][0].width,math.ceil(max(b[0]+b[2] for b in boxes))),
            min(samples[0][0].height,math.ceil(max(b[1]+b[3] for b in boxes))))
    subject_pixels=pixel_change(samples[0][0].crop(region),samples[-1][0].crop(region))
    fraction=(region[2]-region[0])*(region[3]-region[1])/(samples[0][0].width*samples[0][0].height)
    subject_pixels={k:v*fraction for k,v in subject_pixels.items()}
    passed = subject_pixels['changed_pixel_fraction'] >= .0001 and subject_pixels['mean_rgb_difference'] >= .00001
    variant = declaration.get('variant', action)
    measured = dict(observations=observations, subject_pixels=subject_pixels, **pixels)
    difference = {}
    if action == 'dissolve':
        if variant == 'opacity':
            values = [o['opacity'] for o in observations]
            passed &= abs(values[0]-declaration['from']) <= 1/255 and values[-1] <= .15 and abs(values[-1]-declaration['to']) <= 1/255
            passed &= all(v >= w for v,w in zip(values,values[1:]))
            difference = dict(start=values[0]-declaration['from'], end=values[-1]-declaration['to'])
        elif variant == 'scale':
            values = [max(o['bbox'][2:])/max(a['bbox'][2:]) for o in observations]
            passed &= values[-1] <= .4 and abs(values[-1]-declaration['to']) <= 1/max(a['bbox'][2:]) and all(v >= w for v,w in zip(values,values[1:]))
            difference = dict(start=values[0]-1, end=values[-1]-declaration['to'])
        elif variant == 'split':
            parts=b['component_bboxes']
            ratios=[max(p[2:])/max(a['bbox'][2:]) for p in parts]
            passed &= len(parts)>=3 and all(v <= .3 for v in ratios)
            difference=dict(count=len(parts)-declaration['to'], max_size_ratio=max(ratios,default=1)-.3)
        else:
            # RGB Euclidean distance, normalized by the RGB cube diagonal.
            color=declaration['target_rgb']
            def distance(o):
                return sum((u-v)**2 for u,v in zip(o['fill_rgb'] or color,color))**.5/(255*3**.5)
            values=[distance(o) for o in observations]
            passed &= values[0]>=.3 and values[-1]<=.1
            difference=dict(start=values[0]-.3,end=values[-1]-.1)
        measured['values'] = values if variant != 'split' else ratios
    elif action == 'highlight':
        measured['highlight'] = subject_pixels
        difference = dict(pixel_fraction=subject_pixels['changed_pixel_fraction']-.0001)
    else:
        target=declaration.get('target')
        targets=[next((o for o in m['objects'] if o['id']==target),None) for _,m in (samples[0],samples[-1])]
        measured['predicate']=predicate(action,a,b,*targets, n=declaration.get('count',2),
            pieces=[dict(bbox=box) for box in b['component_bboxes']])
        passed &= measured['predicate']['passed']
        difference=dict(pixel_fraction=pixels['changed_pixel_fraction']-.0001)
    if action == 'split':
        from app.action_end_state import gap
        # The manifest children must agree with independently measured raster components.
        # At q=0 adjoining crop sprites intentionally form one component.
        for obs in observations[1:]:
            actual = sorted(obs['component_bboxes'])
            declared = sorted(child['bbox'] for child in obs['children'])
            if (len(actual) != len(declared) or
                    any(abs(x-y) > 1 for a,b in zip(actual,declared) for x,y in zip(a,b))):
                if passed or obs.get('frame_component_bboxes') is not None:
                    reject('MANIFEST_FRAME_MISMATCH', action=action, declaration=declaration,
                                            declared=declared, actual=actual)
                break
            actual_gap = min((gap(a,b) for i,a in enumerate(actual) for b in actual[i+1:]),default=0)
            if obs['gap_px'] is None or abs(actual_gap-obs['gap_px']) > 1:
                reject('MANIFEST_FRAME_MISMATCH', action=action, declaration=declaration,
                                        declared_gap=obs['gap_px'], actual_gap=actual_gap)
        gaps = [obs['gap_px'] for obs in observations]
        passed &= all(v is not None for v in gaps) and all(a <= b for a,b in zip(gaps,gaps[1:]))
        passed &= all(obs['original_sprite_visible'] is False for obs in observations)
        measured['split_frames'] = [observations[i] for i in (0,len(observations)//2,len(observations)-1)]
    difference.update(changed_pixel_fraction=subject_pixels['changed_pixel_fraction']-.0001,
                      mean_rgb_difference=subject_pixels['mean_rgb_difference']-.00001)
    if action == 'split' and passed:
        # Lossless stage witnesses allow the encoded artifact to be checked against
        # the manifest, including a moving but unsplit/stretched replacement.
        import base64
        from io import BytesIO
        measured['frame_witnesses'] = []
        for i in (0,len(samples)//2,len(samples)-1):
            buffer = BytesIO()
            samples[i][0].crop(region).convert('RGB').save(buffer, format='PNG')
            measured['frame_witnesses'].append(dict(at=i/(len(samples)-1), region=list(region),
                png=base64.b64encode(buffer.getvalue()).decode('ascii')))
    result=dict(declaration=declaration, measured=measured, difference=difference, passed=bool(passed))
    from app.action_start_state import endpoint_findings
    state_hits, counts = endpoint_findings(declaration, samples[0][1], samples[-1][1], samples[0][0].size)
    measured['component_counts'] = counts
    from app.enforcement import partition, record
    record(state_hits, 'render')
    hard = partition(state_hits)['blocking']
    if hard:
        reject(hard[0]['code'], findings=state_hits, **counts)
    if not passed:
        reject('RENDER_ACTION_NOT_APPLIED', action=action, variant=variant, **result)
    return result


def audit_scene(scene, size, *, validate_start=True):
    from worker.scenekit_renderer import _stage
    from worker.ambient import clock
    from app.action_geometry import split_directions
    from app.expression_contract import visual_payload
    visual=split_directions(visual_payload(scene), scene.get('narration', '')); duration=scene['duration_ms']; results=[]
    for i,beat in enumerate(visual.get('beats', [])):
        action=beat.get('change')
        if action is None: continue
        require_supported(action)
        from app.sentence_beats import animation_window
        lo, hi = animation_window(visual, beat, i, duration)
        start=lo+.2*(hi-lo)
        end=lo+.8*(hi-lo)
        samples=[]
        with clock(None):
            for q in (0,.25,.5,.75,1):
                image,metrics=_stage(json.dumps(visual),size,scene['index'],start+(end-start)*q,duration)
                samples.append((image.render() if hasattr(image,'render') else image,metrics))
        from app.action_start_state import split_start, outcome_items
        from app.enforcement import partition, record
        outcomes = outcome_items(visual, beat, samples[0][1], scene['index'])
        record(outcomes, 'render')
        start_findings = outcomes + split_start(visual, beat, samples[0][1], scene['index'])
        record(start_findings, 'render')
        start_hits = partition(start_findings)['blocking']
        if start_hits and validate_start:
            reject(start_hits[0]['code'], findings=start_hits)
        declaration=required_first(((r for r in samples[0][1]['render_actions'] if r['sentence']==beat['sentence'])), path='worker/worker/render_actions.py:176')
        declaration=dict(declaration, before_ms=start, after_ms=end)
        results.append(verify(declaration,samples))
    return results


def decode_frame(path, ms):
    import os
    import subprocess
    from io import BytesIO
    from PIL import Image
    data=run_process([os.getenv('FFMPEG','ffmpeg'),'-v','error','-nostdin','-threads','1','-ss',str(ms/1000),
        '-i',str(path),'-frames:v','1','-f','image2pipe','-vcodec','png','-threads','1','pipe:1'], code='RENDER_FAILED', paths=[path]).stdout
    return Image.open(BytesIO(data)).convert('RGB')


def verify_movie(receipt, path, offset_ms):
    """Decode the delivered artifact as well; a correct stage cannot certify a stale movie."""
    d=receipt['declaration']
    if d['action'] == 'split' and not d.get('relaxed_noop'):
        import base64
        from io import BytesIO
        from PIL import Image
        checks = []
        for witness in receipt['measured'].get('frame_witnesses', []):
            ms = d['before_ms']+(d['after_ms']-d['before_ms'])*witness['at']
            frame = decode_frame(path,offset_ms+ms)
            expected = Image.open(BytesIO(base64.b64decode(witness['png']))).convert('RGB')
            actual = frame.crop(witness['region']).convert('RGB')
            delta = ImageChops.difference(expected,actual)
            # Codec noise is small and local; widespread changed geometry is not.
            hist = ImageChops.lighter(ImageChops.lighter(*delta.split()[:2]),delta.split()[2]).histogram()
            error = sum(hist[33:])/(delta.width*delta.height)
            checks.append(dict(ms=ms, differing_fraction=error))
            if error > .05:
                reject('MANIFEST_FRAME_MISMATCH', action='split', declaration=d,
                                        artifact=str(path), measured=checks)
        receipt['encoded_split_frames'] = checks
    images=[decode_frame(path,offset_ms+d[key]) for key in ('before_ms','after_ms')]
    measured=pixel_change(*images)
    receipt['encoded_pixels']=measured
    import math
    if d.get('relaxed_noop'):
        reject('RENDER_ACTION_NOT_APPLIED', declaration=d, measured=measured)
        return receipt
    boxes=[o['bbox'] for o in receipt['measured']['observations']]
    region=(max(0,math.floor(min(b[0] for b in boxes))),max(0,math.floor(min(b[1] for b in boxes))),
            min(images[0].width,math.ceil(max(b[0]+b[2] for b in boxes))),
            min(images[0].height,math.ceil(max(b[1]+b[3] for b in boxes))))
    subject=pixel_change(*(im.crop(region) for im in images))
    fraction=(region[2]-region[0])*(region[3]-region[1])/(images[0].width*images[0].height)
    subject={k:v*fraction for k,v in subject.items()}
    receipt['encoded_subject_pixels']=subject
    if subject['changed_pixel_fraction'] < .0001 or subject['mean_rgb_difference'] < .00001:
        reject('RENDER_ACTION_NOT_APPLIED',action=d['action'],variant=d.get('variant',d['action']),
            declaration=d,measured=subject,difference=dict(changed_pixel_fraction=subject['changed_pixel_fraction']-.0001),
            artifact=str(path))
    return receipt
