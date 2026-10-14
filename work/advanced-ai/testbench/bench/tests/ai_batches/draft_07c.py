"""Batch 07, part c (draft): positions where a strong player knows the right play. Themes: item and move rules (a Weakness Policy
holder that stays in to take the hit, and one too low on HP for the policy to fire; Destiny Bond from a slower Focus Sash user;
Toxic on a 1-HP Wonder Guard holder); two-turn plans (the strong move first and priority on the last turn, a priority chip that lets
the next Pokemon win, the surer of two KO moves under the AI's own rain); and the replacement after a faint, turned into turn-1
decisions.

The replacement after a faint cannot be graded as such: the bench stops at the first action of turn 1 (see batch_06a.py). It is
adapted in two opposite positions. In b07c_switch_to_mirror_coat the doomed lead should leave at once: one candidate outspeeds and
KOs the foe but cannot take the hit it switches into, another takes that hit and the next one and wins with Mirror Coat, and a
Counter user loses (Counter cannot return a special hit); letting the lead fall to bring the fast candidate in free also wins, but
costs the lead. In b07c_free_entry_metal_burst the doomed lead should stay: the Metal Burst user wins only from the free entry after
the faint, since a hard switch costs it the hit that it needed to survive.

The ops below extend tests/ai_checks.py without editing it. Each is registered in ai_checks.CHECKS on import (prefix b07c_), before
`with_items` runs. Two classes of earlier batches are reused by loading those files: batch_05a.C5 (ai_checks.Ctx plus Weakness
Policy) and batch_06a.Fight (plans of moves with Counter, Mirror Coat and Metal Burst). The ops of earlier batches (b03_, b04b_,
b05_, b06_) are used as they are; every bench run loads batch_01..06 before the drafts. The rules, on top of the hack's data, with
the evidence from this ROM (qa/aivsai/runs are the AI-vs-AI battle logs):
  Weakness Policy (b07c_wp_holds): every sequence of the foe's attacks is played turn by turn (ai_checks.Race's order and margins:
      the holder is favored, its minimum x 0.9 against the foe's maximum x 1.1); the first super effective hit that leaves the
      holder standing raises its Attack and Sp. Atk by four stages (measured, ENGINE_FACTS.md), in force from its next action on,
      the same turn included (seen: runs/20261003_100721/s013_g0.log turn 3, Coalossal's Flare Blitz right after the policy went
      off KOd Arceus at 358 HP; it does 133-157 unboosted and 399-469 at +4, and no critical hit was shown).
  Destiny Bond (b07c_db_trade): Gen 5. The bond lasts until its user moves again; if the user faints from a foe's attack before
      then, the attacker faints too. Fainting at the end of a turn (poison, sand) does not set it off. Seen lasting into the next
      turn: runs/20261002_234540/s038_g1.log turns 12-13 (Shiftry's Sucker Punch) and runs/20261003_030315/s006_g0.log turns 11-12
      (Crawdaunt's Knock Off) both knocked the bond user out first thing in the next turn and fainted with it.
  Toxic into Wonder Guard (b07c_status_kos): Wonder Guard blocks only damaging moves (Gen 5), so Toxic lands, and the first
      end-of-turn bad poison damage (1/16, at least 1 HP) knocks out a holder at 1 HP. Seen: runs/20261004_021033_self/s006_g0.log
      turn 5, Tentacruel's Toxic badly poisoned Shedinja, and the poison knocked it out at the end of the turn. A burn on a 1-HP
      holder is not in the logs, so Will-O-Wisp is not modeled.
  The switch-in fight (b07c_entry_fight): a bench member switches in, takes the foe's attack, and then fights under batch_06a's
      b06_fight rules (Counter and Mirror Coat return twice, Metal Burst one and a half times, the damage of the hit taken earlier
      the same turn). Seen in qa/aivsai/runs: every Mirror Coat (27) and Counter (77 of 78) whose target survived returned
      exactly twice the single hit before it, and every Metal Burst (24) one and a half times, rounded down.
"""
import importlib.util
import itertools
import os

import ai_checks
from ai_checks import CHECKS, STATUS, T, Race, _actives, _race_moves, with_items
from aidata import norm
from ai_helpers import PLAIN, S, mon  # noqa: F401

_HERE = os.path.dirname(os.path.abspath(__file__))


def _load(fname):
    spec = importlib.util.spec_from_file_location('ai_batch_07c_' + fname[:-3], os.path.join(_HERE, fname))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_B5 = _load('batch_05a.py')
_B6 = _load('batch_06a.py')
C5, Fight = _B5.C5, _B6.Fight

DESTINY_BOND = 98
POISON, STEEL = T['Poison'], T['Steel']
TOXIC_REFUSED_ABILITIES = _B6.TOXIC_REFUSED_ABILITIES
TOXIC_REFUSED_ITEMS = _B6.TOXIC_REFUSED_ITEMS
UNMODELED_HP_ITEMS = {'Life Orb', 'Sitrus Berry', 'Oran Berry', 'Shell Bell'}


def _op7(name, ctx=ai_checks.Ctx):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(ctx(d, views, c, ref))
        return fn
    return reg


def _plain(x, r, mv):
    """A move these ops play as a plain hit: no recoil, drain, self-KO, recharge or sure stat change."""
    m = x.d.move(mv)
    raw = x.d.moves[m['id']]
    assert int.from_bytes(raw[18:19], 'little', signed=True) == 0, '%s has recoil or drain: not modeled here' % mv
    assert m['effect'] not in (ai_checks.SELF_KO, ai_checks.RECHARGE), '%s is not a plain hit' % mv
    if raw[1] in (ai_checks.Q_USER_STAT, ai_checks.Q_TARGET_DROP):
        assert all(raw[27 + k] != 100 for k in range(3)), '%s changes a stat for sure: not modeled here' % mv


class _Hp:
    """Sets the views' current HP for the duration of a block and restores it."""

    def __init__(self, x, hp):
        self.x, self.hp = x, hp

    def __enter__(self):
        self.saved = {r: self.x.ref(r)['cur_hp'] for r in self.hp}
        for r, h in self.hp.items():
            self.x.ref(r)['cur_hp'] = h

    def __exit__(self, *a):
        for r, h in self.saved.items():
            self.x.ref(r)['cur_hp'] = h


# --- Weakness Policy: the holder stays in

def _hit(x, a, mv, df, hp, sure):
    """Damage of one action at the margin (sure: minimum x 0.9, else maximum x 1.1), Focus Sash / Sturdy at full HP."""
    with _Hp(x, hp):
        dmg = int(x.total(a, mv, df, sure) * (0.9 if sure else 1.1))
        if x.endures(a, mv, df):
            dmg = min(dmg, hp[df] - 1)
            if x.item(df) == 'Focus Sash':
                x.consumed.add(df)
    return min(dmg, hp[df])


@_op7('b07c_wp_holds', C5)
def wp_holds(x):
    """('b07c_wp_holds', e, mv, p, n): e holds Weakness Policy and stays in, using mv every turn, while p uses any of its attacks
    on any turn (every sequence of n turns is tried): e knocks p out within n turns and is still standing. The turn order is
    ai_checks.Race's (priority, then Speed under both paralysis rules); e's hits are its minimum x 0.9, p's its maximum x 1.1; the
    first super effective hit that leaves e standing raises e's Attack and Sp. Atk by four stages (this hack, measured); Focus Sash
    and Sturdy hold once at full HP; the end of each turn follows ai_checks.Race.chip under both burn rules. Moves with recoil,
    drain, self-KO, recharge or a sure stat change, and Life Orb, Shell Bell and HP berries, are refused."""
    e, mv, p, n = x.args
    assert x.items.get(e) == 'Weak. Policy', '%s does not hold Weakness Policy' % x.ref(e)['species']
    moves_p = _race_moves(x, p, '*')
    for r, m in [(e, mv)] + [(p, m) for m in moves_p]:
        _plain(x, r, m)
    for r in (e, p):
        assert x.item(r) not in UNMODELED_HP_ITEMS, '%s holds %s' % (x.ref(r)['species'], x.item(r))
        assert x.ref(r)['status'] not in ('tox', 'slp', 'frz'), '%s: a status these turns do not model' % x.ref(r)['species']
    _actives(x, e, p)
    mx = {e: x.ref(e)['stats']['hp'], p: x.ref(p)['stats']['hp']}
    for par_div in (4, 2):
        for burn_div in (8, 16):
            race = Race(x, e, par_div, burn_div)
            race.vet_move(e, mv, p)
            for mp in moves_p:
                race.vet_move(p, mp, e)
            for seq in itertools.product(moves_p, repeat=n):
                hp = {e: x.ref(e)['cur_hp'], p: x.ref(p)['cur_hp']}
                x.boosts.clear()
                x.consumed.clear()
                fired, won = False, False
                try:
                    for turn, mp in enumerate(seq, 1):
                        for r in race.order({e: mv, p: mp}):
                            t = p if r == e else e
                            if hp[r] <= 0 or hp[t] <= 0:
                                continue
                            hp[t] -= _hit(x, r, mv if r == e else mp, t, dict(hp), r == e)
                            if r == p and hp[e] > 0 and not fired and (x.effectiveness(p, mp, e) or 0) > 1:
                                fired = True
                                x.boosts[(e, 'atk')], x.boosts[(e, 'spa')] = 4, 4
                        if hp[e] > 0 and hp[p] > 0:
                            with _Hp(x, dict(hp)):
                                for r in race.order({e: mv, p: mp}):
                                    hp[r] = min(mx[r], race.chip(r, hp[r], 1))
                        assert hp[e] > 0, '%s falls on turn %d to %s (par /%d, burn /%d)' % (
                            x.ref(e)['species'], turn, ', '.join(seq[:turn]), par_div, burn_div)
                        if hp[p] <= 0:
                            won = True
                            break
                finally:
                    x.boosts.clear()
                    x.consumed.clear()
                assert won, '%s does not knock %s out within %d turns against %s (par /%d, burn /%d)' % (
                    x.ref(e)['species'], x.ref(p)['species'], n, ', '.join(seq), par_div, burn_div)


# --- Destiny Bond

@_op7('b07c_db_trade')
def db_trade(x):
    """('b07c_db_trade', e, p): e uses Destiny Bond this turn and p goes down with it next turn (module docstring). The claim:
    e has Destiny Bond and no move with priority (it cannot move first next turn and end the bond); p has only attacks, none with
    negative priority, and is faster than e under both paralysis rules; e survives each of p's attacks this turn, whatever the
    order (maximum x 1.1 under its HP, or Focus Sash / Sturdy at full HP against a single hit); the end of this turn takes nothing
    from e; and next turn each of p's attacks knocks e out (minimum x 0.9) from the most HP the first hit can leave it. A foe that
    sees the bond can still decline to attack; the key's assumption is that it plays its best attack."""
    e, p = x.args
    ev, pv = x.ref(e), x.ref(p)
    assert any(x.d.move(m)['effect'] == DESTINY_BOND for m in ev['moves']), '%s has no Destiny Bond' % ev['species']
    assert all(x.d.move(m)['priority'] <= 0 for m in ev['moves']), '%s has a priority move' % ev['species']
    for m in pv['moves']:
        assert x.d.move(m)['class'] != STATUS, '%s has a status move (%s): it could wait out the bond' % (pv['species'], m)
        assert x.d.move(m)['priority'] >= 0, '%s has a negative priority move' % pv['species']
    for div in (4, 2):
        assert x.speed(p, div) > x.speed(e, div), '%s is not faster than %s (paralysis /%d)' % (pv['species'], ev['species'], div)
    assert not x.moves_last(p), '%s moves last' % pv['species']
    hp0 = ev['cur_hp']
    for m1 in pv['moves']:
        x.consumed.clear()
        hi = _hit(x, p, m1, e, {e: hp0, p: pv['cur_hp']}, False)
        assert hi < hp0, '%s can knock %s out this turn before the bond: %s does up to %d of %d' % (pv['species'], ev['species'], m1, hi, hp0)
        lo = _hit(x, p, m1, e, {e: hp0, p: pv['cur_hp']}, True)
        left = hp0 - lo
        with _Hp(x, {e: left}):
            for div in (8, 16):
                after = Race(x, p, 4, div).chip(e, left, 1)
                assert after >= left, '%s loses HP at the end of the turn (%d to %d): it could faint without a bond' % (ev['species'], left, after)
        for m2 in pv['moves']:
            with _Hp(x, {e: left}):
                k = int(x.total(p, m2, e, True) * 0.9)
                assert not x.endures(p, m2, e) and k >= left, '%s\'s %s does at least %d: %s keeps %d HP after %s' % (
                    pv['species'], m2, k, ev['species'], left, m1)
    x.consumed.clear()


# --- Toxic into Wonder Guard

@_op7('b07c_status_kos')
def status_kos(x):
    """('b07c_status_kos', p, 'Toxic', e): p's Toxic (a status move, which Wonder Guard does not block) can hit e, and the bad
    poison it then takes at the end of this turn (ai_checks.Race.chip: 1/16, at least 1; Leftovers and the like counted) knocks e
    out. The target must not be a Poison or Steel type and must have none of batch_06a's refused abilities and items. Magic
    Guard takes no such damage. Accuracy is a separate fact, stated in the description."""
    p, mv, e = x.args
    m = x.d.move(mv)
    ev = x.ref(e)
    assert norm(mv) == 'toxic', '%s: only Toxic is modeled' % mv
    assert mv in x.ref(p)['moves'] and m['class'] == STATUS, '%s is not a status move of %s' % (mv, x.ref(p)['species'])
    assert not ev['status'], '%s already has a status' % ev['species']
    ab, it = x.ability(e), x.item(e)
    assert not ({POISON, STEEL} & set(ev['types'])), '%s cannot be poisoned' % ev['species']
    assert ab not in TOXIC_REFUSED_ABILITIES and it not in TOXIC_REFUSED_ITEMS, '%s: %s / %s' % (ev['species'], ab, it)
    assert x.effectiveness(p, mv, e) is None, '%s is not a status move' % mv
    saved = ev['status']
    ev['status'] = 'tox'
    try:
        left = Race(x, e, 4, 16).chip(e, ev['cur_hp'], 1)
    finally:
        ev['status'] = saved
    assert left <= 0, '%s keeps %d HP after the first end-of-turn damage' % (ev['species'], left)


# --- a switch-in that takes the hit, then fights

@_op7('b07c_entry_fight')
def entry_fight(x):
    """('b07c_entry_fight', b, plan_b, p, plan_p, entry, n, want): the bench member b switches in this turn and takes p's entry move
    (an attack of p, or '*' for each of p's attacks), the end of the turn follows ai_checks.Race.chip, and from the next turn b and p
    fight under batch_06a's b06_fight rules (plans of moves, the last repeated; '*' = each attack of that side, tried one at a time;
    Counter, Mirror Coat, Metal Burst; both paralysis and both burn rules). want 'win': b is favored: the entry hit is p's maximum
    x 1.1 (Focus Sash and Sturdy hold at full HP), b survives it and then knocks p out within n turns under every plan of p. want
    'lose': p is favored: the entry hit is p's minimum x 0.9, and b either falls to it or loses the fight within n turns under every
    plan of b."""
    b, plan_b, p, plan_p, entry, n, want = x.args
    assert want in ('win', 'lose'), 'want is win or lose'
    assert b[0] != p[0] and b not in x.actives[x.side(b)], '%s is not a bench member' % b
    _actives(x, b, p)
    favored = b if want == 'win' else p
    bv, pv = x.ref(b), x.ref(p)
    entries = _race_moves(x, p, entry)
    plans_b, plans_p = _B6._plans(x, b, plan_b), _B6._plans(x, p, plan_p)
    assert not (want == 'win' and len(plans_b) > 1) and not (want == 'lose' and len(plans_p) > 1), (
        "'*' belongs to the side whose every option is tried")
    for em in entries:
        x.consumed.clear()
        Race(x, favored, 4, 8).vet_move(p, em, b)
        hit = _hit(x, p, em, b, {b: bv['cur_hp'], p: pv['cur_hp']}, want == 'lose')
        left = bv['cur_hp'] - hit
        if want == 'win':
            assert left > 0, '%s can fall to %s as it switches in (up to %d of %d)' % (bv['species'], em, hit, bv['cur_hp'])
        elif left <= 0:
            continue
        for par_div in (4, 2):
            for burn_div in (8, 16):
                race = Race(x, favored, par_div, burn_div)
                with _Hp(x, {b: left}):
                    hb = race.chip(b, left, 2 if favored == b else 1)
                    hp_ = race.chip(p, pv['cur_hp'], 2 if favored == p else 1)
                if want == 'win':
                    assert hb > 0, '%s falls at the end of the entry turn' % bv['species']
                    if hp_ <= 0:
                        continue
                elif hb <= 0:
                    continue
                for pb in plans_b:
                    for pp in plans_p:
                        with _Hp(x, {b: hb, p: hp_}):
                            who, turn = Fight(x, favored, par_div, burn_div).play(b, pb, p, pp, n)
                        assert who == favored, '%s in on %s (%d HP left, %s), %s vs %s %s: %s within %d turns (par /%d, burn /%d)' % (
                            bv['species'], em, hb, bv['status'] or 'no status', '/'.join(pb), pv['species'], '/'.join(pp),
                            'neither wins' if who is None else x.ref(who)['species'] + ' wins on turn %d' % turn, n, par_div, burn_div)


SCENARIOS = with_items([
    # --- 6. item and move rules

    S('b07c_wp_holder_stays', 'item',
      "Vaporeon holds Weakness Policy and is slower than Jolteon, whose Thunderbolt (2x, 57-67%) would win the race on paper; but "
      'it cannot KO from full, so the policy fires (+4 Attack and Sp. Atk in this hack, measured) and Surf then KOs Jolteon the same '
      "turn, while against Jolteon's neutral moves (at most 20%) Vaporeon wins the race in two Surfs; Golurk looks safe from "
      "Thunderbolt, but Jolteon's best move against the policy is Shadow Ball (2x on Golurk), which with a second one KOs it first",
      [mon('Jolteon', ['Thunderbolt', 'Shadow Ball', 'Signal Beam'], hp=0.85)],
      [mon('Vaporeon', ['Surf', 'Ice Beam', 'Wish', 'Protect'], item='Weak. Policy', evs={'spa': 252}),
       mon('Golurk', ['Earthquake', 'Shadow Punch', 'Ice Punch'], hp=0.55)],
      best=['Surf'],
      checks=[('b05_faster', 'p0', 'e0'), ('b07c_wp_holds', 'e0', 'Surf', 'p0', 2), ('b05_wp', 'p0', 'Thunderbolt', 'e0'),
              ('b05_boosted_ko', 'e0', 'Surf', 'p0', 4), ('b05_loses', 'e0', 'Surf', 'p0', 'Thunderbolt'),
              ('b05_eff', 'p0', 'Thunderbolt', 'e1', 0.0),
              ('b05_loses_after', 'e1', '*', 'p0', 'Shadow Ball', [('p0', 'Shadow Ball', 'e1'), 'eot'])]),

    S('b07c_wp_too_low', 'item',
      'Ursaluna holds Weakness Policy, but at 45% it is slower than Starmie, whose Surf (2x) KOs it outright, so the policy never '
      'fires and none of its moves land (from full HP it would survive Surf and the policy would turn the game); Ludicolo takes Surf '
      'for under 11% and wins with Giga Drain (2x, 56-68%) in two hits',
      [mon('Starmie', ['Surf', 'Psychic', 'Ice Beam', 'Thunderbolt'])],
      [mon('Ursaluna', ['Earthquake', 'Facade', 'Crunch', 'Ice Punch'], item='Weak. Policy', hp=0.45),
       mon('Ludicolo', ['Giga Drain', 'Ice Beam', 'Scald'])],
      best=['switch:Ludicolo'], bad=['Earthquake', 'Facade', 'Crunch', 'Ice Punch'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Surf', 'e0'), ('b05_noko_at', 'p0', 'Surf', 'e0', 1.0),
              ('b05_eff', 'p0', 'Surf', 'e0', 2.0),
              ('b05_wins_after', 'e1', 'Giga Drain', 'p0', '*', 2, [('p0', 'Surf', 'e1'), 'eot'])]),

    S('b07c_db_sash_slower', 'rules',
      'Focus Sash Smeargle at full HP is slower than Garchomp, whose Earthquake or Outrage would KO it: the Sash keeps it at 1 HP '
      "(Garchomp's weaker hits leave it in range anyway), so Destiny Bond goes up this turn, and next turn the faster Garchomp KOs "
      'Smeargle before it moves and faints with it; Seismic Toss only chips, and Heatran, the other Pokemon, falls to Earthquake (4x)',
      [mon('Garchomp', ['Earthquake', 'Outrage', 'Stone Edge', 'Crunch'])],
      [mon('Smeargle', ['Destiny Bond', 'Seismic Toss', 'Stealth Rock', 'Whirlwind'], item='Focus Sash'),
       mon('Heatran', ['Flamethrower', 'Earth Power', 'Flash Cannon'])],
      best=['Destiny Bond'], bad=['switch:Heatran'],
      checks=[('b07c_db_trade', 'e0', 'p0'), ('b06_endures', 'e0', 'p0', 'Earthquake'), ('b06_faster', 'p0', 'e0'),
              ('b03_single_hits', 'p0'), ('b06_ko', 'p0', 'Earthquake', 'e1'), ('b06_eff', 'p0', 'Earthquake', 'e1', 4.0)]),

    S('b07c_toxic_wonder_guard', 'rules',
      "Jellicent's Scald and Ice Beam cannot touch Wonder Guard Shedinja, but Toxic is a status move, which Wonder Guard does not "
      "block, and bad poison takes Shedinja's only HP at the end of the turn (90% accuracy); Shedinja's Shadow Sneak and Shadow "
      'Claw (2x) cannot KO Jellicent first, so staying loses Shedinja for a scratch; Magnezone is a Steel type, so Toxic cannot '
      'poison it, and it takes Scald or Ice Beam easily and beats Jellicent with Thunderbolt (2x)',
      [mon('Jellicent', ['Scald', 'Ice Beam', 'Toxic', 'Recover'])],
      [mon('Shedinja', ['Shadow Sneak', 'Shadow Claw', 'X-Scissor', 'Swords Dance'], ability='Wonder Guard'),
       mon('Magnezone', ['Thunderbolt', 'Flash Cannon', 'Volt Switch'], evs={'spa': 252, 'spe': 252})],
      best=['switch:Magnezone'], bad=['Shadow Sneak', 'Shadow Claw', 'X-Scissor', 'Swords Dance'],
      checks=[('b07c_status_kos', 'p0', 'Toxic', 'e0'), ('meff', 'p0', 'Scald', 'e0', 0.0), ('meff', 'p0', 'Ice Beam', 'e0', 0.0),
              ('mnoko', 'e0', 'Shadow Sneak', 'p0'), ('mnoko', 'e0', 'Shadow Claw', 'p0'), ('mfaster', 'p0', 'e0'),
              ('acc_lt', 'Toxic', 100), ('type', 'e1', 'Steel'),
              ('b07c_entry_fight', 'e1', 'Thunderbolt', 'p0', '*', '*', 4, 'win')]),

    # --- 7. two-turn plans

    S('b07c_strong_then_priority', 'priority',
      'Hydreigon is faster (118 to 115) and Dragon Pulse (58-69%) KOs Primeape in two hits; Close Combat (2x, 86-102%) may fall '
      'short now, but next turn Mach Punch (priority, 2x, 30-36%) finishes Hydreigon before it moves; Mach Punch first loses, since '
      'two of them cannot KO and Close Combat on turn 2 comes after the second Dragon Pulse; Bulk Up raises only Defense against a '
      'special attacker',
      [mon('Hydreigon', ['Dark Pulse', 'Dragon Pulse', 'Flamethrower', 'Earth Power'])],
      [mon('Primeape', ['Close Combat', 'Mach Punch', 'Stone Edge', 'Bulk Up'])],
      best=['Close Combat'], bad=['Bulk Up'],
      checks=[('b06_faster', 'p0', 'e0'), ('b06_fight', 'e0', ('Close Combat', 'Mach Punch'), 'p0', '*', 2, 'win'),
              ('b06_fight', 'e0', 'Mach Punch', 'p0', 'Dragon Pulse', 4, 'lose'),
              ('b06_fight', 'e0', ('Mach Punch', 'Close Combat'), 'p0', 'Dragon Pulse', 4, 'lose'),
              ('b06_fight', 'e0', ('Bulk Up', 'Mach Punch'), 'p0', 'Dragon Pulse', 4, 'lose'),
              ('b06_fight', 'e0', ('Bulk Up', 'Close Combat'), 'p0', 'Dragon Pulse', 4, 'lose'),
              ('b06_no_nhko', 'e0', 'Mach Punch', 'p0', 2), ('b06_pri', 'e0', 'Mach Punch', 1)]),

    S('b07c_sucker_chip_free_entry', 'priority',
      'Infernape at 40% is faster and Close Combat or Flare Blitz (2x) KOs Shiftry, so Explosion and every other move never fire; '
      'Sucker Punch (priority) goes first against an attack and takes 22-27%, and then Lucario comes in free and its ExtremeSpeed '
      "(+2) KOs the weakened Infernape before it moves; without the chip ExtremeSpeed falls short and Infernape's Close Combat (2x) "
      'KOs Lucario, and Lucario switched in now takes that hit at once',
      [mon('Infernape', ['Flare Blitz', 'Close Combat', 'Stone Edge', 'ThunderPunch'], hp=0.4)],
      [mon('Shiftry', ['Sucker Punch', 'Explosion', 'Leaf Storm', 'Dark Pulse']),
       mon('Lucario', ['ExtremeSpeed', 'Close Combat', 'Flash Cannon'])],
      best=['Sucker Punch'], bad=['Explosion', 'Leaf Storm', 'Dark Pulse'],
      checks=[('mfaster', 'p0', 'e0'), ('mko', 'p0', 'Close Combat', 'e0'), ('mko', 'p0', 'Flare Blitz', 'e0'),
              ('b03_no_priority', 'p0'), ('b03_attacks_only', 'p0'), ('pri', 'Sucker Punch', 1),
              ('mnoko', 'e0', 'Sucker Punch', 'p0'), ('mko', 'e0', 'Explosion', 'p0'), ('pri', 'ExtremeSpeed', 2),
              ('first', 'p0', 'Close Combat', 'e0', 'Explosion'),
              ('b05_wins_after', 'e1', 'ExtremeSpeed', 'p0', '*', 1, [('e0', 'Sucker Punch', 'p0')]),
              ('b05_loses_after', 'e1', '*', 'p0', 'Close Combat', []),
              ('b05_loses_after', 'e1', '*', 'p0', 'Close Combat', [('p0', 'Close Combat', 'e1'), 'eot'])]),

    S('b07c_rain_surer_ko', 'ko',
      "Politoed's Drizzle set rain: Surf (rain-boosted, never misses) now KOs Ursaring at 48%, which it would not do in clear "
      'weather; Hydro Pump (90%) and Focus Blast (2x, 70%) also KO but can miss, and Politoed at 50% then falls to Double-Edge; '
      'Ice Beam does not KO',
      [mon('Ursaring', ['Double-Edge', 'Close Combat', 'Crunch', 'Swords Dance'], hp=0.48)],
      [mon('Politoed', ['Surf', 'Hydro Pump', 'Focus Blast', 'Ice Beam'], ability='Drizzle', hp=0.5)],
      best=['Surf'], ok=['Hydro Pump'], bad=['Ice Beam'],
      checks=[('weather', 'rain'), ('mfaster', 'e0', 'p0'), ('mko', 'e0', 'Surf', 'p0'), ('noko', 'e0', 'Surf', 'p0'),
              ('mko', 'e0', 'Hydro Pump', 'p0'), ('mko', 'e0', 'Focus Blast', 'p0'), ('acc_lt', 'Hydro Pump', 100),
              ('acc_lt', 'Focus Blast', 80), ('mnoko', 'e0', 'Ice Beam', 'p0'), ('mko', 'p0', 'Double-Edge', 'e0')]),

    # --- 8. the replacement after a faint, as a turn-1 switch

    S('b07c_switch_to_mirror_coat', 'switch',
      'Alakazam is faster and Psychic (4x) KOs Toxicroak before it moves; Mantine (HP and Sp. Def trained) takes Psychic for at '
      'most 28% and the next hit too, and Mirror Coat returns twice the damage, a KO; Choice Scarf Gengar outspeeds Alakazam and '
      'Shadow Ball (2x) KOs it, but Psychic (2x) KOs Gengar as it switches in; Hariyama takes Psychic (2x, 79-94%), its Counter '
      'cannot return a special hit, and it falls next turn; letting Toxicroak fall brings Gengar in free to win, at the cost of '
      'Toxicroak',
      [mon('Alakazam', ['Psychic', 'Focus Blast', 'Shadow Ball', 'DazzlngGleam'], hp=0.85)],
      [mon('Toxicroak', ['Drain Punch', 'Poison Jab', 'Ice Punch', 'Swords Dance']),
       mon('Mantine', ['Mirror Coat', 'Scald', 'Air Slash'], evs={'hp': 252, 'spd': 252}),
       mon('Gengar', ['Shadow Ball', 'Sludge Bomb', 'Focus Blast'], item='Choice Scarf', evs={'spa': 252}),
       mon('Hariyama', ['Counter', 'Close Combat', 'Knock Off'])],
      best=['switch:Mantine'], ok=['Drain Punch', 'Poison Jab', 'Ice Punch', 'Swords Dance'], bad=['switch:Gengar', 'switch:Hariyama'],
      checks=[('mfaster', 'p0', 'e0'), ('mko', 'p0', 'Psychic', 'e0'), ('b03_attacks_only', 'p0'),
              ('b07c_entry_fight', 'e1', 'Mirror Coat', 'p0', '*', '*', 8, 'win'),
              ('mfaster', 'e2', 'p0'), ('faster', 'p0', 'e2'), ('mko', 'e2', 'Shadow Ball', 'p0'), ('mko', 'p0', 'Psychic', 'e2'),
              ('race', 'e2', 'Shadow Ball', 'p0', '*', 1),
              ('b07c_entry_fight', 'e3', '*', 'p0', 'Psychic', 'Psychic', 6, 'lose')]),

    S('b07c_free_entry_metal_burst', 'switch',
      'Staraptor is faster and Close Combat (4x) KOs Tyranitar before it moves, so Tyranitar falls whatever it picks; Registeel '
      'survives one Close Combat (2x, 75-90%) and Metal Burst returns one and a half times the damage, a KO, so it wins coming in '
      'free after the faint; switched in now, it takes Close Combat on the way in and the faster Staraptor KOs it with the second '
      'before Metal Burst can fire',
      [mon('Staraptor', ['Brave Bird', 'Close Combat', 'Double-Edge'])],
      [mon('Tyranitar', ['Stone Edge', 'Crunch', 'Earthquake', 'Ice Beam']),
       mon('Registeel', ['Metal Burst', 'Iron Head', 'Curse'])],
      best=['Stone Edge', 'Crunch', 'Earthquake', 'Ice Beam'], bad=['switch:Registeel'],
      checks=[('mfaster', 'p0', 'e0'), ('mko', 'p0', 'Close Combat', 'e0'), ('b03_attacks_only', 'p0'), ('b03_no_priority', 'p0'),
              ('mfaster', 'p0', 'e1'), ('b06_fight', 'e1', 'Metal Burst', 'p0', '*', 6, 'win'),
              ('b07c_entry_fight', 'e1', '*', 'p0', 'Close Combat', 'Close Combat', 6, 'lose'),
              ('b07c_entry_fight', 'e1', 'Metal Burst', 'p0', 'Close Combat', 'Close Combat', 6, 'lose')]),
])
