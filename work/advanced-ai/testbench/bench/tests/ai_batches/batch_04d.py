"""Batch 04, author D: recovery and attrition.

When to heal and when healing loses: Recover, Slack Off, Soft-Boiled, Milk Drink, Moonlight and Rest against a foe that
out-damages the heal, a setup sweeper that uses the free turn, a burned attacker, sun-boosted Fire; drain moves against
recoil moves; Toxic against a foe whose own Recover out-heals every attack; Pain Split at low HP, and Pain Split that
would hand HP to the foe; Rest without a Chesto Berry against a two-hit KO.

The ops below extend tests/ai_checks.py without editing it (prefix b04d_, registered in ai_checks.CHECKS on import, before
`with_items` runs). They build ai_checks.Ctx, so every item and ability goes through its vetting and the Gen 5 damage model.

`b04d_plan` plays a fight turn by turn like ai_checks.Race (same order rules, damage margins, drain, recoil, Life Orb,
Sitrus Berry, guaranteed stat changes, end-of-turn damage through Race.chip), but each side follows a plan of moves, one
per turn (the last one repeated), and the plan may hold these status moves:
  heal moves (effect 32: Recover, Slack Off, Soft-Boiled, Milk Drink, Heal Order): half the user's max HP (rounded down
      for the favored side, up for the other), capped at the max HP.
  Moonlight, Synthesis, Morning Sun (effect 132): half in clear weather. The weather versions are not measured in this
      ROM, so both readings are tried and the claim must hold for each: in sun 1/2 and 2/3 (Gen 5), in rain, sand or hail
      1/2 and 1/4 (Gen 5).
  Roost (effect 214): half, like Recover; refused when the user is a Flying type and the foe has a Ground attack (Roost
      takes the Flying type away for the turn, which the plan does not model).
  Rest (effect 37): fails at full HP (refused); otherwise full HP, any status replaced by sleep, and the user then cannot
      act for k turns. The sleep length differs by generation and is not measured, so k = 1, 2 and 3 are all tried.
      No Chesto Berry or Sleep Talk is modeled (refused).
  Pain Split (effect 91): both Pokemon go to floor((HP a + HP b) / 2), capped at each one's max HP.
  Toxic: badly poisons a foe with no status that is not a Poison or Steel type and has none of the abilities or berries
      that stop or cure it; the counter starts at 1 at the first end of turn. Its 90% accuracy is not counted.
  Leech Seed (effect 84): a foe that is not a Grass type loses an eighth of its max HP at each end of turn (after
      Race.chip: weather, items, then poison and burn) and the user gains as much. Its 90% accuracy is not counted.
  a plain self-boosting move (Swords Dance, Nasty Plot, Calm Mind...): its boosts, as ai_checks.Race.setup_boosts.
  Any other status move is refused. A Pokemon that starts asleep or frozen is refused.
"""
import ai_checks
from ai_checks import CHECKS, STATUS, T, Ctx, Race, _actives
from aidata import norm
from ai_helpers import PLAIN, S, mon  # noqa: F401

HEAL_HALF, HEAL_ROOST, HEAL_WEATHER, REST, PAIN_SPLIT, LEECH_SEED = 32, 214, 132, 37, 91, 84
POISON, STEEL, GRASS, FLYING, GROUND = T['Poison'], T['Steel'], T['Grass'], T['Flying'], T['Ground']
# Abilities and items that stop, cure, reflect or profit from a bad poison: Toxic is refused against them.
TOXIC_REFUSED_ABILITIES = {'Immunity', 'Poison Heal', 'Magic Guard', 'Magic Bounce', 'Synchronize', 'Natural Cure',
                           'Shed Skin', 'Hydration', 'Leaf Guard', 'Guts', 'Marvel Scale', 'Toxic Boost', 'Quick Feet'}
TOXIC_REFUSED_ITEMS = {'Lum Berry', 'Pecha Berry', 'Toxic Orb', 'Flame Orb'}
SEED_REFUSED_ABILITIES = {'Magic Guard', 'Liquid Ooze', 'Magic Bounce'}
REST_REFUSED_ITEMS = {'Chesto Berry', 'Lum Berry'}
WEATHER_HEAL = {None: (50,), 'sun': (50, 66), 'rain': (25, 50), 'sand': (25, 50), 'hail': (25, 50)}


def _op4(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(Ctx(d, views, c, ref))
        return fn
    return reg


def _kind(x, mv):
    """What a move does in the plan: 'attack', 'heal', 'rest', 'split', 'toxic', 'seed' or 'setup'."""
    m = x.d.move(mv)
    if m['class'] != STATUS:
        return 'attack'
    if m['effect'] in (HEAL_HALF, HEAL_ROOST, HEAL_WEATHER):
        return 'heal'
    if m['effect'] == REST:
        return 'rest'
    if m['effect'] == PAIN_SPLIT:
        return 'split'
    if m['effect'] == LEECH_SEED:
        return 'seed'
    if norm(mv) == 'toxic':
        return 'toxic'
    r = x.d.moves[m['id']]
    assert r[20] == 7 and r[1] == 2, '%s is a status move the plan does not model' % mv
    return 'setup'


class Plan:
    """One fight between a and b, each following its plan (module docstring). `favored` takes the low damage readings."""

    def __init__(self, x, favored, par_div, burn_div, sleep_k, heal_pct):
        self.x, self.favored, self.par_div, self.burn_div = x, favored, par_div, burn_div
        self.sleep_k, self.heal_pct = sleep_k, heal_pct
        self.race = Race(x, favored, par_div, burn_div)

    def heal_amount(self, r, mv):
        x = self.x
        mx = x.ref(r)['stats']['hp']
        m = x.d.move(mv)
        pct = m['heal'] if m['effect'] != HEAL_WEATHER else self.heal_pct
        if m['effect'] == HEAL_WEATHER and x.weather is None:
            pct = 50
        num = mx * pct
        return num // 100 if r == self.favored else -(-num // 100)

    def vet(self, r, t, mv):
        x = self.x
        k = _kind(x, mv)
        v, tv = x.ref(r), x.ref(t)
        if k == 'attack':
            self.race.vet_move(r, mv, t)
        if k == 'heal' and x.d.move(mv)['effect'] == HEAL_ROOST and FLYING in v['types']:
            assert not any(x.d.move(m)['class'] != STATUS and x.d.move(m)['type'] == GROUND for m in tv['moves']), (
                'Roost on a Flying type facing a Ground attack is not modeled')
        if k == 'rest':
            assert x.item(r) not in REST_REFUSED_ITEMS, 'a berry that wakes %s is not modeled' % v['species']
            assert not any(norm(m) == 'sleeptalk' for m in v['moves']), 'Sleep Talk is not modeled'
        if k == 'toxic':
            assert POISON not in tv['types'] and STEEL not in tv['types'], 'Toxic cannot poison %s' % tv['species']
            assert x.ability(t) not in TOXIC_REFUSED_ABILITIES, '%s has %s' % (tv['species'], x.ability(t))
            assert x.item(t) not in TOXIC_REFUSED_ITEMS, '%s holds %s' % (tv['species'], x.item(t))
        if k == 'seed':
            assert GRASS not in tv['types'], 'Leech Seed cannot seed a Grass type'
            assert x.ability(t) not in SEED_REFUSED_ABILITIES, '%s has %s' % (tv['species'], x.ability(t))
        return k

    def play(self, a, plan_a, b, plan_b, n):
        """(winner, turn): the one left standing when the other faints (None if both or neither within n turns)."""
        x = self.x
        plans = {a: plan_a, b: plan_b}
        foe = {a: b, b: a}
        views = {a: x.ref(a), b: x.ref(b)}
        saved = {r: (views[r]['cur_hp'], views[r]['status']) for r in (a, b)}
        for r in (a, b):
            assert saved[r][1] not in ('slp', 'frz'), '%s starts asleep or frozen: not modeled' % views[r]['species']
        hp = {r: saved[r][0] for r in (a, b)}
        status = {r: saved[r][1] for r in (a, b)}
        tox = {r: 2 if r == self.favored else 1 for r in (a, b)}   # the battle's counter for a starting bad poison
        asleep = {a: 0, b: 0}
        seeded = {}
        recharge = {a: False, b: False}
        x.boosts.clear()
        x.consumed.clear()

        def sync():
            for r in (a, b):
                views[r]['cur_hp'], views[r]['status'] = hp[r], status[r]

        def mx(r):
            return views[r]['stats']['hp']

        try:
            for turn in range(1, n + 1):
                moves = {r: plans[r][min(turn - 1, len(plans[r]) - 1)] for r in (a, b)}
                kinds = {r: self.vet(r, foe[r], moves[r]) for r in (a, b)}
                sync()
                acted = set()
                for r in self.race.order(moves):
                    t = foe[r]
                    if hp[r] <= 0 or hp[t] <= 0:
                        continue
                    acted.add(r)
                    if asleep[r]:
                        asleep[r] -= 1
                        if not asleep[r]:
                            status[r] = None
                        continue
                    if recharge[r]:
                        recharge[r] = False
                        continue
                    mv, k = moves[r], kinds[r]
                    sync()
                    if k == 'heal':
                        hp[r] = min(mx(r), hp[r] + self.heal_amount(r, mv))
                        continue
                    if k == 'rest':
                        assert hp[r] < mx(r), 'Rest fails at full HP'
                        hp[r], status[r], asleep[r], tox[r] = mx(r), 'slp', self.sleep_k, 1
                        continue
                    if k == 'split':
                        avg = (hp[r] + hp[t]) // 2
                        hp[r], hp[t] = min(avg, mx(r)), min(avg, mx(t))
                        continue
                    if k == 'toxic':
                        if status[t] is None:
                            status[t], tox[t] = 'tox', 1
                        continue
                    if k == 'seed':
                        seeded.setdefault(t, r)
                        continue
                    if k == 'setup':
                        for stat, amt in self.race.setup_boosts(r, mv):
                            x.boosts[(r, stat)] = max(-6, min(6, x.boosts.get((r, stat), 0) + amt))
                        continue
                    m = x.d.move(mv)
                    raw = x.d.moves[m['id']]
                    rec = int.from_bytes(raw[18:19], 'little', signed=True)
                    sure = r == self.favored
                    dmg = x.total(r, mv, t, sure) * (0.9 if sure else 1.1)
                    if m['effect'] == ai_checks.SUCKER and (t in acted or kinds[t] != 'attack'):
                        dmg = 0
                    if x.endures(r, mv, t):
                        dmg = min(dmg, hp[t] - 1)
                        if x.item(t) == 'Focus Sash':
                            x.consumed.add(t)
                    dealt = min(int(dmg), hp[t])
                    hp[t] -= dealt
                    if dealt and x.item(r) == 'Life Orb' and x.ability(r) != 'Magic Guard' and not (
                            x.ability(r) == 'Sheer Force' and x.has_secondary(mv)):
                        hp[r] -= max(1, mx(r) // 10)
                    if dealt and rec > 0:
                        hp[r] = min(mx(r), hp[r] + max(1, dealt * rec // 100))
                    if dealt and rec < 0 and x.ability(r) not in ('Rock Head', 'Magic Guard'):
                        basis = min(x.total(r, mv, t, False), hp[t] + dealt) if sure else dealt
                        hp[r] -= max(1, basis * (-rec) // 100)
                    if m['effect'] == ai_checks.SELF_KO:
                        hp[r] = 0
                    if m['effect'] == ai_checks.RECHARGE and dealt:
                        recharge[r] = True
                    if raw[1] in (ai_checks.Q_USER_STAT, ai_checks.Q_TARGET_DROP):
                        who = r if raw[1] == ai_checks.Q_USER_STAT else t
                        for j in range(3):
                            stat = ai_checks.STAT_IDS.get(raw[21 + j])
                            amt, chance = int.from_bytes(raw[24 + j:25 + j], 'little', signed=True), raw[27 + j]
                            if stat and amt and chance == 100:
                                if who == t and amt < 0 and x.ability(t) in ai_checks.DROP_BLOCKERS[stat] and x.ability(r) not in ai_checks.MOLD_BREAKER:
                                    continue
                                x.boosts[(who, stat)] = max(-6, min(6, x.boosts.get((who, stat), 0) + amt))
                    for q in (r, t):
                        if 0 < hp[q] <= mx(q) // 2 and x.item(q) in ('Sitrus Berry', 'Oran Berry'):
                            hp[q] = min(mx(q), hp[q] + (mx(q) // 4 if x.item(q) == 'Sitrus Berry' else 10))
                            x.consumed.add(q)
                    if hp[t] <= 0 or hp[r] <= 0:
                        break
                # the end of the turn comes for whoever is still standing, even when the other has fainted
                for r in self.race.order(moves):
                    if hp[r] > 0:
                        sync()
                        hp[r] = self.race.chip(r, hp[r], tox[r])
                        if status[r] == 'tox':
                            tox[r] += 1
                if hp[a] > 0 and hp[b] > 0:
                    for t, s in seeded.items():
                        if hp[t] > 0 and hp[s] > 0:
                            drain = min(hp[t], max(1, mx(t) // 8))
                            hp[t] -= drain
                            hp[s] = min(mx(s), hp[s] + drain)
                alive = [r for r in (a, b) if hp[r] > 0]
                if len(alive) == 1:
                    return alive[0], turn
                if not alive:
                    return None, turn
            return None, n
        finally:
            for r in (a, b):
                views[r]['cur_hp'], views[r]['status'] = saved[r]
            x.boosts.clear()
            x.consumed.clear()


def _plan(x, r, spec):
    """A plan as a tuple of moves; '*' alone means each attack of r, tried one at a time."""
    if spec == '*':
        return [(mv,) for mv in x.ref(r)['moves'] if x.d.move(mv)['class'] != STATUS]
    return [tuple(spec) if isinstance(spec, (tuple, list)) else (spec,)]


def _variants(x, plans):
    """Every reading of the unmeasured details the plan holds: paralysis and burn rules, Rest's sleep, weather heals."""
    moves = {mv for p in plans for mv in p}
    rest = any(_kind(x, mv) == 'rest' for mv in moves)
    weather_heal = any(_kind(x, mv) == 'heal' and x.d.move(mv)['effect'] == HEAL_WEATHER for mv in moves)
    for par_div in (4, 2):
        for burn_div in (8, 16):
            for k in ((1, 2, 3) if rest else (2,)):
                for pct in (WEATHER_HEAL[x.weather] if weather_heal else (50,)):
                    yield par_div, burn_div, k, pct


def _entry_hit(x, a, df, entry):
    """The most a's entry move ('*' = each of its attacks) does to df as df switches in (maximum x 1.1)."""
    moves = [mv for mv in x.ref(a)['moves'] if x.d.move(mv)['class'] != STATUS] if entry == '*' else [entry]
    return max(int(x.total(a, mv, df, False) * 1.1) for mv in moves)


@_op4('b04d_plan')
def plan(x):
    """('b04d_plan', a, plan_a, b, plan_b, n, want[, entry]): a fight between one Pokemon of each side played turn by turn, each
    following its plan (a move, or a tuple of moves for turns 1, 2, ..., the last repeated; '*' = each attack of that Pokemon,
    tried one at a time). want 'win': a is favored (its minimum x 0.9, the foe's maximum x 1.1) and knocks b out within n turns
    while still standing, under every plan of b. want 'lose': b is favored and knocks a out within n turns, before a knocks b
    out, under every plan of a. Every reading of the unmeasured details is tried and the claim must hold in each: paralysis at
    a quarter and a half, burn at an eighth and a sixteenth, Rest's sleep 1, 2 or 3 turns, a weather heal at both values
    (module docstring). With `entry` (a move of b, or '*' for the strongest of b's attacks), a is a bench member that switches in
    and first takes that hit at its maximum x 1.1, so 'win' then means the switch-in wins from there."""
    a, plan_a, b, plan_b, n, want = x.args[:6]
    entry = x.args[6] if len(x.args) > 6 else None
    assert want in ('win', 'lose'), 'want is win or lose'
    _actives(x, a, b)
    favored = a if want == 'win' else b
    plans_a, plans_b = _plan(x, a, plan_a), _plan(x, b, plan_b)
    assert not (want == 'win' and len(plans_a) > 1) and not (want == 'lose' and len(plans_b) > 1), (
        "'*' belongs to the side whose every option is tried")
    av = x.ref(a)
    start = av['cur_hp']
    if entry is not None:
        hit = _entry_hit(x, b, a, entry)
        assert hit < start, '%s can be knocked out as it switches in (up to %d of %d)' % (av['species'], hit, start)
    try:
        if entry is not None:
            av['cur_hp'] = start - hit
        for pa in plans_a:
            for pb in plans_b:
                for par_div, burn_div, k, pct in _variants(x, [pa, pb]):
                    who, turn = Plan(x, favored, par_div, burn_div, k, pct).play(a, pa, b, pb, n)
                    assert who == favored, '%s %s vs %s %s: %s within %d turns (paralysis /%d, burn /%d, Rest sleep %d, weather heal %d%%)' % (
                        av['species'], '/'.join(pa), x.ref(b)['species'], '/'.join(pb),
                        'neither wins (both faint, or both still stand)' if who is None else x.ref(who)['species'] + ' wins on turn %d' % turn, n, par_div, burn_div, k, pct)
    finally:
        av['cur_hp'] = start


@_op4('b04d_ko_boosted')
def ko_boosted(x):
    """('b04d_ko_boosted', a, mv, df, stat, stage, frac): with its stat ('atk' or 'spa') raised by that many stages (a setup move
    used on an earlier turn), a's move is a sure KO on df from that fraction of df's max HP (minimum x 0.9 >= that HP), and df
    cannot hang on through Focus Sash or Sturdy."""
    a, mv, df, stat, stage, frac = x.args
    dv = x.ref(df)
    saved = dv['cur_hp']
    x.boosts[(a, stat)] = stage
    dv['cur_hp'] = int(dv['stats']['hp'] * frac)
    try:
        lo = x.total(a, mv, df, True)
        assert not x.endures(a, mv, df), '%s keeps 1 HP' % dv['species']
        assert lo * 0.9 >= dv['cur_hp'], '%s at +%d does %d at least: not a sure KO on %s from %d HP' % (mv, stage, lo, dv['species'], dv['cur_hp'])
    finally:
        dv['cur_hp'] = saved
        x.boosts.clear()


@_op4('b04d_outheals')
def outheals(x):
    """('b04d_outheals', r, heal_move, foe, mv): r's heal move (half its max HP; a weather heal at its lower reading) restores
    more than the foe's mv ('*' = each of the foe's attacks) can do to r at most (maximum x 1.1): the foe cannot wear r down while
    r heals."""
    r, heal_move, foe, mv = x.args
    assert _kind(x, heal_move) == 'heal', '%s is not a heal move' % heal_move
    m = x.d.move(heal_move)
    pct = min(WEATHER_HEAL[x.weather]) if m['effect'] == HEAL_WEATHER else m['heal']
    heal = x.ref(r)['stats']['hp'] * pct // 100
    moves = [q for q in x.ref(foe)['moves'] if x.d.move(q)['class'] != STATUS] if mv == '*' else [mv]
    for q in moves:
        hi = int(x.total(foe, q, r, False) * 1.1)
        assert hi < heal, '%s heals %d, %s does up to %d' % (heal_move, heal, q, hi)


@_op4('b04d_overpowers_heal')
def overpowers_heal(x):
    """('b04d_overpowers_heal', foe, mv, r, heal_move): the foe's mv does more to r at least (minimum x 0.9) than r's heal move
    restores (half its max HP; a weather heal at its higher reading): healing loses ground every turn."""
    foe, mv, r, heal_move = x.args
    assert _kind(x, heal_move) == 'heal', '%s is not a heal move' % heal_move
    m = x.d.move(heal_move)
    pct = max(WEATHER_HEAL[x.weather]) if m['effect'] == HEAL_WEATHER else m['heal']
    heal = -(-x.ref(r)['stats']['hp'] * pct // 100)
    lo = int(x.total(foe, mv, r, True) * 0.9)
    assert lo > heal, '%s does %d at least, %s heals %d' % (mv, lo, heal_move, heal)


@_op4('b04d_toxic_lands')
def toxic_lands(x):
    """('b04d_toxic_lands', a, df): a has Toxic and it can badly poison df: df has no status, is not a Poison or Steel type, and
    has no ability or item that stops, reflects or cures it (its 90% accuracy is not counted)."""
    a, df = x.args
    assert any(norm(m) == 'toxic' for m in x.ref(a)['moves']), '%s has no Toxic' % x.ref(a)['species']
    dv = x.ref(df)
    assert dv['status'] is None, '%s already has a status' % dv['species']
    assert POISON not in dv['types'] and STEEL not in dv['types'], 'Toxic cannot poison %s' % dv['species']
    assert x.ability(df) not in TOXIC_REFUSED_ABILITIES and x.item(df) not in TOXIC_REFUSED_ITEMS, '%s can stop or cure it' % dv['species']


@_op4('b04d_split_change')
def split_change(x):
    """('b04d_split_change', a, df, sign): Pain Split sets both to floor((HP a + HP df) / 2), capped at each max HP. sign '+':
    a gains HP and df loses HP; sign '-': a loses HP and df gains HP (the absolute HP decide, not the fractions)."""
    a, df, sign = x.args
    av, dv = x.ref(a), x.ref(df)
    avg = (av['cur_hp'] + dv['cur_hp']) // 2
    da = min(avg, av['stats']['hp']) - av['cur_hp']
    dd = min(avg, dv['stats']['hp']) - dv['cur_hp']
    if sign == '+':
        assert da > 0 and dd < 0, 'Pain Split: %s %+d, %s %+d' % (av['species'], da, dv['species'], dd)
    else:
        assert da < 0 and dd > 0, 'Pain Split: %s %+d, %s %+d' % (av['species'], da, dv['species'], dd)


SCENARIOS = ai_checks.with_items([
    # --- healing that loses: near-full HP against a setup sweeper, a foe that out-damages the heal, priority, Rest's sleep
    S('b04d_heal_feeds_setup', 'recovery',
      'Clefable at 80% is faster than Conkeldurr and Moonblast (2x) takes 69-82%, so two Moonblasts win before a second '
      'Poison Jab (2x, 59-69%) lands, even if Conkeldurr uses Swords Dance; Soft-Boiled heals only a fifth here and Poison Jab '
      'out-damages it every turn: after a heal, Conkeldurr can Swords Dance and +2 Poison Jab KOs Clefable from full HP',
      [mon('Conkeldurr', ['Swords Dance', 'Poison Jab', 'Drain Punch', 'Stone Edge'], evs={'hp': 252, 'atk': 64})],
      [mon('Clefable', ['Soft-Boiled', 'Moonblast', 'Flamethrower', 'Thunder Wave'], hp=0.8)],
      best=['Moonblast'], bad=['Soft-Boiled', 'Flamethrower'],
      checks=[('mfaster', 'e0', 'p0'), ('mnoko', 'e0', 'Moonblast', 'p0'), ('mnoko', 'p0', 'Poison Jab', 'e0'),
              ('b04d_plan', 'e0', 'Moonblast', 'p0', '*', 2, 'win'),
              ('b04d_plan', 'e0', 'Moonblast', 'p0', ('Swords Dance', 'Poison Jab'), 2, 'win'),
              ('b04d_plan', 'e0', ('Soft-Boiled', 'Moonblast'), 'p0', ('Swords Dance', 'Poison Jab'), 3, 'lose'),
              ('b04d_plan', 'e0', ('Soft-Boiled', 'Moonblast'), 'p0', 'Poison Jab', 4, 'lose'),
              ('b04d_plan', 'e0', 'Flamethrower', 'p0', 'Poison Jab', 4, 'lose'),
              ('b04d_ko_boosted', 'p0', 'Poison Jab', 'e0', 'atk', 2, 1.0),
              ('b04d_overpowers_heal', 'p0', 'Poison Jab', 'e0', 'Soft-Boiled')]),
    S('b04d_recover_loses_ground', 'recovery',
      "Celebi at 45% is faster than Tyranitar, but Crunch (2x, 66-80%) out-damages Recover's half and the sandstorm chips "
      'another sixteenth, so healing only buys one turn, and Celebi falls before two Leaf Storms or Giga Drains can KO; '
      'Psychic cannot touch a Dark type; Breloom resists all three attacks and Drain Punch (4x) KOs: switch',
      [mon('Tyranitar', ['Crunch', 'Stone Edge', 'Earthquake', 'Dragon Dance'], ability='Sand Stream')],
      [mon('Celebi', ['Recover', 'Leaf Storm', 'Giga Drain', 'Psychic'], hp=0.45),
       mon('Breloom', ['Drain Punch', 'Mach Punch', 'Seed Bomb', 'Spore'])],
      best=['switch:Breloom'], bad=['Leaf Storm', 'Giga Drain', 'Psychic'],
      checks=[('weather', 'sand'), ('mfaster', 'e0', 'p0'), ('mko', 'p0', 'Crunch', 'e0'),
              ('b04d_overpowers_heal', 'p0', 'Crunch', 'e0', 'Recover'),
              ('b04d_plan', 'e0', 'Recover', 'p0', 'Crunch', 3, 'lose'),
              ('b04d_plan', 'e0', ('Recover', 'Leaf Storm'), 'p0', 'Crunch', 3, 'lose'),
              ('b04d_plan', 'e0', ('Recover', 'Giga Drain'), 'p0', 'Crunch', 3, 'lose'),
              ('b04d_plan', 'e0', '*', 'p0', 'Crunch', 3, 'lose'),
              ('meff', 'e0', 'Psychic', 'p0', 0.0),
              ('b04d_plan', 'e1', 'Drain Punch', 'p0', '*', 2, 'win', '*')]),
    S('b04d_priority_beats_heal', 'recovery',
      "Cresselia at 20% would survive Bullet Punch after Moonlight (it heals to 70%), but Technician Bullet Punch (2x) has "
      'priority, comes first and KOs it at 20%; its own attacks are resisted; Chandelure resists Bullet Punch and X-Scissor, '
      'is immune to Superpower, outspeeds Scizor and Flamethrower (4x) KOs: switch',
      [mon('Scizor', ['Bullet Punch', 'X-Scissor', 'Superpower', 'Swords Dance'], ability='Technician')],
      [mon('Cresselia', ['Moonlight', 'Psychic', 'Moonblast', 'Ice Beam'], hp=0.2),
       mon('Chandelure', ['Flamethrower', 'Shadow Ball', 'Energy Ball', 'Will-O-Wisp'])],
      best=['switch:Chandelure'], bad=['Moonlight', 'Psychic', 'Moonblast', 'Ice Beam'],
      checks=[('has_ability', 'p0', 'Technician'), ('mpri', 'p0', 'Bullet Punch', 1), ('mko', 'p0', 'Bullet Punch', 'e0'),
              ('first', 'p0', 'Bullet Punch', 'e0', 'Moonlight'), ('mnoko_at', 'p0', 'Bullet Punch', 'e0', 0.7),
              ('b04d_plan', 'e0', 'Moonlight', 'p0', 'Bullet Punch', 1, 'lose'),
              ('b04d_plan', 'e0', '*', 'p0', 'Bullet Punch', 1, 'lose'),
              ('meff', 'p0', 'Superpower', 'e1', 0.0),
              ('b04d_plan', 'e1', 'Flamethrower', 'p0', '*', 1, 'win', '*')]),
    S('b04d_rest_sleeps_into_ko', 'recovery',
      'Speed-trained Suicune at 35% moves first, but Rest without a Chesto Berry or Sleep Talk leaves it asleep, and Leaf Blade '
      '(2x, 58-69%) KOs it from full HP in two hits, so it never acts again; attacking also loses it; Volcarona resists '
      "Leafeon's attacks (none does over 30% to it) and outspeeds it, and Flamethrower (2x) KOs: switch",
      [mon('Leafeon', ['Leaf Blade', 'X-Scissor', 'Knock Off', 'Swords Dance'])],
      [mon('Suicune', ['Rest', 'Scald', 'Ice Beam', 'Calm Mind'], hp=0.35, evs={'spe': 252}),
       mon('Volcarona', ['Flamethrower', 'Bug Buzz', 'Giga Drain', 'Quiver Dance'])],
      best=['switch:Volcarona'], ok=['Ice Beam'], bad=['Rest', 'Calm Mind'],
      checks=[('mfaster', 'e0', 'p0'), ('mko', 'p0', 'Leaf Blade', 'e0'),
              ('b04d_plan', 'e0', 'Rest', 'p0', 'Leaf Blade', 2, 'lose'),
              ('b04d_plan', 'e0', 'Calm Mind', 'p0', 'Leaf Blade', 1, 'lose'),
              ('b04d_plan', 'e0', '*', 'p0', 'Leaf Blade', 3, 'lose'),
              ('mfaster', 'e1', 'p0'), ('b04d_plan', 'e1', 'Flamethrower', 'p0', '*', 1, 'win', '*')]),
    S('b04d_pain_split_feeds_foe', 'recovery',
      'Drifblim at 30% looks lower than Dusknoir at 45%, but Pain Split works on HP, not fractions: Drifblim has 67 HP and '
      'Dusknoir 54, so it would lose 7 and heal Dusknoir by 6, and Shadow Punch (2x) then KOs it; Drifblim is faster and '
      'Shadow Ball (2x) KOs Dusknoir first',
      [mon('Dusknoir', ['Shadow Punch', 'Ice Punch', 'Earthquake', 'Will-O-Wisp'], hp=0.45)],
      [mon('Drifblim', ['Pain Split', 'Shadow Ball', 'Thunderbolt', 'Thunder Wave'], hp=0.3)],
      best=['Shadow Ball'], bad=['Pain Split', 'Thunderbolt'],
      checks=[('mfaster', 'e0', 'p0'), ('mko', 'e0', 'Shadow Ball', 'p0'), ('mnoko', 'e0', 'Thunderbolt', 'p0'),
              ('b04d_split_change', 'e0', 'p0', '-'), ('mko', 'p0', 'Shadow Punch', 'e0'),
              ('b04d_plan', 'e0', 'Pain Split', 'p0', 'Shadow Punch', 1, 'lose'),
              ('b04d_plan', 'e0', 'Thunderbolt', 'p0', 'Shadow Punch', 1, 'lose'),
              ('meff', 'p0', 'Earthquake', 'e0', 0.0)]),

    # --- healing that wins: a burned attacker, a sun-boosted hit
    S('b04d_milk_drink_vs_burn', 'recovery',
      "Burned Machamp's Close Combat (2x, halved: 46-54%) KOs Miltank at 30%, and Body Slam (33-40%) cannot KO Machamp at 50% "
      'first (only with the burn at the end of the turn, after Miltank has fallen); Milk Drink takes Miltank to 80%, the burn '
      'and the Defense drop from Close Combat wear Machamp down, and Body Slam finishes it',
      [mon('Machamp', ['Close Combat', 'Knock Off', 'Stone Edge', 'Bullet Punch'], status='brn', hp=0.5)],
      [mon('Miltank', ['Milk Drink', 'Body Slam', 'Earthquake', 'Curse'], hp=0.3)],
      best=['Milk Drink'],
      checks=[('has_status', 'p0', 'brn'), ('mfaster', 'e0', 'p0'), ('mko', 'p0', 'Close Combat', 'e0'),
              ('mnoko', 'e0', 'Body Slam', 'p0'), ('mnoko_at', 'p0', 'Close Combat', 'e0', 0.8),
              ('b04d_plan', 'e0', ('Milk Drink', 'Body Slam'), 'p0', '*', 3, 'win')]),
    S('b04d_moonlight_vs_sun', 'weather',
      "The player's Drought sun boosts Torkoal's Flamethrower, which KOs Umbreon at 25%; Umbreon is faster, and after "
      'Moonlight (half its HP, or two thirds if the sun counts) it is at 75% or more and Flamethrower cannot KO; Dark Pulse '
      'does a third and Toxic does not stop the hit',
      [mon('Torkoal', ['Flamethrower', 'Earth Power', 'Solar Beam', 'Yawn'], ability='Drought')],
      [mon('Umbreon', ['Moonlight', 'Dark Pulse', 'Toxic', 'Protect'], hp=0.25)],
      best=['Moonlight'], bad=['Dark Pulse', 'Toxic'],
      checks=[('weather', 'sun'), ('mfaster', 'e0', 'p0'), ('mko', 'p0', 'Flamethrower', 'e0'),
              ('mnoko_at', 'p0', 'Flamethrower', 'e0', 0.75), ('mnoko', 'e0', 'Dark Pulse', 'p0'),
              ('b04d_plan', 'e0', 'Dark Pulse', 'p0', 'Flamethrower', 1, 'lose')]),

    # --- drain against recoil, Toxic in both directions
    S('b04d_horn_leech_over_wood_hammer', 'recovery',
      'Rillaboom at 55% is faster than Snorlax at 75%; Wood Hammer (50-59%) looks like a two-hit KO, but its recoil and Body '
      'Slam (33-39%) knock Rillaboom out first, while Horn Leech (31-37%) heals half of what it deals and wins in three hits; '
      'Knock Off and U-turn are too weak',
      [mon('Snorlax', ['Body Slam', 'Earthquake', 'Crunch'], hp=0.75)],
      [mon('Rillaboom', ['Horn Leech', 'Wood Hammer', 'Knock Off', 'U-turn'], hp=0.55)],
      best=['Horn Leech'], bad=['Wood Hammer', 'Knock Off', 'U-turn'],
      checks=[('mfaster', 'e0', 'p0'), ('nhko', 'e0', 'Wood Hammer', 'p0', 2),
              ('b04d_plan', 'e0', 'Horn Leech', 'p0', '*', 3, 'win'),
              ('b04d_plan', 'e0', 'Wood Hammer', 'p0', 'Body Slam', 6, 'lose'),
              ('b04d_plan', 'e0', 'Knock Off', 'p0', 'Body Slam', 6, 'lose'),
              ('b04d_plan', 'e0', 'U-turn', 'p0', 'Body Slam', 6, 'lose')]),
    S('b04d_toxic_breaks_recover', 'status',
      "Neither side can wear the other down: Gastrodon's best attack (Earth Power, under 29%) is less than Milotic's Recover "
      "heals, and Milotic's (Moonblast, under 41%) less than Gastrodon's; only Toxic, whose damage grows every turn, makes "
      'progress; Recover at full HP does nothing',
      [mon('Milotic', ['Recover', 'Scald', 'Moonblast', 'Ice Beam'], item='Leftovers')],
      [mon('Gastrodon', ['Toxic', 'Recover', 'Earth Power', 'Scald'])],
      best=['Toxic'], ok=['Earth Power'], bad=['Recover'],
      checks=[('has_item', 'p0', 'Leftovers'), ('b04d_outheals', 'p0', 'Recover', 'e0', '*'),
              ('b04d_outheals', 'e0', 'Recover', 'p0', '*'), ('b04d_toxic_lands', 'e0', 'p0')]),
    S('b04d_toxic_too_slow', 'status',
      "Nidoking at 65% is faster than Togekiss and Sludge Wave (2x) KOs it in two hits even through Leftovers, so Togekiss "
      'gets one Air Slash in; Toxic spends a turn and lets Togekiss land a second Air Slash (40-48%), or use Nasty Plot, and '
      'Nidoking falls first; Ice Beam (2x, 39-46%) is too weak to win the race and Earth Power cannot touch a Flying type',
      [mon('Togekiss', ['Air Slash', 'DazzlngGleam', 'Flamethrower', 'Nasty Plot'], item='Leftovers')],
      [mon('Nidoking', ['Toxic', 'Sludge Wave', 'Earth Power', 'Ice Beam'], hp=0.65)],
      best=['Sludge Wave'], bad=['Toxic', 'Ice Beam', 'Earth Power'],
      checks=[('mfaster', 'e0', 'p0'), ('meff', 'e0', 'Sludge Wave', 'p0', 2.0), ('b04d_toxic_lands', 'e0', 'p0'),
              ('b04d_plan', 'e0', 'Sludge Wave', 'p0', '*', 2, 'win'),
              ('b04d_plan', 'e0', 'Sludge Wave', 'p0', ('Nasty Plot', 'Air Slash'), 2, 'win'),
              ('b04d_plan', 'e0', ('Toxic', 'Sludge Wave'), 'p0', 'Air Slash', 3, 'lose'),
              ('b04d_plan', 'e0', 'Ice Beam', 'p0', 'Air Slash', 3, 'lose'), ('meff', 'e0', 'Earth Power', 'p0', 0.0)]),
])
