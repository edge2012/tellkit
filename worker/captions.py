"""Lossless, font-measured Chinese subtitles; paginate before rasterization."""
from functools import lru_cache
import jieba
import math
from app.word_timing import word_spans

CLOSING = set('，。！？；：、,.!?;:）】》」』”’')
OPENING = set('（【《「『“‘')


@lru_cache(maxsize=1)
def tokenizer():
    # Keep the dictionary cache in the writable temporary directory in containers.
    tok = jieba.Tokenizer()
    tok.tmp_dir = '/tmp'
    return tok


def units(text, word_texts=()):
    tokens, cursor = [], 0
    for word in word_texts:
        start = text.find(word, cursor)
        if start < 0:
            return units(text)
        tokens.extend(tokenizer().cut(text[cursor:start], HMM=False))
        tokens.append(word)
        cursor = start+len(word)
    tokens.extend(tokenizer().cut(text[cursor:], HMM=False))
    result = []
    pending = ''
    quote_open = False
    for token in tokens:
        if token == '"':
            if quote_open and result:
                result[-1] += token
            else:
                pending += token
            quote_open = not quote_open
            continue
        if all(c in CLOSING for c in token) and result:
            result[-1] += token
        elif all(c in OPENING for c in token):
            pending += token
        else:
            result.append(pending + token)
            pending = ''
    if pending:
        if result: result[-1] += pending
        else: result.append(pending)
    return result


@lru_cache(maxsize=2048)
def lines(text, fonts, size, width, word_texts=()):
    tokens = units(text, word_texts)
    def measure(value):
        return sum(fonts.font(c, size).getlength(c) for c in value)
    # Dynamic programming prefers clause boundaries and balanced readable lines.
    costs = [float('inf')] * (len(tokens) + 1)
    paths = [None] * (len(tokens) + 1)
    costs[-1] = 0
    for i in range(len(tokens)-1, -1, -1):
        value = ''
        for j in range(i, len(tokens)):
            value += tokens[j]
            used = measure(value)
            if used > width: break
            if value[-1] in OPENING or value[0] in CLOSING: continue
            penalty = (width-used)**2 / width**2
            if j+1 < len(tokens) and value[-1] not in CLOSING:
                penalty += 1
            score = 1 + penalty + costs[j+1]
            if score < costs[i]:
                costs[i], paths[i] = score, (value, j+1)
    if paths[0] is None and tokens:
        raise ValueError('CAPTION_UNBREAKABLE: semantic unit exceeds caption width')
    result, i = [], 0
    while i < len(tokens):
        value, i = paths[i]
        result.append(value)
    assert ''.join(result) == text
    return tuple(result)


def sentence_captions(captions):
    """TTS emits comma clauses; keep the sentence's tail on the subtitle timeline."""
    result, current = [], None
    for cap in captions:
        if current is None:
            current = dict(text='', start_ms=cap['start_ms'], end_ms=cap['end_ms'], word_boundaries=[])
        current['text'] += cap['text']
        current['word_boundaries'].extend(cap.get('word_boundaries', []))
        current['end_ms'] = cap['end_ms']
        if cap['text'].rstrip('”’」』"').endswith(('。','！','？','!','?','.')):
            result.append(current)
            current = None
    if current is not None: result.append(current)
    return result


def paginate(captions, fonts, size, width):
    result = []
    for cap in sentence_captions(captions):
        spans = word_spans(cap['text'], cap.get('word_boundaries', []))
        wrapped = lines(cap['text'], fonts, size, int(width), tuple(cap['text'][a:b] for a,b,_ in spans))
        pages = [wrapped[i:i+2] for i in range(0, len(wrapped), 2)]
        count = sum(map(len, wrapped))
        consumed = 0
        for page in pages:
            start = cap['start_ms'] + (cap['end_ms']-cap['start_ms']) * consumed/max(1,count)
            page_start = consumed
            consumed += sum(map(len, page))
            end = cap['start_ms'] + (cap['end_ms']-cap['start_ms']) * consumed/max(1,count)
            covered = [w for a,b,w in spans if b > page_start and a < consumed]
            if covered:
                start = covered[0]['offset_ms']
                end = covered[-1]['offset_ms']+covered[-1]['duration_ms']
            result.append(dict(text=''.join(page), lines=list(page), start_ms=start, end_ms=end))
    return result


def measured_page(page, fonts, caption_size, size):
    """Shared tight-ink placement for rendering and delivery evidence (xywh)."""
    from worker.visual import centered_text
    w,h=size
    bitmaps=[centered_text(fonts,line,caption_size,w*.90) for line in page['lines']]
    gap=max(6,round(caption_size*.3))
    top=h-math.ceil(h*.08)-sum(b.height for b in bitmaps)-gap*(len(bitmaps)-1)
    boxes=[]
    for bitmap in bitmaps:
        boxes.append((round(w/2-bitmap.width/2),round(top),bitmap.width,bitmap.height))
        top+=bitmap.height+gap
    return bitmaps,boxes
