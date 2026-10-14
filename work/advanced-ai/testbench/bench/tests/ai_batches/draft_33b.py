"""Batch 33, part b (draft, rc33 unit A1b). WRITTEN BY THE IMPLEMENTER of the fix, not by an isolated author
(tests/ai_batches/AUTHORING.md wants one), so these positions only show that each A1b rule reaches the decision. One
position per mechanic the census showed the AI misjudging on random sets (qa/aivsai/rc33_A1b.md):

1. Imposter: a benched Imposter Ditto comes in as a copy of the foe it faces, not with its own moves (census s028_g1).
2. Sucker Punch fails against a status move, and a Choice item then keeps it locked (census s045_g1).
3. Moody: the foe's stages climb at each turn's end (census s041_g1). A guard: both builds attack here.
"""
from ai_helpers import S, mon  # noqa: F401

SCENARIOS = [
    S('b33b_imposter_copy', 'switch',
      'Ditto (Imposter) would come in as a copy of the Choice Scarf Lumineon: slower, less HP and only Icy Wind, not '
      'Volt Tackle. Mothim attacks rather than send it in',
      [mon('Lumineon', ['Icy Wind'], ability='Swift Swim', item='Choice Scarf', level=100)],
      [mon('Mothim', ['Aura Sphere', 'Rage', 'Detect', 'Rage Powder'], item='Life Orb', level=100, hp=0.7),
       mon('Ditto', ['Magnet Rise', 'Psybeam', 'Volt Tackle', 'Ion Deluge'], ability='Imposter', item='Focus Sash', level=100),
       mon('Kakuna', ['Bite', 'Muddy Water'], level=100)],
      best=['Aura Sphere'], ok=['Rage'], bad=['switch:Ditto']),
    S('b33b_sucker_choice', 'attack',
      'Bibarel holds a Choice Band; Deoxys has two status moves, and Sucker Punch fails against them and then stays locked',
      [mon('Deoxys', ['Astonish', 'Sonic Boom', 'Nightmare', 'Conversion'], ability='Pressure', level=100)],
      [mon('Bibarel', ['Sucker Punch', 'Return', 'Grass Pledge'], ability='Moody', item='Choice Band', level=100),
       mon('Muk', ['Poison Jab', 'Shadow Sneak'], level=100)],
      best=['Return'], bad=['Sucker Punch']),
    S('b33b_moody_toxic', 'attack',
      'Smeargle (Moody) gains stages every turn: Venusaur attacks now rather than spend a turn on Toxic',
      [mon('Smeargle', ['Tackle', 'Spore'], ability='Moody', level=100)],
      [mon('Venusaur', ['Toxic', 'Giga Drain', 'Sludge Bomb'], level=100), mon('Muk', ['Poison Jab', 'Shadow Sneak'], level=100)],
      best=['Sludge Bomb', 'Giga Drain'], bad=['Toxic']),
]
