"""Batch 04, author A: doubles (`double=True`). Only enemy[0]'s turn-1 action is graded.

Ten positions: Fake Out into a Ghost, a weak spread move against a single-target KO, a spread move that hits a partner who
resists it, the target the partner cannot touch, a Rocky Helmet on the foe that cannot touch the AI's Pokemon, Wide Guard
against a KO that removes the spread user, a switch out of a spread move, the spread user as the bigger threat, Explosion
that hits the partner and spares a Ghost, and staying in when the switch-in would take a spread move.

Every key rests on the type chart, the stats, the Gen 5 damage formula, priority and speed. Mechanics not measured in this
ROM never decide a key unless the margin holds either way:
  - the spread reduction (0.75 for a move that hits two or more targets): b04a_ko / b04a_noko require the claim with and
    without it, so the key holds whether the engine applies it or not;
  - Wide Guard, Fake Out's flinch, Knock Off against an item holder: never the best answer and never punished as bad
    because of what they do;
  - Rocky Helmet: measured (id 590 deals a sixth of the attacker's max HP on contact). b04a_helmet_kos only claims it for a
    hit that leaves the holder standing, so the key does not depend on whether the Helmet still triggers when the holder faints.

ai_checks.Ctx refuses every item whose byte 2 in `a/0/1/7` is 0, and Rocky Helmet (590) is one of them, although the
measurement above shows the engine applies it. `B4Ctx` is ai_checks.Ctx that accepts Rocky Helmet and nothing else new; the
damage model is unchanged. The ops below are registered in ai_checks.CHECKS on import (prefix b04a_), before `with_items` runs.
"""
from ai_checks import CHECKS, MODELED_ABILITIES, STATUS, Ctx, with_items
from ai_helpers import PLAIN, S, mon  # noqa: F401

FLAG_CONTACT = 1
ROCKY_HELMET = 'Rocky Helmet'   # aidata resolves the name to id 590, the one measured to work
SPREAD_ALL, SPREAD_FOES, SINGLE = 4, 5, 0   # move data target byte: every other Pokemon / both foes / one chosen target
FOE_TARGETS = {SINGLE, SPREAD_ALL, SPREAD_FOES}


class B4Ctx(Ctx):
    """ai_checks.Ctx plus Rocky Helmet (measured: a sixth of the attacker's max HP on contact)."""

    def vet(self, r, v):
        if self.items.get(r) == ROCKY_HELMET:
            assert v['ability'] in MODELED_ABILITIES, '%s: %s has %s, which these checks do not model' % (r, v['species'], v['ability'])
            return
        super().vet(r, v)

    def total_rule(self, a, mv, df, sure, spread):
        """total() with the spread reduction applied (spread=True, the Gen 5 rule) or not (spread=False)."""
        saved = self.double
        self.double = saved and spread
        try:
            return self.total(a, mv, df, sure)
        finally:
            self.double = saved


def _op(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(B4Ctx(d, views, c, ref))
        return fn
    return reg


@_op('b04a_ko')
def b04a_ko(x):
    """('b04a_ko', a, mv, df): a sure KO whether or not the engine applies the doubles spread reduction (0.75 when the move hits
    two or more targets): the minimum with the reduction x 0.9 >= current HP (the lower of the two), and no Focus Sash / Sturdy hold."""
    a, mv, df = x.args
    hp = x.ref(df)['cur_hp']
    assert not x.endures(a, mv, df), '%s: %s keeps 1 HP (Focus Sash / Sturdy at full HP)' % (mv, x.ref(df)['species'])
    for spread in (True, False):
        lo = x.total_rule(a, mv, df, True, spread)
        assert lo * 0.9 >= hp, '%s does at least %d to %s at %d HP (spread reduction %s): not a sure KO' % (
            mv, lo, x.ref(df)['species'], hp, 'on' if spread else 'off')


@_op('b04a_noko')
def b04a_noko(x):
    """('b04a_noko', a, mv, df): cannot KO whether or not the engine applies the doubles spread reduction: the maximum without
    the reduction (the higher of the two) x 1.1 < current HP."""
    a, mv, df = x.args
    hp = x.ref(df)['cur_hp']
    for spread in (True, False):
        hi = x.total_rule(a, mv, df, False, spread)
        assert hi * 1.1 < hp, '%s does up to %d to %s at %d HP (spread reduction %s): can KO' % (
            mv, hi, x.ref(df)['species'], hp, 'on' if spread else 'off')


@_op('b04a_noko_sum')
def b04a_noko_sum(x):
    """('b04a_noko_sum', df, ((a, mv), ...)): those hits together cannot KO df in one turn: the sum of their maxima without the
    spread reduction x 1.1 < current HP."""
    df, hits = x.args
    total = sum(x.total_rule(a, mv, df, False, False) for a, mv in hits)
    hp = x.ref(df)['cur_hp']
    assert total * 1.1 < hp, '%s do up to %d together to %s at %d HP: can KO' % (
        ' + '.join(mv for _, mv in hits), total, x.ref(df)['species'], hp)


@_op('b04a_reach')
def b04a_reach(x):
    """('b04a_reach', a, mv, ally, want): whether a's move damages its own partner. Only a move whose target byte is 4 (every other
    Pokemon: Earthquake, Surf, Explosion) reaches the partner; 5 (both foes) and 0 (one chosen target) never do. A reached partner
    still takes nothing when it is immune (type chart, type-immune abilities, Telepathy)."""
    a, mv, ally, want = x.args
    assert x.double, 'b04a_reach is a doubles claim'
    assert x.side(ally) == x.side(a) and ally != a, '%s is not %s\'s partner' % (ally, a)
    m = x.d.move(mv)
    assert m['class'] != STATUS, '%s is a status move' % mv
    hit = m['target'] == SPREAD_ALL and x.ability(ally) != 'Telepathy' and x.effectiveness(a, mv, ally) > 0
    assert hit == want, '%s %s %s\'s partner %s' % (mv, 'damages' if hit else 'does not damage', x.ref(a)['species'], x.ref(ally)['species'])


@_op('b04a_walled')
def b04a_walled(x):
    """('b04a_walled', a, df): nothing a can do touches df: every damaging move of a does nothing to it (type chart, type-immune
    abilities), and none of a's status moves can be aimed at a foe (target byte 0, 4 or 5)."""
    a, df = x.args
    for mv in x.ref(a)['moves']:
        m = x.d.move(mv)
        if m['class'] == STATUS:
            assert m['target'] not in FOE_TARGETS, '%s\'s %s can be aimed at %s' % (x.ref(a)['species'], mv, x.ref(df)['species'])
        else:
            eff = x.effectiveness(a, mv, df)
            assert eff == 0, '%s\'s %s hits %s (x%s)' % (x.ref(a)['species'], mv, x.ref(df)['species'], eff)


@_op('b04a_single_target')
def b04a_single_target(x):
    """('b04a_single_target', a): none of a's damaging moves hits more than one Pokemon (target byte 0 only)."""
    (a,) = x.args
    for mv in x.ref(a)['moves']:
        m = x.d.move(mv)
        if m['class'] != STATUS:
            assert m['target'] == SINGLE, '%s\'s %s hits several Pokemon (target %d)' % (x.ref(a)['species'], mv, m['target'])


@_op('b04a_contact')
def b04a_contact(x):
    """('b04a_contact', mv, want): the move makes contact (flag bit 0 of the move data) or not."""
    mv, want = x.args
    got = bool(x.d.move(mv)['flags'] & FLAG_CONTACT)
    assert got == want, '%s %s contact' % (mv, 'makes' if got else 'does not make')


@_op('b04a_helmet_kos')
def b04a_helmet_kos(x):
    """('b04a_helmet_kos', a, mv, df): df holds Rocky Helmet (id 590, measured: a sixth of the attacker's max HP when hit by a
    contact move), the move makes contact, df survives it (maximum without the spread reduction x 1.1 < HP, so the Helmet
    triggers on a holder that is still standing), and a sixth of a's max HP is at least a's current HP. Magic Guard refused."""
    a, mv, df = x.args
    av, dv = x.ref(a), x.ref(df)
    assert x.items.get(df) == ROCKY_HELMET, '%s does not hold Rocky Helmet' % dv['species']
    assert x.d.move(mv)['flags'] & FLAG_CONTACT, '%s makes no contact' % mv
    assert av['ability'] != 'Magic Guard', 'Magic Guard takes no Helmet damage'
    hi = x.total_rule(a, mv, df, False, False)
    assert hi * 1.1 < dv['cur_hp'], '%s can KO %s (up to %d of %d HP)' % (mv, dv['species'], hi, dv['cur_hp'])
    assert av['stats']['hp'] // 6 >= av['cur_hp'], 'the Helmet costs %s %d HP, it has %d' % (av['species'], av['stats']['hp'] // 6, av['cur_hp'])


@_op('b04a_eff')
def b04a_eff(x):
    """('b04a_eff', a, mv, df, want): ai_checks' meff on B4Ctx, for a scenario with a Rocky Helmet holder."""
    a, mv, df, want = x.args
    got = x.effectiveness(a, mv, df)
    assert got == want, '%s vs %s: effectiveness %s, claimed %s' % (mv, x.ref(df)['species'], got, want)


@_op('b04a_faster')
def b04a_faster(x):
    """('b04a_faster', p, q): ai_checks' mfaster rule (paralysis at a quarter and at half, items, abilities) on B4Ctx."""
    p, q = x.args
    for div in (4, 2):
        sp, sq = x.speed(p, div), x.speed(q, div)
        assert sp > sq, '%s (%d) is not faster than %s (%d)' % (x.ref(p)['species'], sp, x.ref(q)['species'], sq)


@_op('b04a_faster_dropped')
def b04a_faster_dropped(x):
    """('b04a_faster_dropped', p, q, stages): p still moves before q with its Speed lowered by that many stages (Electroweb, Icy
    Wind), under both paralysis rules. Whether a Speed drop changes the order within the same turn depends on the generation
    (Gen 5 fixes the order at the start of the turn, Gen 8 recomputes it); this claim makes the order the same either way."""
    p, q, stages = x.args
    x.boosts[(p, 'spe')] = stages
    try:
        for div in (4, 2):
            sp, sq = x.speed(p, div), x.speed(q, div)
            assert sp > sq, '%s at %+d Speed (%d) is not faster than %s (%d)' % (x.ref(p)['species'], stages, sp, x.ref(q)['species'], sq)
    finally:
        x.boosts.clear()


@_op('b04a_no_priority')
def b04a_no_priority(x):
    """('b04a_no_priority', a): none of a's moves has a priority above 0."""
    (a,) = x.args
    for mv in x.ref(a)['moves']:
        assert x.d.move(mv)['priority'] <= 0, '%s has %s (priority %d)' % (x.ref(a)['species'], mv, x.d.move(mv)['priority'])


SCENARIOS = with_items([
    S('b04a_fake_out_into_ghost', 'doubles',
      "Gengar at 55% is faster than partner Breloom and Sludge Bomb (2x) KOs it; Weavile is faster than Gengar and Night Slash (2x) "
      "KOs it first. Fake Out and Brick Break cannot touch a Ghost, Breloom's own moves cannot KO Gengar, and Snorlax cannot KO "
      "anyone this turn, so flinching Snorlax gains nothing",
      [mon('Gengar', ['Shadow Ball', 'Sludge Bomb', 'Focus Blast', 'Thunderbolt'], hp=0.55), mon('Snorlax', ['Body Slam', 'Curse', 'Rest'])],
      [mon('Weavile', ['Fake Out', 'Night Slash', 'Ice Shard', 'Brick Break']), mon('Breloom', ['Seed Bomb', 'Mach Punch', 'Rock Tomb'], hp=0.6)],
      best=['Night Slash>Gengar'], bad=['Fake Out>Gengar', 'Brick Break>Gengar'], double=True,
      checks=[('pri', 'Fake Out', 3), ('meff', 'e0', 'Fake Out', 'p0', 0.0), ('meff', 'e0', 'Brick Break', 'p0', 0.0),
              ('mko', 'e0', 'Night Slash', 'p0'), ('mnoko', 'e0', 'Ice Shard', 'p0'), ('mfaster', 'e0', 'p0'), ('mfaster', 'p0', 'e1'),
              ('mko', 'p0', 'Sludge Bomb', 'e1'), ('mnoko', 'e1', 'Seed Bomb', 'p0'), ('mnoko', 'e1', 'Rock Tomb', 'p0'),
              ('meff', 'e1', 'Mach Punch', 'p0', 0.0), ('mnoko', 'p1', 'Body Slam', 'e0'), ('mnoko', 'p1', 'Body Slam', 'e1')]),

    S('b04a_spread_chip_vs_ko', 'doubles',
      "Golduck at 63% is faster than partner Conkeldurr, even after Electroweb's Speed drop, and Psychic (2x) KOs it; Raichu is "
      "faster than Golduck and Thunderbolt KOs it. Electroweb hits both foes, but even at full power (no spread reduction) it "
      "cannot KO Golduck, and Conkeldurr has no priority move, so the spread move costs the partner",
      [mon('Golduck', ['Psychic', 'Hydro Pump', 'Ice Beam', 'Calm Mind'], hp=0.63), mon('Vaporeon', ['Scald', 'Wish', 'Protect', 'Toxic'])],
      [mon('Raichu', ['Thunderbolt', 'Electroweb', 'Focus Blast', 'Nasty Plot']), mon('Conkeldurr', ['Drain Punch', 'Ice Punch', 'Knock Off', 'Bulk Up'], hp=0.55)],
      best=['Thunderbolt>Golduck'], double=True,
      checks=[('mko', 'e0', 'Thunderbolt', 'p0'), ('b04a_noko', 'e0', 'Electroweb', 'p0'), ('mfaster', 'e0', 'p0'), ('b04a_faster_dropped', 'p0', 'e1', -1),
              ('mko', 'p0', 'Psychic', 'e1'), ('b04a_no_priority', 'e1'), ('mnoko', 'p1', 'Scald', 'e0')]),

    S('b04a_surf_partner_resists', 'doubles',
      "Surf also hits partner Dragonite, but Dragonite resists Water, takes under a fifth and survives even without the spread reduction, "
      "while Surf KOs both Golem (4x) and Camerupt at 80% (4x) before either moves; Hydro Pump KOs only one (90% accurate), and "
      "Dragonite's own moves cannot KO either foe",
      [mon('Golem', ['Earthquake', 'Stone Edge', 'Sucker Punch', 'Rock Polish']), mon('Camerupt', ['Eruption', 'Earth Power', 'Fire Blast', 'Ancient Power'], hp=0.8)],
      [mon('Kingdra', ['Surf', 'Hydro Pump', 'Draco Meteor', 'Ice Beam']), mon('Dragonite', ['ExtremeSpeed', 'Dragon Claw', 'Fire Punch', 'Roost'])],
      best=['Surf'], ok=['Hydro Pump>Golem', 'Hydro Pump>Camerupt'], double=True,
      checks=[('b04a_ko', 'e0', 'Surf', 'p0'), ('b04a_ko', 'e0', 'Surf', 'p1'), ('b04a_reach', 'e0', 'Surf', 'e1', True),
              ('meff', 'e0', 'Surf', 'e1', 0.5), ('b04a_noko', 'e0', 'Surf', 'e1'), ('mfrac', 'e0', 'Surf', 'e1', 0, 0.2),
              ('mfaster', 'e0', 'p0'), ('mfaster', 'e0', 'p1'), ('acc_lt', 'Hydro Pump', 100),
              ('mnoko', 'e1', 'Dragon Claw', 'p0'), ('mnoko', 'e1', 'Dragon Claw', 'p1'), ('mnoko', 'e1', 'ExtremeSpeed', 'p1'),
              ('pri', 'Sucker Punch', 1), ('mnoko', 'p0', 'Sucker Punch', 'e0')]),

    S('b04a_partner_cannot_touch_ghost', 'doubles',
      "Partner Hitmonlee has only Normal and Fighting moves, so it cannot touch Chandelure, whose Flamethrower then KOs it; it can "
      "KO Scizor at 40% with Close Combat before Scizor moves. Houndoom is the fastest and can KO either foe: Dark Pulse on "
      "Chandelure leaves Scizor to Hitmonlee, while the tempting Flamethrower on Scizor (4x) leaves Chandelure free",
      [mon('Chandelure', ['Shadow Ball', 'Flamethrower', 'Energy Ball', 'Calm Mind'], hp=0.55), mon('Scizor', ['X-Scissor', 'Iron Head', 'U-turn', 'Swords Dance'], hp=0.4)],
      [mon('Houndoom', ['Dark Pulse', 'Flamethrower', 'Sludge Bomb', 'Nasty Plot']), mon('Hitmonlee', ['Close Combat', 'Mach Punch', 'Fake Out', 'Bulk Up'], hp=0.45)],
      best=['Dark Pulse>Chandelure'], double=True,
      checks=[('mko', 'e0', 'Dark Pulse', 'p0'), ('mko', 'e0', 'Flamethrower', 'p1'), ('b04a_walled', 'e1', 'p0'),
              ('mko', 'e1', 'Close Combat', 'p1'), ('mfaster', 'e1', 'p1'), ('mfaster', 'e0', 'p0'), ('mfaster', 'e0', 'p1'),
              ('mko', 'p0', 'Flamethrower', 'e1'), ('mnoko', 'p0', 'Flamethrower', 'e0'), ('mnoko', 'p0', 'Shadow Ball', 'e0')]),

    S('b04a_helmet_on_the_harmless_foe', 'doubles',
      "Sableye at 15% is a Ghost and Dark type: neither Medicham nor Kangaskhan has a move that can touch it. Medicham holds "
      "Rocky Helmet: Shadow Claw (contact, 2x, the most damage) leaves it standing and the Helmet's sixth knocks Sableye out; "
      "Shadow Ball is also 2x but makes no contact. Partner Amoonguss moves after Sableye, so Medicham is at full HP when it is "
      "hit. Ghost moves do nothing to Kangaskhan",
      [mon('Medicham', ['Hi Jump Kick', 'Zen Headbutt', 'Fake Out', 'Bulk Up'], item='Rocky Helmet'), mon('Kangaskhan', ['Double-Edge', 'Hammer Arm', 'Fake Out', 'Body Slam'])],
      [mon('Sableye', ['Shadow Claw', 'Shadow Ball', 'Knock Off', 'Will-O-Wisp'], hp=0.15, evs={'atk': 252}), mon('Amoonguss', ['Spore', 'Giga Drain', 'Sludge Bomb', 'Clear Smog'])],
      best=['Shadow Ball>Medicham'], ok=['Will-O-Wisp', 'Knock Off>Kangaskhan'],
      bad=['Shadow Claw>Medicham', 'Shadow Claw>Kangaskhan', 'Shadow Ball>Kangaskhan'], double=True,
      checks=[('b04a_walled', 'p0', 'e0'), ('b04a_walled', 'p1', 'e0'), ('b04a_helmet_kos', 'e0', 'Shadow Claw', 'p0'),
              ('b04a_contact', 'Shadow Ball', False), ('b04a_contact', 'Knock Off', True), ('b04a_eff', 'e0', 'Shadow Ball', 'p0', 2.0),
              ('b04a_eff', 'e0', 'Shadow Claw', 'p0', 2.0), ('b04a_eff', 'e0', 'Shadow Claw', 'p1', 0.0),
              ('b04a_eff', 'e0', 'Shadow Ball', 'p1', 0.0), ('b04a_noko', 'e0', 'Shadow Ball', 'p0'), ('b04a_faster', 'e0', 'e1')]),

    S('b04a_ko_beats_wide_guard', 'doubles',
      "Tyranitar's Rock Slide (both foes) KOs partner Volcarona (4x) even with the spread reduction; Mienshao is the fastest and "
      "Close Combat (4x) KOs Tyranitar before it moves, which removes the spread move for good, where Wide Guard only blocks it "
      "this turn. Ursaring has no spread move and Volcarona cannot KO Tyranitar itself",
      [mon('Tyranitar', ['Rock Slide', 'Crunch', 'Ice Punch', 'Dragon Dance']), mon('Ursaring', ['Double-Edge', 'Crunch', 'Swords Dance'])],
      [mon('Mienshao', ['Close Combat', 'Wide Guard', 'U-turn', 'Stone Edge']), mon('Volcarona', ['Bug Buzz', 'Fiery Dance', 'Giga Drain', 'Quiver Dance'])],
      best=['Close Combat>Tyranitar'], double=True,
      checks=[('mko', 'e0', 'Close Combat', 'p0'), ('mfaster', 'e0', 'p0'), ('mfaster', 'e0', 'p1'), ('b04a_ko', 'p0', 'Rock Slide', 'e1'),
              ('b04a_reach', 'p0', 'Rock Slide', 'p1', False), ('b04a_single_target', 'p1'), ('pri', 'Wide Guard', 3),
              ('mnoko', 'e1', 'Bug Buzz', 'p0'), ('mnoko', 'e1', 'Fiery Dance', 'p0'), ('mnoko', 'e1', 'Giga Drain', 'p0')]),

    S('b04a_switch_out_of_eruption', 'doubles',
      "Typhlosion at full HP is faster than Ferrothorn and Eruption (both foes, 150 power) KOs it (4x) even with the spread "
      "reduction, so Ferrothorn never gets to move; Swampert resists Fire, is immune to Zapdos's Thunderbolt and survives "
      "Focus Blast plus Hurricane together: switch",
      [mon('Typhlosion', ['Eruption', 'Focus Blast', 'Extrasensory', 'Flamethrower']), mon('Zapdos', ['Thunderbolt', 'Hurricane', 'Heat Wave', 'Roost'])],
      [mon('Ferrothorn', ['Power Whip', 'Gyro Ball', 'Leech Seed', 'Iron Head']), mon('Milotic', ['Scald', 'Ice Beam', 'Recover', 'Toxic']),
       mon('Swampert', ['Waterfall', 'Earthquake', 'Ice Punch', 'Stealth Rock'], evs={'hp': 252, 'spd': 252})],
      best=['switch:Swampert'], bad=['Power Whip', 'Gyro Ball', 'Leech Seed', 'Iron Head'], double=True,
      checks=[('b04a_ko', 'p0', 'Eruption', 'e0'), ('mfaster', 'p0', 'e0'), ('mfaster', 'p1', 'e0'), ('meff', 'p0', 'Eruption', 'e2', 0.5),
              ('meff', 'p1', 'Thunderbolt', 'e2', 0.0), ('b04a_noko_sum', 'e2', (('p0', 'Focus Blast'), ('p1', 'Hurricane'))),
              ('b04a_noko_sum', 'e2', (('p0', 'Eruption'), ('p1', 'Hurricane')))]),

    S('b04a_spread_user_first', 'doubles',
      "Togekiss's Dazzling Gleam (both foes) KOs both Hydreigon at 80% (4x) and Scrafty at 70% (4x) even with the spread "
      "reduction; Lucario at 45% KOs only Hydreigon. Hydreigon is faster than both foes: Flash Cannon (2x) KOs Togekiss and "
      "costs at most Hydreigon to Lucario, while the easy Flamethrower KO on Lucario lets Gleam take both; Draco Meteor cannot touch a Fairy",
      [mon('Togekiss', ['DazzlngGleam', 'Air Slash', 'Roost', 'Thunder Wave'], hp=0.35), mon('Lucario', ['Close Combat', 'Aura Sphere', 'Extreme Speed', 'Swords Dance'], hp=0.45)],
      [mon('Hydreigon', ['Dark Pulse', 'Draco Meteor', 'Flash Cannon', 'Flamethrower'], hp=0.8), mon('Scrafty', ['Drain Punch', 'Knock Off', 'Ice Punch', 'Bulk Up'], hp=0.7)],
      best=['Flash Cannon>Togekiss'], bad=['Draco Meteor>Togekiss'], double=True,
      checks=[('mko', 'e0', 'Flash Cannon', 'p0'), ('mko', 'e0', 'Flamethrower', 'p1'), ('b04a_ko', 'p0', 'DazzlngGleam', 'e0'),
              ('b04a_ko', 'p0', 'DazzlngGleam', 'e1'), ('b04a_reach', 'p0', 'DazzlngGleam', 'p1', False), ('mko', 'p1', 'Close Combat', 'e0'),
              ('mfaster', 'e0', 'p0'), ('mfaster', 'e0', 'p1'), ('mfaster', 'p0', 'e1'), ('meff', 'e0', 'Draco Meteor', 'p0', 0.0),
              ('mnoko', 'e0', 'Dark Pulse', 'p0')]),

    S('b04a_explosion_hits_partner', 'doubles',
      "Electrode at 30% is the fastest and Thunderbolt (4x) KOs Gyarados at 90%. Explosion hits every other Pokemon: Jellicent is "
      "a Ghost and takes nothing, Gyarados survives it, and partner Alakazam at 50% is knocked out, so it trades Electrode and "
      "Alakazam for no KO",
      [mon('Gyarados', ['Waterfall', 'Earthquake', 'Ice Fang', 'Dragon Dance'], hp=0.9), mon('Jellicent', ['Scald', 'Shadow Ball', 'Will-O-Wisp', 'Recover'])],
      [mon('Electrode', ['Explosion', 'Thunderbolt', 'Volt Switch', 'Thunder Wave'], hp=0.3), mon('Alakazam', ['Psychic', 'Shadow Ball', 'Focus Blast', 'Calm Mind'], hp=0.5)],
      best=['Thunderbolt>Gyarados'], bad=['Explosion'], double=True,
      checks=[('mko', 'e0', 'Thunderbolt', 'p0'), ('mfaster', 'e0', 'p0'), ('mfaster', 'e0', 'p1'), ('meff', 'e0', 'Explosion', 'p1', 0.0),
              ('b04a_noko', 'e0', 'Explosion', 'p0'), ('b04a_reach', 'e0', 'Explosion', 'e1', True), ('b04a_ko', 'e0', 'Explosion', 'e1'),
              ('mnoko', 'e1', 'Psychic', 'p0'), ('mnoko', 'e1', 'Shadow Ball', 'p0')]),

    S('b04a_stay_when_switch_eats_spread', 'doubles',
      "Abomasnow at 60% has Ice Beam (4x) for Salamence, but Salamence is faster and Flamethrower (4x) KOs it first. Heatran resists "
      "Ice, but Excadrill's Earthquake (every other Pokemon, Salamence immune) KOs it (4x) on the switch even with the spread "
      "reduction; partner Gardevoir cannot KO Abomasnow, and Dragon Dance leaves Salamence to Ice Beam",
      [mon('Abomasnow', ['Blizzard', 'Wood Hammer', 'Ice Beam', 'Giga Drain'], hp=0.6), mon('Excadrill', ['Earthquake', 'Iron Head', 'X-Scissor', 'Swords Dance'])],
      [mon('Salamence', ['Flamethrower', 'Dragon Claw', 'Fire Blast', 'Dragon Dance']), mon('Gardevoir', ['Psychic', 'Moonblast', 'Thunderbolt', 'Calm Mind']),
       mon('Heatran', ['Flamethrower', 'Earth Power', 'Flash Cannon', 'Protect'])],
      best=['Flamethrower>Abomasnow'], ok=['Fire Blast>Abomasnow'], bad=['switch:Heatran', 'Dragon Dance'], double=True,
      checks=[('mko', 'e0', 'Flamethrower', 'p0'), ('mko', 'e0', 'Fire Blast', 'p0'), ('acc_lt', 'Fire Blast', 100), ('mfaster', 'e0', 'p0'),
              ('mfaster', 'e0', 'p1'), ('mko', 'p0', 'Ice Beam', 'e0'), ('meff', 'p1', 'Earthquake', 'e0', 0.0), ('mnoko', 'p1', 'Iron Head', 'e0'),
              ('meff', 'p0', 'Ice Beam', 'e2', 0.25), ('b04a_ko', 'p1', 'Earthquake', 'e2'), ('mnoko', 'e1', 'Moonblast', 'p0'),
              ('mnoko', 'e0', 'Dragon Claw', 'p0')]),
])
