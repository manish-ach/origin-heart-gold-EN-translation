"""Batch 07, part a (draft): positions where a strong player knows the right play. Two themes:

1. The foe moves first and knocks the AI's active out in every roll (it is faster, it has priority, or the active is asleep).
   The right play is priority damage that matters, or a switch to the Pokemon that takes the hit well. Traps: a strong
   attack, or a status move, that never fires.
2. Choosing a switch-in for the foe's obvious move: the resist that wins, against an immune or resisting teammate that loses
   the next turn (to priority, to coverage, or because its HP is too low), and a statused teammate that a sleep move cannot touch.

Every bench run loads batch_01..06 first, so their ops (b05_*, b06_*) are registered when these checks run. The op below
(prefix b07a_) builds on ai_checks.Ctx and ai_checks.Race and is registered in ai_checks.CHECKS on import:
  An Intimidate switch-in (b07a_intim_entry). Gen 5 rule: a Pokemon switched in as the turn's action enters before any move,
      and its Intimidate lowers each opposing active's Attack one stage at once (not through Clear Body, White Smoke or Hyper
      Cutter), so the foe's attack that turn already hits it at -1, and the drop stays while the foe stays in (seen in this
      hack: qa/aivsai/runs/20261003_101454/s004_g0.log turn 4, Masquerain's entry, then Garchomp's Earthquake did 84, which
      fits -1 at 78-92 and not 0 at 116-137). The op plays that
      entry hit (the favored side's margins: its own damage minimum x 0.9, the other's maximum x 1.1; Focus Sash and Sturdy at
      full HP keep 1 HP), the hit's guaranteed stat changes, one end of turn, and then ai_checks.Race from those HPs with the
      foe's stages kept, under both paralysis and both burn rules. 'lose_without' plays the same switch with no Intimidate, the
      foe favored, to show that the drop is what wins. Refused: an Intimidate or Download holder among the actives (the race
      would keep counting it after the switch), and a foe whose ability makes Intimidate depend on the generation.
"""
import ai_checks
from ai_checks import CHECKS, INTIMIDATE_AMBIGUOUS, INTIMIDATE_BLOCKERS, STATUS, Ctx, Race, with_items
from ai_helpers import PLAIN, S, mon  # noqa: F401


def _op7(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(Ctx(d, views, c, ref))
        return fn
    return reg


def _guaranteed_stat_changes(x, src, mv, tgt):
    """The move's stat changes with chance 100 (Close Combat's own drops...), into x.boosts, as ai_checks.Race applies them."""
    raw = x.d.moves[x.d.move(mv)['id']]
    if raw[1] not in (ai_checks.Q_USER_STAT, ai_checks.Q_TARGET_DROP):
        return
    who = src if raw[1] == ai_checks.Q_USER_STAT else tgt
    for k in range(3):
        stat = ai_checks.STAT_IDS.get(raw[21 + k])
        amt, chance = int.from_bytes(raw[24 + k:25 + k], 'little', signed=True), raw[27 + k]
        if stat and amt and chance == 100:
            if who == tgt and amt < 0 and x.ability(tgt) in ai_checks.DROP_BLOCKERS[stat] and x.ability(src) not in ai_checks.MOLD_BREAKER:
                continue
            x.boosts[(who, stat)] = max(-6, min(6, x.boosts.get((who, stat), 0) + amt))


def _entry_race(x, e, p, entry_mv, mv_e, mv_p, n, favored, drop, par_div, burn_div):
    """e switches in and takes p's entry_mv (at -1 Attack when drop), one end of turn passes, then e (mv_e) and p (mv_p) race.
    Returns the winner, or None."""
    other = p if favored == e else e
    ve, vp = x.ref(e), x.ref(p)
    saved = (ve['cur_hp'], vp['cur_hp'])
    x.boosts.clear()
    x.consumed.clear()
    try:
        if drop and x.ability(p) not in INTIMIDATE_BLOCKERS:
            x.boosts[(p, 'atk')] = -1
        sure = favored == p
        dmg = int(x.total(p, entry_mv, e, sure) * (0.9 if sure else 1.1))
        if dmg >= ve['cur_hp'] and x.endures(p, entry_mv, e):
            dmg = ve['cur_hp'] - 1
            if x.item(e) == 'Focus Sash':
                x.consumed.add(e)
        ve['cur_hp'] -= dmg
        if ve['cur_hp'] <= 0:
            return p
        if dmg:
            _guaranteed_stat_changes(x, p, entry_mv, e)
        race = Race(x, favored, par_div, burn_div)
        for r in (e, p):
            assert x.ref(r)['status'] != 'tox', 'bad poison is not modeled across the entry turn'
            x.ref(r)['cur_hp'] = race.chip(r, x.ref(r)['cur_hp'], 2 if r == favored else 1)
            if x.ref(r)['cur_hp'] <= 0:
                return other if r == favored else favored
        boosts = dict(x.boosts)
        mv_f, mv_o = (mv_e, mv_p) if favored == e else (mv_p, mv_e)
        return favored if race.play(favored, mv_f, other, mv_o, n, start_boosts=boosts) is not None else None
    finally:
        ve['cur_hp'], vp['cur_hp'] = saved
        x.boosts.clear()
        x.consumed.clear()


@_op7('b07a_intim_entry')
def intim_entry(x):
    """('b07a_intim_entry', e, mv_e, p, entry_mv, mv_p, n, want): e, an Intimidate holder on the AI's bench, switches in and takes
    p's entry_mv (the move p aims at the AI's active) at -1 Attack, one end of turn passes, then e (mv_e every turn) and p (mv_p
    every turn) race from those HPs with p's stages kept (module docstring). want 'win': e is favored and knocks p out within n
    turns while still standing; mv_p '*' tries each attack of p. want 'lose_without': the same switch with no Attack drop and p
    favored: p knocks e out within n turns, before e knocks p out; mv_e '*' tries each attack of e."""
    e, mv_e, p, entry_mv, mv_p, n, want = x.args
    assert want in ('win', 'lose_without'), 'want is win or lose_without'
    assert e[0] == 'e' and e not in x.actives['enemy'] and p in x.actives['player'], 'e is an AI bench member, p a player active'
    assert x.ability(e) == 'Intimidate', '%s has no Intimidate' % x.ref(e)['species']
    for r in x.actives['enemy'] + x.actives['player']:
        assert x.ability(r) not in ('Intimidate', 'Download'), '%s has %s, which the race would keep counting' % (
            x.ref(r)['species'], x.ability(r))
    assert x.ability(p) not in INTIMIDATE_AMBIGUOUS, '%s vs Intimidate depends on the engine' % x.ref(p)['species']
    assert x.d.move(entry_mv)['class'] != STATUS, '%s is a status move' % entry_mv
    favored, other = (e, p) if want == 'win' else (p, e)
    mv_fav, mv_other = (mv_e, mv_p) if favored == e else (mv_p, mv_e)
    assert mv_fav != '*', "'*' belongs to the side whose every option is tried"
    options = [m for m in x.ref(other)['moves'] if x.d.move(m)['class'] != STATUS] if mv_other == '*' else [mv_other]
    for opt in options:
        me, mp = (mv_fav, opt) if favored == e else (opt, mv_fav)
        for par_div in (4, 2):
            for burn_div in (8, 16):
                won = _entry_race(x, e, p, entry_mv, me, mp, n, favored, want == 'win', par_div, burn_div)
                assert won == favored, '%s %s vs %s %s after the entry %s (%s): %s within %d turns (par /%d, burn /%d)' % (
                    x.ref(e)['species'], me, x.ref(p)['species'], mp, entry_mv,
                    'with Intimidate' if want == 'win' else 'no Intimidate', 'not a sure %s' % ('win' if want == 'win' else 'loss'),
                    n, par_div, burn_div)


SCENARIOS = with_items([
    # --- 1. the active is knocked out before it moves

    S('b07a_mach_punch_sets_ko', 'priority',
      'Kangaskhan is faster than Conkeldurr at 30% and Earthquake KOs it, so Close Combat (a KO) never fires; Mach Punch goes '
      'first and takes about half of Kangaskhan, after which Toxicroak comes in free, outspeeds it and Brick Break KOs; without '
      'that chip Toxicroak at 55% loses to Earthquake, and switching it in now hands it an Earthquake that KOs it',
      [mon('Kangaskhan', ['Double-Edge', 'Earthquake', 'Crunch', 'Ice Punch'])],
      [mon('Conkeldurr', ['Mach Punch', 'Close Combat', 'Stone Edge', 'Bulk Up'], hp=0.3, evs={'atk': 252}),
       mon('Toxicroak', ['Brick Break', 'Poison Jab', 'Sucker Punch', 'Swords Dance'], hp=0.55, evs={'atk': 100})],
      best=['Mach Punch'], bad=['Close Combat', 'Stone Edge', 'Bulk Up', 'switch:Toxicroak'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Earthquake', 'e0'), ('pri', 'Mach Punch', 1),
              ('b05_first', 'e0', 'Mach Punch', 'p0', 'Earthquake'), ('b05_ko', 'e0', 'Close Combat', 'p0'),
              ('b05_first', 'p0', 'Earthquake', 'e0', 'Close Combat'), ('b05_noko', 'e0', 'Mach Punch', 'p0'),
              ('b05_faster', 'e1', 'p0'),
              ('b05_wins_after', 'e1', 'Brick Break', 'p0', '*', 1, [('e0', 'Mach Punch', 'p0')]),
              ('b05_loses_after', 'e1', '*', 'p0', 'Earthquake', []),
              ('b05_faints', 'e1', [('p0', 'Earthquake', 'e1')])]),
    S('b07a_sleep_talk_never_fires', 'switch',
      'Empoleon is asleep and slower than Infernape, whose Close Combat (2x) KOs it, so Sleep Talk never runs (even when it would '
      'call Scald, nearly a KO); Slowbro resists Close Combat and Flare Blitz, survives the next hits and Psychic (2x) wins; '
      'Mismagius takes nothing from Close Combat but is slower and Flare Blitz beats it; Weavile is KOd on entry',
      [mon('Infernape', ['Close Combat', 'Flare Blitz', 'Stone Edge', 'U-turn'])],
      [mon('Empoleon', ['Sleep Talk', 'Rest', 'Scald', 'Flash Cannon'], status='slp', sleep=3),
       mon('Slowbro', ['Psychic', 'Scald', 'Fire Blast', 'Slack Off']),
       mon('Mismagius', ['Shadow Ball', 'Mystical Fire', 'DazzlngGleam', 'Thunderbolt']),
       mon('Weavile', ['Icicle Crash', 'Knock Off', 'Ice Shard', 'Swords Dance'])],
      best=['switch:Slowbro'], bad=['Sleep Talk', 'Rest', 'Scald', 'Flash Cannon', 'switch:Weavile'],
      checks=[('b05_has_status', 'e0', 'slp'), ('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Close Combat', 'e0'),
              ('b05_frac', 'e0', 'Scald', 'p0', 0.85, 1.1),
              ('b05_eff', 'p0', 'Close Combat', 'e1', 0.5), ('b05_eff', 'p0', 'Flare Blitz', 'e1', 0.5),
              ('b05_wins_after', 'e1', 'Psychic', 'p0', '*', 2, [('p0', 'Close Combat', 'e1'), 'eot']),
              ('b05_eff', 'p0', 'Close Combat', 'e2', 0.0), ('b05_faster', 'p0', 'e2'),
              ('b05_loses_after', 'e2', '*', 'p0', 'Flare Blitz', ['eot']),
              ('b05_faints', 'e3', [('p0', 'Close Combat', 'e3')])]),
    S('b07a_shard_loses_bracket', 'priority',
      'Cloyster at 15% has Ice Shard, which would KO Dragonite at 17% (4x), but ExtremeSpeed has the higher priority and KOs '
      'Cloyster first; Dusknoir is a Ghost, so ExtremeSpeed does nothing to it, and it survives Outrage and KOs with Shadow Punch; '
      'Skarmory at 30% resists ExtremeSpeed but the faster Dragonite then KOs it with Fire Punch',
      [mon('Dragonite', ['ExtremeSpeed', 'Outrage', 'Earthquake', 'Fire Punch'], hp=0.17)],
      [mon('Cloyster', ['Icicle Spear', 'Ice Shard', 'Rock Blast', 'Shell Smash'], ability='Skill Link', hp=0.15),
       mon('Dusknoir', ['Shadow Sneak', 'Shadow Punch', 'Earthquake', 'Will-O-Wisp']),
       mon('Skarmory', ['Brave Bird', 'Iron Head', 'Roost', 'Spikes'], hp=0.3)],
      best=['switch:Dusknoir'], bad=['Icicle Spear', 'Ice Shard', 'Rock Blast', 'Shell Smash', 'switch:Skarmory'],
      checks=[('pri', 'ExtremeSpeed', 2), ('pri', 'Ice Shard', 1), ('b05_ko', 'e0', 'Ice Shard', 'p0'),
              ('b05_first', 'p0', 'ExtremeSpeed', 'e0', 'Ice Shard'), ('b05_ko', 'p0', 'ExtremeSpeed', 'e0'),
              ('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Outrage', 'e0'),
              ('b05_eff', 'p0', 'ExtremeSpeed', 'e1', 0.0),
              ('b05_wins_after', 'e1', 'Shadow Punch', 'p0', '*', 1, [('p0', 'ExtremeSpeed', 'e1'), 'eot']),
              ('b05_faster', 'p0', 'e2'),
              ('b05_loses_after', 'e2', '*', 'p0', 'Fire Punch', [('p0', 'ExtremeSpeed', 'e2'), 'eot'])]),

    S('b07a_jet_plus_poison', 'priority',
      'Poisoned Jolteon is far faster than Crawdaunt and Thunderbolt (2x) KOs it, so Crabhammer (a KO) never fires; Aqua Jet '
      'goes first and does not KO alone, but the poison at the end of the turn finishes Jolteon, a one-for-one trade; both '
      'teammates are low enough that Thunderbolt KOs them on entry, and either one loses to Jolteon if it survives this turn',
      [mon('Jolteon', ['Thunderbolt', 'Shadow Ball', 'Volt Switch', 'Hyper Voice'], status='psn', hp=48)],
      [mon('Crawdaunt', ['Aqua Jet', 'Crabhammer', 'Knock Off', 'Swords Dance']),
       mon('Gyarados', ['Waterfall', 'Earthquake', 'Ice Fang', 'Dragon Dance'], hp=0.35),
       mon('Ludicolo', ['Giga Drain', 'Surf', 'Ice Beam', 'Rain Dance'], hp=0.25)],
      best=['Aqua Jet'], bad=['Crabhammer', 'Knock Off', 'Swords Dance', 'switch:Gyarados', 'switch:Ludicolo'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Thunderbolt', 'e0'), ('pri', 'Aqua Jet', 1),
              ('b05_first', 'e0', 'Aqua Jet', 'p0', 'Thunderbolt'), ('b05_has_status', 'p0', 'psn'),
              ('b05_noko', 'e0', 'Aqua Jet', 'p0'), ('b05_faints', 'p0', [('e0', 'Aqua Jet', 'p0')]),
              ('b05_ko', 'e0', 'Crabhammer', 'p0'), ('b05_first', 'p0', 'Thunderbolt', 'e0', 'Crabhammer'),
              ('b05_faints', 'e1', [('p0', 'Thunderbolt', 'e1')]), ('b05_faints', 'e2', [('p0', 'Thunderbolt', 'e2')]),
              ('b05_loses_after', 'e1', '*', 'p0', 'Thunderbolt', ['eot']),
              ('b05_loses_after', 'e2', '*', 'p0', 'Thunderbolt', ['eot'])]),

    S('b07a_immune_dies_to_priority', 'switch',
      'Lucario is faster than Bisharp and Close Combat (4x) KOs it; Mismagius is immune to Close Combat and faster than Lucario, '
      'but at 40% the priority Bullet Punch (2x on a Fairy) KOs it before it moves; Crobat resists Close Combat (a quarter), '
      'outspeeds Lucario and wins with two Acrobatics (110 power with no held item); Tyranitar is KOd on entry',
      [mon('Lucario', ['Close Combat', 'Bullet Punch', 'ExtremeSpeed', 'Crunch'])],
      [mon('Bisharp', ['Iron Head', 'Sucker Punch', 'Knock Off', 'Swords Dance']),
       mon('Mismagius', ['Shadow Ball', 'Mystical Fire', 'DazzlngGleam', 'Thunderbolt'], hp=0.4),
       mon('Crobat', ['Acrobatics', 'Cross Poison', 'U-turn', 'Roost'], evs={'atk': 252}),
       mon('Tyranitar', ['Stone Edge', 'Crunch', 'Earthquake', 'Ice Punch'])],
      best=['switch:Crobat'], bad=['Iron Head', 'Knock Off', 'Swords Dance', 'switch:Mismagius', 'switch:Tyranitar'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Close Combat', 'e0'), ('b05_noko', 'e0', 'Sucker Punch', 'p0'),
              ('b05_eff', 'p0', 'Close Combat', 'e1', 0.0), ('b05_faster', 'e1', 'p0'), ('pri', 'Bullet Punch', 1),
              ('b05_ko', 'p0', 'Bullet Punch', 'e1'),
              ('b05_eff', 'p0', 'Close Combat', 'e2', 0.25), ('b05_faster', 'e2', 'p0'),
              ('b05_has_item', 'e2', None),
              ('b05_wins_after', 'e2', 'Acrobatics', 'p0', '*', 2, [('p0', 'Close Combat', 'e2'), 'eot']),
              ('b05_faints', 'e3', [('p0', 'Close Combat', 'e3')])]),
    S('b07a_low_resist_into_sand', 'switch',
      "The player's Tyranitar set a sandstorm and its Rock Slide (4x) KOs Charizard, whose attacks do under a sixth; Machamp resists "
      'Rock Slide and its Close Combat would KO Tyranitar, but at 15% even the resisted hit KOs it on entry; Swampert resists '
      'it too at full HP, is immune to the sand, outspeeds Tyranitar and wins with two Earthquakes; Moltres is KOd on entry',
      [mon('Tyranitar', ['Rock Slide', 'Crunch', 'Earthquake', 'Ice Punch'], ability='Sand Stream')],
      [mon('Charizard', ['Flamethrower', 'Air Slash', 'Dragon Pulse', 'Roost']),
       mon('Machamp', ['Close Combat', 'Knock Off', 'Stone Edge', 'Bullet Punch'], hp=0.15),
       mon('Swampert', ['Earthquake', 'Waterfall', 'Ice Punch', 'Stealth Rock']),
       mon('Moltres', ['Flamethrower', 'Air Slash', 'Roost', 'Will-O-Wisp'])],
      best=['switch:Swampert'], bad=['Flamethrower', 'Air Slash', 'Roost', 'switch:Machamp', 'switch:Moltres'],
      checks=[('b05_weather', 'sand'), ('b05_faster', 'e0', 'p0'), ('b05_ko', 'p0', 'Rock Slide', 'e0'),
              ('b05_frac', 'e0', 'Dragon Pulse', 'p0', 0.0, 0.16), ('b05_frac', 'e0', 'Flamethrower', 'p0', 0.0, 0.16),
              ('b05_eff', 'p0', 'Rock Slide', 'e1', 0.5), ('b05_ko', 'e1', 'Close Combat', 'p0'),
              ('b05_faints', 'e1', [('p0', 'Rock Slide', 'e1')]),
              ('b05_eff', 'p0', 'Rock Slide', 'e2', 0.5), ('b05_faster', 'e2', 'p0'),
              ('b05_wins_after', 'e2', 'Earthquake', 'p0', '*', 2, [('p0', 'Rock Slide', 'e2'), 'eot']),
              ('b05_faints', 'e3', [('p0', 'Rock Slide', 'e3')])]),
    S('b07a_burned_special_takes_spore', 'status',
      'Breloom is faster than Donphan and Spore never misses; Togekiss and Weavile are both burned, so Spore cannot touch '
      'either; Weavile still loses, since the priority Mach Punch (4x) KOs it before it moves, while Togekiss is faster, its '
      'Air Slash is special (the burn does not halve it) and KOs Breloom (4x) after Mach Punch barely scratches it; Gyarados '
      'would be put to sleep on the way in',
      [mon('Breloom', ['Spore', 'Mach Punch', 'Seed Bomb', 'Stone Edge'])],
      [mon('Donphan', ['Earthquake', 'Ice Shard', 'Gunk Shot', 'Knock Off']),
       mon('Togekiss', ['Air Slash', 'DazzlngGleam', 'Flamethrower', 'Roost'], status='brn'),
       mon('Weavile', ['Icicle Crash', 'Knock Off', 'Ice Shard', 'Swords Dance'], status='brn'),
       mon('Gyarados', ['Waterfall', 'Ice Fang', 'Earthquake', 'Dragon Dance'])],
      best=['switch:Togekiss'], bad=['switch:Weavile'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_macc', 'p0', 'Spore', 'e0', 100), ('b05_sleep_lands', 'p0', 'Spore', 'e0'),
              ('b05_has_status', 'e1', 'brn'), ('b05_sleep_fails', 'p0', 'Spore', 'e1'), ('cls', 'Air Slash', 'special'),
              ('b05_faster', 'e1', 'p0'), ('b05_wins_after', 'e1', 'Air Slash', 'p0', '*', 1, ['eot']),
              ('b05_has_status', 'e2', 'brn'), ('b05_sleep_fails', 'p0', 'Spore', 'e2'), ('pri', 'Mach Punch', 1),
              ('b05_loses_after', 'e2', '*', 'p0', 'Mach Punch', ['eot']),
              ('b05_sleep_lands', 'p0', 'Spore', 'e3')]),
    S('b07a_intimidate_switch_in', 'switch',
      'Gyarados is faster than Coalossal at 70% and Waterfall (4x) KOs it; Luxray switched in drops its Attack at once with '
      'Intimidate, so it takes the Waterfall and then Earthquake (2x) at -1, survives both and KOs with Thunder Fang (4x); '
      'without the drop the same two hits would KO it first; Golem is KOd on entry; if the player reads the switch with '
      'Earthquake, Luxray survives only on low rolls, and every other option loses too',
      [mon('Gyarados', ['Waterfall', 'Earthquake', 'Ice Fang', 'Dragon Dance'])],
      [mon('Coalossal', ['Stone Edge', 'Flamethrower', 'Stealth Rock', 'Will-O-Wisp'], hp=0.7),
       mon('Luxray', ['Thunder Fang', 'Crunch', 'Ice Fang', 'Volt Switch'], ability='Intimidate', hp=0.97),
       mon('Golem', ['Earthquake', 'Stone Edge', 'Explosion', 'Stealth Rock'])],
      best=['switch:Luxray'], bad=['Stone Edge', 'Flamethrower', 'Stealth Rock', 'Will-O-Wisp', 'switch:Golem'],
      checks=[('b05_faster', 'p0', 'e0'), ('b05_ko', 'p0', 'Waterfall', 'e0'), ('b05_faster', 'p0', 'e1'),
              ('b07a_intim_entry', 'e1', 'Thunder Fang', 'p0', 'Waterfall', '*', 1, 'win'),
              ('b07a_intim_entry', 'e1', '*', 'p0', 'Waterfall', 'Earthquake', 2, 'lose_without'),
              ('b05_faints', 'e2', [('p0', 'Waterfall', 'e2')])]),
])
