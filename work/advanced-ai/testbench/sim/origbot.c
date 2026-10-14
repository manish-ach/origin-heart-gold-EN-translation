/* A model of the hack's original trainer AI (overlay 11), so the simulator can play the advanced AI against it.
   The inputs (orig_moves) and the logged-decision dumps for fitting are here; the rules are fitted by
   tools/sim/origfit.py on the emulator's adv-vs-orig logs. */
#include <stdlib.h>
#include <string.h>
#include "sim.h"
#include "sim_ids.h"
#include "internal.h"
#include "origbot.h"

static int hits_x10(const MoveRec *m)
{
    if (m->hits_max <= 1)
        return 10;
    if (m->hits_min == m->hits_max)
        return 10 * m->hits_max;
    if (m->hits_min == 2 && m->hits_max == 5)
        return 31;
    return 5 * (m->hits_min + m->hits_max);
}

static int prio_of(const Battle *b, int s, int mv)
{
    const MoveRec *m = &sim_moves[mv];
    int p = m->prio, ab = b->v[s].ability;
    if (ab == A_PRANKSTER && m->cls == CLS_STATUS)
        p++;
    if (ab == A_GALEWINGS && m->type == T_FLYING)
        p++;
    if (ab == A_TRIAGE && (m->heal > 0 || m->drain > 0))
        p += 3;
    return p;
}

static int faster(const Battle *b, int s)
{
    int me = sim_eff_speed(b, s), foe = sim_eff_speed(b, s ^ 1);
    return b->trick_room ? me < foe : me > foe;
}

static int has_type_mon(const Battle *b, int s, int t)
{
    return b->v[s].types[0] == t || b->v[s].types[1] == t || b->v[s].types[2] == t;
}

/* a main status (ST_*) can take on side d's Pokemon from side s's move m */
static int status_takes(const Battle *b, int s, int d, const MoveRec *m, int st)
{
    const Mon *x = &b->party[d][0];
    int ab = b->v[d].ability;
    if (x->status || b->side[d].safeguard || ab == A_COMATOSE || ab == A_PURIFYNGSALT)
        return 0;
    if (b->terrain == TERRAIN_MISTY && grounded(b, d))
        return 0;
    if ((m->flags & FL_POWDER) && (has_type_mon(b, d, T_GRASS) || ab == A_OVERCOAT))
        return 0;
    switch (st) {
    case ST_PAR:
        return !has_type_mon(b, d, T_ELECTRIC) && ab != A_LIMBER && !(m->type == T_ELECTRIC && has_type_mon(b, d, T_GROUND));
    case ST_SLP:
        return ab != A_INSOMNIA && ab != A_VITALSPIRIT && ab != A_SWEETVEIL &&
               !(b->terrain == TERRAIN_ELECTRIC && grounded(b, d));
    case ST_PSN:
        return !has_type_mon(b, d, T_POISON) && !has_type_mon(b, d, T_STEEL) && ab != A_IMMUNITY;
    case ST_BRN:
        return !has_type_mon(b, d, T_FIRE) && ab != A_WATERVEIL && ab != A_WATERBUBBLE;
    }
    return 1;
}

/* the status move m (slot k of side s) can have an effect: the kind of check the original AI scores -10 */
static int status_works(const Battle *b, int s, const MoveRec *m, int mv)
{
    int d = s ^ 1, k;
    const Mon *me = &b->party[s][0];
    const Volatile *vd = &b->v[d], *vs = &b->v[s];
    const Side *my = &b->side[s], *their = &b->side[d];
    switch (mv) {
    case M_SPIKES: return their->spikes < 3;
    case M_TOXICSPIKES: return their->tspikes < 2;
    case M_STEALTHROCK: return !their->rocks;
    case M_REFLECT: return !my->reflect;
    case M_LIGHTSCREEN: return !my->screen;
    case M_AURORAVEIL: return !my->veil && (b->weather == W_SNOW);
    case M_SAFEGUARD: return !my->safeguard;
    case M_TAILWIND: return !my->tailwind;
    case M_SUBSTITUTE: return !vs->sub && me->hp * 4 > me->maxhp;
    case M_RAINDANCE: return b->weather != W_RAIN;
    case M_SUNNYDAY: return b->weather != W_SUN;
    case M_SANDSTORM: return b->weather != W_SAND;
    case M_HAIL: case M_SNOWSCAPE: return b->weather != W_SNOW;
    case M_LEECHSEED: return !vd->seeded && !has_type_mon(b, d, T_GRASS);
    case M_TAUNT: return !vd->taunt;
    case M_YAWN: return !vd->yawn && status_takes(b, s, d, m, ST_SLP);
    case M_SLEEPTALK: case M_SNORE: return me->status == ST_SLP;
    case M_REST: return me->status != ST_SLP && me->hp < me->maxhp;
    }
    if (m->target != TG_USER && (m->quality == Q_SICK || m->quality == Q_EFFECT_SICK)) {
        if (m->sick >= SICK_PAR && m->sick <= SICK_PSN)
            return status_takes(b, s, d, m, m->sick);
        if (m->sick == SICK_CONFUSION)
            return !vd->confused && vd->ability != A_OWNTEMPO;
    }
    if (m->heal > 0 && (m->target == TG_USER || m->target == TG_USER_OR_ALLY))
        return me->hp < me->maxhp;
    for (k = 0; k < 3; k++)                    /* boosts: the first raised stat below +6 */
        if (m->rank_val[k] > 0 && (m->target == TG_USER || m->target == TG_USER_OR_ALLY || m->target == TG_USER_SIDE_MONS)) {
            int st = m->rank_type[k] == 9 ? STAT_ATK : m->rank_type[k] - 1;
            return st < 0 || st > 6 || vs->stage[st] < 6;
        }
    for (k = 0; k < 3; k++)                    /* drops on the foe: the first lowered stat above -6 */
        if (m->rank_val[k] < 0 && m->target != TG_USER) {
            int st = m->rank_type[k] == 9 ? STAT_ATK : m->rank_type[k] - 1;
            return st < 0 || st > 6 || vd->stage[st] > -6;
        }
    return 1;
}

/* the Gen 5 effectiveness scale overlay 11 and the chooser use: 7 = x1, 8 = x2, 9 = x4, 6 = x0.5, 5 = x0.25, 0 immune */
static int eff7(int x4)
{
    return x4 >= 16 ? 9 : x4 >= 8 ? 8 : x4 >= 4 ? 7 : x4 >= 2 ? 6 : x4 >= 1 ? 5 : 0;
}

/* the level of move o's row on the foe in the fitted table (origfit.py fit): kind (0 an attack, 1 an attack the foe is
   immune to, 2 a status move that fails, 3 one that works), then for an attack the knockout at the lowest roll (2), the
   highest only (1) or none (0), whether its highest roll is the best of the legal attacks', the effectiveness (eff7)
   and positive priority */
static void foe_key(OrigMove *o, int top)
{
    int *k = o->fkey;
    memset(o->fkey, 0, sizeof o->fkey);
    if (o->cls == CLS_STATUS)
        k[0] = 2 + (o->works != 0);
    else if (!o->eff)
        k[0] = 1;
    else
        k[1] = o->ko_min ? 2 : o->ko_max ? 1 : 0, k[2] = o->dmax >= top, k[3] = eff7(o->eff), k[4] = o->prio > 0;
}

void orig_moves(const Battle *b, int s, OrigMove f[4])
{
    const Mon *me = &b->party[s][0], *foe = &b->party[s ^ 1][0];
    int k, fast = faster(b, s), top = 1;
    for (k = 0; k < 4; k++) {
        OrigMove *o = &f[k];
        int mv = me->moves[k];
        const MoveRec *m = &sim_moves[mv];
        memset(o, 0, sizeof *o);
        o->slot = k;
        o->move = mv;
        if (!mv)
            continue;
        o->legal = sim_legal_move(b, s, k);
        o->cls = m->cls;
        o->type = sim_move_type(me, &b->v[s], mv, sim_weather(b), b->terrain);
        o->power = m->power;
        o->prio = prio_of(b, s, mv);
        o->acc = m->acc;
        o->effect = m->effect;
        o->quality = m->quality;
        o->sick = m->sick;
        o->target = m->target;
        o->first = o->prio > 0 || (o->prio == 0 && fast);
        if (m->cls != CLS_STATUS && sim_alive(foe)) {
            DamageQ q;
            memset(&q, 0, sizeof q);
            q.a = me, q.d = foe, q.va = &b->v[s], q.vd = &b->v[s ^ 1];
            q.a_active = q.d_active = 1;
            q.weather = sim_weather(b), q.terrain = b->terrain;
            q.screen = m->cls == CLS_PHYSICAL ? b->side[s ^ 1].reflect || b->side[s ^ 1].veil :
                       b->side[s ^ 1].screen || b->side[s ^ 1].veil;
            q.sim = 1;
            q.roll = 100;
            o->dmax = sim_damage(&q, mv) * hits_x10(m) / 10;
            o->eff = q.type_eff;
            q.roll = 85;
            o->dmin = q.fixed ? o->dmax : sim_damage(&q, mv) * hits_x10(m) / 10;
            o->ko_min = o->dmin >= foe->hp;
            o->ko_max = o->dmax >= foe->hp;
            o->works = o->eff > 0;
        } else
            o->works = status_works(b, s, m, mv);
        if (o->legal && o->cls != CLS_STATUS && o->dmax > top)
            top = o->dmax;
    }
    for (k = 0; k < 4; k++)
        foe_key(&f[k], top);
}

/* ---------------------------------------------------------------- the dumps for fitting */

static void dump_moves(FILE *f, const OrigMove *mv)
{
    int k;
    fprintf(f, "\"moves\": [");
    for (k = 0; k < 4; k++) {
        const OrigMove *o = &mv[k];
        fprintf(f, "%s{\"slot\": %d, \"move\": %d, \"name\": \"%s\", \"legal\": %d, \"cls\": %d, \"type\": %d, \"power\": %d, "
                "\"prio\": %d, \"acc\": %d, \"effect\": %d, \"quality\": %d, \"sick\": %d, \"target\": %d, \"eff\": %d, "
                "\"dmin\": %d, \"dmax\": %d, \"ko_min\": %d, \"ko_max\": %d, \"first\": %d, \"works\": %d, \"heal\": %d, "
                "\"rank\": [%d, %d], \"flags\": %u, \"fkey\": [%d, %d, %d, %d, %d]}",
                k ? ", " : "", o->slot, o->move, sim_move_name[o->move], o->legal, o->cls, o->type, o->power, o->prio, o->acc,
                o->effect, o->quality, o->sick, o->target, o->eff, o->dmin, o->dmax, o->ko_min, o->ko_max, o->first, o->works,
                sim_moves[o->move].heal, sim_moves[o->move].rank_type[0], sim_moves[o->move].rank_val[0],
                sim_moves[o->move].flags, o->fkey[0], o->fkey[1], o->fkey[2], o->fkey[3], o->fkey[4]);
    }
    fprintf(f, "]");
}

/* its first decision since it came out, however it came (the user-side rows' "first turn out" level: it fits the
   logged scores better than the engine's turns-out counter, which reads 0 only for a lead and 1 for a lead's second
   decision too) */
static int first_out(const Battle *b, int s) { return b->turn - b->v[s].entered == 1; }

static void dump_mon(FILE *f, const Battle *b, int s, const char *key)
{
    const Mon *m = &b->party[s][0];
    const Volatile *v = &b->v[s];
    int k;
    fprintf(f, "\"%s\": {\"species\": \"%s\", \"hp\": %d, \"maxhp\": %d, \"status\": %d, \"speed\": %d, \"types\": [%d, %d, %d], "
            "\"ability\": %d, \"item\": %d, \"confused\": %d, \"sub\": %d, \"turns_out\": %d, \"fresh\": %d, \"stage\": [",
            key, sim_species_name[m->species], m->hp, m->maxhp, m->status, sim_eff_speed(b, s), v->types[0], v->types[1],
            v->types[2], v->ability, m->item, v->confused, v->sub, v->turns_out, first_out(b, s));
    for (k = 0; k < 7; k++)
        fprintf(f, "%s%d", k ? ", " : "", v->stage[k]);
    fprintf(f, "]}");
}

/* side s's bench member i against the foe on the field: its best hit (max roll, % of the foe's HP) and the foe's best
   hit on it (% of its HP), each with the move's effectiveness */
static void bench_matchup(const Battle *b, int s, int i, int *mine, int *mine_eff, int *theirs, int *theirs_eff)
{
    const Mon *x = &b->party[s][i], *foe = &b->party[s ^ 1][0];
    Volatile vx;
    int k;
    memset(&vx, 0, sizeof vx);
    vx.types[0] = x->types[0], vx.types[1] = x->types[1], vx.types[2] = T_NONE;
    vx.ability = x->ability;
    *mine = *theirs = 0, *mine_eff = *theirs_eff = -1;
    for (k = 0; k < 4; k++) {
        DamageQ q;
        int mv = x->moves[k], d;
        if (mv && sim_moves[mv].cls != CLS_STATUS && foe->hp) {
            memset(&q, 0, sizeof q);
            q.a = x, q.d = foe, q.va = &vx, q.vd = &b->v[s ^ 1];
            q.a_active = 0, q.d_active = 1, q.sim = 1, q.roll = 100;
            q.weather = sim_weather(b), q.terrain = b->terrain;
            d = sim_damage(&q, mv) * hits_x10(&sim_moves[mv]) / 10 * 100 / foe->hp;
            if (d > *mine || *mine_eff < 0)
                *mine = d > *mine ? d : *mine, *mine_eff = q.type_eff > *mine_eff ? q.type_eff : *mine_eff;
        }
        mv = foe->moves[k];
        if (mv && sim_moves[mv].cls != CLS_STATUS && x->hp) {
            memset(&q, 0, sizeof q);
            q.a = foe, q.d = x, q.va = &b->v[s ^ 1], q.vd = &vx;
            q.a_active = 1, q.d_active = 0, q.sim = 1, q.roll = 100;
            q.weather = sim_weather(b), q.terrain = b->terrain;
            d = sim_damage(&q, mv) * hits_x10(&sim_moves[mv]) / 10 * 100 / x->hp;
            if (d > *theirs)
                *theirs = d;
            if (q.type_eff > *theirs_eff)
                *theirs_eff = q.type_eff;
        }
    }
}

static void dump_bench(FILE *f, const Battle *b, int s)
{
    int i, first = 1;
    fprintf(f, "\"bench\": [");
    for (i = 1; i < b->n[s]; i++) {
        const Mon *x = &b->party[s][i];
        int mine, me, theirs, te;
        if (!sim_alive(x))
            continue;
        bench_matchup(b, s, i, &mine, &me, &theirs, &te);
        fprintf(f, "%s{\"idx\": %d, \"set\": %d, \"species\": \"%s\", \"hp\": %d, \"maxhp\": %d, \"speed\": %d, "
                "\"mine\": %d, \"mine_eff\": %d, \"theirs\": %d, \"theirs_eff\": %d, \"types\": [%d, %d]}",
                first ? "" : ", ", i, x->set, sim_species_name[x->species], x->hp, x->maxhp, x->stat[STAT_SPE], mine, me,
                theirs, te, x->types[0], x->types[1]);
        first = 0;
    }
    fprintf(f, "]");
}

static void dump_field(FILE *f, const Battle *b, int s)
{
    fprintf(f, "\"weather\": %d, \"terrain\": %d, \"trick_room\": %d, \"my_side\": [%d, %d, %d, %d, %d], "
            "\"their_side\": [%d, %d, %d, %d, %d], \"trapped\": %d, \"can_switch\": %d",
            sim_weather(b), b->terrain, b->trick_room, b->side[s].spikes, b->side[s].tspikes, b->side[s].rocks,
            b->side[s].reflect, b->side[s].screen, b->side[s ^ 1].spikes, b->side[s ^ 1].tspikes, b->side[s ^ 1].rocks,
            b->side[s ^ 1].reflect, b->side[s ^ 1].screen, sim_trapped(b, s), sim_can_switch(b, s));
}

static void dump_scores(FILE *f, const char *key, const OrigScores *sc)
{
    int k;
    fprintf(f, "\"%s\": [", key);
    for (k = 0; k < sc->n; k++)
        fprintf(f, "%s[%d, %d]", k ? ", " : "", sc->move[k], sc->val[k]);
    fprintf(f, "], ");
}

void orig_dump_decision(FILE *f, const Battle *b, int s, int gi, int turn, int kind, int arg, const OrigScores *own,
                        const OrigScores *foe)
{
    OrigMove mv[4], fm[4];
    int k;
    orig_moves(b, s, mv);
    orig_moves(b, s ^ 1, fm);
    fprintf(f, "{\"t\": \"dec\", \"game\": %d, \"turn\": %d, \"side\": %d, \"kind\": \"%c\", \"arg\": %d, ",
            gi, turn, s, kind, arg);
    dump_scores(f, "scores", own);
    dump_scores(f, "foe_scores", foe);
    dump_mon(f, b, s, "me");
    fprintf(f, ", ");
    dump_mon(f, b, s ^ 1, "foe");
    fprintf(f, ", ");
    dump_field(f, b, s);
    fprintf(f, ", ");
    dump_moves(f, mv);
    fprintf(f, ", \"foe_best\": [");
    for (k = 0; k < 4; k++)
        fprintf(f, "%s[%d, %d, %d, %d]", k ? ", " : "", fm[k].move, fm[k].dmax, fm[k].eff, fm[k].first);
    fprintf(f, "], ");
    dump_bench(f, b, s);
    fprintf(f, "}\n");
}

void orig_dump_replace(FILE *f, const Battle *b, int s, int gi, int turn, int set)
{
    fprintf(f, "{\"t\": \"repl\", \"game\": %d, \"turn\": %d, \"side\": %d, \"set\": %d, ", gi, turn, s, set);
    dump_mon(f, b, s ^ 1, "foe");
    fprintf(f, ", ");
    dump_bench(f, b, s);
    fprintf(f, "}\n");
}


/* ---------------------------------------------------------------- the policy

   Overlay 11's structure, read from its code (qa/simulator_feasibility.md section 13): every (target, move) pair the
   move's target type allows is a row; in singles a move aimed at the user or its side has one row on the user, a move
   aimed at the foe one row on the foe, a field-wide move one row on each. A row's score is the sum of five factors;
   the move is drawn uniformly among the rows with the top score. A switch competes with that score when one of the
   switch rules fires; the replacement after a faint is a fixed ranking. The factor values are not decoded: both kinds
   of rows' values are learned from the rows aivsai logs, the foe rows' by level (foe_key); a parametrized model of the
   foe rows, fitted by origfit.py on the choices, answers a level the table lacks. */

typedef struct {
    u8 nv;
    u32 n;
    s8 val[24];
    u16 cnt[24];
} Dist;                         /* logged row values and their counts */
typedef struct {
    u16 move;
    s8 works, hp4, fresh;       /* -1: any (a backoff level) */
    Dist d;
} OrigSelf;
typedef struct {
    s8 key[5];                  /* foe_key's levels, -1: any (a backoff level) */
    Dist d;
} OrigFoe;
/* the random model's move-free levels (origfit.py --model random): a move's rows by its effect code, so a move the
   fit never saw still gets the rows of the moves that work alike; effect ORIG_ANY_EFFECT: any effect */
typedef struct {
    u8 foe;                     /* 0: the row on the user, 1: the row on the foe of a status move */
    s8 works;
    u16 effect;
    Dist d;
} OrigEff;
#define ORIG_ANY_EFFECT 0xFFFF
enum { P_KO, P_KO_PRIO, P_IMMUNE, P_WEAK_Q, P_SE4_BONUS, P_SE4_P, P_STATUS_FAILS, P_STATUS_NEG, P_SELF_WORKS,
       P_SELF_FAILS, P_R5, P_R6, P_R7_SE_EXIT, P_R7_IMM, P_R7_RES, P_R7_HIGH, ORIG_NP };
static const char *const orig_param_name[ORIG_NP] = { "ko", "ko_prio", "immune", "weak_q", "se4_bonus", "se4_p",
                                                      "status_fails", "status_neg", "self_works", "self_fails",
                                                      "r5", "r6", "r7_se_exit", "r7_imm", "r7_res", "r7_high" };
#include "origmodel.h"      /* origfit.py --model trainer: orig_param_default[], orig_self[], orig_foe[] and counts */
#include "origmodel_rand.h" /* origfit.py --model random: origr_param_default[], origr_self[], origr_foe[], origr_eff[] */

/* one fitted model: the trainer teams' (the gates' pools), or aivsai's random teams' (POOL_RANDOM), whose sets hold
   moves the trainer games never showed */
typedef struct {
    const OrigSelf *self;
    int nself;
    const OrigFoe *foe;
    int nfoe;
    const OrigEff *eff;
    int neff;
    const double *param_default;
    const char *env;            /* name=value,... overrides the fitted parameters (origfit.py tune) */
} OrigModel;
enum { MODEL_TRAINER, MODEL_RANDOM, NMODEL };
static const OrigModel orig_models[NMODEL] = {
    { orig_self, orig_nself, orig_foe, orig_nfoe, 0, 0, orig_param_default, "ORIG_PARAMS" },
    { origr_self, origr_nself, origr_foe, origr_nfoe, origr_eff, origr_neff, origr_param_default, "ORIG_PARAMS_RAND" },
};

static double OP[NMODEL][ORIG_NP];
static int op_ready;

static void params_init(void)
{
    int k, m;
    for (m = 0; m < NMODEL; m++) {
        const char *e = getenv(orig_models[m].env);
        memcpy(OP[m], orig_models[m].param_default, sizeof OP[m]);
        while (e && *e) {
            char name[32];
            double v;
            int n = 0;
            if (sscanf(e, "%31[^=]=%lf%n", name, &v, &n) != 2)
                break;
            for (k = 0; k < ORIG_NP; k++)
                if (!strcmp(name, orig_param_name[k]))
                    OP[m][k] = v;
            e += n;
            if (*e == ',')
                e++;
        }
    }
    op_ready = 1;
}

static u64 orng = 0x6F726967626F74ULL;

static u32 ornd(u64 *r, u32 n)
{
    u64 x = *r;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    *r = x;
    return n ? (u32)(((x * 0x2545F4914F6CDD1DULL) >> 32) % n) : 0;
}

u64 orig_rng_get(void) { return orng; }
void orig_rng_set(u64 r) { orng = r ? r : 1; }

static int pct(u64 *r, double p) { return ornd(r, 1000000) < p * 1000000; }

static int type_eff4(int type, const u8 *types)
{
    return sim_type_eff(type, types, 0);
}

/* P x 2^(eff - 7), P the base power (60 below 10): the replacement chooser's and the switch bonus's move value */
static int move_value(int mv, const u8 *foe_types)
{
    const MoveRec *m = &sim_moves[mv];
    int e = eff7(type_eff4(m->type, foe_types)), p = m->power < 10 ? 60 : m->power;
    return e >= 7 ? p << (e - 7) : p >> (7 - e);
}

/* the move-free level of a move's row: its effect code, then any effect (none in the trainer model) */
static const Dist *eff_dist(const OrigModel *m, int foe, int works, int effect)
{
    int i;
    const OrigEff *any = 0;
    for (i = 0; i < m->neff; i++) {
        const OrigEff *e = &m->eff[i];
        if (e->foe != foe || e->works != works)
            continue;
        if (e->effect == effect)
            return &e->d;
        if (e->effect == ORIG_ANY_EFFECT)
            any = e;
    }
    return any ? &any->d : 0;
}

/* the most specific level of a move's row on the user: the move with works, HP quarter and first turn out, the move
   with works, the move, then the move-free levels; 0: the self_works/self_fails parameter */
static const Dist *self_dist(const OrigModel *m, const OrigMove *o, int hp4, int fresh)
{
    int i;
    const OrigSelf *l1 = 0, *l0 = 0;
    for (i = 0; i < m->nself; i++) {
        const OrigSelf *e = &m->self[i];
        if (e->move != o->move)
            continue;
        if (e->works == o->works && e->hp4 == hp4 && e->fresh == fresh)
            return &e->d;
        if (e->works == o->works && e->hp4 < 0)
            l1 = e;
        if (e->works < 0)
            l0 = e;
    }
    if (l1 || l0)
        return l1 ? &l1->d : &l0->d;
    return eff_dist(m, 0, o->works, o->effect);
}

/* the table's most specific level for this key: the full key, then kind, KO and strongest, then the kind alone; a
   status move's move-free levels come first */
static const Dist *foe_dist(const OrigModel *m, const OrigMove *o)
{
    int i, j;
    const OrigFoe *l1 = 0, *l0 = 0;
    const Dist *d = o->cls == CLS_STATUS ? eff_dist(m, 1, o->works != 0, o->effect) : 0;
    if (d)
        return d;
    for (i = 0; i < m->nfoe; i++) {
        const OrigFoe *e = &m->foe[i];
        for (j = 0; j < 5 && e->key[j] == o->fkey[j]; j++)
            ;
        if (j == 5)
            return &e->d;
        if (j >= 3 && e->key[3] < 0)
            l1 = e;
        if (j >= 1 && e->key[1] < 0)
            l0 = e;
    }
    return l1 ? &l1->d : l0 ? &l0->d : 0;
}

static int dist_sample(const Dist *d, u64 *r)
{
    u32 x = ornd(r, d->n), k;
    for (k = 0; k < d->nv; k++) {
        if (x < d->cnt[k])
            return d->val[k];
        x -= d->cnt[k];
    }
    return d->val[d->nv - 1];
}

typedef struct {
    const double *op;           /* the model's parameters */
    OrigMove mv[4];
    int dmg[4][16];             /* one hit at each roll 85..100, times the usual hit count */
    int self_row[4], foe_row[4];
    const Dist *self[4];        /* the row's table level, 0: the parametrized model */
    const Dist *foe[4];
    int foe_hp;
    int nsw, sw_idx[5];         /* the switch candidates (party index) */
    int sw_bonus[5], sw_se[5], sw_absorb[5], sw_resist_last[5], sw_imm_last[5];
    int cur_se, cur_boost4, natural_cure, foe_last;
} Ctx;

static int self_sample(const Ctx *c, int k, u64 *r)
{
    if (!c->self[k])
        return c->mv[k].works ? (int)c->op[P_SELF_WORKS] : (int)c->op[P_SELF_FAILS];
    return dist_sample(c->self[k], r);
}

static int se_move(const Battle *b, int s, const Mon *x, const u8 *foe_types, int on_field)
{
    int k;
    for (k = 0; k < 4; k++) {
        int mv = x->moves[k];
        if (!mv || !x->pp[k] || (on_field && !sim_legal_move(b, s, k)))
            continue;
        if (sim_moves[mv].cls != CLS_STATUS && type_eff4(sim_moves[mv].type, foe_types) > 4)
            return 1;
    }
    return 0;
}

static int absorbs(int ability, int type)
{
    switch (ability) {
    case A_VOLTABSORB: case A_LIGHTNINGROD: case A_MOTORDRIVE: return type == T_ELECTRIC;
    case A_WATERABSORB: case A_STORMDRAIN: case A_DRYSKIN: return type == T_WATER;
    case A_FLASHFIRE: case A_WELLBAKEDBDY: return type == T_FIRE;
    case A_SAPSIPPER: return type == T_GRASS;
    case A_LEVITATE: case A_EARTHEATER: return type == T_GROUND;
    }
    return 0;
}

static void ctx_build(const Battle *b, int s, Ctx *c)
{
    const Mon *me = &b->party[s][0], *foe = &b->party[s ^ 1][0];
    const u8 *ft = b->v[s ^ 1].types;
    int k, r, i, hp4 = me->hp * 4 / (me->maxhp ? me->maxhp : 1), fresh = first_out(b, s), st = 0;
    const OrigModel *m = &orig_models[b->rand_team[s] ? MODEL_RANDOM : MODEL_TRAINER];
    memset(c, 0, sizeof *c);
    c->op = OP[m - orig_models];
    orig_moves(b, s, c->mv);
    c->foe_hp = foe->hp;
    if (hp4 > 4)
        hp4 = 4;
    for (k = 0; k < 4; k++) {
        OrigMove *o = &c->mv[k];
        int tt = o->target;
        if (!o->legal)
            continue;
        c->self_row[k] = tt == TG_USER || tt == TG_USER_OR_ALLY || tt == TG_USER_SIDE_MONS || tt == TG_USER_SIDE ||
                         tt == TG_ALL || tt == TG_FIELD || tt == TG_CURSE;
        c->foe_row[k] = tt == TG_OTHER || tt == TG_ENEMY || tt == TG_ALL_OTHERS || tt == TG_ALL_ENEMIES ||
                        tt == TG_RANDOM || tt == TG_ENEMY_SIDE || tt == TG_ALL || tt == TG_FIELD || tt == TG_CURSE;
        if (c->self_row[k])
            c->self[k] = self_dist(m, o, hp4, fresh);
        if (c->foe_row[k])
            c->foe[k] = foe_dist(m, o);
        if (o->cls != CLS_STATUS && sim_alive(foe)) {
            const MoveRec *m = &sim_moves[o->move];
            DamageQ q;
            int hx = m->hits_max <= 1 ? 10 : m->hits_min == m->hits_max ? 10 * m->hits_max : m->hits_min == 2 && m->hits_max == 5 ? 31 : 5 * (m->hits_min + m->hits_max);
            memset(&q, 0, sizeof q);
            q.a = me, q.d = foe, q.va = &b->v[s], q.vd = &b->v[s ^ 1];
            q.a_active = q.d_active = 1, q.sim = 1;
            q.weather = sim_weather(b), q.terrain = b->terrain;
            q.screen = o->cls == CLS_PHYSICAL ? b->side[s ^ 1].reflect || b->side[s ^ 1].veil : b->side[s ^ 1].screen || b->side[s ^ 1].veil;
            for (r = 0; r < 16; r++) {
                q.roll = 85 + r;
                c->dmg[k][r] = sim_damage(&q, o->move) * hx / 10;
            }
        }
    }
    /* the switch rules' inputs (R5-R7 and the bonus; R1-R4 need Perish Song, Wonder Guard or a Choice lock on a move
       with no power, left out) */
    if (!sim_can_switch(b, s) || sim_trapped(b, s) || !sim_alive(foe))
        return;
    c->cur_se = se_move(b, s, me, ft, 1);
    for (k = 0; k < 5; k++)
        st += b->v[s].stage[k] > 0 ? b->v[s].stage[k] : 0;
    c->cur_boost4 = st >= 4;
    c->natural_cure = b->v[s].ability == A_NATURALCURE && (me->status == ST_SLP || me->status == ST_FRZ) && me->hp * 2 >= me->maxhp;
    c->foe_last = b->v[s ^ 1].last_move;
    for (i = 1; i < b->n[s]; i++) {
        const Mon *x = &b->party[s][i];
        int best = 0, j = c->nsw, last = b->v[s].hit_by_move;
        if (!sim_alive(x))
            continue;
        c->sw_idx[j] = i;
        for (k = 0; k < 4; k++)
            if (x->moves[k] && x->pp[k] && sim_moves[x->moves[k]].power) {
                int v = move_value(x->moves[k], ft);
                best = v > best ? v : best;
            }
        c->sw_bonus[j] = best >= 240 ? 4 : best >= 200 ? 3 : best >= 160 ? 2 : 0;
        c->sw_se[j] = se_move(b, s, x, ft, 0);
        c->sw_absorb[j] = c->foe_last && absorbs(x->ability, sim_moves[c->foe_last].type);
        if (last) {
            u8 xt[3] = { x->types[0], x->types[1], T_NONE };
            int e = type_eff4(sim_moves[last].type, xt);
            c->sw_imm_last[j] = e == 0;
            c->sw_resist_last[j] = e > 0 && e < 4;
        }
        c->nsw++;
    }
}

/* one draw of the switch candidate's score (the best candidate's, 0 when none fires) and its party index */
static int switch_draw(const Ctx *c, u64 *r, int *pick)
{
    int j, best = 0, nbest = 0, sc[5];
    for (j = 0; j < c->nsw; j++) {
        int t = 0;
        /* R5: the foe's last move would be absorbed by the candidate's ability */
        if (c->sw_absorb[j] && !(c->cur_se && pct(r, 0.33)) && pct(r, c->op[P_R5]))
            t += pct(r, 0.85) ? 20 : 1;
        /* R6: Natural Cure while asleep or frozen at half HP or more */
        if (c->natural_cure && (c->foe_last ? c->sw_resist_last[j] : pct(r, 0.5)) && pct(r, c->op[P_R6]))
            t += pct(r, 0.7) ? 20 : 1;
        /* R7: no super-effective move here, the candidate has one, and it takes last turn's hit badly */
        if (!(c->cur_se && pct(r, c->op[P_R7_SE_EXIT])) && !c->cur_boost4 && c->sw_se[j] &&
            ((c->sw_imm_last[j] && pct(r, c->op[P_R7_IMM])) || (c->sw_resist_last[j] && pct(r, c->op[P_R7_RES]))))
            t += pct(r, c->op[P_R7_HIGH]) ? 20 : 1;
        if (t > 0)
            t += c->sw_bonus[j];
        sc[j] = t;
        if (t > best)
            best = t, nbest = 1;
        else if (t == best && t > 0)
            nbest++;
    }
    if (best <= 0)
        return 0;
    nbest = (int)ornd(r, (u32)nbest);
    for (j = 0; j < c->nsw; j++)
        if (sc[j] == best && !nbest--) {
            *pick = c->sw_idx[j];
            break;
        }
    return best;
}

/* the foe row of an attack: a draw from the logged values of its table level, or without one the parametrized model
   of the factors (immune, a knockout at this draw's roll, the strongest attack at this draw's rolls, a weaker one) */
static int foe_row_attack(const Ctx *c, int k, const int *d, int dmax_all, u64 *r)
{
    const OrigMove *o = &c->mv[k];
    int v = 0;
    if (c->foe[k])
        return dist_sample(c->foe[k], r);
    if (o->eff == 0)
        return (int)c->op[P_IMMUNE];
    if (d[k] >= c->foe_hp)
        return (int)c->op[P_KO] + (o->prio > 0 ? (int)c->op[P_KO_PRIO] : 0);
    if (d[k] < dmax_all && pct(r, c->op[P_WEAK_Q]))
        v -= 1;
    if (o->eff >= 16 && pct(r, c->op[P_SE4_P]))
        v += (int)c->op[P_SE4_BONUS];
    return v;
}

static int foe_row_status(const Ctx *c, int k, u64 *r)
{
    if (c->foe[k])
        return dist_sample(c->foe[k], r);
    if (!c->mv[k].works)
        return (int)c->op[P_STATUS_FAILS];
    return pct(r, c->op[P_STATUS_NEG]) ? -1 : 0;
}

/* one draw of the whole decision: 0..3 a move slot, 4 Struggle, 5 + i a switch to party index i */
static int draw(const Ctx *c, u64 *r)
{
    int k, d[4] = { 0 }, dmax_all = 0, best = -1000, nbest = 0, sc[8], sl[8], n = 0, pick = 0, sw;
    for (k = 0; k < 4; k++)
        if (c->mv[k].legal && c->mv[k].cls != CLS_STATUS) {
            d[k] = c->dmg[k][ornd(r, 16)];
            dmax_all = d[k] > dmax_all ? d[k] : dmax_all;
        }
    for (k = 0; k < 4; k++) {
        if (!c->mv[k].legal)
            continue;
        if (c->self_row[k])
            sc[n] = self_sample(c, k, r), sl[n++] = k;
        if (c->foe_row[k])
            sc[n] = c->mv[k].cls != CLS_STATUS ? foe_row_attack(c, k, d, dmax_all, r) :
                    c->self_row[k] ? self_sample(c, k, r) : foe_row_status(c, k, r), sl[n++] = k;
    }
    if (!n)
        sc[n] = 0, sl[n++] = 4;
    for (k = 0; k < n; k++)
        if (sc[k] > best)
            best = sc[k], nbest = 1;
        else if (sc[k] == best)
            nbest++;
    nbest = (int)ornd(r, (u32)nbest);
    for (k = 0; k < n; k++)
        if (sc[k] == best && !nbest--) {
            pick = sl[k];
            break;
        }
    if (best < -100)            /* the writer's floor: no move candidate beats -100 */
        best = -100;
    sw = switch_draw(c, r, &k);
    if (sw > 0 && (sw > best || (sw == best && ornd(r, 2))))
        return 5 + k;
    return pick;
}

#define NDRAW 400

void orig_choice(const Battle *b, int s, double p[11])
{
    Ctx c;
    u64 r = 0x9E3779B97F4A7C15ULL ^ ((u64)b->turn << 32) ^ (u64)b->party[s][0].hp ^ ((u64)b->party[s ^ 1][0].hp << 16);
    int i;
    if (!op_ready)
        params_init();
    ctx_build(b, s, &c);
    memset(p, 0, sizeof(double) * 11);
    for (i = 0; i < NDRAW; i++) {
        int a = draw(&c, &r);
        p[a] += 1.0 / NDRAW;
    }
}

int orig_replace_pick(const Battle *b, int s, double p[6])
{
    const Mon *foe = &b->party[s ^ 1][0];
    int i, k, best = -1000, pick = 0;
    memset(p, 0, sizeof(double) * 6);
    for (i = 1; i < b->n[s]; i++) {
        const Mon *x = &b->party[s][i];
        int v = 0;
        if (!sim_alive(x))
            continue;
        if (sim_alive(foe)) {
            u8 ft[3] = { foe->types[0], foe->types[1], T_NONE };
            for (k = 0; k < 4; k++)
                if (x->moves[k] && x->pp[k] && sim_moves[x->moves[k]].power) {
                    int w = move_value(x->moves[k], ft);
                    v = w > v ? w : v;
                }
        }
        if (v > best)
            best = v, pick = i;
    }
    if (pick)
        p[pick] = 1;
    return pick;
}

static Action orig_choose(Battle *b, int s, void *ctx)
{
    Ctx c;
    Action a = { ACT_MOVE, 4 };
    int x;
    if (!op_ready)
        params_init();
    ctx_build(b, s, &c);
    x = draw(&c, &orng);
    if (x >= 5)
        a.kind = ACT_SWITCH, a.idx = (u8)(x - 5);
    else
        a.idx = (u8)x;
    return a;
}

static int orig_replace(Battle *b, int s, void *ctx)
{
    double p[6];
    return orig_replace_pick(b, s, p);
}

static void orig_start(Battle *b, void *ctx)
{
    orng ^= b->rng * 0x9E3779B97F4A7C15ULL | 1;
}

const Policy policy_orig = { "orig", orig_choose, orig_replace, orig_start, 0 };
