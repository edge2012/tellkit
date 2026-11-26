from app.aspects import delivery_aspects, delivery_sizes
"""Narrative and delivery checks. Measurements are evidence, never inferred passes."""
import re
from app.visual_spec_w27b import violation

from app.visual_thresholds import MAX_LINES, MIN_SECONDS, MAX_SECONDS, MAX_BYTES, PAUSE_MS, SAFE


def subtitles(pages, source, scene, size):
    from worker.captions import tokenizer, CLOSING, OPENING
    errors=[]
    def add(code,value,threshold):errors.append(violation(code,scene,{'id':'subtitle'},value,threshold))
    boundaries=set();offset=0
    for token in tokenizer().cut(source,HMM=False):
        offset+=len(token);boundaries.add(offset)
    offset=0
    for page in pages:
        lines=page['lines']
        if len(lines)>MAX_LINES:add('SUBTITLE_TOO_MANY_LINES',len(lines),MAX_LINES)
        for line in lines:
            offset+=len(line)
            if offset not in boundaries:add('SUBTITLE_BREAK_WORD',offset,'jieba token boundary')
            if line and (line[0] in CLOSING or line[-1] in OPENING or all(c in CLOSING|OPENING for c in line)):
                add('SUBTITLE_PUNCT_EDGE',line,'no isolated or dangling punctuation')
        for x,y,w,h in page.get('ink_boxes',[]):
            pad=min(size)*SAFE
            if x<pad or y<pad or x+w>size[0]-pad or y+h>size[1]-pad:
                add('SUBTITLE_OUT_OF_SAFE',[x,y,w,h],{'size':size,'padding':pad})
    rendered=''.join(line for page in pages for line in page['lines'])
    if rendered!=source:
        add('SUBTITLE_OUT_OF_SAFE',rendered,source)
    if rendered!=source or any(e['code'] in {'SUBTITLE_BREAK_WORD','SUBTITLE_PUNCT_EDGE'} for e in errors):
        add('SUBTITLE_BROKEN',rendered,source)
    return errors


def delivery(board, layouts, media, speech):
    errors=[]
    for aspect, data in media.items():
        for code,value,limit,bad in [
            ('DURATION_BELOW_FLOOR' if data['duration_s'] < MIN_SECONDS else 'DURATION_ABOVE_CEILING',data['duration_s'],[MIN_SECONDS,MAX_SECONDS],not MIN_SECONDS<=data['duration_s']<=MAX_SECONDS),
            ('SIZE_EXCEEDS_LIMIT',data['bytes'],MAX_BYTES,data['bytes']>MAX_BYTES)]:
            if bad:
                from app.enforcement import fail
                errors.append(fail(code, scene=0, sentence=0, object_id=aspect,
                    check='media_duration' if code.startswith('DURATION') else 'media_bytes',
                    actual=value, threshold=limit,
                    basis='measured delivery duration must be within fixed 15/45 seconds' if code.startswith('DURATION')
                          else 'measured delivery file size must not exceed MAX_BYTES'))
    for i,s in enumerate(board.get('scenes',[])):
        scene=s.get('index',i+1);both={}
        for aspect,size in delivery_sizes().items():
            pages=layouts.get(aspect,{}).get(str(scene),layouts.get(aspect,{}).get(scene,[]))
            hits=subtitles(pages,s.get('narration',''),scene,size);errors+=hits
            both[aspect]=[p['lines'] for p in pages]
            if aspect=='9x16' and any(e['code']=='SUBTITLE_OUT_OF_SAFE' for e in hits):
                errors.append(violation('SUBTITLE_RATIO',scene,{'id':'subtitle'},both,'subtitle bounds checked for each enabled aspect'))
        if '9x16' in both and both['16x9']!=both['9x16']:
            errors.append(violation('SUBTITLE_RATIO',scene,{'id':'subtitle'},both,'matching line breaks in both ratios (W27c)'))
    timeline=[];offset=0
    for row in speech:
        timeline.extend(dict(c,start_ms=c['start_ms']+offset,end_ms=c['end_ms']+offset,scene=row['scene']) for c in row['captions'])
        s=next((s for s in board['scenes'] if s.get('index')==row['scene']),{})
        offset+=s.get('duration_ms',row.get('speech_ms',0))
    for a,b in zip(timeline,timeline[1:]):
        if a['text'].rstrip('”’」』"').endswith(tuple('。！？.!?')):
            gap=b['start_ms']-a['end_ms']
            if gap<PAUSE_MS:errors.append(violation('PAUSE_TOO_SHORT',b['scene'],{'id':'speech'},gap,PAUSE_MS))
    return errors
