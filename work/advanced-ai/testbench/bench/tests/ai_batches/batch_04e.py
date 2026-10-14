"""Batch 04, author E: utility moves (hazards, Taunt, Destiny Bond, Perish Song, Memento, Trick Room, pivots, Rapid Spin).

Each key is built so that it holds whether or not the utility move works in this ROM, wherever that was possible: the
alternatives are shown to gain nothing (an immunity, a lost race, a turn that changes nothing), so the utility move is
never worse than they are. The keys that still rest on a utility mechanic nobody measured in this ROM are listed in the
scenario descriptions ("not measured").

The ops below extend tests/ai_checks.py without editing it. They are registered in ai_checks.CHECKS on import (prefix
b04e_), before `with_items` runs, so their check tuples carry the held items like the batch 01 and 02 ops. They follow
the Gen 5 rules on top of the hack's data:
  Hazards (b04e_hazard): what one layer does to a Pokemon that switches in. Stealth Rock: an eighth of its max HP times the
      Rock effectiveness on its types. Spikes: an eighth to a grounded Pokemon, nothing to a Flying type or Levitate (an Iron
      Ball grounds). Toxic Spikes: poisons a grounded Pokemon that is not a Poison or Steel type, has no status and no
      Immunity; nothing otherwise. Magic Guard takes no hazard damage.
  Simple claims: b04e_no_bench (a side with only its active), b04e_outheals (a healing move outpaces every attack),
      b04e_ko_after (two hits in a row surely KO), b04e_entry_holds (a switch-in survives the hit it takes).
  The fight (b04e_idle_loses, b04e_opener_race, b04e_drop_race, b04e_chip_loses, b04e_entry_loses): the two Pokemon trade moves turn by turn
      with ai_checks.Race's rules (priority, speed under both paralysis rules, both burn rules, the favored side's minimum x
      0.9 against the other's maximum x 1.1, recoil, drain, guaranteed stat changes, berries, end-of-turn damage), plus:
      a turn-1 move that is not the move used afterwards (a status move that does nothing to the fight, or a damaging opener
      whose guaranteed stat changes count from turn 2), Trick Room (from the turn after it is used, the slower Pokemon
      moves first inside each priority bracket; it lasts five turns, longer than any fight claimed here), starting stat
      stages (a Memento already used) and a starting HP below the current one (a hit already taken). Both fainting in the
      same turn counts against the claim.
"""
import ai_checks
from ai_checks import CHECKS, STATUS, T, Ctx, Race, _actives, _race_moves, with_items
from ai_helpers import PLAIN, S, mon  # noqa: F401

ROCK, FLYING, POISON, STEEL = T['Rock'], T['Flying'], T['Poison'], T['Steel']
STAT_NAMES = ('atk', 'def', 'spa', 'spd', 'spe')


def _op4(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(Ctx(d, views, c, ref))
        return fn
    return reg


def _grounded(x, r):
    v = x.ref(r)
    return x.item(r) == 'Iron Ball' or (FLYING not in v['types'] and x.ability(r) != 'Levitate')


def _rock_eff(x, r):
    mult = 1.0
    for t in set(x.ref(r)['types']):
        mult *= x.d.chart[ROCK][t] / 4
    return mult


@_op4('b04e_hazard')
def hazard(x):
    """('b04e_hazard', move, r, want): what one layer of the hazard does to r when it switches in (Gen 5): Stealth Rock an
    eighth of its max HP times the Rock effectiveness on its types; Spikes an eighth if r is grounded (not a Flying type,
    no Levitate, or an Iron Ball), else nothing; Toxic Spikes poison (want 'psn') if r is grounded, not a Poison or Steel
    type, has no status and not Immunity, else nothing (want 0). Magic Guard takes no damage from them (want 0)."""
    mv, r, want = x.args
    v = x.ref(r)
    name = x.d.move_name[x.d.move(mv)['id']]
    if name == 'Stealth Rock':
        got = 0 if x.ability(r) == 'Magic Guard' else _rock_eff(x, r) / 8
    elif name == 'Spikes':
        got = 1 / 8 if _grounded(x, r) and x.ability(r) != 'Magic Guard' else 0
    elif name == 'Toxic Spikes':
        poisonable = not ({POISON, STEEL} & set(v['types'])) and not v['status'] and x.ability(r) != 'Immunity'
        got = 'psn' if _grounded(x, r) and poisonable else 0
    else:
        raise AssertionError('%s is not a hazard these checks model' % mv)
    assert got == want, '%s on %s: %s, claimed %s' % (name, v['species'], got, want)


@_op4('b04e_no_bench')
def no_bench(x):
    """('b04e_no_bench', side): that side ('player' or 'enemy') has only its active Pokemon: nothing of it can ever switch
    in, so hazards laid on its side never hurt anything, and Roar, Whirlwind, Dragon Tail and Circle Throw cannot force a
    switch (Roar and Whirlwind fail; the two attacks only deal their damage)."""
    (side,) = x.args
    assert len(x.views[side]) == 1, 'the %s side has %d Pokemon' % (side, len(x.views[side]))


@_op4('b04e_outheals')
def outheals(x):
    """('b04e_outheals', a, b, heal): b's healing move restores more HP (its heal % of b's max HP, from the move data) than
    any attack of a deals (maximum x 1.1, with items and abilities), and b's current HP is above that maximum: while b
    heals every turn a's attacks never knock it out, whichever of the two moves first."""
    a, b, heal = x.args
    m = x.d.move(heal)
    pct = x.d.moves[m['id']][19]
    assert m['class'] == STATUS and pct > 0 and x.d.moves[m['id']][20] == 7, '%s is not a self-healing move' % heal
    bv = x.ref(b)
    restored = bv['stats']['hp'] * pct // 100
    for mv in x.ref(a)['moves']:
        if x.d.move(mv)['class'] == STATUS:
            continue
        hi = x.total(a, mv, b, False) * 1.1
        assert hi < restored, '%s does up to %d to %s, more than %s restores (%d)' % (mv, hi, bv['species'], heal, restored)
        assert hi < bv['cur_hp'], '%s does up to %d to %s at %d HP' % (mv, hi, bv['species'], bv['cur_hp'])


@_op4('b04e_ko_after')
def ko_after(x):
    """('b04e_ko_after', c, mv_c, a, mv, df): c's mv_c and then a's mv surely knock df out: the sum of their minimums x 0.9
    is at least df's current HP. A Focus Sash or Sturdy target is refused."""
    c, mv_c, a, mv, df = x.args
    hp = x.ref(df)['cur_hp']
    lo = x.total(c, mv_c, df, True) * 0.9 + x.total(a, mv, df, True) * 0.9
    assert x.item(df) != 'Focus Sash' and x.ability(df) != 'Sturdy', '%s could hang on at 1 HP' % x.ref(df)['species']
    assert lo >= hp, '%s then %s do at least %d to %s at %d HP: not a sure KO' % (mv_c, mv, lo, x.ref(df)['species'], hp)


class Fight(Race):
    """ai_checks.Race with a separate turn-1 move for a, Trick Room, starting stat stages and starting HP (docstring)."""

    def order_tr(self, moves, trick_room):
        if not trick_room:
            return self.order(moves)
        x = self.x
        keys = {}
        for r, mv in moves.items():
            assert not x.moves_last(r), 'Lagging Tail, Full Incense and Stall under Trick Room are not modeled'
            m = x.d.move(mv)
            pri = m['priority'] + (1 if x.ability(r) == 'Prankster' and m['class'] == STATUS else 0)
            keys[r] = (-pri, x.speed(r, self.par_div))
        rs = sorted(moves, key=lambda r: keys[r])
        for p, q in zip(rs, rs[1:]):
            assert keys[p] != keys[q], 'speed tie under Trick Room between %s and %s' % (x.ref(p)['species'], x.ref(q)['species'])
        return rs

    def fight(self, a, first_a, mv_a, b, mv_b, max_turns, start_hp=None, start_boosts=None):
        """('a', turn) when b faints with a standing, ('b', turn) when a faints with b standing, ('both', turn) when both
        fall in the same turn (against any claim), (None, max_turns) if neither falls. a uses first_a on turn 1 and mv_a afterwards; a status first_a does nothing, except Trick Room."""
        x = self.x
        for mv in (first_a, mv_a):
            if x.d.move(mv)['class'] != STATUS:
                self.vet_move(a, mv, b)
        self.vet_move(b, mv_b, a)
        tr_name = 'Trick Room'
        first_is_tr = x.d.move_name[x.d.move(first_a)['id']] == tr_name
        va, vb = x.ref(a), x.ref(b)
        saved = {a: va['cur_hp'], b: vb['cur_hp']}
        hp = dict(saved)
        hp.update(start_hp or {})
        tox = {r: (2 if r == self.favored else 1) for r in (a, b)}
        recharge = {a: False, b: False}
        trick_room = False
        x.boosts.clear()
        x.boosts.update(start_boosts or {})
        x.consumed.clear()
        try:
            for turn in range(1, max_turns + 1):
                acted = set()
                moves = {a: first_a if turn == 1 else mv_a, b: mv_b}
                for r in self.order_tr(moves, trick_room):
                    t = b if r == a else a
                    if hp[r] <= 0 or hp[t] <= 0:
                        continue
                    if recharge[r]:
                        recharge[r] = False
                        acted.add(r)
                        continue
                    mv = moves[r]
                    m = x.d.move(mv)
                    if m['class'] == STATUS:
                        assert r == a and turn == 1, 'only a\'s turn-1 move may be a status move'
                        if first_is_tr:
                            trick_room = True
                        acted.add(r)
                        continue
                    rec = int.from_bytes(x.d.moves[m['id']][18:19], 'little', signed=True)
                    sure = r == self.favored
                    x.ref(r)['cur_hp'], x.ref(t)['cur_hp'] = hp[r], hp[t]
                    dmg = x.total(r, mv, t, sure) * (0.9 if sure else 1.1)
                    if m['effect'] == ai_checks.SUCKER and t in acted:
                        dmg = 0
                    if x.endures(r, mv, t):
                        dmg = min(dmg, hp[t] - 1)
                        if x.item(t) == 'Focus Sash':
                            x.consumed.add(t)
                    dealt = min(int(dmg), hp[t])
                    hp[t] -= dealt
                    acted.add(r)
                    if dealt and x.item(r) == 'Life Orb' and x.ability(r) != 'Magic Guard' and not (
                            x.ability(r) == 'Sheer Force' and x.has_secondary(mv)):
                        hp[r] -= max(1, x.ref(r)['stats']['hp'] // 10)
                    if dealt and rec > 0:
                        hp[r] = min(x.ref(r)['stats']['hp'], hp[r] + max(1, dealt * rec // 100))
                    if dealt and rec < 0 and x.ability(r) not in ('Rock Head', 'Magic Guard'):
                        basis = min(x.total(r, mv, t, False), hp[t] + dealt) if sure else dealt
                        hp[r] -= max(1, basis * (-rec) // 100)
                    if m['effect'] == ai_checks.SELF_KO:
                        hp[r] = 0
                    if m['effect'] == ai_checks.RECHARGE and dealt:
                        recharge[r] = True
                    rr = x.d.moves[m['id']]
                    if rr[1] in (ai_checks.Q_USER_STAT, ai_checks.Q_TARGET_DROP):
                        who = r if rr[1] == ai_checks.Q_USER_STAT else t
                        for k in range(3):
                            stat = ai_checks.STAT_IDS.get(rr[21 + k])
                            amt = int.from_bytes(rr[24 + k:25 + k], 'little', signed=True)
                            if stat and amt and rr[27 + k] == 100:
                                if who == t and amt < 0 and x.ability(t) in ai_checks.DROP_BLOCKERS[stat] and x.ability(r) not in ai_checks.MOLD_BREAKER:
                                    continue
                                x.boosts[(who, stat)] = max(-6, min(6, x.boosts.get((who, stat), 0) + amt))
                    for q in (r, t):
                        mxq = x.ref(q)['stats']['hp']
                        if 0 < hp[q] <= mxq // 2 and x.item(q) in ('Sitrus Berry', 'Oran Berry'):
                            hp[q] = min(mxq, hp[q] + (mxq // 4 if x.item(q) == 'Sitrus Berry' else 10))
                            x.consumed.add(q)
                    if hp[t] <= 0 or hp[r] <= 0:
                        break
                if hp[a] > 0 and hp[b] > 0:
                    for r in self.order_tr(moves, trick_room):
                        hp[r] = self.chip(r, hp[r], tox[r])
                        if x.ref(r)['status'] == 'tox':
                            tox[r] += 1
                if hp[a] <= 0 and hp[b] <= 0:
                    return 'both', turn
                if hp[b] <= 0:
                    return 'a', turn
                if hp[a] <= 0:
                    return 'b', turn
            return None, max_turns
        finally:
            va['cur_hp'], vb['cur_hp'] = saved[a], saved[b]
            x.boosts.clear()
            x.consumed.clear()


def _rules():
    return [(p, q) for p in (4, 2) for q in (8, 16)]


@_op4('b04e_idle_loses')
def idle_loses(x):
    """('b04e_idle_loses', a, idle, mv_a, b, mv_b): a spends turn 1 on the status move `idle` (it does nothing to the fight;
    Trick Room reverses the speed order from turn 2, as the docstring says), then uses mv_a ('*' = each of its attacks);
    b, using mv_b every turn, knocks a out first (b's minimum x 0.9, a's maximum x 1.1, both paralysis and burn rules)."""
    a, idle, mv_a, b, mv_b = x.args
    _actives(x, a, b)
    assert x.d.move(idle)['class'] == STATUS, '%s is not a status move' % idle
    for ma in _race_moves(x, a, mv_a):
        for par_div, burn_div in _rules():
            who, turn = Fight(x, b, par_div, burn_div).fight(a, idle, ma, b, mv_b, 12)
            assert who == 'b', '%s, after %s, is not surely knocked out by %s\'s %s while using %s (paralysis /%d, burn /%d): %s' % (
                x.ref(a)['species'], idle, x.ref(b)['species'], mv_b, ma, par_div, burn_div, who)


@_op4('b04e_opener_race')
def opener_race(x):
    """('b04e_opener_race', a, opener, mv_a, b, mv_b, n): a uses the attack `opener` on turn 1 (its guaranteed stat changes
    count from turn 2, e.g. Rapid Spin's or Flame Charge's +1 Speed) and mv_a afterwards, and knocks b out within n turns
    while standing; b uses mv_b ('*' = each of its attacks) every turn; a's minimum x 0.9, b's maximum x 1.1, both rules."""
    a, opener, mv_a, b, mv_b, n = x.args
    _actives(x, a, b)
    assert x.d.move(opener)['class'] != STATUS, '%s is not an attack' % opener
    for mb in _race_moves(x, b, mv_b):
        for par_div, burn_div in _rules():
            who, turn = Fight(x, a, par_div, burn_div).fight(a, opener, mv_a, b, mb, n)
            assert who == 'a', '%s\'s %s then %s does not surely beat %s\'s %s within %d turns (paralysis /%d, burn /%d)' % (
                x.ref(a)['species'], opener, mv_a, x.ref(b)['species'], mb, n, par_div, burn_div)


@_op4('b04e_drop_race')
def drop_race(x):
    """('b04e_drop_race', a, mv_a, b, mv_b, n, drops): with b's stats already lowered by `drops` ({'atk': -2, 'spa': -2}
    after a Memento), a, using mv_a every turn, knocks b out within n turns while standing; b uses mv_b ('*' = each of its
    attacks); a may be a bench member that comes in once the active in front of it faints (ai_checks._actives)."""
    a, mv_a, b, mv_b, n, drops = x.args
    _actives(x, a, b)
    assert all(k in STAT_NAMES and v < 0 for k, v in drops.items()), 'drops must lower stats'
    assert x.ability(b) not in ai_checks.STAGE_AMBIGUOUS and not any(
        x.ability(b) in ai_checks.DROP_BLOCKERS[k] for k in drops), '%s changes or blocks the drops' % x.ability(b)
    boosts = {(b, k): v for k, v in drops.items()}
    for mb in _race_moves(x, b, mv_b):
        for par_div, burn_div in _rules():
            who, turn = Fight(x, a, par_div, burn_div).fight(a, mv_a, mv_a, b, mb, n, start_boosts=boosts)
            assert who == 'a', '%s\'s %s does not surely beat %s\'s %s at %s within %d turns (paralysis /%d, burn /%d)' % (
                x.ref(a)['species'], mv_a, x.ref(b)['species'], mb, drops, n, par_div, burn_div)


@_op4('b04e_chip_loses')
def chip_loses(x):
    """('b04e_chip_loses', a, mv_a, b, mv_b, c, mv_c): even after b has taken c's mv_c (its maximum x 1.1), a, using mv_a
    ('*' = each of its attacks), is knocked out by b's mv_b before it can knock b out (b's minimum x 0.9, a's maximum x 1.1,
    both rules): the chip does not change the fight. a may be a bench member coming in after the active faints."""
    a, mv_a, b, mv_b, c, mv_c = x.args
    _actives(x, a, b)
    chip = int(x.total(c, mv_c, b, False) * 1.1)
    left = x.ref(b)['cur_hp'] - chip
    assert left > 0, '%s\'s %s can knock %s out' % (x.ref(c)['species'], mv_c, x.ref(b)['species'])
    for ma in _race_moves(x, a, mv_a):
        for par_div, burn_div in _rules():
            who, turn = Fight(x, b, par_div, burn_div).fight(a, ma, ma, b, mv_b, 12, start_hp={b: left})
            assert who == 'b', '%s\'s %s is not surely beaten by %s\'s %s from %d HP (paralysis /%d, burn /%d): %s' % (
                x.ref(a)['species'], ma, x.ref(b)['species'], mv_b, left, par_div, burn_div, who)


def _entry_hit(x, b, mv_b, a, sure):
    """What a takes when it switches in on b's move: b's minimum x 0.9 when the claim favors b, else its maximum x 1.1."""
    return int(x.total(b, mv_b, a, True) * 0.9) if sure else int(x.total(b, mv_b, a, False) * 1.1)


@_op4('b04e_entry_holds')
def entry_holds(x):
    """('b04e_entry_holds', a, b, mv_b): a switches in on b's mv_b ('*' = each of b's attacks) and is still standing (b's
    maximum x 1.1 < a's current HP; no Focus Sash or Sturdy counted)."""
    a, b, mv_b = x.args
    for mb in _race_moves(x, b, mv_b):
        hit = _entry_hit(x, b, mb, a, False)
        assert hit < x.ref(a)['cur_hp'], '%s switching in can be knocked out by %s (%d)' % (x.ref(a)['species'], mb, hit)


@_op4('b04e_entry_loses')
def entry_loses(x):
    """('b04e_entry_loses', a, mv_a, b, mv_b): a switches in on b's mv_b (b's minimum x 0.9), then, using mv_a ('*' = each of
    its attacks), is knocked out by b's mv_b before it can knock b out (b's minimum x 0.9, a's maximum x 1.1, both rules)."""
    a, mv_a, b, mv_b = x.args
    _actives(x, a, b)
    left = x.ref(a)['cur_hp'] - _entry_hit(x, b, mv_b, a, True)
    if left <= 0:
        return
    for ma in _race_moves(x, a, mv_a):
        for par_div, burn_div in _rules():
            who, turn = Fight(x, b, par_div, burn_div).fight(a, ma, ma, b, mv_b, 12, start_hp={a: left})
            assert who == 'b', '%s, switched in at %d HP, is not surely beaten by %s\'s %s while using %s (paralysis /%d, burn /%d)' % (
                x.ref(a)['species'], left, x.ref(b)['species'], mv_b, ma, par_div, burn_div)


SCENARIOS = with_items([
    # --- hazards: only what touches the foe's team counts, and nothing counts against a last Pokemon
    S('b04e_rocks_last_mon', 'utility',
      "Metagross is the player's last Pokemon, so nothing will ever switch in on Stealth Rock and Roar has nothing to bring in (it fails); Garchomp at 60% is faster and Earthquake (2x) KOs in two hits while Meteor Mash needs two to KO it, so attacking now wins the race and any wasted turn loses it; Dragon Claw is resisted",
      [mon('Metagross', ['Meteor Mash', 'Zen Headbutt', 'Earthquake', 'ThunderPunch'])],
      [mon('Garchomp', ['Stealth Rock', 'Roar', 'Earthquake', 'Dragon Claw'], hp=0.6)],
      best=['Earthquake'], bad=['Stealth Rock', 'Roar', 'Dragon Claw'],
      checks=[('b04e_no_bench', 'player'), ('faster', 'e0', 'p0'), ('race', 'e0', 'Earthquake', 'p0', '*', 2), ('mnoko', 'e0', 'Earthquake', 'p0'),
              ('b04e_idle_loses', 'e0', 'Stealth Rock', 'Earthquake', 'p0', 'Meteor Mash'), ('b04e_idle_loses', 'e0', 'Roar', 'Earthquake', 'p0', 'Meteor Mash'),
              ('loses', 'e0', 'Dragon Claw', 'p0', 'Meteor Mash'), ('eff', 'e0', 'Dragon Claw', 'p0', 0.5)]),
    S('b04e_rocks_air_team', 'utility',
      "Levitate Eelektross and Ground-type Clodsire cannot touch each other (Earthquake fails on Levitate; Thunderbolt, Volt Switch, Charge Beam and Thunder Wave fail on a Ground type), so the turn goes to a hazard: every player Pokemon is airborne (Levitate, two Flying types), so Spikes and Toxic Spikes would never touch any of them, while Stealth Rock takes half of Charizard and a quarter of Gyarados each time they come in (hazards are not measured in this ROM; if they did nothing, every option here would do nothing)",
      [mon('Eelektross', ['Thunderbolt', 'Volt Switch', 'Thunder Wave', 'Charge Beam'], ability='Levitate'),
       mon('Charizard', ['Flamethrower', 'Air Slash', 'Roost']), mon('Gyarados', ['Waterfall', 'Ice Fang', 'Dragon Dance'])],
      [mon('Clodsire', ['Stealth Rock', 'Spikes', 'Toxic Spikes', 'Earthquake'])],
      best=['Stealth Rock'], bad=['Spikes', 'Toxic Spikes', 'Earthquake'],
      checks=[('eff', 'p0', 'Thunderbolt', 'e0', 0.0), ('eff', 'p0', 'Volt Switch', 'e0', 0.0), ('eff', 'p0', 'Charge Beam', 'e0', 0.0),
              ('type', 'e0', 'Ground'), ('eff', 'e0', 'Earthquake', 'p0', 0.0),
              ('b04e_hazard', 'Stealth Rock', 'p0', 0.125), ('b04e_hazard', 'Stealth Rock', 'p1', 0.5), ('b04e_hazard', 'Stealth Rock', 'p2', 0.25),
              ('b04e_hazard', 'Spikes', 'p0', 0), ('b04e_hazard', 'Spikes', 'p1', 0), ('b04e_hazard', 'Spikes', 'p2', 0),
              ('b04e_hazard', 'Toxic Spikes', 'p0', 0), ('b04e_hazard', 'Toxic Spikes', 'p1', 0), ('b04e_hazard', 'Toxic Spikes', 'p2', 0)]),
    S('b04e_spikes_steel_team', 'utility',
      "Forretress and Levitate Bronzong wall each other (every attack either has is resisted, and Toxic fails on a Steel type), so the turn goes to a hazard: the player's bench is three grounded Steel types, which Stealth Rock barely scratches (a 32nd, a 32nd and a 16th) and Toxic Spikes cannot poison, while one layer of Spikes takes an eighth from each; Rapid Spin has nothing to clear (hazards are not measured in this ROM; if they did nothing, every option here would do nothing)",
      [mon('Bronzong', ['Gyro Ball', 'Psychic', 'Toxic'], ability='Levitate'),
       mon('Excadrill', ['Earthquake', 'Iron Head']), mon('Lucario', ['Close Combat', 'Flash Cannon']), mon('Metagross', ['Meteor Mash', 'Earthquake'])],
      [mon('Forretress', ['Spikes', 'Stealth Rock', 'Toxic Spikes', 'Rapid Spin'])],
      best=['Spikes'], ok=['Stealth Rock'], bad=['Toxic Spikes'],
      checks=[('type', 'e0', 'Steel'), ('eff', 'p0', 'Gyro Ball', 'e0', 0.5), ('eff', 'p0', 'Psychic', 'e0', 0.5), ('eff', 'e0', 'Rapid Spin', 'p0', 0.5),
              ('b04e_hazard', 'Spikes', 'p0', 0), ('b04e_hazard', 'Spikes', 'p1', 0.125), ('b04e_hazard', 'Spikes', 'p2', 0.125), ('b04e_hazard', 'Spikes', 'p3', 0.125),
              ('b04e_hazard', 'Stealth Rock', 'p0', 0.0625), ('b04e_hazard', 'Stealth Rock', 'p1', 0.03125), ('b04e_hazard', 'Stealth Rock', 'p2', 0.03125),
              ('b04e_hazard', 'Stealth Rock', 'p3', 0.0625),
              ('b04e_hazard', 'Toxic Spikes', 'p0', 0), ('b04e_hazard', 'Toxic Spikes', 'p1', 0), ('b04e_hazard', 'Toxic Spikes', 'p2', 0), ('b04e_hazard', 'Toxic Spikes', 'p3', 0)]),

    # --- moves that only work in the right order
    S('b04e_db_vs_sneak', 'switch',
      "Gengar at 20% is faster than Dusknoir and looks doomed, so Destiny Bond seems a free trade, but Dusknoir's Shadow Sneak (priority, 2x) KOs it before it moves, so neither Destiny Bond nor any attack ever happens; Snorlax is immune to both Ghost moves and takes Earthquake or Ice Punch for under a third, while Alakazam at 85% is KO'd by Shadow Punch on the way in",
      [mon('Dusknoir', ['Shadow Sneak', 'Shadow Punch', 'Earthquake', 'Ice Punch'])],
      [mon('Gengar', ['Destiny Bond', 'Shadow Ball', 'Sludge Bomb', 'Focus Blast'], hp=0.2),
       mon('Snorlax', ['Body Slam', 'Crunch', 'Earthquake', 'Curse']), mon('Alakazam', ['Psychic', 'Focus Blast', 'Shadow Ball'], hp=0.85)],
      best=['switch:Snorlax'], bad=['Destiny Bond', 'Shadow Ball', 'Sludge Bomb', 'Focus Blast', 'switch:Alakazam'],
      checks=[('faster', 'e0', 'p0'), ('pri', 'Shadow Sneak', 1), ('ko', 'p0', 'Shadow Sneak', 'e0'), ('cls', 'Destiny Bond', 'status'),
              ('eff', 'p0', 'Shadow Sneak', 'e1', 0.0), ('eff', 'p0', 'Shadow Punch', 'e1', 0.0), ('b04e_entry_holds', 'e1', 'p0', '*'),
              ('ko', 'p0', 'Shadow Punch', 'e2'), ('eff', 'e0', 'Focus Blast', 'p0', 0.0)]),
    S('b04e_tr_vs_par', 'utility',
      "Garchomp is naturally faster than Mr. Mime, but it is paralyzed, so Mr. Mime moves first and Moonblast (2x) KOs it in two hits before its second Earthquake; Trick Room (-7 priority) would hand Garchomp the first move from the next turn, and even if it failed it wastes the turn, so either way Garchomp wins; Taunt does nothing to a Pokemon that only attacks, Psychic is too weak, and Outrage cannot touch a Fairy",
      [mon('Garchomp', ['Earthquake', 'Outrage', 'Stone Edge', 'Fire Fang'], status='par'), mon('Tyranitar', ['Crunch', 'Stone Edge'])],
      [mon('Mr. Mime', ['Trick Room', 'Moonblast', 'Psychic', 'Taunt'])],
      best=['Moonblast'], bad=['Trick Room', 'Psychic', 'Taunt'],
      checks=[('has_status', 'p0', 'par'), ('mfaster', 'e0', 'p0'), ('race', 'e0', 'Moonblast', 'p0', '*', 2), ('pri', 'Trick Room', -7),
              ('b04e_idle_loses', 'e0', 'Trick Room', 'Moonblast', 'p0', 'Earthquake'), ('b04e_idle_loses', 'e0', 'Taunt', 'Moonblast', 'p0', 'Earthquake'),
              ('loses', 'e0', 'Psychic', 'p0', 'Earthquake'), ('eff', 'p0', 'Outrage', 'e0', 0.0), ('mnoko', 'e0', 'Moonblast', 'p0')]),
    S('b04e_taunt_staller', 'utility',
      "Blissey has only status moves (Toxic, Soft-Boiled, Thunder Wave, Heal Bell): its Soft-Boiled heals half its HP, more than Thundurus's best hit (Focus Blast, under a third), so attacks never get through, and Toxic wins the long game; Thundurus is faster, so Taunt lands before Blissey's first move and leaves it nothing but Struggle (Taunt is not measured in this ROM; if it failed, the attacks would gain nothing either)",
      [mon('Blissey', ['Toxic', 'Soft-Boiled', 'Thunder Wave', 'Heal Bell'])],
      [mon('Thundurus', ['Taunt', 'Thunderbolt', 'Focus Blast', 'Hurricane'])],
      best=['Taunt'],
      checks=[('status_only', 'p0'), ('b04e_outheals', 'e0', 'p0', 'Soft-Boiled'), ('faster', 'e0', 'p0'), ('eff', 'e0', 'Focus Blast', 'p0', 2.0),
              ('cls', 'Taunt', 'status'), ('type', 'e0', 'Electric')]),

    # --- pivots, Memento, Perish Song, Rapid Spin
    S('b04e_slow_u_turn', 'switch',
      "Garchomp is faster than Scizor but none of its moves KO it, so a slow U-turn takes the hit, chips Garchomp and brings Weavile in after Garchomp has moved; Weavile is faster and Ice Punch (4x) then surely KOs the chipped Garchomp, which from full HP it might not; switching Weavile in directly hands it a Brick Break (4x) that KOs it, and Scizor staying in loses to Earthquake (U-turn's switch is not measured in this ROM; without it U-turn is just a hit, no worse than the others)",
      [mon('Garchomp', ['Earthquake', 'Outrage', 'Brick Break', 'Swords Dance'])],
      [mon('Scizor', ['U-turn', 'Bullet Punch', 'Iron Head', 'X-Scissor']), mon('Weavile', ['Ice Punch', 'Ice Shard', 'Night Slash', 'Swords Dance'])],
      best=['U-turn'], bad=['switch:Weavile'],
      checks=[('pivot', 'U-turn'), ('faster', 'p0', 'e0'), ('mnoko', 'p0', 'Earthquake', 'e0'), ('mnoko', 'p0', 'Outrage', 'e0'), ('mnoko', 'p0', 'Brick Break', 'e0'),
              ('b04e_ko_after', 'e0', 'U-turn', 'e1', 'Ice Punch', 'p0'), ('faster', 'e1', 'p0'), ('eff', 'e1', 'Ice Punch', 'p0', 4.0),
              ('ko', 'p0', 'Brick Break', 'e1'), ('loses', 'e0', '*', 'p0', 'Earthquake')]),
    S('b04e_memento_last', 'utility',
      "Metagross is the player's last Pokemon, so it cannot switch away stat drops; Whimsicott is faster but Meteor Mash (2x) KOs it and its own attacks are resisted; Tyranitar comes in after Whimsicott falls either way and loses to Metagross at full strength even after Whimsicott's chip, but against Attack and Sp. Atk at -2 Crunch (2x) wins: Memento (not measured in this ROM; without the drops it ends like an attack) is the only line that wins",
      [mon('Metagross', ['Meteor Mash', 'Zen Headbutt', 'Earthquake', 'Ice Punch'])],
      [mon('Whimsicott', ['Memento', 'Moonblast', 'Energy Ball', 'Taunt']), mon('Tyranitar', ['Crunch', 'Stone Edge', 'Earthquake', 'Fire Blast'])],
      best=['Memento'],
      checks=[('b04e_no_bench', 'player'), ('mfaster', 'e0', 'p0'), ('mko', 'p0', 'Meteor Mash', 'e0'), ('eff', 'e0', 'Moonblast', 'p0', 0.5), ('eff', 'e0', 'Energy Ball', 'p0', 0.5),
              ('b04e_chip_loses', 'e1', '*', 'p0', 'Meteor Mash', 'e0', 'Moonblast'), ('b04e_chip_loses', 'e1', '*', 'p0', 'Meteor Mash', 'e0', 'Energy Ball'),
              ('b04e_drop_race', 'e1', 'Crunch', 'p0', '*', 4, {'atk': -2, 'spa': -2}), ('b04e_entry_loses', 'e1', '*', 'p0', 'Meteor Mash')]),
    S('b04e_perish_wonder_guard', 'utility',
      "The player's last Pokemon is Wonder Guard Shedinja, and nothing on the AI's team is super effective on it, so every attack fails; Perish Song is a status move that Wonder Guard does not stop, and with no bench Shedinja cannot switch out of the count, while the AI still has Snorlax (immune to Shedinja's Ghost moves) after Lapras (Perish Song is not measured in this ROM; if it failed, nothing else here could do anything either)",
      [mon('Shedinja', ['X-Scissor', 'Shadow Claw', 'Shadow Sneak', 'Swords Dance'], ability='Wonder Guard')],
      [mon('Lapras', ['Perish Song', 'Surf', 'Ice Beam', 'Body Slam']), mon('Snorlax', ['Body Slam', 'Earthquake', 'Curse', 'Rest'])],
      best=['Perish Song'], bad=['Surf', 'Ice Beam', 'Body Slam'],
      checks=[('b04e_no_bench', 'player'), ('has_ability', 'p0', 'Wonder Guard'), ('cls', 'Perish Song', 'status'),
              ('meff', 'e0', 'Surf', 'p0', 0.0), ('meff', 'e0', 'Ice Beam', 'p0', 0.0), ('meff', 'e0', 'Body Slam', 'p0', 0.0),
              ('meff', 'e1', 'Body Slam', 'p0', 0.0), ('meff', 'e1', 'Earthquake', 'p0', 0.0),
              ('eff', 'p0', 'Shadow Claw', 'e1', 0.0), ('eff', 'p0', 'Shadow Sneak', 'e1', 0.0), ('mnoko', 'p0', 'X-Scissor', 'e0')]),
    S('b04e_spin_speed', 'utility',
      "Zapdos at 35% is faster than Excadrill and Heat Wave (2x) KOs it in two hits, while no Excadrill attack KOs Zapdos in one (Earthquake cannot touch it), so trading hits loses; this ROM's Rapid Spin raises the user's Speed by one stage (the move data says so; the boost is not measured): spinning first makes Excadrill faster than Zapdos, and the spin's chip plus Shadow Claw KOs it before the second Heat Wave",
      [mon('Zapdos', ['Thunderbolt', 'Heat Wave', 'Hurricane'], hp=0.35)],
      [mon('Excadrill', ['Rapid Spin', 'Earthquake', 'Iron Head', 'Shadow Claw'])],
      best=['Rapid Spin'], bad=['Earthquake'],
      checks=[('faster', 'p0', 'e0'), ('b04e_opener_race', 'e0', 'Rapid Spin', 'Shadow Claw', 'p0', '*', 2), ('eff', 'e0', 'Earthquake', 'p0', 0.0),
              ('loses', 'e0', 'Shadow Claw', 'p0', 'Heat Wave'), ('loses', 'e0', 'Iron Head', 'p0', 'Heat Wave'), ('mnoko', 'p0', 'Heat Wave', 'e0'),
              ('mnoko', 'e0', 'Shadow Claw', 'p0'), ('mnoko', 'e0', 'Iron Head', 'p0')]),
])
