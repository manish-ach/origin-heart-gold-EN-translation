"""Damage and speed calculator for battle analysts and AI test authors.

One shared calculator built from the ROM's own data (lib/aidata.py: the hack's types, base stats, moves and
type chart) and the Gen 5 damage formula with the common item, ability, field and move modifiers. Every modifier
it applies is printed with one of these labels:
  measured   measured in this hack (emulator tests listed in qa/aivsai/ANALYST_BRIEF.md and
             tests/ai_batches/AUTHORING.md); the measured value is used
  official   the official games' rule, not measured in this hack
  hack       an ability only this hack has, or one the hack changed, read from its description (bank 712)
A factor that changed between generations and was never measured here is a range: Refrigerate is 1.3 in Gen 6 and
1.2 from Gen 7, so the minimum damage uses 1.2 and the maximum 1.3. Where the AI vs AI battle logs point one way the
note says so (`--modifiers` lists everything).

Validation (`--validate`): the hits the battle analysts quoted, then a walk through every run log (`Sweep`) that
tracks what the log implies (stages, statuses, items, weather, terrain, screens, hazards) and compares each hit whose
conditions are all known with the computed range. Anything the log hides makes it skip the hit and count why.

Ported from the Spanish workspace's tools/aicalc.py (dc8577c). Changes: test bench imports (lib/tbpaths.py), the ROM
defaults to the untouched Chinese hack (--rom), battle logs are found under RUNS/aivsai (versus/aivsai.py's runs). The
Spanish analysts' quoted hits (--validate) name Spanish run logs this project does not have: they are reported as
"log not present" unless those logs are copied under RUNS/aivsai/runs/.

Run `.venv/bin/python work/advanced-ai/testbench/dev/aicalc.py --help` for the command line. In Python:

  from aicalc import Calc, Field, read_log
  calc = Calc(rom)
  teams = read_log(calc, 'RUN/s006_g0.log')   # {'ADVANCED': [Mon], 'ORIGINAL': [Mon]}
  jynx, skarmory = calc.pick(teams, 'Jynx'), calc.pick(teams, 'Skarmory')
  r = calc.damage(jynx, 'Hyper Voice', skarmory, Field(weather='rain'))
  r.lo, r.hi, r.ko        # total damage range and [(uses, KO chance at the low end, at the high end)]
  print(r.text())         # the report the command line prints
  m = calc.mon('Mawile', level=100, ability='Huge Power', item='Shuca Berry', nature='Adamant', evs={'atk': 252})
  calc.speed(m)           # (lowest, highest) effective Speed
  calc.order(jynx, skarmory)[0]   # 'speed Jynx 338, Skarmory 169: Jynx moves first'

Formula (Gen 5, as Pokemon Showdown implements it): base power, Attack and Defense modifiers chained in 4096ths;
base = floor(floor(floor(2L/5 + 2) * BP * A / D) / 50) + 2; then spread (0.75), weather, critical hit, the random
roll (85-100%), STAB, type effectiveness (the ROM's chart), burn, and the final modifiers (screens, Multiscale,
Filter, Life Orb, Expert Belt, resist berries...). Accuracy is not part of the KO chances.
"""
import argparse
import functools
import os
import re
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aiteams  # noqa: E402
from aidata import NATURES, PHYSICAL, SPECIAL, STATS, STATUS, TYPE_IMMUNE_ABILITIES, TYPES, norm  # noqa: E402

DEFAULT_ROM = os.path.join(tbpaths.WORK, 'rom', 'origin_v4.0.3_cn.nds')
LOGS = os.path.join(tbpaths.RUNS, 'aivsai')      # the AI-vs-AI runs: LOGS/<run>/<scenario>_g<game>.log

MEASURED, OFFICIAL, HACK = 'measured', 'official', 'hack'
LABELS = {MEASURED: 'measured in this hack', OFFICIAL: 'official rule, not measured', HACK: 'hack ability, not measured'}

T = {norm(t): i for i, t in enumerate(TYPES)}
NORMAL, FIGHTING, FLYING, POISON, GROUND, ROCK, BUG, GHOST, STEEL, FAIRY, FIRE, WATER, GRASS, ELECTRIC, PSYCHIC, ICE, \
    DRAGON, DARK = range(18)
STAT_IDS = {1: 'atk', 2: 'def', 3: 'spa', 4: 'spd', 5: 'spe'}
STAT_ALIASES = {'hp': 'hp', 'atk': 'atk', 'att': 'atk', 'attack': 'atk', 'def': 'def', 'defense': 'def', 'spa': 'spa',
                'satk': 'spa', 'spatk': 'spa', 'spd': 'spd', 'sdef': 'spd', 'spdef': 'spd', 'spe': 'spe', 'speed': 'spe'}
STATUSES = {'brn', 'psn', 'tox', 'par', 'slp', 'frz'}
STAT_ORDER = ['hp', 'atk', 'def', 'spa', 'spd', 'spe']
STAT_LABEL = {'hp': 'HP', 'atk': 'Atk', 'def': 'Def', 'spa': 'SpA', 'spd': 'SpD', 'spe': 'Spe'}
FLAG_CONTACT, FLAG_PUNCH, FLAG_SOUND, FLAG_BITE, FLAG_BALL = 1, 1 << 7, 1 << 8, 1 << 29, 1 << 30
SPREAD_TARGETS = {4, 5}           # move data target byte: all adjacent Pokémon, all adjacent foes
# Gen 5+ hit counts of a 2-5 hit move: 2 and 3 hits 35% each, 4 and 5 hits 15% each.
MULTI_HIT_ODDS = {2: 0.35, 3: 0.35, 4: 0.15, 5: 0.15}

# --- facts measured in this hack (qa/aivsai/ANALYST_BRIEF.md, tests/ai_batches/AUTHORING.md)
MEASURED_INERT_ITEMS = {'souldew': 'Soul Dew does nothing in this ROM (a Latios dealt and took the same damage with and '
                                   'without it, same battle seed)'}
MEASURED_WORKING = {'lightball', 'thickclub', 'focussash', 'bulletproof', 'laggingtail', 'rockyhelmet'}

# --- abilities (keys are aidata.norm() of the ROM's English names; checked against the ROM on load)
ATE = {'refrigerate': (ICE, OFFICIAL), 'pixilate': (FAIRY, OFFICIAL), 'aerilate': (FLYING, OFFICIAL),
       'galvanize': (ELECTRIC, OFFICIAL), 'burningskin': (FIRE, HACK), 'azureskin': (WATER, HACK),
       'grassskin': (GRASS, HACK), 'darkskin': (DARK, HACK), 'dragonize': (DRAGON, HACK)}
ATE_EXEMPT_EFFECTS = {203, 268, 135}   # Weather Ball, Judgment / Techno Blast / Multi-Attack, Hidden Power keep their type
ABILITY_IMMUNE = {norm(a): T[norm(t)] for a, t in TYPE_IMMUNE_ABILITIES.items()}
ABILITY_IMMUNE.update({'eartheater': GROUND, 'wellbakedbdy': FIRE})
MOLD_BREAKERS = {'moldbreaker', 'teravolt', 'turboblaze', 'myceliummght'}
NO_WEATHER = {'cloudnine', 'airlock'}
WEATHER_ABILITIES = {'drizzle': ('rain', OFFICIAL), 'drought': ('sun', OFFICIAL), 'sandstream': ('sand', OFFICIAL),
                     'snowwarning': ('hail', OFFICIAL), 'desolateland': ('harsh', OFFICIAL),
                     'primrdialsea': ('heavy', OFFICIAL), 'orichlcmplse': ('sun', OFFICIAL), 'wildfire': ('sun', HACK)}
TERRAIN_ABILITIES = {'elecsurge': 'electric', 'psychicsurge': 'psychic', 'mistysurge': 'misty', 'grassysurge': 'grassy',
                     'hadronengine': 'electric', 'thunderroar': 'electric'}
PINCH = {'blaze': FIRE, 'torrent': WATER, 'overgrow': GRASS}      # Swarm is a Filter in this hack (bank 712)
TYPE_ATTACK_ABILITIES = {'steelworker': (STEEL, 1.5, 1.5), 'transistor': (ELECTRIC, 1.3, 1.5),
                         'dragonsmaw': (DRAGON, 1.5, 1.5), 'rockypayload': (ROCK, 1.5, 1.5), 'waterbubble': (WATER, 1, 2)}
WEATHER_SPEED = {'swiftswim': ('rain', 'heavy'), 'chlorophyll': ('sun', 'harsh'), 'sandrush': ('sand',),
                 'slushrush': ('hail', 'snow')}
UNMODELED_ABILITIES = {
    'deserthawk': 'Desert Hawk (sandstorm: Speed and Attack up; factors unknown)',
    'protosynthss': 'Protosynthesis (boosts the top stat in sun or with Booster Energy)',
    'quarkdrive': 'Quark Drive (boosts the top stat in Electric Terrain or with Booster Energy)',
    'analytic': 'Analytic (1.3x when moving last)', 'flashfire': 'Flash Fire (1.5x Fire after absorbing one: pass '
    '--a-flags flashfire)', 'suprmoverlrd': 'Supreme Overlord', 'blazingawe': 'Blazing Awe (lowers the foe\'s Attack '
    'on entry: pass the stage with --a-boost / --d-boost)', 'intimidate': 'Intimidate (pass the -1 Attack stage with '
    '--a-boost atk-1)', 'download': 'Download (+1 Atk or SpA on entry: pass it with --a-boost)',
    'parentalbond': None, 'rivalry': 'Rivalry (depends on genders)', 'stakeout': None}

# --- items (keys are aidata.norm() of the ROM's English names)
TYPE_ITEMS = {'charcoal': FIRE, 'mysticwater': WATER, 'magnet': ELECTRIC, 'miracleseed': GRASS, 'nevermeltice': ICE,
              'blackbelt': FIGHTING, 'poisonbarb': POISON, 'softsand': GROUND, 'sharpbeak': FLYING, 'twistedspoon': PSYCHIC,
              'silverpowder': BUG, 'hardstone': ROCK, 'spelltag': GHOST, 'dragonfang': DRAGON, 'blackglasses': DARK,
              'metalcoat': STEEL, 'silkscarf': NORMAL, 'fairyfeather': FAIRY, 'pixieplate': FAIRY, 'flameplate': FIRE,
              'splashplate': WATER, 'zapplate': ELECTRIC, 'meadowplate': GRASS, 'icicleplate': ICE, 'fistplate': FIGHTING,
              'toxicplate': POISON, 'earthplate': GROUND, 'skyplate': FLYING, 'mindplate': PSYCHIC, 'insectplate': BUG,
              'stoneplate': ROCK, 'spookyplate': GHOST, 'dracoplate': DRAGON, 'dreadplate': DARK, 'ironplate': STEEL,
              'seaincense': WATER, 'waveincense': WATER, 'roseincense': GRASS, 'oddincense': PSYCHIC,
              'rockincense': ROCK}
RESIST_BERRIES = {'occaberry': FIRE, 'passhoberry': WATER, 'wacanberry': ELECTRIC, 'rindoberry': GRASS,
                  'yacheberry': ICE, 'chopleberry': FIGHTING, 'kebiaberry': POISON, 'shucaberry': GROUND,
                  'cobaberry': FLYING, 'payapaberry': PSYCHIC, 'tangaberry': BUG, 'chartiberry': ROCK,
                  'kasibberry': GHOST, 'habanberry': DRAGON, 'colburberry': DARK, 'babiriberry': STEEL,
                  'roseliberry': FAIRY, 'chilanberry': NORMAL}
# What the AI vs AI logs show for resist berries (all 18 share one handler and their item data names the right type):
# the high end of the berry factor (0.5 when a log hit showed it working) and the evidence. Not seen: 0.5-1.
BERRY_EVIDENCE = {'yacheberry': (0.5, 'halved the hit in the AI vs AI logs (s006_g0 turn 11)'),
                  'shucaberry': (0.5, 'halved the hit in the AI vs AI logs (s008_g1 turn 9)'),
                  'cobaberry': (1, 'did nothing in two log hits (s008_g0 turn 1, s008_g1 turn 2)'),
                  'chartiberry': (1, 'did nothing in a log hit (s033_g0 turn 4)'),
                  'kebiaberry': (1, 'did nothing in a log hit (s033_g1 turn 6)')}
ORBS = {'adamantorb': ('dialga', {STEEL, DRAGON}), 'lustrousorb': ('palkia', {WATER, DRAGON}),
        'griseousorb': ('giratina', {GHOST, DRAGON})}
HALF_SPEED_ITEMS = {'ironball', 'machobrace', 'powerweight', 'powerbracer', 'powerbelt', 'powerlens', 'powerband',
                    'poweranklet'}

# --- moves, by the ROM's spelling (aidata.norm) or by effect id (aidata.move()['effect'])
PULSE = {'aurasphere', 'darkpulse', 'dragonpulse', 'originpulse', 'waterpulse', 'terrainpulse'}
CANNON = {'flashcannon', 'hydrocannon', 'zapcannon', 'armorcannon', 'spikecannon', 'dynamaxcannon'}
SLICING = {'aerialace', 'aircutter', 'airslash', 'aquacutter', 'behemthblade', 'bitterblade', 'ceaselesedge',
           'crosspoison', 'cut', 'furycutter', 'kowtowcleave', 'leafblade', 'nightslash', 'populatnbomb', 'psychocut',
           'razorleaf', 'razorshell', 'sacredsword', 'secretsword', 'slash', 'solarblade', 'stoneaxe', 'xscissor',
           'tachyoncuttr', 'psyblade',
           'dragonclaw'}   # dragonclaw: Sharpness boosts it in this hack (logs: s009_g1 t4 136 vs 90-107, 20261003_101454 s015_g1 x1.5)
CRASH = {'jumpkick', 'hijumpkick', 'axekick', 'supercellslm'}
SOLAR = {'solarbeam', 'solarblade'}
GRASSY_HALVED = {'earthquake', 'bulldoze', 'magnitude'}
E = dict(WEATHER_BALL=203, FOUL_PLAY=297, BODY_PRESS=433, RIVAL=430, KNOCK_OFF=188, PSYSHOCK=282, FACADE=169,
         BRINE=221, VENOSHOCK=283, HEX=310, ACROBATICS=317, ERUPTION=190, GYRO_BALL=219, ELECTRO_BALL=293,
         REVERSAL=99, LEVEL_DAMAGE=87, DRAGON_RAGE=41, SONIC_BOOM=130, STORED_POWER=305)
FIXED_NOTES = {'counter': 'returns twice the physical damage it took this turn', 'mirrorcoat': 'returns twice the '
               'special damage it took this turn', 'metalburst': 'returns 1.5x the damage it took this turn',
               'comeuppance': 'returns 1.5x the damage it took this turn', 'endeavor': 'cuts the target to the user\'s HP',
               'finalgambit': 'deals the user\'s HP and faints it', 'superfang': 'halves the target\'s HP',
               'naturmadness': 'halves the target\'s HP', 'ruination': 'halves the target\'s HP',
               'psywave': 'random 50-150% of the user\'s level', 'bide': 'returns twice the damage taken over two turns'}
VARIABLE_NOTES = {'lowkick': 'weight', 'grassknot': 'weight', 'heavyslam': 'weights', 'heatcrash': 'weights',
                  'return': 'friendship', 'frustration': 'friendship', 'hiddenpower': 'IVs (type and power)',
                  'punishment': 'the target\'s boosts', 'payback': 'move order (2x moving last)',
                  'avalanche': 'whether the user was hit first (2x)', 'revenge': 'whether the user was hit first (2x)',
                  'assurance': 'whether the target was hit this turn (2x)', 'pursuit': 'whether the target switches (2x)',
                  'rollout': 'consecutive uses', 'iceball': 'consecutive uses', 'furycutter': 'consecutive uses',
                  'echoedvoice': 'consecutive uses', 'round': 'an ally using Round', 'spitup': 'Stockpile count',
                  'beatup': 'the party', 'present': 'a random roll', 'magnitude': 'a random roll',
                  'trumpcard': 'remaining PP', 'lastrespects': 'fainted allies', 'ragefist': 'hits taken',
                  'smellingsalt': 'a paralyzed target (2x)', 'wakeupslap': 'a sleeping target (2x)',
                  'fling': 'the held item', 'naturalgift': 'the held Berry', 'storedpower': None}


def q(f):
    """A factor in 4096ths, as the games store it (1.3 = 5325, 1.2 = 4915, 1.1 = 4505)."""
    return int(f * 4096 + 0.5)


def chain(qs):
    m = 4096
    for x in qs:
        m = (m * x + 2048) >> 12
    return m


def modify(v, m):
    """v x m/4096 rounded half down (Showdown's modify, the games' rounding)."""
    return (v * m + 2047) >> 12


def staged(stat, stage):
    stage = max(-6, min(6, stage))
    return stat * (2 + stage) // 2 if stage >= 0 else stat * 2 // (2 - stage)


@dataclass
class Mod:
    name: str
    lo: float
    hi: float
    label: str
    stage: str          # raw (power set directly), power, tech, second (Parental Bond's 2nd hit), atk, def, spread,
                        # weather, crit, stab, burn, final, first (first hit only), note, speed
    note: str = ''
    qlo: int = None     # explicit 4096ths when the game's value is not the rounded factor (Life Orb 5324)
    qhi: int = None

    def qs(self, case):
        if case:
            return self.qhi if self.qhi is not None else q(self.hi)
        return self.qlo if self.qlo is not None else q(self.lo)

    def factor(self):
        if self.lo == self.hi:
            return 'x%s' % ('%.4g' % self.lo)
        return 'x%s-%s' % ('%.4g' % self.lo, '%.4g' % self.hi)


@dataclass
class Field:
    """weather: None, 'sun', 'rain', 'sand', 'hail', 'snow' (Gen 9 snow: Ice types get 1.5x Defense), 'harsh'
    (Desolate Land), 'heavy' (Primordial Sea). terrain: None, 'electric', 'grassy', 'psychic', 'misty'.
    spread: a spread move hitting two or more targets (doubles). trick_room: slower moves first."""
    weather: str = None
    terrain: str = None
    spread: bool = False
    doubles: bool = False
    trick_room: bool = False

    @staticmethod
    def auto(calc, mons, weather=None, terrain=None):
        """The weather and terrain the given Pokémon's entry abilities set, unless given. Returns (Field, notes)."""
        notes = []
        for m in mons:
            if weather is None and m.ab in WEATHER_ABILITIES:
                weather = WEATHER_ABILITIES[m.ab][0]
                notes.append('weather %s from %s\'s %s; it lasts 5 turns (8 with its rock) and a re-entry does not renew it '
                             '(override with --weather)' % (weather, m.name, m.ability))
                if m.ab == 'snowwarning':
                    notes.append('this hail did no chip damage in the logs, so it may be Gen 9 snow, which also gives Ice '
                                 'types 1.5x Defense: try --weather snow')
            if terrain is None and m.ab in TERRAIN_ABILITIES:
                terrain = TERRAIN_ABILITIES[m.ab]
                notes.append('%s terrain from %s\'s %s (override with --terrain)' % (terrain, m.name, m.ability))
        return Field(weather=None if weather == 'none' else weather, terrain=None if terrain == 'none' else terrain), notes


class Mon:
    """A Pokémon in a battle state. Built by Calc.mon(); the fields below are what the calculator reads.
    flags: 'tailwind', 'reflect', 'lightscreen', 'auroraveil' (on this Pokémon's side), 'unburden' (its item is gone),
    'flashfire' (Flash Fire activated), 'charged'."""

    def __init__(self, calc, species, level=100, ability=None, item=None, nature='Hardy', evs=None, ivs=31,
                 boosts=None, status=None, hp=None, moves=(), side='', flags=()):
        d = calc.d
        self.calc = calc
        self.sid = d.id('species', species)
        self.name = d.species_name[self.sid]
        self.level = level
        self.nature = NATURES[[norm(n) for n in NATURES].index(norm(nature))] if nature else 'Hardy'
        self.evs = {STAT_ALIASES[k]: v for k, v in (evs or {}).items()}
        self.ivs = ivs
        self.stats = d.stats(self.sid, level, self.evs, ivs, self.nature)
        self.types = d.species(self.sid)['types']
        self.ability = d.ability_name[d.id('ability', ability)] if ability not in (None, '', 'none') else None
        self.ab = norm(self.ability) if self.ability else ''
        self.set_item(item)
        self.boosts = {STAT_ALIASES[k]: v for k, v in (boosts or {}).items()}
        if status and status not in STATUSES:
            raise ValueError('status %r: use one of %s' % (status, ', '.join(sorted(STATUSES))))
        self.status = status
        self.hp = self.stats['hp'] if hp is None else hp_value(hp, self.stats['hp'])
        self.moves = [d.move_name[d.id('move', mv)] for mv in moves]
        self.side = side
        self.flags = set(flags)
        self.maybe_ = set()     # statuses it may have (the log validator's uncertainty)

    def set_item(self, item):
        """item: a name, an id (the log prints ids for names that stand for two items), or None."""
        d, self.item_note, self.item_label = self.calc.d, '', None
        if item in (None, '', 'none', '-', 0):
            self.item, self.item_id, self.it = None, 0, ''
            return
        self.item_id = int(item) if str(item).isdigit() else d.id('item', item)
        self.item = d.item_name.get(self.item_id, str(self.item_id))
        self.it = norm(self.item)
        if self.item_id not in self.calc.handled_items:
            self.item_note = ('item %d (%s) has no entry in the battle engine\'s item handler table: no effect' %
                              (self.item_id, self.item))
            self.item_label = MEASURED if self.it == 'rockyhelmet' else 'rom'
            self.it = ''
        elif self.it in MEASURED_INERT_ITEMS:
            self.item_note, self.item_label, self.it = MEASURED_INERT_ITEMS[self.it], MEASURED, ''
        elif self.ab == 'klutz':
            self.item_note, self.item_label, self.it = 'Klutz: the item has no effect', OFFICIAL, ''

    @property
    def maxhp(self):
        return self.stats['hp']

    def describe(self):
        bits = ['L%d' % self.level, self.nature, self.ability or 'no ability', '@ ' + (self.item or '-')]
        if self.status:
            bits.append(self.status)
        boosts = ' '.join('%s%+d' % (k, v) for k, v in self.boosts.items() if v)
        if boosts:
            bits.append(boosts)
        if self.flags:
            bits.append(','.join(sorted(self.flags)))
        side = '%s ' % self.side if self.side else ''
        return '%s%s (%s): HP %d/%d, %s' % (side, self.name, ', '.join(bits), self.hp, self.maxhp,
                                            ' '.join('%s %d' % (STAT_LABEL[k], self.stats[k]) for k in STAT_ORDER[1:]))


def hp_value(hp, maxhp):
    """182, '182', '50%', 0.5 -> current HP."""
    if isinstance(hp, str):
        hp = hp.strip()
        if hp.endswith('%'):
            return max(1, int(maxhp * float(hp[:-1]) / 100))
        hp = float(hp) if '.' in hp else int(hp)
    if isinstance(hp, float) and 0 < hp <= 1:
        return max(1, int(maxhp * hp))
    return int(hp)


class Result:
    def __init__(self, att, move, dfn):
        self.att, self.move, self.dfn = att, move, dfn
        self.mods, self.notes, self.after = [], [], []
        self.fails = None           # why the move does nothing (immunity, weather, terrain)
        self.fixed = None           # fixed damage (Seismic Toss...)
        self.rolls = None           # rolls[case][hit] = 16 damages; case 0 low factors, case 1 high factors
        self.hits = (1, 1)
        self.hit_odds = {1: 1.0}
        self.mtype = self.cls = self.eff = None
        self.power = (0, 0)
        self.ko = []

    @property
    def lo(self):
        if self.fixed is not None:
            return self.fixed
        if not self.rolls:
            return 0
        return sum(self.rolls[0][i][0] for i in range(self.hits[0]))

    @property
    def hi(self):
        if self.fixed is not None:
            return self.fixed
        if not self.rolls:
            return 0
        return sum(self.rolls[1][i][15] for i in range(self.hits[1]))

    def pct(self, v):
        return 100.0 * v / self.dfn.maxhp

    def text(self, verbose=False):
        a, d = self.att, self.dfn
        out = ['%s %s -> %s' % (a.name, self.move, d.name)]
        if self.fails:
            out.append('  no damage: %s' % self.fails)
        elif self.fixed is not None:
            out.append('  fixed damage: %d (%.1f%% of %d)%s' % (self.fixed, self.pct(self.fixed), d.maxhp, self.ko_text()))
        elif self.rolls is None:
            out.append('  ' + '; '.join(self.notes))
            return '\n'.join(out)
        else:
            plo, phi = self.power
            hits = '' if self.hits == (1, 1) else ', %d-%d hits' % self.hits if self.hits[0] != self.hits[1] else \
                ', %d hits' % self.hits[0]
            out.append('  %s %s, power %s%s, effectiveness x%s' % (
                TYPES[self.mtype], ['status', 'physical', 'special'][self.cls], plo if plo == phi else '%d-%d' % (plo, phi),
                hits, '%g' % self.eff))
            if self.hits != (1, 1):
                ranges = [(self.rolls[0][i][0], self.rolls[1][i][15]) for i in range(max(self.hits))]
                if len(set(ranges)) == 1:
                    out.append('  per hit %d-%d' % ranges[0])
                else:
                    out.append('  per hit: %s' % ', '.join('hit %d %d-%d' % (i + 1, a, b) for i, (a, b) in enumerate(ranges)))
            out.append('  damage %d-%d (%.1f-%.1f%% of %d)%s' % (self.lo, self.hi, self.pct(self.lo), self.pct(self.hi),
                                                              d.maxhp, self.ko_text()))
            if verbose:
                for case, name in ((0, 'low'), (1, 'high')):
                    for i, h in enumerate(self.rolls[case][:max(self.hits)]):
                        out.append('  rolls (%s factors%s): %s' % (name, ', hit %d' % (i + 1) if self.hits != (1, 1) else '',
                                                                   ' '.join(map(str, h))))
                    if not any(m.lo != m.hi for m in self.mods):
                        break
        for m in self.mods:
            out.append('    %-38s %-9s %s%s' % (m.name, '' if m.stage == 'note' else m.factor(), LABELS.get(m.label, m.label),
                                                ('; ' + m.note) if m.note else ''))
        for n in self.notes + self.after:
            out.append('  note: ' + n)
        return '\n'.join(out)

    def ko_text(self):
        if not self.ko:
            return ''
        d = self.dfn
        parts = []
        first = next((k for k, (n, lo, hi) in enumerate(self.ko) if max(lo, hi) > 0), None)
        shown = self.ko if first is None else self.ko[max(0, first - 1):]
        for n, lo, hi in shown:
            parts.append('%s %s' % ('OHKO' if n == 1 else '%dHKO' % n, pct_range(lo, hi)))
        if first is None:
            parts = [parts[-1] + ' (more needed)']
        start = 'from %d/%d HP' % (d.hp, d.maxhp) if d.hp != d.maxhp else 'from full HP'
        return '\n  KO chance %s: %s' % (start, ', '.join(parts))


def pct_range(lo, hi):
    f = lambda x: '%.0f%%' % (100 * x) if x in (0, 1) or 100 * x >= 99.95 or 100 * x < 0.05 else '%.1f%%' % (100 * x)
    return f(lo) if abs(lo - hi) < 0.0005 else '%s-%s' % (f(min(lo, hi)), f(max(lo, hi)))


def dist_add(a, b):
    out = {}
    for x, p in a.items():
        for y, r in b.items():
            out[x + y] = out.get(x + y, 0) + p * r
    return out


def uniform(rolls):
    return {v: rolls.count(v) / 16 for v in set(rolls)}


class Calc:
    def __init__(self, rom=DEFAULT_ROM):
        self.rom = rom
        self.d = aiteams.data(rom)
        self.handled_items = aiteams.rom_tables(rom)['handled_items']
        self.override = {}
        known = set(self.d.names['ability'])
        tables = [ATE, ABILITY_IMMUNE, MOLD_BREAKERS, NO_WEATHER, WEATHER_ABILITIES, TERRAIN_ABILITIES, PINCH,
                  TYPE_ATTACK_ABILITIES, WEATHER_SPEED, UNMODELED_ABILITIES]
        missing = sorted({k for t in tables for k in t if k not in known})
        assert not missing, 'aicalc ability tables name abilities the ROM does not have: %s' % missing

    def mon(self, species, **kw):
        return Mon(self, species, **kw)

    def pick(self, teams, name):
        """A Pokémon of a log's teams by species name; 'adv:Name' or 'orig:Name' picks the side."""
        side, _, sp = name.rpartition(':')
        side = {'a': 'ADVANCED', 'adv': 'ADVANCED', 'advanced': 'ADVANCED', 'o': 'ORIGINAL', 'orig': 'ORIGINAL',
                'original': 'ORIGINAL', '': None}.get(side.lower(), side.upper() or None)
        key = norm(sp)
        found = [m for s, mons in teams.items() if side in (None, s) for m in mons if norm(m.name) == key]
        if not found:
            found = [m for s, mons in teams.items() if side in (None, s) for m in mons if norm(m.name).startswith(key)]
        if len(found) != 1:
            names = ', '.join('%s:%s' % (s[:3].lower() if s in ('ADVANCED', 'ORIGINAL') else s, m.name)
                              for s, mons in teams.items() for m in mons)
            raise KeyError('%r matches %d Pokémon in these teams (%s)%s' % (
                name, len(found), names, '; prefix adv: or orig:' if len(found) > 1 else ''))
        return found[0]

    # --- speed
    def speed(self, mon, field=None, mods=None):
        """(lowest, highest) effective Speed (equal since the paralysis rule was measured)."""
        field = field or Field()
        mods = [] if mods is None else mods
        s = staged(mon.stats['spe'], mon.boosts.get('spe', 0))
        qs = []
        weather = None if mon.ab in NO_WEATHER else field.weather

        def add(name, f, label=OFFICIAL, note=''):
            qs.append(q(f))
            mods.append(Mod(name, f, f, label, 'speed', note))
        if mon.it == 'choicescarf':
            add('Choice Scarf', 1.5)
        if mon.it in HALF_SPEED_ITEMS:
            add(mon.item, 0.5)
        if mon.ab in WEATHER_SPEED and weather in WEATHER_SPEED[mon.ab]:
            add(mon.ability, 2)
        if mon.ab == 'surgesurfer' and field.terrain == 'electric':
            add('Surge Surfer', 2)
        if mon.ab == 'unburden' and 'unburden' in mon.flags:
            add('Unburden', 2)
        if mon.ab == 'quickfeet' and mon.status:
            add('Quick Feet', 1.5, MEASURED, 'any status; it lifts the paralysis halving (rc27 engine fix)')
        if mon.ab == 'slowstart':
            add('Slow Start (first five turns)', 0.5)
        if 'tailwind' in mon.flags:
            add('Tailwind', 2)
        s = modify(s, chain(qs))
        if mon.status == 'par' and mon.ability != 'Quick Feet':     # after every other factor (qa/aivsai/paralysis.md)
            mods.append(Mod('paralysis', 0.5, 0.5, MEASURED, 'speed', '1/2; Quick Feet lifts it since the rc27 engine fix'))
            s = modify(s, 2048)
        return s, s

    def priority(self, mon, move):
        if not move:
            return 0, ''
        m = self.d.move(move)
        p, why = m['priority'], ''
        if mon.ab == 'prankster' and m['class'] == STATUS:
            p, why = p + 1, 'Prankster +1'
        if mon.ab == 'galewings' and m['type'] == FLYING:
            p, why = p + 1, 'Gale Wings +1 (Gen 7+: only at full HP)'
        if mon.ab == 'triage' and (m['heal'] or m['recoil'] > 0):
            p, why = p + 3, 'Triage +3'
        return p, why

    def order(self, a, b, field=None, move_a=None, move_b=None):
        """(text, who): who is 1 when a surely moves first, -1 when b does, 0 when it is open."""
        field = field or Field()
        ma, mb = [], []
        sa, sb = self.speed(a, field, ma), self.speed(b, field, mb)
        pa, why_a = self.priority(a, move_a)
        pb, why_b = self.priority(b, move_b)
        tr = ' (Trick Room)' if field.trick_room else ''
        fmt = lambda s: str(s[0]) if s[0] == s[1] else '%d-%d' % s
        mods = '; '.join('%s %s' % (x.name, x.factor()) for x in ma + mb)
        text = 'speed %s %s, %s %s%s' % (a.name, fmt(sa), b.name, fmt(sb), tr)
        if mods:
            text += ' [%s]' % mods
        if pa != pb:
            who = 1 if pa > pb else -1
            text += ': %s moves first (priority %+d vs %+d%s)' % ((a if who > 0 else b).name, pa, pb,
                                                                ', ' + (why_a or why_b) if (why_a or why_b) else '')
            return text, who
        lo_a, hi_a = sa
        lo_b, hi_b = sb
        sign = -1 if field.trick_room else 1
        if sign * (lo_a - hi_b) > 0 and sign * (hi_a - lo_b) > 0:
            who = 1
        elif sign * (hi_a - lo_b) < 0 and sign * (lo_a - hi_b) < 0:
            who = -1
        else:
            return text + ': speed tie (random)', 0
        last = [x.it in ('laggingtail', 'fullincense') or x.ab == 'stall' for x in (a, b)]
        extra = ''
        if last[0] != last[1]:
            slow = a if last[0] else b
            who = -1 if last[0] else 1
            extra = ' (%s moves last in its priority bracket: %s%s)' % (
                slow.name, slow.item if slow.it else slow.ability, ', measured' if slow.it == 'laggingtail' else '')
        if any(x.it == 'quickclaw' for x in (a, b)):
            extra += ' (Quick Claw: 20% to move first)'
        return text + ': %s moves first%s' % ((a if who > 0 else b).name, extra), who

    # --- damage
    def grounded(self, mon):
        if mon.it == 'ironball':
            return True
        return FLYING not in mon.types and mon.ab != 'levitate' and mon.it != 'airballoon'

    def damage(self, att, move, dfn, field=None, crit=False, switch_in=False):
        """One use of `move` by att on dfn. switch_in: dfn is switching in this turn (Fishious Rend and Bolt Beak
        double, Stakeout doubles). Returns a Result."""
        field = field or Field()
        d = self.d
        m = d.move(move)
        name = d.move_name[m['id']]
        key = norm(name)
        r = Result(att, name, dfn)
        r.cls = m['class']
        if m['class'] == STATUS:
            r.notes.append('status move: no damage')
            return r
        aab = att.ab
        mold = aab in MOLD_BREAKERS
        dab = '' if mold and dfn.ab else dfn.ab
        if mold and dfn.ab:
            r.notes.append('%s ignores %s\'s %s' % (att.ability, dfn.name, dfn.ability))
        weather = field.weather
        if aab in NO_WEATHER or dab in NO_WEATHER:
            weather = None
        if aab == 'megasol' and weather not in ('rain', 'heavy'):
            weather = 'sun'
            r.mods.append(Mod('Mega Sol: moves as in sun', 1, 1, HACK, 'note'))
        mods = r.mods

        def add(stage, name, lo, hi=None, label=OFFICIAL, note='', qlo=None, qhi=None):
            if name in self.override:      # experiments: aicalc.Calc().override['Iron Fist (punch)'] = (1.3, 1.3)
                (lo, hi), qlo, qhi = self.override[name], None, None
            mods.append(Mod(name, lo, lo if hi is None else hi, label, stage, note, qlo, qhi))

        # type
        mtype, power, cls, eff_id = m['type'], m['power'], m['class'], m['effect']
        if eff_id == E['WEATHER_BALL'] and weather:
            mtype = {'sun': FIRE, 'harsh': FIRE, 'rain': WATER, 'heavy': WATER, 'sand': ROCK, 'hail': ICE, 'snow': ICE}[weather]
            add('raw', 'Weather Ball in %s: %s, power x2' % (weather, TYPES[mtype]), 2)
        if aab == 'normalize':
            if mtype != NORMAL:
                mtype = NORMAL
            add('power', 'Normalize: every move Normal', 1.0, 1.2, note='Gen 4-6: no boost, Gen 7+: 1.2')
        elif aab in ATE and mtype == NORMAL and eff_id not in ATE_EXEMPT_EFFECTS:
            mtype, label = ATE[aab]
            add('power', '%s: Normal -> %s' % (att.ability, TYPES[mtype]), 1.2, 1.3, label,
                'Gen 6: 1.3, Gen 7+: 1.2; the AI vs AI logs fit 1.2 (9 of 9 -ate hits, 4 fit 1.3)' +
                ('; assumed to work like Refrigerate' if label == HACK else ''))
        elif aab == 'liquidvoice' and m['flags'] & FLAG_SOUND:
            mtype = WATER
            add('power', 'Liquid Voice: sound move -> Water', 1)
        if key == 'terrainpulse' and field.terrain and self.grounded(att):
            mtype = {'electric': ELECTRIC, 'grassy': GRASS, 'psychic': PSYCHIC, 'misty': FAIRY}[field.terrain]
            add('raw', 'Terrain Pulse in %s terrain: %s, power x2' % (field.terrain, TYPES[mtype]), 2)
        r.mtype = mtype

        # does it work at all
        fails = None
        eff_parts = []
        for t in dfn.types:
            e = d.chart[mtype][t] / 4
            if key == 'freezedry' and t == WATER:
                e = 2
            if e == 0 and t == GHOST and mtype in (NORMAL, FIGHTING) and aab in ('scrappy', 'mindseye'):
                e = 1
                r.notes.append('%s: %s hits Ghost types' % (att.ability, TYPES[mtype]))
            if key == 'flyingpress':
                e *= d.chart[FLYING][t] / 4
            eff_parts.append(e)
        eff = 1
        for e in eff_parts:
            eff *= e
        if mtype == GROUND and dfn.it == 'airballoon' and eff:
            fails = '%s\'s Air Balloon (official rule)' % dfn.name
        if eff and dab in ABILITY_IMMUNE and ABILITY_IMMUNE[dab] == mtype:
            fails = '%s\'s %s makes it immune to %s moves (official rule)' % (dfn.name, dfn.ability, TYPES[mtype])
        if eff and dab == 'wonderguard' and eff <= 1:
            fails = 'Wonder Guard: only super effective moves hit (official rule)'
        if eff and dab == 'soundproof' and m['flags'] & FLAG_SOUND:
            fails = 'Soundproof blocks sound moves (official rule)'
        if eff and dab == 'bulletproof' and m['flags'] & FLAG_BALL:
            fails = 'Bulletproof blocks ball and bomb moves (measured in this hack)'
        if weather == 'harsh' and mtype == WATER:
            fails = 'Water moves fail in harsh sun (Desolate Land; official rule)'
        if weather == 'heavy' and mtype == FIRE:
            fails = 'Fire moves fail in heavy rain (Primordial Sea; official rule)'
        pri, _ = self.priority(att, name)
        if field.terrain == 'psychic' and pri > 0 and self.grounded(dfn):
            fails = 'Psychic Terrain blocks priority moves against a grounded target (official rule)'
        if (aab == 'thunderroar' or dab == 'thunderroar') and pri > 0:
            r.notes.append('Thunder Roar: "first-strike moves fail" (hack ability, not measured)')
        r.eff = eff
        if eff == 0 and not fails:
            fails = '%s does not affect %s (type chart)' % (TYPES[mtype], '/'.join(TYPES[t] for t in dfn.types))
        if fails:
            r.fails = fails
            return r

        # fixed damage
        if eff_id == E['LEVEL_DAMAGE']:
            r.fixed = att.level
        elif eff_id == E['DRAGON_RAGE']:
            r.fixed = 40
        elif eff_id == E['SONIC_BOOM']:
            r.fixed = 20
        elif key in ('superfang', 'naturmadness', 'ruination'):
            r.fixed = max(1, dfn.hp // 2)
        if r.fixed is not None:
            r.ko = [(1, float(r.fixed >= dfn.hp), float(r.fixed >= dfn.hp))]
            return r
        if key in FIXED_NOTES:
            r.notes.append('%s %s: compute that damage first' % (name, FIXED_NOTES[key]))
            return r

        # variable power
        plo = phi = power
        if key in VARIABLE_NOTES and VARIABLE_NOTES[key]:
            r.notes.append('power depends on %s, not modeled: computed at the listed power %d' % (VARIABLE_NOTES[key], power))
        if eff_id == E['FACADE'] and att.status in ('brn', 'psn', 'tox', 'par'):
            add('raw', 'Facade with a status', 2)
        if eff_id == E['BRINE'] and dfn.hp * 2 <= dfn.maxhp:
            add('raw', 'Brine on a target at half HP or less', 2)
        if eff_id == E['VENOSHOCK'] and dfn.status in ('psn', 'tox'):
            add('raw', '%s on a poisoned target' % name, 2)
        if eff_id == E['HEX'] and dfn.status:
            add('raw', '%s on a target with a status' % name, 2)
        if eff_id == E['ACROBATICS'] and not att.item:
            add('raw', 'Acrobatics without an item', 2)
        if eff_id == E['ERUPTION'] or key == 'dragonenergy':
            plo = phi = max(1, 150 * att.hp // att.maxhp)
            add('note', '%s at %d/%d HP: power %d' % (name, att.hp, att.maxhp, plo), 1)
        if key in ('wringout', 'crushgrip', 'hardpress'):
            top = 100 if key == 'hardpress' else 120
            plo = phi = max(1, top * dfn.hp // dfn.maxhp)
            add('note', '%s on %d/%d HP: power %d' % (name, dfn.hp, dfn.maxhp, plo), 1)
        if eff_id == E['REVERSAL']:
            p = 48 * att.hp // att.maxhp
            plo = phi = 200 if p <= 1 else 150 if p <= 4 else 100 if p <= 9 else 80 if p <= 16 else 40 if p <= 32 else 20
            add('note', '%s at %d/%d HP: power %d' % (name, att.hp, att.maxhp, plo), 1)
        if eff_id == E['STORED_POWER']:
            plo = phi = 20 + 20 * sum(v for v in att.boosts.values() if v > 0)
            add('note', '%s: 20 + 20 per boost = %d' % (name, plo), 1)
        if eff_id in (E['GYRO_BALL'], E['ELECTRO_BALL']):
            us, ts = self.speed(att, field), self.speed(dfn, field)
            if eff_id == E['GYRO_BALL']:
                ps = [min(150, 25 * t // max(1, u) + 1) for u in us for t in ts]
            else:
                ps = [{0: 40, 1: 60, 2: 80, 3: 120}.get(u // max(1, t), 150) for u in us for t in ts]
            plo, phi = min(ps), max(ps)
            add('note', '%s from the Speeds: power %s' % (name, plo if plo == phi else '%d-%d' % (plo, phi)), 1)
        if key == 'expandforce' and field.terrain == 'psychic' and self.grounded(att):
            add('raw', 'Expanding Force in Psychic Terrain', 1.5, note='Gen 8+: power 120')
        if eff_id == E['RIVAL']:
            if switch_in:
                add('raw', '%s on a Pokémon switching in' % name, 2, note='doubles when the target has not moved yet')
            else:
                _, who = self.order(att, dfn, field, name)
                if who > 0:
                    add('raw', '%s, user moves first' % name, 2, note='the target has not moved yet')
                elif who == 0:
                    add('raw', '%s, move order open' % name, 1, 2, note='2x if the user moves first')
                else:
                    r.notes.append('%s does not double: the target moves first (pass --switch-in for a switch-in)' % name)
        if key in SOLAR and weather in ('rain', 'heavy', 'sand', 'hail', 'snow'):
            add('power', '%s in %s' % (name, weather), 0.5)
        raw_lo = raw_hi = 1
        for x in mods:
            if x.stage == 'raw':
                raw_lo, raw_hi = raw_lo * x.lo, raw_hi * x.hi
        r.power = (int(plo * raw_lo), int(phi * raw_hi))

        # base power modifiers
        contact = bool(m['flags'] & FLAG_CONTACT)
        secondary = (m['status'] and m['status'] != 8 and m['chance'] > 0) or m['flinch'] > 0 or (
            m['quality'] == 6 and any(c for _, _, c in m['stat_changes'])) or (
            m['quality'] == 7 and any(s > 0 for _, s, _ in m['stat_changes']))
        hits = m['hits']
        if aab == 'technician':
            add('tech', 'Technician (power 60 or less)', 1.5)
        if aab == 'ironfist' and m['flags'] & FLAG_PUNCH:
            add('power', 'Iron Fist (punch)', 1.2, 1.3, note='official 1.2; all 7 Iron Fist hits in the AI vs AI logs '
                'fit 1.3, 3 fit 1.2')
        if aab == 'toughclaws' and cls == PHYSICAL:
            add('power', 'Tough Claws (physical)', 1.3, label=HACK,
                note='"Powers up physical moves" (official: contact moves only); two non-contact Stone Edge hits in '
                'the logs fit only with it')
        if aab == 'strongjaw' and m['flags'] & FLAG_BITE:
            add('power', 'Strong Jaw (bite)', 1.5)
        if aab == 'megalauncher' and key in PULSE:
            add('power', 'Mega Launcher (pulse)', 1.5)
        if aab == 'megalauncher' and key in CANNON:
            r.notes.append('Mega Launcher\'s description says "pulse and cannon moves", but two cannon hits in the logs '
                           '(Vikavolt\'s Flash Cannon and Zap Cannon) show no boost: none applied')
        if aab == 'sharpness' and key in SLICING:
            add('power', 'Sharpness (slicing)', 1.5)
        if aab == 'reckless' and (m['recoil'] < 0 or key in CRASH):
            add('power', 'Reckless (recoil)', 1.2)
        if aab == 'sheerforce' and secondary:
            add('power', 'Sheer Force (secondary effect)', 1.3, note='also no Life Orb recoil')
        if aab == 'sandforce' and weather == 'sand' and mtype in (ROCK, GROUND, STEEL):
            add('power', 'Sand Force', 1.3)
        if aab == 'punkrock' and m['flags'] & FLAG_SOUND:
            add('power', 'Punk Rock (sound)', 1.3)
        if aab == 'flamemane' and mtype == FIRE:
            add('power', 'Flame Mane (Fire)', 1.2, 1.5, HACK, '"Powers up Fire-type moves"; factor unknown')
        if aab == 'stakeout' and switch_in:
            add('atk', 'Stakeout (target switching in)', 2)
        if att.it in TYPE_ITEMS and TYPE_ITEMS[att.it] == mtype:
            add('power', att.item, 1.2)
        if att.it == 'muscleband' and cls == PHYSICAL:
            add('power', 'Muscle Band', 1.1)
        if att.it == 'wiseglasses' and cls == SPECIAL:
            add('power', 'Wise Glasses', 1.1)
        if att.it in ORBS and norm(att.name).startswith(ORBS[att.it][0]) and mtype in ORBS[att.it][1]:
            add('power', att.item, 1.2)
        if eff_id == E['KNOCK_OFF'] and dfn.item:
            add('power', 'Knock Off on a held item', 1.5, note='Gen 6+')
        if dab == 'dryskin' and mtype == FIRE:
            add('power', 'Dry Skin (Fire)', 1.25)
        if dab == 'heatproof' and mtype == FIRE:
            add('power', 'Heatproof (Fire)', 0.5)
        terrain = field.terrain
        if terrain in ('electric', 'grassy', 'psychic') and self.grounded(att) and \
                mtype == {'electric': ELECTRIC, 'grassy': GRASS, 'psychic': PSYCHIC}[terrain]:
            add('power', '%s Terrain' % terrain.capitalize(), 1.3, 1.5,
                note='Gen 7: 1.5, Gen 8+: 1.3; Psychic Terrain hits in the AI vs AI logs fit 1.3 (16 of 17, 4 fit 1.5)')
        if terrain == 'misty' and mtype == DRAGON and self.grounded(dfn):
            add('power', 'Misty Terrain (Dragon on a grounded target)', 0.5)
        if terrain == 'grassy' and key in GRASSY_HALVED and self.grounded(dfn):
            add('power', 'Grassy Terrain (%s)' % name, 0.5)

        # attack and defense stats
        if eff_id == E['BODY_PRESS']:
            a_stat, a_stage, a_key = att.stats['def'], att.boosts.get('def', 0), 'def'
            add('note', 'Body Press: the user\'s Defense', 1)
        elif eff_id == E['FOUL_PLAY']:
            a_stat, a_stage, a_key = dfn.stats['atk'], dfn.boosts.get('atk', 0), 'atk'
            add('note', 'Foul Play: the target\'s Attack and its stages', 1,
                note='the user\'s Attack modifiers still apply, as in Showdown')
        elif cls == PHYSICAL:
            a_stat, a_stage, a_key = att.stats['atk'], att.boosts.get('atk', 0), 'atk'
        else:
            a_stat, a_stage, a_key = att.stats['spa'], att.boosts.get('spa', 0), 'spa'
        if cls == PHYSICAL or eff_id == E['PSYSHOCK']:
            d_stat, d_stage, d_key = dfn.stats['def'], dfn.boosts.get('def', 0), 'def'
            if eff_id == E['PSYSHOCK']:
                add('note', '%s hits Defense' % name, 1)
        else:
            d_stat, d_stage, d_key = dfn.stats['spd'], dfn.boosts.get('spd', 0), 'spd'
        if dab == 'unaware' and a_stage:
            r.notes.append('%s\'s Unaware ignores the attacker\'s %+d (official rule)' % (dfn.name, a_stage))
            a_stage = 0
        if aab == 'unaware' and d_stage:
            r.notes.append('%s\'s Unaware ignores the target\'s %+d (official rule)' % (att.name, d_stage))
            d_stage = 0
        if crit:
            if a_stage < 0:
                r.notes.append('critical hit ignores the attacker\'s %d' % a_stage)
            if d_stage > 0:
                r.notes.append('critical hit ignores the target\'s +%d' % d_stage)
            a_stage, d_stage = max(0, a_stage), min(0, d_stage)

        physical_atk = a_key == 'atk'
        if eff_id != E['BODY_PRESS']:
            if aab in ('hugepower', 'purepower') and physical_atk:
                add('atk', att.ability, 2)
            if aab == 'guts' and att.status and physical_atk:
                add('atk', 'Guts (status)', 1.5)
            if aab == 'quickfeet' and att.status and physical_atk:
                add('atk', 'Quick Feet (status)', 1.2, 1.5, HACK, '"Ups Attack and Speed with a status problem"; '
                    'the Attack factor is unknown')
            if aab == 'hustle' and physical_atk:
                add('atk', 'Hustle', 1.5)
            if aab == 'gorillatctcs' and physical_atk:
                add('atk', 'Gorilla Tactics', 1.5)
            if aab == 'megaclaws' and physical_atk:
                add('atk', 'Mega Claws', 1.3, label=HACK, note='"Ups Attack by 30%"')
            if aab == 'toxicboost' and att.status in ('psn', 'tox') and physical_atk:
                add('atk', 'Toxic Boost', 1.5)
            if aab == 'flareboost' and att.status == 'brn' and not physical_atk:
                add('atk', 'Flare Boost', 1.5, note='one log hit (s031_g1 turn 5, the turn after Flame Orb could first '
                    'burn it) fits no boost')
            if aab == 'solarpower' and weather in ('sun', 'harsh') and not physical_atk:
                add('atk', 'Solar Power (sun)', 1.5)
            if aab == 'orichlcmplse' and weather in ('sun', 'harsh') and physical_atk:
                add('atk', 'Orichalcum Pulse (sun)', 4 / 3, qlo=5461, qhi=5461)
            if aab == 'hadronengine' and terrain == 'electric' and not physical_atk:
                add('atk', 'Hadron Engine (Electric Terrain)', 4 / 3, qlo=5461, qhi=5461)
            if aab == 'defeatist' and att.hp * 2 <= att.maxhp:
                add('atk', 'Defeatist (half HP or less)', 0.5)
            if aab == 'slowstart' and physical_atk:
                add('atk', 'Slow Start (first five turns)', 0.5)
            if aab in PINCH and PINCH[aab] == mtype and att.hp * 3 <= att.maxhp:
                add('atk', '%s (a third of HP or less)' % att.ability, 1.5)
            if aab in TYPE_ATTACK_ABILITIES and TYPE_ATTACK_ABILITIES[aab][0] == mtype:
                _, lo, hi = TYPE_ATTACK_ABILITIES[aab]
                add('atk', att.ability, lo, hi, HACK if aab == 'waterbubble' else OFFICIAL,
                    'official 2x; the hack\'s description names only the Fire resistance and the burn immunity'
                    if aab == 'waterbubble' else 'Gen 8: 1.5, Gen 9: 1.3' if lo != hi else '')
            if 'flashfire' in att.flags and aab == 'flashfire' and mtype == FIRE:
                add('atk', 'Flash Fire (activated)', 1.5)
            if att.it == 'choiceband' and physical_atk:
                add('atk', 'Choice Band', 1.5)
            if att.it == 'choicespecs' and not physical_atk:
                add('atk', 'Choice Specs', 1.5)
            if att.it == 'lightball' and norm(att.name).startswith('pikachu'):
                add('atk', 'Light Ball (Pikachu)', 2, label=MEASURED, note='measured to work; 2x is the official factor')
            if att.it == 'thickclub' and norm(att.name) in ('cubone', 'marowak') and physical_atk:
                add('atk', 'Thick Club', 2, label=MEASURED, note='measured to work; 2x is the official factor')
            if att.it == 'deepseatooth' and norm(att.name) == 'clamperl' and not physical_atk:
                add('atk', 'Deep Sea Tooth', 2)
        if dab == 'thickfat' and mtype in (FIRE, ICE):
            add('atk', 'Thick Fat (Fire, Ice)', 0.5)
        if dab == 'waterbubble' and mtype == FIRE:
            add('atk', 'Water Bubble (Fire taken)', 0.5)
        if dab == 'purifyngsalt' and mtype == GHOST:
            add('atk', 'Purifying Salt (Ghost)', 0.5)
        if dab == 'tabletsruin' and physical_atk and aab != 'tabletsruin':
            add('atk', 'Tablets of Ruin', 0.75)
        if dab == 'vesselofruin' and not physical_atk and aab != 'vesselofruin':
            add('atk', 'Vessel of Ruin', 0.75)
        if d_key == 'def':
            if dfn.it == 'eviolite' and d.evolves(dfn.sid):
                add('def', 'Eviolite', 1.5)
            if dab == 'furcoat':
                add('def', 'Fur Coat', 2)
            if dab == 'marvelscale' and dfn.status:
                add('def', 'Marvel Scale (status)', 1.5)
            if dab == 'grasspelt' and terrain == 'grassy':
                add('def', 'Grass Pelt', 1.5)
            if weather == 'snow' and ICE in dfn.types:
                add('def', 'snow (Ice type)', 1.5)
            if aab == 'swordofruin' and dab != 'swordofruin':
                add('def', 'Sword of Ruin', 0.75)
        else:
            if dfn.it == 'eviolite' and d.evolves(dfn.sid):
                add('def', 'Eviolite', 1.5)
            if dfn.it == 'assaultvest':
                add('def', 'Assault Vest', 1.5)
            if dab == 'marvelscale' and dfn.status:
                add('def', 'Marvel Scale (status)', 1.5, label=HACK, note='"Ups Defense and Sp. Def" (official: Defense)')
            if weather == 'sand' and ROCK in dfn.types:
                add('def', 'sandstorm (Rock type)', 1.5)
            if dfn.it == 'deepseascale' and norm(dfn.name) == 'clamperl':
                add('def', 'Deep Sea Scale', 2)
            if aab == 'beadsofruin' and dab != 'beadsofruin':
                add('def', 'Beads of Ruin', 0.75)
        if dfn.it == 'eviolite' and not d.evolves(dfn.sid):
            r.notes.append('Eviolite does nothing: %s does not evolve' % dfn.name)

        # after the base damage
        if field.spread and m['target'] in SPREAD_TARGETS:
            add('spread', 'spread move, 2+ targets', 0.75)
        if weather in ('sun', 'harsh') and mtype == FIRE or weather in ('rain', 'heavy') and mtype == WATER:
            add('weather', '%s (%s)' % (weather, TYPES[mtype]), 1.5)
        elif weather == 'sun' and mtype == WATER or weather == 'rain' and mtype == FIRE:
            add('weather', '%s (%s)' % (weather, TYPES[mtype]), 0.5)
        if crit and dab in ('battlearmor', 'shellarmor'):
            r.notes.append('%s blocks critical hits: computed without one' % dfn.ability)
            crit = False
        if crit:
            add('crit', 'critical hit', 1.5, note='Gen 6+ (Gen 5: 2); 20 of the 23 above-range hits in the AI vs AI logs fit '
                '1.5, none fits only 2 except two through resist berries')
        stab = mtype in att.types or aab in ('protean', 'libero')
        if stab:
            add('stab', 'STAB' + (' (Adaptability)' if aab == 'adaptability' else ''), 2 if aab == 'adaptability' else 1.5)
        if att.status == 'brn' and cls == PHYSICAL and aab != 'guts':
            if eff_id == E['FACADE']:
                add('burn', 'burn (Facade)', 0.5, 1, note='Gen 5: halved, Gen 6+: Facade ignores the burn')
            else:
                add('burn', 'burn', 0.5)
        # final modifiers
        screen = None
        if not crit and aab != 'infiltrator':
            if 'auroraveil' in dfn.flags:
                screen = 'Aurora Veil'
            elif cls == PHYSICAL and 'reflect' in dfn.flags:
                screen = 'Reflect'
            elif cls == SPECIAL and 'lightscreen' in dfn.flags:
                screen = 'Light Screen'
        if screen:
            if field.doubles:
                add('final', screen + ' (doubles)', 2 / 3, qlo=2732, qhi=2732)
            else:
                add('final', screen, 0.5)
        if (dab == 'multiscale' or dfn.ab == 'shadowshield') and dfn.hp == dfn.maxhp:
            add('first', '%s (full HP)' % dfn.ability, 0.5, note='first hit only')
        if (dab in ('filter', 'solidrock') or dfn.ab == 'prismarmor') and eff > 1:
            add('final', '%s (super effective)' % dfn.ability, 0.75)
        if dab == 'swarm' and eff > 1:
            add('final', 'Swarm (super effective)', 0.75, label=HACK,
                note='"Reduces damage from supereffective attacks" in this hack; factor assumed as Filter')
        if dab == 'shellarmor' and cls == PHYSICAL:
            add('final', 'Shell Armor (physical)', 0.8, label=HACK,
                note='"cuts physical damage"; 7 physical hits on Slowbro in the logs fit 0.78-0.80')
        if dab == 'icescales' and cls == SPECIAL:
            add('final', 'Ice Scales (special)', 0.5)
        if dab == 'fluffy' and contact:
            add('final', 'Fluffy (contact)', 0.5)
        if dab == 'fluffy' and mtype == FIRE:
            add('final', 'Fluffy (Fire)', 2)
        if dab == 'punkrock' and m['flags'] & FLAG_SOUND:
            add('final', 'Punk Rock (sound taken)', 0.5)
        if 'glaiverush' in dfn.flags:
            add('final', 'Glaive Rush (target used it last turn)', 2,
                note='its user takes double damage until it moves again')
        if aab == 'tintedlens' and eff < 1:
            add('final', 'Tinted Lens (not very effective)', 2)
        if aab == 'neuroforce' and eff > 1:
            add('final', 'Neuroforce (super effective)', 1.25)
        if aab == 'sniper' and crit:
            add('final', 'Sniper (critical hit)', 1.5)
        if att.it == 'expertbelt' and eff > 1:
            add('final', 'Expert Belt (super effective)', 1.2)
        if att.it == 'lifeorb':
            add('final', 'Life Orb', 1.3, qlo=5324, qhi=5324)
        if dfn.it in RESIST_BERRIES and RESIST_BERRIES[dfn.it] == mtype and (eff > 1 or dfn.it == 'chilanberry'):
            if aab == 'unnerve' or aab == 'asone':
                r.notes.append('%s\'s %s stops %s\'s %s' % (att.name, att.ability, dfn.name, dfn.item))
            else:
                hi, note = BERRY_EVIDENCE.get(dfn.it, (1, 'not seen in the logs, where 3 of the 5 berries seen did '
                                                          'nothing'))
                add('first', dfn.item, 0.5, hi, note='official 0.5; ' + note +
                    '; eaten after the hit: pass --d-item none for the next one')

        # hits
        if hits != (1, 1):
            if att.ab == 'skilllink':
                hits = (hits[1], hits[1])
                r.notes.append('Skill Link: always %d hits' % hits[1])
            elif att.it == 'loadeddice' and hits[1] >= 4:
                hits = (4, hits[1])
                r.notes.append('Loaded Dice: 4-%d hits' % hits[1])
        bond = aab == 'parentalbond' and hits == (1, 1) and not (field.spread and m['target'] in SPREAD_TARGETS)
        if bond:
            hits = (2, 2)
            add('second', 'Parental Bond second hit', 0.25, 0.5, note='Gen 7+: 0.25, Gen 6: 0.5; only the second hit')
        r.hits = hits
        if hits[0] == hits[1]:
            r.hit_odds = {hits[0]: 1.0}
        elif hits == (2, 5):
            r.hit_odds = dict(MULTI_HIT_ODDS)
        else:
            r.hit_odds = {k: 1 / (hits[1] - hits[0] + 1) for k in range(hits[0], hits[1] + 1)}
        escalate = key == 'tripleaxel' or key == 'triplekick'

        # rolls: r.rolls for the first use, r.rolls_later for later uses (no Multiscale, the berry eaten, no Sash)
        level_part = 2 * att.level // 5 + 2
        tech = [x for x in mods if x.stage == 'tech']
        tech_used = []

        def hit_rolls(case, i, first):
            bp = plo if case == 0 else phi
            for x in mods:
                if x.stage == 'raw':
                    bp = int(bp * (x.lo if case == 0 else x.hi))
            if escalate:
                bp *= i + 1
            if tech and bp <= 60:
                tech_used.append(i)
            power_qs = [x.qs(case) for x in mods if x.stage == 'power'] + [x.qs(case) for x in tech if bp <= 60] + \
                [x.qs(case) for x in mods if x.stage == 'second' and i == 1]
            bp = max(1, modify(bp, chain(power_qs)))
            A = max(1, modify(staged(a_stat, a_stage), chain([x.qs(case) for x in mods if x.stage == 'atk'])))
            D = max(1, modify(staged(d_stat, d_stage), chain([x.qs(case) for x in mods if x.stage == 'def'])))
            base = level_part * bp * A // D // 50 + 2
            for stg in ('spread', 'weather'):
                for x in mods:
                    if x.stage == stg:
                        base = modify(base, x.qs(case))
            for x in mods:
                if x.stage == 'crit':
                    base = int(base * (x.lo if case == 0 else x.hi))
            finals = chain([x.qs(case) for x in mods if x.stage == 'final' or x.stage == 'first' and first])
            out = []
            for roll in range(85, 101):
                v = base * roll // 100
                for x in mods:
                    if x.stage == 'stab':
                        v = modify(v, x.qs(case))
                for e in eff_parts:
                    if e >= 2:
                        v *= int(e)
                    elif e == 0.5:
                        v //= 2
                    elif e == 0.25:
                        v //= 4
                for x in mods:
                    if x.stage == 'burn':
                        v = modify(v, x.qs(case))
                out.append(max(1, modify(max(1, v), finals)))
            return out
        r.rolls = [[hit_rolls(case, i, i == 0) for i in range(max(hits))] for case in (0, 1)]
        r.rolls_later = [[hit_rolls(case, i, False) for i in range(max(hits))] for case in (0, 1)]
        if tech and not tech_used:
            mods.remove(tech[0])      # Technician applies to the power the move really has (Gen 5)

        # what happens after
        if m['recoil'] < 0 and aab not in ('rockhead', 'magicguard') and key != 'volttackle':
            r.after.append('recoil: %d%% of the damage dealt' % -m['recoil'])
        if key == 'volttackle':
            r.after.append('Volt Tackle has no recoil here (measured in this hack; the move data has none)')
        if m['recoil'] > 0:
            r.after.append('drain: the user heals %d%% of the damage dealt' % m['recoil'])
        if att.it == 'lifeorb' and aab != 'magicguard' and not (aab == 'sheerforce' and secondary):
            r.after.append('Life Orb: the user loses %d HP (a tenth)' % (att.maxhp // 10))
        if dfn.it == 'rockyhelmet' and contact:
            r.after.append('Rocky Helmet: the attacker loses %d HP (a sixth; measured in this hack)' % (att.maxhp // 6))
        if dfn.ab == 'battlearmor' and contact:
            r.after.append('Battle Armor hurts the attacker on contact in this hack (amount unknown)')
        if dfn.ab in ('roughskin', 'ironbarbs') and contact:
            r.after.append('%s: the attacker loses %d HP (an eighth)' % (dfn.ability, att.maxhp // 8))
        if dfn.it == 'weakpolicy' and eff > 1:
            r.after.append('Weakness Policy: if the target survives, +2 Attack and +2 Sp. Atk')
        if m['accuracy'] < 100:
            r.notes.append('accuracy %d%%: KO chances assume the move hits' % m['accuracy'])
        if dfn.item_note:
            r.notes.append(dfn.item_note + (' (%s)' % LABELS[dfn.item_label] if dfn.item_label in LABELS else ''))
        if att.item_note:
            r.notes.append(att.item_note + (' (%s)' % LABELS[att.item_label] if att.item_label in LABELS else ''))
        for mon in (att, dfn):
            if UNMODELED_ABILITIES.get(mon.ab):
                r.notes.append('not modeled: %s\'s %s' % (mon.name, UNMODELED_ABILITIES[mon.ab]))
        if dfn.ab == 'stamina' or dfn.ab == 'weakarmor':
            r.notes.append('%s changes %s\'s Defense after each hit: pass the stage with --d-boost' % (dfn.ability, dfn.name))
        r.ko = self.ko_chances(r)
        return r

    def ko_chances(self, r, max_uses=4):
        """[(uses, chance with low factors, chance with high factors)] that `uses` uses of the move KO from the
        defender's current HP. Focus Sash and Sturdy keep the defender at 1 HP from full HP once; Multiscale and a
        resist berry only act on the first hit."""
        dfn = r.dfn
        hp = dfn.hp
        sash = dfn.hp == dfn.maxhp and (dfn.it == 'focussash' or dfn.ab == 'sturdy' and r.att.ab not in MOLD_BREAKERS)
        out = []
        dists = []
        for case in (0, 1):
            first_use, later_use = {}, {}
            for k, p in r.hit_odds.items():
                f = {0: 1.0}
                lat = {0: 1.0}
                for i in range(k):
                    hit = uniform(r.rolls[case][i])
                    if i == 0 and sash:
                        capped = {}
                        for v, pr in hit.items():
                            capped[min(v, hp - 1)] = capped.get(min(v, hp - 1), 0) + pr
                        hit = capped
                    f = dist_add(f, hit)
                    lat = dist_add(lat, uniform(r.rolls_later[case][i]))
                for v, pr in f.items():
                    first_use[v] = first_use.get(v, 0) + pr * p
                for v, pr in lat.items():
                    later_use[v] = later_use.get(v, 0) + pr * p
            dists.append((first_use, later_use))
        totals = [dict(dists[0][0]), dict(dists[1][0])]
        for n in range(1, max_uses + 1):
            if n > 1:
                totals = [dist_add(totals[c], dists[c][1]) for c in (0, 1)]
            ch = [sum(p for v, p in totals[c].items() if v >= hp) for c in (0, 1)]
            out.append((n, ch[0], ch[1]))
            if min(ch) >= 0.9999:
                break
            if n == 1 and sash and min(ch) == 0 and r.hi >= hp:
                r.notes.append('%s keeps %s at 1 HP from full HP (%s)' % (
                    dfn.item if dfn.it == 'focussash' else 'Sturdy', dfn.name,
                    LABELS[MEASURED] if dfn.it == 'focussash' else LABELS[OFFICIAL]))
        return out

# --- battle logs
HEADER = re.compile(r'^  (.+?)\s+L(\d+) (.+?)\s+@ (.+?)\s{2,}(.+?)(?:\s+\((\w+)\))?\s*$')   # random teams: no nature
HP_LINE = re.compile(r'^  (ADVANCED|ORIGINAL)  (.+?)\s+(\d+)/(\d+) ')
# self-play logs (aivsai --self) name the sides TRAINER/PLAYER; read as ADVANCED/ORIGINAL (the same columns)
SELF_LABELS = ((re.compile(r'^TRAINER SIDE team: '), 'ADVANCED team: '), (re.compile(r'^PLAYER SIDE team: '), 'ORIGINAL team: '),
               (re.compile(r'^  TRAINER   '), '  ADVANCED  '), (re.compile(r'^  PLAYER    '), '  ORIGINAL  '),
               # tools/aiplay.py: a person plays the player's side, named HUMAN
               (re.compile(r'^HUMAN team: '), 'ORIGINAL team: '), (re.compile(r'^  HUMAN     '), '  ORIGINAL  '))
CUT = re.compile(r'^(.*?) \((\d+) of (\d+): members ([\d, ]+)\)$')


def log_lines(path):
    for line in open(path, encoding='utf-8'):
        for rx, new in SELF_LABELS:
            line = rx.sub(new, line, count=1)
        yield line


def log_header(path):
    """{'ADVANCED': {'name': trainer, 'mons': [(species, level, ability, item, moves, nature)]}, 'ORIGINAL': ...}"""
    sides, cur = {}, None
    for line in log_lines(path):
        mt = re.match(r'(ADVANCED|ORIGINAL) team: (.*)', line)
        if mt:
            cur = mt.group(1)
            sides[cur] = {'name': mt.group(2).strip(), 'mons': []}
            continue
        mh = HEADER.match(line.rstrip('\n'))
        if mh and cur:
            sp, lv, ab, it, mv, nat = mh.groups()
            sides[cur]['mons'].append((sp.strip(), int(lv), ab.strip(), it.strip(), [x.strip() for x in mv.split(',')], nat))
        if line.startswith('==='):
            break
    if not sides:
        raise ValueError('%s has no team header (live logs have none: use --trainer ID for each side)' % path)
    return sides


@functools.lru_cache(None)
def _trainer_teams(rom):
    return aiteams.trainer_teams(rom)


def read_log(calc, path):
    """Both teams of a battle log as Mons: species, ability, item, moves, nature and level from the header, EVs and
    IVs from the trainer's ROM record (tools/aiteams.py); a random team (no record) has no EVs and IVs 31.
    Max HP is checked against the HP the log shows."""
    d = calc.d
    teams, warnings = {}, []
    def moves_of(x):
        return [norm(str(d.move_name[d.id('move', mv)])) for mv in x['moves']]

    def same_set(x, m):
        return norm(d.species_name[d.id('species', x['species'])]) == norm(m[0]) and moves_of(x) == [norm(mv) for mv in m[4]]

    for side, s in log_header(path).items():
        spec, name, slots = None, s['name'], None
        cut = CUT.match(name)
        if cut:      # a handicap run's team: "Name (4 of 6: members 1, 2, 3, 4)"
            name, slots = cut.group(1), [int(x) - 1 for x in cut.group(4).split(',')]
        if name.startswith('Mixed'):      # aivsai --teams mixed: each member is a trainer Pokemon with its own record
            members = [x for t in _trainer_teams(calc.rom) for x in t['team']]
            spec = []
            for m in s['mons']:
                found = [x for x in members if same_set(x, m)]
                spec.append(found[0] if found else {'evs': {}, 'ivs': 31})
                if not found:
                    warnings.append('%s %s not found among the trainer Pokemon: EVs 0 and IVs 31 assumed' % (side, m[0]))
        elif not name.startswith('Random'):
            cands = [t for t in _trainer_teams(calc.rom) if t['name'] == name and
                     len(t['team']) > max(slots or [len(s['mons']) - 1]) and
                     all(same_set(t['team'][i], m) for i, m in zip(slots or range(len(s['mons'])), s['mons']))]
            if cands:
                spec = [cands[0]['team'][i] for i in (slots or range(len(s['mons'])))]
            else:
                warnings.append('%s team %r not found among the trainer teams: EVs 0 and IVs 31 assumed' % (side, s['name']))
        mons = []
        for k, (sp, lv, ab, it, mv, nat) in enumerate(s['mons']):
            evs, ivs = (spec[k]['evs'], spec[k]['ivs']) if spec else ({}, 31)
            mons.append(Mon(calc, sp, level=lv, ability=ab if ab != '-' else None, item=it, nature=nat, evs=evs, ivs=ivs,
                            moves=mv, side=side))
        teams[side] = mons
    seen = {}
    for line in log_lines(path):
        mh = HP_LINE.match(line)
        if mh:
            seen.setdefault((mh.group(1), norm(mh.group(2))), int(mh.group(4)))
    for side, mons in teams.items():
        for mon in mons:
            hp = seen.get((side, norm(mon.name)))
            if hp is not None and hp != mon.maxhp:
                warnings.append('%s %s: the log shows %d max HP, the spec gives %d' % (side, mon.name, hp, mon.maxhp))
    for w in warnings:
        print('warning: ' + w, file=sys.stderr)
    return teams


def trainer_mons(calc, tid, level=None):
    team, why = aiteams.trainer_team(tid, calc.rom)
    if why:
        raise ValueError('trainer %d: %s (%s)' % (tid, why[0], why[1]))
    return team['name'], [Mon(calc, s['species'], level=level or s['level'], ability=s['ability'], item=s['item'],
                              nature=s['nature'], evs=s['evs'], ivs=s['ivs'], moves=s['moves'], side=team['name'])
                          for s in team['team']]


# --- validation against battle logs
TURN_LINE = re.compile(r'^--- Turn (\d+) ')
ACT_LINE = re.compile(r'^  (ADVANCED|ORIGINAL)  (.+?) -> (.+) on (.+?)\s*$')
SWITCH_LINE = re.compile(r'^  (ADVANCED|ORIGINAL)  (.+?) -> switch to (.+?)\s*$')
FAINT_LINE = re.compile(r'^  (ADVANCED|ORIGINAL)  (.+?) fainted\s*$')
REPLACE_LINE = re.compile(r'^  (ADVANCED|ORIGINAL)  (.+?) out, (.+?) in\s*$')
OTHER = {'ADVANCED': 'ORIGINAL', 'ORIGINAL': 'ADVANCED'}
SIDES = ('ADVANCED', 'ORIGINAL')

# What the log does not show makes a hit unusable for validation. These lists keep the validator conservative:
# a hit is compared only when every condition that changes it is known from the log.
PROTECTS = {'protect', 'detect', 'kingsshield', 'spikyshield', 'banefulbunkr', 'obstruct', 'silktrap', 'burningbulwrk',
            'banefulbunker', 'burningbulwark', 'maxguard'}
NEUTRAL_STATUS = {'protect', 'detect', 'endure', 'destinybond', 'perishsong', 'taunt', 'encore', 'disable', 'torment',
                  'imprison', 'teleport', 'helpinghand', 'followme', 'ragepowder', 'magiccoat', 'snatch', 'spite',
                  'grudge', 'lockon', 'mindreader', 'foresight', 'odorsleuth', 'miracleeye', 'meanlook', 'block',
                  'spiderweb', 'roar', 'whirlwind', 'recover', 'roost', 'slackoff', 'synthesis', 'moonlight',
                  'morningsun', 'softboiled', 'milkdrink', 'healorder', 'shoreup', 'lifedew', 'rest', 'wish',
                  'substitute', 'splash', 'celebrate', 'healbell', 'aromatherapy', 'refresh', 'charge', 'stockpile',
                  'laserfocus', 'focusenergy', 'tailwind', 'luckychant', 'safeguard', 'mist', 'quickguard',
                  'wideguard', 'craftyshield', 'matblock', 'camouflage', 'conversion', 'conversion2', 'reflecttype',
                  'soak', 'magicpowder', 'forestscurse', 'trickortreat', 'sketch', 'mimic', 'metronome',
                  'sleeptalk', 'naturepower', 'copycat', 'mefirst', 'assist', 'transform', 'healpulse',
                  'floralhealing', 'junglehealng', 'lunarblessng', 'aquaring', 'ingrain', 'leechseed', 'yawn',
                  'nightmare', 'curse', 'stealthrock', 'spikes', 'toxicspikes', 'stickyweb', 'reflect', 'lightscreen',
                  'auroraveil', 'raindance', 'sunnyday', 'sandstorm', 'hail', 'snowscape', 'electerrain',
                  'grassterrain', 'psychterrain', 'mistyterrain', 'haze', 'defog', 'courtchange', 'tidyup',
                  'painsplit', 'bellydrum', 'shellsmash', 'memento', 'healingwish', 'lunardance', 'batonpass',
                  'trick', 'switcheroo', 'trickroom', 'gravity', 'magicroom', 'wonderroom', 'attract'}
UNSURE_ALL_MOVES = {'psychup', 'powertrick', 'powerswap', 'guardswap', 'heartswap', 'speedswap', 'topsyturvy',
                    'spectrlthief', 'skillswap', 'roleplay', 'entrainment', 'simplebeam', 'worryseed', 'gastroacid',
                    'acupressure', 'swagger', 'flatter', 'strengthsap', 'venomdrench', 'captivate', 'geomancy',
                    'meteorbeam', 'skullbash', 'filletaway', 'clangoroussoul', 'noretreat', 'stuffcheeks',
                    'shedtail', 'transform', 'lunardance', 'recycle', 'corrosivegas', 'magicroom', 'wonderroom',
                    'powersplit', 'guardsplit', 'clearsmog', 'spectralthief'}
SELF_HP = {'substitute', 'bellydrum', 'painsplit', 'explosion', 'selfdestruct', 'memento', 'healingwish', 'lunardance',
           'finalgambit', 'mindblown', 'steelbeam', 'chloroblast', 'struggle', 'filletaway', 'clangoroussoul',
           'shedtail', 'leechseed', 'ingrain', 'aquaring', 'curse', 'wish', 'rest', 'mistyexplosn'}
RECHARGE = {'hyperbeam', 'gigaimpact', 'blastburn', 'hydrocannon', 'rockwrecker', 'roaroftime', 'prismaticlsr',
            'eternabeam', 'meteorassault'}
ITEM_TAKERS = {'knockoff', 'thief', 'covet', 'bugbite', 'pluck', 'incinerate', 'trick', 'switcheroo', 'fling',
               'corrosivegas', 'recycle'}
HP_BERRIES = {'sitrusberry', 'oranberry', 'figyberry', 'wikiberry', 'magoberry', 'aguavberry', 'iapapaberry',
              'enigmaberry', 'berryjuice'}
UNSURE_ITEMS = {'starfberry', 'custapberry', 'metronome', 'mirrorherb', 'lansatberry'}
CONTACT_HURT = {'roughskin', 'ironbarbs'}
STATUS_ON_CONTACT = {'flamebody': 'brn', 'poisonpoint': 'psn', 'effectspore': 'psn', 'static': 'par',
                     'toxicchain': 'tox', 'poisontouch': 'psn'}
# Abilities whose effects the log hides (boosts on hits or KOs, type changes, absorbed moves, disguises...):
# hits by or on their holders are not compared.
HIDDEN_ABILITIES = {
    'angerpoint', 'angershell', 'cottondown', 'gooey', 'tanglinghair', 'mummy', 'lingerngarma', 'wanderngsprt',
    'seedsower', 'sandspit', 'electromorph', 'windpower', 'toxicdebris', 'colorchange', 'protean', 'libero',
    'illusion', 'imposter', 'beastboost', 'asone', 'soulheart', 'suprmoverlrd', 'moody', 'slowstart', 'truant',
    'disguise', 'iceface', 'opportunist', 'costar', 'protosynthss', 'quarkdrive', 'zerotohero', 'commander', 'forecast',
    'stancechange', 'zenmode', 'schooling', 'shieldsdown', 'powrconstrct', 'battlebond', 'gulpmissile', 'hungerswitch',
    'mimicry', 'trace', 'receiver', 'powrofalchmy', 'symbiosis', 'pickpocket', 'magician', 'harvest', 'cudchew',
    'ripen', 'deserthawk', 'analytic', 'neutralgas', 'curiousmedcn', 'embodyaspect',
    'terashift', 'terashell', 'teraformzero', 'poisnpuppetr'}
# Intimidate's effect on these changed between generations or triggers something the log hides.
INTIMIDATE_UNSURE = {'innerfocus', 'oblivious', 'owntempo', 'scrappy', 'guarddog', 'mirrorarmor', 'defiant',
                     'competitive', 'contrary', 'simple', 'rattled'}
INTIMIDATE_BLOCK = {'clearbody', 'whitesmoke', 'fullmetalbdy', 'hypercutter'}
# Absorbing abilities: hit by the type, they raise a stat (or activate) instead.
ABSORB = {'sapsipper': (GRASS, 'atk'), 'lightningrod': (ELECTRIC, 'spa'), 'stormdrain': (WATER, 'spa'),
          'motordrive': (ELECTRIC, 'spe'), 'flashfire': (FIRE, 'flashfire'), 'wellbakedbdy': (FIRE, 'def'),
          'eartheater': (GROUND, None), 'blazingawe': (FIRE, 'spa'), 'waterabsorb': (WATER, None),
          'voltabsorb': (ELECTRIC, None), 'dryskin': (WATER, None)}
# Boosts on taking a hit: ability -> (types that trigger it, or 'physical' / None for any), stage changes.
ON_HIT = {'stamina': (None, {'def': 1}), 'weakarmor': ('physical', {'def': -1, 'spe': 1}),
          'justified': ({DARK}, {'atk': 1}), 'watercompact': ({WATER}, {'def': 2}),
          'steamengine': ({FIRE, WATER}, {'spe': 6}), 'thermalexchg': ({FIRE}, {'atk': 1}),
          'rattled': ({BUG, DARK, GHOST}, {'spe': 1})}
ON_KO = {'moxie': 'atk', 'chillngneigh': 'atk', 'grimneigh': 'spa'}
ON_HIT_ITEMS = {'keeberry': ('physical', 'def'), 'marangaberry': ('special', 'spd'), 'absorbbulb': ({WATER}, 'spa'),
                'cellbattery': ({ELECTRIC}, 'atk'), 'luminousmoss': ({WATER}, 'spd'), 'snowball': ({ICE}, 'atk')}
PINCH_BERRIES = {'liechiberry': 'atk', 'ganlonberry': 'def', 'petayaberry': 'spa', 'apicotberry': 'spd',
                 'salacberry': 'spe'}
STATUS_BLOCK = {'clearbody', 'whitesmoke', 'fullmetalbdy', 'goodasgold', 'ninjabond'}


def parse_turns(path):
    turns, cur = [], None
    for raw in log_lines(path):
        line = raw.rstrip('\n')
        mt = TURN_LINE.match(line)
        if mt:
            cur = {'n': int(mt.group(1)), 'hp': {}, 'act': {}, 'switch': {}, 'faint': set(), 'replace': {}}
            turns.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith('==='):
            cur = None
            continue
        for rx, kind in ((SWITCH_LINE, 'switch'), (ACT_LINE, 'act'), (FAINT_LINE, 'faint'), (REPLACE_LINE, 'replace')):
            mm = rx.match(line)
            if mm:
                if kind == 'faint':
                    cur['faint'].add(mm.group(1))
                elif kind == 'act':
                    cur['act'][mm.group(1)] = (mm.group(2).strip(), mm.group(3).strip(), mm.group(4).strip())
                else:
                    cur[kind][mm.group(1)] = (mm.group(2).strip(), mm.group(3).strip())
                break
        else:
            mm = HP_LINE.match(line)
            if mm:
                cur['hp'][mm.group(1)] = (mm.group(2).strip(), int(mm.group(3)), int(mm.group(4)))
    return turns


class _Poke:
    """What the validator knows about one Pokémon across a battle."""

    def __init__(self, mon):
        self.mon = mon
        self.hp, self.hp_known = mon.maxhp, True
        self.status, self.maybe = None, set()
        self.item = 'held' if mon.item else 'none'
        self.stint()

    def stint(self):
        self.boosts, self.unsure, self.flags = {}, set(), set()
        self.entered, self.confused_until, self.toxic_n = None, -1, 0

    def able(self, n):
        return not (self.maybe & {'slp', 'frz', 'par'} or self.status in ('slp', 'frz', 'par') or
                    self.confused_until >= n or 'attract' in self.flags or 'recharge' in self.flags)


@dataclass
class Observation:
    log: str
    turn: int
    attacker: str
    move: str
    defender: str
    observed: list          # possible damages of the hit (alternatives for unknown same-turn chip)
    lo: int = 0
    hi: int = 0
    verdict: str = ''
    detail: str = ''
    alt_used: str = ''
    result: object = None


def _sure_first(calc, a, b, ma, mb, field):
    """True when a surely moves before b, False when surely after, None when open (unknown paralysis included)."""
    outs = set()
    for pa in ([a.status] if 'par' not in a.maybe_ else [None, 'par']):
        for pb in ([b.status] if 'par' not in b.maybe_ else [None, 'par']):
            sa, sb = a.status, b.status
            a.status, b.status = pa, pb
            outs.add(calc.order(a, b, field, ma, mb)[1])
            a.status, b.status = sa, sb
    if outs == {1}:
        return True
    if outs == {-1}:
        return False
    return None


class Sweep:
    """Walks one battle log and collects the hits it can compare (see validate())."""

    def __init__(self, calc, path, ability_weather=5):
        self.calc, self.path, self.d = calc, path, calc.d
        self.ability_weather = ability_weather      # None: unknown (beyond 5 turns is unsure), 5, or 'inf'
        self.teams = read_log(calc, path)
        self.obs, self.skips, self.skip_log = [], {}, []

    def reset(self):
        self.pokes = {(s, norm(m.name)): _Poke(m) for s, mons in self.teams.items() for m in mons}
        self.active = {}
        self.weather = None      # dict kind, start, end (inclusive, None = while it lasts), unsure_from
        self.terrain = None
        self.screens = {s: {} for s in SIDES}   # kind -> (start, end)
        self.tailwind = {s: None for s in SIDES}
        self.hazards = {s: set() for s in SIDES}
        self.wish = {}
        self.rooms = {}          # trickroom / gravity / magicroom / wonderroom -> end turn
        self.side_unsure = {s: False for s in SIDES}   # Baton Pass, Healing Wish: the next entrant is not known

    def skip(self, why):
        self.skips[why] = self.skips.get(why, 0) + 1
        self.skip_log.append((getattr(self, '_cur', None), why))

    def key(self, side, sp):
        return (side, norm(sp))

    # field state
    def weather_at(self, n):
        """(kind or None, sure, chip_sure) for turn n."""
        w = self.weather
        if not w:
            return None, True, True
        if w['end'] is not None and n > w['end']:
            return None, True, True
        sure = not (w.get('unsure_turn') == n) and not (w.get('unsure_from') is not None and n >= w['unsure_from'])
        chip = sure and not (w['end'] is not None and n == w['end']) and not (
            w.get('unsure_from') is not None and n >= w['unsure_from'] - 1)
        for p in (self.pokes.get(k) for k in self.active.values()):
            if p and p.mon.ab in NO_WEATHER:
                return None, True, True
        return w['kind'], sure, chip

    def terrain_at(self, n):
        t = self.terrain
        if not t or (t['end'] is not None and n > t['end']):
            return None, True
        return t['kind'], t.get('unsure_turn') != n and not (t['end'] is not None and n == t['end'] + 1)

    def set_weather(self, kind, n, src, holder=None, unsure_turn=None):
        w = self.weather
        if w and w['kind'] in ('harsh', 'heavy') and kind not in ('harsh', 'heavy') and self.weather_at(n)[0]:
            return
        if w and src == 'ability' and w['kind'] == kind and self.ability_weather != 'inf' and \
                (w['end'] is None or n <= w['end']):
            return      # Gen 6+: an ability does not renew the weather already up (s014_g0 turn 9 shows it)
        rock = {'rain': 'damprock', 'sun': 'heatrock', 'sand': 'smoothrock', 'hail': 'icyrock', 'snow': 'icyrock'}
        dur = 8 if holder is not None and holder.mon.it == rock.get(kind) else 5
        nw = {'kind': kind, 'start': n, 'end': n + dur - 1, 'unsure_turn': unsure_turn, 'unsure_from': None,
              'src': holder.mon.ab if holder is not None and src == 'ability' else src}
        if kind in ('harsh', 'heavy'):
            nw['end'], nw['holder'] = None, holder
        elif src == 'ability':
            if self.ability_weather == 'inf':
                nw['end'] = None
            elif self.ability_weather is None:
                nw['end'], nw['unsure_from'] = None, n + dur
        self.weather = nw

    def enter(self, side, key, n, mid_turn=False, fresh=True):
        """A Pokémon comes in: entry abilities. mid_turn: a pivot the log does not show (timing unknown).
        fresh=False: its stint was already started (two Pokémon entering together)."""
        p = self.pokes[key]
        if fresh:
            self.start_stint(side, key, n)
        if self.side_unsure[side]:
            p.unsure |= {'atk', 'def', 'spa', 'spd', 'spe', 'hp'}
            self.side_unsure[side] = False
        if 'toxicspikes' in self.hazards[side] and self.calc.grounded(p.mon) and not _status_immune(p.mon, 'psn') \
                and p.status is None:
            p.maybe.add('psn')
        foe = self.pokes.get(self.active.get(OTHER[side]))
        ab = p.mon.ab
        if ab in ('intimidate', 'blazingawe') and foe:
            if foe.mon.ab in INTIMIDATE_BLOCK:
                pass
            elif mid_turn or foe.mon.ab in INTIMIDATE_UNSURE or foe.mon.it == 'adrenalineorb':
                foe.unsure |= {'atk', 'spe'} if foe.mon.ab != 'mirrorarmor' else {'atk'}
                if foe.mon.ab == 'mirrorarmor':
                    p.unsure.add('atk')
            else:
                _boost(foe, {'atk': -1}, True, by_foe=True)
        if ab == 'download' and foe:
            df = staged(foe.mon.stats['def'], foe.boosts.get('def', 0))
            sd = staged(foe.mon.stats['spd'], foe.boosts.get('spd', 0))
            if {'def', 'spd'} & foe.unsure or mid_turn:
                p.unsure |= {'atk', 'spa'}
            else:
                _boost(p, {'atk' if df < sd else 'spa': 1}, True)
        if ab in ('speedboost', 'unburden'):
            p.unsure.add('spe')
        if ab in WEATHER_ABILITIES:
            kind = WEATHER_ABILITIES[ab][0]
            self.set_weather(kind, n, 'ability', p, unsure_turn=n if mid_turn else None)
        if ab in TERRAIN_ABILITIES:
            dur = 8 if p.mon.it == 'terrainextender' else 5
            self.terrain = {'kind': TERRAIN_ABILITIES[ab], 'start': n, 'end': n + dur - 1,
                            'unsure_turn': n if mid_turn else None}
        if ab == 'aurorashine':
            for s in SIDES:
                self.screens[s]['unsure'] = (n, n + 8)

    def start_stint(self, side, key, n):
        p = self.pokes[key]
        old = self.active.get(side)
        if old and old != key:
            self.leave(side)
        p.stint()
        p.entered = n
        self.active[side] = key

    def leave(self, side):
        key = self.active.get(side)
        if not key:
            return
        p = self.pokes[key]
        if p.mon.ab == 'regenerator':
            p.hp_known = False
        if p.mon.ab == 'naturalcure':
            p.status, p.maybe = None, set()
        w = self.weather
        if w and w.get('holder') is p:
            self.weather = None
        p.stint()

    def residual_context(self, side, n):
        """What decides a Pokémon's end-of-turn HP change: a quiet turn's change applies to a hit with the same."""
        key = self.active.get(side)
        if not key:
            return None
        p = self.pokes[key]
        wk, wsure, wchip = self.weather_at(n)
        if not wchip:
            return None
        return (key, p.entered, wk, p.item, p.status, frozenset(p.maybe),
                frozenset(p.flags & {'seeded', 'bound', 'regen', 'sub'}), self.wish.get(side))

    def note_quiet(self, t, nxt, side, switched_in):
        """Record the end-of-turn HP change of a Pokémon nothing hit this turn and that did not change its own HP."""
        key = self.active.get(side)
        if not key or side in switched_in or side in t['faint'] or side not in nxt['hp'] or side not in t['hp'] or \
                self.key(side, nxt['hp'][side][0]) != key or self.key(side, t['hp'][side][0]) != key:
            return
        o = OTHER[side]
        oact, own = t['act'].get(o), t['act'].get(side)
        if oact is None and o not in switched_in:
            return
        try:
            om = self.d.move(oact[1]) if oact else None
            mm = self.d.move(own[1]) if own else None
        except KeyError:
            return
        if om and (om['class'] != STATUS or norm(oact[1]) in SELF_HP or om['status'] in (4, 5, 8, 18)):
            return
        if mm and (mm['heal'] or mm['recoil'] or norm(own[1]) in SELF_HP or
                   mm['class'] != STATUS and self.pokes[key].mon.it in ('lifeorb', 'shellbell')):
            return
        cur, mx = t['hp'][side][1], t['hp'][side][2]
        if nxt['hp'][side][1] >= mx or cur >= mx:
            return
        ctx = self.residual_context(side, t['n'])
        if ctx:
            self.quiet_found.setdefault(ctx, []).append(nxt['hp'][side][1] - cur)

    def run(self):
        turns = parse_turns(self.path)
        self.quiet_found = {}
        self.walk(turns, collect=True)       # first pass: end-of-turn changes on quiet turns
        self.quiet = self.quiet_found
        self.walk(turns, collect=False)
        return self

    def walk(self, turns, collect):
        self.reset()
        prev = None
        for k, t in enumerate(turns):
            nxt = turns[k + 1] if k + 1 < len(turns) else None
            n = t['n']
            # 1. who is on the field at the start of the turn
            entering = []
            for side in SIDES:
                if side not in t['hp']:
                    continue
                sp, cur, mx = t['hp'][side]
                key = self.key(side, sp)
                if key not in self.pokes:
                    self.skip('species not in the team header')
                    continue
                if self.active.get(side) != key:
                    how = 'lead' if prev is None else 'replace' if norm(prev['replace'].get(side, ('', ''))[1]) == key[1] \
                        else 'pivot'
                    entering.append((side, key, how))
                self.pokes[key].hp, self.pokes[key].hp_known = cur, True
            first = True
            if len(entering) == 2:
                for e in entering:
                    self.pokes[e[1]].mon.maybe_ = self.pokes[e[1]].maybe
                first = _sure_first(self.calc, self.pokes[entering[0][1]].mon, self.pokes[entering[1][1]].mon,
                                    None, None, Field())
                if first is False:
                    entering.reverse()       # the faster one's entry ability goes first, the slower one's lasts
            for side, key, how in entering:      # both are on the field before either entry ability acts
                self.start_stint(side, key, n)
            for side, key, how in entering:
                self.enter(side, key, n, mid_turn=(how == 'pivot'), fresh=False)
            if first is None and sum(self.pokes[e[1]].mon.ab in WEATHER_ABILITIES for e in entering) == 2:
                self.weather = {'kind': None, 'start': n, 'end': None, 'unsure_from': n}
            # 2. hard switches happen before moves
            switched_in = {}
            for side, (old, new) in t['switch'].items():
                key = self.key(side, new)
                if key not in self.pokes:
                    continue
                self.enter(side, key, n)
                switched_in[side] = key
            if nxt is not None:
                for side in SIDES:
                    if collect:
                        self.note_quiet(t, nxt, side, switched_in)
                    else:
                        self.evaluate(t, nxt, side, switched_in)
                self.effects(t, nxt, switched_in)
            prev = t

    def evaluate(self, t, nxt, side, switched_in):
        """Compare side's damaging move this turn with the defender's HP change, if the conditions are known."""
        if side not in t['act']:
            return
        usp, mv, _ = t['act'][side]
        n, dside = t['n'], OTHER[side]
        self._cur = (n, usp, mv)
        akey = self.key(side, usp)
        if self.active.get(side) != akey or side in switched_in:
            return self.skip('attacker not the active Pokémon')
        try:
            m = self.d.move(mv)
        except KeyError:
            return self.skip('move name unknown')
        if m['class'] == STATUS:
            return
        mkey = norm(self.d.move_name[m['id']])
        dkey = self.active.get(dside)
        if not dkey:
            return self.skip('no defender')
        A, D = self.pokes[akey], self.pokes[dkey]
        if dside in t['faint']:
            return self.skip('defender fainted (damage capped)')
        if dside not in nxt['hp'] or self.key(dside, nxt['hp'][dside][0]) != dkey:
            return self.skip('defender left the field (pivot, forced switch)')
        if dside in switched_in:
            if not D.hp_known or self.hazards[dside] - {'stickyweb'}:
                return self.skip('switch-in with unknown HP or entry hazards')
            before = D.hp
        else:
            before = t['hp'][dside][1]
        after = nxt['hp'][dside][1]
        if after <= 1:
            return self.skip('defender left at 1 HP or less (Sash, Sturdy)')
        dact = t['act'].get(dside)
        dmove = None
        if dact and dside not in switched_in:
            try:
                dmove = self.d.move(dact[1])
            except KeyError:
                return self.skip('move name unknown')
        dmkey = norm(self.d.move_name[dmove['id']]) if dmove else ''
        A.mon.maybe_, D.mon.maybe_ = A.maybe, D.maybe
        for p in (A, D):
            if p.mon.ab in HIDDEN_ABILITIES:
                return self.skip('an ability the log hides (%s)' % p.mon.ability)
            if p.mon.it in UNSURE_ITEMS and p.item == 'held':
                return self.skip('an item the log hides (%s)' % p.mon.item)
            if p.item == 'unsure':
                return self.skip('item may be gone')
            if 'hp' in p.unsure:
                return self.skip('passed boosts (Baton Pass) or unknown entrant')
        for rk, end in self.rooms.items():
            if n <= end:
                return self.skip('%s in effect' % rk)
        if mkey in VARIABLE_NOTES or mkey in FIXED_NOTES or m['effect'] in (E['ERUPTION'], E['REVERSAL']) or \
                mkey in ('dragonenergy', 'wringout', 'crushgrip', 'hardpress', 'pursuit', 'brine'):
            return self.skip('power depends on battle state')
        # D's own HP changes this turn
        if dmove and (dmkey in SELF_HP or dmove['heal'] or dmove['recoil'] != 0):
            return self.skip('defender changed its own HP')
        if dmove and dmove['class'] != STATUS and D.mon.it == 'lifeorb' and D.mon.ab != 'magicguard':
            return self.skip('defender Life Orb recoil')
        if dmove and dmove['flags'] & FLAG_CONTACT and (A.mon.it == 'rockyhelmet' or A.mon.ab in CONTACT_HURT):
            return self.skip('defender hurt by contact')
        if 'transformed' in A.flags | D.flags or (dact and norm(dact[1]) == 'transform'):
            return self.skip('Transform (stats and types copied)')
        if D.flags & {'seeded', 'bound', 'sub', 'regen'} or 'seeded' in A.flags or self.wish.get(dside) in (n, n - 1):
            return self.skip('residual HP effect (Leech Seed, binding, Substitute, Ingrain, Wish)')
        if D.confused_until >= t['n']:
            return self.skip('defender may be confused (self-hit)')
        # stat stages and statuses
        if m['effect'] == E['BODY_PRESS']:
            a_stat = 'def'
        elif m['effect'] == E['FOUL_PLAY']:
            a_stat = None
        else:
            a_stat = 'atk' if m['class'] == PHYSICAL else 'spa'
        d_stat = 'def' if m['class'] == PHYSICAL or m['effect'] == E['PSYSHOCK'] else 'spd'
        if (a_stat and a_stat in A.unsure) or d_stat in D.unsure or (a_stat is None and 'atk' in D.unsure):
            return self.skip('stat stages unknown')
        if m['type'] == FIRE and 'flashfire' in A.unsure:
            return self.skip('Flash Fire may be active')
        if m['class'] == PHYSICAL and A.maybe & {'brn'} and A.status != 'brn':
            return self.skip('attacker may be burned')
        if A.mon.ab in ('flareboost', 'toxicboost', 'guts', 'quickfeet') and A.maybe and not A.status:
            return self.skip('status-boost ability with an unknown status')
        if D.maybe & {'brn', 'psn', 'tox'} and D.status is None and D.mon.ab != 'magicguard':
            return self.skip('defender may take status damage')
        if m['effect'] in (E['FACADE'], E['HEX'], E['VENOSHOCK']) and (A.maybe or D.maybe):
            return self.skip('power depends on an unknown status')
        # same-turn changes by the defender's move that the order decides
        field = Field()
        wk, wsure, wchip = self.weather_at(n)
        tk, tsure = self.terrain_at(n)
        field.weather, field.terrain = wk, tk
        weather_matters = (m['type'] in (FIRE, WATER) or m['effect'] == E['WEATHER_BALL'] or mkey in SOLAR or
                           wk == 'sand' and ROCK in D.mon.types or A.mon.ab in WEATHER_SPEED)
        if not wsure and (weather_matters or not _chip_immune(D.mon, 'sand') or not _chip_immune(D.mon, 'hail')):
            return self.skip('weather unknown')
        if not tsure:
            return self.skip('terrain unknown')
        if any(e[0] == 'unsure' and e[1] <= n <= e[1] + 8 for e in [(k2, *v) for k2, v in self.screens[dside].items()]):
            return self.skip('screens unknown')
        att = _view(A, self.calc)
        dfn = _view(D, self.calc, hp=before)
        for kind, (s0, e0) in self.screens[dside].items():
            if kind != 'unsure' and s0 <= n <= e0:
                if n == s0:
                    return self.skip('screen set this turn (order unknown)')
                if mkey not in ('brickbreak', 'psychicfangs', 'ragingbull'):
                    dfn.flags.add(kind)
        if 'glaiverush_%d' % (n - 1) in D.flags:
            first = _sure_first(self.calc, att, dfn, self.d.move_name[m['id']],
                                self.d.move_name[dmove['id']] if dmove else None, Field())
            if first is None:
                return self.skip('Glaive Rush vulnerability with an open move order')
            if first:
                dfn.flags.add('glaiverush')
        if self.tailwind[side] and self.tailwind[side][0] <= n <= self.tailwind[side][1]:
            att.flags.add('tailwind')
        if self.tailwind[dside] and self.tailwind[dside][0] <= n <= self.tailwind[dside][1]:
            dfn.flags.add('tailwind')
        dself = dmove is not None and (dmove['target'] in (6, 7) if dmove['class'] == STATUS else dmove['quality'] == 7)
        interfere = dmove is not None and (
            any(STAT_IDS.get(sid) == (a_stat or 'atk') for sid, _, _ in dmove['stat_changes']) and not dself
            or any(STAT_IDS.get(sid) == d_stat for sid, _, _ in dmove['stat_changes']) and dself
            or dmkey in ('raindance', 'sunnyday', 'sandstorm', 'hail', 'snowscape', 'electerrain', 'grassterrain',
                         'psychterrain', 'mistyterrain', 'haze', 'defog', 'reflect', 'lightscreen', 'auroraveil')
            or dmove['status'] == 4 and m['class'] == PHYSICAL and A.mon.ab != 'guts')
        if dmove is not None and dmove['class'] != STATUS and not interfere:
            dtype = _used_type(self.calc, D.mon, dmove, wk)
            eff_on_a = 1
            for ty in A.mon.types:
                eff_on_a *= self.d.chart[dtype][ty] / 4
            trig = ON_HIT.get(A.mon.ab)
            item_trig = ON_HIT_ITEMS.get(A.mon.it) if A.item == 'held' else None
            interfere = (A.mon.it == 'weakpolicy' and A.item == 'held' and eff_on_a > 1) or bool(
                trig and (trig[0] is None or trig[0] == 'physical' and dmove['class'] == PHYSICAL or
                          isinstance(trig[0], set) and dtype in trig[0])) or bool(
                item_trig and (item_trig[0] == 'physical' and dmove['class'] == PHYSICAL or item_trig[0] == 'special'
                               and dmove['class'] == SPECIAL or isinstance(item_trig[0], set) and dtype in item_trig[0]))
        if interfere:
            first = _sure_first(self.calc, att, dfn, self.d.move_name[m['id']], self.d.move_name[dmove['id']], field)
            if first is not True:
                return self.skip('the defender\'s move this turn may have changed the hit')
        if m['effect'] == E['RIVAL'] and side not in switched_in and dside not in switched_in:
            if _sure_first(self.calc, att, dfn, self.d.move_name[m['id']],
                           self.d.move_name[dmove['id']] if dmove else None, field) is None:
                return self.skip('Fishious Rend / Bolt Beak with an open move order')
        if m['effect'] in (E['GYRO_BALL'], E['ELECTRO_BALL']) and ('spe' in A.unsure or 'spe' in D.unsure or
                                                                  'par' in A.maybe | D.maybe):
            return self.skip('Speed-based power with unknown Speed')
        # what else changed the defender's HP by the next turn
        heal = 0
        item_lost = mkey in ('knockoff', 'thief', 'covet', 'bugbite', 'pluck', 'incinerate') and D.item == 'held' and \
            (mkey == 'knockoff' or mkey in ('thief', 'covet') and A.item == 'none' or D.mon.it.endswith('berry'))
        if item_lost and D.mon.it in ('leftovers', 'blacksludge'):
            D = _copy_poke(D, item='gone')
        if 'berry_hurt_%d' % n in D.flags:
            return self.skip('defender hurt by Jaboca / Rowap Berry')
        if A.mon.it in ('jabocaberry', 'rowapberry') and A.item == 'held' and dmove and dmove['class'] != STATUS:
            return self.skip('defender may be hurt by Jaboca / Rowap Berry')
        if D.mon.it in ('shellbell', 'stickybarb') and D.item == 'held' and (dmove and dmove['class'] != STATUS or
                                                                         D.mon.it == 'stickybarb'):
            return self.skip('defender\'s Shell Bell or Sticky Barb')
        if A.mon.ab == 'baddreams' and ('slp' in D.maybe or D.status == 'slp'):
            return self.skip('Bad Dreams on a sleeping defender')
        if self.weather and self.weather.get('src') == 'wildfire' and wk == 'sun' and FIRE not in D.mon.types:
            return self.skip('Wildfire sun hurts non-Fire Pokemon (amount unknown)')
        if D.mon.ab in ('raindish', 'icebody', 'dryskin', 'solarpower') and wk:
            gain = {('raindish', 'rain'): 16, ('raindish', 'heavy'): 16, ('icebody', 'hail'): 16, ('icebody', 'snow'): 16,
                    ('dryskin', 'rain'): 8, ('dryskin', 'heavy'): 8, ('dryskin', 'sun'): -8, ('dryskin', 'harsh'): -8,
                    ('solarpower', 'sun'): -8, ('solarpower', 'harsh'): -8}.get((D.mon.ab, wk))
            if gain:
                if not wchip:
                    return self.skip('weather heal or chip unknown')
                heal += D.mon.maxhp // abs(gain) * (1 if gain > 0 else -1)
        if D.mon.ab == 'poisonheal' and D.status in ('psn', 'tox'):
            heal += D.mon.maxhp // 8
        if D.mon.it == 'leftovers' and D.item == 'held':
            if after >= D.mon.maxhp:
                return self.skip('Leftovers may have been capped at full HP')
            heal += D.mon.maxhp // 16
        if D.mon.it == 'blacksludge' and D.item == 'held':
            heal += D.mon.maxhp // 16 if POISON in D.mon.types else -(D.mon.maxhp // 8)
        if D.mon.it in HP_BERRIES and D.item == 'held' and after * 4 <= D.mon.maxhp * 3:
            return self.skip('an HP berry may have been eaten')
        chip = 0
        if wk in ('sand', 'hail') and not _chip_immune(D.mon, wk):
            if not wchip:
                return self.skip('weather chip unknown')
            chip += D.mon.maxhp // 16
        if D.status in ('brn', 'psn', 'tox') and D.mon.ab not in ('magicguard', 'poisonheal'):
            return self.skip('defender takes status damage')
        if heal > 0 and after >= D.mon.maxhp:
            return self.skip('end-of-turn heal may have been capped at full HP')
        resid = heal - chip
        quiet = self.quiet.get(self.residual_context(dside, n))
        if quiet and any(v != resid for v in quiet):
            if len(set(quiet)) != 1:
                return self.skip('end-of-turn HP change inconsistent between quiet turns')
            resid = quiet[0]
        drop = before - after + resid
        alts = [('' if not quiet or quiet[0] == heal - chip else 'end-of-turn change measured on quiet turns', drop)]
        # a burn or poison inflicted this turn also hurts at the end of this turn
        new = set()
        if m['status'] in (4, 5) and (m['chance'] > 0) and A.mon.ab != 'sheerforce':
            new.add({4: 'brn', 5: 'psn'}[m['status']])
        if dmove and dmove['flags'] & FLAG_CONTACT and A.mon.ab in STATUS_ON_CONTACT and \
                STATUS_ON_CONTACT[A.mon.ab] in ('brn', 'psn', 'tox'):
            new.add(STATUS_ON_CONTACT[A.mon.ab])
        if D.mon.it in ('flameorb', 'toxicorb') and D.item == 'held' and D.status is None:
            return self.skip('defender\'s Flame / Toxic Orb')
        for s in new:
            if _status_immune(D.mon, s):
                continue
            if s == 'brn':
                alts += [('burn 1/16 this turn', drop - D.mon.maxhp // 16), ('burn 1/8 this turn', drop - D.mon.maxhp // 8)]
            elif s == 'psn':
                alts += [('poison 1/8 this turn', drop - D.mon.maxhp // 8)]
            else:
                alts += [('bad poison 1/16 this turn', drop - D.mon.maxhp // 16)]
        if all(v <= 0 for _, v in alts):
            return self.skip('no damage seen (miss, Protect, immunity, failed move)')
        r = self.calc.damage(att, self.d.move_name[m['id']], dfn, field, switch_in=dside in switched_in)
        o = Observation(os.path.relpath(self.path, LOGS), n, '%s %s' % (side[:3].lower(), A.mon.name),
                        r.move, '%s %s' % (dside[:3].lower(), D.mon.name), [v for _, v in alts], result=r)
        if r.fails or r.rolls is None and r.fixed is None:
            o.verdict, o.detail = 'calc says no damage', r.fails or '; '.join(r.notes)
            self.obs.append(o)
            return
        ranges = []
        if r.fixed is not None:
            ranges = [(r.fixed, r.fixed)]
        else:
            for kh in r.hit_odds:
                ranges.append((sum(r.rolls[0][i][0] for i in range(kh)), sum(r.rolls[1][i][15] for i in range(kh))))
        o.lo, o.hi = min(x for x, _ in ranges), max(y for _, y in ranges)
        for label, v in alts:
            if any(x <= v <= y for x, y in ranges):
                o.verdict, o.alt_used = 'inside', label
                break
        else:
            v = alts[0][1]
            crit_ranges = [(int(x * 1.5) - 2, y * 2 + 2) for x, y in ranges]
            if v > o.hi and any(x <= v <= y for x, y in crit_ranges):
                o.verdict = 'above, fits a critical hit'
            elif v > o.hi:
                o.verdict = 'above'
            else:
                o.verdict = 'below'
        self.obs.append(o)

    def effects(self, t, nxt, switched_in):
        """What this turn's moves did to stages, statuses, items, the field: the state for the next turn."""
        n = t['n']
        acts = dict(t['act'])
        landed = {}
        for side, (usp, mv, tsp) in acts.items():
            dside = OTHER[side]
            tk = self.active.get(dside)
            if not tk:
                continue
            if dside in t['faint']:
                landed[side] = True
            elif dside in nxt['hp'] and self.key(dside, nxt['hp'][dside][0]) == tk:
                before = self.pokes[tk].hp if dside in switched_in else t['hp'].get(dside, (0, 0))[1]
                landed[side] = nxt['hp'][dside][1] < before
            else:
                landed[side] = None
        for side, (usp, mv, tsp) in acts.items():
            ukey = self.key(side, usp)
            if self.active.get(side) != ukey or side in switched_in:
                continue
            U = self.pokes[ukey]
            dside = OTHER[side]
            T_ = self.pokes.get(self.active.get(dside))
            try:
                m = self.d.move(mv)
            except KeyError:
                U.unsure |= {'atk', 'def', 'spa', 'spd', 'spe'}
                continue
            key = norm(self.d.move_name[m['id']])
            hit = landed.get(side)
            able = U.able(n)
            tact = acts.get(dside)
            tprotect = tact is not None and norm(tact[1]) in PROTECTS
            foe_flinch = tact is not None and _flinches(self.d, tact[1])
            if foe_flinch and U.mon.ab != 'innerfocus':
                able = False
            # stat changes
            if key in UNSURE_ALL_MOVES:
                for p in (U, T_):
                    if p:
                        p.unsure |= {'atk', 'def', 'spa', 'spd', 'spe'}
            elif key == 'bellydrum':
                if able and U.hp * 2 > U.mon.maxhp:
                    U.boosts['atk'] = 6
                else:
                    U.unsure.add('atk')
            elif key == 'shellsmash':
                _boost(U, {'atk': 2, 'spa': 2, 'spe': 2, 'def': -1, 'spd': -1}, able)
            elif key == 'curse' and GHOST not in U.mon.types:
                _boost(U, {'atk': 1, 'def': 1, 'spe': -1}, able)
            elif key == 'haze':
                for p in (U, T_):
                    if p:
                        if able:
                            p.boosts = {}
                        else:
                            p.unsure |= {'atk', 'def', 'spa', 'spd', 'spe'}
            elif key == 'memento' and T_:
                _boost(T_, {'atk': -2, 'spa': -2}, able and not tprotect)
            elif m['stat_changes']:
                ch = {STAT_IDS[s]: v for s, v, c in m['stat_changes'] if s in STAT_IDS}
                chance = max(c for _, _, c in m['stat_changes'])
                selfish = m['target'] in (6, 7) if m['class'] == STATUS else m['quality'] == 7
                if m['class'] == STATUS:
                    if selfish:
                        _boost(U, ch, able)
                    elif T_:
                        ab = T_.mon.ab
                        if ab in ('magicbounce', 'mirrorarmor'):
                            U.unsure |= set(ch)
                        elif ab not in STATUS_BLOCK:
                            ch = {k2: v for k2, v in ch.items() if not (ab == 'hypercutter' and k2 == 'atk' or
                                                                        ab == 'bigpecks' and k2 == 'def')}
                            _boost(T_, ch, able and not tprotect and m['accuracy'] >= 100 and 'sub' not in T_.flags,
                                   by_foe=True)
                elif hit:
                    if U.mon.ab == 'sheerforce' and (chance < 100 or not selfish or any(v > 0 for v in ch.values())):
                        pass
                    elif selfish:
                        _boost(U, ch, chance >= 100 or chance == 0)
                    elif T_ and T_.mon.ab not in ('shielddust', 'clearbody', 'whitesmoke', 'fullmetalbdy') and \
                            T_.mon.it != 'covertcloak':
                        _boost(T_, ch, chance >= 100, by_foe=True)
                elif hit is None:
                    for p in ((U,) if selfish else (T_,)):
                        if p:
                            p.unsure |= set(ch)
            # statuses
            st = m['status']
            if T_ and st in (1, 2, 3, 4, 5) and (m['class'] == STATUS or hit is not False and m['chance']):
                if not (U.mon.ab == 'sheerforce' and m['class'] != STATUS):
                    s = {1: 'par', 2: 'slp', 3: 'frz', 4: 'brn', 5: 'psn'}[st]
                    if not _status_immune(T_.mon, s) and T_.status is None:
                        T_.maybe.add(s)
            if T_ and st == 6 and (m['class'] == STATUS or hit):
                T_.confused_until = n + 5
            if T_ and st == 14:
                T_.maybe.add('slp')
            if T_ and st == 8 and hit:
                T_.flags.add('bound')
            if T_ and key == 'leechseed' and GRASS not in T_.mon.types:
                T_.flags.add('seeded')
            if key in ('ingrain', 'aquaring'):
                U.flags.add('regen')
            if key == 'transform':
                U.flags.add('transformed')
            if key == 'glaiverush' and hit:
                U.flags.add('glaiverush_%d' % n)
            if key == 'substitute':
                U.flags.add('sub')
            if key == 'wish':
                self.wish[side] = n
            if key == 'rest':
                U.maybe.add('slp')
            if key == 'attract' and T_:
                T_.flags.add('attract')
            if key in ('healbell', 'aromatherapy') and able:
                for kk, p in self.pokes.items():
                    if kk[0] == side:
                        p.status, p.maybe = None, set()
            if m['class'] != STATUS and T_ and hit and tact and norm(tact[1]) in PROTECTS:
                pass
            if m['flags'] & FLAG_CONTACT and T_ and T_.mon.ab in STATUS_ON_CONTACT and hit:
                U.maybe.add(STATUS_ON_CONTACT[T_.mon.ab])
            if key in RECHARGE and hit:
                U.flags.add('recharge_next')
            # items
            if T_ and key in ITEM_TAKERS:
                if key == 'knockoff' and hit:
                    T_.item = 'gone' if T_.item == 'held' else T_.item
                elif key in ('trick', 'switcheroo', 'corrosivegas', 'recycle'):
                    T_.item = 'unsure' if T_.item != 'none' else 'none'
                    U.item = 'unsure' if U.item != 'none' or key in ('trick', 'switcheroo') else U.item
                elif key in ('thief', 'covet') and hit and U.item == 'none':
                    if T_.item == 'held':
                        T_.item, U.item = 'gone', 'unsure'
                elif key in ('bugbite', 'pluck', 'incinerate') and hit and T_.mon.it.endswith('berry'):
                    T_.item = 'gone'
                elif key == 'fling':
                    U.item = 'gone'
            if T_ and hit and m['class'] != STATUS and T_.item == 'held':
                eff = 1
                for ty in T_.mon.types:
                    eff *= self.d.chart[_used_type(self.calc, U.mon, m, self.weather_at(n)[0])][ty] / 4
                if T_.mon.it in RESIST_BERRIES and (eff > 1 or T_.mon.it == 'chilanberry') and \
                        RESIST_BERRIES[T_.mon.it] == _used_type(self.calc, U.mon, m, self.weather_at(n)[0]) and \
                        U.mon.ab not in ('unnerve', 'asone'):
                    T_.item = 'gone'
                if T_.mon.it == 'airballoon':
                    T_.item = 'gone'
                if T_.mon.it == 'weakpolicy' and eff > 1 and dside not in t['faint']:
                    T_.item = 'gone'
                    _boost(T_, {'atk': 2, 'spa': 2}, True)
                if T_.mon.it in HP_BERRIES:
                    after = nxt['hp'].get(dside, ('', 0, 1))[1]
                    mx = T_.mon.maxhp
                    if after * 2 <= mx:
                        T_.item = 'gone'
                    elif after * 4 <= mx * 3:
                        T_.item = 'unsure'
            # what taking the hit triggers
            utype = _used_type(self.calc, U.mon, m, self.weather_at(n)[0])
            if T_ and T_.mon.ab in ABSORB and ABSORB[T_.mon.ab][0] == utype and m['class'] != STATUS:
                stat = ABSORB[T_.mon.ab][1]
                if stat:
                    T_.unsure.add(stat)
            if T_ and hit and m['class'] != STATUS:
                trig = ON_HIT.get(T_.mon.ab)
                if trig and (trig[0] is None or trig[0] == 'physical' and m['class'] == PHYSICAL or
                             isinstance(trig[0], set) and utype in trig[0]):
                    _boost(T_, trig[1], True)
                    if T_.mon.ab == 'weakarmor':
                        T_.unsure.add('spe')
                it = ON_HIT_ITEMS.get(T_.mon.it)
                if it and T_.item == 'held' and (it[0] == 'physical' and m['class'] == PHYSICAL or it[0] == 'special' and
                                                 m['class'] == SPECIAL or isinstance(it[0], set) and utype in it[0]):
                    _boost(T_, {it[1]: 1}, True)
                    T_.item = 'gone'
                if T_.mon.ab == 'berserk':
                    before = t['hp'].get(dside, ('', 0, 1))[1]
                    after = nxt['hp'].get(dside, ('', 0, 1))[1]
                    if before * 2 > T_.mon.maxhp >= after * 2:
                        _boost(T_, {'spa': 1}, True)
                if T_.mon.it in ('jabocaberry', 'rowapberry') and T_.item == 'held' and \
                        (m['class'] == PHYSICAL) == (T_.mon.it == 'jabocaberry'):
                    T_.item = 'gone'
                    U.flags.add('berry_hurt_%d' % n)
            if U.mon.ab in ON_KO and hit and dside in t['faint']:
                _boost(U, {ON_KO[U.mon.ab]: 1}, True)
            if U.mon.it == 'throatspray' and U.item == 'held' and m['flags'] & FLAG_SOUND:
                if hit:
                    _boost(U, {'spa': 1}, True)
                    U.item = 'gone'
                elif hit is None:
                    U.unsure.add('spa')
                    U.item = 'unsure'
            # field
            wmoves = {'raindance': 'rain', 'sunnyday': 'sun', 'sandstorm': 'sand', 'hail': 'hail', 'snowscape': 'snow'}
            if key in wmoves:
                if able:
                    self.set_weather(wmoves[key], n, 'move', U, unsure_turn=n)
                else:
                    self.weather = {'kind': wmoves[key], 'start': n, 'end': n + 8, 'unsure_from': n}
            tmoves = {'electerrain': 'electric', 'grassterrain': 'grassy', 'psychterrain': 'psychic', 'mistyterrain': 'misty'}
            if key in tmoves:
                dur = 8 if U.mon.it == 'terrainextender' else 5
                self.terrain = {'kind': tmoves[key], 'start': n, 'end': n + dur - 1, 'unsure_turn': n}
                if not able:
                    self.terrain['unsure_turn'] = None
                    self.terrain = {'kind': tmoves[key], 'start': n, 'end': n + 8, 'unsure_turn': n}
            if key in ('reflect', 'lightscreen', 'auroraveil'):
                dur = 8 if U.mon.it == 'lightclay' else 5
                kind = {'reflect': 'reflect', 'lightscreen': 'lightscreen', 'auroraveil': 'auroraveil'}[key]
                if able and (key != 'auroraveil' or self.weather_at(n)[0] in ('hail', 'snow')):
                    self.screens[side][kind] = (n, n + dur - 1)
                elif key != 'auroraveil' or self.weather_at(n)[0] in ('hail', 'snow') or not self.weather_at(n)[1]:
                    self.screens[side]['unsure'] = (n, n + dur)
            if key in ('brickbreak', 'psychicfangs', 'ragingbull') and hit:
                self.screens[dside] = {}
            if key == 'defog':
                if able:
                    self.screens[dside] = {}
                    self.hazards = {s: set() for s in SIDES}
                else:
                    self.screens[dside] = {'unsure': (n, n + 8)}
            if key in ('rapidspin', 'mortalspin') and hit:
                self.hazards[side] = set()
            if key == 'tidyup' and able:
                self.hazards = {s: set() for s in SIDES}
            if key in ('stealthrock', 'spikes', 'toxicspikes', 'stickyweb'):
                self.hazards[dside].add(key)
            if key == 'courtchange':
                both = self.hazards['ADVANCED'] | self.hazards['ORIGINAL']
                self.hazards = {s: set(both) for s in SIDES}
            if key == 'tailwind':
                self.tailwind[side] = (n + 1, n + 3) if able else None
            if key in ('trickroom', 'gravity', 'magicroom', 'wonderroom'):
                self.rooms[key] = n + 5
            if key in ('batonpass', 'healingwish', 'lunardance', 'shedtail'):
                self.side_unsure[side] = True
        # end of turn
        for side in SIDES:
            k = self.active.get(side)
            if not k:
                continue
            p = self.pokes[k]
            if p.mon.it in PINCH_BERRIES and p.item == 'held' and side in nxt['hp']:
                hp_next = nxt['hp'][side][1]
                if self.key(side, nxt['hp'][side][0]) == k and hp_next * 4 <= p.mon.maxhp * (2 if p.mon.ab == 'gluttony' else 1):
                    _boost(p, {PINCH_BERRIES[p.mon.it]: 1}, True)
                    p.item = 'gone'
                elif hp_next * 4 <= p.mon.maxhp * 2:
                    p.unsure.add(PINCH_BERRIES[p.mon.it])
            if 'recharge' in p.flags:
                p.flags.discard('recharge')
            if 'recharge_next' in p.flags:
                p.flags.discard('recharge_next')
                p.flags.add('recharge')
            if p.mon.it in ('flameorb', 'toxicorb') and p.item == 'held' and p.status is None and \
                    not _status_immune(p.mon, 'brn' if p.mon.it == 'flameorb' else 'tox'):
                s_ = 'brn' if p.mon.it == 'flameorb' else 'tox'
                if p.entered == n and side in switched_in or 'orb_wait' in p.flags:
                    p.maybe.add(s_)         # first end of turn after a switch-in: activation not confirmed (s031_g1)
                    p.flags.discard('orb_wait')
                else:
                    p.status = s_
            if p.mon.ab in ('shedskin', 'hydration') and p.status:
                p.maybe.add(p.status)       # may be cured at the end of any turn
                p.status = None
        # faints leave the field; the replacement comes in at the start of the next turn
        for side in t['faint']:
            k = self.active.get(side)
            if k:
                self.leave(side)
                del self.active[side]
        for side, key in switched_in.items():
            pass


def _copy_poke(p, **kw):
    q2 = _Poke.__new__(_Poke)
    q2.__dict__.update(p.__dict__)
    q2.__dict__.update(kw)
    return q2


def _boost(p, changes, sure, by_foe=False):
    """Apply stage changes to a _Poke, or mark those stats unknown when it is not sure they happened. Contrary,
    Simple, Defiant, Competitive and White Herb act as the official rules say."""
    if p.mon.ab == 'contrary':
        changes = {k: -v for k, v in changes.items()}
    elif p.mon.ab == 'simple':
        changes = {k: 2 * v for k, v in changes.items()}
    dropped = False
    for s, v in changes.items():
        if s not in ('atk', 'def', 'spa', 'spd', 'spe'):
            continue
        if sure and s not in p.unsure:
            p.boosts[s] = max(-6, min(6, p.boosts.get(s, 0) + v))
            dropped = dropped or v < 0
        else:
            p.unsure.add(s)
            dropped = dropped or v < 0
    if dropped and by_foe and p.mon.ab in ('defiant', 'competitive'):
        p.unsure.add('atk' if p.mon.ab == 'defiant' else 'spa')
    if dropped and p.mon.it == 'whiteherb' and p.item == 'held':
        if sure:
            for s in list(p.boosts):
                p.boosts[s] = max(0, p.boosts[s])
            p.item = 'gone'
        else:
            p.item = 'unsure'
            p.unsure |= {k for k, v in changes.items() if v < 0}


def _view(p, calc, hp=None):
    """A Mon in the state the validator knows: stages, certain status, item (gone when it is gone)."""
    m = p.mon
    v = Mon(calc, m.sid, level=m.level, ability=m.ability, item=m.item_id if p.item == 'held' else None,
            nature=m.nature, evs=m.evs, ivs=m.ivs, boosts=dict(p.boosts), status=p.status, moves=m.moves, side=m.side)
    if hp is not None:
        v.hp = hp
    v.maybe_ = p.maybe
    return v


def _chip_immune(mon, weather):
    if mon.ab in ('magicguard', 'overcoat') or mon.it == 'safetygoggles':
        return True
    if weather == 'sand':
        return bool({ROCK, GROUND, STEEL} & set(mon.types)) or mon.ab in ('sandveil', 'sandrush', 'sandforce')
    if weather in ('hail',):
        return True     # no hail chip in this hack: Alakazam kept 251/251 HP for six turns of Snow Warning (s005_g0)
    return True


def _status_immune(mon, s):
    t = set(mon.types)
    if s == 'brn':
        return FIRE in t or mon.ab in ('waterveil', 'waterbubble', 'thermalexchg', 'comatose', 'purifyngsalt')
    if s in ('psn', 'tox'):
        return bool({POISON, STEEL} & t) or mon.ab in ('immunity', 'pastelveil', 'comatose', 'purifyngsalt')
    if s == 'par':
        return ELECTRIC in t or mon.ab in ('limber', 'comatose', 'purifyngsalt')
    if s == 'slp':
        return mon.ab in ('insomnia', 'vitalspirit', 'sweetveil', 'comatose', 'purifyngsalt')
    if s == 'frz':
        return ICE in t or mon.ab in ('magmaarmor', 'comatose', 'purifyngsalt')
    return False


def _flinches(d, mv):
    try:
        m = d.move(mv)
    except KeyError:
        return True
    return m['flinch'] > 0


def _used_type(calc, mon, m, weather):
    t = m['type']
    if m['effect'] == E['WEATHER_BALL'] and weather:
        return {'sun': FIRE, 'harsh': FIRE, 'rain': WATER, 'heavy': WATER, 'sand': ROCK, 'hail': ICE, 'snow': ICE}[weather]
    if mon.ab == 'normalize':
        return NORMAL
    if mon.ab in ATE and t == NORMAL and m['effect'] not in ATE_EXEMPT_EFFECTS:
        return ATE[mon.ab][0]
    if mon.ab == 'liquidvoice' and m['flags'] & FLAG_SOUND:
        return WATER
    return t


def sweep(calc, paths, ability_weather=5):
    """(observations, skip counts) over battle logs."""
    obs, skips = [], {}
    for p in paths:
        s = Sweep(calc, p, ability_weather)
        s.run()
        obs += s.obs
        for k, v in s.skips.items():
            skips[k] = skips.get(k, 0) + v
    return obs, skips


# --- observed hits quoted by the battle analysts (qa/aivsai/findings/20261002_184929/analyst1-4.md and
# qa/aivsai/analysis_live_20261002_180214.md). quote: the number in the report. hit: the damage the log shows once
# end-of-turn effects and hazards are taken out (None: the log validator derives it). cond: the battle state at that hit,
# read from the log (None: the log validator's own tracking).
Q = lambda src, log, turn, att, move, dfn, quote, hit=None, cond=None, note='': dict(
    src=src, log=log, turn=turn, att=att, move=move, dfn=dfn, quote=quote, hit=hit, cond=cond, note=note)
RUN = 'runs/20261002_184929/'
QUOTED = [
    Q('analyst 1', RUN + 's006_g0.log', 18, 'Jynx', 'Hyper Voice', 'Crawdaunt', 75),
    Q('analyst 1', RUN + 's006_g0.log', 11, 'Jynx', 'Hyper Voice', 'Gliscor', 246, note='through Yache Berry'),
    Q('analyst 1', RUN + 's006_g0.log', 12, 'Jynx', 'Psychic', 'Pidgeot', 171),
    Q('analyst 1', RUN + 's006_g1.log', 3, 'Mr. Mime', 'DazzlngGleam', 'Skarmory', 66, 66, {'d_hp': 357},
      'Skarmory 357 -> 263 also holds Brave Bird recoil (50) and Leftovers (+22)'),
    Q('analyst 1', RUN + 's018_g0.log', 12, 'Spiritomb', 'Sucker Punch', 'Hypno', 272),
    Q('analyst 1', RUN + 's018_g0.log', 24, 'Houndoom', 'Hyper Voice', 'Spiritomb', 133, 133,
      {'a_boost': 'spa+2', 'd_hp': 264, 'switch_in': True}, 'switch-in at 264 HP; Unaware ignores the +2'),
    Q('analyst 1', RUN + 's018_g0.log', 25, 'Houndoom', 'Sludge Bomb', 'Arbok', 78, 78,
      {'a_boost': 'spa+2', 'switch_in': True}),
    Q('analyst 1', RUN + 's007_g0.log', 21, 'Groudon', 'PrcipceBlade', 'Slowbro', 67, 67,
      {'d_boost': 'def+2', 'd_hp': 199, 'weather': 'harsh'}),
    Q('analyst 1', RUN + 's007_g0.log', 22, 'Groudon', 'PrcipceBlade', 'Slowbro', 67, 67,
      {'d_boost': 'def+2', 'd_hp': 132, 'weather': 'harsh'}),
    Q('analyst 1', RUN + 's014_g0.log', 2, 'Rampardos', 'Head Smash', 'Venusaur', 277, note='277 leaves out Leftovers'),
    Q('analyst 1', RUN + 's014_g0.log', 5, 'Claydol', 'Psychic', 'Magmortar', 145),
    Q('analyst 1', RUN + 's014_g0.log', 13, 'Arcanine', 'ExtremeSpeed', 'Miltank', 64,
      note='the analyst read 64-70 as a Fire ExtremeSpeed halved by Thick Fat; with Miltank\'s Leftovers the hits are a '
           'plain Normal ExtremeSpeed'),
    Q('analyst 1', RUN + 's014_g0.log', 14, 'Arcanine', 'ExtremeSpeed', 'Miltank', 70),
    Q('analyst 1', RUN + 's020_g1.log', 2, 'Pelipper', 'Weather Ball', 'Skarmory', 299, note='a critical hit'),
    Q('analyst 1', RUN + 's020_g1.log', 4, 'Pelipper', 'Hurricane', 'Raticate', 118, 118,
      {'switch_in': True, 'weather': 'rain'}),
    Q('analyst 1', RUN + 's020_g1.log', 7, 'Pelipper', 'Hurricane', 'Quagsire', 154, note='154 leaves out Leftovers'),
    Q('analyst 1', RUN + 's020_g1.log', 8, 'Pelipper', 'Weather Ball', 'Beedrill', 156),
    Q('analyst 1', RUN + 's020_g1.log', 9, 'Beedrill', 'Poison Jab', 'Pelipper', 154),
    Q('analyst 1', RUN + 's024_g0.log', 24, 'Alakazam', 'Shadow Ball', 'Kingdra', 106, 68, {'switch_in': True, 'd_hp': 139},
      '106 includes 38 Stealth Rock damage'),
    Q('analyst 1', RUN + 's034_g1.log', 10, 'Dragalge', 'Sludge Bomb', 'Beartic', 190),
    Q('analyst 1', RUN + 's034_g1.log', 16, 'Beartic', 'Aqua Jet', 'Dragalge', 42),
    Q('analyst 2', RUN + 's008_g0.log', 7, 'Mawile', 'Iron Head', 'Hariyama', 280),
    Q('analyst 2', RUN + 's008_g1.log', 7, 'Machamp', 'Close Combat', 'Metagross', 264, 264,
      {'a_status': 'brn', 'switch_in': True}, 'Machamp burned by its Flame Orb: Guts'),
    Q('analyst 2', RUN + 's008_g1.log', 9, 'Heracross', 'HighHorsepwr', 'Mawile', 105, note='through Shuca Berry'),
    Q('analyst 2', RUN + 's025_g0.log', 1, 'Nidoqueen', 'Thunderbolt', 'Pidgeot', 244),
    Q('analyst 2', RUN + 's025_g0.log', 2, 'Nidoqueen', 'Thunderbolt', 'Staraptor', 213, 213, {'switch_in': True},
      'the report says Ice Beam; the log shows Thunderbolt'),
    Q('analyst 2', RUN + 's025_g0.log', 3, 'Nidoqueen', 'Ice Beam', 'Noctowl', 198),
    Q('analyst 2', RUN + 's002_g1.log', 1, 'Feraligatr', 'Dragon Claw', 'Tropius', 354),
    Q('analyst 2', RUN + 's002_g1.log', 3, 'Feraligatr', 'Rock Slide', 'Walrein', 318, note='318 leaves out Leftovers'),
    Q('analyst 2', RUN + 's002_g1.log', 4, 'Feraligatr', 'Rock Slide', 'Shiftry', 194),
    Q('analyst 2', RUN + 's021_g1.log', 11, 'Garchomp', 'Dragon Rush', 'Pidgeot', 252, 252, {'switch_in': True, 'd_hp': 277},
      'after 92 Stealth Rock damage'),
    Q('analyst 2', RUN + 's027_g0.log', 8, 'Seviper', 'Poison Jab', 'Claydol', 88, 109, {'switch_in': True, 'd_hp': 310},
      '88 leaves out Claydol\'s Leftovers (+21)'),
    Q('analyst 2', RUN + 's027_g0.log', 10, 'Meganium', 'Weather Ball', 'Seviper', 139, 157, {'a_hp': 16},
      '139 leaves out Seviper\'s Black Sludge (+18); Mega Sol makes it a sun Weather Ball'),
    Q('analyst 2', RUN + 's027_g0.log', 11, 'Seviper', 'Night Slash', 'Leafeon', 160, 160, {'switch_in': True, 'crit': True},
      'a critical hit, as the report says'),
    Q('analyst 2', RUN + 's015_g1.log', 14, 'Granbull', 'Play Rough', 'Sceptile', 258, 258, {'a_status': 'brn', 'd_hp': 263},
      'Granbull burned'),
    Q('analyst 3', RUN + 's033_g1.log', 16, 'Azumarill', 'Aqua Jet', 'Dusknoir', 226, note='226 leaves out Leftovers'),
    Q('analyst 4', RUN + 's016_g0.log', 11, 'Sceptile', 'Focus Blast', 'Infernape', 99),
    Q('analyst 4', RUN + 's016_g0.log', 15, 'Typhlosion', 'Focus Blast', 'Torkoal', 143),
    Q('analyst 4', RUN + 's016_g0.log', 18, 'Arcanine', 'Outrage', 'Shiftry', 201, 201, {'switch_in': True}),
    Q('analyst 4', RUN + 's016_g1.log', 2, 'Typhlosion', 'Extrasensory', 'Infernape', 156, 156, {},
      'Typhlosion\'s Blazing Awe took Infernape\'s Flare Blitz'),
    Q('analyst 4', RUN + 's036_g0.log', 1, 'Spiritomb', 'Foul Play', 'Rhyperior', 144),
    Q('analyst 4', RUN + 's036_g1.log', 4, 'Milotic', 'Moonblast', 'Rhyperior', 171, note='through Solid Rock'),
    Q('analyst 4', RUN + 's005_g0.log', 1, 'Alakazam', 'ExpandForce', 'Baxcalibur', 165),
    Q('analyst 4', RUN + 's005_g0.log', 2, 'Alakazam', 'ExpandForce', 'Cloyster', 249),
    Q('analyst 4', RUN + 's005_g0.log', 3, 'Alakazam', 'ExpandForce', 'Glaceon', 219),
    Q('analyst 4', RUN + 's005_g0.log', 4, 'Alakazam', 'DazzlngGleam', 'Abomasnow', 74),
    Q('analyst 4', RUN + 's005_g0.log', 6, 'Abomasnow', 'Ice Shard', 'Alakazam', 99),
    Q('analyst 4', RUN + 's005_g0.log', 26, 'Baxcalibur', 'Dragon Rush', 'Wobbuffet', 319, 319, {'a_boost': 'atk+1'},
      '583 -> 409 with Sitrus Berry +145'),
    Q('analyst 4', RUN + 's013_g1.log', 3, 'Infernape', 'Rock Tomb', 'Scizor', 71),
    Q('analyst 4', RUN + 's013_g1.log', 8, 'Vikavolt', 'Flash Cannon', 'Clefable', 220, 220, {}),
    Q('analyst 4', RUN + 's019_g1.log', 21, 'Garchomp', 'Dragon Rush', 'Arceus', 193),
    Q('analyst 4', RUN + 's019_g1.log', 27, 'Garchomp', 'Dragon Rush', 'Lugia', 170, 170, {'a_boost': 'atk+4'},
      'after four Dragon Dances; Multiscale at full HP'),
    Q('analyst 4', RUN + 's019_g1.log', 27, 'Lugia', 'Aeroblast', 'Garchomp', 258, note='a critical hit'),
    Q('analyst 4', RUN + 's023_g1.log', 15, 'Kommo-o', 'Body Press', 'Hypno', 187),
    Q('analyst 4', RUN + 's023_g1.log', 11, 'Krookodile', 'Earthquake', 'Mightyena', 138),
    Q('analyst 4', RUN + 's023_g1.log', 12, 'Krookodile', 'Earthquake', 'Persian', 79, 79,
      {'switch_in': True, 'a_boost': 'atk-1'}, 'Mightyena\'s Intimidate on turn 11; Fur Coat'),
    Q('analyst 4', RUN + 's030_g1.log', 5, 'Ho-Oh', 'Sky Attack', 'Espeon', 229),
    Q('analyst 4', RUN + 's030_g1.log', 4, 'Chimecho', 'Extrasensory', 'Ho-Oh', 91),
    Q('analyst 4', RUN + 's040_g1.log', 2, 'Mewtwo', 'Flamethrower', 'Dusknoir', 125, 125, {'switch_in': True}),
    Q('analyst 4', RUN + 's040_g1.log', 4, 'Mewtwo', 'Flamethrower', 'Mismagius', 125),
    Q('live analysis', (871, 979), 1, 'Flygon', 'Earth Power', 'Lucario', 198, 198, {}, 'live_20261002_180214.log'),
]


def quoted_hit(calc, q, sweeps):
    """(lo, hi, hit, verdict, how) for one quoted hit."""
    if q['cond'] is None:
        path = os.path.join(LOGS, q['log'])
        if not os.path.exists(path):
            return None, None, None, 'log not present', 'the Spanish run log is not under RUNS/aivsai'
        if path not in sweeps:
            sweeps[path] = Sweep(calc, path)
            sweeps[path].run()
        cands = [o for o in sweeps[path].obs if o.turn == q['turn'] and norm(o.attacker.split(' ', 1)[1]) == norm(q['att'])
                 and norm(o.defender.split(' ', 1)[1]) == norm(q['dfn'])]
        if not cands:
            return None, None, None, 'not compared', 'the log validator skipped it'
        o = cands[0]
        return o.lo, o.hi, o.observed[0], o.verdict, 'log validator' + (' (%s)' % o.alt_used if o.alt_used else '')
    if isinstance(q['log'], tuple):
        teams = {}
        for tid in q['log']:
            name, mons = trainer_mons(calc, tid, 100)
            teams[name] = mons
    else:
        if not os.path.exists(os.path.join(LOGS, q['log'])):
            return None, None, None, 'log not present', 'the Spanish run log is not under RUNS/aivsai'
        teams = read_log(calc, os.path.join(LOGS, q['log']))
    c = q['cond']
    att, dfn = calc.pick(teams, q['att']), calc.pick(teams, q['dfn'])
    att = Mon(calc, att.sid, level=att.level, ability=att.ability, item=att.item_id or None, nature=att.nature,
              evs=att.evs, ivs=att.ivs, boosts=parse_pairs(c.get('a_boost', ''), 'a_boost'), status=c.get('a_status'),
              hp=c.get('a_hp'), moves=att.moves)
    dfn = Mon(calc, dfn.sid, level=dfn.level, ability=dfn.ability, item=dfn.item_id or None, nature=dfn.nature,
              evs=dfn.evs, ivs=dfn.ivs, boosts=parse_pairs(c.get('d_boost', ''), 'd_boost'), status=c.get('d_status'),
              hp=c.get('d_hp'), moves=dfn.moves)
    fld, _ = Field.auto(calc, [att, dfn], c.get('weather'), c.get('terrain'))
    r = calc.damage(att, q['move'], dfn, fld, crit=c.get('crit', False), switch_in=c.get('switch_in', False))
    lo, hi = r.lo, r.hi
    verdict = 'inside' if lo <= q['hit'] <= hi else 'below' if q['hit'] < lo else 'above'
    if verdict == 'above' and not c.get('crit'):
        rc = calc.damage(att, q['move'], dfn, fld, crit=True, switch_in=c.get('switch_in', False))
        if rc.lo <= q['hit'] <= rc.hi:
            verdict = 'above, fits a critical hit'
    return lo, hi, q['hit'], verdict, 'conditions read from the log'


def validate(calc, sweep_logs=None):
    """Quoted hits, then every comparable hit of the AI vs AI logs. True when every quoted hit is inside."""
    sweeps, tally = {}, {}
    print('Observed hits quoted by the analysts (hit = the log\'s HP change without end-of-turn effects and hazards):')
    for q in QUOTED:
        lo, hi, hit, verdict, how = quoted_hit(calc, q, sweeps)
        tally[verdict] = tally.get(verdict, 0) + 1
        where = os.path.basename(q['log']) if isinstance(q['log'], str) else 'trainers %d/%d' % q['log']
        rng = '%d-%d' % (lo, hi) if lo is not None else '-'
        shown = '%d' % q['quote'] + ('' if hit in (None, q['quote']) else ' (hit %d)' % hit)
        print('  %-13s %-12s t%-3d %-11s %-13s -> %-11s %-14s calc %-9s %-27s %s%s' % (
            q['src'], where, q['turn'], q['att'], q['move'], q['dfn'], shown, rng, verdict, how,
            ('; ' + q['note']) if q['note'] else ''))
    print('  quoted hits: %d; %s' % (len(QUOTED), ', '.join('%s %d' % kv for kv in sorted(tally.items()))))
    paths = sweep_logs or sorted(__import__('glob').glob(os.path.join(LOGS, '*', '*.log')))
    obs, skips = sweep(calc, paths)
    counts = {}
    for o in obs:
        counts[o.verdict] = counts.get(o.verdict, 0) + 1
    print('\nEvery hit of the %d run logs whose conditions the log shows: %d compared; %s' % (
        len(paths), len(obs), ', '.join('%s %d' % kv for kv in sorted(counts.items(), key=lambda kv: -kv[1]))))
    print('  not compared (most common reasons): %s' % '; '.join(
        '%s %d' % kv for kv in sorted(skips.items(), key=lambda kv: -kv[1])[:8]))
    for o in obs:
        if o.verdict in ('below', 'above'):
            print('  %-8s %-10s t%-3d %-16s %-13s -> %-16s seen %-5d calc %d-%d' % (
                o.verdict, os.path.basename(o.log), o.turn, o.attacker, o.move, o.defender, o.observed[0], o.lo, o.hi))
    return tally.get('inside', 0) + tally.get('above, fits a critical hit', 0) == len(QUOTED)


# --- command line
MODIFIERS = """\
What the calculator applies, with its label (the per-hit output prints the same labels and notes).
Log evidence comes from `aicalc.py --validate` on the AI vs AI battle logs: real engine runs, not controlled tests.

measured in this hack (emulator tests in qa/aivsai/ANALYST_BRIEF.md, tests/ai_batches/AUTHORING.md)
  Soul Dew does nothing. Light Ball (Pikachu, 2x Atk and Sp. Atk) and Thick Club (Cubone, Marowak, 2x Atk) work;
  2x is the official factor. Focus Sash keeps the holder at 1 HP from full HP. Bulletproof blocks ball and bomb
  moves. Lagging Tail moves last. Rocky Helmet id 590 takes a sixth on contact; id 324 does nothing. Volt Tackle
  has no recoil. Items with no entry in the battle engine's item table do nothing (from the ROM).

official rule, not measured (a range where generations differ; log evidence in brackets)
  abilities  Huge Power, Pure Power 2x Atk. Guts 1.5x Atk with a status, no burn halving. Hustle, Gorilla Tactics
             1.5x Atk. Solar Power 1.5x Sp. Atk in sun. Toxic Boost, Flare Boost 1.5x [one Flare Boost hit fits
             none]. Defeatist, Slow Start 0.5x. Blaze, Torrent, Overgrow 1.5x at a third of HP. Steelworker,
             Dragon's Maw, Rocky Payload 1.5x; Transistor 1.3-1.5x. Orichalcum Pulse, Hadron Engine 1.33x.
             Stakeout 2x on a switch-in. Technician 1.5x at power 60 or less. Iron Fist 1.2-1.3x [7 of 7 hits fit
             1.3, 3 fit 1.2]. Strong Jaw, Mega Launcher (pulse), Sharpness 1.5x. Reckless 1.2x. Sheer Force 1.3x.
             Sand Force 1.3x. Punk Rock 1.3x, 0.5x taken. Adaptability 2x STAB. Refrigerate, Pixilate, Aerilate,
             Galvanize: Normal moves take the type, 1.2-1.3x [9 of 9 hits fit 1.2, 4 fit 1.3]. Normalize 1-1.2x.
             Liquid Voice. Thick Fat, Heatproof 0.5x. Dry Skin 1.25x Fire. Fur Coat 2x Def. Marvel Scale 1.5x Def.
             Multiscale, Shadow Shield 0.5x at full HP. Filter, Solid Rock, Prism Armor 0.75x super effective.
             Ice Scales 0.5x special. Fluffy 0.5x contact, 2x Fire. Tinted Lens 2x. Neuroforce 1.25x. Sniper 1.5x
             on crits. Unaware. Scrappy, Mind's Eye. Mold Breaker, Teravolt, Turboblaze. Ruin abilities 0.75x.
             Grass Pelt 1.5x Def. Immunities: Levitate, Flash Fire, Water/Volt Absorb, Lightningrod, Motor Drive,
             Storm Drain, Sap Sipper, Dry Skin, Earth Eater, Well-Baked Body, Wonder Guard, Soundproof.
             Parental Bond second hit 0.25-0.5x. Skill Link. Prankster, Gale Wings, Triage priority.
  items      Choice Band, Choice Specs 1.5x; Choice Scarf 1.5x Speed. Life Orb 1.3x (5324/4096). Expert Belt 1.2x
             super effective. Type boosters, plates, Fairy Feather 1.2x [38 of 42 hits fit 1.2, 31 fit 1.1].
             Muscle Band, Wise Glasses 1.1x. Adamant, Lustrous, Griseous Orb 1.2x. Eviolite 1.5x Def and Sp. Def
             if the holder evolves (a/0/3/4). Assault Vest 1.5x Sp. Def. Resist berries 0.5x on the first super
             effective hit [Yache, Shuca halved; Coba (2 hits), Charti, Kebia did nothing: 0.5-1 for all but
             Yache and Shuca]. Air Balloon. Iron Ball, Macho Brace, power items 0.5x Speed.
  field      Sun, rain 1.5x / 0.5x. Harsh sun, heavy rain: Water / Fire moves fail. Sand 1.5x Sp. Def for Rock.
             Snow 1.5x Def for Ice (--weather snow). Electric, Grassy, Psychic Terrain 1.3-1.5x [16 of 17 fit 1.3].
             Misty Terrain 0.5x Dragon; Grassy Terrain 0.5x Earthquake. Psychic Terrain blocks priority on grounded
             targets [an Ice Shard did 0]. Screens 0.5x (2/3 in doubles). Critical hit 1.5x [20 of 23 above-range
             hits fit 1.5; none fits only 2]. Burn 0.5x physical. Spread 0.75x. Tailwind 2x Speed. Paralysis
             0.5x Speed [measured; Quick Feet lifts it since the rc27 engine fix]. Trick Room.
  moves      Weather Ball, Terrain Pulse, Expanding Force 1.5x in Psychic Terrain [fits], Foul Play, Body Press,
             Psyshock / Psystrike / Secret Sword, Fishious Rend and Bolt Beak 2x on a switch-in or moving first,
             Knock Off 1.5x on an item, Facade, Hex, Venoshock, Brine, Acrobatics, Eruption, Water Spout, Dragon
             Energy, Wring Out, Crush Grip, Hard Press, Reversal, Flail, Stored Power, Gyro Ball, Electro Ball,
             Solar Beam 0.5x in bad weather, Freeze-Dry, Flying Press, Triple Axel, multi-hit (2-5 hits 35/35/15/15%),
             fixed damage (Seismic Toss, Night Shade, Dragon Rage, Sonic Boom, Super Fang), Glaive Rush 2x taken.

hack ability, not measured (read from bank 712)
  Burning Skin, Azure Skin, Grass Skin, Dark Skin, Dragonize: Normal moves become Fire, Water, Grass, Dark, Dragon,
  1.2-1.3x. Flame Mane 1.2-1.5x Fire [it does not make ExtremeSpeed Fire]. Mega Claws 1.3x Atk. Mega Sol: its
  moves act as in sun. Wildfire: sun. Tough Claws: every physical move 1.3x [two non-contact Stone Edge hits fit
  only with it]. Shell Armor: physical damage 0.8x [7 hits fit 0.78-0.80], no crits. Swarm: 0.75x super effective.
  Quick Feet: Atk 1.2-1.5x with a status. Marvel Scale: Sp. Def too. Water Bubble: its Water boost 1-2x. Battle
  Armor hurts on contact (amount unknown). Mega Launcher's "cannon moves" get no boost [two cannon hits].

engine facts the logs show (not damage modifiers; useful for reading a battle)
  Weather from an ability lasts 5 turns (8 with its rock) and a re-entry does not renew it. Snow Warning's hail
  does no chip damage. Burn and Leftovers are 1/16 a turn. Some Pokemon healed 2/16 a turn with Leftovers alone
  (Baxcalibur in s003, Swampert in s017_g0), cause unknown. The log's HP lines are taken after end-of-turn effects.
"""

EPILOG = """\
examples:
  # one move in an AI vs AI battle: both teams' exact specs (EVs, IVs, nature, item, ability) come from the log
  aicalc.py --log RUNS/aivsai/<run>/s006_g0.log Jynx "Hyper Voice" Skarmory
  # the same in the battle's state: Skarmory at 182 HP, Jynx at +1 Sp. Atk, rain
  aicalc.py --log LOG Jynx "Hyper Voice" Skarmory --d-hp 182 --a-boost spa+1 --weather rain
  # every damaging move both ways, and who moves first
  aicalc.py --log LOG Jynx vs Skarmory
  # every damaging move of one side only
  aicalc.py --log LOG Jynx all Skarmory
  # speed order only, or both teams with stats and speeds
  aicalc.py --log LOG --speed Jynx Skarmory
  aicalc.py --log LOG --show
  # a species on both teams (mirror match): prefix the side
  aicalc.py --log LOG adv:Jynx Psychic orig:Jynx
  # Fishious Rend or Bolt Beak into a Pokémon switching in (they double), a critical hit
  aicalc.py --log LOG Gyarados FishiousRend Swampert --switch-in
  aicalc.py --log LOG Lugia Aeroblast Garchomp --crit
  # trainer teams by id (live logs have no team header): aiteams.py lists them; --level 100 as the bench plays
  aicalc.py --trainer 871 --trainer 979 --level 100 Flygon "Earth Power" Lucario
  # no log: name everything; a Pokémon has level 100, a neutral nature, no EVs, IVs 31 and NO ability or item
  # unless given (the bench's default ability Run Away does nothing either)
  aicalc.py Mawile "Play Rough" Lucario --a-ability "Huge Power" --a-nature Adamant --a-evs atk252
  # every modifier with its label and the log evidence; check against the hits analysts quoted from logs
  aicalc.py --modifiers
  aicalc.py --validate

names: the ROM's English spelling, any case, spaces and punctuation ignored. Long names are truncated as in the
  game (DazzlngGleam, FishiousRend, HighHorsepwr, ExpandForce, Elec. Surge, PsychicSurge). A wrong name prints
  close matches. The hack changed types, stats and powers: `aidata.py NAME` prints the ROM's values.

per-Pokémon options (--a-* for the attacker, --d-* for the defender; with --log they override the log's spec):
  --a-hp 182 | 50%          current HP (default full). KO chances start from the defender's current HP
  --a-boost "atk+2 spe-1"   stat stages (atk def spa spd spe)
  --a-status brn            brn psn tox par slp frz
  --a-item NAME | none      none = the item is gone (eaten berry, Knock Off): Acrobatics doubles, no berry
  --a-flags tailwind,reflect,lightscreen,auroraveil,unburden,flashfire
                            effects on this Pokémon or its side (screens protect the side they are on)
  --a-ability, --a-nature, --a-evs "atk252 spe252", --a-ivs 31, --a-level 100, --a-moves "Move, Move"

how to read the output:
  damage 183-216 (50.4-59.5% of 363)   the lowest roll with every low factor to the highest with every high one
  KO chance from 182/363 HP: OHKO 100%  the chance that one use (2HKO: two uses...) of the move KOs, over the 16
                            rolls (and the 2-5 hit odds 35/35/15/15%); a range when a factor is a range
  per modifier: its factor and its label:
    measured in this hack        an emulator test found it (Soul Dew does nothing; Light Ball, Thick Club,
                                 Focus Sash, Bulletproof, Lagging Tail, Rocky Helmet 590 work; Volt Tackle
                                 has no recoil; Rocky Helmet 324 does nothing)
    official rule, not measured  the official games' rule, assumed to hold here
    hack ability, not measured   only this hack has it, or the hack changed it; read from its description
  A note after a factor gives the AI vs AI log evidence where there is some (`--modifiers` lists it all).
  notes: immunities, Focus Sash and Sturdy, recoil, Life Orb and Rocky Helmet damage, Weakness Policy.
  Not modeled: crits unless --crit, Intimidate and other entry boosts (pass them with --a-boost), doubles
  partners (Helping Hand, Friend Guard), Protosynthesis and Quark Drive, moves whose power depends on weight,
  friendship or move order (a note says so). Accuracy is not in the KO chances.
  Weather and terrain default to what the two Pokémon's own abilities set (Drizzle, PsychicSurge...); pass
  --weather none / --terrain none to drop them. Ability weather lasts 5 turns (8 with its rock) in this ROM.
"""


def parse_pairs(text, what):
    """'atk252 spe252', 'atk=252,spe=252', 'spa+2 spe-1' -> {stat: n}"""
    out = {}
    for tok in re.split(r'[,\s/]+', text.strip()):
        if not tok:
            continue
        mt = re.fullmatch(r'([a-zA-Z]+)[=:]?([+-]?\d+)', tok) or re.fullmatch(r'([+-]?\d+)([a-zA-Z]+)', tok)
        if not mt:
            raise ValueError('%s: cannot read %r (write e.g. atk252 or spa+2)' % (what, tok))
        a, b = mt.groups()
        stat, n = (a, b) if a[0].isalpha() else (b, a)
        if norm(stat) not in STAT_ALIASES:
            raise ValueError('%s: unknown stat %r (hp atk def spa spd spe)' % (what, stat))
        out[STAT_ALIASES[norm(stat)]] = int(n)
    return out


def with_overrides(calc, base, a, p):
    """A Mon from a log/trainer Mon (or a species name) with the --a-* / --d-* options applied."""
    g = lambda k: getattr(a, '%s_%s' % (p, k))
    kw = {}
    if base is not None and not isinstance(base, str):
        kw = dict(level=base.level, ability=base.ability, item=base.item_id or None, nature=base.nature, evs=base.evs,
                  ivs=base.ivs, boosts=dict(base.boosts), status=base.status, moves=base.moves, side=base.side,
                  flags=set(base.flags))
        species = base.sid
    else:
        species = base
    if g('level'):
        kw['level'] = g('level')
    elif a.level and 'level' not in kw:
        kw['level'] = a.level
    for k in ('ability', 'item', 'nature', 'status'):
        if g(k) is not None:
            kw[k] = None if g(k).lower() == 'none' else g(k)
    if g('evs') is not None:
        kw['evs'] = parse_pairs(g('evs'), '--%s-evs' % p)
    if g('ivs') is not None:
        kw['ivs'] = g('ivs')
    if g('boost') is not None:
        kw['boosts'] = dict(kw.get('boosts') or {}, **parse_pairs(g('boost'), '--%s-boost' % p))
    if g('moves') is not None:
        kw['moves'] = [x.strip() for x in g('moves').split(',') if x.strip()]
    if g('flags') is not None:
        kw['flags'] = set(kw.get('flags') or ()) | {norm(x) for x in g('flags').split(',') if x.strip()}
    mon = Mon(calc, species, **kw)
    if g('hp') is not None:
        mon.hp = hp_value(g('hp'), mon.maxhp)
    return mon


def damaging(calc, mon):
    return [mv for mv in mon.moves if calc.d.move(mv)['class'] != STATUS]


def show_teams(calc, teams, field):
    for side, mons in teams.items():
        print('%s' % side)
        for m in mons:
            lo, hi = calc.speed(m, field)
            print('  %-12s %-17s %-13s @ %-14s %-8s IV %-2s EVs %-17s HP %3d Atk %3d Def %3d SpA %3d SpD %3d Spe %3d%s' % (
                m.name, '/'.join(TYPES[t] for t in m.types), m.ability or '-', m.item or '-', m.nature, m.ivs,
                '/'.join(str(m.evs.get(k, 0)) for k in STATS), m.maxhp, m.stats['atk'], m.stats['def'], m.stats['spa'],
                m.stats['spd'], m.stats['spe'], '' if lo == hi == m.stats['spe'] else ' (effective %s)' % (
                    lo if lo == hi else '%d-%d' % (lo, hi))))
            print('  %12s %s' % ('', ', '.join(m.moves)))
        print()


def build_parser():
    ap = argparse.ArgumentParser(
        prog='aicalc.py', formatter_class=argparse.RawDescriptionHelpFormatter, epilog=EPILOG,
        description='Damage ranges, KO chances and speed order from the hack\'s own data and the Gen 5 rules. '
                    'Each modifier is labeled: measured in this hack, official rule (not measured), or hack '
                    'ability (not measured).',
        usage='aicalc.py [--log LOG | --trainer ID ...] ATTACKER MOVE|vs|all DEFENDER [options]\n'
              '       aicalc.py [--log LOG] --speed A B | --show\n'
              '       aicalc.py --modifiers | --validate')
    ap.add_argument('names', nargs='*', help='ATTACKER MOVE DEFENDER; MOVE "vs" = every damaging move both ways, '
                                             '"all" = every damaging move of the attacker')
    src = ap.add_argument_group('teams')
    src.add_argument('--log', help='an AI vs AI battle log (RUNS/aivsai/<run>/<scenario>_g<game>.log)')
    src.add_argument('--trainer', type=int, action='append', help='load a ROM trainer team by id (repeat for two)')
    src.add_argument('--level', type=int, help='level for every Pokémon named without a log, or loaded by --trainer')
    src.add_argument('--rom', default=DEFAULT_ROM, help='ROM to read the data from (default: the Chinese hack)')
    mode = ap.add_argument_group('modes')
    mode.add_argument('--show', action='store_true', help='print both teams with stats and speeds')
    mode.add_argument('--speed', action='store_true', help='speed order of two Pokémon only')
    mode.add_argument('--validate', action='store_true', help='compare with the observed hits analysts quoted, then '
                                                               'with every comparable hit of the AI vs AI run logs')
    mode.add_argument('--modifiers', action='store_true', help='list every modifier with its label and log evidence')
    mode.add_argument('--rolls', action='store_true', help='print all 16 damage rolls')
    fld = ap.add_argument_group('field')
    fld.add_argument('--weather', choices=['none', 'sun', 'rain', 'sand', 'hail', 'snow', 'harsh', 'heavy'],
                     help='harsh = Desolate Land, heavy = Primordial Sea, snow = Gen 9 snow (Ice types 1.5x Def)')
    fld.add_argument('--terrain', choices=['none', 'electric', 'grassy', 'psychic', 'misty'])
    fld.add_argument('--crit', action='store_true', help='a critical hit (1.5x, the Gen 6+ rule the logs fit)')
    fld.add_argument('--switch-in', action='store_true', help='the defender switches in this turn (Fishious Rend, '
                                                              'Bolt Beak and Stakeout double)')
    fld.add_argument('--spread', action='store_true', help='doubles: a spread move hits two or more targets (0.75x)')
    fld.add_argument('--doubles', action='store_true', help='doubles (screens are 2/3 instead of 1/2)')
    fld.add_argument('--trick-room', action='store_true')
    for p, who in (('a', 'attacker (first name)'), ('d', 'defender (second name)')):
        g = ap.add_argument_group('%s, --%s-*' % (who, p))
        g.add_argument('--%s-hp' % p, metavar='HP', help='current HP: 182 or 50%%')
        g.add_argument('--%s-boost' % p, metavar='STAGES', help='"atk+2 spe-1"')
        g.add_argument('--%s-status' % p, metavar='S', help='brn psn tox par slp frz')
        g.add_argument('--%s-item' % p, metavar='ITEM', help='an item, or none')
        g.add_argument('--%s-ability' % p, metavar='ABILITY')
        g.add_argument('--%s-nature' % p, metavar='NATURE')
        g.add_argument('--%s-evs' % p, metavar='EVS', help='"atk252 spe252"')
        g.add_argument('--%s-ivs' % p, metavar='N', type=int, help='one value for all six (default 31)')
        g.add_argument('--%s-level' % p, metavar='N', type=int)
        g.add_argument('--%s-moves' % p, metavar='MOVES', help='"Move, Move" (for vs / all without a log)')
        g.add_argument('--%s-flags' % p, metavar='FLAGS', help='tailwind,reflect,lightscreen,auroraveil,unburden,flashfire')
    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.modifiers:
        print(MODIFIERS)
        return
    calc = Calc(a.rom)
    if a.validate:
        sys.exit(0 if validate(calc) else 1)
    teams = None
    if a.log:
        teams = read_log(calc, a.log)
    elif a.trainer:
        teams = {}
        for tid in a.trainer:
            name, mons = trainer_mons(calc, tid, a.level)
            teams['%s #%d' % (name, tid)] = mons
    if a.show:
        if not teams:
            ap.error('--show needs --log or --trainer')
        show_teams(calc, teams, Field(weather=None if a.weather in (None, 'none') else a.weather, terrain=a.terrain))
        return
    names = a.names
    if a.speed:
        if len(names) != 2:
            ap.error('--speed takes two Pokémon')
        first, second = names
        mode, move = 'speed', None
    elif len(names) == 3:
        first, move, second = names
        mode = {'vs': 'vs', 'all': 'all'}.get(move.lower(), 'move')
    else:
        ap.error('give ATTACKER MOVE DEFENDER (or ATTACKER vs DEFENDER, --speed A B, --show, --validate)')
    base_a = calc.pick(teams, first) if teams else first
    base_d = calc.pick(teams, second) if teams else second
    att, dfn = with_overrides(calc, base_a, a, 'a'), with_overrides(calc, base_d, a, 'd')
    fld, notes = Field.auto(calc, [att, dfn], a.weather, a.terrain)
    fld.spread, fld.doubles, fld.trick_room = a.spread, a.doubles or a.spread, a.trick_room
    print(att.describe())
    print(dfn.describe())
    for n in notes:
        print('field: ' + n)
    print()
    if mode == 'speed':
        print(calc.order(att, dfn, fld)[0])
        return
    if mode == 'move':
        pairs = [(att, move, dfn)]
    else:
        pairs = [(att, mv, dfn) for mv in damaging(calc, att)]
        if mode == 'vs':
            pairs += [(dfn, mv, att) for mv in damaging(calc, dfn)]
        if not pairs:
            ap.error('no damaging moves known: give --a-moves / --d-moves')
    for x, mv, y in pairs:
        r = calc.damage(x, mv, y, fld, crit=a.crit, switch_in=a.switch_in and y is dfn)
        print(r.text(verbose=a.rolls))
        print()
    print(calc.order(att, dfn, fld, move if mode == 'move' else None)[0])


if __name__ == '__main__':
    try:
        main()
    except (KeyError, ValueError) as e:
        sys.exit('aicalc.py: error: %s' % (e.args[0] if e.args else e))
