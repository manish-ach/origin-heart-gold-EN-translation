"""Batch 06, part c: single-battle rules. A powder move into a Grass type, Thunder Wave into Motor Drive, Endeavor when the user
has more HP, Sucker Punch against a foe that can only use a status move, Glaive Rush against a faster foe (on the field, and as the
next Pokemon in), and the opposite of both (Sucker Punch against a foe that can only attack, Glaive Rush when the next foe is
slower), a Skill Link multi-hit move against a Focus Sash behind Wonder Guard.

The b06_ ops are defined in draft_06a.py (batch_06a.py once the batch is final); see draft_06b.py for how they are loaded. Keys that
rest on a rule nobody measured in this ROM say so in their description ("not measured").
"""
import importlib.util
import os

from ai_checks import CHECKS, with_items
from ai_helpers import PLAIN, S, mon  # noqa: F401

if 'b06_fight' not in CHECKS:
    _here = os.path.dirname(os.path.abspath(__file__))
    for _name in ('draft_06a.py', 'batch_06a.py'):
        if os.path.exists(os.path.join(_here, _name)):
            _spec = importlib.util.spec_from_file_location('ai_batch_06a_ops', os.path.join(_here, _name))
            _spec.loader.exec_module(importlib.util.module_from_spec(_spec))
            break

SCENARIOS = with_items([
    S('b06_powder_into_grass', 'rules',
      'Venusaur is faster than Exeggutor and Sludge Bomb (2x) wins the race in two hits, while Venusaur survives one Psychic (2x); '
      'Exeggutor is a Grass type, so Sleep Powder does nothing (the Gen 6 powder rule; the ROM flags powder moves, but the rule is not '
      'measured in this hack), and the lost turn lets the second Psychic KO Venusaur first',
      [mon('Exeggutor', ['Psychic', 'Leaf Storm', 'Flamethrower', 'Giga Drain'])],
      [mon('Venusaur', ['Sleep Powder', 'Sludge Bomb', 'Giga Drain', 'Earth Power'])],
      best=['Sludge Bomb'], bad=['Sleep Powder'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_powder_immune', 'e0', 'Sleep Powder', 'p0'), ('b06_noko', 'e0', 'Sludge Bomb', 'p0'),
              ('b06_fight', 'e0', 'Sludge Bomb', 'p0', '*', 2, 'win'),
              ('b06_fight', 'e0', ('Sleep Powder', 'Sludge Bomb'), 'p0', 'Psychic', 3, 'lose')]),
    S('b06_twave_motor_drive', 'rules',
      'Alakazam is faster than Zebstrika and Psychic wins the race in two hits; Zebstrika has Motor Drive and is an Electric type, so '
      'Thunder Wave does nothing but raise its Speed by one stage, after which Zebstrika moves first and two Wild Charges KO Alakazam '
      '(Motor Drive taking Thunder Wave is the Gen 4-5 rule, and Gen 6 Electric types cannot be paralyzed; not measured in this ROM)',
      [mon('Zebstrika', ['Wild Charge', 'Overheat', 'Volt Switch', 'Flame Charge'], ability='Motor Drive')],
      [mon('Alakazam', ['Thunder Wave', 'Psychic', 'Shadow Ball', 'DazzlngGleam'])],
      best=['Psychic'], bad=['Thunder Wave'],
      checks=[('b06_faster', 'e0', 'p0'), ('b05_absorbs', 'p0', 'e0', 'Thunder Wave'), ('type', 'p0', 'Electric'),
              ('b06_fight', 'e0', 'Psychic', 'p0', '*', 2, 'win'),
              ('b06_fight', 'e0', ('Thunder Wave', 'Psychic'), 'p0', 'Wild Charge', 3, 'lose')]),
    S('b06_endeavor_more_hp', 'rules',
      'Ambipom at 45 HP (30%) is faster than Mr. Mime at 44 HP (33%); Endeavor sets the target\'s HP to the user\'s, so it does '
      'nothing when the user has as much HP or more, whatever the percentages; Technician Double Hit and Fake Out each KO Mr. Mime',
      [mon('Mr. Mime', ['Psychic', 'Moonblast', 'Focus Blast', 'Reflect'], hp=44)],
      [mon('Ambipom', ['Endeavor', 'Double Hit', 'Knock Off', 'Fake Out'], ability='Technician', hp=45)],
      best=['Double Hit', 'Fake Out'], bad=['Endeavor'],
      checks=[('b06_endeavor_fails', 'e0', 'p0'), ('b06_ko', 'e0', 'Double Hit', 'p0'), ('b06_ko', 'e0', 'Fake Out', 'p0')]),
    S('b06_sucker_vs_immune_foe', 'rules',
      'Espeon at 85% is faster than Absol, but Absol is Fairy/Dark in this hack and Espeon\'s two attacks are Psychic moves that '
      'cannot touch it, so Espeon\'s reply is a status move; Sucker Punch, which would KO it first, fails against a status move; '
      'Night Slash (2x) KOs Espeon after it moves',
      [mon('Espeon', ['Psychic', 'Psyshock', 'Calm Mind', 'Light Screen'], hp=0.85)],
      [mon('Absol', ['Sucker Punch', 'Night Slash', 'Play Rough', 'Swords Dance'])],
      best=['Night Slash'], bad=['Sucker Punch'],
      checks=[('b06_faster', 'p0', 'e0'), ('b06_no_attack_lands', 'p0', 'e0'), ('b06_ko', 'e0', 'Night Slash', 'p0'),
              ('b06_ko', 'e0', 'Sucker Punch', 'p0'), ('b06_pri', 'e0', 'Sucker Punch', 1)]),
    S('b06_glaive_rush_race', 'rules',
      'Starmie is faster than Garchomp at 156 HP, and Surf or Psychic does 32-38%; Earthquake (62-73%) wins in two turns while '
      'Garchomp survives two hits; Glaive Rush hits harder (74-87%) but cannot KO, and the next Surf, which comes before Garchomp moves '
      'again, does double damage and KOs it (seen in this hack\'s logs, round S2 analyst 2, not measured)',
      [mon('Starmie', ['Surf', 'Psychic', 'Thunderbolt', 'Rapid Spin'])],
      [mon('Garchomp', ['Glaive Rush', 'Earthquake', 'Dragon Claw', 'Stone Edge'], evs={'atk': 252}, hp=156)],
      best=['Earthquake'], bad=['Glaive Rush'],
      checks=[('b06_faster', 'p0', 'e0'), ('b06_noko', 'e0', 'Glaive Rush', 'p0'), ('b06_frac', 'e0', 'Glaive Rush', 'p0', 0.7, 0.9),
              ('b06_fight', 'e0', 'Earthquake', 'p0', '*', 2, 'win'),
              ('b06_fight', 'e0', 'Glaive Rush', 'p0', 'Surf', 3, 'lose'),
              ('b06_fight', 'e0', 'Glaive Rush', 'p0', 'Psychic', 3, 'lose')]),
    S('b06_glaive_rush_replacement', 'rules',
      'Baxcalibur is faster than Dragonite, and Glaive Rush (2x) or Icicle Crash (4x, 90%) KOs it; the player\'s next Pokemon is '
      'Infernape, faster than Baxcalibur, whose Close Combat (2x, 71-85%) cannot KO it, but after Glaive Rush that hit comes before '
      'Baxcalibur moves again, does double damage and KOs it (seen in this hack\'s logs, round S2 analyst 2, not measured); '
      'Earthquake cannot touch a Flying type',
      [mon('Dragonite', ['Dragon Claw', 'Earthquake', 'Fire Punch', 'Roost']),
       mon('Infernape', ['Close Combat', 'Flare Blitz', 'Mach Punch', 'ThunderPunch'])],
      [mon('Baxcalibur', ['Glaive Rush', 'Icicle Crash', 'Ice Shard', 'Earthquake'], evs={'def': 252})],
      best=['Icicle Crash'], bad=['Glaive Rush', 'Earthquake'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_ko', 'e0', 'Glaive Rush', 'p0'), ('b06_ko', 'e0', 'Icicle Crash', 'p0'),
              ('b06_eff', 'e0', 'Earthquake', 'p0', 0.0), ('b06_glaive_punished', 'p1', 'Close Combat', 'e0')]),
    S('b06_skill_link_sash_guard', 'rules',
      'Shedinja has Wonder Guard and a Focus Sash: only super effective moves touch it, and a single hit leaves it at 1 HP; Skill Link '
      'Rock Blast (2x, five hits, 90%) breaks the Sash with the first hit and KOs with the next; Knock Off is super effective too but '
      'hits once, so the Sash holds; Tail Slap and U-turn are not super effective and Wonder Guard blocks them',
      [mon('Shedinja', ['X-Scissor', 'Shadow Sneak', 'Will-O-Wisp', 'Swords Dance'], ability='Wonder Guard', item='Focus Sash')],
      [mon('Cinccino', ['Rock Blast', 'Tail Slap', 'Knock Off', 'U-turn'], ability='Skill Link')],
      best=['Rock Blast'], bad=['Tail Slap', 'U-turn'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_multi_breaks', 'e0', 'Rock Blast', 'p0'), ('b06_single_held', 'e0', 'Knock Off', 'p0'),
              ('b06_eff', 'e0', 'Tail Slap', 'p0', 0.0), ('b06_eff', 'e0', 'U-turn', 'p0', 0.0)]),
    S('b06_sucker_vs_all_attacks', 'priority',
      'Mewtwo at 50% is faster than Kingambit and Aura Sphere (4x, never misses) KOs it; all four of Mewtwo\'s moves are attacks, so it '
      'attacks this turn and Sucker Punch (2x, priority) KOs it first; Night Slash also KOs but comes after Aura Sphere, and Iron Head '
      'does not KO',
      [mon('Mewtwo', ['Psychic', 'Aura Sphere', 'Shadow Ball', 'Ice Beam'], hp=0.5)],
      [mon('Kingambit', ['Sucker Punch', 'Iron Head', 'Night Slash', 'Swords Dance'])],
      best=['Sucker Punch'], bad=['Night Slash', 'Iron Head', 'Swords Dance'],
      checks=[('b06_faster', 'p0', 'e0'), ('b06_attacks_only', 'p0'), ('b06_ko', 'p0', 'Aura Sphere', 'e0'),
              ('b06_ko', 'e0', 'Sucker Punch', 'p0'), ('b06_pri', 'e0', 'Sucker Punch', 1), ('b06_noko', 'e0', 'Iron Head', 'p0')]),
    S('b06_glaive_rush_safe', 'rules',
      'Salamence is faster than Goodra, whose Draco Meteor (2x) KOs Salamence, and only Glaive Rush (2x) KOs Goodra first; the '
      'player\'s other Pokemon, Snorlax, is slower than Salamence, so on the next turn Salamence moves again before Snorlax can hit '
      'it, and the double damage Glaive Rush leaves never comes into play (it would make Double-Edge a KO)',
      [mon('Goodra', ['Draco Meteor', 'Fire Blast', 'Sludge Bomb', 'Thunderbolt']),
       mon('Snorlax', ['Double-Edge', 'Earthquake', 'Crunch', 'Curse'])],
      [mon('Salamence', ['Glaive Rush', 'Earthquake', 'Fire Fang', 'Aerial Ace'])],
      best=['Glaive Rush'], bad=['Earthquake', 'Fire Fang', 'Aerial Ace'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_ko', 'e0', 'Glaive Rush', 'p0'), ('b06_noko', 'e0', 'Earthquake', 'p0'),
              ('b06_noko', 'e0', 'Fire Fang', 'p0'), ('b06_noko', 'e0', 'Aerial Ace', 'p0'), ('b06_ko', 'p0', 'Draco Meteor', 'e0'),
              ('b06_faster', 'e0', 'p1'), ('b06_no_priority', 'p1')]),
])
