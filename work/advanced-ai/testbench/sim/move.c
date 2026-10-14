/* A move from choice to its last effect. The generic part follows the move data the way the Gen 5 engine does
   (quality: damage, status, stat changes, recovery, drain; the condition, its chance and length; the stat changes and
   their chances; flinch, recoil, drain, charge and recharge bits). Moves whose behavior is code, not data, are cases
   on the AI's effect code or the move id. */
#include <stdio.h>
#include <string.h>
#include "sim.h"
#include "sim_ids.h"
#include "ids.h"
#include "internal.h"

#define FL_MAGICCOAT (1u << 4)
#define FL_SNATCH (1u << 5)
#define SLEEP_DRAWN 250         /* the validator's sleep: the 1-3 turn length is decided at each check */
#define SLEEP_EARLY 251         /* the same, halved by Early Bird */
#define FL_DEFROST (1u << 11)

/* effect codes (the AI's, shared by moves that work alike) */
enum { E_EXPLOSION = 7, E_DREAM_EATER = 8, E_LOCK = 27, E_ROAR = 28, E_HAZE = 25, E_LIGHT_SCREEN = 35, E_REST = 37,
       E_OHKO = 38, E_FOCUS_ENERGY = 47, E_TRANSFORM = 57, E_REFLECT = 65, E_SUBSTITUTE = 79, E_METRONOME = 83,
       E_COUNTER = 89, E_ENCORE = 90, E_PAIN_SPLIT = 91, E_LOCK_ON = 94, E_SLEEP_TALK = 97, E_DESTINY = 98,
       E_HEAL_BELL = 102, E_MEAN_LOOK = 106, E_NIGHTMARE = 107, E_CURSE = 109, E_PROTECT = 111, E_SPIKES = 112,
       E_SANDSTORM = 115, E_SAFEGUARD = 124, E_BATON_PASS = 127, E_RAPID_SPIN = 129, E_SYNTHESIS = 132, E_RAIN = 136,
       E_SUN = 137, E_BELLY_DRUM = 142, E_MIRROR_COAT = 144, E_FAKE_OUT = 158, E_STOCKPILE = 160, E_HAIL = 164,
       E_MEMENTO = 168, E_FOLLOW_ME = 172, E_TAUNT = 175, E_HELPING_HAND = 176, E_ROLE_PLAY = 178, E_WISH = 179,
       E_INGRAIN = 181, E_RECYCLE = 184, E_REVENGE = 185, E_BRICK_BREAK = 186, E_KNOCK_OFF = 188, E_ENDEAVOR = 189,
       E_TAILWIND = 225, E_METAL_BURST = 227, E_PIVOT = 228, E_PAYBACK = 230, E_ASSURANCE = 231, E_COPYCAT = 242,
       E_SUCKER_PUNCH = 248, E_TOXIC_SPIKES = 249, E_AQUA_RING = 251, E_TRICK_ROOM = 259, E_STEALTH_ROCK = 266,
       E_SHELL_SMASH = 308, E_DRAGON_TAIL = 313, E_FINAL_GAMBIT = 320, E_GRASSY_TERRAIN = 351, E_SPIKY_SHIELD = 361, E_ENDURE = 116, E_WIDE_GUARD = 278, E_QUICK_GUARD = 306, E_MAT_BLOCK = 376,
       E_FIRST_IMPRESSION = 382, E_STRENGTH_SAP = 387, E_AURORA_VEIL = 406, E_STOMPING = 408, E_SNOW = 465,
       E_CONVERSION = 30, E_MIMIC = 82, E_SPLASH = 85, E_CONVERSION2 = 93, E_SKETCH = 95, E_SPITE = 100,
       E_ODOR_SLEUTH = 113, E_TORMENT = 165, E_TRICK = 177, E_ASSIST = 180, E_MAGIC_COAT = 183, E_IMPRISON = 192,
       E_GRUDGE = 194, E_SNATCH = 195, E_MUD_SPORT = 201, E_CAMOUFLAGE = 213, E_GRAVITY = 215, E_MIRACLE_EYE = 216,
       E_ACUPRESSURE = 226, E_EMBARGO = 232, E_HEAL_BLOCK = 236, E_POWER_TRICK = 238, E_GASTRO_ACID = 239,
       E_POWER_SWAP = 243, E_GUARD_SWAP = 244, E_WORRY_SEED = 247, E_HEART_SWAP = 250, E_MAGNET_RISE = 252,
       E_GUARD_SPLIT = 279, E_POWER_SPLIT = 280, E_WONDER_ROOM = 281, E_TELEKINESIS = 285, E_MAGIC_ROOM = 286,
       E_SOAK = 294, E_SIMPLE_BEAM = 298, E_ENTRAINMENT = 299, E_QUASH = 315, E_REFLECT_TYPE = 318,
       E_TRICK_OR_TREAT = 342, E_MISTY_TERRAIN = 352, E_ELECTRIC_TERRAIN = 368, E_FORESTS_CURSE = 375, E_POWDER = 377,
       E_WATER_SPORT = 210, E_STICKY_WEB = 340, E_DISABLE = 86,
       E_WEIGHT = 196, E_HEAVY_SLAM = 291, E_RETURN = 121, E_FRUSTRATION = 123, E_MAGNITUDE = 126 };

static int is_protect(int e) { return e == E_PROTECT || e == E_SPIKY_SHIELD || e == 355 || e == 383 || e == 441 || e == 451; }

/* the moves Gravity stops */
static int gravity_blocked(int mv)
{
    return mv == M_FLY || mv == M_BOUNCE || mv == M_SKYDROP || mv == M_SPLASH || mv == M_MAGNETRISE ||
           mv == M_TELEKINESIS || mv == M_HIJUMPKICK || mv == M_JUMPKICK || mv == M_FLYINGPRESS;
}

/* the moves Assist cannot call */
static int no_assist(int mv)
{
    const MoveRec *m = &sim_moves[mv];
    return !mv || mv == M_ASSIST || mv == M_COPYCAT || mv == M_METRONOME || mv == M_MIMIC || mv == M_SKETCH ||
           mv == M_SLEEPTALK || mv == M_TRANSFORM || mv == M_STRUGGLE || mv == M_CHATTER || mv == M_COUNTER ||
           mv == M_MIRRORCOAT || mv == M_FOCUSPUNCH || mv == M_THIEF || mv == M_COVET || mv == M_TRICK ||
           mv == M_SWITCHEROO || mv == M_SNATCH || mv == M_FOLLOWME || mv == M_RAGEPOWDER || mv == M_HELPINGHAND ||
           mv == M_DESTINYBOND || mv == M_FEINT || mv == M_BESTOW || mv == M_CIRCLETHROW || mv == M_DRAGONTAIL ||
           mv == M_NATUREPOWER || mv == M_MEFIRST || mv == M_BELCH || mv == M_ROAR || mv == M_WHIRLWIND ||
           mv == M_MIRRORMOVE || m->effect == E_PROTECT || m->effect == E_SPIKY_SHIELD ||
           m->effect == 355 || m->effect == 383 || m->effect == 441 || m->effect == 451 || m->effect == E_ENDURE;
}

/* the move Assist calls: one of the n candidates, uniform */
const u16 *g_call_cand;
int g_called;
static int call_pick(Battle *b, int s, const u16 *cand, int n)
{
    double p[24];
    int k;
    if (!b->oracle)
        return (int)sim_rand(b, n);
    for (k = 0; k < n; k++)
        p[k] = 1.0 / n;
    g_call_cand = cand;
    k = b->oracle->pick(b->oracle, b, K_CALL, s, n, p);
    g_call_cand = 0;
    return k;
}

static int to_foe(const MoveRec *m)
{
    return m->target != TG_USER && m->target != TG_USER_OR_ALLY && m->target != TG_USER_SIDE_MONS &&
           m->target != TG_FIELD && m->target != TG_USER_SIDE && m->target != TG_ALL && m->target != TG_ENEMY_SIDE &&
           !(m->target == TG_CURSE);
}

/* ---------------------------------------------------------------- statuses */

int inflict(Battle *b, int s, int st, int bad, int by)
{
    Mon *m = &b->party[s][0];
    Volatile *v = &b->v[s];
    int ab = v->ability, w = sim_weather(b);
    if (!sim_alive(m) || m->status || !st)
        return 0;
    if (by >= 0 && by != s && b->side[s].safeguard)
        return 0;
    if (b->terrain == TERRAIN_MISTY && grounded(b, s))
        return 0;
    if (ab == A_COMATOSE || ab == A_PURIFYNGSALT || (ab == A_LEAFGUARD && is_sun(w)))
        return 0;
    if (by >= 0 && by != s && ab == A_NINJABOND)
        return 0;
    switch (st) {
    case ST_PAR:
        if (has_type_v(v, T_ELECTRIC) || ab == A_LIMBER)
            return 0;
        break;
    case ST_PSN:
        if (((has_type_v(v, T_POISON) || has_type_v(v, T_STEEL)) && !(by >= 0 && b->v[by].ability == A_CORROSION)) ||
            ab == A_IMMUNITY)
            return 0;
        break;
    case ST_BRN:
        if (has_type_v(v, T_FIRE) || ab == A_WATERVEIL || ab == A_WATERBUBBLE || ab == A_THERMALEXCHG)
            return 0;
        break;
    case ST_FRZ:
        if (has_type_v(v, T_ICE) || ab == A_MAGMAARMOR || is_sun(w))
            return 0;
        break;
    case ST_SLP:
        if (ab == A_INSOMNIA || ab == A_VITALSPIRIT || (b->terrain == TERRAIN_ELECTRIC && grounded(b, s)))
            return 0;
        break;
    }
    m->status = st;
    m->toxic = st == ST_PSN && bad;
    m->tox_n = 0;
    note(b, N_STATUS, s, st == ST_PSN && bad ? 6 : st, 0);
    if (st == ST_SLP) {
        if (b->oracle)
            m->sleep = ab == A_EARLYBIRD ? SLEEP_EARLY : SLEEP_DRAWN;   /* drawn at each check (wake_chance) */
        else
            m->sleep = 1 + sim_rand(b, 3);      /* sleeps through 1-3 turns, acts on the turn it wakes (measured) */
        if (ab == A_EARLYBIRD && !b->oracle)
            m->sleep /= 2;
        m->slept = 0;
    }
    sim_log(b, "  %s got status %d%s", mon_name(m), st, m->toxic ? " (bad)" : "");
    if (ab == A_SYNCHRONIZE && by >= 0 && by != s && st != ST_SLP && st != ST_FRZ)
        inflict(b, by, st, bad, s);
    status_berry(b, s);
    return 1;
}

static int confuse(Battle *b, int s, int by)
{
    Volatile *v = &b->v[s];
    if (!sim_alive(&b->party[s][0]) || v->confused || v->ability == A_OWNTEMPO)
        return 0;
    if ((by >= 0 && by != s && b->side[s].safeguard) || (b->terrain == TERRAIN_MISTY && grounded(b, s)))
        return 0;
    if (b->oracle)
        v->confused = 1, v->conf_n = 0;         /* its end is decided at each move attempt (conf_end_chance) */
    else
        v->confused = 2 + sim_rand(b, 4);      /* the move data's 2-5 turns */
    note(b, N_CONFUSE, s, 0, 0);
    status_berry(b, s);
    return 1;
}

/* a condition (WP_SICK numbering) from move m, used by side by on side s */
static int apply_sick(Battle *b, int s, const MoveRec *m, int by)
{
    Volatile *v = &b->v[s];
    switch (m->sick) {
    case SICK_PAR: return inflict(b, s, ST_PAR, 0, by);
    case SICK_SLP: return inflict(b, s, ST_SLP, 0, by);
    case SICK_FRZ: return inflict(b, s, ST_FRZ, 0, by);
    case SICK_BRN: return inflict(b, s, ST_BRN, 0, by);
    case SICK_PSN: return inflict(b, s, ST_PSN, m->sick_tmin >= 15, by);
    case SICK_CONFUSION: return confuse(b, s, by);
    case SICK_BIND:
        if (v->bind || !sim_alive(&b->party[s][0]))
            return 0;
        v->bind = item_of(b, by) == I_GRIPCLAW ? 7 : 4 + sim_rand(b, 2);
        v->bind_by = by;
        return 1;
    case SICK_LEECH_SEED:
        if (v->seeded || has_type_v(v, T_GRASS))
            return 0;
        return v->seeded = 1;
    case SICK_YAWN:
        if (v->yawn || b->party[s][0].status)
            return 0;
        v->yawn = 2;
        return 1;
    case SICK_NIGHTMARE:
        if (b->party[s][0].status != ST_SLP)
            return 0;
        return v->nightmare = 1;
    case SICK_INGRAIN:          /* the move data's Ingrain and Aqua Ring are conditions on the user */
        if (v->ingrain)
            return 0;
        v->ingrain = v->trapped = 1;
        return 1;
    case SICK_AQUA_RING:
        return v->aqua ? 0 : (v->aqua = 1);
    case SICK_PERISH: {
        int k, any = 0;
        for (k = 0; k < 2; k++)
            if (sim_alive(&b->party[k][0]) && !b->v[k].perish && b->v[k].ability != A_SOUNDPROOF)
                b->v[k].perish = 4, any = 1;
        return any;
    }
    }
    return 0;
}

/* the move data's stat changes on side s (rank type 9: all five) */
/* would side s's Pokemon take the change (the validator grades a chance only when its outcome would show) */
static int rank_takes(const Battle *b, int s, int t, int val, int by_foe)
{
    Battle c = *b;
    int j, any = 0;
    c.oracle = 0;
    if (t == 9) {
        for (j = 0; j < 5; j++)
            any |= boost(&c, s, j, val, by_foe) != 0;
        return any;
    }
    return t <= 7 && boost(&c, s, t - 1, val, by_foe) != 0;
}

static void apply_ranks(Battle *b, int s, const MoveRec *m, int by_foe, int chance_roll, int serene)
{
    int k;
    for (k = 0; k < 3; k++) {
        int t = m->rank_type[k], per = m->rank_per[k];
        if (!t || !m->rank_val[k])
            continue;
        if (chance_roll && per && per < 100) {
            if (b->oracle && !rank_takes(b, s, t, m->rank_val[k], by_foe))
                continue;
            if (b->oracle)
                b->oracle->arg = t | (m->rank_val[k] < 0) << 4;
            if (!yes(b, K_RANK, s, serene ? 2 * per : per))
                continue;
        }
        if (t == 9) {
            int j;
            for (j = 0; j < 5; j++)
                boost(b, s, j, m->rank_val[k], by_foe);
        } else if (t <= 7)
            boost(b, s, t - 1, m->rank_val[k], by_foe);
    }
}

/* ---------------------------------------------------------------- accuracy and crits */

static int reaches(int mv, int semi)
{
    if (semi & SEMI_FLY)
        return mv == M_THUNDER || mv == M_HURRICANE || mv == M_GUST || mv == M_TWISTER || mv == M_SKYUPPERCUT ||
               mv == M_SMACKDOWN;
    if (semi & SEMI_DIG)
        return mv == M_EARTHQUAKE || mv == M_MAGNITUDE || mv == M_FISSURE;
    if (semi & SEMI_DIVE)
        return mv == M_SURF || mv == M_WHIRLPOOL;
    return 0;
}

static int lands(Battle *b, int s, int t, int mv)
{
    const MoveRec *m = &sim_moves[mv];
    const Mon *u = &b->party[s][0];
    int ab = b->v[s].ability, dab = b->v[t].ability, acc = m->acc, st, it = item_of(b, s), dit = item_of(b, t);
    int w = sim_weather(b);
    if (ab == A_NOGUARD || dab == A_NOGUARD)
        return 1;
    if (m->quality == Q_OHKO) {
        if (b->party[t][0].level > u->level || (mv == M_SHEERCOLD && has_type_v(&b->v[t], T_ICE)))
            return 0;
        if (b->oracle)
            return yes(b, K_OHKO, s, 30 + u->level - b->party[t][0].level);
        return (int)sim_rand(b, 100) < 30 + u->level - b->party[t][0].level;
    }
    if ((mv == M_THUNDER || mv == M_HURRICANE) && is_rain(w))
        return 1;
    if (mv == M_BLIZZARD && w == W_SNOW)
        return 1;
    if (mv == M_TOXIC && has_type_v(&b->v[s], T_POISON))
        return 1;
    if (acc >= 101 || b->v[t].tele)
        return 1;
    if (b->gravity)
        acc = acc * 5 / 3;
    if ((mv == M_THUNDER || mv == M_HURRICANE) && is_sun(w))
        acc = 50;
    st = b->v[s].stage[STAT_ACC] - (ab == A_UNAWARE || ab == A_KEENEYE ? 0 : b->v[t].stage[STAT_EVA]);
    st = st > 6 ? 6 : st < -6 ? -6 : st;
    acc = st >= 0 ? acc * (3 + st) / 3 : acc * 3 / (3 - st);       /* 3/(3+n) (measured) */
    if (ab == A_COMPOUNDEYES)
        acc = acc * 13 / 10;
    if (ab == A_CONCENTRATE || ab == A_MYSTICDANCE)
        acc = acc * 13 / 10;                  /* "somewhat raises accuracy": x1.3 (logs: likeliest over 210 moves; 1.2 too low) */
    if (ab == A_HUSTLE && m->cls == CLS_PHYSICAL)
        acc = acc * 8 / 10;
    if (it == I_WIDELENS)
        acc = acc * 11 / 10;
    if (it == I_ZOOMLENS && b->v[t].moved)
        acc = acc * 12 / 10;
    if (dit == I_BRIGHTPOWDER || dit == I_LAXINCENSE)
        acc = acc * 9 / 10;                   /* BrightPowder measured at the official 10% */
    if ((dab == A_SANDVEIL && w == W_SAND) || (dab == A_SNOWCLOAK && w == W_SNOW))
        acc = acc * 8 / 10;
    if (b->oracle)
        return yes(b, K_ACC, s, acc);
    {
        int x;
        g_tracked++;
        x = (int)sim_rand(b, 100) < acc;
        g_tracked--;
        luck_roll(s, LUCK_ACC, acc / 100.0, x, x);
        if (!x)
            OBS(obs_miss(b, s, m->acc));
        return x;
    }
}

static int crit_roll(Battle *b, int s, int t, const MoveRec *m)
{
    int st = m->crit + 2 * b->v[s].focus, it = item_of(b, s), dab = b->v[t].ability;
    if (dab == A_BATTLEARMOR || dab == A_SHELLARMOR)
        return 0;
    if (b->v[s].ability == A_MERCILESS && b->party[t][0].status == ST_PSN)
        return OBS(obs_crit(b, s, 3)), 1;
    st += b->v[s].ability == A_SUPERLUCK || b->v[s].ability == A_SNIPER;     /* Sniper too here (logs: 18 of 35 at stage 2) */
    st += it == I_SCOPELENS || it == I_RAZORCLAW;
    st += 2 * (it == I_LEEK && (b->party[s][0].species == S_FARFETCHD));
    if (st >= 3)
        return OBS(obs_crit(b, s, 3)), 1;     /* stage 3 always crits (seen in logs) */
    if (b->oracle)
        return b->oracle->yes(b->oracle, b, K_CRIT, s, st == 2 ? 0.5 : st == 1 ? 1 / 8.0 : 1 / 24.0);
    {
        int x;
        g_tracked++;
        x = st == 2 ? chance(b, 50) : st == 1 ? sim_rand(b, 8) == 0 : sim_rand(b, 24) == 0;
        g_tracked--;
        luck_roll(s, LUCK_CRIT, st == 2 ? 0.5 : st == 1 ? 1 / 8.0 : 1 / 24.0, x, x);
        if (x)
            OBS(obs_crit(b, s, st));
        return x;
    }
}

/* ---------------------------------------------------------------- damage moves */

static int screen_on(const Battle *b, int t, int cls)
{
    const Side *sd = &b->side[t];
    return sd->veil || (cls == CLS_PHYSICAL && sd->reflect) || (cls == CLS_SPECIAL && sd->screen);
}

static int hit_count(Battle *b, int s, const MoveRec *m)
{
    int lo = m->hits_min, hi = m->hits_max, r;
    if (hi <= 1)
        return b->v[s].ability == A_PARENTALBOND ? 2 : 1;
    if (lo == hi || b->v[s].ability == A_SKILLLINK)
        return hi;
    if (b->oracle) {            /* the same distributions, outcome k = k + lo hits */
        double p[10] = { 0 };
        int k, n = hi - lo + 1;
        if (item_of(b, s) == I_LOADEDDICE && hi >= 4)
            for (k = 4 - lo; k < n; k++)
                p[k] = 1.0 / (hi - 3);
        else if (lo == 2 && hi == 5)
            p[0] = p[1] = 0.35, p[2] = p[3] = 0.15;
        else
            for (k = 0; k < n; k++)
                p[k] = 1.0 / n;
        return lo + b->oracle->pick(b->oracle, b, K_HITS, s, n, p);
    }
    if (item_of(b, s) == I_LOADEDDICE && hi >= 4)
        return 4 + sim_rand(b, hi - 3);
    if (lo == 2 && hi == 5) {
        r = sim_rand(b, 100);
        return r < 35 ? 2 : r < 70 ? 3 : r < 85 ? 4 : 5;
    }
    return lo + sim_rand(b, hi - lo + 1);
}

/* would side s's Pokemon take the status / the move's condition (the validator grades a chance only when its outcome
   would show) */
static int status_takes(const Battle *b, int s, int st, int by)
{
    Battle c = *b;
    c.oracle = 0;
    return inflict(&c, s, st, 0, by);
}

static int sick_takes(const Battle *b, int t, const MoveRec *m, int by)
{
    Battle c = *b;
    c.oracle = 0;
    return apply_sick(&c, t, m, by);
}

/* one hit's damage at a roll, with the move's own multipliers (the validator grades all 16 rolls) */
static int roll_damage(DamageQ *q, int mv, int roll, int pw, int mult, int fixed, int pb, int i)
{
    int dmg;
    q->roll = roll;
    dmg = sim_damage(q, mv);
    if (pw && !q->fixed && sim_moves[mv].power)     /* the override power: sim_damage reads the data, so scale */
        dmg = dmg * pw / sim_moves[mv].power;
    if (fixed > 0)
        return fixed;
    if (fixed < 0)
        dmg *= mult;
    if (pb)
        dmg /= 4;
    if ((mv == M_TRIPLEKICK || mv == M_TRIPLEAXEL) && i)
        dmg *= i + 1;
    return dmg < 1 ? 1 : dmg;
}

/* the end of the turn a pending Future Sight or Doom Desire lands on side t: its user's stats as they are then
   (its stages only while it is on the field), the Pokemon on the field now; the roll is sampled, also under the
   validator, which does not match this hit to the log */
void future_lands(Battle *b, int t)
{
    int s = t ^ 1, i, mv = b->future_by[t] & 0x80 ? M_DOOMDESIRE : M_FUTURESIGHT, dmg;
    Mon *d = &b->party[t][0];
    DamageQ q;
    if (!b->future[t] || --b->future[t])
        return;
    if (!sim_alive(d))
        return;
    for (i = 0; i < b->n[s] && b->party[s][i].id != (b->future_by[t] & 0x7F); i++)
        ;
    if (i == b->n[s])
        return;
    memset(&q, 0, sizeof q);
    q.a = &b->party[s][i], q.va = i ? 0 : &b->v[s], q.a_active = !i;
    q.d = d, q.vd = &b->v[t], q.d_active = 1;
    q.weather = sim_weather(b), q.terrain = b->terrain;
    q.screen = screen_on(b, t, sim_moves[mv].cls);
    dmg = roll_damage(&q, mv, 85 + (int)sim_rand(b, 16), 0, 1, -1, 0, 0);
    if (!q.type_eff) {
        note(b, N_NOEFFECT, t, 0, 0);
        return;
    }
    if (dmg > d->hp)
        dmg = d->hp;
    d->hp -= dmg;
    b->last_hit[t] = dmg;
    sim_log(b, "  %s took the %s attack: %d", mon_name(d), sim_move_name[mv], dmg);
    if (!sim_alive(d))
        fainted(b, t);
}

/* side t's ability takes the move in (absorb, immunity with a bonus) */
static void absorb(Battle *b, int t, int mtype)
{
    int ab = b->v[t].ability;
    Mon *d = &b->party[t][0];
    if ((ab == A_VOLTABSORB && mtype == T_ELECTRIC) || (ab == A_WATERABSORB && mtype == T_WATER) ||
        (ab == A_DRYSKIN && mtype == T_WATER) || (ab == A_EARTHEATER && mtype == T_GROUND))
        heal(b, t, d->maxhp / 4);
    if ((ab == A_LIGHTNINGROD && mtype == T_ELECTRIC) || (ab == A_STORMDRAIN && mtype == T_WATER) ||
        (ab == A_BLAZINGAWE && mtype == T_FIRE))
        boost(b, t, STAT_SPA, 1, 0);
    if (ab == A_MOTORDRIVE && mtype == T_ELECTRIC)
        boost(b, t, STAT_SPE, 1, 0);
    if (ab == A_SAPSIPPER && mtype == T_GRASS)
        boost(b, t, STAT_ATK, 1, 0);
    if (ab == A_FLASHFIRE && mtype == T_FIRE)
        b->v[t].flash_fire = 1;
    if (ab == A_WELLBAKEDBDY && mtype == T_FIRE)
        boost(b, t, STAT_DEF, 2, 0);
}

/* the fixed damage of the counter moves and their like (0: it fails), -1 when the move is not one */
static int fixed_special(Battle *b, int s, int t, int mv)
{
    const MoveRec *m = &sim_moves[mv];
    const Volatile *vu = &b->v[s];
    switch (m->effect) {
    case E_COUNTER:
        return vu->hit_by_move && vu->hit_cls == CLS_PHYSICAL ? 2 * vu->hit_last : 0;
    case E_MIRROR_COAT:
        return vu->hit_by_move && vu->hit_cls == CLS_SPECIAL ? 2 * vu->hit_last : 0;
    case E_METAL_BURST:
        return vu->hit_by_move ? vu->hit_last * 3 / 2 : 0;
    case E_ENDEAVOR:
        return b->party[t][0].hp > b->party[s][0].hp ? b->party[t][0].hp - b->party[s][0].hp : 0;
    case E_FINAL_GAMBIT:
        return b->party[s][0].hp;
    }
    return -1;
}

static int base_power_override(int e)
{
    switch (e) {
    case E_MAGNITUDE: return 71;
    }
    return 0;
}

/* which of side t's Pokemon on the bench Roar or Dragon Tail drags in, counted among those able to fight */
static int phaze_pick(Battle *b, int t)
{
    int n = bench_count(b, t), k;
    double p[6];
    if (!b->oracle)
        return (int)sim_rand(b, (u32)n);
    for (k = 0; k < n; k++)
        p[k] = 1.0 / n;
    return b->oracle->pick(b->oracle, b, K_PHAZE, t, n, p);
}

/* damage on side t from side s's move; returns the total dealt (-1: it did not affect the target) */
static int shares_type(const Volatile *a, const Volatile *d)
{
    int i, j;
    for (i = 0; i < 3; i++)
        for (j = 0; j < 3; j++)
            if (a->types[i] != T_NONE && a->types[i] == d->types[j])
                return 1;
    return 0;
}

/* what the field changes in a real hit's target (the AI's engine simulation does not see these): Odor Sleuth and Miracle
   Eye take away a Ghost or Dark immunity, Gravity a Flying type and Levitate against Ground, Wonder Room swaps the
   defenses */
static void field_view(const Battle *b, int s, int t, int mv, Volatile *tv, Mon *dw)
{
    int ty = sim_move_type(&b->party[s][0], &b->v[s], mv, sim_weather(b), b->terrain), k, drop = T_NONE;
    if (tv->identified == 1 && (ty == T_NORMAL || ty == T_FIGHTING))
        drop = T_GHOST;
    if (tv->identified == 2 && ty == T_PSYCHIC)
        drop = T_DARK;
    if (b->gravity && ty == T_GROUND) {
        drop = T_FLYING;
        if (tv->ability == A_LEVITATE)
            tv->ability = 0;
    }
    if (drop != T_NONE)
        for (k = 0; k < 3; k++)
            if (tv->types[k] == drop)
                tv->types[k] = T_NONE;      /* no type left: neutral, as Struggle sees it */
    if (b->wonder_room) {
        u16 x = dw->stat[STAT_DEF];
        dw->stat[STAT_DEF] = dw->stat[STAT_SPD];
        dw->stat[STAT_SPD] = x;
    }
}

static int damage_move(Battle *b, int s, int t, int mv, const Policy *const pol[2])
{
    const MoveRec *m0 = &sim_moves[mv];
    MoveRec mr = *m0;
    const MoveRec *m = &mr;
    Mon *u = &b->party[s][0], *d = &b->party[t][0];
    Volatile *vu = &b->v[s], *vd = &b->v[t];
    int ab = vu->ability, dab = vd->ability, w = sim_weather(b), n, i, total = 0, fixed, eff = 4, last = 0;
    int contact = (m->flags & FL_CONTACT) != 0, subbed = 0, mold = ab == A_MOLDBREAKER || ab == A_TERAVOLT || ab == A_TURBOBLAZE;
    int secondary, sheer, serene = ab == A_SERENEGRACE, mult = 1, pw = base_power_override(m->effect);
    int mtype0 = sim_move_type(u, vu, mv, w, b->terrain);
    if (pw)
        mr.power = pw;
    if (mold)
        dab = 0;
    if ((m->effect == E_REVENGE && vu->hit_by_move) || (m->effect == E_PAYBACK && vd->moved) ||
        (m->effect == E_ASSURANCE && vd->hit_by_move) || (m->effect == E_STOMPING && vu->failed))
        mult = 2;
    if (m->effect == E_BRICK_BREAK)
        b->side[t].reflect = b->side[t].screen = b->side[t].veil = 0;
    if (m->effect == E_DREAM_EATER && d->status != ST_SLP)
        return note(b, N_FAIL, s, mv, 0), -1;
    if (mv == M_FLING && (!u->item || b->magic_room || vu->embargo || vu->ability == A_KLUTZ))
        return note(b, N_FAIL, s, mv, 0), -1;       /* Fling with no usable item fails (logs) */
    if (mv == M_SYNCHRONOISE && !shares_type(vu, vd))
        return note(b, N_NOEFFECT, t, 0, 0), -1;
    if (mv == M_FUTURESIGHT || mv == M_DOOMDESIRE) {
        if (b->future[t])
            return note(b, N_FAIL, s, mv, 0), -1;
        b->future[t] = 3;
        b->future_by[t] = u->id | (mv == M_DOOMDESIRE ? 0x80 : 0);
        return 0;
    }
    fixed = fixed_special(b, s, t, mv);
    if (fixed == 0)
        return note(b, N_FAIL, s, mv, 0), -1;
    n = fixed > 0 ? 1 : hit_count(b, s, m);
    if (mtype0 == T_GROUND && (vd->magnet || vd->tele) && !b->gravity && item_of(b, t) != I_IRONBALL)
        return note(b, N_NOEFFECT, t, 0, 0), -1;    /* Magnet Rise, Telekinesis */
    if ((mtype0 == T_ELECTRIC && b->mud_sport) || (mtype0 == T_FIRE && b->water_sport))
        pw = (pw ? pw : m->power) / 3;
    for (i = 0; i < n && sim_alive(d); i++) {
        DamageQ q;
        Volatile tv = *vd;
        Mon dw = *d;
        int dmg, crit = fixed > 0 ? 0 : crit_roll(b, s, t, m);
        memset(&q, 0, sizeof q);
        if (mv == M_STRUGGLE)
            tv.types[0] = tv.types[1] = tv.types[2] = T_NONE;
        if (mold)
            tv.ability = 0;
        field_view(b, s, t, mv, &tv, &dw);
        q.a = u, q.d = b->wonder_room ? &dw : d, q.va = vu, q.vd = &tv;
        q.a_active = q.d_active = 1;
        q.weather = w, q.terrain = b->terrain;
        q.screen = screen_on(b, t, m->cls);
        q.crit = crit, q.hit = i;
        q.foe_moved = vd->moved && vd->acted;       /* Bolt Beak: a target that switched in this turn has not moved */
        {
            int pb = n == 2 && i == 1 && ab == A_PARENTALBOND && m->hits_max <= 1;
            int ri = 15;
            if (!b->oracle) {
                g_tracked++;
                ri = (int)sim_rand(b, 16);
                g_tracked--;
                luck_roll(s, LUCK_DMG, 7.5, ri, ri >= 8);
                if (g_fsr && !i && !g_fsr->s[s].roll1)
                    g_fsr->s[s].roll1 = ri + 1;
            }
            dmg = roll_damage(&q, mv, 85 + ri, pw, mult, fixed, pb, i);
            eff = q.type_eff;
            if (fixed > 0 && !sim_type_eff(m->type, vd->types, mv))
                return note(b, N_NOEFFECT, t, 0, 0), -1;
            if (fixed <= 0 && !eff) {
                if (!sim_type_eff(sim_move_type(u, vu, mv, w, b->terrain), vd->types, mv) ||
                    (dab != A_LIGHTNINGROD && dab != A_STORMDRAIN && dab != A_MOTORDRIVE && dab != A_SAPSIPPER &&
                     dab != A_FLASHFIRE && dab != A_WELLBAKEDBDY))
                    note(b, N_NOEFFECT, t, 0, 0);       /* a redirecting ability that takes the move prints no such line (logs) */
                absorb(b, t, sim_move_type(u, vu, mv, w, b->terrain));
                return -1;
            }
            if (b->oracle) {
                int cand[16], r;
                for (r = 0; r < 16; r++)
                    cand[r] = roll_damage(&q, mv, 85 + r, pw, mult, fixed, pb, i);
                dmg = b->oracle->damage(b->oracle, b, s, i, crit, cand);
            }
        }
        if (vd->sub && !(m->flags & FL_SOUND) && ab != A_INFILTRATOR) {
            subbed = 1;
            if (dmg >= vd->sub) {
                dmg = vd->sub;
                vd->sub = 0;
            } else
                vd->sub -= dmg;
            total += dmg;
            if (g_fsr)
                g_fsr->s[s].dmg += dmg, g_fsr->s[s].crit |= crit;
            continue;
        }
        if (dmg >= d->hp && (mv == M_FALSESWIPE || mv == M_HOLDBACK))
            dmg = d->hp - 1;
        if (dmg >= d->hp) {
            int it = item_of(b, t);
            if (vd->endure)
                dmg = d->hp - 1;
            else if (d->hp == d->maxhp && (it == I_FOCUSSASH || dab == A_STURDY)) {     /* a multi-hit's first hit too (logs) */
                dmg = d->hp - 1;
                if (it == I_FOCUSSASH)
                    consume(b, t);
            } else if (it == I_FOCUSBAND && yes(b, K_FOCUSBAND, t, 10))
                dmg = d->hp - 1;
        }
        if (dmg > d->hp)
            dmg = d->hp;
        d->hp -= dmg;
        total += dmg;
        if (g_fsr)
            g_fsr->s[s].dmg += dmg, g_fsr->s[s].crit |= crit;
        last = dmg;
        vd->hit_by_move = mv;
        vd->hit_cls = m->cls;
        vd->hit_last = dmg;
        vd->hit_dmg += dmg;
        b->last_hit[t] = dmg;
        if (item_of(b, t) == I_AIRBALLOON && sim_alive(d))
            consume(b, t);                          /* a hit pops the Air Balloon (logs) */
        /* the resist berry halved the first hit; it is eaten */
        {
            int it = item_of(b, t), mt = sim_move_type(u, vu, mv, w, b->terrain);
            if (it && i == 0 && sim_item_resist[it] == mt + 1 && (eff > 4 || it == I_CHILANBERRY) && ab != A_UNNERVE)
                consume(b, t);
        }
        /* contact */
        if (contact && sim_alive(u) && ab != A_MAGICGUARD && item_of(b, s) != I_PROTECTVPADS) {
            int dit = item_of(b, t);
            if (dab == A_ROUGHSKIN || dab == A_IRONBARBS || dab == A_BATTLEARMOR || dab == A_MAGMAARMOR)
                chip(b, s, u->maxhp / 8);
            if (dit == I_ROCKYHELMET && sim_alive(u))
                chip(b, s, u->maxhp / 6);
            if (sim_alive(u) && (dab == A_STATIC || dab == A_FLAMEBODY || dab == A_POISONPOINT || dab == A_EFFECTSPORE || !b->oracle) &&
                (!b->oracle || status_takes(b, s, dab == A_STATIC ? ST_PAR : dab == A_FLAMEBODY ? ST_BRN : dab == A_POISONPOINT ? ST_PSN : ST_SLP, t)) &&
                yes(b, K_CONTACT, s, 30)) {
                if (dab == A_STATIC)
                    inflict(b, s, ST_PAR, 0, t);
                else if (dab == A_FLAMEBODY)
                    inflict(b, s, ST_BRN, 0, t);
                else if (dab == A_POISONPOINT)
                    inflict(b, s, ST_PSN, 0, t);
                else if (dab == A_EFFECTSPORE && !has_type_v(vu, T_GRASS)) {
                    int r = sim_rand(b, 3);
                    inflict(b, s, r == 0 ? ST_PSN : r == 1 ? ST_PAR : ST_SLP, 0, t);
                }
            }
            if (!sim_alive(u))
                fainted(b, s);
        }
        /* the defender's reactions */
        if (sim_alive(d)) {
            int mt = sim_move_type(u, vu, mv, w, b->terrain), dit = item_of(b, t);
            if (dit == I_WEAKPOLICY && eff > 4) {
                boost(b, t, STAT_ATK, 4, 0);        /* +4 and +4: it goes off twice (measured) */
                boost(b, t, STAT_SPA, 4, 0);
                consume(b, t);
            }
            if (dab == A_STAMINA)
                boost(b, t, STAT_DEF, 1, 0);
            if (dab == A_WEAKARMOR && m->cls == CLS_PHYSICAL) {
                boost(b, t, STAT_DEF, -1, 0);
                boost(b, t, STAT_SPE, 2, 0);
            }
            if (dab == A_RATTLED && (mt == T_DARK || mt == T_GHOST || mt == T_BUG))
                boost(b, t, STAT_SPE, 1, 0);
            if (dab == A_STEAMENGINE && (mt == T_WATER || mt == T_FIRE))
                boost(b, t, STAT_SPE, 6, 0);
            if (dab == A_THERMALEXCHG && mt == T_FIRE)
                boost(b, t, STAT_ATK, 1, 0);
            if (dab == A_JUSTIFIED && mt == T_DARK)
                boost(b, t, STAT_ATK, 1, 0);
            if (dab == A_ANGERPOINT && crit)
                boost(b, t, STAT_ATK, 12, 0);
            if ((dit == I_JABOCABERRY && m->cls == CLS_PHYSICAL) || (dit == I_ROWAPBERRY && m->cls == CLS_SPECIAL)) {
                chip(b, s, u->maxhp / 8);
                consume(b, t);
                if (!sim_alive(u))
                    fainted(b, s);
            }
            berry_check(b, t);
        }
        if (!sim_alive(d)) {
            fainted(b, t);
            if (dab == A_INNARDSOUT && sim_alive(u))
                chip(b, s, last);
            if (dab == A_AFTERMATH && contact && sim_alive(u))
                chip(b, s, u->maxhp / 4);
            if (vd->destiny && sim_alive(u)) {
                u->hp = 0;
                sim_log(b, "  Destiny Bond takes %s", mon_name(u));
            }
            if (!sim_alive(u))
                fainted(b, s);
            else if (ab == A_MOXIE)
                boost(b, s, STAT_ATK, 1, 0);
        }
    }
    sim_log(b, "  %s used %s: %d damage (x%d/4)%s", mon_name(u), sim_move_name[mv], total, eff, subbed ? " to the substitute" : "");
    if (!total)
        return total;
    /* after the hits */
    if (sim_alive(u)) {
        int it = item_of(b, s);
        if (m->drain > 0) {
            int h = (total * m->drain + 50) / 100;     /* rounded to nearest (logs: 45 damage drained 23) */
            h = h < 1 ? 1 : h;
            if (it == I_BIGROOT)
                h = (h * 5324 + 2047) / 4096;           /* x1.3 in the engine's fixed point (logs) */
            if (dab == A_LIQUIDOOZE)
                chip(b, s, h);
            else
                heal(b, s, h);
        } else if (m->drain < 0 && ab != A_ROCKHEAD && ab != A_MAGICGUARD)
            chip(b, s, (total * -m->drain + 50) / 100);     /* rounded to nearest (logs: 33% of 127 took 42, of 383 126) */
        if (mv == M_STRUGGLE)
            chip(b, s, u->maxhp / 4);
        secondary = (m->sick && m->sick_per) || m->flinch || (m->quality == Q_DAMAGE_EFFECT && m->rank_type[0]) ||
                    (m->quality == Q_DAMAGE_EFFECT_USER && m->rank_val[0] > 0);
        sheer = ab == A_SHEERFORCE && secondary;
        if (it == I_LIFEORB && ab != A_MAGICGUARD && !sheer && sim_alive(u))
            chip(b, s, u->maxhp / 10);
        if (it == I_SHELLBELL)
            heal(b, s, total / 8);
        if (!sim_alive(u))
            fainted(b, s);
    } else
        sheer = ab == A_SHEERFORCE;
    /* secondary effects on the target */
    if (sim_alive(d) && !subbed && !sheer && dab != A_SHIELDDUST && item_of(b, t) != I_COVERTCLOAK) {
        if ((m->quality == Q_DAMAGE_SICK || m->quality == Q_DAMAGE) && m->sick && m->sick_per &&
            (!b->oracle || (sick_takes(b, t, m, s) && (b->oracle->arg = m->sick, 1))) &&
            yes(b, K_SICK, t, serene ? 2 * m->sick_per : m->sick_per))
            apply_sick(b, t, m, s);
        if (m->quality == Q_DAMAGE_EFFECT)
            apply_ranks(b, t, m, 1, 1, serene);
        if (!vd->moved && dab != A_INNERFOCUS) {
            int fl = m->flinch, it = item_of(b, s);
            if (!fl && (it == I_KINGSROCK || it == I_RAZORFANG || ab == A_STENCH))
                fl = 10;
            if (fl && yes(b, K_FLINCH, t, serene ? 2 * fl : fl)) {
                vd->flinched = 1;
                if (g_fsr)
                    g_fsr->s[s].flinch_foe = 1;
            }
        }
    }
    if (m->quality == Q_DAMAGE_EFFECT_USER && sim_alive(u) && !(sheer && m->rank_val[0] > 0)) {
        apply_ranks(b, s, m, 0, 1, serene);
        white_herb(b, s);
    }
    if ((m->flags & FL_SOUND) && item_of(b, s) == I_THROATSPRAY && sim_alive(u)) {
        boost(b, s, STAT_SPA, 1, 0);            /* Throat Spray (logs) */
        consume(b, s);
    }
    /* move-specific after-effects */
    switch (m->effect) {
    case E_KNOCK_OFF:
        if (d->item && sim_alive(u)) {
            d->item = 0;
            if (vd->ability == A_UNBURDEN)
                vd->unburden = 1;
        }
        break;
    case E_RAPID_SPIN:
        if (sim_alive(u)) {
            b->side[s].spikes = b->side[s].tspikes = b->side[s].rocks = b->side[s].sticky = 0;
            vu->seeded = 0;
            vu->bind = 0;
        }
        break;
    case E_PIVOT:
        if (sim_alive(u) && bench_count(b, s) && b->winner < 0)
            replace(b, s, pol[s], 1);
        break;
    case E_DRAGON_TAIL:
        if (sim_alive(d) && sim_alive(u) && bench_count(b, t) && vd->ability != A_SUCTIONCUPS && !vd->ingrain) {
            int k, c = phaze_pick(b, t) + 1;
            for (k = 1; k < b->n[t] && c; k++)
                if (sim_alive(&b->party[t][k]) && !--c)
                    switch_in(b, t, k, 0);
        }
        break;
    }
    return total;
}

/* ---------------------------------------------------------------- status moves with their own code */

static int other_move(Battle *b, int s, int t, int mv, const Policy *const pol[2], int depth);

void transform(Battle *b, int s, int t)
{
    Mon *u = &b->party[s][0];
    const Mon *d = &b->party[t][0];
    int k;
    if (b->v[s].transformed || b->v[t].transformed || b->v[t].sub)
        return;
    b->tf_saved[s] = *u;
    u->species = d->species;
    for (k = 0; k < 5; k++)
        u->stat[k] = d->stat[k];
    for (k = 0; k < 4; k++) {
        u->moves[k] = d->moves[k];
        u->pp[k] = d->moves[k] ? 5 : 0;
    }
    memcpy(b->v[s].types, b->v[t].types, 3);
    memcpy(b->v[s].stage, b->v[t].stage, 7);
    b->v[s].ability = b->v[t].ability;
    b->v[s].transformed = 1;
    b->v[s].choice = 0;
}

static int run_move(Battle *b, int s, int mv, const Policy *const pol[2], int depth);

/* the Protect family and the guards (DS traces T4c, T4d): the streak counts on only after a move of the engine's table,
   else it restarts at 0; s > 0 holds on BattleRandom(3^min(s,6)) == 0, the guards draw nothing, Mat Block fails after
   the first turn, and a Protect moving last fails (the DS draws first) */
static int protect_move(Battle *b, int s, int t, const MoveRec *m)
{
    Volatile *vu = &b->v[s], *vd = &b->v[t];
    unsigned s0 = IS_STREAK_MOVE(vu->last_move) ? vu->protects : 0, n = 1, k;
    int guard = m->effect == E_WIDE_GUARD || m->effect == E_QUICK_GUARD || m->effect == E_MAT_BLOCK;
    for (k = 0; k < s0 && k < 6; k++)
        n *= 3;
    if (guard ? m->effect == E_MAT_BLOCK && vu->turns_out : vd->moved || !yes_1in(b, K_PROTECT, s, n)) {
        vu->protects = 0;
        return 0;
    }
    vu->protects = s0 + 1;
    if (m->effect == E_ENDURE)
        vu->endure = 1;
    else if (!guard) {
        vu->protecting = m->effect == E_SPIKY_SHIELD ? 2 : 1;
        note(b, N_PROTECT, s, 0, 0);
    }
    return 1;
}

/* the status moves other_move handles whatever their quality in the move data (Odor Sleuth is a condition there) */
static int mech_case(int e)
{
    switch (e) {
    case E_ACUPRESSURE: case E_ASSIST: case E_MAGIC_COAT: case E_SNATCH: case E_POWDER: case E_ODOR_SLEUTH:
    case E_MIRACLE_EYE: case E_REFLECT_TYPE: case E_HEART_SWAP: case E_GUARD_SWAP: case E_POWER_SWAP:
    case E_FORESTS_CURSE: case E_TRICK_OR_TREAT: case E_SOAK: case E_WORRY_SEED: case E_SIMPLE_BEAM: case E_ENTRAINMENT:
    case E_GASTRO_ACID: case E_TELEKINESIS: case E_MAGNET_RISE: case E_TRICK: case E_SPITE: case E_MIMIC: case E_SKETCH:
    case E_DISABLE: case E_CONVERSION: case E_CONVERSION2: case E_TORMENT: case E_GUARD_SPLIT: case E_POWER_SPLIT: case E_POWER_TRICK: case E_EMBARGO: case E_IMPRISON: case E_GRUDGE: case E_SPLASH:
    case E_QUASH: case E_HEAL_BLOCK: case E_CAMOUFLAGE:
        return 1;
    }
    return 0;
}

/* abilities a move cannot replace (Worry Seed, Simple Beam, Gastro Acid, the target of Entrainment) */
static int fixed_ability(int ab)
{
    return ab == A_MULTITYPE || ab == A_STANCECHANGE || ab == A_SCHOOLING || ab == A_DISGUISE || ab == A_RKSSYSTEM ||
           ab == A_COMATOSE || ab == A_ZENMODE;
}

static void save_stats(Volatile *v, const Mon *m)
{
    if (!v->stats_saved)
        memcpy(v->saved_stat, m->stat, sizeof m->stat), v->stats_saved = 1;
}

/* Guard Split (Def, SpD) and Power Split (Atk, SpA): both sides take the average */
static void split(Battle *b, int s, int t, int i, int j)
{
    Mon *u = &b->party[s][0], *d = &b->party[t][0];
    save_stats(&b->v[s], u);
    save_stats(&b->v[t], d);
    u->stat[i] = d->stat[i] = (u->stat[i] + d->stat[i]) / 2;
    u->stat[j] = d->stat[j] = (u->stat[j] + d->stat[j]) / 2;
}

static int set_type(Volatile *v, int t)
{
    if (v->types[0] == t && (v->types[1] == t || v->types[1] == T_NONE) && v->types[2] == T_NONE)
        return 0;
    v->types[0] = v->types[1] = t;
    v->types[2] = T_NONE;
    return 1;
}

static int other_move(Battle *b, int s, int t, int mv, const Policy *const pol[2], int depth)
{
    const MoveRec *m = &sim_moves[mv];
    Mon *u = &b->party[s][0], *d = &b->party[t][0];
    Volatile *vu = &b->v[s], *vd = &b->v[t];
    int k;
    switch (m->effect) {
    case E_PROTECT: case E_SPIKY_SHIELD: case 355: case 383: case 441: case 451: case E_ENDURE:
        return protect_move(b, s, t, m);
    case E_PAIN_SPLIT: {
        int avg = (u->hp + d->hp) / 2;
        if (vd->sub)
            return 0;
        u->hp = avg > u->maxhp ? u->maxhp : avg;
        d->hp = avg > d->maxhp ? d->maxhp : avg;
        return 1;
    }
    case E_CURSE:
        if (has_type_v(vu, T_GHOST)) {
            if (vd->cursed || vd->sub)
                return 0;
            vd->cursed = 1;
            chip(b, s, u->maxhp / 2);
            if (!sim_alive(u))
                fainted(b, s);
            return 1;
        }
        boost(b, s, STAT_ATK, 1, 0);
        boost(b, s, STAT_DEF, 1, 0);
        boost(b, s, STAT_SPE, -1, 0);
        return 1;
    case E_DESTINY:
        if (vu->last_move == mv && vu->worked)
            return 0;
        vu->destiny = 1;
        return 1;
    case E_AQUA_RING: return vu->aqua ? 0 : (vu->aqua = 1);
    case E_INGRAIN: return vu->ingrain ? 0 : (vu->ingrain = vu->trapped = 1);
    case E_BELLY_DRUM:
        if (u->hp <= u->maxhp / 2 || vu->stage[STAT_ATK] >= 6)
            return 0;
        chip(b, s, u->maxhp / 2);
        vu->stage[STAT_ATK] = 6;
        return 1;
    case E_ENCORE: {
        int slot = -1;
        for (k = 0; k < 4; k++)
            if (d->moves[k] && d->moves[k] == vd->last_move && d->pp[k])
                slot = k;
        if (slot < 0 || vd->encore || vd->last_move == M_ENCORE)
            return 0;
        vd->encore = 3;
        vd->encore_slot = slot;
        return 1;
    }
    case E_REST:
        if (u->hp == u->maxhp || vu->ability == A_INSOMNIA || vu->ability == A_VITALSPIRIT ||
            (b->terrain == TERRAIN_ELECTRIC && grounded(b, s)))
            return 0;
        u->status = ST_SLP;
        u->toxic = u->tox_n = 0;
        u->sleep = 2;
        u->slept = 0;
        u->hp = u->maxhp;
        status_berry(b, s);
        return 1;
    case E_TRANSFORM:
        transform(b, s, t);
        return vu->transformed;
    case E_ROLE_PLAY:
        if (vu->ability == vd->ability)
            return 0;
        vu->ability = vd->ability;
        return 1;
    case E_RECYCLE:
        if (u->item || !u->lost_item)
            return 0;
        u->item = u->lost_item;
        u->lost_item = 0;
        return 1;
    case E_MEAN_LOOK: return vd->trapped ? 0 : (vd->trapped = 1);
    case E_FOCUS_ENERGY: return vu->focus ? 0 : (vu->focus = 1);
    case E_STOCKPILE:
        if (vu->stockpile >= 3)
            return 0;
        vu->stockpile++;
        boost(b, s, STAT_DEF, 1, 0);
        boost(b, s, STAT_SPD, 1, 0);
        return 1;
    case E_SUBSTITUTE:
        if (vu->sub || u->hp <= u->maxhp / 4)
            return 0;
        chip(b, s, u->maxhp / 4);
        vu->sub = u->maxhp / 4;
        return 1;
    case E_TAUNT:
        if (vd->taunt || vd->ability == A_OBLIVIOUS)
            return 0;
        vd->taunt = 3;                       /* 3 turns, this one included (measured) */
        return 1;
    case E_MEMENTO:
        boost(b, t, STAT_ATK, -2, 1);
        boost(b, t, STAT_SPA, -2, 1);
        u->hp = 0;
        fainted(b, s);
        return 1;
    case E_HEAL_BELL:
        for (k = 0; k < b->n[s]; k++) {
            b->party[s][k].status = 0;
            b->party[s][k].toxic = b->party[s][k].tox_n = 0;
        }
        return 1;
    case E_WISH:
        if (b->side[s].wish)
            return 0;
        b->side[s].wish = 2;
        b->side[s].wish_hp = u->maxhp / 2;
        return 1;
    case E_BATON_PASS:
        if (!bench_count(b, s))
            return 0;
        replace(b, s, pol[s], 2);
        return 1;
    case E_SHELL_SMASH:
        boost(b, s, STAT_DEF, -1, 0);
        boost(b, s, STAT_SPD, -1, 0);
        boost(b, s, STAT_ATK, 2, 0);
        boost(b, s, STAT_SPA, 2, 0);
        boost(b, s, STAT_SPE, 2, 0);
        if (item_of(b, s) == I_WHITEHERB) {
            vu->stage[STAT_DEF] = vu->stage[STAT_DEF] < 0 ? 0 : vu->stage[STAT_DEF];
            vu->stage[STAT_SPD] = vu->stage[STAT_SPD] < 0 ? 0 : vu->stage[STAT_SPD];
            consume(b, s);
        }
        return 1;
    case E_NIGHTMARE:
        return apply_sick(b, t, m, s);
    case E_STRENGTH_SAP: {
        int st = vd->stage[STAT_ATK], a = d->stat[STAT_ATK];
        if (st <= -6)
            return 0;
        a = st >= 0 ? a * (2 + st) / 2 : a * 2 / (2 - st);
        boost(b, t, STAT_ATK, -1, 1);
        heal(b, s, a);
        return 1;
    }
    case E_COPYCAT:
        if (!b->last_used || b->last_used == M_COPYCAT || depth)
            return 0;
        run_move(b, s, b->last_used, pol, depth + 1);
        return 1;                           /* the called move notes its own failure (logs: one "it failed") */
    case E_METRONOME: {
        int pick;
        if (depth)
            return 0;
        do
            pick = 1 + sim_rand(b, sim_nmoves - 1);
        while (!sim_move_name[pick][0] || pick == M_METRONOME || pick == M_STRUGGLE || (sim_moves[pick].flags & FL_CHARGE) ||
               sim_moves[pick].quality == Q_OTHER);
        return run_move(b, s, pick, pol, depth + 1);
    }
    case E_SLEEP_TALK: {
        int slots[4], n = 0;
        if (u->status != ST_SLP || depth)
            return 0;
        for (k = 0; k < 4; k++)
            if (u->moves[k] && u->moves[k] != mv && !(sim_moves[u->moves[k]].flags & FL_CHARGE))
                slots[n++] = k;
        return n ? run_move(b, s, u->moves[slots[sim_rand(b, n)]], pol, depth + 1) : 0;
    }
    case E_LOCK_ON:
        return 1;                            /* nothing (Lock-On and Mind Reader measured) */
    /* the moves below work on the DS where the simulator had them fail (rc33 A0-SIMMECH, the census logs) */
    case E_ACUPRESSURE: {
        double p[7];
        int open = 0, pick;
        for (k = 0; k < 7; k++)
            open += vu->stage[k] < 6;
        if (!open)
            return 0;
        for (k = 0; k < 7; k++)
            p[k] = vu->stage[k] < 6 ? 1.0 / open : 0;
        if (b->oracle)
            pick = b->oracle->pick(b->oracle, b, K_ACUPRESSURE, s, 7, p);
        else
            for (pick = 0, k = (int)sim_rand(b, open); pick < 7; pick++)
                if (vu->stage[pick] < 6 && !k--)
                    break;
        boost(b, s, pick, 2, 0);
        return 1;
    }
    case E_ASSIST: {
        u16 cand[24];
        int n = 0, j;
        if (depth)
            return 0;
        for (k = 1; k < b->n[s]; k++)
            for (j = 0; j < 4; j++)
                if (!no_assist(b->party[s][k].moves[j]))
                    cand[n++] = b->party[s][k].moves[j];
        if (!n)
            return 0;
        run_move(b, s, cand[call_pick(b, s, cand, n)], pol, depth + 1);
        return 1;
    }
    case E_MAGIC_COAT: return vd->moved ? 0 : (vu->coat = 1);     /* it fails when the foe has acted (logs) */
    case E_SNATCH: return vd->moved ? 0 : (vu->snatch = 1);
    case E_POWDER: return vd->sub ? 0 : (vd->powder = 1);
    case E_ODOR_SLEUTH: return vd->identified = 1;
    case E_MIRACLE_EYE: return vd->identified = 2;
    case E_REFLECT_TYPE:
        if (vd->types[0] == T_NONE || !memcmp(vu->types, vd->types, 3))
            return 0;
        memcpy(vu->types, vd->types, 3);
        return 1;
    case E_HEART_SWAP: case E_GUARD_SWAP: case E_POWER_SWAP:
        return 1;       /* the DS prints the swap and changes no stage (logs: 7 of 7 uses with stages on either side) */
    case E_FORESTS_CURSE: case E_TRICK_OR_TREAT: {
        int ty = m->effect == E_FORESTS_CURSE ? T_GRASS : T_GHOST;
        if (vd->sub || has_type_v(vd, ty))
            return 0;
        vd->types[2] = ty;
        return 1;
    }
    case E_SOAK: return vd->sub ? 0 : set_type(vd, T_WATER);
    case E_WORRY_SEED: case E_SIMPLE_BEAM: {
        int ab = m->effect == E_WORRY_SEED ? A_INSOMNIA : A_SIMPLE;
        if (vd->sub || vd->ability == ab || vd->ability == A_TRUANT || fixed_ability(vd->ability))
            return 0;
        vd->ability = ab;
        return 1;
    }
    case E_ENTRAINMENT:
        if (vd->sub || vd->ability == vu->ability || vd->ability == A_TRUANT || fixed_ability(vd->ability) ||
            vu->ability == A_TRACE || vu->ability == A_IMPOSTER || vu->ability == A_ILLUSION || fixed_ability(vu->ability))
            return 0;
        vd->ability = vu->ability;
        return 1;
    case E_GASTRO_ACID:
        if (vd->sub || !vd->ability || fixed_ability(vd->ability))
            return 0;
        vd->ability = 0;
        return 1;
    case E_TELEKINESIS:
        if (vd->ingrain || b->gravity || d->species == S_DIGLETT || d->species == S_DUGTRIO)
            return 0;
        vd->tele = 3;
        return 1;
    case E_MAGNET_RISE:
        if (vu->magnet || vu->ingrain || b->gravity)
            return 0;
        vu->magnet = 5;
        return 1;
    case E_TRICK: {
        int x = u->item;
        if ((!u->item && !d->item) || vd->sub || vd->ability == A_STICKYHOLD)
            return 0;
        u->item = d->item;
        d->item = x;
        vu->choice = vd->choice = 0;
        return 1;
    }
    case E_SPITE:
        for (k = 0; k < 4; k++)
            if (d->moves[k] && d->moves[k] == vd->last_move && d->pp[k]) {
                d->pp[k] = d->pp[k] > 4 ? d->pp[k] - 4 : 0;
                return 1;
            }
        return 0;
    case E_MIMIC: case E_SKETCH: {
        int slot = -1, lm = vd->last_move;
        if (!lm || lm == M_STRUGGLE || lm == M_SKETCH || lm == M_MIMIC || lm == M_TRANSFORM || lm == M_CHATTER)
            return 0;
        for (k = 0; k < 4; k++) {
            if (u->moves[k] == lm)
                return 0;
            if (u->moves[k] == mv)
                slot = k;
        }
        if (slot < 0)
            return 0;
        if (m->effect == E_MIMIC && !vu->mimic_slot && !vu->transformed)
            vu->mimic_slot = slot + 1, vu->mimic_move = mv;
        u->moves[slot] = lm;
        u->pp[slot] = m->effect == E_MIMIC ? 5 : sim_moves[lm].pp;
        return 1;
    }
    case E_CONVERSION: {
        int ty = sim_moves[u->moves[0]].type;
        return set_type(vu, ty);
    }
    case E_CONVERSION2: {
        int lt, ty[18], n = 0;
        if (!vd->last_move)
            return 0;
        lt = sim_moves[vd->last_move].type;
        for (k = 0; k < 18; k++)
            if (sim_chart[lt][k] < 4 && !has_type_v(vu, k))
                ty[n++] = k;
        return n ? set_type(vu, ty[sim_rand(b, n)]) : 0;
    }
    case E_GUARD_SPLIT: split(b, s, t, STAT_DEF, STAT_SPD); return 1;
    case E_POWER_SPLIT: split(b, s, t, STAT_ATK, STAT_SPA); return 1;
    case E_POWER_TRICK: {
        u16 x = u->stat[STAT_ATK];
        save_stats(vu, u);
        u->stat[STAT_ATK] = u->stat[STAT_DEF];
        u->stat[STAT_DEF] = x;
        return 1;
    }
    case E_TORMENT: return vd->sub || vd->torment ? 0 : (vd->torment = 1);
    case E_DISABLE:
        for (k = 0; k < 4; k++)
            if (!vd->disabled && vd->last_move && d->moves[k] == vd->last_move && d->pp[k] && vd->last_move != M_STRUGGLE) {
                vd->disabled = 4;
                vd->disabled_move = vd->last_move;
                return 1;
            }
        return 0;
    case E_EMBARGO: return vd->embargo ? 0 : (vd->embargo = 5);
    case E_IMPRISON: return vu->imprison ? 0 : (vu->imprison = 1);
    case E_GRUDGE: return vu->grudge = 1;
    case E_CAMOUFLAGE:
        return set_type(vu, T_NORMAL);      /* Normal here: it fails on a Normal type (logs) */
    case E_SPLASH: case E_QUASH: case E_HEAL_BLOCK:
        return 1;                            /* worked on the DS; no state the simulator keeps */
    case E_FOLLOW_ME: case E_HELPING_HAND:
        return 0;                            /* they fail in singles (logs) */
    }
    return 0;
}

static int field_move(Battle *b, int s, const MoveRec *m)
{
    int k;
    switch (m->effect) {
    case E_RAIN: if (b->weather == W_RAIN) return 0; set_weather(b, W_RAIN, s, 0); return 1;
    case E_SUN: if (b->weather == W_SUN) return 0; set_weather(b, W_SUN, s, 0); return 1;
    case E_SANDSTORM: if (b->weather == W_SAND) return 0; set_weather(b, W_SAND, s, 0); return 1;
    case E_HAIL: case E_SNOW: if (b->weather == W_SNOW) return 0; set_weather(b, W_SNOW, s, 0); return 1;
    case E_TRICK_ROOM: b->trick_room = b->trick_room ? 0 : 5; return 1;
    case E_GRASSY_TERRAIN: if (b->terrain == TERRAIN_GRASSY) return 0; set_terrain(b, TERRAIN_GRASSY, s); return 1;
    case E_HAZE:
        for (k = 0; k < 7; k++)
            b->v[0].stage[k] = b->v[1].stage[k] = 0;
        return 1;
    case E_ELECTRIC_TERRAIN: if (b->terrain == TERRAIN_ELECTRIC) return 0; set_terrain(b, TERRAIN_ELECTRIC, s); return 1;
    case E_MISTY_TERRAIN: if (b->terrain == TERRAIN_MISTY) return 0; set_terrain(b, TERRAIN_MISTY, s); return 1;
    case E_GRAVITY: return b->gravity ? 0 : (b->gravity = 5);
    case E_MUD_SPORT: return b->mud_sport ? 0 : (b->mud_sport = 5);
    case E_WATER_SPORT: return b->water_sport ? 0 : (b->water_sport = 5);
    case E_WONDER_ROOM: b->wonder_room = b->wonder_room ? 0 : 5; return 1;
    case E_MAGIC_ROOM: b->magic_room = b->magic_room ? 0 : 5; return 1;
    }
    return 0;
}

static int side_move(Battle *b, int s, const MoveRec *m)
{
    Side *mine = &b->side[s], *foe = &b->side[s ^ 1];
    int clay = item_of(b, s) == I_LIGHTCLAY ? 8 : 5;
    switch (m->effect) {
    case E_WIDE_GUARD: case E_QUICK_GUARD: case E_MAT_BLOCK: return protect_move(b, s, s ^ 1, m);
    case E_STEALTH_ROCK: return foe->rocks ? 0 : (note(b, N_HAZARD, s ^ 1, 0, 0), foe->rocks = 1);
    case E_SPIKES: return foe->spikes >= 3 ? 0 : (note(b, N_HAZARD, s ^ 1, 1, 0), ++foe->spikes, 1);
    case E_TOXIC_SPIKES: return foe->tspikes >= 2 ? 0 : (note(b, N_HAZARD, s ^ 1, 2, 0), ++foe->tspikes, 1);
    case E_STICKY_WEB: return foe->sticky ? 0 : (foe->sticky = 1);
    case E_REFLECT: return mine->reflect ? 0 : (mine->reflect = clay);
    case E_LIGHT_SCREEN: return mine->screen ? 0 : (mine->screen = clay);
    case E_AURORA_VEIL: return mine->veil || sim_weather(b) != W_SNOW ? 0 : (mine->veil = clay);
    case E_TAILWIND: return mine->tailwind ? 0 : (mine->tailwind = 4);     /* 4 turns, this one included (measured) */
    case E_SAFEGUARD: return mine->safeguard ? 0 : (mine->safeguard = 5);
    }
    return 1;           /* Quick Guard and its like: nothing in this simulator */
}

/* ---------------------------------------------------------------- one move */

/* side s uses move mv (after the checks that can stop it); returns 1 if it worked */
static int run_move(Battle *b, int s, int mv, const Policy *const pol[2], int depth)
{
    const MoveRec *m = &sim_moves[mv];
    int t = s ^ 1, foe = to_foe(m), ok = 0, dab;
    Mon *u = &b->party[s][0], *d = &b->party[t][0];
    Volatile *vu = &b->v[s], *vd = &b->v[t];
    if (m->effect != E_COPYCAT)
        b->last_used = mv;
    if (depth && b->oracle) {
        g_called = mv;
        b->oracle->pick(b->oracle, b, K_CALL, s, 0, 0);
    }
    if (vu->powder && sim_move_type(u, vu, mv, sim_weather(b), b->terrain) == T_FIRE) {
        if (chip(b, s, u->maxhp / 4))       /* Powder: the Fire move explodes on its user */
            fainted(b, s);
        return note(b, N_FAIL, s, mv, 0), 0;
    }
    if (b->gravity && gravity_blocked(mv))
        return note(b, N_FAIL, s, mv, 0), 0;
    if (vd->snatch && (m->flags & FL_SNATCH) && sim_alive(d) && !depth) {
        vd->snatch = 0;                     /* the foe's Snatch takes the move */
        return run_move(b, t, mv, pol, depth + 1), 0;
    }
    if (m->effect == E_FAKE_OUT || m->effect == E_FIRST_IMPRESSION) {
        if (vu->acted)                  /* only before it has acted since it came out */
            return note(b, N_FAIL, s, mv, 0), 0;
    }
    if (m->effect == E_SUCKER_PUNCH && (vd->moved || !vd->planned || sim_moves[vd->planned].cls == CLS_STATUS))
        return note(b, N_FAIL, s, mv, 0), 0;
    if (mv == M_DARKVOID && u->species != S_DARKRAI)    /* only Darkrai can use it (logs: 43 of 43 others failed) */
        return note(b, N_FAIL, s, mv, 0), 0;
    if (foe && !sim_alive(d))
        return note(b, N_FAIL, s, mv, 0), 0;        /* no target left */
    dab = vd->ability;
    if (vu->ability == A_MOLDBREAKER || vu->ability == A_TERAVOLT || vu->ability == A_TURBOBLAZE)
        dab = 0;
    if (foe && vd->protecting && (m->flags & FL_PROTECT) && !(vu->ability == A_UNSEENFIST && (m->flags & FL_CONTACT))) {
        note(b, N_PROTECT, t, 1, 0);
        if (g_fsr)
            g_fsr->s[s].missed = 1;
        sim_log(b, "  %s protected itself from %s", mon_name(d), sim_move_name[mv]);
        if (vd->protecting == 2 && (m->flags & FL_CONTACT) && !v_magic_guard(b, s) && chip(b, s, u->maxhp / 8))
            fainted(b, s);
        if (mv == M_HIJUMPKICK || mv == M_JUMPKICK)
            if (chip(b, s, u->maxhp / 2))
                fainted(b, s);
        return 0;
    }
    if (foe && vd->semi && !reaches(mv, vd->semi) && vu->ability != A_NOGUARD && dab != A_NOGUARD)
        return 0;
    if (foe && b->terrain == TERRAIN_PSYCHIC && grounded(b, t) && m->prio + (vu->ability == A_PRANKSTER && !m->cls) > 0)
        return 0;
    if (foe && m->cls == CLS_STATUS && (m->flags & FL_MAGICCOAT) && (dab == A_MAGICBOUNCE || vd->coat)) {
        /* bounced back at the user */
        if (m->quality == Q_SICK)
            return apply_sick(b, s, m, t);
        if (m->quality == Q_EFFECT)
            apply_ranks(b, s, m, 1, 0, 0);
        return 0;
    }
    if (foe && m->cls == CLS_STATUS && (m->flags & FL_SOUND) && dab == A_SOUNDPROOF)
        return 0;
    if (foe && m->cls == CLS_STATUS && m->type != T_NORMAL &&
        (((dab == A_VOLTABSORB || dab == A_LIGHTNINGROD || dab == A_MOTORDRIVE) && m->type == T_ELECTRIC) ||
         ((dab == A_WATERABSORB || dab == A_STORMDRAIN || dab == A_DRYSKIN) && m->type == T_WATER) ||
         (dab == A_SAPSIPPER && m->type == T_GRASS) || (dab == A_FLASHFIRE && m->type == T_FIRE))) {
        absorb(b, t, m->type);                      /* a status move taken in too (logs: Thunder Wave into Volt Absorb heals) */
        return 0;
    }
    if (foe && (m->flags & FL_POWDER) && (has_type_v(vd, T_GRASS) || dab == A_OVERCOAT || item_of(b, t) == I_SAFETYGOGGLS))
        return note(b, N_NOEFFECT, t, 0, 0), 0;
    /* Thunder Wave has no effect on Ground types (qa/aivsai/paralysis.md, measured 7 of 7); Glare still hits Ghosts */
    if (foe && m->cls == CLS_STATUS && m->type == T_ELECTRIC && m->quality == Q_SICK && has_type_v(vd, T_GROUND))
        return note(b, N_NOEFFECT, t, 0, 0), 0;
    if (foe && m->quality != Q_FIELD && m->quality != Q_SIDE && !lands(b, s, t, mv)) {
        note(b, N_MISS, t, 0, 0);
        if (g_fsr)
            g_fsr->s[s].missed = 1;
        sim_log(b, "  %s's %s missed", mon_name(u), sim_move_name[mv]);
        if (mv == M_HIJUMPKICK || mv == M_JUMPKICK)
            if (chip(b, s, u->maxhp / 2))
                fainted(b, s);
        return 0;
    }
    if (m->cls != CLS_STATUS) {
        int dealt;
        if (m->quality == Q_OHKO) {
            if (dab == A_STURDY || sim_type_eff(m->type, vd->types, mv) == 0)
                return 0;
            d->hp = 0;
            fainted(b, t);
            return 1;
        }
        dealt = damage_move(b, s, t, mv, pol);
        return dealt >= 0;
    }
    switch (mech_case(m->effect) ? Q_OTHER : m->quality) {
    case Q_SICK:
        if (foe && vd->sub && m->sick != SICK_PERISH)
            return 0;
        ok = apply_sick(b, m->target == TG_USER ? s : t, m, s);
        break;
    case Q_EFFECT:
        if (foe) {
            if (vd->sub)
                return 0;
            apply_ranks(b, t, m, 1, 0, 0);
        } else if (mv == M_GROWTH && is_sun(sim_weather(b))) {
            boost(b, s, STAT_ATK, 2, 0);            /* Growth: +2 in sun */
            boost(b, s, STAT_SPA, 2, 0);
        } else
            apply_ranks(b, s, m, 0, 0, 0);
        ok = 1;
        break;
    case Q_EFFECT_SICK:
        if (vd->sub)
            return 0;
        apply_ranks(b, t, m, 1, 0, 0);
        ok = apply_sick(b, t, m, s) || 1;
        break;
    case Q_RECOVER: {
        int pct = m->heal, w = sim_weather(b);
        if (u->hp == u->maxhp)
            return 0;
        if (m->effect == E_SYNTHESIS)
            pct = is_sun(w) ? 67 : w && w != WX_STRONG_WINDS ? 25 : 50;
        heal(b, s, u->maxhp * pct / 100);
        if (mv == M_ROOST && has_type_v(vu, T_FLYING))
            vu->roosted = 1;
        ok = 1;
        break;
    }
    case Q_FIELD: ok = field_move(b, s, m); break;
    case Q_SIDE: ok = side_move(b, s, m); break;
    case Q_PUSHOUT:
        if (!bench_count(b, t) || dab == A_SUCTIONCUPS || vd->ingrain || vd->moved == 2)
            return 0;
        {
            int k, c = phaze_pick(b, t) + 1;
            for (k = 1; k < b->n[t] && c; k++)
                if (sim_alive(&b->party[t][k]) && !--c)
                    switch_in(b, t, k, 0);
        }
        ok = 1;
        break;
    case Q_OTHER:
        ok = other_move(b, s, t, mv, pol, depth);
        break;
    }
    sim_log(b, "  %s used %s%s", mon_name(u), sim_move_name[mv], ok ? "" : ": it failed");
    if (!ok)
        note(b, N_FAIL, s, mv, 0);
    return ok;
}

/* the validator's sleep and confusion: the chance they end at this check, from the drawn lengths' distribution and the
   turns already spent (sleep: 1-3 turns slept through, uniform, halved by Early Bird; Rest: 2; confusion: it ends at
   move attempt 2-5, uniform) */
static double wake_chance(const Mon *u)
{
    int k = u->slept;
    if (u->sleep == SLEEP_EARLY)            /* 0, 1, 1 */
        return k == 0 ? 1 / 3.0 : 1.0;
    if (u->sleep != SLEEP_DRAWN)            /* a fixed length (Rest) */
        return k >= u->sleep ? 1.0 : 0.0;
    return k <= 0 ? 0.0 : k >= 3 ? 1.0 : 1.0 / (4 - k);
}

static double conf_end_chance(int attempt)
{
    return attempt <= 1 ? 0.0 : attempt >= 5 ? 1.0 : 1.0 / (6 - attempt);
}

static void use_move_(Battle *b, int s, int slot, const Policy *const pol[2]);
void use_move(Battle *b, int s, int slot, const Policy *const pol[2])
{
    int o = g_owner;
    g_owner = s;
    b->v[s].ran = 0;
    use_move_(b, s, slot, pol);
    if (!b->v[s].ran)
        b->v[s].protects = 0;           /* a turn lost before the move zeroes the streak (DS traces T4c) */
    g_owner = o;
}
static void use_move_(Battle *b, int s, int slot, const Policy *const pol[2])
{
    Mon *u = &b->party[s][0];
    Volatile *vu = &b->v[s];
    int cont = forced_slot(b, s) == slot, mv, ok, worked;
    const MoveRec *m;
    if (slot == 5) {
        vu->recharge = 0;
        sim_log(b, "  %s must recharge", mon_name(u));
        return;
    }
    mv = slot == 4 ? M_STRUGGLE : u->moves[slot];
    if (!mv)
        return;
    if (g_fsr && !g_fsr->s[s].called) {
        g_fsr->s[s].called = ++g_fsr->n;
        g_fsr->s[s].st_at = u->status;
        g_fsr->s[s].stg = memcmp(vu->stage, g_fsr->stg0[s], sizeof vu->stage) != 0;
        g_fsr->s[s].chg = u->status != g_fsr->st0[s] || g_fsr->s[s].stg;
        g_fsr->mv[s] = mv;
    }
    m = &sim_moves[mv];
    vu->destiny = 0;
    if (vu->roosted)
        vu->roosted = 0;
    /* what can stop it */
    if (u->status == ST_SLP) {
        if (b->oracle ? !b->oracle->yes(b->oracle, b, K_WAKE, s, wake_chance(u)) : u->sleep > 0) {
            if (!b->oracle)
                u->sleep--;
            u->slept++;
            if (m->effect != E_SLEEP_TALK && mv != M_SNORE) {
                if (g_fsr)
                    g_fsr->s[s].stopped = 1;
                sim_log(b, "  %s is asleep", mon_name(u));
                vu->lock = vu->charging = 0;
                vu->semi = 0;
                return;
            }
        } else {
            u->status = 0;
            u->slept = 0;
        }
    }
    if (u->status == ST_FRZ) {
        if ((m->flags & FL_DEFROST) || yes(b, K_THAW, s, 20))
            u->status = 0;
        else {
            if (g_fsr)
                g_fsr->s[s].stopped = 1;
            vu->lock = vu->charging = 0;
            return;
        }
    }
    if (vu->flinched) {
        vu->flinched = 0;
        note(b, N_FLINCH, s, 0, 0);
        if (g_fsr)
            g_fsr->s[s].flinched = 1;
        if (vu->ability == A_STEADFAST)
            boost(b, s, STAT_SPE, 1, 0);
        vu->lock = vu->charging = 0;
        vu->semi = 0;
        return;
    }
    if (vu->confused) {
        int end;
        if (b->oracle) {
            end = b->oracle->yes(b->oracle, b, K_CONF_END, s, conf_end_chance(++vu->conf_n));
            if (end)
                vu->confused = 0;
        } else
            end = !--vu->confused;
        if (end)
            ;
        else if (yes(b, K_CONF_HIT, s, 33)) {           /* 33% (measured) */
            int a = u->stat[STAT_ATK], d = u->stat[STAT_DEF], sa = vu->stage[STAT_ATK], sd = vu->stage[STAT_DEF], dmg;
            a = sa >= 0 ? a * (2 + sa) / 2 : a * 2 / (2 - sa);
            d = sd >= 0 ? d * (2 + sd) / 2 : d * 2 / (2 - sd);
            dmg = ((2 * u->level / 5 + 2) * 40 * a / (d ? d : 1) / 50 + 2) * (85 + sim_rand(b, 16)) / 100;
            sim_log(b, "  %s hurt itself in confusion (%d)", mon_name(u), dmg);
            note(b, N_SELFHIT, s, dmg, 0);
            if (g_fsr)
                g_fsr->s[s].stopped = 1;
            if (chip(b, s, dmg))
                fainted(b, s);
            vu->lock = vu->charging = 0;
            vu->semi = 0;
            return;
        }
    }
    if (u->status == ST_PAR && yes(b, K_PARA, s, 25)) {
        if (g_fsr)
            g_fsr->s[s].stopped = 1;
        vu->lock = vu->charging = 0;
        vu->semi = 0;
        return;
    }
    if (g_fsr)
        g_fsr->s[s].reached = 1;
    if (vu->taunt && m->cls == CLS_STATUS)
        return;
    vu->ran = 1;
    /* PP, choice lock, memory */
    if (slot < 4 && !cont) {
        if (u->pp[slot])
            u->pp[slot]--;
        if (u->pp[slot] && b->v[s ^ 1].ability == A_PRESSURE && sim_alive(&b->party[s ^ 1][0]))
            u->pp[slot]--;
    }
    if (slot < 4) {
        int it = item_of(b, s);
        u->used |= 1 << slot;
        if (!vu->choice && (it == I_CHOICEBAND || it == I_CHOICESPECS || it == I_CHOICESCARF))
            vu->choice = slot + 1;
    }
    /* charging */
    if (m->flags & FL_CHARGE) {
        if (cont && vu->charging) {
            vu->charging = 0;
            vu->semi = 0;
        } else {
            int w = sim_weather(b);
            if ((mv == M_SOLARBEAM || mv == M_SOLARBLADE) && (is_sun(w) || vu->ability == A_MEGASOL))
                ;
            else if (item_of(b, s) == I_POWERHERB) {
                consume(b, s);
                if (mv == M_METEORBEAM)
                    boost(b, s, STAT_SPA, 1, 0);    /* the charge turn's boost still comes (logs) */
            } else {
                vu->charging = slot + 1;
                vu->semi = mv == M_FLY || mv == M_BOUNCE ? SEMI_FLY : mv == M_DIG ? SEMI_DIG : mv == M_DIVE ? SEMI_DIVE :
                           mv == M_PHANTOMFORCE || mv == M_SHADOWFORCE ? SEMI_SHADOW : 0;
                if (mv == M_METEORBEAM)
                    boost(b, s, STAT_SPA, 1, 0);
                vu->last_move = mv;
                vu->acted = 1;
                sim_log(b, "  %s charges %s", mon_name(u), sim_move_name[mv]);
                return;
            }
        }
    }
    if ((vu->ability == A_PROTEAN || vu->ability == A_LIBERO) && mv != M_STRUGGLE) {
        vu->types[0] = sim_move_type(u, vu, mv, sim_weather(b), b->terrain);   /* before the move (logs) */
        vu->types[1] = vu->types[2] = T_NONE;
    }
    ok = run_move(b, s, mv, pol, 0);
    vu->acted = 1;                      /* after run_move: Fake Out reads it */
    vu->failed = !ok;
    worked = ok || (mv == M_AURORAVEIL && b->side[s].veil);     /* the engine counts a veil already up as worked (DS traces) */
    if (worked && vu->last_move == mv)
        vu->worked++;
    else
        vu->worked = worked;
    vu->last_move = mv;
    if (!ok && !sim_alive(&b->party[s ^ 1][0]))
        ;
    /* Outrage and its like: locked in 2-3 turns, then confused */
    if (m->effect == E_LOCK) {
        if (!ok)
            vu->lock = 0;
        else if (!cont) {
            vu->lock = b->oracle ? 2 : 1 + sim_rand(b, 2);      /* the validator decides the end at each turn */
            vu->lock_slot = slot;
        } else if (b->oracle) {
            if (b->oracle->yes(b->oracle, b, K_LOCK_END, s, --vu->lock ? 0.5 : 1.0)) {
                vu->lock = 0;
                confuse(b, s, -1);
            }
        } else if (!--vu->lock)
            confuse(b, s, -1);
    }
    if (ok && (m->flags & FL_RECHARGE) && sim_alive(u))
        vu->recharge = 1;
    if (m->effect == E_EXPLOSION || mv == M_MISTYEXPLOSN || m->effect == E_FINAL_GAMBIT) {
        if (sim_alive(u)) {
            u->hp = 0;
            fainted(b, s);
        }
    }
}
