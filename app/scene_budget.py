"""Nonblocking visual budget, shared by author handoff and render fallback."""
from copy import deepcopy


def trim(visual, narration='', scene=0):
    # W324 keeps all detail objects. Role quotas are applied to final drawables,
    # including repeated instances; no declaration or narration is discarded.
    return deepcopy(visual), []


def trim_board(board, notes):
    for scene in board['scenes']:
        scene['visual'],hits=trim(scene['visual'],scene.get('narration',''),scene.get('index',0))
        notes.extend(hits)
        if hits:
            ids={it['id'] for it in scene['visual']['items']}
            if isinstance(scene.get('subject'),list):
                scene['subject']=[s for s in scene['subject'] if s.get('ref') in ids]
            if isinstance(scene.get('relation'),list):
                scene['relation']=[r for r in scene['relation'] if r.get('from') in ids and r.get('to') in ids]
    return board
