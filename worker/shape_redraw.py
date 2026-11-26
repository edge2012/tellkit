"""Small, procedural glyphs painted inside the W318 allocated rectangle."""
import math
from functools import lru_cache
from PIL import Image, ImageDraw


def handles(item):
    return item.get('shape') in {'sound', 'vibration', 'heat', 'charge'} or (
        item.get('shape') == 'arrow' and any(s in item.get('label', '') for s in ('绷紧', '收紧', '收缩', '夹紧')))


@lru_cache(maxsize=128)
def paint(shape, size, label, phase):
    w,h=size
    im=Image.new('RGBA',size); d=ImageDraw.Draw(im)
    ink=(48,65,80,255); orange=(226,117,39,255)
    pen=max(3,round(min(size)*.018))
    def line(points, fill=ink):
        d.line([(round(x*w),round(y*h)) for x,y in points],fill=fill,width=pen,joint='curve')
    if shape == 'sound':
        d.ellipse((.03*w,.42*h,.17*w,.58*h),fill=orange,outline=ink,width=pen)
        for i in range(3):
            r=.24+(i+phase)*.21
            points=[(.10+r*math.cos(a),.5+r*.56*math.sin(a)) for a in [math.radians(-65+j*130/64) for j in range(65)]]
            line(points,orange)
    elif shape == 'vibration':
        for i in range(3):
            q=(i+phase)/3; r=.08+.40*q
            for a in range(0,360,30):
                d.arc(((.5-r)*w,(.5-r)*h,(.5+r)*w,(.5+r)*h),a,a+18,fill=(70,100,124,round(255*(1-.75*q))),width=pen)
    elif shape == 'heat':
        d.ellipse((.08*w,.70*h,.92*w,.97*h),fill=(255,178,103,42))
        for x in (.24,.5,.76):
            line([(x+.055*math.sin(t*math.tau*1.6-phase*math.tau),.85-.73*t) for t in [j/64 for j in range(65)]],orange)
    elif shape == 'charge':
        d.ellipse((pen,pen,w-pen-1,h-pen-1),fill=(255,241,220,255),outline=ink,width=pen)
        line([(.30,.5),(.70,.5)])
        if '负' not in label: line([(.5,.30),(.5,.70)])
    else:
        line([(.04,.5),(.42,.5)])
        line([(.96,.5),(.58,.5)])
        for tip,back in [(.44,.30),(.56,.70)]:
            d.polygon([(tip*w,.5*h),(back*w,.28*h),(back*w,.72*h)],fill=ink)
    return im
