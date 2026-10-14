"""Batch 05, part a: lessons from the round S1 AI-vs-AI battles turned into turn-1 positions (draft_05b.py and draft_05c.py hold
the rest). Themes: the move that also hurts the foe's forced switch-in; picking the switch-in that takes the coming hit best
(the sandstorm stands in for entry hazards, which a turn-1 bench position cannot have); letting a doomed active go down
fighting instead of feeding a teammate to the hit; keeping the only answer to a foe in the back healthy; faster sleep moves;
absorbing abilities on the AI's own side; and single-battle rules (Thunder Wave into an Electric absorber, Weakness Policy,
Prankster Will-O-Wisp, Super Fang, Counter against a multi-hit move).

The ops below extend tests/ai_checks.py without editing it. `C5` is ai_checks.Ctx plus Weakness Policy as a held item. Every op
here builds a C5 and is registered in ai_checks.CHECKS on import (prefix b05_), before `with_items` runs. draft_05b.py and
draft_05c.py load this file for the ops when they are not registered yet. The rules, on top of the hack's data:
  The ops of tests/ai_checks.py (ko, noko, eff, faster, first, race, loses, frac, beats, macc, pri, endures, has_*), run on C5
  under a b05_ name, so a scenario with a Weakness Policy holder can use them.
  Prior hits (b05_wins_after, b05_loses_after, b05_faints): a list of (attacker, move, target) applied before a race, in order.
      Each hit is taken at the margin that is worst for the claim: the favored side's own HP after the hit uses the attacker's
      maximum x 1.1, the other side's its minimum x 0.9. '*' as the move means whatever the attacker picks: the strongest of its
      attacks against a favored target, the weakest against the other. A Focus Sash or Sturdy holder at full HP keeps 1 HP
      against a single hit (the Sash is then gone). The entry 'eot' applies one end of turn to both fighters (the favored one's
      worst case: burn an eighth, bad poison 2/16; the other's least), in the Gen 5 order of ai_checks.Race.chip. A switch-in
      is an attacker's hit on a bench member followed by 'eot'. A prior hit's guaranteed stat changes (Close Combat's drops,
      Leaf Storm's; none from a hit the target is immune to) carry into the race, which is ai_checks.Race from those HPs and
      stages (a Focus Sash used up by a prior hit cannot hold again, since its holder is no longer at full HP).
      A bench member in a race must have no entry ability (ai_checks._actives), and a switch-in's hit is refused when an active
      foe of the attacker has Intimidate or the attacker has Download (both would change with the switch).
  Sleep (b05_sleep_lands, b05_sleep_fails): a sleep move (move data status 2) lands unless the target already has a major status,
      has Insomnia, Vital Spirit, Sweet Veil or Comatose, or reflects it (Magic Bounce). The Gen 6 powder immunity of Grass types
      and Overcoat is not measured here: such a target is refused for Spore and Sleep Powder, either way. Sap Sipper (absorbs a
      Grass move), a Lum or Chesto Berry and Safety Goggles are refused too. Accuracy and order are separate claims (b05_macc,
      b05_first).
  Absorbing abilities (b05_absorbs): Volt Absorb, Motor Drive and Lightningrod take an Electric move, Water Absorb, Storm Drain
      and Dry Skin a Water move, Flash Fire a Fire move, Sap Sipper a Grass move, Levitate a Ground attack (not a status move),
      unless the attacker has Mold Breaker, Teravolt or Turboblaze: the move does nothing to the holder (Gen 5: status moves of
      that type too, such as Thunder Wave into Volt Absorb, which is not measured in this ROM).
  Burn from Prankster Will-O-Wisp (b05_wisp_first, b05_noko_burned): Will-O-Wisp with Prankster has priority +1 and goes before
      any priority-0 move; it burns a target that has no status, is not a Fire type, and has no Water Veil, Flash Fire, Magic Bounce,
      Rawst or Lum Berry. A burned attacker's physical damage is halved (not with Guts). Its 85% accuracy is stated in the
      description, not counted.
  Weakness Policy ('Weak. Policy', id 600): a super effective hit that does not knock its holder out raises its Attack and Sp. Atk
      by four stages in this hack (measured, qa/aivsai/ENGINE_FACTS.md: two "+2" messages each); it does not change the hit.
  Super Fang (b05_fang_noko): it deals half the target's current HP, rounded down, at least 1, whatever the stats (Gen 5); a Ghost
      takes nothing. So it knocks out only a target at 1 HP.
  Counter against a multi-hit move (b05_counter_last): seen in this hack's AI-vs-AI logs, not measured (ENGINE_FACTS.md): Counter
      returns twice the LAST hit, not twice the total (the official rule). b05_counter_total_kos states what the official rule
      would give, so the scenario shows the gap.
"""
import ai_checks
from ai_checks import (CHECKS, MODELED_ABILITIES, PHYSICAL, STATUS, T, Ctx, Race,
                       _actives, _race_moves, with_items)
from aidata import norm
from ai_helpers import PLAIN, S, mon  # noqa: F401

FIRE, GHOST, GRASS = T['Fire'], T['Ghost'], T['Grass']
EXTRA_ITEMS = {'Weak. Policy'}
WP_STAGES = 4                       # measured in this hack (ENGINE_FACTS.md, round 2 unit D, case wp)
SLEEP_BLOCK_ABILITIES = {'Insomnia', 'Vital Spirit', 'Sweet Veil', 'Comatose'}
POWDER_SLEEP = {'spore', 'sleeppowder'}
ABSORB = {'Volt Absorb': 'Electric', 'Motor Drive': 'Electric', 'Lightningrod': 'Electric', 'Water Absorb': 'Water',
          'Storm Drain': 'Water', 'Dry Skin': 'Water', 'Flash Fire': 'Fire', 'Sap Sipper': 'Grass', 'Levitate': 'Ground'}
SUPER_FANG, COUNTER = 40, 89
ENTRY_SENSITIVE = {'Intimidate'}


class C5(Ctx):
    """ai_checks.Ctx with Weakness Policy accepted as a held item (it changes no damage; the ops that use it say so)."""

    def vet(self, r, v):
        it = self.items.get(r)
        if it in EXTRA_ITEMS:
            ab = v['ability']
            assert ab in MODELED_ABILITIES, '%s: %s has %s, which these checks do not model' % (r, v['species'], ab)
            return
        super().vet(r, v)


def _op5(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(C5(d, views, c, ref))
        return fn
    return reg


for _name, _fn in (('b05_ko', ai_checks.mko), ('b05_noko', ai_checks.mnoko), ('b05_noko_at', ai_checks.mnoko_at),
                   ('b05_eff', ai_checks.meff), ('b05_faster', ai_checks.mfaster), ('b05_first', ai_checks.first),
                   ('b05_race', ai_checks.race), ('b05_loses', ai_checks.loses), ('b05_frac', ai_checks.mfrac),
                   ('b05_beats', ai_checks.mbeats), ('b05_macc', ai_checks.macc), ('b05_pri', ai_checks.mpri),
                   ('b05_endures', ai_checks.endures), ('b05_has_item', ai_checks.has_item),
                   ('b05_has_ability', ai_checks.has_ability), ('b05_has_status', ai_checks.has_status),
                   ('b05_weather', ai_checks.weather), ('b05_status_only', ai_checks.status_only)):
    _op5(_name)(_fn)


# --- prior hits, then a race

def _hit(x, src, mv, tgt, worst_for_tgt, hp):
    """HP of tgt after src's move: maximum x 1.1 when worst_for_tgt, else minimum x 0.9; Sash / Sturdy at full HP keep 1.
    Returns (hp, the move used): with '*', the strongest (worst_for_tgt) or the weakest of src's attacks."""
    moves = _race_moves(x, src, mv)
    for m in moves:
        Race(x, src, 4, 8).vet_move(src, m, tgt)
    if worst_for_tgt:
        dmg, used = max((int(x.total(src, m, tgt, False) * 1.1), m) for m in moves)
    else:
        dmg, used = min((int(x.total(src, m, tgt, True) * 0.9), m) for m in moves)
    full = hp == x.ref(tgt)['stats']['hp']
    if full and x.endures(src, used, tgt) and dmg >= hp:
        dmg = hp - 1
        if x.item(tgt) == 'Focus Sash':
            x.consumed.add(tgt)
    return hp - dmg, used


def _stat_changes(x, src, mv, tgt):
    """The move's guaranteed stat changes (chance 100), into x.boosts, as ai_checks.Race.play applies them."""
    r = x.d.moves[x.d.move(mv)['id']]
    if r[1] not in (ai_checks.Q_USER_STAT, ai_checks.Q_TARGET_DROP):
        return
    who = src if r[1] == ai_checks.Q_USER_STAT else tgt
    for k in range(3):
        stat = ai_checks.STAT_IDS.get(r[21 + k])
        amt, chance = int.from_bytes(r[24 + k:25 + k], 'little', signed=True), r[27 + k]
        if stat and amt and chance == 100:
            if who == tgt and amt < 0 and x.ability(tgt) in ai_checks.DROP_BLOCKERS[stat] and x.ability(src) not in ai_checks.MOLD_BREAKER:
                continue
            x.boosts[(who, stat)] = max(-6, min(6, x.boosts.get((who, stat), 0) + amt))


def _check_entry(x, src, tgt):
    """A hit on a bench member: its own entry would change what the model computes (Intimidate on the attacker's side
    opposite, Download on the attacker), so those are refused."""
    if tgt in x.actives[x.side(tgt)]:
        return
    for f in x.foes(src):
        assert x.ability(f) not in ENTRY_SENSITIVE, '%s has %s, which leaves with it when %s switches in' % (
            x.ref(f)['species'], x.ability(f), x.ref(tgt)['species'])
    assert x.ability(src) != 'Download', '%s has Download, which would read the switch-in' % x.ref(src)['species']
    assert x.ability(tgt) not in ai_checks.ENTRY_ABILITIES, '%s has an entry ability' % x.ref(tgt)['species']


def _apply(x, favored, other, hits):
    """Run the prior hits; returns ({ref: hp} for the two fighters and any other target hit, the stat stages they left)."""
    hp = {favored: x.ref(favored)['cur_hp'], other: x.ref(other)['cur_hp']}
    x.boosts.clear()
    for h in hits:
        if h == 'eot':
            for r, worst in ((favored, True), (other, False)):
                if hp[r] > 0:
                    v = x.ref(r)
                    assert v['status'] != 'tox', 'bad poison counters are not modeled across prior hits'
                    saved = v['cur_hp']
                    v['cur_hp'] = hp[r]
                    try:
                        if worst:
                            hp[r] = min(Race(x, favored, 4, 8).chip(r, hp[r], 2), Race(x, favored, 4, 16).chip(r, hp[r], 2))
                        else:
                            hp[r] = max(Race(x, favored, 4, 8).chip(r, hp[r], 1), Race(x, favored, 4, 16).chip(r, hp[r], 1))
                    finally:
                        v['cur_hp'] = saved
            continue
        src, mv, tgt = h
        _check_entry(x, src, tgt)
        cur = hp.get(tgt, x.ref(tgt)['cur_hp'])
        if cur <= 0:
            continue
        saved = x.ref(tgt)['cur_hp']
        x.ref(tgt)['cur_hp'] = cur
        try:
            hp[tgt], used = _hit(x, src, mv, tgt, tgt == favored, cur)
        finally:
            x.ref(tgt)['cur_hp'] = saved
        if x.effectiveness(src, used, tgt) != 0:
            _stat_changes(x, src, used, tgt)
    boosts = dict(x.boosts)
    x.boosts.clear()
    return hp, boosts


def _race_from(x, favored, mv_f, other, mv_o, n, hp, boosts, par_div, burn_div):
    va, vb = x.ref(favored), x.ref(other)
    saved = (va['cur_hp'], vb['cur_hp'])
    va['cur_hp'], vb['cur_hp'] = hp[favored], hp[other]
    try:
        return Race(x, favored, par_div, burn_div).play(favored, mv_f, other, mv_o, n, start_boosts=boosts)
    finally:
        va['cur_hp'], vb['cur_hp'] = saved


@_op5('b05_wins_after')
def wins_after(x):
    """('b05_wins_after', a, mv_a, b, mv_b, n, hits): after the prior hits (module docstring; a is favored), a, using mv_a every
    turn, knocks b out within n more turns and is still standing, whatever b uses ('*': each of its attacks), under the race
    rules of tests/ai_checks.py (a's minimum x 0.9, b's maximum x 1.1, both paralysis and both burn rules). a must survive the
    prior hits; b may already be out."""
    a, mv_a, b, mv_b, n, hits = x.args
    _actives(x, a, b)
    x.consumed.clear()
    hp, boosts = _apply(x, a, b, hits)
    assert hp[a] > 0, '%s does not survive the prior hits (%s)' % (x.ref(a)['species'], hits)
    if hp[b] <= 0:
        return
    for mb in _race_moves(x, b, mv_b):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                turn = _race_from(x, a, mv_a, b, mb, n, hp, boosts, par_div, burn_div)
                assert turn is not None, '%s at %d HP, using %s, does not surely beat %s at %d HP (its %s) within %d turns (par /%d, burn /%d)' % (
                    x.ref(a)['species'], hp[a], mv_a, x.ref(b)['species'], hp[b], mb, n, par_div, burn_div)


@_op5('b05_loses_after')
def loses_after(x):
    """('b05_loses_after', a, mv_a, b, mv_b, hits): after the prior hits (b is favored), a, using mv_a every turn ('*': each of its
    attacks), is knocked out by b's mv_b before it knocks b out (within 12 turns), under the race rules with b favored (b's
    minimum x 0.9, a's maximum x 1.1). If a is already out after the prior hits, the claim holds."""
    a, mv_a, b, mv_b, hits = x.args
    _actives(x, a, b)
    x.consumed.clear()
    hp, boosts = _apply(x, b, a, hits)
    assert hp[b] > 0, '%s does not survive the prior hits' % x.ref(b)['species']
    if hp[a] <= 0:
        return
    for ma in _race_moves(x, a, mv_a):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                turn = _race_from(x, b, mv_b, a, ma, 12, hp, boosts, par_div, burn_div)
                assert turn is not None, '%s at %d HP (its %s) is not surely beaten by %s at %d HP using %s (par /%d, burn /%d)' % (
                    x.ref(a)['species'], hp[a], ma, x.ref(b)['species'], hp[b], mv_b, par_div, burn_div)


@_op5('b05_faints')
def faints(x):
    """('b05_faints', r, hits): the hits (each at the attacker's minimum x 0.9; '*' = the weakest of its attacks; a Focus Sash or
    Sturdy at full HP keeps 1 HP against a single hit) and then the least end-of-turn damage of this turn (sandstorm, poison,
    burn a sixteenth, Black Sludge; less Leftovers and the healing abilities) surely knock r out by the end of the turn."""
    r, hits = x.args
    hp = x.ref(r)['cur_hp']
    x.consumed.clear()
    for src, mv, tgt in hits:
        assert tgt == r, 'b05_faints takes hits on %s only' % r
        _check_entry(x, src, tgt)
        saved = x.ref(r)['cur_hp']
        x.ref(r)['cur_hp'] = hp
        try:
            hp = _hit(x, src, mv, r, False, hp)[0]
        finally:
            x.ref(r)['cur_hp'] = saved
        if hp <= 0:
            return
    v = x.ref(r)
    saved = v['cur_hp']
    v['cur_hp'] = hp
    try:
        left = max(Race(x, r, 4, 16).chip(r, hp, 1), Race(x, r, 4, 8).chip(r, hp, 1))
    finally:
        v['cur_hp'] = saved
    assert left <= 0, '%s is left at %d HP after the hits and %d after the end of the turn' % (v['species'], hp, left)


# --- sleep

def _sleep_move(x, mv):
    m = x.d.move(mv)
    assert m['class'] == STATUS and m['status'] == 2, '%s is not a sleep move' % mv
    return m


@_op5('b05_sleep_lands')
def sleep_lands(x):
    """('b05_sleep_lands', a, mv, df): a's sleep move can put df to sleep (module docstring): df has no major status, no
    Insomnia, Vital Spirit, Sweet Veil, Comatose or Magic Bounce; the powder rule of Grass types and Overcoat (Gen 6, not
    measured) and Sap Sipper are refused; no Lum or Chesto Berry, no Safety Goggles."""
    a, mv, df = x.args
    _sleep_move(x, mv)
    dv = x.ref(df)
    assert not dv['status'], '%s already has a status' % dv['species']
    ab = x.ability(df)
    breaker = x.ability(a) in ai_checks.MOLD_BREAKER
    assert breaker or ab not in SLEEP_BLOCK_ABILITIES | {'Magic Bounce', 'Sap Sipper'}, '%s has %s' % (dv['species'], ab)
    if norm(mv) in POWDER_SLEEP:
        assert GRASS not in dv['types'] and ab != 'Overcoat', '%s: the powder rule is not measured' % dv['species']
    assert x.item(df) not in ('Lum Berry', 'Chesto Berry', 'Safety Goggles'), '%s holds %s' % (dv['species'], x.item(df))


@_op5('b05_sleep_fails')
def sleep_fails(x):
    """('b05_sleep_fails', a, mv, df): a's sleep move cannot affect df: df already has a major status (a Pokemon has one at a
    time), or has Insomnia, Vital Spirit, Sweet Veil or Comatose and a has no Mold Breaker."""
    a, mv, df = x.args
    _sleep_move(x, mv)
    dv = x.ref(df)
    if dv['status']:
        return
    assert x.ability(df) in SLEEP_BLOCK_ABILITIES and x.ability(a) not in ai_checks.MOLD_BREAKER, (
        '%s can fall asleep (no status, %s)' % (dv['species'], x.ability(df)))


# --- absorbing abilities

@_op5('b05_absorbs')
def absorbs(x):
    """('b05_absorbs', df, a, mv): df's ability takes a's move of its type (module docstring), so the move does nothing to df:
    Volt Absorb, Motor Drive, Lightningrod (Electric), Water Absorb, Storm Drain, Dry Skin (Water), Flash Fire (Fire), Sap
    Sipper (Grass), Levitate (Ground attacks only); a's Mold Breaker, Teravolt or Turboblaze would ignore it."""
    df, a, mv = x.args
    m = x.d.move(mv)
    ab = x.ability(df)
    assert ab in ABSORB and ABSORB[ab] == ai_checks.TYPES[m['type']], '%s\'s %s does not take %s' % (x.ref(df)['species'], ab, mv)
    assert not (ab == 'Levitate' and m['class'] == STATUS), 'Levitate does not stop a Ground status move'
    assert x.ability(a) not in ai_checks.MOLD_BREAKER, '%s ignores abilities' % x.ref(a)['species']


# --- burn from Prankster Will-O-Wisp

@_op5('b05_wisp_first')
def wisp_first(x):
    """('b05_wisp_first', p, e): p's Will-O-Wisp, with Prankster's +1, goes before every priority-0 attack of e, and it can burn e:
    no status, not a Fire type, no Water Veil, Flash Fire or Magic Bounce, no Rawst or Lum Berry, and e has no priority attack."""
    p, e = x.args
    assert 'willowisp' in {norm(mv) for mv in x.ref(p)['moves']}, '%s has no Will-O-Wisp' % x.ref(p)['species']
    assert x.ability(p) == 'Prankster', '%s has no Prankster' % x.ref(p)['species']
    ev = x.ref(e)
    for mv in ev['moves']:
        m = x.d.move(mv)
        if m['class'] != STATUS:
            assert m['priority'] < 1, '%s has %s (priority %d)' % (ev['species'], mv, m['priority'])
    assert not ev['status'] and FIRE not in ev['types'], '%s cannot be burned' % ev['species']
    assert x.ability(e) not in ('Water Veil', 'Flash Fire', 'Magic Bounce'), '%s has %s' % (ev['species'], x.ability(e))
    assert x.item(e) not in ('Rawst Berry', 'Lum Berry'), '%s holds %s' % (ev['species'], x.item(e))


@_op5('b05_noko_burned')
def noko_burned(x):
    """('b05_noko_burned', a, mv, df): with a burned (physical damage halved, not with Guts), a's move cannot knock df out:
    maximum x 1.1 < df's current HP."""
    a, mv, df = x.args
    v = x.ref(a)
    saved = v['status']
    v['status'] = 'brn'
    try:
        hi = x.total(a, mv, df, False)
    finally:
        v['status'] = saved
    assert hi * 1.1 < x.ref(df)['cur_hp'], 'burned %s\'s %s does up to %d to %s at %d HP' % (
        v['species'], mv, hi, x.ref(df)['species'], x.ref(df)['cur_hp'])


# --- Weakness Policy

@_op5('b05_wp')
def wp(x):
    """('b05_wp', a, mv, df): df holds Weakness Policy and a's move is super effective on it without knocking it out (maximum x 1.1
    < HP), so the policy fires: +4 Attack and +4 Sp. Atk in this hack (measured)."""
    a, mv, df = x.args
    assert x.items.get(df) == 'Weak. Policy', '%s does not hold Weakness Policy' % x.ref(df)['species']
    eff = x.effectiveness(a, mv, df)
    assert eff and eff > 1, '%s is not super effective on %s (%s)' % (mv, x.ref(df)['species'], eff)
    hi = x.total(a, mv, df, False)
    assert hi * 1.1 < x.ref(df)['cur_hp'], '%s can KO %s: the policy might not fire' % (mv, x.ref(df)['species'])


@_op5('b05_no_wp')
def no_wp(x):
    """('b05_no_wp', a, mv, df): a's move is not super effective on df, so a Weakness Policy does not fire."""
    a, mv, df = x.args
    eff = x.effectiveness(a, mv, df)
    assert eff is not None and eff <= 1, '%s is super effective on %s (%s)' % (mv, x.ref(df)['species'], eff)


@_op5('b05_boosted_ko')
def boosted_ko(x):
    """('b05_boosted_ko', a, mv, df, stages): with a's Attack and Sp. Atk raised by that many stages (4 = a Weakness Policy here),
    its move surely knocks df out (minimum x 0.9 >= HP, no Focus Sash or Sturdy hold)."""
    a, mv, df, st = x.args
    x.boosts[(a, 'atk')], x.boosts[(a, 'spa')] = st, st
    try:
        lo = x.total(a, mv, df, True)
        assert not x.endures(a, mv, df), '%s hangs on at 1 HP' % x.ref(df)['species']
        assert lo * 0.9 >= x.ref(df)['cur_hp'], '+%d %s does %d at least: not a sure KO on %s at %d HP' % (
            st, mv, lo, x.ref(df)['species'], x.ref(df)['cur_hp'])
    finally:
        x.boosts.clear()


# --- Super Fang

@_op5('b05_fang_noko')
def fang_noko(x):
    """('b05_fang_noko', a, df): a's Super Fang deals half of df's current HP, rounded down and at least 1 (Gen 5), so it cannot
    knock out df, which has at least 2 HP; a Ghost takes nothing (no Scrappy)."""
    a, df = x.args
    fang = [mv for mv in x.ref(a)['moves'] if x.d.move(mv)['effect'] == SUPER_FANG]
    assert fang, '%s has no Super Fang' % x.ref(a)['species']
    dv = x.ref(df)
    assert x.ability(df) != 'Wonder Guard', 'Wonder Guard is not modeled with Super Fang'
    assert dv['cur_hp'] >= 2, '%s has 1 HP: Super Fang KOs it' % dv['species']


# --- Counter against a multi-hit move

def _multi(x, p, mv):
    m = x.d.move(mv)
    lo_n, hi_n = x.hits(mv)
    assert m['class'] == PHYSICAL and hi_n > 1, '%s is not a multi-hit physical move' % mv
    if x.ability(p) == 'Skill Link':
        lo_n = hi_n
    return lo_n, hi_n


@_op5('b05_counter_last')
def counter_last(x):
    """('b05_counter_last', e, mv, p): p's multi-hit physical move cannot knock out e (every hit at its maximum x 1.1, all hits),
    and e's Counter, which returns twice the LAST hit in this hack's engine (seen in logs, not measured), cannot knock out p:
    2 x one hit's maximum x 1.1 < p's HP."""
    e, mv, p = x.args
    assert 'counter' in {norm(m) for m in x.ref(e)['moves']}, '%s has no Counter' % x.ref(e)['species']
    lo_n, hi_n = _multi(x, p, mv)
    hit_hi = x.damage(p, mv, e)[1]
    assert hit_hi * hi_n * 1.1 < x.ref(e)['cur_hp'], '%s (%d x %d) can KO %s before it counters' % (mv, hi_n, hit_hi, x.ref(e)['species'])
    assert 2 * hit_hi * 1.1 < x.ref(p)['cur_hp'], 'twice one hit of %s (%d) can KO %s at %d HP' % (
        mv, 2 * hit_hi, x.ref(p)['species'], x.ref(p)['cur_hp'])


@_op5('b05_counter_total_kos')
def counter_total_kos(x):
    """('b05_counter_total_kos', e, mv, p): on the official rule (twice the total damage of the move), e's Counter would surely
    knock out p: 2 x (minimum hits x one hit's minimum) x 0.9 >= p's HP. It states the gap with b05_counter_last."""
    e, mv, p = x.args
    lo_n, hi_n = _multi(x, p, mv)
    lo = x.damage(p, mv, e)[0] * lo_n
    assert 2 * lo * 0.9 >= x.ref(p)['cur_hp'], 'twice the total of %s (%d) does not surely KO %s' % (mv, 2 * lo, x.ref(p)['species'])


SCENARIOS = with_items([
    # --- 1. the foe's active must leave: the move that also hurts its switch-in

    S('b05_cover_flash_fire', 'switch',
      'Ferrothorn at 70% is far slower than Infernape and Flare Blitz (4x) KOs it, so the player switches to its only answer, '
      'Flash Fire Houndoom, which takes nothing from Flare Blitz and gets its Fire boost; Close Combat also KOs Ferrothorn and '
      'surely KOs Houndoom (2x on its Dark type), so it wins whether the player stays or switches; Earthquake does not KO Ferrothorn',
      [mon('Ferrothorn', ['Power Whip', 'Gyro Ball', 'Leech Seed', 'Knock Off'], hp=0.7),
       mon('Houndoom', ['Dark Pulse', 'Flamethrower', 'Sludge Bomb', 'Nasty Plot'], ability='Flash Fire')],
      [mon('Infernape', ['Flare Blitz', 'Close Combat', 'Earthquake', 'Mach Punch']),
       mon('Togekiss', ['Air Slash', 'DazzlngGleam', 'Roost', 'Nasty Plot'])],
      best=['Close Combat'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'Close Combat', 'p0'), ('b05_ko', 'e0', 'Flare Blitz', 'p0'),
              ('b05_absorbs', 'p1', 'e0', 'Flare Blitz'), ('b05_eff', 'e0', 'Flare Blitz', 'p1', 0.0),
              ('b05_ko', 'e0', 'Close Combat', 'p1'), ('b05_noko', 'e0', 'Earthquake', 'p0'),
              ('b05_noko', 'p0', 'Power Whip', 'e0')]),
    S('b05_cover_dark_switch', 'switch',
      'Toxicroak at 25% is slower than Alakazam and Psychic (4x) KOs it, so the player switches to Umbreon, which no Psychic move '
      'touches; Dazzling Gleam also KOs Toxicroak and hits Umbreon 2x (38-45%), right whether Toxicroak stays or leaves; Focus '
      'Blast is the 70% gamble that only pays if Umbreon comes in (Toxicroak resists it and may survive); Recover at full HP fails',
      [mon('Toxicroak', ['Drain Punch', 'Poison Jab', 'Earthquake', 'Bulk Up'], hp=0.25),
       mon('Umbreon', ['Toxic', 'Wish', 'Protect', 'Moonlight'])],
      [mon('Alakazam', ['Psychic', 'Focus Blast', 'DazzlngGleam', 'Recover']),
       mon('Jirachi', ['Iron Head', 'Zen Headbutt', 'Fire Punch', 'Stealth Rock'])],
      best=['DazzlngGleam'], ok=['Focus Blast'], bad=['Recover'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'DazzlngGleam', 'p0'), ('b05_ko', 'e0', 'Psychic', 'p0'),
              ('b05_eff', 'e0', 'Psychic', 'p1', 0.0), ('b05_frac', 'e0', 'DazzlngGleam', 'p1', 0.35, 0.5),
              ('b05_noko', 'p0', 'Poison Jab', 'e0'), ('acc_lt', 'Focus Blast', 100)]),
    S('b05_cover_levitate', 'switch',
      'Magnezone at 28% is slower than Krookodile and Earthquake (4x) KOs it, so the player switches to Levitate Bronzong, which '
      'Earthquake cannot touch; Crunch also KOs Magnezone and is 2x with the same-type bonus on Bronzong (65-77%), more than Fire '
      'Fang (35-42%), which KOs Magnezone too; Stone Edge is resisted by both',
      [mon('Magnezone', ['Thunderbolt', 'Flash Cannon', 'Volt Switch', 'Thunder Wave'], hp=0.28),
       mon('Bronzong', ['Gyro Ball', 'Psychic', 'Earthquake', 'Stealth Rock'], ability='Levitate')],
      [mon('Krookodile', ['Earthquake', 'Crunch', 'Fire Fang', 'Stone Edge']),
       mon('Zapdos', ['Thunderbolt', 'Heat Wave', 'Air Slash', 'Roost'])],
      best=['Crunch'], ok=['Fire Fang'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'Earthquake', 'p0'), ('b05_ko', 'e0', 'Crunch', 'p0'),
              ('b05_ko', 'e0', 'Fire Fang', 'p0'), ('b05_eff', 'e0', 'Earthquake', 'p1', 0.0),
              ('b05_frac', 'e0', 'Crunch', 'p1', 0.6, 0.8), ('b05_beats', 'e0', 'Crunch', 'Fire Fang', 'p1'),
              ('b05_noko', 'p0', 'Flash Cannon', 'e0')]),
    S('b05_cover_not_into_wp', 'rules',
      'Levitate Flygon at 18% is slower than Garchomp and every Garchomp move but Earthquake KOs it, so the player switches to its '
      'Weakness Policy Ninetales, which Dragon Claw cannot touch; Stone Edge would also cover the switch, but it is 2x and cannot '
      'KO Ninetales, so the policy gives +4 and the faster Ninetales then KOs Garchomp with Moonblast; Iron Head KOs Flygon and hits '
      'Ninetales neutrally (27-32%), and Ninetales at +0 cannot KO Garchomp',
      [mon('Flygon', ['Dragon Claw', 'Earthquake', 'Fire Punch', 'Dragon Dance'], ability='Levitate', hp=0.18),
       mon('Ninetales', ['Moonblast', 'Fire Blast', 'Energy Ball', 'Nasty Plot'], item='Weak. Policy', evs={'hp': 252})],
      [mon('Garchomp', ['Dragon Claw', 'Earthquake', 'Stone Edge', 'Iron Head']),
       mon('Scizor', ['Bullet Punch', 'Iron Head', 'Superpower', 'Swords Dance'])],
      best=['Iron Head'], bad=['Stone Edge'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'Iron Head', 'p0'), ('b05_ko', 'e0', 'Stone Edge', 'p0'),
              ('b05_ko', 'e0', 'Dragon Claw', 'p0'), ('b05_eff', 'e0', 'Earthquake', 'p0', 0.0),
              ('b05_eff', 'e0', 'Dragon Claw', 'p1', 0.0), ('b05_wp', 'e0', 'Stone Edge', 'p1'),
              ('b05_no_wp', 'e0', 'Iron Head', 'p1'), ('b05_boosted_ko', 'p1', 'Moonblast', 'e0', 4),
              ('b05_faster', 'p1', 'e0'), ('b05_noko', 'p1', 'Moonblast', 'e0')]),
    S('b05_cover_water_absorb', 'switch',
      'Arcanine at 19% is slower than Starmie and Surf (2x) KOs it, so the player switches to Water Absorb Vaporeon, which Surf '
      'only heals; Thunderbolt also KOs Arcanine and is 2x on Vaporeon, more than Psychic, which KOs Arcanine too; Recover at full '
      'HP fails',
      [mon('Arcanine', ['Flare Blitz', 'Close Combat', 'Wild Charge', 'Morning Sun'], hp=0.19),
       mon('Vaporeon', ['Scald', 'Ice Beam', 'Wish', 'Protect'], ability='Water Absorb')],
      [mon('Starmie', ['Surf', 'Thunderbolt', 'Psychic', 'Recover']),
       mon('Ampharos', ['Thunderbolt', 'Dragon Pulse', 'Focus Blast', 'Volt Switch'])],
      best=['Thunderbolt'], ok=['Psychic'], bad=['Recover'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'Surf', 'p0'), ('b05_ko', 'e0', 'Thunderbolt', 'p0'),
              ('b05_ko', 'e0', 'Psychic', 'p0'), ('b05_absorbs', 'p1', 'e0', 'Surf'), ('b05_eff', 'e0', 'Surf', 'p1', 0.0),
              ('b05_eff', 'e0', 'Thunderbolt', 'p1', 2.0), ('b05_beats', 'e0', 'Thunderbolt', 'Psychic', 'p1'),
              ('b05_noko', 'p0', 'Wild Charge', 'e0')]),
    S('b05_cover_ghost_switch', 'switch',
      'Porygon2 at 27% is slower than Heracross and Close Combat (2x) KOs it, so the player switches to Dusknoir, which no Fighting '
      'move touches; Stone Edge also KOs Porygon2 and hits Dusknoir neutrally, while Knock Off (2x on Dusknoir) does not KO '
      'Porygon2 and lets it stay; Stone Edge has 80% accuracy, Close Combat throws the turn away if the switch comes',
      [mon('Porygon2', ['Tri Attack', 'Ice Beam', 'Recover', 'Thunder Wave'], hp=0.275),
       mon('Dusknoir', ['Shadow Sneak', 'Earthquake', 'Will-O-Wisp', 'Pain Split'])],
      [mon('Heracross', ['Close Combat', 'Stone Edge', 'Knock Off', 'Swords Dance']),
       mon('Lapras', ['Surf', 'Ice Beam', 'Thunderbolt', 'Psychic'])],
      best=['Stone Edge'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'Close Combat', 'p0'), ('b05_ko', 'e0', 'Stone Edge', 'p0'),
              ('b05_noko', 'e0', 'Knock Off', 'p0'), ('b05_eff', 'e0', 'Close Combat', 'p1', 0.0),
              ('b05_eff', 'e0', 'Stone Edge', 'p1', 1.0), ('b05_frac', 'e0', 'Stone Edge', 'p1', 0.25, 0.4),
              ('acc_lt', 'Stone Edge', 100)]),

    # --- 2. picking the switch-in that takes the coming hit best

    S('b05_sash_into_sand', 'switch',
      'Hippowdon set a sandstorm and its Earthquake (4x) KOs Magnezone, whose Flash Cannon cannot KO it; Focus Sash Gengar looks like '
      'the answer (faster, Energy Ball 4x), but Earthquake would KO it on the way in, the Sash leaves it at 1 HP and the sand '
      'finishes it at the end of the turn; Wonder Guard Shedinja is immune to Earthquake but not to the sand, which takes its only '
      'HP; Gyarados takes nothing from Earthquake, outspeeds Hippowdon and Waterfall (4x) KOs it',
      [mon('Hippowdon', ['Earthquake', 'Stone Edge', 'Crunch', 'Slack Off'], ability='Sand Stream')],
      [mon('Magnezone', ['Flash Cannon', 'Thunderbolt', 'Volt Switch', 'Thunder Wave']),
       mon('Gengar', ['Energy Ball', 'Shadow Ball', 'Sludge Bomb', 'Focus Blast'], ability='Cursed Body', item='Focus Sash'),
       mon('Gyarados', ['Waterfall', 'Bounce', 'Ice Fang', 'Dragon Dance'], evs={'atk': 252}),
       mon('Shedinja', ['X-Scissor', 'Shadow Sneak', 'Will-O-Wisp', 'Protect'], ability='Wonder Guard')],
      best=['switch:Gyarados'], bad=['switch:Gengar', 'switch:Shedinja', 'Flash Cannon', 'Thunderbolt', 'Volt Switch', 'Thunder Wave'],
      checks=[('b05_weather', 'sand'), ('b05_faster', 'e0', 'p0'), ('b05_ko', 'p0', 'Earthquake', 'e0'),
              ('b05_noko', 'e0', 'Flash Cannon', 'p0'), ('b05_eff', 'e0', 'Thunderbolt', 'p0', 0.0),
              ('b05_has_item', 'e1', 'Focus Sash'), ('b05_endures', 'e1', 'p0', 'Earthquake'),
              ('b05_faints', 'e1', [('p0', 'Earthquake', 'e1')]),
              ('b05_eff', 'p0', 'Earthquake', 'e2', 0.0),
              ('b05_wins_after', 'e2', 'Waterfall', 'p0', '*', 1, [('p0', 'Earthquake', 'e2'), 'eot']),
              ('b05_eff', 'p0', 'Earthquake', 'e3', 0.0), ('b05_faints', 'e3', [('p0', 'Earthquake', 'e3')])]),
    S('b05_immune_but_outsped', 'switch',
      'Galvantula outspeeds Gyarados and Thunderbolt (4x) KOs it; Quagsire is immune to Thunderbolt, but it is slower and '
      'Galvantula\'s Energy Ball (4x) KOs it the next turn before it moves; Chandelure takes Thunderbolt neutrally (36-43%), resists '
      'Bug Buzz and Energy Ball, survives a second Thunderbolt and Flamethrower (2x) KOs Galvantula',
      [mon('Galvantula', ['Thunderbolt', 'Bug Buzz', 'Energy Ball', 'Volt Switch'])],
      [mon('Gyarados', ['Waterfall', 'Stone Edge', 'Earthquake', 'Dragon Dance']),
       mon('Quagsire', ['Earthquake', 'Scald', 'Recover', 'Toxic'], hp=0.9),
       mon('Chandelure', ['Flamethrower', 'Shadow Ball', 'Energy Ball', 'Calm Mind'])],
      best=['switch:Chandelure'], bad=['Waterfall', 'Stone Edge', 'Earthquake', 'Dragon Dance'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Thunderbolt', 'e0'), ('b05_eff', 'p0', 'Thunderbolt', 'e1', 0.0),
              ('b05_faster', 'p0', 'e1'),
              ('b05_loses_after', 'e1', '*', 'p0', 'Energy Ball', [('p0', 'Thunderbolt', 'e1'), 'eot']),
              ('b05_wins_after', 'e2', 'Flamethrower', 'p0', '*', 1, [('p0', '*', 'e2'), 'eot'])]),
    S('b05_mold_breaker_switch', 'switch',
      'Mold Breaker Excadrill outspeeds Heatran and Earthquake (4x) KOs it; Levitate Bronzong looks immune, but Mold Breaker '
      'ignores Levitate, so Earthquake hits it 2x on the way in and again the next turn before it moves; Zapdos is a Flying type, '
      'immune whatever the ability, outspeeds Excadrill and wins with Heat Wave (2x) before two Rock Slides land; Heatran staying '
      'is KOd before it moves',
      [mon('Excadrill', ['Earthquake', 'Iron Head', 'Rock Slide', 'Swords Dance'], ability='Mold Breaker')],
      [mon('Heatran', ['Earth Power', 'Flash Cannon', 'Lava Plume', 'Stealth Rock']),
       mon('Bronzong', ['Gyro Ball', 'Psychic', 'Earthquake', 'Trick Room'], ability='Levitate'),
       mon('Zapdos', ['Thunderbolt', 'Heat Wave', 'Air Slash', 'Roost'])],
      best=['switch:Zapdos'], bad=['switch:Bronzong', 'Earth Power', 'Flash Cannon', 'Lava Plume', 'Stealth Rock'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Earthquake', 'e0'), ('b05_eff', 'p0', 'Earthquake', 'e1', 2.0),
              ('b05_has_ability', 'e1', 'Levitate'), ('b05_faster', 'p0', 'e1'),
              ('b05_loses_after', 'e1', '*', 'p0', 'Earthquake', [('p0', 'Earthquake', 'e1'), 'eot']),
              ('b05_eff', 'p0', 'Earthquake', 'e2', 0.0), ('b05_faster', 'e2', 'p0'),
              ('b05_wins_after', 'e2', 'Heat Wave', 'p0', '*', 2, [('p0', 'Earthquake', 'e2'), 'eot'])]),

    # --- 3. the active is lost this turn: attack, and let the next Pokemon come in free

    S('b05_free_entry_tempo', 'switch',
      'Weavile at 30% outspeeds Infernape (which has no priority move) but cannot KO it, and Close Combat or Flare Blitz KOs '
      'Weavile; Swampert switched in now takes '
      'Close Combat (51-61%) and the faster Infernape KOs it with a second one before Earthquake lands; if Weavile attacks and '
      'faints instead, Swampert comes in free, survives one Close Combat and Earthquake (2x) KOs Infernape',
      [mon('Infernape', ['Close Combat', 'Flare Blitz', 'ThunderPunch', 'Swords Dance'])],
      [mon('Weavile', ['Knock Off', 'Icicle Crash', 'Ice Shard', 'Swords Dance'], hp=0.3),
       mon('Swampert', ['Earthquake', 'Waterfall', 'Ice Punch', 'Stealth Rock'], hp=0.85)],
      best=['Icicle Crash', 'Knock Off', 'Ice Shard'], ok=['Swords Dance'], bad=['switch:Swampert'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_noko', 'e0', 'Icicle Crash', 'p0'), ('b05_ko', 'p0', 'Close Combat', 'e0'),
              ('b05_ko', 'p0', 'Flare Blitz', 'e0'),
              ('b05_eff', 'p0', 'ThunderPunch', 'e1', 0.0),
              ('b05_loses_after', 'e1', '*', 'p0', 'Close Combat', [('p0', 'Close Combat', 'e1'), 'eot']),
              ('b05_wins_after', 'e1', 'Earthquake', 'p0', '*', 1, [('e0', 'Icicle Crash', 'p0')])]),
    S('b05_doomed_recoil_trade', 'ko',
      'Honchkrow at 10% outspeeds Machamp at 60%, and any Machamp attack KOs it next; Brave Bird (2x) KOs Machamp and its recoil '
      'knocks Honchkrow out too, a one-for-one trade; Heat Wave, Night Slash and Sucker Punch leave Machamp standing and lose '
      'Honchkrow for nothing; Bisharp switched in takes Close Combat (4x) and is KOd',
      [mon('Machamp', ['Close Combat', 'Stone Edge', 'Knock Off', 'Bulk Up'], hp=0.6)],
      [mon('Honchkrow', ['Brave Bird', 'Night Slash', 'Sucker Punch', 'Heat Wave'], hp=0.1),
       mon('Bisharp', ['Iron Head', 'Night Slash', 'Sucker Punch', 'Swords Dance'])],
      best=['Brave Bird'], bad=['Heat Wave', 'Night Slash', 'Sucker Punch', 'switch:Bisharp'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'Brave Bird', 'p0'), ('recoil_kos_user', 'e0', 'Brave Bird', 'p0'),
              ('b05_noko', 'e0', 'Heat Wave', 'p0'), ('b05_noko', 'e0', 'Night Slash', 'p0'),
              ('b05_noko', 'e0', 'Sucker Punch', 'p0'), ('b05_ko', 'p0', 'Stone Edge', 'e0'),
              ('b05_ko', 'p0', 'Close Combat', 'e0'), ('b05_ko', 'p0', 'Close Combat', 'e1')]),
])
