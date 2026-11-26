"""Bounded layout repair using W123's shared three-adjustment scene journal."""
from copy import deepcopy
from app.aspects import canvas_aspect
from app.canvas_bounds import normalize_bbox
from contextvars import ContextVar

planning = ContextVar('geometry_planning', default=False)


def clipping(box, size):
    x,y,w,h = box
    W,H = size
    visible = max(0,min(x+w,W)-max(x,0))*max(0,min(y+h,H)-max(y,0))
    return dict(bbox=list(box), canvas=list(size), aspect=canvas_aspect(size), visible_fraction=visible/(w*h) if w*h else 0,
                overflow=dict(left=max(0,-x),top=max(0,-y),right=max(0,x+w-W),bottom=max(0,y+h-H)))


def normalize_sprite(sp, x, y, size, shape=None):
    """Fit actual pixels before painting, including animation output."""
    from PIL import Image
    from worker.occlusion_guard import fit_box
    # Keep the existing worker area guard separate from canvas containment.
    nx, ny, w, h = normalize_bbox(fit_box((x, y, *sp.size), size, raster=False), size)
    import math
    dims = (max(1, math.floor(w)), max(1, math.floor(h)))
    if dims != sp.size:
        sp = sp.resize(dims, Image.Resampling.BICUBIC)
    return sp, max(0, min(round(nx), size[0]-sp.width)), max(0, min(round(ny), size[1]-sp.height))


def heal(objects, size, scene, *, attempts=None, sentence=1, frame_ms=0):
    from app.layout_validation import check_layout
    from app.enforcement import fail, visual_gate
    result=deepcopy(objects)
    attempts=[] if attempts is None else attempts
    W,H=size
    margin=round(min(size)*.04)
    for obj in result:
        if obj.get('shape') == 'ground' or obj.get('visible') is False:
            continue
        c=clipping(obj['bbox'],size)
        if not any(c['overflow'].values()):continue
        before=deepcopy(result)
        x,y,w,h=obj['bbox']
        from worker.occlusion_guard import fit_box
        obj['bbox'] = normalize_bbox(fit_box(obj['bbox'], size, raster=False), size)
        # Boundary normalization never consumes or depends on overlap/action retries.
        attempts.append(dict(code='SUBJECT_CLIPPED', scene=scene, canvas=list(size),
            aspect=canvas_aspect(size), strategy='normalize_canvas', success=True,
            original_parameters=before, corrected_parameters=deepcopy(result),
            reason='translate into canvas; shrink only oversized objects', frame_ms=frame_ms))
    product = visual_gate() == 'product'
    # Repair severe pairs before compiling actions, so action endpoints use the new anchors.
    for hit in check_layout(result,scene=scene,aspect=canvas_aspect(size)):
        if hit['code'] not in ({'LAYOUT_IDENTICAL_POSITION','OVERLAP_SEVERE','OVERLAP_NOTED'} if product else {'LAYOUT_IDENTICAL_POSITION','OVERLAP_SEVERE'}):continue
        if not product and sum(a.get('strategy') != 'normalize_canvas' for a in attempts)>=3:break
        before=deepcopy(result)
        a,b=[next(o for o in result if o['id']==key) for key in hit['measured']['ids']]
        x,y,w,h=a['bbox'];u,v,s,t=b['bbox']
        if product and (x+w < u or u+s < x or y+h < v or v+t < y):
            continue
        success=False
        from app.visual_thresholds import GAP
        gap = max(8, margin, GAP) if product else margin
        for nx,ny in ((x+w+gap,v),(x-s-gap,v),(u,y+h+gap),(u,y-t-gap)):
            if margin<=nx<=W-margin-s and margin<=ny<=H-margin-t:
                if product:
                    import math
                    occupied = False
                    for other in result:
                        if other is b or other.get('shape') == 'ground' or other.get('visible') is False:
                            continue
                        ox,oy,ow,oh = other['bbox']
                        distance = math.hypot(max(nx-ox-ow,ox-nx-s,0),max(ny-oy-oh,oy-ny-t,0))
                        if distance < gap:
                            occupied = True
                            break
                    if occupied:
                        continue
                b['bbox']=[nx,ny,s,t];success=True;break
        attempts.append(dict(code='SUBJECT_SPACING' if hit['code']=='OVERLAP_NOTED' else hit['code'],scene=scene,canvas=list(size), aspect=canvas_aspect(size),adjustment=len(attempts)+1,
            strategy='separate_pair',success=success,original_parameters=before,
            corrected_parameters=deepcopy(result),reason='reflow with safe gap' if success else 'no safe adjacent slot',frame_ms=frame_ms))
    hits=[]
    for obj in result:
        if obj.get('shape')=='ground' or obj.get('visible') is False:continue
        c=clipping(obj['bbox'],size)
        if c['visible_fraction']<.6:
            # 只有「教学主体」被裁到看不见才算不可出片；其余（粒子、传播、装饰）记为 craft，
            # 按可见部分照常绘制，不阻断出片。
            role = obj.get('teaching_role') or obj.get('role')
            if role == 'subject':
                hits.append(fail('SUBJECT_CLIPPED',scene=scene,sentence=sentence,object_id=obj['id'],
                    check='visible_area',actual=c['visible_fraction'],threshold=.6,
                    basis='visible bbox intersection / bbox area < 60% after bounded repair',
                    frame_ms=frame_ms,attempts=deepcopy(attempts),**c))
            else:
                hits.append(dict(code='SUBJECT_CLIPPED', tier='craft', original_tier='hard',
                    scene=scene, sentence=sentence, object=obj['id'], role=role, aspect=canvas_aspect(size),
                    measured=dict(c, threshold=.6, check='visible_area'), attempts=deepcopy(attempts),
                    reason='非主体对象部分出画，按可见部分绘制'))
    for hit in check_layout(result,scene=scene,aspect=canvas_aspect(size)):
        if hit['code'] in {'LAYOUT_IDENTICAL_POSITION','OVERLAP_SEVERE'}:
            hit['measured'].update(attempts=deepcopy(attempts),frame_ms=frame_ms,sentence=sentence)
            hits.append(hit)
    return result,attempts,hits
