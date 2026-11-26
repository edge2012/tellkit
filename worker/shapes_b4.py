from worker.design_tokens import PALETTE, STROKE, RADIUS, SHADOW
"""B4 nature silhouettes, drawn at 3x resolution without texture or sticker rims."""
import math
from PIL import Image, ImageDraw, ImageFilter

SHAPES = frozenset('sun cloud rain river drop ground'.split())
INK = PALETTE['neutral_900']


def bank_feature(draw, x, y, width, height, *, grass):
    """A few explicit silhouette landmarks, never a texture fill."""
    points = ([(-1,0),(-.9,-.8),(-.25,-.25),(0,-1),(.35,-.2),(.85,-.65),(1,0)]
              if grass else [(-1,0),(-.8,-.65),(-.15,-1),(.6,-.8),(1,-.2),(.5,.1)])
    draw.polygon([(round((x+px*width)*3),round((y+py*height)*3)) for px,py in points],
                 fill=PALETTE['secondary'] if grass else PALETTE['neutral_600'],outline=INK,width=STROKE['body']*3)


def sprite(shape, color, diameter, *, height=None):
    n = max(16, round(diameter))
    ratios = dict(sun=1, cloud=.64, rain=.18, river=.30, drop=1.22, ground=.42)
    w, h = n, height or max(8, round(n*ratios[shape]))
    im = Image.new('RGBA', (w*3, h*3))
    d = ImageDraw.Draw(im)
    pen = STROKE['body']*3
    def box(b): return tuple(round(v*3) for v in b)
    def ellipse(b, fill, outline=None): d.ellipse(box(b), fill=fill, outline=outline, width=pen)
    def line(points, fill=INK, width=pen):
        p=[(round(x*3),round(y*3)) for x,y in points]
        d.line(p, fill=fill, width=width, joint='curve')
        for x,y in (p[0],p[-1]):d.ellipse((x-width/2,y-width/2,x+width/2,y+width/2),fill=fill)
    def bez(a,b,c,e):
        return [tuple((1-t)**3*a[k]+3*(1-t)**2*t*b[k]+3*(1-t)*t*t*c[k]+t**3*e[k] for k in (0,1)) for t in [j/64 for j in range(65)]]
    if shape == 'sun':
        r=n*.415; cx=cy=n/2
        for j in range(12):
            a=j*math.tau/12
            line([(cx+math.cos(a)*n*.455,cy+math.sin(a)*n*.455),(cx+math.cos(a)*n*.48,cy+math.sin(a)*n*.48)])
        ellipse((cx-r,cy-r,cx+r,cy+r),PALETTE['accent'],INK)
    elif shape == 'cloud':
        mask=Image.new('L',im.size); md=ImageDraw.Draw(mask)
        for b in [(w*.025,h*.30,w*.44,h*.82),(w*.24,h*.06,w*.76,h*.82),(w*.57,h*.27,w*.975,h*.82)]:md.ellipse(box(b),fill=255)
        md.rectangle(box((w*.21,h*.49,w*.79,h*.82)),fill=255)
        # Erode the union to draw only its exterior contour; no internal ball seams.
        inside=mask.filter(ImageFilter.MinFilter(2*(pen//2)+1))
        im.paste(INK,(0,0),mask);im.paste(PALETTE['neutral_300'],(0,0),inside)
    elif shape == 'rain':
        length=w*.12
        for j in range(5):
            x=w*(.10+j*.20)
            line([(x,h*.12),(x-length*.35,h*.12+length*math.sqrt(1-.35**2))], PALETTE['neutral_600'])
    elif shape == 'river':
        pen = STROKE['body']*3
        upper = [(w*(.02+.96*j/128), h*(.16+.04*math.sin(j/128*math.tau))) for j in range(129)]
        # Both banks share one longitudinal parameter: narrow in the distance,
        # then open towards the near/right reach. Two flat water bands only.
        lower = [(x, y+h*(.66+.06*math.cos(j/128*math.tau))) for j,(x,y) in enumerate(upper)]
        middle = [(x, y+(lower[j][1]-y)*.30) for j,(x,y) in enumerate(upper)]
        def polygon(points, color):
            d.polygon([(round(x*3),round(y*3)) for x,y in points],fill=color)
        polygon(upper+lower[::-1], PALETTE['neutral_600'])
        polygon(middle+lower[::-1], PALETTE['neutral_300'])
        line(upper,width=pen); line(lower,width=pen)
        # W33: banks convey the water boundary; incidental trees/grass add no information.
    elif shape == 'drop':
        p=bez((w*.50,h*.025),(w*.43,h*.27),(w*.07,h*.49),(w*.09,h*.70))
        p+=bez(p[-1],(w*.10,h*1.05),(w*.90,h*1.05),(w*.91,h*.70))
        p+=bez(p[-1],(w*.93,h*.49),(w*.57,h*.27),(w*.50,h*.025))
        d.polygon([(round(x*3),round(y*3)) for x,y in p],fill=PALETTE['neutral_300'])
        line(p)
    elif shape == 'ground':
        pen = STROKE['body']*3
        top=[(w*(.01+.98*j/128), h*(.46+.045*math.sin(j/128*math.tau*2))) for j in range(129)]
        d.polygon([(round(x*3),round(y*3)) for x,y in top+[(w*.99,h*.98),(w*.01,h*.98)]],fill=PALETTE['ground'])
        line(top)
        # Intrinsic ground landmarks remain legible without a scene or labels.
        for x,y in [(.19,.48),(.65,.49)]:
            bank_feature(d,w*x,h*y,w*.075,h*.40,grass=True)
        for x,y in [(.43,.78),(.83,.72)]:
            bank_feature(d,w*x,h*y,w*.055,h*.20,grass=False)
    im=im.resize((w,h),Image.Resampling.LANCZOS)
    if shape not in {'rain','ground'}:
        from worker.scenekit_shapes import soft_lighting
        im=soft_lighting(im,im.getchannel('A'),grammar_shape=shape,arc=shape in {'sun','cloud','river'},repair=True)
    from worker.lighting_declaration import unlit
    if 'lighting_declaration' not in im.info:im.info['lighting_declaration']=unlit(shape,im)
    im.info['rendered_shape']=shape
    return im,im.getchannel('A')
