"""Independently validate native loading evidence against the shipped ROM."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import opaque_control_proof as opaque


def units_digest(units):
    return hashlib.sha256(struct.pack('<' + 'H' * len(units), *units)).hexdigest()


def expected_records(path):
    import ndspy.rom
    import msgtool as m
    rom = ndspy.rom.NintendoDSRom.fromFile(str(path))
    result = {}
    for archive, path in (('a027', 'a/0/2/7'), ('battle_string', 'battle/string/battle_string.narc')):
        narc = m.Narc.parse(m.get_file(rom, path))
        for bank, data in enumerate(narc.files):
            _, records, _ = m.decrypt_bank(data)
            for index, raw in enumerate(records):
                if raw and raw[0] == m.CODE_COMPRESSED:
                    units, _ = m.decompress_units(raw)
                else:
                    end = 0
                    while end < len(raw) and raw[end] != m.CODE_END:
                        end += 3 + raw[end+2] if raw[end] == m.CODE_CMD else 1
                    if end >= len(raw):
                        raise ValueError('Unterminated entry')
                    units = raw[:end]
                semantic_length = len(units)
                stored = raw[:raw.index(m.CODE_END)]
                if raw[0] != m.CODE_COMPRESSED:
                    units = stored
                result[f'{archive}/{bank:04d}#{index}'] = (len(units), units_digest(units), len(stored), units_digest(stored), raw[0] == m.CODE_COMPRESSED, semantic_length, units_digest(raw))
    return result


def validate(report, expected, proven_controls=()):
    checks = {}
    records = report.get('records', [])
    refs = [r.get('ref') for r in records]
    checks['exact_inventory'] = bool(expected) and len(refs) == len(set(refs)) and set(refs) == set(expected)
    checks['declared_inventory'] = report.get('expected_count') == len(expected) and set(report.get('expected_refs', [])) == set(expected)
    checks['native_outputs'] = bool(records) and all(
        row.get('ref') in expected and
        (row.get('actual_units'), row.get('actual_sha256')) == expected[row['ref']][:2] and
        (row.get('expected_units'), row.get('expected_sha256')) == expected[row['ref']][:2] and
        (row.get('stored_actual_units'), row.get('stored_actual_sha256')) == expected[row['ref']][2:4] and
        (row.get('stored_expected_units'), row.get('stored_expected_sha256')) == expected[row['ref']][2:4] and
        row.get('decompression_called') is expected[row['ref']][4] and
        row.get('semantic_units') == expected[row['ref']][5] and
        bool(row.get('semantic_gap')) == (expected[row['ref']][5] != expected[row['ref']][0]) and
        row.get('terminator') == 65535 and row.get('native_call_completed') is True and
        row.get('capacity', -1) >= row.get('actual_units', 0)
        for row in records)
    banks = {ref.split('#')[0] for ref in expected}
    cycles = report.get('lifecycles', [])
    cycle_refs = [f"{'a027' if c.get('narc') == 27 else 'battle_string' if c.get('narc') == 277 else 'unknown'}/{c.get('bank', -1):04d}" for c in cycles]
    checks['bank_cleanup_coverage'] = len(cycle_refs) == len(set(cycle_refs)) and set(cycle_refs) == banks
    checks['bank_cleanup_balanced'] = bool(cycles) and all(c.get('before') and c.get('before') == c.get('after') for c in cycles)
    stress = report.get('stress', [])
    checks['archive_paths'] = report.get('archive_paths_observed') == {'27': 'a/0/2/7', '277': 'battle/string/battle_string.narc'}
    checks['cross_archive_stress'] = bool(stress) and all({27, 277}.issubset({pair[0] for pair in cycle.get('bank_refs', [])}) for cycle in stress)
    checks['stress_balanced'] = bool(stress) and all(c.get('handles', 0) >= 2 and c.get('reads', 0) > 0 and c.get('before') and c.get('before') == c.get('after') for c in stress)
    for key in ('errors', 'allocation_failures', 'null_writes', 'heap_table_errors'):
        checks['clean_' + key] = key in report and not report[key]
    checks['heap_observations'] = report.get('heap_checks', 0) >= 2 * (len(banks) + len(stress))
    for key in ('code_guards_passed', 'source_unchanged', 'script_unchanged', 'save_unchanged', 'reference_unchanged'):
        checks[key] = report.get(key) is True
    resolved=report.get('resolved_controls', [])
    resolved_refs=[row.get('ref') for row in resolved]
    checks['resolved_controls_proven']=(len(resolved_refs)==len(set(resolved_refs)) and set(resolved_refs)==set(proven_controls) and all(row.get('raw_payload_sha256')==opaque.PAYLOAD_HASH and row.get('source_matches') is True and row.get('native_units')==4 and row.get('semantic_units')==5 for row in resolved))
    if resolved:
        checks['opaque_native_formatter']=opaque.native_evidence_ok(report.get('opaque_formatter_cases', []), report.get('opaque_cleanup', {}))
    gaps = [ref for ref, data in expected.items() if data[0] != data[5] and ref not in proven_controls]
    declared_gaps = report.get('semantic_gaps', [])
    checks['semantic_gap_inventory'] = len(declared_gaps) == len(gaps) and {r.get('ref') for r in declared_gaps} == set(gaps)
    return {'status': ('passed_with_semantic_gaps' if gaps else 'pass') if all(checks.values()) else 'fail', 'checks': checks, 'entry_count': len(expected), 'semantic_gaps': gaps}


def validate_file(path):
    report = json.loads(Path(path).read_text())
    import ndspy.rom
    candidate=expected_records(report['source']['path'])
    baseline=expected_records(report['reference']['path'])
    arm=ndspy.rom.NintendoDSRom.fromFile(report['source']['path']).loadArm9().sections[0]
    proof=opaque.inspect_code(bytes(arm.data),arm.ramAddress)
    proven=[ref for ref in candidate if ref in baseline and opaque.eligible(ref,candidate[ref][6],baseline[ref][6],proof)]
    result = validate(report, candidate, proven)
    result['checks']['opaque_code_proof']=not proven or report.get('opaque_code_proof')==proof
    for key in ('source', 'script', 'save', 'reference'):
        item = report.get(key, {})
        source = Path(item.get('path', ''))
        result['checks'][key + '_identity'] = source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == item.get('sha256')
    if result['semantic_gaps']:
        baseline = expected_records(report['reference']['path'])
        candidate = expected_records(report['source']['path'])
        result['checks']['semantic_gaps_preserved_from_chinese'] = all(ref in baseline and baseline[ref][6] == candidate[ref][6] for ref in result['semantic_gaps'])
    result['status'] = ('passed_with_semantic_gaps' if result['semantic_gaps'] else 'pass') if all(result['checks'].values()) else 'fail'
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    result = validate_file(args.report)
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] not in ('pass', 'passed_with_semantic_gaps'))
