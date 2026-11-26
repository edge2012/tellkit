from worker.peak_memory import PeakMemory
"""Bounded ffmpeg execution with structured, durable failure evidence."""
import os
from pathlib import Path
import subprocess
from worker.errors import PipelineFailure

TIMEOUT = 120


def failure(command, returncode, stderr, timeout=TIMEOUT, *, input_bytes=None, timed_out=False):
    if isinstance(stderr, bytes):
        stderr = stderr.decode('utf-8', errors='replace')
    from worker.process_evidence import redact
    tail = ' '.join(redact(stderr or '').split())[-2000:]
    lower = (stderr or '').lower()
    code = 'ENCODE_FAILED'
    for needles, candidate in [
        (('permission denied', 'operation not permitted', 'read-only file system'), 'PERMISSION_DENIED'),
        (('no space left on device', 'disk quota exceeded'), 'DISK_LOW'),
        (('cannot find a valid font', 'could not load font', 'font_missing', 'failed to load font'), 'ENCODE_FONT_MISSING'),
        (('no such filter', 'filter not found'), 'ENCODE_FILTER_UNSUPPORTED'),
        (('not divisible by 2', 'invalid picture size', 'invalid frame size', 'picture size 0x0', 'invalid size'), 'ENCODE_INVALID_DIMENSIONS'),
    ]:
        if any(n in lower for n in needles):
            code = candidate
            break
    inputs = []
    for index, arg in enumerate(command[:-1]):
        if arg == '-i':
            name = command[index+1]
            path = Path(name)
            try:
                size = input_bytes if name == 'pipe:0' else path.stat().st_size if path.is_file() else None
                inputs.append(dict(path=redact(name), bytes=size, duration_ms=None))
            except OSError as exc:
                inputs.append(dict(path=name, bytes=None, stat_error=str(exc)))
    detail = dict(code=code, failure_category='machine', failure_domain='media_encoding', command=redact(__import__('shlex').join(command)), exit_code=returncode, timed_out=timed_out,
                  stderr_tail=tail, inputs=inputs, output=command[-1], timeout_seconds=timeout)
    detail['message'] = (f'{code}: ffmpeg退出码={returncode}，超时设置={timeout}s；'
                         f'输出={command[-1]}；stderr尾部：\n{tail or "(无stderr输出)"}')
    detail['original_code'] = code
    detail['code'] = 'ENCODE_FAILED'
    return PipelineFailure('ENCODE_FAILED', detail)


@PeakMemory("ffmpeg")
def run(command, **kwargs):
    command = list(command)
    if '-threads' not in command:
        command[1:1] = ['-threads', '1']
        command[-1:-1] = ['-threads', '1']
    timeout = kwargs.pop('timeout', TIMEOUT)
    kwargs.pop('check', None)
    if kwargs.pop('capture_output', False):
        kwargs['stdout'] = subprocess.PIPE
    kwargs['stderr'] = subprocess.PIPE
    try:
        result = subprocess.run(command, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired as exc:
        error = failure(command, None, exc.stderr or 'ffmpeg timed out', timeout)
        error.breakdown['timed_out'] = True
        raise error from exc
    except OSError as exc:
        raise failure(command, None, str(exc), timeout) from exc
    if result.returncode:
        cause = subprocess.CalledProcessError(result.returncode, command, stderr=result.stderr)
        raise failure(command, result.returncode, result.stderr, timeout) from cause
    return result
