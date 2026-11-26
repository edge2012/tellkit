"""Render the bundled board without services or credentials."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import json
import os
from demo.offline import install, NOTES
install()
from worker.visual import Scene
from demo.offline import Storyboard as InputBoard
from worker.render import render
from pydantic import Field, model_validator

class DemoBoard(InputBoard):
    scenes: list[Scene] = Field(min_length=2, max_length=3)

    @model_validator(mode='after')
    def timeline(self):
        if sum(s.duration_ms for s in self.scenes) != self.total_duration_ms:
            raise ValueError('Scene durations must sum to the timeline')
        return self

def main():
    os.environ['RENDER_STYLE'] = 'scenekit'
    board = DemoBoard.model_validate_json((ROOT/'demo/storyboard.json').read_text())
    out = ROOT/'out'
    render(board, out, aspects=('16x9',), frame_workers=1)
    receipts = json.loads((out/'render_manifest.json').read_text())['actions']
    if not receipts or not all(r['passed'] for r in receipts):
        raise RuntimeError('Action evidence did not pass')
    (out/'video-16x9.mp4').replace(out/'episode.mp4')
    (out/'offline-diagnostics.json').write_text(json.dumps(NOTES, ensure_ascii=False, indent=2))
    print('Rendered out/episode.mp4')

if __name__ == '__main__':
    main()
