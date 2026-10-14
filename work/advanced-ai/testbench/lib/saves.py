"""The test bench's battery saves (.dsv): made locally, checked by SHA-256, never committed.

  S=work/advanced-ai/testbench/lib/saves.py
  .venv/bin/python $S make --base /path/to/your/save.sav [--rom ROM]    # derive them all from a save of your own game
  ADVAI_ES_REPO=/path/to/spanish/repo .venv/bin/python $S make [NAME ...]   # or take the reference ones (or --es-repo)
  .venv/bin/python $S check                                             # which ones are in place, and where from

The saves (work/build/advanced-ai/saves/<name>.dsv): violet_gym (the field at the Violet City Gym door, a level-100
lead: the pre-battle state of aibench, aivsai, aiprops and most checks is made from it), party_nostatus (storycheck's
starting point), party, items, whiteout and blank (512 KiB of 0xFF). They are game data: *.dsv and *.sav are ignored
and never committed.

Two sources:
- The reference saves: the Spanish workspace's tests/*.dsv at commit dc8577c, taken with `git show` (read only) and
  checked against SAVES. Every recorded reference (testbench/references/) was made with them.
- Derived saves (`make --base`): the Spanish savetool's make() (its tools/savetool.py, dc8577c) run on ONE save of
  your own game of this hack: a raw 512 KiB .sav (melonDS, a flashcart) or a DeSmuME .dsv. The base is first
  normalised into party_nostatus (normalise()); party, items, violet_gym and whiteout follow from it as the Spanish
  make() made them; blank needs no input. Derived from the Spanish party_nostatus, they are the reference saves byte
  for byte (test_saves.py proves it when that save is in place).

What normalise() fixes, whatever the base (each value the reference save's):
- the player: name 'AAAAAA', trainer ID 0x09A68217 (its SID in the high half), gender male, money 3000, options 0x0200;
- the party: six Pokémon (Eggs dropped; with fewer than six, the base's own Pokémon are repeated in order), each with
  no status, full HP, and the player as its original trainer (ID, name, gender: so no injected Pokémon is a traded,
  disobedient one);
- the beaten flag of trainer 71 (flag 0x550 + 71), the Violet Gym trainer the bench walks to, cleared.
What the derivation sets (the Spanish make()): party's statuses; items' Master Ball, Friend Ball, Rare Candy and Nugget
and options; violet_gym's flags 739 and 740 (the event NPCs at the gym door hidden), its lead at level 100 (the
experience of level 100 for its species' growth rate, read from --rom) with 999 in every stat, and its place: map 73
at (479, 258) facing up with every other saved map object off and the camera byte 4, the reference save's (the
gym door's warp then sets the camera from map 73's header); whiteout's lead at level 5 and 1 HP, the rest fainted.
What still comes from the base: every other story flag and variable, badges, the bag (besides the four items), the
Pokédex, the boxes, the party's species, levels, moves, items, IVs and EVs, and the map position of party_nostatus,
party and items. A base far from the reference's story point (the Violet City Gym not yet open, its trainer gone)
may make the field scripts behave otherwise; the tools then say so (e.g. aibench: the save state never reaches the
trainer battle).

Identity: `make` writes SAVES_DIR/manifest.json, each save's SHA-256 and its source ('spanish dc8577c', or 'base <the
input's SHA-256>'). path() hands a tool a save only when its SHA-256 is its manifest entry's or the reference one;
reference() says whether the saves the tiers use are the reference bytes: run.py prints the source, and the deep
tier's byte-identical comparison of AI-vs-AI logs applies only then.
"""
import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys

import tbpaths
from savetool import FLAGS, IMAGE_SIZE, MONEY, NAME, OPTIONS, PARTY, Mon, Save, dsv, gen4_slow_exp, image

ES_REPO = os.environ.get('ADVAI_ES_REPO')     # the Spanish workspace repository (or --es-repo)
ES_COMMIT = 'dc8577c'
SPANISH = 'spanish %s' % ES_COMMIT
MANIFEST = os.path.join(tbpaths.SAVES, 'manifest.json')
DEFAULT_ROM = os.path.join(tbpaths.BUILD, 'base', 'rc8_release.nds')
# name -> SHA-256 of work_es/tests/<name>.dsv at dc8577c: the reference saves
SAVES = {
    'violet_gym': '42434c064575c14dafe587cb2a9f30fa21dd2a786d6b7cc91d53ec8b6d65e02b',
    'party_nostatus': '2e6dc14b5075bfba550d5e8becb3bbad8d3ed81ff2d24d611cb6a7d932c31b64',
    'party': 'fc3444105a40edac3a90c5671421ee33fca36325f1944991bc68692ab0f4a811',
    'items': '3e11d85e6e65d67ac3a84528890ac53a6a5df73d3b00722b165c25ef254fa596',
    'whiteout': 'acb0743f2449abc8a466c4950ed132797d2e882348804ce120cad671b0b697a4',
    'blank': 'bb7684028d47e3eb2a36e5b345d60d4a0eed29f0307731fa36d3c83bb2968be3',
}
TIER_SAVES = ('violet_gym', 'party_nostatus')    # the ones the tiers' tools boot

# --- normalise(): the reference save's values
PLAYER_NAME = bytes.fromhex('2b012b012b012b012b012b01ffff0000')    # 'AAAAAA', 0xFFFF, 0: 8 u16
PLAYER_ID, PLAYER_GENDER, PLAYER_MONEY, PLAYER_OPTIONS = 0x09A68217, 0, 3000, 0x0200
PROFILE_ID, PROFILE_GENDER = NAME + 0x10, NAME + 0x18    # the profile after the name: u32 ID, u32 money, u8 gender
PARTY_COUNT, PARTY_SIZE, MON_SIZE = PARTY - 4, 6, 236
STATUS, HP, MAX_HP = 0, 6, 8              # party data offsets: u32 status, u16 HP, u16 max HP
EGG_BIT = 30                              # block B +0x10, u32: IVs and the Egg / nickname bits
OT_GENDER = 0x80                          # block D +0x1C: met level (bits 0-6), the trainer's gender (bit 7)
TRAINER_BEATEN = 0x550                    # trainer t's beaten flag is 0x550 + t (the Spanish flagcheck.py)
BENCH_TRAINER = 71                        # the Violet Gym trainer aibench walks to
# --- the derivation (the Spanish make(), dc8577c)
STATUSES = (0x10, 0x40, 0x20, 0x00, 0x03, 0x00)   # party: burned, paralyzed, frozen, -, asleep, healthy
ITEMS = (('balls', 1, 1), ('balls', 497, 1), ('medicine', 50, 1), ('items', 92, 1))   # Master Ball, Friend Ball, Rare Candy, Nugget
GYM_NPC_FLAGS = (739, 740)                # the event NPCs blocking the Violet Gym door hidden
GYM_DOOR = (73, 479, 258, 'up')
REFERENCE_CAMERA = 4                      # the reference violet_gym's camera byte (made before its place() set map 73's, 0)


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def is_egg(mon):
    return struct.unpack_from('<I', mon.blocks['B'], 0x10)[0] >> EGG_BIT & 1


def normalise(sv):
    """The base save as party_nostatus (the module docstring lists what changes). Idempotent."""
    sv.put('<16s', NAME, PLAYER_NAME)
    sv.put('<I', PROFILE_ID, PLAYER_ID)
    sv.put('<I', MONEY, PLAYER_MONEY)
    sv.put('<B', PROFILE_GENDER, PLAYER_GENDER)
    sv.put('<H', OPTIONS, PLAYER_OPTIONS)
    count = min(sv.u('<I', PARTY_COUNT)[0], PARTY_SIZE)
    at = sv.base + PARTY
    kept = [bytes(sv.data[at + MON_SIZE * k:at + MON_SIZE * (k + 1)]) for k in range(count)]
    kept = [raw for raw in kept if not is_egg(Mon(raw))]
    if not kept:
        raise ValueError('the base save has no Pokémon in its party that is not an Egg')
    sv.put('<I', PARTY_COUNT, PARTY_SIZE)
    for k in range(PARTY_SIZE):
        m = Mon(kept[k % len(kept)])
        struct.pack_into('<I', m.blocks['A'], 4, PLAYER_ID)
        m.blocks['D'][0:16] = PLAYER_NAME
        m.blocks['D'][0x1C] = m.blocks['D'][0x1C] & ~OT_GENDER | (OT_GENDER if PLAYER_GENDER else 0)
        struct.pack_into('<I', m.party, STATUS, 0)
        struct.pack_into('<H', m.party, HP, struct.unpack_from('<H', m.party, MAX_HP)[0])
        sv.set_mon(k, m)
    flag = TRAINER_BEATEN + BENCH_TRAINER
    sv.put('<B', FLAGS + flag // 8, sv.u('<B', FLAGS + flag // 8)[0] & ~(1 << flag % 8))
    return sv


def derive(base, exp100):
    """{name: .dsv bytes} of every save in SAVES, from a base save's bytes (raw or .dsv). exp100(species): the
    experience of level 100 for that species' growth rate (aidata.Data.exp_for)."""
    out = {'party_nostatus': normalise(Save(data=image(base))).to_bytes()}

    s = Save(data=out['party_nostatus'])     # the regular test save: every status label on screen
    for k, st in enumerate(STATUSES):
        m = s.mon(k)
        m.set_status(st)
        s.set_mon(k, m)
    out['party'] = s.to_bytes()

    s = Save(data=out['party_nostatus'])     # items for the capture, tutor and shop scenarios
    for pocket, item, qty in ITEMS:
        s.add_item(pocket, item, qty)
    s.set_options(battle_scene_off=False, battle_style_set=True)   # animations on (they load files); no switch prompt
    out['items'] = s.to_bytes()

    s = Save(data=out['items'])              # the Violet City Gym door; the event NPCs blocking the gym hidden
    for flag in GYM_NPC_FLAGS:
        s.set_flag(flag)
    m = s.mon(0)
    m.set_level(100, exp100(struct.unpack_from('<H', m.blocks['A'], 0)[0]))   # no level-up, so the stats below stay
    m.set_stats(999, 999, 999, 999, 999, 999)   # moves first and knocks out each trainer Pokémon in one hit
    s.set_mon(0, m)
    s.place(*GYM_DOOR, camera=REFERENCE_CAMERA)
    out['violet_gym'] = s.to_bytes()

    s = Save(data=out['violet_gym'])         # loses the Violet Gym battle: lead at level 5 and 1 HP, the rest fainted
    for k in range(PARTY_SIZE):
        m = s.mon(k)
        if k == 0:
            m.set_level(5, gen4_slow_exp(5))
            m.set_stats(1, 5, 5, 5, 5, 5)
        else:
            m.set_hp(0)
        s.set_mon(k, m)
    out['whiteout'] = s.to_bytes()

    out['blank'] = b'\xff' * IMAGE_SIZE
    return {name: dsv(data) for name, data in out.items()}


# --- the files and their manifest
def manifest():
    try:
        with open(MANIFEST, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_files(saves, source):
    """Write {name: bytes} into SAVES_DIR (each atomically) and record them in the manifest."""
    os.makedirs(tbpaths.SAVES, exist_ok=True)
    entries = manifest()
    for name, data in sorted(saves.items()):
        out = os.path.join(tbpaths.SAVES, name + '.dsv')
        with open(out + '.tmp', 'wb') as f:
            f.write(data)
        os.replace(out + '.tmp', out)
        digest = hashlib.sha256(data).hexdigest()
        entries[name] = {'sha256': digest, 'source': source}
        print('%s  %s  %s' % (digest, tbpaths.rel(out), 'the reference' if digest == SAVES[name] else source))
    with open(MANIFEST + '.tmp', 'w', encoding='utf-8') as f:
        json.dump(entries, f, indent=1, sort_keys=True)
        f.write('\n')
    os.replace(MANIFEST + '.tmp', MANIFEST)


def path(name):
    """The checked save `name`: its SHA-256 is its manifest entry's or the reference one. Else exit with how to make it."""
    if name not in SAVES:
        raise KeyError('no test save %r (known: %s)' % (name, ', '.join(sorted(SAVES))))
    p = os.path.join(tbpaths.SAVES, name + '.dsv')
    how = '%s make --base /path/to/your/save.sav (or make, from the Spanish repository)' % tbpaths.rel(__file__)
    if not os.path.exists(p):
        sys.exit('the test save %s is missing: run %s' % (tbpaths.rel(p), how))
    got = sha256(p)
    if got != SAVES[name] and got != manifest().get(name, {}).get('sha256'):
        sys.exit('%s has SHA-256 %s, neither the reference one nor its manifest entry: run %s' % (tbpaths.rel(p), got, how))
    return p


def source(name):
    """Where save `name` came from: 'reference' (the reference bytes, however made), the manifest's source, or None."""
    p = os.path.join(tbpaths.SAVES, name + '.dsv')
    if not os.path.exists(p):
        return None
    got = sha256(p)
    if got == SAVES[name]:
        return 'reference'
    entry = manifest().get(name, {})
    return entry.get('source') if entry.get('sha256') == got else None


def reference(names=TIER_SAVES):
    """True when every one of `names` is the reference bytes."""
    return all(source(n) == 'reference' for n in names)


def describe(names=TIER_SAVES):
    """One line for a tier's summary: the saves' source."""
    if reference(names):
        return 'saves: the reference ones (Spanish %s)' % ES_COMMIT
    return 'saves: %s (not the reference ones)' % ', '.join(
        '%s from %s' % (n, source(n) or 'nowhere (missing or changed)') for n in names)


def make_spanish(names, repo):
    out = {}
    for name in names:
        data = subprocess.run(['git', '-C', repo, 'show', '%s:work_es/tests/%s.dsv' % (ES_COMMIT, name)], check=True,
                              capture_output=True).stdout
        got = hashlib.sha256(data).hexdigest()
        if got != SAVES[name]:
            sys.exit('%s.dsv at %s has SHA-256 %s, not %s' % (name, ES_COMMIT, got, SAVES[name]))
        out[name] = data
    write_files(out, SPANISH)


def make_base(base, rom):
    from aidata import Data
    d = Data(rom)
    with open(base, 'rb') as f:
        data = f.read()
    write_files(derive(data, lambda species: d.exp_for(species, 100)), 'base ' + hashlib.sha256(data).hexdigest())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('action', choices=('make', 'check'))
    ap.add_argument('names', nargs='*')
    ap.add_argument('--base', help='make: derive every save from this save of your own game (a raw .sav or a .dsv)')
    ap.add_argument('--rom', default=DEFAULT_ROM, help='--base: a ROM of this hack, for the growth rates (default: '
                    'work/build/advanced-ai/base/rc8_release.nds)')
    ap.add_argument('--es-repo', default=ES_REPO, help='the Spanish workspace repository (default: ADVAI_ES_REPO)')
    a = ap.parse_args()
    names = a.names or sorted(SAVES)
    unknown = [n for n in names if n not in SAVES]
    if unknown:
        ap.error('unknown save(s): %s' % ', '.join(unknown))
    if a.action == 'make' and a.base:
        if a.names:
            ap.error('--base makes every save; give no names')
        if not os.path.exists(a.rom):
            ap.error('--rom %s not found: give a ROM of this hack (e.g. the rc8 release)' % a.rom)
        try:
            return make_base(a.base, a.rom)
        except ValueError as e:
            sys.exit('%s: %s' % (a.base, e))
    if a.action == 'make':
        if not a.es_repo:
            ap.error('give --base SAVE (your own game\'s save), or --es-repo DIR / ADVAI_ES_REPO for the reference saves')
        return make_spanish(names, a.es_repo)
    bad = 0
    for name in names:
        p = os.path.join(tbpaths.SAVES, name + '.dsv')
        src = source(name)
        state = 'missing' if not os.path.exists(p) else 'ok (%s)' % src if src else 'WRONG SHA-256 (remake it)'
        bad += not src
        print('%-15s %s' % (name, state))
    print(describe())
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
