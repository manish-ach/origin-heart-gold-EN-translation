#include <string.h>
#include "sim.h"
#include "policy.h"
#include "lapol.h"

u64 la_mix(u64 x)
{
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}

/* ---------------------------------------------------------------- greedy plus a switch out of a sure KO */

static int hit(const Battle *b, const Mon *a, const Volatile *va, const Mon *d, const Volatile *vd, int move, int roll)
{
    const MoveRec *m = &sim_moves[move];
    DamageQ q;
    int v;
    if (!move || m->cls == CLS_STATUS)
        return 0;
    memset(&q, 0, sizeof q);
    q.a = a, q.d = d, q.va = va, q.vd = vd;
    q.a_active = q.d_active = 1;
    q.weather = sim_weather(b), q.terrain = b->terrain;
    q.roll = roll;
    v = sim_damage(&q, move);
    return q.type_eff ? v * (m->hits_min ? m->hits_min : 1) : 0;
}

static void fresh(Volatile *v, const Mon *m)
{
    memset(v, 0, sizeof *v);
    v->types[0] = m->types[0], v->types[1] = m->types[1], v->types[2] = T_NONE;
    v->ability = m->ability;
}

/* The foe's strongest legal hit on (m, v) at roll r (0 when it has none), and that move's priority */
static int foe_best(const Battle *b, int s, const Mon *m, const Volatile *v, int roll, int *prio)
{
    const Mon *f = &b->party[s ^ 1][0];
    int k, best = 0;
    for (k = 0; k < 4; k++)
        if (sim_legal_move(b, s ^ 1, k)) {
            int x = hit(b, f, &b->v[s ^ 1], m, v, f->moves[k], roll);
            if (x > best) {
                best = x;
                if (prio)
                    *prio = sim_moves[f->moves[k]].prio;
            }
        }
    return best;
}

static Action gswitch_choose(Battle *b, int s, void *ctx)
{
    Action a = policy_greedy.choose(b, s, 0);
    const Mon *me = &b->party[s][0], *foe = &b->party[s ^ 1][0];
    int fprio = 0, foe_ko, my_ko = 0, foe_first, i, pick = 0, pick_frac = 1000;
    if (!sim_alive(foe) || !sim_can_switch(b, s))
        return a;
    foe_ko = foe_best(b, s, me, &b->v[s], 85, &fprio) >= me->hp;
    if (!foe_ko)
        return a;
    if (a.kind == ACT_MOVE && a.idx < 4)
        my_ko = hit(b, me, &b->v[s], foe, &b->v[s ^ 1], me->moves[a.idx], 85) >= foe->hp;
    {
        int myprio = a.kind == ACT_MOVE && a.idx < 4 ? sim_moves[me->moves[a.idx]].prio : 0;
        int ms = sim_eff_speed(b, s), fs = sim_eff_speed(b, s ^ 1);
        foe_first = fprio != myprio ? fprio > myprio : b->trick_room ? fs <= ms : fs >= ms;
    }
    if (my_ko && !foe_first)
        return a;
    /* the bench member that takes the smallest share of its HP from the foe's strongest hit, if it survives it */
    for (i = 1; i < b->n[s]; i++) {
        const Mon *m = &b->party[s][i];
        Volatile v;
        int frac;
        if (!sim_alive(m))
            continue;
        fresh(&v, m);
        frac = foe_best(b, s, m, &v, 100, 0) * 1000 / m->hp;
        if (frac < pick_frac)
            pick_frac = frac, pick = i;
    }
    if (pick) {
        a.kind = ACT_SWITCH;
        a.idx = (u8)pick;
    }
    return a;
}

static int gswitch_replace(Battle *b, int s, void *ctx) { return policy_greedy.replace(b, s, 0); }

const Policy policy_gswitch = { "gswitch", gswitch_choose, gswitch_replace, 0, 0 };

/* ---------------------------------------------------------------- greedy that takes a sure KO first (gko), and gko with a
   careful switch (gsw2): out only when the foe KOs first and this Pokemon cannot, into a member that survives the foe's
   strongest hit and hits back for half the foe's HP or more */

static Action gko_choose(Battle *b, int s, void *ctx)
{
    Action a = policy_greedy.choose(b, s, 0);
    const Mon *me = &b->party[s][0], *foe = &b->party[s ^ 1][0];
    int k, bk = -1, bprio = -99, bacc = -1;
    if (!sim_alive(foe))
        return a;
    for (k = 0; k < 4; k++)
        if (sim_legal_move(b, s, k)) {
            int mv = me->moves[k], prio = sim_moves[mv].prio, acc = sim_moves[mv].acc;
            if (hit(b, me, &b->v[s], foe, &b->v[s ^ 1], mv, 85) < foe->hp)
                continue;
            if (prio > bprio || (prio == bprio && acc > bacc))
                bk = k, bprio = prio, bacc = acc;
        }
    if (bk >= 0)
        a.kind = ACT_MOVE, a.idx = (u8)bk;
    return a;
}

static Action gsw2_choose(Battle *b, int s, void *ctx)
{
    Action a = gko_choose(b, s, 0);
    const Mon *me = &b->party[s][0], *foe = &b->party[s ^ 1][0];
    int fprio = 0, myprio, ms, fs, foe_first, i, pick = 0, pick_v = -1000000;
    if (!sim_alive(foe) || !sim_can_switch(b, s) || a.kind != ACT_MOVE || a.idx >= 4)
        return a;
    if (foe_best(b, s, me, &b->v[s], 85, &fprio) < me->hp)
        return a;
    myprio = sim_moves[me->moves[a.idx]].prio;
    ms = sim_eff_speed(b, s), fs = sim_eff_speed(b, s ^ 1);
    foe_first = fprio != myprio ? fprio > myprio : b->trick_room ? fs <= ms : fs >= ms;
    if (!foe_first && hit(b, me, &b->v[s], foe, &b->v[s ^ 1], me->moves[a.idx], 85) >= foe->hp)
        return a;
    for (i = 1; i < b->n[s]; i++) {
        const Mon *m = &b->party[s][i];
        Volatile v;
        int took, give, k;
        if (!sim_alive(m))
            continue;
        fresh(&v, m);
        took = foe_best(b, s, m, &v, 100, 0);
        if (took >= m->hp)
            continue;
        for (give = 0, k = 0; k < 4; k++) {
            int x = hit(b, m, &v, foe, &b->v[s ^ 1], m->moves[k], 92);
            give = x > give ? x : give;
        }
        if (2 * give < foe->hp)
            continue;
        if (give * 1000 / foe->hp - took * 1000 / m->hp > pick_v)
            pick_v = give * 1000 / foe->hp - took * 1000 / m->hp, pick = i;
    }
    if (pick)
        a.kind = ACT_SWITCH, a.idx = (u8)pick;
    return a;
}

const Policy policy_gko = { "gko", gko_choose, gswitch_replace, 0, 0 };
const Policy policy_gsw2 = { "gsw2", gsw2_choose, gswitch_replace, 0, 0 };

const Policy *la_policy(int pol)
{
    return pol == LA_POL_GSWITCH ? &policy_gswitch : pol == LA_POL_GKO ? &policy_gko : pol == LA_POL_GSW2 ? &policy_gsw2 :
           &policy_greedy;
}

/* ---------------------------------------------------------------- the leaf */

/* side s's strongest hit on the foe on the field: the mean roll times accuracy */
static int best_hit(const Battle *b, int s)
{
    const Mon *me = &b->party[s][0], *foe = &b->party[s ^ 1][0];
    int k, best = 0;
    for (k = 0; k < 4; k++)
        if (sim_legal_move(b, s, k)) {
            int mv = me->moves[k], acc = sim_moves[mv].acc >= 101 ? 100 : sim_moves[mv].acc;
            int x = hit(b, me, &b->v[s], foe, &b->v[s ^ 1], mv, 92) * acc / 100;
            if (x > best)
                best = x;
        }
    return best;
}

/* LA_EVAL_RACE: the two Pokemon on the field race with their strongest hits, the faster first; the loser's HP counts
   as 0 and the winner keeps what the race leaves it. The other Pokemon count their HP as in LA_EVAL_HP. */
static void race(const Battle *b, int hp[2])
{
    int d[2], n[2], first1, s;
    for (s = 0; s < 2; s++)
        d[s] = best_hit(b, s);
    for (s = 0; s < 2; s++)
        n[s] = d[s] ? (hp[s ^ 1] + d[s] - 1) / d[s] : 9999;
    if (n[0] == 9999 && n[1] == 9999)
        return;
    {
        int s0 = sim_eff_speed(b, 0), s1 = sim_eff_speed(b, 1);
        first1 = b->trick_room ? s1 < s0 : s1 > s0;
    }
    s = n[1] < n[0] || (n[1] == n[0] && first1) ? 1 : 0;   /* the race's winner */
    {
        int hits = n[s] - ((s == 1) == first1 ? 1 : 0);
        hp[s] -= hits * d[s ^ 1];
        if (hp[s] < 1)
            hp[s] = 1;
        hp[s ^ 1] = 0;
    }
}

s32 la_leaf(const Battle *b, int eval)
{
    s32 h[2] = { 0, 0 };
    int s, i, hp[2] = { b->party[0][0].hp, b->party[1][0].hp };
    if (b->winner >= 0)
        return b->winner == 1 ? 1000 : b->winner == 0 ? 0 : 500;
    if (eval == LA_EVAL_RACE && hp[0] && hp[1])
        race(b, hp);
    for (s = 0; s < 2; s++)
        for (i = 0; i < b->n[s]; i++) {
            const Mon *m = &b->party[s][i];
            int now = i == 0 ? hp[s] : m->hp;
            if (now <= 0)
                continue;
            h[s] += eval == LA_EVAL_COUNT ? 1000 : eval == LA_EVAL_MIX ? 500 + 500 * now / m->maxhp :
                    1000 * now / m->maxhp;
        }
    return h[0] + h[1] ? 1000 * h[1] / (h[0] + h[1]) : 500;
}

/* ---------------------------------------------------------------- the decision */

typedef struct {
    const Policy *inner;
    int force;
    Action a;
    LaWork *cnt;
} Side1;

static Action la_choose(Battle *b, int s, void *ctx)
{
    Side1 *x = ctx;
    if (x->force) {
        x->force = 0;
        return x->a;
    }
    x->cnt->calls++;
    return x->inner->choose(b, s, x->inner->ctx);
}

static int la_replace(Battle *b, int s, void *ctx)
{
    Side1 *x = ctx;
    x->cnt->calls++;
    return x->inner->replace(b, s, x->inner->ctx);
}

/* pol0, pol1: each side's policy inside the playouts (the DS build: la_policy(c->pol) for both) */
void la_decide(const Battle *root, const Action *alt, int nalt, const LaCfg *c, const Policy *pol0, const Policy *pol1,
               Battle *work, s32 *w, LaWork *cnt)
{
    u64 base = (u64)c->base_hi << 32 | c->base_lo;
    int i, k;
    for (i = 0; i < nalt; i++) {
        w[i] = 0;
        for (k = 0; k < c->n; k++) {
            Side1 x0 = { pol0, 0, { 0, 0 }, cnt }, x1 = { pol1, 1, alt[i], cnt };
            Policy p0 = { "la0", la_choose, la_replace, 0, &x0 }, p1 = { "la1", la_choose, la_replace, 0, &x1 };
            int t = 0;
            *work = *root;
            work->verbose = 0;
            work->rng = la_mix(base + (u64)k) | 1;
            while (work->winner < 0 && work->turn < c->max_turns && (!c->depth || t < c->depth)) {
                t++;
                if (!sim_turn(work, &p0, &p1))
                    break;
            }
            cnt->turns += work->turn - root->turn;
            w[i] += work->winner < 0 && work->turn >= c->max_turns ? 500 : la_leaf(work, c->eval);
        }
    }
}
