"""The hack's own trainer teams, and random teams, as team specs for the AI vs AI test (the Spanish qa/aivsai_plan.md).

  .venv/bin/python work/advanced-ai/testbench/versus/aiteams.py --rom ROM            # six-Pokémon teams, skipped, examples
  .venv/bin/python work/advanced-ai/testbench/versus/aiteams.py --rom ROM --trainer ID   # one trainer's team
  .venv/bin/python work/advanced-ai/testbench/versus/aiteams.py --rom ROM --check    # every team through aibench.build_mon
  .venv/bin/python work/advanced-ai/testbench/versus/aiteams.py --rom ROM --game ID [ID ...]   # the game's own builder

Ported from the Spanish workspace's tools/aiteams.py (dc8577c). Changes: the ROM is an argument (no default build);
the trainer classes and natures come from lib/names.json (the Spanish text/en banks 720 and 33); the random teams
from lib/randteams.py; the docs/trainers.md comparison runs only with ADVAI_TRAINERS_DOC (that file is the Spanish
bundle's); no rc32 trainer exclusions (the Spanish set was empty).

API (the shapes of the plan's "Interfaces"):
  trainer_teams(rom, size=6) -> [{'source': 'trainer', 'trainer': 712, 'name': 'Leader Falkner', 'team': [spec x 6]}]
  random_team(seed, size=6, level=100) -> {'source': 'random', 'seed': seed, 'name': 'Random <seed>', 'team': [...]}

A spec is what aibench.build_mon builds: species, level (the record's own), moves, ability, item, evs,
nature, ivs. Each field is read the way the game's party builder (0x0207272C) reads the records, so a
spec builds the Pokémon that trainer has in the game:
- header a/0/5/5 (20 bytes): class at 1, party size at 3. Party a/0/5/6, 28 bytes per Pokémon: 0 IV byte,
  1 PID bias (gender low nibble, ability slot high nibble), 2 form, 3 nature (0xFF: the PID's), 4 ability
  u16, 6 level u16, 8 species u16, 10 item u16, 12 four moves u16 (first 0: level-up moves), 20 EVs,
  26 shiny.
- EVs go to MON_DATA 13-18 in that order: HP, Atk, Def, Spe, SpA, SpD. docs/trainers.md prints the six
  bytes as they are, and most spreads read as Showdown's order (HP/Atk/Def/SpA/SpD/Spe), so the
  game gives a "6/252/0/0/0/252" Jolly attacker 252 Sp. Def EVs and no Speed EVs. The specs follow the game.
- IVs: CreateMon sets all six to byte * 31 // 255, then the builder sets the HP IV to 10, 20 or 31 (level
  up to 40, below 80, from 80). `ivs` is one value for all six, so a spec's HP IV is the other five's.
- Nature: the record's (MON_DATA 0xBE), else the PID's: seed = trainer + species + IV byte + level,
  the LCRNG run (class) times, PID = (last << 8) + bias (0x78 for a female class, else 0x88; a record's
  gender nibble sets it to the gender ratio +2 (1) or -2, its ability nibble clears (1) or sets (2) bit 0,
  and the bias stays changed for the records after it).
- Moves: the record's; with none, the last four level-up moves at its level (a/0/3/3, (level, move) pairs).
- Names: species, moves, abilities and items by tools/aidata.py's names. A name aidata maps to another id is
  given as the id (Data.id accepts it): Eviolite, Weak. Policy and Air Balloon each name two items, aidata
  takes the lower id (110, 111, 252), which has no entry in the battle engine's item handler table (overlay
  14, 0x0224BA30), and the trainers hold the higher one (584, 600, 576). Rocky Helmet names 324 and 590 too;
  the trainers hold 324, which has no handler either: by the table their Rocky Helmets do nothing (not tried in a
  battle; the specs keep 324).
- Trainer names: the ROM's (bank 719 of the message NARC, decoded), after the class (lib/names.json trainer_class, the
  Spanish English bank 720), as docs/trainers.md's headings print them; --check compares the two with that file.
  Our build stores five long names (D-2487, work/tools/trainer_display.py: ids 17, 59, 632, 666, 745) in bank 719 as
  keys 'T000xx' and draws the full name from ITCM; full_names() puts the full names back, from the translation
  workspace the build takes them from (work/translate/banks/a027/0719.json, trainer_display.plan).
Skipped: teams with an alternate form (build_mon writes no form), records with no ability (the game picks
one at random), names aidata does not have.
"""
import argparse
import collections
import functools
import json
import os
import random
import re
import struct
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
import randteams  # noqa: E402
from aidata import NAMES, NATURES, STATS, Data, norm  # noqa: E402
from text import decode_bank  # noqa: E402

DOCS = os.environ.get('ADVAI_TRAINERS_DOC') or ''      # only check() reads it, and runs without it
EXCLUDED_TRAINERS = set()        # trainer ids never turned into bench teams (the Spanish rc32 list: empty)
WORKSPACE = os.path.join(tbpaths.WORK, 'translate', 'banks')    # where the build takes the full trainer names from
TOOLS = os.path.join(tbpaths.WORK, 'tools')                      # work/tools/trainer_display.py
TRAINER_NAMES = 719             # the message bank of trainer names (packed; the same in every build)
CLASS_GENDER = 0x020FF77C        # arm9: u8 per trainer class, 1 = female (the PID bias 0x78 instead of 0x88)
ITEM_HANDLERS = (14, 0x0224BA30, 211)   # overlay 14: (u32 item, u32 handler) per item the battle engine handles
TRAINER_SET_INIT = 0x02072544    # EnemyTrainerSet_Init(setup, ...): trainer ids at setup+0x18, the foe's at +0x1C
BUILT = 0x02072920               # party builder: r4 = the finished Pokémon (stats calculated), before AddMonToParty
LEAF_TORNADO = 'Leaf Tornado'    # battle heap leak: froze doubles after ~16 uses (failures.KNOWN_ANIM)
NAME_TABLE = {'species': 'species_name', 'move': 'move_name', 'ability': 'ability_name', 'item': 'item_name'}


@functools.lru_cache(None)
def data(rom):
    return Data(rom)


@functools.lru_cache(None)
def rom_tables(rom):
    import ndspy.narc
    import ndspy.rom
    r = ndspy.rom.NintendoDSRom.fromFile(rom)
    narc = lambda path: ndspy.narc.NARC(r.getFileByName(path)).files
    arm9 = bytes(r.arm9)
    ov, addr, n = ITEM_HANDLERS
    o = r.loadArm9Overlays()[ov]
    code = bytes(r.files[o.fileID])
    handled = {struct.unpack_from('<I', code, addr - o.ramAddress + 8 * k)[0] for k in range(n)}
    return {'headers': narc('a/0/5/5'), 'parties': narc('a/0/5/6'), 'learnsets': narc('a/0/3/3'),
            'names': full_names([text for text, _ in decode_bank(narc('a/0/2/7')[TRAINER_NAMES])[1]]),
            'class_gender': arm9[CLASS_GENDER - 0x02000000:CLASS_GENDER - 0x02000000 + 256], 'handled_items': handled}


def full_names(names, workspace=WORKSPACE):
    """Bank 719's names with the build's full-name keys ('T00017' at id 17: trainer_display.key) replaced by the full
    names the build draws (trainer_display.plan of the translation workspace). Other names, the Spanish build's among
    them, stay as they are; a key without its full name in the workspace is an error, never a label."""
    if TOOLS not in sys.path:
        sys.path.append(TOOLS)              # after the test bench's own modules
    import trainer_display
    keyed = [i for i, n in enumerate(names) if i in trainer_display.IDS and n == trainer_display.key(i)]
    if not keyed:
        return names
    full = trainer_display.plan(workspace)
    missing = [i for i in keyed if i not in full]
    if missing:
        raise KeyError('trainer names %s are full-name keys, but %s has no full name for them'
                       % (', '.join(trainer_display.key(i) for i in missing), tbpaths.rel(str(workspace))))
    return [full[i] if i in keyed else n for i, n in enumerate(names)]


@functools.lru_cache(None)
def bank(n):
    """The frozen English strings of message bank 720 (trainer classes) or 33 (natures) (lib/names.json)."""
    with open(NAMES, encoding='utf-8') as f:
        return json.load(f)[{720: 'trainer_class', 33: 'nature'}[n]]


def trainer_name(t, tid):
    """'Class Name' of trainer tid as the ROM names it (rom_tables t): the English class (bank 720) and bank 719,
    '#tid' when both are empty."""
    return ('%s %s' % (bank(720)[t['headers'][tid][1]].replace('₧₦', 'PKMN'), t['names'][tid])).strip() or '#%d' % tid


def name(d, kind, i):
    """aidata's name for an id; the id itself when that name stands for another id in aidata."""
    n = getattr(d, NAME_TABLE[kind]).get(i)
    if n is None:
        raise KeyError('no English name for %s %d' % (kind, i))
    return n if d.id(kind, n) == i else i


def levelup_moves(learnset, level):
    """The last four moves learned by `level`, as CreateMon fills a Pokémon with no moves given."""
    moves = []
    for k in range(0, len(learnset) - 3, 4):
        lv, mv = struct.unpack_from('<HH', learnset, k)
        if lv == 0xFFFF or lv > level:
            break
        if mv not in moves:
            moves = (moves + [mv])[-4:]
    return moves


def party_pids(d, t, tid):
    """The PIDs the party builder gives a trainer's records (their natures when a record sets none). The
    bias is one variable for the whole party: a record's changes stay for the records after it."""
    cls = t['headers'][tid][1]
    bias = 0x78 if t['class_gender'][cls] == 1 else 0x88
    party, pids = t['parties'][tid], []
    for k in range(t['headers'][tid][3]):
        rec = party[28 * k:28 * k + 28]
        level, species = struct.unpack_from('<HH', rec, 6)
        gender, slot = rec[1] & 0xF, rec[1] >> 4
        if gender:
            bias = d.personal[species][0x10] + (2 if gender == 1 else -2)
        if slot == 1:
            bias &= ~1
        elif slot == 2:
            bias |= 1
        seed = r = (tid + species + rec[0] + level) & 0xFFFFFFFF
        for _ in range(cls):
            seed = (seed * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
            r = seed >> 16
        pids.append(((r << 8) + bias) & 0xFFFFFFFF)
    return pids


def record_spec(d, t, rec, pid):
    """(spec, None) for one party record and its PID, or (None, (reason, detail))."""
    ability, level, species, item = struct.unpack_from('<4H', rec, 4)
    moves = list(struct.unpack_from('<4H', rec, 12))
    if not species:
        return None, ('empty record', '')
    if rec[2]:
        return None, ('alternate form (build_mon writes no form)', '%s form %d' % (d.species_name.get(species), rec[2]))
    if not ability:
        return None, ('no ability in the record (the game picks one at random)', d.species_name.get(species))
    moves = [m for m in moves if m] if moves[0] else levelup_moves(t['learnsets'][species], level)
    nature = rec[3] if rec[3] != 0xFF else pid % 25
    try:
        spec = {'species': name(d, 'species', species), 'level': level, 'moves': [name(d, 'move', m) for m in moves],
                'ability': name(d, 'ability', ability), 'item': name(d, 'item', item) if item else None,
                'evs': dict(zip(STATS, rec[20:26])), 'nature': NATURES[nature], 'ivs': rec[0] * 31 // 255}
    except KeyError as e:
        return None, ('a name aidata does not have', e.args[0])
    return spec, None


def trainer_team(tid, rom):
    """(team, None) for one trainer whatever its party size, or (None, (reason, detail))."""
    d, t = data(rom), rom_tables(rom)
    party = t['parties'][tid]
    team = {'source': 'trainer', 'trainer': tid, 'name': trainer_name(t, tid), 'team': []}
    for k, pid in enumerate(party_pids(d, t, tid)):
        spec, why = record_spec(d, t, party[28 * k:28 * k + 28], pid)
        if why:
            return None, why
        team['team'].append(spec)
    return team, None


def scan(rom, size=6):
    """(teams, skipped) over every trainer with exactly `size` Pokémon; skipped: (id, name, reason, detail)."""
    t = rom_tables(rom)
    teams, skipped = [], []
    for tid, head in enumerate(t['headers']):
        if head[3] != size or tid in EXCLUDED_TRAINERS:
            continue
        team, why = trainer_team(tid, rom)
        if why:
            skipped.append((tid, trainer_name(t, tid)) + why)
        else:
            teams.append(team)
    return teams, skipped


def trainer_teams(rom, size=6):
    return scan(rom, size)[0]


def random_team(seed, size=6, level=100, rom=None):
    """aifuzz's random Pokémon (any move, randteams.ITEMS), redrawn while one knows Leaf Tornado or a move of
    randteams.PLAYER_NO. rom: whose data (default ADVAI_TEAMS_ROM, which versus/aivsai.py sets from --rom)."""
    d, rng = data(rom or os.environ['ADVAI_TEAMS_ROM']), random.Random(seed)
    banned = randteams.PLAYER_NO | {LEAF_TORNADO}
    team = []
    while len(team) < size:
        mon = randteams.random_team(d, rng, 1, level, False)[0]
        if not banned & set(mon['moves']):
            team.append(mon)
    return {'source': 'random', 'seed': seed, 'name': 'Random %d' % seed, 'team': team}


def show(n, d):
    return '%s (id %d)' % (d.item_name.get(n, '?'), n) if isinstance(n, int) else str(n)


def describe(team, d):
    head = '%s (#%d)' % (team['name'], team['trainer']) if team['source'] == 'trainer' else team['name']
    lines = [head + ('  (EVs HP/Atk/Def/Spe/SpA/SpD)' if team['source'] == 'trainer' else '')]
    for s in team['team']:
        evs = '/'.join(str(s['evs'][k]) for k in STATS) if s.get('evs') else '-'
        lines.append('  %-12s Lv%-3d %-13s @ %-16s %-8s IV %-2s EVs %-17s %s' % (
            s['species'], s['level'], s['ability'], show(s['item'], d) if s['item'] else '-', s.get('nature', '-'),
            s.get('ivs', '-'), evs, ', '.join(show(m, d) for m in s['moves'])))
    return '\n'.join(lines)


# --- checks
def docs_rows():
    """({trainer id: [docs table cells per Pokémon]}, {trainer id: its team heading's name})"""
    out, names, cur = {}, {}, None
    for line in open(DOCS, encoding='utf-8'):
        m = re.match(r'#### (.*) \(#(\d+)\)$', line.rstrip('\n'))
        if m:
            cur = out.setdefault(int(m.group(2)), [])
            names[int(m.group(2))] = m.group(1).strip()
        elif cur is not None and line.startswith('| ') and not line.startswith(('| Pokémon', '|---')):
            cur.append([c.strip() for c in line.strip().strip('|').split('|')])
        elif line.startswith('#'):
            cur = None
    return out, names


def docs_problems(team, rows, d, rec_moves):
    """Differences between a team and its docs table (EVs as the docs print them: the record's byte order)."""
    out = []
    if len(rows) != len(team['team']):
        return ['%d rows in the docs, %d Pokémon' % (len(rows), len(team['team']))]
    for k, (s, row) in enumerate(zip(team['team'], rows)):
        sp, lv, ab, it, nat, iv, mv = row
        evs = re.search(r'\(EVs ([\d/]+)\)', mv)
        moves = re.sub(r'\s*\(.*\)$', '', mv)
        want = {'species': norm(sp), 'level': int(lv), 'ability': norm(ab), 'item': norm(it) if it != '—' else None,
                'ivs': int(iv), 'evs': [int(x) for x in evs.group(1).split('/')] if evs else [0] * 6,
                'moves': 'level-up' if mv.startswith('(default') else [norm(x) for x in moves.split(', ')]}
        n = lambda x: norm(d.item_name[x] if isinstance(x, int) else x)
        got = {'species': n(s['species']), 'level': s['level'], 'ability': n(s['ability']),
               'item': n(s['item']) if s['item'] else None, 'ivs': s['ivs'], 'evs': [s['evs'][x] for x in STATS],
               'moves': [norm(d.move_name[x] if isinstance(x, int) else x) for x in s['moves']] if rec_moves[k] else 'level-up'}
        if nat != '—':      # '—': the record has none, the spec has the PID's
            want['nature'], got['nature'] = nat, s['nature']
        for f in want:
            if want[f] != got[f]:
                out.append('%s %s: docs %s, spec %s' % (s['species'], f, want[f], got[f]))
    return out


def decode(raw):
    """The fields a spec sets, from a 236-byte party Pokémon."""
    from savetool import Mon
    m = Mon(raw)
    A, B = m.blocks['A'], m.blocks['B']
    iv = struct.unpack_from('<I', B, 0x10)[0]
    override = struct.unpack_from('<I', B, 0x14)[0] >> 25 & 0x3F
    return {'species': struct.unpack_from('<H', A, 0)[0], 'item': struct.unpack_from('<H', A, 2)[0],
            'ability': struct.unpack_from('<H', B, 0x1A)[0], 'moves': [x for x in struct.unpack_from('<4H', B, 0) if x],
            'level': m.party[4], 'nature': override - 1 if override else m.pid % 25,
            'ivs': [iv >> 5 * k & 31 for k in range(6)], 'evs': list(A[0x10:0x16]),
            'stats': list(struct.unpack_from('<6H', m.party, 8))}


def expected(d, s):
    return {'species': d.id('species', s['species']), 'item': d.id('item', s['item']) if s['item'] else 0,
            'ability': d.id('ability', s['ability']), 'moves': [d.id('move', m) for m in s['moves']],
            'level': s['level'], 'nature': NATURES.index(s['nature']), 'ivs': [s['ivs']] * 6,
            'evs': [s['evs'][k] for k in STATS],
            'stats': list(d.stats(s['species'], s['level'], s['evs'], s['ivs'], s['nature']).values())}


def from_record(d, t, rec, pid, spec):
    """What the built Pokémon must hold, straight from the record's numbers (stats from the spec)."""
    ability, level, species, item = struct.unpack_from('<4H', rec, 4)
    moves = list(struct.unpack_from('<4H', rec, 12))
    return {'species': species, 'item': item, 'ability': ability, 'level': level,
            'moves': [m for m in moves if m] if moves[0] else levelup_moves(t['learnsets'][species], level),
            'nature': rec[3] if rec[3] != 0xFF else pid % 25,
            'ivs': [rec[0] * 31 // 255] * 6, 'evs': list(rec[20:26]), 'stats': expected(d, spec)['stats']}


def built(d, team, seed=1234):
    import aibench
    template = aibench.template_mon()
    return [aibench.build_mon(d, template, s, seed + 31 * i) for i, s in enumerate(team['team'])]


def check(rom):
    d, t = data(rom), rom_tables(rom)
    problems = []
    if bank(33) != NATURES:
        problems.append('aidata.NATURES is not bank 33')
    teams, _ = scan(rom)
    rows, headings = docs_rows() if DOCS and os.path.exists(DOCS) else (None, None)
    mons = 0
    for team in teams:
        tid = team['trainer']
        party = t['parties'][tid]
        cls = bank(720)[t['headers'][tid][1]].replace('₧₦', 'PKMN')
        if not team['name'].startswith(cls):
            problems.append('#%d: name %r, class %r' % (tid, team['name'], cls))
        rec_moves = [struct.unpack_from('<H', party, 28 * k + 12)[0] != 0 for k in range(6)]
        if rows is not None:
            if (headings.get(tid) or '#%d' % tid) != team['name']:      # the docs print a nameless trainer's heading empty
                problems.append('#%d: docs heading %r, ROM name %r' % (tid, headings.get(tid), team['name']))
            problems += ['#%d docs: %s' % (tid, p) for p in docs_problems(team, rows.get(tid, []), d, rec_moves)]
        for k, (s, raw, pid) in enumerate(zip(team['team'], built(d, team), party_pids(d, t, tid))):
            got, want = decode(raw), from_record(d, t, party[28 * k:28 * k + 28], pid, s)
            mons += 1
            problems += ['#%d build_mon: %s %s %s, record %s' % (tid, s['species'], f, got[f], want[f]) for f in want if got[f] != want[f]]
            if isinstance(s['item'], int) and s['item'] not in t['handled_items']:
                problems.append('#%d: %s holds item %d, which the battle engine does not handle' % (tid, s['species'], s['item']))
    banned = randteams.PLAYER_NO | {LEAF_TORNADO}
    for seed in range(20):
        team = random_team(seed, rom=rom)
        if team != random_team(seed, rom=rom) or len(team['team']) != 6 or banned & {m for s in team['team'] for m in s['moves']}:
            problems.append('%s: not the same twice, not six Pokémon or a banned move' % team['name'])
        for s, raw in zip(team['team'], built(d, team)):
            got, want = decode(raw), expected(d, dict(s, evs=dict.fromkeys(STATS, 0), nature='Hardy', ivs=31))
            del want['nature']      # no nature in the spec: build_mon picks one of the neutral five
            mons += 1
            problems += ['%s build_mon: %s %s %s, spec %s' % (team['name'], s['species'], f, got[f], want[f]) for f in want if got[f] != want[f]]
    if problems:
        print('\n'.join(problems))
    print('%d trainer teams checked %s; %d Pokémon (with 20 random teams) built and decoded: %d problem(s)' % (
        len(teams), 'against docs/trainers.md' if rows is not None else '(docs checks skipped: no ADVAI_TRAINERS_DOC)', mons,
        len(problems)))
    return not problems


def game_check(rom, ids):
    """Each trainer's party as the game builds it (the Violet Gym save; the foe's trainer id rewritten at
    EnemyTrainerSet_Init) against build_mon's Pokémon for the same specs. Differences in the HP IV and max
    HP are expected (the builder's HP IV by level), anything else is not."""
    import shutil

    import aibench
    import saves
    from emu import Runner
    out = os.path.join(tbpaths.RUNS, 'aiteams')
    os.makedirs(out, exist_ok=True)
    rom_copy = aibench.link_rom(rom, os.path.join(out, 'aiteams_game.nds'))
    dsv = os.path.join(aibench.DSV_DIR, 'aiteams_game.dsv')
    shutil.copy(saves.path('violet_gym'), dsv)
    d = data(rom)
    r = Runner(rom_copy, os.path.join(out, 'shots'))
    r.skip_render = True
    mem, reg, mu = r.emu.memory, r.emu.memory.register_arm9, r.emu.memory.unsigned
    cur = {'id': None, 'built': []}
    mem.register_exec(TRAINER_SET_INIT, lambda a, s: cur['id'] is not None and mem.write_long(reg.r0 + 0x1C, cur['id']))
    mem.register_exec(BUILT, lambda a, s: cur['built'].append(bytes(mu.read_byte(reg.r4 + k) for k in range(236))))
    r.run(open(os.path.join(tbpaths.LIB, 'boot.txt')).read().splitlines())
    state = os.path.join(out, 'field.dst')
    r.emu.savestate.save_file(state)
    bad = 0
    for tid in ids:
        team, why = trainer_team(tid, rom)
        if why:
            print('#%d: no spec (%s: %s)' % (tid, why[0], why[1]))
            continue
        r.emu.savestate.load_file(state)
        cur.update(id=tid, built=[])
        start = r.frames
        aibench.approach(r, start, lambda: len(cur['built']) >= len(team['team']))
        lines = []
        if len(cur['built']) != len(team['team']):
            lines.append('the game built %d Pokémon, the trainer has %d' % (len(cur['built']), len(team['team'])))
        for s, game, mine, pid in zip(team['team'], cur['built'], built(d, team), party_pids(d, rom_tables(rom), tid)):
            g, m = decode(game), decode(mine)
            if struct.unpack_from('<I', game, 0)[0] != pid:
                lines.append('  %s PID: game %08X, party_pids %08X' % (s['species'], struct.unpack_from('<I', game, 0)[0], pid))
                bad += 1
            for f in g:
                if f == 'ivs' and g[f][1:] == m[f][1:] or f == 'stats' and g[f][1:] == m[f][1:]:
                    if g[f][0] != m[f][0]:
                        lines.append('  (expected) %s %s: game %s, spec %s' % (s['species'], 'HP IV' if f == 'ivs' else 'max HP', g[f][0], m[f][0]))
                elif g[f] != m[f]:
                    lines.append('  %s %s: game %s, spec %s' % (s['species'], f, g[f], m[f]))
                    bad += 1
        print('#%d %s: %d Pokémon built by the game' % (tid, team['name'], len(cur['built'])))
        print('\n'.join(lines) or '  identical')
    for f in (rom_copy, dsv, state):
        os.remove(f)
    print('game check: %d difference(s) besides the HP IV' % bad)
    return not bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True)
    ap.add_argument('--trainer', type=int)
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--game', type=int, nargs='+')
    a = ap.parse_args()
    d = data(a.rom)
    if a.check:
        sys.exit(0 if check(a.rom) else 1)
    if a.game:
        sys.exit(0 if game_check(a.rom, a.game) else 1)
    if a.trainer is not None:
        team, why = trainer_team(a.trainer, a.rom)
        print(describe(team, d) if team else '#%d: skipped (%s: %s)' % (a.trainer, why[0], why[1]))
        return
    teams, skipped = scan(a.rom)
    print('trainers with six Pokémon: %d; usable teams: %d; skipped: %d' % (len(teams) + len(skipped), len(teams), len(skipped)))
    for reason, group in sorted(collections.Counter(s[2] for s in skipped).items()):
        ex = [s for s in skipped if s[2] == reason]
        print('  skipped, %s: %d (%s)' % (reason, group, ', '.join('#%d %s' % (s[0], s[3]) for s in ex)))
    specs = [s for team in teams for s in team['team']]
    t = rom_tables(a.rom)
    ids = collections.Counter(show(s['item'], d) for s in specs if isinstance(s['item'], int))
    print('items given as ids (aidata\'s name is another item): %s' % ', '.join('%s x%d' % kv for kv in sorted(ids.items())))
    pid_natures = sum(t['parties'][team['trainer']][28 * k + 3] == 0xFF for team in teams for k in range(6))
    levelup = sum(struct.unpack_from('<H', t['parties'][team['trainer']], 28 * k + 12)[0] == 0 for team in teams for k in range(6))
    print('natures from the PID (none in the record): %d Pokémon; level-up moves (none in the record): %d Pokémon' % (pid_natures, levelup))
    knows = lambda moves: [team for team in teams if any(moves & set(s['moves']) for s in team['team'])]
    print('teams with Leaf Tornado: %d; with a move of randteams.PLAYER_NO: %d (random teams have neither)' % (
        len(knows({LEAF_TORNADO})), len(knows(randteams.PLAYER_NO))))
    dup = sum(n - 1 for n in collections.Counter(team['name'] for team in teams).values() if n > 1)
    print('team names used by more than one team: %d extra teams share a name (tell them apart by the trainer id)' % dup)
    print()
    for team in (teams[0], teams[len(teams) // 2], teams[-1]):
        print(describe(team, d))
        print()


if __name__ == '__main__':
    main()
