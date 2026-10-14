"""Batch 04, author C: setup and anti-setup, turn 1.

The positions ask when a boost wins the game and when it only hands the foe a free hit, and how the AI's side answers a
foe that would set up. The ideas: a Defense boost from the faster side that turns a would-be OHKO into a survivable hit
(Bulk Up, Iron Defense), Amnesia against Psyshock (a special move that hits Defense), Swords Dance under Intimidate when the
user's own Close Combat drop loses the straight trade, Swords Dance against Sturdy, Belly Drum whose payoff cannot touch a
Ghost, Quiver Dance behind a Focus Sash, a boost before an available KO because the foe's bench is the threat, Haze on turn 1
(nobody has a stage yet), and Dragon Dance in a double where both foes can aim at the dancer.

The ops below extend tests/ai_checks.py without editing it. They are registered in ai_checks.CHECKS on import (prefix b04c_),
before `with_items` runs, and they build ai_checks.Ctx, so items and abilities the model does not cover are refused as there.

b04c_line and b04c_line_loses play a race (ai_checks.Race, singles) whose first turn may differ from the rest: on turn 1 each
side uses its own first move, from turn 2 on its usual move. A first move is one of:
  - an attack, played as every race turn is (the favored side's minimum x 0.9, the other's maximum x 1.1, Focus Sash, Sturdy,
    Life Orb, recoil, drain, guaranteed stat changes, Sitrus Berry);
  - a self-boosting status move whose stat changes are in its move data (Swords Dance, Dragon Dance, Calm Mind, Nasty Plot,
    Quiver Dance, Bulk Up, Agility, Coil...): the stages apply when it moves, so a Defense or Special Defense boost from a
    faster user already shrinks the hit that comes after it that turn, and every stage counts in the turns after (damage and
    the Speed order). An accuracy raise (Coil) is ignored: the race never misses. Evasion changes are refused. Shell Smash and
    Belly Drum (no stat data, a special effect) are refused;
  - 'idle:Move': a status move that changes nothing in the race this turn (Haze when nobody has a stat stage). Only its
    priority is used, for the order. The position must say why it does nothing.
  - None: the same move as from turn 2 on.
  Sucker Punch also fails against a target whose move this turn is a status move (Gen 5).
"""
import ai_checks
from ai_checks import (CHECKS, Q_TARGET_DROP, Q_USER_STAT, RECHARGE, SELF_KO, STAGE_AMBIGUOUS, STAT_IDS, STATUS,
                       SUCKER, Ctx, Race, _actives, _race_moves, with_items)
from ai_helpers import PLAIN, S, mon  # noqa: F401

ACC, EVA = 6, 7


def _signed(b):
    return b - 256 if b > 127 else b


class LineRace(Race):
    """ai_checks.Race with a first turn of its own for each side (see the module docstring)."""

    def first_kind(self, r, mv):
        """'attack', 'setup' or 'idle' for a first-turn move, after vetting it."""
        x = self.x
        if mv.startswith('idle:'):
            assert x.d.move(mv[5:])['class'] == STATUS, '%s is not a status move: it cannot be idle' % mv[5:]
            return 'idle'
        if x.d.move(mv)['class'] == STATUS:
            self.stage_changes(r, mv)
            return 'setup'
        return 'attack'

    def stage_changes(self, r, mv):
        """(stat, stages) a self-targeting stat move gives its user, from the move data (raises and drops)."""
        x = self.x
        m = x.d.move(mv)
        rec = x.d.moves[m['id']]
        assert m['class'] == STATUS and rec[20] == 7 and rec[1] == 2, '%s is not a self-boosting status move with stat data' % mv
        assert x.ability(r) not in STAGE_AMBIGUOUS, '%s changes what a stat stage does' % x.ability(r)
        out = []
        for k in range(3):
            sid, amt = rec[21 + k], _signed(rec[24 + k])
            if not (sid and amt):
                continue
            assert sid != EVA, '%s changes evasion, which the race does not model' % mv
            if sid == ACC:
                continue
            assert sid in STAT_IDS, '%s changes a stat the race does not model' % mv
            out.append((STAT_IDS[sid], amt))
        assert out, '%s changes no stat the race models' % mv
        return out

    def play_line(self, a, a1, a_rest, b, b1, b_rest, max_turns):
        """The turn (1-based) on which b faints with a still standing, or None."""
        x = self.x
        first = {a: a1, b: b1}
        rest = {a: a_rest, b: b_rest}
        kinds = {}
        for r, t in ((a, b), (b, a)):
            self.vet_move(r, rest[r], t)
            kinds[r] = self.first_kind(r, first[r])
            if kinds[r] == 'attack':
                self.vet_move(r, first[r], t)
        va, vb = x.ref(a), x.ref(b)
        saved = {a: va['cur_hp'], b: vb['cur_hp']}
        hp = dict(saved)
        tox = {r: (2 if r == self.favored else 1) for r in (a, b)}
        recharge = {a: False, b: False}
        x.boosts.clear()
        x.consumed.clear()
        try:
            for turn in range(1, max_turns + 1):
                acted = set()
                chosen = first if turn == 1 else rest
                order_moves = {r: (mv[5:] if mv.startswith('idle:') else mv) for r, mv in chosen.items()}
                for r in self.order(order_moves):
                    t = b if r == a else a
                    if hp[r] <= 0 or hp[t] <= 0:
                        continue
                    if recharge[r]:
                        recharge[r] = False
                        acted.add(r)
                        continue
                    if turn == 1 and kinds[r] != 'attack':
                        if kinds[r] == 'setup':
                            for stat, amt in self.stage_changes(r, first[r]):
                                x.boosts[(r, stat)] = max(-6, min(6, x.boosts.get((r, stat), 0) + amt))
                        acted.add(r)
                        continue
                    mv = chosen[r]
                    m = x.d.move(mv)
                    rr = x.d.moves[m['id']]
                    rec = _signed(rr[18])
                    sure = r == self.favored
                    x.ref(r)['cur_hp'], x.ref(t)['cur_hp'] = hp[r], hp[t]
                    dmg = x.total(r, mv, t, sure) * (0.9 if sure else 1.1)
                    if m['effect'] == SUCKER and (t in acted or x.d.move(order_moves[t])['class'] == STATUS):
                        dmg = 0
                    if dmg and x.endures(r, mv, t):
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
                    if m['effect'] == SELF_KO:
                        hp[r] = 0
                    if m['effect'] == RECHARGE and dealt:
                        recharge[r] = True
                    if rr[1] in (Q_USER_STAT, Q_TARGET_DROP) and dmg:
                        who = r if rr[1] == Q_USER_STAT else t
                        for k in range(3):
                            stat, amt, chance = STAT_IDS.get(rr[21 + k]), _signed(rr[24 + k]), rr[27 + k]
                            if stat and amt and chance == 100:
                                if who == t and amt < 0 and x.ability(t) in ai_checks.DROP_BLOCKERS[stat] and \
                                        x.ability(r) not in ai_checks.MOLD_BREAKER:
                                    continue
                                x.boosts[(who, stat)] = max(-6, min(6, x.boosts.get((who, stat), 0) + amt))
                    for q in (r, t):
                        mxq = x.ref(q)['stats']['hp']
                        if 0 < hp[q] <= mxq // 2 and x.item(q) in ('Sitrus Berry', 'Oran Berry') and q not in x.consumed:
                            hp[q] = min(mxq, hp[q] + (mxq // 4 if x.item(q) == 'Sitrus Berry' else 10))
                            x.consumed.add(q)
                    if hp[t] <= 0 or hp[r] <= 0:
                        break
                if hp[a] > 0 and hp[b] > 0:
                    for r in self.order(order_moves):
                        hp[r] = self.chip(r, hp[r], tox[r])
                        if x.ref(r)['status'] == 'tox':
                            tox[r] += 1
                if hp[b] <= 0 and hp[a] > 0:
                    return turn
                if hp[a] <= 0:
                    return None
            return None
        finally:
            va['cur_hp'], vb['cur_hp'] = saved[a], saved[b]
            x.boosts.clear()
            x.consumed.clear()


def _pairs(x, r, first, rest):
    """(first move, usual move) pairs: '*' as the usual move means each of r's attacks; a first move of None repeats it."""
    out = []
    for mv in _race_moves(x, r, rest):
        if first is None:
            out.append((mv, mv))
        elif first == '*':
            out.extend((f, mv) for f in _race_moves(x, r, '*'))
        else:
            out.append((first, mv))
    return out


def _op(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(Ctx(d, views, c, ref))
        return fn
    return reg


@_op('b04c_line')
def line(x):
    """('b04c_line', a, a1, a_rest, b, b1, b_rest, n): a uses a1 on turn 1 and a_rest from turn 2, b uses b1 on turn 1 and
    b_rest from turn 2 ('*' = each of its attacks; a first move of None repeats the usual one; see the module docstring for
    setup and 'idle:' first moves); a knocks b out by the end of turn n and is still standing. Race rules of ai_checks: a's
    minimum x 0.9, b's maximum x 1.1, both paralysis rules (a quarter, a half) and both burn rules (an eighth, a sixteenth),
    the end-of-turn damage, the stages and the Speed order they give; a speed tie is refused."""
    a, a1, a_rest, b, b1, b_rest, n = x.args
    _actives(x, a, b)
    for fa, ra in _pairs(x, a, a1, a_rest):
        for fb, rb in _pairs(x, b, b1, b_rest):
            for par_div in (4, 2):
                for burn_div in (8, 16):
                    turn = LineRace(x, a, par_div, burn_div).play_line(a, fa, ra, b, fb, rb, n)
                    assert turn is not None, '%s (%s, then %s) does not surely beat %s (%s, then %s) within %d turns (paralysis /%d, burn /%d)' % (
                        x.ref(a)['species'], fa, ra, x.ref(b)['species'], fb, rb, n, par_div, burn_div)


@_op('b04c_line_loses')
def line_loses(x):
    """('b04c_line_loses', a, a1, a_rest, b, b1, b_rest): the same two-phase race, but b is the favored side and knocks a out
    first, within 12 turns: b's minimum x 0.9, a's maximum x 1.1, both paralysis and both burn rules. Every listed line of a
    is tried ('*' = each of its attacks), and every listed line of b must win against it (name one line of b to show that a's
    plan fails, since the player answers with its best move)."""
    a, a1, a_rest, b, b1, b_rest = x.args
    _actives(x, a, b)
    for fa, ra in _pairs(x, a, a1, a_rest):
        for fb, rb in _pairs(x, b, b1, b_rest):
            for par_div in (4, 2):
                for burn_div in (8, 16):
                    turn = LineRace(x, b, par_div, burn_div).play_line(b, fb, rb, a, fa, ra, 12)
                    assert turn is not None, '%s (%s, then %s) is not surely beaten by %s (%s, then %s) (paralysis /%d, burn /%d)' % (
                        x.ref(a)['species'], fa, ra, x.ref(b)['species'], fb, rb, par_div, burn_div)


@_op('b04c_focus_ko')
def focus_ko(x):
    """('b04c_focus_ko', df, a1, mv1, a2, mv2): in a double, two single-target attacks from the two foes aimed at df knock it
    out together on the same turn: the sum of their minimums (minimum hits) x 0.9 is at least df's current HP. Refused when
    df holds a Focus Sash or has Sturdy (the first hit could leave it at 1 HP), or when a move is not single-target."""
    df, a1, mv1, a2, mv2 = x.args
    assert x.double, 'b04c_focus_ko is a doubles claim'
    assert a1 != a2 and a1[0] == a2[0] != df[0], 'two attackers of the side opposite %s' % df
    assert x.item(df) != 'Focus Sash' and x.ability(df) != 'Sturdy', '%s could hang on at 1 HP' % x.ref(df)['species']
    total = 0
    for a, mv in ((a1, mv1), (a2, mv2)):
        assert x.d.move(mv)['target'] == 0, '%s is not a single-target move' % mv
        total += x.total(a, mv, df, True)
    hp = x.ref(df)['cur_hp']
    assert total * 0.9 >= hp, '%s and %s do at least %d together: not a sure KO on %s at %d HP' % (mv1, mv2, total, x.ref(df)['species'], hp)


SCENARIOS = with_items([
    S('b04c_bulk_up_before_eq', 'setup',
      "Excadrill's Earthquake (2x) takes 111-133% of Toxicroak's HP, so attacking at once loses it (Drain Punch, 2x, does 76-91% and "
      "cannot KO); but Toxicroak is faster, so Bulk Up raises its Defense before the Earthquake lands, which then cannot KO, and the "
      "+1 Drain Punch KOs next turn while healing; Swords Dance boosts only the Attack and dies to the same Earthquake, and Poison "
      "Jab cannot touch a Steel type",
      [mon('Excadrill', ['Earthquake', 'Iron Head', 'Rock Slide'])],
      [mon('Toxicroak', ['Bulk Up', 'Swords Dance', 'Drain Punch', 'Poison Jab'])],
      best=['Bulk Up'], bad=['Swords Dance', 'Poison Jab'],
      checks=[('mfaster', 'e0', 'p0'), ('mko', 'p0', 'Earthquake', 'e0'), ('mnoko', 'e0', 'Drain Punch', 'p0'),
              ('eff', 'e0', 'Poison Jab', 'p0', 0.0),
              ('b04c_line', 'e0', 'Bulk Up', 'Drain Punch', 'p0', '*', '*', 2),
              ('b04c_line_loses', 'e0', None, '*', 'p0', None, 'Earthquake'),
              ('b04c_line_loses', 'e0', 'Swords Dance', 'Drain Punch', 'p0', None, 'Earthquake')]),
    S('b04c_amnesia_psyshock', 'setup',
      "Amnesia looks like the answer to a special attacker, but Psyshock is special and hits Snorlax's Defense, which Amnesia does not "
      "raise: Espeon is faster and Psyshock takes 34-41% a hit, so Snorlax (215 HP) survives two and its second Crunch (2x, 63-74%) "
      "KOs first; spending turn 1 on Amnesia gives Espeon the third Psyshock; against Psychic alone Amnesia would have worked",
      [mon('Espeon', ['Psyshock', 'Psychic', 'Shadow Ball', 'DazzlngGleam'])],
      [mon('Snorlax', ['Amnesia', 'Body Slam', 'Crunch', 'Earthquake'], hp=215)],
      best=['Crunch'], bad=['Amnesia'],
      checks=[('mfaster', 'p0', 'e0'), ('cls', 'Psyshock', 'special'), ('eff', 'e0', 'Crunch', 'p0', 2.0),
              ('b04c_line', 'e0', None, 'Crunch', 'p0', '*', '*', 2),
              ('b04c_line_loses', 'e0', 'Amnesia', '*', 'p0', None, 'Psyshock'),
              ('b04c_line', 'e0', 'Amnesia', 'Crunch', 'p0', None, 'Psychic', 3)]),
    S('b04c_intimidate_sd_cc', 'setup',
      "Krookodile's Intimidate cut Zangoose's Attack: Close Combat (2x) now does 72-86% and does not KO, and it lowers Zangoose's own "
      "Defense, so the Earthquake that follows (65-77% at +0) KOs Zangoose at 85%; Zangoose is faster, so Swords Dance comes first, the "
      "Earthquake cannot KO at +0 Defense, and the +1 Close Combat KOs next turn; Night Slash is resisted",
      [mon('Krookodile', ['Earthquake', 'Crunch', 'Stone Edge'], ability='Intimidate')],
      [mon('Zangoose', ['Swords Dance', 'Double-Edge', 'Close Combat', 'Night Slash'], hp=0.85)],
      best=['Swords Dance'], bad=['Night Slash'],
      checks=[('has_ability', 'p0', 'Intimidate'), ('mfaster', 'e0', 'p0'), ('mnoko', 'e0', 'Close Combat', 'p0'),
              ('mnoko', 'p0', 'Earthquake', 'e0'),
              ('b04c_line', 'e0', 'Swords Dance', 'Close Combat', 'p0', '*', '*', 2),
              ('b04c_line_loses', 'e0', None, '*', 'p0', None, 'Earthquake')]),
    S('b04c_sturdy_no_sd', 'setup',
      "Sturdy Sudowoodo at full HP keeps 1 HP against any single hit, so even a +2 Waterfall leaves it standing and Kingler needs two "
      "hits whatever it does; Kingler is faster, Waterfall or Iron Head (2x, 57-67%) now and again next turn wins with one Earthquake "
      "taken (54-63%), while Swords Dance hands Sudowoodo a second Earthquake, which KOs Kingler at 85%",
      [mon('Sudowoodo', ['Head Smash', 'Wood Hammer', 'Earthquake'], ability='Sturdy')],
      [mon('Kingler', ['Swords Dance', 'Waterfall', 'Iron Head', 'X-Scissor'], hp=0.85)],
      best=['Waterfall', 'Iron Head'], bad=['Swords Dance'],
      checks=[('endures', 'p0', 'e0', 'Waterfall'), ('mfaster', 'e0', 'p0'), ('mnoko', 'p0', 'Earthquake', 'e0'),
              ('b04c_line', 'e0', None, 'Waterfall', 'p0', '*', '*', 2),
              ('b04c_line', 'e0', None, 'Iron Head', 'p0', '*', '*', 2),
              ('b04c_line_loses', 'e0', 'Swords Dance', '*', 'p0', None, 'Earthquake')]),
    S('b04c_haze_turn_one', 'setup',
      "Tyranitar has Dragon Dance, but it is turn 1 and nobody has a stat stage yet; Vaporeon is faster, so Haze would clear nothing "
      "and waste the turn; Scald (2x, 55-65%) twice KOs Tyranitar at 85% whether it attacks or dances (a +1 Crunch takes at most 45% "
      "x 1.5), while after a wasted turn the +1 Tyranitar is faster and two boosted Crunches KO Vaporeon first",
      [mon('Tyranitar', ['Dragon Dance', 'Crunch', 'Earthquake', 'Iron Head'], hp=0.85)],
      [mon('Vaporeon', ['Haze', 'Scald', 'Ice Beam', 'Shadow Ball'])],
      best=['Scald'], bad=['Haze'],
      checks=[('mfaster', 'e0', 'p0'), ('cls', 'Haze', 'status'), ('mnoko', 'e0', 'Scald', 'p0'),
              ('b04c_line', 'e0', None, 'Scald', 'p0', None, '*', 2),
              ('b04c_line', 'e0', None, 'Scald', 'p0', 'Dragon Dance', '*', 2),
              ('b04c_line_loses', 'e0', 'idle:Haze', '*', 'p0', 'Dragon Dance', 'Crunch')]),
    S('b04c_belly_drum_ghost', 'setup',
      "Belly Drum's payoff moves are ExtremeSpeed and Body Slam, and neither can touch Golurk, a Ghost type; the drum would also cost "
      "half of Linoone's HP, and Golurk's Earthquake (57-68%) KOs it from half while it cannot from full; Linoone is faster and Seed "
      "Bomb (2x) twice KOs Golurk at 70% with only one Earthquake taken",
      [mon('Golurk', ['Earthquake', 'Shadow Claw', 'Ice Punch'], hp=0.7)],
      [mon('Linoone', ['Belly Drum', 'ExtremeSpeed', 'Body Slam', 'Seed Bomb'])],
      best=['Seed Bomb'], bad=['ExtremeSpeed', 'Body Slam'],
      checks=[('eff', 'e0', 'ExtremeSpeed', 'p0', 0.0), ('eff', 'e0', 'Body Slam', 'p0', 0.0), ('mfaster', 'e0', 'p0'),
              ('mnoko', 'p0', 'Earthquake', 'e0'), ('mko_at', 'p0', 'Earthquake', 'e0', 0.5),
              ('b04c_line', 'e0', None, 'Seed Bomb', 'p0', '*', '*', 2)]),
    S('b04c_iron_defense_cc', 'setup',
      "Close Combat is 2x both ways and Cobalion is faster, but Cobalion's own Close Combat (76-90%) does not KO and lowers its Defense, "
      "so Hariyama's reply KOs it; Iron Defense first doubles Cobalion's Defense before Hariyama moves, its Close Combat then takes at "
      "most half (40-48%), and Cobalion wins the exchange: if Hariyama used Close Combat, its own Defense drop lets Cobalion's Close "
      "Combat KO next turn, and its other moves are resisted; Stone Edge is resisted",
      [mon('Hariyama', ['Close Combat', 'Knock Off', 'Ice Punch'])],
      [mon('Cobalion', ['Iron Defense', 'Close Combat', 'Iron Head', 'Stone Edge'])],
      best=['Iron Defense'], bad=['Stone Edge'],
      checks=[('mfaster', 'e0', 'p0'), ('mnoko', 'e0', 'Close Combat', 'p0'), ('eff', 'e0', 'Stone Edge', 'p0', 0.5),
              ('b04c_line', 'e0', 'Iron Defense', 'Close Combat', 'p0', '*', '*', 4),
              ('b04c_line_loses', 'e0', None, '*', 'p0', None, 'Close Combat')]),
    S('b04c_sash_quiver_dance', 'setup',
      "Garchomp (100 HP) is barely faster than Volcarona (122 to 120): Stone Edge (4x) would KO but the Focus Sash keeps Volcarona at "
      "1 HP, and its Outrage takes at most 76%; a Bug Buzz now (76-90 damage) does not KO and Garchomp then moves first again; Quiver Dance "
      "makes Volcarona the faster one and the +1 Bug Buzz KOs next turn, whatever Garchomp used",
      [mon('Garchomp', ['Stone Edge', 'Earthquake', 'Outrage', 'Fire Fang'], hp=100)],
      [mon('Volcarona', ['Quiver Dance', 'Bug Buzz', 'Fiery Dance', 'Giga Drain'], item='Focus Sash')],
      best=['Quiver Dance'],
      checks=[('mfaster', 'p0', 'e0'), ('endures', 'e0', 'p0', 'Stone Edge'), ('has_item', 'e0', 'Focus Sash'),
              ('mnoko', 'e0', 'Bug Buzz', 'p0'),
              ('b04c_line', 'e0', 'Quiver Dance', 'Bug Buzz', 'p0', '*', '*', 2),
              ('b04c_line_loses', 'e0', None, 'Bug Buzz', 'p0', None, 'Outrage'),
              ('b04c_line_loses', 'e0', None, 'Fiery Dance', 'p0', None, 'Outrage')]),
    S('b04c_dbl_focus_fire', 'doubles',
      "Neither foe alone can KO Salamence (148 HP), but Double-Edge and Body Slam together do; Salamence is the fastest Pokemon out "
      "and Dragon Claw KOs either foe (Kangaskhan at 35%, Ursaring at 40%), after which the other cannot finish it; Dragon Dance would "
      "only take both hits, and Earthquake (a spread move, also hitting partner Blissey) KOs neither",
      [mon('Kangaskhan', ['Double-Edge', 'Crunch', 'Earthquake'], hp=0.35), mon('Ursaring', ['Body Slam', 'Crunch', 'Close Combat'], hp=0.4)],
      [mon('Salamence', ['Dragon Dance', 'Dragon Claw', 'Earthquake', 'Fire Fang'], hp=148),
       mon('Blissey', ['Soft-Boiled', 'Protect', 'Wish', 'Heal Bell'])],
      best=['Dragon Claw>Kangaskhan', 'Dragon Claw>Ursaring'], bad=['Dragon Dance', 'Earthquake'], double=True,
      checks=[('b04c_focus_ko', 'e0', 'p0', 'Double-Edge', 'p1', 'Body Slam'),
              ('mnoko', 'p0', 'Double-Edge', 'e0'), ('mnoko', 'p0', 'Crunch', 'e0'), ('meff', 'p0', 'Earthquake', 'e0', 0.0),
              ('mnoko', 'p1', 'Body Slam', 'e0'), ('mnoko', 'p1', 'Crunch', 'e0'), ('mnoko', 'p1', 'Close Combat', 'e0'),
              ('mfaster', 'e0', 'p0'), ('mfaster', 'e0', 'p1'),
              ('mko', 'e0', 'Dragon Claw', 'p0'), ('mko', 'e0', 'Dragon Claw', 'p1'),
              ('mnoko', 'e0', 'Earthquake', 'p0'), ('mnoko', 'e0', 'Earthquake', 'p1')]),
    S('b04c_boost_before_ko', 'setup',
      "Electrode (90%) has only Electric moves and cannot touch Gliscor; Earthquake would KO it now, but then Swampert comes in, and at +0 "
      "Gliscor loses to it (Ice Punch, 4x, 70-83%, against Earthquake 36-43%); Electrode is a free turn: after Swords Dance Gliscor "
      "beats Swampert (two +2 Earthquakes before two Ice Punches), whether it comes in now or after Electrode falls",
      [mon('Electrode', ['Thunderbolt', 'Volt Switch', 'Discharge', 'Charge Beam'], hp=0.9), mon('Swampert', ['Waterfall', 'Earthquake', 'Ice Punch'])],
      [mon('Gliscor', ['Swords Dance', 'Earthquake', 'Ice Fang', 'Night Slash'])],
      best=['Swords Dance'], ok=['Earthquake'],
      checks=[('eff', 'p0', 'Thunderbolt', 'e0', 0.0), ('eff', 'p0', 'Volt Switch', 'e0', 0.0), ('eff', 'p0', 'Discharge', 'e0', 0.0),
              ('eff', 'p0', 'Charge Beam', 'e0', 0.0), ('mko', 'e0', 'Earthquake', 'p0'),
              ('boosted_race', 'e0', 'Swords Dance', 'Earthquake', 'p1', '*', 4),
              ('loses', 'e0', '*', 'p1', 'Ice Punch')]),
])
