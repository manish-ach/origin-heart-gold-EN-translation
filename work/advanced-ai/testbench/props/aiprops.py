"""Property tests for the advanced trainer AI: random singles turn-1 positions, the AI run on each, and invariants
that must always hold. Every violation comes with its position as a bench scenario and a command that reruns it.

  P=work/advanced-ai/testbench/props/aiprops.py
  .venv/bin/python $P --rom ROM --payload PAYLOAD [--n N] [--seed S] [--workers W] [--only INV,...] [--pos K,...]
                      [--det-every K] [--self-every K] [--mirror-tol P] [--hp-tol P]
  .venv/bin/python $P --repro RUNS/aiprops/reports/<rom>_<seed>.json#k [--rom ROM] [--payload P]   # rerun a violation
  .venv/bin/python $P --report RUNS/aiprops/reports/<rom>_<seed>.json [--rom ROM]   # check saved runs again, no emulator
  .venv/bin/python $P --selftest --rom ROM                                          # the invariants on made-up runs

Ported from the Spanish workspace's tools/aiprops.py (dc8577c). Changes: the AI-build addresses come from the payload
(through aibench and aivsai); the ROM is never changed (no speed toggle) and each worker opens a symlink of it; the AI
setting is written into the save in RAM after every state load (and into the battery save, as the Spanish tool did); aifuzz's item list comes from lib/randteams.py;
results go to RUNS/aiprops/reports/ (work files to RUNS/aiprops/), and a saved run records its ROM's path.

Positions (make_position): teams of 1-3 per side, sets from the ROM trainers' Pokémon (their moves, item, EVs, nature;
tools/aiteams.py) or random species and moves, one level per position (50-100), random HP fractions and statuses,
and in a quarter of them a weather from a lead's ability. Position k of seed S is always the same; each Pokémon is
built from its own seed, so it is the same bytes on either side. No trainer bag items (the player side has none).
The checked team is the position's trainer team ("my" side below); the player team is its opponent.

Runs (Prober: aibench's pre-battle state, both teams injected, the player's controller entries pointed at the AI's
routines as aivsai does, the self-play magic at 0x01FFFFFC set). In a solo run only one side uses the advanced AI and
the other side's polls go to overlay 11 (the slot word set to 11 around them, aivsai's adv mode), as in a real game;
in the self run both sides use it. The deciding side's first decision and its own debug record (every option with
its value) are read at the setter call. Per position, as --only needs them (about 2.9 s each on one emulator):
  A   the position, solo: the advanced AI on the trainer side          every invariant
  A2  A again (every --det-every-th position)                          determinism
  B   the teams swapped, solo: the advanced AI on the player side      mirror
  S   A with the advanced AI on both sides (every --self-every-th)     interference
  T   A with my lead's HP changed (even positions)                     hp
  P   A with the foe's lead's HP changed (odd positions)               hp
A side whose AI fell back to overlay 11's code (debug fallback code) or read another position than the one set up
(snapshot) is not checked; the summary counts both.

Invariants (each a function of the position and its runs; values of my team unless said):
  determinism   A and A2 give the same options, values and choice.
  mirror        my team valued on the trainer side (A) and on the player side (B, side 0's record) agrees within
                --mirror-tol points, and so does its choice. With both sides down to their actives, both falling the
                same turn is the trainer's win and the player's loss (advai.c outcome()): the player side may value
                such options lower by up to 2 * LAST_BONUS + worth(the foe's HP), a note, not a violation.
  interference  my team's values do not change when the other side's advanced AI decides in the same turn (S against
                A, within --mirror-tol): the two AIs' polls interleave frame by frame in one overlay.
  immunity      a damaging move into a type immunity (the ROM's chart) or an absorbing ability (Levitate, Volt Absorb,
                Lightningrod, Motor Drive, Storm Drain, Water Absorb, Dry Skin, Flash Fire, Well-Baked Body, Sap Sipper,
                Earth Eater, Wonder Guard) is never chosen and never valued above a damaging move that hits, unless the
                foe's likely switch-in (debug record) takes it. Its only move option, with no other move usable, is a
                stay (advai.c) and only noted.
  status        a move that cannot work (cannot_work: a major status on a statused target, powder on Grass, Electric
                status into an absorber, Endeavor with more HP...) is never chosen while a move that works is an option
                (chosen over switches only, it is a stay and only noted).
  hp            option values are changes from the current position (advai.c outcome()), so they are compared on an
                absolute scale, value + worth(my HP) + role - worth(foe's HP), role being what my active's roles are
                worth at its HP (debug version 5; advai.c role_loss is measured from the current HP). More HP for my active does not lower my best
                option by more than --hp-tol. More HP for the foe's active does not raise my best sure-KO move (the
                engine's damage at the lowest roll, debug d_mo) by more than --hp-tol plus DAMAGE_CREDIT times the HP
                fraction added (the credit for this turn's damage, which a fuller foe gives more of by design). Sides
                with HP-dependent moves, abilities or items (Rules.hp_*) are skipped.
Listed-but-harmless cases (a failing move valued below the rest, explained ones) are notes, not violations.
Types, abilities, items and moves come from the ROM (tools/aidata.py). Results: qa/aiprops/<rom>_<seed>.json
(positions, runs, violations, notes) and the summary beside it (.txt).
"""
import argparse
import copy
import json
import os
import random
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
import aibench  # noqa: E402
import aivsai  # noqa: E402
import payload  # noqa: E402
import randteams  # noqa: E402
from aidata import TYPES, Data, norm  # noqa: E402

OUT = os.path.join(tbpaths.RUNS, 'aiprops')
REPORTS = os.path.join(OUT, 'reports')
INVARIANTS = ('determinism', 'mirror', 'interference', 'immunity', 'status', 'hp')
# run: (teams swapped, the side the advanced AI decides for (None: both), whose lead's HP changes)
RUNS = {'A': (False, 1, None), 'A2': (False, 1, None), 'B': (True, 0, None), 'S': (False, None, None),
        'T': (False, 1, 'trainer'), 'P': (False, 1, 'player')}
MY_SIDE = {'A': 1, 'A2': 1, 'B': 0, 'S': 1, 'T': 1, 'P': 1}       # where the checked (trainer) team plays
FRAME_LIMIT = 6000          # both turn-1 decisions come within ~600 frames of the state (weather and Intimidate included)
WORTH_BASE = 250            # advai.c worth(): a Pokemon at 1 HP is worth 250 of 1000
DAMAGE_CREDIT = 90          # advai.c: a move's value gains this times the foe's max HP fraction it takes this turn
LAST_BONUS = 500            # advai.c: the KO that ends the battle
MIN_TRAINER_LEVEL = 50      # trainer sets from below this level are mostly level-up moves
MAX_SPECIES = 1025          # national dex; higher ids are alternate forms, which build_mon does not write
LEVELS = (50, 60, 70, 80, 90, 100)
STATUSES = ('par', 'brn', 'psn', 'tox', 'slp', 'frz')
STATUS_WEIGHTS = (3, 3, 2, 2, 3, 1)
NAME_STATUS = {0: None, 1: 'par', 2: 'slp', 3: 'frz', 4: 'brn', 5: 'psn'}    # debug record (BPP_GetPokeSick)
WEATHER_SETTERS = ('Drizzle', 'Drought', 'Sand Stream', 'Snow Warning')
W_SUN = 2                   # debug record weather
NONE_TYPE = 18
S_SLP = 2
Q_SICK, Q_RECOVER, Q_OHKO = 1, 3, 9      # move qualities (engine.h)
TARGET_USER = 7
FOE_TARGETS = (0, 3, 4, 5, 9)            # one foe, every foe, every other, a random foe (advai.c at_mon)
F_CHARGE, F_RECHARGE, F_MAGICCOAT, F_SOUND, F_POWDER = 1, 2, 4, 8, 28     # move flag bits (engine.h)


# --- names: the ROM's own (aidata), some truncated to its 12-character limit

def ids(d, kind, *names):
    """The ids of names the ROM has; each name may be 'Official|ROM spelling'. A name the ROM does not have in any
    spelling is an error, so a rule never goes silently empty."""
    out = set()
    for name in names:
        found = [d.names[kind][norm(n)] for n in name.split('|') if norm(n) in d.names[kind]]
        if not found:
            raise KeyError('%s %r is not in the ROM' % (kind, name))
        out.add(found[0])
    return out


def one(d, kind, name):
    return next(iter(ids(d, kind, name)))


class Rules:
    """Type, ability, item and move facts the invariants use, resolved once per ROM."""

    def __init__(self, d):
        T = self.T = {t: i for i, t in enumerate(TYPES)}
        ab = lambda *n: ids(d, 'ability', *n)  # noqa: E731
        mv = lambda *n: ids(d, 'move', *n)  # noqa: E731
        self.mold = ab('Mold Breaker', 'Teravolt', 'Turboblaze')
        self.scrappy = ab('Scrappy', "Mind's Eye")
        self.normalize = one(d, 'ability', 'Normalize')
        self.liquid_voice = one(d, 'ability', 'Liquid Voice')
        self.ate = {one(d, 'ability', n): T[t] for n, t in (('Refrigerate', 'Ice'), ('Pixilate', 'Fairy'),
                                                              ('Aerilate', 'Flying'), ('Galvanize', 'Electric'))}
        # the hack's own type-changing abilities: their exact rules are not measured, so their Normal moves are skipped
        self.hack_ate = ab('Burning Skin', 'Azure Skin', 'Grass Skin', 'Dark Skin', 'Dragonize')
        # official absorbing or immunity abilities and the move type each takes (Mold Breaker gets past them)
        self.absorb = {}
        for names, t in ((('Levitate', 'Earth Eater'), 'Ground'), (('Volt Absorb', 'Lightningrod', 'Motor Drive'), 'Electric'),
                         (('Water Absorb', 'Storm Drain', 'Dry Skin'), 'Water'), (('Flash Fire', 'Well-Baked Body|WellBakedBdy'), 'Fire'),
                         (('Sap Sipper',), 'Grass')):
            for a in ab(*names):
                self.absorb[a] = T[t]
        self.wonder_guard = one(d, 'ability', 'Wonder Guard')
        self.air_balloon = d.id('item', 'Air Balloon')        # aidata resolves the id the engine handles (576)
        self.iron_ball = d.id('item', 'Iron Ball')
        self.ring_target = d.id('item', 'Ring Target')
        self.thousand_arrows = one(d, 'move', 'Thousand Arrows|ThousndArrws')
        self.variable_type = mv('Weather Ball', 'Hidden Power', 'Judgment', 'Natural Gift', 'Techno Blast', 'Multi-Attack',
                                'Revelation Dance|RevelatnDnce', 'Terrain Pulse', 'Aura Wheel', 'Raging Bull', 'Ivy Cudgel',
                                'Tera Blast')
        # damaging moves that may fail or are worth less for a reason of their own: never counted as "a move that hits"
        self.conditional = mv('Dream Eater', 'Snore', 'Endeavor', 'Last Resort', 'Steel Roller', 'Poltergeist', 'Synchronoise',
                              'Burn Up', 'Double Shock', 'Belch', 'Spit Up', 'Fling', 'Sucker Punch', 'Thunderclap',
                              'Focus Punch', 'Counter', 'Mirror Coat', 'Metal Burst', 'Bide', 'Shell Trap', 'Future Sight',
                              'Doom Desire', 'Explosion', 'Selfdestruct', 'Misty Explosion|MistyExplosn', 'Final Gambit',
                              'Upper Hand') | self.variable_type
        # cannot_work's rules
        self.sleep_block = ab('Insomnia', 'Vital Spirit', 'Sweet Veil')
        self.par_block = ab('Limber')
        self.psn_block = ab('Immunity', 'Pastel Veil')
        self.brn_block = ab('Water Veil', 'Water Bubble', 'Thermal Exchange|ThermalExchg')
        self.frz_block = ab('Magma Armor')
        self.no_status = ab('Comatose', 'Purifying Salt|PurifyngSalt')
        self.leaf_guard = one(d, 'ability', 'Leaf Guard')
        self.corrosion = one(d, 'ability', 'Corrosion')
        self.overcoat = one(d, 'ability', 'Overcoat')
        self.good_as_gold = one(d, 'ability', 'Good as Gold')
        self.magic_bounce = one(d, 'ability', 'Magic Bounce')
        self.goggles = d.id('item', 'SafetyGoggls')
        self.electric_absorb = ab('Volt Absorb', 'Lightningrod', 'Motor Drive')
        self.endeavor = one(d, 'move', 'Endeavor')
        self.dream_eater = one(d, 'move', 'Dream Eater')
        self.snore_talk = mv('Snore', 'Sleep Talk')
        self.yawn = one(d, 'move', 'Yawn')
        self.leech_seed = one(d, 'move', 'Leech Seed')
        self.rest = one(d, 'move', 'Rest')
        self.substitute = one(d, 'move', 'Substitute')
        self.belly_drum = one(d, 'move', 'Belly Drum')
        self.first_move_needed = mv('Encore', 'Disable')
        self.field_setters = ab(*WEATHER_SETTERS, 'Desolate Land', 'Primordial Sea|PrimrdialSea', 'Delta Stream',
                                'Orichalcum Pulse|OrichlcmPlse', 'Electric Surge|Elec. Surge', 'Psychic Surge', 'Grassy Surge',
                                'Misty Surge', 'Hadron Engine')
        # what makes a side's values depend on HP other than through what it can take (inv_hp skips the side)
        self.hp_moves = mv('Endeavor', 'Flail', 'Reversal', 'Pain Split', 'Rest', 'Belly Drum', 'Substitute', 'Final Gambit',
                           'Eruption', 'Water Spout', 'Dragon Energy', 'Curse', 'Clangorous Soul|ClangrusSoul', 'Fillet Away',
                           'Mind Blown', 'Steel Beam', 'Chloroblast', 'Shed Tail', 'Wish', 'Healing Wish', 'Lunar Dance',
                           'Memento', 'Wring Out', 'Crush Grip', 'Hard Press', 'Super Fang', "Nature's Madness|NaturMadness",
                           'Ruination', 'Brine')
        self.hp_abilities = ab('Blaze', 'Torrent', 'Overgrow', 'Swarm', 'Berserk', 'Anger Shell', 'Emergency Exit|EmergncyExit',
                               'Wimp Out', 'Gluttony', 'Ripen', 'Defeatist', 'Multiscale', 'Shadow Shield', 'Sturdy')
        self.hp_items = {d.id('item', n) for n in ('Sitrus Berry', 'Oran Berry', 'Figy Berry', 'Wiki Berry', 'Mago Berry',
                                                   'Aguav Berry', 'Iapapa Berry', 'Salac Berry', 'Liechi Berry', 'Petaya Berry',
                                                   'Ganlon Berry', 'Apicot Berry', 'Lansat Berry', 'Starf Berry', 'Micle Berry',
                                                   'Custap Berry', 'Berry Juice', 'Focus Sash')}


# --- positions

def trainer_pool(rom):
    """The ROM trainers' Pokémon from level MIN_TRAINER_LEVEL up that build_mon can build (aiteams), each set once."""
    import aiteams
    seen, pool = set(), []
    for size in range(1, 7):
        for team in aiteams.scan(rom, size)[0]:
            for m in team['team']:
                key = (m['species'], tuple(m['moves']), m.get('item'), m['ability'])
                if m['level'] >= MIN_TRAINER_LEVEL and key not in seen:
                    seen.add(key)
                    pool.append(m)
    return pool


def random_moves(d):
    struggle = d.id('move', 'Struggle')
    return [m for m in sorted(d.move_name) if m < len(d.moves) and m != struggle and d.move_name[m].strip('-? ')]


def random_mon(d, rng, moves):
    """Any species of the national dex, any four moves, one of its abilities, an item of aifuzz's (lib/randteams)."""
    while True:
        sp = rng.randrange(1, MAX_SPECIES + 1)
        name = d.species_name.get(sp)
        if name and name.strip('-? ') and d.species(sp)['base']['hp']:
            break
    abilities = [a for a in d.species(sp)['abilities'] if a in d.ability_name]
    return {'species': name, 'moves': [d.move_name[m] for m in rng.sample(moves, 4)],
            'ability': d.ability_name[rng.choice(abilities)] if abilities else 'Run Away', 'item': rng.choice(randteams.ITEMS)}


def status_ok(d, species, status):
    """A status the species can have (no burned Fire types, poisoned Steel types...)."""
    types = {TYPES[t] for t in d.species(species)['types']}
    return not ((status in ('psn', 'tox') and types & {'Poison', 'Steel'}) or (status == 'brn' and 'Fire' in types) or
                (status == 'frz' and 'Ice' in types) or (status == 'par' and 'Electric' in types))


def other_hp(rng, h):
    """An HP fraction at least 0.15 away from h: full HP for a hurt lead 40% of the time."""
    while True:
        x = 1.0 if h < 1.0 and rng.random() < 0.4 else round(rng.uniform(0.05, 1.0), 2)
        if abs(x - h) >= 0.15:
            return x


def make_position(d, R, pool, moves, seed, index):
    """Position `index` of seed `seed`: {'id', 'trainer': [spec...], 'player': [spec...], ...}; specs as aibench's."""
    rng = random.Random('aiprops:%d:%d' % (seed, index))
    level = rng.choice(LEVELS)
    source = 'trainer' if rng.random() < 0.7 else 'random'
    used, teams = set(), []
    for _ in range(2):
        team = []
        for _ in range(rng.choice((1, 2, 3))):
            while True:
                m = copy.deepcopy(rng.choice(pool)) if source == 'trainer' else random_mon(d, rng, moves)
                if m['species'] not in used:     # names stay unambiguous: no species twice in a position
                    break
            used.add(m['species'])
            m['level'] = level
            m['hp'] = 1.0 if rng.random() < 0.55 else round(rng.uniform(0.05, 0.99), 2)
            if rng.random() < 0.2:
                st = rng.choices(STATUSES, STATUS_WEIGHTS)[0]
                if status_ok(d, m['species'], st):
                    m['status'] = st
                    if st == 'slp':
                        m['sleep'] = rng.randrange(1, 4)
            m['build_seed'] = rng.randrange(1 << 30)
            team.append(m)
        teams.append(team)
    weather = None
    if rng.random() < 0.25:
        weather = rng.choice(WEATHER_SETTERS)
        teams[rng.randrange(2)][0]['ability'] = weather
    leads = [t[0] for t in teams]
    if all(d.id('ability', m['ability']) in R.field_setters for m in leads):
        leads[1]['ability'] = 'Run Away'     # two field setters: the speed order (a tie is random) would decide
    return {'id': 'p%04d' % index, 'seed': seed, 'index': index, 'source': source, 'level': level, 'weather': weather,
            'battle_seed': rng.randrange(1 << 31), 'trainer': teams[0], 'player': teams[1],
            'hp_variant': {'T': other_hp(rng, teams[0][0]['hp']), 'P': other_hp(rng, teams[1][0]['hp'])}}


def runs_of(pos, only, det_every=1, self_every=1):
    """The runs a position needs for the invariants in `only` (RUNS)."""
    i = pos['index']
    want = {'A': True, 'A2': 'determinism' in only and i % det_every == 0, 'B': 'mirror' in only,
            'S': 'interference' in only and i % self_every == 0, 'T': 'hp' in only and i % 2 == 0, 'P': 'hp' in only and i % 2 == 1}
    return [r for r in RUNS if want[r]]


def run_teams(pos, run):
    """(trainer team, player team) of one run of a position."""
    t, p = copy.deepcopy(pos['trainer']), copy.deepcopy(pos['player'])
    swap, _, hp = RUNS[run]
    if hp:
        (t if hp == 'trainer' else p)[0]['hp'] = pos['hp_variant'][run]
    return (p, t) if swap else (t, p)


def scenario(pos, run='A'):
    """A run's position as an aibench scenario (tests/ai_scenarios.py format, no answer key)."""
    t, p = run_teams(pos, run)
    return {'id': '%s_%s' % (pos['id'], run), 'cat': 'props', 'desc': 'aiprops seed %d position %d run %s' % (
        pos['seed'], pos['index'], run), 'player': p, 'enemy': t, 'items': [], 'expect': {'best': [], 'ok': [], 'bad': []},
        'checks': [], 'double': False}


# --- runs

class Prober(aibench.Bench):
    """One emulator: injects a position from the bench's pre-battle state and reads the advanced AI's first decision
    on each side it decides for."""

    def __init__(self, rom, state):
        with aivsai.quiet():
            super().__init__(rom, state)
        self.side, self.solo, self.restore = None, None, False
        self.mem.register_exec(aivsai.AI_POLL, self._poll)
        self.mem.register_exec(aivsai.AI_POLL_RET, self._poll_ret)

    def _poll(self, a, s):
        if self.cur is None:
            return
        self.side = self.mu.read_byte(self.reg.r4 + aivsai.CLIENT_SIDE) & 1
        main = self.mu.read_long(aibench.MAIN_PTR)
        if self.solo is not None and self.side != self.solo and self.mu.read_long(main + aivsai.MAIN_SLOT) == aibench.AI_OVERLAY:
            self.mem.write_long(main + aivsai.MAIN_SLOT, 11)       # this call goes to the original AI's entry
            self.restore = True

    def _poll_ret(self, a, s):
        if self.restore:
            self.mem.write_long(self.mu.read_long(aibench.MAIN_PTR) + aivsai.MAIN_SLOT, aibench.AI_OVERLAY)
            self.restore = False

    def _inject(self, a, s):
        c = self.cur
        fresh = c is not None and 'setup' in c and not c.get('injected')
        super()._inject(a, s)
        if fresh:      # the player side's AI reads trainer[0]'s bag (BattleSetup + 0x2C): empty, like the trainer's
            for k in range(4):
                self.mem.write_short(c['setup'] + 0x2C + 2 * k, 0)

    def _setter(self, kind):
        def f(a, s):
            c = self.cur
            if c is None or kind == 'none' or not c.get('injected') or self.side is None or self.side in c['sides']:
                return
            lr = self.reg.r14
            by = 'advanced' if aivsai.ADV_CODE[0] <= lr < aivsai.ADV_CODE[1] else \
                'overlay 11 code' if aivsai.ORIG_CODE[0] <= lr < aivsai.ORIG_CODE[1] else None
            if by:
                ours = self.solo is None or self.side == self.solo
                c['sides'][self.side] = {'kind': kind, 'r1': self.reg.r1, 'r2': self.reg.r2, 'by': by if ours else 'overlay 11',
                                         'rec': compact(self.read_debug(self.side)) if ours and self.debug_addr else {}}
        return f

    def run(self, trainer, player, seed, solo):
        """trainer, player: built Pokémon; solo: the only side that uses the advanced AI (None: both).
        {'sides': {side: decision}, 'injected', 'failures', 'frames'}."""
        c = self.cur = {'mons': {'player': player, 'enemy': trainer}, 'items': [], 'seed': seed & 0xFFFFFFFF, 'calls': [],
                        'failures': [], 'notes': [], 'done': False, 'double': False, 'sides': {}}
        self.side, self.solo, self.restore = None, solo, False
        r = self.r
        start = r.frames
        with aivsai.quiet():
            aibench.to_battle(r, self.state)
        self.mem.write_long(aivsai.SELFPLAY_FLAG, aivsai.SELFPLAY_MAGIC)    # ITCM: every state load restores it
        self.mem.write_long(aibench.NOLEAD_FLAG, aibench.NOLEAD_MAGIC)      # the position's own leads (tools/ai/lead.c)
        self.mem.write_long(aibench.NOREAD_FLAG, aibench.NOREAD_MAGIC)      # blind decisions: mirror and interference compare sides
        for k in range(0, 2 * aivsai.REPLACED_SIZE, 4):
            self.mem.write_long(aivsai.REPLACED_AT + k, 0)
        patched = False
        while len(c['sides']) < 2 and r.frames - start < FRAME_LIMIT and not r.frozen:
            if not patched and self.mu.read_long(aivsai.SELECT) == aivsai.HUMAN_SELECT:
                self.mem.write_long(aivsai.SELECT, aivsai.AI_SELECT)       # the player's side chooses through an AI
                self.mem.write_long(aivsai.REPLACE, aivsai.AI_REPLACE)
                patched = True
            if (r.frames - start) % 40 == 0:      # A only advances the battle's intro text
                r.hold('A', 4, release=4)
            else:
                r.step(1)
        self.cur = None
        return {'injected': bool(c.get('injected')), 'sides': {str(k): v for k, v in c['sides'].items()},
                'failures': c['failures'], 'frames': r.frames - start}


def compact(rec):
    """The debug record without what no invariant reads."""
    if 'me' not in rec:
        return rec
    keep = ('polls', 'fallback', 'options', 'chosen', 'weather', 'nbench', 'trapped', 'legal', 'why', 'lost', 'strong',
            'sw_species', 'sw_w', 'd_mo', 'd_om', 'version', 'sim_unsure', 'role')
    out = {k: rec[k] for k in keep}
    for s in ('me', 'opp'):
        out[s] = {k: rec[s][k] for k in ('species', 'hp', 'maxhp', 'stats', 'types', 'level', 'status', 'ability', 'item', 'moves')}
    return out


def worker(rom, state, jobs_path, out_path):
    d = Data(rom)
    template = aibench.template_mon()
    prober = Prober(rom, state)
    results = []
    for job in json.load(open(jobs_path)):
        build = lambda team: [aibench.build_mon(d, template, m, m['build_seed']) for m in team]  # noqa: E731
        t0 = time.time()
        for attempt in range(3):        # the walk from the save state now and then misses the trainer
            res = prober.run(build(job['trainer']), build(job['player']), job['seed'], RUNS[job['run']][1])
            if res['injected']:
                break
        res.update(pos=job['pos'], run=job['run'], attempts=attempt + 1, seconds=round(time.time() - t0, 1))
        results.append(res)
        with open(out_path, 'w') as f:
            json.dump(results, f)


def prepare(rom, tag):
    """ROM link and a battery save with fast text (aivsai.prepare without its shared files); the advanced AI on through
    the AI setting every state load writes. The pre-battle state is kept per ROM build (its SHA-1), so later runs on
    the same build skip making it."""
    import hashlib
    os.makedirs(OUT, exist_ok=True)
    save = aibench.setting_save('all', os.path.join(OUT, tag + '.dsv'), options=True)
    h = hashlib.sha1()
    with open(rom, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    rom_copy = aibench.link_rom(rom, os.path.join(OUT, tag + '.nds'))
    state = os.path.join(OUT, 'state_%s.dst' % h.hexdigest()[:16])
    shutil.copy(save, os.path.join(aibench.DSV_DIR, tag + '.dsv'))
    return rom_copy, state, save


def run_jobs(chunks, rom_copy, state, save, tag):
    """Each chunk of jobs on its own emulator process (its own ROM copy and battery save)."""
    def go(k):
        rom_k, dsv_k = os.path.join(OUT, '%s_%d.nds' % (tag, k)), os.path.join(aibench.DSV_DIR, '%s_%d.dsv' % (tag, k))
        aibench.link_rom(rom_copy, rom_k)
        shutil.copy(save, dsv_k)
        jp, op = os.path.join(OUT, 'jobs_%s_%d.json' % (tag, k)), os.path.join(OUT, 'res_%s_%d.json' % (tag, k))
        with open(jp, 'w') as f:
            json.dump(chunks[k], f)
        if os.path.exists(op):
            os.remove(op)
        subprocess.run([sys.executable, __file__, '--worker', rom_k, state, jp, op],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        out = json.load(open(op)) if os.path.exists(op) else []
        for p in (rom_k, dsv_k, jp, op):
            if os.path.lexists(p):
                os.remove(p)
        return out
    with ThreadPoolExecutor(len(chunks)) as pool:
        return [x for part in pool.map(go, range(len(chunks))) for x in part]


def execute(rom, positions, workers, tag):
    """Every run in each position's 'runs'; {(pos id, run): result}. A position's runs stay on one emulator."""
    rom_copy, state, save = prepare(rom, tag)
    jobs = lambda pos: [{'pos': pos['id'], 'run': r, 'seed': pos['battle_seed'],  # noqa: E731
                         **dict(zip(('trainer', 'player'), run_teams(pos, r)))} for r in pos['runs']]
    for attempt in range(3):            # the state must reach the battle before anything is run from it
        if attempt or not os.path.exists(state):
            subprocess.run([sys.executable, aibench.__file__, '--make-state', rom_copy, state],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        probe = run_jobs([jobs(positions[0])[:1]], rom_copy, state, save, tag + '_probe')
        if probe and probe[0]['injected']:
            break
    else:
        sys.exit('the save state never reaches the trainer battle (see %s/no_battle_*.png)' % tbpaths.rel(os.path.join(aibench.OUT, 'shots')))
    chunks = [[j for pos in positions[k::workers] for j in jobs(pos)] for k in range(workers) if positions[k::workers]]
    results = run_jobs(chunks, rom_copy, state, save, tag)
    for p in (rom_copy, save, os.path.join(aibench.DSV_DIR, tag + '.dsv')):
        if os.path.lexists(p):
            os.remove(p)
    return {(x['pos'], x['run']): x for x in results}


# --- reading a run

def worth(hp, maxhp):
    return 0 if hp <= 0 else WORTH_BASE + (1000 - WORTH_BASE) * hp // max(1, maxhp)


def view(d, pos, runs, run, side=None):
    """The advanced AI's turn-1 decision for a side of a run (default: my team's side): {'options': {name: value},
    'order': [names], 'choice', 'rec', 'team', 'foe'}, or {'skip': why}."""
    res = runs.get(run)
    side = MY_SIDE[run] if side is None else side
    if res is None or not res.get('injected'):
        return {'skip': 'no battle' if res else 'not run'}
    s = res['sides'].get(str(side))
    if not s:
        return {'skip': 'no decision'}
    rec = s['rec']
    swap = RUNS[run][0]
    team, foe = (pos['player'], pos['trainer']) if (side == 1) == swap else (pos['trainer'], pos['player'])
    if s['by'] != 'advanced' or rec.get('fallback') or 'options' not in rec:
        return {'skip': 'fallback %s' % (rec.get('fallback') or s['by'])}
    t, p = run_teams(pos, run)
    me, them = (t[0], p[0]) if side == 1 else (p[0], t[0])
    problems = snapshot(d, rec, me, them)
    if problems:
        return {'skip': 'snapshot: ' + '; '.join(problems)}
    names, order = {}, []
    for kind, idx, extra, value in rec['options']:
        if kind == 0:
            mid = rec['me']['moves'][idx] if idx < 4 else 0
            name = d.move_name.get(mid, 'move %d' % mid)
        elif kind == 1:
            name = 'switch:' + (team[extra]['species'] if extra < len(team) else '?%d' % extra)
        else:
            name = 'item:' + d.item_name.get(extra, str(extra))
        names[name] = value
        order.append(name)
    if s['kind'] == 'move':
        choice = d.move_name.get(s['r1'], str(s['r1']))
    elif s['kind'] == 'switch':
        choice = 'switch:' + (team[s['r2']]['species'] if s['r2'] < len(team) else '?%d' % s['r2'])
    else:
        choice = 'item:' + d.item_name.get(s['r1'], str(s['r1']))
    return {'options': names, 'order': order, 'choice': choice, 'rec': rec, 'team': team, 'foe': foe}


def snapshot(d, rec, me, foe):
    """What the AI read of both actives against what the run set up: species, max HP, stats, moves (not HP: a Sitrus
    Berry below half HP is eaten on entry, before turn 1)."""
    out = []
    for key, spec in (('me', me), ('opp', foe)):
        got, v = rec[key], aibench.mon_view(d, spec)
        want = {'species': d.id('species', spec['species']), 'maxhp': v['stats']['hp'],
                'stats': [v['stats'][k] for k in ('atk', 'def', 'spa', 'spd', 'spe')],
                'moves': [d.id('move', m) for m in spec['moves']] + [0] * (4 - len(spec['moves']))}
        out += ['%s.%s read %s, set %s' % (key, k, got[k], w) for k, w in want.items() if got[k] != w]
    return out


def violation(inv, pos, run, reason, **values):
    return {'invariant': inv, 'pos': pos['id'], 'run': run, 'reason': reason, 'values': values}


def same_values(inv, pos, a, b, run, what, tol):
    """Two views of my team in one position: a violation when options, values (beyond tol) or the choice differ."""
    names = set(a['options']) | set(b['options'])
    missing = sorted(k for k in names if (k in a['options']) != (k in b['options']))
    gaps = {k: [a['options'][k], b['options'][k]] for k in names - set(missing) if abs(a['options'][k] - b['options'][k]) > tol}
    if not (missing or gaps or a['choice'] != b['choice']):
        return []
    worst = max([abs(x - y) for x, y in gaps.values()] or [0])
    parts = ['options only in one run: %s' % ', '.join(missing) if missing else '',
             'up to %d points apart (%s)' % (worst, ', '.join('%s %d/%d' % (k, x, y) for k, (x, y) in sorted(gaps.items())))
             if gaps else '', 'choice %s vs %s' % (a['choice'], b['choice']) if a['choice'] != b['choice'] else '']
    return [violation(inv, pos, run, '%s: %s' % (what, '; '.join(p for p in parts if p)), worst_gap=worst,
                      choice=[a['choice'], b['choice']], A=a['options'], other=b['options'],
                      sw=[a['rec']['sw_species'], a['rec']['sw_w'], b['rec']['sw_species'], b['rec']['sw_w']])]


# --- invariants: each (rules, data, position, {run: result}, options) -> (checked, [violation], [note])

def inv_determinism(R, d, pos, runs, opts):
    a, b = view(d, pos, runs, 'A'), view(d, pos, runs, 'A2')
    if 'skip' in a or 'skip' in b:
        both = 'skip' in a and 'skip' in b
        return (0, [] if both or 'not run' in (a.get('skip'), b.get('skip')) else
                [violation('determinism', pos, 'A2', 'one run fell back or misread, the other did not',
                           A=a.get('skip', 'ok'), A2=b.get('skip', 'ok'))], [])
    return 1, same_values('determinism', pos, a, b, 'A2', 'the same position decided twice', 0), []


def dko_room(v):
    """advai.c outcome(): with both sides down to their actives, both falling the same turn is the trainer's win and the
    player's loss, so the player side values such a line lower by 2 * LAST_BONUS + worth(the foe's HP now), times the
    line's odds. 0 when either side has another Pokémon (the term never applies)."""
    rec = v['rec']
    if rec['nbench'] or len(v['foe']) > 1:
        return 0
    return 2 * LAST_BONUS + worth(rec['opp']['hp'], rec['opp']['maxhp'])


def inv_mirror(R, d, pos, runs, opts):
    a, b = view(d, pos, runs, 'A'), view(d, pos, runs, 'B')
    if 'skip' in a or 'skip' in b:
        return 0, [], []
    room, tol = dko_room(a), opts.mirror_tol
    dko = sorted(k for k in set(a['options']) & set(b['options'])
                 if room and tol < a['options'][k] - b['options'][k] <= room + tol)
    if not dko:
        return 1, same_values('mirror', pos, a, b, 'B', 'trainer side (A) vs player side (B)', tol), []
    note = violation('mirror', pos, 'B', 'double-KO rule (advai.c outcome): the player side values %s lower, by at most %d'
                     % (', '.join(dko), room), A=a['options'], other=b['options'], choice=[a['choice'], b['choice']])
    drop = lambda v: dict(v, options={k: x for k, x in v['options'].items() if k not in dko})  # noqa: E731
    a2, b2 = drop(a), drop(b)
    if a['choice'] in dko:      # the trainer side took a double KO, its win; the player side's loss
        b2['choice'] = a['choice']
    return 1, same_values('mirror', pos, a2, b2, 'B', 'trainer side (A) vs player side (B), double-KO lines aside', tol), [note]


def inv_interference(R, d, pos, runs, opts):
    a, b = view(d, pos, runs, 'A'), view(d, pos, runs, 'S')
    if 'skip' in a or 'skip' in b:
        return 0, [], []
    return 1, same_values('interference', pos, a, b, 'S', 'alone (A) vs with the advanced AI on the other side too (S)',
                          opts.mirror_tol), []


def move_slot(d, v, name):
    """(slot, move data) of a move option of my active Pokémon."""
    mid = d.id('move', name)
    return v['rec']['me']['moves'].index(mid), d.move(mid)


def immune_reason(R, d, mid, me, opp):
    """Why move `mid` of my active (debug record side) cannot touch the foe's active, or None: it can, or its type is
    not known from the data alone."""
    m = d.move(mid)
    if not m['class'] or mid in R.variable_type:
        return None
    T, t, ab = R.T, m['type'], me['ability']
    if ab == R.normalize:
        t = T['Normal']
    elif ab in R.ate and t == T['Normal']:
        t = R.ate[ab]
    elif ab in R.hack_ate and t == T['Normal']:
        return None
    elif ab == R.liquid_voice and m['flags'] >> F_SOUND & 1:
        t = T['Water']
    types, item = [x for x in opp['types'] if x < NONE_TYPE], opp['item']
    grounded = item == R.iron_ball or mid == R.thousand_arrows
    if item != R.ring_target:
        hit = [x for x in types if not (t == T['Ground'] and grounded and x == T['Flying']) and
               not (t in (T['Normal'], T['Fighting']) and ab in R.scrappy and x == T['Ghost'])]
        if d.type_mult(t, hit) == 0:
            return '%s (%s) into %s: type immunity' % (d.move_name[mid], TYPES[t], '/'.join(TYPES[x] for x in types))
    if t == T['Ground'] and item == R.air_balloon and mid != R.thousand_arrows:
        return '%s into an Air Balloon' % d.move_name[mid]
    if ab in R.mold:
        return None
    oab = opp['ability']
    if R.absorb.get(oab) == t and not (t == T['Ground'] and grounded):
        return '%s (%s) into %s' % (d.move_name[mid], TYPES[t], d.ability_name.get(oab, oab))
    if oab == R.wonder_guard and d.type_mult(t, types) <= 1:
        return '%s into Wonder Guard (not super effective)' % d.move_name[mid]
    return None


def hits(R, d, mid, me, opp):
    """A damaging move that connects and has no condition or cost of its own (charge, recharge, OHKO, self-KO...)."""
    m = d.move(mid)
    return bool(m['class']) and mid not in R.conditional and not m['flags'] >> F_CHARGE & 1 and \
        not m['flags'] >> F_RECHARGE & 1 and m['quality'] != Q_OHKO and immune_reason(R, d, mid, me, opp) is None


def takes_switch_in(R, d, v, mid):
    """The record's likely foe switch-in (with its weight) is hit by the move: the stated reason it keeps a value."""
    rec = v['rec']
    if not rec.get('sw_w'):
        return None
    spec = next((m for m in v['foe'] if d.id('species', m['species']) == rec['sw_species']), None)
    switch_in = {'types': d.species(rec['sw_species'])['types'] + [NONE_TYPE],
                 'ability': d.id('ability', spec['ability']) if spec else 0,
                 'item': d.id('item', spec['item']) if spec and spec.get('item') else 0}
    if immune_reason(R, d, mid, rec['me'], switch_in) is None:
        return 'the foe\'s likely switch-in %s (weight %d per-mille) takes it' % (d.species_name.get(rec['sw_species']), rec['sw_w'])
    return None


def inv_immunity(R, d, pos, runs, opts):
    v = view(d, pos, runs, 'A')
    if 'skip' in v:
        return 0, [], []
    bad, notes = [], []
    me, opp = v['rec']['me'], v['rec']['opp']
    moves = [m for m in me['moves'] if m]
    movenames = {d.move_name.get(m) for m in moves}
    usable = [d.move_name[m] for m in moves if hits(R, d, m, me, opp) or
              (not d.move(m)['class'] and cannot_work(R, d, m, me, opp, v['rec']['weather']) is None)]
    listed = [n for n in v['order'] if n in movenames]
    hitting = {n: v['options'][n] for n in listed if hits(R, d, d.id('move', n), me, opp)}
    for name in listed:
        why = immune_reason(R, d, d.id('move', name), me, opp)
        if not why:
            continue
        value, chosen = v['options'][name], v['choice'] == name
        below = {n: x for n, x in hitting.items() if x < value}
        stated = takes_switch_in(R, d, v, d.id('move', name))
        facts = dict(move=name, value=value, chosen=chosen, options=v['options'], choice=v['choice'],
                     sw_species=d.species_name.get(v['rec'].get('sw_species')), sw_w=v['rec'].get('sw_w'))
        if not chosen and not below:
            notes.append(violation('immunity', pos, 'A', 'listed, not vetoed (below every move that hits): ' + why, **facts))
        elif stated:
            notes.append(violation('immunity', pos, 'A', why + '; explained: ' + stated, **facts))
        elif chosen and len(listed) == 1 and not [u for u in usable if u != name]:
            notes.append(violation('immunity', pos, 'A', why + '; a stay: no other move of it works', **facts))
        else:
            bad.append(violation('immunity', pos, 'A', why + ('; chosen' if chosen else '') +
                                 ('; valued %d, above %s' % (value, ', '.join('%s %d' % kv for kv in sorted(below.items())))
                                  if below else ' (value %d)' % value), below=below, **facts))
    return 1, bad, notes


def cannot_work(R, d, mid, me, opp, weather=0):
    """Why move `mid` of my active (debug record side) fails against the foe's active on turn 1, or None. The rules,
    each official unless marked measured:
      a major status (paralysis, sleep, freeze, burn, poison) on a target that has one;
      Electric-type status into the type chart's immunity (Thunder Wave into Ground) or an absorbing ability;
      poison into Poison or Steel (not from Corrosion), burn into Fire, freeze into Ice;
      the status blocked by the target's ability (Insomnia, Limber, Immunity, Water Veil, Magma Armor, Comatose,
      Leaf Guard in sun...), Mold Breaker excepted;
      powder or spore into a Grass type (measured: Spore), Overcoat or Safety Goggles;
      a status move into Good as Gold, or into Magic Bounce (bounced back);
      Yawn into a statused target; Leech Seed into a Grass type (measured);
      Endeavor with as much HP as the target or more; Dream Eater on an awake target; Snore or Sleep Talk awake;
      Encore or Disable before the target has moved (turn 1);
      a recovery move or Rest at full HP; Substitute at 1/4 HP or less; Belly Drum at half HP or less.
    Hazards at their most layers cannot happen on turn 1."""
    m, T, mold = d.move(mid), R.T, me['ability'] in R.mold
    oab, ost, types = opp['ability'], opp['status'], [x for x in opp['types'] if x < NONE_TYPE]
    name = d.move_name.get(mid, str(mid))
    if mid == R.endeavor and me['hp'] >= opp['hp']:
        return 'Endeavor with %d HP against %d' % (me['hp'], opp['hp'])
    if mid == R.dream_eater and ost != S_SLP:
        return 'Dream Eater on an awake target'
    if mid in R.snore_talk and me['status'] != S_SLP:
        return '%s while awake' % name
    if m['class']:
        return None
    if m['target'] == TARGET_USER:
        if (m['quality'] == Q_RECOVER or mid == R.rest) and me['hp'] >= me['maxhp']:
            return '%s at full HP' % name
        if mid == R.substitute and me['hp'] * 4 <= me['maxhp']:
            return 'Substitute at 1/4 HP or less'
        if mid == R.belly_drum and me['hp'] * 2 <= me['maxhp']:
            return 'Belly Drum at half HP or less'
        return None
    if m['target'] not in FOE_TARGETS:
        return None
    if mid in R.first_move_needed:
        return '%s before the target has moved' % name
    powder = m['flags'] >> F_POWDER & 1
    if powder and T['Grass'] in types:
        return '%s (powder) into a Grass type (measured)' % name
    if powder and (opp['item'] == R.goggles or (oab == R.overcoat and not mold)):
        return '%s (powder) into Overcoat or Safety Goggles' % name
    if not mold and oab == R.good_as_gold:
        return '%s into Good as Gold' % name
    if not mold and oab == R.magic_bounce and m['flags'] >> F_MAGICCOAT & 1:
        return '%s into Magic Bounce (bounced back)' % name
    if m['type'] == T['Electric'] and not mold and oab in R.electric_absorb:
        return '%s (Electric) into %s' % (name, d.ability_name.get(oab))
    if mid == R.yawn and ost:
        return 'Yawn into a statused target'
    if mid == R.leech_seed and T['Grass'] in types:
        return 'Leech Seed into a Grass type (measured)'
    st = m['status']
    if m['quality'] != Q_SICK or not 1 <= st <= 5:
        return None
    sname = NAME_STATUS[st]
    if ost:
        return '%s (%s) into a target that is %s' % (name, sname, NAME_STATUS.get(ost, ost))
    if m['type'] == T['Electric'] and d.type_mult(m['type'], types) == 0:
        return '%s (Electric) into %s: type immunity' % (name, '/'.join(TYPES[x] for x in types))
    if sname == 'psn' and (T['Poison'] in types or T['Steel'] in types) and me['ability'] != R.corrosion:
        return '%s (poison) into a Poison or Steel type' % name
    if sname == 'brn' and T['Fire'] in types:
        return '%s (burn) into a Fire type' % name
    if sname == 'frz' and T['Ice'] in types:
        return '%s (freeze) into an Ice type' % name
    if not mold:
        block = {'slp': R.sleep_block, 'par': R.par_block, 'psn': R.psn_block, 'brn': R.brn_block, 'frz': R.frz_block}[sname]
        if oab in block or oab in R.no_status or (oab == R.leaf_guard and weather == W_SUN):
            return '%s (%s) into %s' % (name, sname, d.ability_name.get(oab))
    return None


def inv_status(R, d, pos, runs, opts):
    v = view(d, pos, runs, 'A')
    if 'skip' in v:
        return 0, [], []
    bad, notes = [], []
    me, opp = v['rec']['me'], v['rec']['opp']
    movenames = {d.move_name.get(m) for m in me['moves'] if m}
    failing = {n: cannot_work(R, d, d.id('move', n), me, opp, v['rec']['weather']) for n in v['order'] if n in movenames}
    failing = {n: why for n, why in failing.items() if why}
    for name, why in failing.items():
        facts = dict(move=name, value=v['options'][name], options=v['options'], choice=v['choice'])
        working = [n for n in v['order'] if n in movenames and n not in failing and immune_reason(R, d, d.id('move', n), me, opp) is None]
        if v['choice'] != name:
            notes.append(violation('status', pos, 'A', 'listed, not vetoed: ' + why, **facts))
        elif working:
            bad.append(violation('status', pos, 'A', 'chose %s: %s; %s work' % (name, why, ', '.join(working)), working=working, **facts))
        elif len(v['order']) > 1:
            notes.append(violation('status', pos, 'A', 'chose %s: %s; a stay, only switches were left' % (name, why), **facts))
    return 1, bad, notes


def hp_exempt(R, d, rec_side):
    """What makes this Pokémon's values depend on its HP beyond what it can take, or None."""
    hit = [d.move_name[m] for m in rec_side['moves'] if m in R.hp_moves or (m and d.move(m)['quality'] == Q_RECOVER)]
    if hit:
        return 'moves ' + ', '.join(hit)
    if rec_side['ability'] in R.hp_abilities:
        return 'ability ' + d.ability_name.get(rec_side['ability'], '?')
    if rec_side['item'] in R.hp_items:
        return 'item ' + d.item_name.get(rec_side['item'], '?')
    return None


def absolute(v, name):
    """An option's value on the absolute scale: plus my active's worth and what its roles are worth at its HP (advai.c
    role_loss is measured from the current HP; debug version 5), minus the foe's worth."""
    me, opp = v['rec']['me'], v['rec']['opp']
    return v['options'][name] + worth(me['hp'], me['maxhp']) + v['rec'].get('role', 0) - worth(opp['hp'], opp['maxhp'])


def inv_hp(R, d, pos, runs, opts):
    run = 'T' if runs.get('T') else 'P'
    a, b = view(d, pos, runs, 'A'), view(d, pos, runs, run)
    if 'skip' in a or 'skip' in b:
        return 0, [], []
    key = 'me' if run == 'T' else 'opp'
    if a['rec'][key]['hp'] == b['rec'][key]['hp']:
        return 0, [], []
    lo, hi = (a, b) if a['rec'][key]['hp'] < b['rec'][key]['hp'] else (b, a)
    runs_ = dict(lo_run='A' if lo is a else run, hi_run=run if lo is a else 'A')
    l_, h_ = lo['rec'][key], hi['rec'][key]
    frac = '%d/%d -> %d/%d HP' % (l_['hp'], l_['maxhp'], h_['hp'], h_['maxhp'])
    if key == 'me':
        if hp_exempt(R, d, a['rec']['me']) or hp_exempt(R, d, a['rec']['opp']):
            return 0, [], []
        best = lambda v: max(v['options'], key=lambda n: absolute(v, n))  # noqa: E731
        bl, bh = best(lo), best(hi)
        al, ah = absolute(lo, bl), absolute(hi, bh)
        if ah < al - opts.hp_tol:
            return 1, [violation('hp', pos, run, 'my active %s: best option %s %d (absolute) fell to %s %d' % (frac, bl, al, bh, ah),
                                 lo_options=lo['options'], hi_options=hi['options'], lo_best=[bl, lo['options'][bl], al],
                                 hi_best=[bh, hi['options'][bh], ah], **runs_)], []
        return 1, [], []
    # the foe's HP: my best move that knocks it out at its lower HP on the lowest roll (engine damage, d_mo)
    if hp_exempt(R, d, a['rec']['opp']):
        return 0, [], []
    rec, ko = lo['rec'], []
    for name in lo['order']:
        if name not in hi['options'] or name.startswith(('switch:', 'item:')):
            continue
        slot, m = move_slot(d, lo, name)
        if m['id'] in R.hp_moves or not m['class'] or immune_reason(R, d, m['id'], rec['me'], rec['opp']):
            continue
        if rec['d_mo'][slot] > 1 and rec['d_mo'][slot] * m['hits'][0] * 85 // 100 >= rec['opp']['hp']:
            ko.append(name)
    if not ko:
        return 0, [], []
    name = max(ko, key=lambda n: lo['options'][n])
    al, ah = absolute(lo, name), absolute(hi, name)
    allowed = opts.hp_tol + DAMAGE_CREDIT * (h_['hp'] - l_['hp']) // max(1, h_['maxhp'])
    if ah > al + allowed:
        return 1, [violation('hp', pos, run, 'foe %s: my sure-KO %s rose from %d to %d (absolute; %d allowed)' % (
            frac, name, al, ah, allowed), move=name, lo_value=lo['options'][name], hi_value=hi['options'][name], lo_abs=al,
            hi_abs=ah, lo_options=lo['options'], hi_options=hi['options'], **runs_)], []
    return 1, [], []


CHECKS = {'determinism': inv_determinism, 'mirror': inv_mirror, 'interference': inv_interference, 'immunity': inv_immunity,
          'status': inv_status, 'hp': inv_hp}


def evaluate(R, d, positions, results, only, opts):
    """{invariant: {'checked', 'violations', 'notes'}} and the sides not checked, by reason."""
    out = {inv: {'checked': 0, 'violations': [], 'notes': []} for inv in only}
    skipped = {}
    for pos in positions:
        runs = {r: results.get((pos['id'], r)) for r in RUNS}
        for r in pos['runs']:
            for side in ((0, 1) if RUNS[r][1] is None else (RUNS[r][1],)):
                v = view(d, pos, runs, r, side)
                if 'skip' in v:
                    skipped.setdefault(v['skip'].split(':')[0], []).append('%s %s side %d: %s' % (pos['id'], r, side, v['skip']))
        for inv in only:
            n, bad, notes = CHECKS[inv](R, d, pos, runs, opts)
            out[inv]['checked'] += n
            out[inv]['violations'] += bad
            out[inv]['notes'] += notes
    for k, v in enumerate(v for f in out.values() for v in f['violations']):
        v['k'] = k              # the number --repro FILE#k takes
    return out, skipped


# --- report

def repro_cmd(path, k):
    return '.venv/bin/python %s --repro %s#%d' % (tbpaths.rel(os.path.abspath(__file__)), tbpaths.rel(path), k)


def summary(meta, positions, results, found, skipped, path):
    lines = ['aiprops on %s: seed %d, %d positions, %d runs, %d workers, %.0f s (%.1f s per position, %.1f s per run on one emulator)' % (
        meta['rom'], meta['seed'], len(positions), len(results), meta['workers'], meta['seconds'],
        meta['seconds'] / max(1, len(positions)), sum(r['seconds'] for r in results.values()) / max(1, len(results)))]
    fails = [(k, r['failures']) for k, r in sorted(results.items()) if r.get('failures')]
    if fails:
        lines.append('emulator failures in %d runs, e.g. %s' % (len(fails), fails[:3]))
    lines.append('sides not checked: ' + (', '.join('%s %d' % (k, len(v)) for k, v in sorted(skipped.items())) or 'none'))
    for inv, f in found.items():
        lines.append('')
        lines.append('%-12s %4d checked, %3d violations, %3d notes' % (inv, f['checked'], len(f['violations']), len(f['notes'])))
        for v in f['violations'][:3]:
            lines.append('  #%d %s (%s): %s' % (v['k'], v['pos'], v['run'], v['reason']))
            lines.append('     ' + repro_cmd(path, v['k']))
        for n in f['notes'][:2]:
            lines.append('  note %s: %s' % (n['pos'], n['reason']))
    return '\n'.join(lines)


def save(path, meta, positions, results, found, skipped, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    saved = {'meta': meta, 'summary': text, 'invariants': found, 'skipped': skipped,
             'positions': positions, 'runs': [results[k] for k in sorted(results)]}
    with open(path, 'w') as f:
        json.dump(saved, f, indent=1)
    with open(os.path.splitext(path)[0] + '.txt', 'w') as f:
        f.write(text + '\n')


def tag_of(rom):
    return 'aiprops_' + os.path.splitext(os.path.basename(rom))[0]


def report(path, opts):
    """Check a saved run's results again with the current invariants and rewrite its files."""
    saved = json.load(open(path))
    meta = dict(saved['meta'], mirror_tol=opts.mirror_tol, hp_tol=opts.hp_tol)
    rom = opts.rom or meta.get('rom_path')
    if not rom:
        sys.exit('--report: give --rom (the saved run does not record its ROM\'s path)')
    d = Data(rom)
    results = {(r['pos'], r['run']): r for r in saved['runs']}
    found, skipped = evaluate(Rules(d), d, saved['positions'], results, meta['only'], opts)
    text = summary(meta, saved['positions'], results, found, skipped, path)
    save(path, meta, saved['positions'], results, found, skipped, text)
    print(text)


def repro(arg, rom, opts):
    """Rerun the runs one saved violation came from and check its invariant again."""
    path, _, k = arg.partition('#')
    saved = json.load(open(path))
    rom = rom or saved['meta'].get('rom_path')
    if not rom:
        sys.exit('--repro: give --rom (the saved run does not record its ROM\'s path)')
    v = next(x for f in saved['invariants'].values() for x in f['violations'] if x['k'] == int(k or 0))
    pos = next(p for p in saved['positions'] if p['id'] == v['pos'])
    print('violation #%s: %s %s (%s): %s' % (k, v['invariant'], v['pos'], v['run'], v['reason']))
    print('position as a bench scenario (run A):\n' + json.dumps(scenario(pos)))
    d = Data(rom)
    R = Rules(d)
    pos['runs'] = sorted({'A', v['run']}, key=list(RUNS).index)
    results = execute(rom, [pos], 1, tag_of(rom) + '_repro')
    n, bad, notes = CHECKS[v['invariant']](R, d, pos, {r: results.get((pos['id'], r)) for r in RUNS}, opts)
    print('rerun on %s: %d checked, %d violations' % (os.path.basename(rom), n, len(bad)))
    for x in bad:
        print('  (%s): %s' % (x['run'], x['reason']))
        print('    ' + json.dumps(x['values']))
    print('reproduced' if bad else 'not reproduced')
    return 0 if bad else 1


# --- selftest (no emulator): each case is a defect an invariant must catch, or a case it must let pass

def _side(d, spec):
    """A debug record side for a spec, as the AI would read the Pokémon build_mon makes of it."""
    v = aibench.mon_view(d, spec)
    return {'species': d.id('species', spec['species']), 'hp': v['cur_hp'], 'maxhp': v['stats']['hp'],
            'stats': [v['stats'][k] for k in ('atk', 'def', 'spa', 'spd', 'spe')],
            'types': (d.species(spec['species'])['types'] + [NONE_TYPE] * 3)[:3], 'level': v['level'],
            'status': {None: 0, 'par': 1, 'slp': 2, 'frz': 3, 'brn': 4, 'psn': 5, 'tox': 5}[spec.get('status')],
            'ability': d.id('ability', spec['ability']), 'item': d.id('item', spec['item']) if spec.get('item') else 0,
            'moves': [d.id('move', m) for m in spec['moves']] + [0] * (4 - len(spec['moves']))}


def _result(d, pos, run, values, choice, **rec):
    """A run result in which my team's AI valued `values` ({option name: value}) and chose `choice`."""
    t, p = run_teams(pos, run)
    side = MY_SIDE[run]
    me, them = (t, p) if side == 1 else (p, t)
    species = [m['species'] for m in me]
    opts = [[1, 0, species.index(n[7:]), x] if n.startswith('switch:') else [0, me[0]['moves'].index(n), 0, x]
            for n, x in values.items()]
    kind, r1, r2 = ('switch', 0, species.index(choice[7:])) if choice.startswith('switch:') else ('move', d.id('move', choice), 0)
    full = {'fallback': 0, 'options': opts, 'weather': 0, 'sw_species': 0, 'sw_w': 0, 'd_mo': [0] * 4, 'nbench': len(me) - 1,
            'me': _side(d, me[0]), 'opp': _side(d, them[0])}
    full.update(rec)
    return {'injected': True, 'run': run, 'sides': {str(side): {'kind': kind, 'r1': r1, 'r2': r2, 'by': 'advanced', 'rec': full}}}


def selftest(rom):
    d = Data(rom)
    R = Rules(d)
    opts = argparse.Namespace(mirror_tol=5, hp_tol=40)
    mon = lambda sp, moves, ability='Run Away', **kw: dict(dict(species=sp, moves=moves, ability=ability, level=50, hp=1.0), **kw)  # noqa: E731
    side = lambda sp, moves=('Tackle',), ability='Run Away', **kw: _side(d, mon(sp, list(moves), ability, **kw))  # noqa: E731
    for sp, types in (('Staraptor', 'Flying'), ('Bronzong', 'Steel'), ('Gengar', 'Ghost'), ('Dugtrio', 'Ground'),
                      ('Skarmory', 'Steel'), ('Arcanine', 'Fire'), ('Venusaur', 'Grass'), ('Shedinja', 'Bug')):
        assert R.T[types] in d.species(sp)['types'], 'the ROM changed %s: the cases below assume it is %s' % (sp, types)

    # positions: reproducible, within the stated shape, the runs' teams as documented
    pool, moves = trainer_pool(rom), random_moves(d)
    ps = [make_position(d, R, pool, moves, 99, k) for k in range(30)]
    assert ps == [make_position(d, R, pool, moves, 99, k) for k in range(30)], 'a position must not depend on the run'
    for p in ps:
        names = [m['species'] for m in p['trainer'] + p['player']]
        assert len(set(names)) == len(names) and all(1 <= len(p[t]) <= 3 for t in ('trainer', 'player')), p['id']
        assert all(isinstance(m['hp'], float) and 0 < m['hp'] <= 1 for m in p['trainer'] + p['player']), p['id']
        assert not all(d.id('ability', p[t][0]['ability']) in R.field_setters for t in ('trainer', 'player')), p['id']
    p = ps[0]
    assert run_teams(p, 'B') == (p['player'], p['trainer'])
    assert run_teams(p, 'T')[0][0]['hp'] == p['hp_variant']['T'] and p['trainer'][0]['hp'] != p['hp_variant']['T']
    assert run_teams(p, 'P')[1][0]['hp'] == p['hp_variant']['P']
    assert runs_of(ps[0], INVARIANTS) == ['A', 'A2', 'B', 'S', 'T'] and runs_of(ps[1], INVARIANTS, 2, 2) == ['A', 'B', 'P']

    # immune_reason, against the ROM's chart and the official abilities
    eq, tb, bs = d.id('move', 'Earthquake'), d.id('move', 'Thunderbolt'), d.id('move', 'Body Slam')
    garchomp = side('Garchomp')
    assert 'type immunity' in (immune_reason(R, d, eq, garchomp, side('Staraptor')) or '')
    assert 'Levitate' in (immune_reason(R, d, eq, garchomp, side('Bronzong', ability='Levitate')) or '')
    assert immune_reason(R, d, eq, side('Garchomp', ability='Mold Breaker'), side('Bronzong', ability='Levitate')) is None
    assert 'Air Balloon' in (immune_reason(R, d, eq, garchomp, side('Snorlax', item='Air Balloon')) or '')
    assert 'Volt Absorb' in (immune_reason(R, d, tb, side('Jolteon'), side('Lanturn', ability='Volt Absorb')) or '')
    assert 'type immunity' in (immune_reason(R, d, bs, side('Tauros'), side('Gengar')) or '')
    assert immune_reason(R, d, bs, side('Tauros', ability='Scrappy'), side('Gengar')) is None
    assert 'Wonder Guard' in (immune_reason(R, d, eq, garchomp, side('Shedinja', ability='Wonder Guard')) or '')
    assert immune_reason(R, d, d.id('move', 'Flamethrower'), side('Arcanine'), side('Shedinja', ability='Wonder Guard')) is None
    assert immune_reason(R, d, eq, garchomp, side('Snorlax')) is None

    # cannot_work
    tw, toxic = d.id('move', 'Thunder Wave'), d.id('move', 'Toxic')
    snorlax = side('Snorlax')
    assert 'type immunity' in (cannot_work(R, d, tw, side('Jolteon'), side('Dugtrio')) or '')
    assert 'Volt Absorb' in (cannot_work(R, d, tw, side('Raichu'), side('Jolteon', ability='Volt Absorb')) or '')
    assert 'Steel' in (cannot_work(R, d, toxic, snorlax, side('Skarmory')) or '')
    assert cannot_work(R, d, toxic, side('Snorlax', ability='Corrosion'), side('Skarmory')) is None
    assert 'Fire' in (cannot_work(R, d, d.id('move', 'Will-O-Wisp'), snorlax, side('Arcanine')) or '')
    assert 'Grass' in (cannot_work(R, d, d.id('move', 'Spore'), snorlax, side('Venusaur')) or '')
    assert cannot_work(R, d, d.id('move', 'Hypnosis'), snorlax, side('Venusaur')) is None
    assert 'a target that is par' in (cannot_work(R, d, toxic, snorlax, side('Snorlax', status='par')) or '')
    assert cannot_work(R, d, toxic, snorlax, snorlax) is None
    assert 'Endeavor' in (cannot_work(R, d, R.endeavor, snorlax, side('Dugtrio', hp=0.5)) or '')
    assert cannot_work(R, d, R.endeavor, side('Snorlax', hp=0.1), side('Dugtrio')) is None
    assert 'full HP' in (cannot_work(R, d, d.id('move', 'Recover'), snorlax, side('Dugtrio')) or '')
    assert cannot_work(R, d, d.id('move', 'Recover'), side('Snorlax', hp=0.5), side('Dugtrio')) is None
    assert 'before the target has moved' in (cannot_work(R, d, d.id('move', 'Encore'), snorlax, side('Dugtrio')) or '')

    def check(inv, pos, runs, violations, notes=None):
        n, bad, nts = CHECKS[inv](R, d, pos, runs, opts)
        assert n == 1 and len(bad) == violations, (inv, n, [b['reason'] for b in bad])
        assert notes is None or len(nts) == notes, (inv, [x['reason'] for x in nts])

    def position(trainer, player, index=0, T=1.0, P=1.0):
        return {'id': 'test', 'seed': 0, 'index': index, 'battle_seed': 0, 'trainer': trainer, 'player': player,
                'hp_variant': {'T': T, 'P': P}}

    # immunity: Earthquake into Levitate valued above moves that hit, chosen, explained by the switch-in, or harmless
    pos = position([mon('Garchomp', ['Earthquake', 'Dragon Claw', 'Fire Fang'])],
                   [mon('Bronzong', ['Tackle'], 'Levitate'), mon('Snorlax', ['Tackle'])])
    vals = {'Earthquake': 300, 'Dragon Claw': 200, 'Fire Fang': 250}
    check('immunity', pos, {'A': _result(d, pos, 'A', vals, 'Fire Fang')}, 1)
    check('immunity', pos, {'A': _result(d, pos, 'A', dict(vals, Earthquake=100), 'Earthquake')}, 1)
    check('immunity', pos, {'A': _result(d, pos, 'A', dict(vals, Earthquake=100), 'Fire Fang')}, 0, 1)
    check('immunity', pos, {'A': _result(d, pos, 'A', vals, 'Fire Fang', sw_species=d.id('species', 'Snorlax'), sw_w=500)}, 0, 1)
    pos = position([mon('Garchomp', ['Earthquake', 'Dragon Claw'])], [mon('Staraptor', ['Tackle'])])
    check('immunity', pos, {'A': _result(d, pos, 'A', {'Earthquake': -50, 'Dragon Claw': 120}, 'Dragon Claw')}, 0, 1)

    # status: Thunder Wave into a Ground type chosen while Shadow Ball works; listed but not chosen is a note
    pos = position([mon('Jolteon', ['Thunder Wave', 'Thunderbolt', 'Shadow Ball'])], [mon('Dugtrio', ['Tackle'])])
    check('status', pos, {'A': _result(d, pos, 'A', {'Thunder Wave': 90, 'Shadow Ball': 80}, 'Thunder Wave')}, 1)
    check('status', pos, {'A': _result(d, pos, 'A', {'Thunder Wave': 90, 'Shadow Ball': 80}, 'Shadow Ball')}, 0, 1)

    # determinism, mirror and interference: the same team valued in two runs
    pos = position([mon('Tauros', ['Body Slam', 'Earthquake']), mon('Gengar', ['Shadow Ball'])], [mon('Snorlax', ['Tackle'])])
    vals = {'Body Slam': 300, 'Earthquake': 250, 'switch:Gengar': -400}
    base = _result(d, pos, 'A', vals, 'Body Slam')
    check('determinism', pos, {'A': base, 'A2': _result(d, pos, 'A2', vals, 'Body Slam')}, 0)
    check('determinism', pos, {'A': base, 'A2': _result(d, pos, 'A2', dict(vals, Earthquake=251), 'Body Slam')}, 1)
    check('mirror', pos, {'A': base, 'B': _result(d, pos, 'B', dict(vals, Earthquake=253), 'Body Slam')}, 0)
    check('mirror', pos, {'A': base, 'B': _result(d, pos, 'B', dict(vals, **{'switch:Gengar': -900}), 'Body Slam')}, 1)
    check('mirror', pos, {'A': base, 'B': _result(d, pos, 'B', vals, 'Earthquake')}, 1)
    check('interference', pos, {'A': base, 'S': _result(d, pos, 'S', dict(vals, **{'Body Slam': 200}), 'Body Slam')}, 1)
    # mirror, the double-KO rule: 1 vs 1, the player side lower within 2 * LAST_BONUS + worth(foe HP) is a note
    pos = position([mon('Salamence', ['Double-Edge', 'Dragon Claw'])], [mon('Dunsparce', ['Tackle'])])
    vals = {'Double-Edge': 1012, 'Dragon Claw': -537}
    one = _result(d, pos, 'A', vals, 'Double-Edge')
    room = 2 * LAST_BONUS + worth(one['sides']['1']['rec']['opp']['hp'], one['sides']['1']['rec']['opp']['maxhp'])
    lower = lambda x, choice='Double-Edge': _result(d, pos, 'B', dict(vals, **{'Double-Edge': x}), choice)  # noqa: E731
    check('mirror', pos, {'A': one, 'B': lower(1012 - room)}, 0, 1)
    check('mirror', pos, {'A': one, 'B': lower(1012 - room, 'Dragon Claw')}, 0, 1)
    check('mirror', pos, {'A': one, 'B': lower(1012 - room - 6)}, 1)
    check('mirror', pos, {'A': one, 'B': lower(1012 + 300)}, 1)
    check('mirror', pos, {'A': _result(d, pos, 'A', vals, 'Dragon Claw'), 'B': lower(1012 - room)}, 1)
    pos = position([mon('Salamence', ['Double-Edge', 'Dragon Claw']), mon('Gengar', ['Shadow Ball'])],
                   [mon('Dunsparce', ['Tackle'])])
    check('mirror', pos, {'A': _result(d, pos, 'A', vals, 'Double-Edge'),
                          'B': _result(d, pos, 'B', dict(vals, **{'Double-Edge': 1012 - room}), 'Double-Edge')}, 1)

    # hp, my active (T: my lead from half to full HP): the best option may not fall on the absolute scale
    pos = position([mon('Tauros', ['Body Slam', 'Earthquake'], hp=0.5)], [mon('Snorlax', ['Tackle'])], index=0, T=1.0)
    lo = _result(d, pos, 'A', {'Body Slam': 300, 'Earthquake': 250}, 'Body Slam')
    check('hp', pos, {'A': lo, 'T': _result(d, pos, 'T', {'Body Slam': 0, 'Earthquake': -50}, 'Body Slam')}, 0)
    check('hp', pos, {'A': lo, 'T': _result(d, pos, 'T', {'Body Slam': -200, 'Earthquake': -250}, 'Body Slam')}, 1)
    # the roles my fuller active holds (debug role) count on the absolute scale: p0030's 1000 stake
    check('hp', pos, {'A': lo, 'T': _result(d, pos, 'T', {'Body Slam': -200, 'Earthquake': -250}, 'Body Slam', role=500)}, 0)
    check('hp', pos, {'A': _result(d, pos, 'A', {'Body Slam': 300, 'Earthquake': 250}, 'Body Slam', role=500),
                      'T': _result(d, pos, 'T', {'Body Slam': 0, 'Earthquake': -50}, 'Body Slam')}, 1)
    # hp, the foe (P: its lead from 20% to full): my sure KO may rise only by the tolerance plus the damage credit
    pos = position([mon('Tauros', ['Body Slam', 'Earthquake'])], [mon('Snorlax', ['Tackle'], hp=0.2)], index=1, P=1.0)
    lo = _result(d, pos, 'A', {'Body Slam': 400, 'Earthquake': 380}, 'Body Slam', d_mo=[999, 999, 0, 0])
    check('hp', pos, {'A': lo, 'P': _result(d, pos, 'P', {'Body Slam': 1050, 'Earthquake': 990}, 'Body Slam', d_mo=[999, 999, 0, 0])}, 0)
    check('hp', pos, {'A': lo, 'P': _result(d, pos, 'P', {'Body Slam': 1200, 'Earthquake': 990}, 'Body Slam', d_mo=[999, 999, 0, 0])}, 1)

    # a fallback or a misread position is never checked
    bad = _result(d, pos, 'A', {'Body Slam': 400}, 'Body Slam')
    bad['sides']['1']['rec']['fallback'] = 6
    assert view(d, pos, {'A': bad}, 'A') == {'skip': 'fallback 6'}
    bad = _result(d, pos, 'A', {'Body Slam': 400}, 'Body Slam')
    bad['sides']['1']['rec']['me']['species'] += 1
    assert view(d, pos, {'A': bad}, 'A')['skip'].startswith('snapshot')
    print('aiprops selftest: all cases pass')


def main():
    if sys.argv[1:2] == ['--worker']:
        return worker(*sys.argv[2:6])
    if '--selftest' in sys.argv[1:]:
        if '--rom' not in sys.argv:
            sys.exit('--selftest needs --rom ROM (the data the made-up runs are built from)')
        return selftest(sys.argv[sys.argv.index('--rom') + 1])
    ap = argparse.ArgumentParser(description='Random turn-1 positions, the advanced AI run on each, invariants checked.')
    ap.add_argument('--rom', default=None, help='the ROM under test (--repro, --report: default the saved run\'s)')
    ap.add_argument('--payload', help='the AI build\'s payload.json (default: ADVAI_PAYLOAD)')
    ap.add_argument('--n', type=int, default=100, help='positions (default 100)')
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--only', default=','.join(INVARIANTS), help='invariants to check: ' + ','.join(INVARIANTS))
    ap.add_argument('--pos', default=None, help='only these position indices of the seed (comma-separated)')
    ap.add_argument('--det-every', type=int, default=1, help='determinism (run A2) on every K-th position (default 1)')
    ap.add_argument('--self-every', type=int, default=1, help='interference (run S) on every K-th position (default 1)')
    ap.add_argument('--mirror-tol', type=int, default=5, help='points two runs of my team may differ by (default 5)')
    ap.add_argument('--hp-tol', type=int, default=40, help='points an absolute value may move the wrong way (default 40)')
    ap.add_argument('--repro', metavar='FILE#k', help='rerun violation k of a saved run')
    ap.add_argument('--report', metavar='FILE', help='check a saved run again with the current invariants (no emulator)')
    a = ap.parse_args()
    if a.report:
        return report(a.report, a)
    payload.path_from(a.payload)            # exported for the workers
    if a.repro:
        sys.exit(repro(a.repro, a.rom, a))
    if not a.rom:
        ap.error('give --rom ROM')
    rom = a.rom
    only = [x for x in a.only.split(',') if x]
    unknown = set(only) - set(INVARIANTS)
    if unknown:
        ap.error('unknown invariant(s) %s; known: %s' % (', '.join(sorted(unknown)), ', '.join(INVARIANTS)))
    seed = a.seed if a.seed is not None else random.randrange(1 << 20)
    d = Data(rom)
    R = Rules(d)
    pool, moves = trainer_pool(rom), random_moves(d)
    indices = [int(x) for x in a.pos.split(',')] if a.pos else range(a.n)
    positions = [make_position(d, R, pool, moves, seed, k) for k in indices]
    for pos in positions:
        pos['runs'] = runs_of(pos, only, a.det_every, a.self_every)
    workers = max(1, min(a.workers, len(positions)))
    print('%d positions (seed %d), %d runs, invariants %s, %d workers' % (
        len(positions), seed, sum(len(p['runs']) for p in positions), ','.join(only), workers), flush=True)
    t0 = time.time()
    results = execute(rom, positions, workers, tag_of(rom))
    meta = {'rom': os.path.basename(rom), 'rom_path': os.path.abspath(rom), 'seed': seed, 'n': len(positions), 'only': only, 'workers': workers,
            'det_every': a.det_every, 'self_every': a.self_every, 'mirror_tol': a.mirror_tol, 'hp_tol': a.hp_tol,
            'seconds': round(time.time() - t0, 1), 'pos': a.pos, 'date': time.strftime('%Y-%m-%d %H:%M')}
    found, skipped = evaluate(R, d, positions, results, only, a)
    path = os.path.join(REPORTS, '%s_%d%s.json' % (os.path.splitext(meta['rom'])[0], seed, '_pos' if a.pos else ''))
    text = summary(meta, positions, results, found, skipped, path)
    save(path, meta, positions, results, found, skipped, text)
    print(text)
    print('\nresults: %s' % tbpaths.rel(path))


if __name__ == '__main__':
    main()
