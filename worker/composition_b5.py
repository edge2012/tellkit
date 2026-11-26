"""B5 measured composition grammar. All boxes use x/y/width/height, in pixels."""
from worker.design_tokens import TYPE as DESIGN_TYPE, RADIUS as DESIGN_RADIUS
import math
from PIL import ImageDraw

from app.visual_thresholds import CODES
CODES = tuple(CODES)


def distance(a, b):
    x,y,w,h=a; px,py,pw,ph=b
    return math.hypot(max(x-px-pw,px-x-w,0),max(y-py-ph,py-y-h,0))


def overlaps(a,b):
    x,y,w,h=a; px,py,pw,ph=b
    return x < px+pw and px < x+w and y < py+ph and py < y+h


class LabelPlacements(list):
    def __init__(self):
        super().__init__()
        self.craft_notes=[]


def place_labels(im, objects, pending, rear, fonts, *, scene=0, title="", craft_notes=None, used_texts=None):
    from worker.visual import centered_text, paste_text
    from worker.label_selection import select_labels, text_key
    used_texts = used_texts if used_texts is not None else set()
    used_texts.add(text_key(title))
    # A list-compatible result keeps existing callers working and retains notes.
    from worker.overlays import caption_band_top
    labels=LabelPlacements()
    notes=labels.craft_notes if craft_notes is None else craft_notes
    labels.craft_notes=notes
    anchored = [(objects[owner] if isinstance(owner,int) and 0 <= owner < len(objects)
                 else dict(id=owner), text) for owner,text in pending]
    for obj,text in select_labels(objects, anchored, title, notes=notes, used_texts=used_texts):
        x,y,w,h=obj['bbox']
        bitmap=centered_text(fonts,text,DESIGN_TYPE['label'],max(w,im.width*.18))
        bw,bh=bitmap.size
        candidates=[(x+(w-bw)/2,y-bh-8),(x+(w-bw)/2,y+h+8),
                    (x+w+8,y+(h-bh)/2),(x-bw-8,y+(h-bh)/2)]
        obstacles=[o['bbox'] for o in objects+rear if o is not obj and o.get('id') != obj.get('parent') and not (o.get('container') and o.get('container')==obj.get('container'))]
        obstacles += [label['bbox'] for label in labels]
        for lx,ly in candidates:
            box=(round(lx),round(ly),bw,bh)
            if lx>=im.width*.05 and ly>=im.height*.05 and lx+bw<=im.width*.95 and ly+bh<=caption_band_top(im.size) and not any(overlaps(box,b) for b in obstacles):
                paste_text(im,bitmap,box[0]+bw/2,box[1])
                labels.append(dict(owner=obj['id'],text=text,bbox=box,font_size=DESIGN_TYPE['label'],glyph_size=bitmap.size));break
        else:
            notes.append(dict(code='LABEL_DROPPED',tier='craft',scene=scene,object=obj['id'],text=text,reason='no free safe slot'))
    used_texts.update(text_key(row['text']) for row in labels)
    return labels


def violations(metrics, size, *, expected_light='upper_left'):
    from app import visual_thresholds as T
    from worker.subject_geometry import violation
    errors=[]
    scene=metrics.get('scene',1)
    def add(code,detail,obj=None,threshold='required'):
        errors.append(violation(code,scene,obj or {'name':'scene'},detail,threshold))
    objects=metrics.get('objects',[]); rear=metrics.get('rear_objects',[])
    if not isinstance(metrics.get('horizon'),(int,float)) or not 0<metrics['horizon']<size[1]:
        add('HORIZON_MISSING',metrics.get('horizon'),threshold=f'0 < horizon < {size[1]}')
    if len(set(metrics.get('planes',[])))<2:
        add('DEPTH_SCALE',metrics.get('planes'),threshold='at least two planes (R10)')
    mid=[o for o in objects if o.get('layer')=='mid' and o.get('role') in {'subject','character'}]
    reference=max((o['bbox'][3] for o in mid),default=0)
    reference_width=max((o['bbox'][2] for o in mid),default=0)
    for o in objects+rear:
        if o.get('parent') is not None:
            parent=next((p for p in objects if p.get('id')==o['parent']),{})
            inner=parent.get('inner_rect')
            supported=False
            if inner:
                ix,iy,iw,ih=inner
                projection=o.get('container_shadow_bbox')
                if projection:
                    px,py,pw,ph=projection
                    supported=ix<=px and iy<=py and px+pw<=ix+iw and py+ph<=iy+ih
                supported |= bool(o.get('contact_line')) and abs(o['bbox'][1]+o['bbox'][3]-iy-ih)<=4
            if not supported:add('FLOATING_SUBJECT',{'inner_rect':inner,'bbox':o['bbox'],'projection':o.get('container_shadow_bbox'),'contact':o.get('contact_line')},o,'container projection or bottom contact <=4px')
            continue
        if o.get('layer')=='back' and (o['bbox'][3]>reference*T.BACKDROP+1e-6 or o['bbox'][2]>reference_width*T.BACKDROP+1e-6):
            add('BACKDROP_SCALE',o['bbox'][2:],o,(reference_width*T.BACKDROP,reference*T.BACKDROP))
        if o.get('role')=='subject' and o['bbox'][3]+1e-6<size[1]*T.MIN_HEIGHT:
            add('SUBJECT_TOO_SMALL',o['bbox'][3],o,size[1]*T.MIN_HEIGHT)
        if o.get('role','subject') in {'subject','character','result','tool'} and o in objects:
            supported = o.get('shadow') or o.get('contact_line') or o.get('ground_error_px') == 0
            flying = o.get('flying') and o.get('motion_vector') and any(o['motion_vector'])
            if not supported and not flying:
                add('FLOATING_SUBJECT',{'shadow':o.get('shadow'),'contact':o.get('contact_line'),'motion':o.get('motion_vector')},o,'projection or contact; flying needs motion')
        if 'base_size' in o:
            expected=[v*T.DEPTH**o.get('depth',0) for v in o['base_size']]
            deviation=max(abs(actual/want-1) for actual,want in zip(o['bbox'][2:],expected))
            if deviation>T.DEPTH_TOLERANCE+1e-6:add('DEPTH_SCALE',deviation,o,T.DEPTH_TOLERANCE)
    for far in objects:
        for near in objects:
            if far.get('parent') is None and near.get('parent') is None and far.get('shape')==near.get('shape') and far.get('depth',0)>near.get('depth',0):
                expected=near['bbox'][3]*T.DEPTH**(far['depth']-near.get('depth',0))
                deviation=abs(far['bbox'][3]/expected-1)
                if deviation>T.DEPTH_TOLERANCE+1e-6:add('DEPTH_SCALE',deviation,far,T.DEPTH_TOLERANCE)
    by_id={o.get('id'):o for o in objects}
    labels=metrics.get('labels',[])
    if len(labels)>1:add('LABEL_TOO_MANY','at most one process/abstract label')
    if any(label.get('font_size')!=DESIGN_TYPE['label'] for label in labels):
        add('LABEL_FONT_MIXED','all labels require the 13px tier')
    for label in labels:
        owner=by_id.get(label.get('owner'))
        if owner is None or distance(label['bbox'],owner['bbox'])>24:
            add('LABEL_ORPHAN',label.get('text'))
        if any(overlaps(label['bbox'],o['bbox']) for o in objects+rear if o is not owner and o.get('id') != (owner or {}).get('parent') and not (o.get('container') and owner and o.get('container')==owner.get('container'))):
            add('LABEL_OVERLAP',label.get('text'))
    if metrics.get('light_direction') not in {'upper_left','upper_right'} or metrics.get('light_direction')!=expected_light:
        add('LIGHT_DIRECTION',metrics.get('light_direction'),threshold=expected_light)
    if metrics.get('rendered_light_direction',expected_light)!=metrics.get('light_direction'):
        add('LIGHT_DIRECTION',metrics.get('rendered_light_direction'),threshold=metrics.get('light_direction'))
    for relation in metrics.get('light_relations',[]):
        source=by_id.get(relation['source']); target=by_id.get(relation['target'])
        valid=False
        if source and target:
            for ray in metrics.get('light_rays',[]):
                if (ray.get('source'),ray.get('target'))!=(relation['source'],relation['target']):continue
                sx,sy=ray['start']; ex,ey=ray['end']; x,y,w,h=source['bbox']
                at_edge=distance((sx,sy,0,0),source['bbox'])<=12 and min(abs(sx-x),abs(sx-x-w),abs(sy-y),abs(sy-y-h))<=12
                valid |= at_edge and distance((ex,ey,0,0),target['bbox'])<=1
        if not valid and relation.get('luma_after',0)-relation.get('luma_before',0)<T.LUMA:
            add('LIGHT_CAUSALITY_MISSING',relation,threshold=f'edge ray or luma delta >= {T.LUMA}')
    return errors


def episode_violations(frames, size):
    direction=next((m['light_direction'] for m in frames if any(o['shape']=='sun' for o in m['objects'])), 'upper_left')
    return [dict(error,scene=m.get('scene',i+1)) for i,m in enumerate(frames) for error in violations(m,size,expected_light=direction)]
