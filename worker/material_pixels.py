from worker.raster_cache import raster_cache
"""R14–R19 single-frame measurements in object-local pixel space.

Lighting masks may be supplied by the compositor; they are sampled against the
actual RGB frame. No boolean material declarations are accepted as evidence.
The automatic path segments palette interiors; antialias pixels are excluded
by requiring a locally constant cross before examining paint transitions.
"""
from collections import Counter, deque
from functools import lru_cache
from copy import deepcopy
from PIL import Image, ImageFilter
from app import visual_thresholds as T
from worker.subject_geometry import violation


def components(points):
    remaining=set(points); out=[]
    while remaining:
        seed=remaining.pop(); region={seed}; queue=deque([seed])
        while queue:
            x,y=queue.popleft()
            for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if p in remaining:
                    remaining.remove(p);region.add(p);queue.append(p)
        out.append(region)
    return out


def bounds(points):
    return min(x for x,y in points),min(y for x,y in points),max(x for x,y in points)+1,max(y for x,y in points)+1


def measure(image, obj):
    # Exact pixel memoization: all frames still undergo the same checks. Static
    # pixels reuse their measurements; any changed pixel/mask/material misses.
    x,y,w,h=map(round,obj['bbox'])
    tile=(image if image.mode == 'RGB' else image.convert('RGB')).crop((x,y,x+w,y+h))
    mask=obj.get('pixel_mask')
    mask_key=(mask.mode,mask.size,mask.tobytes()) if mask is not None else None
    base=tuple(obj['base_color']) if 'base_color' in obj else None
    # Pixels outside the measurement silhouette (and its excluded border) are
    # never read by _measure_uncached. Canonicalize only those irrelevant bytes
    # so moving ambient backgrounds do not invalidate a static subject.
    import numpy as np
    pixels=np.asarray(tile).copy()
    if mask is not None and len(mask.getbands())==1:
        pixels[np.asarray(mask)==0]=0
    pixels[:1]=0;pixels[-1:]=0;pixels[:,:1]=0;pixels[:,-1:]=0
    measured=deepcopy(_measure_pixels(tile.size,pixels.tobytes(),mask_key,base,obj['shape']))
    if not obj.get('legacy_lighting',False):
        from worker.lighting_declaration import analyze
        measured['highlight_grammar']=analyze(image,obj)
    else:
        # Explicit archival diagnostics only; production defaults to W35.
        from worker.highlight_grammar import analyze
        measured['highlight_grammar']=analyze(image,obj)
    return measured


@raster_cache(maxsize=128)
def _measure_pixels(size, pixels, mask_key, base, shape):
    image=Image.frombytes('RGB',size,pixels)
    obj=dict(bbox=(0,0,*size),shape=shape)
    if mask_key is not None:obj['pixel_mask']=Image.frombytes(*mask_key)
    if base is not None:obj['base_color']=base
    return _measure_uncached(image,obj)


def _measure_uncached(image, obj):
    x,y,w,h=map(round,obj['bbox'])
    tile=(image if image.mode == 'RGB' else image.convert('RGB')).crop((x,y,x+w,y+h)); px=tile.load()
    # A supplied silhouette is a pixel mask, not an asserted material property.
    mask=obj.get('pixel_mask')
    import numpy as np
    rgb=np.asarray(tile)
    packed=(rgb[:,:,0].astype(np.int32)<<16)|(rgb[:,:,1].astype(np.int32)<<8)|rgb[:,:,2]
    valid_array=np.ones((h,w),dtype=bool) if mask is None or len(mask.getbands())>1 else np.asarray(mask)!=0
    valid_array=valid_array.copy()
    valid_array[:1,:]=False;valid_array[-1:,:]=False
    valid_array[:,:1]=False;valid_array[:,-1:]=False
    keys,counts=np.unique(packed[valid_array],return_counts=True)
    colors={(int(k)>>16,(int(k)>>8)&255,int(k)&255):int(n) for k,n in zip(keys,counts)}
    base=obj.get('base_color')
    if base is None:
        maximum=max(colors.values(),default=0)
        tied=[c for c,n in colors.items() if n==maximum]
        if len(tied)>1:
            # Retain the original set traversal tie ordering exactly.
            valid={(xx,yy) for yy in range(1,h-1) for xx in range(1,w-1) if valid_array[yy,xx]}
            base=Counter(px[p] for p in valid).most_common(1)[0][0]
        else:base=tied[0] if tied else (0,0,0)
    base=tuple(base)
    light_color=(255,250,233); dark_color=(43,33,24)
    palette=sorted(colors)
    palette_keys=np.array([(r<<16)|(g<<8)|b for r,g,b in palette],dtype=np.int32)
    indices=np.searchsorted(palette_keys,packed)
    indices=np.minimum(indices,max(0,len(palette)-1))
    def alpha_map(target):
        # Preserve scalar operation order and the one-step quantization test.
        if not palette:return np.full((h,w),-1.)
        values=np.asarray(palette,dtype=np.float64)
        channels=[k for k in range(3) if target[k]!=base[k]]
        if not channels:return np.full((h,w),-1.)
        ratios=[(values[:,k]-base[k])/(target[k]-base[k]) for k in channels]
        alpha=sum(ratios)/len(ratios)
        legal=(alpha>0)&(alpha<=1)
        for k in range(3):
            legal &= np.abs(values[:,k]-(base[k]+alpha*(target[k]-base[k])))<=1
        return np.where(legal,alpha,-1.)[indices]
    light_values=alpha_map(light_color);dark_values=alpha_map(dark_color)
    def points(mask):
        yy,xx=np.nonzero(mask)
        return zip(xx.tolist(),yy.tolist())
    highlights={p:float(light_values[p[1],p[0]]) for p in points(valid_array & (light_values>=T.HIGHLIGHT_ALPHA[0]))}
    dark_mask=valid_array & (dark_values>=T.SHADE_ALPHA[0]) & (packed!=((43<<16)|(33<<8)|24))
    all_light=bool(np.any(valid_array & (light_values>0) & (light_values<T.HIGHLIGHT_ALPHA[0])))
    all_dark=bool(np.any(valid_array & (dark_values>0) & (dark_values<T.SHADE_ALPHA[0])))
    regions=components(highlights)
    bars=[]
    for region in regions:
        l,t,r,b=bounds(region)
        rows={yy:[] for yy in range(t,b)}
        for xx,yy in region:rows[yy].append(xx)
        centers=[(min(xs)+max(xs))/2 for xs in rows.values() if xs]
        widths=[max(xs)-min(xs)+1 for xs in rows.values() if xs]
        vertical=b-t>r-l and max(centers)-min(centers)<=1
        rounded=bool(widths and widths[0]<max(widths) and widths[-1]<max(widths))
        # Curved thin ridge: changing x center, narrower cross-section than span,
        # and changing slope; excludes a straight diagonal polygon/facet.
        slopes=[b-a for a,b in zip(centers,centers[1:])]
        arc=bool(len(slopes)>1 and max(slopes)!=min(slopes) and max(widths)<r-l and not vertical)
        hard_edge=any(px[q]==base for xx,yy in region for q in ((xx-1,yy),(xx+1,yy),(xx,yy-1),(xx,yy+1)) if 0<=q[0]<w and 0<=q[1]<h and valid_array[q[1],q[0]] and q not in region)
        bars.append(dict(hard_edge=hard_edge,width=(r-l)/w,vertical=vertical,rounded=rounded,arc=arc,
                         alpha=max(highlights[p] for p in region),center=(l+r)/2/w))
    from worker.pixel_regions import regions as raster_regions
    rings=[]
    for region in raster_regions(valid_array & (packed==0xffffff)):
        l,t,r,b=region.bounds
        center=((l+r-1)//2,(t+b-1)//2)
        # White must enclose a nonwhite hole in all four directions.
        cx,cy=center
        if center not in region and all(any((cx+dx*k,cy+dy*k) in region for k in range(1,max(w,h))) for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):
            rings.append((l,t,r,b))
    texture=False;gradient=False;bands=0
    # Sample only the bbox interior, excluding the two-pixel AA border.
    # A stripe must be flat across six contiguous transverse pixels. Ink and
    # disconnected silhouette gaps terminate runs rather than joining paints.
    # Same six-pixel cross and run lengths as the reference implementation.
    packed=(rgb[:,:,0].astype(np.int32)<<16)|(rgb[:,:,1].astype(np.int32)<<8)|rgb[:,:,2]
    dark_packed=(43<<16)|(33<<8)|24
    for transpose in (False,True):
        if texture:break
        data=packed.T if transpose else packed
        ok=valid_array.T if transpose else valid_array
        outer,inner=data.shape
        if outer<10 or inner<5:continue
        flat=(data!=dark_packed)
        for d in range(-2,4):
            flat[4:outer-5] &= ok[4+d:outer-5+d] & (data[4:outer-5]==data[4+d:outer-5+d])
        values=np.where(flat[4:outer-5,2:inner-2],data[4:outer-5,2:inner-2],-1)
        if not values.size:continue
        # Flatten row runs, retaining row identity so runs never cross a row.
        starts=np.ones(values.shape,dtype=bool)
        starts[:,1:]=values[:,1:]!=values[:,:-1]
        offsets=np.flatnonzero(starts)
        colors5=values.ravel()[offsets]
        lengths=np.diff(np.r_[offsets,values.size])
        rows=offsets//values.shape[1]
        if len(colors5)>=5:
            legal=(rows[:-4]==rows[4:])&(colors5[:-4]!=-1)&(colors5[1:-3]!=-1)
            alternating=(colors5[:-4]==colors5[2:-2])&(colors5[:-4]==colors5[4:])&(colors5[1:-3]==colors5[3:-1])&(colors5[:-4]!=colors5[1:-3])
            lengths5=sum(lengths[k:len(lengths)-4+k] for k in range(5))
            texture=bool(np.any(legal & alternating & (lengths5>=6)))
    interior=valid_array & ~((light_values>0)|((dark_values>0)&(packed!=dark_packed)))
    yy,xx=np.nonzero(interior)
    values=rgb[yy,xx]
    if len(values):
        starts=np.r_[True,(yy[1:]!=yy[:-1])|np.any(values[1:]!=values[:-1],axis=1)]
        runs=values[starts].astype(np.int16); row_ids=yy[starts]
        counts=np.bincount(row_ids,minlength=h)
        same=row_ids[1:]==row_ids[:-1]
        differences=np.diff(runs,axis=0)
        for channel in range(3):
            # Strict monotonicity implies all levels are distinct.
            nonpositive=np.bincount(row_ids[1:][same & (differences[:,channel]<=0)],minlength=h)
            nonnegative=np.bincount(row_ids[1:][same & (differences[:,channel]>=0)],minlength=h)
            gradient |= bool(np.any((counts>T.WATER_BANDS)&((nonpositive==0)|(nonnegative==0))))
    water=obj['shape'] in {'river','water','water_surface'}
    if water and len(values):
        # Row/color counts with the same first-seen tie break as Counter.
        keys=(yy.astype(np.int64)<<24)|packed[yy,xx]
        unique,first,counts=np.unique(keys,return_index=True,return_counts=True)
        rows=unique>>24
        order=np.lexsort((first,-counts,rows))
        ordered_rows=rows[order]
        winners=order[np.r_[True,ordered_rows[1:]!=ordered_rows[:-1]]]
        row_colors=unique[winners]&0xffffff
        bands=int(1+np.count_nonzero(row_colors[1:]!=row_colors[:-1]))
        gradient |= bands>T.WATER_BANDS
    dark_regions=raster_regions(dark_mask)
    dark_x=np.nonzero(dark_mask)[1]
    dark_center=int(dark_x.sum())/len(dark_x)/w if len(dark_x) else None
    continents=any(g>r and g>b for r,g,b in colors)
    # Axis is dark ink crossing both the upper and lower parts of the sphere.
    ink=valid_array & (packed==dark_packed)
    axis=bool(np.any(np.any(ink[:h//4,w//4:3*w//4],axis=0)&np.any(ink[3*h//4:,w//4:3*w//4],axis=0)))
    from worker.lighting_declaration import analyze
    return dict(highlight_grammar=analyze(image,obj),highlights=bars,dark_count=len(dark_regions),dark_alpha=float(np.max(dark_values[dark_mask],initial=0)),
                light_soft=bool(all_light),dark_soft=bool(all_dark),dark_center=dark_center,
                rings=rings,texture=texture,gradient=gradient,water_bands=bands,
                continents=continents,axis=axis)


def violations(image, objects, scene=1, light='upper_left'):
    errors=[]
    for obj in objects:
        if 'bbox' not in obj or obj.get('render_channel') == 'surface_region':continue
        m=measure(image,obj)
        def add(code,value,limit):errors.append(violation(code,scene,obj,value,limit))
        # W34: any evidenced bright-region defect is checked, regardless of
        # shape name. Unlit flat lines naturally have no candidate region.
        grammar=m['highlight_grammar']
        if not obj.get('legacy_lighting',False):
            if grammar['status']!='compliant':
                add('HIGHLIGHT_GRAMMAR',grammar,dict(width=T.HIGHLIGHT_WIDTH,height=[.5,1],
                    alpha=T.HIGHLIGHT_ALPHA,arc_length=[.5,.9],shade_alpha=T.SHADE_ALPHA,luminance_lift_min=.12))
            if grammar.get('mismatches') or grammar['status']=='undetermined':
                add('HIGHLIGHT_DECLARATION_MISMATCH',grammar,'declared paint must match rendered RGB')
        elif grammar['status']=='violation':
            add('HIGHLIGHT_GRAMMAR',grammar,dict(diagonal_angle=[20,70],edge_length_gt=8,
                facet_directions_min=3,horizontal_aspect_gt=.6,legal_aspect_max=.35,
                alpha=[.35,.55],alpha_tolerance=.08))
        if obj['shape'] in {'earth','moon','planet','sphere','ball','sun'}:
            if not any(b['arc'] for b in m['highlights']) or m['dark_count']!=1 or (obj['shape']=='earth' and not (m['continents'] and m['axis'])):
                add('SPHERE_SHADING',m,'arc + dark side; earth additionally continents + rotation axis')
        if m['rings']:add('WHITE_RING_IN_VIDEO',m['rings'],0)
        if m['texture']:add('TEXTURE_BANNED','repeated alternating interior paint',0)
        if m['gradient']:add('GRADIENT_BANNED',m['water_bands'] or 'monotone interior colors',f'no gradient; water bands <= {T.WATER_BANDS}')
    return errors
