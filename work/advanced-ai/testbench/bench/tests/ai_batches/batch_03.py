"""Batch 03: lessons from full AI-vs-AI battles turned into turn-1 positions (about 30), plus free hard positions.

The battle ideas: switch-ins that look safe on the type chart but are knocked out by an ability that turns a Normal move into
another type, an item, the weather or a move that doubles against a switch-in; attacking (and fainting) before a free switch
beats feeding a healthy teammate to the hit, and the reverse when the active is the only answer to a later foe; Counter and
Mirror Coat; Weakness Policy; Shedinja against a super effective move; status and screens for their lasting value; the field
set by an ability on entry (Desolate Land, Psychic, Misty and Electric Surge); and single-battle rules (Healing Wish and Lunar
Dance, Endeavor with a Focus Sash, Swords Dance into Foul Play, Follow Me, a Choice lock).

The ops below extend tests/ai_checks.py without editing it. `Ctx3` is ai_checks.Ctx plus the mechanics these positions need,
and every op here builds a Ctx3, so a key never rests on an effect that was silently ignored. Each op is registered in
ai_checks.CHECKS on import (prefix b03_), before `with_items` runs. The Gen 5 formula of ai_checks is kept; what Ctx3 adds:
  -ate abilities (Refrigerate Ice, Pixilate Fairy, Aerilate Flying, Galvanize Electric): a damaging Normal move takes the
      ability's type (not Weather Ball). Its power boost is 1.3 in Gen 6 and 1.2 from Gen 7, and this ROM has not been
      measured: a sure claim (minimum) uses 1.2, a cannot claim (maximum) 1.3.
  Primal weather from an active's entry ability: Desolate Land (harsh sun: Fire x1.5, Water attacks fail) and Primordial Sea
      (heavy rain: Water x1.5, Fire attacks fail). Mixed with another weather ability, Cloud Nine or Air Lock: refused.
  Terrain from an active's entry ability (Misty, Psychic, Electric, Grassy Surge; two setters refused). Grounded = not a
      Flying type and no Levitate (an Iron Ball grounds). Psychic / Electric / Grassy Terrain boost the matching type from a
      grounded user by 1.3 (Gen 8) or 1.5 (Gen 7): minimum with 1.3, maximum with 1.5. Misty Terrain halves Dragon moves
      against a grounded target; Grassy Terrain halves Earthquake and Bulldoze against one. The blocks (`b03_fails`): Psychic
      Terrain stops priority moves aimed at a grounded foe, Misty Terrain stops major status on a grounded target, Electric
      Terrain stops sleep on a grounded target.
  Weather Ball: 100 power and the weather's type (Fire in sun, Water in rain, Rock in sand, Ice in hail), else Normal 50.
  Fishious Rend / Bolt Beak (effect 430): 170 power when the target has not moved yet this turn, which a Pokemon switching
      in never has. Against an active, the minimum doubles only if the user surely moves first (priority, then Speed under
      both paralysis rules, against every move of the target), the maximum unless it surely moves second.
  Foul Play (effect 297): the target's Attack and Attack stages instead of the user's. Refused when either side has an
      Attack-changing ability or item, or a burn, whose handling differs between generations.
  Weakness Policy ('Weak. Policy', id 600): a super effective hit that does not knock its holder out raises its Attack and
      Sp. Atk by two stages. It changes nothing about the hit itself. Not measured in this ROM; AI-vs-AI battle logs show the
      boost (b03_wp only states the trigger; b03_boosted_ko the boosted hit).
"""
import ai_checks
from ai_checks import (CHECKS, INERT_ITEMS, MODELED_ABILITIES, MODELED_ITEMS, PHYSICAL, RANDOM_ITEMS, SPECIAL, STATUS, T,
                       TYPES, WEATHER_ABILITIES, Ctx, Race, _actives, _race_moves, with_items)
from aidata import norm
from ai_helpers import PLAIN, S, mon  # noqa: F401

NORMAL, FLYING, WATER, FIRE, DRAGON = T['Normal'], T['Flying'], T['Water'], T['Fire'], T['Dragon']
ATE = {'refrigerate': 'Ice', 'pixilate': 'Fairy', 'aerilate': 'Flying', 'galvanize': 'Electric'}
PRIMAL = {'desolateland': 'harsh', 'primrdialsea': 'heavy'}
TERRAIN = {'mistysurge': 'misty', 'psychicsurge': 'psychic', 'elecsurge': 'electric', 'grassysurge': 'grassy'}
TERRAIN_TYPE = {'psychic': 'Psychic', 'electric': 'Electric', 'grassy': 'Grass'}
EXTRA_ABILITIES = set(ATE) | set(PRIMAL) | set(TERRAIN)
EXTRA_ITEMS = {'Weak. Policy'}
WEATHER_BALL, RIVAL_DOUBLE, FOUL_PLAY = 203, 430, 297
GROUND_HALVED = {'earthquake', 'bulldoze', 'magnitude'}
# Attack changes whose interplay with Foul Play differs between generations: refused next to it.
FOUL_REFUSED_ABILITIES = {'Huge Power', 'Pure Power', 'Guts', 'Hustle', 'Toxic Boost', 'Slow Start', 'Defeatist'}
FOUL_REFUSED_ITEMS = {'Choice Band', 'Muscle Band', 'Life Orb', 'Black Glasses', 'Expert Belt'}
# Move data status byte: 1 paralysis, 2 sleep, 3 freeze, 4 burn, 5 poison; 6 confusion, 14 Yawn.
MAJOR_STATUS = {1: 'par', 2: 'slp', 3: 'frz', 4: 'brn', 5: 'psn'}
# Abilities that stop, reflect, cure or profit from a burn or a paralysis: refused on the target of b03_status_race.
STATUS_RACE_REFUSED = {'Limber', 'Water Veil', 'Magic Bounce', 'Synchronize', 'Guts', 'Quick Feet', 'Marvel Scale', 'Flare Boost',
                       'Toxic Boost', 'Shed Skin', 'Hydration', 'Leaf Guard', 'Natural Cure', 'Heatproof'}
STATUS_BERRY_FOR = {'brn': {'Rawst Berry', 'Lum Berry'}, 'par': {'Cheri Berry', 'Lum Berry'}}


class _Moves:
    """The data module as the move in hand is used: Ctx3.move_as_used replaces move(); everything else is the ROM's data."""

    def __init__(self, ctx):
        self._ctx = ctx

    def __getattr__(self, k):
        return getattr(self._ctx.raw, k)

    def move(self, mv):
        return self._ctx.move_as_used(mv)


class Ctx3(Ctx):
    """ai_checks.Ctx with -ate abilities, primal weather, terrains, Weather Ball, Fishious Rend / Bolt Beak, Foul Play and
    Weakness Policy (module docstring)."""

    def __init__(self, d, views, c, ref):
        self._cur, self._hi, self.entering = None, False, None
        super().__init__(d, views, c, ref)
        self.raw = self.d
        self.d = _Moves(self)

    def vet(self, r, v):
        ab = v['ability']
        assert ab in MODELED_ABILITIES or norm(ab) in EXTRA_ABILITIES, (
            '%s: %s has %s, which these checks do not model; use another ability' % (r, v['species'], ab))
        it = self.items.get(r)
        if it is None or it in EXTRA_ITEMS:
            return
        assert it not in RANDOM_ITEMS, '%s: %s is random; the key cannot rest on it' % (r, it)
        assert it not in INERT_ITEMS, '%s: %s was measured to have no effect in this ROM' % (r, it)
        assert it in MODELED_ITEMS, '%s: %s has %s, which these checks do not model' % (r, v['species'], it)
        if ab != 'Klutz':
            assert self.d.id('item', it) and self.hold_effect(it), '%s: %s has no hold effect in this ROM' % (r, it)

    def find_weather(self):
        actives = self.actives['enemy'] + self.actives['player']
        abil = [norm(self.ability(r)) for r in actives]
        ters = [TERRAIN[a] for a in abil if a in TERRAIN]
        assert len(ters) <= 1, 'two terrain abilities on the field: the order would decide the terrain'
        self.terrain = ters[0] if ters else None
        prim = [PRIMAL[a] for a in abil if a in PRIMAL]
        self.primal = None
        if not prim:
            return super().find_weather()
        assert len(prim) == 1, 'two primal weathers on the field'
        assert not any(self.ability(r) in WEATHER_ABILITIES or self.ability(r) in ('Cloud Nine', 'Air Lock') for r in actives), (
            'a primal weather next to another weather ability, Cloud Nine or Air Lock is not modeled')
        self.primal = prim[0]
        return 'sun' if self.primal == 'harsh' else 'rain'

    def grounded(self, r):
        v = self.ref(r)
        return self.item(r) == 'Iron Ball' or (FLYING not in v['types'] and self.ability(r) != 'Levitate')

    def ate(self, a):
        return ATE.get(norm(self.ability(a)))

    def first_kind(self, a, pri, df):
        """True if a, using a move of that priority, surely moves before df whatever df picks; False if surely after; else None."""
        out = set()
        for mv in self.ref(df)['moves']:
            m = self.raw.move(mv)
            p2 = m['priority'] + (1 if self.ability(df) == 'Prankster' and m['class'] == STATUS else 0)
            if p2 != pri:
                out.add(pri > p2)
            elif self.moves_last(a) != self.moves_last(df):
                out.add(self.moves_last(df))
            else:
                for div in (4, 2):
                    sa, sd = self.speed(a, div), self.speed(df, div)
                    out.add(None if sa == sd else sa > sd)
        return True if out == {True} else False if out == {False} else None

    def move_as_used(self, mv):
        m = dict(self.raw.move(mv))
        if self._cur is None:
            return m
        a, df = self._cur
        if m['effect'] == WEATHER_BALL:
            t = {'sun': 'Fire', 'rain': 'Water', 'sand': 'Rock', 'hail': 'Ice'}.get(self.weather)
            if t:
                m['type'], m['power'] = T[t], m['power'] * 2
            m['effect'] = 0
        elif m['class'] != STATUS and m['type'] == NORMAL and self.ate(a):
            m['type'], m['ate'] = T[self.ate(a)], True
        if m['effect'] == RIVAL_DOUBLE:
            if self.entering == df:
                doubled = True
            else:
                kind = self.first_kind(a, m['priority'], df)
                doubled = kind is True if not self._hi else kind is not False
            m['power'] *= 2 if doubled else 1
            m['effect'] = 0
        if m['effect'] == FOUL_PLAY:
            m['effect'], m['foul'] = 0, True
        return m

    def effectiveness(self, a, mv, df):
        self._cur = (a, df)
        m = self.d.move(mv)
        if m['class'] != STATUS and ((self.primal == 'harsh' and m['type'] == WATER) or (self.primal == 'heavy' and m['type'] == FIRE)):
            return 0.0
        return super().effectiveness(a, mv, df)

    def power(self, a, mv, df):
        self._cur = (a, df)
        bp = super().power(a, mv, df)
        m = self.d.move(mv)
        if m.get('ate'):
            bp = int(bp * (1.3 if self._hi else 1.2))
        if self.terrain in TERRAIN_TYPE and TYPES[m['type']] == TERRAIN_TYPE[self.terrain] and self.grounded(a):
            bp = int(bp * (1.5 if self._hi else 1.3))
        if self.terrain == 'misty' and m['type'] == DRAGON and self.grounded(df):
            bp = int(bp * 0.5)
        if self.terrain == 'grassy' and norm(self.raw.move_name[m['id']]) in GROUND_HALVED and self.grounded(df):
            bp = int(bp * 0.5)
        return bp

    def attack(self, a, mv, df):
        self._cur = (a, df)
        m = self.d.move(mv)
        if not m.get('foul'):
            return super().attack(a, mv, df)
        for q in (a, df):
            assert self.ability(q) not in FOUL_REFUSED_ABILITIES and self.item(q) not in FOUL_REFUSED_ITEMS, (
                'Foul Play next to %s / %s: not modeled' % (self.ability(q), self.item(q)))
            assert self.ref(q)['status'] != 'brn', 'Foul Play with a burn: not modeled'
        self._cur = (a, df)
        return int(self.ref(df)['stats']['atk'] * self.stage_mult(self.stages(df, 'atk')))

    def defense(self, a, mv, df):
        self._cur = (a, df)
        return super().defense(a, mv, df)

    def damage(self, a, mv, df):
        """(min, max): the minimum from the low reading of every unmeasured boost, the maximum from the high one."""
        saved = self._hi
        try:
            self._cur, self._hi = (a, df), False
            lo = super().damage(a, mv, df)[0]
            self._cur, self._hi = (a, df), True
            hi = super().damage(a, mv, df)[1]
        finally:
            self._hi = saved
        return (lo, hi)

    def fails(self, a, mv, df):
        """Why the move does nothing here because of the field, or None."""
        self._cur = (a, df)
        m = self.d.move(mv)
        if m['class'] != STATUS and self.primal == 'harsh' and m['type'] == WATER:
            return 'Water attacks fail in Desolate Land\'s harsh sun'
        if m['class'] != STATUS and self.primal == 'heavy' and m['type'] == FIRE:
            return 'Fire attacks fail in Primordial Sea\'s heavy rain'
        if self.side(a) == self.side(df) or not self.grounded(df):
            return None
        pri = m['priority'] + (1 if self.ability(a) == 'Prankster' and m['class'] == STATUS else 0)
        if self.terrain == 'psychic' and pri > 0:
            return 'Psychic Terrain stops priority moves aimed at a grounded foe'
        if self.terrain == 'misty' and m['class'] == STATUS and m['status'] in MAJOR_STATUS:
            return 'Misty Terrain stops major status on a grounded target'
        if self.terrain == 'electric' and m['class'] == STATUS and MAJOR_STATUS.get(m['status']) == 'slp':
            return 'Electric Terrain stops sleep on a grounded target'
        return None


def _op3(name):
    def reg(fn):
        CHECKS[name] = lambda d, views, c, ref: fn(Ctx3(d, views, c, ref))
        return fn
    return reg


# --- the ops of tests/ai_checks.py, run on Ctx3 (same rules, plus the mechanics above)
for _name, _fn in (('b03_ko', ai_checks.mko), ('b03_noko', ai_checks.mnoko), ('b03_noko_at', ai_checks.mnoko_at),
                   ('b03_ko_at', ai_checks.mko_at), ('b03_beats', ai_checks.mbeats), ('b03_frac', ai_checks.mfrac),
                   ('b03_eff', ai_checks.meff), ('b03_faster', ai_checks.mfaster), ('b03_first', ai_checks.first),
                   ('b03_race', ai_checks.race), ('b03_loses', ai_checks.loses), ('b03_endures', ai_checks.endures),
                   ('b03_survives_recoil', ai_checks.survives_recoil)):
    _op3(_name)(_fn)


@_op3('b03_terrain')
def terrain(x):
    """('b03_terrain', kind): the terrain at turn 1 from the actives' entry abilities ('misty', 'psychic', 'electric', 'grassy', None)."""
    (kind,) = x.args
    assert x.terrain == kind, 'terrain is %s, claimed %s' % (x.terrain, kind)


@_op3('b03_primal')
def primal(x):
    """('b03_primal', kind): the primal weather at turn 1 ('harsh' from Desolate Land, 'heavy' from Primordial Sea, None)."""
    (kind,) = x.args
    assert x.primal == kind, 'primal weather is %s, claimed %s' % (x.primal, kind)


@_op3('b03_grounded')
def grounded(x):
    """('b03_grounded', r, want): r touches the ground (no Flying type, no Levitate, or an Iron Ball), so terrain acts on it."""
    r, want = x.args
    assert x.grounded(r) == want, '%s grounded is %s, claimed %s' % (x.ref(r)['species'], x.grounded(r), want)


@_op3('b03_fails')
def fails(x):
    """('b03_fails', a, mv, df): the field makes the move do nothing: a Water attack in harsh sun, a Fire attack in heavy rain,
    a priority move (Prankster counted) aimed at a grounded foe in Psychic Terrain, a major status move on a grounded target
    in Misty Terrain, a sleep move on a grounded target in Electric Terrain (Gen 7 rules)."""
    a, mv, df = x.args
    assert x.fails(a, mv, df), '%s from %s works on %s here' % (mv, x.ref(a)['species'], x.ref(df)['species'])


@_op3('b03_type_as_used')
def type_as_used(x):
    """('b03_type_as_used', a, mv, type): the type the move has when a uses it here (an -ate ability, Weather Ball)."""
    a, mv, want = x.args
    x._cur = (a, a)
    got = TYPES[x.d.move(mv)['type']]
    assert got == want, '%s from %s is %s, claimed %s' % (mv, x.ref(a)['species'], got, want)


@_op3('b03_wp')
def wp(x):
    """('b03_wp', a, mv, df): df holds Weakness Policy and a's move is super effective on it without knocking it out
    (maximum x 1.1 < HP), so the item fires: df's Attack and Sp. Atk rise by two stages."""
    a, mv, df = x.args
    assert x.items.get(df) == 'Weak. Policy' and x.item(df), '%s does not hold a working Weakness Policy' % x.ref(df)['species']
    eff = x.effectiveness(a, mv, df)
    assert eff and eff > 1, '%s is not super effective on %s (%s)' % (mv, x.ref(df)['species'], eff)
    hi = x.total(a, mv, df, False)
    assert hi * 1.1 < x.ref(df)['cur_hp'], '%s can KO %s (up to %d of %d): the policy might not fire' % (
        mv, x.ref(df)['species'], hi, x.ref(df)['cur_hp'])


@_op3('b03_boosted_ko')
def boosted_ko(x):
    """('b03_boosted_ko', a, mv, df, atk, spa): with a's Attack and Sp. Atk at those stages, its move is a sure KO on df
    (minimum x 0.9 >= HP, no Focus Sash or Sturdy hold)."""
    a, mv, df, atk, spa = x.args
    x.boosts[(a, 'atk')], x.boosts[(a, 'spa')] = atk, spa
    lo = x.total(a, mv, df, True)
    assert not x.endures(a, mv, df), '%s hangs on at 1 HP' % x.ref(df)['species']
    assert lo * 0.9 >= x.ref(df)['cur_hp'], 'boosted %s does %d at least: not a sure KO on %s at %d HP' % (
        mv, lo, x.ref(df)['species'], x.ref(df)['cur_hp'])


def _entering_ok(x, a, df):
    """df is a bench member of a's foe that switches in now: it has no entry ability that would change the field, and the
    active it replaces does not hold a primal weather, which ends when its holder leaves."""
    assert x.side(a) != x.side(df) and df not in x.actives[x.side(df)], '%s is not a bench member of the other side' % df
    assert x.ability(df) not in ai_checks.ENTRY_ABILITIES and norm(x.ability(df)) not in EXTRA_ABILITIES - set(ATE), (
        '%s has an entry ability that would change the field' % x.ref(df)['species'])
    for r in x.actives[x.side(df)]:
        assert norm(x.ability(r)) not in PRIMAL, 'the primal weather of %s ends when it leaves' % x.ref(r)['species']


@_op3('b03_entry_ko')
def entry_ko(x):
    """('b03_entry_ko', a, mv, df): df switches in this turn and takes a's move: a sure KO (minimum x 0.9 >= HP; Fishious Rend
    and Bolt Beak doubled, since the newcomer has not moved; no Sash or Sturdy hold). The field is as it is now."""
    a, mv, df = x.args
    _entering_ok(x, a, df)
    x.entering = df
    lo = x.total(a, mv, df, True)
    assert not x.endures(a, mv, df), '%s hangs on at 1 HP' % x.ref(df)['species']
    assert lo * 0.9 >= x.ref(df)['cur_hp'], '%s does %d at least to %s entering at %d HP: not a sure KO' % (
        mv, lo, x.ref(df)['species'], x.ref(df)['cur_hp'])


@_op3('b03_entry_noko')
def entry_noko(x):
    """('b03_entry_noko', a, mv, df): df switches in this turn and survives a's move (maximum x 1.1 < HP; Fishious Rend and Bolt
    Beak doubled)."""
    a, mv, df = x.args
    _entering_ok(x, a, df)
    x.entering = df
    hi = x.total(a, mv, df, False)
    assert hi * 1.1 < x.ref(df)['cur_hp'], '%s does up to %d to %s entering at %d HP: can KO' % (
        mv, hi, x.ref(df)['species'], x.ref(df)['cur_hp'])


def _with_hp(x, changes, fn):
    """Run fn with some views' HP (and status) changed for the duration."""
    saved = {r: (x.ref(r)['cur_hp'], x.ref(r)['status']) for r in changes}
    try:
        for r, (hp, st) in changes.items():
            x.ref(r)['cur_hp'] = hp
            if st != '-':
                x.ref(r)['status'] = st
        return fn()
    finally:
        for r, (hp, st) in saved.items():
            x.ref(r)['cur_hp'], x.ref(r)['status'] = hp, st


@_op3('b03_entry_loses')
def entry_loses(x):
    """('b03_entry_loses', df, a, mv_entry, mv_df, mv_a): df switches in and takes a's mv_entry (a's minimum x 0.9, Fishious Rend
    and Bolt Beak doubled), then loses the fight from there: a, using mv_a every turn, knocks df out before df ('*' = each of
    its attacks) knocks a out, under the race rules of tests/ai_checks.py with a favored (a's minimum x 0.9, df's maximum x 1.1,
    both paralysis and both burn rules)."""
    df, a, mv_entry, mv_df, mv_a = x.args
    _actives(x, a, df)
    _entering_ok(x, a, df)
    x.entering = df
    hit = int(x.total(a, mv_entry, df, True) * 0.9)
    x.entering = None
    left = x.ref(df)['cur_hp'] - hit
    if left <= 0:
        return
    for mb in _race_moves(x, df, mv_df):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                turn = _with_hp(x, {df: (left, '-')}, lambda: Race(x, a, par_div, burn_div).play(a, mv_a, df, mb, 12))
                assert turn is not None, '%s entering at %d HP (after %d from %s) is not surely beaten by %s\'s %s (its %s; par /%d, burn /%d)' % (
                    x.ref(df)['species'], left, hit, mv_entry, x.ref(a)['species'], mv_a, mb, par_div, burn_div)


@_op3('b03_entry_wins')
def entry_wins(x):
    """('b03_entry_wins', df, a, mv_entry, mv_df, n): df switches in and takes a's mv_entry ('*' = the strongest of a's attacks;
    a's maximum x 1.1, Fishious Rend and Bolt Beak doubled), then wins the fight from there: df, using mv_df every turn, knocks a
    out within n turns and is still standing, whatever a uses ('*': each of its attacks), under the race rules with df favored."""
    df, a, mv_entry, mv_df, n = x.args
    _actives(x, df, a)
    _entering_ok(x, a, df)
    x.entering = df
    hit = max(int(x.total(a, m, df, False) * 1.1) for m in _race_moves(x, a, mv_entry))
    x.entering = None
    left = x.ref(df)['cur_hp'] - hit
    assert left > 0, '%s can KO %s as it switches in (up to %d)' % (mv_entry, x.ref(df)['species'], hit)
    for mb in _race_moves(x, a, '*'):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                turn = _with_hp(x, {df: (left, '-')}, lambda: Race(x, df, par_div, burn_div).play(df, mv_df, a, mb, n))
                assert turn is not None, '%s entering at %d HP does not surely beat %s (its %s) within %d turns (par /%d, burn /%d)' % (
                    x.ref(df)['species'], left, x.ref(a)['species'], mb, n, par_div, burn_div)


@_op3('b03_chip_then_race')
def chip_then_race(x):
    """('b03_chip_then_race', e, mv_e, p, b, mv_b, n): e hits p once with mv_e (e's minimum x 0.9: claim it with b03_first) and is
    then knocked out; b comes in free at its current HP and, using mv_b every turn, knocks p ('*' = each of its attacks) out
    within n turns and is still standing (race rules, b favored)."""
    e, mv_e, p, b, mv_b, n = x.args
    _actives(x, b, p)
    chip = int(x.total(e, mv_e, p, True) * 0.9)
    left = x.ref(p)['cur_hp'] - chip
    if left <= 0:
        return
    for mb in _race_moves(x, p, '*'):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                turn = _with_hp(x, {p: (left, '-')}, lambda: Race(x, b, par_div, burn_div).play(b, mv_b, p, mb, n))
                assert turn is not None, '%s at %d HP (after %d from %s) is not surely beaten by %s\'s %s within %d turns (its %s; par /%d, burn /%d)' % (
                    x.ref(p)['species'], left, chip, mv_e, x.ref(b)['species'], mv_b, n, mb, par_div, burn_div)


@_op3('b03_status_race')
def status_race(x):
    """('b03_status_race', e, smove, mv_e, p, mv_p, n): e spends turn 1 on a burn or paralysis move (Will-O-Wisp, Thunder Wave)
    while p hits it with mv_p ('*' = each of p's attacks; maximum x 1.1, already halved by the burn only when e's move surely
    comes first: higher priority with Prankster, or faster under both paralysis rules), then attacks with
    mv_e every turn: e survives and knocks p out by the end of turn n. From the end of turn 1 p is burned (physical damage
    halved, an eighth or a sixteenth a turn) or paralyzed (Speed a quarter or a half; the chance to lose a turn is not counted).
    The move must be able to land: p has no status, is not Fire (burn) or Electric (paralysis), is not immune to the move's type
    (Thunder Wave on Ground), holds no curing berry, has no ability that blocks, reflects, cures or profits from it, and is
    not on Misty Terrain. Its accuracy (Will-O-Wisp 85, Thunder Wave 90) is not counted: state it in the description."""
    e, smove, mv_e, p, mv_p, n = x.args
    _actives(x, e, p)
    m = x.raw.move(smove)
    st = MAJOR_STATUS.get(m['status'])
    assert m['class'] == STATUS and st in ('brn', 'par'), '%s is not a burn or paralysis move' % smove
    pv = x.ref(p)
    assert not pv['status'], '%s already has a status' % pv['species']
    assert {'brn': FIRE, 'par': T['Electric']}[st] not in pv['types'], '%s cannot get %s' % (pv['species'], st)
    assert x.raw.type_mult(m['type'], pv['types']) != 0, '%s cannot touch %s' % (smove, pv['species'])
    assert x.ability(p) not in STATUS_RACE_REFUSED, '%s has %s' % (pv['species'], x.ability(p))
    assert x.item(p) not in STATUS_BERRY_FOR[st], '%s holds %s' % (pv['species'], x.item(p))
    assert not (x.terrain == 'misty' and x.grounded(p)), 'Misty Terrain blocks the status'
    for mb in _race_moves(x, p, mv_p):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                race = Race(x, e, par_div, burn_div)
                # p's turn-1 hit already carries the status when e's move surely comes first (Speed or Prankster)
                first = race.order({e: smove, p: mb})[0] == e
                hit = int(_with_hp(x, {p: (pv['cur_hp'], st if first else pv['status'])}, lambda: x.total(p, mb, e, False)) * 1.1)
                e_hp = x.ref(e)['cur_hp'] - hit
                assert e_hp > 0, '%s\'s %s can KO %s on turn 1 (up to %d)' % (pv['species'], mb, x.ref(e)['species'], hit)
                p_hp = _with_hp(x, {p: (pv['cur_hp'], st)}, lambda: race.chip(p, pv['cur_hp'], 1))
                e_hp = race.chip(e, e_hp, 2) if e_hp > 0 else e_hp
                assert e_hp > 0 and p_hp > 0 or p_hp <= 0 < e_hp, 'the end of turn 1 decides it the wrong way'
                if p_hp <= 0:
                    continue
                turn = _with_hp(x, {e: (e_hp, '-'), p: (p_hp, st)}, lambda: race.play(e, mv_e, p, mb, n - 1))
                assert turn is not None, '%s\'s %s then %s does not surely beat %s (%s) within %d turns (par /%d, burn /%d)' % (
                    x.ref(e)['species'], smove, mv_e, pv['species'], mb, n, par_div, burn_div)


@_op3('b03_countered')
def countered(x):
    """('b03_countered', a, mv, df): df has Counter (for a physical mv) or Mirror Coat (special) and survives mv, either because
    the hit cannot KO it (maximum x 1.1 < HP) or because a Focus Sash or Sturdy at full HP keeps it at 1 HP against a single
    hit; it then returns twice the HP it lost, which surely knocks a out (2 x min(minimum x 0.9, what it can lose) >= a's HP):
    attacking with mv loses a. Counter and Mirror Coat have -5 priority, so they always come after. Refused: a Ghost attacker
    into Counter and a Dark attacker into Mirror Coat (type immunities whose handling differs between generations)."""
    a, mv, df = x.args
    m = x.d.move(mv)
    dv = x.ref(df)
    have = {norm(n) for n in dv['moves']}
    need = {PHYSICAL: 'counter', SPECIAL: 'mirrorcoat'}.get(m['class'])
    assert need in have, '%s has no %s for %s' % (dv['species'], need, mv)
    assert not (need == 'counter' and T['Ghost'] in x.ref(a)['types']), 'Counter against a Ghost: refused'
    assert not (need == 'mirrorcoat' and T['Dark'] in x.ref(a)['types']), 'Mirror Coat against a Dark type: refused'
    lo, hi = x.total(a, mv, df, True), x.total(a, mv, df, False)
    assert lo > 0, '%s does nothing to %s' % (mv, dv['species'])
    if x.endures(a, mv, df):
        lost = min(int(lo * 0.9), dv['cur_hp'] - 1)
    else:
        assert hi * 1.1 < dv['cur_hp'], '%s can KO %s before it strikes back' % (mv, dv['species'])
        lost = int(lo * 0.9)
    assert 2 * lost >= x.ref(a)['cur_hp'], 'twice what %s surely loses (%d) does not surely KO %s at %d HP' % (
        dv['species'], 2 * lost, x.ref(a)['species'], x.ref(a)['cur_hp'])


@_op3('b03_reflect_only')
def reflect_only(x):
    """('b03_reflect_only', r): r's only damaging moves are Counter and Mirror Coat, which fail unless r was hit by an attack of
    their class this turn: r does nothing to a foe that uses a status move."""
    (r,) = x.args
    for mv in x.ref(r)['moves']:
        m = x.raw.move(mv)
        assert m['class'] == STATUS or norm(mv) in ('counter', 'mirrorcoat'), '%s can attack with %s' % (x.ref(r)['species'], mv)


@_op3('b03_hits_ally')
def hits_ally(x):
    """('b03_hits_ally', a, mv, want): in a double, whether the move also hits a's partner: target class 4 (every other Pokemon,
    as Earthquake, Surf, Lava Plume, Explosion) does, class 5 (both foes only, as Heat Wave, Rock Slide) and single-target moves
    do not."""
    a, mv, want = x.args
    assert x.double, 'b03_hits_ally is a doubles claim'
    got = x.raw.move(mv)['target'] == 4
    assert got == want, '%s hits the partner: %s, claimed %s' % (mv, got, want)


@_op3('b03_seed_beats')
def seed_beats(x):
    """('b03_seed_beats', e, p, mv): Leech Seed on p drains an eighth of its max HP every turn (Gen 5), at least as much as e's
    mv can do at most, and heals e by the same amount; p is not a Grass type, has no Magic Guard or Liquid Ooze and is not
    already seeded (turn 1)."""
    e, p, mv = x.args
    pv = x.ref(p)
    assert T['Grass'] not in pv['types'], '%s is a Grass type: Leech Seed fails' % pv['species']
    assert x.ability(p) not in ('Magic Guard', 'Liquid Ooze'), '%s has %s' % (pv['species'], x.ability(p))
    drain = max(1, pv['stats']['hp'] // 8)
    hi = x.total(e, mv, p, False)
    assert drain >= hi, 'the seed drains %d a turn, %s does up to %d' % (drain, mv, hi)


@_op3('b03_attacks_only')
def attacks_only(x):
    """('b03_attacks_only', r): every move r has is an attack: it has no setup, status or healing move to use while its foe
    protects itself or sets up."""
    (r,) = x.args
    bad = [mv for mv in x.ref(r)['moves'] if x.raw.move(mv)['class'] == STATUS]
    assert not bad, '%s has %s' % (x.ref(r)['species'], ', '.join(bad))


@_op3('b03_protect_race')
def protect_race(x):
    """('b03_protect_race', a, mv_a, b, mv_b, n): a has Speed Boost and uses Protect on turn 1, which blocks b's attack (b must
    have only attacks: claim b03_attacks_only); at the end of the turn Speed Boost raises a's Speed by one stage. From turn 2
    a uses mv_a every turn and knocks b ('*' = each of its attacks) out by the end of turn n, under the race rules with a
    favored and the +1 Speed in force (later Speed Boosts are not counted). Pair it with `loses` for attacking at once."""
    a, mv_a, b, mv_b, n = x.args
    _actives(x, a, b)
    assert x.ability(a) == 'Speed Boost', '%s has no Speed Boost' % x.ref(a)['species']
    assert any(norm(m) == 'protect' for m in x.ref(a)['moves']), '%s has no Protect' % x.ref(a)['species']
    for mb in _race_moves(x, b, mv_b):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                race = Race(x, a, par_div, burn_div)
                a_hp = race.chip(a, x.ref(a)['cur_hp'], 2)
                b_hp = race.chip(b, x.ref(b)['cur_hp'], 1)
                assert a_hp > 0, '%s falls to the end of turn 1' % x.ref(a)['species']
                if b_hp <= 0:
                    continue
                turn = _with_hp(x, {a: (a_hp, '-'), b: (b_hp, '-')},
                                lambda: race.play(a, mv_a, b, mb, n - 1, start_boosts={(a, 'spe'): 1}))
                assert turn is not None, '%s, Protect then +1 Speed, does not surely beat %s (%s) within %d turns (par /%d, burn /%d)' % (
                    x.ref(a)['species'], x.ref(b)['species'], mb, n, par_div, burn_div)


@_op3('b03_foul_ko')
def foul_ko(x):
    """('b03_foul_ko', a, df, stage): a's Foul Play (95 power, Dark) computed with df's own Attack at that stage (df's Swords Dance:
    +2) is a sure KO on df (minimum x 0.9 >= HP)."""
    a, df, stage = x.args
    x.boosts[(df, 'atk')] = stage
    lo = x.total(a, 'Foul Play', df, True)
    assert lo * 0.9 >= x.ref(df)['cur_hp'], 'Foul Play against +%d Attack does %d at least: not a sure KO on %s at %d HP' % (
        stage, lo, x.ref(df)['species'], x.ref(df)['cur_hp'])


@_op3('b03_foul_noko')
def foul_noko(x):
    """('b03_foul_noko', a, df, stage): a's Foul Play with df's Attack at that stage cannot KO df (maximum x 1.1 < HP)."""
    a, df, stage = x.args
    x.boosts[(df, 'atk')] = stage
    hi = x.total(a, 'Foul Play', df, False)
    assert hi * 1.1 < x.ref(df)['cur_hp'], 'Foul Play against +%d Attack does up to %d: can KO %s at %d HP' % (
        stage, hi, x.ref(df)['species'], x.ref(df)['cur_hp'])


@_op3('b03_all_class')
def all_class(x):
    """('b03_all_class', side, cls): every damaging move of that side's whole team ('enemy' or 'player') is physical (or special),
    so a screen of the matching kind halves all of it."""
    side, cls = x.args
    want = {'physical': PHYSICAL, 'special': SPECIAL}[cls]
    for v in x.views[side]:
        for mv in v['moves']:
            m = x.raw.move(mv)
            assert m['class'] in (STATUS, want), '%s has %s, which is not %s' % (v['species'], mv, cls)


@_op3('b03_no_priority')
def no_priority(x):
    """('b03_no_priority', r): none of r's moves has priority above 0 (Prankster counted on status moves)."""
    (r,) = x.args
    for mv in x.ref(r)['moves']:
        m = x.raw.move(mv)
        pri = m['priority'] + (1 if x.ability(r) == 'Prankster' and m['class'] == STATUS else 0)
        assert pri <= 0, '%s has %s at priority %d' % (x.ref(r)['species'], mv, pri)


@_op3('b03_single_hits')
def single_hits(x):
    """('b03_single_hits', r): every attack r has hits once, so a Focus Sash or Sturdy at full HP holds against each."""
    (r,) = x.args
    for mv in x.ref(r)['moves']:
        if x.raw.move(mv)['class'] != STATUS:
            assert x.hits(mv)[1] == 1, '%s hits more than once' % mv


@_op3('b03_half_beats')
def half_beats(x):
    """('b03_half_beats', a, df, mv): Super Fang (effect 40) takes half of df's current HP (rounded down, at least 1) whatever the
    stats, STAB or type multiplier, only a type immunity stops it (it is Normal: Ghosts are immune); that is more than a's
    mv can do to df at most."""
    a, df, mv = x.args
    sf = x.raw.move('Super Fang')
    assert sf['effect'] == 40, 'Super Fang has effect %d here' % sf['effect']
    dv = x.ref(df)
    assert x.raw.type_mult(sf['type'], dv['types']) != 0, '%s is immune to Super Fang' % dv['species']
    half = max(1, dv['cur_hp'] // 2)
    hi = x.total(a, mv, df, False)
    assert half > hi, 'Super Fang takes %d from %s, %s can do up to %d' % (half, dv['species'], mv, hi)


@_op3('b03_split_beats')
def split_beats(x):
    """('b03_split_beats', a, df, mv): Pain Split sets both Pokemon to the average of their current HP (Gen 5: floor((a + df) / 2),
    capped at each one's max HP): df loses more than a's mv can do to it at most, and a gains HP. df must not be immune to it
    (it is a typeless status move; Substitute and Wonder Guard do not apply on turn 1)."""
    a, df, mv = x.args
    av, dv = x.ref(a), x.ref(df)
    avg = (av['cur_hp'] + dv['cur_hp']) // 2
    loss = dv['cur_hp'] - min(avg, dv['stats']['hp'])
    gain = min(avg, av['stats']['hp']) - av['cur_hp']
    hi = x.total(a, mv, df, False)
    assert gain > 0, 'Pain Split does not heal %s' % av['species']
    assert loss > hi, 'Pain Split takes %d from %s, %s can do up to %d' % (loss, dv['species'], mv, hi)


@_op3('b03_charges')
def charges(x):
    """('b03_charges', a, mv): the move spends this turn charging and hits only next turn: a two-turn move (Solar Beam outside
    sun, Sky Attack, Fly, Dig, Dive, Bounce, Shadow Force) without a Power Herb."""
    a, mv = x.args
    m = x.raw.move(mv)
    assert m['effect'] == ai_checks.SOLAR_BEAM or (m['effect'] in ai_checks.TWO_TURN_EFFECTS and m['effect'] != 170), '%s is not a charge move' % mv
    assert x.item(a) != 'Power Herb', '%s holds a Power Herb' % x.ref(a)['species']
    assert not (m['effect'] == ai_checks.SOLAR_BEAM and x.weather == 'sun'), 'Solar Beam fires at once in sun'


@_op3('b03_race_healed')
def race_healed(x):
    """('b03_race_healed', b, mv_b, p, mv_p, n): b, restored to full HP with its status cured (Healing Wish or Lunar Dance on the
    Pokemon that comes in), beats p from a free entry: using mv_b every turn it knocks p ('*' = each attack of p) out within n
    turns and is still standing (race rules, b favored; the field as it is now)."""
    b, mv_b, p, mv_p, n = x.args
    _actives(x, b, p)
    bv = x.ref(b)
    for mb in _race_moves(x, p, mv_p):
        for par_div in (4, 2):
            for burn_div in (8, 16):
                turn = _with_hp(x, {b: (bv['stats']['hp'], None)}, lambda: Race(x, b, par_div, burn_div).play(b, mv_b, p, mb, n))
                assert turn is not None, 'healed %s does not surely beat %s (%s) within %d turns (par /%d, burn /%d)' % (
                    bv['species'], x.ref(p)['species'], mb, n, par_div, burn_div)


SCENARIOS = with_items([
    # --- switch-ins that look safe on the type chart: -ate abilities, Weather Ball, a doubled Fishious Rend, the sun and a Choice item

    S('b03_pixilate_ghost_trap', 'switch',
      "The player's Pixilate Sylveon turns Hyper Voice into a Fairy move with STAB: it KOs Haxorus (4x), and Sableye, which the type chart calls immune to a Normal move, takes 99-126% (Fairy is 2x on Dark); Metagross resists it (21-27%), is faster and KOs Sylveon with Meteor Mash (2x) next turn; Haxorus's Dragon Claw cannot touch a Fairy, and staying in only gets an Earthquake (41-49%) off before Hyper Voice KOs it",
      [mon('Sylveon', ['Hyper Voice', 'Psyshock', 'Calm Mind', 'Wish'], ability='Pixilate')],
      [mon('Haxorus', ['Dragon Claw', 'Close Combat', 'Earthquake', 'Dragon Dance']), mon('Sableye', ['Foul Play', 'Will-O-Wisp', 'Recover']), mon('Metagross', ['Meteor Mash', 'Zen Headbutt', 'Earthquake', 'Bullet Punch'])],
      best=['switch:Metagross'], bad=['switch:Sableye', 'Dragon Claw', 'Dragon Dance'],
      checks=[('b03_type_as_used', 'p0', 'Hyper Voice', 'Fairy'), ('eff', 'p0', 'Hyper Voice', 'e1', 0.0),
              ('b03_eff', 'p0', 'Hyper Voice', 'e1', 2.0), ('b03_frac', 'p0', 'Hyper Voice', 'e1', 0.95, 1.4), ('b03_ko', 'p0', 'Hyper Voice', 'e0'),
              ('b03_faster', 'e0', 'p0'), ('b03_noko', 'e0', 'Earthquake', 'p0'), ('b03_eff', 'e0', 'Dragon Claw', 'p0', 0.0),
              ('b03_eff', 'p0', 'Hyper Voice', 'e2', 0.5), ('b03_entry_wins', 'e2', 'p0', 'Hyper Voice', 'Meteor Mash', 1)]),
    S('b03_refrigerate_rock_trap', 'switch',
      "Refrigerate makes the player's Glalie's Body Slam an Ice move with STAB: Golem, which resists a Normal move on paper, takes 66-83% (2x) on the way in and falls to the next one before it can move (Glalie is faster); Empoleon resists Ice twice over (11-14%) and wins with Flash Cannon (2x); Garchomp at 45% is KO'd first by Ice Shard (4x, priority) whatever it picks",
      [mon('Glalie', ['Body Slam', 'Ice Shard', 'Crunch', 'Spikes'], ability='Refrigerate')],
      [mon('Garchomp', ['Earthquake', 'Dragon Claw', 'Stone Edge', 'Swords Dance'], hp=0.45), mon('Golem', ['Stone Edge', 'Earthquake', 'Explosion']), mon('Empoleon', ['Flash Cannon', 'Hydro Pump', 'Ice Beam'])],
      best=['switch:Empoleon'], bad=['switch:Golem', 'Earthquake', 'Dragon Claw', 'Stone Edge', 'Swords Dance'],
      checks=[('b03_type_as_used', 'p0', 'Body Slam', 'Ice'), ('eff', 'p0', 'Body Slam', 'e1', 0.5), ('b03_eff', 'p0', 'Body Slam', 'e1', 2.0),
              ('b03_entry_loses', 'e1', 'p0', 'Body Slam', '*', 'Body Slam'), ('b03_ko', 'p0', 'Ice Shard', 'e0'), ('pri', 'Ice Shard', 1),
              ('b03_eff', 'p0', 'Body Slam', 'e2', 0.25), ('b03_entry_wins', 'e2', 'p0', '*', 'Flash Cannon', 3)]),
    S('b03_aerilate_shedinja', 'switch',
      "Aerilate makes the player's Salamence's Double-Edge a Flying move with STAB: Shedinja, which Wonder Guard shields from Normal, Dragon and Ground moves alike, is hit super effectively and dies on entry; Levitate Bronzong resists Flying and Dragon and ignores Earthquake; Breloom is slower and the Flying Double-Edge (4x) KOs it whatever it does",
      [mon('Salamence', ['Double-Edge', 'Dragon Claw', 'Earthquake', 'Dragon Dance'], ability='Aerilate')],
      [mon('Breloom', ['Mach Punch', 'Seed Bomb', 'Bullet Seed', 'Swords Dance']), mon('Shedinja', ['X-Scissor', 'Shadow Sneak', 'Shadow Claw'], ability='Wonder Guard'), mon('Bronzong', ['Gyro Ball', 'Psychic', 'Earthquake'], ability='Levitate')],
      best=['switch:Bronzong'], bad=['switch:Shedinja', 'Mach Punch', 'Seed Bomb', 'Bullet Seed', 'Swords Dance'],
      checks=[('b03_type_as_used', 'p0', 'Double-Edge', 'Flying'), ('eff', 'p0', 'Double-Edge', 'e1', 0.0),
              ('b03_eff', 'p0', 'Double-Edge', 'e1', 2.0), ('b03_eff', 'p0', 'Dragon Claw', 'e1', 0.0), ('b03_eff', 'p0', 'Earthquake', 'e1', 0.0),
              ('b03_entry_ko', 'p0', 'Double-Edge', 'e1'), ('b03_ko', 'p0', 'Double-Edge', 'e0'), ('b03_faster', 'p0', 'e0'),
              ('b03_eff', 'p0', 'Earthquake', 'e2', 0.0), ('b03_eff', 'p0', 'Double-Edge', 'e2', 0.5), ('b03_eff', 'p0', 'Dragon Claw', 'e2', 0.5),
              ('b03_entry_noko', 'p0', 'Double-Edge', 'e2'), ('b03_noko_at', 'p0', 'Double-Edge', 'e2', 0.5)]),
    S('b03_sun_weather_ball_trap', 'switch',
      "Under the player's Drought sun Ninetales's Weather Ball is a 100-power Fire move with STAB and the sun boost: Forretress, which resists Normal and Fairy on paper, takes it 4x and dies on entry, and Ferrothorn (far slower) dies to it before acting; Swampert resists it (22-27%), survives Moonblast and KOs Ninetales with Earthquake (2x) next turn; only Protect delays the KO",
      [mon('Ninetales', ['Weather Ball', 'Moonblast', 'Nasty Plot', 'Will-O-Wisp'], ability='Drought')],
      [mon('Ferrothorn', ['Gyro Ball', 'Power Whip', 'Leech Seed', 'Protect']), mon('Forretress', ['Gyro Ball', 'Volt Switch', 'Rapid Spin']), mon('Swampert', ['Earthquake', 'Waterfall', 'Ice Beam'], evs={'atk': 252})],
      best=['switch:Swampert'], bad=['switch:Forretress', 'Gyro Ball', 'Power Whip', 'Leech Seed'],
      checks=[('weather', 'sun'), ('b03_type_as_used', 'p0', 'Weather Ball', 'Fire'), ('eff', 'p0', 'Weather Ball', 'e1', 0.5),
              ('b03_eff', 'p0', 'Weather Ball', 'e1', 4.0), ('b03_entry_ko', 'p0', 'Weather Ball', 'e1'), ('b03_eff', 'p0', 'Moonblast', 'e1', 0.5),
              ('b03_ko', 'p0', 'Weather Ball', 'e0'), ('b03_faster', 'p0', 'e0'), ('b03_eff', 'p0', 'Weather Ball', 'e2', 0.5),
              ('b03_entry_wins', 'e2', 'p0', 'Weather Ball', 'Earthquake', 2)]),
    S('b03_rend_doubles_switch', 'switch',
      'Choice Band Dracovish is faster than Rhyperior at 45%, and Fishious Rend, doubled against a target that has not moved yet, KOs it whatever it picks; Garchomp (90%) switching in has not moved either, takes the doubled hit (127-150) and then loses to the locked Fishious Rend, while coming in free after Rhyperior falls it is the faster one, takes the undoubled move (64-76) and wins with two Dragon Claws: let Rhyperior fall',
      [mon('Dracovish', ['Fishious Rend', 'Dragon Claw', 'Crunch'], item='Choice Band')],
      [mon('Rhyperior', ['Stone Edge', 'Earthquake', 'Megahorn', 'Rock Polish'], hp=0.45), mon('Garchomp', ['Dragon Claw', 'Earthquake', 'Stone Edge', 'Fire Fang'], hp=0.9)],
      best=['Stone Edge', 'Earthquake', 'Megahorn', 'Rock Polish'], bad=['switch:Garchomp'],
      checks=[('has_item', 'p0', 'Choice Band'), ('b03_faster', 'p0', 'e0'), ('b03_ko', 'p0', 'Fishious Rend', 'e0'), ('b03_faster', 'e1', 'p0'),
              ('b03_entry_loses', 'e1', 'p0', 'Fishious Rend', '*', 'Fishious Rend'), ('b03_race', 'e1', 'Dragon Claw', 'p0', 'Fishious Rend', 2),
              ('noko_at', 'p0', 'Fishious Rend', 'e1', 0.5)]),
    S('b03_own_sun_specs_trap', 'switch',
      "The AI's own Drought sun boosts the player's Choice Specs Solar Power Charizard: Fire Blast does 58-68% to Vaporeon and 61-72% to Tyranitar, which both resist Fire on paper, and the faster Charizard finishes either before it acts (the sun also halves Vaporeon's Scald); Flash Fire Heatran is immune to Fire, resists Air Slash and Dragon Pulse, and Stone Edge (4x) KOs Charizard; Ninetales moves first but does under 30% and falls next, and Will-O-Wisp cannot burn a Fire type",
      [mon('Charizard', ['Fire Blast', 'Air Slash', 'Dragon Pulse', 'Roost'], ability='Solar Power', item='Choice Specs')],
      [mon('Ninetales', ['Flamethrower', 'Moonblast', 'Nasty Plot', 'Will-O-Wisp'], ability='Drought', hp=0.4), mon('Vaporeon', ['Scald', 'Ice Beam', 'Wish', 'Protect']), mon('Heatran', ['Stone Edge', 'Flash Cannon', 'Earth Power'], ability='Flash Fire'), mon('Tyranitar', ['Stone Edge', 'Crunch', 'Earthquake'])],
      best=['switch:Heatran'], bad=['switch:Vaporeon', 'switch:Tyranitar', 'Will-O-Wisp', 'Nasty Plot'],
      checks=[('weather', 'sun'), ('has_item', 'p0', 'Choice Specs'), ('eff', 'p0', 'Fire Blast', 'e1', 0.5), ('eff', 'p0', 'Fire Blast', 'e3', 0.5),
              ('b03_entry_loses', 'e1', 'p0', 'Fire Blast', '*', 'Fire Blast'), ('b03_entry_loses', 'e3', 'p0', 'Fire Blast', '*', 'Fire Blast'),
              ('b03_eff', 'p0', 'Fire Blast', 'e2', 0.0), ('b03_entry_noko', 'p0', 'Air Slash', 'e2'),
              ('b03_entry_noko', 'p0', 'Dragon Pulse', 'e2'), ('b03_ko', 'e2', 'Stone Edge', 'p0'), ('b03_faster', 'e0', 'p0'),
              ('b03_noko', 'e0', 'Flamethrower', 'p0'), ('b03_ko', 'p0', 'Air Slash', 'e0'), ('type', 'p0', 'Fire')]),

    # --- -ate abilities on the AI's side

    S('b03_galvanize_vs_ghost', 'ability',
      "Galvanize makes Electivire's Double-Edge an Electric move with STAB: it hits Ghost/Water Jellicent 2x and KOs (on paper a Normal move cannot touch a Ghost), while ThunderPunch, also 2x, leaves it at 13-27%; Close Combat cannot touch a Ghost, and Double-Edge's recoil cannot faint Electivire from full HP",
      [mon('Jellicent', ['Scald', 'Shadow Ball', 'Will-O-Wisp', 'Recover'])],
      [mon('Electivire', ['Double-Edge', 'Close Combat', 'ThunderPunch', 'Ice Punch'], ability='Galvanize')],
      best=['Double-Edge'], ok=['ThunderPunch'], bad=['Close Combat'],
      checks=[('eff', 'e0', 'Double-Edge', 'p0', 0.0), ('b03_type_as_used', 'e0', 'Double-Edge', 'Electric'), ('b03_ko', 'e0', 'Double-Edge', 'p0'),
              ('b03_noko', 'e0', 'ThunderPunch', 'p0'), ('b03_eff', 'e0', 'Close Combat', 'p0', 0.0), ('b03_faster', 'e0', 'p0'),
              ('b03_survives_recoil', 'e0', 'Double-Edge', 'p0')]),
    S('b03_pixilate_quick_attack', 'priority',
      'Weavile at 20% is faster than Sylveon at 25% and Poison Jab (2x) or Icicle Crash KOs it; Pixilate makes Quick Attack a priority Fairy move with STAB, 2x on Weavile, and it KOs first, where a plain Normal Quick Attack would not; Hyper Voice also KOs but comes second',
      [mon('Weavile', ['Poison Jab', 'Night Slash', 'Icicle Crash', 'Swords Dance'], hp=0.2)],
      [mon('Sylveon', ['Quick Attack', 'Hyper Voice', 'Calm Mind', 'Wish'], ability='Pixilate', hp=0.25)],
      best=['Quick Attack'], bad=['Hyper Voice', 'Calm Mind', 'Wish'],
      checks=[('b03_type_as_used', 'e0', 'Quick Attack', 'Fairy'), ('b03_ko', 'e0', 'Quick Attack', 'p0'), ('noko', 'e0', 'Quick Attack', 'p0'),
              ('pri', 'Quick Attack', 1), ('b03_faster', 'p0', 'e0'), ('b03_ko', 'p0', 'Poison Jab', 'e0'), ('b03_ko', 'p0', 'Icicle Crash', 'e0'),
              ('b03_no_priority', 'p0')]),
    S('b03_pixilate_vs_soundproof', 'ability',
      "Pixilate would make Gardevoir's Hyper Voice a 4x Fairy hit on Hydreigon, but it is a sound move and Soundproof blocks it; Moonblast (4x) KOs, Psychic cannot touch a Dark type, and Hydreigon's faster Flash Cannon (45-55%) cannot KO first",
      [mon('Hydreigon', ['Dark Pulse', 'Draco Meteor', 'Flash Cannon', 'Roost'], ability='Soundproof')],
      [mon('Gardevoir', ['Hyper Voice', 'Moonblast', 'Psychic', 'Calm Mind'], ability='Pixilate')],
      best=['Moonblast'], bad=['Hyper Voice', 'Psychic'],
      checks=[('b03_type_as_used', 'e0', 'Hyper Voice', 'Fairy'), ('b03_eff', 'e0', 'Hyper Voice', 'p0', 0.0), ('b03_ko', 'e0', 'Moonblast', 'p0'),
              ('b03_eff', 'e0', 'Psychic', 'p0', 0.0), ('b03_faster', 'p0', 'e0'), ('b03_noko', 'p0', 'Flash Cannon', 'e0')]),

    # --- a doomed active: chip and a free switch, and the reverse

    S('b03_doomed_chip_free_entry', 'switch',
      'Starmie at 25% is faster than Mamoswine and dies to its next hit: Surf (2x) takes 63-76% first, then Infernape comes in free, moves first and KOs with Close Combat; switching Infernape in now hands it an Earthquake (2x) that KOs it on entry; Thunderbolt cannot touch a Ground type',
      [mon('Mamoswine', ['Earthquake', 'Icicle Crash', 'Stone Edge', 'Knock Off'])],
      [mon('Starmie', ['Surf', 'Psychic', 'Thunderbolt', 'Rapid Spin'], hp=0.25), mon('Infernape', ['Close Combat', 'Flare Blitz', 'Mach Punch', 'Stone Edge'])],
      best=['Surf'], ok=['Psychic'], bad=['switch:Infernape', 'Thunderbolt'],
      checks=[('b03_faster', 'e0', 'p0'), ('b03_noko', 'e0', 'Surf', 'p0'), ('b03_ko', 'p0', 'Earthquake', 'e0'),
              ('b03_ko', 'p0', 'Knock Off', 'e0'), ('b03_entry_ko', 'p0', 'Earthquake', 'e1'),
              ('b03_chip_then_race', 'e0', 'Surf', 'p0', 'e1', 'Close Combat', 1), ('b03_eff', 'e0', 'Thunderbolt', 'p0', 0.0),
              ('b03_faster', 'e1', 'p0')]),
    S('b03_save_the_only_answer', 'switch',
      "Golem at 30% is slower than Venusaur and dies to Energy Ball (4x), but it is the AI's only answer to the player's Jolteon: no Electric move touches it and Earthquake KOs Jolteon, which in turn beats Skarmory; Skarmory takes Energy Ball for 10-13% (Sludge Bomb cannot touch it) and beats Venusaur with Brave Bird, so switching keeps Golem for Jolteon, and staying loses Golem for nothing",
      [mon('Venusaur', ['Energy Ball', 'Sludge Bomb', 'Synthesis']), mon('Jolteon', ['Thunderbolt', 'Volt Switch', 'Thunder Wave', 'Charge Beam'])],
      [mon('Golem', ['Earthquake', 'Stone Edge', 'Explosion'], hp=0.3), mon('Skarmory', ['Brave Bird', 'Iron Head', 'Roost'])],
      best=['switch:Skarmory'], bad=['Earthquake', 'Stone Edge', 'Explosion'],
      checks=[('b03_faster', 'p0', 'e0'), ('b03_ko', 'p0', 'Energy Ball', 'e0'), ('b03_eff', 'p0', 'Sludge Bomb', 'e1', 0.0),
              ('b03_entry_noko', 'p0', 'Energy Ball', 'e1'), ('b03_entry_wins', 'e1', 'p0', '*', 'Brave Bird', 2),
              ('b03_race', 'e0', 'Earthquake', 'p1', '*', 1), ('b03_eff', 'p1', 'Thunderbolt', 'e0', 0.0),
              ('b03_loses', 'e1', '*', 'p1', 'Thunderbolt')]),

    # --- Counter, Mirror Coat and Weakness Policy

    S('b03_mirror_coat_setup', 'setup',
      "The player's Shadow Tag Wobbuffet traps Togekiss (80%) and can only hurt it with Counter and Mirror Coat: Air Slash or Dazzling Gleam does about a third of Wobbuffet's HP and Mirror Coat returns double, a KO; Nasty Plot is free, since Mirror Coat fails against a status move, and at +6 Dazzling Gleam KOs Wobbuffet before it can reflect anything",
      [mon('Wobbuffet', ['Counter', 'Mirror Coat', 'Safeguard', 'Charm'], ability='Shadow Tag')],
      [mon('Togekiss', ['Nasty Plot', 'Air Slash', 'DazzlngGleam', 'Roost'], hp=0.8), mon('Blastoise', ['Scald', 'Flash Cannon'])],
      best=['Nasty Plot'], ok=['Roost'], bad=['Air Slash', 'DazzlngGleam'],
      checks=[('b03_countered', 'e0', 'Air Slash', 'p0'), ('b03_countered', 'e0', 'DazzlngGleam', 'p0'), ('b03_reflect_only', 'p0'),
              ('b03_boosted_ko', 'e0', 'DazzlngGleam', 'p0', 0, 6), ('has_ability', 'p0', 'Shadow Tag'), ('cls', 'Nasty Plot', 'status')]),
    S('b03_sturdy_counter', 'rules',
      'Sturdy Sudowoodo at full HP keeps 1 HP against Close Combat (99-116%, a KO on paper) and Counter returns twice what it lost, a KO on Infernape; Counter cannot return a special move: Vacuum Wave (36-44%) or Flamethrower takes away the full HP, and Close Combat then KOs next turn, before Counter (-5 priority) acts',
      [mon('Sudowoodo', ['Counter', 'Stone Edge', 'Sucker Punch', 'Stealth Rock'], ability='Sturdy')],
      [mon('Infernape', ['Close Combat', 'Mach Punch', 'Vacuum Wave', 'Flamethrower'], evs={'atk': 252, 'spa': 252})],
      best=['Vacuum Wave', 'Flamethrower'], ok=['Mach Punch'], bad=['Close Combat'],
      checks=[('b03_endures', 'p0', 'e0', 'Close Combat'), ('b03_countered', 'e0', 'Close Combat', 'p0'), ('cls', 'Vacuum Wave', 'special'),
              ('cls', 'Flamethrower', 'special'), ('b03_noko', 'e0', 'Vacuum Wave', 'p0'), ('b03_ko_at', 'e0', 'Close Combat', 'p0', 0.68),
              ('b03_ko_at', 'e0', 'Close Combat', 'p0', 0.82), ('b03_noko', 'p0', 'Stone Edge', 'e0'), ('b03_faster', 'e0', 'p0')]),
    S('b03_wp_ko_not_trigger', 'item',
      'Snorlax at 80% holds Weakness Policy: Close Combat (2x) KOs it outright, so the policy never fires; Aura Sphere (2x, 41-49%) does not KO, raises its Attack and Sp. Atk by two stages, and the +2 Earthquake (2x) then KOs Lucario, which Earthquake at +0 (69-83%) cannot; neutral hits do not trigger it but waste the KO',
      [mon('Snorlax', ['Body Slam', 'Earthquake', 'Crunch', 'Curse'], item='Weak. Policy', hp=0.8)],
      [mon('Lucario', ['Close Combat', 'Aura Sphere', 'Flash Cannon', 'ExtremeSpeed'])],
      best=['Close Combat'], ok=['Flash Cannon', 'ExtremeSpeed'], bad=['Aura Sphere'],
      checks=[('b03_ko', 'e0', 'Close Combat', 'p0'), ('b03_wp', 'e0', 'Aura Sphere', 'p0'), ('b03_boosted_ko', 'p0', 'Earthquake', 'e0', 2, 2),
              ('b03_noko', 'p0', 'Earthquake', 'e0'), ('b03_faster', 'e0', 'p0'), ('eff', 'e0', 'Flash Cannon', 'p0', 1.0)]),
    S('b03_dbl_wp_single_target', 'doubles',
      "The player's Tyranitar holds Weakness Policy: Earthquake would KO Heatran but also hit Tyranitar (2x, 55-65%) without a KO, and the slower Tyranitar's +2 Earthquake then KOs Excadrill this very turn; Drill Run aimed at Heatran KOs it and leaves Tyranitar unboosted (its Earthquake does 58-69%); any 2x hit on Tyranitar triggers the item",
      [mon('Tyranitar', ['Crunch', 'Stone Edge', 'Earthquake', 'Ice Beam'], item='Weak. Policy'), mon('Heatran', ['Flamethrower', 'Earth Power'])],
      [mon('Excadrill', ['Earthquake', 'Drill Run', 'Iron Head', 'Rock Slide']), mon('Zapdos', ['Thunderbolt', 'Heat Wave'])],
      best=['Drill Run>Heatran'], bad=['Earthquake', 'Drill Run>Tyranitar', 'Iron Head>Tyranitar'], double=True,
      checks=[('b03_ko', 'e0', 'Earthquake', 'p1'), ('b03_ko', 'e0', 'Drill Run', 'p1'), ('b03_wp', 'e0', 'Earthquake', 'p0'),
              ('b03_wp', 'e0', 'Drill Run', 'p0'), ('b03_wp', 'e0', 'Iron Head', 'p0'), ('b03_boosted_ko', 'p0', 'Earthquake', 'e0', 2, 2),
              ('b03_noko', 'p0', 'Earthquake', 'e0'), ('b03_noko', 'p0', 'Crunch', 'e0'), ('b03_eff', 'e0', 'Earthquake', 'e1', 0.0),
              ('b03_hits_ally', 'e0', 'Earthquake', True), ('b03_faster', 'e0', 'p1'), ('b03_faster', 'e0', 'p0')]),

    # --- Shedinja

    S('b03_shedinja_walls_it', 'switch',
      "Machamp has no super effective move against Shedinja and no status move: Close Combat, Earthquake, Ice Punch and Bullet Punch all fail on Wonder Guard, so Shedinja walls it and chips it with Shadow Claw; Kangaskhan takes Close Combat (2x) and dies, and the slower Kingambit is KO'd by it (4x) after a priority Sucker Punch at most",
      [mon('Machamp', ['Close Combat', 'Earthquake', 'Ice Punch', 'Bullet Punch'])],
      [mon('Kingambit', ['Iron Head', 'Sucker Punch', 'Night Slash', 'Swords Dance']), mon('Shedinja', ['Shadow Claw', 'X-Scissor', 'Shadow Sneak'], ability='Wonder Guard'), mon('Kangaskhan', ['Body Slam', 'Earthquake'])],
      best=['switch:Shedinja'], ok=['Sucker Punch'], bad=['switch:Kangaskhan', 'Iron Head', 'Night Slash', 'Swords Dance'],
      checks=[('b03_eff', 'p0', 'Close Combat', 'e1', 0.0), ('b03_eff', 'p0', 'Earthquake', 'e1', 0.0), ('b03_eff', 'p0', 'Ice Punch', 'e1', 0.0),
              ('b03_eff', 'p0', 'Bullet Punch', 'e1', 0.0), ('b03_attacks_only', 'p0'), ('b03_ko', 'p0', 'Close Combat', 'e0'),
              ('b03_faster', 'p0', 'e0'), ('b03_noko', 'e0', 'Sucker Punch', 'p0'), ('b03_entry_ko', 'p0', 'Close Combat', 'e2'),
              ('pri', 'Sucker Punch', 1)]),
    S('b03_shedinja_into_sand', 'weather',
      "The player's Hippowdon set a sandstorm: none of its attacks get through Wonder Guard, but the sand takes Shedinja's only HP at the end of the turn; Tangrowth (Rock, spared by the sand) takes Earthquake for 36-43%, is faster and KOs with Energy Ball (4x) within two hits; Jolteon's Electric moves cannot touch Hippowdon (Volt Switch does not switch out) and Earthquake (2x) KOs it",
      [mon('Hippowdon', ['Earthquake', 'Ice Fang', 'Slack Off', 'Whirlwind'], ability='Sand Stream')],
      [mon('Jolteon', ['Thunderbolt', 'Volt Switch', 'Shadow Ball', 'Thunder Wave'], hp=0.6), mon('Shedinja', ['Shadow Claw', 'X-Scissor', 'Shadow Sneak'], ability='Wonder Guard'), mon('Tangrowth', ['Energy Ball', 'Leech Seed', 'Rock Slide'])],
      best=['switch:Tangrowth'], bad=['switch:Shedinja', 'Thunderbolt', 'Volt Switch', 'Thunder Wave'],
      checks=[('weather', 'sand'), ('b03_eff', 'p0', 'Earthquake', 'e1', 0.0), ('b03_eff', 'p0', 'Ice Fang', 'e1', 0.0), ('chip_kos', 'e1'),
              ('b03_ko', 'p0', 'Earthquake', 'e0'), ('b03_eff', 'e0', 'Thunderbolt', 'p0', 0.0), ('b03_eff', 'e0', 'Volt Switch', 'p0', 0.0),
              ('b03_entry_wins', 'e2', 'p0', '*', 'Energy Ball', 2)]),

    # --- lasting value: a burn, a screen, Leech Seed

    S('b03_wisp_physical_wall', 'status',
      "Levitate Mismagius is immune to Snorlax's Body Slam and Earthquake, but Crunch takes 37-44% and wins the straight trade against Moonblast (22-27%); Will-O-Wisp (85% accurate) goes first since Mismagius is faster, halves every physical hit and costs Snorlax a sixteenth or an eighth a turn, and Moonblast then wins; Shadow Ball cannot touch a Normal type",
      [mon('Snorlax', ['Crunch', 'Earthquake', 'Body Slam', 'Fire Punch'])],
      [mon('Mismagius', ['Will-O-Wisp', 'Moonblast', 'Shadow Ball', 'Mystical Fire'], ability='Levitate')],
      best=['Will-O-Wisp'], bad=['Shadow Ball'],
      checks=[('b03_status_race', 'e0', 'Will-O-Wisp', 'Moonblast', 'p0', '*', 8), ('b03_loses', 'e0', '*', 'p0', 'Crunch'),
              ('b03_all_class', 'player', 'physical'), ('b03_faster', 'e0', 'p0'), ('b03_eff', 'p0', 'Body Slam', 'e0', 0.0),
              ('b03_eff', 'p0', 'Earthquake', 'e0', 0.0), ('b03_eff', 'p0', 'Crunch', 'e0', 1.0)]),
    S('b03_reflect_physical_team', 'status',
      "Every attack on the player's team is physical; Uxie holds Light Clay (an eight-turn screen), moves first and has weak attacks (Psychic cannot touch Krookodile or Bisharp, U-turn does 31-36%): Reflect halves everything the team takes for eight turns, Light Screen does nothing here, and Krookodile's Crunch (2x) cannot KO Uxie from full HP",
      [mon('Krookodile', ['Crunch', 'Earthquake', 'Stone Edge']), mon('Bisharp', ['Iron Head', 'Night Slash', 'X-Scissor']), mon('Staraptor', ['Brave Bird', 'Close Combat', 'U-turn'])],
      [mon('Uxie', ['Reflect', 'Light Screen', 'Psychic', 'U-turn'], item='Light Clay'), mon('Gyarados', ['Waterfall'])],
      best=['Reflect'], bad=['Light Screen', 'Psychic'],
      checks=[('b03_all_class', 'player', 'physical'), ('b03_eff', 'e0', 'Psychic', 'p0', 0.0), ('b03_faster', 'e0', 'p0'),
              ('b03_noko', 'p0', 'Crunch', 'e0'), ('has_item', 'e0', 'Light Clay'), ('b03_frac', 'e0', 'U-turn', 'p0', 0.0, 0.4)]),
    S('b03_leech_seed_outdrains', 'status',
      "Ferrothorn's attacks barely scratch Steel/Dragon Steelix (Power Whip 0.25x and Gyro Ball 0.5x, under 9%), while Leech Seed drains an eighth of Steelix's HP every turn, more than either attack, and heals Ferrothorn as much; Steelix's Earthquake (26-30%) is only neutral, so Protect is a decent move too",
      [mon('Steelix', ['Earthquake', 'Iron Head', 'Rock Slide', 'Stealth Rock'])],
      [mon('Ferrothorn', ['Leech Seed', 'Power Whip', 'Gyro Ball', 'Protect'])],
      best=['Leech Seed'], ok=['Protect'],
      checks=[('b03_seed_beats', 'e0', 'p0', 'Power Whip'), ('b03_seed_beats', 'e0', 'p0', 'Gyro Ball'), ('b03_eff', 'e0', 'Power Whip', 'p0', 0.25),
              ('b03_eff', 'e0', 'Gyro Ball', 'p0', 0.5), ('b03_noko', 'p0', 'Earthquake', 'e0')]),

    # --- the field set by an ability on entry

    S('b03_desolate_land_stay', 'weather',
      "Groudon at 80% has Desolate Land: in its harsh sun the player's Milotic's Water moves fail (Hydro Pump would be 4x and a KO in normal weather), and Moonblast and Ice Beam do under 25%; Groudon moves first and two Earthquakes KO Milotic; switching ends the harsh sun, and Arcanine would then take a 2x Water hit",
      [mon('Milotic', ['Hydro Pump', 'Surf', 'Moonblast', 'Ice Beam'])],
      [mon('Groudon', ['Earthquake', 'Stone Edge', 'Fire Punch', 'Swords Dance'], ability='DesolateLand', hp=0.8), mon('Arcanine', ['Flare Blitz', 'ExtremeSpeed'])],
      best=['Earthquake'], ok=['Swords Dance'], bad=['switch:Arcanine'],
      checks=[('b03_primal', 'harsh'), ('eff', 'p0', 'Hydro Pump', 'e0', 4.0), ('b03_fails', 'p0', 'Hydro Pump', 'e0'),
              ('b03_fails', 'p0', 'Surf', 'e0'), ('b03_race', 'e0', 'Earthquake', 'p0', '*', 2), ('eff', 'p0', 'Surf', 'e1', 2.0)]),
    S('b03_desolate_land_water_fails', 'weather',
      "The player's Groudon has Desolate Land: Swampert's Waterfall, 4x on Ground/Fire on paper, fails in the harsh sun; Earthquake (2x) is its only real damage",
      [mon('Groudon', ['Earthquake', 'Fire Punch', 'Stone Edge', 'Swords Dance'], ability='DesolateLand')],
      [mon('Swampert', ['Waterfall', 'Earthquake', 'Ice Punch', 'Stealth Rock'])],
      best=['Earthquake'], bad=['Waterfall'],
      checks=[('b03_primal', 'harsh'), ('eff', 'e0', 'Waterfall', 'p0', 4.0), ('b03_fails', 'e0', 'Waterfall', 'p0'),
              ('b03_eff', 'e0', 'Earthquake', 'p0', 2.0), ('b03_beats', 'e0', 'Earthquake', 'Ice Punch', 'p0')]),
    S('b03_psychic_terrain_priority', 'priority',
      "The player's Tapu Lele at 30% set Psychic Terrain and is grounded: Bullet Punch, a KO on paper, fails, and Lele is faster, so Iron Head and X-Scissor come too late; the boosted Psychic KOs Scizor whatever it does; Metagross takes Psychic at 0.25x, survives anything Lele has and KOs it with Meteor Mash, while Toxicroak takes the boosted Psychic 4x",
      [mon('Tapu Lele', ['Psychic', 'Moonblast', 'Focus Blast', 'Calm Mind'], ability='PsychicSurge', hp=0.3)],
      [mon('Scizor', ['Bullet Punch', 'Iron Head', 'X-Scissor', 'Swords Dance'], hp=0.3), mon('Metagross', ['Meteor Mash', 'Bullet Punch', 'Earthquake']), mon('Toxicroak', ['Gunk Shot', 'Drain Punch', 'Sucker Punch'])],
      best=['switch:Metagross'], bad=['Bullet Punch', 'Iron Head', 'X-Scissor', 'Swords Dance', 'switch:Toxicroak'],
      checks=[('b03_terrain', 'psychic'), ('b03_grounded', 'p0', True), ('ko', 'e0', 'Bullet Punch', 'p0'), ('pri', 'Bullet Punch', 1),
              ('b03_fails', 'e0', 'Bullet Punch', 'p0'), ('b03_faster', 'p0', 'e0'), ('b03_ko', 'p0', 'Psychic', 'e0'),
              ('b03_entry_ko', 'p0', 'Psychic', 'e2'), ('b03_entry_wins', 'e1', 'p0', '*', 'Meteor Mash', 1)]),
    S('b03_misty_terrain_status', 'status',
      "The player's Tapu Fini set Misty Terrain and is grounded: Spore and Toxic fail; Sludge Bomb and Giga Drain are both 2x, and Fini's attacks are resisted (under 20%)",
      [mon('Tapu Fini', ['Scald', 'Moonblast', 'Calm Mind', 'Taunt'], ability='Misty Surge')],
      [mon('Amoonguss', ['Spore', 'Sludge Bomb', 'Giga Drain', 'Toxic'])],
      best=['Sludge Bomb', 'Giga Drain'], bad=['Spore', 'Toxic'],
      checks=[('b03_terrain', 'misty'), ('b03_grounded', 'p0', True), ('b03_fails', 'e0', 'Spore', 'p0'), ('b03_fails', 'e0', 'Toxic', 'p0'),
              ('b03_eff', 'e0', 'Sludge Bomb', 'p0', 2.0), ('b03_eff', 'e0', 'Giga Drain', 'p0', 2.0), ('b03_noko', 'p0', 'Moonblast', 'e0')]),
    S('b03_electric_terrain_spore', 'switch',
      "The player's Tapu Koko set Electric Terrain and is grounded, so Spore fails; Koko is faster and Dazzling Gleam (2x) wins the trade with Breloom; Excadrill is immune to Thunderbolt, resists Dazzling Gleam and KOs Koko with Earthquake (2x)",
      [mon('Tapu Koko', ['Thunderbolt', 'DazzlngGleam', 'Calm Mind', 'Roost'], ability='Elec. Surge')],
      [mon('Breloom', ['Spore', 'Mach Punch', 'Seed Bomb', 'Swords Dance']), mon('Excadrill', ['Earthquake', 'Iron Head', 'Rock Slide'])],
      best=['switch:Excadrill'], bad=['Spore', 'Swords Dance'],
      checks=[('b03_terrain', 'electric'), ('b03_grounded', 'p0', True), ('b03_fails', 'e0', 'Spore', 'p0'), ('b03_faster', 'p0', 'e0'),
              ('b03_loses', 'e0', '*', 'p0', 'DazzlngGleam'), ('b03_eff', 'p0', 'Thunderbolt', 'e1', 0.0),
              ('b03_entry_wins', 'e1', 'p0', '*', 'Earthquake', 1)]),
    S('b03_grassy_terrain_halves_eq', 'weather',
      "The player's Roserade set Grassy Terrain and is grounded, which halves Earthquake (33-39%); Fire Fang (2x, 57-68%) and Dragon Claw (52-62%) both do clearly more",
      [mon('Roserade', ['Giga Drain', 'Sludge Bomb', 'Shadow Ball', 'Spikes'], ability='Grassy Surge')],
      [mon('Garchomp', ['Earthquake', 'Dragon Claw', 'Fire Fang', 'Stone Edge'])],
      best=['Fire Fang'], ok=['Dragon Claw', 'Stone Edge'],
      checks=[('b03_terrain', 'grassy'), ('b03_grounded', 'p0', True), ('b03_beats', 'e0', 'Fire Fang', 'Earthquake', 'p0'),
              ('b03_beats', 'e0', 'Dragon Claw', 'Earthquake', 'p0'), ('b03_eff', 'e0', 'Earthquake', 'p0', 1.0), ('b03_faster', 'e0', 'p0')]),

    # --- single-battle rules

    S('b03_lunar_dance_full_team', 'rules',
      'Cresselia is faster and Moonblast (2x) KOs Goodra at 30%, whose Dragon moves cannot touch a Fairy and whose other moves do under 22%; Lunar Dance would faint Cresselia to heal a Lapras that is already at full HP',
      [mon('Goodra', ['Dragon Pulse', 'Draco Meteor', 'Fire Blast', 'Thunderbolt'], hp=0.3)],
      [mon('Cresselia', ['Lunar Dance', 'Moonblast', 'Psychic', 'Thunder Wave'], ability='Levitate'), mon('Lapras', ['Surf', 'Ice Beam'])],
      best=['Moonblast'], bad=['Lunar Dance'],
      checks=[('b03_ko', 'e0', 'Moonblast', 'p0'), ('b03_faster', 'e0', 'p0'), ('b03_eff', 'p0', 'Dragon Pulse', 'e0', 0.0),
              ('b03_eff', 'p0', 'Draco Meteor', 'e0', 0.0), ('b03_noko', 'p0', 'Fire Blast', 'e0'), ('b03_noko', 'p0', 'Thunderbolt', 'e0')]),
    S('b03_endeavor_sash', 'rules',
      'Primeape is faster and Close Combat would KO Furret, but the Focus Sash keeps Furret at 1 HP; Endeavor then cuts Primeape to 1 HP, and next turn Quick Attack (priority, and Primeape has none) finishes it; Double-Edge at 1 HP faints Furret to its own recoil',
      [mon('Primeape', ['Close Combat', 'Gunk Shot', 'Stone Edge', 'Thunder Punch'])],
      [mon('Furret', ['Endeavor', 'Quick Attack', 'Double-Edge', 'Body Slam'], item='Focus Sash')],
      best=['Endeavor'], bad=['Double-Edge'],
      checks=[('b03_faster', 'p0', 'e0'), ('ko', 'p0', 'Close Combat', 'e0'), ('b03_endures', 'e0', 'p0', 'Close Combat'), ('b03_single_hits', 'p0'),
              ('b03_no_priority', 'p0'), ('eff', 'e0', 'Endeavor', 'p0', 1.0), ('pri', 'Quick Attack', 1), ('b03_noko', 'e0', 'Double-Edge', 'p0'),
              ('b03_noko', 'e0', 'Body Slam', 'p0')]),
    S('b03_swords_dance_foul_play', 'setup',
      "Grimmsnarl's own attacks barely hurt Scizor, but Foul Play uses Scizor's Attack: at +0 it does 46-56% and cannot KO Scizor at 80%, after Swords Dance it KOs; Scizor is faster and Iron Head (2x) KOs Grimmsnarl at 85% now",
      [mon('Grimmsnarl', ['Foul Play', 'Spirit Break', 'Thunder Wave', 'Taunt'], hp=0.85)],
      [mon('Scizor', ['Swords Dance', 'Iron Head', 'Bullet Punch', 'X-Scissor'], hp=0.8)],
      best=['Iron Head'], ok=['Bullet Punch'], bad=['Swords Dance'],
      checks=[('b03_ko', 'e0', 'Iron Head', 'p0'), ('b03_faster', 'e0', 'p0'), ('b03_foul_noko', 'p0', 'e0', 0), ('b03_foul_ko', 'p0', 'e0', 2),
              ('b03_noko', 'p0', 'Spirit Break', 'e0'), ('b03_no_priority', 'p0')]),
    S('b03_follow_me_singles', 'rules',
      'Electivire at 30% is faster and ThunderPunch (2x) KOs Togekiss at 25%; Dazzling Gleam would KO Electivire but comes second, and Follow Me (+2 priority) does nothing in a single battle; Golurk is immune to ThunderPunch and Cross Chop and KOs Electivire with Earthquake',
      [mon('Electivire', ['ThunderPunch', 'Cross Chop', 'Fire Punch', 'Earthquake'], hp=0.3)],
      [mon('Togekiss', ['Follow Me', 'Air Slash', 'DazzlngGleam', 'Roost'], hp=0.25), mon('Golurk', ['Earthquake', 'Shadow Punch', 'Ice Punch'])],
      best=['switch:Golurk'], bad=['Follow Me', 'Roost', 'Air Slash', 'DazzlngGleam'],
      checks=[('pri', 'Follow Me', 2), ('b03_faster', 'p0', 'e0'), ('b03_ko', 'p0', 'ThunderPunch', 'e0'), ('b03_ko', 'e0', 'DazzlngGleam', 'p0'),
              ('b03_eff', 'p0', 'ThunderPunch', 'e1', 0.0), ('b03_eff', 'p0', 'Cross Chop', 'e1', 0.0),
              ('b03_entry_wins', 'e1', 'p0', '*', 'Earthquake', 1), ('b03_no_priority', 'p0')]),
    S('b03_choice_lock_fairy_bench', 'item',
      "Choice Scarf Garchomp outspeeds Raikou at 20%, and Earthquake and Dragon Claw both KO it, but the Scarf locks the move in: the player's Clefable comes in next, immune to Dragon Claw, while a locked Earthquake still does about half",
      [mon('Raikou', ['Thunderbolt', 'Shadow Ball', 'Extrasensory', 'Calm Mind'], hp=0.2), mon('Clefable', ['Moonblast', 'Soft-Boiled', 'Thunder Wave'])],
      [mon('Garchomp', ['Earthquake', 'Dragon Claw', 'Stone Edge', 'Fire Fang'], item='Choice Scarf')],
      best=['Earthquake'], ok=['Stone Edge'],
      checks=[('has_item', 'e0', 'Choice Scarf'), ('b03_faster', 'e0', 'p0'), ('b03_ko', 'e0', 'Earthquake', 'p0'),
              ('b03_ko', 'e0', 'Dragon Claw', 'p0'), ('b03_eff', 'e0', 'Dragon Claw', 'p1', 0.0), ('b03_eff', 'e0', 'Earthquake', 'p1', 1.0),
              ('b03_frac', 'e0', 'Earthquake', 'p1', 0.45, 0.65)]),

    # --- free choice: rules, recovery, setup, status, abilities, items, weather, damage

    S('b03_destiny_bond_doomed', 'rules',
      "Froslass at 70% is faster than Kingambit, its attacks are resisted (under 22%), and Iron Head, Night Slash or Stone Edge KOs it next; Destiny Bond takes Kingambit down with it if it attacks, and Kingambit would otherwise also KO Gardevoir, the AI's last Pokémon",
      [mon('Kingambit', ['Iron Head', 'Night Slash', 'Stone Edge', 'Earthquake'])],
      [mon('Froslass', ['Destiny Bond', 'Ice Beam', 'Shadow Ball', 'Spikes'], hp=0.7), mon('Gardevoir', ['Moonblast', 'Psychic'])],
      best=['Destiny Bond'],
      checks=[('b03_faster', 'e0', 'p0'), ('b03_ko', 'p0', 'Iron Head', 'e0'), ('b03_ko', 'p0', 'Night Slash', 'e0'),
              ('b03_ko', 'p0', 'Stone Edge', 'e0'), ('b03_noko', 'e0', 'Ice Beam', 'p0'), ('b03_noko', 'e0', 'Shadow Ball', 'p0'),
              ('b03_no_priority', 'p0'), ('b03_ko', 'p0', 'Iron Head', 'e1')]),
    S('b03_healing_wish_doomed', 'recovery',
      'Mesprit at 5% faints to the sandstorm at the end of the turn whatever it does, and it is faster than Tyranitar: Healing Wish brings the next Pokémon in at full HP with its status cured; Lucario at 40% and paralyzed is slower than Tyranitar and dies to Earthquake (2x), while healed it is faster and Close Combat (4x) KOs; Psychic cannot touch a Dark type, and U-turn would bring the crippled Lucario in at once',
      [mon('Tyranitar', ['Stone Edge', 'Crunch', 'Earthquake', 'Ice Beam'], ability='Sand Stream')],
      [mon('Mesprit', ['Healing Wish', 'Psychic', 'Ice Beam', 'U-turn'], hp=0.05), mon('Lucario', ['Close Combat', 'Extreme Speed', 'Flash Cannon'], hp=0.4, status='par')],
      best=['Healing Wish'], bad=['Psychic', 'U-turn'],
      checks=[('weather', 'sand'), ('chip_kos', 'e0'), ('b03_faster', 'e0', 'p0'), ('b03_eff', 'e0', 'Psychic', 'p0', 0.0),
              ('b03_noko', 'e0', 'U-turn', 'p0'), ('has_status', 'e1', 'par'), ('b03_loses', 'e1', '*', 'p0', 'Earthquake'),
              ('b03_race_healed', 'e1', 'Close Combat', 'p0', '*', 1)]),
    S('b03_prankster_encore_turn_one', 'rules',
      "Encore fails against a Pokémon that has not used a move yet, and on turn 1 Whimsicott's Encore (Prankster priority, and Whimsicott is faster anyway) comes before Dragonite's first move; Moonblast (2x) takes over half, and Dragonite's Outrage cannot touch a Fairy",
      [mon('Dragonite', ['Dragon Dance', 'Outrage', 'Earthquake', 'ExtremeSpeed'])],
      [mon('Whimsicott', ['Encore', 'Moonblast', 'Stun Spore', 'Giga Drain'], ability='Prankster')],
      best=['Moonblast'], bad=['Encore'],
      checks=[('b03_faster', 'e0', 'p0'), ('mpri', 'e0', 'Encore', 1), ('b03_eff', 'e0', 'Moonblast', 'p0', 2.0),
              ('b03_eff', 'p0', 'Outrage', 'e0', 0.0), ('b03_noko', 'p0', 'ExtremeSpeed', 'e0'), ('b03_noko', 'p0', 'Earthquake', 'e0')]),
    S('b03_toxic_poison_heal', 'status',
      'Poison Heal Gliscor recovers an eighth of its HP every turn while poisoned, so Toxic heals it; Ice Beam (4x) KOs it after its Earthquake (37-44%)',
      [mon('Gliscor', ['Earthquake', 'Stone Edge', 'Knock Off', 'Roost'], ability='Poison Heal')],
      [mon('Vaporeon', ['Toxic', 'Scald', 'Ice Beam', 'Wish'])],
      best=['Ice Beam'], ok=['Scald'], bad=['Toxic'],
      checks=[('has_ability', 'p0', 'Poison Heal'), ('b03_ko', 'e0', 'Ice Beam', 'p0'), ('b03_noko', 'e0', 'Scald', 'p0'),
              ('b03_noko', 'p0', 'Earthquake', 'e0'), ('b03_faster', 'p0', 'e0')]),
    S('b03_magic_bounce_hypnosis', 'ability',
      'Magic Bounce Hatterene reflects status moves back: Hypnosis would put Gengar to sleep and Will-O-Wisp would burn it; Gengar is faster and Sludge Bomb (2x) KOs Hatterene at 65% before its Psychic (2x) KOs Gengar',
      [mon('Hatterene', ['Psychic', 'DazzlngGleam', 'Calm Mind', 'MysticalFire'], ability='Magic Bounce', hp=0.65)],
      [mon('Gengar', ['Hypnosis', 'Will-O-Wisp', 'Sludge Bomb', 'Shadow Ball'])],
      best=['Sludge Bomb'], ok=['Shadow Ball'], bad=['Hypnosis', 'Will-O-Wisp'],
      checks=[('has_ability', 'p0', 'Magic Bounce'), ('b03_ko', 'e0', 'Sludge Bomb', 'p0'), ('b03_faster', 'e0', 'p0'),
              ('b03_ko', 'p0', 'Psychic', 'e0'), ('cls', 'Hypnosis', 'status'), ('cls', 'Will-O-Wisp', 'status')]),
    S('b03_speed_boost_protect', 'setup',
      'Sharpedo at 70% is slower than Alakazam, whose Energy Ball (2x) KOs it; Alakazam has only attacks, so Protect wastes its turn, Speed Boost makes Sharpedo the faster one (+1), and Crunch (2x) KOs Alakazam first next turn; attacking now loses Sharpedo',
      [mon('Alakazam', ['Psychic', 'Focus Blast', 'Shadow Ball', 'Energy Ball'])],
      [mon('Sharpedo', ['Protect', 'Crunch', 'Waterfall', 'Ice Fang'], ability='Speed Boost', hp=0.7)],
      best=['Protect'], bad=['Crunch', 'Waterfall', 'Ice Fang'],
      checks=[('b03_attacks_only', 'p0'), ('b03_protect_race', 'e0', 'Crunch', 'p0', '*', 2), ('b03_loses', 'e0', '*', 'p0', 'Energy Ball'),
              ('b03_faster', 'p0', 'e0'), ('pri', 'Protect', 4)]),
    S('b03_recover_into_ohko', 'recovery',
      "Choice Band Scizor's X-Scissor (2x) KOs Starmie even from full HP, so Recover at 40% gains nothing; Starmie is faster and Surf takes 42-50% before it falls",
      [mon('Scizor', ['X-Scissor', 'Bullet Punch', 'Iron Head', 'Superpower'], item='Choice Band')],
      [mon('Starmie', ['Recover', 'Surf', 'Thunderbolt', 'Psychic'], hp=0.4)],
      best=['Surf'], ok=['Thunderbolt', 'Psychic'], bad=['Recover'],
      checks=[('has_item', 'p0', 'Choice Band'), ('b03_ko_at', 'p0', 'X-Scissor', 'e0', 1.0), ('b03_faster', 'e0', 'p0'),
              ('b03_noko', 'e0', 'Surf', 'p0'), ('b03_beats', 'e0', 'Surf', 'Psychic', 'p0')]),
    S('b03_sun_halves_hydro_pump', 'weather',
      "The player's Drought sun halves Water moves: Hydro Pump (2x, 110 power) does less than Earth Power (2x, 90 power), which KOs Torkoal at 72%; Recover at full HP does nothing",
      [mon('Torkoal', ['Lava Plume', 'Earth Power', 'Stealth Rock', 'Yawn'], ability='Drought', hp=0.72)],
      [mon('Gastrodon', ['Hydro Pump', 'Earth Power', 'Ice Beam', 'Recover'])],
      best=['Earth Power'], ok=['Hydro Pump'], bad=['Recover'],
      checks=[('weather', 'sun'), ('b03_ko', 'e0', 'Earth Power', 'p0'), ('b03_noko', 'e0', 'Hydro Pump', 'p0'),
              ('b03_beats', 'e0', 'Earth Power', 'Hydro Pump', 'p0'), ('eff', 'e0', 'Hydro Pump', 'p0', 2.0), ('acc_lt', 'Hydro Pump', 100),
              ('b03_noko', 'p0', 'Earth Power', 'e0')]),
    S('b03_magic_guard_life_orb', 'item',
      "Magic Guard Clefable takes no Life Orb recoil, so at 6% it can still attack: it is faster and Moonblast (2x) KOs Machamp at 50%; healing gives up the KO, and Machamp's Poison Jab (2x) can KO it even after a heal",
      [mon('Machamp', ['Close Combat', 'Poison Jab', 'Stone Edge', 'Ice Punch'], hp=0.5)],
      [mon('Clefable', ['Moonblast', 'Soft-Boiled', 'Flamethrower', 'Calm Mind'], ability='Magic Guard', item='Life Orb', hp=0.06)],
      best=['Moonblast'], bad=['Soft-Boiled', 'Calm Mind', 'Flamethrower'],
      checks=[('has_item', 'e0', 'Life Orb'), ('has_ability', 'e0', 'Magic Guard'), ('b03_ko', 'e0', 'Moonblast', 'p0'),
              ('survives_recoil', 'e0', 'Moonblast', 'p0'), ('b03_faster', 'e0', 'p0'), ('b03_ko', 'p0', 'Poison Jab', 'e0'),
              ('b03_noko', 'e0', 'Flamethrower', 'p0'), ('b03_no_priority', 'p0')]),
    S('b03_technician_fake_out_bracket', 'priority',
      'Dragonite at 16% has ExtremeSpeed (+2), which KOs Ambipom at 20% before Sucker Punch (+1) or any other attack; Fake Out (+3, first turn only) goes first and with Technician (60 power) KOs',
      [mon('Dragonite', ['Outrage', 'ExtremeSpeed', 'Earthquake', 'Fire Punch'], hp=0.16)],
      [mon('Ambipom', ['Fake Out', 'Sucker Punch', 'U-turn', 'Double Hit'], ability='Technician', hp=0.2)],
      best=['Fake Out'], bad=['Sucker Punch', 'U-turn', 'Double Hit'],
      checks=[('b03_ko', 'e0', 'Fake Out', 'p0'), ('has_ability', 'e0', 'Technician'), ('pri', 'Fake Out', 3), ('pri', 'ExtremeSpeed', 2),
              ('pri', 'Sucker Punch', 1), ('b03_first', 'e0', 'Fake Out', 'p0', 'ExtremeSpeed'),
              ('b03_first', 'p0', 'ExtremeSpeed', 'e0', 'Sucker Punch'), ('b03_ko', 'p0', 'ExtremeSpeed', 'e0'),
              ('b03_ko', 'e0', 'Double Hit', 'p0')]),
    S('b03_venoshock_poisoned', 'damage',
      'Clefable is poisoned, so Venoshock doubles to 130 power and, with STAB and 2x, KOs it at 90%, where Sludge Bomb (90 power, the better move against a healthy target) may not',
      [mon('Clefable', ['Moonblast', 'Soft-Boiled', 'Calm Mind', 'Flamethrower'], hp=0.9, status='psn')],
      [mon('Roserade', ['Venoshock', 'Sludge Bomb', 'Leaf Storm', 'Shadow Ball'])],
      best=['Venoshock'], ok=['Sludge Bomb'],
      checks=[('has_status', 'p0', 'psn'), ('b03_ko', 'e0', 'Venoshock', 'p0'), ('beats', 'e0', 'Sludge Bomb', 'Venoshock', 'p0'),
              ('b03_beats', 'e0', 'Venoshock', 'Sludge Bomb', 'p0'), ('b03_faster', 'e0', 'p0'), ('b03_noko', 'p0', 'Flamethrower', 'e0')]),
    S('b03_pain_split_blissey', 'recovery',
      "None of Dusknoir's attacks touch Normal-type Blissey and Seismic Toss cannot touch a Ghost; Pain Split averages the two HP totals: Dusknoir (30%) goes back to full and Blissey loses 147; Blissey's Ice Beam cannot KO Dusknoir first",
      [mon('Blissey', ['Seismic Toss', 'Ice Beam', 'Soft-Boiled', 'Toxic'])],
      [mon('Dusknoir', ['Pain Split', 'Shadow Sneak', 'Will-O-Wisp', 'Shadow Punch'], hp=0.3)],
      best=['Pain Split'], ok=['Will-O-Wisp'], bad=['Shadow Sneak', 'Shadow Punch'],
      checks=[('b03_split_beats', 'e0', 'p0', 'Shadow Punch'), ('b03_eff', 'e0', 'Shadow Sneak', 'p0', 0.0),
              ('b03_eff', 'e0', 'Shadow Punch', 'p0', 0.0), ('b03_eff', 'p0', 'Seismic Toss', 'e0', 0.0), ('b03_noko', 'p0', 'Ice Beam', 'e0'),
              ('b03_faster', 'p0', 'e0')]),
    S('b03_burned_scarf_foe_stay', 'switch',
      "The player's Choice Scarf Garchomp is faster but burned: Stone Edge, a KO on Glaceon at 55% without the burn, now does 30-36% at most, and Ice Beam (4x) then KOs it; switching to Bronzong or using Wish gives up the KO",
      [mon('Garchomp', ['Earthquake', 'Dragon Claw', 'Stone Edge', 'Fire Fang'], item='Choice Scarf', hp=0.75, status='brn')],
      [mon('Glaceon', ['Ice Beam', 'Shadow Ball', 'Water Pulse', 'Wish'], hp=0.55), mon('Bronzong', ['Gyro Ball', 'Psychic'], ability='Levitate')],
      best=['Ice Beam'], bad=['switch:Bronzong', 'Wish'],
      checks=[('has_status', 'p0', 'brn'), ('b03_faster', 'p0', 'e0'), ('b03_noko', 'p0', 'Earthquake', 'e0'),
              ('b03_noko', 'p0', 'Dragon Claw', 'e0'), ('b03_noko', 'p0', 'Stone Edge', 'e0'), ('b03_ko', 'e0', 'Ice Beam', 'p0'),
              ('b03_eff', 'e0', 'Ice Beam', 'p0', 4.0)]),
    S('b03_facade_poisoned', 'damage',
      'Ursaring is poisoned, so Facade doubles to 140 power and KOs Alakazam, where Crunch (2x, the better move on paper) may fall short; Alakazam is faster but its Psychic cannot KO first',
      [mon('Alakazam', ['Psychic', 'Shadow Ball', 'Energy Ball', 'Calm Mind'])],
      [mon('Ursaring', ['Facade', 'Crunch', 'Close Combat', 'Earthquake'], status='psn')],
      best=['Facade'], ok=['Crunch'],
      checks=[('has_status', 'e0', 'psn'), ('b03_ko', 'e0', 'Facade', 'p0'), ('beats', 'e0', 'Crunch', 'Facade', 'p0'),
              ('b03_beats', 'e0', 'Facade', 'Crunch', 'p0'), ('b03_faster', 'p0', 'e0'), ('b03_noko', 'p0', 'Psychic', 'e0'),
              ('b03_noko', 'p0', 'Energy Ball', 'e0')]),
    S('b03_solar_beam_no_sun', 'rules',
      "There is no sun, so Solar Beam spends this turn charging and Swampert's Earthquake KOs Venusaur at 40% before it fires; Giga Drain (4x) KOs now, and Venusaur is faster",
      [mon('Swampert', ['Earthquake', 'Ice Beam', 'Waterfall', 'Stealth Rock'], hp=0.95)],
      [mon('Venusaur', ['Solar Beam', 'Giga Drain', 'Sludge Bomb', 'Sleep Powder'], hp=0.4)],
      best=['Giga Drain'], bad=['Solar Beam'],
      checks=[('weather', None), ('b03_charges', 'e0', 'Solar Beam'), ('b03_ko', 'e0', 'Giga Drain', 'p0'), ('b03_faster', 'e0', 'p0'),
              ('b03_ko', 'p0', 'Earthquake', 'e0')]),
    S('b03_super_fang_wall', 'damage',
      "Super Fang takes half of Skarmory's HP (77) whatever its Defense or type, more than any of Raticate's attacks (Double-Edge is resisted, Crunch does under 17%)",
      [mon('Skarmory', ['Brave Bird', 'Iron Head', 'Roost', 'Spikes'])],
      [mon('Raticate', ['Super Fang', 'Double-Edge', 'Crunch', 'Sucker Punch'])],
      best=['Super Fang'], ok=['Crunch'],
      checks=[('b03_half_beats', 'e0', 'p0', 'Crunch'), ('b03_half_beats', 'e0', 'p0', 'Double-Edge'),
              ('b03_half_beats', 'e0', 'p0', 'Sucker Punch'), ('eff', 'e0', 'Double-Edge', 'p0', 0.5), ('b03_faster', 'e0', 'p0')]),

    # --- free choice: doubles

    S('b03_dbl_explosion_ghost_partner', 'doubles',
      'Metagross at 25% moves first and either foe KOs it next; Explosion hits every other Pokémon, but partner Dusknoir is a Ghost and immune, and it KOs both Machamp (50%) and Miltank (40%), where a single-target hit KOs one',
      [mon('Machamp', ['Close Combat', 'Stone Edge'], hp=0.5), mon('Miltank', ['Body Slam', 'Earthquake'], hp=0.4)],
      [mon('Metagross', ['Explosion', 'Meteor Mash', 'Zen Headbutt', 'Bullet Punch'], hp=0.25), mon('Dusknoir', ['Shadow Sneak', 'Will-O-Wisp'])],
      best=['Explosion'], ok=['Zen Headbutt>Machamp', 'Meteor Mash>Miltank'], double=True,
      checks=[('b03_ko', 'e0', 'Explosion', 'p0'), ('b03_ko', 'e0', 'Explosion', 'p1'), ('ally_immune', 'e1', 'e0', 'Explosion'),
              ('b03_faster', 'e0', 'p0'), ('b03_faster', 'e0', 'p1'), ('b03_ko', 'p0', 'Close Combat', 'e0'), ('b03_ko', 'p1', 'Earthquake', 'e0'),
              ('b03_ko', 'e0', 'Zen Headbutt', 'p0'), ('b03_ko', 'e0', 'Zen Headbutt', 'p0')]),
    S('b03_dbl_heat_wave_not_lava_plume', 'doubles',
      'Heat Wave hits only the two foes and KOs both (4x, spread damage); Lava Plume hits every other Pokémon, partner Escavalier included (4x, 105-122%)',
      [mon('Ferrothorn', ['Power Whip', 'Gyro Ball']), mon('Abomasnow', ['Blizzard', 'Wood Hammer'])],
      [mon('Heatran', ['Heat Wave', 'Lava Plume', 'Earth Power', 'Flash Cannon']), mon('Escavalier', ['Megahorn', 'Iron Head'])],
      best=['Heat Wave'], bad=['Lava Plume'], double=True,
      checks=[('b03_ko', 'e0', 'Heat Wave', 'p0'), ('b03_ko', 'e0', 'Heat Wave', 'p1'), ('b03_hits_ally', 'e0', 'Heat Wave', False),
              ('b03_hits_ally', 'e0', 'Lava Plume', True), ('b03_frac', 'e0', 'Lava Plume', 'e1', 0.95, 1.3), ('acc_lt', 'Heat Wave', 100)]),
    S('b03_dbl_mold_breaker_eq_shedinja', 'doubles',
      "Mold Breaker ignores Wonder Guard, the partner's included: Earthquake would knock out Shedinja along with Magnezone, and Gyarados is immune to it; Drill Run (single target, 4x) KOs Magnezone alone",
      [mon('Magnezone', ['Thunderbolt', 'Flash Cannon']), mon('Gyarados', ['Waterfall', 'Ice Fang'])],
      [mon('Excadrill', ['Earthquake', 'Drill Run', 'Iron Head', 'Rock Slide'], ability='Mold Breaker'), mon('Shedinja', ['Shadow Sneak', 'X-Scissor'], ability='Wonder Guard')],
      best=['Drill Run>Magnezone'], bad=['Earthquake'], double=True,
      checks=[('has_ability', 'e0', 'Mold Breaker'), ('has_ability', 'e1', 'Wonder Guard'), ('b03_hits_ally', 'e0', 'Earthquake', True),
              ('b03_eff', 'e0', 'Earthquake', 'e1', 0.5), ('b03_ko', 'e0', 'Earthquake', 'e1'), ('b03_eff', 'e0', 'Earthquake', 'p1', 0.0),
              ('b03_ko', 'e0', 'Drill Run', 'p0'), ('b03_ko', 'e0', 'Earthquake', 'p0')]),
])
