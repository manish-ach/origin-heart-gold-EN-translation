"""Shared test utilities; never writes source ROMs, saves, or historical fixtures."""
from pathlib import Path
import hashlib
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
SOURCE = ROOT / 'work/research/difficulty-armips'
OUTPUT = ROOT / 'work/build/difficulty-v2/tests'
CN = ROOT / 'work/rom/origin_v4.0.3_cn.nds'
CN_SHA256 = '4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8'
HISTORY = ROOT / 'work/build/exp-share-research'
# The candidate receipt of the current tool mode: integration-impl, or
# integration-impl-dev with DIFFICULTY_DEV_TOOLS=1 (build.py OUTPUT).
sys.path.insert(0, str(SOURCE))
from build import RECEIPT  # noqa: E402,F401  (re-exported)
# Options page 2: ITEMS, SHARE, CAP, TRAINER AI, then CANCEL and APPLY.
OPTIONS_ROWS = 4
FOCUS_COUNT = OPTIONS_ROWS + 2


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def scratch(prefix):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    return tempfile.TemporaryDirectory(prefix=prefix, dir=OUTPUT)


def command(argv, cwd=ROOT, success=True):
    result = subprocess.run([str(v) for v in argv], cwd=cwd, text=True,
                            capture_output=True, timeout=90)
    if (result.returncode == 0) != success:
        raise AssertionError(f'{argv}: exit {result.returncode}\n{result.stdout}{result.stderr}')
    return result


def source_hashes():
    return {str(p.relative_to(ROOT)): sha256(p) for p in sorted(SOURCE.rglob('*'))
            if p.is_file() and p.suffix in ('.py','.c','.h','.asm','.ld','.json','.toml','.md') and '__pycache__' not in p.parts}


def load_rom():
    from ndspy.rom import NintendoDSRom
    if sha256(CN) != CN_SHA256:
        raise AssertionError('Untouched Chinese source identity differs')
    return NintendoDSRom.fromFile(str(CN))


def arm9_main(rom):
    from ndspy.code import MainCodeFile
    sections = MainCodeFile(rom.arm9, rom.arm9RamAddress).sections
    return bytes(next(s.data for s in sections if s.ramAddress == 0x02000000))


def historical_inventory():
    """Hash old inputs without treating their claims as current test outcomes."""
    names = ['probe.py', 'rom-identities.json', 'two-ready.dst', 'test-battle.dst',
             'baseline-stats.log', 'cheat-stats.log', 'en-baseline.log', 'en-cheat.log']
    return {'classification': 'historical-only; not a native candidate replay',
            'artifacts': {name: {'sha256': sha256(HISTORY / name),
                                  'bytes': (HISTORY / name).stat().st_size}
                          for name in names if (HISTORY / name).is_file()}}
