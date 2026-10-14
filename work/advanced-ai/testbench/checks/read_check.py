"""The advanced AI reading the player's committed action, at run time, on one emulator (aibench's machinery).

  .venv/bin/python work/advanced-ai/testbench/checks/read_check.py --rom ROM --payload PAYLOAD [--blind-only] [CASE ...]

Ported from the Spanish workspace's tools/read_check.py (dc8577c). Changes: the AI is switched on for every trainer by
writing the setting into the save in RAM after each state load (bench/aibench.py ADVAI_AI_SETTING 'all') instead of the
battery save; the Read record's address comes from the payload (READS_AT); the ROM is linked, not copied; results go
to RUNS/read/.

Each case is a turn-1 position, singles or doubles. The player never touches the menu after the battle starts; the check
writes the player's committed action itself, as the player's client hands it to the server: its action records
(client+0x534, 12 bytes per Pokemon on the field) and its adapter's answer (0x02252D20[0]: +0 the records, +4 their size,
+0xA answered). Per case:
  wait      no player action for WAIT frames after the AI's first poll: the AI must keep polling and write nothing
  noread    the bench's NOREAD word set (tools/aibench.py): the AI must decide at once, without the player's action
  run       (singles) the player touches RUN WAIT frames after the first poll: no failure or freeze; printed is whether
            the client answered (the AI then decides blind) or refused it in this trainer battle (the AI keeps waiting)
  menu_move, menu_switch  (singles) the player itself chooses, WAIT frames after the first poll, through the touch
            screen: FIGHT and its first move, or POKEMON, the second Pokemon and SHIFT (the party screen loads its
            overlay into the AI's slot meanwhile). The record it commits is printed and checked (kind, move or party
            index, the user's pokeID), and the AI must decide as for that action
  <action>  the action written WAIT frames after the first poll: the AI must then decide, within a few polls, the
            expected action when the case names one
In doubles the AI decides both its Pokemon; both decisions are printed (target by battle position: the player's are
even). With --blind-only, every case runs once, the player idle, for the AI's blind decision (the Spanish tool ran it on a
build without the reading). Prints one JSON line per run and a summary; exits 1 on a failure.

RD (rc33, advai.c rd_gate): the AI uses a read only when its blind model gave the action odds of at least rd_t, or on
its own 20% draw. Each run reads the outcome back from the trainer side's Read record (READS_AT +14, `seen`: bits 0-1
RD_ODDS 1, RD_DRAW 2, RD_BLIND 3; in singles the odds / 16 above them; in doubles foe 0 in bits 0-1, foe 1 in bits
2-3). A used read must give the case's answer. An unused read must give the blind answer: the noread run's for a
switch or an item (the same position, no foresight either way); for a move, foresight's cells still hold (the foe did
commit a move), so every blind move run of a case must decide the same, whatever move was committed, and it is shown
against noread's. Every case gets a noread run.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aibench  # noqa: E402
import payload  # noqa: E402
import saves  # noqa: E402
from aibench import DSV_DIR, Bench, action_name, build_mon, template_mon, to_battle  # noqa: E402
from ai_helpers import mon  # noqa: E402
from aidata import Data  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'read')

AI_POLL = 0x02203736          # the AI client's poll call: r2 the client byte
ADAPTERS = 0x02252D20
MAIN_PTR, MAIN_CLIENTS = 0x02255BAC, 0x234
WAIT = 600
RUN_BUTTON = (128, 176)       # the battle menu's RUN (tools/soundcheck.py)
FIGHT, MOVE_1 = (128, 90), (64, 53)                         # fuzz/aifuzz.py
POKEMON, PANEL_1, SHIFT = (221, 165), (192, 28), (128, 108)  # dev/aitime.py Player
POLLS_AFTER = 8               # a known move or item decides in the same poll; a switch reruns the simulations
SEEN = 14                     # the trainer side's Read record (the payload's READS_AT), its `seen` byte: RD's last outcome
RD_NAMES = {0: 'none', 1: 'odds', 2: 'draw', 3: 'blind'}

# singles: (name, kind, argument, expected action or None); doubles: (name, [(kind, argument, target position)] for the
# player's two Pokemon, {AI pokeID: expected action})
CASES = [
    # Ghost in front, a Normal behind: staying asks for Shadow Claw, the switch to Snorlax for Close Combat
    {'id': 'claw_or_cc', 'player': [mon('Dusknoir', ['Shadow Punch', 'Earthquake']), mon('Snorlax', ['Body Slam'])],
     'enemy': [mon('Machamp', ['Close Combat', 'Shadow Claw', 'Stone Edge'])],
     'actions': [('move:Shadow Punch', 'move', 'Shadow Punch', 'Shadow Claw'), ('move:Earthquake', 'move', 'Earthquake', 'Shadow Claw'),
                 ('switch:Snorlax', 'switch', 1, 'Close Combat'), ('item:Hyper Potion', 'item', 'Hyper Potion', 'Shadow Claw')]},
    # Water/Flying in front, a Ground behind: staying asks for Thunderbolt, the switch to Dugtrio for another answer
    {'id': 'bolt_or_not', 'player': [mon('Gyarados', ['Waterfall', 'Bounce']), mon('Dugtrio', ['Earthquake'])],
     'enemy': [mon('Jolteon', ['Thunderbolt', 'Shadow Ball', 'Hidden Power']), mon('Snorlax', ['Body Slam'])],
     'actions': [('move:Waterfall', 'move', 'Waterfall', 'Thunderbolt'), ('move:Bounce', 'move', 'Bounce', 'Thunderbolt'),
                 ('switch:Dugtrio', 'switch', 1, 'switch:Snorlax'), ('item:Hyper Potion', 'item', 'Hyper Potion', 'Thunderbolt')]},
    # doubles: the blind Close Combat goes to the Snorlax; when the Snorlax protects, to the Tyranitar
    {'id': 'd_protect', 'double': True,
     'player': [mon('Tyranitar', ['Crunch']), mon('Snorlax', ['Body Slam', 'Protect'])],
     'enemy': [mon('Machamp', ['Close Combat']), mon('Blissey', ['Seismic Toss'])],
     'actions': [('crunch+slam', [('move', 'Crunch', 1), ('move', 'Body Slam', 1)], {13: 'Close Combat>Snorlax'}),
                 ('crunch+protect', [('move', 'Crunch', 1), ('move', 'Protect', 2)], {13: 'Close Combat>Tyranitar'})]},
    # doubles: the Snorlax's switch to Gengar puts a Ghost where Close Combat would land: it goes to the Tyranitar
    {'id': 'd_switch', 'double': True,
     'player': [mon('Tyranitar', ['Crunch']), mon('Snorlax', ['Body Slam']), mon('Gengar', ['Shadow Ball'])],
     'enemy': [mon('Machamp', ['Close Combat']), mon('Blissey', ['Seismic Toss'])],
     'actions': [('crunch+slam', [('move', 'Crunch', 1), ('move', 'Body Slam', 1)], {13: 'Close Combat>Snorlax'}),
                 ('crunch+switch:Gengar', [('move', 'Crunch', 1), ('switch', 2, 0)], {13: 'Close Combat>Tyranitar'})]},
    # doubles, Protect (rc31 D2; quick: the waiting runs above already cover the reading). Torkoal at 80% falls to the
    # faster Slowbro's Scald (82.8-99.3% from full): Protect when that buys a turn, attack when nothing changes
    {'id': 'dp_ally_ko', 'double': True, 'quick': True,     # the slower Ferrothorn's Power Whip (70-85%) then KOs the 40% Slowbro
     'player': [mon('Slowbro', ['Scald'], hp=0.4), mon('Pikachu', ['Thunderbolt'])],
     'enemy': [mon('Torkoal', ['Protect', 'Flamethrower'], hp=0.8), mon('Ferrothorn', ['Power Whip'])],
     'actions': [('scald+bolt', [('move', 'Scald', 1), ('move', 'Thunderbolt', 3)], {13: 'Protect>ally'})]},
    {'id': 'dp_ally_first', 'double': True, 'quick': True,  # the faster Raichu's Thunderbolt (67-79%) KOs the 60% Slowbro first
     'player': [mon('Slowbro', ['Scald'], hp=0.6), mon('Pikachu', ['Thunderbolt'])],
     'enemy': [mon('Torkoal', ['Protect', 'Flamethrower'], hp=0.8), mon('Raichu', ['Thunderbolt'])],
     'actions': [('scald+bolt', [('move', 'Scald', 1), ('move', 'Thunderbolt', 3)], {13: '!Protect'})]},
    {'id': 'dp_no_gain', 'double': True, 'quick': True,     # Raichu cannot hurt the Slowbro: nothing changes
     'player': [mon('Slowbro', ['Scald']), mon('Pikachu', ['Thunderbolt'])],
     'enemy': [mon('Torkoal', ['Protect', 'Flamethrower'], hp=0.8), mon('Raichu', ['Thunder Wave'])],
     'actions': [('scald+bolt', [('move', 'Scald', 1), ('move', 'Thunderbolt', 3)], {13: '!Protect'})]},
    {'id': 'dp_poison', 'double': True, 'quick': True,      # the 10% Slowbro faints to its poison at the turn's end
     'player': [mon('Slowbro', ['Scald'], hp=0.1, status='psn'), mon('Pikachu', ['Thunderbolt'])],
     'enemy': [mon('Torkoal', ['Protect', 'Flamethrower'], hp=0.8), mon('Raichu', ['Thunder Wave'])],
     'actions': [('scald+bolt', [('move', 'Scald', 1), ('move', 'Thunderbolt', 3)], {13: 'Protect>ally'})]},
    {'id': 'dp_fakeout', 'double': True, 'quick': True,     # a fresh Ambipom's Fake Out at Torkoal: it flinches anyway
     'player': [mon('Ambipom', ['Fake Out']), mon('Pikachu', ['Thunderbolt'])],
     'enemy': [mon('Torkoal', ['Protect', 'Flamethrower']), mon('Raichu', ['Thunder Wave'])],
     'actions': [('fakeout+bolt', [('move', 'Fake Out', 1), ('move', 'Thunderbolt', 3)], {13: 'Protect>ally'})]},
    # doubles, the order of KOs (rc31 D3): the first decider leads, the second reads its action
    {'id': 'dt_split', 'double': True, 'quick': True,       # Psychic cannot touch Tyranitar: Machamp takes it, Alakazam Pikachu
     'player': [mon('Tyranitar', ['Crunch']), mon('Pikachu', ['Thunderbolt'], hp=0.7)],
     'enemy': [mon('Machamp', ['Close Combat']), mon('Alakazam', ['Psychic'])],
     'actions': [('crunch+bolt', [('move', 'Crunch', 3), ('move', 'Thunderbolt', 1)],
                  {13: 'Close Combat>Tyranitar', 14: 'Psychic>Pikachu'})]},
    {'id': 'dt_faster', 'double': True, 'quick': True,      # both fall to Close Combat; Weavile's Ice Punch KOs Garchomp first
     'player': [mon('Snorlax', ['Body Slam']), mon('Weavile', ['Ice Punch'])],
     'enemy': [mon('Machamp', ['Close Combat']), mon('Garchomp', ['Dragon Claw'])],
     'actions': [('slam+punch', [('move', 'Body Slam', 1), ('move', 'Ice Punch', 3)], {13: 'Close Combat>Weavile'})]},
    {'id': 'dt_focus', 'double': True, 'quick': True,       # tests/ai_batches/draft_31.py b31_focus_with_partner, read
     'player': [mon('Chandelure', ['Flamethrower', 'Heat Wave', 'Shadow Ball', 'Energy Ball']),
                mon('Porygon2', ['Tri Attack', 'Ice Beam', 'Recover'], hp=0.9)],
     'enemy': [mon('Lucario', ['Shadow Ball', 'Close Combat', 'Flash Cannon', 'Swords Dance']), mon('Froslass', ['Shadow Ball'])],
     'actions': [('ball+tri', [('move', 'Shadow Ball', 1), ('move', 'Tri Attack', 3)],
                  {13: 'Shadow Ball>Chandelure', 14: 'Shadow Ball>Chandelure'})]},
]


def record(d, kind, arg, pos_index, user_id, target):
    """The 12-byte action record the player's client hands to the server (the setters' format)."""
    if kind == 'move':
        return struct.pack('<III', 1 | (target << 4) | (d.id('move', arg) << 8), 0, user_id)
    if kind == 'switch':
        return struct.pack('<III', 3 | (pos_index << 4) | (arg << 7), 0, 0)
    return struct.pack('<III', 2 | (d.id('item', arg) << 4), user_id, user_id)


def runs(d, case, blind):
    """(name, records or None, noread, {pokeID: expected})"""
    if blind:
        return [('blind', None, False, {})]
    out = ([] if case.get('quick') else [('wait', None, False, {})]) + [('noread', None, True, {})]
    if not case.get('double'):
        by_name = {a[0]: a[3] for a in case['actions']}
        out += [('run', [RUN_BUTTON], False, {}),
                ('menu_move', [FIGHT, MOVE_1], False, {13: by_name['move:' + case['player'][0]['moves'][0]]}),
                ('menu_switch', [POKEMON, PANEL_1, SHIFT], False, {13: by_name['switch:' + case['player'][1]['species']]})]
    for a in case['actions']:
        if case.get('double'):
            recs = b''.join(record(d, k, arg, i, i + 1, tgt) for i, (k, arg, tgt) in enumerate(a[1]))
            out.append((a[0], recs, False, a[2]))
        else:
            out.append((a[0], record(d, a[1], a[2], 0, 1, 1), False, {13: a[3]}))
    return out


class ReadBench(Bench):
    def _event(self, **ev):
        if ev['ev'] == 'clipped':           # a text-fit note (lib/emu.py), not the reading's business: kept apart
            if self.cur is not None:
                self.cur['notes'].append('clipped text %r' % (ev.get('text') or '')[:60])
            return
        super()._event(**ev)

    def __init__(self, rom, state):
        super().__init__(rom, state)
        self.read_seen = self.layout.words['READS_AT'] + SEEN
        self.mem.register_exec(AI_POLL, self._poll)

    def _poll(self, a, s):
        c = self.cur
        if c is None or not (self.reg.r2 & 1):
            return
        c['polls'] += 1
        if c['first'] is None:
            c['first'] = self.r.frames
        if isinstance(c['recs'], list) and 'committed' not in c and self.mu.read_byte(self.mu.read_long(ADAPTERS) + 0xA):
            rec = self.mu.read_long(self.mu.read_long(ADAPTERS))
            c['committed'] = [self.mu.read_long(rec + 4 * k) for k in range(3)]
        if isinstance(c['recs'], bytes) and not c.get('wrote') and self.r.frames - c['first'] >= WAIT:
            self.inject(c['recs'])
            c['wrote'] = self.r.frames
            c['polls_at_write'] = c['polls']

    def inject(self, recs):
        mu = self.mu
        ad = mu.read_long(ADAPTERS)
        pc = mu.read_long(mu.read_long(MAIN_PTR) + MAIN_CLIENTS)
        self.cur['adapter_cmd'] = mu.read_byte(ad + 0xB)
        self.cur['answered_before'] = mu.read_byte(ad + 0xA)
        self.cur['client_adapter_match'] = mu.read_long(pc + 0x18) == ad
        buf = pc + 0x534
        self._write(buf, recs)
        self.mem.write_long(ad, buf)
        self.mem.write_long(ad + 4, len(recs))
        self.mem.write_byte(ad + 0xA, 1)

    def go(self, mons, recs, noread, double, seed, tag=''):
        self.cur = {'mons': mons, 'items': [], 'seed': seed, 'calls': [], 'failures': [], 'notes': [], 'done': False,
                    'double': double, 'polls': 0, 'first': None, 'recs': recs, 'tag': tag}
        start = self.r.frames
        to_battle(self.r, self.state)
        self.mem.write_long(aibench.NOLEAD_FLAG, aibench.NOLEAD_MAGIC)
        self.mem.write_long(aibench.NOREAD_FLAG, aibench.NOREAD_MAGIC if noread else 0)
        self.mem.write_byte(self.read_seen, 0)
        limit = aibench.FRAME_LIMIT + WAIT + 600
        done_at = None
        while self.r.frames - start < limit and not self.r.frozen:
            if self.cur['first'] is None and (self.r.frames - start) % 40 == 0:
                self.r.hold('A', 4, release=4)
            else:
                self.r.step(1)
            c = self.cur
            if c['done'] and done_at is None:
                done_at = self.r.frames
            # doubles: the AI's second Pokemon decides after the first; singles stop at the decision
            if done_at is not None and (not double or len({x[3] for x in c['calls'] if x[0] != 'none'}) >= 2 or
                                        self.r.frames - done_at > 300):
                break
            if recs is None and not noread and c['first'] is not None and self.r.frames - c['first'] > WAIT:
                break
            if isinstance(recs, list) and c['first'] is not None and self.r.frames - c['first'] >= WAIT:
                if not c.get('wrote'):
                    self.r.skip_render = False      # for the screenshots below
                    for pt in recs:
                        self.r.touch(*pt)
                        self.r.step(42)
                    c['wrote'], c['polls_at_write'] = self.r.frames, c['polls']
                elif self.r.frames - c['wrote'] in (30, 300):
                    c['notes'].append(self.r.shot('read_%s_%d' % (c['tag'], self.r.frames - c['wrote'])))
                elif self.r.frames - c['wrote'] > WAIT:
                    break
        c, self.cur = self.cur, None
        self.r.skip_render = True
        return {'calls': [x for x in c['calls'] if x[0] != 'none'], 'polls': c['polls'], 'first': c['first'],
                'wrote': c.get('wrote'), 'polls_at_write': c.get('polls_at_write'), 'end': self.r.frames,
                'adapter_cmd': c.get('adapter_cmd'), 'answered_before': c.get('answered_before'),
                'client_adapter_match': c.get('client_adapter_match'), 'failures': c['failures'], 'notes': c['notes'],
                'committed': c.get('committed'), 'seen': self.mu.read_byte(self.read_seen),
                'frozen': bool(self.r.frozen)}


def prepare(rom, tag):
    """A link to `rom`, its battery save (the Violet Gym save) and the bench's save state; the AI on for every trainer
    in the save in RAM after each load."""
    os.makedirs(OUT, exist_ok=True)
    os.environ[aibench.SETTING_ENV] = 'all'
    with open(os.path.join(OUT, 'template.bin'), 'wb') as f:
        f.write(template_mon())
    rom_copy = aibench.link_rom(rom, os.path.join(OUT, 'rc_%s.nds' % tag))
    shutil.copy(saves.path('violet_gym'), os.path.join(DSV_DIR, 'rc_%s.dsv' % tag))
    state = os.path.join(OUT, 'rc_%s.dst' % tag)
    if os.path.exists(state):
        os.remove(state)                # a state belongs to one build
    subprocess.run([sys.executable, aibench.__file__, '--make-state', rom_copy, state],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(state):
        sys.exit('no save state made from %s' % rom)
    return rom_copy, state


def rd_outcomes(res, double):
    """RD's outcome per foe read (RD_NAMES keys), and in singles the odds (per mille, to 16)"""
    v = res['seen']
    return ([v & 3, (v >> 2) & 3], None) if double else ([v & 3], (v >> 2) * 16)


def unused(res, double):
    return 3 in rd_outcomes(res, double)[0]


def problems(case, name, res, expect, blind):
    out = []
    if res['failures'] or res['frozen']:
        out.append('failures %s frozen %s' % (res['failures'], res['frozen']))
    if blind:
        return out
    if name == 'run':
        return out
    if name.startswith('menu_'):
        w = res['committed']
        want = (1, case['player'][0]['moves'][0]) if name == 'menu_move' else (3, 1)
        if not w:
            out.append('the player committed nothing')
        elif want[0] == 1 and (w[0] & 15 != 1 or (w[0] >> 8) & 0xFFFF != res['move_id'] or w[2] != 1):
            out.append('committed %s, expected kind 1, move %d, user pokeID 1' % (['%08X' % x for x in w], res['move_id']))
        elif want[0] == 3 and (w[0] & 15 != 3 or (w[0] >> 7) & 7 != 1 or (w[0] >> 4) & 7 or w[0] & 0x400):
            out.append('committed %s, expected kind 3, party index 1, position index 0' % ['%08X' % x for x in w])
    if name == 'wait':
        if res['calls']:
            out.append('decided without the player\'s action: %s' % res['calls'])
        if res['polls'] < WAIT // 2:
            out.append('only %d polls while waiting' % res['polls'])
        return out
    if name == 'noread':
        if not res['calls'] or res['polls'] > POLLS_AFTER + 8:
            out.append('NOREAD: no prompt decision (%d polls)' % res['polls'])
        return out
    if not res['calls']:
        out.append('no decision after the action')
    elif res['polls'] - res['polls_at_write'] > POLLS_AFTER * (2 if case.get('double') else 1) and not name.startswith('menu_'):
        out.append('%d polls after the action' % (res['polls'] - res['polls_at_write']))
    if not name.startswith('menu_') and (res['adapter_cmd'] != 2 or res['answered_before'] or not res['client_adapter_match']):
        out.append('adapter %s answered %s match %s' % (res['adapter_cmd'], res['answered_before'], res['client_adapter_match']))
    if unused(res, case.get('double')):
        return out                  # checked against the blind runs (rd_blind)
    for who, want in expect.items():
        got = [x['action'] for x in res['named'] if x['who'] == who]
        if want.startswith('!') and len(got) == 1 and not got[0].startswith(want[1:]):
            continue
        if got != [want]:
            out.append('pokeID %d: %s, expected %s' % (who, got, want))
    return out


def rd_blind(case, rows):
    """the runs whose read RD did not use: a switch or item decides as noread, the moves all alike"""
    double = bool(case.get('double'))
    acts = lambda r: sorted((x['who'], x['action']) for x in r['named'])
    nr = next((r for r in rows if r['player'] == 'noread'), None)
    moves = []
    for r in rows:
        if r['player'] in ('wait', 'noread', 'run') or not unused(r, double):
            continue
        outs = rd_outcomes(r, double)[0]
        if double and any(o in (1, 2) for o in outs):
            r['notes'].append('RD mixed %s: not checked' % outs)
            continue
        is_move = not double and (r['player'].startswith('move:') or r['player'] == 'menu_move')
        if is_move:
            moves.append(r)
        elif nr is None or acts(r) != acts(nr):
            r['problems'].append('RD blind: %s, noread %s' % (acts(r), acts(nr) if nr else None))
    if len({tuple(acts(r)) for r in moves}) > 1:
        for r in moves:
            r['problems'].append('RD blind moves differ: %s' % [(m['player'], acts(m)) for m in moves])
    for r in moves:
        r['notes'].append('RD blind move: %s (noread %s)' % (acts(r), acts(nr) if nr else None))


def run(rom, tag, blind, only):
    d = Data(rom)
    rom_copy, state = prepare(rom, tag)
    template = open(os.path.join(OUT, 'template.bin'), 'rb').read()
    b = ReadBench(rom_copy, state)
    rows = []
    for case in CASES:
        if only and case['id'] not in only:
            continue
        seed = aibench.hash_id(case['id'])
        double = bool(case.get('double'))
        mons = {k: [build_mon(d, template, spec, seed + 31 * i) for i, spec in enumerate(case[k])] for k in ('player', 'enemy')}
        case_rows = []
        for name, recs, noread, expect in runs(d, case, blind):
            res = b.go(mons, recs, noread, double, seed, case['id'] + '_' + name)
            res['move_id'] = d.id('move', case['player'][0]['moves'][0])
            res['named'] = [{'who': x[3], 'action': action_name(d, x[0], x[1], x[2], case['enemy'], case['player'] if double else None)}
                            for x in res['calls']]
            res.update(case=case['id'], player=name, rom=tag, double=double)
            res['problems'] = problems(case, name, res, expect, blind)
            case_rows.append(res)
        if not blind:
            rd_blind(case, case_rows)
        for res in case_rows:
            rows.append(res)
            print(json.dumps(res), flush=True)
    return rows


def main():                          # one emulator per process
    ap = argparse.ArgumentParser()
    ap.add_argument('cases', nargs='*', help='case ids (default: every case)')
    ap.add_argument('--rom', required=True, help='an AI build')
    ap.add_argument('--payload', help="the AI build's payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--blind-only', action='store_true', help='each case once, the player idle: the blind decision')
    a = ap.parse_args()
    payload.path_from(a.payload)
    blind = a.blind_only
    tag = '%s_%s' % (os.path.splitext(os.path.basename(a.rom))[0], 'blind' if blind else 'read')
    rows = run(a.rom, tag, blind, set(a.cases))
    print('\nsummary')
    for r in rows:
        dt = (r['end'] - r['wrote']) if r['wrote'] else None
        outs, odds = rd_outcomes(r, r['double'] if 'double' in r else False)
        rd = '/'.join(RD_NAMES[o] for o in outs) + ('' if odds is None else ' %d' % odds)
        print('%-12s %-6s %-20s -> %-50s rd %-12s polls %3s (at write %s) frames after write %s%s' % (
            r['case'], r['rom'], r['player'], ', '.join('%s %s' % (x['who'], x['action']) for x in r['named']) or 'none',
            rd, r['polls'], r['polls_at_write'], dt, ' FAIL ' + '; '.join(r['problems']) if r['problems'] else ''))
    bad = sum(bool(r['problems']) for r in rows)
    print('%d of %d runs failed' % (bad, len(rows)))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
