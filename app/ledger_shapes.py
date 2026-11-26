"""Preserve implemented author choices; vocabulary is only a capability list.

The historical label table remains available for legacy diagnostics, never as
proof that an implemented author-selected shape has the wrong identity.
"""
import re
from app.official_shapes import SHAPES as OFFICIAL
from app.shape_vocab import NEW_SHAPES
from app.shape_implementations import IMPLEMENTED
from app.visual_spec_w27b import VOCABULARY, RECOGNIZABLE

USABLE = sorted((VOCABULARY & RECOGNIZABLE) - {'awen'})
# Each entry states exactly what the glyph depicts; synonyms are reviewed data.
MEANINGS = {**NEW_SHAPES, **OFFICIAL,
    'apple':'苹果', 'bacteria':'细菌|病菌', 'book':'书|书本', 'candy':'糖果',
    'drop':'水滴|小水滴|雨滴|水珠', 'water_drop':'水滴|小水滴|雨滴|水珠',
    'tooth':'牙齿|蛀牙', 'toothbrush':'牙刷', 'lightning':'闪电',
    'heart':'爱心', 'rainbow':'彩虹', 'circle':'圆形', 'square':'正方形|方块',
    'triangle':'三角形', 'tank':'水槽', 'cup':'杯子|水杯', 'bowl':'碗',
    'water':'水|清水|河水|融水', 'stone':'石头', 'wood':'木头|木块',
    'cookie':'饼干', 'shoe':'鞋', 'ice':'冰', 'ear':'耳朵',
    'vapor_particles':'水蒸气|水蒸气放大示意', 'sugar_grains':'糖粒|白糖', 'cloud':'云|云朵', 'tree':'树|树木', 'river':'河|河水',
    'arrow':'箭头|方向', 'curved_arrow':'箭头|方向',
    'diagram_box':'抽象示意方框（必须带对象标签，不声称真实外形）'}


def semantic_table():
    return {shape: MEANINGS.get(shape, shape) for shape in USABLE}


def matches(shape, label):
    if shape == 'diagram_box':
        return bool(label.strip())
    # Whole labels with a small set of visual qualifiers; no arbitrary substring
    # match (水 in 水蒸气 and 树 in 树脂 do not establish semantic identity).
    clean = re.sub(r'^(左边|右边|左侧|右侧|干净的|洁净|大|小)', '', label)
    return label == shape or any(label == term or clean == term
                                 for term in MEANINGS.get(shape, '').split('|') if term)


def normalize(items, *, scene=None):
    normalized, mappings = [], []
    for source in items:
        item = dict(source)
        original, label = item['shape'], item['label']
        if original == 'awen' or item.get('role') == 'character':
            raise ValueError('VIDEO_CHARACTER_FORBIDDEN: object-only video')
        shape = original
        if original not in USABLE:
            exact = [s for s in USABLE if s != 'diagram_box' and matches(s, label)]
            shape = exact[0] if exact else 'diagram_box'
        item['shape'] = shape
        mappings.append(dict(scene=scene, label=label, rejected_shape=original if original != shape else None,
            replacement_shape=shape, meaning=MEANINGS.get(shape, shape),
            representation='abstract_labelled_box' if shape == 'diagram_box' else 'literal',
            semantic_correct=None))
        normalized.append(item)
    return normalized, mappings


# Human concepts already used by storyboard.Item's semantic checks.
HUMAN_CONCEPT = r"小朋友|小?孩子?|男孩|女孩|小明|小红|妈妈|爸爸|老师|人物|人|猿"
HUMAN_SHAPES = {s for s in USABLE if s.startswith(('human_', 'ape_'))} | {
    'child', 'stick', 'silhouette_leaning', 'silhouette_upright', 'silhouette_upright_tool'}


def is_light_source(identity):
    return any(term in identity for term in ('光源', '灯', '太阳'))


def expression_shape(shape, label, subject):
    """An implemented declaration owns its identity; map only unknown shapes."""
    if shape in IMPLEMENTED:
        return shape
    names = [subject.get('identity', ''), subject.get('name', ''), label]
    candidates = [s for s in USABLE if s in IMPLEMENTED and s != 'diagram_box'
                  and any(matches(s, name) for name in names)]
    if candidates:
        return candidates[0]
    from app.degradation import degrade
    degrade('SHAPE_UNMAPPED', dict(original_shape=shape, label=label),
            '无法映射的形状使用带对象标签的 diagram_box')
    return 'diagram_box'



def resolve_expression_shapes(visual):
    """Rendering copy only; keep the author contract and source items intact."""
    expression = visual.get('expression')
    if not expression:
        return
    subjects = {s['ref']: s for s in expression['subject']}
    for item in visual['items']:
        subject = subjects.get(item.get('id'), {})
        item['shape'] = expression_shape(item['shape'], item.get('label', ''), subject)
        if item['shape'] == 'diagram_box':
            item['label'] = item.get('label') or subject.get('name') or item['id']
