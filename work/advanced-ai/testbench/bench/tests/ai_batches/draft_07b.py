"""Batch 07, part b (draft): positions where a strong player knows the right play. Themes of this part: the cover move against a
resisting switch-in that has Intimidate; keeping the AI's only answer to a Pokemon still to come (an Iron Defense and Body Press
wall) instead of trading it now; and a faster foe that boosts bulk and damage (Calm Mind, Bulk Up), where Roar after the boost or
Toxic beats the slower boost race, and its opposite, where the boost does not change the race and attacking is right.

The ops below extend tests/ai_checks.py without editing it. Each is registered in ai_checks.CHECKS on import (prefix b07b_),
before `with_items` runs. The rules, on top of the hack's data and the Gen 5 formula of ai_checks:
  Body Press (C7, Gen 8 rule): Body Press (effect 433, 80 power, Fighting, physical) uses its user's Defense stat and Defense
      stages in place of Attack, so Iron Defense (+2 Defense) doubles its damage and Intimidate does not lower it. The target's
      Defense, the type chart, STAB and a burn's halving apply as for any physical move. Black Belt (x1.2) and Muscle Band (x1.1)
      raise its power. Refused, because the Gen 8 rule for them is not certain: an attacker with an ability or item that changes
      Attack (Huge Power, Pure Power, Guts, Hustle, Choice Band, Defeatist, Slow Start...) or Defense (Marvel Scale), and a target
      with Unaware while the user has a Defense stage. b07b_fight, b07b_ko, b07b_noko, b07b_frac, b07b_wins_after and
      b07b_loses_after are the ops of batch_06a.py, tests/ai_checks.py and batch_05a.py run on C7, so a fight or a race can hold
      Body Press (and Iron Defense, a plain self-boosting move b06_fight already plays). Seen in this hack: tools/aicalc.py
      models Body Press on the user's Defense and its stages, and 152 of the 173 Body Press hits of qa/aivsai/runs it compares
      fall inside its range (13 more fit a critical hit); Kommo-o at Def +4 did 175 to Tentacruel, inside 171-202 and far
      above the 57-68 of Def 0 (runs/20261003_123719/s023_g1.log turn 22).
  Switch-in hits (b07b_entry_beats, b07b_entry_nhko): the damage an attacker's move does to a bench member that switches in this
      turn, with that member on the field: its Intimidate lowers the attacker's Attack by one stage first (Gen 5: Intimidate
      triggers on entry, before the turn's moves; Clear Body, White Smoke and Hyper Cutter block it; seen in this hack,
      runs/20261003_101454/s004_g0.log turn 4). Refused: a leaving active
      with Intimidate (its drop would stay on the attacker), an attacker with Download (it read the leaving foe), a switch-in with
      a weather ability, doubles.
  Phazing (b07b_phaze): Roar and Whirlwind (effect 28) have priority -6, so a user whose foe picks any move of higher priority
      moves after it, and the foe's stat stages from that turn are gone when it is dragged out. The move works only when the
      target's side has a bench member with HP left. In a trainer battle the replacement is a random bench member, so a key that
      depends on it uses a player with one bench member. Seen in this hack: the move data's priority is -6; Kangaskhan's Roar
      came after the slower Wobbuffet's Counter (-5) (runs/20261004_022215_self_5v6r/s001_g1.log turn 3) and Breloom's
      Whirlwind after the slower Blissey's Splash (tests/run/factprobe/slpsw_0.log turn 3), and each dragged a bench member in;
      stages are cleared when a Pokemon leaves the field (the Espeon of that Roar log). Refused because nothing in this ROM
      has shown them: Suction Cups, Guard Dog and Soundproof on the target.
  Destiny Bond is not modeled: the scenario that offers it states the Gen 5 rule (the user moves first, the foe's attack then
      knocks it out, and the attacker faints too) and proves only the order and the KO. Seen in this hack: 17 bonds went off
      in qa/aivsai/runs, 15 of them in the turn the bond was made.
  b07b_cannot_hurt: every damaging move of the attacker does nothing to the target (type chart and type-immune abilities), so the
      target never loses HP to it.
"""
import importlib.util
import os

import ai_checks
from ai_checks import CHECKS, STATUS, Ctx, with_items
from ai_helpers import PLAIN, S, mon  # noqa: F401

_here = os.path.dirname(os.path.abspath(__file__))


def _ops(part):
    """The op functions of an earlier batch file (loading it registers its ops again, unchanged)."""
    spec = importlib.util.spec_from_file_location('ai_batch_%s_ops_for_07b' % part, os.path.join(_here, 'batch_%s.py' % part))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_b05, _b06 = _ops('05a'), _ops('06a')

BODY_PRESS, PHAZE = 433, 28
ATTACK_CHANGERS = {'Huge Power', 'Pure Power', 'Guts', 'Hustle', 'Toxic Boost', 'Defeatist', 'Slow Start', 'Flare Boost',
                   'Solar Power', 'Marvel Scale'}
ATTACK_ITEMS = {'Choice Band', 'Light Ball', 'Thick Club'}
PHAZE_BLOCKERS = {'Suction Cups', 'Guard Dog', 'Soundproof'}


class C7(Ctx):
    """ai_checks.Ctx with Body Press (module docstring)."""

    def _press(self, a, mv):
        return self.d.move(mv)['effect'] == BODY_PRESS

    def power(self, a, mv, df):
        if not self._press(a, mv):
            return super().power(a, mv, df)
        bp = self.d.move(mv)['power']
        it = self.item(a)
        if it == 'Black Belt':
            bp *= 1.2
        if it == 'Muscle Band':
            bp *= 1.1
        return int(bp)

    def attack(self, a, mv, df):
        if not self._press(a, mv):
            return super().attack(a, mv, df)
        av = self.ref(a)
        assert av['ability'] not in ATTACK_CHANGERS, '%s has %s: its effect on Body Press is not modeled' % (av['species'], av['ability'])
        assert self.item(a) not in ATTACK_ITEMS, '%s holds %s: its effect on Body Press is not modeled' % (av['species'], self.item(a))
        stage = self.boosts.get((a, 'def'), 0)
        assert not (stage and self.ability(df) == 'Unaware'), 'Unaware against a boosted Body Press is not modeled'
        return int(av['stats']['def'] * self.stage_mult(stage))


def _op7(name, ctx=C7):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(ctx(d, views, c, ref))
        return fn
    return reg


for _name, _fn in (('b07b_fight', _b06.fight), ('b07b_ko', ai_checks.mko), ('b07b_noko', ai_checks.mnoko),
                   ('b07b_frac', ai_checks.mfrac), ('b07b_wins_after', _b05.wins_after),
                   ('b07b_loses_after', _b05.loses_after), ('b07b_eff', ai_checks.meff), ('b07b_first', ai_checks.first),
                   ('b07b_nhko', ai_checks.nhko), ('b07b_endures', ai_checks.endures)):
    _op7(_name)(_fn)


# --- a switch-in's own entry

class _Entering:
    """p stands on the field in place of its side's active for the damage it takes this turn (module docstring)."""

    def __init__(self, x, a, p):
        self.x, self.a, self.p = x, a, p

    def __enter__(self):
        x, a, p = self.x, self.a, self.p
        assert not x.double, 'switch-in hits are a singles claim'
        side = x.side(p)
        assert p not in x.actives[side], '%s is already on the field' % x.ref(p)['species']
        leaving = x.actives[side][0]
        assert x.ability(leaving) != 'Intimidate', '%s has Intimidate: its drop would stay on the attacker' % x.ref(leaving)['species']
        assert x.ability(a) != 'Download', '%s has Download, which read the leaving foe' % x.ref(a)['species']
        assert x.ability(p) not in ai_checks.WEATHER_ABILITIES, '%s would change the weather' % x.ref(p)['species']
        self.saved = x.actives[side]
        x.actives[side] = [p]
        return x

    def __exit__(self, *exc):
        self.x.actives[self.x.side(self.p)] = self.saved
        return False


@_op7('b07b_entry_beats')
def entry_beats(x):
    """('b07b_entry_beats', a, m1, m2, p): on bench member p as it switches in (its Intimidate in force), a's m1 at its minimum
    beats m2 at its maximum by 5%."""
    a, m1, m2, p = x.args
    with _Entering(x, a, p):
        lo1, hi2 = x.total(a, m1, p, True), x.total(a, m2, p, False)
        assert lo1 > hi2 * 1.05, 'on %s as it comes in, %s does %d at least and %s up to %d' % (x.ref(p)['species'], m1, lo1, m2, hi2)


@_op7('b07b_entry_nhko')
def entry_nhko(x):
    """('b07b_entry_nhko', a, mv, p, n, want): on bench member p as it switches in (its Intimidate in force), n hits of a's move are
    a sure KO (want True: n x minimum x 0.9 >= p's HP) or surely not one (want False: n x maximum x 1.1 < p's HP)."""
    a, mv, p, n, want = x.args
    with _Entering(x, a, p):
        hp = x.ref(p)['cur_hp']
        if want:
            lo = x.total(a, mv, p, True)
            assert n * lo * 0.9 >= hp, '%s x%d does %d at least to %s as it comes in (%d HP)' % (mv, n, n * lo, x.ref(p)['species'], hp)
        else:
            hi = x.total(a, mv, p, False)
            assert n * hi * 1.1 < hp, '%s x%d does up to %d to %s as it comes in (%d HP)' % (mv, n, n * hi, x.ref(p)['species'], hp)


# --- Roar and Whirlwind

@_op7('b07b_phaze')
def phaze(x):
    """('b07b_phaze', a, mv, t): a's Roar or Whirlwind drags t out after t's own move, whatever t picks (module docstring)."""
    a, mv, t = x.args
    assert not x.double, 'phazing is a singles claim'
    m = x.d.move(mv)
    assert m['effect'] == PHAZE, '%s is not Roar or Whirlwind' % mv
    tv = x.ref(t)
    for tm in tv['moves']:
        assert x.d.move(tm)['priority'] > m['priority'], '%s has %s, which does not go before %s' % (tv['species'], tm, mv)
    assert x.ability(t) not in PHAZE_BLOCKERS, '%s has %s, which this ROM has not shown to work or fail' % (tv['species'], x.ability(t))
    bench = x.views['player' if t[0] == 'p' else 'enemy'][1:]
    assert any(v['cur_hp'] > 0 for v in bench), '%s has no bench member to bring in' % tv['species']


@_op7('b07b_cannot_hurt')
def cannot_hurt(x):
    """('b07b_cannot_hurt', a, df): every damaging move of a has no effect on df."""
    a, df = x.args
    for mv in x.ref(a)['moves']:
        if x.d.move(mv)['class'] != STATUS:
            assert x.effectiveness(a, mv, df) == 0, '%s\'s %s can hurt %s' % (x.ref(a)['species'], mv, x.ref(df)['species'])


SCENARIOS = with_items([
    # --- 3. the move good against the stay and the switch

    S('b07b_cover_intimidate_resist', 'switch',
      'Lucario outspeeds Tyranitar at 45% and Close Combat (4x), Meteor Mash and Flash Cannon all KO it, so the player switches to '
      'Granbull, which resists Fighting and whose Intimidate cuts Lucario\'s Attack as it comes in; Flash Cannon is special, so it '
      'ignores the drop and takes 58-68% of Granbull (two hits KO), while Meteor Mash at -1 takes 37-44% and Close Combat about a tenth',
      [mon('Tyranitar', ['Crunch', 'Stone Edge', 'Earthquake', 'Dragon Dance'], hp=0.45),
       mon('Granbull', ['Play Rough', 'Crunch', 'Earthquake', 'Thunder Wave'], ability='Intimidate', evs={'hp': 252, 'def': 252})],
      [mon('Lucario', ['Close Combat', 'Meteor Mash', 'Flash Cannon', 'ExtremeSpeed'])],
      best=['Flash Cannon'], ok=['Meteor Mash'], bad=['ExtremeSpeed'],
      checks=[('b07b_first', 'e0', 'Flash Cannon', 'p0', 'Earthquake'), ('b07b_ko', 'e0', 'Flash Cannon', 'p0'),
              ('b07b_ko', 'e0', 'Meteor Mash', 'p0'), ('b07b_ko', 'e0', 'Close Combat', 'p0'),
              ('b07b_noko', 'e0', 'ExtremeSpeed', 'p0'), ('b07b_eff', 'e0', 'Close Combat', 'p1', 0.5),
              ('b07b_entry_beats', 'e0', 'Flash Cannon', 'Meteor Mash', 'p1'),
              ('b07b_entry_beats', 'e0', 'Meteor Mash', 'Close Combat', 'p1'),
              ('b07b_entry_nhko', 'e0', 'Flash Cannon', 'p1', 2, True),
              ('b07b_entry_nhko', 'e0', 'Meteor Mash', 'p1', 2, False)]),

    # --- 4. keeping the only answer to a Pokemon still to come

    S('b07b_db_keeps_press_answer', 'switch',
      "Gengar at 85% is faster than Hydreigon, whose Dark Pulse KOs it, and its own attacks do under half; Destiny Bond would trade "
      "it for Hydreigon, but Gengar is the AI's only answer to Orthworm (Iron Defense, then Body Press, which uses its Defense): no "
      "Orthworm attack touches a Ghost, while Grimmsnarl loses to it; Grimmsnarl takes any Hydreigon hit (at most 38%) and Spirit "
      "Break (4x) KOs Hydreigon next, so switching keeps Gengar for Orthworm",
      [mon('Hydreigon', ['Dark Pulse', 'Flamethrower', 'Earth Power', 'Draco Meteor']),
       mon('Orthworm', ['Iron Defense', 'Body Press', 'Rest', 'Sleep Talk'])],
      [mon('Gengar', ['Shadow Ball', 'Sludge Bomb', 'Destiny Bond', 'Thunderbolt'], hp=0.85),
       mon('Grimmsnarl', ['Spirit Break', 'Crunch', 'Sucker Punch', 'Bulk Up'])],
      best=['switch:Grimmsnarl'],
      checks=[('b07b_first', 'e0', 'Destiny Bond', 'p0', 'Dark Pulse'), ('b07b_ko', 'p0', 'Dark Pulse', 'e0'),
              ('b07b_noko', 'e0', 'Sludge Bomb', 'p0'), ('b07b_noko', 'e0', 'Shadow Ball', 'p0'),
              ('b07b_cannot_hurt', 'p1', 'e0'), ('b07b_nhko', 'e0', 'Shadow Ball', 'p1', 2),
              ('b07b_wins_after', 'e1', 'Spirit Break', 'p0', '*', 2, [('p0', '*', 'e1')]),
              ('b07b_fight', 'e1', '*', 'p1', ('Iron Defense', 'Body Press'), 12, 'lose'),
              ('b07b_fight', 'e1', '*', 'p1', ('Iron Defense', 'Iron Defense', 'Body Press'), 12, 'lose')]),

    S('b07b_stay_keeps_sweeper_answer', 'switch',
      'Nidoking at 70% is slower than Espeon, whose Psychic KOs it, so it falls first whatever it picks; Weavile is immune to Psychic '
      'and looks like the switch-in, but Dazzling Gleam (2x) takes 73-87% of it, and then Dragonite\'s ExtremeSpeed (priority +2) '
      'KOs it before Ice Punch; coming in at full HP after Nidoking faints, Weavile outspeeds Espeon and Crunch KOs it, then it '
      'survives ExtremeSpeed (at most 55%) and Ice Punch (4x) KOs Dragonite, so Nidoking stays and Weavile stays healthy; '
      'the switch also wins if the player clicks Psychic (Weavile takes nothing and Nidoking lives), so it is ok, but only '
      'staying wins against every reply',
      [mon('Espeon', ['Psychic', 'DazzlngGleam', 'Shadow Ball', 'Calm Mind'], evs={'spa': 252}),
       mon('Dragonite', ['ExtremeSpeed', 'Outrage', 'Earthquake', 'Fire Punch'], evs={'atk': 252})],
      [mon('Nidoking', ['Earth Power', 'Sludge Wave', 'Thunderbolt', 'Flamethrower'], hp=0.7),
       mon('Weavile', ['Crunch', 'Ice Punch', 'Ice Shard', 'Knock Off'], evs={'atk': 252})],
      best=['Earth Power', 'Sludge Wave', 'Thunderbolt', 'Flamethrower'], ok=['switch:Weavile'],
      checks=[('mfaster', 'p0', 'e0'), ('b07b_ko', 'p0', 'Psychic', 'e0'), ('b07b_eff', 'p0', 'Psychic', 'e1', 0.0),
              ('b05_loses_after', 'e1', '*', 'p1', 'ExtremeSpeed', [('p0', 'DazzlngGleam', 'e1')]),
              ('b05_wins_after', 'e1', 'Crunch', 'p0', '*', 1, [('p0', 'DazzlngGleam', 'e1')]),
              ('race', 'e1', 'Crunch', 'p0', '*', 1), ('race', 'e1', 'Ice Punch', 'p1', '*', 2),
              ('b07b_first', 'p1', 'ExtremeSpeed', 'e1', 'Ice Shard'), ('loses', 'e0', '*', 'p1', 'Earthquake')]),

    # --- 5. a faster foe boosting bulk and damage

    S('b07b_roar_after_calm_mind', 'setup',
      'Latias is faster and has Calm Mind; Heatran\'s best hit on it is Flash Cannon (30-35%) and one Calm Mind is enough for Latias '
      'to win whatever Heatran attacks with; Roar (priority -6) goes after the boost, drags Latias out with its boost gone and brings '
      'in the player\'s only other Pokemon, Scizor, which Flamethrower (4x) KOs next turn even after Heatran takes a Surf (at most 51%)',
      [mon('Latias', ['Calm Mind', 'Dragon Pulse', 'Surf', 'Recover']),
       mon('Scizor', ['Bullet Punch', 'U-turn', 'Superpower', 'Swords Dance'])],
      [mon('Heatran', ['Roar', 'Flamethrower', 'Earth Power', 'Flash Cannon'])],
      best=['Roar'],
      checks=[('b07b_phaze', 'e0', 'Roar', 'p0'), ('mfaster', 'p0', 'e0'),
              ('setup_wins', 'p0', 'Calm Mind', 'Surf', 'e0', '*', 8),
              ('mnoko', 'p0', 'Surf', 'e0'), ('mnoko', 'p0', 'Dragon Pulse', 'e0'),
              ('b05_wins_after', 'e0', 'Flamethrower', 'p1', '*', 1, [('p0', '*', 'e0')]),
              ('mfrac', 'e0', 'Flash Cannon', 'p0', 0.29, 0.36)]),

    S('b07b_toxic_calm_mind_stall', 'status',
      'Suicune is faster and neither side\'s attacks do more than 14% a hit; if Milotic attacks, Calm Mind turns the trade into a sure '
      'loss, but Toxic (90% accurate) ignores Suicune\'s rising Sp. Def: after it, Scald every turn wins whether Suicune attacks at '
      'once or uses Calm Mind up to six times first; Recover at full HP does nothing',
      [mon('Suicune', ['Calm Mind', 'Scald', 'Ice Beam'])],
      [mon('Milotic', ['Toxic', 'Scald', 'Ice Beam', 'Recover'])],
      best=['Toxic'], bad=['Recover'],
      checks=[('mfaster', 'p0', 'e0'), ('b06_fight', 'e0', '*', 'p0', ('Calm Mind', 'Scald'), 12, 'lose'),
              ('b06_fight', 'e0', '*', 'p0', ('Calm Mind', 'Ice Beam'), 12, 'lose'),
              ('b06_fight', 'e0', ('Toxic', 'Scald'), 'p0', '*', 14, 'win')] +
             [('b06_fight', 'e0', ('Toxic', 'Scald'), 'p0', ('Calm Mind',) * k + (mp,), 16, 'win')
              for mp in ('Scald', 'Ice Beam') for k in range(1, 7)]),

    S('b07b_bulk_up_no_sp_def', 'setup',
      'Kommo-o is faster and has Bulk Up, but Bulk Up raises Defense, not Sp. Def: Psychic (2x, 64-76%) KOs it in two hits whether '
      'it attacks or boosts up to six times first, and its best hit, Dragon Claw, does at most 37%; Toxic only hands it a free turn, '
      'and Psyshock hits the Defense that Bulk Up raises',
      [mon('Kommo-o', ['Bulk Up', 'Drain Punch', 'Dragon Claw', 'Iron Head'])],
      [mon('Gothitelle', ['Psychic', 'Psyshock', 'Toxic', 'Shadow Ball'])],
      best=['Psychic'],
      checks=[('mfaster', 'p0', 'e0'), ('b06_fight', 'e0', 'Psychic', 'p0', '*', 12, 'win'),
              ('b06_beats', 'e0', 'Psychic', 'Psyshock', 'p0')] +
             [('b06_fight', 'e0', 'Psychic', 'p0', ('Bulk Up',) * k + (mp,), 12, 'win')
              for mp in ('Drain Punch', 'Dragon Claw', 'Iron Head') for k in range(1, 7)]),

    S('b07b_whirlwind_toxic_steel', 'setup',
      'Jirachi is faster and has Calm Mind, after which it wins whatever Mandibuzz attacks with; Toxic cannot poison a Steel type, '
      'so the answer is Whirlwind (priority -6): it goes after the boost, drags Jirachi out with the boost gone and brings in '
      'Breloom, the player\'s only other Pokemon, which Air Slash (4x) KOs next turn even after Mandibuzz takes a Thunderbolt (at '
      'most 47%)',
      [mon('Jirachi', ['Calm Mind', 'Psychic', 'Thunderbolt', 'Flash Cannon']),
       mon('Breloom', ['Mach Punch', 'Seed Bomb', 'Rock Tomb', 'Swords Dance'])],
      [mon('Mandibuzz', ['Whirlwind', 'Toxic', 'Air Slash', 'Dark Pulse'])],
      best=['Whirlwind'], bad=['Toxic'],
      checks=[('b07b_phaze', 'e0', 'Whirlwind', 'p0'), ('type', 'p0', 'Steel'), ('mfaster', 'p0', 'e0'),
              ('setup_wins', 'p0', 'Calm Mind', 'Thunderbolt', 'e0', '*', 8),
              ('mnoko', 'p0', 'Thunderbolt', 'e0'), ('mnoko', 'p0', 'Psychic', 'e0'), ('mnoko', 'p0', 'Flash Cannon', 'e0'),
              ('b05_wins_after', 'e0', 'Air Slash', 'p1', '*', 1, [('p0', '*', 'e0')])]),

    S('b07b_calm_mind_vs_physical', 'setup',
      'Mr. Mime is faster and has Calm Mind, but Calm Mind raises Sp. Atk and Sp. Def, not Defense: Waterfall (58-69%) KOs it in two '
      'hits whether it attacks or boosts up to six times first, and its best hit, Psychic, does at most 36%; Roar and Toxic only '
      'delay a fight that Waterfall already wins',
      [mon('Mr. Mime', ['Calm Mind', 'Psychic', 'DazzlngGleam', 'Focus Blast']),
       mon('Snorlax', ['Body Slam', 'Earthquake', 'Crunch', 'Curse'])],
      [mon('Gyarados', ['Roar', 'Toxic', 'Waterfall', 'Earthquake'])],
      best=['Waterfall'],
      checks=[('mfaster', 'p0', 'e0'),
              ('b06_fight', 'e0', 'Waterfall', 'p0', '*', 14, 'win')] +
             [('b06_fight', 'e0', 'Waterfall', 'p0', ('Calm Mind',) * k + (mp,), 14, 'win')
              for mp in ('Psychic', 'DazzlngGleam', 'Focus Blast') for k in range(1, 7)]),
])
