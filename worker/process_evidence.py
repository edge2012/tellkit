"""Bounded subprocess diagnostics, never intended as public copy."""
import os
from pathlib import Path
import re
import shlex
import subprocess
from worker.errors import PipelineFailure

TIMEOUT = 120


def redact(value):
    text = str(value)
    for key, secret in os.environ.items():
        if len(secret) >= 4 and any(word in key.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD', 'PSK')):
            text = text.replace(secret, '[REDACTED]')
    text = re.sub(r'(?i)(bearer\s+)[^\s]+', r'\1[REDACTED]', text)
    return re.sub(r'(?i)((?:key|token|secret|password)=)[^\s&]+', r'\1[REDACTED]', text)


def detail(command, exc, timeout=TIMEOUT, *, paths=(), duration_ms=None):
    stderr = getattr(exc, 'stderr', None) or str(exc)
    if isinstance(stderr, bytes):
        stderr = stderr.decode('utf-8', 'replace')
    inputs = []
    for path in paths:
        try:
            size = Path(path).stat().st_size
        except OSError:
            size = None
        inputs.append(dict(path=redact(path), bytes=size, duration_ms=duration_ms))
    from app.error_codes import detail_tail
    return dict(command=redact(shlex.join([str(x) for x in command])),
                detail_tail=detail_tail(stderr),
                exit_code=getattr(exc, 'returncode', None),
                timed_out=isinstance(exc, subprocess.TimeoutExpired), timeout_seconds=timeout,
                stderr_tail=' '.join(redact(stderr).split())[-2000:], inputs=inputs)


def run(command, *, code, paths=(), duration_ms=None, timeout=TIMEOUT, **kwargs):
    kwargs.pop('check', None)
    kwargs.pop('capture_output', None)
    try:
        return subprocess.run(command, check=True, capture_output=True, timeout=timeout, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PipelineFailure(code, detail(command, exc, timeout, paths=paths, duration_ms=duration_ms)) from exc


def craft_receipt(root):
    import json
    from app.enforcement import craft_metadata, write_craft_audit
    def receipt(rows):
        write_craft_audit(root, rows)
        return dict(craft_note='TRIM_SKIPPED', craft_notes=craft_metadata(rows)) if rows else {}
    journal = Path(root)/'trim-notes.jsonl'
    if journal.exists():
        rows = [json.loads(line) for line in journal.read_text().splitlines()]
        return receipt(rows)
    rows = []
    for path in sorted(Path(root).rglob('*.trim-note.json')):
        rows.append(json.loads(path.read_text()))
    return receipt(rows)


async def async_run(command, *, code, input=None, paths=(), timeout=TIMEOUT):
    import asyncio
    process = None
    communication = None
    try:
        process = await asyncio.create_subprocess_exec(*command,
            stdin=asyncio.subprocess.PIPE if input is not None else None,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            communication = asyncio.create_task(process.communicate(input))
            out, stderr = await asyncio.wait_for(asyncio.shield(communication), timeout)
        except TimeoutError as exc:
            process.kill()
            out, stderr = await communication
            raise subprocess.TimeoutExpired(command, timeout, output=out, stderr=stderr) from exc
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, command, stderr=stderr)
        return out
    except (OSError, subprocess.SubprocessError) as exc:
        evidence = detail(command, exc, timeout, paths=paths)
        if input is not None:
            evidence['inputs'].append(dict(path='pipe:0', bytes=len(input), duration_ms=None))
        raise PipelineFailure(code, evidence) from exc
    finally:
        if process is not None and process.returncode is None:
            process.kill()
            await process.wait()
        if communication is not None and not communication.done():
            await asyncio.gather(communication, return_exceptions=True)


def redact_internal(value, *secrets):
    """Internal receipts keep replayable paths while still removing credentials."""
    if isinstance(value, str):
        value = redact(value)
        for secret in sorted(filter(None, secrets), key=len, reverse=True):
            value = value.replace(secret, '[REDACTED]')
        return value
    if isinstance(value, dict):
        cleaned = {key: redact_internal(item, *secrets) for key, item in value.items()}
        if isinstance(cleaned.get('stderr_tail'), str):
            cleaned['stderr_tail'] = ' '.join(cleaned['stderr_tail'].split())[-2000:]
        return cleaned
    if isinstance(value, list):
        return [redact_internal(item, *secrets) for item in value]
    return value


def compact_completion_notes(payload):
    from app.enforcement import craft_metadata
    audit = payload.get('storyboard_audit')
    if isinstance(audit, dict):
        notes = audit.get('craft_notes', []) + payload.pop('craft_notes', [])
        audit['craft_notes'] = craft_metadata(notes)
    elif isinstance(payload.get('craft_notes'), list):
        payload['craft_notes'] = craft_metadata(payload['craft_notes'])


def failure_code(stderr, fallback='PIPELINE_PROCESS_FAILED'):
    """Extract explicit child exception codes, never arbitrary prose."""
    import json
    if isinstance(stderr, bytes):
        stderr = stderr.decode('utf-8', 'replace')
    def specific(value):
        return isinstance(value, str) and re.fullmatch(r'[A-Z][A-Z0-9_]+', value) and value not in {'STAGE_EXCEPTION', 'PIPELINE_FAILED', 'PIPELINE_PROCESS_FAILED', 'UNKNOWN_CHILD_ERROR', 'UNKNOWN', 'UNSPECIFIED_REASON'}
    for line in reversed(str(stderr or '').splitlines()):
        try:
            row = json.loads(line.removeprefix('STAGE_EXCEPTION ').strip())
        except ValueError:
            row = None
        if isinstance(row, dict) and (row.get('error') == 'PipelineFailure' or row.get('code') == 'STAGE_EXCEPTION' or line.startswith('STAGE_EXCEPTION ')):
            for source in (row.get('measured'), row.get('breakdown'), row):
                if isinstance(source, dict):
                    for key in ('reason_code', 'reason', 'code'):
                        if specific(source.get(key)):
                            return source[key]
        match = re.search(r"(?:PipelineFailure\s*\(\s*code\s*=\s*['\"]?([A-Z][A-Z0-9_]+)|PipelineFailure:\s*([A-Z][A-Z0-9_]+)\s*$|STAGE_EXCEPTION\s+code\s*=\s*['\"]?([A-Z][A-Z0-9_]+))", line)
        if match:
            value = next(v for v in match.groups() if v)
            if specific(value):
                return value
    return fallback
