"""Physical altitude only; no title, narration, discipline or topic inputs."""
BANDS = {'sky': (0., .55), 'ground': (.45, .85), 'underground': (.70, 1.)}
# Canonical interiors avoid the overlapping acceptance margins reversing edges.
INTERIORS = {'sky': (.18, .43), 'ground': (.57, .68), 'underground': (.78, .90)}
GROUPS = {
    'sky': 'cloud sun moon star lightning rainbow rain vapor_particles wind graupel sun_ray',
    'ground': 'water river ground mountain house boat car tree grass apple wood campfire ape_bent ape_upright human_standing human_bent child sleeping_child awen silhouette_quadruped silhouette_leaning silhouette_upright silhouette_upright_tool',
    'underground': 'stone',
}
SHAPE_BANDS = {shape: band for band, shapes in GROUPS.items() for shape in shapes.split()}
CATEGORY_BANDS = dict(SHAPE_BANDS, ocean='ground', lake='ground', volcano='ground',
                      person='ground', animal='ground', plant='ground',
                      rock='underground', underground_ice='underground', seed='underground',
                      root='underground', magma='underground', vapor='sky')
# Location words describe physical placement, never a curriculum/topic.
LOCATION_WORDS = {
    'underground': ('地下', '深部', '地底', '根部', '岩浆', '种子', 'underground'),
    'sky': ('天空', '天上', '空中', '高空', '太空', '云中', '云里', '水蒸气', '水汽', 'sky'),
    'ground': ('地面', '地表', '地上', '海洋', '湖', 'ground'),
}


def data(value):
    return value.model_dump() if hasattr(value, 'model_dump') else value or {}


def resolve(item, visual=None):
    item, visual = data(item), data(visual)
    subjects = (visual.get('expression') or {}).get('subject', [])
    subject = next((s for s in subjects if s.get('ref') == item.get('id')), {})
    for owner, row in (('item', item), ('subject', subject)):
        for key in ('semantic_category', 'spatial_frame', 'anchor', 'region'):
            value = row.get(key)
            category = value.get('band', value.get('category')) if isinstance(value, dict) else value
            band = category if isinstance(category, str) and category in BANDS else CATEGORY_BANDS.get(category) if isinstance(category, str) else None
            if band:
                return dict(band=band, source=f'{owner}.{key}', value=value)
    for owner, key, value in (('subject', 'identity', subject.get('identity', '')),
                              ('item', 'label', item.get('label', ''))):
        for band, words in LOCATION_WORDS.items():
            if isinstance(value, str) and any(word in value for word in words):
                return dict(band=band, source=f'{owner}.{key}', value=value)
    shape = item.get('shape')
    if shape in SHAPE_BANDS:
        return dict(band=SHAPE_BANDS[shape], source='shape.physical_location', value=shape)
    # Abstract glyphs and ambiguous objects have no intrinsic altitude.
    frame = visual.get('spatial_frame')
    if frame in BANDS:
        return dict(band=frame, source='visual.spatial_frame', value=frame)
    return dict(band=None, source='unconstrained', value=shape)


def project(box, evidence, size):
    x, y, w, h = box
    band = evidence['band']
    if band is None: return tuple(box)
    lo, hi = INTERIORS[band]
    center = max(lo*size[1], min(y+h/2, hi*size[1]))
    # Translate only; retain shape, scale, x and within-band slot order.
    return (x, round(center-h/2), w, h)


def place(sprite, x, y, item, visual, size):
    return project((x, y, *sprite.size), resolve(item, visual), size)[:2]


def validate(objects, items, visual, size, scene):
    declarations = {data(it).get('id'): it for it in items}
    hits = []
    for obj in objects:
        evidence = resolve(declarations.get(obj.get('id'), obj), visual)
        obj['semantic_band'] = evidence
        band = evidence['band']
        if band is None: continue
        if not obj.get('bbox'): continue
        cy = (obj['bbox'][1]+obj['bbox'][3]/2)/size[1]
        if BANDS[band][0] <= cy <= BANDS[band][1]: continue
        actual = [b for b, (lo, hi) in BANDS.items() if lo <= cy <= hi]
        hits.append(dict(code='SEMANTIC_BAND_MISMATCH', tier='craft', scene=scene,
                         object=obj['id'], measured=dict(id=obj['id'], expected_band=band,
                         actual_band=actual or ['outside_canvas'], center_y=cy, provenance=evidence),
                         threshold=BANDS[band]))
    return hits


def relation_ports(source, target):
    """Choose receiver/source faces by semantic order, never by a y comparison."""
    sb = source.get('semantic_band', {}).get('band')
    tb = target.get('semantic_band', {}).get('band')
    if sb not in BANDS or tb not in BANDS: return None
    sx, sy, sw, sh = source['bbox']
    tx, ty, tw, th = target['bbox']
    if sb == tb:
        right = tx+tw/2 >= sx+sw/2
        return ((sx+sw if right else sx, sy+sh/2),
                (tx if right else tx+tw, ty+th/2))
    down = list(BANDS).index(tb) > list(BANDS).index(sb)
    if down and sy+sh < ty:
        return ((sx+sw/2, sy+sh), (tx+tw/2, ty))
    if not down and ty+th < sy:
        return ((sx+sw/2, sy), (tx+tw/2, ty+th))
    # Horizontal contour rays preserve semantic center-height order even when
    # large silhouettes overlap vertically. The resulting path may be diagonal.
    right = tx+tw/2 >= sx+sw/2
    return ((sx+sw if right else sx, sy+sh/2),
            (tx if right else tx+tw, ty+th/2))
