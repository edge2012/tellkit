"""Shared canvas containment for assembly estimates and worker drawing bounds."""


def normalize_bbox(box, size):
    """Translate inside both axes; shrink proportionally only when oversized."""
    x, y, w, h = box
    width, height = size
    factor = min(1., width / max(1, w), height / max(1, h))
    nw, nh = w * factor, h * factor
    return [max(0, min(x + (w - nw) / 2, width - nw)),
            max(0, min(y + (h - nh) / 2, height - nh)), nw, nh]
