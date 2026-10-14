"""Batch 06, part b: setup that wins and setup that loses, and Trick Room for a slow team against one fast sweeper.

The b06_ ops are defined in draft_06a.py (batch_06a.py once the batch is final) and registered in ai_checks.CHECKS when that file
loads; it loads first when both are named, and this file loads it itself otherwise, before `with_items` runs.

Dragon Dance into Foul Play (a theme of the brief) is left out on purpose: with the bench's margins (the favored side's minimum x 0.9,
the other side's maximum x 1.1) no position can show both that attacking at once wins in two hits and that Dragon Dance then loses,
because the +1 attack would then knock out at once; a search of the ROM's data over 16 setup users and 8 Foul Play users found only
Swords Dance cases, which batch 03 already holds (b03_swords_dance_foul_play).
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
    # --- 3. setup that wins and setup that loses

    S('b06_smash_herb_wins', 'setup',
      'Rotom is faster than Cloyster and Thunderbolt (2x, 74-86%) wins the race if Cloyster attacks now, since no Cloyster attack '
      'KOs Rotom in one hit; after Shell Smash (+2 Attack, Sp. Atk and Speed; the White Herb restores the lowered Defense and Sp. Def) '
      'Cloyster outspeeds Rotom and a five-hit Skill Link Icicle Spear KOs it before it moves again (Shell Smash and White Herb '
      'follow the official rules, not measured in this ROM)',
      [mon('Rotom', ['Thunderbolt', 'Shadow Ball', 'Volt Switch', 'Pain Split'])],
      [mon('Cloyster', ['Shell Smash', 'Icicle Spear', 'Rock Blast', 'Hydro Pump'], ability='Skill Link', item='White Herb')],
      best=['Shell Smash'], bad=['Icicle Spear', 'Rock Blast', 'Hydro Pump'],
      checks=[('b06_faster', 'p0', 'e0'), ('b06_has_item', 'e0', 'White Herb'),
              ('b06_fight', 'e0', ('Shell Smash', 'Icicle Spear'), 'p0', '*', 2, 'win'),
              ('b06_fight', 'e0', 'Icicle Spear', 'p0', 'Thunderbolt', 6, 'lose'),
              ('b06_fight', 'e0', 'Rock Blast', 'p0', 'Thunderbolt', 6, 'lose'),
              ('b06_fight', 'e0', 'Hydro Pump', 'p0', 'Thunderbolt', 6, 'lose')]),
    S('b06_calm_mind_vs_physical', 'setup',
      'Infernape is faster than Reuniclus at 90%, and its strongest move, Flare Blitz (56-66%), is physical; Calm Mind raises only '
      'Sp. Atk and Sp. Def, so the second Flare Blitz KOs Reuniclus before the boosted Psychic lands; Psychic now (2x, 109-128%) KOs '
      'Infernape or leaves it to the next one, and Reuniclus survives the Flare Blitz in between',
      [mon('Infernape', ['Close Combat', 'Flare Blitz', 'ThunderPunch', 'Mach Punch'])],
      [mon('Reuniclus', ['Calm Mind', 'Psychic', 'Focus Blast', 'Shadow Ball'], hp=0.9)],
      best=['Psychic'], bad=['Calm Mind'],
      checks=[('b06_faster', 'p0', 'e0'), ('cls', 'Flare Blitz', 'physical'), ('b06_frac', 'p0', 'Flare Blitz', 'e0', 0.55, 0.7),
              ('b06_fight', 'e0', 'Psychic', 'p0', '*', 2, 'win'),
              ('b06_fight', 'e0', ('Calm Mind', 'Psychic'), 'p0', 'Flare Blitz', 4, 'lose')]),
    S('b06_sd_before_close_combat', 'setup',
      'Arcanine at 80% is faster than Snorlax but one Close Combat (2x, 59-70%) cannot KO it, and Close Combat lowers Arcanine\'s own '
      'Defense, after which Snorlax\'s Earthquake (2x) KOs it before the second Close Combat; Swords Dance first is safe, because '
      'Earthquake does at most 72%, and the +2 Close Combat then KOs Snorlax next turn before it moves; Flare Blitz and '
      'ExtremeSpeed lose the race too',
      [mon('Snorlax', ['Double-Edge', 'Earthquake', 'Crunch', 'Fire Punch'])],
      [mon('Arcanine', ['Swords Dance', 'Close Combat', 'Flare Blitz', 'ExtremeSpeed'], hp=0.8)],
      best=['Swords Dance'], bad=['Close Combat', 'Flare Blitz', 'ExtremeSpeed'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_noko', 'e0', 'Close Combat', 'p0'), ('b06_noko', 'p0', 'Earthquake', 'e0'),
              ('b06_fight', 'e0', ('Swords Dance', 'Close Combat'), 'p0', '*', 2, 'win'),
              ('b06_fight', 'e0', 'Close Combat', 'p0', 'Earthquake', 6, 'lose'),
              ('b06_fight', 'e0', 'Flare Blitz', 'p0', 'Earthquake', 6, 'lose'),
              ('b06_fight', 'e0', 'ExtremeSpeed', 'p0', 'Earthquake', 6, 'lose')]),

    # --- 4. Trick Room

    S('b06_trick_room_slow_team', 'utility',
      'Gengar outspeeds the AI\'s whole team, and its Focus Blast (4x) KOs Tyranitar before Tyranitar\'s Crunch (2x) can KO it; '
      'Bronzong survives Shadow Ball (72-85%), so Trick Room (priority -7) goes up this turn; Bronzong falls to the next Shadow Ball, '
      'and Tyranitar comes in with the room still running (turns 2 to 5, measured) and KOs Gengar with Crunch before it moves; '
      'switching to Tyranitar now loses it to Focus Blast (70%), and Iron Defense raises a stat none of Gengar\'s special attacks use',
      [mon('Gengar', ['Shadow Ball', 'Sludge Bomb', 'Focus Blast', 'Thunderbolt'])],
      [mon('Bronzong', ['Trick Room', 'Gyro Ball', 'Stealth Rock', 'Iron Defense']),
       mon('Tyranitar', ['Crunch', 'Stone Edge', 'Earthquake', 'Fire Punch'])],
      best=['Trick Room'], bad=['switch:Tyranitar', 'Iron Defense'],
      checks=[('b06_pri', 'e0', 'Trick Room', -7), ('cls', 'Shadow Ball', 'special'), ('cls', 'Sludge Bomb', 'special'),
              ('cls', 'Focus Blast', 'special'), ('cls', 'Thunderbolt', 'special'), ('b06_faster', 'p0', 'e0'), ('b06_noko', 'p0', 'Shadow Ball', 'e0'),
              ('b06_nhko', 'p0', 'Shadow Ball', 'e0', 2), ('b06_noko', 'e0', 'Gyro Ball', 'p0'), ('b06_faster', 'p0', 'e1'),
              ('b06_ko', 'p0', 'Focus Blast', 'e1'), ('b06_ko', 'e1', 'Crunch', 'p0'), ('b06_no_priority', 'p0')]),
    S('b06_trick_room_too_slow', 'utility',
      'Gardevoir at 50% is faster than Swampert at 90% and Energy Ball (4x) KOs it; Trick Room has priority -7, so Swampert\'s '
      'Earthquake, which KOs Gardevoir, lands first and the room never goes up (it would only make Swampert faster anyway); Moonblast '
      'and Psychic cannot KO Swampert',
      [mon('Swampert', ['Earthquake', 'Waterfall', 'Ice Punch', 'Stone Edge'], hp=0.9)],
      [mon('Gardevoir', ['Trick Room', 'Moonblast', 'Psychic', 'Energy Ball'], hp=0.5)],
      best=['Energy Ball'], bad=['Trick Room', 'Moonblast', 'Psychic'],
      checks=[('b06_faster', 'e0', 'p0'), ('b06_ko', 'e0', 'Energy Ball', 'p0'), ('b06_ko', 'p0', 'Earthquake', 'e0'),
              ('b06_pri', 'e0', 'Trick Room', -7), ('b06_noko', 'e0', 'Moonblast', 'p0'), ('b06_noko', 'e0', 'Psychic', 'p0')]),
])
