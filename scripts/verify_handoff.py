"""Verify every shipped file with Python's standard library, before installation."""
import hashlib
import json
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def main():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'HANDOFF_MANIFEST.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file() or digest(path) != expected:
            raise SystemExit(f'FAIL: {name}')
    print(f"PASS: {len(manifest['files'])} files verified; model {manifest['run']}")


if __name__ == '__main__':
    main()
