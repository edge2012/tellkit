from worker.design_tokens import PALETTE, STROKE, RADIUS, SHADOW, TYPE
from worker.json_files import file_sha256
from worker.peak_memory import PeakMemory
from worker.render_resources import release_scene
from app.aspects import delivery_aspects, delivery_sizes
"""Deterministic Pillow frames and sample-aligned audio, streamed to ffmpeg."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import wave
import tempfile
import threading
from worker.encoding import run as run_encoder, failure as encode_failure, TIMEOUT as ENCODE_TIMEOUT

from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont
from worker.frame_pool import ordered_frames
from app.expression_contract import visual_payload
from worker.visual import Storyboard, frame as legacy_frame, normalize, label_for

# Compatibility export for callers of the old frame API. render() selects style explicitly.
frame = legacy_frame

ROOT = Path(__file__).resolve().parents[1]
BG, INK, BLUE = PALETTE['background'], STROKE['color'], PALETTE['primary']
OUTPUTS = {'video-16x9': 'video-16x9.mp4', 'video-9x16': 'video-9x16.mp4',
           'audio': 'audio.m4a', 'cover': 'cover.jpg'}


from functools import lru_cache


@lru_cache(maxsize=16)
def _font_cmap(path, mtime_ns, size):
    # Static font metadata is shared by all character/label instances.
    with TTFont(path) as font:
        return font.getBestCmap()


class Fonts:
    def __init__(self):
        root = Path(os.getenv('TELLKIT_FONT_DIR', str(ROOT / 'assets/fonts')))
        self.paths = [root / 'TellkitHappySubset-Regular.ttf',
                      root / 'TellkitSansSubset-Regular.otf',
                      Path(os.getenv('TELLKIT_FALLBACK_FONT', str(ROOT / 'assets/worker-fonts/SourceHanSansCN-Regular.otf')))]
        self.maps = []
        self.cache = {}
        for path in self.paths:
            if not path.is_file():
                from worker.errors import PipelineFailure
                raise PipelineFailure('ENCODE_FONT_MISSING', dict(code='ENCODE_FONT_MISSING',
                    message=f'编码前字体检查失败：文件不存在 {path}', phase='font_preflight',
                    inputs=[dict(path=str(path), bytes=None)]))
            stat=path.stat()
            self.maps.append(_font_cmap(str(path.resolve()),stat.st_mtime_ns,stat.st_size))

    def font(self, char, size):
        for index, cmap in enumerate(self.maps):
            if ord(char) in cmap:
                key = index, size
                if key not in self.cache:
                    self.cache[key] = ImageFont.truetype(str(self.paths[index]), size)
                return self.cache[key]
        raise ValueError(f'FONT_MISSING: U+{ord(char):04X}')

    def text(self, draw, xy, text, size, max_width):
        # Resolve every character; never silently draw .notdef boxes.
        while size > 12:
            width = sum(self.font(c, size).getlength(c) for c in text)
            if width <= max_width:
                break
            size -= 2
        x, y = xy
        for char in text:
            font = self.font(char, size)
            draw.text((x, y), char, font=font, fill=INK, anchor='lt')
            x += font.getlength(char)


def ffmpeg(args, **kwargs):
    return run_encoder([os.getenv('FFMPEG', 'ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y', *args], check=True, **kwargs)


def event(stage, progress):
    print(json.dumps({'stage': stage, 'progress': progress}), flush=True)


@PeakMemory("audio-prepare")
def prepare_audio(board, out, sources):
    parts = []
    for index, scene in enumerate(board.scenes):
        part = out / f'scene-{index}.pcm'
        samples = scene.duration_ms*48
        if sources:
            ffmpeg(['-i', str(sources[index]), '-af', f'aresample=48000,apad,atrim=end_sample={samples},asetpts=PTS-STARTPTS',
                    '-ar', '48000', '-ac', '1', '-f', 's16le', str(part)])
        else:
            part.write_bytes(b'\0' * samples*2)
        data = part.read_bytes()
        # Sample count is authoritative even if input resampling rounds a boundary.
        parts.append((data+b'\0'*max(0, samples*2-len(data)))[:samples*2])
        part.unlink()
    with wave.open(str(out / 'timeline.wav'), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(48000)
        for part in parts:
            wav.writeframes(part)
    ffmpeg(['-i', str(out/'timeline.wav'), '-c:a', 'aac', '-b:a', '64k', '-ac', '1', '-ar', '48000',
            '-threads', '1', '-map_metadata', '-1', '-movflags', '+faststart', str(out/'audio.m4a')])
    (out/'timeline.wav').unlink()


@PeakMemory("render-total")
def render(board, out, sources=None, captions=None, *, aspects=None, frame_workers=None):
    from app.scene_budget import trim_board
    from app.enforcement import record
    notes=[]
    data=trim_board(board.model_dump(mode='json', by_alias=True),notes)
    if notes:
        board=type(board).model_validate(data)
        record(notes,'render_budget')
        Path(out).mkdir(parents=True,exist_ok=True)
        (Path(out)/'storyboard.json').write_text(json.dumps(data,ensure_ascii=False,indent=2))
    from app.action_geometry import ActionGeometryError
    from worker.scenekit_renderer import SceneRenderError
    try:
        return _render(board, out, sources, captions, aspects=aspects, frame_workers=frame_workers)
    except (ActionGeometryError, SceneRenderError) as exc:
        detail = getattr(exc, 'row', getattr(exc, 'metrics', {}))
        target = Path(out)
        target.mkdir(parents=True, exist_ok=True)
        (target/'render-report.json').write_text(json.dumps(dict(
            failure=dict(code=exc.code, measured=detail),
            healing=detail.get('attempts', detail.get('healing', []))), ensure_ascii=False, indent=2)+'\n')
        raise
    finally:
        release_scene()


def _render(board, out, sources=None, captions=None, *, aspects=None, frame_workers=None):
    aspects = delivery_aspects() if aspects is None else tuple(aspects)
    frame_workers = int(os.getenv('TELLKIT_FRAME_WORKERS', '1')) if frame_workers is None else frame_workers
    if type(frame_workers) is not int or not 1 <= frame_workers <= 4:
        raise ValueError('TELLKIT_FRAME_WORKERS must be an integer in [1,4]')
    lighting_catalog={}; lighting_frames=[]; lighting_states={}; last_lighting={}
    declaration_keys={}
    geometry_healing={}
    label_notes={}
    style = os.getenv('RENDER_STYLE', 'scenekit')
    if style not in ('legacy', 'scenekit'):
        raise ValueError('RENDER_STYLE must be scenekit or legacy')
    from worker.render_actions import require_supported
    for scene in board.scenes:
        for beat in scene.visual.beats:
            if beat.change is not None: require_supported(beat.change,style)
    if style == 'scenekit':
        from worker.scenekit_renderer import frame as kit_frame
        def frame(scene, title, size, local, fonts):
            debug={}
            result=kit_frame(scene, title, size, local, fonts, debug=debug,
                             ambient_ms=sum(s.duration_ms for s in board.scenes if s.index < scene.index)+local*scene.duration_ms,
                             captions=(captions or {}).get(scene.index),
                             previous_scene=next((s for s in board.scenes if s.index==scene.index-1),None),
                             episode_progress=(sum(s.duration_ms for s in board.scenes if s.index < scene.index)+local*scene.duration_ms)/board.total_duration_ms)
            for note in debug.get("label_notes", []):
                key=(scene.index,size,note["object"],note["text"])
                label_notes[key]=dict(note,scene=scene.index,size=size)
            last_lighting.clear();last_lighting.update(debug)
            return result
    else:
        frame = legacy_frame
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    fonts = Fonts()
    for scene in board.scenes:
        texts = [('text', board.title+scene.narration+(scene.on_screen_text or ''))]
        texts += [(str(i+1), label_for(item)) for i,item in enumerate(normalize(scene.visual).items)]
        for item_id, text in texts:
            for char in text:
                try:
                    fonts.font(char, 24)
                except ValueError:
                    from worker.scenekit_renderer import SceneRenderError
                    raise SceneRenderError(scene.index,item_id,'font',f'missing glyph U+{ord(char):04X}')
    event('tts', 10)
    audio_started = time.monotonic()
    prepare_audio(board, out, sources)
    audio_seconds = time.monotonic()-audio_started
    metrics = {'render_style': style, 'audio_prepare_seconds': audio_seconds, 'frame_workers': frame_workers}
    frames = (board.total_duration_ms*30+500)//1000
    for kind, size, base in [('16x9', (1280,720), 20), ('9x16', (720,1280), 55)]:
        if aspects is not None and kind not in aspects:
            continue
        stage = 'render-'+kind
        event(stage, base)
        started = time.monotonic()
        with PeakMemory(stage+"-prepare"):
            # Prepare glyphs and reusable silhouettes outside the 30fps drawing loop.
            prepare_started = time.monotonic()
            for scene in board.scenes:
                frame(scene, board.title, size, .5, fonts).close()
                if normalize(scene.visual).motion == 'count':
                    for step in range(33):
                        frame(scene, board.title, size, min(1, step*250/scene.duration_ms), fonts).close()
                release_scene()
            if style == 'scenekit':
                from worker.scenekit_renderer import stage as measure_stage, SceneRenderError
                from worker.composition_b5 import episode_violations
                spatial = [measure_stage(json.dumps(visual_payload(s)),size,s.index,1000)[1]
                           for s in board.scenes if s.visual.spatial_frame in {'ground','table','tank'} and s.visual.background]
                errors = episode_violations(spatial,size)
                from app.enforcement import blocks
                if blocks(errors, 'episode'):
                    raise SceneRenderError('episode','scene','composition',str(errors))
        prepare_seconds = time.monotonic()-prepare_started
        frame_hashes = []
        encode_seconds = 0
        draw_seconds = 0
        max_frame = 0
        cmd = [os.getenv('FFMPEG', 'ffmpeg'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
               '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{size[0]}x{size[1]}', '-r', '30', '-i', 'pipe:0',
               '-map', '0:v', '-c:v', 'libx264', '-preset', 'veryfast',
               '-crf', '20', '-pix_fmt', 'yuv420p', '-threads', '1',
               '-map_metadata', '-1', '-movflags', '+faststart', str(out/f'video-{kind}-silent.mp4')]
        spool = tempfile.TemporaryDirectory(prefix='frames-', dir=out)
        stderr_file = tempfile.TemporaryFile()
        try:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=stderr_file)
        except OSError as exc:
            spool.cleanup()
            stderr_file.close()
            raise encode_failure(cmd, None, str(exc), 900, input_bytes=0) from exc
        # Kill even when a blocked pipe write cannot return to the supervisor loop.
        timeout = 900
        timed_out = threading.Event()
        def expire():
            if proc.poll() is None:
                timed_out.set()
                proc.kill()
        timer = threading.Timer(timeout, expire)
        timer.daemon = True
        timer.start()
        input_bytes = 0
        try:
            def tasks():
                scene_idx, boundary = 0, board.scenes[0].duration_ms
                for f in range(frames):
                    ms = f*1000/30
                    while ms >= boundary and scene_idx < len(board.scenes)-1:
                        scene_idx += 1
                        boundary += board.scenes[scene_idx].duration_ms
                    scene = board.scenes[scene_idx]
                    local = (ms-(boundary-scene.duration_ms))/scene.duration_ms
                    yield f, ms, scene, local

            active_scene = None
            def draw(task):
                nonlocal active_scene
                if active_scene != task[2].index:
                    release_scene()
                    active_scene = task[2].index
                f, ms, scene, local = task
                tick = time.monotonic()
                im = frame(scene, board.title, size, local, fonts)
                path = Path(spool.name)/f'{f:08d}.rgb'
                try:
                    if kind == '16x9' and f == 0:
                        im.save(out/'cover.jpg', quality=92, subsampling=0)
                    path.write_bytes(im.tobytes())
                finally:
                    im.close()
                return f, ms, scene.index, path, dict(last_lighting), dict(label_notes), time.monotonic()-tick

            with PeakMemory(stage+"-frames-and-encode"):
                items = tasks()
                pool_options = {}
                if frame_workers > 1 and style == 'scenekit':
                    from worker.frame_renderer import configuration, initialize
                    pool_options = dict(initializer=initialize, initargs=(
                        configuration(board, captions, size, kind, out, spool.name),))
                    items = ((f, ms, scene.index, local) for f, ms, scene, local in items)
                with ordered_frames(draw, items, frame_workers, **pool_options) as results:
                    for f, ms, scene_index, path, lighting, notes, elapsed in results:
                        if f % 30 == 0:
                            import shutil
                            from app.degradation import disk_notice
                            disk_notice(out)
                        label_notes.update(notes)
                        last_lighting.clear(); last_lighting.update(lighting)
                        # Persist stage declarations and checks associated with encoded frames.
                        # Repeated states and records are content-addressed, not re-rendered.
                        import hashlib
                        for attempt in last_lighting.get('healing', []):
                            geometry_healing[json.dumps(attempt, sort_keys=True)] = attempt
                        objects=[]
                        for obj in last_lighting.get('objects',[]):
                            declaration=obj.get('lighting_declaration')
                            identity=hashlib.sha256(json.dumps(declaration,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                            if identity not in declaration_keys:
                                serial=json.dumps(declaration,sort_keys=True,separators=(',',':'))
                                key=hashlib.sha256(serial.encode()).hexdigest()
                                lighting_catalog[key]=declaration
                                declaration_keys[identity]=(key,declaration)
                            key=declaration_keys[identity][0]
                            objects.append(dict(symbol_position_source=obj.get('symbol_position_source'),phenomenon_geometry=obj.get('phenomenon_geometry'),symbol_label=obj.get('symbol_label'),ground=obj.get('ground'),ground_error_px=obj.get('ground_error_px'),visible_bottom_y=obj.get('visible_bottom_y'),shadow=obj.get('shadow'),rests_on=obj.get('rests_on'),attached_to=obj.get('attached_to'),render_channel=obj.get('render_channel'),on_surface=obj.get('on_surface'),object=obj.get('id',obj.get('name',obj['shape'])),shape=obj['shape'],bbox=obj.get('bbox'),visible=obj.get('visible',True),fill_rgb=obj.get('fill_rgb'),opacity=obj.get('opacity',1),parent=obj.get('parent'),component_bboxes=obj.get('component_bboxes',[]),frame_component_bboxes=obj.get('frame_component_bboxes'),split_children=obj.get('split_children',[]),split_gap_px=obj.get('split_gap_px'),original_sprite_visible=obj.get('original_sprite_visible'),declaration=key))
                        state=dict(objects=objects, split_base_areas=last_lighting.get('split_base_areas', []), info=last_lighting.get('info', []), overlap_permissions=last_lighting.get('overlap_permissions', []), placements=[r for r in last_lighting.get('render_actions', []) if r.get('placement')], hits=[hit for hit in last_lighting.get('pixel_violations',[]) if hit['code'] in {'HIGHLIGHT_GRAMMAR','HIGHLIGHT_DECLARATION_MISMATCH'}])
                        serial=json.dumps(state,sort_keys=True,separators=(',',':'))
                        key=hashlib.sha256(serial.encode()).hexdigest();lighting_states[key]=state
                        lighting_frames.append(dict(aspect=kind,frame=f,scene=scene_index,ms=ms,state=key))
                        draw_seconds += elapsed
                        max_frame = max(max_frame, elapsed)
                        # Only a filename crosses the pool boundary. Map one completed
                        # frame and feed its buffer directly to ffmpeg, then unlink it.
                        import mmap
                        encode_tick = time.monotonic()
                        try:
                            with path.open('rb') as source, mmap.mmap(source.fileno(), 0, access=mmap.ACCESS_READ) as raw:
                                frame_hashes.append(hashlib.sha256(raw).hexdigest())
                                proc.stdin.write(raw)
                                input_bytes += len(raw)
                        finally:
                            path.unlink(missing_ok=True)
                        encode_seconds += time.monotonic()-encode_tick
                        if f % 30 == 0:
                            event(stage, base+int(34*f/frames))
            encode_tick = time.monotonic()
            proc.stdin.close()
            if proc.wait(timeout=ENCODE_TIMEOUT) != 0:
                stderr_file.seek(0)
                raise encode_failure(cmd, proc.returncode, stderr_file.read(), timeout, input_bytes=input_bytes, timed_out=timed_out.is_set())
            encode_seconds += time.monotonic()-encode_tick
        except (BrokenPipeError, subprocess.TimeoutExpired) as exc:
            if proc.poll() is None:
                proc.kill()
            proc.wait()
            stderr_file.seek(0)
            raise encode_failure(cmd, proc.returncode, stderr_file.read(), timeout, input_bytes=input_bytes, timed_out=timed_out.is_set() or isinstance(exc, subprocess.TimeoutExpired)) from exc
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            if proc.stdin is not None:
                try:
                    proc.stdin.close()
                except OSError:
                    pass  # Preserve the original rendering/encoding failure.
            stderr_file.close()
            spool.cleanup()
            release_scene()
        mux_started = time.monotonic()
        ffmpeg(['-i', str(out/f'video-{kind}-silent.mp4'), '-i', str(out/'audio.m4a'),
                '-map', '0:v', '-map', '1:a', '-c', 'copy', '-map_metadata', '-1',
                '-movflags', '+faststart', str(out/f'video-{kind}.mp4')])
        mux_seconds = time.monotonic()-mux_started
        (out/f'video-{kind}-silent.mp4').unlink()
        (out/f'frame-hashes-{kind}.json').write_text(json.dumps(frame_hashes))
        metrics[stage] = {'seconds': round(time.monotonic()-started,3), 'frames': frames, 'encode_pipe_seconds': encode_seconds, 'mux_seconds': mux_seconds, 'prepare_ms': round(prepare_seconds*1000,3),
                          'frame_mean_ms': round(draw_seconds/frames*1000,3), 'frame_max_ms': round(max_frame*1000,3)}
    event('encode', 90)
    (out/'lighting-declarations.json').write_text(json.dumps(dict(version=1,pixel_space='stage_before_transition_and_text',catalog=lighting_catalog,states=lighting_states,frames=lighting_frames),ensure_ascii=False))
    (out/'render_manifest.json').write_text(json.dumps(dict(version=1, pixel_space='stage_before_transition_and_text', canvas={a: delivery_sizes().get(a, (720,1280)) for a in aspects}, states={key:dict(objects=value['objects'], placements=value['placements'], overlap_permissions=value['overlap_permissions'], split_base_areas=value['split_base_areas'], info=value['info']) for key,value in lighting_states.items()}, frames=lighting_frames),ensure_ascii=False))
    # Validate completed paint output against the exact manifest declarations.
    from worker.render_actions import audit_scene, verify_movie, RenderActionError
    manifest_path = out/'render_manifest.json'
    action_manifest = json.loads(manifest_path.read_text())
    from app.layout_validation import overlap_craft
    from app.enforcement import record
    action_manifest['craft_notes'] = overlap_craft(
        [r for state in action_manifest['states'].values() for r in state['overlap_permissions']],
        [frame['scene'] for frame in action_manifest['frames']])
    record(action_manifest['craft_notes'], 'layout')
    action_manifest['actions'] = []
    try:
        with PeakMemory("encoded-action-audit"):
            for aspect,size in [('16x9',(1280,720)),('9x16',(720,1280))]:
                if aspects is not None and aspect not in aspects: continue
                offset_ms=0
                for scene in board.scenes:
                    receipts=audit_scene(scene.model_dump(by_alias=True),size)
                    action_manifest['actions'].extend(receipts)
                    for receipt in receipts:
                        verify_movie(receipt,out/f'video-{aspect}.mp4',offset_ms)
                    offset_ms+=scene.duration_ms
                    release_scene()
    except RenderActionError as exc:
        action_manifest['action_failure'] = dict(code=exc.code, **exc.detail)
        raise
    finally:
        manifest_path.write_text(json.dumps(action_manifest,ensure_ascii=False))
    metrics['healing'] = list({**geometry_healing, **{json.dumps(h, sort_keys=True): h
        for receipt in action_manifest['actions']
        for h in receipt['declaration'].get('healing', [])}}.values())
    metrics['layout_repairs'] = metrics['healing']
    action_manifest['healing'] = metrics['healing']
    manifest_path.write_text(json.dumps(action_manifest, ensure_ascii=False))
    metrics['label_notes']=list(label_notes.values())
    (out/'render-report.json').write_text(json.dumps(metrics, indent=2)+'\n')
    print(json.dumps({'metrics': metrics}), flush=True)
    return metrics


def manifest(out, prefix, duration):
    assets = []
    for kind, name in OUTPUTS.items():
        if kind == 'video-9x16' and not (Path(out)/name).exists():
            continue
        path = Path(out)/name
        item = {'kind': kind, 'path': f'{prefix}/{name}', 'bytes': path.stat().st_size,
                'sha256': file_sha256(path)}
        if kind != 'cover':
            item['duration_ms'] = duration
        if kind.startswith('video') or kind == 'cover':
            item['width'], item['height'] = (1280,720) if kind in ('video-16x9', 'cover') else (720,1280)
        assets.append(item)
    return assets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--storyboard', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--audio-dir', type=Path, help='Per-scene 1.mp3 …; omitted: deterministic silence for offline rendering')
    args = parser.parse_args()
    board = Storyboard.model_validate_json(args.storyboard.read_text())
    sources = [args.audio_dir/f'{s.index}.mp3' for s in board.scenes] if args.audio_dir else None
    from worker.postcheck import render_checked
    render_checked(board, args.out, render, sources=sources)


if __name__ == '__main__':
    main()
