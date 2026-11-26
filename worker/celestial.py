"""Fit complete subject ink, including attached marks, before compositing."""
import math
from PIL import Image

CELESTIAL={'sun','moon','earth','planet','rotation_globe'}


def fit(sp,x,y,size,shape,*,safe=None):
    w,h=size
    margin=math.ceil(min(w,h)*.04)
    left,top,right,bottom=safe or (margin,margin,w-margin,h-margin)
    bounds=sp.getchannel('A').getbbox()
    if bounds is None:raise ValueError('empty subject raster')
    l,t,r,b=bounds
    original=(x+l,y+t,r-l,b-t)
    info=dict(sp.info)
    from worker.lighting_declaration import for_sprite, transform
    declaration=for_sprite(sp)
    # Container coordinates follow the same crop and scale as its visible ink.
    if 'inner_rect' in info:
        iw0,ih0=info.get('inner_size',sp.size)
        ix,iy,iw,ih=info['inner_rect']
        info['inner_rect']=(ix*sp.width/iw0-l,iy*sp.height/ih0-t,iw*sp.width/iw0,ih*sp.height/ih0)
        info['inner_size']=(r-l,b-t)
    sp=sp.crop(bounds);x+=l;y+=t
    available=(right-left,bottom-top)
    if min(available)<=0:raise ValueError('SUBJECT_CLIPPED: empty safe region')
    factor=min(1,available[0]/sp.width,
               1 if shape=='ground' else available[1]/sp.height,
               h*.22/sp.height if shape in CELESTIAL else 1)
    nw,nh=max(1,math.floor(sp.width*factor)),max(1,math.floor(sp.height*factor))
    cx,cy=x+sp.width/2,y+sp.height/2
    if (nw,nh)!=sp.size:sp=sp.resize((nw,nh),Image.Resampling.LANCZOS)
    x=max(left,min(right-nw,round(cx-nw/2)))
    y=max(top,round(cy-nh/2) if shape=='ground' else min(bottom-nh,round(cy-nh/2)))
    if not (left<=x and top<=y and x+nw<=right and (shape=='ground' or y+nh<=bottom) and (shape not in CELESTIAL or nh<=h*.22)):
        raise ValueError('SUBJECT_CLIPPED: subject outside safe region after fit')
    ox,oy,ow,oh=original
    info['raster_fit']=dict(before=original,after=(x,y,nw,nh),safe=(left,top,right,bottom),
        overflow=dict(left=max(0,left-ox),top=max(0,top-oy),right=max(0,ox+ow-right),bottom=0 if shape=='ground' else max(0,oy+oh-bottom)))
    if declaration is not None:
        declaration=transform(declaration,(r-l,b-t),offset=(-l,-t))
        info['lighting_declaration']=transform(declaration,sp.size,scale=(nw/(r-l),nh/(b-t)))
    sp.info.update(info)
    return sp,x,y
