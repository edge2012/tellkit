"""W33: recognize opposing shoes from alpha contours, never RGB or labels."""
from PIL import Image, ImageChops
from app.visual_spec_w27b import violation


def similarity(left, right):
    def normalized(mask):
        mask = mask.convert('L').point(lambda a: 255 if a >= 128 else 0)
        bounds = mask.getbbox()
        if bounds is None:
            raise ValueError('empty shoe silhouette')
        return mask.crop(bounds).resize((128, 128), Image.Resampling.NEAREST)
    a, b = normalized(left), normalized(right)
    intersection = sum(ImageChops.darker(a, b).getdata())
    union = sum(ImageChops.lighter(a, b).getdata())
    return intersection / union


def violations(image, objects, scene=1):
    errors = []
    left = [o for o in objects if o.get('shape') == 'shoe_left']
    right = [o for o in objects if o.get('shape') == 'shoe_right']
    for a in left:
        for b in right:
            score = similarity(a['pixel_mask'], b['pixel_mask'])
            if score > .85:
                errors.append(violation('SHAPE_UNRECOGNIZABLE', scene, b,
                    dict(peer=a.get('id'), silhouette_iou=score),
                    'opposing shoe contours: similarity <= 0.85'))
    return errors
