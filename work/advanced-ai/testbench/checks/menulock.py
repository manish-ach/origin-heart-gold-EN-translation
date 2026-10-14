"""The player's battle menu when no move can be selected, its message for a move the hack bans, and recoil.

  .venv/bin/python work/advanced-ai/testbench/checks/menulock.py --rom ROM [--rom ROM ...] [--payload PAYLOAD]
                   [--advanced] [--inject] [CASE ...]   # exit 1 when a case fails

Ported from the Spanish workspace's qa/ai_research/menulock.py (dc8577c). Changes: the AI setting is written into the
save in RAM after each state load (bench/aibench.py ADVAI_AI_SETTING: 'all' with --advanced, else 'off'); the battle
messages it counts are the ROM's own (battle_string.narc banks 1 and 2, filled with the Pokemon's name, and the move-use
line 'Mew used/usó <the ROM's Struggle>'), so the check reads English and Spanish builds alike; the ROM is linked, not
copied; results go to RUNS/menulock/. --payload is always needed (the bench's machinery reads the AI build's
addresses; on a ROM without the AI any payload of the same layout serves).

Several cases test fixes of the Spanish build's tools/asm/enginefix.s (fight_forced, the recoil rounding, the Pursuit
refusal message), which this project does not port: on a build without those fixes they fail as the Chinese ROM does.
The quick tier runs the advanced AI's side of it: --advanced with the foe cases (foe_pp4, foe_pp4_one, foe_pp4_bench,
foe_pp4_double), where the AI must Struggle or switch and the battle must end.

Each case is a trainer battle, the player's Mew (two in `double`) against two level 70 Snorlax, played by
fuzz/aifuzz.py's FullBattle with the AI setting off (overlay 11). The Mew is level 20 at 1 HP unless a case
says otherwise, so the first Struggle's recoil ends the battle. The player touches the first move; after a refused
move the next one, as a person would. Cases:
- struggle cases (the battle must end, with the player's Struggle set and used): `choice` (Choice Scarf, Crush Grip
  5 PP and Psybeam: locked into Crush Grip with no PP), `pp` (Crush Grip only), `taunt` (status moves only, the foe
  Taunts), `disable` (Psybeam only, the foe Disables it), `double` (the second Mew is `choice`'s, the first `pp`'s),
  `pursuit` (Pursuit only: the hack marks it never selectable), and (rc42, qa/bug_enfix.md) four moves at 0 PP from
  the start: `pp4`, `pp4_choice` (with a Choice Scarf, no lock yet), `pp4_double` (both Mew, the second with a Choice
  Band; both must Struggle). Before tools/asm/enginefix.s's fight_forced the menu refused every move with nothing else
  to choose: the soft lock.
- `foe_pp4` (rc42): the Snorlax know four moves at 0 PP and the Mew Splashes: the foe's Struggle must be set, its
  "no moves left" and recoil messages shown, and the battle must end (the AI's side; --advanced for the advanced AI).
  `foe_pp4_one`: the same with one Snorlax, so the AI cannot switch. `foe_pp4_double`: a double against three such
  Snorlax. `foe_pp4_bench`: only the first Snorlax is out of PP, the second has its moves, and the trainer keeps its
  party order (the NOLEAD word, written at the lead pick's call): the battle must end (the AI may switch).
- `encore` (Crush Grip and Psybeam, the foe Encores): the battle must end, Struggle or not. It never reached a turn
  with no selectable move (the same play before and after the fix), so it only shows Encore unchanged.
- `pursuit_msg` (Pursuit and Psybeam): refusing Pursuit must show std 441 "This move can't be used!"; the Chinese
  ROM showed the last message left in the client's message parameter (the send-out line "Go, Mew!").
- `choice_pp` (Choice Scarf, Psybeam and Crush Grip, a short battle): a lock with PP left, unchanged: the menu takes
  Psybeam every turn, no refusal, no Struggle.
- recoil cases (a level 100 Mew at full HP): each use of a move whose recoil is a share of its user's max HP must
  cost that share, rounded half up as Gen 5 does (Struggle 1/4, Chloroblast 1/2; the HP loss command carries the
  amount even when the user has less HP left). `recoil`: the foes know only Pursuit, so overlay 11 Struggles every
  turn (the Mew Splashes); `recoil_player`: the Mew knows only Pursuit and Struggles; `chloroblast`: the Mew uses
  Chloroblast. The Chinese ROM took the share of the damage dealt instead. Read from the battle commands 8 (damage,
  with the move) and 48 (HP loss, cause 4: recoil).
--advanced sets the AI setting 'all' (flag 0x2C2): the foes use the advanced AI. Each case's printed texts are kept in
RUNS/menulock/<ROM tag>_<case>_texts.json (with the actions set).
--inject puts the Chinese bytes back at the Spanish build's patch sites in overlay 14 when the FIGHT step first runs,
so a fixed Spanish build plays as the Chinese ROM does (the check must then fail). Spanish rc44 only.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aibench  # noqa: E402
import aifuzz  # noqa: E402
import failures  # noqa: E402
import payload  # noqa: E402
import saves  # noqa: E402
from aidata import Data  # noqa: E402
from failures import INHERITED, MENU_MOVE, STRUGGLE, USED  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'menulock')
SPLASH = ['Splash']
FOUR, NO_PP = ['Psybeam', 'Crush Grip', 'Growl', 'Tail Whip'], [0, 0, 0, 0]


def case(players, foes, expect, frames, double=False, level=20, hp=1, uses=0, foe_pp=None, want=None, foe_count=2,
         keep_lead=False):
    """players: (moves, item) or (moves, item, PP left per move) per Mew; hp as aibench takes it (an int is HP, a
    float a fraction); uses: the recoil cases' least number of measured uses; foe_pp: the Snorlax's PP left per move;
    want: the player's pokeIDs that must set Struggle (default the last Mew's)."""
    return {'players': players, 'foes': foes, 'expect': expect, 'frames': frames, 'double': double, 'level': level,
            'hp': hp, 'uses': uses, 'foe_pp': foe_pp, 'want': want, 'foe_count': foe_count,
            'keep_lead': keep_lead}


CASES = {
    'choice': case([(['Crush Grip', 'Psybeam'], 'Choice Scarf')], SPLASH, 'struggle', 30000),
    'pp': case([(['Crush Grip'], None)], SPLASH, 'struggle', 30000),
    'taunt': case([(['Growl', 'Tail Whip'], None)], ['Taunt'], 'struggle', 30000),
    'disable': case([(['Psybeam'], None)], ['Disable'], 'struggle', 30000),
    'double': case([(['Crush Grip'], None), (['Crush Grip', 'Psybeam'], 'Choice Scarf')], SPLASH, 'struggle', 36000,
                   double=True),
    'pursuit': case([(['Pursuit'], None)], SPLASH, 'struggle', 30000),
    'encore': case([(['Crush Grip', 'Psybeam'], None)], ['Encore'], 'ends', 36000),
    'pursuit_msg': case([(['Pursuit', 'Psybeam'], None)], SPLASH, 'message', 5000),
    'choice_pp': case([(['Psybeam', 'Crush Grip'], 'Choice Scarf')], SPLASH, 'normal', 6000),
    'recoil': case([(SPLASH, None)], ['Pursuit'], 'recoil', 3500, level=100, hp=1.0, uses=3),
    'recoil_player': case([(['Pursuit'], None)], SPLASH, 'recoil', 3500, level=100, hp=1.0, uses=3),
    'chloroblast': case([(['Chloroblast'], None)], SPLASH, 'recoil', 3500, level=100, hp=1.0, uses=2),
    'pp4': case([(FOUR, None, NO_PP)], SPLASH, 'struggle', 30000),
    'pp4_choice': case([(FOUR, 'Choice Scarf', NO_PP)], SPLASH, 'struggle', 30000),
    'pp4_double': case([(FOUR, None, NO_PP), (FOUR, 'Choice Band', NO_PP)], SPLASH, 'struggle', 36000, double=True,
                       want={1, 2}),
    'foe_pp4': case([(SPLASH, None)], FOUR, 'foe_struggle', 30000, foe_pp=NO_PP),
    'foe_pp4_one': case([(SPLASH, None)], FOUR, 'foe_struggle', 30000, foe_pp=NO_PP, foe_count=1),
    'foe_pp4_bench': case([(SPLASH, None)], FOUR, 'ends', 30000, foe_pp=[NO_PP, None], keep_lead=True),
    'foe_pp4_double': case([(SPLASH, None), (SPLASH, None)], FOUR, 'foe_struggle', 36000, double=True, foe_pp=NO_PP,
                           foe_count=3),
}
MAX_HP_RECOIL = {'Struggle': 4, 'Chloroblast': 2}    # the user loses 1/n of its max HP (move data byte 19 negative)
BATTLE_NARC = 'battle/string/battle_string.narc'
# the ROM's battle strings this check counts: (bank, index, the Pokemon named), read by messages()
CANT_BE_USED = (2, 441, None)           # "This move can't be used!"
FOE_NO_MOVES = (1, 1134, 'Snorlax')     # the foe's variant of 1132, from the server's Struggle handler
FOE_RECOIL = (1, 514, 'Snorlax')        # the foe's recoil line (its move use line is not a 'print' event)
NO_MOVES_LEFT = (1, 1132, 'Mew')        # "Mew has no moves left!"
STUCK_TAIL = 8      # this many refused moves in a row, every move tried: the menu accepts none
FIGHT_STEP = 0x02202F4C
CHINESE_BYTES = {0x02202F7C: '29f0e8fa', 0x0222C6A0: 'fbf734fca3490022f9f7d6f8', 0x02206A9C: '281c'}
LEAD_CALL = 0x022153C2      # overlay 14: the single battle's call to the server start, where ai_lead picks the lead
BATTLE_CMD, READ_CMD = 0x0220467E, (0x02204668, bytes.fromhex('20f036fb'))   # tools/emu.py: overlay 14 loaded
CMD_DAMAGE, CMD_HP_LOSS, CAUSE_RECOIL = 8, 48, 4


class Stuck(Exception):
    pass


def flat(text):
    """A message as one line: its line and page breaks as spaces, its commands left out."""
    t = re.sub(r'\\[nrf]', ' ', text or '')
    return ' '.join(re.sub(r'\{[^}]*\}', '', t).split())


def messages(rom):
    """{name: the flat text to look for} from the ROM's own strings: a Pokemon's name in place of its buffer, and the
    player's Struggle line ('Mew used Struggle', 'Mew usó Forcejeo') from the ROM's move name."""
    from romio import read_narc
    from text import decode_bank
    narc, _ = read_narc(rom, BATTLE_NARC)
    banks = {}
    out = {}
    for key, (bank, idx, name) in (('CANT_BE_USED', CANT_BE_USED), ('FOE_NO_MOVES', FOE_NO_MOVES),
                                   ('FOE_RECOIL', FOE_RECOIL), ('NO_MOVES_LEFT', NO_MOVES_LEFT)):
        if bank not in banks:
            banks[bank] = decode_bank(narc.files[bank])[1]
        t = banks[bank][idx][0]
        out[key] = flat(re.sub(r'\{STRVAR_1 2,[^}]*\}', name or '', t))
    failures.use_rom(rom)
    out['STRUGGLE_USED'] = ['Mew' + m + failures.move_names()[STRUGGLE] for m in USED]
    return out


def shows(text, want):
    """The printed text holds the message (or one of the messages)."""
    t = flat(text)
    return any(w in t for w in want) if isinstance(want, list) else want in t


def refusal(acts):
    """The player's last pick was refused: the menu set a move and nothing came after it (an accepted move is
    followed by the AI's next decision, or in a double by the target screen's)."""
    return bool(acts) and acts[-1][5] == MENU_MOVE


class Retry:
    """The first move button; after a refusal the next one. Raises Stuck when the menu refused STUCK_TAIL in a row."""
    def __init__(self, fb):
        self.fb, self.k = fb, 0

    def choice(self, seq):
        if seq is not aifuzz.MOVE_BUTTONS:
            return seq[0]
        acts = self.fb.cur['actions']
        tail = acts[-STUCK_TAIL:]
        if len(tail) == STUCK_TAIL and all(a[5] == MENU_MOVE for a in tail):
            raise Stuck()
        self.k = (self.k + 1) % len(seq) if refusal(acts) else 0
        return seq[self.k]


def watch_commands(fb, d):
    """Damage and recoil of the MAX_HP_RECOIL moves from the battle client's commands, into fb.uses while it is a
    list: per use the move and the damage dealt, then its user's pokeID, the recoil and the user's max HP."""
    m = fb.mu
    moves = {d.id('move', name) for name in MAX_HP_RECOIL}
    fb.uses = None

    def bpp(poke):
        return m.read_long(m.read_long(aibench.MAIN_PTR) + 0x54 + 0x8C + 4 * poke)

    def cmd(a, s):
        if fb.uses is None or bytes(m.read_byte(READ_CMD[0] + k) for k in range(4)) != READ_CMD[1]:
            return
        client = fb.reg.r4
        code, args = m.read_long(client + 0x2C), [m.read_long(client + 0x38 + 4 * k) for k in range(3)]
        if code == CMD_DAMAGE and args[2] in moves:
            fb.uses.append({'move': args[2], 'dealt': m.read_long(client + 0x9C)})   # (pokeID, damage) at +0x98
        elif code == CMD_HP_LOSS and args[2] == CAUSE_RECOIL and fb.uses and 'user' not in fb.uses[-1]:
            fb.uses[-1].update(user=args[0], lost=args[1], max_hp=m.read_short(bpp(args[0]) + 0x1C))
    fb.mem.register_exec(BATTLE_CMD, cmd)


def play(fb, d, template, name, tag, msg):
    c = CASES[name]
    build = lambda spec, i: aibench.build_mon(d, template, dict(spec, ability='Run Away'), 500 + i)
    mons = {'player': [build({'species': 'Mew', 'level': c['level'], 'hp': c['hp'], 'moves': p[0], 'item': p[1],
                              'pp': p[2] if len(p) > 2 else None}, i) for i, p in enumerate(c['players'])],
            'enemy': [build({'species': 'Snorlax', 'level': 70, 'moves': c['foes'], 'item': None,
                             'pp': c['foe_pp'][i] if c['foe_pp'] and isinstance(c['foe_pp'][0], list) else c['foe_pp']},
                            8 + i) for i in range(c['foe_count'])]}
    texts = []
    forward = fb.r.event

    def event(**ev):
        if ev['ev'] == 'print':
            texts.append((fb.r.frames, ev['text']))
        else:
            forward(**ev)
    fb.r.event, fb.r.trace, fb.uses = event, True, []
    fb.keep_lead = c['keep_lead']
    aifuzz.BATTLE_FRAMES = c['frames']
    stuck = False
    try:
        res = fb.play(mons, [], 0x77, Retry(fb), c['double'])
    except Stuck:
        stuck = True
        res = {'ended': None, 'actions': fb.cur['actions'], 'failures': fb.cur['failures']}
        fb.cur = None
    fb.r.event, fb.r.trace = forward, None
    with open(os.path.join(OUT, '%s_%s_texts.json' % (tag, name)), 'w') as f:
        json.dump({'texts': texts, 'actions': res['actions']}, f, ensure_ascii=False, indent=0)
    uses, fb.uses = [u for u in fb.uses if 'user' in u], None
    acts = res['actions']
    menu = [a for a in acts if a[5] == MENU_MOVE]
    struggle = sorted({a[4] for a in acts if a[2] == STRUGGLE and a[4] is not None and a[4] <= 6})
    foe_struggle = sorted({a[4] for a in acts if a[2] == STRUGGLE and a[4] is not None and a[4] >= 13})
    foe_no_moves = sum(1 for f, t in texts if shows(t, msg['FOE_NO_MOVES']))
    foe_recoil = sum(1 for f, t in texts if shows(t, msg['FOE_RECOIL']))
    refusals = sum(1 for i in range(1, len(acts)) if acts[i][5] == acts[i - 1][5] == MENU_MOVE)
    used = sum(1 for f, t in texts if shows(t, msg['STRUGGLE_USED']))
    no_moves = sum(1 for f, t in texts if shows(t, msg['NO_MOVES_LEFT']))
    detail = '%s; menu moves %d, refused %d, player Struggle set by %s, "%s" x%d, "%s" x%d' % (
        'ended at frame %d' % res['ended'] if res['ended'] else 'stuck at the menu' if stuck else 'did not end',
        len(menu), refusals, struggle or 'nobody', msg['NO_MOVES_LEFT'], no_moves, msg['STRUGGLE_USED'][-1], used)
    if c['foe_pp']:
        detail += '; AI switches %d' % sum(1 for a in acts if a[1] == 'switch' and a[5] == 'ai')
    expect = c['expect']
    if expect == 'struggle':
        want = c['want'] or ({2} if c['double'] else {1})
        ok = bool(res['ended']) and want <= set(struggle) and used > 0
    elif expect == 'foe_struggle':
        ok = bool(res['ended']) and bool(foe_struggle) and foe_no_moves > 0 and foe_recoil > 0
        detail += '; foe Struggle set by %s, "%s" x%d, "%s" x%d, AI fallbacks %s' % (
            foe_struggle or 'nobody', msg['FOE_NO_MOVES'], foe_no_moves, msg['FOE_RECOIL'], foe_recoil,
            sorted({x.get('fallback') for x in res.get('fallbacks', [])}) or 'none')
    elif expect == 'ends':
        ok = bool(res['ended'])
    elif expect == 'normal':
        psybeam = d.id('move', 'Psybeam')
        ok = not struggle and refusals == 0 and sum(1 for a in menu if a[2] == psybeam) >= 3
    elif expect == 'recoil':
        def rule(u):     # 1/n of max HP rounded half up, as Gen 5
            n = MAX_HP_RECOIL[d.move_name[u['move']]]
            return (2 * u['max_hp'] + n) // (2 * n)
        ok = len(uses) >= c['uses'] and all(u['lost'] == rule(u) for u in uses)
        detail += '; uses (user, move, dealt, recoil, max HP, its share): %s' % ', '.join(
            '(%d, %s, %d, %d, %d, %d)' % (u['user'], d.move_name[u['move']], u['dealt'], u['lost'], u['max_hp'],
                                          rule(u)) for u in uses)
    else:
        banned = d.id('move', 'Pursuit')
        first = next((a[0] for a in menu if a[2] == banned), None)
        shown = next((t for f, t in texts if first is not None and f >= first), None)
        earlier = next((f for f, t in texts if first is not None and f < first and t == shown), None)
        ok = flat(shown) == msg['CANT_BE_USED']
        detail += '; refusal message %r%s' % (shown, '' if earlier is None else
                                              ' (stale: printed before, at frame %d)' % earlier)
    bad = [f for f in res.get('failures', []) if f.split()[-1] not in INHERITED]
    if bad:
        ok = False
        detail += '; failures %s' % bad
    # the advanced AI's fallbacks: 6 (no usable option: overlay 11 Struggles) is by design, any other is not
    loud = sorted({x.get('fallback') for x in res.get('fallbacks', [])} - {None, 0, 6})
    if loud:
        ok = False
        detail += '; the advanced AI fell back with codes %s (FB_* in src/advai.c)' % loud
    print('   %-4s %-13s %s' % ('ok' if ok else 'FAIL', name, detail), flush=True)
    return ok


def inject(fb):
    def put(a, s):
        for addr, hexs in CHINESE_BYTES.items():
            for k, byte in enumerate(bytes.fromhex(hexs)):
                fb.mem.write_byte(addr + k, byte)
    fb.mem.register_exec(FIGHT_STEP, put)


def run(rom, names, injected=False, advanced=False):
    os.makedirs(OUT, exist_ok=True)
    d = Data(rom)
    msg = messages(rom)
    template = aibench.template_mon()
    tag = 'menulock_' + os.path.splitext(os.path.basename(rom))[0] + '_adv' * advanced
    rom_copy, state = aibench.link_rom(rom, os.path.join(OUT, tag + '.nds')), os.path.join(OUT, tag + '.dst')
    os.environ[aibench.SETTING_ENV] = 'all' if advanced else 'off'     # written after each state load (to_battle)
    shutil.copy(saves.path('violet_gym'), os.path.join(aibench.DSV_DIR, tag + '.dsv'))
    subprocess.run([sys.executable, aibench.__file__, '--make-state', rom_copy, state],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fb = aifuzz.FullBattle(rom_copy, state)
    fb.keep_lead = False
    fb.mem.register_exec(LEAD_CALL, lambda a, s: fb.keep_lead and fb.mem.write_long(aibench.NOLEAD_FLAG,
                                                                                   aibench.NOLEAD_MAGIC))
    watch_commands(fb, d)
    if injected:
        inject(fb)
    ok = all([play(fb, d, template, name, tag, msg) for name in names])
    os.remove(rom_copy)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', action='append', required=True, help='a ROM (repeat for several, one process each)')
    ap.add_argument('--payload', help="an AI build's payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--inject', action='store_true')
    ap.add_argument('--advanced', action='store_true', help='the save\'s AI setting on: the foes use the advanced AI')
    ap.add_argument('cases', nargs='*', metavar='CASE')
    a = ap.parse_args()
    roms = a.rom
    names = a.cases or list(CASES)
    if set(names) - set(CASES):
        ap.error('unknown case %s (cases: %s)' % (sorted(set(names) - set(CASES)), ' '.join(CASES)))
    if len(roms) > 1:      # one emulator per process (two DeSmuME instances in one process crash)
        codes = [subprocess.run([sys.executable, __file__, '--rom', rom] + ['--inject'] * a.inject +
                                ['--advanced'] * a.advanced + (['--payload', a.payload] if a.payload else []) +
                                names).returncode
                 for rom in roms]
        sys.exit(1 if any(codes) else 0)
    payload.path_from(a.payload)            # the bench's machinery reads the AI build's addresses (slot range, words)
    print('==', os.path.basename(roms[0]), '(Chinese bytes injected)' if a.inject else '',
          '(advanced AI)' if a.advanced else '(AI setting off: overlay 11)', flush=True)
    sys.exit(0 if run(roms[0], names, a.inject, a.advanced) else 1)


if __name__ == '__main__':
    main()
