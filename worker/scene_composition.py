from PIL.ImageColor import getrgb as design_rgb
from worker.design_tokens import PALETTE
from worker.design_tokens import PALETTE, STROKE as DESIGN_STROKE, RADIUS as DESIGN_RADIUS
from worker.design_tokens import PALETTE, STROKE, LAYOUT
from worker.raster_cache import raster_cache
from app.response_assembly import required_first
from worker.lighting_declaration import for_sprite
from worker.drawing_plan import DrawingPlan
"""Shared-stage orchestration; frozen B2/O1 sprite implementations are untouched."""
import math
from collections import Counter
from PIL import Image, ImageDraw


from functools import lru_cache


@raster_cache(maxsize=128)
def _material_rgb(size, pixels):
    """Reuse exact sprite properties across frames and consecutive sentences."""
    image=Image.frombytes('RGBA',size,pixels)
    colors=[(count,color[:3]) for count,color in image.getcolors(size[0]*size[1])
            if color[3]==255 and sum(color[:3])>180]
    if not colors:return []
    maximum=max(count for count,color in colors)
    tied={color for count,color in colors if count==maximum}
    if len(tied)==1:return [(required_first((iter(tied)), path='worker/worker/scene_composition.py:21'),maximum)]
    # Match Counter's first-observed tie ordering, without changing base color.
    color=required_first(((p[:3] for p in image.get_flattened_data() if p[3]==255 and p[:3] in tied)), path='worker/worker/scene_composition.py:23')
    return [(color,maximum)]


def stage(visual, size, index, t=0, duration_ms=2200):
    from worker.scenekit_renderer import sprite, BG, INK, _stage_fonts
    from worker.shapes_o1 import awen_sprite
    from worker.visual import paste_text, centered_text
    from app.container_semantics import validate_parents
    validate_parents(visual.items)
    w, h = size
    im = DrawingPlan(size, BG)
    d = ImageDraw.Draw(im)
    bg = visual.background
    has_river = any(it.shape == "river" for it in visual.items)
    horizon, ground = round(h*.55), round(h*(.64 if has_river else .76))
    from worker.expression_scene import channels
    if channels(visual.expression)[0]:
        horizon = ground
    # Ground commands follow the semantic far plane inserted after layout resolves.
    from worker.size_semantics import furniture_allowed, NARRATION
    if furniture_allowed(NARRATION.get()):
        d.rectangle((0, horizon, w, h), fill=PALETTE['ground'])
    # Environmental silhouettes are separate from labeled teaching objects.
    if furniture_allowed(NARRATION.get()):
        d.line((0,horizon,w,horizon),fill=STROKE['color'],width=STROKE['decoration'])
    from worker.expression_scene import channels
    contract_surfaces, contract_region = channels(visual.expression)
    if not furniture_allowed(NARRATION.get()):
        pass
    elif contract_surfaces:
        pass  # The declared receiver replaces the implicit support, once.
    elif bg['support'] != 'ground':
        d.polygon([(w*.04,ground-h*.10),(w*.94,ground-h*.10),(w*.98,ground+h*.035),(w*.02,ground+h*.035)],fill=PALETTE['ground'],outline=INK)
        d.rectangle((w*.02,ground+h*.035,w*.98,ground+h*.06),fill=PALETTE['accent'])
        for x in (.08,.89):
            d.rectangle((w*x,ground+h*.06,w*(x+.025),h*.88),fill=PALETTE['neutral_600'])
    elif has_river:
        d.rectangle((0,ground,w,h),fill=PALETTE['neutral_600'])
    else:
        support=sprite('ground','green',round(w*.94))[0].resize((round(w*.94),round(h*.10)))
        im.paste(support,(round(w*.03),ground-round(h*.034)),support)
    teaching = [(i,it) for i,it in enumerate(visual.items) if it.parent is None and it.shape != 'awen' and (it.shape not in {'arrow','curved_arrow'} or (it.from_ is None and it.to is None)) and it.action != 'fall']
    kinds = {it.shape for _,it in teaching}
    shared_tank = kinds == {'tank_stone','tank_wood'}
    # Independent route IDs need independent sprites and action transforms.
    # A composite painted once cannot obey two solved bboxes.
    shared_routes = False
    copies = sum(1 if it.shape == 'water' else it.count for _,it in teaching)
    cell_band = .58 if copies <= 2 else .44
    n = round(min(h*.51,w*.53)) if shared_tank or shared_routes else round(min(h*.45,w*cell_band/max(2,copies)))
    metrics, positions, pending_labels = [], {}, []
    def put(sp, x, y, names, label):
        command_start = len(im.commands)
        from worker.ambient import sprite as animate
        sp = animate(sp, names[0][1].shape)
        from worker.celestial import fit
        placement=names[0][1].placement.get('16x9' if w>=h else '9x16')
        if placement is not None:
            x,y=x+round(placement[0]*w),y+round(placement[1]*h)
        sp,x,y=fit(sp,x,y,size,names[0][1].shape)
        from worker.beat_animation import transform
        sp,x,y=transform(sp,x,y,names[0][1],size)
        # Reserve the observer band once, before the scene layout is cached.
        if (not names[0][1].animation_state and names[0][1].comparison
                and w < h and any(it.shape == 'awen' for it in visual.items)):
            observer_height = awen_sprite(round(h*.26))[0].height
            y = min(y, ground-observer_height-24-sp.height)
        from app.geometry_healing import normalize_sprite
        sp,x,y=normalize_sprite(sp,x,y,size,names[0][1].shape)
        from app.semantic_bands import place
        x,y=place(sp,x,y,names[0][1],visual,size)
        sw,sh=sp.size
        from worker.depth_measure import contour_width
        depth_stroke = contour_width(sp, design_rgb(PALETTE['neutral_900']))
        material_rgb = _material_rgb(sp.size,sp.convert("RGBA").tobytes())
        # Projection to lower-right establishes the upper-left light direction.
        d=ImageDraw.Draw(im)
        if furniture_allowed(NARRATION.get()) and not any(it.shape in {'sun','cloud','rain','drop','river'} for _,it in names):
            d.ellipse((x+sw*.10,y+sh-4,x+sw*1.04,y+sh+h*.022),fill=PALETTE['neutral_600'])
        im.paste(sp,(x,y),sp)
        if label:
            pending_labels.append((len(metrics), label))
        for i,it in names:
            positions[i]=(x+sw/2,y+sh*.50)
            metrics.append(dict(sentence=(it.animation_state or {}).get('frame_sentence', 1),depth_stroke=depth_stroke, material_rgb=material_rgb[0][0] if material_rgb else None, raster_fit=sp.info.get('raster_fit'), id=it.id or str(i), parent=it.parent, item_index=i, causal_role=it.causal_role, scale=it.scale, position=it.position, layer='back' if it.shape in {'sun','cloud'} and it.role!='subject' else 'mid', depth=it.depth, shape=it.shape,semantic_label=it.label,bbox=(x,y,sw,sh),pixel_mask=sp.getchannel('A'),lighting_declaration=for_sprite(sp),ground=ground,ground_error_px=abs(y+sh-ground),spatial_frame=visual.spatial_frame,shadow=it.shape not in {'sun','cloud','rain','drop','river'},contact_line=it.shape=='river',flying=it.shape in {'sun','cloud','rain','drop'},motion_vector=(0,1) if it.samples or it.action=='fall' else None,role=it.role,container="tank" if shared_tank else "routes" if shared_routes else None))
            if visual.expression:
                metrics[-1].update(_commands=(command_start, len(im.commands)), _sprite=sp.copy())
            if 'inner_rect' in sp.info:
                iw0,ih0=sp.info.get('inner_size',sp.size)
                ix,iy,iw,ih=sp.info['inner_rect']
                metrics[-1]['inner_rect']=(x+ix*sw/iw0,y+iy*sh/ih0,iw*sw/iw0,ih*sh/ih0)
    if shared_tank:
        from worker.scenekit_shapes import b3_frozen_sprite
        subject = required_first(((it for _,it in teaching if it.shape == 'tank_stone')), path='worker/worker/scene_composition.py:96')
        phase = subject.phase or 'bottom'
        # The same stone travels through one tank. No narrative/index heuristics.
        progress = min(1, max(0, t / max(duration_ms, 1)))
        stone_y = {'surface': .20 + .16*progress, 'sinking': .36 + .30*progress, 'bottom': .66}[phase]
        stone = b3_frozen_sprite('tank_stone','gray',n,stone_y=stone_y)[0].copy()
        wood = sprite('tank_wood','brown',n)[0]
        # Copy only the wood region; never erase the moving stone on the left.
        box = (round(n*.46),round(n*.25),round(n*.90),round(n*.49))
        stone.paste(wood.crop(box),box[:2])
        x,y=round(w*.62-stone.width/2),ground-stone.height
        put(stone,x,y,teaching,'')
        metrics[0]['phase'] = phase
        metrics[0]['stone_y'] = stone_y
    elif shared_routes:
        long = sprite('route_long','brown',n)[0].copy()
        short = sprite('route_short','green',n)[0]
        assert long.size == short.size
        long.alpha_composite(short)
        x,y=round(w*.62-long.width/2),ground-long.height
        put(long,x,y,teaching,'同一起点 · 同一终点')
    else:
        expanded=[(i,it) for i,it in teaching for _ in range(1 if visual.expression or it.shape == 'water' else it.count)]
        expanded.sort(key=lambda pair: pair[1].position//3 if pair[1].position is not None else 2)
        expanded.sort(key=lambda pair: pair[1].shape == 'river')
        for j,(i,it) in enumerate(expanded):
            if it.shape == 'river':
                from worker.shapes_b4 import sprite as nature_sprite
                sp=nature_sprite('river',it.color,round(w*.80),height=round(h*.22))[0]
                put(sp,round(w*.08),round(h*.68),[(i,it)],it.label)
                continue
            diameter = n  # Native raster resolution; final area is semantic.
            sp=sprite(it.shape,it.color,diameter,it.mood,it.state,polarity=it.polarity)[0].copy()
            if visual.expression and not channels(visual.expression)[1]:
                available = ground-h*LAYOUT['content_top']
                if sp.height > available:
                    factor = available/sp.height
                    sp = sp.resize((round(sp.width*factor),round(available)), Image.Resampling.LANCZOS)
            if it.shape == 'water':
                # A continuous body expands with quantity; it is never a grid of vessels.
                width = min(round(w*(1-2*LAYOUT['safe'])), round(sp.width*math.sqrt(it.count)))
                sp = sp.resize((max(1,width),sp.height),Image.Resampling.LANCZOS)
            elif visual.expression and it.count > 1:
                # A reference identifies the group; copies occupy separate cells
                # inside it, so actions and relations still use one stable ID.
                columns = math.ceil(math.sqrt(it.count))
                rows = math.ceil(it.count/columns)
                extent = min(round(diameter*LAYOUT['group_scale']), round(ground-h*LAYOUT['content_top']))
                gap = LAYOUT['gap']
                cell = max(1, (extent-(columns-1)*gap)//columns)
                factor = min(cell/sp.width,cell/sp.height)
                tile = sp.resize((max(1,round(sp.width*factor)),max(1,round(sp.height*factor))),Image.Resampling.LANCZOS)
                group = Image.new('RGBA',(columns*cell+(columns-1)*gap,rows*cell+(rows-1)*gap))
                for copy in range(it.count):
                    gx=(copy%columns)*(cell+gap)+(cell-tile.width)//2
                    gy=(copy//columns)*(cell+gap)+(cell-tile.height)//2
                    group.paste(tile,(gx,gy),tile)
                sp=group
            sp.info['inner_size']=sp.size
            if it.role == 'subject' and it.shape != 'water' and sp.height < h*.18:
                factor=h*.18/sp.height
                sp=sp.resize((round(sp.width*factor),math.ceil(h*.18)),Image.Resampling.LANCZOS)
            if it.shape in {'sun','cloud'} and it.role != 'subject':
                factor=min(1,h*.125/sp.height)
                sp=sp.resize((round(sp.width*factor),round(sp.height*factor)),Image.Resampling.LANCZOS)
            base_size=sp.size
            if it.depth:
                factor=.75**it.depth
                sp=sp.resize((max(1,round(sp.width*factor)),max(1,round(sp.height*factor))),Image.Resampling.LANCZOS)
            cx=w*LAYOUT['columns'][j % len(LAYOUT['columns'])]
            bottom = ground
            if it.position is not None or it.samples:
                from worker.logic_w24 import progress as sample_progress
                if it.samples:
                    # Interpolate the grid's two axes, including diagonal motion.
                    f=min(1,max(0,t/max(duration_ms,1)))
                    pair=next(((a,b) for a,b in zip(it.samples,it.samples[1:]) if f<=b.at),(it.samples[-2],it.samples[-1]))
                    a,b=pair; q=min(1,max(0,(f-a.at)/(b.at-a.at)))
                    col=a.position%3+(b.position%3-a.position%3)*q
                    row=a.position//3+(b.position//3-a.position//3)*q
                else: col,row=it.position%3,it.position//3
                cx = w*(LAYOUT['columns'][0] + (LAYOUT['columns'][1]-LAYOUT['columns'][0])*col)
                bottom = h*(LAYOUT['rows'][0] + (LAYOUT['rows'][1]-LAYOUT['rows'][0])*row)
            if it.shape == 'sun':
                cx=w*(LAYOUT['safe']+.04); bottom=h*.29
            if it.shape == 'ground':
                sp=sp.resize((sp.width,round(h*.06)))
            # Keep the requested grid and scale, reserving the title and label band.
            bottom=max(h*LAYOUT['content_top']+sp.height,bottom)
            cx=max(sp.width/2+w*LAYOUT['safe'],min(w*(1-LAYOUT['safe'])-sp.width/2,cx))
            x,y=round(cx-sp.width/2),round(bottom-sp.height)
            # Two 4px endpoint gaps leave at least 80% of a 40px box gap.
            gap=40 if any(item.shape in {"arrow","curved_arrow"} for item in visual.items) else 24
            # Resolve collisions in pixel space, keeping the nearest free vertical slot.
            if not it.animation_state:
                occupied=[m['bbox'] for m in metrics]
                def free(top):
                    return all(math.hypot(max(x-px-pw,px-x-sp.width,0),max(top-py-ph,py-top-sp.height,0))>=gap for px,py,pw,ph in occupied)
                candidates=[y,round(h*LAYOUT['content_top']),round(ground-sp.height)]
                for px,py,pw,ph in occupied:
                    candidates.extend([math.ceil(py+ph+gap),math.floor(py-gap-sp.height)])
                valid=[top for top in candidates if top>=h*LAYOUT['content_top'] and top+sp.height<=ground and free(top)]
                if valid:y=min(valid,key=lambda top:abs(top-y))
            put(sp,x,y,[(i,it)],it.label)
            metrics[-1]['base_size']=base_size
    # Children are placed in parent coordinates, after every vessel is positioned.
    for i,it in enumerate(visual.items):
        if it.parent is None:continue
        command_start = len(im.commands)
        parent=required_first(((m for m in metrics if m['id']==it.parent)), path='worker/worker/scene_composition.py:183')
        ix,iy,iw,ih=parent['inner_rect']
        sp=sprite(it.shape,it.color,round(min(iw,ih)*.70),it.mood,it.state,polarity=it.polarity)[0]
        if it.role=='subject' and sp.height<h*.18:
            factor=h*.18/sp.height
            sp=sp.resize((round(sp.width*factor),math.ceil(h*.18)),Image.Resampling.LANCZOS)
        siblings=[child for child in visual.items if child.parent==it.parent]
        slot=required_first(((j for j,child in enumerate(siblings) if child is it)), path='worker/worker/scene_composition.py:190')
        cx=ix+iw*(slot+.5)/len(siblings)
        x,y=round(cx-sp.width/2),round(iy+ih-sp.height)
        if it.shape in {'stone','wood'} and it.phase:
            fraction=min(1,max(0,t/max(duration_ms,1)))
            progress={'surface': .0+.35*fraction, 'sinking': .35+.65*fraction, 'bottom': 1.}[it.phase]
            if it.shape=='wood':progress=0.
            y=round(iy+max(0,ih-sp.height)*progress)
        px,py=it.placement.get('16x9' if w>=h else '9x16',(0,0))
        x+=round(px*w);y+=round(py*h)
        from worker.celestial import fit
        sp,x,y=fit(sp,x,y,size,it.shape)
        from worker.beat_animation import transform
        sp,x,y=transform(sp,x,y,it,size)
        bottom=iy+ih
        contact=abs(y+sp.height-bottom)<=4
        container_shadow=None
        if not contact and it.shape in {'stone','wood'}:
            left=max(ix,x);right=min(ix+iw,x+sp.width)
            if right>left:
                container_shadow=(left,bottom-3,right-left,3)
                ImageDraw.Draw(im).ellipse((left,bottom-3,right,bottom),fill=PALETTE['ground'])
        if contact:
            ImageDraw.Draw(im).line((max(ix,x),bottom,min(ix+iw,x+sp.width),bottom),fill=INK,width=DESIGN_STROKE['decoration'])
        im.paste(sp,(x,y),sp)
        positions[i]=(x+sp.width/2,y+sp.height/2)
        if it.label:pending_labels.append((len(metrics),it.label))
        metrics.append(dict(raster_fit=sp.info.get('raster_fit'),id=it.id or str(i),item_index=i,parent=it.parent,shape=it.shape,
            role=it.role,bbox=(x,y,*sp.size),pixel_mask=sp.getchannel('A'),lighting_declaration=for_sprite(sp),ground=bottom,
            ground_error_px=abs(y+sp.height-bottom),contact_line=contact,shadow=False,container_shadow_bbox=container_shadow,
            layer='mid',depth=0,scale=it.scale,position=it.position,causal_role=it.causal_role))
        if visual.expression:
            metrics[-1].update(_commands=(command_start, len(im.commands)), _sprite=sp.copy())
    for i,it in enumerate(visual.items):
        if it.shape != 'awen':continue
        an=round(h*.26)
        sp,mask,eyes=awen_sprite(an)
        ax=round(w*.19-sp.width/2)
        target=positions.get(it.gaze_target)
        ay=ground-sp.height
        if it.placement.get('16x9' if w>=h else '9x16') is not None:
            px,py=it.placement['16x9' if w>=h else '9x16']
        else:px,py=0,0
        eye=(ax+round(px*w)+eyes['eye'][0],ay+round(py*h)+eyes['eye'][1])
        direction=(target[0]-eye[0],target[1]-eye[1]) if target else (1,0)
        sp,mask,eyes=awen_sprite(an,direction)
        # Observer stands on a continuous extension of the same support plane.
        command_start=len(im.commands)
        put(sp,ax,ay,[(i,it)],'' if visual.poses or visual.camera_motion is not None else it.label)
        if visual.poses or visual.camera_motion is not None:del im.commands[command_start:]
        metrics[-1]['gaze']=dict(eye=eye,target=target,angle_degrees=math.degrees(math.atan2(-direction[1],abs(direction[0])))) if target else None
    from worker.expression_scene import compose
    compose(im, metrics, visual, size, ground, t, duration_ms)
    from worker.composition_b5 import place_labels, violations as grammar_violations
    from worker.depth import backdrop
    far_commands, rear = backdrop(visual, size, horizon, metrics)
    im.commands[0:0] = far_commands
    labels = []  # W38 screen-space labels are composed by frame().
    light_rays=[]
    sun=next((m for m in metrics if m['shape']=='sun'),None)
    receiver=next((m for m in metrics if m['shape'] in {'river','earth'}),None)
    if sun and receiver:
        x,y,sw,sh=sun['bbox']; tx,ty,tw,th=receiver['bbox']
        start=(x+sw*.65,y+sh*.96)
        end=(tx+tw*.48,ty+th*.55)
        ImageDraw.Draw(im).line((start,end), fill=PALETTE['accent'],width=DESIGN_STROKE['body'])
        light_rays.append(dict(source=sun['id'],target=receiver['id'],start=start,end=end))
    from worker.subject_geometry import violations
    errors=violations(metrics,size,index,frame_ms=t)
    result=dict(scene=index,objects=metrics, labels=labels, rear_objects=rear,
                horizon=horizon, planes=['sky','ground'], rendered_light_direction='upper_left', light_direction=bg.get('light','upper_left'),
                light_relations=[dict(source=sun['id'],target=receiver['id'])] if sun and receiver else [],
                light_rays=light_rays, ray_gaps=[],content_bottom=max(ground+h*.06,max(m['bbox'][1]+m['bbox'][3] for m in metrics)),
                background=bg,spatial_frame=visual.spatial_frame,element_count=sum(it.count for it in visual.items))
    from worker.logic_w24 import connections
    result['arrows'], result['transfers'] = connections(im, visual, metrics, min(1,max(0,t/max(duration_ms,1))), scene=index)
    errors += grammar_violations(result,size)
    result['violations']=errors
    from app.enforcement import blocks
    if blocks(errors, 'frame'):
        from worker.scenekit_renderer import SceneRenderError
        failure=SceneRenderError(index,'scene','geometry',str(errors))
        failure.metrics=result
        raise failure
    return im,result
