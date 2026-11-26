"""Small token-styled diagrams composed only from generic primitives."""
from PIL import Image, ImageDraw
from app.shape_implementations import W293 as SHAPES, require_shape
from worker.design_tokens import PALETTE, STROKE, RADIUS, LAYOUT


def sprite(shape, color, diameter, *, polarity='-'):
    from worker.visual import COLORS
    require_shape(shape, SHAPES)
    n = max(LAYOUT['padding'] * 2, round(diameter))
    im = Image.new('RGBA', (n, n))
    d = ImageDraw.Draw(im)
    ink, fill = STROKE['color'], COLORS.get(color, PALETTE['primary'])
    pen = max(1, round(STROKE['body'] * n / (LAYOUT['padding'] * 16)))
    def box(values):
        return tuple(round(v * (n-1)) for v in values)
    def line(points, color=ink):
        d.line([box(p) for p in points], fill=color, width=pen, joint='curve')
    def ellipse(bounds, color=fill):
        d.ellipse(box(bounds), fill=color, outline=ink, width=pen)
    if shape == 'graupel':
        d.polygon([box(p) for p in [( .15,.27),(.39,.09),(.70,.16),(.89,.45),(.78,.79),(.45,.91),(.12,.65)]], fill=fill, outline=ink, width=pen)
        for b in [(.28,.28,.41,.40),(.55,.35,.72,.48),(.39,.60,.54,.73)]:
            d.ellipse(box(b), fill=PALETTE['neutral_050'])
    elif shape == 'charge':
        ellipse((.08,.08,.92,.92))
        line([(.30,.50),(.70,.50)])
        if polarity == '+':
            line([(.50,.30),(.50,.70)])
    elif shape == 'channel':
        line([(.68,.07),(.38,.32),(.58,.44),(.30,.68),(.48,.76),(.27,.93)], fill)
    elif shape == 'brain':
        ellipse((.07,.18,.93,.82))
        for b, start, end in [((.20,.27,.55,.68),250,105),((.47,.30,.81,.72),70,265)]:
            d.arc(box(b),start,end,fill=ink,width=pen)
    elif shape == 'sleeping_child':
        ellipse((.29,.39,.91,.78))
        ellipse((.07,.27,.39,.59))
        d.arc(box((.15,.38,.29,.46)),0,180,fill=ink,width=pen)
        d.arc(box((.40,.46,.76,.74)),180,315,fill=ink,width=pen)
        line([(.66,.72),(.86,.76)])
    elif shape == 'memory_card':
        d.rounded_rectangle(box((.13,.08,.87,.92)),radius=max(1,round(RADIUS['small']*n/(LAYOUT['padding']*16))),fill=fill,outline=ink,width=pen)
        for y in (.32,.50,.68):
            line([(.28,y),(.72,y)])
    return im, im.getchannel('A')
