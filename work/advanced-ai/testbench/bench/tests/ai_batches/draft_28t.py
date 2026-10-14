"""Batch 28, part t (draft, rc28 unit T): status moves that cannot work. The foe in front already has a major status, so
every sleep, burn, paralysis or poison move fails on it ("Blissey ya está envenenado", "¡Pero falló!"), whatever else
the position offers. A strong player never spends the turn on one:

1. Reads. The foe in front is statused and its likely switch-in is not. The status move would land only if the foe
   switches; if it stays, the turn is lost. The attacks still do something either way.
2. Nothing works. Every move of the AI's active is a status move that fails on the statused foe, and a healthy teammate
   can come in: switching is right, staying in wastes the turn.
3. Trapped. The same, but the foe's Shadow Tag keeps the active in: a status move is all it has (no error, no fallback).
"""
from ai_helpers import PLAIN, S, mon  # noqa: F401

SCENARIOS = [
    S('b28t_read_wisp_slowbro', 'status',
      'Gengar faces a poisoned Slowbro, whose likely switch-in is Tyranitar; Will-O-Wisp and Hypnosis fail on the poisoned '
      'Slowbro, while Shadow Ball hits it super effectively',
      [mon('Slowbro', ['Scald', 'Slack Off'], status='psn', hp=0.8), mon('Tyranitar', ['Crunch', 'Stone Edge'])],
      [mon('Gengar', ['Will-O-Wisp', 'Hypnosis', 'Shadow Ball', 'Sludge Bomb']), mon('Muk', ['Poison Jab', 'Shadow Sneak'])],
      best=['Shadow Ball'], ok=['Sludge Bomb', 'switch:Muk'], bad=['Will-O-Wisp', 'Hypnosis'],
      checks=[('eff', 'e0', 'Shadow Ball', 'p0', 2.0), ('eff', 'e0', 'Shadow Ball', 'p1', 0.5)]),
    S('b28t_read_spore_snorlax', 'status',
      'Breloom faces a burned Snorlax, whose likely switch-in is Dusknoir (immune to Fighting); Spore fails on the burned '
      'Snorlax, while Drain Punch hits it super effectively',
      [mon('Snorlax', ['Body Slam', 'Rest'], status='brn'), mon('Dusknoir', ['Shadow Sneak', 'Ice Punch'])],
      [mon('Breloom', ['Spore', 'Drain Punch', 'Seed Bomb', 'Rock Tomb'], level=45), mon('Muk', ['Poison Jab', 'Shadow Sneak'])],
      best=['Drain Punch'], ok=['Seed Bomb', 'Rock Tomb', 'switch:Muk'], bad=['Spore'],
      checks=[('eff', 'e0', 'Drain Punch', 'p0', 2.0), ('eff', 'e0', 'Drain Punch', 'p1', 0.0)]),
    S('b28t_read_powder_rhydon', 'status',
      'Venusaur faces a burned Rhydon at a higher level, whose likely switch-in is Charizard; Sleep Powder fails on the '
      'burned Rhydon, while Giga Drain hits it four times over',
      [mon('Rhydon', ['Earthquake', 'Rock Slide'], status='brn', level=60), mon('Charizard', ['Air Slash', 'Flamethrower'], level=60)],
      [mon('Venusaur', ['Sleep Powder', 'Giga Drain', 'Sludge Bomb', 'Synthesis'], level=45), mon('Muk', ['Poison Jab', 'Shadow Sneak'])],
      best=['Giga Drain'], ok=['Sludge Bomb', 'switch:Muk'], bad=['Sleep Powder'],
      checks=[('eff', 'e0', 'Giga Drain', 'p0', 4.0), ('eff', 'e0', 'Giga Drain', 'p1', 0.25)]),
    S('b28t_read_yawn_vaporeon', 'status',
      'Jolteon faces a paralyzed Vaporeon, whose likely switch-in is Quagsire (immune to Electric); Yawn fails on the '
      'paralyzed Vaporeon, while Thunderbolt hits it super effectively',
      [mon('Vaporeon', ['Surf', 'Wish'], status='par'), mon('Quagsire', ['Earthquake', 'Surf'])],
      [mon('Jolteon', ['Yawn', 'Thunderbolt', 'Shadow Ball', 'Hyper Voice']), mon('Muk', ['Poison Jab', 'Shadow Sneak'])],
      best=['Thunderbolt'], ok=['Shadow Ball', 'Hyper Voice', 'switch:Muk'], bad=['Yawn'],
      checks=[('eff', 'e0', 'Thunderbolt', 'p0', 2.0), ('eff', 'e0', 'Thunderbolt', 'p1', 0.0)]),
    S('b28t_stay_sableye_snorlax', 'status',
      'Every move of Sableye is a major status move and the foe, Snorlax, is already burned, so all four fail; Muk can '
      'come in and fight',
      [mon('Snorlax', ['Body Slam', 'Rest'], status='brn')],
      [mon('Sableye', ['Toxic', 'Will-O-Wisp', 'Thunder Wave', 'Hypnosis']), mon('Muk', ['Poison Jab', 'Drain Punch'])],
      best=['switch:Muk'], bad=['Toxic', 'Will-O-Wisp', 'Thunder Wave', 'Hypnosis']),
    S('b28t_stay_jynx_blissey', 'status',
      'Every move of Jynx is a major status move and the foe, Blissey, is already poisoned, so all four fail; Machamp can '
      'come in and fight',
      [mon('Blissey', ['Seismic Toss', 'Soft-Boiled'], status='psn')],
      [mon('Jynx', ['Lovely Kiss', 'Thunder Wave', 'Will-O-Wisp', 'Toxic']), mon('Machamp', ['Cross Chop', 'Knock Off'])],
      best=['switch:Machamp'], bad=['Lovely Kiss', 'Thunder Wave', 'Will-O-Wisp', 'Toxic']),
    S('b28t_stay_sableye_alakazam', 'status',
      'Every move of Sableye is a major status move and the paralyzed Alakazam already has a status, so all four fail; '
      'Alakazam cannot touch Sableye either (Psychic and Fighting), a stalemate that chips nobody. Absol is immune to '
      'Psychic and its Night Slash hits Alakazam super effectively: it comes in and wins',
      [mon('Alakazam', ['Psychic', 'Focus Blast'], status='par')],
      [mon('Sableye', ['Toxic', 'Will-O-Wisp', 'Thunder Wave', 'Hypnosis']), mon('Absol', ['Night Slash', 'Play Rough'])],
      best=['switch:Absol'], bad=['Toxic', 'Will-O-Wisp', 'Thunder Wave', 'Hypnosis'],
      checks=[('eff', 'p0', 'Psychic', 'e0', 0.0), ('eff', 'p0', 'Focus Blast', 'e0', 0.0), ('eff', 'p0', 'Psychic', 'e1', 0.0),
              ('eff', 'e1', 'Night Slash', 'p0', 2.0)]),
    S('b28t_stay_sableye_dusknoir', 'status',
      'Every move of Sableye is a major status move and the paralyzed Alakazam already has a status, so all four fail; '
      'Alakazam cannot touch Sableye either. Dusknoir, at 70% HP, is immune to Focus Blast, takes Psychic with its high '
      'Special Defense, and its Shadow Punch hits Alakazam super effectively: it comes in and wins',
      [mon('Alakazam', ['Psychic', 'Focus Blast'], status='par')],
      [mon('Sableye', ['Toxic', 'Will-O-Wisp', 'Thunder Wave', 'Hypnosis']), mon('Dusknoir', ['Shadow Punch', 'Ice Punch'], hp=0.7)],
      best=['switch:Dusknoir'], bad=['Toxic', 'Will-O-Wisp', 'Thunder Wave', 'Hypnosis'],
      checks=[('eff', 'p0', 'Focus Blast', 'e1', 0.0), ('eff', 'e1', 'Shadow Punch', 'p0', 2.0), ('noko', 'p0', 'Psychic', 'e1')]),
    S('b28t_stay_trapped_wobbuffet', 'status',
      'Every move of Gardevoir is a major status move and the foe, a paralyzed Wobbuffet, traps it with Shadow Tag: it '
      'cannot switch, so it stays in with a move that fails (the only legal actions)',
      [mon('Wobbuffet', ['Counter', 'Mirror Coat'], ability='Shadow Tag', status='par')],
      [mon('Gardevoir', ['Hypnosis', 'Thunder Wave', 'Will-O-Wisp', 'Toxic']), mon('Muk', ['Poison Jab', 'Drain Punch'])],
      best=['Hypnosis', 'Thunder Wave', 'Will-O-Wisp', 'Toxic']),
]
