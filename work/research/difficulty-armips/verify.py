#!/usr/bin/env python3
"""Independently recompile and verify a difficulty-installed English ROM.

Run from this repository root. Does not promote ROMs or edit installer pins.
"""
import argparse
import json
from pathlib import Path
import tempfile

import ndspy.rom

import build
import install


def verify(receipt_path, output):
    receipt = json.loads(receipt_path.read_text())
    install.require(receipt.get('tool_mode', 'release') == build.tool_mode(),
                    f'receipt tool mode differs from {build.DEV_ENV}: verify a development build in development mode')
    for item in [receipt['input'], receipt['output'], *receipt['sources'].values(),
                 *receipt['tools'].values(), *receipt['build_artifacts'].values()]:
        install.require(install.sha(Path(item['path']).read_bytes()) == item['sha256'],
                        'stale verification input: ' + item['path'])
    install.source_tools()
    original = ndspy.rom.NintendoDSRom.fromFile(receipt['input']['path'])
    candidate = ndspy.rom.NintendoDSRom.fromFile(receipt['output']['path'])
    arm, overlays, raw = install.sections(original)
    layout = install.bounds(arm, overlays)
    comp, hooks, edits = install.contracts()
    guards = install.validate_sections(raw, comp, hooks, edits)
    stage = Path(tempfile.mkdtemp(prefix='verify-', dir=output))
    for filename, data in raw.items():
        (stage / filename).write_bytes(data)
    payload, report = build.build(stage)
    staged = {filename: (stage / filename).read_bytes() for filename in raw}
    diff = install.verify_stage(raw, staged, hooks, edits, report, comp)
    logical = install.verify_rom(original, candidate, raw, staged, payload, report)
    negative = install.negative_checks(raw, comp, hooks, edits, arm, overlays, candidate)
    status = build.DEV_LABEL + '; passed' if build.dev_tools() else 'passed'
    result = dict(status=status, tool_mode=build.tool_mode(), receipt=install.pin(receipt_path), input=receipt['input'],
                  output=receipt['output'], fresh_compilation=str(stage), layout=layout,
                  guards=guards, stage_exact_diff=diff, logical_preservation=logical,
                  negative_checks=negative, native_acceptance=False)
    (output / 'verification.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    install.require(Path.cwd().resolve() == build.ROOT, 'run from repository root')
    output = args.out.resolve()
    install.require(output.is_relative_to(build.ROOT / 'work/build'), 'output must remain in work/build')
    output.mkdir(parents=True, exist_ok=True)
    result = verify(args.receipt.resolve(), output)
    print(json.dumps(dict(status=result['status'], output=result['output'],
                         negative_rejections=result['negative_checks']['rejections']), indent=2))


if __name__ == '__main__':
    main()
