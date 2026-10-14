/* One hit's damage: tools/aicalc.py's Gen 5 formula (base power, Attack and Defense modifiers chained in 4096ths,
   then weather, critical hit, the 85-100 roll, STAB, type effectiveness, burn, the final modifiers), ported to ROM ids.
   Where aicalc keeps a range for a factor nobody measured, the value here is the one the logs fit (aicalc's notes),
   else the official one; ENGINE_FACTS.md's measured changes are in (Shell Armor 0.81, Tough Claws on every physical
   move, Sharpness on Dragon Claw, Soul Dew inert, items without an engine handler inert).
   q->sim reproduces the engine's own simulation (E_SIM_DAMAGE), which the AI reads: 1 against a type immunity, no
   "no effect" abilities or Air Balloon, and the defender's ability and item only when it is on the field. */
#include "sim.h"
#include "sim_ids.h"

/* the AI's effect codes for the moves whose power or stats are special (tools/aicalc.py E) */
enum { E_WEIGHT = 196, E_HEAVY_SLAM = 291, E_RETURN = 121, E_FRUSTRATION = 123, E_WEATHER_BALL = 203, E_FOUL_PLAY = 297, E_BODY_PRESS = 433, E_RIVAL = 430, E_KNOCK_OFF = 188, E_PSYSHOCK = 282,
       E_FACADE = 169, E_BRINE = 221, E_VENOSHOCK = 283, E_HEX = 310, E_ACROBATICS = 317, E_ERUPTION = 190,
       E_GYRO_BALL = 219, E_ELECTRO_BALL = 293, E_REVERSAL = 99, E_LEVEL_DAMAGE = 87, E_DRAGON_RAGE = 41,
       E_SONIC_BOOM = 130, E_STORED_POWER = 305, E_SUPER_FANG = 40, E_JUDGMENT = 268, E_HIDDEN_POWER = 135,
       E_ENDEAVOR = 189, E_FINAL_GAMBIT = 320 };

/* fixed damage, -1 for a move without it. The engine's simulation gives it whatever the types, and rolls nothing
   (measured on the bench records: Seismic Toss on a Ghost, Endeavor) */
static int fixed_damage(const Mon *a, const Mon *d, int eff_id, int sim)
{
    switch (eff_id) {
    case E_LEVEL_DAMAGE: return a->level;
    case E_DRAGON_RAGE: return 40;
    case E_SONIC_BOOM: return 20;
    case E_SUPER_FANG: return d->hp / 2 > 1 ? d->hp / 2 : 1;
    case E_ENDEAVOR: return sim ? (d->hp > a->hp ? d->hp - a->hp : 1) : -1;
    case E_FINAL_GAMBIT: return sim ? a->hp : -1;
    }
    return -1;
}

typedef int64_t s64;
static int q12(double f) { return (int)(f * 4096 + 0.5); }
static int chain(int m, int x) { return (m * x + 2048) >> 12; }
static int modify(int v, int m) { return (int)(((s64)v * m + 2047) >> 12); }

static int staged(int stat, int stage)
{
    if (stage > 6) stage = 6;
    if (stage < -6) stage = -6;
    return stage >= 0 ? stat * (2 + stage) / 2 : stat * 2 / (2 - stage);
}

/* Speed with its stage, Choice Scarf, the half-Speed items and paralysis (Gyro Ball, Electro Ball) */
static int speed_of(const Mon *m, const s8 *st, int item, int ab, int weather)
{
    int s = staged(m->stat[STAT_SPE], st ? st[STAT_SPE] : 0);
    if ((ab == A_SWIFTSWIM && (weather == W_RAIN || weather == WX_HEAVY_RAIN)) ||
        (ab == A_CHLOROPHYLL && (weather == W_SUN || weather == WX_HARSH_SUN)) || (ab == A_SANDRUSH && weather == W_SAND) ||
        (ab == A_SLUSHRUSH && weather == W_SNOW))
        s *= 2;                         /* the weather Speed abilities count for Gyro Ball (logs) */
    if (item == I_CHOICESCARF)
        s = s * 3 / 2;
    if (item == I_MACHOBRACE || item == I_IRONBALL || item == I_POWERANKLET)
        s /= 2;
    if (ab == A_QUICKFEET && m->status)
        s = s * 3 / 2;
    if (m->status == ST_PAR && ab != A_QUICKFEET)   /* halves last; Quick Feet lifts it (rc27 engine fix) */
        s /= 2;
    return s;
}

static int has_type(const u8 *t, int x) { return t[0] == x || t[1] == x || t[2] == x; }

/* Low Kick and Grass Knot by the target's weight; Heavy Slam and Heat Crash by the weight ratio, which this engine
   takes the other way round, target over user (logs: Bronzong's Heavy Slam hits light targets at 40); 80 when a weight
   is unknown (species past 493) */
static int weight_power(const Mon *a, const Mon *d, int eff_id)
{
    int wa = a->species < sim_nspecies ? sim_weight[a->species] : 0, wd = d->species < sim_nspecies ? sim_weight[d->species] : 0;
    if (eff_id == E_WEIGHT)
        return 20;              /* Low Kick and Grass Knot hit at 20 whatever the weight (logs: 220 kg Mantine, 34 kg Porygon-Z) */
    if (!wd || !wa)
        return 80;
    return wd >= 5 * wa ? 120 : wd >= 4 * wa ? 100 : wd >= 3 * wa ? 80 : wd >= 2 * wa ? 60 : 40;
}

int sim_type_eff(int type, const u8 *types, int move)
{
    int e = 4, i;
    for (i = 0; i < 3; i++) {
        int t = types[i], x;
        if (t >= T_NONE || (i && t == types[0]) || (i == 2 && t == types[1]))
            continue;
        x = sim_chart[type][t];
        if (move == M_FREEZEDRY && t == T_WATER)
            x = 8;
        if (move == M_FLYINGPRESS)
            x = x * sim_chart[T_FLYING][t] / 4;
        e = e * x / 4;
    }
    return e;
}

static int item_of(const Mon *m, u16 ability)
{
    int it = m->item;
    if (!it || it >= sim_nitems || !sim_item_handled[it] || it == I_SOULDEW || ability == A_KLUTZ)
        return 0;
    return it;
}

static int ate_type(int ab)
{
    switch (ab) {
    case A_REFRIGERATE: return T_ICE;
    case A_PIXILATE: return T_FAIRY;
    case A_AERILATE: return T_FLYING;
    case A_GALVANIZE: return T_ELECTRIC;
    case A_BURNINGSKIN: return T_FIRE;
    case A_AZURESKIN: return T_WATER;
    case A_GRASSSKIN: return T_GRASS;
    case A_DARKSKIN: return T_DARK;
    case A_DRAGONIZE: return T_DRAGON;
    }
    return -1;
}

static int is_slicing(int mv)
{
    switch (mv) {
    case M_AERIALACE: case M_AIRCUTTER: case M_AIRSLASH: case M_CROSSPOISON: case M_CUT: case M_FURYCUTTER:
    case M_LEAFBLADE: case M_NIGHTSLASH: case M_PSYCHOCUT: case M_RAZORLEAF: case M_RAZORSHELL: case M_SACREDSWORD:
    case M_SECRETSWORD: case M_SLASH: case M_SOLARBLADE: case M_XSCISSOR: case M_DRAGONCLAW:
        return 1;
    }
    return 0;
}

static int is_pulse(int mv)
{
    return mv == M_AURASPHERE || mv == M_DARKPULSE || mv == M_DRAGONPULSE || mv == M_ORIGINPULSE || mv == M_WATERPULSE;
}

static int grounded(const Mon *m, const Volatile *v, int item)
{
    const u8 *t = v ? v->types : m->types;
    int ab = v ? v->ability : m->ability;
    if (item == I_IRONBALL)
        return 1;
    return !has_type(t, T_FLYING) && ab != A_LEVITATE && item != I_AIRBALLOON;
}

int sim_move_type(const Mon *a, const Volatile *va, int move, int weather, int terrain)
{
    const MoveRec *m = &sim_moves[move];
    int ab = va ? va->ability : a->ability, t = m->type, at;
    if (ab == A_MEGASOL && weather != W_RAIN && weather != WX_HEAVY_RAIN)
        weather = W_SUN;
    if (m->effect == E_WEATHER_BALL && weather && weather != WX_STRONG_WINDS)
        t = weather == W_SUN || weather == WX_HARSH_SUN ? T_FIRE : weather == W_RAIN || weather == WX_HEAVY_RAIN ? T_WATER :
            weather == W_SAND ? T_ROCK : T_ICE;
    else if (ab == A_NORMALIZE)
        t = T_NORMAL;
    else if (t == T_NORMAL && (at = ate_type(ab)) >= 0 && m->effect != E_JUDGMENT && m->effect != E_HIDDEN_POWER)
        t = at;
    else if (ab == A_LIQUIDVOICE && (m->flags & FL_SOUND))
        t = T_WATER;
    return t;
}

int sim_damage(DamageQ *q, int move)
{
    const MoveRec *m = &sim_moves[move];
    const Mon *a = q->a, *d = q->d;
    const u8 *at = q->va ? q->va->types : a->types, *dt = q->vd ? q->vd->types : d->types;
    u8 at3[3] = { a->types[0], a->types[1], T_NONE }, dt3[3] = { d->types[0], d->types[1], T_NONE };
    int aab = q->va ? q->va->ability : a->ability;
    int dab = q->d_active ? (q->vd ? q->vd->ability : d->ability) : 0;
    int ait = item_of(a, aab), dit = q->d_active ? item_of(d, dab) : 0;
    int weather = q->weather, terrain = q->terrain, cls = m->cls, eff_id = m->effect;
    int mold = aab == A_MOLDBREAKER || aab == A_TERAVOLT || aab == A_TURBOBLAZE || aab == A_MYCELIUMMGHT;
    int mtype, eff, bp, raw2 = 0, power_q = 4096, atk_q = 4096, def_q = 4096, final_q = 4096, stab_q = 0;
    int a_stat, a_stage, d_stat, d_stage, base, v, crit = q->crit, contact = (m->flags & FL_CONTACT) != 0;
    int ahp = a->hp, dhp = d->hp, i, burned;
    const s8 *as = q->va ? q->va->stage : 0, *ds = q->vd ? q->vd->stage : 0;
    if (!q->va)
        at = at3;
    if (!q->vd)
        dt = dt3;
    q->type_eff = 4;
    q->fixed = 0;
    if (!cls)
        return 0;
    if (mold && dab)
        dab = 0;
    if (aab == A_CLOUDNINE || aab == A_AIRLOCK || dab == A_CLOUDNINE || dab == A_AIRLOCK)
        weather = W_NONE;
    if (aab == A_MEGASOL && weather != W_RAIN && weather != WX_HEAVY_RAIN)
        weather = W_SUN;
    mtype = sim_move_type(a, q->va, move, weather, terrain);
    if (m->effect == E_WEATHER_BALL && weather && weather != WX_STRONG_WINDS)
        raw2 = 1;

    if (q->sim && fixed_damage(a, d, eff_id, 1) >= 0) {
        q->fixed = 1;
        return fixed_damage(a, d, eff_id, 1);
    }
    eff = sim_type_eff(mtype, dt, move);
    if (!eff && has_type(dt, T_GHOST) && (mtype == T_NORMAL || mtype == T_FIGHTING) && (aab == A_SCRAPPY || aab == A_MINDSEYE)) {
        u8 t2[3];
        for (i = 0; i < 3; i++)
            t2[i] = dt[i] == T_GHOST ? T_NONE : dt[i];
        eff = sim_type_eff(mtype, t2, move);
    }
    if (mtype == T_GROUND && dit == I_IRONBALL && !eff)
        eff = 4;
    if (weather == WX_STRONG_WINDS && has_type(dt, T_FLYING) && sim_chart[mtype][T_FLYING] == 8)
        eff /= 2;                       /* the strong winds take away the super effectiveness on Flying */
    q->type_eff = eff;
    if (!eff)
        return q->sim ? 1 : 0;
    if (q->sim && mtype == T_GROUND && dab == A_LEVITATE && dit != I_IRONBALL)
        return 1;                       /* the simulation sees Levitate (bench records), not Air Balloon (measured) */
    if (!q->sim) {
        if (mtype == T_GROUND && dit == I_AIRBALLOON)
            return q->type_eff = 0;
        switch (dab) {
        case A_LEVITATE: if (mtype == T_GROUND && dit != I_IRONBALL) return q->type_eff = 0; break;
        case A_EARTHEATER: if (mtype == T_GROUND) return q->type_eff = 0; break;
        case A_FLASHFIRE: case A_WELLBAKEDBDY: case A_BLAZINGAWE: if (mtype == T_FIRE) return q->type_eff = 0; break;
        case A_WATERABSORB: case A_STORMDRAIN: case A_DRYSKIN: if (mtype == T_WATER) return q->type_eff = 0; break;
        case A_VOLTABSORB: case A_LIGHTNINGROD: case A_MOTORDRIVE: if (mtype == T_ELECTRIC) return q->type_eff = 0; break;
        case A_SAPSIPPER: if (mtype == T_GRASS) return q->type_eff = 0; break;
        case A_WONDERGUARD: if (eff <= 4) return q->type_eff = 0; break;
        case A_SOUNDPROOF: if (m->flags & FL_SOUND) return q->type_eff = 0; break;
        case A_BULLETPROOF: if (m->flags & FL_BALL) return q->type_eff = 0; break;
        }
        if ((weather == WX_HARSH_SUN && mtype == T_WATER) || (weather == WX_HEAVY_RAIN && mtype == T_FIRE))
            return q->type_eff = 0;
    }

    if (fixed_damage(a, d, eff_id, 0) >= 0) {
        q->fixed = 1;
        return fixed_damage(a, d, eff_id, 0);
    }

    /* base power */
    bp = m->power;
    if (eff_id == E_FACADE && a->status && a->status != ST_SLP && a->status != ST_FRZ)
        raw2 = 1;
    if (eff_id == E_BRINE && dhp * 2 <= d->maxhp)
        raw2 = 1;
    if (eff_id == E_VENOSHOCK && d->status == ST_PSN)
        raw2 = 1;
    if (eff_id == E_HEX && d->status)
        raw2 = 1;
    if (eff_id == E_ACROBATICS && !a->item)
        raw2 = 1;
    if (eff_id == E_RIVAL && !q->foe_moved)
        raw2 = 1;
    if (eff_id == E_ERUPTION)
        bp = 150 * ahp / a->maxhp > 1 ? 150 * ahp / a->maxhp : 1;
    if (move == M_WRINGOUT || move == M_CRUSHGRIP)
        bp = 120 * dhp / d->maxhp > 1 ? 120 * dhp / d->maxhp : 1;
    if (eff_id == E_REVERSAL) {
        int p = 48 * ahp / a->maxhp;
        bp = p <= 1 ? 200 : p <= 4 ? 150 : p <= 9 ? 100 : p <= 16 ? 80 : p <= 32 ? 40 : 20;
    }
    if (eff_id == E_GYRO_BALL || eff_id == E_ELECTRO_BALL) {
        int us = speed_of(a, as, ait, aab, weather), ts = speed_of(d, ds, dit, q->d_active ? dab : 0, weather), r;
        if (eff_id == E_GYRO_BALL)
            bp = 25 * ts / (us ? us : 1) + 1 > 150 ? 150 : 25 * ts / (us ? us : 1) + 1;
        else
            r = us / (ts ? ts : 1), bp = r >= 4 ? 150 : r == 3 ? 120 : r == 2 ? 80 : r == 1 ? 60 : 40;
    }
    if (eff_id == E_STORED_POWER && as) {
        bp = 20;
        for (i = 0; i < 7; i++)
            if (as[i] > 0)
                bp += 20 * as[i];
    }
    if (eff_id == E_WEIGHT || eff_id == E_HEAVY_SLAM)
        bp = weight_power(a, d, eff_id);
    if (eff_id == E_RETURN || eff_id == E_FRUSTRATION)  /* friendship 70: aibench's template Pokemon (measured) */
        bp = eff_id == E_RETURN ? 70 * 2 / 5 : (255 - 70) * 2 / 5;
    if (raw2)
        bp *= 2;
    if ((move == M_SOLARBEAM || move == M_SOLARBLADE) && weather && weather != W_SUN && weather != WX_HARSH_SUN &&
        weather != WX_STRONG_WINDS)
        power_q = chain(power_q, 2048);

    /* base power modifiers */
    {
        int secondary = (m->sick && m->sick != SICK_BIND && m->sick_per) || m->flinch ||
                        (m->quality == Q_DAMAGE_EFFECT && (m->rank_per[0] || m->rank_per[1] || m->rank_per[2])) ||
                        (m->quality == Q_DAMAGE_EFFECT_USER && (m->rank_val[0] > 0 || m->rank_val[1] > 0 || m->rank_val[2] > 0));
        if (aab == A_TECHNICIAN && bp <= 60)
            power_q = chain(power_q, q12(1.5));
        if (aab == A_IRONFIST && (m->flags & FL_PUNCH))
            power_q = chain(power_q, q12(1.3));
        if (aab == A_TOUGHCLAWS && cls == CLS_PHYSICAL)
            power_q = chain(power_q, q12(1.3));
        if (aab == A_STRONGJAW && (m->flags & FL_BITE))
            power_q = chain(power_q, q12(1.5));
        if (aab == A_MEGALAUNCHER && is_pulse(move))
            power_q = chain(power_q, q12(1.5));
        if (aab == A_SHARPNESS && is_slicing(move))
            power_q = chain(power_q, q12(1.5));
        if (aab == A_RECKLESS && (m->drain < 0 || move == M_JUMPKICK || move == M_HIJUMPKICK))
            power_q = chain(power_q, q12(1.2));
        if (aab == A_SHEERFORCE && secondary)
            power_q = chain(power_q, q12(1.3));
        if (aab == A_SANDFORCE && weather == W_SAND && (mtype == T_ROCK || mtype == T_GROUND || mtype == T_STEEL))
            power_q = chain(power_q, q12(1.3));
        if (aab == A_PUNKROCK && (m->flags & FL_SOUND))
            power_q = chain(power_q, q12(1.3));
        if (aab == A_FLAMEMANE && mtype == T_FIRE)
            power_q = chain(power_q, q12(1.5));             /* guess: "powers up Fire-type moves" */
        if (aab == A_DAMP && mtype == T_WATER)
            power_q = chain(power_q, q12(1.2));             /* guess: "ups Water"; one measured Water Gun fit x1.2 */
        if (ate_type(aab) >= 0 && mtype == ate_type(aab) && m->type == T_NORMAL)
            power_q = chain(power_q, q12(1.2));
        if (aab == A_NORMALIZE)
            power_q = chain(power_q, q12(1.2));
        if (ait && ait < sim_nitems && sim_item_boost[ait] == mtype + 1)
            power_q = chain(power_q, q12(1.2));

        if ((ait == I_ADAMANTORB && a->species == S_DIALGA && (mtype == T_STEEL || mtype == T_DRAGON)) ||
            (ait == I_LUSTROUSORB && a->species == S_PALKIA && (mtype == T_WATER || mtype == T_DRAGON)))
            power_q = chain(power_q, q12(1.2));
        if (eff_id == E_KNOCK_OFF && d->item)
            power_q = chain(power_q, q12(1.5));
        if (dab == A_DRYSKIN && mtype == T_FIRE)
            power_q = chain(power_q, q12(1.25));
        if (dab == A_HEATPROOF && mtype == T_FIRE)
            power_q = chain(power_q, 2048);
        if (dab == A_DAMP && mtype == T_FIRE)
            power_q = chain(power_q, 3413);                 /* "cuts Fire moves": 1/1.2 (logs: Fire hits at 1.4-1.7x the old x0.5) */
        if (((terrain == TERRAIN_ELECTRIC && mtype == T_ELECTRIC) || (terrain == TERRAIN_GRASSY && mtype == T_GRASS) ||
             (terrain == TERRAIN_PSYCHIC && mtype == T_PSYCHIC)) && grounded(a, q->va, ait))
            power_q = chain(power_q, q12(1.3));
        if (move == M_EXPANDFORCE && terrain == TERRAIN_PSYCHIC && grounded(a, q->va, ait))
            power_q = chain(power_q, q12(1.5));
        if (terrain == TERRAIN_MISTY && mtype == T_DRAGON && grounded(d, q->vd, dit))
            power_q = chain(power_q, 2048);
        if (terrain == TERRAIN_GRASSY && (move == M_EARTHQUAKE || move == M_BULLDOZE || move == M_MAGNITUDE) &&
            grounded(d, q->vd, dit))
            power_q = chain(power_q, 2048);
    }

    /* attack and defense */
    if (eff_id == E_BODY_PRESS) {
        a_stat = a->stat[STAT_DEF];
        a_stage = as ? as[STAT_DEF] : 0;
    } else if (eff_id == E_FOUL_PLAY) {
        a_stat = d->stat[STAT_ATK];
        a_stage = ds ? ds[STAT_ATK] : 0;
    } else {
        a_stat = a->stat[cls == CLS_PHYSICAL ? STAT_ATK : STAT_SPA];
        a_stage = as ? as[cls == CLS_PHYSICAL ? STAT_ATK : STAT_SPA] : 0;
    }
    if (cls == CLS_PHYSICAL || eff_id == E_PSYSHOCK) {
        d_stat = d->stat[STAT_DEF];
        d_stage = ds ? ds[STAT_DEF] : 0;
    } else {
        d_stat = d->stat[STAT_SPD];
        d_stage = ds ? ds[STAT_SPD] : 0;
    }
    if (dab == A_UNAWARE)
        a_stage = 0;
    if (aab == A_UNAWARE)
        d_stage = 0;
    if (crit && (dab == A_BATTLEARMOR || dab == A_SHELLARMOR))
        crit = 0;
    if (crit) {
        if (a_stage < 0) a_stage = 0;
        if (d_stage > 0) d_stage = 0;
    }
    {
        int phys = cls == CLS_PHYSICAL && eff_id != E_FOUL_PLAY ? 1 : cls == CLS_PHYSICAL;
        if (eff_id != E_BODY_PRESS) {
            if ((aab == A_HUGEPOWER || aab == A_PUREPOWER) && phys)
                atk_q = chain(atk_q, 8192);
            if (aab == A_GUTS && a->status && phys)
                atk_q = chain(atk_q, q12(1.5));
            if (aab == A_QUICKFEET && a->status && phys)
                atk_q = chain(atk_q, q12(1.5));             /* x1.5 and no burn halving, like Guts (validator: logged hits) */
            if (aab == A_WATERBUBBLE && mtype == T_WATER)
                atk_q = chain(atk_q, 8192);
            if (aab == A_HUSTLE && phys)
                atk_q = chain(atk_q, q12(1.5));
            if (aab == A_GORILLATCTCS && phys)
                atk_q = chain(atk_q, q12(1.5));
            if (aab == A_MEGACLAWS && phys)
                atk_q = chain(atk_q, q12(1.3));
            if (aab == A_TOXICBOOST && a->status == ST_PSN && phys)
                atk_q = chain(atk_q, q12(1.5));
            /* Flare Boost: no boost here, whatever its text says (logs: 9 burned special hits at 0.66-0.71 of x1.5) */
            if (aab == A_SOLARPOWER && (weather == W_SUN || weather == WX_HARSH_SUN) && !phys)
                atk_q = chain(atk_q, q12(1.5));
            if (aab == A_DEFEATIST && ahp * 2 <= a->maxhp)
                atk_q = chain(atk_q, 2048);
            if (((aab == A_BLAZE && mtype == T_FIRE) || (aab == A_TORRENT && mtype == T_WATER) ||
                 (aab == A_OVERGROW && mtype == T_GRASS)) && ahp * 3 <= a->maxhp)
                atk_q = chain(atk_q, q12(1.5));
            if ((aab == A_STEELWORKER && mtype == T_STEEL) || (aab == A_TRANSISTOR && mtype == T_ELECTRIC) ||
                (aab == A_DRAGONSMAW && mtype == T_DRAGON) || (aab == A_ROCKYPAYLOAD && mtype == T_ROCK))
                atk_q = chain(atk_q, q12(1.5));
            if (aab == A_FLASHFIRE && q->va && q->va->flash_fire && mtype == T_FIRE)
                atk_q = chain(atk_q, q12(1.5));
            if (ait == I_CHOICEBAND && phys)
                atk_q = chain(atk_q, q12(1.5));
            if (ait == I_CHOICESPECS && !phys)
                atk_q = chain(atk_q, q12(1.5));
            if (ait == I_LIGHTBALL && a->species == S_PIKACHU)
                atk_q = chain(atk_q, 8192);
            if (ait == I_THICKCLUB && (a->species == S_CUBONE || a->species == S_MAROWAK) && phys)
                atk_q = chain(atk_q, 8192);
        }
        if (dab == A_THICKFAT && (mtype == T_FIRE || mtype == T_ICE))
            atk_q = chain(atk_q, 2048);
        if (dab == A_WATERBUBBLE && mtype == T_FIRE)
            atk_q = chain(atk_q, 2048);
        if (dab == A_PURIFYNGSALT && mtype == T_GHOST)
            atk_q = chain(atk_q, 2048);
        if (cls == CLS_PHYSICAL || eff_id == E_PSYSHOCK) {
            if (dit == I_EVIOLITE && sim_species[d->species].evolves)
                def_q = chain(def_q, q12(1.5));
            if (dab == A_FURCOAT)
                def_q = chain(def_q, 8192);
            if (dab == A_MARVELSCALE && d->status)
                def_q = chain(def_q, q12(1.5));
            if (dab == A_GRASSPELT && terrain == TERRAIN_GRASSY)
                def_q = chain(def_q, q12(1.5));
            if (weather == W_SNOW && has_type(dt, T_ICE))
                def_q = chain(def_q, q12(1.5));
        } else {
            if (dit == I_EVIOLITE && sim_species[d->species].evolves)
                def_q = chain(def_q, q12(1.5));
            if (dit == I_ASSAULTVEST)
                def_q = chain(def_q, q12(1.5));
            if (dab == A_MARVELSCALE && d->status)
                def_q = chain(def_q, q12(1.5));
            if (weather == W_SAND && has_type(dt, T_ROCK))
                def_q = chain(def_q, q12(1.5));
        }
    }

    /* the final modifiers */
    if (!crit && aab != A_INFILTRATOR && q->screen)
        final_q = chain(final_q, 2048);
    if ((dab == A_MULTISCALE || (q->d_active && d->ability == A_SHADOWSHIELD)) && dhp == d->maxhp && !q->hit)
        final_q = chain(final_q, 2048);
    if ((dab == A_FILTER || dab == A_SOLIDROCK || dab == A_SWARM || (q->d_active && d->ability == A_PRISMARMOR)) && eff > 4)
        final_q = chain(final_q, q12(0.75));
    if (dab == A_SHELLARMOR && cls == CLS_PHYSICAL)
        final_q = chain(final_q, q12(0.81));
    if (dab == A_ICESCALES && cls == CLS_SPECIAL)
        final_q = chain(final_q, 2048);
    if (dab == A_FLUFFY && contact)
        final_q = chain(final_q, 2048);
    if (dab == A_FLUFFY && mtype == T_FIRE)
        final_q = chain(final_q, 8192);
    if (dab == A_PUNKROCK && (m->flags & FL_SOUND))
        final_q = chain(final_q, 2048);
    if (aab == A_TINTEDLENS && eff < 4)
        final_q = chain(final_q, 8192);
    if (aab == A_NEUROFORCE && eff > 4)
        final_q = chain(final_q, q12(1.25));
    if (aab == A_SNIPER && crit)
        final_q = chain(final_q, q12(1.5));
    if ((ait == I_MUSCLEBAND && cls == CLS_PHYSICAL) || (ait == I_WISEGLASSES && cls == CLS_SPECIAL))
        final_q = chain(final_q, q12(1.1));
    if (ait == I_EXPERTBELT && eff > 4)
        final_q = chain(final_q, q12(1.2));
    if (ait == I_LIFEORB)
        final_q = chain(final_q, 5324);
    if (dit && dit < sim_nitems && sim_item_resist[dit] == mtype + 1 && (eff > 4 || dit == I_CHILANBERRY) && !q->hit &&
        aab != A_UNNERVE && aab != A_ASONE)
        final_q = chain(final_q, 2048);
    if (aab == A_ADAPTABILITY)
        stab_q = has_type(at, mtype) ? 8192 : 0;
    else if (has_type(at, mtype) || aab == A_PROTEAN || aab == A_LIBERO)
        stab_q = q12(1.5);
    burned = a->status == ST_BRN && cls == CLS_PHYSICAL && aab != A_GUTS && aab != A_QUICKFEET && eff_id != E_FACADE;

    bp = modify(bp, power_q);
    if (bp < 1) bp = 1;
    {
        int A = modify(staged(a_stat, a_stage), atk_q), D = modify(staged(d_stat, d_stage), def_q);
        if (A < 1) A = 1;
        if (D < 1) D = 1;
        base = (2 * a->level / 5 + 2) * bp * A / D / 50 + 2;
    }
    if (((weather == W_SUN || weather == WX_HARSH_SUN) && mtype == T_FIRE) ||
        ((weather == W_RAIN || weather == WX_HEAVY_RAIN) && mtype == T_WATER))
        base = modify(base, q12(1.5));
    else if (((weather == W_SUN || weather == WX_HARSH_SUN) && mtype == T_WATER) ||
             ((weather == W_RAIN || weather == WX_HEAVY_RAIN) && mtype == T_FIRE))
        base = modify(base, 2048);      /* harsh sun's Water (heavy rain's Fire) fails in battle, but the simulation halves it */
    if (crit)
        base = base * 3 / 2;
    v = base * q->roll / 100;
    if (stab_q)
        v = modify(v, stab_q);
    /* effectiveness as one multiplier (Ice on Fire/Flying stays x1: measured on the engine's numbers) */
    if (eff >= 8)
        v *= eff / 4;
    else if (eff == 2)
        v /= 2;
    else if (eff == 1)
        v /= 4;
    if (burned)
        v = modify(v, 2048);
    if (v < 1)
        v = 1;
    v = modify(v, final_q);
    return v < 1 ? 1 : v;
}
