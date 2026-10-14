"""Batch 35, Dig draft (rc35 unit DIG). WRITTEN BY THE IMPLEMENTER, not by an isolated author (tests/ai_batches/
AUTHORING.md wants one), so these positions only probe one report (qa/aivsai/rc35_DIG.md): a Gym Leader's Raichu and
the move Dig.

The real Raichu sets (trainers 142, 255, 722) do not know Dig. b35_real_* use trainer 255's real team against a player
Pokemon with Dig; b35_own_* give a Raichu Dig in place of Charge Beam, to check how the AI values its own two-turn
move (A1's unreachable, acc_now, the race's half rate for charge moves).
"""
from ai_helpers import S, mon  # noqa: F401

RAICHU = dict(level=25, ivs=12, item='BrightPowder', nature='Quirky')
REAL = ['Thunder Wave', 'Quick Attack', 'Charge Beam', 'Double Team']
OWN = ['Thunder Wave', 'Quick Attack', 'Dig', 'Double Team']
TEAM = [mon('Voltorb', ['Thunder Wave', 'Explosion', 'Shock Wave', 'Light Screen'], ability='Elec. Surge',
            level=24, ivs=12, item='Salac Berry', nature='Careful'),
        mon('Magnemite', ['Protect', 'Toxic', 'Shock Wave', 'Mirror Shot'], ability='Magnet Pull',
            level=24, ivs=12, item='Eviolite', nature='Gentle'),
        mon('Flaaffy', ['Signal Beam', 'Double Team', 'Thunder Wave', 'Shock Wave'], ability='Static',
            level=25, ivs=12, item='BrightPowder', nature='Sassy'),
        mon('Electabuzz', ['Quick Attack', 'Shock Wave', 'Light Screen', 'Low Kick'], ability='Galvanize',
            level=25, ivs=12, item='Air Balloon', nature='Lax')]
GRAVELER = ['Dig', 'Rock Throw', 'Rollout', 'Defense Curl']

SCENARIOS = [
    S('b35_real_graveler_team', 'switch',
      "Graveler is immune to Raichu's Electric moves and resists Quick Attack; Electabuzz's Air Balloon makes it immune "
      'to Dig and Low Kick hits Graveler super effectively; Magnemite resists Rock and Mirror Shot is super effective',
      [mon('Graveler', GRAVELER, ability='Rock Head', level=25)],
      [mon('Raichu', REAL, ability='Static', **RAICHU)] + TEAM,
      best=['switch:Electabuzz', 'switch:Magnemite'], ok=['Double Team'], bad=['Thunder Wave', 'Charge Beam']),
    S('b35_real_graveler_alone', 'status',
      "Raichu alone: Graveler is immune to its Electric moves and resists Quick Attack; Double Team (with BrightPowder) "
      'is the only thing that slows Graveler down',
      [mon('Graveler', GRAVELER, ability='Rock Head', level=25)],
      [mon('Raichu', REAL, ability='Static', **RAICHU)],
      best=['Double Team'], ok=['Quick Attack'], bad=['Thunder Wave', 'Charge Beam']),
    S('b35_own_graveler', 'attack',
      "Raichu with Dig, slower Graveler without Magnitude or Earthquake: Electric does nothing, Quick Attack is resisted, "
      'Dig is super effective and Graveler cannot hit Raichu underground',
      [mon('Graveler', ['Rock Throw', 'Rollout', 'Defense Curl', 'Tackle'], ability='Rock Head', level=25)],
      [mon('Raichu', OWN, ability='Static', **RAICHU), TEAM[0]],
      best=['Dig'], ok=['Double Team'], bad=['Thunder Wave']),
    S('b35_own_magneton', 'attack',
      'Raichu with Dig against Magneton: Electric is resisted and Thunder Wave fails on an Electric type, Dig is four '
      'times effective',
      [mon('Magneton', ['Thunder Shock', 'Sonic Boom', 'Mirror Shot', 'Supersonic'], ability='Magnet Pull', level=26)],
      [mon('Raichu', OWN, ability='Static', **RAICHU), TEAM[0]],
      best=['Dig'], bad=['Thunder Wave']),
    S('b35_own_graveler_low', 'attack',
      'Graveler has 3% HP: Quick Attack (priority, resisted) knocks it out now; Dig would take two turns',
      [mon('Graveler', ['Rock Throw', 'Rollout', 'Defense Curl', 'Tackle'], ability='Rock Head', level=25, hp=0.03)],
      [mon('Raichu', OWN, ability='Static', **RAICHU), TEAM[0]],
      best=['Quick Attack'], ok=['Dig']),
    S('b35_own_graveler_quake', 'switch',
      'Graveler knows Earthquake, which hits a Pokemon underground; Electabuzz (Air Balloon) is immune to it and Low '
      'Kick is super effective',
      [mon('Graveler', ['Earthquake', 'Rock Throw', 'Rollout', 'Defense Curl'], ability='Rock Head', level=25)],
      [mon('Raichu', OWN, ability='Static', **RAICHU), TEAM[3]],
      best=['switch:Electabuzz'], ok=['Dig'], bad=['Thunder Wave']),
]
