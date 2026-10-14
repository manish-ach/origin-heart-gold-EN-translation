"""Batch 06, part a: lessons from the round S2 AI-vs-AI battles turned into turn-1 positions (draft_06b.py and draft_06c.py hold
the rest). Themes of this part: the move that also hurts the foe's switch-in, and its opposite (the foe's active wins the exchange,
so it stays and the move for the stay case is best); Counter, Mirror Coat and Metal Burst on a foe that survives the hit; a Shadow
Tag Wobbuffet trapping an attacker.

Theme 6 of the brief (the replacement after a faint) is left out: the bench grades the first decision of turn 1 (tools/aibench.py
stops at the first action setter the AI calls), and a replacement is chosen in the middle of a turn, after a faint, so no turn-1
position can ask for it.

The ops below extend tests/ai_checks.py without editing it. Every op builds an ai_checks.Ctx, so items and abilities go through its
vetting and a key never rests on an effect that was silently ignored. Each op is registered in ai_checks.CHECKS on import (prefix
b06_), before `with_items` runs; draft_06b.py and draft_06c.py load this file for the ops when they are not registered yet. Two ops
of earlier batches are reused as they are: b05_absorbs (batch_05a.py) and b04d_ko_boosted (batch_04d.py); every bench run loads
those batches before the drafts. The rules, on top of the hack's data and the Gen 5 formula of ai_checks:
  The ops of tests/ai_checks.py (ko, noko, noko_at, ko_at, eff, faster, first, frac, beats, endures, nhko, race, loses, has_*)
      under a b06_ name, so a scenario's claims read alike.
  The fight (b06_fight): ai_checks.Race's turn rules (order by priority then Speed under both paralysis rules, damage margins with
      the favored side's minimum x 0.9 and the other side's maximum x 1.1, Focus Sash and Sturdy, recoil, drain, Life Orb, Sitrus
      Berry, guaranteed stat changes, end-of-turn damage, burn at an eighth and at a sixteenth), each side following a plan of moves,
      one per turn (the last repeated). A plan may hold, besides attacks:
        a plain self-boosting move (Swords Dance, Dragon Dance, Nasty Plot, Iron Defense...): its stages after the user moves;
        Shell Smash (effect 308): +2 Attack, Sp. Atk and Speed, -1 Defense and Sp. Def (Gen 5); a White Herb held by the user
            restores the lowered stats at once and is used up. Shell Smash and the herb are not measured in this ROM.
        a status move the target's ability absorbs (the b05_absorbs abilities: Motor Drive +1 Speed, Lightningrod and Storm Drain
            +1 Sp. Atk, Sap Sipper +1 Attack, Volt Absorb, Water Absorb and Dry Skin heal a quarter): it does nothing else.
        a powder move (flag bit 28: Sleep Powder, Spore, Stun Spore, PoisonPowder, Cotton Spore...) into a Grass type or an
            Overcoat holder: it does nothing (the Gen 6 rule; see b06_powder_immune).
        Leech Seed (effect 84): an eighth of a non-Grass target's max HP at each end of turn, to the user.
        Toxic: badly poisons a target with no status that is not a Poison or Steel type and has none of the abilities or
            berries that stop or cure it (b04d's list); the counter starts at 1 at the first end of turn and the damage is
            n/16 of max HP, n going up by one each turn (measured, ENGINE_FACTS.md round 2: 10, 20, 30... of 175). Its 90%
            accuracy is not counted. A second Toxic on a poisoned target does nothing.
      Counter, Mirror Coat and Metal Burst return 2x (physical), 2x (special) or 1.5x (either) the damage of the hit their user
      took earlier in the same turn, read at the margin worst for the favored side; with no such hit they do nothing.
      Glaive Rush (effect 456): after its user uses it, every attack on that user does double damage until the user moves again
      (Gen 9; seen in this hack's AI-vs-AI logs, round S2 analyst 2: Shadow Punch 190 and Shadow Sneak 97 on Baxcalibur, not
      measured). Sucker Punch fails when its target has already moved this turn or does not use an attack (Counter, Mirror Coat
      and Metal Burst count as attacks).
"""
import ai_checks
from ai_checks import (CHECKS, MOLD_BREAKER, PHYSICAL, SPECIAL, STATUS, T, TYPES, Ctx, Race, _actives, with_items)
from aidata import norm
from ai_helpers import PLAIN, S, mon  # noqa: F401

SHELL_SMASH, GLAIVE_RUSH, LEECH_SEED = 308, 456, 84
ENDEAVOR, METAL_BURST, COUNTER, MIRROR_COAT, PIVOT = 189, 227, 89, 144, 228
FLAG_POWDER = 1 << 28
REFLECT = {COUNTER: (2, PHYSICAL), MIRROR_COAT: (2, SPECIAL), METAL_BURST: (1.5, None)}
GRASS, GHOST, ELECTRIC = T['Grass'], T['Ghost'], T['Electric']
ABSORB = {'Volt Absorb': 'Electric', 'Motor Drive': 'Electric', 'Lightningrod': 'Electric', 'Water Absorb': 'Water',
          'Storm Drain': 'Water', 'Dry Skin': 'Water', 'Sap Sipper': 'Grass'}
TOXIC_REFUSED_ABILITIES = {'Immunity', 'Poison Heal', 'Magic Guard', 'Magic Bounce', 'Synchronize', 'Natural Cure', 'Shed Skin',
                           'Hydration', 'Leaf Guard', 'Guts', 'Marvel Scale', 'Toxic Boost', 'Quick Feet'}
TOXIC_REFUSED_ITEMS = {'Lum Berry', 'Pecha Berry', 'Toxic Orb', 'Flame Orb'}
ABSORB_BOOST = {'Motor Drive': 'spe', 'Lightningrod': 'spa', 'Storm Drain': 'spa', 'Sap Sipper': 'atk'}


def _op6(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(Ctx(d, views, c, ref))
        return fn
    return reg


for _name, _fn in (('b06_ko', ai_checks.mko), ('b06_noko', ai_checks.mnoko), ('b06_noko_at', ai_checks.mnoko_at),
                   ('b06_ko_at', ai_checks.mko_at), ('b06_eff', ai_checks.meff), ('b06_faster', ai_checks.mfaster),
                   ('b06_first', ai_checks.first), ('b06_frac', ai_checks.mfrac), ('b06_beats', ai_checks.mbeats),
                   ('b06_endures', ai_checks.endures), ('b06_has_item', ai_checks.has_item),
                   ('b06_has_ability', ai_checks.has_ability), ('b06_has_status', ai_checks.has_status),
                   ('b06_pri', ai_checks.mpri), ('b06_nhko', ai_checks.nhko), ('b06_no_nhko', ai_checks.no_nhko),
                   ('b06_race', ai_checks.race), ('b06_loses', ai_checks.loses)):
    _op6(_name)(_fn)


# --- the fight

def _powder_blocked(x, a, mv, t):
    m = x.d.move(mv)
    return bool(m['flags'] & FLAG_POWDER) and (GRASS in x.ref(t)['types'] or x.ability(t) == 'Overcoat') and \
        x.ability(a) not in MOLD_BREAKER


def _kind(x, a, t, mv):
    """What a move does in a fight (module docstring)."""
    m = x.d.move(mv)
    if m['effect'] in REFLECT:
        return 'reflect'
    if m['class'] != STATUS:
        return 'attack'
    if m['effect'] == SHELL_SMASH:
        return 'smash'
    if norm(mv) == 'toxic':
        tv = x.ref(t)
        assert not ({T['Poison'], T['Steel']} & set(tv['types'])), 'Toxic cannot poison %s' % tv['species']
        assert x.ability(t) not in TOXIC_REFUSED_ABILITIES, '%s has %s' % (tv['species'], x.ability(t))
        assert x.item(t) not in TOXIC_REFUSED_ITEMS, '%s holds %s' % (tv['species'], x.item(t))
        return 'toxic'
    if m['effect'] == LEECH_SEED:
        assert GRASS not in x.ref(t)['types'], 'Leech Seed cannot seed a Grass type'
        assert x.ability(t) not in ('Magic Guard', 'Liquid Ooze', 'Magic Bounce'), '%s has %s' % (x.ref(t)['species'], x.ability(t))
        return 'seed'
    ab = x.ability(t)
    if ab in ABSORB and ABSORB[ab] == TYPES[m['type']] and x.ability(a) not in MOLD_BREAKER:
        return 'absorbed'
    if _powder_blocked(x, a, mv, t):
        return 'nothing'
    r = x.d.moves[m['id']]
    assert r[20] == 7 and r[1] == 2, '%s is a status move the fight does not model' % mv
    return 'setup'


class Fight:
    """One fight between a and b, each following its plan; `favored` takes the low damage readings (module docstring)."""

    def __init__(self, x, favored, par_div, burn_div):
        self.x, self.favored = x, favored
        self.race = Race(x, favored, par_div, burn_div)

    def boost(self, r, stat, amt):
        x = self.x
        x.boosts[(r, stat)] = max(-6, min(6, x.boosts.get((r, stat), 0) + amt))

    def play(self, a, plan_a, b, plan_b, n):
        """(winner, turn): the one left standing when the other faints (None if both or neither within n turns)."""
        x, race = self.x, self.race
        plans, foe = {a: plan_a, b: plan_b}, {a: b, b: a}
        views = {a: x.ref(a), b: x.ref(b)}
        saved = {r: views[r]['cur_hp'] for r in (a, b)}
        saved_status = {r: views[r]['status'] for r in (a, b)}
        for r in (a, b):
            assert views[r]['status'] not in ('slp', 'frz'), '%s starts asleep or frozen: not modeled' % views[r]['species']
            assert views[r]['status'] != 'tox', 'bad poison is not modeled in a fight'
        hp = dict(saved)
        mx = {r: views[r]['stats']['hp'] for r in (a, b)}
        vuln, recharge, seeded, tox = set(), set(), {}, {}
        x.boosts.clear()
        x.consumed.clear()

        def sync():
            for r in (a, b):
                views[r]['cur_hp'] = hp[r]

        try:
            for turn in range(1, n + 1):
                moves = {r: plans[r][min(turn - 1, len(plans[r]) - 1)] for r in (a, b)}
                kinds = {r: _kind(x, r, foe[r], moves[r]) for r in (a, b)}
                for r in (a, b):
                    if kinds[r] == 'attack':
                        race.vet_move(r, moves[r], foe[r])
                sync()
                acted, hit_by = set(), {}
                for r in race.order(moves):
                    t = foe[r]
                    if hp[r] <= 0 or hp[t] <= 0:
                        continue
                    acted.add(r)
                    vuln.discard(r)
                    if r in recharge:
                        recharge.discard(r)
                        continue
                    mv, k = moves[r], kinds[r]
                    sync()
                    if k == 'nothing':
                        continue
                    if k == 'absorbed':
                        ab = x.ability(t)
                        if ab in ABSORB_BOOST:
                            self.boost(t, ABSORB_BOOST[ab], 1)
                        else:
                            hp[t] = min(mx[t], hp[t] + mx[t] // 4)
                        continue
                    if k == 'seed':
                        seeded.setdefault(t, r)
                        continue
                    if k == 'toxic':
                        if not views[t]['status'] and t not in tox:
                            tox[t] = 1
                        continue
                    if k == 'reflect':
                        mult, cls = REFLECT[x.d.move(mv)['effect']]
                        if r in hit_by and (cls is None or x.d.move(hit_by[r])['class'] == cls):
                            low = r == self.favored     # the reading worst for the favored side
                            base = x.total(t, hit_by[r], r, low) * (0.9 if low else 1.1)
                            hp[t] -= min(hp[t], int(int(base) * mult))
                            if hp[t] <= 0:
                                break
                        continue
                    if k == 'setup':
                        for stat, amt in race.setup_boosts(r, mv):
                            self.boost(r, stat, amt)
                        continue
                    if k == 'smash':
                        for stat, amt in (('atk', 2), ('spa', 2), ('spe', 2), ('def', -1), ('spd', -1)):
                            self.boost(r, stat, amt)
                        if x.item(r) == 'White Herb':
                            for stat in ('def', 'spd'):
                                if x.boosts.get((r, stat), 0) < 0:
                                    x.boosts[(r, stat)] = 0
                            x.consumed.add(r)
                        continue
                    m = x.d.move(mv)
                    raw = x.d.moves[m['id']]
                    rec = int.from_bytes(raw[18:19], 'little', signed=True)
                    sure = r == self.favored
                    dmg = x.total(r, mv, t, sure) * (0.9 if sure else 1.1)
                    if t in vuln:
                        dmg *= 2
                    if m['effect'] == ai_checks.SUCKER and (t in acted or kinds[t] not in ('attack', 'reflect')):
                        dmg = 0
                    if x.endures(r, mv, t) and hp[t] == mx[t]:
                        dmg = min(dmg, hp[t] - 1)
                        if x.item(t) == 'Focus Sash':
                            x.consumed.add(t)
                    dealt = min(int(dmg), hp[t])
                    hp[t] -= dealt
                    if dealt:
                        hit_by[t] = mv
                    if m['effect'] == GLAIVE_RUSH:
                        vuln.add(r)
                    if dealt and x.item(r) == 'Life Orb' and x.ability(r) != 'Magic Guard' and not (
                            x.ability(r) == 'Sheer Force' and x.has_secondary(mv)):
                        hp[r] -= max(1, mx[r] // 10)
                    if dealt and rec > 0:
                        hp[r] = min(mx[r], hp[r] + max(1, dealt * rec // 100))
                    if dealt and rec < 0 and x.ability(r) not in ('Rock Head', 'Magic Guard'):
                        basis = min(x.total(r, mv, t, False), hp[t] + dealt) if sure else dealt
                        hp[r] -= max(1, basis * (-rec) // 100)
                    if m['effect'] == ai_checks.SELF_KO:
                        hp[r] = 0
                    if m['effect'] == ai_checks.RECHARGE and dealt:
                        recharge.add(r)
                    if raw[1] in (ai_checks.Q_USER_STAT, ai_checks.Q_TARGET_DROP):
                        who = r if raw[1] == ai_checks.Q_USER_STAT else t
                        for j in range(3):
                            stat = ai_checks.STAT_IDS.get(raw[21 + j])
                            amt, chance = int.from_bytes(raw[24 + j:25 + j], 'little', signed=True), raw[27 + j]
                            if stat and amt and chance == 100:
                                if who == t and amt < 0 and x.ability(t) in ai_checks.DROP_BLOCKERS[stat] and \
                                        x.ability(r) not in MOLD_BREAKER:
                                    continue
                                self.boost(who, stat, amt)
                                if who == r and amt < 0 and x.item(r) == 'White Herb':
                                    x.boosts[(r, stat)] = max(0, x.boosts[(r, stat)])
                                    x.consumed.add(r)
                    for q in (r, t):
                        if 0 < hp[q] <= mx[q] // 2 and x.item(q) in ('Sitrus Berry', 'Oran Berry'):
                            hp[q] = min(mx[q], hp[q] + (mx[q] // 4 if x.item(q) == 'Sitrus Berry' else 10))
                            x.consumed.add(q)
                    if hp[t] <= 0 or hp[r] <= 0:
                        break
                for r in race.order(moves):
                    if hp[r] > 0:
                        sync()
                        if r in tox:
                            views[r]['status'] = 'tox'
                        try:
                            hp[r] = race.chip(r, hp[r], tox.get(r, 1))
                        finally:
                            views[r]['status'] = saved_status[r]
                        if r in tox:
                            tox[r] += 1
                if hp[a] > 0 and hp[b] > 0:
                    for t, s in seeded.items():
                        if hp[t] > 0 and hp[s] > 0:
                            drain = min(hp[t], max(1, mx[t] // 8))
                            hp[t] -= drain
                            hp[s] = min(mx[s], hp[s] + drain)
                alive = [r for r in (a, b) if hp[r] > 0]
                if len(alive) == 1:
                    return alive[0], turn
                if not alive:
                    return None, turn
            return None, n
        finally:
            for r in (a, b):
                views[r]['cur_hp'] = saved[r]
            x.boosts.clear()
            x.consumed.clear()


def _plans(x, r, spec):
    """A plan as a tuple of moves; '*' alone means each attack of r, tried one at a time."""
    if spec == '*':
        return [(mv,) for mv in x.ref(r)['moves'] if x.d.move(mv)['class'] != STATUS]
    return [tuple(spec) if isinstance(spec, (tuple, list)) else (spec,)]


@_op6('b06_fight')
def fight(x):
    """('b06_fight', a, plan_a, b, plan_b, n, want): a fight between one Pokemon of each side played turn by turn under the rules
    of the module docstring, each following its plan (a move, or a tuple of moves for turns 1, 2, ..., the last repeated; '*' =
    each attack of that Pokemon, tried one at a time). want 'win': a is favored (its minimum x 0.9, the foe's maximum x 1.1) and
    knocks b out within n turns while still standing, under every plan of b. want 'lose': b is favored and knocks a out within n
    turns, before a knocks b out, under every plan of a. Both paralysis rules (a quarter, a half) and both burn rules (an eighth, a
    sixteenth) are tried, and the claim must hold in each."""
    a, plan_a, b, plan_b, n, want = x.args
    assert want in ('win', 'lose'), 'want is win or lose'
    _actives(x, a, b)
    favored = a if want == 'win' else b
    plans_a, plans_b = _plans(x, a, plan_a), _plans(x, b, plan_b)
    assert not (want == 'win' and len(plans_a) > 1) and not (want == 'lose' and len(plans_b) > 1), (
        "'*' belongs to the side whose every option is tried")
    for pa in plans_a:
        for pb in plans_b:
            for par_div in (4, 2):
                for burn_div in (8, 16):
                    who, turn = Fight(x, favored, par_div, burn_div).play(a, pa, b, pb, n)
                    assert who == favored, '%s %s vs %s %s: %s within %d turns (paralysis /%d, burn /%d)' % (
                        x.ref(a)['species'], '/'.join(pa), x.ref(b)['species'], '/'.join(pb),
                        'neither wins (both faint, or both still stand)' if who is None else
                        x.ref(who)['species'] + ' wins on turn %d' % turn, n, par_div, burn_div)


# --- static claims

@_op6('b06_sum_ko')
def sum_ko(x):
    """('b06_sum_ko', df, hits): the hits [(attacker, move), ...] on df, each at its minimum x 0.9, add up to at least df's current
    HP (several attackers in turn: a chip now and a finishing hit later, with no healing in between). No Focus Sash or Sturdy may
    hold at full HP."""
    df, hits = x.args
    dv = x.ref(df)
    total = 0
    for i, (a, mv) in enumerate(hits):
        if i == 0:
            assert not x.endures(a, mv, df), '%s hangs on at 1 HP' % dv['species']
        total += x.total(a, mv, df, True) * 0.9
    assert total >= dv['cur_hp'], 'the hits do at least %d to %s at %d HP' % (total, dv['species'], dv['cur_hp'])


@_op6('b06_sum_noko')
def sum_noko(x):
    """('b06_sum_noko', df, hits): the hits [(attacker, move), ...] on df, each at its maximum x 1.1, add up to less than df's HP."""
    df, hits = x.args
    dv = x.ref(df)
    total = sum(x.total(a, mv, df, False) * 1.1 for a, mv in hits)
    assert total < dv['cur_hp'], 'the hits do up to %d to %s at %d HP' % (total, dv['species'], dv['cur_hp'])


@_op6('b06_burst_kos')
def burst_kos(x):
    """('b06_burst_kos', a, mv, df[, 'paralyzed']): df has Metal Burst and is slower than a (Metal Burst returns 1.5 times the
    damage of the last hit df took this turn, rounded down, and fails if df moves first, Gen 5); a's move cannot knock df out
    (maximum x 1.1 < HP, one hit) and 1.5 x its minimum x 0.9 knocks a out. With 'paralyzed', df's Speed is read as paralyzed
    (both rules), for a claim about what a Thunder Wave would change. Metal Burst is seen in this hack's AI-vs-AI logs (round S2
    analysts 11 and 13: 1.5 times the hit), not measured."""
    a, mv, df = x.args[:3]
    paralyzed = x.args[3:] == ('paralyzed',)
    assert x.args[3:] in ((), ('paralyzed',)), 'the fourth argument can only be paralyzed'
    dv, av = x.ref(df), x.ref(a)
    assert any(x.d.move(m)['effect'] == METAL_BURST for m in dv['moves']), '%s has no Metal Burst' % dv['species']
    saved = dv['status']
    if paralyzed:
        assert not saved and ELECTRIC not in dv['types'] and x.ability(df) != 'Limber', '%s cannot be paralyzed' % dv['species']
        dv['status'] = 'par'
    try:
        for div in (4, 2):
            assert x.speed(a, div) > x.speed(df, div), '%s is not faster than %s' % (av['species'], dv['species'])
    finally:
        dv['status'] = saved
    assert x.hits(mv)[1] == 1, '%s hits more than once' % mv
    lo, hi = x.total(a, mv, df, True), x.total(a, mv, df, False)
    assert lo > 0 and hi * 1.1 < dv['cur_hp'], '%s does %d-%d to %s at %d HP: it may not survive to strike back' % (
        mv, lo, hi, dv['species'], dv['cur_hp'])
    back = int(lo * 0.9) * 3 // 2
    assert back >= av['cur_hp'], 'Metal Burst returns at least %d, %s has %d HP' % (back, av['species'], av['cur_hp'])


@_op6('b06_countered')
def countered(x):
    """('b06_countered', a, mv, df): df has Counter (for a physical move) or Mirror Coat (special) and survives a's move (maximum x
    1.1 < HP, one hit); it then returns twice the damage, at least 2 x the minimum x 0.9, which knocks a out (Gen 5; Counter and
    Mirror Coat have priority -5). A Ghost attacker into Counter and a Dark one into Mirror Coat are refused."""
    a, mv, df = x.args
    m = x.d.move(mv)
    dv = x.ref(df)
    want = {PHYSICAL: COUNTER, SPECIAL: MIRROR_COAT}.get(m['class'])
    assert any(x.d.move(n)['effect'] == want for n in dv['moves']), '%s has nothing that returns %s' % (dv['species'], mv)
    assert not (want == COUNTER and GHOST in x.ref(a)['types']) and not (want == MIRROR_COAT and T['Dark'] in x.ref(a)['types']), (
        'a type the reflecting move cannot hit: refused')
    assert x.hits(mv)[1] == 1, '%s hits more than once' % mv
    lo, hi = x.total(a, mv, df, True), x.total(a, mv, df, False)
    assert lo > 0 and hi * 1.1 < dv['cur_hp'], '%s does %d-%d: it can knock %s out first' % (mv, lo, hi, dv['species'])
    assert 2 * int(lo * 0.9) >= x.ref(a)['cur_hp'], 'twice %d does not knock %s out at %d HP' % (
        int(lo * 0.9), x.ref(a)['species'], x.ref(a)['cur_hp'])


@_op6('b06_reflects_only')
def reflects_only(x):
    """('b06_reflects_only', r): r's only attacks are Counter, Mirror Coat and Metal Burst, which do nothing unless r is hit by an
    attack that turn: r cannot hurt a foe that uses a status move."""
    (r,) = x.args
    for mv in x.ref(r)['moves']:
        m = x.d.move(mv)
        assert m['class'] == STATUS or m['effect'] in (COUNTER, MIRROR_COAT, METAL_BURST), '%s can attack with %s' % (
            x.ref(r)['species'], mv)


@_op6('b06_pivot_reflected')
def pivot_reflected(x):
    """('b06_pivot_reflected', a, mv, df): a's U-turn or Volt Switch cannot knock df out (maximum x 1.1 < HP), df has Counter
    (physical) or Mirror Coat (special), and twice the minimum x 0.9 knocks out every Pokemon on a's bench, one of which comes in
    after the pivot and takes the reflected hit (seen in this hack's AI-vs-AI logs, round S2 analyst 5: Mirror Coat after Volt
    Switch hit the replacement for 2 x 174; not measured)."""
    a, mv, df = x.args
    m = x.d.move(mv)
    dv = x.ref(df)
    assert m['effect'] == PIVOT, '%s is not a pivot move' % mv
    want = {PHYSICAL: COUNTER, SPECIAL: MIRROR_COAT}[m['class']]
    assert any(x.d.move(n)['effect'] == want for n in dv['moves']), '%s cannot return %s' % (dv['species'], mv)
    lo, hi = x.total(a, mv, df, True), x.total(a, mv, df, False)
    assert lo > 0 and hi * 1.1 < dv['cur_hp'], '%s can knock %s out' % (mv, dv['species'])
    side = 'enemy' if a[0] == 'e' else 'player'
    bench = ['%s%d' % (a[0], i) for i in range(1, len(x.views[side]))]
    assert bench, '%s has no bench: the pivot brings nobody in' % x.ref(a)['species']
    for r in bench:
        rv = x.ref(r)
        assert not (want == COUNTER and GHOST in rv['types']) and not (want == MIRROR_COAT and T['Dark'] in rv['types']), (
            '%s is immune to the reflected hit' % rv['species'])
        assert 2 * int(lo * 0.9) >= rv['cur_hp'], 'the replacement %s survives twice %d' % (rv['species'], int(lo * 0.9))


@_op6('b06_trapped')
def trapped(x):
    """('b06_trapped', p, e): p has Shadow Tag, so e cannot switch out (e has no Shadow Tag, is not a Ghost type and holds no Shed
    Shell; Gen 6 lets Ghosts escape, so they are refused either way). Trapping is seen in this hack's AI-vs-AI logs (round S2 analysts
    5, 7 and 10), not measured."""
    p, e = x.args
    assert x.ability(p) == 'Shadow Tag', '%s has no Shadow Tag' % x.ref(p)['species']
    ev = x.ref(e)
    assert x.ability(e) != 'Shadow Tag' and GHOST not in ev['types'], '%s can leave' % ev['species']
    assert x.item(e) != 'Shed Shell', '%s holds a Shed Shell' % ev['species']


@_op6('b06_no_attack_lands')
def no_attack_lands(x):
    """('b06_no_attack_lands', p, e): every attack p has does nothing to e (a type or ability immunity), so the only moves p can
    usefully choose are its status moves, and p has at least one."""
    p, e = x.args
    pv = x.ref(p)
    status = [mv for mv in pv['moves'] if x.d.move(mv)['class'] == STATUS]
    assert status, '%s has no status move' % pv['species']
    for mv in pv['moves']:
        if x.d.move(mv)['class'] != STATUS:
            assert x.effectiveness(p, mv, e) == 0, '%s\'s %s hits %s' % (pv['species'], mv, x.ref(e)['species'])


@_op6('b06_endeavor_fails')
def endeavor_fails(x):
    """('b06_endeavor_fails', a, df): a's Endeavor (effect 189) does nothing: it sets df's HP to a's own, so it fails when a has at
    least as much HP as df (Gen 5); a moves before df (faster under both paralysis rules, and df has no priority attack), so a's
    HP is still its current HP when Endeavor runs."""
    a, df = x.args
    av, dv = x.ref(a), x.ref(df)
    assert any(x.d.move(m)['effect'] == ENDEAVOR for m in av['moves']), '%s has no Endeavor' % av['species']
    for div in (4, 2):
        assert x.speed(a, div) > x.speed(df, div), '%s is not faster than %s' % (av['species'], dv['species'])
    for mv in dv['moves']:
        m = x.d.move(mv)
        assert m['class'] == STATUS or m['priority'] <= 0, '%s has %s' % (dv['species'], mv)
    assert av['cur_hp'] >= dv['cur_hp'], '%s has %d HP, %s %d: Endeavor works' % (av['species'], av['cur_hp'], dv['species'], dv['cur_hp'])


@_op6('b06_powder_immune')
def powder_immune(x):
    """('b06_powder_immune', a, mv, df): a's move is a powder move (flag bit 28 of the move data, the bit the ROM sets on exactly
    PoisonPowder, Stun Spore, Sleep Powder, Spore, Cotton Spore, Powder and Magic Powder) and df is a Grass type (or has Overcoat):
    from Gen 6 on, it does nothing (a has no Mold Breaker). The ROM carries the Gen 6 flags (bit 30, ball and bomb moves, drives
    Bulletproof, which was measured to work), but the powder rule itself is not measured in this hack: Gen 5 had no such rule."""
    a, mv, df = x.args
    assert x.d.move(mv)['flags'] & FLAG_POWDER, '%s is not a powder move' % mv
    assert _powder_blocked(x, a, mv, df), '%s is neither a Grass type nor an Overcoat holder (or %s has Mold Breaker)' % (
        x.ref(df)['species'], x.ref(a)['species'])


@_op6('b06_multi_breaks')
def multi_breaks(x):
    """('b06_multi_breaks', a, mv, df): df is at full HP with a Focus Sash (or Sturdy) that holds against any single hit, and a's
    move hits several times (the minimum count; Skill Link: the maximum): the first hit leaves df at 1 HP at worst and the other
    hits (minimum x 0.9 each) knock it out. Wonder Guard lets the move through only when it is super effective."""
    a, mv, df = x.args
    dv = x.ref(df)
    assert dv['cur_hp'] == dv['stats']['hp'] and (x.item(df) == 'Focus Sash' or x.ability(df) == 'Sturdy'), (
        '%s does not hang on at full HP' % dv['species'])
    lo_n, hi_n = x.hits(mv)
    if x.ability(a) == 'Skill Link':
        lo_n = hi_n
    assert lo_n >= 2, '%s hits once' % mv
    eff = x.effectiveness(a, mv, df)
    assert eff and eff > 0, '%s does nothing to %s' % (mv, dv['species'])
    per = x.damage(a, mv, df)[0]
    left = dv['cur_hp'] - min(int(per * 0.9), dv['cur_hp'] - 1)
    assert (lo_n - 1) * max(1, int(per * 0.9)) >= left, '%d more hits of %d leave %s standing at %d' % (lo_n - 1, per, dv['species'], left)


@_op6('b06_single_held')
def single_held(x):
    """('b06_single_held', a, mv, df): a's move hits once and df, at full HP with a Focus Sash or Sturdy (and a without Mold Breaker
    for Sturdy), keeps 1 HP however hard it hits (the Sash is then used up)."""
    a, mv, df = x.args
    assert x.hits(mv)[1] == 1, '%s hits more than once' % mv
    assert x.endures(a, mv, df), '%s does not hang on against %s' % (x.ref(df)['species'], mv)
    assert x.effectiveness(a, mv, df), '%s does nothing to %s anyway' % (mv, x.ref(df)['species'])


@_op6('b06_glaive_punished')
def glaive_punished(x):
    """('b06_glaive_punished', a, mv, df): a is faster than df under both paralysis rules (or mv has priority), and a's move
    cannot knock df out at full strength (maximum x 1.1 < HP) but surely does at double damage (2 x minimum x 0.9 >= HP): the
    hit Glaive Rush leaves its user open to until it moves again (module docstring; seen in logs, not measured)."""
    a, mv, df = x.args
    av, dv = x.ref(a), x.ref(df)
    if x.d.move(mv)['priority'] <= 0:
        for div in (4, 2):
            assert x.speed(a, div) > x.speed(df, div), '%s is not faster than %s' % (av['species'], dv['species'])
    lo, hi = x.total(a, mv, df, True), x.total(a, mv, df, False)
    assert hi * 1.1 < dv['cur_hp'], '%s can knock %s out even without the doubling' % (mv, dv['species'])
    assert 2 * lo * 0.9 >= dv['cur_hp'], 'doubled, %s does at least %d to %s at %d HP' % (mv, 2 * lo * 0.9, dv['species'], dv['cur_hp'])


@_op6('b06_attacks_only')
def attacks_only(x):
    """('b06_attacks_only', r): every move r has is an attack, so whatever it picks it attacks this turn (Sucker Punch works against
    it if it has not moved yet)."""
    (r,) = x.args
    bad = [mv for mv in x.ref(r)['moves'] if x.d.move(mv)['class'] == STATUS]
    assert not bad, '%s has %s' % (x.ref(r)['species'], ', '.join(bad))


@_op6('b06_no_priority')
def no_priority(x):
    """('b06_no_priority', r): none of r's attacks has priority above 0, so a foe's priority move goes before any of them, and under
    Trick Room a slower foe moves first."""
    (r,) = x.args
    for mv in x.ref(r)['moves']:
        m = x.d.move(mv)
        assert m['class'] == STATUS or m['priority'] <= 0, '%s has %s at priority %d' % (x.ref(r)['species'], mv, m['priority'])


SCENARIOS = with_items([
    # --- 1. the foe's active is outsped and KOd: the move that also hurts its switch-in; and the stay case

    S('b06_cover_resisted_sap', 'switch',
      'Quagsire at 22% is slower than Roserade and Leaf Storm (4x) KOs it, so the player switches to Sap Sipper Azumarill, which '
      'takes nothing from Leaf Storm and gains +1 Attack (Gen 5 Sap Sipper, not measured here); Sludge Bomb is resisted by Quagsire '
      '(0.5x) but still KOs it at 37 HP, and it hits Azumarill 2x for 81-95%; Shadow Ball also KOs Quagsire but does 24-29% to '
      'Azumarill',
      [mon('Quagsire', ['Earthquake', 'Waterfall', 'Recover', 'Toxic'], hp=0.22),
       mon('Azumarill', ['Aqua Jet', 'Play Rough', 'Waterfall', 'Superpower'], ability='Sap Sipper')],
      [mon('Roserade', ['Leaf Storm', 'Sludge Bomb', 'Shadow Ball', 'Sleep Powder']),
       mon('Jolteon', ['Thunderbolt', 'Shadow Ball', 'Volt Switch', 'Signal Beam'])],
      best=['Sludge Bomb'], ok=['Shadow Ball'], bad=['Leaf Storm'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_ko', 'e0', 'Leaf Storm', 'p0'), ('b06_ko', 'e0', 'Sludge Bomb', 'p0'),
              ('b06_eff', 'e0', 'Sludge Bomb', 'p0', 0.5), ('b06_ko', 'e0', 'Shadow Ball', 'p0'),
              ('b05_absorbs', 'p1', 'e0', 'Leaf Storm'), ('b06_eff', 'e0', 'Leaf Storm', 'p1', 0.0),
              ('b06_frac', 'e0', 'Sludge Bomb', 'p1', 0.75, 1.0), ('b06_beats', 'e0', 'Sludge Bomb', 'Shadow Ball', 'p1'),
              ('b06_noko', 'p0', 'Earthquake', 'e0')]),
    S('b06_cover_lightningrod_dragon', 'switch',
      'Pelipper at 30% is slower than Ampharos and Thunderbolt (4x) KOs it, so the player switches to Lightningrod Rhyperior, which '
      'takes Thunderbolt for nothing (seen in this hack\'s logs, round S2 analyst 12, not measured); Rhyperior is Rock/Dragon in this '
      'hack, so Dragon Pulse hits it 2x (61-74%) and also KOs Pelipper; Power Gem KOs Pelipper but does only 19-23% to Rhyperior',
      [mon('Pelipper', ['Scald', 'Hurricane', 'U-turn', 'Roost'], hp=0.3),
       mon('Rhyperior', ['Earthquake', 'Stone Edge', 'Megahorn', 'Dragon Claw'], ability='Lightningrod')],
      [mon('Ampharos', ['Thunderbolt', 'Dragon Pulse', 'Focus Blast', 'Power Gem'])],
      best=['Dragon Pulse'], ok=['Power Gem'], bad=['Thunderbolt'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_ko', 'e0', 'Thunderbolt', 'p0'), ('b06_ko', 'e0', 'Dragon Pulse', 'p0'),
              ('b06_ko', 'e0', 'Power Gem', 'p0'), ('b05_absorbs', 'p1', 'e0', 'Thunderbolt'), ('type', 'p1', 'Dragon'),
              ('b06_eff', 'e0', 'Dragon Pulse', 'p1', 2.0), ('b06_frac', 'e0', 'Dragon Pulse', 'p1', 0.6, 0.75),
              ('b06_beats', 'e0', 'Dragon Pulse', 'Power Gem', 'p1'), ('b06_noko', 'p0', 'Hurricane', 'e0')]),
    S('b06_stay_eq_not_ice', 'switch',
      'Electivire outspeeds Excadrill but cannot KO it, and Excadrill\'s Earthquake (2x) KOs Electivire, so Excadrill stays in '
      'instead of switching to Salamence; Earthquake (2x, 70-83%) leaves it in range of Breloom\'s Mach Punch (2x, priority) when '
      'Breloom comes in after Electivire faints, and Breloom is slower, so only Mach Punch can do it; Ice Punch, the move for a switch '
      'to Salamence (4x), does 26-31% to Excadrill and leaves it out of range; ThunderPunch cannot touch a Ground type; switching to '
      'Breloom (which takes Earthquake at 0.5x) trades about as evenly, so it is ok',
      [mon('Excadrill', ['Earthquake', 'Iron Head', 'Rock Slide', 'Swords Dance'], evs={'hp': 64}),
       mon('Salamence', ['Dragon Claw', 'Earthquake', 'Fire Fang', 'Aerial Ace'])],
      [mon('Electivire', ['ThunderPunch', 'Ice Punch', 'Earthquake', 'Fire Punch']),
       mon('Breloom', ['Mach Punch', 'Seed Bomb', 'Rock Tomb', 'Swords Dance'])],
      best=['Earthquake'], ok=['Fire Punch', 'switch:Breloom'], bad=['ThunderPunch'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_ko', 'p0', 'Earthquake', 'e0'), ('b06_noko', 'e0', 'Earthquake', 'p0'),
              ('b06_eff', 'e0', 'Earthquake', 'p1', 0.0), ('b06_eff', 'e0', 'ThunderPunch', 'p0', 0.0),
              ('b06_eff', 'e0', 'Ice Punch', 'p1', 4.0), ('b06_beats', 'e0', 'Earthquake', 'Ice Punch', 'p0'),
              ('b06_beats', 'e0', 'Earthquake', 'Fire Punch', 'p0'), ('b06_faster', 'p0', 'e1'), ('b06_pri', 'e1', 'Mach Punch', 1),
              ('b06_sum_ko', 'p0', [('e0', 'Earthquake'), ('e1', 'Mach Punch')]),
              ('b06_sum_noko', 'p0', [('e0', 'Ice Punch'), ('e1', 'Mach Punch')]), ('b06_no_priority', 'p0')]),

    # --- 2. Counter, Mirror Coat, Metal Burst; a Shadow Tag trap

    S('b06_seed_vs_shadow_tag', 'status',
      'Shadow Tag Wobbuffet traps Ferrothorn at 85% and can hurt it only with Counter and Mirror Coat; Power Whip or Knock Off cannot '
      'KO Wobbuffet and Counter returns twice the damage, a KO on Ferrothorn; Leech Seed (90%) drains an eighth of Wobbuffet\'s HP '
      'every turn and wins outright, because nothing Wobbuffet does hurts a Ferrothorn that does not attack; Protect wastes the turn '
      'but costs nothing (Shadow Tag trapping is seen in this hack\'s logs, not measured)',
      [mon('Wobbuffet', ['Counter', 'Mirror Coat', 'Encore', 'Destiny Bond'], ability='Shadow Tag')],
      [mon('Ferrothorn', ['Power Whip', 'Knock Off', 'Leech Seed', 'Protect'], hp=0.85),
       mon('Heatran', ['Flamethrower', 'Earth Power', 'Flash Cannon', 'Stealth Rock'])],
      best=['Leech Seed'], ok=['Protect'], bad=['Power Whip', 'Knock Off'],
      checks=[('b06_trapped', 'p0', 'e0'), ('b06_reflects_only', 'p0'), ('b06_countered', 'e0', 'Power Whip', 'p0'),
              ('b06_countered', 'e0', 'Knock Off', 'p0'), ('b06_fight', 'e0', 'Leech Seed', 'p0', '*', 10, 'win')]),
    S('b06_toxic_vs_trapping_wynaut', 'status',
      'Shadow Tag Wynaut traps Jolteon and can hurt it only with Counter and Mirror Coat; Thunderbolt or Shadow Ball cannot KO Wynaut '
      'and Mirror Coat returns twice the damage, a KO on Jolteon; Volt Switch escapes the trap, but Mirror Coat then hits the '
      'Pokemon that comes in, and Scizor at 90% faints to twice the hit (seen in this hack\'s logs, round S2 analyst 5, not '
      'measured); Toxic (90%) wins outright, because Wynaut has no attack of its own',
      [mon('Wynaut', ['Counter', 'Mirror Coat', 'Encore', 'Destiny Bond'], ability='Shadow Tag')],
      [mon('Jolteon', ['Thunderbolt', 'Volt Switch', 'Shadow Ball', 'Toxic']),
       mon('Scizor', ['Bullet Punch', 'X-Scissor', 'Superpower', 'Swords Dance'], hp=0.9)],
      best=['Toxic'], bad=['Thunderbolt', 'Shadow Ball', 'Volt Switch'],
      checks=[('b06_trapped', 'p0', 'e0'), ('b06_reflects_only', 'p0'), ('b06_countered', 'e0', 'Thunderbolt', 'p0'),
              ('b06_countered', 'e0', 'Shadow Ball', 'p0'), ('b06_pivot_reflected', 'e0', 'Volt Switch', 'p0'),
              ('b06_fight', 'e0', 'Toxic', 'p0', '*', 8, 'win')]),
    S('b06_ko_before_destiny_bond', 'ko',
      'Wobbuffet at 118 HP (45%) has Counter and Destiny Bond and is slower than Weavile; Knock Off (2x; Wobbuffet holds no item) KOs '
      'it before it moves; Icicle Crash, the move with the same-type bonus, cannot KO and Counter returns twice its damage, a KO on '
      'Weavile; Swords Dance gives Wobbuffet a turn for Destiny Bond, so the KO next turn would take Weavile down too',
      [mon('Wobbuffet', ['Counter', 'Mirror Coat', 'Encore', 'Destiny Bond'], ability='Shadow Tag', hp=118)],
      [mon('Weavile', ['Knock Off', 'Icicle Crash', 'Ice Shard', 'Swords Dance'])],
      best=['Knock Off'], bad=['Icicle Crash', 'Swords Dance'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_ko', 'e0', 'Knock Off', 'p0'), ('b06_eff', 'e0', 'Knock Off', 'p0', 2.0),
              ('b06_countered', 'e0', 'Icicle Crash', 'p0'), ('b06_reflects_only', 'p0')]),
    S('b06_wobbuffet_mirror_coat', 'rules',
      'The AI\'s Shadow Tag Wobbuffet traps Glaceon, whose four moves are all special attacks and none KOs Wobbuffet from full HP; '
      'whichever one Glaceon uses, Mirror Coat returns twice the damage and KOs it this turn; Counter answers only physical moves and '
      'does nothing here; Encore would only lock Glaceon into its attack after taking it, and delay the KO',
      [mon('Glaceon', ['Ice Beam', 'Blizzard', 'Shadow Ball', 'Signal Beam'])],
      [mon('Wobbuffet', ['Counter', 'Mirror Coat', 'Encore', 'Destiny Bond'], ability='Shadow Tag'),
       mon('Scizor', ['Bullet Punch', 'X-Scissor', 'Superpower', 'Swords Dance'])],
      best=['Mirror Coat'], bad=['Counter'],
      checks=[('b06_trapped', 'e0', 'p0'), ('b06_attacks_only', 'p0'), ('cls', 'Ice Beam', 'special'), ('cls', 'Blizzard', 'special'),
              ('cls', 'Shadow Ball', 'special'), ('cls', 'Signal Beam', 'special'),
              ('b06_countered', 'p0', 'Ice Beam', 'e0'), ('b06_countered', 'p0', 'Blizzard', 'e0'),
              ('b06_countered', 'p0', 'Shadow Ball', 'e0'), ('b06_countered', 'p0', 'Signal Beam', 'e0'),
              ('b06_fight', 'e0', 'Mirror Coat', 'p0', '*', 1, 'win')]),
    S('b06_plot_past_metal_burst', 'setup',
      'Registeel has Metal Burst and is slower than Chandelure at 85%; Flamethrower (2x) cannot KO it from full HP, and Metal Burst '
      'returns 1.5 times the damage, a KO on Chandelure (unlike Counter it also returns special damage; seen in this hack\'s logs, not '
      'measured); Nasty Plot is safe, since Iron Head is resisted and Body Press cannot touch a Ghost, and the +2 Flamethrower then '
      'KOs Registeel before it moves',
      [mon('Registeel', ['Iron Head', 'Body Press', 'Curse', 'Metal Burst'])],
      [mon('Chandelure', ['Flamethrower', 'Shadow Ball', 'Nasty Plot', 'Will-O-Wisp'], hp=0.85)],
      best=['Nasty Plot'], bad=['Flamethrower'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_burst_kos', 'e0', 'Flamethrower', 'p0'), ('b06_noko', 'p0', 'Iron Head', 'e0'),
              ('b06_eff', 'p0', 'Body Press', 'e0', 0.0), ('b04d_ko_boosted', 'e0', 'Flamethrower', 'p0', 'spa', 2, 1.0),
              ('b06_fight', 'e0', ('Nasty Plot', 'Flamethrower'), 'p0', '*', 2, 'win'),
              ('b06_fight', 'e0', 'Flamethrower', 'p0', 'Metal Burst', 3, 'lose')]),
    S('b06_physical_into_mirror_coat', 'rules',
      'Milotic has Mirror Coat and is slower than Raichu; Thunderbolt (2x) cannot KO it and Mirror Coat returns twice the damage, a '
      'KO on Raichu; Volt Tackle is physical, so Mirror Coat cannot return it, and it hits 2x for 74-88% and wins in two turns (this '
      'ROM\'s Volt Tackle has no recoil, measured)',
      [mon('Milotic', ['Mirror Coat', 'Scald', 'Ice Beam', 'Recover'])],
      [mon('Raichu', ['Volt Tackle', 'Thunderbolt', 'Focus Blast', 'Nasty Plot'])],
      best=['Volt Tackle'], bad=['Thunderbolt'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_countered', 'e0', 'Thunderbolt', 'p0'), ('b06_noko', 'e0', 'Volt Tackle', 'p0'),
              ('cls', 'Volt Tackle', 'physical'), ('b06_fight', 'e0', 'Volt Tackle', 'p0', '*', 2, 'win')]),
    S('b06_metal_burst_too_fast', 'rules',
      'HP-trained Durant has Metal Burst, but it is faster than Magnezone, and Metal Burst fails when its user moves first, so '
      'Thunderbolt (68-81%) is safe and wins in two turns, since Durant\'s own attacks barely scratch a Steel/Electric type; Thunder Wave would make Durant '
      'the slower one, and Metal Burst would then return 1.5 times the next Thunderbolt, a KO on Magnezone (Metal Burst seen in this '
      'hack\'s logs; the moves-first failure is the official rule, not measured)',
      [mon('Durant', ['X-Scissor', 'Iron Head', 'Rock Slide', 'Metal Burst'], evs={'hp': 252})],
      [mon('Magnezone', ['Thunderbolt', 'Flash Cannon', 'Thunder Wave', 'Volt Switch'])],
      best=['Thunderbolt'], ok=['Volt Switch', 'Flash Cannon'], bad=['Thunder Wave'],
      checks=[('b06_faster', 'p0', 'e0'), ('b06_fight', 'e0', 'Thunderbolt', 'p0', '*', 2, 'win'),
              ('b06_noko', 'p0', 'X-Scissor', 'e0'), ('b06_burst_kos', 'e0', 'Thunderbolt', 'p0', 'paralyzed')]),
])
