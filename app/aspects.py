"""Delivery aspects; portrait remains an explicit opt-in."""
import os
SIZES = {'16x9': (1280, 720), '9x16': (720, 1280)}
def delivery_aspects():
    aspects = tuple(key for key, env, default in (
        ('16x9', 'TELLKIT_LANDSCAPE_ENABLED', '1'),
        ('9x16', 'TELLKIT_PORTRAIT_ENABLED', '0'),
    ) if os.getenv(env, default).lower() in {'1', 'true', 'yes'})
    if not aspects:
        raise ValueError('no delivery aspects enabled')
    return aspects
def delivery_sizes():
    return {key: SIZES[key] for key in delivery_aspects()}


def canvas_aspect(size):
    """Canonical aspect for a measured canvas, including scaled previews."""
    return '16x9' if size[0] >= size[1] else '9x16'
