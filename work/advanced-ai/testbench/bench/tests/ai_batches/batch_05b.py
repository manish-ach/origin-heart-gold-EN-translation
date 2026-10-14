"""Batch 05, part b: the only answer to a foe in the back, faster sleep moves, and absorbing abilities on the AI's own side.

The b05_ ops are defined in draft_05a.py (batch_05a.py once the batch is final) and registered in ai_checks.CHECKS when that file
loads; it loads first when both are named, and this file loads it itself otherwise, before `with_items` runs.
"""
import importlib.util
import os

from ai_checks import CHECKS, with_items
from ai_helpers import PLAIN, S, mon  # noqa: F401

if 'b05_wins_after' not in CHECKS:
    _here = os.path.dirname(os.path.abspath(__file__))
    for _name in ('draft_05a.py', 'batch_05a.py'):
        if os.path.exists(os.path.join(_here, _name)):
            _spec = importlib.util.spec_from_file_location('ai_batch_05a_ops', os.path.join(_here, _name))
            _spec.loader.exec_module(importlib.util.module_from_spec(_spec))
            break

SCENARIOS = with_items([
    # --- 4. the only answer to a foe in the back

    S('b05_keep_only_answer', 'switch',
      "Tyranitar's sand is up and it is the AI's only answer to the player's Volcarona: at full HP it survives Bug Buzz and Rock "
      'Slide (4x) KOs it, while Rotom and Scizor lose to it; Gyarados is faster and Waterfall (2x) takes 66-79% of Tyranitar, '
      "after which Tyranitar falls to Volcarona's Bug Buzz before it moves; Rotom takes any Gyarados attack on the way in, "
      'outspeeds it and '
      'Thunderbolt (4x) KOs it, so Tyranitar stays healthy for Volcarona',
      [mon('Gyarados', ['Waterfall', 'Earthquake', 'Ice Fang', 'Stone Edge'], evs={'atk': 252}),
       mon('Volcarona', ['Fire Blast', 'Bug Buzz', 'Giga Drain', 'Quiver Dance'])],
      [mon('Tyranitar', ['Stone Edge', 'Rock Slide', 'Crunch', 'Stealth Rock'], ability='Sand Stream'),
       mon('Rotom', ['Thunderbolt', 'Shadow Ball', 'Will-O-Wisp', 'Volt Switch'], ability='Levitate'),
       mon('Scizor', ['Bullet Punch', 'Iron Head', 'Superpower', 'Swords Dance'])],
      best=['switch:Rotom'],
      checks=[('b05_weather', 'sand'), ('b05_faster', 'p0', 'e0'), ('b05_noko', 'p0', 'Waterfall', 'e0'),
              ('b05_frac', 'p0', 'Waterfall', 'e0', 0.6, 0.8),
              ('b05_race', 'e0', 'Rock Slide', 'p1', '*', 1),
              ('b05_loses_after', 'e0', '*', 'p1', 'Bug Buzz', [('p0', 'Waterfall', 'e0')]),
              ('b05_faster', 'e1', 'p0'),
              ('b05_wins_after', 'e1', 'Thunderbolt', 'p0', '*', 1, [('p0', '*', 'e1'), 'eot']),
              ('b05_loses', 'e1', '*', 'p1', 'Fire Blast'), ('b05_loses', 'e2', '*', 'p1', 'Fire Blast')]),

    # --- 5. a faster sleep move

    S('b05_vital_spirit_takes_powder', 'status',
      "Compoundeyes Butterfree is faster than Rhyperior and its Sleep Powder lands 97% of the time, before Rock Slide (4x) could "
      'KO it; Vital Spirit Electivire cannot fall asleep, survives any Butterfree attack, outspeeds it and ThunderPunch (2x) KOs '
      'it; Salamence would be put to sleep on the way in (Butterfree at level 45: since rc27 its base Speed is 100, and at the '
      'default level 50 it would outrun Electivire and survive ThunderPunch)',
      [mon('Butterfree', ['Sleep Powder', 'Quiver Dance', 'Bug Buzz', 'Psychic'], ability='Compoundeyes', level=45)],
      [mon('Rhyperior', ['Rock Slide', 'Earthquake', 'Megahorn', 'Stone Edge']),
       mon('Electivire', ['ThunderPunch', 'Ice Punch', 'Cross Chop', 'Earthquake'], ability='Vital Spirit'),
       mon('Salamence', ['Outrage', 'Earthquake', 'Fire Fang', 'Dragon Dance'])],
      best=['switch:Electivire'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_macc', 'p0', 'Sleep Powder', 'e0', 97),
              ('b05_sleep_lands', 'p0', 'Sleep Powder', 'e0'), ('b05_ko', 'e0', 'Rock Slide', 'p0'),
              ('b05_sleep_fails', 'p0', 'Sleep Powder', 'e1'), ('b05_faster', 'e1', 'p0'),
              ('b05_wins_after', 'e1', 'ThunderPunch', 'p0', '*', 1, [('p0', '*', 'e1'), 'eot']),
              ('b05_sleep_lands', 'p0', 'Sleep Powder', 'e2')]),
    S('b05_statused_takes_spore', 'status',
      'Smeargle is faster than Kingambit and Spore never misses; Sucker Punch fails against a status move, so Kingambit falls '
      'asleep whatever it picks; Gliscor is already poisoned (Poison Heal), so Spore cannot touch it, and it beats Smeargle; Lapras '
      'would be put to sleep on the way in',
      [mon('Smeargle', ['Spore', 'Stealth Rock', 'Sticky Web', 'Hyper Voice'])],
      [mon('Kingambit', ['Iron Head', 'Sucker Punch', 'Night Slash', 'Swords Dance']),
       mon('Gliscor', ['Earthquake', 'Acrobatics', 'Stone Edge', 'Roost'], ability='Poison Heal', status='psn'),
       mon('Lapras', ['Surf', 'Ice Beam', 'Thunderbolt', 'Psychic'])],
      best=['switch:Gliscor'], bad=['Sucker Punch'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_macc', 'p0', 'Spore', 'e0', 100), ('b05_sleep_lands', 'p0', 'Spore', 'e0'),
              ('pri', 'Sucker Punch', 1), ('b05_has_status', 'e1', 'psn'), ('b05_sleep_fails', 'p0', 'Spore', 'e1'),
              ('b05_wins_after', 'e1', 'Acrobatics', 'p0', '*', 2, [('p0', '*', 'e1'), 'eot']),
              ('b05_sleep_lands', 'p0', 'Spore', 'e2')]),
    S('b05_paralyzed_sleeper_slower', 'status',
      'Breloom has Spore and would outspeed Slowking, but it is paralyzed (a quarter or half Speed), so Slowking moves first and '
      'Psychic (2x) KOs it at 45% before Spore; Mach Punch has priority but is resisted; switching to the burned, sleep-proof '
      'Ursaring throws the KO away; Slack Off at full HP fails',
      [mon('Breloom', ['Spore', 'Seed Bomb', 'Mach Punch', 'Swords Dance'], status='par', hp=0.45)],
      [mon('Slowking', ['Psychic', 'Surf', 'Fire Blast', 'Slack Off']),
       mon('Ursaring', ['Facade', 'Close Combat', 'Crunch', 'Swords Dance'], ability='Guts', status='brn')],
      best=['Psychic'], ok=['Fire Blast'], bad=['switch:Ursaring', 'Slack Off'],
      checks=[('b05_has_status', 'p0', 'par'), ('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'Psychic', 'p0'),
              ('b05_ko', 'e0', 'Fire Blast', 'p0'), ('acc_lt', 'Fire Blast', 100), ('pri', 'Mach Punch', 1),
              ('b05_noko', 'p0', 'Mach Punch', 'e0'), ('b05_sleep_fails', 'p0', 'Spore', 'e1')]),
    S('b05_statused_stays_vs_powder', 'status',
      'Compoundeyes Vivillon is faster, but Conkeldurr is already burned (Guts, so its Attack rises), so Sleep Powder cannot touch '
      'it; Rock Slide (4x) KOs Vivillon after its best hit (Psychic, 2x) and the burn; switching to Lanturn only gives Vivillon a '
      'Pokemon to put to sleep',
      [mon('Vivillon', ['Sleep Powder', 'Quiver Dance', 'Bug Buzz', 'Psychic'], ability='Compoundeyes')],
      [mon('Conkeldurr', ['Rock Slide', 'Stone Edge', 'Drain Punch', 'Mach Punch'], ability='Guts', status='brn'),
       mon('Lanturn', ['Scald', 'Thunderbolt', 'Ice Beam', 'Volt Switch'])],
      best=['Rock Slide', 'Stone Edge'], bad=['switch:Lanturn'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_has_status', 'e0', 'brn'), ('b05_has_ability', 'e0', 'Guts'),
              ('b05_sleep_fails', 'p0', 'Sleep Powder', 'e0'), ('b05_ko', 'e0', 'Rock Slide', 'p0'),
              ('b05_race', 'e0', 'Rock Slide', 'p0', '*', 1), ('b05_sleep_lands', 'p0', 'Sleep Powder', 'e1')]),

    # --- 6. absorbing abilities on the AI's side

    S('b05_levitate_stays', 'ability',
      "Excadrill's Earthquake would be 2x on an Electric type, but Levitate Eelektross is immune and its other attacks do under a "
      'third; Thunderbolt and Volt Switch cannot touch a Ground type; Superpower (2x) wins the race in two hits, Flamethrower (2x) '
      'more slowly; Ampharos switched in takes a hit and then the faster Excadrill KOs it with Earthquake (2x)',
      [mon('Excadrill', ['Earthquake', 'Iron Head', 'Rock Slide', 'Swords Dance'])],
      [mon('Eelektross', ['Thunderbolt', 'Flamethrower', 'Superpower', 'Volt Switch'], ability='Levitate'),
       mon('Ampharos', ['Thunderbolt', 'Dragon Pulse', 'Focus Blast', 'Volt Switch'])],
      best=['Superpower'], ok=['Flamethrower'], bad=['Thunderbolt', 'Volt Switch', 'switch:Ampharos'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_absorbs', 'e0', 'p0', 'Earthquake'), ('b05_eff', 'p0', 'Earthquake', 'e0', 0.0),
              ('b05_eff', 'e0', 'Thunderbolt', 'p0', 0.0), ('b05_eff', 'e0', 'Volt Switch', 'p0', 0.0),
              ('b05_frac', 'p0', 'Rock Slide', 'e0', 0.2, 0.33), ('b05_frac', 'p0', 'Iron Head', 'e0', 0.15, 0.33),
              ('b05_race', 'e0', 'Superpower', 'p0', '*', 2), ('b05_race', 'e0', 'Flamethrower', 'p0', '*', 3),
              ('b05_loses_after', 'e1', '*', 'p0', 'Earthquake', [('p0', '*', 'e1'), 'eot'])]),
    S('b05_sap_sipper_stays', 'ability',
      "Breloom's Seed Bomb would be 2x on Water-type Azumarill, but Sap Sipper takes it; Mach Punch is resisted and Rock Tomb does "
      'under a quarter, so Azumarill stays and Play Rough (2x) wins in three hits; Rhydon switched in takes a hit and the faster '
      'Breloom KOs it with Seed Bomb (4x) the next turn',
      [mon('Breloom', ['Seed Bomb', 'Mach Punch', 'Rock Tomb', 'Swords Dance'])],
      [mon('Azumarill', ['Play Rough', 'Aqua Jet', 'Waterfall', 'Superpower'], ability='Sap Sipper'),
       mon('Rhydon', ['Earthquake', 'Stone Edge', 'Megahorn', 'Swords Dance'])],
      best=['Play Rough'], bad=['switch:Rhydon'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_absorbs', 'e0', 'p0', 'Seed Bomb'), ('b05_eff', 'p0', 'Seed Bomb', 'e0', 0.0),
              ('b05_eff', 'p0', 'Mach Punch', 'e0', 0.5), ('b05_frac', 'p0', 'Rock Tomb', 'e0', 0.15, 0.25),
              ('b05_race', 'e0', 'Play Rough', 'p0', '*', 3), ('b05_faster', 'p0', 'e1'),
              ('b05_loses_after', 'e1', '*', 'p0', 'Seed Bomb', [('p0', '*', 'e1'), 'eot'])]),
    S('b05_sap_sipper_switch', 'ability',
      "Roserade outspeeds Whiscash and Leaf Storm (4x) KOs it; Seismitoad is also Ground/Water, 4x weak to Grass on paper, but Sap "
      'Sipper takes Leaf Storm, and Sludge Bomb and Shadow Ball do under 30%, so it wins the race with Earthquake',
      [mon('Roserade', ['Leaf Storm', 'Sludge Bomb', 'Shadow Ball', 'Spikes'])],
      [mon('Whiscash', ['Earthquake', 'Waterfall', 'Stone Edge', 'Dragon Dance']),
       mon('Seismitoad', ['Earthquake', 'Waterfall', 'Poison Jab', 'Stealth Rock'], ability='Sap Sipper'),
       mon('Walrein', ['Surf', 'Ice Beam', 'Toxic', 'Protect'])],
      best=['switch:Seismitoad'], bad=['Earthquake', 'Waterfall', 'Stone Edge', 'Dragon Dance'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Leaf Storm', 'e0'), ('b05_absorbs', 'e1', 'p0', 'Leaf Storm'),
              ('b05_eff', 'p0', 'Leaf Storm', 'e1', 0.0), ('b05_frac', 'p0', 'Shadow Ball', 'e1', 0.15, 0.3),
              ('b05_frac', 'p0', 'Sludge Bomb', 'e1', 0.15, 0.3),
              ('b05_wins_after', 'e1', 'Earthquake', 'p0', '*', 3, [('p0', 'Leaf Storm', 'e1'), 'eot'])]),
    S('b05_flash_fire_over_resist', 'ability',
      "Volcarona outspeeds Forretress and Fire Blast (4x) KOs it; Slowbro resists Fire, but Bug Buzz (2x) KOs it next; Flash Fire "
      'Heatran takes Fire Blast for nothing, resists Bug Buzz and Giga Drain to a quarter (about a tenth a turn), and wins with '
      'Flamethrower whatever Volcarona uses',
      [mon('Volcarona', ['Fire Blast', 'Bug Buzz', 'Giga Drain', 'Quiver Dance'])],
      [mon('Forretress', ['Gyro Ball', 'Volt Switch', 'Spikes', 'Rapid Spin']),
       mon('Heatran', ['Flamethrower', 'Earth Power', 'Stone Edge', 'Flash Cannon'], ability='Flash Fire'),
       mon('Slowbro', ['Scald', 'Psychic', 'Fire Blast', 'Slack Off'])],
      best=['switch:Heatran'], bad=['switch:Slowbro', 'Gyro Ball', 'Volt Switch', 'Spikes', 'Rapid Spin'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Fire Blast', 'e0'), ('b05_absorbs', 'e1', 'p0', 'Fire Blast'),
              ('b05_eff', 'p0', 'Bug Buzz', 'e1', 0.25), ('b05_eff', 'p0', 'Giga Drain', 'e1', 0.25),
              ('b05_wins_after', 'e1', 'Flamethrower', 'p0', '*', 4, [('p0', '*', 'e1'), 'eot']),
              ('b05_eff', 'p0', 'Fire Blast', 'e2', 0.5),
              ('b05_loses_after', 'e2', '*', 'p0', 'Bug Buzz', [('p0', '*', 'e2'), 'eot'])]),
])
