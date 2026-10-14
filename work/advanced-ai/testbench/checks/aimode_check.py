"""The advanced AI's three settings at run time: who it serves under each (flags 0x2C2 and 0x2C3, src/aiselect.s).

  .venv/bin/python work/advanced-ai/testbench/checks/aimode_check.py --rom ROM --payload PAYLOAD [CASE ...] [--workers N]

Rewritten from the Spanish workspace's tools/aimode_check.py (dc8577c) for this project's setting: the Spanish check
set the flags in the battery save before booting (its Pokemon Center NPC's three answers); here each case writes its
setting into the save in RAM after the bench state loads (lib/emu.py set_ai_setting, through bench/aibench.py
ADVAI_AI_SETTING), as the Options row will write the same flags (docs/build-contract.md "Settings"):

  off        0x2C2 clear              the hack's own AI for every trainer
  all        0x2C2 set, 0x2C3 clear   the advanced AI for every trainer it supports
  important  0x2C2 set, 0x2C3 set     the advanced AI only for marked trainers (bit 0 of header byte 2, a/0/5/5)

Every case is a full trainer battle from the bench's save state (the Violet Gym save, the field before Officer Felix,
trainer 71) with the battle's trainers set when SetupAndStartTrainerBattle (0x02050768) is entered: trainer 1,
trainer 2 (a double against two trainers) and a partner (a multi battle). The marks this check relies on: 253 (Leader
Brock, a Gym Leader), 8 (Rival Blue), 63 (Steven, a partner), 71 (a Violet Gym trainer, marked by the gym rule) and 937
(Elder Tianyuan, a one-of-a-kind story character) are marked; 5 (Picnicker Amelia), 6 (Youngster Sol) and 15 (Bug
Catcher Dylan) are not. Both the ROM's header bytes and data/trainer_marks.json must agree before anything runs.

Trainer 1's team is replaced as the bench does (three level 10 Pokemon), the player's too (level 100 Pokemon with
damaging moves, two in a double), so trainer 1 loses its first Pokemon on turn 1 and picks a replacement among two;
the battle is played to the end as fuzz/aifuzz.py plays it. Recorded: the setting the save in RAM held, the overlay
each selection phase loads into the battle slot (10: overlay 11 plus the advanced AI, 11: overlay 11 alone), each AI
poll's entry by client (adv_entry or overlay 11's entry, as aiselect.s ai_entry sends it; 1 and 3 are the foes, 2 the
partner), the AI actions written from the advanced AI's code, each ai_replace call and the advanced replacements it
made (src/replace.c, the Replaced records at the payload's REPLACED_AT), and every assert, NULL allocation, freeze or
text outside its window. A case fails if any of that differs from what its setting must do, or the battle does not
end, or when a decision made in overlay 10 shows a fallback code other than 0 (or 3, doubles by design): a fallback
where the AI should serve fails loudly. Results: RUNS/aimode/. Exit status 1 when a case fails.
"""
import argparse
import json
import os
import random
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aibench  # noqa: E402
import aifuzz  # noqa: E402
import emu  # noqa: E402
import payload  # noqa: E402
import saves  # noqa: E402
from aidata import Data  # noqa: E402
from failures import INHERITED  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'aimode')
TRAINER_DATA = 'a/0/5/5'        # trainer headers: byte 2 bit 0 = important, bit 1 = keep lead (data/trainer_marks.json)
MARKS = os.path.join(tbpaths.ADV, 'data', 'trainer_marks.json')
POLL_RETURN = 0x0220373A        # after the client's "bl" to the AI entry at 0x02203736 (ai_entry tail-calls)
REPLACED_SIZE = 32              # replace.c's Replaced record: seq first, the trainer's first
MARKED, UNMARKED = (253, 8, 63, 71, 937), (5, 6, 15)
# case: (setting, trainer 1 (None: the save's 71), trainer 2, partner, the overlays the slot must load, the clients
# whose polls must go to adv_entry, those that must go to overlay 11's entry). Only clients served by adv_entry may
# get advanced replacements, and trainer 1 must get one when it is served.
CASES = {
    'all_unmarked':       ('all', 5, 0, 0, {10}, {1}, set()),
    'all_marked':         ('all', 253, 0, 0, {10}, {1}, set()),
    'important_marked':   ('important', 253, 0, 0, {10}, {1}, set()),
    'important_unmarked': ('important', 5, 0, 0, {11}, set(), {1}),
    'important_gym':      ('important', None, 0, 0, {10}, {1}, set()),     # the save's own Gym trainer, 71
    'important_story':    ('important', 937, 0, 0, {10}, {1}, set()),      # a story character, Elder Tianyuan
    'off_marked':         ('off', 253, 0, 0, {11}, set(), {1}),
    'off_unmarked':       ('off', 5, 0, 0, {11}, set(), {1}),
    'important_double_1': ('important', 253, 6, 0, {10}, {1}, {3}),        # marked trainer 1, unmarked trainer 2
    'important_double_3': ('important', 5, 8, 0, {10}, {3}, {1}),          # unmarked trainer 1, marked trainer 2
    'important_multi':    ('important', 5, 6, 63, {10}, {2}, {1, 3}),      # only the partner is marked
    'important_multi_no': ('important', 5, 6, 15, {11}, set(), {1, 2, 3}),
    'all_multi':          ('all', 5, 6, 63, {10}, {1, 2, 3}, set()),
    'off_multi':          ('off', 5, 6, 63, {11}, set(), {1, 2, 3}),
}
ENEMY = [{'species': s, 'level': 10, 'moves': ['Tackle'], 'ability': 'Run Away'} for s in ('Rattata', 'Pidgey', 'Sentret')]
PLAYER = [{'species': 'Mewtwo', 'level': 100, 'moves': ['Psychic', 'Ice Beam', 'Thunderbolt', 'Flamethrower'],
           'ability': 'Pressure'},
          {'species': 'Mew', 'level': 100, 'moves': ['Psychic', 'Ice Beam', 'Thunderbolt', 'Flamethrower'],
           'ability': 'Synchronize'}]


class ModeBattle(aifuzz.FullBattle):
    """A full battle with the case's trainers, recording which AI served each client."""

    def __init__(self, rom, state):
        super().__init__(rom, state)
        lay = self.layout
        self.adv_entry, self.ov11_entry = lay.adv_code[0], lay.orig_code[0]
        self.replaced_at = lay.words['REPLACED_AT']
        self.case = (None, 0, 0)
        self.mem.register_exec(self.adv_entry, self._poll('adv'))
        self.mem.register_exec(self.ov11_entry, self._poll('ov11'))
        self.mem.register_exec(lay.sym('ai_replace') & ~1, self._replace)

    def _double(self, a, s):        # SetupAndStartTrainerBattle(task, trainer 1, trainer 2, partner, ...)
        if self.cur is None:
            return
        t1, t2, partner = self.case
        if t1:
            self.reg.r1 = t1
        self.reg.r2, self.reg.r3 = t2, partner

    def _inject(self, a, s):
        c = self.cur
        fresh = c is not None and not c.get('injected')
        super()._inject(a, s)
        if fresh and c.get('injected'):
            c.update({'slots': set(), 'polls': {}, 'replace_calls': [], 'adv_actions': 0, 'pending': None, 'adv_reps': {},
                      'setting': emu.ai_setting(self.r)})
            self.rec = c

    def _slot(self, a, s):
        super()._slot(a, s)
        if self.cur is not None and 'slots' in self.cur and self.reg.r0 in (10, 11):
            self.cur['slots'].add(self.reg.r0)

    def _poll(self, entry):
        def f(a, s):
            c = self.cur
            if c is not None and 'polls' in c and self.reg.r14 & ~1 == POLL_RETURN and c.get('slot') in (10, 11):
                c['polls'].setdefault(entry, set()).add(self.reg.r2 & 0xFF)
        return f

    def replaced(self):
        return sum(self.mu.read_byte(self.replaced_at + REPLACED_SIZE * k) for k in range(2))

    def _settle(self, c):
        """Credit the advanced replacements since the last ai_replace call to that call's client (one at a time)."""
        if c.get('pending'):
            client, seq = c['pending']
            n = self.replaced() - seq & 0xFF
            if n:
                c['adv_reps'][client] = c['adv_reps'].get(client, 0) + n

    def _replace(self, a, s):
        c = self.cur
        if c is not None and 'replace_calls' in c:
            self._settle(c)
            client = self.mu.read_byte(self.reg.r0 + 2)
            c['replace_calls'].append(client)
            c['pending'] = (client, self.replaced())

    def _setter(self, kind):
        base = super()._setter(kind)
        lo, hi = self.layout.adv_code

        def f(a, s):
            c = self.cur
            if c is not None and 'adv_actions' in c and kind != 'none' and lo <= self.reg.r14 < hi and c.get('slot') == 10:
                c['adv_actions'] += 1
            base(a, s)
        return f

    def run_case(self, mons, seed, t1, t2, partner):
        self.case, self.rec = (t1, t2, partner), None
        res = self.play(mons, [], seed, random.Random(seed), double=bool(t2))
        c = self.rec                    # play() drops self.cur when it returns
        if c is not None:
            self._settle(c)
            res.update({'slots': sorted(c['slots']), 'polls': {k: sorted(v) for k, v in c['polls'].items()},
                        'replace_calls': c['replace_calls'], 'adv_actions': c['adv_actions'], 'adv_reps': c['adv_reps'],
                        'setting': c['setting']})
        return res


def worker(case, rom, state, out_path):
    t1, t2, partner = CASES[case][1:4]
    d = Data(rom)
    template = open(os.path.join(aibench.OUT, 'template.bin'), 'rb').read()
    mb = ModeBattle(rom, state)
    seed = aibench.hash_id(case)
    mons = {'player': [aibench.build_mon(d, template, m, seed + i) for i, m in enumerate(PLAYER[:2 if t2 else 1])],
            'enemy': [aibench.build_mon(d, template, m, seed + 7 + i) for i, m in enumerate(ENEMY)]}
    t0 = time.time()
    res = mb.run_case(mons, seed, t1, t2, partner)
    res['seconds'] = round(time.time() - t0, 1)
    with open(out_path, 'w') as f:
        json.dump(res, f)


def check(case, res):
    """What differs from the case's setting."""
    setting, t1, t2, partner, slots, adv, ov11 = CASES[case]
    if res is None:
        return ['no result (the worker died)']
    if not res.get('injected') or 'slots' not in res:
        return ['no battle']
    out = []
    if res.get('setting') != setting:
        out.append('the save in RAM held setting %r, the case wrote %r' % (res.get('setting'), setting))
    if set(res['slots']) != slots:
        out.append('the slot loaded overlays %s, the setting wants %s' % (res['slots'], sorted(slots)))
    got_adv, got_ov11 = set(res['polls'].get('adv', [])), set(res['polls'].get('ov11', []))
    if got_adv != adv:
        out.append('adv_entry served clients %s, the setting wants %s' % (sorted(got_adv), sorted(adv)))
    if got_ov11 != ov11:
        out.append("overlay 11's entry served clients %s, the setting wants %s" % (sorted(got_ov11), sorted(ov11)))
    if bool(adv) != bool(res['adv_actions']):
        out.append('%d actions written by the advanced AI' % res['adv_actions'])
    # a fallback where the AI serves would look like the setting working (src/advai.c FB_*: 3 is doubles' by-design)
    fb = sorted({d['fallback'] for d in res.get('decisions', []) if d.get('slot') == 10} - {None, 0, 3})
    if fb:
        out.append('the advanced AI fell back where it serves (codes %s, FB_* in src/advai.c)' % fb)
    if 1 not in res['replace_calls']:
        out.append('trainer 1 never picked a replacement (ai_replace calls: %s)' % res['replace_calls'])
    reps = {int(k): v for k, v in res['adv_reps'].items()}
    if set(reps) - adv:
        out.append('advanced replacements for clients the setting does not serve: %s' % reps)
    if 1 in adv and not reps.get(1):
        out.append('trainer 1 got no advanced replacement')
    bad = [f for f in res['failures'] if f.split()[0] != 'assert' or f.split()[-1] not in INHERITED]
    if bad:
        out.append('failures: %s' % bad)
    if not res.get('ended'):
        out.append('the battle did not end (%s)' % ('frozen' if res.get('frozen') else '%d frames' % res['frames']))
    return out


def marks_problems(rom):
    """The trainers this check relies on, against the ROM's important bits and data/trainer_marks.json."""
    from romio import read_narc
    rom_marks = {k: f[2] & 1 for k, f in enumerate(read_narc(rom, TRAINER_DATA)[0].files)}
    listed = set(json.load(open(MARKS))['important'])
    out = []
    for t in MARKED + UNMARKED:
        want = t in MARKED
        if bool(rom_marks.get(t)) != want:
            out.append('trainer %d is %s in the ROM; this check needs it %s' % (
                t, 'marked' if rom_marks.get(t) else 'not marked', 'marked' if want else 'unmarked'))
        if (t in listed) != want:
            out.append('trainer %d is %s in %s' % (t, 'listed' if t in listed else 'not listed', tbpaths.rel(MARKS)))
    return out


def make_state(rom, tag):
    """The bench's save state for this ROM (the Violet Gym save, booted on a link to `rom`); the setting is written
    after each load, so one state serves every case."""
    import shutil
    rom_link = aibench.link_rom(rom, os.path.join(OUT, tag + '.nds'))
    state = os.path.join(OUT, tag + '.dst')
    dsv = os.path.join(aibench.DSV_DIR, tag + '.dsv')
    shutil.copy(saves.path('violet_gym'), dsv)
    subprocess.run([sys.executable, aibench.__file__, '--make-state', rom_link, state],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for p in (rom_link, dsv):
        if os.path.lexists(p):
            os.remove(p)
    if not os.path.exists(state):
        sys.exit('no save state made from %s' % rom)
    return state


def rom_tag(rom):
    return os.path.splitext(os.path.basename(rom))[0]


def run(case, rom, state):
    """One case on its own link to `rom` (named by the ROM and the case: DeSmuME names the battery save after it)."""
    import shutil
    tag = 'aimode_%s_%s' % (rom_tag(rom), case)
    rom_k, dsv_k = os.path.join(OUT, tag + '.nds'), os.path.join(aibench.DSV_DIR, tag + '.dsv')
    aibench.link_rom(rom, rom_k)
    shutil.copy(saves.path('violet_gym'), dsv_k)
    op = os.path.join(OUT, '%s.json' % tag)
    if os.path.exists(op):
        os.remove(op)
    env = dict(os.environ, **{aibench.SETTING_ENV: CASES[case][0]})
    subprocess.run([sys.executable, __file__, '--worker', case, rom_k, state, op], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for p in (rom_k, dsv_k):
        if os.path.lexists(p):
            os.remove(p)
    return json.load(open(op)) if os.path.exists(op) else None


def main():
    if sys.argv[1:2] == ['--worker']:
        return worker(*sys.argv[2:6])
    ap = argparse.ArgumentParser()
    ap.add_argument('cases', nargs='*', help='default: every case (%s)' % ', '.join(CASES))
    ap.add_argument('--rom', required=True, help='an AI build')
    ap.add_argument('--payload', help="the AI build's payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--workers', type=int, default=2, help='emulator processes (lib/emupool.py caps the machine)')
    a = ap.parse_args()
    payload.path_from(a.payload)            # exported for the workers
    wrong = marks_problems(a.rom)
    if wrong:
        sys.exit('the trainer marks are not as this check expects:\n  ' + '\n  '.join(wrong))
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(aibench.OUT, exist_ok=True)
    with open(os.path.join(aibench.OUT, 'template.bin'), 'wb') as f:
        f.write(aibench.template_mon())
    cases = a.cases or list(CASES)
    unknown = [c for c in cases if c not in CASES]
    if unknown:
        sys.exit('unknown cases %s (known: %s)' % (unknown, ', '.join(CASES)))
    t0 = time.time()
    state = make_state(a.rom, 'aimode_' + rom_tag(a.rom))
    with ThreadPoolExecutor(a.workers) as pool:
        res = dict(zip(cases, pool.map(lambda c: run(c, a.rom, state), cases)))
    failed = 0
    for c in cases:
        problems = check(c, res[c])
        failed += bool(problems)
        r = res[c] or {}
        print('%-19s %-6s setting %s, slots %s, adv_entry %s, overlay 11 %s, advanced actions %d, ai_replace by client '
              '%s, advanced replacements by client %s, %s s' % (
                  c, 'ok' if not problems else 'FAILED', r.get('setting'), r.get('slots'), r.get('polls', {}).get('adv', []),
                  r.get('polls', {}).get('ov11', []), r.get('adv_actions', 0), r.get('replace_calls'), r.get('adv_reps'),
                  r.get('seconds')))
        for p in problems:
            print('    ' + p)
    print('aimode_check: %d of %d case(s) failed (%.0f s)' % (failed, len(cases), time.time() - t0))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
