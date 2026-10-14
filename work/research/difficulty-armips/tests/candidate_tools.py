"""Fresh isolated build of shipping source, without installer promotion."""
import functools
import importlib
import json
import sys
from pathlib import Path
from support import ROOT, SOURCE, OUTPUT
sys.path.insert(0, str(SOURCE))
build = importlib.import_module('build')
install = importlib.import_module('install')
INPUT = ROOT / json.loads((SOURCE/'compatibility.json').read_text())['roms']['en']['path']
RECEIPT = build.RECEIPT

@functools.lru_cache(maxsize=1)
def assembled():
    import tempfile
    import ndspy.rom
    stage = Path(tempfile.mkdtemp(prefix='compiled-', dir=OUTPUT))
    rom = ndspy.rom.NintendoDSRom.fromFile(INPUT)
    arm, overlays, raw = install.sections(rom)
    comp, hooks, edits = install.contracts()
    install.bounds(arm, overlays)
    install.validate_sections(raw, comp, hooks, edits)
    for name, data in raw.items(): (stage / name).write_bytes(data)
    payload, report = build.build(stage)
    staged = {name: (stage / name).read_bytes() for name in raw}
    install.verify_stage(raw, staged, hooks, edits, report, comp)
    (stage / 'fresh-build.json').write_text(json.dumps(report, indent=2)+'\n')
    return stage, rom, arm, overlays, raw, staged, payload, report
