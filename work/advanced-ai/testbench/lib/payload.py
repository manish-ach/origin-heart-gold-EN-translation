"""Every address of an AI build the test bench reads, from the build's payload.json (docs/build-contract.md).

  .venv/bin/python work/advanced-ai/testbench/lib/payload.py show [--payload P] [--rom ROM]   # the addresses the tools use

The test bench never hard-codes an AI-build address (the Spanish tools took them from their build.py: ITCM_SYMS,
AI_SYMS and fixed constants). A tool gets its payload from --payload, or from the ADVAI_PAYLOAD environment variable,
which every tool sets from its --payload so its worker processes inherit it.

What the tools read (Layout):
  adv_code     the AI's code in the slot overlay: regions.slot ram .. limit (the Spanish aivsai ADV_CODE)
  orig_code    overlay 11's copy at the start of overlay 10: overlay10.ram .. slot ram - 0x20 (overlay 11's 0x20-byte
               bss sits between; the contract places slot.bin right after it) (ORIG_CODE)
  slot_range   all of overlay 10: overlay10.ram .. regions.slot limit (aibench SLOT_RANGE)
  debug        symbol ai_debug (advai.c's debug record, first in overlay 10's bss); when the payload has none, the
               end of overlay 10's image in the ROM, as the Spanish aibench found it
  tune         symbol g_tune (tune.h's table), or None
  words        the test-only words of engine.h (NOLEAD_FLAG/MAGIC, NOREAD_FLAG/MAGIC, SELFPLAY_FLAG/MAGIC, READS_AT,
               REPLACED_AT, FS_WORD_AT/MAGIC): the payload's 'test_words' when it has them, else the #defines of the
               engine.h whose sha256 the payload records under 'sources' (work/advanced-ai/src/engine.h, or the
               committed version of it with that sha256; refused when neither has it, so the words always belong to
               the build under test)
"""
import argparse
import hashlib
import json
import os
import re
import sys

import tbpaths

AI_OVERLAY = 10                 # the slot overlay the advanced AI is built into (build.AI_OVERLAY)
OV11_BSS = 0x20                 # overlay 11's bss, zeros between its image and slot.bin in overlay 10
WORD_NAMES = ('SELFPLAY_FLAG', 'SELFPLAY_MAGIC', 'NOLEAD_FLAG', 'NOLEAD_MAGIC', 'NOREAD_FLAG', 'NOREAD_MAGIC',
              'REPLACED_AT', 'READS_AT', 'FS_WORD_AT', 'FS_WORD_MAGIC')
ENGINE_H = os.path.join(tbpaths.ADV, 'src', 'engine.h')
ENV = 'ADVAI_PAYLOAD'


def num(v):
    return v if isinstance(v, int) else int(v, 0)


def engine_h_from_git(sha256):
    """The bytes of the committed version of src/engine.h whose sha256 is `sha256`, or None."""
    import subprocess
    rel = os.path.relpath(ENGINE_H, tbpaths.REPO)
    log = subprocess.run(['git', '-C', tbpaths.REPO, 'log', '--format=%H', '--', rel], capture_output=True, text=True)
    for commit in log.stdout.split():
        blob = subprocess.run(['git', '-C', tbpaths.REPO, 'show', '%s:%s' % (commit, rel)], capture_output=True).stdout
        if hashlib.sha256(blob).hexdigest() == sha256:
            return blob
    return None


def engine_words(text):
    """The test words' #defines of an engine.h's text: {name: int}."""
    out = {}
    for name in WORD_NAMES:
        m = re.search(r'^#define %s (0x[0-9A-Fa-f]+)u?\b' % name, text, re.M)
        if m:
            out[name] = int(m.group(1), 16)
    missing = [n for n in WORD_NAMES if n not in out]
    if missing:
        raise SystemExit('engine.h defines no %s' % ', '.join(missing))
    return out


class Layout:
    """The addresses of one AI build (see the module docstring)."""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        with open(path, encoding='utf-8') as f:
            self.raw = json.load(f)
        p = self.raw
        self.name = p.get('layout', '?')
        self.symbols = {k: num(v) for k, v in p.get('symbols', {}).items()}
        self.regions = {k: {f: num(v) if f in ('ram', 'limit', 'size', 'bss') else v for f, v in r.items()}
                        for k, r in p.get('regions', {}).items()}
        slot = self.regions['slot']
        ov10 = num(p['overlay10']['ram'])
        self.overlay10 = ov10
        self.adv_code = (slot['ram'], slot['limit'])
        self.orig_code = (ov10, slot['ram'] - OV11_BSS)
        self.slot_range = (ov10, slot['limit'])
        self.debug = self.symbols.get('ai_debug')
        tune = self.symbols.get('g_tune')
        self.tune = tune & ~1 if tune is not None else None
        self.words, self.words_from = self._words()

    def _words(self):
        given = self.raw.get('test_words') or {}
        if given:
            words = {k: num(v) for k, v in given.items()}
            missing = [n for n in WORD_NAMES if n not in words]
            if missing:
                raise SystemExit('%s: test_words lacks %s' % (tbpaths.rel(self.path), ', '.join(missing)))
            return words, 'payload'
        want = (self.raw.get('sources') or {}).get('src/engine.h')
        text = open(ENGINE_H, 'rb').read()
        if want and hashlib.sha256(text).hexdigest() != want:
            text = engine_h_from_git(want)
            if text is None:
                raise SystemExit('%s was built from an engine.h with sha256 %s, which is neither %s nor in its git '
                                 'history: the test words may have moved' % (tbpaths.rel(self.path), want, tbpaths.rel(ENGINE_H)))
            return engine_words(text.decode('utf-8')), 'engine.h %s (git history)' % want[:12]
        return engine_words(text.decode('utf-8')), tbpaths.rel(ENGINE_H)

    def word(self, name):
        return self.words[name]

    def sym(self, name):
        """A symbol's address (Thumb bit kept, as the linker gives it)."""
        if name not in self.symbols:
            raise KeyError('%s has no symbol %r' % (tbpaths.rel(self.path), name))
        return self.symbols[name]

    def debug_addr(self, rom=None):
        """ai_debug, or (no such symbol) the end of overlay 10's image in `rom`; None when overlay 10 is the stub."""
        if self.debug is not None:
            return self.debug
        if rom is None:
            return None
        import ndspy.rom
        o = ndspy.rom.NintendoDSRom.fromFile(rom).loadArm9Overlays().get(AI_OVERLAY)
        return o.ramAddress + o.ramSize if o and o.ramSize > 0x20 else None


def path_from(arg=None):
    """The payload path: --payload, else ADVAI_PAYLOAD. Exports it for the tool's worker processes."""
    p = arg or os.environ.get(ENV)
    if not p:
        raise SystemExit('no payload: give --payload PAYLOAD.json (or set %s); the Spanish rc44 one is made by '
                         '`builder/build.py --layout es`' % ENV)
    if not os.path.exists(p):
        raise SystemExit('payload %s not found' % p)
    os.environ[ENV] = os.path.abspath(p)
    return os.environ[ENV]


_cache = {}


def load(arg=None):
    """The Layout of --payload / ADVAI_PAYLOAD (cached per path)."""
    p = path_from(arg)
    if p not in _cache:
        _cache[p] = Layout(p)
    return _cache[p]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=('show',))
    ap.add_argument('--payload')
    ap.add_argument('--rom')
    a = ap.parse_args()
    lay = load(a.payload)
    print('payload %s (layout %s, %d symbols)' % (tbpaths.rel(lay.path), lay.name, len(lay.symbols)))
    hx = lambda r: '%08X-%08X' % r  # noqa: E731
    print('  adv_code %s  orig_code %s  slot_range %s' % (hx(lay.adv_code), hx(lay.orig_code), hx(lay.slot_range)))
    debug = lay.debug_addr(a.rom)
    print('  debug %s  tune %s' % ('%08X' % debug if debug else None, '%08X' % lay.tune if lay.tune else None))
    print('  test words (%s): %s' % (lay.words_from, ', '.join('%s %08X' % kv for kv in lay.words.items())))


if __name__ == '__main__':
    sys.exit(main())
