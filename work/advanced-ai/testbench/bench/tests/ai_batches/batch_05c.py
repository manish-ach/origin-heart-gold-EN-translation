"""Batch 05, part c: single-battle rules. Thunder Wave and other Electric moves into an Electric absorber, Spore into Sap Sipper,
Weakness Policy, Prankster Will-O-Wisp against a physical attacker, Super Fang at low HP, Counter against a multi-hit move.

The b05_ ops are defined in draft_05a.py (batch_05a.py once the batch is final); see draft_05b.py for how they are loaded.
Keys that rest on a rule nobody measured in this ROM say so in their description ("not measured").
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
    S('b05_twave_volt_absorb', 'rules',
      'Raikou at 55% is faster and paralysis would flip the race, but it has Volt Absorb (and is an Electric type), so Thunder '
      'Wave does nothing (Gen 5 Volt Absorb or the Gen 6 Electric-type immunity; not measured in this ROM); Moonblast wins the '
      'race in two hits while Raikou needs three; Soft-Boiled at full HP fails',
      [mon('Raikou', ['Thunderbolt', 'Extrasensory', 'Shadow Ball', 'Scald'], ability='Volt Absorb', hp=0.55)],
      [mon('Clefable', ['Thunder Wave', 'Moonblast', 'Flamethrower', 'Soft-Boiled'])],
      best=['Moonblast'], bad=['Thunder Wave', 'Soft-Boiled'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_absorbs', 'p0', 'e0', 'Thunder Wave'), ('type', 'p0', 'Electric'),
              ('b05_race', 'e0', 'Moonblast', 'p0', '*', 2)]),
    S('b05_lightningrod_takes_all', 'rules',
      'Lightningrod Sceptile at 40% takes every Electric move: Thunderbolt, Volt Switch and Thunder Wave do nothing and raise its '
      'Sp. Atk (Gen 5 Lightningrod in a single battle; not measured in this ROM, and Sceptile is not an Electric type); Jolteon is '
      'faster and Shadow Ball KOs it in two hits, surviving any one hit in between (Earthquake, 2x, included)',
      [mon('Sceptile', ['Leaf Storm', 'Dragon Pulse', 'Focus Blast', 'Earthquake'], ability='Lightningrod', hp=0.4)],
      [mon('Jolteon', ['Thunderbolt', 'Thunder Wave', 'Shadow Ball', 'Volt Switch'])],
      best=['Shadow Ball'], bad=['Thunderbolt', 'Thunder Wave', 'Volt Switch'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_absorbs', 'p0', 'e0', 'Thunderbolt'), ('b05_absorbs', 'p0', 'e0', 'Thunder Wave'),
              ('b05_absorbs', 'p0', 'e0', 'Volt Switch'), ('b05_eff', 'e0', 'Thunderbolt', 'p0', 0.0),
              ('b05_race', 'e0', 'Shadow Ball', 'p0', '*', 2)]),
    S('b05_spore_sap_sipper', 'rules',
      'Sap Sipper Miltank takes Grass moves, Spore included, and raises its Attack (Gen 5; for Spore not measured in this ROM), so '
      'Spore and Seed Bomb are wasted; Breloom is faster and Close Combat (2x) KOs Miltank at 80%, which cannot KO Breloom',
      [mon('Miltank', ['Body Slam', 'Earthquake', 'Milk Drink', 'Heal Bell'], ability='Sap Sipper', hp=0.8)],
      [mon('Breloom', ['Spore', 'Close Combat', 'Seed Bomb', 'Mach Punch'])],
      best=['Close Combat'], bad=['Spore', 'Seed Bomb'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'Close Combat', 'p0'), ('b05_absorbs', 'p0', 'e0', 'Spore'),
              ('b05_absorbs', 'p0', 'e0', 'Seed Bomb'), ('b05_eff', 'e0', 'Seed Bomb', 'p0', 0.0),
              ('b05_noko', 'e0', 'Mach Punch', 'p0'), ('b05_noko', 'p0', 'Body Slam', 'e0')]),
    S('b05_wp_neutral_race', 'rules',
      'Golem holds Weakness Policy: Earth Power (2x) does the most but cannot KO it, so the policy fires (+4 Attack and Sp. Atk in '
      'this hack, measured) and Golem then KOs Hydreigon with Earthquake the same turn; Dragon Pulse and Dark Pulse are neutral, '
      'and the faster Hydreigon wins the race in three hits while Golem at +0 needs three too',
      [mon('Golem', ['Earthquake', 'Stone Edge', 'Rock Slide', 'Fire Punch'], item='Weak. Policy', evs={'hp': 252})],
      [mon('Hydreigon', ['Dragon Pulse', 'Dark Pulse', 'Earth Power', 'Flamethrower'], evs={'hp': 176})],
      best=['Dragon Pulse', 'Dark Pulse'], bad=['Earth Power'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_wp', 'e0', 'Earth Power', 'p0'), ('b05_beats', 'e0', 'Earth Power', 'Dragon Pulse', 'p0'),
              ('b05_boosted_ko', 'p0', 'Earthquake', 'e0', 4), ('b05_noko', 'p0', 'Earthquake', 'e0'),
              ('b05_no_wp', 'e0', 'Dragon Pulse', 'p0'), ('b05_no_wp', 'e0', 'Dark Pulse', 'p0'),
              ('b05_race', 'e0', 'Dragon Pulse', 'p0', '*', 3), ('b05_race', 'e0', 'Dark Pulse', 'p0', '*', 3)]),
    S('b05_prankster_wisp_special', 'rules',
      "Prankster Sableye at 48% has Will-O-Wisp, which goes first; Outrage would KO it unburned, but burned it cannot, and the "
      'burn lands before Outrage (85% accuracy); Draco Meteor is special and KOs it either way (90% accuracy); Earthquake and Fire '
      'Blast do not KO',
      [mon('Sableye', ['Will-O-Wisp', 'Foul Play', 'Shadow Ball', 'Taunt'], ability='Prankster', hp=0.48)],
      [mon('Dragonite', ['Outrage', 'Draco Meteor', 'Earthquake', 'Fire Blast'])],
      best=['Draco Meteor'],
      checks=[('b05_wisp_first', 'p0', 'e0'), ('b05_pri', 'p0', 'Will-O-Wisp', 1), ('cls', 'Draco Meteor', 'special'),
              ('b05_ko', 'e0', 'Draco Meteor', 'p0'), ('b05_ko', 'e0', 'Outrage', 'p0'), ('b05_noko_burned', 'e0', 'Outrage', 'p0'),
              ('b05_noko', 'e0', 'Earthquake', 'p0'), ('b05_noko', 'e0', 'Fire Blast', 'p0')]),
    S('b05_super_fang_no_ko', 'rules',
      'Snorlax at 25% would KO Raticate at 40% with Body Slam; Raticate is faster and Double-Edge KOs Snorlax, with recoil Raticate '
      'survives; Super Fang takes only half of what Snorlax has left (half its current HP, Gen 5; not measured in this ROM), and '
      'Crunch and Sucker Punch fall short too',
      [mon('Snorlax', ['Body Slam', 'Earthquake', 'Crunch', 'Rest'], hp=0.25)],
      [mon('Raticate', ['Super Fang', 'Double-Edge', 'Crunch', 'Sucker Punch'], hp=0.4)],
      best=['Double-Edge'], bad=['Super Fang', 'Crunch', 'Sucker Punch'],
      checks=[('b05_faster', 'e0', 'p0'), ('b05_ko', 'e0', 'Double-Edge', 'p0'), ('survives_recoil', 'e0', 'Double-Edge', 'p0'),
              ('b05_fang_noko', 'e0', 'p0'), ('b05_noko', 'e0', 'Crunch', 'p0'), ('b05_noko', 'e0', 'Sucker Punch', 'p0'),
              ('b05_ko', 'p0', 'Body Slam', 'e0')]),
    S('b05_counter_multi_hit', 'rules',
      "Skill Link Cloyster at 75% is faster and its best move is Icicle Spear (five hits, 45-55% in all); in this hack Counter "
      'returns twice the last hit only (seen in AI-vs-AI logs, not measured), far from a KO, where twice the total would KO; Close '
      'Combat (2x) KOs Cloyster after Hariyama survives the Icicle Spear',
      [mon('Cloyster', ['Icicle Spear', 'Rock Blast', 'Ice Shard', 'Spikes'], ability='Skill Link', hp=0.75)],
      [mon('Hariyama', ['Counter', 'Close Combat', 'Knock Off', 'Bulk Up'])],
      best=['Close Combat'], bad=['Counter'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'e0', 'Close Combat', 'p0'), ('b05_noko', 'p0', 'Icicle Spear', 'e0'),
              ('b05_beats', 'p0', 'Icicle Spear', 'Rock Blast', 'e0'), ('b05_beats', 'p0', 'Icicle Spear', 'Ice Shard', 'e0'),
              ('b05_counter_last', 'e0', 'Icicle Spear', 'p0'), ('b05_counter_total_kos', 'e0', 'Icicle Spear', 'p0')]),
])
