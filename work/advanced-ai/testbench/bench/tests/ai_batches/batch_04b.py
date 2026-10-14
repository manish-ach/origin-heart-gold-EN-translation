"""Batch 04, author B: the trainer's bag items (heal now or attack, cure a status or play through it, X items).

Every claim that rests on what a bag item does goes through the ops below, which extend tests/ai_checks.py without editing
it (each is registered in ai_checks.CHECKS on import, prefix b04b_, and runs on ai_checks.Ctx, so held items and abilities
are modeled or refused exactly as there).

The item model (Gen 5 trainer item use, on the hack's item data `a/0/1/7`, read from the ROM):
  Order: a trainer's item is used before any move of the turn, whatever the move's priority (every generation).
  Healing: the party-use HP parameter (byte 0x1B, 255 = full HP) when the HP flag (byte 0x13 bit 2) is set. The amount
      changed between generations for two items, and this ROM has not been measured: Hyper Potion 200 (data, Gen 1-6) or
      120 (Gen 7+), Super Potion 50 or 60. Every op tries each reading and the claim must hold for all of them. Other
      healing items with a partial amount (berries, drinks, Revive) are refused.
  Status cures: byte 0x0E bits 0-4 (sleep, poison and bad poison, burn, freeze, paralysis). Full Restore heals and cures.
  X items: the stage nibbles (Attack byte 0x0F high, Defense 0x10 low, Sp. Atk 0x10 high, Sp. Def 0x11 low, Speed 0x11
      high). The data gives +1 (Gen 3-6); Gen 7+ gives +2. Both readings are tried. X Accuracy, Dire Hit and Guard Spec.
      are refused.
  Turn 1 of an item race: the item applies, then the foe's move hits the Pokemon as the item left it (an X Defense boost
      counts). The foe's move must be a plain hit for that turn: no drain, self-KO, recharge or guaranteed stat change, no
      Shell Bell on the foe, no Focus Sash, Sturdy or HP berry on the item's target. The foe's own losses on turn 1 (recoil,
      Life Orb, lowering its own stats as Close Combat does) are left out, which only weakens a claim that the item user
      wins, so they are allowed there and refused when the foe is the favored side. Sucker Punch fails against a trainer
      who uses an item (the target is not attacking), so it deals nothing on turn 1. The end of turn 1 follows
      ai_checks.Race.chip (status as the item left it). From turn 2 the race of ai_checks plays on, with the X item's boost
      in force. Bad poison, sleep or freeze left on the favored side after the item is refused (the counter would be past the
      race's start; the race would let a sleeping or frozen Pokemon act).

The scenarios: heal or not when the healed HP still falls (a 4x hit, Choice Specs, two foes in a double), when the potion
is too small, when only Full Restore also cures the paralysis that makes the Pokemon slower, when a priority move beats a
faster Pokemon; cure a status or play through it (bad poison in a long trade, a burn that still leaves a KO, sleep with
Sleep Talk); X items against a priority move.
"""
import ai_checks
from ai_checks import CHECKS, Ctx, Race, STATUS, _actives, _race_moves, with_items
from ai_helpers import PLAIN, S, mon  # noqa: F401

HP_FLAG_BYTE, HP_FLAG, HP_PARAM, CURE_BYTE = 0x13, 0x04, 0x1B, 0x0E
CURE_BITS = {'slp': 1, 'psn': 2, 'tox': 2, 'brn': 4, 'frz': 8, 'par': 16}
STAGE_NIBBLES = {'atk': (0x0F, 4), 'def': (0x10, 0), 'spa': (0x10, 4), 'spd': (0x11, 0), 'spe': (0x11, 4)}
# Gen 7+ values next to the data's (Gen 1-6) for the healing items whose amount changed.
ALT_HEAL = {'Hyper Potion': 120, 'Super Potion': 60}
KNOWN_HEAL = {'Potion', 'Super Potion', 'Hyper Potion', 'Max Potion', 'Full Restore'}
REFUSED_ITEMS = {'X Accuracy', 'Dire Hit', 'Guard Spec.'}
SUCKER, SELF_KO, RECHARGE = 248, 7, 80
SLEEP_TALK = 97
HP_BERRIES = {'Sitrus Berry', 'Oran Berry'}


def _item_row(x, item):
    x.hold_effect('Potion')            # loads the item NARC into x.d._items
    return x.d._items[x.d.id('item', item)]


def item_readings(x, item):
    """[(heal, cures, boosts)] for every reading of the item (see the module docstring): heal in HP or 'full' or 0, cures a set
    of statuses, boosts {stat: stages}."""
    assert item not in REFUSED_ITEMS, '%s is not modeled' % item
    r = _item_row(x, item)
    cures = {st for st, bit in CURE_BITS.items() if r[CURE_BYTE] & bit}
    heals = [0]
    if r[HP_FLAG_BYTE] & HP_FLAG:
        assert item in KNOWN_HEAL, '%s heals an amount these ops do not model' % item
        p = r[HP_PARAM]
        heals = ['full'] if p == 255 else sorted({p, ALT_HEAL.get(item, p)})
    stages = {st: (r[b] >> sh) & 15 for st, (b, sh) in STAGE_NIBBLES.items() if (r[b] >> sh) & 15}
    boosts = [{}] if not stages else [{st: n for st in stages} for n in sorted({min(stages.values()), 2})]
    assert heals != [0] or cures or stages, '%s does nothing these ops model' % item
    return [(h, cures, b) for h in heals for b in boosts]


def _after_item(x, a, reading):
    """(hp, status) of a once the item reading has applied."""
    heal, cures, _ = reading
    v = x.ref(a)
    mx = v['stats']['hp']
    hp = mx if heal == 'full' else min(mx, v['cur_hp'] + heal)
    st = None if v['status'] in cures else v['status']
    return hp, st


def _set(x, changes):
    saved = {r: (x.ref(r)['cur_hp'], x.ref(r)['status']) for r in changes}
    for r, (hp, st) in changes.items():
        x.ref(r)['cur_hp'], x.ref(r)['status'] = hp, st
    return saved


def _vet_turn_one(x, a, b, mb, favored):
    """b's turn-1 move against a, which used an item: a plain hit (module docstring). b's own losses (recoil, Life Orb) are
    left out of turn 1, which only weakens a claim that a wins, so they are allowed there and refused when b is favored; so is
    b lowering its own stats (Close Combat, Superpower), which is not carried into the turns after."""
    m = x.d.move(mb)
    Race(x, a, 4, 8).vet_move(b, mb, a)
    assert m['recoil'] <= 0, '%s drains: turn 1 is not modeled' % mb
    assert m['recoil'] == 0 or favored == a, '%s has recoil: turn 1 is not modeled when %s is favored' % (mb, x.ref(b)['species'])
    assert x.item(b) != 'Life Orb' or favored == a, 'Life Orb on %s: turn 1 is not modeled when it is favored' % x.ref(b)['species']
    sure = [(stat, amt) for stat, amt, ch in m['stat_changes'] if ch == 100]
    own_drops = m['quality'] == ai_checks.Q_USER_STAT and all(amt < 0 for _, amt in sure)
    assert not sure or (own_drops and favored == a), (
        '%s changes a stat for sure: turn 1 is not modeled (only the foe lowering its own stats, when %s is favored)' % (
            mb, x.ref(a)['species']))
    assert m['effect'] not in (SELF_KO, RECHARGE), '%s: turn 1 is not modeled' % mb
    assert x.item(b) != 'Shell Bell', '%s holds a Shell Bell: turn 1 is not modeled' % x.ref(b)['species']
    assert x.item(a) != 'Focus Sash' and x.ability(a) != 'Sturdy' and x.item(a) not in HP_BERRIES, (
        '%s holds on or heals by itself: turn 1 is not modeled' % x.ref(a)['species'])


def _turn_one_hit(x, a, b, mb, boosts, sure_for_b):
    """b's damage to a on turn 1 after the item (b's minimum x 0.9 when b is favored, else its maximum x 1.1)."""
    if x.d.move(mb)['effect'] == SUCKER:
        return 0
    x.boosts.clear()
    x.boosts.update({(a, st): n for st, n in boosts.items()})
    try:
        return int(x.total(b, mb, a, sure_for_b) * (0.9 if sure_for_b else 1.1))
    finally:
        x.boosts.clear()


def _ctx(d, views, c, ref):
    x = Ctx(d, views, c, ref)
    x.extra = c[-1]
    return x


def _op(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(_ctx(d, views, c, ref))
        return fn
    return reg


def with_sleep(scenarios):
    """Add the sleep turns left of every sleeping Pokemon (aibench.mon_view does not carry them) to the context with_items
    appended, as {ref: turns} under 'sleep' (the bench's default is 3)."""
    for sc in scenarios:
        sleep = {}
        for side, pre in (('enemy', 'e'), ('player', 'p')):
            for i, m in enumerate(sc[side]):
                if m.get('status') == 'slp':
                    sleep[pre + str(i)] = m.get('sleep', 3)
        for c in sc['checks']:
            if isinstance(c[-1], dict) and 'items' in c[-1]:
                c[-1]['sleep'] = sleep
    return scenarios


@_op('b04b_item_effect')
def item_effect(x):
    """('b04b_item_effect', item, kind, value): what the ROM's item data says the item does when a trainer uses it:
    kind 'heal' (value: HP, or 'full'), 'cures' (value: a status), 'stage' (value: (stat, stages)), 'nothing_for' (value: a
    stat the item does not raise). A readable claim next to the key it explains; the ops read the same data."""
    item, kind, value = x.args
    r = _item_row(x, item)
    if kind == 'heal':
        assert r[HP_FLAG_BYTE] & HP_FLAG, '%s heals nothing' % item
        got = 'full' if r[HP_PARAM] == 255 else r[HP_PARAM]
        assert got == value, '%s heals %s, claimed %s' % (item, got, value)
    elif kind == 'cures':
        assert r[CURE_BYTE] & CURE_BITS[value], '%s does not cure %s' % (item, value)
    elif kind == 'stage':
        st, n = value
        b, sh = STAGE_NIBBLES[st]
        assert (r[b] >> sh) & 15 == n, '%s raises %s by %d, claimed %d' % (item, st, (r[b] >> sh) & 15, n)
    elif kind == 'nothing_for':
        b, sh = STAGE_NIBBLES[value]
        assert not (r[b] >> sh) & 15, '%s raises %s' % (item, value)
    else:
        raise AssertionError('unknown kind %r' % kind)


@_op('b04b_heal_still_ko')
def heal_still_ko(x):
    """('b04b_heal_still_ko', a, item, b, mv): the item is used on a first, and b's mv then surely knocks a out anyway: b's
    minimum x 0.9 is at least a's HP after the largest heal any reading gives (Hyper Potion 200), and a cannot hang on
    (Focus Sash, Sturdy at full HP). Sucker Punch is refused (it fails against an item user)."""
    a, item, b, mv = x.args
    assert x.d.move(mv)['effect'] != SUCKER, 'Sucker Punch fails against a trainer who uses an item'
    for reading in item_readings(x, item):
        hp, st = _after_item(x, a, reading)
        saved = _set(x, {a: (hp, st)})
        try:
            assert not x.endures(b, mv, a), '%s hangs on at 1 HP' % x.ref(a)['species']
            dmg = _turn_one_hit(x, a, b, mv, reading[2], True)
            assert dmg >= hp, '%s healed to %d HP by %s survives %s (at least %d)' % (x.ref(a)['species'], hp, item, mv, dmg)
        finally:
            _set(x, saved)


@_op('b04b_heal_survives')
def heal_survives(x):
    """('b04b_heal_survives', a, item, b, mv): the item is used on a first, and b's mv cannot knock a out this turn: b's
    maximum x 1.1 stays under a's HP after the smallest heal any reading gives (Hyper Potion 120)."""
    a, item, b, mv = x.args
    for reading in item_readings(x, item):
        hp, st = _after_item(x, a, reading)
        saved = _set(x, {a: (hp, st)})
        try:
            dmg = _turn_one_hit(x, a, b, mv, reading[2], False)
            assert dmg < hp, '%s healed to %d HP by %s can fall to %s (up to %d)' % (x.ref(a)['species'], hp, item, mv, dmg)
        finally:
            _set(x, saved)


def _item_turn(x, a, item, b, mb, favored, reading, race):
    """Turn 1: the item on a, b's hit, the end of the turn. Returns (a_hp, a_status, b_hp)."""
    _vet_turn_one(x, a, b, mb, favored)
    hp, st = _after_item(x, a, reading)
    fav_status = st if favored == a else x.ref(b)['status']
    assert fav_status != 'tox', 'bad poison on the favored side after the item: its counter is not modeled'
    assert fav_status not in ('slp', 'frz'), 'the favored side is asleep or frozen after the item: the race would let it act'
    saved = _set(x, {a: (hp, st)})
    try:
        hp -= _turn_one_hit(x, a, b, mb, reading[2], favored == b)
        if hp <= 0:
            return hp, st, x.ref(b)['cur_hp']
        hp = race.chip(a, hp, 2 if favored == a else 1)
        b_hp = race.chip(b, x.ref(b)['cur_hp'], 2 if favored == b else 1)
        return hp, st, b_hp
    finally:
        _set(x, saved)


@_op('b04b_item_race')
def item_race(x):
    """('b04b_item_race', a, item, mv_a, b, mv_b, n): a's trainer uses the item on turn 1 (before any move) while b hits a with
    mv_b ('*' = each of b's attacks; b's maximum x 1.1), then a attacks with mv_a every turn: a survives and knocks b out by
    the end of turn n, under every reading of the item and the race rules of tests/ai_checks.py (a's minimum x 0.9, both
    paralysis and both burn rules, the end-of-turn damage, an X item's boost in force from turn 2)."""
    a, item, mv_a, b, mv_b, n = x.args
    _actives(x, a, b)
    for reading in item_readings(x, item):
        for mb in _race_moves(x, b, mv_b):
            for par_div in (4, 2):
                for burn_div in (8, 16):
                    race = Race(x, a, par_div, burn_div)
                    a_hp, a_st, b_hp = _item_turn(x, a, item, b, mb, a, reading, race)
                    what = '%s after %s (%s) vs %s\'s %s (par /%d, burn /%d)' % (
                        x.ref(a)['species'], item, reading, x.ref(b)['species'], mb, par_div, burn_div)
                    assert a_hp > 0, '%s: falls on turn 1' % what
                    if b_hp <= 0:
                        continue
                    saved = _set(x, {a: (a_hp, a_st), b: (b_hp, x.ref(b)['status'])})
                    try:
                        boosts = {(a, st): k for st, k in reading[2].items()}
                        turn = race.play(a, mv_a, b, mb, n - 1, start_boosts=boosts)
                    finally:
                        _set(x, saved)
                    assert turn is not None, '%s: %s does not surely win within %d turns' % (what, mv_a, n)


@_op('b04b_item_loses')
def item_loses(x):
    """('b04b_item_loses', a, item, mv_a, b, mv_b): a's trainer uses the item on turn 1 while b hits a with mv_b (b's minimum
    x 0.9), and from turn 2 a, using mv_a every turn ('*' = each of its attacks), is still knocked out by b before it can
    knock b out (within 12 turns), under every reading of the item and the race rules with b favored."""
    a, item, mv_a, b, mv_b = x.args
    _actives(x, a, b)
    for reading in item_readings(x, item):
        for ma in _race_moves(x, a, mv_a):
            for par_div in (4, 2):
                for burn_div in (8, 16):
                    race = Race(x, b, par_div, burn_div)
                    a_hp, a_st, b_hp = _item_turn(x, a, item, b, mv_b, b, reading, race)
                    what = '%s after %s (%s) vs %s\'s %s, using %s (par /%d, burn /%d)' % (
                        x.ref(a)['species'], item, reading, x.ref(b)['species'], mv_b, ma, par_div, burn_div)
                    if a_hp <= 0:
                        continue
                    assert b_hp > 0, '%s: %s falls at the end of turn 1' % (what, x.ref(b)['species'])
                    saved = _set(x, {a: (a_hp, a_st), b: (b_hp, x.ref(b)['status'])})
                    try:
                        boosts = {(a, st): k for st, k in reading[2].items()}
                        turn = race.play(b, mv_b, a, ma, 12, start_boosts=boosts)
                    finally:
                        _set(x, saved)
                    assert turn is not None, '%s: not surely beaten' % what


@_op('b04b_entry_loses')
def entry_loses(x):
    """('b04b_entry_loses', b, p, mv_p, mv_b): the bench member b switches in and takes p's mv_p (p's minimum x 0.9; the
    switch comes before any move), then loses the fight from there: from turn 2 p, using mv_p every turn, knocks b out before
    b ('*' = each of its attacks) knocks p out, under the race rules with p favored (both paralysis and both burn rules, the
    end-of-turn damage). b must have no entry ability, so the field stays as it is."""
    b, p, mv_p, mv_b = x.args
    _actives(x, b, p)
    assert b[1:] != '0', '%s is not a bench member' % b
    _vet_turn_one(x, b, p, mv_p, p)
    assert x.ref(p)['status'] not in ('slp', 'frz', 'tox'), '%s is asleep, frozen or badly poisoned: not modeled' % x.ref(p)['species']
    for mb in _race_moves(x, b, mv_b):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                race = Race(x, p, par_div, burn_div)
                hit = int(x.total(p, mv_p, b, True) * 0.9) if x.d.move(mv_p)['effect'] != SUCKER else 0
                left = x.ref(b)['cur_hp'] - hit
                if left <= 0:
                    continue
                left = race.chip(b, left, 1)
                p_hp = race.chip(p, x.ref(p)['cur_hp'], 2)
                if left <= 0:
                    continue
                assert p_hp > 0, '%s falls at the end of the switch turn' % x.ref(p)['species']
                saved = _set(x, {b: (left, x.ref(b)['status']), p: (p_hp, x.ref(p)['status'])})
                try:
                    turn = race.play(p, mv_p, b, mb, 12)
                finally:
                    _set(x, saved)
                assert turn is not None, '%s switching in (%d HP left after %s) is not surely beaten by %s using %s (its %s; par /%d, burn /%d)' % (
                    x.ref(b)['species'], left, mv_p, x.ref(p)['species'], mv_p, mb, par_div, burn_div)


@_op('b04b_hit_then_chip_kos')
def hit_then_chip_kos(x):
    """('b04b_hit_then_chip_kos', a, mv, df): a's mv (minimum x 0.9) and then df's own end-of-turn damage at its least (poison
    an eighth, bad poison at its first tick, burn a sixteenth, sandstorm or hail, less Leftovers and healing abilities, as
    ai_checks.Race.chip computes it) surely knock df out this turn, whether or not a is still standing by then. That a moves
    before df is a separate claim (mfaster)."""
    a, mv, df = x.args
    v = x.ref(df)
    hit = int(x.total(a, mv, df, True) * 0.9)
    assert not x.endures(a, mv, df), '%s hangs on at 1 HP' % v['species']
    left = v['cur_hp'] - hit
    if left <= 0:
        return
    least = max(Race(x, df, 4, 16).chip(df, left, 1), Race(x, df, 4, 8).chip(df, left, 1))
    assert least <= 0, '%s at %d HP keeps %d after %s (at least %d) and the end of the turn' % (v['species'], v['cur_hp'], least, mv, hit)


@_op('b04b_sleep_talk_kos')
def sleep_talk_kos(x):
    """('b04b_sleep_talk_kos', a, b): a is asleep with at least 2 turns left, so it stays asleep this turn, and has Sleep Talk,
    which uses one of a's other moves at random: every other move is a one-turn attack that surely knocks b out (minimum x 0.9
    >= HP, no Focus Sash or Sturdy hold), so whichever is drawn, Sleep Talk knocks b out."""
    a, b = x.args
    v = x.ref(a)
    assert v['status'] == 'slp', '%s is not asleep' % v['species']
    assert x.extra.get('sleep', {}).get(a, 0) >= 2, '%s may wake up this turn' % v['species']
    ids = [x.d.move(mv)['effect'] for mv in v['moves']]
    assert SLEEP_TALK in ids, '%s has no Sleep Talk' % v['species']
    others = [mv for mv in v['moves'] if x.d.move(mv)['effect'] != SLEEP_TALK]
    assert others, 'Sleep Talk has nothing to call'
    for mv in others:
        m = x.d.move(mv)
        assert m['class'] != STATUS, '%s is a status move' % mv
        Race(x, a, 4, 8).vet_move(a, mv, b)
        lo = x.total(a, mv, b, True)
        assert not x.endures(a, mv, b), '%s hangs on against %s' % (x.ref(b)['species'], mv)
        assert lo * 0.9 >= x.ref(b)['cur_hp'], '%s does %d at least: not a sure KO on %s at %d HP' % (mv, lo, x.ref(b)['species'], x.ref(b)['cur_hp'])


@_op('b04b_pair_ko')
def pair_ko(x):
    """('b04b_pair_ko', df, item, a1, mv1, a2, mv2): a double; df's trainer uses the item on it first (None: no item), then the
    two foes' moves together surely knock it out: a1's and a2's minimum damage (doubles spread reduction counted) x 0.9 add up
    to at least df's HP after the largest heal any reading gives. Sucker Punch is refused (it fails against an item user)."""
    df, item, a1, mv1, a2, mv2 = x.args
    assert x.double, 'pair_ko is a doubles claim'
    assert a1 != a2 and x.side(a1) == x.side(a2) != x.side(df), 'a1 and a2 must be the two foes of df'
    for mv in (mv1, mv2):
        assert x.d.move(mv)['effect'] != SUCKER, 'Sucker Punch fails against a trainer who uses an item'
    readings = item_readings(x, item) if item else [(0, set(), {})]
    for reading in readings:
        hp, st = _after_item(x, df, reading) if item else (x.ref(df)['cur_hp'], x.ref(df)['status'])
        saved = _set(x, {df: (hp, st)})
        try:
            assert not x.endures(a1, mv1, df), '%s hangs on at 1 HP' % x.ref(df)['species']
            dmg = int(x.total(a1, mv1, df, True) * 0.9) + int(x.total(a2, mv2, df, True) * 0.9)
            assert dmg >= hp, '%s at %d HP survives %s + %s (at least %d)' % (x.ref(df)['species'], hp, mv1, mv2, dmg)
        finally:
            _set(x, saved)


SCENARIOS = with_sleep(with_items([
    # --- healing that only delays a knockout
    S('b04b_poison_finishes_heal_futile', 'item',
      'Gyarados at 30% is faster than poisoned Ampharos at 65%, whose Thunderbolt (4x) KOs it even from full HP, so Max Potion buys nothing; Earthquake (2x, 63-75%) and the poison at the end of the turn surely knock Ampharos out even after Gyarados falls, while Ice Fang or Waterfall cannot be counted on to do it, and switching Skarmory in feeds it a Thunderbolt (2x) and then a second one',
      [mon('Ampharos', ['Thunderbolt', 'Dragon Pulse', 'Focus Blast'], status='psn', hp=0.65)],
      [mon('Gyarados', ['Earthquake', 'Waterfall', 'Ice Fang'], hp=0.3), mon('Skarmory', ['Brave Bird', 'Iron Head'])],
      items=['Max Potion'],
      best=['Earthquake'], bad=['item:Max Potion', 'switch:Skarmory'],
      checks=[('has_status', 'p0', 'psn'), ('mfaster', 'e0', 'p0'), ('eff', 'p0', 'Thunderbolt', 'e0', 4.0),
              ('b04b_heal_still_ko', 'e0', 'Max Potion', 'p0', 'Thunderbolt'), ('b04b_hit_then_chip_kos', 'e0', 'Earthquake', 'p0'),
              ('chip_survives', 'p0'), ('mnoko', 'e0', 'Ice Fang', 'p0'), ('mnoko', 'e0', 'Waterfall', 'p0'),
              ('eff', 'p0', 'Thunderbolt', 'e1', 2.0), ('b04b_entry_loses', 'e1', 'p0', 'Thunderbolt', '*')]),
    S('b04b_specs_heal_or_switch', 'switch',
      'Metagross at 35% is slower than Choice Specs Volcarona, whose Flamethrower (2x) KOs it even after Hyper Potion fills its HP, and Rock Slide (4x) would KO Volcarona but never gets to move: switch to Flash Fire Heatran, which takes nothing from Fire and little from Bug Buzz or Hurricane; Scizor would fall to the Flamethrower (4x)',
      [mon('Volcarona', ['Flamethrower', 'Bug Buzz', 'Hurricane'], item='Choice Specs')],
      [mon('Metagross', ['Meteor Mash', 'Zen Headbutt', 'Earthquake', 'Rock Slide'], hp=0.35), mon('Heatran', ['Earth Power', 'Flash Cannon', 'Lava Plume'], ability='Flash Fire'),
       mon('Scizor', ['X-Scissor', 'Bullet Punch', 'Iron Head'])],
      items=['Hyper Potion'],
      best=['switch:Heatran'], bad=['item:Hyper Potion', 'switch:Scizor', 'Meteor Mash', 'Zen Headbutt', 'Earthquake', 'Rock Slide'],
      checks=[('mfaster', 'p0', 'e0'), ('has_item', 'p0', 'Choice Specs'), ('mko', 'p0', 'Flamethrower', 'e0'),
              ('b04b_heal_still_ko', 'e0', 'Hyper Potion', 'p0', 'Flamethrower'), ('eff', 'e0', 'Rock Slide', 'p0', 4.0),
              ('meff', 'p0', 'Flamethrower', 'e1', 0.0), ('mnoko', 'p0', 'Bug Buzz', 'e1'), ('mnoko', 'p0', 'Hurricane', 'e1'),
              ('mko', 'p0', 'Flamethrower', 'e2')]),

    # --- healing that wins, and the item that has to do it
    S('b04b_max_not_hyper', 'item',
      'Blissey (HP and Defense trained) has 15 HP and is slower than Garchomp at 50%, whose Earthquake takes 38-45% of its HP: Max Potion comes before any move, so Blissey survives two Earthquakes and its Ice Beam (4x) KOs Garchomp; Hyper Potion (200 HP at most) leaves it to the second Earthquake, and Soft-Boiled or an attack comes after Garchomp, which KOs it first',
      [mon('Garchomp', ['Earthquake', 'Dragon Claw', 'Stone Edge'], hp=0.5)],
      [mon('Blissey', ['Ice Beam', 'Hyper Voice', 'Soft-Boiled'], evs={'hp': 252, 'def': 252}, hp=15)],
      items=['Hyper Potion', 'Max Potion'],
      best=['item:Max Potion'], bad=['Soft-Boiled', 'Ice Beam', 'Hyper Voice'],
      checks=[('mfaster', 'p0', 'e0'), ('mko', 'p0', 'Earthquake', 'e0'), ('mko', 'p0', 'Dragon Claw', 'e0'), ('mko', 'p0', 'Stone Edge', 'e0'),
              ('pri', 'Soft-Boiled', 0), ('loses', 'e0', '*', 'p0', 'Earthquake'), ('b04b_item_effect', 'Max Potion', 'heal', 'full'),
              ('b04b_item_effect', 'Hyper Potion', 'heal', 200), ('b04b_item_race', 'e0', 'Max Potion', 'Ice Beam', 'p0', '*', 2),
              ('b04b_item_loses', 'e0', 'Hyper Potion', '*', 'p0', 'Earthquake'), ('eff', 'e0', 'Ice Beam', 'p0', 4.0), ('mko', 'e0', 'Ice Beam', 'p0')]),
    S('b04b_full_restore_par_flip', 'item',
      'Paralyzed Infernape at 20% is slower than Kangaskhan, whose Double-Edge and Earthquake (2x) each take 67-89% of its full HP: Full Restore heals it and cures the paralysis, so next turn Infernape is the faster one again and Close Combat (2x) KOs; Hyper Potion leaves it paralyzed and slower, to fall to the second hit, Full Heal leaves it at 20% for the first, and attacking now (even Mach Punch, which goes first but cannot KO) lets Kangaskhan KO it',
      [mon('Kangaskhan', ['Double-Edge', 'Earthquake', 'Crunch'], hp=0.9)],
      [mon('Infernape', ['Close Combat', 'Flare Blitz', 'Mach Punch'], status='par', hp=0.2)],
      items=['Hyper Potion', 'Full Heal', 'Full Restore'],
      best=['item:Full Restore'], bad=['item:Full Heal', 'Close Combat', 'Flare Blitz', 'Mach Punch'],
      checks=[('has_status', 'e0', 'par'), ('mfaster', 'p0', 'e0'), ('mko', 'p0', 'Double-Edge', 'e0'), ('mko', 'p0', 'Earthquake', 'e0'),
              ('b04b_heal_still_ko', 'e0', 'Full Heal', 'p0', 'Double-Edge'), ('b04b_item_effect', 'Full Restore', 'cures', 'par'),
              ('b04b_item_race', 'e0', 'Full Restore', 'Close Combat', 'p0', '*', 2), ('b04b_item_loses', 'e0', 'Hyper Potion', '*', 'p0', 'Earthquake'),
              ('loses', 'e0', '*', 'p0', 'Double-Edge'), ('mnoko', 'e0', 'Mach Punch', 'p0'), ('mko', 'e0', 'Close Combat', 'p0')]),
    S('b04b_priority_forces_heal', 'priority',
      'Ninetales at 25% is faster than Lucario and Flamethrower (2x) would KO it, but ExtremeSpeed (+2) KOs Ninetales first; Hyper Potion comes before any move, and from full HP Ninetales takes two ExtremeSpeeds or a Close Combat and still KOs Lucario with Flamethrower next turn',
      [mon('Lucario', ['Extreme Speed', 'Close Combat', 'Bullet Punch'], hp=0.6)],
      [mon('Ninetales', ['Flamethrower', 'Moonblast', 'Energy Ball'], hp=0.25)],
      items=['Hyper Potion'],
      best=['item:Hyper Potion'], bad=['Flamethrower', 'Moonblast', 'Energy Ball'],
      checks=[('mfaster', 'e0', 'p0'), ('pri', 'Extreme Speed', 2), ('mko', 'p0', 'Extreme Speed', 'e0'), ('mko', 'e0', 'Flamethrower', 'p0'),
              ('loses', 'e0', '*', 'p0', 'Extreme Speed'), ('b04b_heal_survives', 'e0', 'Hyper Potion', 'p0', 'Close Combat'),
              ('b04b_item_race', 'e0', 'Hyper Potion', 'Flamethrower', 'p0', '*', 2)]),

    # --- cure the status, or play through it
    S('b04b_full_heal_toxic_race', 'status',
      'Badly poisoned Suicune (HP and Sp. Def trained) trades Surf for Surf with level 48 Walrein, and each side does under a fifth of the other\'s HP a hit: the poison, growing every turn, knocks Suicune out before its sixth Surf lands, while after Full Heal it wins the long trade even with the turn spent',
      [mon('Walrein', ['Surf', 'Aurora Beam'], level=48)],
      [mon('Suicune', ['Surf', 'Ice Beam'], status='tox', evs={'hp': 252, 'spd': 252})],
      items=['Full Heal'],
      best=['item:Full Heal'],
      checks=[('has_status', 'e0', 'tox'), ('mfaster', 'e0', 'p0'), ('b04b_item_effect', 'Full Heal', 'cures', 'tox'),
              ('b04b_item_race', 'e0', 'Full Heal', 'Surf', 'p0', '*', 9), ('loses', 'e0', '*', 'p0', 'Surf'), ('loses', 'e0', '*', 'p0', 'Aurora Beam')]),
    S('b04b_burned_still_kos', 'status',
      'Burned Mamoswine at full HP is slower than Typhlosion at 45%, whose Flamethrower (2x) takes 69-82%: the burn halves Earthquake (2x), but it still KOs Typhlosion after Mamoswine survives the first Flamethrower; Full Heal would spend that turn and leave Mamoswine to the second one, and Ice Shard (priority) or Icicle Crash is resisted and cannot KO',
      [mon('Typhlosion', ['Flamethrower', 'Focus Blast'], hp=0.45)],
      [mon('Mamoswine', ['Earthquake', 'Icicle Crash', 'Ice Shard'], status='brn')],
      items=['Full Heal'],
      best=['Earthquake'], bad=['item:Full Heal', 'Ice Shard', 'Icicle Crash'],
      checks=[('has_status', 'e0', 'brn'), ('mfaster', 'p0', 'e0'), ('mnoko', 'p0', 'Flamethrower', 'e0'), ('mnoko', 'p0', 'Focus Blast', 'e0'),
              ('race', 'e0', 'Earthquake', 'p0', '*', 1), ('b04b_item_loses', 'e0', 'Full Heal', '*', 'p0', 'Flamethrower'),
              ('mnoko', 'e0', 'Ice Shard', 'p0'), ('loses', 'e0', 'Ice Shard', 'p0', 'Flamethrower'), ('loses', 'e0', 'Icicle Crash', 'p0', 'Flamethrower')]),
    S('b04b_sleep_talk_over_full_heal', 'rules',
      'Lapras is asleep for at least two more turns and slower than Electivire at 30%, whose Thunder Punch and Brick Break (2x) each take 57-67%: Sleep Talk uses Surf or Ice Beam at random and either KOs Electivire this turn, while Full Heal wakes Lapras but spends the turn and leaves it to the second hit; Surf or Ice Beam chosen directly does nothing while asleep',
      [mon('Electivire', ['Thunder Punch', 'Brick Break', 'Ice Punch'], hp=0.3)],
      [mon('Lapras', ['Sleep Talk', 'Surf', 'Ice Beam'], status='slp', sleep=3)],
      items=['Full Heal'],
      best=['Sleep Talk'], bad=['item:Full Heal', 'Surf', 'Ice Beam'],
      checks=[('has_status', 'e0', 'slp'), ('mfaster', 'p0', 'e0'), ('b04b_sleep_talk_kos', 'e0', 'p0'), ('mnoko', 'p0', 'Thunder Punch', 'e0'),
              ('mnoko', 'p0', 'Brick Break', 'e0'), ('b04b_item_loses', 'e0', 'Full Heal', '*', 'p0', 'Thunder Punch')]),

    # --- X items
    S('b04b_x_items_vs_priority', 'setup',
      'Torterra at 50% is slower than Weavile, whose Ice Shard (priority, 2x) takes 29-36% of Torterra\'s full HP a hit and whose other attacks do less, and Superpower (4x) KOs Weavile: attacking now wins, while X Speed or X Attack spends the turn and two Ice Shards, which go first whatever Torterra\'s Speed, KO it before it attacks; Stone Edge also KOs but can miss',
      [mon('Weavile', ['Ice Shard', 'Night Slash', 'Poison Jab'], ability='Pressure')],
      [mon('Torterra', ['Superpower', 'Wood Hammer', 'Stone Edge'], hp=0.5)],
      items=['X Speed', 'X Attack'],
      best=['Superpower'], ok=['Stone Edge'], bad=['item:X Speed', 'item:X Attack'],
      checks=[('mfaster', 'p0', 'e0'), ('pri', 'Ice Shard', 1), ('mnoko', 'p0', 'Ice Shard', 'e0'), ('mnoko', 'p0', 'Night Slash', 'e0'),
              ('race', 'e0', 'Superpower', 'p0', '*', 1), ('mko', 'e0', 'Stone Edge', 'p0'), ('acc_lt', 'Stone Edge', 100),
              ('b04b_item_effect', 'X Speed', 'stage', ('spe', 1)), ('b04b_item_loses', 'e0', 'X Speed', '*', 'p0', 'Ice Shard'),
              ('b04b_item_loses', 'e0', 'X Attack', '*', 'p0', 'Ice Shard')]),

    # --- doubles
    S('b04b_dbl_heal_two_attackers', 'doubles',
      'Alakazam at 30% is the fastest Pokemon out; neither foe KOs it from full HP alone, but Togekiss\'s Air Slash and Honchkrow\'s Dark Pulse together do, so Full Restore only delays it, and both foes move before slow partner Hippowdon: Alakazam should take Honchkrow (25%) with it, and Dazzling Gleam (both foes) or Focus Blast KOs it, while Psychic cannot touch a Dark type',
      [mon('Togekiss', ['Air Slash', 'Aura Sphere']), mon('Honchkrow', ['Dark Pulse', 'Heat Wave'], hp=0.25)],
      [mon('Alakazam', ['Psychic', 'Shadow Ball', 'DazzlngGleam', 'Focus Blast'], hp=0.3), mon('Hippowdon', ['Stone Edge', 'Crunch'])],
      items=['Full Restore'], double=True,
      best=['DazzlngGleam'], ok=['Focus Blast>Honchkrow'], bad=['item:Full Restore', 'Psychic>Honchkrow'],
      checks=[('mfaster', 'e0', 'p0'), ('mfaster', 'e0', 'p1'), ('mfaster', 'p0', 'e1'), ('mfaster', 'p1', 'e1'),
              ('b04b_heal_survives', 'e0', 'Full Restore', 'p0', 'Air Slash'), ('b04b_heal_survives', 'e0', 'Full Restore', 'p1', 'Dark Pulse'),
              ('b04b_pair_ko', 'e0', 'Full Restore', 'p0', 'Air Slash', 'p1', 'Dark Pulse'), ('mko', 'p0', 'Air Slash', 'e0'),
              ('mko', 'e0', 'DazzlngGleam', 'p1'), ('mko', 'e0', 'Focus Blast', 'p1'), ('acc_lt', 'Focus Blast', 100), ('eff', 'e0', 'Psychic', 'p1', 0.0)]),
]))
