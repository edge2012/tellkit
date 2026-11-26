"""Word timing helpers; offsets are milliseconds on the current audio timeline."""
from html import unescape


def word_spans(text, boundaries):
    """Map repeated words in order; incomplete/unmatchable metadata falls back safely."""
    spans, cursor = [], 0
    for word in boundaries:
        token = unescape(word['text'])
        start = text.find(token, cursor) if token else -1
        if start < 0:
            return []
        spans.append((start, start+len(token), word))
        cursor = start+len(token)
    # Do not claim real timing if spoken text has no matching metadata.
    covered = ''.join(text[a:b] for a, b, _ in spans)
    if ''.join(c for c in covered if c.isalnum()) != ''.join(c for c in text if c.isalnum()):
        return []
    return spans


def shift_boundaries(boundaries, removed_ms, start_ms, duration_ms):
    result = []
    for word in boundaries:
        lo = min(duration_ms, max(0, word['offset_ms']-removed_ms))
        hi = min(duration_ms, max(lo, word['offset_ms']+word['duration_ms']-removed_ms))
        result.append(dict(word, offset_ms=start_ms+lo, duration_ms=hi-lo))
    return result


def boundary_duration_record(boundaries, measured_ms):
    """Opt-in diagnostic only. No enforcement/hard/warn integration in W65."""
    span = (boundaries[-1]['offset_ms']+boundaries[-1]['duration_ms']-
            boundaries[0]['offset_ms']) if boundaries else None
    delta = abs(measured_ms-span) if span is not None else None
    return dict(word_boundary_span_ms=span, measured_ms=measured_ms, delta_ms=delta,
                code='WORD_BOUNDARY_MISMATCH' if delta is not None and delta > 150 else None)
