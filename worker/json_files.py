"""JSON I/O; storyboard audits use bounded, best-effort storage projections."""
import json
from pathlib import Path


def write_json(path, value, **options):
    if Path(path).name == 'storyboard-audit.json':
        from worker.audit_storage import write
        return write(path, value)
    with Path(path).open('w', encoding='utf-8') as stream:
        if not isinstance(value, dict) or any(not isinstance(k, str) for k in value) or options.get('indent') is not None or options.get('sort_keys'):
            json.dump(value, stream, **options)
            return
        # One compact value per line allows loading without a second full-file
        # string alongside the decoded tree. JSON strings escape their newlines.
        stream.write('{\n')
        for index, (key, item) in enumerate(value.items()):
            if index:
                stream.write(',\n')
            stream.write(json.dumps(key, ensure_ascii=options.get('ensure_ascii', True)))
            stream.write(': ')
            _write_value(stream, item, options)
        stream.write('\n}')


def _write_value(stream, value, options, depth=0):
    """Keep the fast C encoder, but never assemble an entire evidence array."""
    item_sep, key_sep = options.get('separators', (', ', ': '))
    if depth < 2 and isinstance(value, (list, tuple)):
        stream.write('[')
        for index, item in enumerate(value):
            if index:
                stream.write(item_sep)
            _write_value(stream, item, options, depth+1)
        stream.write(']')
    elif depth < 2 and isinstance(value, dict) and all(isinstance(k, str) for k in value):
        stream.write('{')
        for index, (key, item) in enumerate(value.items()):
            if index:
                stream.write(item_sep)
            stream.write(json.dumps(key, ensure_ascii=options.get('ensure_ascii', True)))
            stream.write(key_sep)
            _write_value(stream, item, options, depth+1)
        stream.write('}')
    else:
        stream.write(json.dumps(value, **options))


def read_json(path):
    if Path(path).name == 'storyboard-audit.json':
        from worker.audit_storage import hydrate, _FAILED_WRITES
        if str(Path(path).absolute()) in _FAILED_WRITES:
            return _FAILED_WRITES[str(Path(path).absolute())]
        with Path(path).open(encoding='utf-8') as stream:
            return hydrate(json.load(stream))
    decoder = json.JSONDecoder()
    with Path(path).open(encoding='utf-8') as stream:
        if stream.readline() == '{\n':
            result = {}
            has_members = comma = False
            try:
                for line in stream:
                    if line.strip() == '}':
                        if comma:
                            raise ValueError('trailing comma')
                        if stream.read().strip():
                            raise ValueError('trailing data')
                        return result
                    if not line.strip():
                        continue
                    if has_members and not comma:
                        raise ValueError('missing comma')
                    key, end = decoder.raw_decode(line)
                    if not isinstance(key, str) or line[end:end+2] != ': ':
                        raise ValueError('not a compact member')
                    value, end = decoder.raw_decode(line, end+2)
                    if line[end:].strip() not in ('', ','):
                        raise ValueError('trailing member data')
                    # partition() writes these aliases to the same observations.
                    # Reuse them after checking equality; external data stays valid.
                    alias = {'craft_violations': 'craft', 'blocking_violations': 'blocking'}.get(key)
                    if alias in result and result[alias] == value:
                        value = result[alias]
                    result[key] = value
                    has_members = True
                    comma = line[end:].strip() == ','
            except (ValueError, TypeError):
                pass
        stream.seek(0)
        return json.load(stream)


def file_sha256(path):
    import hashlib
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
