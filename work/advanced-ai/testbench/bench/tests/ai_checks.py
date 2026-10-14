"""Extra claim checks for the AI bench scenarios, owned by the scenario authors (tests/ai_batches/AUTHORING.md).

Ported from the Spanish workspace's tests/ai_checks.py (dc8577c): only the import path and the ROM hold_effect reads
(the ROM under test, not the Spanish build's fixed one) changed.

tools/aibench.py --check runs the built-in checks (eff, ko, noko, noko_at, beats, faster, cls, pri, acc_lt,
type) and, for any other op, CHECKS[op](d, views, c, ref): d is tools/aidata.Data (the ROM's data),
views the scenario's Pokémon as aibench.mon_view builds them, c the check tuple, ref('e0') a Pokémon.
A check raises AssertionError with a readable message when the claim is false.

The ops below (batch 01) model the Gen 5 damage formula with held items and damage-changing abilities on
top of the hack's data, and refuse (raise) any item or ability they do not model, so a key never rests on
an effect that was silently ignored. Items the ROM names but gives no hold effect (Assault Vest, Eviolite,
Air Balloon, Weakness Policy...; byte 2 of `a/0/1/7` is 0) are refused too: the engine never reads them.

aibench.mon_view does not carry held items or whether the battle is a double, so these ops read both from
the check tuple's last element, a dict {'items': {ref: item name or None}, 'double': bool} that
`with_items(scenarios)` appends from the scenario specs: a batch writes `SCENARIOS = with_items([...])`.

Modified damage, Gen 5 (one hit, no crit, rolls 85-100%):
  base = floor(floor(floor(2L/5 + 2) * BP * A / D) / 50) + 2, then x spread (0.75, doubles, 2+ targets),
  x weather (1.5 / 0.5 for Fire and Water in sun or rain), x roll, x STAB (1.5; Adaptability 2),
  x type effectiveness, x burn (0.5, physical, not Guts), x final modifiers.
  BP: Technician 1.5 (BP <= 60), Iron Fist 1.2 (punch flag), Reckless 1.2 (recoil and crash moves),
      Sheer Force 1.3 (moves with a secondary effect, see has_secondary), Sand Force 1.3 (Rock, Ground,
      Steel in sand), type-boosting item 1.2, Muscle Band / Wise Glasses 1.1, Heatproof 0.5 and Dry Skin
      1.25 on the target for Fire, Facade 2 with a status, Brine 2 under half HP, Venoshock 2 on a poisoned
      target, Hex 2 on a statused target, Wake-Up Slap 2 on a sleeping target, SmellingSalt 2 on a
      paralyzed target, Eruption / Water Spout scaled by the user's HP; any other variable power is refused.
  A:  Intimidate from the opposing actives (one stage each, 2/3; blocked by Clear Body, White Smoke,
      Hyper Cutter), Download (+1 stage to Atk if the foes' Def < SpD, else SpA), Huge Power / Pure Power 2,
      Guts 1.5 with a status, Hustle 1.5, Toxic Boost 1.5 when poisoned, Flare Boost 1.5 when burned,
      Solar Power 1.5 in sun, Slow Start 0.5, Defeatist 0.5 at or under half HP, Blaze / Torrent /
      Overgrow / Swarm 1.5 at or under a third, Choice Band / Specs 1.5, Light Ball 2 (Pikachu),
      Thick Club 2 (Cubone, Marowak), Deep Sea Tooth 2 (Clamperl), and the target's Thick Fat 0.5 for Fire and Ice.
  D:  Marvel Scale 1.5 with a status, sandstorm 1.5 Sp. Def for Rock types, Deep Sea Scale 2 (Clamperl);
      Psyshock hits Defense.
  Refused: Soul Dew (INERT_ITEMS). A measurement in the emulator showed it does nothing in this ROM: a level 50 Latios took and
      dealt the same damage with and without it, on the same battle seed. No key may rest on it, either way.
  final: Multiscale 0.5 at full HP, Tinted Lens 2 when not very effective, Filter / Solid Rock 0.75 when
      super effective, Expert Belt 1.2 when super effective, Life Orb 1.3, a type-resist berry 0.5 when
      super effective (Chilan: any Normal move).
  Mold Breaker (Teravolt, Turboblaze) ignores the target's abilities. Scrappy lets Normal and Fighting hit
  Ghosts; Iron Ball grounds the holder; Soundproof blocks sound moves; Bulletproof blocks ball and bomb
  moves; Klutz and the hack's unimplemented items give no item effect.
  Multi-hit moves: hit count from the move data (2-5 hits: min 2, max 5; Skill Link: the maximum); a sure
  claim uses the minimum hits, a cannot claim the maximum.
  Weather: the one weather ability among the actives (Drizzle, Drought, Sand Stream, Snow Warning);
  two or more are refused (order would decide); Cloud Nine / Air Lock clear it.

Batch 02 adds the turn-order and multi-turn ops (race, loses, first, chip_kos, chip_survives, survives_recoil,
macc, status_only, no_endure). The race plays the two actives' moves turn by turn, singles only:
  order: move priority (Prankster +1 on status moves), then speed as mfaster computes it, under both
      paralysis rules (a quarter and a half) and both burn rules (an eighth, Gen 4-6, and a sixteenth, Gen 7+);
      a speed tie is refused. Lagging Tail / Full Incense / Stall act last in their bracket.
  damage: the favored side (the one the claim says wins) deals its minimum (minimum hits) x 0.9 and takes the
      other's maximum (maximum hits) x 1.1, the same margins as mko / mnoko. Focus Sash and Sturdy keep 1 HP
      once (the Sash is then gone). Guaranteed stat changes are applied for the turns after (Close Combat,
      Superpower, Overheat, Hammer Arm, Icy Wind, Bulldoze...), but none after a hit the target is immune to;
      chance-based secondary effects (burns, flinches, 10% drops) are not counted, so keys must keep a
      margin. Sucker Punch and Thunderclap fail when the target has already moved that turn. Hyper Beam /
      Giga Impact cost the next turn. Explosion and
      Selfdestruct knock the user out after the hit (refused against Damp). Drain moves heal (Liquid Ooze is
      refused); recoil moves cost their fraction of the damage dealt (Rock Head and Magic Guard take none);
      Life Orb costs a tenth after each hit (not with Magic Guard or a Sheer Force-boosted move); Sitrus and
      Oran Berries heal once at or under half HP. Refused: status moves, two-turn moves (Fly, Dig, Dive,
      Bounce, Sky Attack, Shadow Force, Focus Punch, Solar Beam outside sun), Fake Out, Shell Bell, a
      status-curing berry on a Pokémon that has a status.
  end of turn, in the Gen 5 order: sandstorm / hail (a sixteenth; Rock, Ground, Steel / Ice types and Sand
      Veil, Sand Rush, Sand Force / Ice Body, Snow Cloak, Slush Rush, Overcoat and Magic Guard are spared),
      Ice Body and Rain Dish (+1/16), Dry Skin (+1/8 in rain, -1/8 in sun), Leftovers (+1/16), Black Sludge
      (+1/16 for Poison types, -1/8 for the rest), poison (1/8), bad poison (n/16; the battle's counter is not
      known, so n starts at 2 on the favored side and at 1 on the other), burn (an eighth or a sixteenth,
      halved by Heatproof), Poison Heal (+1/8 instead of the poison damage), Magic Guard (no indirect
      damage). Both fainting at the same end of turn counts against the claim.

Batch 02, second part (setup_wins, boosted_race, fixed_ko, has_ability, has_status, pivot, one_turn, and three more variable powers):
  Gyro Ball = 25 x target Speed / user Speed + 1 (at most 150), Electro Ball = 150 / 120 / 80 / 60 / 40 for a user at least
      4 / 3 / 2 / 1 / under 1 times as fast as the target (whole-number ratio), Reversal and Flail = 200 / 150 / 100 / 80 / 40 / 20 for
      floor(48 x HP / max HP) of at most 1 / 4 / 9 / 16 / 32 / more (all Gen 5). The Speed ones refuse paralysis and any item, ability
      or weather that moves the Speed, so the power never rests on a detail the model skips.
  Technician now compares the power the move really has (after Acrobatics' doubling, Eruption's HP scaling, Gyro Ball...) with 60,
      as Gen 5 does; every fixed-power move behaves exactly as before.
  setup_wins: `race` with a first turn spent on a plain self-boosting status move (the boosts apply after it moves and change the
      Speed order and the damage of the turns after); Race.play takes the move as `setup`.
  boosted_race: `race` with the boosts of a setup move already in force (a boost kept from an earlier turn; Race.play takes
      `start_boosts`). The two fighters of race / loses / setup_wins / boosted_race may be an active and a bench member that
      comes in once the foe in front of it faints, as long as the newcomer has no entry ability (the field is as it is now).
  fixed_ko: Seismic Toss and Night Shade (the user's level), Dragon Rage (40) and Sonic Boom (20) as a sure KO, ignoring stats,
      items and rolls but not type immunities, Focus Sash or Sturdy.
  pivot: the move is U-turn or Volt Switch (effect 228); one_turn: Solar Beam in sun, or any charge move with a Power Herb;
      has_ability and has_status: the readable twins of has_item.

Batch 31 (doubles) adds sum_ko / sum_noko, several hits on one Pokémon in the same turn added up (the partner's hit and the
AI's, or the AI's own spread move and a foe's), each under both spread rules because the 0.75 doubles reduction was never
measured in this ROM, and dbl_chip_kos, chip_kos for a double (the race refuses doubles, the end-of-turn model does not need it).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
from aidata import PHYSICAL, SPECIAL, STATUS, TYPE_IMMUNE_ABILITIES, TYPES  # noqa: E402

CHECKS = {}

T = {t: i for i, t in enumerate(TYPES)}
NORMAL, FIGHTING, GROUND, ROCK, GHOST, STEEL, FIRE, WATER, ICE, FLYING = (
    T['Normal'], T['Fighting'], T['Ground'], T['Rock'], T['Ghost'], T['Steel'], T['Fire'], T['Water'], T['Ice'], T['Flying'])

# Move data (Gen 5 format, see aidata): flags bit 0 contact, bit 7 punch, bit 8 sound, bit 30 ball/bomb.
FLAG_CONTACT, FLAG_PUNCH, FLAG_SOUND, FLAG_BALL = 1, 0x80, 0x100, 1 << 30
# Effects: recoil (Take Down 48, Brave Bird 198, Flare Blitz 253, Volt Tackle 262, Head Smash 269) and the
# crash kicks (45) are what Reckless powers up; the flinch effects are secondary effects for Sheer Force.
RECOIL_EFFECTS = {48, 198, 253, 262, 269, 45}
FLINCH_EFFECTS = {31, 150, 146, 75, 92, 158}
# "quality" byte 1: 4 damage + status chance, 6 damage + target stat drop, 7 damage + user stat change.
Q_STATUS, Q_TARGET_DROP, Q_USER_STAT = 4, 6, 7
VARIABLE_POWER_OK = {169: 'facade', 221: 'brine', 283: 'venoshock', 310: 'hex', 217: 'wakeupslap', 171: 'smellingsalt',
                     190: 'eruption', 317: 'acrobatics', 219: 'gyroball', 293: 'electroball', 99: 'reversal'}
# Fixed-damage moves (effect: damage in HP): Seismic Toss / Night Shade (the user's level), Dragon Rage 40, Sonic Boom 20.
FIXED_LEVEL, FIXED_DRAGON_RAGE, FIXED_SONIC_BOOM = 87, 41, 130
PIVOT_EFFECT = 228   # U-turn, Volt Switch: the user switches out after the hit
# Moves with a listed power that the formula does not use as such: Foul Play (the target's Attack), Payback, Avalanche
# and Revenge (move order), Stored Power, Weather Ball, Hidden Power (type from IVs), Rage Fist, Assurance, Bolt Beak /
# Fishious Rend, Round, Fury Cutter, Echoed Voice, Last Respects, Judgment / Techno Blast, Rollout, Body Press (the
# user's Defense), Tera Blast, Retaliate, Rage, the Pledges, Fusion Flare / Bolt, Future Sight / Doom Desire, Struggle.
UNMODELED_POWER_EFFECTS = {297, 230, 185, 305, 203, 135, 466, 231, 430, 301, 119, 302, 452, 268, 117, 433, 450, 319, 81,
                           324, 325, 326, 335, 336, 148, 254}
KNOCK_OFF = 188
PSYSHOCK = 282

TYPE_ITEMS = {'Charcoal': 'Fire', 'Mystic Water': 'Water', 'Magnet': 'Electric', 'Miracle Seed': 'Grass',
              'NeverMeltIce': 'Ice', 'Never-Melt Ice': 'Ice', 'Black Belt': 'Fighting', 'Poison Barb': 'Poison',
              'Soft Sand': 'Ground', 'Sharp Beak': 'Flying', 'Twisted Spoon': 'Psychic', 'Silver Powder': 'Bug',
              'Hard Stone': 'Rock', 'Spell Tag': 'Ghost', 'Dragon Fang': 'Dragon', 'Black Glasses': 'Dark',
              'Metal Coat': 'Steel', 'Silk Scarf': 'Normal', 'Pixie Plate': None}
RESIST_BERRIES = {'Occa Berry': 'Fire', 'Passho Berry': 'Water', 'Wacan Berry': 'Electric', 'Rindo Berry': 'Grass',
                  'Yache Berry': 'Ice', 'Chople Berry': 'Fighting', 'Kebia Berry': 'Poison', 'Shuca Berry': 'Ground',
                  'Coba Berry': 'Flying', 'Payapa Berry': 'Psychic', 'Tanga Berry': 'Bug', 'Charti Berry': 'Rock',
                  'Kasib Berry': 'Ghost', 'Haban Berry': 'Dragon', 'Colbur Berry': 'Dark', 'Babiri Berry': 'Steel',
                  'Chilan Berry': 'Normal'}
# Items whose effect these ops model, or that change nothing about turn-1 damage, speed and survival.
MODELED_ITEMS = {'Choice Band', 'Choice Specs', 'Choice Scarf', 'Life Orb', 'Expert Belt', 'Focus Sash', 'Muscle Band',
                 'Wise Glasses', 'Light Ball', 'Thick Club', 'Deep Sea Tooth', 'Deep Sea Scale', 'Iron Ball',
                 'Macho Brace', 'Lagging Tail', 'Full Incense', 'Leftovers', 'Black Sludge', 'Sitrus Berry', 'Oran Berry',
                 'Lum Berry', 'Chesto Berry', 'Cheri Berry', 'Pecha Berry', 'Rawst Berry', 'Aspear Berry',
                 'Persim Berry', 'Leppa Berry', 'Shell Bell', 'Rocky Helmet', 'Flame Orb', 'Toxic Orb', 'Scope Lens',
                 'Razor Claw', "King's Rock", 'Razor Fang', 'Wide Lens', 'Zoom Lens', 'Big Root', 'Power Herb',
                 'White Herb', 'Mental Herb', 'Shed Shell', 'Metronome', 'Bright Powder', 'Lax Incense', 'Everstone',
                 'Lucky Egg', 'Amulet Coin', 'Smoke Ball', 'Destiny Knot', 'Grip Claw', 'Sticky Barb',
                 'Damp Rock', 'Heat Rock', 'Smooth Rock', 'Icy Rock', 'Light Clay'} | set(TYPE_ITEMS) | set(RESIST_BERRIES)
RANDOM_ITEMS = {'Quick Claw', 'Focus Band'}
# Items the ROM gives a hold effect but the battle engine was measured not to apply (see the module docstring): refused outright.
INERT_ITEMS = {'Soul Dew'}

WEATHER_ABILITIES = {'Drizzle': 'rain', 'Drought': 'sun', 'Sand Stream': 'sand', 'Snow Warning': 'hail'}
WEATHER_SPEED = {'Swift Swim': 'rain', 'Chlorophyll': 'sun', 'Sand Rush': 'sand', 'Slush Rush': 'hail'}
MOLD_BREAKER = {'Mold Breaker', 'Teravolt', 'Turboblaze'}
INTIMIDATE_BLOCKERS = {'Clear Body', 'White Smoke', 'Hyper Cutter'}
# With these the Intimidate result depends on the generation the engine follows, or reverses: refused.
INTIMIDATE_AMBIGUOUS = {'Inner Focus', 'Oblivious', 'Own Tempo', 'Scrappy', 'Contrary', 'Defiant', 'Competitive',
                        'Rattled', 'Guard Dog', 'Mirror Armor', 'Simple'}
PINCH_ABILITIES = {'Blaze': 'Fire', 'Torrent': 'Water', 'Overgrow': 'Grass', 'Swarm': 'Bug'}
# Abilities the model handles, plus those that change nothing about turn-1 damage, speed and survival.
MODELED_ABILITIES = {
    'Huge Power', 'Pure Power', 'Guts', 'Hustle', 'Toxic Boost', 'Flare Boost', 'Solar Power', 'Slow Start', 'Defeatist',
    'Technician', 'Iron Fist', 'Reckless', 'Sheer Force', 'Tinted Lens', 'Adaptability', 'Sand Force', 'Thick Fat',
    'Heatproof', 'Dry Skin', 'Marvel Scale', 'Multiscale', 'Filter', 'Solid Rock', 'Intimidate', 'Download', 'Sturdy',
    'Skill Link', 'Scrappy', 'Soundproof', 'Bulletproof', 'Wonder Guard', 'Klutz', 'Cloud Nine', 'Air Lock',
    'Quick Feet', 'Prankster', 'Stall',
    # no effect on the numbers these ops compute
    'Run Away', 'Pressure', 'Natural Cure', 'Synchronize', 'Inner Focus', 'Keen Eye', 'Shed Skin', 'Early Bird',
    'Insomnia', 'Vital Spirit', 'Limber', 'Immunity', 'Water Veil', 'Own Tempo', 'Oblivious', 'Clear Body',
    'White Smoke', 'Hyper Cutter', 'Shell Armor', 'Battle Armor', 'Illuminate', 'Sticky Hold', 'Suction Cups',
    'Arena Trap', 'Shadow Tag', 'Magnet Pull', 'Static', 'Flame Body', 'Poison Point', 'Effect Spore', 'Rough Skin',
    'Iron Barbs', 'Aftermath', 'Cute Charm', 'Serene Grace', 'Super Luck', 'Magic Guard', 'Regenerator',
    'Poison Heal', 'Unaware', 'Moxie', 'Speed Boost', 'Sniper', 'Compoundeyes', 'No Guard', 'Infiltrator', 'Frisk',
    'Anticipation', 'Forewarn', 'Stench', 'Damp', 'Gluttony', 'Pickup', 'Honey Gather', 'Big Pecks', 'Overcoat',
    'Leaf Guard', 'Hydration', 'Ice Body', 'Rain Dish', 'Snow Cloak', 'Sand Veil', 'Tangled Feet', 'Steadfast',
    'Justified', 'Rattled', 'Weak Armor', 'Cursed Body', 'Mummy', 'Telepathy', 'Pickpocket', 'Harvest', 'Healer',
    'Unnerve', 'Defiant', 'Competitive', 'Anger Point', 'Contrary', 'Simple', 'Moody', 'Liquid Ooze',
    'Magic Bounce', 'Wonder Skin', 'Shield Dust', 'Merciless', 'Swarm', 'Blaze',
    'Torrent', 'Overgrow', 'Swift Swim', 'Chlorophyll', 'Sand Rush', 'Slush Rush', 'Unburden', 'Analytic',
    'Rock Head',
} | set(TYPE_IMMUNE_ABILITIES) | set(WEATHER_ABILITIES) | MOLD_BREAKER
ORDER_DEPENDENT_ABILITIES = {'Analytic'}   # 1.3x when moving last: refused on an attacker


def with_items(scenarios):
    """Append to every check tuple the context these ops need (held items by ref, singles or doubles)."""
    for sc in scenarios:
        ctx = {'items': {}, 'double': bool(sc.get('double'))}
        for side, pre in (('enemy', 'e'), ('player', 'p')):
            for i, m in enumerate(sc[side]):
                ctx['items'][pre + str(i)] = m.get('item')
        sc['checks'] = [tuple(c) + (ctx,) if c[0] in CHECKS else c for c in sc['checks']]
    return scenarios


class Ctx:
    """One scenario's battle as the ops see it: the views, items, the actives of both sides, the weather."""

    def __init__(self, d, views, c, ref):
        assert isinstance(c[-1], dict) and 'items' in c[-1], (
            '%s: the batch must wrap its list in ai_checks.with_items() so the ops know the held items' % (c[0],))
        self.d, self.views, self.ref = d, views, ref
        self.items, self.double = c[-1]['items'], c[-1]['double']
        self.args = c[1:-1]
        self.boosts = {}      # (ref, stat) -> stage, set only by the race simulation (turn 1 has none)
        self.consumed = set()  # refs whose held item is gone (a Focus Sash or berry used during the race)
        n = 2 if self.double else 1
        self.actives = {'enemy': [('e%d' % i) for i in range(min(n, len(views['enemy'])))],
                        'player': [('p%d' % i) for i in range(min(n, len(views['player'])))]}
        for side in ('enemy', 'player'):
            for i, v in enumerate(views[side]):
                self.vet(side[0] + str(i), v)
        self.weather = self.find_weather()

    def side(self, r):
        return 'enemy' if r[0] == 'e' else 'player'

    def foes(self, r):
        return self.actives['player' if r[0] == 'e' else 'enemy']

    def item(self, r):
        it = self.items.get(r)
        if it is None or self.ability(r) == 'Klutz' or r in self.consumed:
            return None
        return it

    def ability(self, r):
        return self.ref(r)['ability']

    def vet(self, r, v):
        """Refuse what the model does not cover, so no key rests on it."""
        ab = v['ability']
        assert ab in MODELED_ABILITIES, '%s: %s has %s, which these checks do not model; use another ability' % (
            r, v['species'], ab)
        it = self.items.get(r)
        if it is not None:
            assert it not in RANDOM_ITEMS, '%s: %s is random; the key cannot rest on it' % (r, it)
            assert it not in INERT_ITEMS, '%s: %s was measured to have no effect in this ROM; the key cannot rest on it' % (r, it)
            assert it in MODELED_ITEMS, '%s: %s has %s, which these checks do not model (or the ROM gives it no hold effect)' % (
                r, v['species'], it)
            if ab == 'Klutz':
                return
            assert self.d.id('item', it) and self.hold_effect(it), '%s: %s has no hold effect in this ROM' % (r, it)

    def hold_effect(self, it):
        if not hasattr(self.d, '_items'):
            import ndspy.narc
            import ndspy.rom
            rom = ndspy.rom.NintendoDSRom.fromFile(self.d.rom_path)     # the ROM under test (Spanish: its own build's)
            self.d._items = ndspy.narc.NARC(rom.getFileByName('a/0/1/7')).files
        return self.d._items[self.d.id('item', it)][2]

    def find_weather(self):
        actives = self.actives['enemy'] + self.actives['player']
        if any(self.ability(r) in ('Cloud Nine', 'Air Lock') for r in actives):
            return None
        ws = [WEATHER_ABILITIES[self.ability(r)] for r in actives if self.ability(r) in WEATHER_ABILITIES]
        assert len(ws) <= 1, 'two weather abilities on the field: the order would decide the weather'
        return ws[0] if ws else None

    # --- the numbers
    def stages(self, r, stat):
        """Atk / Sp. Atk stages at turn 1: Intimidate from the opposing actives, the holder's own Download."""
        v, st = self.ref(r), 0
        if stat == 'atk':
            for f in self.foes(r):
                if self.ability(f) == 'Intimidate':
                    assert v['ability'] not in INTIMIDATE_AMBIGUOUS, '%s: %s vs Intimidate depends on the engine' % (r, v['ability'])
                    if v['ability'] not in INTIMIDATE_BLOCKERS:
                        st -= 1
        if v['ability'] == 'Download':
            defs = sum(self.ref(f)['stats']['def'] for f in self.foes(r))
            spds = sum(self.ref(f)['stats']['spd'] for f in self.foes(r))
            if (defs < spds) == (stat == 'atk'):
                st += 1
        return max(-6, min(6, st + self.boosts.get((r, stat), 0)))

    def stage_mult(self, st):
        return (2 + max(st, 0)) / (2 + max(-st, 0))

    def hits(self, mv):
        """(min, max) hits of a move: byte 7 of the data (low nibble min, high nibble max), Skill Link the max."""
        r = self.d.moves[self.d.id('move', mv)]
        return (r[7] & 15, r[7] >> 4) if r[7] else (1, 1)

    def has_secondary(self, mv):
        """Sheer Force's moves: a status chance, a target stat drop, a user stat raise, or a flinch chance."""
        m = self.d.move(mv)
        r = self.d.moves[m['id']]
        if m['effect'] in FLINCH_EFFECTS:
            return True
        if r[1] == Q_STATUS or r[1] == Q_TARGET_DROP:
            return True
        if r[1] == Q_USER_STAT:
            return any(int.from_bytes(r[k:k + 1], 'little', signed=True) > 0 for k in (24, 25, 26))
        return False

    def grounded_or_hittable(self, df, atk_type):
        """Ground against a Flying type or Levitate: Iron Ball grounds the holder."""
        return atk_type == GROUND and self.item(df) == 'Iron Ball'

    def effectiveness(self, a, mv, df):
        m = self.d.move(mv)
        if m['class'] == STATUS:
            return None
        dv, av = self.ref(df), self.ref(a)
        types = list(dv['types'])
        breaker = av['ability'] in MOLD_BREAKER
        if not breaker:
            if dv['ability'] == 'Soundproof' and m['flags'] & FLAG_SOUND:
                return 0.0
            if dv['ability'] == 'Bulletproof' and m['flags'] & FLAG_BALL:
                return 0.0
            if TYPE_IMMUNE_ABILITIES.get(dv['ability']) == TYPES[m['type']] and not self.grounded_or_hittable(df, m['type']):
                return 0.0
        mult = 1.0
        for t in set(types):
            x = self.d.chart[m['type']][t] / 4
            if x == 0 and m['type'] in (NORMAL, FIGHTING) and t == GHOST and av['ability'] == 'Scrappy':
                x = 1.0
            if x == 0 and m['type'] == GROUND and t == FLYING and self.item(df) == 'Iron Ball':
                x = 1.0
            mult *= x
        if dv['ability'] == 'Wonder Guard' and not breaker and mult <= 1:
            return 0.0
        return mult

    def power(self, a, mv, df):
        m = self.d.move(mv)
        av, dv = self.ref(a), self.ref(df)
        bp = m['power']
        if bp <= 1:
            kind = VARIABLE_POWER_OK.get(m['effect'])
            assert kind, '%s has a variable power these checks do not model' % mv
        assert m['effect'] not in UNMODELED_POWER_EFFECTS, '%s\'s damage does not follow its listed power: not modeled' % mv
        assert not (m['effect'] == KNOCK_OFF and self.items.get(df)), 'Knock Off against an item holder: the boost depends on the engine'
        if m['effect'] in VARIABLE_POWER_OK:
            kind = VARIABLE_POWER_OK[m['effect']]
            if kind == 'acrobatics' and self.item(a) is None:   # Acrobatics doubles when the user holds nothing
                bp *= 2
            if kind == 'facade' and av['status']:
                assert av['ability'] == 'Guts' or av['status'] != 'brn', 'burned Facade without Guts: the burn halving differs by generation'
                bp *= 2
            if kind == 'brine' and dv['cur_hp'] * 2 <= dv['stats']['hp']:
                bp *= 2
            if kind == 'venoshock' and dv['status'] in ('psn', 'tox'):
                bp *= 2
            if kind == 'hex' and dv['status']:
                bp *= 2
            if kind == 'wakeupslap' and dv['status'] == 'slp':
                bp *= 2
            if kind == 'smellingsalt' and dv['status'] == 'par':
                bp *= 2
            if kind == 'eruption':   # Eruption, Water Spout: 150 x current HP / max HP, at least 1
                bp = max(1, bp * av['cur_hp'] // av['stats']['hp'])
            if kind == 'reversal':   # Reversal, Flail (Gen 5): 200 / 150 / 100 / 80 / 40 / 20 for floor(48 x HP / max HP) of at most 1 / 4 / 9 / 16 / 32 / more
                p48 = 48 * av['cur_hp'] // av['stats']['hp']
                bp = 200 if p48 <= 1 else 150 if p48 <= 4 else 100 if p48 <= 9 else 80 if p48 <= 16 else 40 if p48 <= 32 else 20
            if kind in ('gyroball', 'electroball'):
                # Speed-based power (Gen 5): Gyro Ball = 25 x the target's Speed / the user's Speed + 1, at most 150;
                # Electro Ball = 150 / 120 / 80 / 60 / 40 for a user at least 4 / 3 / 2 / 1 / under 1 times as fast.
                # Only plain Speed is modeled: paralysis, held items and abilities that move the Speed are refused.
                for q in (a, df):
                    qv = self.ref(q)
                    plain = int(qv['stats']['spe'] * self.stage_mult(self.boosts.get((q, 'spe'), 0)))
                    assert qv['status'] != 'par' and self.speed(q, 2) == plain, (
                        '%s: %s\'s Speed is changed by paralysis, an item or an ability, which the power does not model' % (mv, qv['species']))
                su, st = self.speed(a, 2), self.speed(df, 2)
                if kind == 'gyroball':
                    bp = min(150, 25 * st // su + 1)
                else:
                    ratio = su // st
                    bp = 150 if ratio >= 4 else {3: 120, 2: 80, 1: 60}.get(ratio, 40)
        ab, it = av['ability'], self.item(a)
        assert ab not in ORDER_DEPENDENT_ABILITIES, '%s depends on move order' % ab
        if ab == 'Technician' and bp <= 60:   # the power the move really has (Eruption at low HP, Gyro Ball), not the listed one
            bp *= 1.5
        if ab == 'Iron Fist' and m['flags'] & FLAG_PUNCH:
            bp *= 1.2
        if ab == 'Reckless' and m['effect'] in RECOIL_EFFECTS:
            bp *= 1.2
        if ab == 'Sheer Force' and self.has_secondary(mv):
            bp *= 1.3
        if ab == 'Sand Force' and self.weather == 'sand' and m['type'] in (ROCK, GROUND, STEEL):
            bp *= 1.3
        if it in TYPE_ITEMS and TYPE_ITEMS[it] == TYPES[m['type']]:
            bp *= 1.2
        if it == 'Muscle Band' and m['class'] == PHYSICAL:
            bp *= 1.1
        if it == 'Wise Glasses' and m['class'] == SPECIAL:
            bp *= 1.1
        if av['ability'] not in MOLD_BREAKER:
            if dv['ability'] == 'Heatproof' and m['type'] == FIRE:
                bp *= 0.5
            if dv['ability'] == 'Dry Skin' and m['type'] == FIRE:
                bp *= 1.25
        return int(bp)

    def attack(self, a, mv, df):
        m = self.d.move(mv)
        av, dv = self.ref(a), self.ref(df)
        physical = m['class'] == PHYSICAL
        stat = 'atk' if physical else 'spa'
        x = av['stats'][stat] * self.stage_mult(self.stages(a, stat))
        ab, it, status = av['ability'], self.item(a), av['status']
        hp, maxhp = av['cur_hp'], av['stats']['hp']
        if physical:
            if ab in ('Huge Power', 'Pure Power'):
                x *= 2
            if ab == 'Guts' and status:
                x *= 1.5
            if ab == 'Hustle':
                x *= 1.5
            if ab == 'Toxic Boost' and status in ('psn', 'tox'):
                x *= 1.5
            if ab == 'Slow Start':
                x *= 0.5
            if it == 'Choice Band':
                x *= 1.5
            if it == 'Thick Club' and av['species'] in ('Cubone', 'Marowak'):
                x *= 2
        else:
            if ab == 'Flare Boost' and status == 'brn':
                x *= 1.5
            if ab == 'Solar Power' and self.weather == 'sun':
                x *= 1.5
            if it == 'Choice Specs':
                x *= 1.5
            if it == 'Deep Sea Tooth' and av['species'] == 'Clamperl':
                x *= 2
        if ab == 'Defeatist' and hp * 2 <= maxhp:
            x *= 0.5
        if ab in PINCH_ABILITIES and hp * 3 <= maxhp and TYPES[m['type']] == PINCH_ABILITIES[ab]:
            x *= 1.5
        if it == 'Light Ball' and av['species'] == 'Pikachu':
            x *= 2
        if dv['ability'] == 'Thick Fat' and m['type'] in (FIRE, ICE) and ab not in MOLD_BREAKER:
            x *= 0.5
        return int(x)

    def defense(self, a, mv, df):
        m = self.d.move(mv)
        av, dv = self.ref(a), self.ref(df)
        physical = m['class'] == PHYSICAL or m['effect'] == PSYSHOCK
        x = dv['stats']['def' if physical else 'spd']
        x *= self.stage_mult(self.boosts.get((df, 'def' if physical else 'spd'), 0))
        ab, it = dv['ability'], self.item(df)
        breaker = av['ability'] in MOLD_BREAKER
        if physical:
            if ab == 'Marvel Scale' and dv['status'] and not breaker:
                x *= 1.5
        else:
            if self.weather == 'sand' and ROCK in dv['types']:
                x *= 1.5
            if it == 'Deep Sea Scale' and dv['species'] == 'Clamperl':
                x *= 2
        return int(x)

    def damage(self, a, mv, df):
        """(min, max) of one hit, as the Gen 5 formula with the modifiers in the module docstring."""
        m = self.d.move(mv)
        if m['class'] == STATUS:
            return (0, 0)
        eff = self.effectiveness(a, mv, df)
        if eff == 0:
            return (0, 0)
        av, dv = self.ref(a), self.ref(df)
        bp, A, D = self.power(a, mv, df), self.attack(a, mv, df), self.defense(a, mv, df)
        base = (2 * av['level'] // 5 + 2) * bp * A // D // 50 + 2
        if self.double and m['target'] in (4, 5):
            others = len(self.foes(a)) + (len(self.actives[self.side(a)]) - 1 if m['target'] == 4 else 0)
            if others >= 2:
                base = base * 0.75
        if self.weather == 'rain':
            base *= {FIRE: 0.5, WATER: 1.5}.get(m['type'], 1)
        if self.weather == 'sun':
            base *= {FIRE: 1.5, WATER: 0.5}.get(m['type'], 1)
        breaker = av['ability'] in MOLD_BREAKER
        out = []
        for roll in (85, 100):
            v = int(base * roll / 100)
            if m['type'] in av['types']:
                v = int(v * (2 if av['ability'] == 'Adaptability' else 1.5))
            v = int(v * eff)
            if av['status'] == 'brn' and m['class'] == PHYSICAL and av['ability'] != 'Guts':
                v //= 2
            final = 1.0
            if not breaker:
                if dv['ability'] == 'Multiscale' and dv['cur_hp'] == dv['stats']['hp']:
                    final *= 0.5
                if dv['ability'] in ('Filter', 'Solid Rock') and eff > 1:
                    final *= 0.75
            if av['ability'] == 'Tinted Lens' and eff < 1:
                final *= 2
            it = self.item(a)
            if it == 'Expert Belt' and eff > 1:
                final *= 1.2
            if it == 'Life Orb':
                final *= 1.3
            dit = self.item(df)
            if dit in RESIST_BERRIES and TYPES[m['type']] == RESIST_BERRIES[dit] and (eff > 1 or m['type'] == NORMAL):
                final *= 0.5
            v = int(v * final)
            out.append(max(1, v))
        return tuple(out)

    def total(self, a, mv, df, sure):
        """Damage of the whole move: the minimum hits times the minimum per hit for a sure claim, else the maximum."""
        lo, hi = self.damage(a, mv, df)
        lo_n, hi_n = self.hits(mv)
        if self.ref(a)['ability'] == 'Skill Link':
            lo_n = hi_n
        return lo * lo_n if sure else hi * hi_n

    def endures(self, a, mv, df):
        """Focus Sash, or Gen 5 Sturdy, at full HP against a single-hit move: the holder keeps 1 HP."""
        dv = self.ref(df)
        if dv['cur_hp'] != dv['stats']['hp'] or self.hits(mv)[1] > 1:
            return False
        if self.item(df) == 'Focus Sash':
            return True
        return dv['ability'] == 'Sturdy' and self.ref(a)['ability'] not in MOLD_BREAKER

    def speed(self, r, par_divisor):
        v = self.ref(r)
        x = v['stats']['spe'] * self.stage_mult(self.boosts.get((r, 'spe'), 0))
        ab, it = v['ability'], self.item(r)
        if ab == 'Quick Feet' and v['status']:
            x *= 1.5
        if ab in WEATHER_SPEED and WEATHER_SPEED[ab] == self.weather:
            x *= 2
        if ab == 'Slow Start':
            x *= 0.5
        if it == 'Choice Scarf':
            x *= 1.5
        if it in ('Iron Ball', 'Macho Brace'):
            x *= 0.5
        if v['status'] == 'par' and ab != 'Quick Feet':      # last; Quick Feet lifts it (rc27 engine fix)
            x /= par_divisor
        return int(x)

    def moves_last(self, r):
        return self.item(r) in ('Lagging Tail', 'Full Incense') or self.ability(r) == 'Stall'


def _op(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(Ctx(d, views, c, ref))
        return fn
    return reg


@_op('mko')
def mko(x):
    """('mko', a, mv, df): a sure KO with items and abilities: minimum damage x 0.9 >= current HP, and
    the target cannot hang on through Focus Sash or Sturdy."""
    a, mv, df = x.args
    lo = x.total(a, mv, df, True)
    hp = x.ref(df)['cur_hp']
    assert not x.endures(a, mv, df), '%s: %s keeps 1 HP (Focus Sash / Sturdy at full HP)' % (mv, x.ref(df)['species'])
    assert lo * 0.9 >= hp, '%s does %d-%d to %s at %d HP: not a sure KO' % (mv, lo, x.total(a, mv, df, False), x.ref(df)['species'], hp)


@_op('mnoko')
def mnoko(x):
    """('mnoko', a, mv, df): cannot KO with items and abilities: maximum damage x 1.1 < current HP."""
    a, mv, df = x.args
    hi = x.total(a, mv, df, False)
    hp = x.ref(df)['cur_hp']
    assert hi * 1.1 < hp, '%s does %d-%d to %s at %d HP: can KO' % (mv, x.total(a, mv, df, True), hi, x.ref(df)['species'], hp)


@_op('mnoko_at')
def mnoko_at(x):
    """('mnoko_at', a, mv, df, frac): cannot KO from that HP fraction, with items and abilities (Multiscale
    counts only when frac is 1)."""
    a, mv, df, frac = x.args
    dv = x.ref(df)
    saved = dv['cur_hp']
    dv['cur_hp'] = int(dv['stats']['hp'] * frac)
    try:
        hi = x.total(a, mv, df, False)
        assert hi * 1.1 < dv['cur_hp'], '%s does up to %d: can KO %s from %d HP' % (mv, hi, dv['species'], dv['cur_hp'])
    finally:
        dv['cur_hp'] = saved


@_op('mko_at')
def mko_at(x):
    """('mko_at', a, mv, df, frac): a sure KO even from that HP fraction of the target, with items and abilities
    (Multiscale counts when frac is 1): minimum damage x 0.9 >= that HP, no Focus Sash / Sturdy hold."""
    a, mv, df, frac = x.args
    dv = x.ref(df)
    saved = dv['cur_hp']
    dv['cur_hp'] = int(dv['stats']['hp'] * frac)
    try:
        lo = x.total(a, mv, df, True)
        assert not x.endures(a, mv, df), '%s: %s keeps 1 HP (Focus Sash / Sturdy at full HP)' % (mv, dv['species'])
        assert lo * 0.9 >= dv['cur_hp'], '%s does %d at least: not a sure KO on %s from %d HP' % (mv, lo, dv['species'], dv['cur_hp'])
    finally:
        dv['cur_hp'] = saved


@_op('mbeats')
def mbeats(x):
    """('mbeats', a, m1, m2, df): m1's minimum (minimum hits) beats m2's maximum (maximum hits) by 5%,
    with items and abilities."""
    a, m1, m2, df = x.args
    lo1, hi2 = x.total(a, m1, df, True), x.total(a, m2, df, False)
    assert lo1 > hi2 * 1.05, '%s (%d-%d) does not clearly out-damage %s (%d-%d) on %s' % (
        m1, lo1, x.total(a, m1, df, False), m2, x.total(a, m2, df, True), hi2, x.ref(df)['species'])


@_op('mfrac')
def mfrac(x):
    """('mfrac', a, mv, df, lo, hi): the move's damage, with items and abilities, is between lo and hi of
    the target's maximum HP (minimum damage >= lo, maximum damage <= hi)."""
    a, mv, df, lo_f, hi_f = x.args
    lo, hi = x.total(a, mv, df, True), x.total(a, mv, df, False)
    maxhp = x.ref(df)['stats']['hp']
    assert lo >= lo_f * maxhp and hi <= hi_f * maxhp, '%s does %d-%d to %s (max HP %d): not within %s-%s of it' % (
        mv, lo, hi, x.ref(df)['species'], maxhp, lo_f, hi_f)


@_op('endures')
def endures(x):
    """('endures', df, a, mv): the target is at full HP with Focus Sash, or with Gen 5 Sturdy against an
    attacker without Mold Breaker, and the move hits once: it keeps at least 1 HP."""
    df, a, mv = x.args
    assert x.endures(a, mv, df), '%s does not hang on against %s (needs full HP, Focus Sash or Sturdy, one hit)' % (
        x.ref(df)['species'], mv)


@_op('meff')
def meff(x):
    """('meff', a, mv, df, want): effectiveness with Mold Breaker, Scrappy, Iron Ball, Soundproof, Bulletproof,
    Wonder Guard and the type-immune abilities."""
    a, mv, df, want = x.args
    got = x.effectiveness(a, mv, df)
    assert got == want, '%s from %s vs %s: effectiveness %s, claimed %s' % (mv, x.ref(a)['species'], x.ref(df)['species'], got, want)


@_op('mfaster')
def mfaster(x):
    """('mfaster', p, q): p moves before q with Choice Scarf (1.5), Iron Ball and Macho Brace (0.5), Quick
    Feet (1.5 with a status), Swift Swim / Chlorophyll / Sand Rush / Slush Rush in their weather (2), Slow Start
    (0.5), paralysis (half, applied last; Quick Feet lifts it since the rc27 engine fix), and Lagging
    Tail / Full Incense / Stall (always last)."""
    p, q = x.args
    if x.moves_last(q) and not x.moves_last(p):
        return
    assert not x.moves_last(p), '%s always moves last' % x.ref(p)['species']
    for div in (2,):
        sp, sq = x.speed(p, div), x.speed(q, div)
        assert sp > sq, '%s (%d) is not faster than %s (%d) (paralysis /%d)' % (x.ref(p)['species'], sp, x.ref(q)['species'], sq, div)


@_op('mpri')
def mpri(x):
    """('mpri', a, mv, want): the move's priority for that user: Prankster adds 1 to status moves."""
    a, mv, want = x.args
    m = x.d.move(mv)
    pri = m['priority'] + (1 if x.ability(a) == 'Prankster' and m['class'] == STATUS else 0)
    assert pri == want, '%s from %s has priority %d, claimed %d' % (mv, x.ref(a)['species'], pri, want)


@_op('nhko')
def nhko(x):
    """('nhko', a, mv, df, n): n hits of the move are a sure KO (n x minimum damage x 0.9 >= current HP) even
    with Leftovers or Black Sludge (a Poison type) healing a sixteenth between hits."""
    a, mv, df, n = x.args
    lo = x.total(a, mv, df, True)
    dv = x.ref(df)
    heal = (n - 1) * dv['stats']['hp'] // 16 if x.item(df) in ('Leftovers', 'Black Sludge') else 0
    assert n * lo * 0.9 >= dv['cur_hp'] + heal, '%s x%d does %d: not a sure KO on %s at %d HP (+%d healed)' % (
        mv, n, n * lo, dv['species'], dv['cur_hp'], heal)


@_op('no_nhko')
def no_nhko(x):
    """('no_nhko', a, mv, df, n): n hits of the move cannot KO (n x maximum damage x 1.1 < current HP)."""
    a, mv, df, n = x.args
    hi = x.total(a, mv, df, False)
    dv = x.ref(df)
    assert n * hi * 1.1 < dv['cur_hp'], '%s x%d does up to %d: can KO %s at %d HP' % (mv, n, n * hi, dv['species'], dv['cur_hp'])


@_op('counter_kos')
def counter_kos(x):
    """('counter_kos', e, mv, p): e's Counter (physical) or Mirror Coat (special) answers p's move mv: the
    move's class matches, e survives it (maximum x 1.1 < HP) and twice its minimum damage x 0.9 >= p's HP."""
    e, mv, p = x.args
    m = x.d.move(mv)
    moves = {n.lower() for n in x.ref(e)['moves']}
    want = PHYSICAL if 'counter' in moves else SPECIAL
    assert m['class'] == want, '%s is not the class %s answers' % (mv, 'Counter' if want == PHYSICAL else 'Mirror Coat')
    lo, hi = x.total(p, mv, e, True), x.total(p, mv, e, False)
    assert hi * 1.1 < x.ref(e)['cur_hp'], '%s can KO %s before it counters' % (mv, x.ref(e)['species'])
    assert 2 * lo * 0.9 >= x.ref(p)['cur_hp'], 'twice %s\'s minimum (%d) does not surely KO %s at %d HP' % (
        mv, 2 * lo, x.ref(p)['species'], x.ref(p)['cur_hp'])


@_op('recoil_kos_user')
def recoil_kos_user(x):
    """('recoil_kos_user', a, mv, df): using the move knocks the user out: Life Orb (a tenth of max HP, after
    the hit, not with Magic Guard or a Sheer Force-boosted move) or the move's own recoil (its fraction of the
    damage dealt, capped at the target's HP, minimum roll, 0.9 margin)."""
    a, mv, df = x.args
    av = x.ref(a)
    m = x.d.move(mv)
    r = x.d.moves[m['id']]
    rec = int.from_bytes(r[18:19], 'little', signed=True)
    hp, maxhp = av['cur_hp'], av['stats']['hp']
    if av['ability'] == 'Magic Guard':
        raise AssertionError('Magic Guard takes no recoil')
    loss = 0
    if x.item(a) == 'Life Orb' and not (av['ability'] == 'Sheer Force' and x.has_secondary(mv)):
        loss += max(1, maxhp // 10)
    if rec < 0 and av['ability'] != 'Rock Head':
        dealt = min(x.total(a, mv, df, True), x.ref(df)['cur_hp'])
        loss += int(dealt * (-rec) / 100 * 0.9)
    assert loss >= hp, '%s costs %s %d HP, it has %d: it survives' % (mv, av['species'], loss, hp)


@_op('contact_recoil_kos')
def contact_recoil_kos(x):
    """('contact_recoil_kos', a, mv, df): the move makes contact and the target's Iron Barbs (an eighth of the
    attacker's max HP), Rough Skin (counted as Gen 4's sixteenth, so the claim holds under Gen 5's eighth too)
    or Rocky Helmet (a sixth) knocks the attacker out, whether or not the hit KOs the target."""
    a, mv, df = x.args
    av, dv = x.ref(a), x.ref(df)
    m = x.d.move(mv)
    assert m['flags'] & FLAG_CONTACT, '%s makes no contact' % mv
    assert av['ability'] != 'Magic Guard', 'Magic Guard takes no contact damage'
    loss = 0
    if dv['ability'] == 'Iron Barbs':
        loss = max(loss, av['stats']['hp'] // 8)
    if dv['ability'] == 'Rough Skin':
        loss = max(loss, av['stats']['hp'] // 16)
    if x.item(df) == 'Rocky Helmet':
        loss = max(loss, av['stats']['hp'] // 6)
    assert loss, '%s has neither Iron Barbs, Rough Skin nor Rocky Helmet' % dv['species']
    assert loss >= av['cur_hp'], 'contact costs %s %d HP, it has %d: it survives' % (av['species'], loss, av['cur_hp'])


@_op('ally_immune')
def ally_immune(x):
    """('ally_immune', e1, e0, mv): e0's spread move (target 4: every other Pokémon) does nothing to its
    partner e1: Telepathy, a type immunity, or a type-immune ability."""
    ally, a, mv = x.args
    m = x.d.move(mv)
    assert x.double, 'ally_immune is a doubles claim'
    assert x.side(ally) == x.side(a) and ally != a, '%s is not %s\'s partner' % (ally, a)
    assert m['target'] == 4, '%s does not hit the partner at all' % mv
    if x.ability(ally) == 'Telepathy':
        return
    assert x.effectiveness(a, mv, ally) == 0, '%s hits the partner %s' % (mv, x.ref(ally)['species'])


@_op('redirected')
def redirected(x):
    """('redirected', e0, mv, e1): in a double, e0's single-target Electric move (Water for Storm Drain) is drawn
    to its own partner e1 by Lightningrod (Storm Drain), so it never reaches a foe (Gen 4 and 5 both redirect;
    Gen 5 also absorbs it)."""
    a, mv, ally = x.args
    m = x.d.move(mv)
    assert x.double, 'redirected is a doubles claim'
    assert x.side(ally) == x.side(a) and ally != a, '%s is not %s\'s partner' % (ally, a)
    assert m['target'] == 0, '%s is not a single-target move' % mv
    drawn = {'Lightningrod': T['Electric'], 'Storm Drain': T['Water']}.get(x.ability(ally))
    assert drawn == m['type'], '%s\'s %s does not draw %s' % (x.ref(ally)['species'], x.ability(ally), mv)


@_op('has_item')
def has_item(x):
    """('has_item', r, item): the Pokémon holds that item (a readable claim next to the key it explains)."""
    r, it = x.args
    assert x.items.get(r) == it, '%s holds %s, not %s' % (x.ref(r)['species'], x.items.get(r), it)


@_op('weather')
def weather(x):
    """('weather', kind): the weather at turn 1 from the actives' entry abilities ('rain', 'sun', 'sand', 'hail', None)."""
    (kind,) = x.args
    assert x.weather == kind, 'weather is %s, claimed %s' % (x.weather, kind)


# --- batch 02: turn order, multi-turn races and end-of-turn damage
STAT_IDS = {1: 'atk', 2: 'def', 3: 'spa', 4: 'spd', 5: 'spe'}   # move data stat ids (6 accuracy, 7 evasion: ignored)
# Fly, Dive, Dig, Bounce, Sky Attack, Shadow Force, Focus Punch: not one turn's attack; Solar Beam only in sun.
TWO_TURN_EFFECTS = {155, 255, 256, 263, 75, 272, 170}
SOLAR_BEAM, RECHARGE, SELF_KO, FAKE_OUT, SUCKER = 151, 80, 7, 158, 248
SAND_IMMUNE_TYPES, SAND_IMMUNE_ABILITIES = {ROCK, GROUND, STEEL}, {'Sand Veil', 'Sand Rush', 'Sand Force', 'Overcoat', 'Magic Guard'}
HAIL_IMMUNE_ABILITIES = {'Ice Body', 'Snow Cloak', 'Slush Rush', 'Overcoat', 'Magic Guard'}
POISON = T['Poison']
STATUS_BERRIES = {'Lum Berry', 'Cheri Berry', 'Pecha Berry', 'Rawst Berry', 'Aspear Berry', 'Chesto Berry', 'Persim Berry'}
DROP_BLOCKERS = {'atk': {'Clear Body', 'White Smoke', 'Hyper Cutter'}, 'def': {'Clear Body', 'White Smoke', 'Big Pecks'},
                 'spa': {'Clear Body', 'White Smoke'}, 'spd': {'Clear Body', 'White Smoke'}, 'spe': {'Clear Body', 'White Smoke'}}
STAGE_AMBIGUOUS = {'Contrary', 'Simple', 'Defiant', 'Competitive'}   # a drop means something else: refused in a race
WEATHER_ACCURACY = {'Thunder': {'rain': 100, 'sun': 50}, 'Hurricane': {'rain': 100, 'sun': 50}, 'Blizzard': {'hail': 100}}
OHKO_EFFECT = 38


class Race:
    """The two actives trade one move each per turn (see the module docstring, batch 02)."""

    def __init__(self, x, favored, par_div, burn_div):
        self.x, self.favored, self.par_div, self.burn_div = x, favored, par_div, burn_div
        assert not x.double, 'the race is a singles claim'

    def vet_move(self, a, mv, df):
        x, m = self.x, self.x.d.move(mv)
        r = x.d.moves[m['id']]
        assert m['class'] != STATUS, '%s is a status move: the race plays attacks' % mv
        assert m['effect'] not in TWO_TURN_EFFECTS, '%s takes two turns' % mv
        assert m['effect'] != SOLAR_BEAM or x.weather == 'sun', 'Solar Beam charges outside sun'
        assert m['effect'] != FAKE_OUT, 'Fake Out works on the first turn only'
        assert m['effect'] != SELF_KO or x.ref(df)['ability'] != 'Damp', '%s fails against Damp' % mv
        rec = int.from_bytes(r[18:19], 'little', signed=True)
        assert not (rec > 0 and x.ref(df)['ability'] == 'Liquid Ooze'), 'Liquid Ooze reverses the drain'
        for q in (a, df):
            assert x.item(q) != 'Shell Bell', 'Shell Bell is not modeled in a race'
            assert not (x.item(q) in STATUS_BERRIES and x.ref(q)['status']), '%s would eat its %s at once' % (x.ref(q)['species'], x.item(q))
            assert x.ability(q) not in STAGE_AMBIGUOUS, '%s changes what a stat drop does' % x.ability(q)
        if r[1] in (Q_USER_STAT, Q_TARGET_DROP):
            for k in range(3):
                assert r[21 + k] in (0, 6, 7) or r[21 + k] in STAT_IDS, '%s changes a stat the race does not model' % mv

    def order(self, moves):
        """Actors in the order they move: priority, then speed; Lagging Tail / Stall last in the bracket; no ties."""
        x = self.x
        keys = {}
        for r, mv in moves.items():
            m = x.d.move(mv)
            pri = m['priority'] + (1 if x.ability(r) == 'Prankster' and m['class'] == STATUS else 0)
            keys[r] = (-pri, 1 if x.moves_last(r) else 0, -x.speed(r, self.par_div))
        rs = sorted(moves, key=lambda r: keys[r])
        for p, q in zip(rs, rs[1:]):
            assert keys[p] != keys[q], 'speed tie between %s and %s (%d): the order is not deterministic' % (
                x.ref(p)['species'], x.ref(q)['species'], x.speed(p, self.par_div))
        return rs

    def chip(self, r, hp, tox_n):
        """End-of-turn HP change for r, in the Gen 5 order: weather, abilities, item, status. Returns the new HP."""
        x = self.x
        v = x.ref(r)
        mx, ab, it, types = v['stats']['hp'], v['ability'], x.item(r), set(v['types'])
        guard = ab == 'Magic Guard'
        if x.weather == 'sand' and not (types & SAND_IMMUNE_TYPES) and ab not in SAND_IMMUNE_ABILITIES:
            hp -= max(1, mx // 16)
        if x.weather == 'hail' and ICE not in types and ab not in HAIL_IMMUNE_ABILITIES:
            hp -= max(1, mx // 16)
        if hp <= 0:
            return hp
        if ab == 'Ice Body' and x.weather == 'hail':
            hp = min(mx, hp + mx // 16)
        if ab == 'Rain Dish' and x.weather == 'rain':
            hp = min(mx, hp + mx // 16)
        if ab == 'Dry Skin' and x.weather == 'rain':
            hp = min(mx, hp + mx // 8)
        if ab == 'Dry Skin' and x.weather == 'sun' and not guard:
            hp -= max(1, mx // 8)
        if it == 'Leftovers':
            hp = min(mx, hp + mx // 16)
        if it == 'Black Sludge':
            if POISON in types:
                hp = min(mx, hp + mx // 16)
            elif not guard:
                hp -= max(1, mx // 8)
        if hp <= 0:
            return hp
        st = v['status']
        if st in ('psn', 'tox'):
            if ab == 'Poison Heal':
                hp = min(mx, hp + mx // 8)
            elif not guard:
                hp -= max(1, mx // 8) if st == 'psn' else max(1, mx * tox_n // 16)
        if st == 'brn' and not guard:
            d = mx // self.burn_div
            if ab == 'Heatproof':
                d //= 2
            hp -= max(1, d)
        return hp

    def setup_boosts(self, a, mv):
        """(stat, stages) a self-boosting status move gives its user (Swords Dance, Dragon Dance, Calm Mind, Agility...)."""
        x = self.x
        m = x.d.move(mv)
        r = x.d.moves[m['id']]
        assert m['class'] == STATUS and r[20] == 7 and r[1] == 2, '%s is not a plain self-boosting move' % mv
        assert x.ability(a) not in STAGE_AMBIGUOUS, '%s changes what a stat boost does' % x.ability(a)
        out = []
        for k in range(3):
            sid, amt = r[21 + k], int.from_bytes(r[24 + k:25 + k], 'little', signed=True)
            if sid and amt:
                assert sid in STAT_IDS and amt > 0, '%s changes a stat the race does not model' % mv
                out.append((STAT_IDS[sid], amt))
        assert out, '%s boosts nothing' % mv
        return out

    def play(self, a, mv_a, b, mv_b, max_turns, setup=None, start_boosts=None):
        """The turn (1-based) on which b faints with a still standing, or None. With `setup`, a spends turn 1 on that
        self-boosting move (the boosts apply after it moves) and attacks with mv_a from turn 2. `start_boosts` ({(ref, stat):
        stages}) are already in force on turn 1 (a boost kept from an earlier turn)."""
        x = self.x
        self.vet_move(a, mv_a, b)
        self.vet_move(b, mv_b, a)
        boosts_gained = self.setup_boosts(a, setup) if setup else []
        va, vb = x.ref(a), x.ref(b)
        saved = {a: va['cur_hp'], b: vb['cur_hp']}
        hp = dict(saved)
        tox = {r: (2 if r == self.favored else 1) for r in (a, b)}
        recharge = {a: False, b: False}
        x.boosts.clear()
        x.boosts.update(start_boosts or {})
        x.consumed.clear()
        try:
            for turn in range(1, max_turns + 1):
                acted = set()
                moves = {a: setup if (setup and turn == 1) else mv_a, b: mv_b}
                for r in self.order(moves):
                    t = b if r == a else a
                    if hp[r] <= 0 or hp[t] <= 0:
                        continue
                    if recharge[r]:
                        recharge[r] = False
                        acted.add(r)
                        continue
                    if setup and turn == 1 and r == a:
                        for stat, amt in boosts_gained:
                            x.boosts[(a, stat)] = max(-6, min(6, x.boosts.get((a, stat), 0) + amt))
                        acted.add(r)
                        continue
                    mv = moves[r]
                    m = x.d.move(mv)
                    rec = int.from_bytes(x.d.moves[m['id']][18:19], 'little', signed=True)
                    sure = r == self.favored
                    x.ref(r)['cur_hp'], x.ref(t)['cur_hp'] = hp[r], hp[t]
                    dmg = x.total(r, mv, t, sure) * (0.9 if sure else 1.1)
                    if m['effect'] == SUCKER and t in acted:
                        dmg = 0
                    if x.endures(r, mv, t):
                        dmg = min(dmg, hp[t] - 1)
                        if x.item(t) == 'Focus Sash':
                            x.consumed.add(t)
                    dealt = min(int(dmg), hp[t])
                    hp[t] -= dealt
                    acted.add(r)
                    if dealt and x.item(r) == 'Life Orb' and x.ability(r) != 'Magic Guard' and not (
                            x.ability(r) == 'Sheer Force' and x.has_secondary(mv)):
                        hp[r] -= max(1, va['stats']['hp'] // 10) if r == a else max(1, vb['stats']['hp'] // 10)
                    if dealt and rec > 0:
                        hp[r] = min(x.ref(r)['stats']['hp'], hp[r] + max(1, dealt * rec // 100))
                    if dealt and rec < 0 and x.ability(r) not in ('Rock Head', 'Magic Guard'):
                        # the favored side's recoil is taken from the most it could have dealt
                        basis = min(x.total(r, mv, t, False), hp[t] + dealt) if sure else dealt
                        hp[r] -= max(1, basis * (-rec) // 100)
                    if m['effect'] == SELF_KO:
                        hp[r] = 0
                    if m['effect'] == RECHARGE and dealt:
                        recharge[r] = True
                    rr = x.d.moves[m['id']]
                    if rr[1] in (Q_USER_STAT, Q_TARGET_DROP) and x.effectiveness(r, mv, t) != 0:
                        who = r if rr[1] == Q_USER_STAT else t
                        for k in range(3):
                            stat, amt, chance = STAT_IDS.get(rr[21 + k]), int.from_bytes(rr[24 + k:25 + k], 'little', signed=True), rr[27 + k]
                            if stat and amt and chance == 100:
                                if who == t and amt < 0 and x.ability(t) in DROP_BLOCKERS[stat] and x.ability(r) not in MOLD_BREAKER:
                                    continue
                                x.boosts[(who, stat)] = max(-6, min(6, x.boosts.get((who, stat), 0) + amt))
                    for q in (r, t):   # berries, after the damage and recoil of this action
                        mxq = x.ref(q)['stats']['hp']
                        if 0 < hp[q] <= mxq // 2 and x.item(q) in ('Sitrus Berry', 'Oran Berry'):
                            hp[q] = min(mxq, hp[q] + (mxq // 4 if x.item(q) == 'Sitrus Berry' else 10))
                            x.consumed.add(q)
                    if hp[t] <= 0 or hp[r] <= 0:
                        break
                if hp[a] > 0 and hp[b] > 0:
                    for r in self.order(moves):
                        hp[r] = self.chip(r, hp[r], tox[r])
                        if x.ref(r)['status'] == 'tox':
                            tox[r] += 1
                if hp[b] <= 0 and hp[a] > 0:
                    return turn
                if hp[a] <= 0:
                    return None
            return None
        finally:
            va['cur_hp'], vb['cur_hp'] = saved[a], saved[b]
            x.boosts.clear()
            x.consumed.clear()


def _race_moves(x, r, spec):
    """'*' means every damaging move of r; otherwise the one move named."""
    if spec != '*':
        return [spec]
    out = [mv for mv in x.ref(r)['moves'] if x.d.move(mv)['class'] != STATUS]
    assert out, '%s has no attack' % x.ref(r)['species']
    return out


ENTRY_ABILITIES = {'Intimidate', 'Download', 'Drizzle', 'Drought', 'Sand Stream', 'Snow Warning', 'Cloud Nine', 'Air Lock'}


def _actives(x, a, b):
    """The two fighters of a race: one of each side, normally the actives e0 and p0. A bench member may stand in for an active
    that is about to faint (the field is then as it is now: the weather stays, and the actives' abilities are not repeated),
    so a newcomer with an entry ability, or an Intimidate / Download holder opposite one, is refused."""
    assert a[0] != b[0] and a[0] in 'ep' and b[0] in 'ep', 'a race is between one Pokémon of each side'
    for r in (a, b):
        x.ref(r)
    if {a, b} != {'e0', 'p0'}:
        for r in (a, b):
            ab = x.ability(r)
            assert ab not in ('Intimidate', 'Download') and (r in ('e0', 'p0') or ab not in ENTRY_ABILITIES), (
                '%s has %s: an entry ability would change the field when a bench member comes in' % (x.ref(r)['species'], ab))


@_op('race')
def race(x):
    """('race', a, mv_a, b, mv_b, n): a, using mv_a every turn, knocks out b (using mv_b every turn; '*' = any of
    its attacks, each tried) within n turns and is still standing, under the race rules in the module docstring
    (a's minimum damage x 0.9, b's maximum x 1.1, both paralysis and both burn rules, the end-of-turn damage)."""
    a, mv_a, b, mv_b, n = x.args
    _actives(x, a, b)
    for mb in _race_moves(x, b, mv_b):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                turn = Race(x, a, par_div, burn_div).play(a, mv_a, b, mb, n)
                assert turn is not None, '%s\'s %s does not surely beat %s\'s %s within %d turns (paralysis /%d, burn /%d)' % (
                    x.ref(a)['species'], mv_a, x.ref(b)['species'], mb, n, par_div, burn_div)


@_op('loses')
def loses(x):
    """('loses', a, mv_a, b, mv_b): a, using mv_a every turn ('*' = any of its attacks, each tried), is knocked out by
    b's mv_b before it can knock b out, however many turns it takes (within 12): b is the favored side, so b's
    minimum x 0.9 and a's maximum x 1.1 are used, under both paralysis and both burn rules."""
    a, mv_a, b, mv_b = x.args
    _actives(x, a, b)
    for ma in _race_moves(x, a, mv_a):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                turn = Race(x, b, par_div, burn_div).play(b, mv_b, a, ma, 12)
                assert turn is not None, '%s\'s %s is not surely beaten by %s\'s %s (paralysis /%d, burn /%d)' % (
                    x.ref(a)['species'], ma, x.ref(b)['species'], mv_b, par_div, burn_div)


@_op('first')
def first(x):
    """('first', a, mv_a, b, mv_b): a's move goes before b's: higher priority (Prankster +1 on a status move), or the
    same priority and a faster under both paralysis rules (Choice Scarf, weather speed, Quick Feet, Iron Ball...),
    Lagging Tail / Full Incense / Stall last in their bracket; a speed tie is refused."""
    a, mv_a, b, mv_b = x.args
    for par_div in (4, 2):
        rs = Race(x, a, par_div, 8).order({a: mv_a, b: mv_b})
        assert rs[0] == a, '%s\'s %s does not go before %s\'s %s (paralysis /%d)' % (
            x.ref(a)['species'], mv_a, x.ref(b)['species'], mv_b, par_div)


def _chip_range(x, r):
    """(least, most) end-of-turn damage r takes this turn: burn a sixteenth or an eighth, bad poison 1/16 or 2/16."""
    hp = x.ref(r)['cur_hp']
    worst = min(Race(x, r, 4, 16).chip(r, hp, 1), Race(x, r, 4, 8).chip(r, hp, 2))
    best = max(Race(x, r, 4, 16).chip(r, hp, 1), Race(x, r, 4, 8).chip(r, hp, 2))
    return hp - best, hp - worst


@_op('chip_kos')
def chip_kos(x):
    """('chip_kos', r): the end-of-turn damage alone (sandstorm, hail, poison, bad poison at its first tick, burn at a
    sixteenth, Black Sludge; less Leftovers and the healing abilities) knocks r out this turn, whatever it does."""
    (r,) = x.args
    least, most = _chip_range(x, r)
    v = x.ref(r)
    assert least >= v['cur_hp'], '%s at %d HP loses only %d-%d at the end of the turn' % (v['species'], v['cur_hp'], least, most)


@_op('chip_survives')
def chip_survives(x):
    """('chip_survives', r): the end-of-turn damage cannot knock r out this turn even at its worst (burn an eighth, bad
    poison 2/16)."""
    (r,) = x.args
    least, most = _chip_range(x, r)
    v = x.ref(r)
    assert most < v['cur_hp'], '%s at %d HP can lose %d at the end of the turn' % (v['species'], v['cur_hp'], most)


@_op('survives_recoil')
def survives_recoil(x):
    """('survives_recoil', a, mv, df): using the move does not knock the user out: Magic Guard or Rock Head where they
    apply, else the Life Orb tenth plus the move's recoil (from the most it can deal) x 1.1 stays under its HP."""
    a, mv, df = x.args
    av = x.ref(a)
    m = x.d.move(mv)
    rec = int.from_bytes(x.d.moves[m['id']][18:19], 'little', signed=True)
    hp, maxhp = av['cur_hp'], av['stats']['hp']
    loss = 0
    if av['ability'] != 'Magic Guard':
        if x.item(a) == 'Life Orb' and not (av['ability'] == 'Sheer Force' and x.has_secondary(mv)):
            loss += max(1, maxhp // 10)
        if rec < 0 and av['ability'] != 'Rock Head':
            dealt = min(x.total(a, mv, df, False), x.ref(df)['cur_hp'])
            loss += int(dealt * (-rec) / 100 * 1.1)
    assert loss < hp, '%s costs %s up to %d HP, it has %d: it may faint' % (mv, av['species'], loss, hp)


@_op('macc')
def macc(x):
    """('macc', a, mv, df, want): the move's accuracy against that target as a whole percentage: 100 for a move that
    never misses or with No Guard on either side; Thunder and Hurricane 100 in rain and 50 in sun, Blizzard 100 in
    hail; then Hustle x0.8 on physical moves, Compoundeyes x1.3, Victory Star x1.1, Wide Lens x1.1, Sand Veil in
    sand / Snow Cloak in hail x0.8, Bright Powder / Lax Incense x0.9, capped at 100. One-hit KO moves are refused."""
    a, mv, df, want = x.args
    m = x.d.move(mv)
    assert m['effect'] != OHKO_EFFECT, '%s\'s accuracy depends on the levels' % mv
    acc = m['accuracy']
    aa, da = x.ability(a), x.ability(df)
    if acc == 101 or 'No Guard' in (aa, da):
        got = 100
    else:
        acc = WEATHER_ACCURACY.get(x.d.move_name[m['id']], {}).get(x.weather, acc)
        mult = 1.0
        if aa == 'Hustle' and m['class'] == PHYSICAL:
            mult *= 0.8
        if aa == 'Compoundeyes':
            mult *= 1.3
        if aa == 'Victory Star':
            mult *= 1.1
        if x.item(a) == 'Wide Lens':
            mult *= 1.1
        if (da == 'Sand Veil' and x.weather == 'sand') or (da == 'Snow Cloak' and x.weather == 'hail'):
            mult *= 0.8
        if x.item(df) in ('Bright Powder', 'Lax Incense'):
            mult *= 0.9
        got = min(100, int(acc * mult))
    assert got == want, '%s from %s on %s has accuracy %d, claimed %d' % (mv, x.ref(a)['species'], x.ref(df)['species'], got, want)


@_op('status_only')
def status_only(x):
    """('status_only', r): every move r has is a status move, so it cannot attack this turn (Sucker Punch and
    Thunderclap fail against it, Counter and Mirror Coat have nothing to return)."""
    (r,) = x.args
    bad = [mv for mv in x.ref(r)['moves'] if x.d.move(mv)['class'] != STATUS]
    assert not bad, '%s can attack with %s' % (x.ref(r)['species'], ', '.join(bad))


@_op('no_endure')
def no_endure(x):
    """('no_endure', df, a, mv): the target cannot hang on at 1 HP against the move: it is below full HP, the move
    hits more than once, the attacker has Mold Breaker, or it has neither a Focus Sash nor Sturdy."""
    df, a, mv = x.args
    assert not x.endures(a, mv, df), '%s hangs on against %s' % (x.ref(df)['species'], mv)


@_op('setup_wins')
def setup_wins(x):
    """('setup_wins', a, setup, mv_a, b, mv_b, n): a spends turn 1 on `setup` (a plain self-boosting status move: Swords
    Dance, Dragon Dance, Calm Mind, Agility...; the boosts apply after it moves) while b attacks with mv_b ('*' = any of
    its attacks, each tried), then attacks with mv_a: a survives and knocks b out by the end of turn n, under the race
    rules (a's minimum x 0.9, b's maximum x 1.1, both paralysis and both burn rules, boosted stats and the Speed order
    they give counted). Pair it with `loses` to show that attacking at once does not work."""
    a, setup, mv_a, b, mv_b, n = x.args
    _actives(x, a, b)
    for mb in _race_moves(x, b, mv_b):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                turn = Race(x, a, par_div, burn_div).play(a, mv_a, b, mb, n, setup=setup)
                assert turn is not None, '%s\'s %s then %s does not surely beat %s\'s %s within %d turns (paralysis /%d, burn /%d)' % (
                    x.ref(a)['species'], setup, mv_a, x.ref(b)['species'], mb, n, par_div, burn_div)


@_op('fixed_ko')
def fixed_ko(x):
    """('fixed_ko', a, mv, df): a fixed-damage move is a sure KO. Seismic Toss and Night Shade deal the user's level in HP,
    Dragon Rage 40, Sonic Boom 20 (Gen 5), whatever the stats, STAB, weather, items or roll; only a type immunity (Night
    Shade on Normal, Seismic Toss on Ghost, Dragon Rage on Fairy...) stops them. The damage x 0.9 is at least the target's
    current HP and it does not hang on at 1 HP (Focus Sash, Sturdy at full HP). Refused: a target with Wonder Guard or
    Multiscale, and a Life Orb attacker (the move itself would be fine, the recoil is not modeled)."""
    a, mv, df = x.args
    m = x.d.move(mv)
    assert m['effect'] in (FIXED_LEVEL, FIXED_DRAGON_RAGE, FIXED_SONIC_BOOM), '%s is not a fixed-damage move' % mv
    av, dv = x.ref(a), x.ref(df)
    assert x.ability(df) not in ('Wonder Guard', 'Multiscale'), '%s: %s on the target changes fixed damage in a way not modeled' % (
        dv['species'], x.ability(df))
    assert x.item(a) != 'Life Orb', 'Life Orb recoil with a fixed-damage move is not modeled'
    assert x.effectiveness(a, mv, df) != 0, '%s cannot affect %s (type or ability immunity)' % (mv, dv['species'])
    dmg = {FIXED_LEVEL: av['level'], FIXED_DRAGON_RAGE: 40, FIXED_SONIC_BOOM: 20}[m['effect']]
    assert not x.endures(a, mv, df), '%s keeps 1 HP (Focus Sash / Sturdy at full HP)' % dv['species']
    assert dmg * 0.9 >= dv['cur_hp'], '%s does exactly %d to %s at %d HP: not a sure KO' % (mv, dmg, dv['species'], dv['cur_hp'])


@_op('has_ability')
def has_ability(x):
    """('has_ability', r, ability): the Pokémon has that ability (a readable claim next to the key it explains)."""
    r, name = x.args
    assert x.ability(r) == name, '%s has %s, not %s' % (x.ref(r)['species'], x.ability(r), name)


@_op('pivot')
def pivot(x):
    """('pivot', mv): the move deals damage and then switches its user out (effect 228: U-turn, Volt Switch)."""
    (mv,) = x.args
    m = x.d.move(mv)
    assert m['effect'] == PIVOT_EFFECT and m['class'] != STATUS, '%s does not switch its user out after the hit' % mv


@_op('one_turn')
def one_turn(x):
    """('one_turn', a, mv): a charge move that attacks at once: Solar Beam in sun, or any charge move (Solar Beam, Sky Attack, Fly,
    Dig, Dive, Bounce, Shadow Force) when its user holds a Power Herb, which skips the charge turn once."""
    a, mv = x.args
    m = x.d.move(mv)
    assert m['effect'] == SOLAR_BEAM or m['effect'] in TWO_TURN_EFFECTS and m['effect'] != 170, '%s is not a charge move' % mv
    assert x.item(a) == 'Power Herb' or (m['effect'] == SOLAR_BEAM and x.weather == 'sun'), (
        '%s still needs its charge turn (no sun for Solar Beam, no Power Herb)' % mv)


@_op('has_status')
def has_status(x):
    """('has_status', r, status): the Pokémon has that major status ('par', 'slp', 'psn', 'tox', 'brn', 'frz'), as a readable
    claim next to the key it explains (a sleeping Pokémon with turns left does not act this turn)."""
    r, st = x.args
    assert x.ref(r)['status'] == st, '%s has status %s, not %s' % (x.ref(r)['species'], x.ref(r)['status'], st)


@_op('boosted_race')
def boosted_race(x):
    """('boosted_race', a, setup, mv_a, b, mv_b, n): a, with the boosts `setup` gives (Dragon Dance: +1 Attack, +1 Speed) already in
    force from the first turn, knocks b out within n turns and is still standing: the race rules (a's minimum x 0.9, b's maximum
    x 1.1, both paralysis and both burn rules, the end-of-turn damage, the boosted Speed order). b may be a bench member that
    will come in once the foe in front of it faints. Pair it with `loses` (the same fight without the boosts)."""
    a, setup, mv_a, b, mv_b, n = x.args
    _actives(x, a, b)
    for mb in _race_moves(x, b, mv_b):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                race = Race(x, a, par_div, burn_div)
                boosts = {(a, stat): amt for stat, amt in race.setup_boosts(a, setup)}
                turn = race.play(a, mv_a, b, mb, n, start_boosts=boosts)
                assert turn is not None, '%s\'s %s, boosted by %s, does not surely beat %s\'s %s within %d turns (paralysis /%d, burn /%d)' % (
                    x.ref(a)['species'], mv_a, setup, x.ref(b)['species'], mb, n, par_div, burn_div)


# --- batch 31: doubles hits that add up in one turn, and end-of-turn damage in a double
HEALING_BERRIES = {'Sitrus Berry', 'Oran Berry'}


def _spread_rules(x, fn):
    """fn() under both spread rules: the doubles reduction (0.75 for a move that hits two or more Pokémon, the Gen 5 rule
    Ctx.damage applies) and none, because the reduction was never measured in this ROM. Returns both results."""
    saved = x.double
    out = []
    try:
        for spread in (True, False):
            x.double = saved and spread
            out.append(fn())
    finally:
        x.double = saved
    return out


def _hits_total(x, df, hits, sure):
    """The hits [(attacker, move), ...] on df added up: each at its minimum (minimum hit count) for a sure claim, else at its
    maximum (maximum hit count)."""
    return sum(x.total(a, mv, df, sure) for a, mv in hits)


@_op('sum_ko')
def sum_ko(x):
    """('sum_ko', df, ((a, mv), ...)): those hits in one turn surely knock df out, whatever their order: the sum of each hit's
    minimum (minimum hit count) x 0.9 >= df's current HP, under both spread rules (the lower sum counts). A single hit is a
    sure KO under both rules. Refused when the claim could fail by an effect the sum skips: df at full HP with a Focus Sash or
    Sturdy (one of the hits could leave it at 1 HP), or a Sitrus / Oran Berry (it heals between hits). Multiscale and resist
    berries are applied to every hit, which only lowers the sum."""
    df, hits = x.args
    dv = x.ref(df)
    assert x.item(df) not in HEALING_BERRIES, '%s holds %s: it heals between the hits' % (dv['species'], x.item(df))
    if dv['cur_hp'] == dv['stats']['hp']:
        assert x.item(df) != 'Focus Sash' and x.ability(df) != 'Sturdy', '%s can hang on at 1 HP (Focus Sash / Sturdy)' % dv['species']
    lo = min(_spread_rules(x, lambda: _hits_total(x, df, hits, True)))
    assert lo * 0.9 >= dv['cur_hp'], '%s: at least %d to %s at %d HP, not a sure KO' % (
        ' + '.join(mv for _, mv in hits), lo, dv['species'], dv['cur_hp'])


@_op('sum_noko')
def sum_noko(x):
    """('sum_noko', df, ((a, mv), ...)): those hits in one turn cannot knock df out: the sum of each hit's maximum (maximum hit
    count) x 1.1 < df's current HP, under both spread rules (the higher sum counts). With one hit: that move alone cannot KO."""
    df, hits = x.args
    dv = x.ref(df)
    hi = max(_spread_rules(x, lambda: _hits_total(x, df, hits, False)))
    assert hi * 1.1 < dv['cur_hp'], '%s: up to %d to %s at %d HP, can KO' % (
        ' + '.join(mv for _, mv in hits), hi, dv['species'], dv['cur_hp'])


class _Chip(Race):
    """Race.chip without the race: the end-of-turn model holds in a double too (weather from any active's ability)."""

    def __init__(self, x, burn_div):
        self.x, self.burn_div = x, burn_div


@_op('dbl_chip_kos')
def dbl_chip_kos(x):
    """('dbl_chip_kos', r): in a double, the end-of-turn damage alone knocks r out this turn, whatever it does: the chip_kos
    model (sandstorm or hail from an active's ability, then Leftovers / Black Sludge, then poison, bad poison at its first tick,
    burn) at its least, with burn a sixteenth (Gen 7+) rather than an eighth (Gen 5)."""
    (r,) = x.args
    assert x.double, 'dbl_chip_kos is a doubles claim (chip_kos covers singles)'
    v = x.ref(r)
    least = v['cur_hp'] - max(_Chip(x, 16).chip(r, v['cur_hp'], 1), _Chip(x, 8).chip(r, v['cur_hp'], 2))
    assert least >= v['cur_hp'], '%s at %d HP loses only %d at the end of the turn' % (v['species'], v['cur_hp'], least)
