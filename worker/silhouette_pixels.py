"""R22: inspect actual opaque interior RGB, excluding antialiased boundaries.

Use the original pre-detail silhouette mask; replacing it with a mask punched
through by facial marks would destroy the evidence. RGB compressed archive
frames need independently measured masks, not regenerated current sprites.
"""
from collections import Counter
from PIL import ImageFilter
from app.visual_spec_w27b import SILHOUETTES, violation


def violations(image, objects, scene=1):
    errors=[]
    for o in objects:
        if o.get('render_channel') == 'surface_region' or o.get('shape') not in SILHOUETTES:continue
        x,y,w,h=map(round,o['bbox'])
        mask=o.get('pixel_mask')
        if mask is None:raise ValueError('R22 requires original silhouette pixel_mask')
        if mask.size!=(w,h):raise ValueError('R22 mask must match object bbox')
        # One-pixel inward erosion excludes antialiasing and contour outlines.
        interior=mask.convert('L').point(lambda p:255 if p==255 else 0).filter(ImageFilter.MinFilter(3))
        crop=(image if image.mode == 'RGB' else image.convert('RGB')).crop((x,y,x+w,y+h))
        colors=Counter(p for p,m in zip(crop.getdata(),interior.getdata()) if m)
        if not colors:raise ValueError('R22 has no measurable opaque interior')
        base,count=colors.most_common(1)[0]
        detail=sum(n for color,n in colors.items() if color!=base)
        if detail:errors.append(violation('SILHOUETTE_DETAIL',scene,o,dict(interior_detail_pixels=detail,base_rgb=base),'one solid interior color'))
    return errors
