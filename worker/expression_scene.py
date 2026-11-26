"""Relation constraints and explicitly declared surfaces, applied after motion."""
from PIL import Image, ImageDraw, ImageChops, ImageColor
from worker.design_tokens import PALETTE, STROKE, RADIUS, SHADOW, TYPE, LAYOUT, OPACITY
from app.relation_migration import migrate


def channels(expression):
    if not expression: return set(), None
    graph = migrate(expression)
    return set(graph['render'].get('surfaces', [])), None


def solve(boxes, baseline, expression, size, ground):
    """Retain grid positions except where explicit constraints take precedence."""
    expression = migrate(expression)
    expression['relation'] = [r for r in expression['relation'] if isinstance(r,dict) and not r.get('degraded')]
    boxes = {k: list(v) for k, v in boxes.items()}
    surfaces, region = channels(expression)
    w,h = size
    for ref in surfaces & boxes.keys():
        boxes[ref] = [0, round(ground), w, h-round(ground)]
    links = {}
    for r in expression['relation']:
        if r['type'] in {'rests_on', 'attached_to'}:
            links.setdefault(r['from'], []).append(r)
    done, visiting = set(), set()
    supported = {}
    def visit(ref):
        if ref in done or ref in visiting or ref not in boxes: return
        visiting.add(ref)
        for r in sorted(links.get(ref, []), key=lambda r: r['type'] == 'rests_on'):
            target = r['to']
            if target not in boxes or target in visiting: continue
            visit(target)
            x,y,bw,bh = boxes[ref]; tx,ty,tw,th = boxes[target]
            if r['type'] == 'attached_to':
                a = baseline.get(target, boxes[target])
                b = baseline.get(ref, boxes[ref])
                boxes[ref][:2] = [tx+tw, max(ty, min(b[1]+ty-a[1],ty+th-bh))]
            else:
                factor = min(1., tw/max(bw,1))
                bw,bh = max(1,round(bw*factor)),max(1,round(bh*factor))
                x = max(tx, min(x,tx+tw-bw))
                # Collapsing different grid rows onto one support must not hide
                # one supported entity behind another in the same column.
                peers = supported.setdefault(target, [])
                candidates = [x] + [edge for px,pw in peers for edge in (px-bw-24, px+pw+24)]
                free = [cx for cx in candidates if tx <= cx <= tx+tw-bw
                        and all(cx+bw+24 <= px or cx >= px+pw+24 for px,pw in peers)]
                if free:
                    x = min(free, key=lambda cx: abs(cx-x))
                boxes[ref] = [x, ty-bh, bw,bh]
                peers.append((x,bw))
        visiting.remove(ref); done.add(ref)
    for ref in boxes: visit(ref)
    config = expression['render']
    light_ref = config.get('light_ref')
    position = config.get('light_position')
    if light_ref in boxes and isinstance(position,(list,tuple)) and len(position)==2:
        import math
        if all(isinstance(v,(int,float)) and math.isfinite(v) for v in position):
            cx,cy = position[0]*w,position[1]*h
            endpoint = next((r['from'] for r in expression['relation'] if r['type']=='casts_on'), None)
            if config.get('light_alignment') == 'overhead' and endpoint in boxes:
                a = boxes[endpoint]; cx = a[0]+a[2]/2
            _,_,bw,bh = boxes[light_ref]
            boxes[light_ref] = [cx-bw/2,cy-bh/2,bw,bh]
    return {k: tuple(round(v) for v in box) for k,box in boxes.items()}


def compose(plan, objects, visual, size, ground, t=0, duration_ms=1):
    expression = visual.expression
    if not expression: return
    expression = migrate(expression)
    drawing_expression = expression
    expression = dict(expression, relation=[r for r in expression['relation'] if not r.get('degraded')])
    surfaces, region = channels(expression)
    from app.ledger_shapes import is_light_source
    sources = {s['ref'] for s in expression['subject'] if is_light_source(s.get('identity',''))}
    sources.update([expression['render']['light_ref']] if isinstance(expression['render'].get('light_ref'), str) else [])
    items = {it.id:it for it in visual.items}
    for obj in objects:
        if obj['id'] in items:
            obj['label'] = items[obj['id']].label
    boxes = {o['id']: o['bbox'] for o in objects}
    baseline = {}
    for obj in objects:
        event = items[obj['id']].animation_state or {}
        baseline[obj['id']] = items[obj['id']].relation_base_bbox or event.get('relation_base_bbox', event.get('start_bbox', event.get('fixed_bbox', obj['bbox'])))
    solved = solve(boxes, baseline, expression, size, ground)
    removed = {i for o in objects for i in range(*o.get('_commands', (0,0)))}
    tiles = {}
    symbols = [o for o in objects if o['shape'] == 'diagram_box'
               and o['id'] not in surfaces and o['id'] != region]
    positioned = {expression['render'].get('light_ref')} if expression['render'].get('light_position') is not None else set()

    from app.semantic_bands import resolve, project
    for obj in objects:
        evidence = resolve(items[obj['id']], visual)
        obj['semantic_band'] = evidence
        solved[obj['id']] = project(solved[obj['id']], evidence, size)

    for obj in objects:
        ref = obj['id']
        sp = obj.pop('_sprite', None)
        obj.pop('_commands', None)
        if sp is None: continue
        x,y,bw,bh = solved[ref]
        if obj in symbols and ref not in positioned and not any(
                r['from']==ref and r['type'] in {'rests_on','attached_to','inside'}
                for r in expression['relation']):
            # Free symbolic actors reserve the same content band during scaling.
            # Relations and phenomenon solving remain in their original space.
            left=round(size[0]*LAYOUT['safe'])
            top=round(size[1]*LAYOUT['content_top'])
            right=round(size[0]*(1-LAYOUT['safe']))
            bottom=round(size[1]*LAYOUT['rows'][-1])
            factor=min(1,(right-left)/bw,(bottom-top)/bh)
            bw,bh=round(bw*factor),round(bh*factor)
            x=max(left,min(x,right-bw));y=max(top,min(y,bottom-bh))
        support = next((r['to'] for r in expression['relation']
                        if r['type'] == 'rests_on' and r['from'] == ref), None)
        # Solve the visible contour, not a transparent sprite canvas.
        ink = sp.getchannel('A').getbbox()
        if support in solved and ink:
            sp = sp.crop(ink)
        sp = sp.resize((max(1,bw),max(1,bh)), Image.Resampling.LANCZOS)
        obj['bbox'] = (x,y,bw,bh)
        obj['relation_base_bbox'] = baseline[ref]
        obj['shadow'] = (ref not in sources and ref not in surfaces and ref != region
                         and not obj.get('flying')
                         and (obj['shape'] != 'diagram_box' or support is not None))
        obj['attached_to'] = next((r['to'] for r in expression['relation']
                                   if r['type']=='attached_to' and r['from']==ref), None)
        if ref in surfaces:
            # One continuous receiver; top edge is the contact coordinate.
            from worker.visual import COLORS
            sp = Image.new('RGBA', (bw,bh), PALETTE['ground'])
            obj['render_channel'] = 'surface'
        if ref not in surfaces and ref != region:
            from worker.visual_style import solid
            sp = solid(sp)
            from worker.lighting_declaration import unlit
            obj['lighting_declaration'] = unlit(obj['shape'],sp)
            obj['depth_stroke'] = STROKE['body']
        if ref not in surfaces and ref != region and obj['shape'] == 'diagram_box':
            anchor = next((r['to'] for r in expression['relation'] if r['from']==ref
                           and r['type'] in {'attached_to','rests_on','inside'}), None)
            obj['symbol_position_source'] = (dict(kind='object', object=anchor) if anchor else
                dict(kind='scene_coordinates', bbox=[x,y,bw,bh], coordinate_system='canvas', source=ref))
            # Text is painted once in screen space by overlays.labels, which
            # owns the title and every item-label entrance's shared registry.
            obj['inline_label'] = True
            obj['symbol_label'] = items[ref].label
        if ref in sources:
            obj['symbol_position_source'] = dict(kind='scene_coordinates', bbox=[x,y,bw,bh],
                                                coordinate_system='canvas', source=ref)
        obj['pixel_mask'] = sp.getchannel('A')
        support = next((r['to'] for r in expression.get('relation', []) if r['type']=='rests_on' and r['from']==ref), None)
        if support in solved:
            obj.update(rests_on=support, ground=solved[support][1], ground_error_px=abs(y+bh-solved[support][1]),
                       contact_line=y+bh==solved[support][1],
                       visible_bottom_y=y+(sp.getchannel('A').getbbox() or (0,0,0,bh))[3])
        tiles[ref] = sp
    # Prepare replacement commands with original endpoint geometry intact.
    # Nothing is removed until the replacement has passed both checks.
    from worker.drawing_plan import DrawingPlan
    from worker.phenomenon import draw, replacement_sources
    propagation = DrawingPlan(size, plan.background)
    draw(propagation, objects, drawing_expression, min(1,max(0,t/max(1,duration_ms))), duration_ms)
    candidates = set(expression['render'].get('carriers', [])) | {
        s['ref'] for s in expression['subject'] if s.get('representation') == 'propagation'}
    accepted = replacement_sources(objects, candidates, size)
    original_masks = {o['id']: o.get('pixel_mask') for o in objects}
    originals = {o['id']: dict(o) for o in objects}
    original_tiles = dict(tiles)
    for obj in objects:
        ref = obj['id']
        if ref not in candidates: continue
        if ref in accepted:
            obj.update(visible=False, shadow=False, render_channel='propagation',
                       pixel_mask=Image.new('L', tuple(max(1,round(v)) for v in obj['bbox'][2:])))
            tiles.pop(ref, None)
        else:
            from app.degradation import degrade
            note = degrade('PROPAGATION_NO_GEOMETRY', dict(object=ref), 'retain original entity')
            obj.setdefault('craft_notes', []).append(note)
    # Recheck the actual final pass, not just the prepared path declaration.
    # If any path disappears, restore its original entity before emitting tiles.
    while True:
        propagation.commands.clear()
        endpoints = [dict(o, pixel_mask=original_masks[o['id']]) for o in objects]
        draw(propagation, endpoints, drawing_expression, min(1,max(0,t/max(1,duration_ms))), duration_ms)
        for obj, endpoint in zip(objects, endpoints):
            obj['phenomenon_geometry'] = endpoint.get('phenomenon_geometry', {})
        rejected = accepted - replacement_sources(objects, accepted, size)
        if not rejected: break
        for obj in objects:
            ref = obj['id']
            if ref not in rejected: continue
            obj.clear(); obj.update(originals[ref])
            if ref in original_tiles: tiles[ref] = original_tiles[ref]
            from app.degradation import degrade
            obj.setdefault('craft_notes', []).append(degrade(
                'PROPAGATION_NO_GEOMETRY', dict(object=ref), 'retain original entity'))
        accepted -= rejected
    # Commit command replacement only after geometry and rollback are settled.
    plan.commands = [c for i,c in enumerate(plan.commands) if i not in removed]
    order = [o for o in objects if o['id'] in surfaces]
    order += [o for o in objects if o['id'] == region]
    order += [o for o in objects if o['id'] not in surfaces and o['id'] != region]
    for obj in order:
        ref = obj['id']
        if ref not in tiles: continue
        sp = tiles[ref]
        x,y,bw,bh = obj['bbox']
        if obj.get('shadow'):
            from worker.visual_style import cast
            cast(plan,sp,(x,y))
        plan.paste(sp, (x,y), sp)
    plan.commands.extend(propagation.commands)
    from worker.relation_geometry import measure
    for row in measure(expression['relation'], order):
        obj = next((o for o in objects if o['id'] == row['relation']['from']), None)
        if obj is not None: obj.setdefault('relation_measurements', []).append(row)


def project_actions(objects, rows, expression, size):
    """The same solved endpoints drive drawing and action evidence."""
    if not expression: return objects, rows
    from copy import deepcopy
    rows = deepcopy(rows)
    baseline = {o['id']:o['bbox'] for o in objects}
    for row in rows:
        for frame in row.get('keyframes', []):
            boxes = dict(baseline)
            boxes[row['subject']] = frame['bbox']
            frame['bbox'] = list(solve(boxes, baseline, expression, size, round(size[1]*.76))[row['subject']])
            from app.semantic_bands import project
            evidence = next((o.get('semantic_band', {'band': None}) for o in objects if o['id'] == row['subject']), {'band': None})
            frame['bbox'] = list(project(frame['bbox'], evidence, size))
        if row.get('keyframes'):
            row['start_bbox'] = row['keyframes'][0]['bbox']
            row['end_bbox'] = row['keyframes'][-1]['bbox']
    return objects, rows
