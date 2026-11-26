"""Measurable predicates over relation endpoints and actual raster evidence."""
import math
import numpy as np
from PIL import Image, ImageChops


def bounds(obj):
    x,y,w,h = obj['bbox']
    return x,y,x+w,y+h


def boundary(obj):
    mask = obj.get('pixel_mask')
    x,y,w,h = obj['bbox']
    if mask is None:
        return np.array([[x,y],[x+w,y],[x,y+h],[x+w,y+h]], dtype=float)
    cells = np.asarray(mask)>32
    inner = cells.copy()
    for axis in (0,1):
        inner &= np.roll(cells,1,axis) & np.roll(cells,-1,axis)
    inner[0,:] = inner[-1,:] = False
    inner[:,0] = inner[:,-1] = False
    yy,xx = np.nonzero(cells & ~inner)
    return np.column_stack((x+xx*w/mask.width,y+yy*h/mask.height))


def distance(point, obj):
    contour = boundary(obj)
    return float(np.sqrt(((contour-np.array(point))**2).sum(axis=1)).min()) if len(contour) else None


def projection(a,b,config,size):
    light = config.get('light_position')
    if not isinstance(light,(list,tuple)) or len(light)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in light):
        return dict(bbox=None, reason='light position unavailable')
    lx,ly = light[0]*size[0],light[1]*size[1]
    ax,ay,aw,ah = a['bbox']; bx,by,bw,bh = b['bbox']; cx=ax+aw/2
    if config.get('light_alignment') == 'overhead': lx = cx
    if ly >= ay: return dict(bbox=None, light=[lx,ly], endpoint_bbox=a['bbox'], target_bbox=b['bbox'], reason='projection intersection unavailable')
    dx = (cx-lx)*max(0,by-ay)/(ay-ly)
    dx = max(bx+min(aw,bw)/2-cx, min(dx,bx+bw-min(aw,bw)/2-cx))
    width = min(bw, max(1,aw+abs(dx)))
    height = min(bh,max(1,ah*.15))
    x = max(bx,min(cx+dx/2-width/2,bx+bw-width))
    return dict(bbox=[x,by,width,height], light=[lx,ly])


def measure(rels, objects):
    lookup = {o['id']:o for o in objects}
    order = {o['id']:i for i,o in enumerate(objects)}
    rows = []
    for rel in rels:
        if not isinstance(rel,dict) or rel.get('degraded'): continue
        a,b = lookup.get(rel.get('from')),lookup.get(rel.get('to'))
        if a is None or b is None: continue
        typ = rel['type']; ax,ay,ar,ab = bounds(a); bx,by,br,bb = bounds(b)
        measured = {}; ok = False
        if typ == 'rests_on':
            mask = a.get('pixel_mask'); ink = mask.getbbox() if mask is not None else None
            bottom = ay+ink[3]*(ab-ay)/mask.height if ink else ab
            measured = dict(contact_px=abs(bottom-by), penetration_px=max(0,bottom-by), horizontal_overlap_px=max(0,min(ar,br)-max(ax,bx)))
            ok = measured['contact_px']<=4 and measured['penetration_px']==0 and measured['horizontal_overlap_px']>0
        elif typ == 'attached_to':
            aa,bc = boundary(a),boundary(b)
            gap = min((float(np.sqrt(((chunk[:,None,:]-bc[None,:,:])**2).sum(axis=2)).min())
                       for chunk in np.array_split(aa,max(1,len(aa)//128)) if len(chunk) and len(bc)), default=None)
            measured = dict(surface_gap_px=gap)
            ok = gap is not None and gap<=4
        elif typ == 'inside':
            overflow = max(0,bx-ax,by-ay,ar-br,ab-bb)
            measured = dict(overflow_px=overflow); ok=overflow==0
        elif typ == 'blocks':
            # Screen-space masks plus actual compositing order define the view ray.
            left,top,right,bottom = int(min(ax,bx)),int(min(ay,by)),int(max(ar,br)),int(max(ab,bb))
            size = (max(1,right-left),max(1,bottom-top))
            masks=[]
            for obj in (a,b):
                x,y,w,h=obj['bbox']; tile=obj.get('pixel_mask')
                mask=Image.new('L',size)
                if tile is not None and obj.get('visible',True): mask.paste(tile,(int(x-left),int(y-top)))
                masks.append(np.asarray(mask,dtype=float)/255)
            total=float(masks[1].sum())
            overlap=float((masks[0]*masks[1]).sum())
            front=order[a['id']]>order[b['id']]
            ratio=overlap/total if total and front else 0
            measured=dict(occlusion_ratio=ratio, in_front=front); ok=ratio>=.5
        elif typ == 'casts_on':
            patch=next((p for p in a.get('phenomenon_geometry',{}).get('projections',[]) if p['relation']==rel),{})
            rect=patch.get('bbox')
            if rect:
                x,y,w,h=rect; cx=(ax+ar)/2
                side=(x+w/2-cx)*(patch['light'][0]-cx)
                overflow=max(0,bx-x,by-y,x+w-br,y+h-bb)
                measured=dict(side_product_px2=side,overflow_px=overflow,projection_bbox=rect,light=patch['light'])
                ok=side<=0 and overflow==0
            else: measured=dict(projection_available=False, reason=patch.get('reason'), light=patch.get('light'), endpoint_bbox=patch.get('endpoint_bbox'), target_bbox=patch.get('target_bbox'))
        elif typ in {'comes_from','goes_to'}:
            source,target = (b,a) if typ=='comes_from' else (a,b)
            path=next((p for p in a.get('phenomenon_geometry',{}).get('paths',[])
                       if p['source']==source['id'] and p['target']==target['id'] and p['relation'].get('type')==typ),None)
            gaps=[distance(path[k],obj) for k,obj in (('start',source),('end',target))] if path else [None,None]
            measured=dict(start_gap_px=gaps[0],end_gap_px=gaps[1]); ok=all(g is not None and g<=2 for g in gaps)
        rows.append(dict(relation={k:rel[k] for k in ('type','from','to')}, measured=measured,satisfied=bool(ok)))
    return rows
