"""Batch 31 (draft): doubles against one trainer (`double=True`). Only enemy[0]'s turn-1 action is graded; enemy[1] acts too,
and each key holds whatever sensible move it makes, or it has one obviously best move.

Themes: the target judged by what each foe threatens against both of the AI's Pokemon; focusing with the partner or
splitting from it; Protect on turn 1, when the turn buys something and when it buys nothing; spread moves that hit the
partner or the AI's Pokemon itself.

Every key rests on the type chart, the stats, the Gen 5 damage formula, speed and priority. The doubles spread reduction
(0.75) was never measured in this ROM, so every claim about a spread move holds under both rules: sum_ko / sum_noko check
both, and a built-in noko uses full power. A target that faints before the AI's Pokemon moves may make its move retarget
(Gen 5) or fail: no best answer depends on which.
"""
from ai_checks import with_items
from ai_helpers import PLAIN, S, mon  # noqa: F401

SCENARIOS = with_items([
    # Protect is right: the partner removes the threat, but only after it has moved.
    S('b31_protect_partner_ko', 'doubles',
      'Sceptile is the fastest Pokemon out and Energy Ball (4x) knocks Quagsire out before it moves, so no attack Quagsire '
      'picks ever happens. Protect blocks it; Sceptile\'s moves barely touch Altaria (Grass '
      'resisted, Dragon cannot touch a Fairy), and Altaria, faster than Bronzong, knocks Sceptile out with Ice Beam (4x) this '
      'turn. Bronzong cannot KO Quagsire, so next turn Quagsire is free',
      [mon('Sceptile', ['Energy Ball', 'Leaf Storm', 'Dragon Pulse', 'Focus Blast']),
       mon('Bronzong', ['Iron Head', 'Psychic', 'Earthquake'])],
      [mon('Quagsire', ['Earthquake', 'Ice Beam', 'Waterfall', 'Protect']),
       mon('Altaria', ['Ice Beam', 'Moonblast'])],
      best=['Protect'], bad=['Earthquake', 'Ice Beam', 'Waterfall'], double=True,
      checks=[('faster', 'p0', 'e0'), ('faster', 'p0', 'e1'), ('ko', 'p0', 'Energy Ball', 'e0'),
              ('noko', 'p0', 'Energy Ball', 'e1'), ('noko', 'p0', 'Leaf Storm', 'e1'), ('noko', 'p0', 'Focus Blast', 'e1'),
              ('eff', 'p0', 'Dragon Pulse', 'e1', 0.0),
              ('faster', 'e1', 'p1'), ('ko', 'e1', 'Ice Beam', 'p0'),
              ('noko', 'p1', 'Psychic', 'e0'), ('noko', 'p1', 'Iron Head', 'e0'), ('noko', 'p1', 'Earthquake', 'e0')]),

    # Protect is right: the threat faints to its own end-of-turn damage.
    S('b31_protect_sand_burn', 'doubles',
      'Galvantula at 10% is burned and Hippowdon\'s Sand Stream is up, so the end-of-turn damage knocks it out this turn '
      'whatever happens; but it is faster than Pelipper and Thunderbolt (4x) knocks Pelipper out first, so no attack '
      'Pelipper picks ever happens. Protect wastes Galvantula\'s last move: its Electric moves cannot touch Hippowdon and '
      'Bug Buzz does little, and Clefable cannot KO Pelipper',
      [mon('Galvantula', ['Thunderbolt', 'Bug Buzz', 'Thunder'], hp=0.1, status='brn'),
       mon('Clefable', ['Moonblast', 'Flamethrower', 'Calm Mind'])],
      [mon('Pelipper', ['Hurricane', 'Scald', 'Ice Beam', 'Protect']),
       mon('Hippowdon', ['Earthquake', 'Stone Edge'], ability='Sand Stream')],
      best=['Protect'], bad=['Hurricane', 'Scald', 'Ice Beam'], double=True,
      checks=[('has_status', 'p0', 'brn'), ('weather', 'sand'), ('dbl_chip_kos', 'p0'),
              ('faster', 'p0', 'e0'), ('ko', 'p0', 'Thunderbolt', 'e0'),
              ('eff', 'p0', 'Thunderbolt', 'e1', 0.0), ('eff', 'p0', 'Thunder', 'e1', 0.0), ('noko', 'p0', 'Bug Buzz', 'e1'),
              ('noko', 'p1', 'Moonblast', 'e0'), ('noko', 'p1', 'Flamethrower', 'e0')]),

    # Protect is wrong, and the target is the spread user; the partner already handles the other foe.
    S('b31_ko_gleam_user_not_protect', 'doubles',
      'Gardevoir at 60% knocks Haxorus out with Moonblast (4x) and Dazzling Gleam hits both, but Haxorus is faster and Iron '
      'Head (2x) knocks Gardevoir out first. Protect only delays that KO and lets Gardevoir and Bisharp knock out Hariyama '
      'before it moves; Hariyama\'s Close Combat (4x) already knocks out Bisharp, so Close Combat on Bisharp leaves Gardevoir '
      'free to KO Haxorus; Dragon Claw cannot touch a Fairy',
      [mon('Gardevoir', ['DazzlngGleam', 'Moonblast', 'Psychic', 'Thunderbolt'], hp=0.6),
       mon('Bisharp', ['Iron Head', 'Sucker Punch', 'Knock Off', 'Swords Dance'])],
      [mon('Haxorus', ['Iron Head', 'Close Combat', 'Dragon Claw', 'Protect']),
       mon('Hariyama', ['Close Combat', 'Knock Off'])],
      best=['Iron Head>Gardevoir'], bad=['Protect', 'Close Combat>Bisharp', 'Dragon Claw>Gardevoir'], double=True,
      checks=[('faster', 'e0', 'p0'), ('ko', 'e0', 'Iron Head', 'p0'), ('ko', 'p0', 'Moonblast', 'e0'),
              ('eff', 'e0', 'Dragon Claw', 'p0', 0.0), ('ko', 'e1', 'Close Combat', 'p1'),
              ('noko', 'p1', 'Iron Head', 'e0'), ('noko', 'p1', 'Sucker Punch', 'e0'), ('noko', 'p1', 'Iron Head', 'e1'),
              ('noko', 'e1', 'Knock Off', 'p0'),
              ('faster', 'p0', 'e1'), ('faster', 'p1', 'e1'), ('sum_ko', 'e1', (('p0', 'Moonblast'), ('p1', 'Iron Head')))]),

    # Protect is wrong: the partner removes the threat before it moves; split from the partner.
    S('b31_partner_first_no_protect', 'doubles',
      'Volcarona at 45% is faster than Scizor and Fiery Dance (4x) would knock it out, but Starmie is faster still and Scald '
      '(2x) knocks Volcarona out first, so Protect wastes the turn: Whimsicott barely scratches Scizor and cannot KO Starmie. '
      'Scizor\'s moves are resisted by Volcarona, which is gone before Scizor moves anyway: Iron Head (2x) on Whimsicott',
      [mon('Volcarona', ['Fiery Dance', 'Bug Buzz', 'Giga Drain', 'Quiver Dance'], hp=0.45),
       mon('Whimsicott', ['Moonblast', 'Energy Ball'])],
      [mon('Scizor', ['Iron Head', 'Bullet Punch', 'X-Scissor', 'Protect']),
       mon('Starmie', ['Scald', 'Recover'])],
      best=['Iron Head>Whimsicott'], ok=['Bullet Punch>Whimsicott', 'X-Scissor>Whimsicott'], bad=['Protect'], double=True,
      checks=[('faster', 'p0', 'e0'), ('ko', 'p0', 'Fiery Dance', 'e0'),
              ('faster', 'e1', 'p0'), ('ko', 'e1', 'Scald', 'p0'), ('faster', 'e1', 'e0'),
              ('noko', 'p1', 'Moonblast', 'e1'), ('noko', 'p1', 'Energy Ball', 'e1'),
              ('noko', 'p1', 'Moonblast', 'e0'), ('noko', 'p1', 'Energy Ball', 'e0'),
              ('eff', 'e0', 'Iron Head', 'p0', 0.5), ('eff', 'e0', 'X-Scissor', 'p0', 0.5), ('eff', 'e0', 'Iron Head', 'p1', 2.0),
              ('beats', 'e0', 'Iron Head', 'Bullet Punch', 'p1'), ('beats', 'e0', 'Iron Head', 'X-Scissor', 'p1')]),

    # Focus with the partner: only the two hits together knock out the big threat.
    S('b31_focus_with_partner', 'doubles',
      'Chandelure is slower than both of the AI\'s Pokemon and Flamethrower knocks out either. Neither Lucario\'s nor '
      'Froslass\'s Shadow Ball (2x) knocks it out alone, but the two together do, and Froslass\'s only move cannot touch '
      'Porygon2 (Normal), so it will hit Chandelure: Lucario should hit it too. Close Combat surely knocks out Porygon2, but '
      'then Chandelure takes Lucario or Froslass, while Porygon2 can barely hurt either',
      [mon('Chandelure', ['Flamethrower', 'Heat Wave', 'Shadow Ball', 'Energy Ball']),
       mon('Porygon2', ['Tri Attack', 'Ice Beam', 'Recover'], hp=0.9)],
      [mon('Lucario', ['Shadow Ball', 'Close Combat', 'Flash Cannon', 'Swords Dance']),
       mon('Froslass', ['Shadow Ball'])],
      best=['Shadow Ball>Chandelure'], bad=['Shadow Ball>Porygon2', 'Close Combat>Chandelure', 'Swords Dance'], double=True,
      checks=[('faster', 'e0', 'p0'), ('faster', 'e1', 'p0'), ('ko', 'p0', 'Flamethrower', 'e0'), ('ko', 'p0', 'Flamethrower', 'e1'),
              ('sum_ko', 'p0', (('e0', 'Shadow Ball'), ('e1', 'Shadow Ball'))),
              ('sum_noko', 'p0', (('e0', 'Shadow Ball'),)), ('sum_noko', 'p0', (('e1', 'Shadow Ball'),)),
              ('eff', 'e1', 'Shadow Ball', 'p1', 0.0), ('eff', 'e0', 'Close Combat', 'p0', 0.0), ('ko', 'e0', 'Close Combat', 'p1'),
              ('noko', 'p1', 'Tri Attack', 'e0'), ('eff', 'p1', 'Tri Attack', 'e1', 0.0),
              ('noko', 'p1', 'Ice Beam', 'e0'), ('noko', 'p1', 'Ice Beam', 'e1')]),

    # Focus with the partner's spread move: its chip and the AI's hit together knock out the big threat.
    S('b31_finish_with_partner_gleam', 'doubles',
      'Tyranitar at 78% is slower than both of the AI\'s Pokemon and Crunch knocks out Alakazam. Sylveon\'s only move, '
      'Dazzling Gleam, hits both foes but does not knock Tyranitar out alone, and neither does Energy Ball (2x); together '
      'they do, even with the spread reduction. Psychic surely knocks out Primeape, whose Fighting moves barely hurt either '
      'of the AI\'s Pokemon, but then Tyranitar survives the Gleam and takes Alakazam; Psychic cannot touch a Dark type',
      [mon('Tyranitar', ['Crunch', 'Iron Head', 'Stone Edge'], hp=0.78),
       mon('Primeape', ['Close Combat', 'Drain Punch', 'Bulk Up'])],
      [mon('Alakazam', ['Psychic', 'Energy Ball', 'Shadow Ball', 'Calm Mind']),
       mon('Sylveon', ['DazzlngGleam'])],
      best=['Energy Ball>Tyranitar'], bad=['Psychic>Tyranitar', 'Calm Mind'], double=True,
      checks=[('faster', 'e0', 'p0'), ('faster', 'e1', 'p0'), ('ko', 'p0', 'Crunch', 'e0'),
              ('sum_ko', 'p0', (('e0', 'Energy Ball'), ('e1', 'DazzlngGleam'))),
              ('sum_noko', 'p0', (('e0', 'Energy Ball'),)), ('sum_noko', 'p0', (('e1', 'DazzlngGleam'),)),
              ('eff', 'e0', 'Psychic', 'p0', 0.0), ('ko', 'e0', 'Psychic', 'p1'),
              ('noko', 'p1', 'Close Combat', 'e0'), ('noko', 'p1', 'Close Combat', 'e1'),
              ('noko', 'p1', 'Drain Punch', 'e0'), ('noko', 'p1', 'Drain Punch', 'e1')]),

    # Target by threat: the spread move that hits both is not the threat; the single-target KO is.
    S('b31_spread_threat_not_ko', 'doubles',
      'Raichu is the fastest Pokemon out and Thunderbolt knocks out either foe. Mantine\'s Muddy Water hits both of the AI\'s '
      'Pokemon but cannot knock out either, even without the spread reduction, while Crawdaunt\'s Crunch (2x) knocks out '
      'Espeon, whose Psychic cannot touch it: Thunderbolt on Crawdaunt, although the 4x hit on Mantine looks bigger',
      [mon('Mantine', ['Muddy Water', 'Air Slash', 'Haze'], hp=0.7),
       mon('Crawdaunt', ['Crunch', 'Aqua Tail', 'Knock Off'], hp=0.85)],
      [mon('Raichu', ['Thunderbolt', 'Focus Blast', 'Nasty Plot']),
       mon('Espeon', ['Psychic', 'Calm Mind'], hp=0.85)],
      best=['Thunderbolt>Crawdaunt'], bad=['Nasty Plot'], double=True,
      checks=[('faster', 'e0', 'p0'), ('faster', 'e0', 'p1'), ('ko', 'e0', 'Thunderbolt', 'p0'), ('ko', 'e0', 'Thunderbolt', 'p1'),
              ('eff', 'e0', 'Thunderbolt', 'p0', 4.0),
              ('sum_noko', 'e0', (('p0', 'Muddy Water'),)), ('sum_noko', 'e1', (('p0', 'Muddy Water'),)),
              ('noko', 'p0', 'Air Slash', 'e1'), ('noko', 'p0', 'Air Slash', 'e0'),
              ('ko', 'p1', 'Crunch', 'e1'), ('eff', 'e1', 'Psychic', 'p1', 0.0),
              ('noko', 'p1', 'Crunch', 'e0'), ('noko', 'p1', 'Aqua Tail', 'e0'), ('noko', 'p1', 'Knock Off', 'e0')]),

    # Target by threat: the 4x decoy is harmless; the real threat is hidden in an item.
    S('b31_specs_threat_over_4x', 'doubles',
      'Staraptor is the fastest Pokemon out and knocks out either foe: Close Combat (4x) on Bastiodon or Brave Bird (2x) on '
      'Roserade. Bastiodon is harmless, but Roserade holds Choice Specs and its boosted Sludge Bomb or Energy Ball (2x) knocks '
      'out Milotic at 80% before Milotic moves, a KO it would not have without the item: Brave Bird on Roserade (Staraptor '
      'survives the recoil)',
      [mon('Roserade', ['Sludge Bomb', 'Energy Ball', 'Shadow Ball'], item='Choice Specs'),
       mon('Bastiodon', ['Iron Head', 'Rock Slide', 'Flash Cannon'])],
      [mon('Staraptor', ['Close Combat', 'Brave Bird', 'Quick Attack']),
       mon('Milotic', ['Scald', 'Moonblast', 'Recover'], hp=0.8)],
      best=['Brave Bird>Roserade'], double=True,
      checks=[('faster', 'e0', 'p0'), ('faster', 'p0', 'e1'), ('mko', 'e0', 'Brave Bird', 'p0'), ('mko', 'e0', 'Close Combat', 'p1'),
              ('survives_recoil', 'e0', 'Brave Bird', 'p0'), ('has_item', 'p0', 'Choice Specs'),
              ('mko', 'p0', 'Sludge Bomb', 'e1'), ('mko', 'p0', 'Energy Ball', 'e1'),
              ('noko', 'p0', 'Sludge Bomb', 'e1'), ('noko', 'p0', 'Energy Ball', 'e1'), ('mnoko', 'p0', 'Sludge Bomb', 'e0'),
              ('mnoko', 'p1', 'Flash Cannon', 'e0'), ('mnoko', 'p1', 'Flash Cannon', 'e1'), ('mnoko', 'p1', 'Iron Head', 'e1'),
              ('sum_noko', 'e1', (('p1', 'Rock Slide'),))]),

    # Protect is right, and the spread move is the partner's.
    S('b31_protect_from_partner_eq', 'doubles',
      'Landorus\'s only move is Earthquake, which hits every other Pokemon, and Landorus is faster than everyone: it knocks '
      'Magnezone (4x, no Levitate) out before Magnezone can act, whatever Magnezone picks, unless Magnezone uses Protect; the '
      'Earthquake also hits Magmortar and Luxray (2x each)',
      [mon('Magmortar', ['Flamethrower', 'Thunderbolt', 'Focus Blast']),
       mon('Luxray', ['Wild Charge', 'Crunch', 'Ice Fang'])],
      [mon('Magnezone', ['Thunderbolt', 'Flash Cannon', 'Protect']),
       mon('Landorus', ['Earthquake'])],
      best=['Protect'], bad=['Thunderbolt', 'Flash Cannon'], double=True,
      checks=[('faster', 'e1', 'e0'), ('faster', 'e1', 'p0'), ('faster', 'e1', 'p1'), ('has_ability', 'e0', 'Run Away'),
              ('sum_ko', 'e0', (('e1', 'Earthquake'),)),
              ('eff', 'e1', 'Earthquake', 'p0', 2.0), ('eff', 'e1', 'Earthquake', 'p1', 2.0)]),

    # The AI's own spread move hits its partner, which puts the partner in a foe's KO range.
    S('b31_eq_chips_partner', 'doubles',
      'Swampert is faster than both foes, and Rampardos at 50% falls to Waterfall or to Earthquake. Earthquake also hits '
      'Spiritomb (no KO) and partner Meowstic, and Spiritomb\'s Crunch (2x) then knocks out the damaged Meowstic, while from '
      'full HP Meowstic survives it and cannot hurt Spiritomb: Waterfall',
      [mon('Rampardos', ['Head Smash', 'Rock Slide', 'Earthquake'], hp=0.5),
       mon('Spiritomb', ['Crunch', 'Shadow Sneak', 'Will-O-Wisp'])],
      [mon('Swampert', ['Earthquake', 'Waterfall', 'Ice Punch']),
       mon('Meowstic', ['Psychic', 'Shadow Ball'])],
      best=['Waterfall>Rampardos'], bad=['Earthquake'], double=True,
      checks=[('faster', 'e0', 'p0'), ('faster', 'e0', 'p1'), ('ko', 'e0', 'Waterfall', 'p0'),
              ('sum_ko', 'p0', (('e0', 'Earthquake'),)), ('sum_noko', 'p1', (('e0', 'Earthquake'),)),
              ('sum_ko', 'e1', (('e0', 'Earthquake'), ('p1', 'Crunch'))),
              ('sum_noko', 'e1', (('p1', 'Crunch'),)), ('sum_noko', 'e1', (('p1', 'Shadow Sneak'),)),
              ('eff', 'e1', 'Psychic', 'p1', 0.0), ('noko', 'e1', 'Shadow Ball', 'p1')]),
])
