"""Move animations in doubles, on the Chinese ROM and the Spanish build: is an assert inherited? Does one leak?

  .venv/bin/python work/advanced-ai/testbench/dev/animcheck.py MOVE [MOVE ...] --rom ROM [--rom ROM ...] [--payload P]
                   [--battles N]
  .venv/bin/python work/advanced-ai/testbench/dev/animcheck.py MOVE [MOVE ...] --uses N [--single] --rom ROM ...

Ported from the Spanish workspace's qa/ai_research/animcheck.py (dc8577c) into the test bench: its imports
(lib/tbpaths.py), the ROMs as arguments (the first --rom is the contrast when it is the untouched Chinese hack), a
payload for the bench's addresses (any AI build's: no AI decision is involved), the Violet Gym save from lib/saves.py,
results under RUNS/animcheck/. The Spanish build's animation fixes (its build.ANIM_RESLOT, ANIM_MISSING_PARAMS and
enginefix.s) are not part of this project, so on our builds these moves fail as on the Chinese ROM.

fuzz/aifuzz.py found asserts while some moves played their animation in doubles (overlay 8's sequence
interpreter 0x021E895E / 0x021E5EFC, the cry player 0x020056FE, 0x02004786), with the move used by the
AI's side and by the player's. Here no AI decision is involved: the player's two Pokemon know only MOVE
and the trainer's two Snorlax know only Splash, in the bench's one-trainer double (bench/aibench.py), so
each ROM plays the same move from the same side. Prints each ROM's asserts with the battle message on
screen when they fired.

--uses N plays one battle per move until MOVE's animation has played N times (used by the player's two level 30
Mew, one with --single, against two level 100 Snorlax; a miss plays none) and reads the battle heap (heap 5) at
every turn's first move menu: its free bytes (the NNS free list) and live allocations (sHeapInfo's count). A move
fails on an assert (the inherited end-of-battle one aside), a NULL allocation, a freeze, or a heap that keeps
shrinking: more than LEAK_PER_USE bytes lost per use from the second turn to the last (the first turn loads a few
things the battle keeps). The exit code is 1 when a ROM other than the Chinese fails. The Chinese run is the
contrast: Leaf Tornado, Leafage, Lunge, Psychic Fangs, Liquidation, Zing Zap and Jet Punch leak 23-28 KB per use
(build.ANIM_RESLOT); Fire Pledge, Searing Shot, Freeze Shock, Throat Chop and Psychic Noise assert, and Psychic
Noise freezes (build.ANIM_MISSING_PARAMS); Hyper Voice asserts in a double (tools/asm/enginefix.s). --inject is the
check's self-test: at run time it sends every particle load (command 0x33) and emitter (0x2E) of slot
build.ANIM_SLOT back to slot 0, the defect build.ANIM_RESLOT removes, so a fixed build must fail again.
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aibench  # noqa: E402
import aifuzz  # noqa: E402
import emu  # noqa: E402
import payload  # noqa: E402
import saves  # noqa: E402
from aidata import Data  # noqa: E402

CN_ROM = os.path.join(tbpaths.WORK, 'rom', 'origin_v4.0.3_cn.nds')
OUT = os.path.join(tbpaths.RUNS, 'animcheck')
HEAP_INFO, BATTLE_HEAP = emu.HEAP_INFO, 5
# overlay 8's move-animation commands, with the first bytes of each handler (other overlays share the addresses)
ANIM_LOAD_CMD, ANIM_EMITTER_CMD = (0x021E5ED8, bytes.fromhex('38b5051c')), (0x021E5B44, bytes.fromhex('f8b584b0'))
# overlay 14's "bl 0x021E4F9C" that starts a move animation (r2 = the move): a use is an animation played
ANIM_START = (0x02200E4A, bytes.fromhex('e4f7a7f8'))
LEAK_PER_USE = 1024        # bytes; measured per use: Razor Leaf 0 after the first turn, the leaking moves 23,000-28,000
FRAMES_PER_USE = 1000      # a double turn (two uses) took 1,100-1,400 frames


class First:
    """The player's policy: the first move button (each Pokemon has one move), the first standing foe."""

    @staticmethod
    def choice(seq):
        return seq[0]


def heap_state(mu, hid=BATTLE_HEAP):
    """(free bytes, live allocations) of heap `hid`, or None if it does not exist."""
    if hid >= mu.read_short(HEAP_INFO + 0x14):
        return None
    h = mu.read_long(mu.read_long(HEAP_INFO) + 4 * mu.read_byte(mu.read_long(HEAP_INFO + 0x10) + hid))
    if not h:
        return None
    free, blk, n = 0, mu.read_long(h + 0x24), 0       # NNS expanded heap free list: +4 size, +12 next
    while blk and n < 4096:
        free, blk, n = free + mu.read_long(blk + 4), mu.read_long(blk + 12), n + 1
    return free, mu.read_short(mu.read_long(HEAP_INFO + 0xC) + 2 * hid)


class HeapBattle(aifuzz.FullBattle):
    def __init__(self, rom, state):
        super().__init__(rom, state)
        self.move, self.played = None, 0
        self.mem.register_exec(ANIM_START[0], self._anim_start)

    def _anim_start(self, a, s):
        if self.reg.r2 == self.move and bytes(self.mu.read_byte(a + k) for k in range(4)) == ANIM_START[1]:
            self.played += 1

    def inject_slot0(self):
        from build import ANIM_SLOT
        for addr, code in (ANIM_LOAD_CMD, ANIM_EMITTER_CMD):
            def back_to_slot0(a, s, code=code):
                if bytes(self.mu.read_byte(a + k) for k in range(4)) != code:
                    return
                slot = self.mu.read_long(self.reg.r0 + 0x18) + 4     # [ctx+0x18]: the command word, then the slot
                if self.mu.read_long(slot) == ANIM_SLOT:
                    self.mem.write_long(slot, 0)
            self.mem.register_exec(addr, back_to_slot0)

    def uses(self, mons, seed, move, n, double):
        """Play until the player's side has used `move` n times; heap 5 at each turn's first move menu."""
        r = self.r
        self.cur = {'mons': mons, 'items': [], 'seed': seed, 'calls': [], 'failures': [], 'notes': [], 'done': False,
                    'decisions': [], 'double': double, 'actions': [], 'fail_detail': [], 'fallbacks': []}
        start, samples, seen_battle, ended = r.frames, [], False, False
        self.move, self.played = move, 0
        aibench.to_battle(r, self.state)
        r.frozen, r.last_beat = False, r.frames        # a freeze in the move before ends with the state load
        while r.frames - start < FRAMES_PER_USE * n + 4000 and not r.frozen:
            k = r.frames - start
            if k % 30 == 0 and self.cur.get('injected'):
                seen_battle = seen_battle or bool(self.alive())
                if seen_battle and r.seen(emu.STATES['field']):
                    ended = True
                    break
            if k % 40 == 0:
                if r.seen(emu.STATES['fight_menu']):
                    if not samples or samples[-1][0] != self.played:    # a turn's first menu (animations since)
                        samples.append((self.played,) + heap_state(self.mu))
                        if self.played >= n:
                            break
                    r.touch(*aifuzz.FIGHT_BUTTON)
                    r.step(50)
                    r.touch(*First.choice(aifuzz.MOVE_BUTTONS))
                    r.step(40 if double else 20)
                    foes = aifuzz.standing_foes(r) if double else []
                    if foes:
                        r.touch(*First.choice(foes))
                        r.step(20)
                else:
                    r.hold('A', 4, release=4)
            else:
                r.step(1)
        c, self.cur = self.cur, None
        fails = sorted({f['ev'].strip() for f in c['fail_detail'] if '020733B2' not in f['ev']})
        return {'samples': samples, 'frozen': r.frozen, 'ended': ended, 'fails': fails, 'used': self.played}


def verdict(res):
    """(failed, loss per use from the second sample to the last, reasons)."""
    s, why = res['samples'], [f for f in res['fails'] if f.startswith(('null', 'assert'))]
    if res['frozen']:
        why.append('freeze')
    why = sorted(set(why))
    per_use = None
    if len(s) >= 3 and s[-1][0] > s[1][0]:
        per_use = (s[1][1] - s[-1][1]) / (s[-1][0] - s[1][0])
        if per_use > LEAK_PER_USE:
            why.append('heap 5 shrinks %d bytes per use' % per_use)
    elif not why:
        why.append('too few turns to measure (%d samples)' % len(s))
    return bool(why), per_use, why


def prepare(rom, tag):
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(aibench.OUT, exist_ok=True)
    rom_copy, state = aibench.link_rom(rom, os.path.join(OUT, tag + '.nds')), os.path.join(OUT, tag + '.dst')
    shutil.copy(saves.path('violet_gym'), os.path.join(aibench.DSV_DIR, tag + '.dsv'))
    subprocess.run([sys.executable, aibench.__file__, '--make-state', rom_copy, state],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return rom_copy, state


def run_uses(rom, moves, n, single, inject=False):
    d = Data(rom)
    template = aibench.template_mon()
    rom_copy, state = prepare(rom, 'animuses_' + os.path.splitext(os.path.basename(rom))[0])
    hb = HeapBattle(rom_copy, state)
    if inject:
        hb.inject_slot0()
    failed = False
    for move in moves:
        mon = lambda sp, lv, mv, i: aibench.build_mon(d, template, {'species': sp, 'level': lv, 'moves': [mv],
                                                                      'ability': 'Run Away', 'item': None}, 1000 + i)
        mons = {'player': [mon('Mew', 30, move, i) for i in range(1 if single else 2)],
                'enemy': [mon('Snorlax', 100, 'Splash', 2), mon('Snorlax', 100, 'Splash', 3)]}
        res = hb.uses(mons, 0x1234, d.id('move', move), n, not single)
        bad, per_use, why = verdict(res)
        failed |= bad
        print('   %-14s %s  played %d; heap 5 per turn (animations, free bytes, allocations): %s; lost per use %s%s' % (
            move, 'FAILED' if bad else 'ok', res['used'], ' '.join('%d:%d/%d' % x for x in res['samples']),
            '%.0f' % per_use if per_use is not None else '-', ('; ' + ', '.join(why)) if why else ''), flush=True)
        if res['fails']:
            print('   %-14s asserts and failures: %s' % ('', ', '.join(res['fails'])), flush=True)
    os.remove(rom_copy)
    return failed


def run(rom, moves, battles):
    d = Data(rom)
    template = aibench.template_mon()
    rom_copy, state = prepare(rom, 'anim_' + os.path.splitext(os.path.basename(rom))[0])
    fb = aifuzz.FullBattle(rom_copy, state)
    out = {}
    for move in moves:
        rows = []
        for k in range(battles):
            mon = lambda sp, lv, mv, i: aibench.build_mon(d, template, {'species': sp, 'level': lv, 'moves': [mv],
                                                                          'ability': 'Run Away', 'item': None}, 1000 + 10 * k + i)
            mons = {'player': [mon('Mew', 70, move, 0), mon('Mew', 70, move, 1)],
                    'enemy': [mon('Snorlax', 60, 'Splash', 2), mon('Snorlax', 60, 'Splash', 3)]}
            res = fb.play(mons, [], 0x1234 + k, First(), True)
            fails = [(f['ev'], (f['text'] or '').replace('\\n', ' ')) for f in res['fail_detail'] if '020733B2' not in f['ev']]
            used = sum(1 for a in res['actions'] if a[1] == 'move' and a[2] == d.id('move', move) and a[5] == '02212673')
            rows.append({'injected': res['injected'], 'ended': res['ended'], 'used': used, 'fails': fails})
        out[move] = rows
    os.remove(rom_copy)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('moves', nargs='+')
    ap.add_argument('--rom', action='append', required=True)
    ap.add_argument('--payload', help="an AI build's payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--battles', type=int, default=1)
    ap.add_argument('--uses', type=int)
    ap.add_argument('--single', action='store_true')
    ap.add_argument('--inject', action='store_true')
    a = ap.parse_args()
    payload.path_from(a.payload)            # exported for the per-ROM processes
    roms = a.rom
    if len(roms) > 1:      # one emulator per process (two DeSmuME instances in one process crash)
        failed = False
        for rom in roms:
            extra = (['--uses', str(a.uses)] if a.uses else []) + (['--single'] if a.single else []) + \
                (['--inject'] if a.inject else [])
            code = subprocess.run([sys.executable, __file__] + a.moves + ['--rom', rom, '--battles', str(a.battles)]
                                  + extra).returncode
            failed |= code != 0 and os.path.realpath(rom) != os.path.realpath(CN_ROM)
        sys.exit(1 if failed else 0)
    rom = roms[0]
    print('==', os.path.basename(rom) + (' (defect injected)' if a.inject else ''), flush=True)
    if a.uses:
        sys.exit(1 if run_uses(rom, a.moves, a.uses, a.single, a.inject) else 0)
    for move, rows in run(rom, a.moves, a.battles).items():
        for r in rows:
            asserts = sorted({ev for ev, _ in r['fails']})
            texts = sorted({t for _, t in r['fails']})
            print('   %-16s used %d, battle %s, asserts %s %s' % (move, r['used'], 'ended' if r['ended'] else 'did not end',
                                                                asserts or 'none', texts[:2] if texts else ''), flush=True)


if __name__ == '__main__':
    main()
