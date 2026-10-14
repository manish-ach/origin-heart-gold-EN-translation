"""Research probe: what the trainer AI (overlay 11) scores and decides, turn by turn, in set-up battles.

  .venv/bin/python work/advanced-ai/testbench/dev/aiprobe.py [SCENARIO ...] [--rom ROM] [--workers N]

Ported from the Spanish workspace's qa/ai_research/aiprobe.py (dc8577c) into the test bench: its imports (lib/tbpaths.py),
the ROM and its default the untouched Chinese hack as arguments, the Violet Gym save from lib/saves.py, results under RUNS/ai_probe/.

Each scenario boots the Violet Gym save with a one-Pokémon party of our choosing, rewrites Officer
Felix's (trainer 71) header and party records as they load (header return 0x02072580, party return
0x02072768), fights with the player's first move every turn, and logs at the AI's decision writer
(0x021E4F2C, r1 = the AI state):
  moves      per AI move: id, the factor values (state+0x30 + target * 0x70 + move * 0x1C: +2 move,
             +4..+0x14 factors 0-4, +0x18 skip flag)
  candidates move (skip, score, move, target), switch (skip, score, slot), item (skip, score, item)
and the action the AI commits through the overlay 14 setters. Output: RUNS/ai_probe/<scenario>.json
and a summary per turn. Not a pass/fail check: the scenarios state what a strong AI would do.
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import emu  # noqa: E402
import saves  # noqa: E402

WORK = tbpaths.WORK
CN_ROM = os.path.join(WORK, 'rom', 'origin_v4.0.3_cn.nds')

DSV_DIR = emu.DSV_DIR
OUT = os.path.join(tbpaths.RUNS, 'ai_probe')
HEADER_THUNK, HEADER_RET = 0x02072700, 0x02072580    # thunk(member r0, dest r1) -> NarcLoad
PARTY_THUNK, PARTY_RET = 0x02072710, 0x02072768
WRITER = 0x021E4F2C
SETTERS = {0x02200960: 'fight', 0x02200A30: 'item', 0x022009AC: 'switch', 0x0220091C: 'none'}
SLOT = 0x02215914
# exits of the switch gate 0x021E6918: battle rule or no Pokémon, side flag or trapped, no bench or no
# opponent, pass
GATE = {0x021E6930: 'no_rule', 0x021E6968: 'trapped_or_flag', 0x021E6988: 'no_bench', 0x021E698C: 'pass'}
PARALYSIS = 0x40

# species, level, (hp, atk, def, spe, spa, spd), moves, status, current hp (None: full)
# enemy: species, level, ability, item, moves, IV byte, nature (0xFF none)
SCENARIOS = {
    'type_choice': {
        'why': 'Blastoise vs Charizard: Rock Slide is 4x, Water Gun 2x with STAB, Earthquake cannot hit',
        'player': (6, 50, (153, 104, 98, 120, 129, 105), [45, 45, 45, 45], 0, None),   # Growl
        'enemy': [(9, 50, 67, 0, [33, 55, 157, 89], 255, 0xFF)],
        'strong': 'Rock Slide (157) or Water Gun (55); never Earthquake (89)',
    },
    'priority_ko': {
        'why': 'Scizor vs a faster Alakazam at 1 HP whose Fire Punch KOs Scizor: only Bullet Punch moves first',
        'player': (65, 50, (130, 70, 65, 140, 155, 105), [7, 7, 7, 7], 0, 1),          # Fire Punch
        'enemy': [(212, 50, 101, 0, [418, 404, 14, 442], 255, 0xFF)],
        'strong': 'Bullet Punch (418)',
    },
    'redundant_status': {
        'why': 'player already paralyzed: Thunder Wave and Toxic cannot work',
        'player': (143, 50, (220, 130, 85, 50, 85, 130), [45, 45, 45, 45], PARALYSIS, None),
        'enemy': [(26, 50, 9, 0, [86, 92, 85, 33], 255, 0xFF)],
        'strong': 'Thunderbolt (85); never Thunder Wave (86) or Toxic (92)',
    },
    'status_healthy': {
        'why': 'same trainer, healthy player: does it ever use a status move?',
        'player': (143, 50, (220, 130, 85, 50, 85, 130), [45, 45, 45, 45], 0, None),
        'enemy': [(26, 50, 9, 0, [86, 92, 85, 33], 255, 0xFF)],
        'strong': 'Thunder Wave or Toxic on turn 1 is reasonable against a bulky Snorlax; Thunderbolt too',
    },
    'switch_bad_matchup': {
        'why': 'Rhydon (4x weak to water) faces a faster Blastoise with Surf; Ludicolo on the bench takes 1/4',
        'player': (9, 50, (154, 103, 120, 98, 105, 125), [57, 57, 57, 57], 0, None),    # Surf
        'enemy': [(112, 50, 31, 0, [89, 157, 33, 39], 255, 0xFF),
                  (272, 50, 33, 0, [402, 57, 58, 33], 255, 0xFF)],
        'strong': 'switch to Ludicolo on turn 1',
    },
    'heal_item': {
        'why': 'Super Fang halves the foe each turn; the trainer carries two Full Restores',
        'player': (20, 50, (900, 101, 600, 117, 70, 600), [162, 162, 162, 162], 0, None),  # Super Fang, bulky
        'enemy': [(143, 50, 17, 0, [34, 33, 0, 0], 255, 0xFF)],
        'items': [23, 23, 0, 0],
        'strong': 'Full Restore once it is low (turn 3, at 25%)',
    },
    'switch_no_effect': {
        'why': 'Raichu knows only Electric moves and faces a Golem (immune to all of them); Blastoise on the bench',
        'player': (76, 50, (155, 130, 150, 65, 75, 85), [45, 45, 45, 45], 0, None),     # Growl
        'enemy': [(26, 50, 9, 0, [85, 84, 87, 9], 255, 0xFF),
                  (9, 50, 67, 0, [57, 58, 33, 39], 255, 0xFF)],
        'strong': 'switch to Blastoise on turn 1',
    },
    'setup_safe': {
        'why': 'Gengar faces a Snorlax that only knows Normal moves (cannot touch it): Nasty Plot is free',
        'player': (143, 50, (220, 130, 85, 50, 85, 130), [34, 34, 34, 34], 0, None),    # Body Slam
        'enemy': [(94, 50, 26, 0, [417, 247, 85, 101], 255, 0xFF)],
        'strong': 'Nasty Plot (417) first, then attack',
    },
}
SCRIPT_TURN = ['press A', 'wait 60', 'until fight_menu A 1500']


def record(species, level, ability, item, moves, iv, nature):
    r = bytearray(28)
    r[0], r[3] = iv, nature
    struct.pack_into('<HHHH', r, 4, ability, level, species, item)
    struct.pack_into('<4H', r, 0xC, *moves)
    return bytes(r)


def make_save(sc, path):
    from savetool import Save
    species, level, stats, moves, status, hp = SCENARIOS[sc]['player']
    s = Save(saves.path('violet_gym'))
    s.put('<I', 0x94, 1)
    m = s.mon(0)
    m.set_species(species, 'TEST')
    m.set_level(level, 125000)
    m.set_stats(*stats)
    m.set_status(status)
    if hp is not None:
        m.set_hp(hp)
    struct.pack_into('<4H', m.blocks['B'], 0, *moves)
    m.blocks['B'][8:12] = bytes([30, 30, 30, 30])
    m.blocks['A'][2:4] = b'\0\0'                 # no held item
    s.set_mon(0, m)
    s.write(path)


def worker(sc, rom, out, turns):
    from emu import Runner
    r = Runner(rom, os.path.join(out, sc + '_shots'))
    mem, reg, mu = r.emu.memory, r.emu.memory.register_arm9, r.emu.memory.unsigned
    r.run(open(os.path.join(tbpaths.LIB, 'boot.txt')).read().splitlines())
    cfg = SCENARIOS[sc]
    party = b''.join(record(*e) for e in cfg['enemy'])
    dest = {}
    log = {'turns': [], 'actions': [], 'slots': []}

    def thunk(kind):
        def f(a, s):
            dest[kind] = (reg.r1, reg.r0)
        return f

    def header_ret(a, s):
        p, member = dest['header']
        if member != 71:
            return
        mem.write_byte(p + 3, len(cfg['enemy']))
        for k, it in enumerate(cfg.get('items', [0, 0, 0, 0])):
            mem.write_short(p + 4 + 2 * k, it)

    def party_ret(a, s):
        p, member = dest['party']
        if member != 71:
            return
        for k, b in enumerate(party):
            mem.write_byte(p + k, b)

    signed = lambda v: v - (1 << 32) if v >> 31 else v

    def writer(a, s):
        if not log['slots'] or log['slots'][-1][1] != 11:
            return
        st = reg.r1
        rows = []
        for t in range(2):
            for k in range(4):
                e = st + 0x30 + t * 0x70 + k * 0x1C
                mv = mu.read_short(e + 2)
                if mv:
                    rows.append({'target': t, 'move': mv, 'skip': mu.read_long(e + 0x18),
                                 'factors': [signed(mu.read_long(e + 4 + 4 * f)) for f in range(5)]})
        log['turns'].append({
            'frame': r.frames, 'moves': rows,
            'cand_move': {'skip': mu.read_long(st + 0x37C), 'score': signed(mu.read_long(st + 0x380)),
                          'move': mu.read_short(st + 0x222), 'target': mu.read_byte(st + 0x220)},
            'cand_switch': {'skip': mu.read_long(st + 0x418), 'score': signed(mu.read_long(st + 0x41C)),
                            'slot': mu.read_byte(st + 0x410)},
            'cand_item': {'skip': mu.read_long(st + 0x3B8), 'score': signed(mu.read_long(st + 0x3BC)),
                          'item': mu.read_short(st + 0x3B4)}})

    def setter(name):
        def f(a, s):
            if 0x021E4DA0 <= reg.r14 < 0x021F6E00 and log['slots'] and log['slots'][-1][1] == 11:
                log['actions'].append({'frame': r.frames, 'kind': name, 'r1': reg.r1, 'r2': reg.r2})
        return f

    mem.register_exec(HEADER_THUNK, thunk('header'))
    mem.register_exec(PARTY_THUNK, thunk('party'))
    mem.register_exec(HEADER_RET, header_ret)
    mem.register_exec(PARTY_RET, party_ret)
    mem.register_exec(WRITER, writer)
    mem.register_exec(SLOT, lambda a, s: log['slots'].append((r.frames, reg.r0)))
    for addr, name in SETTERS.items():
        mem.register_exec(addr, setter(name))
    log['gate'] = {}

    def gate(name):
        def f(a, s):
            if log['slots'] and log['slots'][-1][1] == 11:
                log['gate'][name] = log['gate'].get(name, 0) + 1
        return f
    for addr, name in GATE.items():
        mem.register_exec(addr, gate(name))
    r.run(['goto 15 14', 'wait 300', 'until fight_menu A 6000'])
    r.shot('turn1')
    for t in range(turns):
        r.run(SCRIPT_TURN)
    log['frozen'] = r.frozen
    with open(os.path.join(out, sc + '.json'), 'w') as f:
        json.dump(log, f, indent=1)


def run(sc, rom_src, turns):
    os.makedirs(OUT, exist_ok=True)
    rom = os.path.join(OUT, 'probe_%s.nds' % sc)
    dsv = os.path.join(DSV_DIR, 'probe_%s.dsv' % sc)
    shutil.copy(rom_src, rom)
    make_save(sc, dsv)
    subprocess.run([sys.executable, __file__, '--worker', sc, rom, OUT, str(turns)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for p in (rom, dsv):
        os.remove(p)
    path = os.path.join(OUT, sc + '.json')
    return json.load(open(path)) if os.path.exists(path) else None


def summary(sc, res):
    lines = ['== %s: %s' % (sc, SCENARIOS[sc]['why']), '   strong play: ' + SCENARIOS[sc]['strong']]
    if res is None:
        return lines + ['   no result']
    acts = [a for a in res['actions'] if a['kind'] != 'none']
    for n, t in enumerate(res['turns']):
        mv = ', '.join('%d%s %s' % (m['move'], ' (skip)' if m['skip'] else '', m['factors'])
                       for m in t['moves'] if m['target'] == 0)
        c = t['cand_move'], t['cand_switch'], t['cand_item']
        act = acts[n] if n < len(acts) else None
        lines.append('   turn %d: moves [%s]' % (n + 1, mv))
        lines.append('           candidates: move %d score %d%s | switch slot %d score %d%s | item %d score %d%s'
                     % (c[0]['move'], c[0]['score'], ' skip' if c[0]['skip'] else '',
                        c[1]['slot'], c[1]['score'], ' skip' if c[1]['skip'] else '',
                        c[2]['item'], c[2]['score'], ' skip' if c[2]['skip'] else ''))
        lines.append('           chose: %s' % (('%s %d (r2 %d)' % (act['kind'], act['r1'], act['r2'])) if act else '?'))
    lines.append('   switch gate exits: %s' % res.get('gate'))
    if res.get('frozen'):
        lines.append('   FROZE')
    return lines


def main():
    if sys.argv[1:2] == ['--worker']:
        return worker(sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5]))
    ap = argparse.ArgumentParser()
    ap.add_argument('scenarios', nargs='*')
    ap.add_argument('--rom', default=CN_ROM)
    ap.add_argument('--workers', type=int, default=2, help='emulator processes (the budget is 2)')
    ap.add_argument('--turns', type=int, default=4)
    a = ap.parse_args()
    names = a.scenarios or list(SCENARIOS)
    with ThreadPoolExecutor(a.workers) as pool:
        results = list(pool.map(lambda n: run(n, a.rom, a.turns), names))
    for n, res in zip(names, results):
        print('\n'.join(summary(n, res)))


if __name__ == '__main__':
    main()
