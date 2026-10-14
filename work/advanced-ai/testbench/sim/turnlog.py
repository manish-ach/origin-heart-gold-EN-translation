"""The emulator's AI-vs-AI battle logs (RUNS/aivsai/*/sNNN_gK.log) as structured turns, for the simulator's
turn-level validator (sim/validate.py, `sim validate`).

  .venv/bin/python work/advanced-ai/testbench/sim/turnlog.py [--runs GLOB] [--rom ROM] [-o OUT] [--unknown]

The battle messages it reads are the Spanish rc44 ROM's (the logs of games played on it): the patterns, the Spanish
names (the Spanish workspace's glossary and species bank at dc8577c, read with git from ADVAI_ES_REPO, lib/names.py)
and the default ROM are the Spanish build's. Logs of the English build print English messages, which these patterns
do not read yet.

Each game becomes the turns the log shows. A turn holds the state at its start (both Pokemon on the field: HP, main
status, confusion, stat stages; the weather), each side's decision with the options it weighed, and the battle's
messages turned into facts, grouped into segments: one per action (a move used, an action stopped before the move:
sleep, paralysis, flinch, confusion, freeze), one per switch or replacement, and the end of the turn. OUT (default
RUNS/sim/val/obs.txt) is the line format `sim validate` reads (see write_obs). --unknown prints the messages
no pattern reads, most frequent first.

Sides are the engine's: 0 the player's (PLAYER, no "enemigo" in messages), 1 the trainer's (TRAINER, "el X enemigo").
Members are named by their slot in the full trainer team (the `set` the simulator gives each Pokemon).
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import names as tbnames  # noqa: E402
from aicalc import CUT, HEADER  # noqa: E402
from logstats import log_lines, orig_runs  # noqa: E402

SIDE_OF = {'PLAYER': 0, 'TRAINER': 1}
# group 4: aivsai --reseed K (the same teams with other luck), None for reseed 0
SCENARIO = re.compile(r'^scenario (s\d+) game (\d+), seed (\d+)(?:, reseed (\d+))?, TRAINER SIDE (\d+) vs PLAYER SIDE (\d+)$')
TEAM = re.compile(r'^(TRAINER|PLAYER) SIDE team: (.*)$')
TURN = re.compile(r'^--- Turn (\d+)(?: \((\w+)(?:, (\d+) turns? left)?\))? ')
STATE = re.compile(r'^  (TRAINER|PLAYER) +(\S.*?) +(\d+)/(\d+) +[█░]+(?:  (.*))?$')
UNKNOWN_STATE = re.compile(r'^  (TRAINER|PLAYER) +\? +\?/\?')
ACT = re.compile(r'^  (TRAINER|PLAYER) +(\S.*?) -> (.*)$')
REPL = re.compile(r'^  (TRAINER|PLAYER) +(?:(\S.*?) out, )?(\S.*?) in$')
FAINT = re.compile(r'^  (TRAINER|PLAYER) +(\S.*?) fainted$')
END = re.compile(r'^=== (?:(TRAINER|PLAYER) wins|No winner)')
OPTS = re.compile(r'^ {12}options: (.*?)(?: \(\+(\d+) more\))?(?: \(the engine\'s pick: (.*)\))?$')
SCORES = re.compile(r'^ {12}scores: +(.*)$')     # the original AI's factor sums per move (adv-vs-orig logs)
# its rows aimed at another target (logs from 2026-10-05): 'foe' for the player side, whose 'scores:' are its own rows
TARGET_SCORES = re.compile(r'^ {12}scores on (\w+): +(.*)$')
FOE = re.compile(r'^ {12}foe model s=([\d.]+)(?:, expects switch to (.+?) \(w ([\d.]+)\))?$')
WEATHER = {'rain': 1, 'sun': 2, 'sand': 3, 'hail': 4}
STATUS = {'PAR': 1, 'SLP': 2, 'FRZ': 3, 'BRN': 4, 'PSN': 5, 'TOX': 5}
STAGE_KEYS = ('Atk', 'Def', 'SpA', 'SpD', 'Spe', 'Acc', 'Eva')      # the bpp's order, the simulator's STAT_*

# the facts, as `sim validate` reads them (validate.c F_*); keep the two lists in step
FACTS = ('hit', 'crit', 'miss', 'fail', 'noeffect', 'protected', 'protect', 'nhits', 'faint', 'status', 'confuse',
         'stat', 'wake', 'asleep', 'fullpara', 'flinch', 'confused', 'selfhit', 'confend', 'frozen', 'thaw',
         'quick', 'item', 'ability', 'weather', 'weather_end', 'terrain', 'terrain_end', 'hazard', 'hazard_hit',
         'chip', 'heal', 'sendin', 'recall', 'other', 'evolve', 'sub', 'tailwind', 'screen', 'trickroom', 'fatigue',
         'bind', 'seeded', 'yawn', 'taunt', 'transform', 'perish', 'struggle', 'statfail')
STAT_NAMES = {'El Ataque': 0, 'La Defensa': 1, 'El Ataque Especial': 2, 'La Defensa Especial': 3, 'La Velocidad': 4,
              'La precisión': 5, 'La evasión': 6, 'el Ataque': 0, 'la Defensa': 1, 'el Ataque Especial': 2,
              'la Defensa Especial': 3, 'la Velocidad': 4}
DELTA = {'subió': 1, 'subió mucho': 2, 'subió muchísimo': 3, 'bajó': -1, 'bajó mucho': -2, 'bajó muchísimo': -3}
ST = {'PAR': 1, 'SLP': 2, 'FRZ': 3, 'BRN': 4, 'PSN': 5, 'TOX': 6}
# chip / heal causes (the HP changes the messages name)
CAUSE = ('leftovers', 'blacksludge', 'burn', 'poison', 'sand', 'seed', 'lifeorb', 'recoil', 'helmet', 'drain',
         'veil', 'ingrain', 'berry', 'curse', 'nightmare', 'bind', 'jaboca', 'crash', 'painsplit', 'rest', 'wish',
         'bellydrum', 'drained', 'other')

P = r'(?P<p>\{\d:[^}]+\})'
P2 = r'(?P<q>\{\d:[^}]+\})'
X = r'(?P<x>.+?)'
STATW = r'(?P<stat>El Ataque Especial|La Defensa Especial|El Ataque|La Defensa|La Velocidad|La precisión|La evasión)'
STATL = r'(?P<stat>el Ataque Especial|la Defensa Especial|el Ataque|la Defensa|la Velocidad)'
DELTAW = r'(?P<delta>subió muchísimo|subió mucho|subió|bajó muchísimo|bajó mucho|bajó)'
# (code, pattern, extra): pattern on the message with every Pokemon as {side:Name}; patterns are tried in order
PATTERNS = [
    ('use', r'¡%s usó (?P<x>.+)!' % P, None),
    ('crit', r'¡Un golpe crítico!', None),
    ('eff', r'¡Es súper eficaz!|No es muy eficaz\.\.\.', None),
    ('miss', r'¡%s esquivó el ataque!' % P, None),
    ('fail', r'¡Pero falló!', None),
    ('noeffect', r'Parece que no afecta a %s\.\.\.' % P, None),
    ('protected', r'¡%s se protegió del ataque!' % P, None),
    ('protect', r'¡%s se protegió!' % P, None),
    ('nhits', r'¡Número de golpes: (?P<n>.+)!', None),
    ('faint', r'¡%s se debilitó!' % P, None),
    ('sendin', r'¡Felix sacó a %s!' % P, 1),
    ('sendin', r'¡(?:Adelante|Te toca|Tú puedes), %s!|¡Un poco más! ¡Aguanta, %s!|¡El rival está débil! ¡Acábalo, %s!' % (
        P, P.replace('<p>', '<p2>'), P.replace('<p>', '<p3>')), 0),
    ('recall', r'¡%s, (?:regresa|bien! ¡Regresa|cambio! ¡Regresa|muy bien! ¡Regresa)!' % P, None),
    ('recall', r'¡%s regresó con (?:Felix|AAAAAA)!' % P, None),
    ('status', r'¡%s se durmió!' % P, 'SLP'),
    ('status', r'¡%s se quemó(?: por culpa de .+)?!' % P, 'BRN'),
    ('status', r'¡%s fue envenenado!' % P, 'PSN'),
    ('status', r'¡%s fue gravemente envenenado!' % P, 'TOX'),
    ('status', r'¡.+ envenenó gravemente a %s!' % P, 'TOX'),
    ('status', r'¡%s está paralizado! ¡Quizás no pueda moverse!' % P, 'PAR'),
    ('status', r'¡%s se congeló!' % P, 'FRZ'),
    ('confuse', r'¡%s quedó confuso!' % P, None),
    ('fatigue', r'¡%s quedó confuso por el cansancio!' % P, None),
    ('yawn', r'¡%s empezó a adormilarse!' % P, None),
    ('seeded', r'¡%s fue infectado por .+!' % P, None),
    ('taunt', r'¡%s cayó en la mofa!' % P, None),
    ('bind', r'¡%s quedó atrapado en (?:el torbellino|un remolino de fuego)!' % P, None),
    ('stat', r'¡%s de %s %s!' % (STATW, P, DELTAW), None),
    ('stat', r'¡(?P<x>.+?) %s %s de %s!' % (DELTAW, STATL, P), None),
    ('statfail', r'¡.+ de %s no puede (?:subir|bajar) más!|¡No se puede bajar .+ de %s!|¡No se pueden bajar las '
                 r'características de %s!|¡Su .+ impide que bajen las características de %s!' % (
                     P, P.replace('<p>', '<p2>'), P.replace('<p>', '<p3>'), P.replace('<p>', '<p4>')), None),
    ('asleep', r'%s está profundamente dormido\.' % P, None),
    ('wake', r'¡%s se despertó!' % P, None),
    ('wake', r'¡.+ despertó a %s!' % P, None),
    ('fullpara', r'¡%s está paralizado! ¡No se puede mover!' % P, None),
    ('flinch', r'¡%s retrocedió y no pudo moverse!' % P, None),
    ('confused', r'¡%s está confuso!' % P, None),
    ('selfhit', r'¡Está tan confuso que se hirió a sí mismo!', None),
    ('confend', r'¡%s ya no está confuso!' % P, None),
    ('confend', r'¡.+ quitó la confusión a %s!' % P, None),
    ('frozen', r'¡%s está congelado!' % P, None),
    ('thaw', r'¡%s se descongeló!' % P, None),
    ('thaw', r'¡.+ de %s derritió el hielo!' % P, None),
    ('quick', r'¡%s puede actuar más rápido gracias a su (?:habilidad )?(?P<x>.+)!' % P, None),
    ('heal', r'%s recuperó unos pocos PS con su (?P<x>.+)\.' % P, 'leftovers'),
    ('heal', r'¡%s recuperó salud con su (?P<x>.+)!' % P, 'berry'),
    ('item', r'¡%s resistió gracias a su (?P<x>.+)!' % P, 'sash'),
    ('item', r'¡Gracias a (?P<x>.+), %s recibió menos daño!' % P, 'resist'),
    ('item', r'(?P<x>.+) cumplió su función y desapareció\.\.\.', 'used'),
    ('item', r'¡%s flota en el aire gracias al (?P<x>.+)!' % P, 'balloon'),
    ('item', r'¡Explotó el (?P<x>.+) de %s!' % P, 'balloonpop'),
    ('item', r'¡%s normalizó sus características con su (?P<x>.+)!' % P, 'whiteherb'),
    ('item', r'¡%s se hizo más fuerte con su (?P<x>.+)!' % P, 'powerherb'),
    ('item', r'¡%s le quitó (?P<x>.+) a %s!' % (P, P2), 'knock'),
    ('item', r'¡%s robó y se comió (?P<x>.+) de su objetivo!' % P, 'bugbite'),
    ('item', r'¡(?P<x>.+) curó .+ de %s!' % P, 'cure'),
    ('item', r'¡(?P<x>.+) curó .+ a %s!' % P, 'cure'),
    ('chip', r'¡%s se hizo daño con (?P<x>.+) de %s!' % (P, P2), 'jaboca'),
    ('chip', r'¡%s perdió algunos PS!' % P, 'lifeorb'),
    ('chip', r'¡%s se hirió con el retroceso!' % P, 'recoil'),
    ('chip', r'¡%s recibió daño!' % P, 'helmet'),
    ('chip', r'¡%s se resiente de la quemadura!' % P, 'burn'),
    ('chip', r'¡El veneno le resta PS a %s!' % P, 'poison'),
    ('chip', r'¡La tormenta de arena zarandea a %s!' % P, 'sand'),
    ('chip', r'¡.+ le resta salud a %s!' % P, 'seed'),
    ('chip', r'¡%s está atrapado en una pesadilla!' % P, 'nightmare'),
    ('chip', r'¡%s sufre daño por .+!' % P, 'bind'),
    ('chip', r'¡%s siguió de largo y se estrelló!' % P, 'crash'),
    ('chip', r'¡%s perdió energía!' % P, 'drained'),
    ('other', r'¡(?P<x>.+) atacó a %s!' % P, 'announce'),
    ('heal', r'%s recuperó PS\.' % P, 'drain'),
    ('heal', r'¡Un velo de agua restauró los PS de %s!' % P, 'veil'),
    ('heal', r'¡%s absorbió nutrientes con sus raíces!' % P, 'ingrain'),
    ('heal', r'¡El deseo de %s se cumplió!' % P, 'wish'),
    ('heal', r'¡%s durmió y recuperó la salud!' % P, 'rest'),
    ('heal', r'¡Los combatientes compartieron su dolor!', 'painsplit'),
    ('other', r'¡%s se rodeó de un velo de agua!' % P, 'veil'),
    ('other', r'¡%s echó raíces!' % P, 'ingrain'),
    ('other', r'¡%s redujo sus PS y subió su Ataque al máximo!' % P, 'bellydrum'),
    ('other', r'¡%s intenta llevarse a su atacante consigo!' % P, 'destiny'),
    ('other', r'¡%s se llevó a su atacante consigo!' % P, 'destinyko'),
    ('other', r'¡%s aguantó el golpe!' % P, 'endure'),
    ('other', r'¡%s (?:absorbió luz|rebosa energía cósmica)!' % P, 'charge'),
    ('other', r'¡%s ejerce presión!|¡%s rompe moldes!|¡%s se estremeció!' % (
        P, P.replace('<p>', '<p2>'), P.replace('<p>', '<p3>')), 'announce'),
    ('other', r'¡%s cacheó a .+!|¡Calcó la habilidad .+ de %s!' % (P, P.replace('<p>', '<p2>')), 'announce'),
    ('other', r'¡%s ahora es de tipo .+!' % P, 'typechange'),
    ('other', r'¡%s devolvió .+!' % P, 'bounce'),
    ('other', r'¡El .+ protege a %s!' % P, 'terrainblock'),
    ('dragged', r'¡%s fue arrastrado al combate!' % P, None),
    ('other', r'¡%s ya está (?:dormido|paralizado|quemado|confuso|envenenado)\.|%s ya está (?:dormido|paralizado|quemado|confuso|envenenado)\.' % (
        P, P.replace('<p>', '<p2>')), 'already'),
    ('other', r'¡Pero los PS de %s están al máximo!' % P, 'fullhp'),
    ('other', r'¡Sonó un cascabel!', 'healbell'),
    ('other', r'¡%s empezó a tener pesadillas!' % P, 'nightmare'),
    ('other', r'¡%s ya no está envenenado!' % P, 'cured'),
    ('other', r'¡%s se liberó de .+!' % P, 'bindend'),
    ('other', r'¡%s ya no sufre los efectos de .+!' % P, 'tauntend'),
    ('other', r'¡Las misteriosas turbulencias debilitaron el ataque!', 'weathermsg'),
    ('struggle', r'¡A %s no le quedan movimientos!' % P, None),
    ('transform', r'¡%s se transformó(?: en %s)?!' % (P, P2), None),
    ('perish', r'¡La cuenta atrás de %s bajó a .+!' % P, None),
    ('perish', r'¡Todos los Pokémon que oyeron la canción se debilitarán en .+ turnos!', None),
    ('evolve', r'¡%s está evolucionando!' % P, None),
    ('evolve', r'¡Felicidades! ¡Tu .+ evolucionó en .+!', None),
    ('evolve', r'¿Qué\?', None),
    ('weather', r'¡Empezó a llover!', 1), ('weather', r'¡El sol pega fuerte!', 2), ('weather', r'¡Se desató una tormenta de arena!', 3),
    ('weather', r'¡Empezó a nevar!', 4), ('weather', r'¡Empezó a llover a cántaros!', 8), ('weather', r'¡El sol pega muy fuerte!', 9),
    ('weather', r'¡Unas misteriosas turbulencias protegen a los Pokémon de tipo Volador!', 7),
    ('weather_end', r'Dejó de llover\.|El sol ya no pega tan fuerte\.|La tormenta de arena amainó\.|Dejó de nevar\.|'
                    r'¡Dejó de llover a cántaros!|¡El sol ya no pega tan fuerte!|¡Las misteriosas turbulencias se disiparon!', None),
    ('other', r'¡La lluvia torrencial no amaina!|¡Las misteriosas turbulencias siguen soplando!|'
              r'¡El ataque de tipo Fuego se apagó por la lluvia torrencial!', 'weathermsg'),
    ('terrain', r'¡La hierba cubrió el terreno de combate!', 1), ('terrain', r'¡La niebla envolvió el terreno de combate!', 2),
    ('terrain', r'¡Una corriente eléctrica recorrió el terreno de combate!', 3),
    ('terrain', r'¡El terreno de combate se volvió muy raro!', 4),
    ('terrain_end', r'¡El terreno de combate volvió a la normalidad!|La hierba desapareció del terreno de combate\.|'
                    r'La niebla desapareció del terreno de combate\.|La electricidad desapareció del terreno de combate\.', None),
    ('hazard', r'¡Hay piedras puntiagudas flotando alrededor (?P<side>del equipo rival|de tu equipo)!', 'rocks'),
    ('hazard', r'¡Hay púas tóxicas esparcidas alrededor (?P<side>del equipo rival|de tu equipo)!', 'tspikes'),
    ('hazard', r'¡Hay púas esparcidas alrededor (?P<side>del equipo rival|de tu equipo)!', 'spikes'),
    ('hazard', r'¡Desaparecieron las (?:piedras puntiagudas|púas tóxicas|púas) alrededor (?P<side>del equipo rival|de tu equipo)!', 'clear'),
    ('hazard_hit', r'¡Unas piedras puntiagudas se clavaron en %s!' % P, 'rocks'),
    ('hazard_hit', r'¡Las púas hieren a %s!' % P, 'spikes'),
    ('tailwind', r'¡Sopla un viento afín a favor (?P<side>del equipo rival|de tu equipo)!', 1),
    ('tailwind', r'¡Dejó de soplar el viento afín a favor (?P<side>del equipo rival|de tu equipo)!', 0),
    ('screen', r'¡.+ hizo (?P<side>al equipo rival|a tu equipo) más resistente .+!', 1),
    ('screen', r'¡Terminó el efecto de .+ en (?P<side>el equipo rival|tu equipo)!', 0),
    ('trickroom', r'¡%s alteró las dimensiones!' % P, 1),
    ('trickroom', r'¡Las dimensiones volvieron a la normalidad!', 0),
    ('other', r'¡Se anularon los cambios en las características de %s!' % P, 'haze'),
    ('ignore', r'¡Policía Felix quiere combatir!|¡Derrotaste a Policía Felix!|Ah, debí esperarlo\.\.\.|'
               r'¡AAAAAA ganó .+ por la victoria!|¡A AAAAAA no le quedan Pokémon!|AAAAAA pagó .+ como premio\.\.\.|'
               r'\.\.\. \.\.\. ¡AAAAAA se desmayó!|.*Felix.*', None),
]
PATTERNS = [(c, re.compile('^' + p + '$'), e) for c, p, e in PATTERNS]


WORK = tbpaths.WORK
ES_ROM = os.path.join(tbpaths.BUILD, 'es', 'rc44.nds')


def es_json(path):
    """A JSON file of the Spanish workspace at the names' commit (lib/names.py)."""
    return json.loads(tbnames.git_show(tbnames.ES_REPO, path))


def en_moves():
    """English move names (as the logs print them) -> ids."""
    d = {}
    for k, v in es_json(tbnames.SOURCES['move']).items():
        if int(k) and v.get('en'):
            d.setdefault(v['en'], int(k))
    return d


def es_names():
    """Spanish names of moves, abilities and items -> ids, from the glossary (the Spanish ROM's names)."""
    out = {}
    for f, kind in (('names_moves', 'move'), ('names_abilities', 'ability'), ('names_items', 'item')):
        d = {}
        for k, v in es_json('work_es/glossary/%s.json' % f).items():
            if int(k) and v.get('es'):
                for name in {v['es'], v.get('es_full') or v['es']}:
                    # an item name given to two ids: the later one, which the battle engine handles (aidata.Data)
                    d[name] = max(int(k), d.get(name, 0)) if kind == 'item' else d.get(name, int(k))
        out[kind] = d
    return out


def species_es():
    """English species name -> the Spanish one where they differ (text/es/0232.json)."""
    en = es_json('work_es/text/en/0232.json')['strings']
    es = es_json('work_es/text/es/0232.json')
    es = es.get('strings', es) if isinstance(es, dict) else es
    return {en[int(k)]: v for k, v in es.items() if int(k) < len(en) and v != en[int(k)]}


class Names:
    def __init__(self, rom=ES_ROM):
        self.es = es_names()
        self.en_move = en_moves()
        self.sp_es = species_es()
        teams = None
        try:
            import gen_simdata
            teams = gen_simdata.all_teams(rom)
        except Exception as e:     # noqa: BLE001
            raise SystemExit('turnlog: cannot read the trainer teams: %s' % e) from e
        self.teams = teams


def find_team(names, team):
    """(team index, slots) of a log team among the exported trainer teams, or (None, why)."""
    slots = team['slots'] if team['slots'] is not None else list(range(len(team['mons'])))
    found = []
    for i, t in enumerate(names.teams):
        if t['name'] != team['name'] or max(slots) >= len(t['team']):
            continue
        if all(t['team'][s]['species'] == m['species'] and [str(x) for x in t['team'][s]['moves']] == m['moves']
               for s, m in zip(slots, team['mons'])):
            found.append(i)
    if len(found) != 1:
        return None, '%d matches for team %r' % (len(found), team['name'])
    return found[0], slots


def find_members(teams, team):
    """[(team index, slot), ...] of a mixed team's members (aivsai --teams mixed draws them from the level-80 pool's
    trainer teams, each with its own set) among the exported teams, the pool's first; None if one is not found."""
    order = sorted(range(len(teams)), key=lambda i: min(x['level'] for x in teams[i]['team']) < 80)
    out = []
    for m in team['mons']:
        hit = next(((i, k) for i in order for k, x in enumerate(teams[i]['team'])
                    if x['species'] == m['species'] and [str(y) for y in x['moves']] == m['moves'] and
                    x['ability'] == m.get('ability') and x['nature'] == m.get('nature') and
                    (x['item'] == m.get('item') or str(m.get('item')).isdigit())), None)     # a nameless item prints its id
        if hit is None:
            return None
        out.append(hit)
    return out


def parse_opts(text, more):
    out = []
    for part in re.split(r', (?=[^,=]+=-?\d)', text):
        if '=' not in part:
            continue
        name, v = part.rsplit('=', 1)
        try:
            out.append((name.strip(), float(v)))
        except ValueError:
            pass
    return out, int(more or 0)


class Game:
    def __init__(self, path):
        self.path = path
        self.run = os.path.basename(os.path.dirname(path))
        self.turns = []
        self.problems = []
        self.unknown = []
        self.winner = None
        self.finished = False


def parse(path, names):
    """One log as a Game: teams (engine side order), turns with state, decisions and segmented facts."""
    g = Game(path)
    lines = log_lines(path)
    head = SCENARIO.match(lines[0])
    if not head:
        g.problems.append('no scenario line')
        return g
    g.scenario, g.game, g.seed, g.reseed = head.group(1), int(head.group(2)), int(head.group(3)), int(head.group(4) or 0)
    teams, side = [None, None], None
    i = 1
    while i < len(lines) and not lines[i].startswith('=== Battle'):
        t, m = TEAM.match(lines[i]), HEADER.match(lines[i])
        if t:
            side = SIDE_OF[t.group(1)]
            name, slots = t.group(2).strip(), None
            cut = CUT.match(name)
            if cut:
                name, slots = cut.group(1), [int(x) - 1 for x in cut.group(4).split(',')]
            teams[side] = {'name': name, 'slots': slots, 'mons': []}
        elif m and side is not None:
            sp, lv, ab, it, mv, nat = m.groups()
            teams[side]['mons'].append({'species': sp.strip(), 'moves': [x.strip() for x in mv.split(',')],
                                        'level': int(lv), 'ability': ab.strip(),
                                        'item': None if it.strip() == '-' else it.strip(), 'nature': nat})
        i += 1
    g.team_idx, g.slots, g.src = [None, None], [None, None], [None, None]
    for s in (0, 1):
        if not teams[s]:
            g.problems.append('no team for side %d' % s)
            return g
        g.team_idx[s], g.slots[s] = find_team(names, teams[s])
        if g.team_idx[s] is None and teams[s]['name'].startswith('Mixed '):
            g.src[s] = find_members(names.teams, teams[s])
            if g.src[s] is not None:
                g.team_idx[s] = -1
                g.slots[s] = teams[s]['slots'] if teams[s]['slots'] is not None else list(range(len(teams[s]['mons'])))
        if g.team_idx[s] is None:
            g.problems.append(g.slots[s])
            return g
    g.teams = teams
    g.level = teams[0]['mons'][0]['level']
    # species name (English and Spanish) -> [set, ...] per side
    members = [collections.defaultdict(list), collections.defaultdict(list)]
    for s in (0, 1):
        for k, mon in enumerate(teams[s]['mons']):
            members[s][mon['species']].append(g.slots[s][k])
            if mon['species'] in names.sp_es:
                members[s][names.sp_es[mon['species']]].append(g.slots[s][k])
    allnames = sorted({n for s in (0, 1) for n in members[s]}, key=len, reverse=True)
    alt = '|'.join(re.escape(n) for n in allnames)
    enemy = re.compile(r'(?:\b(?:El|el|del|al) )(%s) enemigo\b' % alt)
    plain = re.compile(r'(?<![\w{:])(%s)(?![\w}])' % alt)
    set_moves = {}
    for s in (0, 1):
        for k, mon in enumerate(teams[s]['mons']):
            set_moves[(s, g.slots[s][k])] = mon['moves']
    g.members = members
    active = [None, None]           # the set on the field per side, from the turn lines and send-ins

    def set_of(s, name, prefer=None):
        c = members[s].get(name)
        if not c:
            return None
        if prefer in c:
            return prefer
        return c[0]

    def norm(text):
        def ene(m):
            art = m.group(0).split(' ')[0]
            pre = {'del': 'de ', 'al': 'a '}.get(art, '')
            return '%s{1:%s}' % (pre, m.group(1))
        text = enemy.sub(ene, text)
        return plain.sub(lambda m: '{0:%s}' % m.group(1), text)

    def who(tok):
        s, name = int(tok[1]), tok[3:-1]
        return s, set_of(s, name, active[s])

    turn = None
    seg = None
    last_hit = None
    pending = None      # a decision line whose options follow

    def new_seg(kind, s, arg=None):
        nonlocal seg
        seg = {'kind': kind, 'side': s, 'arg': arg, 'facts': []}
        if turn is not None:
            turn['segs'].append(seg)
        return seg

    def fact(code, s=-1, *args):
        if seg is None:
            new_seg('pre', -1)
        seg['facts'].append((code, s) + tuple(args))

    def faint(s, fset):
        if not any(f[0] == 'faint' and f[1] == s and f[2] == fset for sg in turn['segs'] for f in sg['facts']):
            fact('faint', s, fset)

    def action_seg(s, kind, arg=None):
        """The segment of side s's action: a pre-action message (wake, confusion check) opens it, the move joins it."""
        if seg is not None and seg['kind'] == 'act' and seg['side'] == s and seg['arg'] is None and kind == 'move':
            seg['arg'] = arg
            return seg
        return new_seg('act', s, arg if kind == 'move' else None)

    for line in lines[i + 1:]:
        if END.match(line):
            w = END.match(line).group(1)
            g.winner = SIDE_OF[w] if w else None
            g.finished = True
            break
        m = TURN.match(line)
        if m:
            turn = {'n': int(m.group(1)), 'weather': WEATHER.get(m.group(2), 0) if m.group(2) else 0,
                    'wturns': int(m.group(3)) if m.group(3) else 0, 'state': [None, None], 'acts': [None, None],
                    'segs': []}
            g.turns.append(turn)
            seg = None
            pending = None
            continue
        if turn is None:
            continue
        m = STATE.match(line)
        if m and turn['state'][SIDE_OF[m.group(1)]] is None and not turn['segs']:
            s = SIDE_OF[m.group(1)]
            st = {'set': set_of(s, m.group(2).strip(), active[s]), 'hp': int(m.group(3)), 'maxhp': int(m.group(4)),
                  'status': 0, 'toxic': 0, 'confused': 0, 'stages': [0] * 7}
            for tok in (m.group(5) or '').split():
                if tok in STATUS:
                    st['status'], st['toxic'] = STATUS[tok], int(tok == 'TOX')
                elif tok == 'confused':
                    st['confused'] = 1
                else:
                    mt = re.match(r'(Atk|Def|SpA|SpD|Spe|Acc|Eva)([+-]\d+)$', tok)
                    if mt:
                        st['stages'][STAGE_KEYS.index(mt.group(1))] = int(mt.group(2))
                    else:
                        g.problems.append('turn %d: unread state %r' % (turn['n'], tok))
            if st['set'] is None:
                g.problems.append('turn %d: unknown Pokemon %r' % (turn['n'], m.group(2)))
            active[s] = st['set']
            turn['state'][s] = st
            continue
        m = ACT.match(line)
        if m:
            s = SIDE_OF[m.group(1)]
            what = m.group(3)
            a = {'opts': [], 'more': 0, 'strong': -1, 'sw': None, 'sw_w': 0}
            if what.startswith('switch to '):
                a['kind'], a['arg'] = 's', set_of(s, what[10:].strip())
            elif what.startswith('use '):
                a['kind'], a['arg'] = 'i', what[4:]
            else:
                mv = what.rsplit(' on ', 1)[0] if ' on ' in what else what
                a['kind'], a['arg'] = 'm', names.en_move.get(mv, -1)
                if a['arg'] < 0:
                    g.problems.append('turn %d: unknown move %r' % (turn['n'], mv))
            turn['acts'][s] = a
            pending = (s, a, 'act')
            continue
        m = REPL.match(line)
        if m:
            s = SIDE_OF[m.group(1)]
            to = set_of(s, m.group(3).strip())
            new_seg('repl', s, to)
            pending = (s, seg, 'repl')
            seg['opts'], seg['more'] = [], 0
            continue
        m = SCORES.match(line)
        if m and pending and pending[2] == 'act':
            pending[1]['scores'] = parse_scores(m.group(1), names)
            continue
        m = TARGET_SCORES.match(line)
        if m and pending and pending[2] == 'act':
            pending[1].setdefault('target_scores', {})[m.group(1)] = parse_scores(m.group(2), names)
            continue
        m = OPTS.match(line)
        if m and pending:
            opts, more = parse_opts(m.group(1), m.group(2))
            pending[1]['opts'], pending[1]['more'] = opts, more
            continue
        m = FOE.match(line)
        if m and pending and pending[2] == 'act':
            a = pending[1]
            a['strong'] = int(round(float(m.group(1)) * 1000))
            if m.group(2):
                a['sw'] = set_of(pending[0] ^ 1, m.group(2).strip())
                a['sw_w'] = int(round(float(m.group(3)) * 1000))
            continue
        m = FAINT.match(line)
        if m:       # the bench's own faint line, or the battle message: either can be missing (one faint each)
            s = SIDE_OF[m.group(1)]
            faint(s, set_of(s, m.group(2).strip(), active[s]) or 0)
            continue
        if UNKNOWN_STATE.match(line) or line.startswith('            '):
            continue
        if not line.startswith('  >> '):
            if line.strip():
                g.problems.append('turn %d: unread line %r' % (turn['n'], line))
            continue
        raw = line[5:]
        if raw.startswith('[hit] '):
            mh = re.match(r'^\[hit\] (.+?): (.+) (\d+)(?:, (super effective|not very effective))?$', raw)
            if not mh:
                g.problems.append('turn %d: unread hit %r' % (turn['n'], raw))
                continue
            u = seg['side'] if seg is not None and seg['side'] in (0, 1) else -1
            t = u ^ 1 if u >= 0 else -1
            eff = {'super effective': 2, 'not very effective': 3}.get(mh.group(4), 1)
            fact('hit', t, int(mh.group(3)), eff)
            last_hit = seg['facts'][-1]
            continue
        if raw.startswith('[ability] '):
            ma = re.match(r'^\[ability\] (.+?): (.+)$', raw)
            name, ab = ma.group(1), ma.group(2)
            ab_id = names.es['ability'].get(ab, 0)
            cands = [s for s in (0, 1) if name in members[s]]
            s = cands[0] if len(cands) == 1 else (next((s for s in cands if active[s] in members[s][name]), cands[0])
                                                  if cands else -1)
            fact('ability', s, ab_id)
            continue
        text = norm(raw)
        for code, rx, extra in PATTERNS:
            mm = rx.match(text)
            if mm:
                break
        else:
            g.unknown.append(re.sub(r'\{\d:[^}]+\}', '{P}', text))
            continue
        gd = mm.groupdict()
        ptok = gd.get('p') or gd.get('p2') or gd.get('p3') or gd.get('p4')
        ps, pset = who(ptok) if ptok else (-1, None)
        if code == 'faint':
            faint(ps, pset or 0)
            continue
        if code in ('ignore', 'eff'):
            continue
        if code == 'use':
            mv = names.es['move'].get(gd['x'], 0)
            action_seg(ps, 'move', mv)
            continue
        if code == 'quick':         # announced at the turn's start, before the switches: not the order
            if seg is None or seg['kind'] != 'pre':
                new_seg('pre', -1)
            fact('quick', ps)
            continue
        if code in ('asleep', 'wake', 'fullpara', 'flinch', 'confused', 'frozen', 'thaw', 'confend'):
            if code == 'thaw' and raw.find('derritió') >= 0:
                fact('thaw', ps)
                continue
            if not (seg is not None and seg['kind'] == 'act' and seg['side'] == ps and seg['arg'] is None):
                action_seg(ps, 'pre')
            fact(code, ps)
            continue
        if code == 'selfhit':
            fact('selfhit', seg['side'] if seg is not None else -1)
            continue
        if code == 'sendin':
            s = extra
            sset = set_of(s, ptok[3:-1])
            if seg is not None and seg['kind'] == 'repl' and seg['side'] == s and not any(f[0] == 'sendin' for f in seg['facts']):
                fact('sendin', s, sset)
            else:
                new_seg('switch', s, sset)
                fact('sendin', s, sset)
            active[s] = sset
            continue
        if code == 'recall':
            continue
        if code == 'dragged':
            fact('sendin', ps, pset)
            active[ps] = pset
            continue
        if code == 'crit':
            if last_hit is not None and seg is not None and last_hit in seg['facts']:
                k = seg['facts'].index(last_hit)
                seg['facts'][k] = last_hit + (1,)
                last_hit = seg['facts'][k]
            fact('crit', -1)
            continue
        if code == 'nhits':
            n = int(''.join(chr(ord(c) - 0xFEE0) if '０' <= c <= '９' else c for c in gd['n']))
            fact('nhits', -1, n)
            continue
        if code == 'status':
            fact('status', ps, ST[extra])
            continue
        if code == 'stat':
            fact('stat', ps, STAT_NAMES[gd['stat']], DELTA[gd['delta']])
            it = names.es['item'].get(gd.get('x') or '', 0)
            if it and it != 600:        # a pinch berry or Throat Spray used up (Weakness Policy prints its own line)
                fact('item', ps, it, 2)
            continue
        user = seg['side'] if seg is not None and seg['kind'] == 'act' and seg['side'] in (0, 1) else -1
        if code in ('weather', 'terrain', 'tailwind', 'screen', 'trickroom'):
            side = gd.get('side')
            side = -1 if side is None else (1 if 'rival' in side else 0)
            if code in ('tailwind', 'screen') and extra and user >= 0:
                side = user         # the side messages name the wrong team (screens always say "tu equipo")
            fact(code, side, extra)
            continue
        if code in ('hazard',):
            side = 1 if 'rival' in gd['side'] else 0
            if extra != 'clear' and user >= 0:
                side = user ^ 1     # the hazards land on the user's foe; the message names the user's team
            fact('hazard', side, ('rocks', 'spikes', 'tspikes', 'clear').index(extra))
            continue
        if code in RESIDUAL or (code in ('chip', 'heal') and extra in RESIDUAL_CAUSES):
            if seg is None or seg['kind'] not in ('end', 'repl'):
                new_seg('end', -1)      # the end of the turn: its facts are not the last action's
        if code in ('chip', 'heal'):
            fact(code, ps, CAUSE.index(extra), names.es['item'].get(gd.get('x') or '', 0))
            if extra == 'jaboca' and gd.get('q'):       # the berry was the other Pokemon's, now used up
                qs, qset = who(gd['q'])
                fact('item', qs, names.es['item'].get(gd.get('x') or '', 0), 2)
            continue
        if code == 'item':
            it = names.es['item'].get(gd.get('x') or '', 0)
            fact('item', ps, it, ('sash', 'resist', 'used', 'balloon', 'balloonpop', 'whiteherb', 'powerherb', 'knock',
                                  'bugbite', 'cure').index(extra))
            continue
        if code == 'hazard_hit':
            fact('hazard_hit', ps, 0 if extra == 'rocks' else 1)
            continue
        if code == 'other':
            fact('other', ps, extra)
            continue
        if code in ('miss', 'noeffect', 'protected', 'bind') and seg is not None and seg['kind'] == 'act' and seg['side'] in (0, 1):
            ps = seg['side'] ^ 1        # the target of the move: some messages name the wrong side (ANALYST_BRIEF)
        fact(code, ps)
    return g


def parse_scores(text, names):
    """'Name=value, ...' (a scores line) -> [(move id or -1, value)]."""
    return [(names.en_move.get(x.rsplit('=', 1)[0].strip(), -1), int(x.rsplit('=', 1)[1]))
            for x in text.split(', ') if '=' in x]


def write_obs(games, out):
    """The validator's input, one game after another:
         game PATH LEVEL WINNER
         team SIDE TEAM_INDEX N SLOT*N                        (side 0 the player's, 1 the trainer's)
         member SIDE TEAM_INDEX SLOT                          (TEAM_INDEX -1 above: a mixed team, one line per member)
         turn N WEATHER WTURNS
         state SIDE SET HP MAXHP STATUS TOXIC CONFUSED STAGE*7
         act SIDE m MOVE | act SIDE s SET | act SIDE i 0       (then its options)
         opt KIND ARG VALUE                                     (0 a move id, 1 a switch set, 2 an item; the logged ones)
         osc MOVE SCORE                                         (the original AI's factor sum per move, adv-vs-orig logs)
         fsc MOVE SCORE                                         (the same for its rows aimed at the foe, logs from 2026-10-05)
         more N STRONG SW_SET SW_W                              (options not shown; the foe model, -1 when none)
         seg KIND SIDE ARG                                      (act MOVE|0, switch SET, repl SET, pre)
         f CODE SIDE A B C                                      (a fact; CODE is the index in FACTS)
         endgame
    """
    with open(out, 'w') as f:
        for g in games:
            f.write('game %s %d %d\n' % (os.path.relpath(g.path, WORK), g.level, -1 if g.winner is None else g.winner))
            for s in (0, 1):
                f.write('team %d %d %d %s\n' % (s, g.team_idx[s], len(g.slots[s]), ' '.join(map(str, g.slots[s]))))
                for t, k in g.src[s] or []:
                    f.write('member %d %d %d\n' % (s, t, k))
            for t in g.turns:
                f.write('turn %d %d %d\n' % (t['n'], t['weather'], t['wturns']))
                for s in (0, 1):
                    st = t['state'][s]
                    if st and st['set'] is not None:
                        f.write('state %d %d %d %d %d %d %d %s\n' % (s, st['set'], st['hp'], st['maxhp'], st['status'],
                                                                     st['toxic'], st['confused'], ' '.join(map(str, st['stages']))))
                for s in (0, 1):
                    a = t['acts'][s]
                    if not a:
                        continue
                    arg = a['arg'] if a['kind'] in 'ms' else 0
                    f.write('act %d %s %d\n' % (s, a['kind'], -1 if arg is None else arg))
                    write_opts(f, g, s, a, t)
                    for mv, v in a.get('scores', []):
                        f.write('osc %d %d\n' % (mv, v))
                    for mv, v in a.get('target_scores', {}).get('foe', []):
                        f.write('fsc %d %d\n' % (mv, v))
                for sg in t['segs']:
                    arg = sg['arg']
                    f.write('seg %s %d %d\n' % (sg['kind'], sg['side'], -1 if arg is None else arg))
                    if sg['kind'] == 'repl':
                        write_opts(f, g, sg['side'], sg, t, repl=True)
                    for fc in sg['facts']:
                        code, s = fc[0], fc[1]
                        args = [x if isinstance(x, int) else 0 for x in fc[2:]] + [0, 0, 0]
                        if code == 'other':
                            args = [OTHER.index(fc[2]) if fc[2] in OTHER else len(OTHER), 0, 0]
                        f.write('f %d %d %d %d %d\n' % (FACTS.index(code), s, args[0], args[1], args[2]))
            f.write('endgame\n')


NAMES = None
RESIDUAL = ('weather_end', 'terrain_end', 'perish')
RESIDUAL_CAUSES = ('leftovers', 'blacksludge', 'burn', 'poison', 'sand', 'seed', 'veil', 'ingrain', 'curse', 'nightmare',
                   'bind', 'wish')
OTHER = ('veil', 'ingrain', 'bellydrum', 'destiny', 'destinyko', 'endure', 'charge', 'announce', 'typechange', 'bounce',
         'terrainblock', 'dragged', 'already', 'fullhp', 'healbell', 'weathermsg', 'haze', 'nightmare', 'cured', 'bindend',
         'tauntend')


def write_opts(f, g, s, a, t, repl=False):
    """The logged options as (kind, arg, value): kind 0 a move slot of the Pokemon on the field, 1 a switch to a set."""
    rows = []
    for name, v in a.get('opts', []):
        if repl:
            c = g.members[s].get(name)
            rows.append((1, c[0] if c else -1, v))
        elif name.startswith('switch:'):
            c = g.members[s].get(name[7:])
            rows.append((1, c[0] if c else -1, v))
        elif name.startswith('item:'):
            rows.append((2, 0, v))
        else:
            rows.append((0, NAMES.en_move.get(name, -1), v))
    for k, arg, v in rows:
        f.write('opt %d %d %d\n' % (k, arg, int(round(v))))
    if repl:
        f.write('more %d -1 -1 0\n' % a.get('more', 0))
    else:
        f.write('more %d %d %d %d\n' % (a.get('more', 0), a.get('strong', -1), -1 if a.get('sw') is None else a['sw'],
                                         a.get('sw_w', 0)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--runs', default=os.path.join(tbpaths.RUNS, 'aivsai', '*_self*'))
    ap.add_argument('--rom', default=ES_ROM, help='the ROM the games ran on (its trainer teams)')
    ap.add_argument('--orig', action='store_true',
                    help='the adv-vs-orig runs instead (aivsai without --self: not *_self*, *_live or holdout)')
    ap.add_argument('-o', '--out', default=os.path.join(tbpaths.RUNS, 'sim', 'val', 'obs.txt'))
    ap.add_argument('--unknown', action='store_true')
    a = ap.parse_args()
    global NAMES
    names = NAMES = Names(a.rom)
    dirs = sorted(glob.glob(a.runs)) if not a.orig else orig_runs()
    paths = sorted(p for d in dirs for p in glob.glob(os.path.join(d, 's*_g*.log')))
    games, skipped, unknown, problems = [], collections.Counter(), collections.Counter(), collections.Counter()
    for p in paths:
        g = parse(p, names)
        unknown.update(g.unknown)
        if not g.turns or getattr(g, 'team_idx', [None])[0] is None:
            skipped[g.problems[0] if g.problems else 'no turns'] += 1
            continue
        for pr in g.problems:
            problems[re.sub(r'turn \d+: ', '', pr)[:60]] += 1
        games.append(g)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    write_obs(games, a.out)
    nturns = sum(len(g.turns) for g in games)
    nfacts = sum(len(sg['facts']) for g in games for t in g.turns for sg in t['segs'])
    print('%d logs: %d games, %d turns, %d facts -> %s; skipped %d; %d unread messages (%d kinds)' % (
        len(paths), len(games), nturns, nfacts, a.out, sum(skipped.values()), sum(unknown.values()), len(unknown)))
    for why, n in skipped.most_common(8):
        print('  skipped %d: %s' % (n, why))
    for why, n in problems.most_common(8):
        print('  problem %d: %s' % (n, why))
    if a.unknown:
        for t, n in unknown.most_common(60):
            print('%6d  %s' % (n, t))


if __name__ == '__main__':
    main()
