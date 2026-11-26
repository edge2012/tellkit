"""Non-blocking craft decisions shared by both label compositors (xywh boxes)."""
import re
import unicodedata


def text_key(text):
    return ''.join(c for c in (text or '') if not c.isspace() and not unicodedata.category(c).startswith('P'))


def area(obj):
    return max(0, obj['bbox'][2]) * max(0, obj['bbox'][3])


def intersection(a, b):
    x, y, w, h = a['bbox']; xx, yy, ww, hh = b['bbox']
    return max(0, min(x+w, xx+ww)-max(x, xx)) * max(0, min(y+h, yy+hh)-max(y, yy))


PROCESS_WORDS = ('膨胀', '传导', '震动', '振动', '分离', '加速', '减速', '移动', '上升', '下降', '扩散', '收缩', '融合', '合并', '分解', '转化', '变化', '传递', '压缩', '拉伸', '平衡', '压力', '引力', '能量', '温度', '速度', '方向', '作用', '吸收', '释放', '绷紧', '波动', '过程', '状态', '数量', '概率', '密度', '距离', '时间', '频率', '质量', '体积', '浓度', '阻力')


def process_label(text):
    return any(word in text_key(text) for word in PROCESS_WORDS)


def select_labels(objects, pending, title='', *, notes, used_texts=None):
    """Return (owner, text) pairs; append info notes, never enforcement hits.

    Pending owners are object dictionaries. Candidate identity must be supported
    by matching text or an id family; unrelated scenery is not a safe fallback.
    """
    texts = {id(obj): text_key(text) for obj, text in pending}
    def label(obj):
        return texts.get(id(obj), text_key(obj.get('label') or obj.get('semantic_label', '')))
    def prefix(obj):
        return re.split(r'[-_.:/\d]', str(obj.get('id', '')))[0]
    def note(code, obj, text):
        notes.append(dict(code=code, object=obj.get('id'), text=text, severity='info'))
    drawn = {o.get('id'): o for o in objects if o.get('id') is not None
             and o.get('bbox') and area(o) > 0 and o.get('visible', True)
             and (o.get('pixel_mask') is None or o['pixel_mask'].getbbox() is not None)}
    objects = list(drawn.values())
    selected=[]; owners=set(); seen=set(used_texts or ())
    already_labeled = bool(seen - {text_key(title), ''})
    seen.add(text_key(title))
    for obj, text in sorted(pending, key=lambda pair: area(pair[0]) if pair[0].get('bbox') else 0, reverse=True):
        if not process_label(text) or len(text) > 8 or len(selected) >= 1 or already_labeled:
            notes.append(dict(code='LABEL_DROPPED', tier='craft', object=obj.get('id'), text=text, reason='process/abstract only; one label per scene'))
            continue
        if obj.get('id') not in drawn:
            note('LABEL_ANCHOR_LOST', obj, text)
            continue
        obj = drawn[obj['id']]
        key=text_key(text)
        if not key:
            continue
        if key == text_key(title):
            note('LABEL_SUPPRESSED_TITLE', obj, text)
            continue
        if key in seen or obj['id'] in owners:
            note('LABEL_DUPLICATE_SUPPRESSED', obj, text)
            continue
        seen.add(key)
        conflicts=[]
        for other in objects:
            if other is obj or not other.get('bbox') or label(other) == key:
                continue
            inter=intersection(obj, other)
            union=area(obj)+area(other)-inter
            if union > 0 and inter/union > .8:
                conflicts.append(other)
        if conflicts:
            candidates=[other for other in objects
                        if other is not obj and other.get('bbox')
                        and (label(other) == key or (prefix(obj) and prefix(other) == prefix(obj)))
                        and not any(intersection(other, blocked) > 0 for blocked in [obj]+conflicts)
                        and label(other) in ('', key)]
            candidates.sort(key=lambda other: (prefix(other) != prefix(obj), -area(other)))
            if not candidates:
                note('LABEL_ANCHOR_AMBIGUOUS', obj, text)
                continue
            obj=candidates[0]
        if obj['id'] in owners:
            note('LABEL_DUPLICATE_SUPPRESSED', obj, text)
            continue
        owners.add(obj['id'])
        selected.append((obj, text))
    return selected


def suppress_empty_boxes(plan, metrics, visual, title=''):
    """A diagram box is the label body; suppress its sprite together with its text."""
    items = {it.get('id') or str(i): it for i, it in enumerate(visual.get('items', []))}
    objects = metrics.get('objects', [])
    pending = [(o, items[o['id']].get('label', '')) for o in objects if o.get('id') in items]
    selected = {id(o) for o, _ in select_labels(objects, pending, title, notes=[])}
    hidden = [o for o in objects if items.get(o.get('id'), {}).get('shape') == 'diagram_box'
              and id(o) not in selected]
    boxes = {tuple(o['bbox']) for o in hidden}
    plan.commands[:] = [c for c in plan.commands if not (c[0] == 'paste'
        and tuple(c[2]) + c[1].size in boxes)]
    for obj in hidden:
        obj['label_body_suppressed'] = True
    metrics['objects'] = [o for o in objects if o not in hidden]
    metrics['suppressed_label_boxes'] = [o['id'] for o in hidden]
