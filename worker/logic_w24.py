from worker.design_tokens import PALETTE, STROKE as DESIGN_STROKE, RADIUS as DESIGN_RADIUS
from app.enforcement import blocks
"""Render bound arrows and the cloud-to-river transfer from storyboard references."""
import math
from PIL import ImageDraw
from app.logic_w24 import arrow_geometry


def progress(samples, fraction):
    for a,b in zip(samples,samples[1:]):
        if fraction<=b.at:
            f=max(0,min(1,(fraction-a.at)/(b.at-a.at)))
            return a.position+(b.position-a.position)*f
    return samples[-1].position


def connections(im, visual, metrics, fraction, scene=0):
    lookup={m['item_index'] if 'item_index' in m else int(m['id']):m for m in metrics}
    d=ImageDraw.Draw(im);arrows=[];transfers=[]
    for i,it in enumerate(visual.items):
        if it.shape not in {'arrow','curved_arrow'} and it.action!='fall':continue
        if it.from_ not in lookup or it.to not in lookup:
            code = 'ARROW_ORPHAN' if it.shape in {'arrow','curved_arrow'} else 'TRANSITION_HANDOFF'
            if blocks([dict(code=code,scene=scene,object=it.id or str(i),measured=[it.from_,it.to],threshold='two valid objects')], 'frame'):
                raise ValueError(code)
            continue
        a,b=lookup[it.from_],lookup[it.to]
        x,y,w,h=a['bbox'];u,v,r,s=b['bbox']
        if it.action=='fall':
            if not it.samples:
                if blocks([dict(code='TRANSITION_HANDOFF',scene=scene,object=it.id or str(i),measured=[],threshold='falling rain samples')], 'frame'):
                    raise ValueError('TRANSITION_HANDOFF: falling rain needs samples')
                continue
            p=(progress(it.samples,fraction)-2)/6
            # Five rain strokes descend continuously from beneath cloud into the water.
            start=(x+w*.5,y+h+10);end=(u+r*.72,v+s*.45)
            cx=start[0]+(end[0]-start[0])*p;cy=start[1]+(end[1]-start[1])*p
            length=min(w*.12,im.height*.025)
            for k in range(5):
                dx=(k-2)*w*.13
                d.line((cx+dx,cy,cx+dx-length*.28,cy+length),fill=PALETTE['primary'],width=DESIGN_STROKE['body'])
            if p>.92:
                d.arc((cx-w*.4,cy-5,cx+w*.4,cy+10),0,180,fill=PALETTE['primary'],width=DESIGN_STROKE['body'])
            transfers.append(dict(subject_id=it.subject_id,source=a['id'],target=b['id'],start=start,end=end,position=(cx,cy),progress=p))
            continue
        start,end=bound_endpoints(a['bbox'],b['bbox'],scene=scene,obj=it.id or str(i))
        if it.shape == 'arrow' and any(word in it.label for word in ('绷紧','收紧','收缩','夹紧')):
            delta=(end[0]-start[0],end[1]-start[1])
            draw_arrow(d,start,(start[0]+delta[0]*.44,start[1]+delta[1]*.44))
            draw_arrow(d,end,(start[0]+delta[0]*.56,start[1]+delta[1]*.56))
        else:
            draw_arrow(d,start,end)
        arrows.append(dict(id=str(i),**{'from':a['id'],'to':b['id']},start=start,end=end))
    errors=arrow_geometry(arrows,metrics)
    if blocks([dict(code=code,scene=scene,object='arrows',measured=arrows,threshold='valid bound arrow') for code in errors], 'frame'):raise ValueError(','.join(errors))
    return arrows,transfers


def bound_endpoints(source, target, *, scene=0, obj='arrow'):
    """Facing box edges, with a four-pixel air gap at each endpoint."""
    x,y,w,h=source;u,v,r,s=target
    ac=(x+w/2,y+h/2);bc=(u+r/2,v+s/2)
    dx,dy=bc[0]-ac[0],bc[1]-ac[1]
    length=math.hypot(dx,dy)
    if not length:
        if blocks([dict(code='ARROW_LENGTH',scene=scene,object=obj,measured=0,threshold='noncoincident centers')], 'frame'):
            raise ValueError('ARROW_LENGTH: coincident centers')
        return ac,bc
    ux,uy=dx/length,dy/length
    def edge(c,bw,bh,sign):
        reach=min(bw/2/abs(ux) if ux else math.inf,bh/2/abs(uy) if uy else math.inf)+4
        return c[0]+sign*ux*reach,c[1]+sign*uy*reach
    start,end=edge(ac,w,h,1),edge(bc,r,s,-1)
    gap=math.hypot(max(x-u-r,u-x-w,0),max(y-v-s,v-y-h,0))
    if (end[0]-start[0])*ux+(end[1]-start[1])*uy<=0 or math.dist(start,end)<gap*.8:
        if blocks([dict(code='ARROW_LENGTH',scene=scene,object=obj,measured=dict(start=start,end=end,gap=gap),threshold='forward endpoints and length >= gap * 0.8')], 'frame'):
            raise ValueError('ARROW_LENGTH: insufficient space outside object boxes')
    return start,end


def draw_arrow(draw,start,end):
    angle=math.atan2(end[1]-start[1],end[0]-start[0]);n=min(12,math.dist(start,end)*.4)
    draw.line((start,end),fill=PALETTE['neutral_900'],width=DESIGN_STROKE['body'])
    draw.polygon([end,(end[0]-n*math.cos(angle-.5),end[1]-n*math.sin(angle-.5)),
                  (end[0]-n*math.cos(angle+.5),end[1]-n*math.sin(angle+.5))],fill=PALETTE['neutral_900'])
