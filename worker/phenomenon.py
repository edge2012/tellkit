"""Phenomenon channels consume references and geometry, never topic names."""
import math
from PIL import ImageDraw
from worker.design_tokens import PALETTE, PATH, TYPE, LAYOUT, STROKE
from app.relation_migration import migrate


def edge(box, target):
    x,y,w,h = box
    cx,cy = x+w/2,y+h/2
    dx,dy = target[0]-cx,target[1]-cy
    scale = min(w/2/max(abs(dx),1e-9),h/2/max(abs(dy),1e-9))
    return (cx+dx*scale,cy+dy*scale)


def center(obj):
    x,y,w,h = obj['bbox']; return x+w/2,y+h/2


def contour(obj, anchor):
    """Connect to painted contours, not transparent sprite padding."""
    mask = obj.get('pixel_mask')
    if mask is None: return anchor
    x,y,w,h = obj['bbox']; cx,cy = x+w/2,y+h/2
    dx,dy = anchor[0]-cx,anchor[1]-cy
    steps = max(1,math.ceil(max(abs(dx),abs(dy))))
    last = anchor
    entered = False
    for i in range(steps+1):
        px,py = cx+dx*i/steps,cy+dy*i/steps
        mx = min(mask.width-1,max(0,round((px-x)*mask.width/max(1,w))))
        my = min(mask.height-1,max(0,round((py-y)*mask.height/max(1,h))))
        if mask.getpixel((mx,my)) > 32:
            entered = True
            last = (x+mx*w/mask.width,y+my*h/mask.height)
        elif entered:
            # Ignore disconnected drop shadows beyond the painted silhouette.
            break
    if not entered:
        # A grouped silhouette may have transparent space on its center ray.
        # Attach to the nearest painted cell instead of its empty outer box.
        import numpy as np
        yy,xx = np.nonzero(np.asarray(mask)>32)
        if len(xx):
            distances=(x+xx*w/mask.width-anchor[0])**2+(y+yy*h/mask.height-anchor[1])**2
            nearest=int(np.argmin(distances))
            last=(x+int(xx[nearest])*w/mask.width,y+int(yy[nearest])*h/mask.height)
    return last


def route(pen, a, b, color, width, dashed=False):
    """Dash phase is anchored to the source, including the final endpoint."""
    length = math.dist(a, b)
    if not dashed or length == 0:
        pen.line((a, b), fill=color, width=width)
        return
    dash, gap = width*PATH['dash_ratio'], width*PATH['gap_ratio']
    for start in range(0, math.ceil(length), dash+gap):
        end = min(length, start+dash)
        points = [tuple(a[k]+(b[k]-a[k])*d/length for k in (0,1)) for d in (start,end)]
        pen.line(points, fill=color, width=width)
    # A short terminal segment guarantees visible contact even in a dash gap.
    start = max(0, length-dash)
    pen.line((tuple(a[k]+(b[k]-a[k])*start/length for k in (0,1)), b), fill=color, width=width)


def arrow(pen, tip, angle, color, width):
    head = width*PATH['head_ratio']
    pen.polygon([tip]+[(tip[0]-head*math.cos(angle+d),tip[1]-head*math.sin(angle+d))
                      for d in (-PATH['head_angle'],PATH['head_angle'])],fill=color)


def draw(plan, objects, expression, progress, duration_ms=4000):
    expression = migrate(expression)
    by_id = {o['id']:o for o in objects}
    rels = expression['relation']
    if not by_id: return
    geometry = dict(progress=progress, paths=[], projections=[], legends=[])
    for obj in objects: obj['phenomenon_geometry'] = geometry
    config = dict(expression['render'])
    light_ref = config.get('light_ref')
    light = by_id.get(light_ref) if isinstance(light_ref, str) else None
    if light is not None and config.get('light_position') is not None:
        cx,cy = center(light)
        config.update(light_position=[cx/plan.width,cy/plan.height],light_alignment=None)
    paths = []
    for rel in rels:
        if not isinstance(rel,dict): continue
        a,b = by_id.get(rel.get('from')),by_id.get(rel.get('to'))
        if a is None or b is None: continue
        typ = rel['type']
        if typ == 'casts_on' and not rel.get('degraded'):
            from worker.relation_geometry import projection
            patch = projection(a,b,config,plan.size)
            geometry['projections'].append(dict(relation=rel, **patch))
            if patch.get('bbox'):
                x,y,w,h = patch['bbox']
                pen = ImageDraw.Draw(plan)
                pen.ellipse((x,y,x+w-1,y+h-1), fill=PALETTE['neutral_900'])
        elif typ in {'comes_from','goes_to'} or rel.get('degraded'):
            path = dict(rel)
            if typ == 'comes_from': path['from'],path['to'] = path['to'],path['from']
            if path not in paths:
                paths.append(path)
    pen = ImageDraw.Draw(plan)
    for i,path in enumerate(paths):
        source,target = by_id.get(path.get('from')),by_id.get(path.get('to'))
        if source is None or target is None: continue
        if (not source.get('visible',True) and source.get('render_channel') != 'propagation') or not target.get('visible',True): continue
        from app.semantic_bands import relation_ports
        ports = relation_ports(source, target)
        if ports is None:
            a = edge(source['bbox'],center(target)); b = edge(target['bbox'],center(source))
        else:
            a,b = ports
        # Separate reciprocal lanes on the entity boundaries, not in empty space.
        peers = [other for other in paths if {other.get('from'),other.get('to')} == {path.get('from'),path.get('to')}]
        if len(peers) > 1:
            offset = (peers.index(path)-(len(peers)-1)/2)*PATH['lane_gap']
            sy,sh = source['bbox'][1],source['bbox'][3]
            ty,th = target['bbox'][1],target['bbox'][3]
            a = (a[0],max(sy,min(sy+sh,a[1]+offset)))
            b = (b[0],max(ty,min(ty+th,b[1]+offset)))
        a,b = contour(source,a),contour(target,b)
        if not path.get('degraded'):
            a = tuple(a[k]+path.get('start_offset_px',[0,0])[k] for k in (0,1))
            b = tuple(b[k]+path.get('end_offset_px',[0,0])[k] for k in (0,1))
        start, end = path.get('start',0), path.get('end',1)
        # Reserve a visible arrival hold, including very late authored paths.
        if end == 1:
            end -= min(.1,(end-start)*.2)
        q = min(1,max(0,(progress-start)/max(.001,end-start)))
        tip = (a[0]+(b[0]-a[0])*q,a[1]+(b[1]-a[1])*q)
        dashed = i % 2 == 1
        color = PALETTE['primary'] if not dashed else PALETTE['accent']
        width = PATH['secondary'] if dashed else PATH['primary']
        angle = math.atan2(b[1]-a[1],b[0]-a[0])
        # Continuous neutral clearance preserves readability over foreground objects.
        pen.line((a,b), fill=PALETTE['neutral_050'], width=width+2*PATH['halo'])
        route(pen,a,b,color,width,dashed)
        arrow(pen,b,angle,color,width)
        if 0 < q < 1:
            arrow(pen,tip,angle,color,width)
        elapsed = (progress-end)*duration_ms
        pulse = q == 1 and 0 <= elapsed < PATH['arrival_ms']
        if pulse:
            radius = width*(1+PATH['pulse_ratio']*math.sin(math.pi*elapsed/PATH['arrival_ms']))
            pen.ellipse((b[0]-radius,b[1]-radius,b[0]+radius,b[1]+radius),
                        outline=color,width=STROKE['body'])
        geometry['paths'].append(dict(relation=path, source=source['id'],target=target['id'],start=a,end=b,tip=tip,progress=q,arrived=q==1,layer='above_objects', termination='receiver',color=color,style='dashed' if dashed else 'solid',width=width,head_size=width*PATH['head_ratio'],arrival_pulse=pulse,arrival_elapsed_ms=elapsed,arrival_duration_ms=PATH['arrival_ms']))


def replacement_sources(objects, candidates, size):
    """Commit only nonzero, on-canvas paths whose receiver survives replacement.

    Geometry was generated while all original entities were still available.
    A receiver removed by another replacement invalidates that transaction;
    restore its source and repeat until the visibility set is stable.
    """
    by_id = {o['id']: o for o in objects}
    paths = objects[0].get('phenomenon_geometry', {}).get('paths', []) if objects else []
    def valid(path, hidden):
        points = path.get('points', [path.get('start'), path.get('end')])
        target = by_id.get(path.get('target'), {})
        if len(points) < 2 or any(p is None for p in points): return False
        if not all(math.isfinite(v) for p in points for v in p): return False
        if sum(math.dist(a,b) for a,b in zip(points,points[1:])) <= 0: return False
        if not target.get('visible', True) or path.get('target') in hidden: return False
        if path.get('visible') is False: return False
        # Validate actual painted geometry, including clipping, on an isolated mask.
        from PIL import Image
        mask = Image.new('L', size)
        ImageDraw.Draw(mask).line(points, fill=255, width=max(1,round(path.get('width',1))))
        return mask.getbbox() is not None
    accepted = {ref for ref in candidates if any(p.get('source') == ref and valid(p,set()) for p in paths)}
    while True:
        rejected = {ref for ref in accepted if not any(p.get('source') == ref and valid(p,accepted) for p in paths)}
        # A carrier may also receive a different path (e.g. a return lane).
        # Keep that endpoint rather than erasing otherwise valid geometry.
        rejected |= accepted & {p.get('target') for p in paths}
        if not rejected: return accepted
        accepted -= rejected
