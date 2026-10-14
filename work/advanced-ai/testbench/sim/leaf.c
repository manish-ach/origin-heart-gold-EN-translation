#include <string.h>
#include <math.h>
#include "sim.h"
#include "leaf.h"

/* the frozen judge of sim cf luck: ai_research_new's fit on 95,007 turn states of 4,000 rc27 self-play games
   (leaf/leaf_w_self.txt; held-out AUC 0.849), 18 feature weights then the intercept. sim cf luck --leaf-w W,... replaces
   them (a refit), and never during a run */
double g_leaf_w[LEAF_NF + 1] = { 0.4522, 0.5591, -0.0190, 0.0900, 0.0413, 0.1144, 0.3543, -0.2901, -0.6517, 0.4390,
                                 0.0192, 0.2717, 0.4849, 0.5559, -0.0472, 0.5119, -0.1638, 0.2365, -0.1650 };

static int hit(const Battle *b, const Mon *a, const Volatile *va, const Mon *d, const Volatile *vd, int move)
{
    const MoveRec *m = &sim_moves[move];
    DamageQ q;
    int v, acc = m->acc >= 101 ? 100 : m->acc, hits10;
    if (!move || m->cls == CLS_STATUS)
        return 0;
    memset(&q, 0, sizeof q);
    q.a = a, q.d = d, q.va = va, q.vd = vd;
    q.weather = sim_weather(b), q.terrain = b->terrain;
    q.roll = 92;
    v = sim_damage(&q, move);
    if (!q.type_eff)
        return 0;
    hits10 = m->hits_max <= 1 ? 10 : m->hits_min == m->hits_max ? 10 * m->hits_max : m->hits_min == 2 && m->hits_max == 5 ? 31 :
             5 * (m->hits_min + m->hits_max);
    return v * acc / 100 * hits10 / 10;
}

static void fresh(Volatile *v, const Mon *m)
{
    memset(v, 0, sizeof *v);
    v->types[0] = m->types[0], v->types[1] = m->types[1], v->types[2] = T_NONE;
    v->ability = m->ability;
}

void leaf_cache(const Battle *b, LeafCache *c)
{
    int s, i, j, k;
    memset(c, 0, sizeof *c);
    for (s = 0; s < 2; s++)
        for (i = 0; i < b->n[s]; i++) {
            const Mon *a = &b->party[s][i];
            Volatile va;
            fresh(&va, a);
            c->spe[s][a->set] = a->stat[4];
            for (j = 0; j < b->n[s ^ 1]; j++) {
                const Mon *d = &b->party[s ^ 1][j];
                Volatile vd;
                int best = 0, bp = 0;
                fresh(&vd, d);
                for (k = 0; k < 4; k++) {
                    int x = hit(b, a, &va, d, &vd, a->moves[k]);
                    if (x > best)
                        best = x, bp = sim_moves[a->moves[k]].prio;
                }
                c->dmg[s][a->set][d->set] = best;
                c->prio[s][a->set][d->set] = (s8)bp;
            }
        }
}

/* turns a needs to KO d at d's HP, 99 if never */
static int turns(s32 dmg, s32 hp) { return dmg <= 0 ? 99 : (hp + dmg - 1) / dmg; }

/* 1 if side s's Pokemon a beats the foe's d one on one at their HP now (a moves first on a tie of turns when faster) */
static int beats(const LeafCache *c, int s, const Mon *a, const Mon *d)
{
    int ta = turns(c->dmg[s][a->set][d->set], d->hp), td = turns(c->dmg[s ^ 1][d->set][a->set], a->hp);
    int pa = c->prio[s][a->set][d->set], pd = c->prio[s ^ 1][d->set][a->set];
    int first = pa != pd ? pa > pd : c->spe[s][a->set] > c->spe[s ^ 1][d->set];
    return ta < td || (ta == td && first && ta < 99);
}

void leaf_features(const Battle *b, const LeafCache *c, s32 *f)
{
    s32 H[2] = { 0, 0 }, N[2] = { 0, 0 }, ans[2] = { 0, 0 }, none[2] = { 0, 0 }, haz[2];
    int s, i, j;
    const Mon *a1 = &b->party[1][0], *a0 = &b->party[0][0];
    for (s = 0; s < 2; s++)
        for (i = 0; i < b->n[s]; i++)
            if (sim_alive(&b->party[s][i]))
                H[s] += 1000 * b->party[s][i].hp / b->party[s][i].maxhp, N[s]++;
    /* answers: the foe's Pokemon (alive) that some Pokemon of mine (alive) beats; none: those nothing of mine beats */
    for (s = 0; s < 2; s++)
        for (j = 0; j < b->n[s ^ 1]; j++) {
            const Mon *d = &b->party[s ^ 1][j];
            int any = 0;
            if (!sim_alive(d))
                continue;
            for (i = 0; i < b->n[s] && !any; i++)
                any = sim_alive(&b->party[s][i]) && beats(c, s, &b->party[s][i], d);
            ans[s] += any;
            none[s] += !any;
        }
    for (s = 0; s < 2; s++)
        haz[s] = (b->side[s].rocks + b->side[s].spikes + b->side[s].tspikes) * (N[s] > 1 ? N[s] - 1 : 0);
    memset(f, 0, sizeof(s32) * LEAF_NF);
    f[0] = H[1] - H[0];
    f[1] = 1000 * (N[1] - N[0]);
    if (sim_alive(a1) && sim_alive(a0)) {
        s32 d10 = c->dmg[1][a1->set][a0->set], d01 = c->dmg[0][a0->set][a1->set], t1, t0, faster;
        d10 = d10 * 64 / 64, d01 = d01 * 64 / 64;
        /* stat stages of the attacking stats change the race */
        {
            int st1 = b->v[1].stage[STAT_ATK] > b->v[1].stage[STAT_SPA] ? b->v[1].stage[STAT_ATK] : b->v[1].stage[STAT_SPA];
            int st0 = b->v[0].stage[STAT_ATK] > b->v[0].stage[STAT_SPA] ? b->v[0].stage[STAT_ATK] : b->v[0].stage[STAT_SPA];
            d10 = st1 >= 0 ? d10 * (2 + st1) / 2 : d10 * 2 / (2 - st1);
            d01 = st0 >= 0 ? d01 * (2 + st0) / 2 : d01 * 2 / (2 - st0);
        }
        t1 = turns(d10, a0->hp), t0 = turns(d01, a1->hp);
        faster = sim_eff_speed(b, 1) > sim_eff_speed(b, 0) ? 1 : -1;
        f[2] = 1000 * a1->hp / a1->maxhp;
        f[3] = 1000 * a0->hp / a0->maxhp;
        f[4] = t1 < t0 || (t1 == t0 && faster > 0) ? 1000 : -1000;
        f[5] = 1000 * faster;
        f[6] = d10 * 1000 / a0->hp > 1500 ? 1500 : d10 * 1000 / a0->hp;
        f[7] = d01 * 1000 / a1->hp > 1500 ? 1500 : d01 * 1000 / a1->hp;
    }
    f[8] = 1000 * (a1->status == ST_SLP || a1->status == ST_FRZ);
    f[9] = 1000 * (a0->status == ST_SLP || a0->status == ST_FRZ);
    f[10] = 1000 * (a1->status && a1->status != ST_SLP && a1->status != ST_FRZ);
    f[11] = 1000 * (a0->status && a0->status != ST_SLP && a0->status != ST_FRZ);
    f[12] = 250 * (b->v[1].stage[STAT_ATK] + b->v[1].stage[STAT_SPA] + b->v[1].stage[STAT_SPE]) -
            250 * (b->v[0].stage[STAT_ATK] + b->v[0].stage[STAT_SPA] + b->v[0].stage[STAT_SPE]);
    f[13] = 250 * (haz[0] - haz[1]);
    f[14] = 1000 * (ans[1] - ans[0]);
    f[15] = 1000 * (none[0] - none[1]);
    f[16] = N[1] && N[0] ? 1000 * (N[1] == 1) - 1000 * (N[0] == 1) : 0;
    f[17] = f[4] * (N[0] == 1 || N[1] == 1);
}

s32 leaf_value(const Battle *b, const LeafCache *c)
{
    s32 f[LEAF_NF];
    double z = g_leaf_w[LEAF_NF];
    int k;
    if (b->winner >= 0)
        return b->winner == 1 ? 1000 : b->winner == 0 ? 0 : 500;
    leaf_features(b, c, f);
    for (k = 0; k < LEAF_NF; k++)
        z += g_leaf_w[k] * f[k] / 1000.0;
    return (s32)(1000.0 / (1.0 + exp(-z)));
}
