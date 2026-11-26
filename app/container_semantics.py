"""Parent references are scene-local stable item IDs; legacy IDs are indices."""
CONTAINERS = {'tank', 'cup', 'bowl', 'water_cup_tall', 'water_cup_wide', 'sugar_solution', 'tank_stone', 'tank_wood'}

def validate_parents(items):
    lookup = {it.id if it.id is not None else str(i): it for i,it in enumerate(items)}
    if len(lookup) != len(items):
        raise ValueError('duplicate item id')
    pure = [it for it in items if it.shape in {'tank','cup','bowl'}]
    notes = []
    for it in items:
        if pure and it.shape in {'stone','wood','water','sugar_grains'} and it.parent is None:
            # 语义提示，不拒片：缺 parent 就按独立对象画。
            notes.append(dict(code='PARENT_MISSING', object=it.id, severity='info',
                              sample=f'可用容器 id：{[c.id for c in pure]!r}'))
            continue
        if it.parent is None: continue
        parent = lookup.get(it.parent)
        if parent is None or parent is it or parent.shape not in CONTAINERS:
            # 悬空/非法 parent：断开引用继续画，不让整集失败。
            notes.append(dict(code='PARENT_INVALID', object=it.id, parent=it.parent, severity='info'))
            it.parent = None
            continue
        if parent.parent is not None or parent.count != 1 or it.count != 1:
            notes.append(dict(code='PARENT_UNSUPPORTED_NESTING', object=it.id, parent=it.parent, severity='info'))
            it.parent = None
    return notes
