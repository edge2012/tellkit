"""R28 glyph measurement independent of the declared font_size.

Tight glyph bounds come from actual text rasterization (or an isolated archive
label). Compare to the same text at 13px using the actual configured fonts.
"""
from worker.design_tokens import TYPE as DESIGN_TYPE, RADIUS as DESIGN_RADIUS
from app.visual_spec_w27b import violation


def violations(labels, fonts, scene=1):
    from worker.visual import centered_text
    errors=[]
    for label in labels:
        if 'glyph_size' not in label:continue
        expected=centered_text(fonts,label['text'],DESIGN_TYPE['label'],10000).size
        actual=tuple(label['glyph_size'])
        if actual!=expected:
            errors.append(violation('LABEL_FONT_MIXED',scene,label,
                dict(glyph_size=actual,text=label['text']),dict(font_size=13,glyph_size=expected)))
    return errors
