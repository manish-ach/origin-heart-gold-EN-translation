"""Exact message inventories and export equality; never writes game data.

This semantic comparison intentionally uses the production codec. Structural
independence belongs to binary_text_validator, which must be run alongside it.
Opaque source entries are only accepted when their stored units stay identical.
"""
from pathlib import Path
import json
import struct
import msgtool as m
import zh_redact


def check_inventory(source_members, candidate_members, export_dir, cm, workspace_dir=None):
    """Compare {archive_key: [bank_bytes]} with an already freshly made export."""
    errors, gaps = [], []
    counts = dict(banks=0, strings=0, opaque_banks=0, opaque_strings=0)
    export_dir = Path(export_dir)
    workspace_dir = Path(workspace_dir) if workspace_dir is not None else None

    def fail(ref, reason):
        errors.append({'ref': ref, 'reason': reason})

    def documents(root, key, expected):
        directory = root / key
        found = {p.name for p in directory.glob('*.json') if p.name != '_meta.json'}
        want = {f'{i:04d}.json' for i in expected}
        if found != want:
            fail(str(directory), f'bank inventory mismatch: missing={sorted(want-found)}, extra={sorted(found-want)}')

    def read(path, bi, n):
        try:
            obj = json.loads(path.read_text(encoding='utf-8'))
            if type(obj.get('bank')) is not int or obj['bank'] != bi:
                raise ValueError('bank identifier differs')
            if n is not None:
                entries = obj.get('strings')
                if not isinstance(entries, list) or [e.get('id') for e in entries] != list(range(n)) or any(type(e.get('id')) is not int for e in entries):
                    raise ValueError('ordered string IDs/count differ from source')
            return obj
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            fail(str(path), str(exc))
            return None

    if set(candidate_members) != set(source_members):
        fail('archives', 'candidate archive keys differ from source')
    for root in (export_dir, workspace_dir):
        if root is not None:
            found = {p.name for p in root.iterdir() if p.is_dir()} if root.exists() else set()
            if found != set(source_members):
                fail(str(root), f'archive directory inventory differs: {sorted(found)}')
    for key, originals in source_members.items():
        candidates = candidate_members.get(key, [])
        if len(candidates) != len(originals):
            fail(key, f'bank count differs: source={len(originals)}, candidate={len(candidates)}')
        documents(export_dir, key, range(len(originals)))
        decoded = []
        for i, data in enumerate(originals):
            try:
                decoded.append(m.bank_to_json(i, data, cm))
            except (ValueError, IndexError, KeyError, TypeError, struct.error) as exc:
                fail(f'{key}/{i:04d}', f'cannot inspect source: {exc}')
                decoded.append({'bank': i, 'raw_bank_hex': data.hex()})
        if workspace_dir is not None:
            documents(workspace_dir, key, [i for i, obj in enumerate(decoded) if 'strings' in obj])
        for bi, src in enumerate(decoded):
            ref = f'{key}/{bi:04d}'
            counts['banks'] += 1
            n = len(src['strings']) if 'strings' in src else None
            exp = read(export_dir / key / f'{bi:04d}.json', bi, n)
            if bi >= len(candidates) or exp is None:
                continue
            data = candidates[bi]
            if n is None:
                counts['opaque_banks'] += 1
                if data != originals[bi] or exp.get('raw_bank_hex') != originals[bi].hex() or 'strings' in exp:
                    fail(ref, 'opaque bank must match original and export bytes exactly')
                gaps.append({'ref': ref, 'reason': 'opaque bank preserved; not semantically decoded'})
                continue
            if 'raw_bank_hex' in exp:
                fail(ref, 'decoded bank cannot be replaced by opaque export')
                continue
            counts['strings'] += n
            workspace = read(workspace_dir / key / f'{bi:04d}.json', bi, n) if workspace_dir is not None else None
            if workspace is not None:
                for original, entry in zip(src['strings'], workspace['strings']):
                    if not zh_redact.matches(entry.get('zh'), original['text']):
                        fail(f'{ref}#{original["id"]}', 'workspace Chinese differs from original')
            try:
                _, stored, _ = m.decrypt_bank(data)
                if len(stored) != n:
                    fail(ref, f'candidate string count differs: {len(stored)} != {n}')
                    continue
                # Whole-bank equality also checks seed, trailer, pad and compressed storage.
                if m.json_to_bank(exp, cm) != data:
                    fail(ref, 'candidate bytes differ from encoded export')
                for original, entry, units in zip(src['strings'], exp['strings'], stored):
                    sid = original['id']
                    if 'raw_hex' in original:
                        counts['opaque_strings'] += 1
                        raw = struct.pack(f'<{len(units)}H', *units).hex()
                        if raw != original['raw_hex'] or entry.get('raw_hex') != original['raw_hex'] or entry.get('text') != original['text']:
                            fail(f'{ref}#{sid}', 'opaque string must match original units and unchanged export text/raw bytes')
                        gaps.append({'ref': f'{ref}#{sid}', 'reason': 'opaque string preserved; not semantically decoded'})
                    elif 'raw_hex' in entry:
                        fail(f'{ref}#{sid}', 'export introduced unexpected opaque string')
            except (ValueError, KeyError, TypeError, struct.error, IndexError) as exc:
                fail(ref, f'cannot compare candidate/export: {exc}')
    return {'status': 'failed' if errors else ('incomplete' if gaps else 'passed'), 'errors': errors, 'gaps': gaps, 'counts': counts}
