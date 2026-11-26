from worker.raster_cache import raster_cache
"""Renderer-owned lighting records. Coordinates are sprite-local, half-open.

Reference rasters are captured before lighting, never inferred from final RGB.
They preserve material ownership across multicolour sprites and ink occlusion.
"""
import base64
import math
import json
from functools import lru_cache
from copy import deepcopy
import zlib
from PIL import Image, ImageDraw, ImageFilter, ImageChops
from app import visual_thresholds as T


def pack(im):
    return dict(size=list(im.size), mode=im.mode,
                data=base64.b64encode(zlib.compress(im.tobytes())).decode())


def unpack(value):
    return Image.frombytes(value['mode'], tuple(value['size']), zlib.decompress(base64.b64decode(value['data'])))


def box_xywh(box):
    x,y,r,b=box
    return [x,y,r-x,b-y]


def record(shape, base, highlight, shadow, light, dark, clip):
    return dict(version=1, shape=shape, size=list(base.size),
                highlight=highlight, shadow=shadow, light_source=[-base.width,-base.height],
                reference=pack(base.convert('RGB')), light_mask=pack(light),
                shadow_mask=pack(dark), clip=pack(clip))


def unlit(shape, im):
    return deepcopy(_unlit(shape, im.mode, im.size, im.tobytes()))


@raster_cache(maxsize=32)
def _unlit(shape, mode, size, pixels):
    im=Image.frombytes(mode,size,pixels)
    zero=Image.new('L', im.size)
    return record(shape,im,dict(kind='none',box=[0,0,0,0],opacity=0,corner_radius=0),
                  None,zero,zero,im.getchannel('A'))


def _analyze(image, obj):
    from worker.material_pixels import components, bounds
    declaration=obj.get('lighting_declaration')
    result=dict(status='undetermined', code=None, reasons=[], mismatches=[], regions=[])
    if declaration is None:
        result['reasons']=['missing_lighting_declaration']
        return result
    reasons=result['reasons']; mismatch=result['mismatches']
    try:
        d=declaration; w,h=d['size']; hi=d['highlight']; sh=d['shadow']
        if d['shape'] != obj['shape']: reasons.append('shape_identity')
        if not all(math.isfinite(v) and v>0 for v in (w,h)):raise ValueError('invalid size')
        if isinstance(hi,list) or isinstance(sh,list):raise ValueError('exactly one highlight and shadow record required')
        if d.get('paint_pass_count',1)>1:reasons.append('multiple_lighting_passes')
        kind=hi['kind']; x,y,bw,bh=hi['box']; opacity=hi['opacity']
        if not all(math.isfinite(v) for v in (x,y,bw,bh,opacity,hi['corner_radius'])):raise ValueError('non-finite highlight')
        if kind not in {'bar','arc','none'}:reasons.append('highlight_kind')
        if kind!='none':
            if not T.HIGHLIGHT_ALPHA[0]<=opacity<=T.HIGHLIGHT_ALPHA[1]:reasons.append('highlight_opacity')
            if bw<=0 or bh<=0 or x<0 or y<0 or x+bw>w or y+bh>h:reasons.append('highlight_box_bounds')
            if hi.get('softness',0)<=0:reasons.append('highlight_softness')
            if kind=='bar':
                if not T.HIGHLIGHT_WIDTH[0]<=bw/w<=T.HIGHLIGHT_WIDTH[1]:reasons.append('bar_width')
                if not .5<=bh/h<=1:reasons.append('bar_height')
                if hi['corner_radius']<=0 or hi['corner_radius']>min(bw,bh)/2:reasons.append('bar_round_top')
                if x>w/4:reasons.append('bar_left_quarter')
            if kind=='arc':
                if not .5<=hi['arc_length']/w<=.9:reasons.append('arc_length')
                if y+bh>h/3:reasons.append('arc_top_band')
            if sh is None:reasons.append('missing_shadow')
        elif sh is not None:reasons.append('unlit_with_shadow')
        if sh is not None:
            sx,sy,sw,shh=sh['box']; lx,ly=d['light_source']
            if not all(math.isfinite(v) for v in (*sh['box'],lx,ly,sh['opacity'],sh['softness'])):raise ValueError('non-finite shadow')
            if not T.SHADE_ALPHA[0]<=sh['opacity']<=T.SHADE_ALPHA[1]:reasons.append('shadow_opacity')
            if sh['softness']<=0:reasons.append('shadow_softness')
            if (sx+sw/2-w/2)*(lx-w/2)+(sy+shh/2-h/2)*(ly-h/2)>=0:reasons.append('shadow_direction')
        ox,oy,ow,oh=map(round,obj['bbox'])
        if (ow,oh)!=(w,h):raise ValueError('coordinate_space_mismatch')
        actual=(image if image.mode == 'RGB' else image.convert('RGB')).crop((ox,oy,ox+ow,oy+oh))
        base=unpack(d['reference']); lm=unpack(d['light_mask']); dm=unpack(d['shadow_mask']); clip=unpack(d['clip'])
        if any(im.size!=(w,h) for im in (base,lm,dm,clip)):raise ValueError('reference_size')
        if kind=='none':
            if lm.getbbox() is not None or dm.getbbox() is not None:
                mismatch.append('none_contains_lighting')
        elif kind in {'bar','arc'}:
            # Reconstruct declared geometry independently of the recorded mask.
            # One raster pixel covers float-coordinate rounding and resampling.
            expected=Image.new('L',(w,h));pen=ImageDraw.Draw(expected)
            if kind=='bar' and bw>0 and bh>0 and hi['corner_radius']>=0:
                pen.rounded_rectangle((x,y,x+bw-1,y+bh-1),radius=hi['corner_radius'],fill=round(opacity*255))
            elif kind=='arc':
                path=[tuple(p) for p in hi['path']];radius=hi['corner_radius']
                length=sum(math.dist(a,b) for a,b in zip(path,path[1:]))
                if abs(length-hi['arc_length'])>1:reasons.append('arc_path_length')
                if len(path)<3 or min(p[1] for p in path)>=min(path[0][1],path[-1][1]):reasons.append('arc_path_curvature')
                pen.line(path,fill=round(opacity*255),width=max(1,round(radius*2)),joint='curve')
                for px,py in (path[0],path[-1]):pen.ellipse((px-radius,py-radius,px+radius,py+radius),fill=round(opacity*255))
            expected=expected.filter(ImageFilter.GaussianBlur(max(0,hi.get('softness',0))))
            threshold=opacity*255*.8
            eligible=clip.point(lambda v:255 if v>=250 else 0)
            ec=ImageChops.multiply(expected.point(lambda v:255 if v>=threshold else 0),eligible)
            ac=ImageChops.multiply(lm.point(lambda v:255 if v>=threshold else 0),eligible)
            if (ImageChops.subtract(ec,ac.filter(ImageFilter.MaxFilter(3))).getbbox() is not None or
                    ImageChops.subtract(ac,ec.filter(ImageFilter.MaxFilter(3))).getbbox() is not None):
                mismatch.append('mask_geometry_differs_from_declaration')
        import numpy as np
        a=np.asarray(actual);b=np.asarray(base)
        lp=np.asarray(lm);dp=np.asarray(dm);cp=np.asarray(clip)
        eligible=(cp>=250)&((a[:,:,0]<40)|(a[:,:,0]>46)|(a[:,:,1]<30)|(a[:,:,1]>36)|(a[:,:,2]<21)|(a[:,:,2]>27))
        def luma(c):return .2126*c[:,:,0]+.7152*c[:,:,1]+.0722*c[:,:,2]
        al,bl=luma(a),luma(b)
        lift=(al-bl)/np.maximum(1,bl)
        yy,xx=np.ogrid[:h,:w];in_box=(x<=xx)&(xx<x+bw)&(y<=yy)&(yy<y+bh)
        inside=lift[eligible & in_box & (lp>=opacity*255*.8)].tolist()
        def points(mask):
            ys,xs=np.nonzero(mask)
            return list(zip(xs.tolist(),ys.tolist()))
        outside=eligible & ~in_box & (lp==0) & (lift>=.12)
        painted=eligible & (lp>10);count=int(np.count_nonzero(painted))
        bad_pixels=np.zeros((h,w),dtype=bool)
        if count:
            da=dp/255;la=lp/255
            for channel,(dark,light) in enumerate(zip((43,33,24),(255,250,233))):
                expected=(b[:,:,channel]*(1-da)+dark*da)*(1-la)+light*la
                bad_pixels |= np.abs(a[:,:,channel]-expected)>3
        bad=int(np.count_nonzero(painted & bad_pixels))
        dark_points=points(eligible & (dp>0) & (lp==0) & (bl-al>.5)) if sh is not None else []
        if kind!='none' and (not inside or sum(inside)/len(inside)<.12):mismatch.append('box_luminance_lift_below_12_percent')
        # Six-by-six connected components; retain measured coordinates for review.
        from worker.pixel_regions import regions
        for region in regions(outside):
            l,t,r,b=region.bounds
            if r-l>=6 and b-t>=6:
                mismatch.append('undeclared_bright_region')
                result['regions'].append(dict(bbox=[l,t,r,b],area=len(region)))
        if count and bad/count>.05:mismatch.append('paint_differs_from_declared_raster')
        if sh is not None:
            if not dark_points:mismatch.append('shadow_not_visible')
            else:
                cx=sum(p[0] for p in dark_points)/len(dark_points);cy=sum(p[1] for p in dark_points)/len(dark_points)
                if (cx-w/2)*(lx-w/2)+(cy-h/2)*(ly-h/2)>=0:mismatch.append('pixel_shadow_direction')
        result['measured']=dict(width_ratio=bw/w,height_ratio=bh/h,mean_luminance_lift=sum(inside)/len(inside) if inside else None,
                                painted_samples=count,disagreeing_samples=bad)
    except (KeyError,TypeError,ValueError,OverflowError,ZeroDivisionError,zlib.error) as exc:
        reasons.append('invalid_declaration: '+str(exc))
    result['status']='violation' if reasons or mismatch else 'compliant'
    result['code']='HIGHLIGHT_DECLARATION_MISMATCH' if mismatch else 'HIGHLIGHT_GRAMMAR' if reasons else None
    return result


def transform(d, size, *, offset=(0,0), scale=(1,1), background=None):
    # Static sprite reference rasters share the exact same affine transform in
    # audit and delivery. Cache paint data only; every frame still runs analyze.
    import os
    import pickle
    if background is not None or os.getenv('TELLKIT_STATIC_LAYER_CACHE') == '0':
        return _transform(d, size, offset=offset, scale=scale, background=background)
    return deepcopy(_static_transform(pickle.dumps(d, protocol=5), tuple(size), tuple(offset), tuple(scale)))


@lru_cache(maxsize=128)
def _static_transform(serial, size, offset, scale):
    import pickle
    # serial is generated above in this process, never loaded from external data.
    return _transform(pickle.loads(serial), size, offset=offset, scale=scale)


def _transform(d, size, *, offset=(0,0), scale=(1,1), background=None):
    """Apply the same affine crop/paste/resize as the sprite, without mutating caches."""
    from copy import deepcopy
    d=deepcopy(d); sx,sy=scale; dx,dy=offset
    for name in ('highlight','shadow'):
        item=d[name]
        if item is None:continue
        x,y,w,h=item['box'];item['box']=[x*sx+dx,y*sy+dy,w*sx,h*sy]
        for key in ('corner_radius','softness','arc_length'):
            if key in item:item[key]*=min(sx,sy)
    if 'path' in d['highlight']:
        d['highlight']['path']=[[x*sx+dx,y*sy+dy] for x,y in d['highlight']['path']]
        d['highlight']['arc_length']=sum(math.dist(a,b) for a,b in zip(d['highlight']['path'],d['highlight']['path'][1:]))
    d['light_source']=[d['light_source'][0]*sx+dx,d['light_source'][1]*sy+dy]
    for key in ('reference','light_mask','shadow_mask','clip'):
        old=unpack(d[key]);new=background.convert('RGB').copy() if key=='reference' and background is not None else Image.new(old.mode,size)
        old=old.resize((max(1,round(old.width*sx)),max(1,round(old.height*sy))),Image.Resampling.LANCZOS)
        new.paste(old,(round(dx),round(dy)));d[key]=pack(new)
    d['size']=list(size)
    return d


def for_sprite(sp):
    d=sp.info.get('lighting_declaration')
    if d is None:return None
    if tuple(d['size'])!=sp.size:
        d=transform(d,sp.size,scale=(sp.width/d['size'][0],sp.height/d['size'][1]))
    return d


def analyze(image, obj):
    x,y,w,h=map(round,obj['bbox'])
    tile=(image if image.mode == 'RGB' else image.convert('RGB')).crop((x,y,x+w,y+h))
    try:serial=json.dumps(obj.get('lighting_declaration'),sort_keys=True,allow_nan=True)
    except (TypeError,ValueError):return _analyze(image,obj)
    return deepcopy(_cached(tile.size,tile.tobytes(),obj['shape'],serial))


@raster_cache(maxsize=128)
def _cached(size, pixels, shape, serial):
    image=Image.frombytes('RGB',size,pixels)
    return _analyze(image,dict(shape=shape,bbox=[0,0,*size],lighting_declaration=json.loads(serial)))
