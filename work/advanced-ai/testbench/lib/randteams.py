"""Random teams for the AI battles: the Spanish tools/aifuzz.py generator and its move and item lists.

Taken unchanged from the Spanish workspace's tools/aifuzz.py (dc8577c) into lib/ because three directories use them:
fuzz/aifuzz.py (its battles), versus/aiteams.py (random_team for aivsai --teams random) and props/aiprops.py (ITEMS).
"""
import random

PLAYER_NO = {'U-turn', 'Volt Switch', 'Baton Pass', 'Teleport', 'Parting Shot', 'Flip Turn', 'Memento', 'Explosion',
             'Selfdestruct', 'Healing Wish', 'Lunar Dance', 'Final Gambit', 'Perish Song', 'Destiny Bond', 'Struggle',
             'Pursuit'}   # Pursuit: the menu never accepts it (the Chinese ROM neither; qa/ai_research/menulock.py)
ITEMS = [None, None, None, 'Leftovers', 'Life Orb', 'Choice Scarf', 'Sitrus Berry', 'Focus Sash', 'Expert Belt',
         'Choice Band', 'Lum Berry']   # no Black Sludge: on a non-Poison holder the engine's message reads item 0xFFFF (inherited assert)
# no Choice items for the player: once the locked move is out of PP the menu accepts no move and never offers
# Struggle, so the battle cannot go on (the Chinese ROM too; qa/ai_research/menulock.py); the AI's side Struggles
PLAYER_ITEMS = [i for i in ITEMS if not (i or '').startswith('Choice')]
TRAINER_ITEMS = ['Full Restore', 'Hyper Potion', 'Full Heal', 'Max Potion']
MAX_SPECIES, MAX_MOVE = 493, 620


def random_team(d, rng, n, level, player):
    team = []
    damaging = [m for m in range(1, MAX_MOVE) if m in d.move_name and d.move(m)['class'] and d.move(m)['power']
                and d.move_name[m] not in PLAYER_NO]
    anymove = [m for m in range(1, MAX_MOVE) if m in d.move_name and d.move_name[m] not in ('Struggle',)]
    while len(team) < n:
        sp = rng.randrange(1, MAX_SPECIES + 1)
        if sp not in d.species_name or d.species(sp)['base']['hp'] == 0:
            continue
        pool = damaging if player else anymove
        moves = []
        while len(moves) < 4:
            m = rng.choice(pool)
            if m not in moves:
                moves.append(m)
        abilities = [a for a in d.species(sp)['abilities'] if a in d.ability_name]
        team.append({'species': d.species_name[sp], 'level': level, 'moves': [d.move_name[m] for m in moves],
                     'ability': d.ability_name[rng.choice(abilities)] if abilities else 'Run Away',
                     'item': rng.choice(PLAYER_ITEMS if player else ITEMS)})
    return team


def battle_spec(d, seed, double=False):
    rng = random.Random(seed)
    level = rng.randrange(30, 66)
    enemy = random_team(d, rng, rng.randrange(2, 7), level, False)
    player = random_team(d, rng, 2 if double else 1, min(100, level + rng.randrange(3, 9)), True)
    items = [rng.choice(TRAINER_ITEMS) for _ in range(rng.choice((0, 0, 1, 2)))]
    return {'player': player, 'enemy': enemy, 'items': items}
