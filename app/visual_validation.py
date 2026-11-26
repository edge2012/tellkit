from app.aspects import delivery_aspects, delivery_sizes
"""One staged entry point for declarations, measured frames and final delivery."""
from app import visual_spec_w27c as C
from app.enforcement import partition, HARD_CODES, evidence
from app.visual_spec_w27b import violation

VETO_CODES = HARD_CODES


from app.storyboard_trace import traced

from app.self_check_budget import sync_session

@sync_session
@traced('self_check.visual_validation')
def check(stage, *, board=None, metrics=None, size=None, image=None, layouts=None, media=None, speech=None, partial=False, pixel_only=False):
    import time
    hits=[];missing=[];checks=[]
    def run(name, fn, *args, needed=True, reason='', **kwargs):
        if not needed:
            checks.append(dict(check=name, status='skipped', reason=reason, ms=0))
            return []
        start=time.perf_counter()
        try:
            from app.self_check_budget import review_errors
            if stage == 'storyboard':
                with review_errors('visual_validation', hits, scenes=len(board['scenes'])):
                    return fn(*args, **kwargs)
                return []
            return fn(*args, **kwargs)
        finally:checks.append(dict(check=name, status='ran', ms=round((time.perf_counter()-start)*1000,3)))
    if stage=='frame':
        from app.self_check_budget import scene_budget
        with scene_budget('visual_validation', metrics.get('scene', 1), hits) as allowed:
            if allowed:
                from worker.subject_geometry import violations
                from worker.composition_b5 import violations as grammar
                from app.visual_spec_w27b import geometry_violations
                hits+=run('subject_geometry',violations,metrics.get('objects',[]),size,metrics.get('scene',1),frame_ms=metrics.get('frame_ms',0))
                hits+=run('composition',grammar,metrics,size,expected_light=metrics.get('expected_light',metrics.get('light_direction','upper_left')))
                from app.visual_spec_w27b import shape_violations, comparison_violations, label_violations, arrow_violations, SILHOUETTES
                from app.visual_spec_w27b import comparison_required
                objects=metrics.get('objects',[]); scene=metrics.get('scene',1)
                hits+=run('shape',shape_violations,objects,scene)
                compare=comparison_required(metrics.get('layout'), metrics.get('narration',''))
                hits+=run('comparison',comparison_violations,objects,scene,layout=metrics.get('layout'),narration=metrics.get('narration',''),size=size,peers=metrics.get('comparison_peers'),needed=compare,reason='no compare layout, intent or group')
                hits+=run('labels',label_violations,metrics.get('labels',[]),objects+metrics.get('rear_objects',[]),scene,needed=bool(metrics.get('labels')),reason='no labels')
                hits+=run('arrows',arrow_violations,metrics.get('arrows',[]),objects,scene,needed=bool(metrics.get('arrows')),reason='no arrows')
                if partial:
                    # Old archives do not contain these measurements. Missing is not a violation.
                    unavailable={'HORIZON_MISSING','DEPTH_SCALE','FLOATING_SUBJECT','LIGHT_DIRECTION','LABEL_FONT_MIXED'}
                    missing.extend(sorted(unavailable))
                    hits=[h for h in hits if h['code'] not in unavailable]
                if pixel_only:
                    hits=[]
                if not pixel_only and any('glyph_size' in label for label in metrics.get('labels',[])):
                    from worker.label_glyphs import violations as glyphs
                    from worker.render import Fonts
                    hits+=run('glyphs',glyphs,metrics['labels'],Fonts(),metrics.get('scene',1))
                if image is not None:
                    from worker.material_pixels import violations as material
                    from worker.silhouette_pixels import violations as silhouette
                    from worker.shoe_pixels import violations as shoes
                    # One RGB buffer is shared by all pixel checks for this frame.
                    image=image if image.mode=='RGB' else image.convert('RGB')
                    hits+=run('material',material,image,objects,scene,metrics.get('light_direction','upper_left'),needed=bool(objects),reason='no objects')
                    hits+=run('silhouette',silhouette,image,objects,scene,needed=any(o.get('shape') in SILHOUETTES for o in objects),reason='no silhouette shapes')
                    shapes={o.get('shape') for o in objects}
                    hits+=run('shoes',shoes,image,objects,scene,needed={'shoe_left','shoe_right'}<=shapes,reason='no opposing shoe peers')
                else:missing.append('material/silhouette pixels')
    elif stage=='delivery':
        hits+=C.delivery(board,layouts or {},media or {},speech or [])
        for aspect in delivery_aspects():
            if aspect not in (media or {}):missing.append(f'{aspect}: media measurement')
            for s in board.get('scenes',[]):
                pages=(layouts or {}).get(aspect,{}).get(str(s['index']),(layouts or {}).get(aspect,{}).get(s['index'],[]))
                if not pages or any('ink_boxes' not in p for p in pages):missing.append(f'{aspect}: scene {s["index"]} subtitle ink boxes')
        if not speech:missing.append('speech timing')
    else:raise ValueError(stage)
    hits = [evidence(h) for h in hits]
    result = partition(hits)
    return dict(stage=stage,checks=checks,hits=hits,vetoes=result['blocking'],missing_evidence=missing,
                **result, status='FAIL' if result['blocking'] else 'INCOMPLETE' if missing else 'PASS')


