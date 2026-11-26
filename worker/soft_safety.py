"""W127 safety checks use renderer observations, independent of motion quality."""
from app.enforcement import fail


def subject_presence(board, manifest):
    subjects = {item['id'] for scene in board['scenes'] for item in scene['visual']['items']
                if item.get('role') == 'subject'}
    aspects = set(manifest.get('canvas', {})) or {f.get('aspect', 'unknown') for f in manifest['frames']} or {'unknown'}
    seen = {aspect: set() for aspect in aspects}
    for frame in manifest['frames']:
        aspect = frame.get('aspect', 'unknown')
        size = manifest.get('canvas', {}).get(aspect)
        for obj in manifest['states'][frame['state']]['objects']:
            box = obj.get('bbox') or [0, 0, 0, 0]
            x,y,w,h = box
            intersects = size is None or (x+w > 0 and y+h > 0 and x < size[0] and y < size[1])
            if obj.get('visible', True) and obj.get('opacity', 1) > 0 and w > 0 and h > 0 and intersects:
                seen.setdefault(aspect, set()).add(obj['object'])
    return [fail('SUBJECT_ABSENT_EPISODE', scene=0, sentence=0, object_id=subject,
        check='episode_render_presence', actual=0, threshold='at least one rendered frame',
        aspect=aspect, basis='all encoded-frame renderer states for this delivery aspect')
        for aspect in sorted(aspects) for subject in sorted(subjects-seen[aspect])]


def subtitle_occlusion(before, after, boxes, scene):
    import numpy as np
    # Only the already drawn glyph rectangles are compared, never layout overlap.
    visible = 0
    total = 0
    for x,y,w,h in boxes:
        region = (int(x), int(y), int(x+w), int(y+h))
        a, b = np.asarray(before.crop(region)), np.asarray(after.crop(region))
        ink = np.max(a, axis=2) - np.min(a, axis=2) < 20
        ink &= np.max(a, axis=2) < 100
        total += int(ink.sum())
        visible += int((ink & (np.abs(a.astype(int)-b.astype(int)).max(axis=2) < 30)).sum())
    if total and not visible:
        return [fail('SUBTITLE_FULLY_OCCLUDED', scene=scene, sentence=0, object_id='subtitle',
            check='composited_caption_ink', actual=0, threshold='visible subtitle ink > 0',
            basis='caption glyph pixels before and after final overlays')]
    return []
