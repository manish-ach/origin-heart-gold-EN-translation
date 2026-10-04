"""Independent fail-closed validation of local native SIZE renderer evidence."""
import argparse
import hashlib
import json
import re
from pathlib import Path

SENTINEL = 'Normal text after shout.{NEWLINE}Second normal line.'


def validate_case(case):
    checks = {}
    def check(name, value):
        checks[name] = bool(value)
    negative = case.get('ref') == 'negative-misty-newline'
    check('heap_sampled', case.get('heap_checks', 0) > 0 and case.get('minspare'))
    if negative:
        check('corruption_reproduced', case.get('corrupt'))
        return {'status': 'expected-failure' if all(checks.values()) else 'fail', 'assertions': checks}
    for key in ('corrupt', 'allocation_failures', 'null_writes', 'heap_table_errors'):
        check('clean_' + key, key in case and not case[key])
    text = case.get('text', '')
    ui = case.get('ui_case', False)
    rendered = text + ('' if text.endswith(('{SCROLL}', '{CLEAR}')) else '{SCROLL}')
    if not ui:
        rendered += SENTINEL + '{SCROLL}'
    expected_pages = re.split(r'\{(?:SCROLL|CLEAR)\}', rendered.removesuffix('{SCROLL}'))
    shots = case.get('screenshots', [])
    check('page_coverage', len(shots) == len(expected_pages) and
          [s.get('expected') for s in shots] == expected_pages and
          all(s.get('glyphs') for s in shots))
    check('capture_hashes', shots and all(re.fullmatch('[a-f0-9]{64}', s.get('text_crop_sha256', '')) for s in shots))
    expected_sizes = [65532 if n == '200' else 0 for n in re.findall(r'\{VAR:FF01:(\d+)\}', text)]
    check('size_transitions', 'size_events' in case and [e.get('size_word') for e in case['size_events']] == expected_sizes)
    glyphs = case.get('glyphs', [])
    big = [g for g in glyphs if g.get('size_word') == 65532]
    check('glyph_evidence', glyphs and (big or 65532 not in expected_sizes))
    check('enlarged_y', all(g.get('y') == 0 for g in big))
    starts = case.get('printer_starts', [])
    check('fresh_printer_reset', starts and all(s.get('size_word') == 0 for s in starts))
    if ui:
        end = shots[-1].get('frame_end', float('inf')) if shots else float('inf')
        fresh = [s for s in starts if s.get('frame', -1) > end]
        check('following_constructor', fresh)
        first = min((s['frame'] for s in fresh), default=float('inf'))
        following = [g for g in glyphs if g.get('frame', -1) >= first]
        check('following_normal', following and all(g.get('size_word') == 0 for g in following))
        check('native_font', big and all(g.get('font') == case.get('harness_font') for g in big))
        width = case.get('native_width', 0)
        check('native_width', width in (144, 216) and 0 < case.get('rendered_advance_extent', 0) <= width and 0 < case.get('static_font_width', 0) <= width)
    else:
        last = shots[-1].get('glyphs', []) if shots else []
        check('sentinel_normal', last and all(g.get('size_word') == 0 for g in last))
    return {'status': 'pass' if all(checks.values()) else 'fail', 'assertions': checks}


def validate_report(report):
    cases = report.get('cases', [])
    results = {c['ref']: validate_case(c) for c in cases}
    refs = [c['ref'] for c in cases]
    from PIL import Image
    images_valid = True
    for case in cases:
        for shot in case.get('screenshots', []):
            try:
                with Image.open(shot['path']) as image:
                    digest = hashlib.sha256(image.crop((12, 153, 236, 183)).convert('RGB').tobytes()).hexdigest()
                images_valid = images_valid and digest == shot.get('text_crop_sha256')
            except (OSError, KeyError):
                images_valid = False
    checks = {'coverage': bool(refs) and refs == report.get('expected_refs') and len(set(refs)) == len(refs)}
    checks['screenshot_artifacts'] = images_valid
    for key in ('source_unchanged', 'script_unchanged', 'inventory_unchanged', 'code_guards_passed', 'inventory_matches_candidate'):
        checks[key] = report.get(key) is True
    for key in ('source', 'save', 'script', 'inventory'):
        identity = report.get(key, {})
        path = Path(identity.get('path', ''))
        checks[key + '_hash'] = path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == identity.get('sha256')
        if key == 'script' and not checks[key + '_hash']:
            archive = report.get('script_archive', {})
            archived_path = Path(archive.get('path', ''))
            checks[key + '_hash'] = (archived_path.is_file() and archive.get('sha256') == identity.get('sha256')
                                     and hashlib.sha256(archived_path.read_bytes()).hexdigest() == identity.get('sha256'))
    control = next((c for c in cases if c['ref'] == 'control-normal'), {})
    baseline = control.get('screenshots', [{}])[-1].get('text_crop_sha256')
    checks['normal_control'] = bool(baseline) and results.get('control-normal', {}).get('status') == 'pass'
    checks['negative_control'] = results.get('negative-misty-newline', {}).get('status') == 'expected-failure'
    for case in cases:
        if not case.get('ui_case') and case['ref'] != 'negative-misty-newline':
            result = results[case['ref']]
            matches = bool(baseline) and case.get('screenshots', [{}])[-1].get('text_crop_sha256') == baseline
            result['assertions']['sentinel_matches_control'] = matches
            if not matches: result['status'] = 'fail'
    return {'status': 'pass' if all(checks.values()) and all(r['status'] in ('pass', 'expected-failure') for r in results.values()) else 'fail', 'assertions': checks, 'cases': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report', type=Path)
    args = parser.parse_args()
    result = validate_report(json.loads(args.report.read_text()))
    print(json.dumps(result, indent=2))
    raise SystemExit(result['status'] != 'pass')
