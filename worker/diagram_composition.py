from worker.design_tokens import TYPE
from worker.design_tokens import PALETTE, STROKE as DESIGN_STROKE, RADIUS as DESIGN_RADIUS
from worker.lighting_declaration import for_sprite
from worker.drawing_plan import DrawingPlan
"""Scientific display layout using only registered items; no episode/title branches."""
from PIL import Image, ImageDraw
from worker.visual import centered_text, paste_text


def stage(visual, size, index, t):
    from worker.scenekit_renderer import sprite, globe, BG, INK, _stage_fonts
    from worker.shapes_o1 import pointing_awen
    w,h=size; portrait=w<h
    im=DrawingPlan(size,BG); metrics=[]
    def label(text,x,y,n=TYPE['label'],width=None):
        from worker.overlays import body_fonts
        paste_text(im,centered_text(body_fonts(),text,n,width or w*.4),x,y)
    def put(it,cx,ground,n,caption=True):
        sp,mask=sprite(it.shape,it.color,round(n))
        x,y=round(cx-sp.width/2),round(ground-sp.height)
        from worker.celestial import fit
        sp,x,y=fit(sp,x,y,size,it.shape)
        from worker.beat_animation import transform
        sp,x,y=transform(sp,x,y,it,size)
        from app.semantic_bands import place
        x,y=place(sp,x,y,it,visual,size)
        mask=sp.getchannel("A")
        im.paste(sp,(x,y),sp)
        metrics.append(dict(shape=it.shape,role=it.role,pixel_mask=mask,lighting_declaration=for_sprite(sp),bbox=(x,y,sp.width,sp.height)))
        # W38 object labels are composed by frame().
    by_shape={it.shape:it for it in visual.items}
    if visual.layout=='narration':
        gy=h*(650/1280 if portrait else 480/720)
        sun=(w*.17,gy-105,120 if portrait else 150)
        earth=(w*.51,gy-85,260 if portrait else 270)
        put(by_shape['sun'],sun[0],sun[1]+sun[2]/2,sun[2])
        # The registered axis and rays attach to the globe, rather than consume cells.
        earth_box=globe(im,earth,-80+t/16000*360,sun=sun)
        metrics.append(dict(shape='earth',bbox=earth_box,lighting_declaration=im.last_globe_declaration,pixel_mask=im.last_globe_mask))
        for shape in ('rotation_axis','sun_ray'):metrics.append(dict(shape=shape,attached_to='earth'))
        # Earth label is composed by frame().
        put(by_shape['moon'],w*(.24 if portrait else .84),h*(950/1280 if portrait else 225/720),110 if portrait else 90,portrait)
        cx=w*(.79 if portrait else .87);ground=h*(1000/1280 if portrait else 570/720);n=230 if portrait else 240;target=earth[:2]
    else:
        subjects=[it for it in visual.items if it.role=='subject']
        axis=by_shape['timeline_axis'];ticks=axis.label.split('|')
        if len(subjects)!=len(ticks):
            from app.enforcement import blocks
            if blocks([dict(code='TIMELINE_LABEL',scene=index,object='timeline_axis',measured=dict(subjects=len(subjects),labels=len(ticks)),threshold='one label per subject')], 'render_declaration'):
                raise ValueError('TIMELINE_LABEL count mismatch')
        # Missing labels remain blank; warn never invents replacement claims.
        ticks=ticks+['']*max(0,len(subjects)-len(ticks))
        xs=[w*(.15+.705*j/max(1,len(subjects)-1)) for j in range(len(subjects))]
        ground=h*(580/1280 if portrait else 390/720)
        ys=[ground-j*(25 if portrait else 15) for j in range(len(subjects))]
        d=ImageDraw.Draw(im);d.line((w*.055,ys[0]+6,w*.95,ys[-1]-6),fill=INK,width=DESIGN_STROKE['body'])
        for it,x,y,tick in zip(subjects,xs,ys,ticks):
            d.line((x,y-5,x,y+12),fill=INK,width=DESIGN_STROKE['body'])
            n=142 if portrait else 205
            put(it,x,y+6*n/160,n,False)
            # Object labels use the shared safe screen-space compositor.
        metrics.append(dict(shape='timeline_axis',labels=ticks))
        cx=w*.20;ground=h*(960/1280 if portrait else 615/720);n=225 if portrait else 180;target=(xs[min(1,len(xs)-1)],ys[min(1,len(ys)-1)]-80)
    if 'awen' in by_shape:
        it=by_shape['awen'];direction=(target[0]-cx,target[1]-(ground-n*.4))
        sp,mask,eyes=pointing_awen(round(n),direction)
        x,y=round(cx-sp.width/2),round(ground-sp.height)
        if not visual.poses and visual.camera_motion is None:im.paste(sp,(x,y),sp)
        metrics.append(dict(shape='awen',lighting_declaration=for_sprite(sp),bbox=(x,y,sp.width,sp.height),gaze_target=it.gaze_target))
    return im,dict(objects=metrics,ray_gaps=[],content_bottom=ground)
