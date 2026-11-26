"""R1–R8 geometry checks; boxes include attached rays and axes."""
import math
from app import visual_thresholds as T


def violation(code, scene, obj, measured, threshold):
    assert code in T.CODES
    name = obj.get('name', obj.get('id', obj.get('shape', 'scene')))
    return dict(code=code, scene=scene, object=name, measured=measured, threshold=threshold,
                detail=f'scene={scene} object={name} measured={measured} threshold={threshold}')


def violations(objects, size, scene=1, *, frame_ms=0):
    objects=[o for o in objects if 'bbox' in o]
    w,h=size
    result=[]
    def add(code,o,value,limit):result.append(violation(code,scene,o,value,limit))
    seen={}
    lookup={str(o.get("id")):o for o in objects}
    for i,o in enumerate(objects):
        x,y,bw,bh=o['bbox'];shape=o['shape'];role=o.get('role','subject')
        if role in {'subject','character','result','tool'} and bw*bh>w*h*T.AREA+1e-6:
            add('SUBJECT_TOO_LARGE',o,bw*bh,w*h*T.AREA)
        if shape in {'sun','moon','earth','planet'} and bh>h*T.CELESTIAL_HEIGHT+1e-6:
            add('SUBJECT_TOO_LARGE',o,bh,h*T.CELESTIAL_HEIGHT)
        from app.geometry_healing import clipping, planning
        # clipping carries the actual canvas aspect into fail() and the audit.
        c = clipping(o['bbox'], size)
        if shape != 'ground' and c['visible_fraction'] < .6 and not planning.get():
            from app.enforcement import fail
            result.append(fail('SUBJECT_CLIPPED', scene=scene, sentence=o.get('sentence', 1),
                object_id=o.get('id', o.get('name')), check='visible_area',
                actual=c['visible_fraction'], threshold=.6,
                basis='visible bbox intersection / bbox area < 60%',
                frame_ms=o.get('frame_ms', frame_ms), attempts=o.get('healing', []), **c))
        if role=='subject' and bh<h*T.MIN_HEIGHT-1e-6:
            add('SUBJECT_TOO_SMALL',o,bh,h*T.MIN_HEIGHT)
        from app.video_contract import VIDEO_CHARACTERS_ENABLED
        if VIDEO_CHARACTERS_ENABLED and shape=='awen' and not h*T.CHARACTER[0]-1e-6<=bh<=h*T.CHARACTER[1]+1e-6:
            add('CHARACTER_SCALE',o,bh,tuple(h*v for v in T.CHARACTER))
        if o.get('parent') is None and role=='subject' and abs(x+bw/2-w/2)<=T.CENTER_BAND:
            add('SUBJECT_SYMMETRY',o,abs(x+bw/2-w/2),f'>{T.CENTER_BAND}px')
        if o.get('parent') is None and role!='decoration':
            identity = (shape, o.get('semantic_label')) if shape == 'diagram_box' else shape
            seen[identity]=seen.get(identity,0)+1
            if seen[identity]>T.DUPLICATES and shape!='rain':
                add('SUBJECT_DUPLICATE',o,seen[identity],T.DUPLICATES)
        if o.get('parent') is not None:
            parent=lookup.get(o['parent'],{})
            inner=parent.get('inner_rect')
            if inner is None:
                add('CONTAINER_OUT_OF_BOUNDS',o,'missing parent inner rectangle','required')
            else:
                ix,iy,iw,ih=inner
                excess=max(ix-x,iy-y,x+bw-ix-iw,y+bh-iy-ih,0)
                if excess>4+1e-6:add('CONTAINER_OUT_OF_BOUNDS',o,excess,4)
        for p in objects[:i]:
            if o.get('parent') is not None or p.get('parent') is not None:
                if o.get('parent') is not None and o.get('parent')==p.get('parent'):
                    px,py,pw,ph=p['bbox']
                    penetration=min(min(x+bw,px+pw)-max(x,px),min(y+bh,py+ph)-max(y,py))
                    if penetration>2+1e-6:add('CONTAINER_OVERLAP',o,{'peer':p.get('id'),'penetration_px':penetration},2)
                continue
            # R5 measures teaching objects; actors have their own presence/scale/clipping checks.
            if role in {'decoration', 'character'} or p.get('role') in {'decoration', 'character'}:continue
            if shape == 'awen' or p.get('shape') == 'awen':continue
            # A shared vessel is a single rendered object, not two overlapping boxes.
            if o.get('container') and o.get('container')==p.get('container'):continue
            px,py,pw,ph=p['bbox']
            gap=math.hypot(max(x-px-pw,px-x-bw,0),max(y-py-ph,py-y-bh,0))
            if gap<T.GAP-1e-6:add('SUBJECT_SPACING',o,gap,T.GAP)
    return result
