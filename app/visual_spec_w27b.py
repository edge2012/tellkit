"""R20–R28/R35–R37 structural checks. Pixel checks live in worker.silhouette_pixels.

Recognition tags belong to the vocabulary, never to a narrator's text label.
A tag is an editorial prerequisite, not proof of child recognition from pixels.
"""
import math
import re
from app.shape_implementations import IMPLEMENTED, W293
from app.comparison import is_comparison
from app.enforcement import comparison_tier
from app.comparison_peers import COMPARISON_ERRORS
from app import visual_thresholds as T

RULE_CODES = {'ARROW_DIRECTION', 'SILHOUETTE_DETAIL', 'ARROW_LENGTH', 'ARROW_ORPHAN', 'CARD_AS_SUBJECT', 'LABEL_OVERLAP', 'LABEL_TOO_MANY', 'COMPARISON_MISSING_PEER', 'LABEL_ORPHAN', 'LABEL_FONT_MIXED', 'SHAPE_UNRECOGNIZABLE', 'UNKNOWN_SHAPE'}

# Compatibility name for semantic callers. The character is excluded by video
# policy, not by render capability; the inventory is still derived in one place.
VOCABULARY = IMPLEMENTED - {'awen'}
# Explicit inventory: adding an implementation does not silently grant recognition.
RECOGNIZABLE = frozenset('''apple bacteria book candy cloud drop heart lightning moon rainbow star sun tooth toothbrush
ape_bent ape_upright boat campfire car child earth grass house human_bent human_standing jar mountain river spear stone_axe tree
foot_left foot_right knife arrow curved_arrow check cross question timeline awen cookie_half cookie_large cookie_small cookie_whole drum ear_section ice_block ice_melting
rain_basin rotation_globe route_long route_short shoe_left shoe_right sugar_grains sugar_solution tank_stone tank_wood vapor_particles water_cup_tall water_cup_wide
stone wood cookie shoe ice ear silhouette_quadruped silhouette_leaning silhouette_upright silhouette_upright_tool timeline_axis water_drop rotation_axis sun_ray rain ground
circle square triangle'''.split())
COMPOSITE_SHAPES = frozenset({'tank_stone', 'tank_wood', 'water_cup_tall', 'water_cup_wide', 'sugar_solution', 'ice_melting', 'ice', 'rain_basin'})
RECOGNIZABLE |= {'tank','cup','bowl','water','diagram_box'}
# These concrete W293 diagrams are recognizable implementations too; derive
# the grant from the backend subset instead of copying its six names here.
RECOGNIZABLE |= W293
TAGS = {s: frozenset({'可识别'}) for s in RECOGNIZABLE}
SILHOUETTES = frozenset('ape_bent ape_upright human_bent human_standing child silhouette_quadruped silhouette_leaning silhouette_upright silhouette_upright_tool'.split())
ARROWS = {'arrow', 'curved_arrow'}


def violation(code, scene, obj, measured, threshold):
    assert code in T.CODES or code in COMPARISON_ERRORS
    return dict(code=code, scene=scene, object=obj.get('id', obj.get('text', obj.get('shape', 'scene'))),
                measured=measured, threshold=threshold, **comparison_tier(code))


def shape_violations(objects, scene=1):
    errors=[]
    for o in objects:
        s=o.get('shape')
        def add(code, measured, threshold):errors.append(violation(code,scene,o,measured,threshold))
        if s not in VOCABULARY:add('UNKNOWN_SHAPE',s,'implemented vocabulary')
        if s not in VOCABULARY or '可识别' not in TAGS.get(s, ()) or o.get('placeholder'):
            add('SHAPE_UNRECOGNIZABLE',s,'vocabulary with 可识别 tag; no placeholder')
        if s in COMPOSITE_SHAPES or (s=='card' and o.get('role')=='subject'):add('CARD_AS_SUBJECT',s,'independent objects; container contents require parent')
        if s in SILHOUETTES and any(o.get(k) for k in ('mood','eyes','mouth','nose','interior_marks')):
            add('SILHOUETTE_DETAIL','interior facial marks','pure silhouette')
    return errors


def comparison_required(layout, narration):
    return layout == 'compare' or is_comparison(narration) or bool(re.search(r'比[^，。；！？]{0,25}(?:重|轻|大|小|多|少|长|短|高|矮|快|慢|远|近)', narration))


def comparison_violations(objects, scene=1, *, layout=None, narration='', size=None, peers=None):
    if layout == 'compare':
        from app.comparison_peers import check_peers
        return check_peers(objects, scene, size=size, peers=peers)
    if not comparison_required(layout,narration):return []
    peers=[o for o in objects if o.get('visible',True) and o.get('role','subject') in {'subject','tool','result'} and o.get('shape') not in ARROWS]
    # Physical support is not a third comparison peer. Compare independently
    # named subject contents, or outer container groups when contents are tools.
    if any(o.get('parent') for o in peers):
        from app.container_semantics import CONTAINERS
        child_subjects=[o for o in peers if o.get('parent') and o.get('role')=='subject']
        peers=([o for o in peers if o.get('role')=='subject' and o.get('shape') not in CONTAINERS]
               if child_subjects else [o for o in peers if not o.get('parent')])
    reasons=[]
    if sum(o.get('count',1) for o in peers)!=2:reasons.append('requires two comparison objects')
    # A vessel containing water is not a separate equal-volume parcel of water.
    if re.search(r'比同样大小的(?:一团)?水',narration) and not any(o.get('shape') in {'water_drop','drop','water'} and not o.get('parent') for o in peers):
        reasons.append('missing referenced equal-volume water peer')
    if len(peers)==2:
        a,b=peers
        if a.get('depth',0)!=b.get('depth',0) or a.get('layer','mid')!=b.get('layer','mid'):reasons.append('different depth planes')
        # Use renderer scale factors: large/normal is only 12%, not a >15% violation.
        factors={'small':.78,'normal':1.,'large':1.12}
        scales=[factors.get(o.get('scale','normal'),1.) for o in peers]
        if max(scales)>min(scales)*1.15+1e-6:reasons.append('declared scale difference >15%')
        if a.get('position') is not None and a.get('position')==b.get('position'):reasons.append('same position')
        if all('bbox' in o for o in peers):
            from worker.composition_b5 import overlaps
            if overlaps(a['bbox'],b['bbox']) and not (a.get('container') and a.get('container')==b.get('container')):reasons.append('occluded peers')
            sizes=[(a['bbox'][axis],b['bbox'][axis]) for axis in (2,3)]
            if any(min(pair)<=0 or max(pair)>min(pair)*1.15+1e-6 for pair in sizes):reasons.append('size difference >15%')
            if size and any(x<0 or y<0 or w<=0 or h<=0 or x+w>size[0] or y+h>size[1] for x,y,w,h in (o['bbox'] for o in peers)):reasons.append('peer outside frame')
    return [dict(violation('COMPARISON_MISSING_PEER',scene,{},reasons,'two visible peers, same depth, size difference <=15%'), geometry=[dict(object=o.get('id', o.get('shape')), bbox=o.get('bbox'), scale=o.get('scale'), depth=o.get('depth')) for o in peers])] if reasons else []


def label_violations(labels, objects, scene=1):
    from worker.composition_b5 import distance, overlaps
    errors=[]; lookup={str(o.get('id')):o for o in objects}
    def add(code,o,value,threshold):errors.append(violation(code,scene,o,value,threshold))
    if len(labels)>4:add('LABEL_TOO_MANY',{},len(labels),4)
    if any(l.get('font_size')!=13 for l in labels):add('LABEL_FONT_MIXED',{},[l.get('font_size') for l in labels],13)
    for l in labels:
        owner=lookup.get(str(l.get('owner')))
        gap=distance(l['bbox'],owner['bbox']) if owner else None
        if gap is None or gap>24:add('LABEL_ORPHAN',l,gap,'bbox distance <=24px, real owner')
        if any(overlaps(l['bbox'],o['bbox']) for o in objects if o is not owner and o.get('id') != (owner or {}).get('parent')):add('LABEL_OVERLAP',l,l['bbox'],'outside every other object bbox')
    return errors


def arrow_violations(arrows, objects, scene=1, *, geometry=True):
    from worker.composition_b5 import distance
    lookup={str(o.get('id')):o for o in objects};errors=[]
    for a in arrows:
        def add(code,v,t):errors.append(violation(code,scene,a,v,t))
        src=lookup.get(str(a.get('from')));dst=lookup.get(str(a.get('to')))
        if src is None or dst is None or src is dst:
            add('ARROW_ORPHAN',[a.get('from'),a.get('to')],'two real distinct objects');continue
        if src.get('causal_role')!='source' or dst.get('causal_role')!='target':
            add('ARROW_DIRECTION',[src.get('causal_role'),dst.get('causal_role')],'source -> target')
        if not geometry:continue
        start,end=a.get('start'),a.get('end')
        if start is None or end is None:
            add('ARROW_ORPHAN',[start,end],'both measured endpoints required');continue
        def inside(p,b):
            x,y,w,h=b;return x-8<=p[0]<=x+w+8 and y-8<=p[1]<=y+h+8
        if not inside(start,src['bbox']) or not inside(end,dst['bbox']):add('ARROW_ORPHAN',[start,end],'endpoints in referenced boxes ±8px')
        direction=[dst['bbox'][i]+dst['bbox'][i+2]/2-src['bbox'][i]-src['bbox'][i+2]/2 for i in (0,1)]
        if sum((end[i]-start[i])*direction[i] for i in (0,1))<=0:add('ARROW_DIRECTION',[start,end],'arrowhead toward target')
        length=math.dist(start,end);required=distance(src['bbox'],dst['bbox'])*.8
        if length+1e-6<required:add('ARROW_LENGTH',length,required)
    return errors


def geometry_violations(metrics,size):
    objects=metrics.get('objects',[]);scene=metrics.get('scene',1)
    return (shape_violations(objects,scene)+comparison_violations(objects,scene,layout=metrics.get('layout'),narration=metrics.get('narration',''),size=size,peers=metrics.get('comparison_peers'))
            +label_violations(metrics.get('labels',[]),objects+metrics.get('rear_objects',[]),scene)
            +arrow_violations(metrics.get('arrows',[]),objects,scene))


def storyboard_violations(board):
    errors=[]
    for i,s in enumerate(board.get('scenes',[])):
        if not isinstance(s,dict) or not isinstance(s.get('visual'),dict):continue
        v=s['visual'];items=v.get('items',[])
        if not isinstance(items,list) or not all(isinstance(o,dict) for o in items):continue
        objects=[dict(o,id=o.get('id') or str(j)) for j,o in enumerate(items) if o.get('shape') not in ARROWS]
        scene=s.get('index',i+1)
        found=shape_violations(items,scene)+comparison_violations(objects,scene,layout=v.get('layout'),narration=s.get('narration',''))
        found+=arrow_violations([dict(o,id=str(j)) for j,o in enumerate(items) if o.get('shape') in ARROWS],objects,scene,geometry=False)
        for e in found:errors.append((('scenes',i,'visual','items'),e['code'],str(e)))
    return errors
