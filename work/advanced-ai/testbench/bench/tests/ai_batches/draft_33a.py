"""Batch 33, part a (draft, rc33 unit A1). WRITTEN BY THE IMPLEMENTER of the fix, not by an isolated author
(tests/ai_batches/AUTHORING.md wants one), so these positions only show that each A1 rule reaches the decision. One
position per mechanic the census showed the AI misjudging on random sets (qa/aivsai/rc33_A1.md):

1. Dark Void fails unless its user is Darkrai (census s014_g0, s019_g0: "But it failed!").
2. Future Sight lands two turns later: it cannot finish a foe this turn (census s049_g1).
3. Protean makes the foe its move's type before that move: a faster Protean foe whose attack is Flying turns Flying
   before my move, so my Ground move does nothing (census s052_g1).
4. Dig's first turn: a faster foe goes underground before my move, which then misses; a free boost is worth more
   (census s045_g0, s042_g1).
"""
from ai_helpers import S, mon  # noqa: F401

SCENARIOS = [
    S('b33a_dark_void_raikou', 'status',
      'Raikou is not Darkrai, so its Dark Void fails, and Growl does nothing that matters; Vaporeon can come in and Surf '
      'Sandshrew super effectively',
      [mon('Sandshrew', ['Water Spout', 'Guillotine', 'Cotton Guard'], ability='Solid Rock')],
      [mon('Raikou', ['Dark Void', 'Growl']), mon('Vaporeon', ['Surf', 'Ice Beam'])],
      best=['switch:Vaporeon'], ok=['Growl'], bad=['Dark Void']),
    S('b33a_future_sight_finish', 'attack',
      'Machamp has a tenth of its HP; Swift knocks it out now, Future Sight would land two turns later',
      [mon('Machamp', ['Cross Chop', 'Bullet Punch'], hp=0.1)],
      [mon('Espeon', ['Future Sight', 'Swift']), mon('Muk', ['Poison Jab', 'Shadow Sneak'])],
      best=['Swift'], bad=['Future Sight']),
    S('b33a_protean_brave_bird', 'attack',
      'Arcanine (Protean) outspeeds Rhyperior and its only attack is Brave Bird: it turns Flying first, so Earthquake '
      'does nothing and Thunder Punch hits super effectively',
      [mon('Arcanine', ['Brave Bird'], ability='Protean')],
      [mon('Rhyperior', ['Earthquake', 'Thunder Punch']), mon('Muk', ['Poison Jab', 'Shadow Sneak'])],
      best=['Thunder Punch'], bad=['Earthquake']),
    S('b33a_dig_vanish_slowbro', 'status',
      'Dugtrio outspeeds Slowbro and its only move is Dig: it goes underground first, so Ice Beam misses this turn; '
      'Calm Mind is a free boost',
      [mon('Dugtrio', ['Dig'])],
      [mon('Slowbro', ['Ice Beam', 'Calm Mind']), mon('Muk', ['Poison Jab', 'Shadow Sneak'])],
      best=['Calm Mind'], bad=['Ice Beam']),
]
