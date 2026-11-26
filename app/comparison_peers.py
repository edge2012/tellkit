"""Resolve distinct comparison identities and report measured visibility evidence."""
from app.response_assembly import required_first
import re
from app.json_safe import sanitize_audit

FAMILIES = (
    {'cookie', 'cookie_whole', 'cookie_half', 'cookie_large', 'cookie_small'},
    {'shoe', 'shoe_left', 'shoe_right', 'foot_left', 'foot_right'},
    {'route_long', 'route_short'}, {'tank_stone', 'tank_wood'},
    {'water', 'water_drop', 'drop', 'ice', 'ice_block', 'ice_melting'},
    {'water_cup_tall', 'water_cup_wide'}, {'stone', 'wood'},
)

# These are specific diagnoses of the existing missing-comparison rule, not
# additional visual hard rules. Keep the approved HARD_CODES inventory intact.
COMPARISON_ERRORS = frozenset({
    'COMPARISON_MISSING_PEER', 'COMPARISON_PEER_SELF',
    'COMPARISON_NO_PEER_CANDIDATE', 'COMPARISON_SINGLE_VISIBLE',
})


def family(shape):
    return next((str(i) for i, shapes in enumerate(FAMILIES) if shape in shapes), shape)


def eligible(obj):
    return (obj.get('role', 'subject') in {'subject', 'tool', 'result'}
            and obj.get('shape') not in {'awen', 'arrow', 'curved_arrow'})


def label_prefix(obj):
    return re.split(r'[\s_\-:：\d]+', obj.get('label') or '')[0]


def visibility(objects, obj, size=None):
    """Return a reason and occluder; never compare an object with itself."""
    if not obj.get('visible', True):
        return 'invisible', None
    box = obj.get('bbox')
    if box is None:
        return None, None
    x, y, w, h = box
    if w <= 0 or h <= 0 or (size and (x < 0 or y < 0 or x+w > size[0] or y+h > size[1])):
        return 'outside frame', None
    if size:
        index = required_first(((i for i, other in enumerate(objects) if other is obj)), path='worker/app/comparison_peers.py:45')
        for other in objects[index+1:]:
            if other.get('id') == obj.get('id') or not other.get('visible', True) or not other.get('bbox'):
                continue
            a, b, c, d = other['bbox']
            if a <= x and b <= y and a+c >= x+w and b+d >= y+h:
                # A sparse sprite (e.g. knife) does not fill its bounding box.
                # When raster evidence exists, require full alpha coverage too.
                from PIL import Image, ImageChops
                mask, cover = obj.get('pixel_mask'), other.get('pixel_mask')
                if isinstance(mask, Image.Image) and isinstance(cover, Image.Image):
                    covered = cover.crop((x-a, y-b, x-a+w, y-b+h))
                    if ImageChops.subtract(mask.convert('L'), covered.convert('L')).getbbox() is not None:
                        continue
                return 'fully occluded', other.get('id')
    return None, None


def finding(code, scene, subject_id, measured):
    return dict(code=code, tier='info' if code == 'COMPARISON_PEER_SUBSTITUTED' else 'hard',
                rule='COMPARISON_MISSING_PEER', scene=scene, object=subject_id,
                measured=sanitize_audit(measured),
                threshold='two distinct comparison objects present, in frame and visible')


def resolve_peer(objects, subject_id, scene=1, *, comparison=None, size=None):
    """Explicit declaration wins; otherwise match shape or a nonempty label prefix.

    Return the resolution even on success so replays can audit candidate choice.
    IDs are scene-local item IDs, not the semantic subject_id shared by sprites.
    """
    found = [o for o in objects if o.get('id') == subject_id]
    subject = found[0] if len(found) == 1 else None
    inventory = [dict(id=o.get('id'), shape=o.get('shape'), label=o.get('label'),
                      bbox=o.get('bbox'), reason=visibility(objects, o, size)[0]) for o in objects]
    candidates = [o for o in objects if subject and eligible(o) and o.get('id') != subject_id
                  and ((subject.get('shape') and o.get('shape') == subject['shape'])
                       or (label_prefix(subject) and label_prefix(o) == label_prefix(subject)))]
    explicit = comparison if comparison is not None else (subject or {}).get('comparison') or {}
    peer_id = explicit.get('peer_id')
    trace = dict(subject_id=subject_id, peer_id=peer_id, candidates=[o['id'] for o in candidates],
                 objects=inventory, source='explicit' if peer_id is not None else 'shape_or_label')
    def fail(code, reason, **extra):
        trace.update(reason=reason, **extra)
        return sanitize_audit(trace), [finding(code, scene, subject_id, trace)]
    if peer_id == subject_id:
        return fail('COMPARISON_PEER_SELF', 'comparison.peer_id equals subject_id; self comparison is forbidden')
    if subject is None:
        return fail('COMPARISON_MISSING_PEER', 'subject missing or duplicated', actual=found)
    if peer_id is None:
        if not candidates:
            visible = [o for o in objects if eligible(o) and not visibility(objects, o, size)[0]]
            code = 'COMPARISON_SINGLE_VISIBLE' if len(visible) == 1 and visible[0]['id'] == subject_id else 'COMPARISON_NO_PEER_CANDIDATE'
            return fail(code, 'only the subject is visible' if code.endswith('SINGLE_VISIBLE') else 'no same-shape or label-prefix peer candidate')
        peer_id = candidates[0]['id']
        trace['peer_id'] = peer_id
    matches = [o for o in objects if o.get('id') == peer_id]
    if len(matches) != 1:
        return fail('COMPARISON_MISSING_PEER', 'peer missing or duplicated', expected=dict(id=peer_id), actual=matches)
    peer = matches[0]
    reason, occluder = visibility(objects, peer, size)
    if reason == 'fully occluded':
        replacements = [o for o in objects if eligible(o) and o.get('id') not in {subject_id, peer_id}
                        and o.get('shape') == peer.get('shape') and not visibility(objects, o, size)[0]]
        if replacements:
            trace.update(peer_id=replacements[0]['id'], original_peer_id=peer_id,
                         reason=reason, occluder_id=occluder,
                         replacement_candidates=[o['id'] for o in replacements])
            return trace, [finding('COMPARISON_PEER_SUBSTITUTED', scene, subject_id, trace)]
    if reason:
        visible = [o for o in objects if eligible(o) and
                   (o['id'] == subject_id or o in candidates or o['id'] == peer_id)
                   and not visibility(objects, o, size)[0]]
        code = 'COMPARISON_SINGLE_VISIBLE' if len(visible) == 1 and visible[0]['id'] == subject_id else 'COMPARISON_MISSING_PEER'
        return fail(code, reason, occluder_id=occluder, expected=dict(id=peer_id), actual=matches,
                    explanation='only the subject is visible' if code.endswith('SINGLE_VISIBLE') else 'peer is not visible')
    return trace, []


def check_peers(objects, scene=1, *, peers=None, size=None, resolutions=None):
    objects = [dict(o, id=o.get('id') or str(i)) for i, o in enumerate(objects)]
    if peers == []:
        return []  # A non-comparison ledger cell has no pair contract.
    declared = peers is not None
    if peers is None:
        candidates = [o for o in objects if eligible(o)]
        # item_1 is the conventional anchor, never an implicit peer of itself.
        anchor = next((o for o in candidates if o['id'] == 'item_1'), next(iter(candidates), None))
        peers = [dict(id=anchor['id'])] if anchor else []
    hits = []
    # Reject self declarations on either side before visibility can hide them.
    for obj in objects:
        if (obj.get('comparison') or {}).get('peer_id') == obj['id']:
            trace, errors = resolve_peer(objects, obj['id'], scene, size=size)
            if resolutions is not None: resolutions.append(trace)
            hits.extend(errors)
    if hits:
        return hits
    if len(peers) > 1 and peers[0]['id'] == peers[1]['id']:
        trace, hits = resolve_peer(objects, peers[0]['id'], scene,
                                   comparison=dict(peer_id=peers[1]['id']), size=size)
        if resolutions is not None: resolutions.append(trace)
        return hits
    # Preserve explicit ledger identities (which may be different shape variants).
    if declared:
        for peer in peers:
            found = [o for o in objects if o['id'] == peer['id']]
            if len(found) != 1:
                hits.append(finding('COMPARISON_MISSING_PEER', scene, peer['id'],
                            dict(peer_id=peer['id'], reason='missing or duplicated', expected=peer, actual=found)))
        if hits: return hits
    if not peers:
        return [finding('COMPARISON_NO_PEER_CANDIDATE', scene, 'scene', dict(objects=[dict(id=o['id'], shape=o.get('shape')) for o in objects], candidates=[], reason='no comparison objects'))]
    anchor_id = peers[0]['id']
    comparison = None
    if len(peers) > 1:
        # If one endpoint is hidden, resolve from the visible endpoint so an
        # alternative can replace the hidden peer without selecting itself.
        first = required_first(((o for o in objects if o['id'] == anchor_id)), path='worker/app/comparison_peers.py:163')
        second = required_first(((o for o in objects if o['id'] == peers[1]['id'])), path='worker/app/comparison_peers.py:164')
        if visibility(objects, first, size)[0] and not visibility(objects, second, size)[0]:
            anchor_id = second['id']
            comparison = dict(peer_id=first['id'])
        else:
            comparison = dict(peer_id=second['id'])
    elif not declared:
        anchor = required_first(((o for o in objects if o['id'] == anchor_id)), path='worker/app/comparison_peers.py:171')
        if visibility(objects, anchor, size)[0]:
            other = next((o for o in objects if eligible(o) and o['id'] != anchor_id
                          and o.get('shape') == anchor.get('shape') and not visibility(objects, o, size)[0]), None)
            if other:
                comparison = dict(peer_id=anchor_id)
                anchor_id = other['id']
    anchor = required_first(((o for o in objects if o['id'] == anchor_id)), path='worker/app/comparison_peers.py:178')
    comparison = anchor.get('comparison') or comparison
    trace, hits = resolve_peer(objects, anchor_id, scene, comparison=comparison, size=size)
    reason, occluder = visibility(objects, anchor, size)
    if reason:
        trace.update(reason=reason, occluder_id=occluder, actual=[anchor])
        trace = sanitize_audit(trace)
        hits = [finding('COMPARISON_MISSING_PEER', scene, anchor_id, trace)]
    if resolutions is not None: resolutions.append(trace)
    return hits
