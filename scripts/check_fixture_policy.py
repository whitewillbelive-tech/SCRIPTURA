#!/usr/bin/env python3
"""Conservative repository fixture gate; not a substitute for rights review."""
import json
import sys
from pathlib import Path

FORBIDDEN_KEYS = frozenset({'full_text', 'raw_text', 'embedding', 'embeddings'})


def check(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc:
        return [f'{path}: cannot read fixture: {exc}']
    if not isinstance(data, dict):
        return [f'{path}: fixture must be an object']
    metadata = data.get('metadata')
    errors = []
    if not isinstance(metadata, dict) or metadata.get('is_synthetic') is not True or metadata.get('approved_for_public_display') is not False:
        errors.append(f'{path}: only explicitly synthetic, non-public-display fixtures may be committed')

    def visit(value, location):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in FORBIDDEN_KEYS:
                    errors.append(f'{path}: prohibited field at {location}.{key}')
                visit(child, f'{location}.{key}')
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f'{location}[{index}]')
    visit(data, '$')
    return errors


def main() -> int:
    fixture_dir = Path(__file__).resolve().parents[1] / 'fixtures'
    errors = [error for path in fixture_dir.rglob('*.json') for error in check(path)]
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print('PASS: checked JSON fixtures are explicitly synthetic and contain no prohibited full-text/embedding fields')
    return 0


if __name__ == '__main__':
    sys.exit(main())
