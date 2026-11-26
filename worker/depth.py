"""Shared depth palette and semantic environmental planes (no teaching items)."""
from PIL.ImageColor import getrgb as design_rgb
from worker.design_tokens import PALETTE
import colorsys
from functools import lru_cache
from PIL import Image, ImageDraw, ImageColor
from worker.design_tokens import PALETTE, STROKE as DESIGN_STROKE

TIERS = ('far', 'mid', 'near')
SCALE = {'far': .70, 'mid': 1., 'near': 1.}
STROKE = {'far': DESIGN_STROKE['decoration'], 'mid': DESIGN_STROKE['body'], 'near': DESIGN_STROKE['body']}


@lru_cache(maxsize=4096)
def color(rgb, depth='mid'):
    """Fixed white/black mix; far chroma is 72.5% of the original HSL S.

    Lightness is HSL L on a 0–100 scale. Do not clamp bright/white materials
    to manufacture an 8-point delta: white cannot become lighter than white.
    """
    if depth not in TIERS:
        raise ValueError(f'unknown depth: {depth}')
    if depth == 'mid':
        return rgb
    if depth == 'near':
        return tuple(round(c*.88) for c in rgb)
    mixed = tuple((c*.82+255*.18)/255 for c in rgb)
    hue, light, _ = colorsys.rgb_to_hls(*mixed)
    saturation = colorsys.rgb_to_hls(*(c/255 for c in rgb))[2]*.725
    return tuple(round(c*255) for c in colorsys.hls_to_rgb(hue, light, saturation))


def measures(rgb):
    _, light, saturation = colorsys.rgb_to_hls(*(c/255 for c in rgb))
    return dict(lightness=100*light, saturation=100*saturation)


def tint(image, depth):
    if depth == 'mid':
        return image
    result = image.copy()
    result.putdata([(*color(tuple(p[:3]), depth), p[3]) for p in image.convert('RGBA').getdata()])
    return result


def candidate(visual):
    """Only infer a backdrop from declared physical environment, never topic text."""
    bg = visual.background or {}
    if any(it.shape == 'river' for it in visual.items):
        return 'far_bank', 'river boundary'
    if bg.get('rear') == 'tree':
        return 'tree_shadow', 'background.rear=tree'
    if bg.get('rear') == 'window':
        return 'window_tree_shadow', 'background.rear=window (exterior silhouette)'
    return None


def silhouette(kind, size, base, depth='far', palette=None, stroke=None):
    """Same geometry/palette in all three planes, with explicit native-pixel ink."""
    if isinstance(stroke,float):
        scale=4
        image=silhouette(kind,(size[0]*scale,size[1]*scale),base,depth,palette,round(stroke*scale))
        return image.resize(size,Image.Resampling.BOX)
    w,h=size
    im=Image.new('RGBA', size)
    d=ImageDraw.Draw(im)
    fill,ink=palette if palette else (color(base,depth),color(design_rgb(PALETTE['neutral_900']),depth)); stroke=STROKE[depth] if stroke is None else stroke
    if kind == 'far_bank':
        points=[(0,h-1),(0,h*.60),(w*.13,h*.30),(w*.25,h*.43),(w*.43,h*.07),(w*.57,h*.32),(w*.72,h*.18),(w*.87,h*.42),(w-1,h*.58),(w-1,h-1)]
        d.polygon(points,fill=fill)
        d.line(points+[points[0]],fill=ink,width=stroke)
    else:
        d.rectangle((w*.44,h*.5,w*.56,h-1),fill=fill)
        points=[(1,h*.7),(w*.17,h*.40),(w*.10,h*.40),(w*.34,h*.16),(w*.29,h*.16),(w*.50,1),(w*.72,h*.16),(w*.66,h*.16),(w*.91,h*.40),(w*.83,h*.40),(w-2,h*.7)]
        d.polygon(points,fill=fill)
        d.line(points+[points[0]],fill=ink,width=stroke)
    return im


def _select_backdrop(kind, size, base, fill, ink, target):
    """Decorative geometry uses the shared stroke; no style search per sprite."""
    stroke=DESIGN_STROKE['decoration']
    return stroke,silhouette(kind,size,base,palette=(fill,ink),stroke=stroke)


# Only selected RGBA silhouettes survive, not the 29 temporary candidates.
# Position and per-frame evidence are computed below on every call.
_static_backdrop = lru_cache(maxsize=16)(_select_backdrop)


def backdrop(visual, size, horizon, objects):
    selection=candidate(visual)
    if selection is None:
        return [], []
    # Use a visible midground body, including a vessel when its contents are tiny.
    refs=[o for o in objects if o.get('render_channel') not in {'surface', 'surface_region'} and o.get('parent') is None and o.get('role') in {'subject','tool'} and o['shape'] not in {'sun','cloud','arrow','curved_arrow','card'}]
    if not refs:
        return [], []
    ref=max(refs,key=lambda o:o['bbox'][2]*o['bbox'][3])
    if ref.get('material_rgb') is None:
        from app.enforcement import record
        record([dict(code='DEPTH_MATERIAL_UNMEASURED', object=ref.get('id'), reason='reference material unavailable; omit optional far backdrop')], 'render')
        return [], []
    rw,rh=ref['bbox'][2:]; w,h=size
    fw,fh=max(3,int(rw*.7)),max(3,int(rh*.7))
    kind,reason=selection
    # Keep its complete bounds above the horizon and out of the title strip.
    if fh > horizon-h*.16:
        from app.enforcement import record
        record([dict(code='DEPTH_SCALE', object=ref.get('id'), reason='no room for optional far backdrop')], 'render')
        return [], []
    x=round((w-fw)*.72); y=round(horizon-fh-(0 if kind == 'far_bank' else 8))
    base=ImageColor.getrgb(PALETTE['secondary'])  # Existing vegetation material (globe land), not a per-scene adjustment.
    from worker.depth_measure import aerial_palette
    fill,ink=ImageColor.getrgb(PALETTE['neutral_300']),ImageColor.getrgb(DESIGN_STROKE['color'])
    target=DESIGN_STROKE['decoration']
    import os
    select = _select_backdrop if os.getenv('TELLKIT_STATIC_LAYER_CACHE') == '0' else _static_backdrop
    stroke,sp=select(kind,(fw,fh),base,fill,ink,target)
    from worker.drawing_plan import DrawingPlan
    plan=DrawingPlan(size,(0,0,0)); plan.paste(sp,(x,y),sp)
    if kind=='window_tree_shadow':
        # A window aperture makes the exterior silhouette unambiguously contextual.
        d=ImageDraw.Draw(plan)
        d.rectangle((x-8,y-8,x+fw+7,y+fh+7),outline=ink,width=DESIGN_STROKE['decoration'])
        d.line((x+fw/2,y-8,x+fw/2,y+fh+7),fill=ink,width=DESIGN_STROKE['decoration'])
    from worker.depth_measure import lightness, saturation
    mid=dict(lightness=lightness(tuple(ref['material_rgb'])),saturation=saturation(tuple(ref['material_rgb'])))
    far=dict(lightness=lightness(fill),saturation=saturation(fill))
    metric=dict(id='environment-far',shape=kind,role='environment',layer='back',depth_tier='far',
                bbox=(x,y,fw,fh),reference_id=ref.get('id'),reference_bbox=ref['bbox'],
                size_ratio=[fw/rw,fh/rh],stroke_px=stroke,base_rgb=base,far_rgb=fill,outline_rgb=ink,reference_rgb=ref['material_rgb'],
                lightness_space='CIE Lab D65',mid=mid,far=far,lightness_delta=far['lightness']-mid['lightness'],
                saturation_reduction=1-far['saturation']/mid['saturation'] if mid['saturation'] else None,selection_reason=reason,
                above_horizon=y+fh<=horizon,draw_order='before ground and subjects')
    return plan.commands,[metric]
