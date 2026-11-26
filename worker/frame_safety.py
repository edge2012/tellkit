"""Fixed text bands: change object commands, never move typography or reject a film."""
import math
from PIL import Image
from worker.overlays import caption_band_top


def fit_box(box, size, minimum):
    x,y,w,h=box
    top=math.ceil(size[1]*.12)
    bottom=math.floor(caption_band_top(size))-4
    if y+h > bottom:
        # Shrink about the centre before translating, stopping at the role floor.
        floor=math.sqrt(minimum*size[0]*size[1]/max(1,w*h))
        factor=min(1,max(floor,(bottom-y)/max(1,h)))
        nw,nh=math.ceil(w*factor),math.ceil(h*factor)
        x+=(w-nw)/2;y+=(h-nh)/2;w,h=nw,nh
    y=max(top,min(y,bottom-h))
    if h>bottom-top or w>size[0]:return None
    return (round(max(0,min(x,size[0]-w))),round(y),round(w),round(h))


def protect_text_bands(plan, metrics, scene):
    notes=[];claimed=set();hidden=set()
    for obj in metrics.get('objects',[]):
        if not obj.get('bbox') or not obj.get('visible',True):continue
        old=tuple(obj['bbox'])
        matches=[i for i,c in enumerate(plan.commands) if i not in claimed and c[0]=='paste'
                 and tuple(c[2][:2])+c[1].size==old]
        if not matches:continue
        i=matches[-1];claimed.add(i)
        new=fit_box(old,plan.size,obj.get('size_bounds',(.03,.05))[0])
        if new is None:
            hidden.add(i);obj['visible']=False;obj['text_band_suppressed']=True
            notes.append(dict(code='OBJECT_PUSHED_OUT_OF_CAPTION_BAND',tier='craft',scene=scene,object=obj['id'],bbox=old))
            continue
        if new==old:continue
        _,sprite,_,mask=plan.commands[i]
        sprite=sprite.resize(new[2:],Image.Resampling.LANCZOS)
        if mask is not None:mask=mask.resize(new[2:],Image.Resampling.LANCZOS)
        plan.commands[i]=('paste',sprite,new[:2],mask)
        obj.update(bbox=new,pixel_mask=sprite.getchannel('A'),size_area=new[2]*new[3]/(plan.width*plan.height))
        if obj.get('layout_trace'):obj['layout_trace']['output_bbox']=list(new)
        if obj.get('inner_rect'):
            ix,iy,iw,ih=obj['inner_rect'];sx,sy=new[2]/old[2],new[3]/old[3]
            obj['inner_rect']=(new[0]+(ix-old[0])*sx,new[1]+(iy-old[1])*sy,iw*sx,ih*sy)
        if obj.get('lighting_declaration'):
            from worker.lighting_declaration import transform
            obj['lighting_declaration']=transform(obj['lighting_declaration'],new[2:],scale=(new[2]/old[2],new[3]/old[3]))
        notes.append(dict(code='OBJECT_TEXT_BAND_ADJUSTED',tier='craft',scene=scene,object=obj['id'],before=old,after=new))
    # Shadows and temporary action sprites have draw commands but no semantic
    # object row. They obey the same bands; otherwise old-position silhouettes
    # can remain in the caption band after their owner has moved.
    for i,command in enumerate(plan.commands):
        if i in claimed or command[0]!='paste':continue
        _,sprite,position,mask=command
        old=tuple(position[:2])+sprite.size
        if old[1]>=math.ceil(plan.height*.12) and old[1]+old[3]<=math.floor(caption_band_top(plan.size))-4:continue
        new=fit_box(old,plan.size,min(.03,old[2]*old[3]/(plan.width*plan.height)))
        identity=f'primitive_{i}'
        if new is None:
            hidden.add(i)
            notes.append(dict(code='OBJECT_PUSHED_OUT_OF_CAPTION_BAND',tier='craft',scene=scene,object=identity,bbox=old))
        else:
            sprite=sprite.resize(new[2:],Image.Resampling.LANCZOS)
            if mask is not None:mask=mask.resize(new[2:],Image.Resampling.LANCZOS)
            plan.commands[i]=('paste',sprite,new[:2],mask)
            notes.append(dict(code='OBJECT_TEXT_BAND_ADJUSTED',tier='craft',scene=scene,object=identity,before=old,after=new))
    plan.commands[:]=[c for i,c in enumerate(plan.commands) if i not in hidden]
    metrics['objects']=[o for o in metrics.get('objects',[]) if not o.get('text_band_suppressed')]
    metrics['content_bottom']=max((o['bbox'][1]+o['bbox'][3] for o in metrics['objects']),default=0)
    metrics.setdefault('craft',[]).extend(notes)
    from app.enforcement import record
    record(notes,'layout')
