/* sim validate OBS [--ai] [--game N] [--orig-dump F] [--orig-eval F]: the turn-level validator. OBS is
   tools/sim/turnlog.py's file: the emulator's logged games as turns (the state at each turn's start, both decisions
   with their option values, the battle's messages as facts grouped by action). Each game is replayed from its teams with the logged actions:
   - at each turn's start the Pokemon on the field, their HP, status, confusion and stat stages and the weather are set
     to the log's, and every difference from what the simulator carried over from the turn before is reported (drift);
   - the order the log shows is graded against the simulator's (priority, Speed, ties, Quick Claw) and then played;
   - every random decision goes through the oracle (internal.h Oracle): it takes the outcome the log shows (a miss, a
     crit, the damage, a secondary effect, a full paralysis, a wake-up...) and records the model's probability of it;
     an outcome the model gives probability 0 is reported, and the rest feed the rate table;
   - each hit's logged damage is checked against the 16 rolls (with the logged crit), and the logged damage is dealt;
   - after the turn, what the simulator did (statuses, confusion, stat changes, faints, send-ins, weather, terrain,
     items used, Protect, misses, failures) is compared with the log's facts, both ways.
   With --ai the advanced AI also decides each logged decision in the replayed state, and its option values are
   compared with the logged ones (the value check; only decisions the log gives options for). Side 1, the trainer's,
   is told side 0's logged action first, as the DS's trainer side reads the player's committed action (VAL_READ=0:
   blind). VAL_PARITY=FILE writes one JSON line per such decision and replacement (logged options, the host's, both
   parties' sets and HP; tools/sim/parity.py reads it), VAL_ROLL=N adds at each disagreement the win rates of N games
   from there with the DS's choice and with the host's (the same N lucks; side 0's logged action kept for that turn,
   then the original-AI model against the advanced AI), VAL_SEED=k another replay luck (the AI's foresight cells).
   On adv-vs-orig logs (turnlog.py --orig, the original AI on side 0)
   --orig-dump FILE writes the original-AI model's inputs at side 0's logged decisions and replacements, and
   --orig-eval FILE the model's probabilities there (origbot.c; tools/sim/origfit.py reads both).
   Output: one JSON line per finding, then the rate table and a summary (tools/sim/validate.py reads them). */
#include <math.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sim.h"
#include "sim_ids.h"
#include "internal.h"
#include "policy.h"
#include "origbot.h"

const void *host_debug(int side);

/* the facts, in tools/sim/turnlog.py FACTS order */
enum { F_HIT, F_CRIT, F_MISS, F_FAIL, F_NOEFFECT, F_PROTECTED, F_PROTECT, F_NHITS, F_FAINT, F_STATUS, F_CONFUSE,
       F_STAT, F_WAKE, F_ASLEEP, F_FULLPARA, F_FLINCH, F_CONFUSED, F_SELFHIT, F_CONFEND, F_FROZEN, F_THAW, F_QUICK,
       F_ITEM, F_ABILITY, F_WEATHER, F_WEATHER_END, F_TERRAIN, F_TERRAIN_END, F_HAZARD, F_HAZARD_HIT, F_CHIP,
       F_HEAL, F_SENDIN, F_RECALL, F_OTHER, F_EVOLVE, F_SUB, F_TAILWIND, F_SCREEN, F_TRICKROOM, F_FATIGUE, F_BIND,
       F_SEEDED, F_YAWN, F_TAUNT, F_TRANSFORM, F_PERISH, F_STRUGGLE, F_STATFAIL };
enum { SG_ACT, SG_SWITCH, SG_REPL, SG_PRE };
#define MAXF 64
#define MAXSEG 40
#define MAXOPT 16
#define MAXNOTE 128

typedef struct { s16 code, side, a, b, c; u8 used; } Fact;
typedef struct { int side, kind, slot, prio, speed; } Act2;
typedef struct { s16 kind, arg; s8 side; u8 used; int nf; Fact f[MAXF]; int nopt, more; s16 ok[MAXOPT], oa[MAXOPT]; int ov[MAXOPT]; } Seg;
typedef struct { int kind, arg, nopt, more, strong, sw_set, sw_w; s16 ok[MAXOPT], oa[MAXOPT]; int ov[MAXOPT];
                 OrigScores sc, fsc; } Act;      /* the original AI's logged rows: its 'scores' line, the rows on the foe */
typedef struct { int set, hp, maxhp, status, toxic, confused; s8 stage[7]; } St;
typedef struct { int n, weather, wturns, has_st[2], has_act[2], nseg; St st[2]; Act act[2]; Seg seg[MAXSEG]; } TurnObs;
typedef struct { char path[320]; int level, winner, team[2], n[2], slots[2][6], nturn, cap; TurnObs *t;
                 int mteam[2][6], mslot[2][6], nmember[2]; } GameObs;    /* each member's source team and slot */
typedef struct { s16 code, side, a, c, seg; } Note;

/* ---------------------------------------------------------------- reading */

static int read_game(FILE *f, GameObs *g)
{
    char line[512], kind[16];
    TurnObs *t = 0;
    Seg *sg = 0;
    Act *ac = 0;
    int got = 0;
    g->nturn = 0;
    while (fgets(line, sizeof line, f)) {
        if (sscanf(line, "%15s", kind) != 1)
            continue;
        if (!strcmp(kind, "game")) {
            sscanf(line, "game %319s %d %d", g->path, &g->level, &g->winner);
            got = 1;
        } else if (!strcmp(kind, "team")) {
            int s, idx, n, k, off;
            char *p = line + 5;
            sscanf(p, "%d %d %d%n", &s, &idx, &n, &off);
            p += off;
            g->team[s] = idx, g->n[s] = n;
            for (k = 0; k < n && k < 6; k++) {
                g->slots[s][k] = (int)strtol(p, &p, 10);
                g->mteam[s][k] = idx, g->mslot[s][k] = g->slots[s][k];
            }
            g->nmember[s] = 0;
        } else if (!strcmp(kind, "member")) {          /* a mixed team: member k's source */
            int s, idx, slot;
            sscanf(line, "member %d %d %d", &s, &idx, &slot);
            if (g->nmember[s] < 6)
                g->mteam[s][g->nmember[s]] = idx, g->mslot[s][g->nmember[s]++] = slot;
        } else if (!strcmp(kind, "turn")) {
            if (g->nturn == g->cap)
                g->t = realloc(g->t, sizeof *g->t * (size_t)(g->cap = g->cap ? 2 * g->cap : 64));
            t = &g->t[g->nturn++];
            memset(t, 0, sizeof *t);
            sscanf(line, "turn %d %d %d", &t->n, &t->weather, &t->wturns);
            sg = 0, ac = 0;
        } else if (!strcmp(kind, "state") && t) {
            int s, v[13], k;
            sscanf(line, "state %d %d %d %d %d %d %d %d %d %d %d %d %d %d", &s, &v[0], &v[1], &v[2], &v[3], &v[4], &v[5],
                   &v[6], &v[7], &v[8], &v[9], &v[10], &v[11], &v[12]);
            St *st = &t->st[s];
            t->has_st[s] = 1;
            st->set = v[0], st->hp = v[1], st->maxhp = v[2], st->status = v[3], st->toxic = v[4], st->confused = v[5];
            for (k = 0; k < 7; k++)
                st->stage[k] = (s8)v[6 + k];
        } else if (!strcmp(kind, "act") && t) {
            int s, arg;
            char k;
            sscanf(line, "act %d %c %d", &s, &k, &arg);
            ac = &t->act[s];
            memset(ac, 0, sizeof *ac);
            t->has_act[s] = 1;
            ac->kind = k, ac->arg = arg;
            sg = 0;
        } else if (!strcmp(kind, "opt") && t) {
            int k, a, v;
            sscanf(line, "opt %d %d %d", &k, &a, &v);
            if (sg && sg->nopt < MAXOPT)
                sg->ok[sg->nopt] = k, sg->oa[sg->nopt] = a, sg->ov[sg->nopt++] = v;
            else if (ac && ac->nopt < MAXOPT)
                ac->ok[ac->nopt] = k, ac->oa[ac->nopt] = a, ac->ov[ac->nopt++] = v;
        } else if ((!strcmp(kind, "osc") || !strcmp(kind, "fsc")) && t) {
            int mv, v;
            OrigScores *sc = ac ? (kind[0] == 'o' ? &ac->sc : &ac->fsc) : 0;
            sscanf(line + 4, "%d %d", &mv, &v);
            if (sc && sc->n < 4)
                sc->move[sc->n] = (short)mv, sc->val[sc->n++] = (short)v;
        } else if (!strcmp(kind, "more") && t) {
            int m, st, sw, w;
            sscanf(line, "more %d %d %d %d", &m, &st, &sw, &w);
            if (sg)
                sg->more = m;
            else if (ac)
                ac->more = m, ac->strong = st, ac->sw_set = sw, ac->sw_w = w;
        } else if (!strcmp(kind, "seg") && t) {
            char k[16];
            int s, arg;
            sscanf(line, "seg %15s %d %d", k, &s, &arg);
            if (t->nseg == MAXSEG) {
                sg = &t->seg[MAXSEG - 1];       /* overflow: facts join the last segment */
                continue;
            }
            sg = &t->seg[t->nseg++];
            memset(sg, 0, sizeof *sg);
            sg->kind = !strcmp(k, "act") ? SG_ACT : !strcmp(k, "switch") ? SG_SWITCH : !strcmp(k, "repl") ? SG_REPL : SG_PRE;   /* pre, end */
            sg->side = (s8)s, sg->arg = (s16)arg;
            ac = 0;
        } else if (!strcmp(kind, "f") && t) {
            int c, s, a, b2, c2;
            if (!sg) {
                if (t->nseg == MAXSEG)
                    continue;
                sg = &t->seg[t->nseg++];
                memset(sg, 0, sizeof *sg);
                sg->kind = SG_PRE, sg->side = -1;
            }
            sscanf(line, "f %d %d %d %d %d", &c, &s, &a, &b2, &c2);
            if (sg->nf < MAXF) {
                Fact *x = &sg->f[sg->nf++];
                x->code = c, x->side = s, x->a = a, x->b = b2, x->c = c2, x->used = 0;
            }
        } else if (!strcmp(kind, "endgame"))
            return got;
    }
    return 0;
}

/* ---------------------------------------------------------------- the oracle */

typedef struct {
    long n, yes;            /* decisions, outcomes "yes" */
    double exp;             /* sum of the model's probability of "yes" */
} Rate;

#define NBUCKET 12
typedef struct {
    Oracle base;
    GameObs *g;
    int gi, ti;
    TurnObs *T;
    Seg *cur;               /* the segment of the action being played, 0 at the end of the turn */
    int hit_i;              /* hits dealt in the current move */
    Note note[MAXNOTE];
    int nnote;
    int quiet;              /* no findings (a turn the simulator cannot follow) */
    long zero[K_N], decisions[K_N];
    Rate rate[K_N][NBUCKET];
    double bucket_p[K_N][NBUCKET];
    int nb[K_N];
    long hits, hits_exact, hits_clamp, hits_out, hits_unmatched;
    int selfhit[2];
    int moody_up;
} Val;

static Val V;
static const char *KNAME[K_N] = { "tie", "quick", "accuracy", "ohko", "crit", "hits", "secondary", "stat_chance", "flinch",
                                  "contact", "spore", "focusband", "wake", "thaw", "full_para", "conf_end", "conf_hit",
                                  "protect", "shedskin", "moody", "lock_end", "bind_len", "phaze", "metronome",
                                  "sleeptalk", "roll", "moody_down", "acupressure", "call" };

static void finding(const char *cat, const char *fmt, ...)
{
    va_list ap;
    if (V.quiet)
        return;
    printf("{\"g\": %d, \"t\": %d, \"cat\": \"%s\"", V.gi, V.T ? V.T->n : 0, cat);
    if (fmt && *fmt) {
        printf(", ");
        va_start(ap, fmt);
        vprintf(fmt, ap);
        va_end(ap);
    }
    printf("}\n");
}

static void rate_add(int kind, double p, int outcome)
{
    int k, n = V.nb[kind];
    for (k = 0; k < n; k++)
        if (fabs(V.bucket_p[kind][k] - p) < 1e-9)
            break;
    if (k == n) {
        if (n == NBUCKET)
            k = NBUCKET - 1;        /* overflow: the last bucket */
        else
            V.bucket_p[kind][k] = p, V.nb[kind]++;
    }
    V.rate[kind][k].n++;
    V.rate[kind][k].yes += outcome;
    V.rate[kind][k].exp += p;
}

/* the facts of segment sg (or the whole turn when sg is 0) with this code and side (-1: any side); first unused */
static Fact *find(Seg *sg, int code, int side)
{
    int i, k;
    if (sg) {
        for (k = 0; k < sg->nf; k++)
            if (sg->f[k].code == code && (side < 0 || sg->f[k].side == side) && !sg->f[k].used)
                return &sg->f[k];
        return 0;
    }
    for (i = 0; i < V.T->nseg; i++) {
        Fact *x = find(&V.T->seg[i], code, side);
        if (x)
            return x;
    }
    return 0;
}

/* the action segment of side s this turn (a move, a stopped move or a switch) */
static Seg *action_seg(int s)
{
    int i;
    for (i = 0; i < V.T->nseg; i++)
        if ((V.T->seg[i].kind == SG_ACT || V.T->seg[i].kind == SG_SWITCH) && V.T->seg[i].side == s)
            return &V.T->seg[i];
    return 0;
}

static int nth_hit(Seg *sg, int i)
{
    int k, n = 0;
    for (k = 0; sg && k < sg->nf; k++)
        if (sg->f[k].code == F_HIT && n++ == i)
            return k;
    return -1;
}

static int hits_in(Seg *sg)
{
    int k, n = 0;
    for (k = 0; sg && k < sg->nf; k++)
        n += sg->f[k].code == F_HIT;
    return n;
}

static Battle *VB;
static int cur_move(void) { return V.cur && V.cur->kind == SG_ACT ? V.cur->arg : 0; }

static void zero_detail(int kind, int side, double p, int outcome)
{
    const Mon *u = side >= 0 ? &VB->party[side][0] : 0, *f = side >= 0 ? &VB->party[side ^ 1][0] : 0;
    finding("zero", "\"kind\": \"%s\", \"side\": %d, \"p\": %.4f, \"outcome\": %d, \"mon\": \"%s\", \"foe\": \"%s\", "
            "\"move\": \"%s\", \"ability\": \"%s\", \"item\": \"%s\"", KNAME[kind], side, p, outcome,
            u ? sim_species_name[u->species] : "", f ? sim_species_name[f->species] : "", sim_move_name[cur_move()],
            u ? sim_ability_name[VB->v[side].ability] : "", u ? sim_item_name[u->item] : "");
}

static int grade(int kind, int side, double p, int outcome)
{
    static int detail = -1;
    V.decisions[kind]++;
    rate_add(kind, p, outcome);
    if (detail < 0)
        detail = getenv("VAL_DECISIONS") != 0;
    if (detail && p > 0 && p < 1 && side >= 0) {     /* every graded decision, for rates by context */
        const Mon *u = &VB->party[side][0], *f = &VB->party[side ^ 1][0];
        finding("decision", "\"kind\": \"%s\", \"p\": %.4f, \"outcome\": %d, \"mon\": \"%s\", \"move\": \"%s\", "
                "\"ability\": \"%s\", \"item\": \"%s\", \"fability\": \"%s\", \"fitem\": \"%s\"", KNAME[kind], p, outcome,
                sim_species_name[u->species], sim_move_name[cur_move()], sim_ability_name[VB->v[side].ability],
                sim_item_name[u->item], sim_ability_name[VB->v[side ^ 1].ability], sim_item_name[f->item]);
    }
    if ((outcome && p <= 1e-12) || (!outcome && p >= 1 - 1e-12)) {
        V.zero[kind]++;
        zero_detail(kind, side, p, outcome);
    }
    return outcome;
}

static int o_yes(Oracle *o, Battle *b, int kind, int side, double p)
{
    Seg *sg = V.cur;
    Fact *x = 0;
    int out;
    (void)o;
    switch (kind) {
    case K_ACC: case K_OHKO:
        if (!sg)
            break;
        x = find(sg, F_MISS, side ^ 1);
        if (x)
            x->used = 1;
        return grade(kind, side, p, !x);
    case K_CRIT: {
        int k = nth_hit(sg, V.hit_i);
        if (k < 0)
            break;
        return grade(kind, side, p, sg->f[k].c != 0);
    }
    case K_SICK: {        /* the move's condition (o->arg, WP_SICK numbering) on the target */
        int a = o->arg, code = a >= SICK_PAR && a <= SICK_PSN ? F_STATUS : a == SICK_CONFUSION ? F_CONFUSE :
                a == SICK_BIND ? F_BIND : a == SICK_LEECH_SEED ? F_SEEDED : a == SICK_YAWN ? F_YAWN : a == SICK_TAUNT ? F_TAUNT : -1;
        int k;
        if (!sg)
            break;
        for (k = 0; k < sg->nf && !x; k++)
            if (sg->f[k].code == code && sg->f[k].side == side &&
                (code != F_STATUS || sg->f[k].a == (a == SICK_PSN ? sg->f[k].a : a == SICK_PAR ? 1 : a == SICK_SLP ? 2 : a == SICK_FRZ ? 3 : 4)))
                x = &sg->f[k];
        return grade(kind, side, p, x != 0);
    }
    case K_RANK: {        /* that stat (o->arg: rank type 1-7, 9 all; x16: lowered) changed on that side */
        int t = o->arg & 15, down = o->arg >> 4, k;
        if (!sg)
            break;
        for (k = 0; k < sg->nf && !x; k++)
            if (sg->f[k].code == F_STAT && sg->f[k].side == side && (t == 9 || sg->f[k].a == t - 1) && (sg->f[k].b < 0) == down)
                x = &sg->f[k];
        return grade(kind, side, p, x != 0);
    }
    case K_FLINCH: {
        Seg *t = action_seg(side);
        return grade(kind, side, p, t && find(t, F_FLINCH, side));
    }
    case K_CONTACT:
        if (!sg)
            break;
        return grade(kind, side, p, find(sg, F_STATUS, side) != 0);
    case K_FOCUSBAND:
        if (!sg)
            break;
        x = find(sg, F_ITEM, side);
        return grade(kind, side, p, x && x->a == I_FOCUSBAND);
    case K_WAKE:
        if (!sg)
            break;
        if (find(sg, F_WAKE, side))
            return grade(kind, side, p, 1);
        return grade(kind, side, p, 0);
    case K_THAW:
        if (!sg)
            break;
        return grade(kind, side, p, find(sg, F_THAW, side) != 0);
    case K_PARA:
        if (!sg)
            break;
        return grade(kind, side, p, find(sg, F_FULLPARA, side) != 0);
    case K_CONF_END:
        if (!sg)
            break;
        return grade(kind, side, p, find(sg, F_CONFEND, side) != 0);
    case K_CONF_HIT:
        if (!sg)
            break;
        out = find(sg, F_SELFHIT, -1) != 0;
        if (out)
            V.selfhit[side] = 1;
        return grade(kind, side, p, out);
    case K_PROTECT:
        if (!sg)
            break;
        /* Endure says nothing when it holds (only when it saves its user) */
        return grade(kind, side, p, (find(sg, F_PROTECT, side) != 0 || sim_moves[cur_move()].effect == 116) && !find(sg, F_FAIL, -1));
    case K_LOCK_END:
        return grade(kind, side, p, find(0, F_FATIGUE, side) != 0 || find(0, F_CONFUSE, side) != 0);
    }
    /* no view of this outcome: sample it, ungraded */
    return p >= 1 || (p > 0 && sim_rand(b, 1000000) < (u32)(p * 1000000));
}

static int o_pick(Oracle *o, Battle *b, int kind, int side, int n, const double *p)
{
    int k;
    (void)o;
    if (kind == K_HITS && V.cur) {
        int got = hits_in(V.cur), lo = -1;
        Fact *x = find(V.cur, F_NHITS, -1);
        if (x)
            got = x->a;
        /* outcome k is k + lo hits: lo from the move (the hit_count caller's distribution starts at hits_min) */
        lo = sim_moves[cur_move()].hits_min;
        if (V.cur->kind == SG_ACT && got > 0) {
            k = got - lo;
            V.decisions[kind]++;
            if (k < 0 || k >= n || p[k] <= 0) {
                V.zero[kind]++;
                zero_detail(kind, side, k >= 0 && k < n ? p[k] : 0, got);
                return k < 0 ? 0 : k >= n ? n - 1 : k;
            }
            return k;
        }
    }
    if (kind == K_MOODY || kind == K_MOODY_DOWN) {    /* the stat the log raised (lowered) at this turn's end */
        int i, j;
        for (i = 0; i < V.T->nseg; i++)
            for (j = 0; j < V.T->seg[i].nf; j++) {
                Fact *x = &V.T->seg[i].f[j];
                if (x->code == F_STAT && x->side == side && x->a < 5 && (kind == K_MOODY ? x->b > 0 : x->b < 0)) {
                    if (kind == K_MOODY) {
                        V.moody_up = x->a;
                        return x->a;
                    }
                    return x->a > V.moody_up ? x->a - 1 : x->a;
                }
            }
    }
    if (kind == K_ACUPRESSURE) {        /* the stat the log raised by 2 */
        int i, j;
        for (i = 0; i < V.T->nseg; i++)
            for (j = 0; j < V.T->seg[i].nf; j++) {
                Fact *x = &V.T->seg[i].f[j];
                if (x->code == F_STAT && x->side == side && x->b > 0 && x->a < n && p[x->a] > 0)
                    return x->a;
            }
    }
    if (kind == K_CALL && !n && V.cur) {    /* a called move starts (move.c run_move): its log segment, if it has one */
        int i, j;
        for (i = 0; i < V.T->nseg; i++)
            if (&V.T->seg[i] == V.cur)
                for (j = i + 1; j < V.T->nseg; j++)
                    if (V.T->seg[j].kind == SG_ACT && V.T->seg[j].side == side && V.T->seg[j].arg == g_called) {
                        V.cur = &V.T->seg[j];
                        return 0;
                    }
        return 0;
    }
    if (kind == K_CALL && g_call_cand && V.cur) {      /* the move the log shows next for this side (Assist) */
        int i, j;
        for (i = 0; i < V.T->nseg; i++)
            if (&V.T->seg[i] == V.cur)
                for (j = i + 1; j < V.T->nseg; j++) {
                    Seg *sg = &V.T->seg[j];
                    if (sg->kind == SG_ACT && sg->side == side && sg->arg > 0) {
                        for (k = 0; k < n; k++)
                            if (g_call_cand[k] == sg->arg)
                                return k;
                        break;
                    }
                }
    }
    if (kind == K_PHAZE) {
        int t = side, i, c = 0;
        Fact *x = find(V.cur, F_SENDIN, t);
        if (!x)
            x = find(0, F_SENDIN, t);
        for (i = 1; x && i < b->n[t]; i++)
            if (sim_alive(&b->party[t][i])) {
                if (b->party[t][i].set == x->a)
                    return c;
                c++;
            }
    }
    {
        double r = sim_rand(b, 1000000) / 1e6, acc = 0;
        for (k = 0; k < n - 1; k++)
            if (r < (acc += p[k]))
                break;
        return k;
    }
}

static int o_damage(Oracle *o, Battle *b, int s, int hit, int crit, const int *cand)
{
    int t = s ^ 1, k = nth_hit(V.cur, hit), lo = cand[0], hi = cand[0], r, logged, hp = b->party[t][0].hp;
    (void)o;
    V.hit_i = hit + 1;
    for (r = 1; r < 16; r++)
        lo = cand[r] < lo ? cand[r] : lo, hi = cand[r] > hi ? cand[r] : hi;
    if (k < 0) {
        V.hits_unmatched++;
        finding("hit_unlogged", "\"move\": \"%s\", \"att\": \"%s\", \"def\": \"%s\", \"hit\": %d, \"min\": %d, \"max\": %d, "
                "\"sub\": %d", sim_move_name[cur_move()], sim_species_name[b->party[s][0].species],
                sim_species_name[b->party[t][0].species], hit, lo, hi, b->v[t].sub);
        return cand[sim_rand(b, 16)];
    }
    V.cur->f[k].used = 1;
    logged = V.cur->f[k].a;
    V.hits++;
    for (r = 0; r < 16; r++)
        if (cand[r] == logged)
            break;
    if (r < 16) {
        V.hits_exact++;
        return logged;
    }
    if ((logged >= hp && hi >= hp) || (logged == hp - 1 && hi >= hp - 1)) {     /* a KO, or a Sash or Sturdy survival */
        V.hits_clamp++;
        return logged == hp - 1 && hi >= hp ? hi : logged;      /* the simulator's Sash or Sturdy then acts */
    }
    V.hits_out++;
    finding("damage", "\"move\": \"%s\", \"att\": \"%s\", \"def\": \"%s\", \"logged\": %d, \"min\": %d, \"max\": %d, "
            "\"crit\": %d, \"hp\": %d, \"hit\": %d, \"ability\": \"%s\", \"item\": \"%s\", \"dability\": \"%s\", "
            "\"ditem\": \"%s\"", sim_move_name[cur_move()], sim_species_name[b->party[s][0].species],
            sim_species_name[b->party[t][0].species], logged, lo, hi, crit, hp, hit, sim_ability_name[b->v[s].ability],
            sim_item_name[b->party[s][0].item], sim_ability_name[b->v[t].ability], sim_item_name[b->party[t][0].item]);
    return logged;
}

static void o_note(Oracle *o, Battle *b, int code, int side, int a, int c)
{
    (void)o;
    (void)b;
    if (V.nnote < MAXNOTE) {
        Note *n = &V.note[V.nnote++];
        n->code = code, n->side = side, n->a = a, n->c = c;
        n->seg = V.cur ? (int)(V.cur - V.T->seg) : -1;
    }
}

/* ---------------------------------------------------------------- the replacement policy: the logged choices */

static int val_ai;
static FILE *orig_dump;      /* --orig-dump: side 0 (the original AI in adv-vs-orig logs), for origfit.py */
static FILE *orig_eval;      /* --orig-eval: the original-AI model's probabilities at side 0's logged decisions */
static Policy g_adv;

static int party_index(const Battle *b, int s, int set)
{
    int i;
    for (i = 0; i < b->n[s]; i++)
        if (b->party[s][i].set == set)
            return i;
    return -1;
}

static void value_check_repl(Battle *b, int s, Seg *sg);

static int val_replace(Battle *b, int s, void *ctx)
{
    int i, idx;
    (void)ctx;
    for (i = 0; i < V.T->nseg; i++) {
        Seg *sg = &V.T->seg[i];
        if (sg->kind != SG_REPL || sg->side != s || sg->used)
            continue;
        sg->used = 1;
        if (val_ai)
            value_check_repl(b, s, sg);
        if (orig_dump && s == 0)
            orig_dump_replace(orig_dump, b, s, V.gi, V.T->n, sg->arg);
        if (orig_eval && s == 0) {
            double p[6];
            int n = 0, j;
            for (j = 1; j < b->n[s]; j++)
                n += sim_alive(&b->party[s][j]);
            fprintf(orig_eval, "{\"g\": %d, \"turn\": %d, \"kind\": \"r\", \"logged\": %d, \"pick\": %d, \"n\": %d}\n", V.gi,
                    V.T->n, party_index(b, s, sg->arg), orig_replace_pick(b, s, p), n);
        }
        idx = party_index(b, s, sg->arg);
        V.cur = sg;
        if (idx < 1 || !sim_alive(&b->party[s][idx])) {
            finding("replace", "\"side\": %d, \"why\": \"logged replacement not on the bench or fainted\", \"set\": %d", s, sg->arg);
            return 0;
        }
        return idx;
    }
    if (val_ai)
        g_adv.replace(b, s, g_adv.ctx);
    finding("replace", "\"side\": %d, \"why\": \"the simulator replaces where the log does not\"", s);
    V.cur = 0;
    return 0;
}

static const Policy g_val = { "val", 0, val_replace, 0, 0 };

/* ---------------------------------------------------------------- the value check */

typedef struct { long decisions, exact, top_same, shown, shown_exact, strong_same, strong_n, repl, repl_same; double absdiff; } ValueStats;
static ValueStats VS;

extern unsigned char sim_foe_act[2];
extern int sim_foe_valid;
extern struct { unsigned magic, word; int me_hp, opp_hp; unsigned short me_species, opp_species; unsigned char on, trusted; } fs;
static FILE *parity;
static void party_dump(const Battle *b)
{
    int s, i;
    fprintf(parity, "[");
    for (s = 0; s < 2; s++) {
        fprintf(parity, "%s[", s ? ", " : "");
        for (i = 0; i < b->n[s]; i++)
            fprintf(parity, "%s[%d, %d]", i ? ", " : "", b->party[s][i].set, b->party[s][i].hp);
        fprintf(parity, "]");
    }
    fprintf(parity, "]");
}
static int alive_n(const Battle *b, int s) { int i, n = 0; for (i = 0; i < b->n[s]; i++) n += sim_alive(&b->party[s][i]); return n; }
static Action g_rf[2];
static int g_rturn;
static Action r_choose(Battle *b, int s, void *ctx)
{
    const Policy *p = s ? &g_adv : &policy_orig;
    return b->turn == g_rturn ? g_rf[s] : p->choose(b, s, p->ctx);
}
static int r_replace(Battle *b, int s, void *ctx)
{
    const Policy *p = s ? &g_adv : &policy_orig;
    return p->replace(b, s, p->ctx);
}
static u64 r_mix(u64 x)
{
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}
/* the win rate of side 1 over n games from b with side 1's first action mine and side 0's foe */
static double rollouts(Battle *b, Action mine, Action foe, int n, u64 key)
{
    static const Policy rp = { "roll", r_choose, r_replace, 0, 0, 0 };
    static Battle save;
    static void *ai;
    u64 orng = orig_rng_get();
    double w = 0;
    int i;
    if (!ai)
        ai = malloc(sim_ai_state_size());
    save = *b;
    sim_ai_state_save(ai);
    for (i = 0; i < n; i++) {
        *b = save;
        sim_ai_state_load(ai);
        b->oracle = 0;
        b->verbose = 0;
        b->rng = r_mix(key + (u64)i) | 1;
        orig_rng_set(r_mix(key ^ (0x6F726967ULL + (u64)i)));
        g_rturn = save.turn;
        b->turn = save.turn - 1;
        g_rf[1] = mine, g_rf[0] = foe;
        while (b->winner < 0 && b->turn < save.turn + 150)
            if (!sim_turn(b, &rp, &rp))
                break;
        w += b->winner == 1 ? 1 : b->winner < 0 || b->winner == 2 ? 0.5 : 0;
    }
    *b = save;
    sim_ai_state_load(ai);
    orig_rng_set(orng);
    return w / n;
}
static Action as_action(const Battle *b, int s, int k, int arg)
{
    Action x = { ACT_NONE, 0 };
    int i;
    if (k == 0)
        for (i = 0; i < 4; i++)
            if (b->party[s][0].moves[i] == arg)
                x.kind = ACT_MOVE, x.idx = (u8)i;
    if (k == 1)
        for (i = 1; i < b->n[s]; i++)
            if (b->party[s][i].set == arg)
                x.kind = ACT_SWITCH, x.idx = (u8)i;
    return x;
}
static void value_check(Battle *b, int s, const Act *a, const Act2 *foe, int foe_forced)
{
    const u8 *d;
    int n, i, j, all = 1, simtop = -1, simtopv = -2147483647, rd = s == 1 && !(getenv("VAL_READ") && *getenv("VAL_READ") == '0');
    if (!a->nopt)
        return;
    if (rd && foe->kind == ACT_MOVE && foe->slot >= 0 && foe->slot < 4)
        sim_foe_act[0] = 1, sim_foe_act[1] = (unsigned char)foe->slot, sim_foe_valid = 1;
    else if (rd && foe->kind == ACT_SWITCH && foe->slot > 0)
        sim_foe_act[0] = 2, sim_foe_act[1] = (unsigned char)foe->slot, sim_foe_valid = 1;
    fs.trusted = 0;
    g_adv.choose(b, s, g_adv.ctx);
    sim_foe_valid = 0;
    d = host_debug(s ^ 1);
    if (d[7] & 15) {            /* a fallback: the record holds no options for this decision */
        finding("value_fallback", "\"side\": %d, \"why\": %d", s, d[7] & 15);
        return;
    }
    n = d[112] < MAXOPT ? d[112] : MAXOPT;
    VS.decisions++;
    if (parity) {
        fprintf(parity, "{\"g\": %d, \"path\": \"%s\", \"turn\": %d, \"side\": %d, \"kind\": \"c\", \"foe\": [%d, %d, %d], "
                "\"fs\": %d, \"hp\": [%d, %d], \"alive\": [%d, %d], \"log\": [", V.gi, V.g->path, V.T->n, s, foe->kind, foe->slot, foe_forced,
                fs.trusted, b->party[s][0].hp, b->party[s ^ 1][0].hp, alive_n(b, 0), alive_n(b, 1));
        for (i = 0; i < a->nopt; i++)
            fprintf(parity, "%s[%d, %d, %d]", i ? ", " : "", a->ok[i], a->oa[i], a->ov[i]);
        fprintf(parity, "], \"party\": ");
        party_dump(b);
        fprintf(parity, ", \"more\": %d, \"sim\": [", a->more);
        for (j = 0; j < n; j++) {
            const u8 *o = d + 120 + 8 * j;
            int k = o[0], idx = o[1], extra = o[2] | o[3] << 8;
            int v = (int)(o[4] | o[5] << 8 | o[6] << 16 | (u32)o[7] << 24);
            int arg = k == 0 ? (idx < 4 ? b->party[s][0].moves[idx] : -1) : k == 1 ? (extra < b->n[s] ? b->party[s][extra].set : -1) : 0;
            fprintf(parity, "%s[%d, %d, %d]", j ? ", " : "", k, arg, v);
        }
        fprintf(parity, "]");
        if (getenv("VAL_ROLL") && s == 1 && n) {
            int jt = 0, nr = atoi(getenv("VAL_ROLL"));
            const u8 *o;
            Action ds = as_action(b, s, a->ok[0], a->oa[0]), hs, fa = { ACT_MOVE, 0 };
            for (j = 1; j < n; j++) {
                int v = (int)(d[120 + 8 * j + 4] | d[120 + 8 * j + 5] << 8 | d[120 + 8 * j + 6] << 16 | (u32)d[120 + 8 * j + 7] << 24);
                int v0 = (int)(d[120 + 8 * jt + 4] | d[120 + 8 * jt + 5] << 8 | d[120 + 8 * jt + 6] << 16 | (u32)d[120 + 8 * jt + 7] << 24);
                if (v > v0)
                    jt = j;
            }
            o = d + 120 + 8 * jt;
            hs.kind = o[0] == 0 ? ACT_MOVE : o[0] == 1 ? ACT_SWITCH : ACT_NONE;
            hs.idx = o[0] == 0 ? o[1] : (u8)(o[2] | o[3] << 8);
            if (foe->kind == ACT_SWITCH && foe->slot > 0)
                fa.kind = ACT_SWITCH, fa.idx = (u8)foe->slot;
            else if (foe->slot >= 0 && foe->slot <= 4)
                fa.idx = (u8)foe->slot;
            else
                fa.kind = ACT_NONE;
            if (ds.kind != ACT_NONE && hs.kind != ACT_NONE && fa.kind != ACT_NONE && (ds.kind != hs.kind || ds.idx != hs.idx)) {
                u64 key = r_mix(0xA0A0ULL + (u64)V.gi * 1000 + (u64)V.T->n);
                double wd = rollouts(b, ds, fa, nr, key), wh = rollouts(b, hs, fa, nr, key);
                fprintf(parity, ", \"roll\": [%.4f, %.4f]", wd, wh);
            }
        }
        fprintf(parity, "}\n");
    }
    if (getenv("VAL_DUMP")) {
        /* the AI's Read record on the host (tools/hostai/host_engine.h READS_AT; 24 bytes with its 8-byte pointer) */
        const u8 *r = (const u8 *)(uintptr_t)(0x8000000000ull + 0x01FFFF00u) + 24 * (s ^ 1);
        fprintf(stderr, "turn %d side %d %s vs %s: strong sim %d log %d llr %d miss %d; sim:", V.T->n, s,
                sim_species_name[b->party[s][0].species], sim_species_name[b->party[s ^ 1][0].species], d[248] | d[249] << 8,
                a->strong, (s16)(r[12] | r[13] << 8), r[19]);
        for (j = 0; j < n; j++) {
            const u8 *o = d + 120 + 8 * j;
            int v = (int)(o[4] | o[5] << 8 | o[6] << 16 | (u32)o[7] << 24), extra = o[2] | o[3] << 8;
            fprintf(stderr, " %s=%d", o[0] == 0 ? (o[1] < 4 ? sim_move_name[b->party[s][0].moves[o[1]]] : "?") :
                    o[0] == 1 && extra < b->n[s] ? sim_species_name[b->party[s][extra].species] : "item", v);
        }
        fprintf(stderr, "\n   log:");
        for (i = 0; i < a->nopt; i++)
            fprintf(stderr, " %s=%d", a->ok[i] == 0 && a->oa[i] > 0 ? sim_move_name[a->oa[i]] : a->ok[i] == 1 ? "switch" : "?", a->ov[i]);
        fprintf(stderr, "\n");
    }
    for (j = 0; j < n; j++) {
        const u8 *o = d + 120 + 8 * j;
        int v = (int)(o[4] | o[5] << 8 | o[6] << 16 | (u32)o[7] << 24);
        if (v > simtopv)
            simtopv = v, simtop = j;
    }
    for (i = 0; i < a->nopt; i++) {
        int found = 0, sv = 0;
        for (j = 0; j < n; j++) {
            const u8 *o = d + 120 + 8 * j;
            int k = o[0], idx = o[1], extra = o[2] | o[3] << 8;
            int v = (int)(o[4] | o[5] << 8 | o[6] << 16 | (u32)o[7] << 24);
            int arg = k == 0 ? (idx < 4 ? b->party[s][0].moves[idx] : -1) : k == 1 ? (extra < b->n[s] ? b->party[s][extra].set : -1) : 0;
            if (k == a->ok[i] && arg == a->oa[i])
                found = 1, sv = v;
        }
        VS.shown++;
        if (found && sv == a->ov[i])
            VS.shown_exact++;
        else {
            all = 0;
            VS.absdiff += found ? fabs((double)sv - a->ov[i]) : 0;
        }
    }
    VS.exact += all && a->nopt;
    if (simtop >= 0 && a->nopt) {
        const u8 *o = d + 120 + 8 * simtop;
        int k = o[0], idx = o[1], extra = o[2] | o[3] << 8;
        int arg = k == 0 ? (idx < 4 ? b->party[s][0].moves[idx] : -1) : k == 1 ? (extra < b->n[s] ? b->party[s][extra].set : -1) : 0;
        int same = k == a->ok[0] && arg == a->oa[0];
        VS.top_same += same;
        if (!all)
            finding("value", "\"side\": %d, \"mon\": \"%s\", \"foe\": \"%s\", \"top_same\": %d, \"log_top\": [%d, %d, %d], "
                    "\"sim_top\": [%d, %d, %d], \"nopt\": %d", s, sim_species_name[b->party[s][0].species],
                    sim_species_name[b->party[s ^ 1][0].species], same, a->ok[0], a->oa[0], a->ov[0], k, arg, simtopv, n);
    }
    if (a->strong >= 0 && d[4] >= 4) {
        int strong = d[248] | d[249] << 8;
        VS.strong_n++;
        VS.strong_same += (strong + 5) / 10 == (a->strong + 5) / 10;     /* the log prints s with two decimals */
    }
}

static void value_check_repl(Battle *b, int s, Seg *sg)
{
    int idx;
    if (!sg->nopt)
        return;
    idx = g_adv.replace(b, s, g_adv.ctx);
    VS.repl++;
    if (parity)
    {   /* repl_opts */
        int i;
        fprintf(parity, "{\"g\": %d, \"path\": \"%s\", \"turn\": %d, \"side\": %d, \"kind\": \"r\", \"log\": [", V.gi,
                V.g->path, V.T->n, s);
        for (i = 0; i < sg->nopt; i++)
            fprintf(parity, "%s[1, %d, %d]", i ? ", " : "", sg->oa[i], sg->ov[i]);
        fprintf(parity, "], \"sim\": [[1, %d, 0]]}\n", idx >= 0 && idx < b->n[s] ? b->party[s][idx].set : -1);
    }
    if (sg->nopt && idx >= 0 && idx < b->n[s])
        VS.repl_same += b->party[s][idx].set == sg->oa[0];
}

/* ---------------------------------------------------------------- one turn */

static const char *CAUSE[] = { "leftovers", "blacksludge", "burn", "poison", "sand", "seed", "lifeorb", "recoil", "helmet",
                               "drain", "veil", "ingrain", "berry", "curse", "nightmare", "bind", "jaboca", "crash",
                               "painsplit", "rest", "wish", "bellydrum", "drained", "other" };

/* the HP-changing messages of side s's Pokemon in turn P (for the HP drift's cause) */
static const char *hp_causes(const TurnObs *P, int s, char *buf, size_t n)
{
    int i, k;
    size_t len = 0;
    buf[0] = 0;
    for (i = 0; P && i < P->nseg; i++)
        for (k = 0; k < P->seg[i].nf; k++) {
            const Fact *x = &P->seg[i].f[k];
            const char *c = 0;
            if ((x->code == F_CHIP || x->code == F_HEAL) && x->side == s && x->a >= 0 && x->a < 24)
                c = CAUSE[x->a];
            else if (x->code == F_HAZARD_HIT && x->side == s)
                c = x->a ? "spikes" : "rocks";
            else if (x->code == F_HIT && x->side == s)
                c = "hit";
            else if (x->code == F_SELFHIT && P->seg[i].side == s)
                c = "selfhit";
            else if (x->code == F_SENDIN && x->side == s)
                c = "sendin";
            if (c && len + strlen(c) + 2 < n)
                len += (size_t)snprintf(buf + len, n - len, "%s%s", len ? "," : "", c);
        }
    return buf;
}

static void resync(Battle *b, const TurnObs *T, const TurnObs *P)
{
    char cause[200];
    int s, k;
    for (s = 0; s < 2; s++) {
        const St *st = &T->st[s];
        Mon *m;
        Volatile *v = &b->v[s];
        int i;
        if (!T->has_st[s])
            continue;
        i = party_index(b, s, st->set);
        if (i < 0)
            continue;
        if (i > 0) {
            Mon tmp = b->party[s][0];
            finding("drift", "\"what\": \"active\", \"side\": %d, \"sim\": \"%s\", \"log\": \"%s\"", s,
                    sim_species_name[tmp.species], sim_species_name[b->party[s][i].species]);
            b->party[s][0] = b->party[s][i];
            b->party[s][i] = tmp;
            reset_volatile(b, s, 0);
        }
        m = &b->party[s][0];
        if (m->maxhp != st->maxhp) {
            finding("maxhp", "\"side\": %d, \"mon\": \"%s\", \"sim\": %d, \"log\": %d", s, sim_species_name[m->species],
                    m->maxhp, st->maxhp);
            m->maxhp = st->maxhp;
        }
        if (m->hp != st->hp && !V.selfhit[s])
            finding("drift", "\"what\": \"hp\", \"side\": %d, \"mon\": \"%s\", \"sim\": %d, \"log\": %d, \"maxhp\": %d, "
                    "\"ability\": \"%s\", \"item\": \"%s\", \"causes\": \"%s\", \"weather\": %d", s, sim_species_name[m->species],
                    m->hp, st->hp, m->maxhp, sim_ability_name[v->ability], sim_item_name[m->item],
                    hp_causes(P, s, cause, sizeof cause), b->weather);
        m->hp = st->hp;
        {
            int sst = m->status == ST_PSN && m->toxic ? 6 : m->status, lst = st->status == ST_PSN && st->toxic ? 6 : st->status;
            if (sst != lst) {
                finding("drift", "\"what\": \"status\", \"side\": %d, \"mon\": \"%s\", \"sim\": %d, \"log\": %d, "
                        "\"ability\": \"%s\", \"item\": \"%s\"", s, sim_species_name[m->species], sst, lst,
                        sim_ability_name[v->ability], sim_item_name[m->item]);
                m->status = st->status;
                m->toxic = st->status == ST_PSN && st->toxic;
                if (m->status == ST_SLP)
                    m->sleep = 250, m->slept = 0;
                else
                    m->sleep = 0;
                if (!m->toxic)
                    m->tox_n = 0;
            }
        }
        if ((v->confused > 0) != (st->confused > 0)) {
            finding("drift", "\"what\": \"confusion\", \"side\": %d, \"mon\": \"%s\", \"sim\": %d, \"log\": %d", s,
                    sim_species_name[m->species], v->confused > 0, st->confused);
            v->confused = st->confused ? 1 : 0;
            v->conf_n = 0;
        }
        for (k = 0; k < 7; k++)
            if (v->stage[k] != st->stage[k]) {
                finding("drift", "\"what\": \"stage\", \"side\": %d, \"mon\": \"%s\", \"stat\": %d, \"sim\": %d, \"log\": %d, "
                        "\"ability\": \"%s\", \"item\": \"%s\"", s, sim_species_name[m->species], k, v->stage[k],
                        st->stage[k], sim_ability_name[v->ability], sim_item_name[m->item]);
                v->stage[k] = st->stage[k];
            }
    }
    {
        int w = b->weather >= WX_STRONG_WINDS ? -1 : b->weather;
        if (w < 0)
            ;                   /* the logs print no extreme weather on the turn line */
        else if (w != T->weather) {
            finding("drift", "\"what\": \"weather\", \"sim\": %d, \"log\": %d, \"sim_turns\": %d, \"log_turns\": %d", w,
                    T->weather, b->weather_turns, T->wturns);
            if (b->weather != WX_STRONG_WINDS || T->weather) {
                b->weather = T->weather;
                b->weather_turns = T->weather ? (T->wturns ? T->wturns : 255) : 0;
            }
        } else if (w && T->wturns && b->weather_turns != 255 && b->weather_turns != T->wturns) {
            finding("drift", "\"what\": \"weather_turns\", \"sim\": %d, \"log\": %d, \"sim_turns\": %d, \"log_turns\": %d", w,
                    T->weather, b->weather_turns, T->wturns);
            b->weather_turns = T->wturns;
        }
    }
}

static int slot_of(const Battle *b, int s, int move)
{
    int k;
    if (move == M_STRUGGLE)
        return 4;
    for (k = 0; k < 4; k++)
        if (b->party[s][0].moves[k] == move)
            return k;
    return -1;
}


static int act_prio(const Battle *b, int s, int slot)
{
    const Mon *m = &b->party[s][0];
    int mv = slot == 4 ? M_STRUGGLE : slot == 5 ? 0 : m->moves[slot], p, ab = b->v[s].ability;
    if (!mv)
        return 0;
    p = sim_moves[mv].prio;
    if (ab == A_PRANKSTER && sim_moves[mv].cls == CLS_STATUS)
        p++;
    if (ab == A_GALEWINGS && sim_moves[mv].type == T_FLYING)
        p++;
    if (ab == A_TRIAGE && (sim_moves[mv].heal > 0 || sim_moves[mv].drain > 0))
        p += 3;
    return p;
}

/* 1 when x acts before y; 0.5 a tie */
static double first_p(const Battle *b, const Act2 *x, const Act2 *y)
{
    if (x->kind != y->kind)
        return x->kind == ACT_SWITCH ? 1 : 0;
    if (x->prio != y->prio)
        return x->prio > y->prio ? 1 : 0;
    if (x->speed != y->speed)
        return (x->speed > y->speed) != (b->trick_room > 0) ? 1 : 0;
    return 0.5;
}

static void compare_turn(Battle *b);

static int play_turn(Battle *b, GameObs *g, int ti)
{
    TurnObs *T = &g->t[ti];
    Act2 a[2];
    int s, i, order[2], log_first = -1, forced[2];
    double qc[2], p;
    const Policy *pol[2] = { &g_val, &g_val };
    V.T = T, V.ti = ti, V.cur = 0, V.nnote = 0;
    V.selfhit[0] = V.selfhit[1] = 0;
    b->turn = T->n;
    for (s = 0; s < 2; s++)
        if (T->has_act[s] && T->act[s].kind == 'i') {
            finding("unsupported", "\"why\": \"trainer item\"");
            return 0;
        }
    for (s = 0; s < 2; s++) {
        forced[s] = forced_slot(b, s);
        a[s].side = s;
        a[s].kind = ACT_MOVE;
        a[s].slot = -1;
        if (forced[s] >= 0)
            a[s].slot = forced[s];
        else if (T->has_act[s] && T->act[s].kind == 's') {
            a[s].kind = ACT_SWITCH;
            a[s].slot = party_index(b, s, T->act[s].arg);
        } else if (T->has_act[s] && T->act[s].kind == 'm') {
            a[s].slot = slot_of(b, s, T->act[s].arg);
            if (a[s].slot < 0) {
                finding("unsupported", "\"why\": \"logged move not in the set\", \"side\": %d, \"move\": \"%s\"", s,
                        sim_move_name[T->act[s].arg > 0 && T->act[s].arg < sim_nmoves ? T->act[s].arg : 0]);
                return 0;
            }
        } else if (sim_alive(&b->party[s][0])) {
            Seg *sg = action_seg(s);
            if (sg && sg->kind == SG_ACT && sg->arg > 0)
                a[s].slot = slot_of(b, s, sg->arg);
            if (a[s].slot < 0)
                a[s].kind = ACT_NONE;
        } else
            a[s].kind = ACT_NONE;
        if (a[s].kind == ACT_SWITCH && a[s].slot < 1)
            a[s].kind = ACT_NONE;
    }
    /* the value check: the AI decides in this state, as the client polls it (forced moves are not polled) */
    if (val_ai)
        for (s = 0; s < 2; s++)
            if (forced[s] < 0 && T->has_act[s] && sim_alive(&b->party[s][0]))
                value_check(b, s, &T->act[s], &a[s ^ 1], forced[s ^ 1]);
    if (orig_eval && forced[0] < 0 && T->has_act[0] && sim_alive(&b->party[0][0]) &&
        (T->act[0].kind == 'm' || T->act[0].kind == 's')) {
        double p[11];
        int j, lg = T->act[0].kind == 'm' ? slot_of(b, 0, T->act[0].arg) : 5 + party_index(b, 0, T->act[0].arg);
        orig_choice(b, 0, p);
        fprintf(orig_eval, "{\"g\": %d, \"turn\": %d, \"kind\": \"%c\", \"logged\": %d, \"p\": [", V.gi, T->n,
                T->act[0].kind, lg);
        for (j = 0; j < 11; j++)
            fprintf(orig_eval, "%s%.4f", j ? ", " : "", p[j]);
        fprintf(orig_eval, "]}\n");
    }
    if (orig_dump && forced[0] < 0 && T->has_act[0] && sim_alive(&b->party[0][0]))
        orig_dump_decision(orig_dump, b, 0, V.gi, T->n, T->act[0].kind, T->act[0].arg, &T->act[0].sc, &T->act[0].fsc);
    for (s = 0; s < 2; s++) {
        int it = item_of(b, s);
        b->v[s].moved = 0;
        b->v[s].hit_by_move = b->v[s].hit_dmg = 0;
        b->v[s].planned = a[s].kind == ACT_MOVE && a[s].slot >= 0 ?
            (a[s].slot < 4 ? b->party[s][0].moves[a[s].slot] : a[s].slot == 4 ? M_STRUGGLE : 0) : 0;
        a[s].prio = a[s].kind == ACT_MOVE && a[s].slot >= 0 ? act_prio(b, s, a[s].slot) : 0;
        a[s].speed = sim_eff_speed(b, s);
        qc[s] = 0;
        if (a[s].kind == ACT_MOVE && forced[s] < 0) {
            if (it == I_QUICKCLAW)
                qc[s] = 0.2;
            else if (b->v[s].ability == A_QUICKDRAW)
                qc[s] = 0.1;
            else if (it == I_LAGGINGTAIL || it == I_FULLINCENSE)
                a[s].speed = b->trick_room ? 0xFFFFF : -1;
            else if (it == I_CUSTAPBERRY && b->party[s][0].hp * 4 <= b->party[s][0].maxhp) {
                a[s].speed = 0xFFFFF;
                consume(b, s);
            }
        }
    }
    for (i = 0; i < T->nseg && log_first < 0; i++)
        if ((T->seg[i].kind == SG_ACT || T->seg[i].kind == SG_SWITCH) && T->seg[i].side >= 0)
            log_first = T->seg[i].side;
    /* the order: the log's, graded against the model given the Quick Claws the log shows */
    for (s = 0; s < 2; s++)
        if (qc[s] > 0) {
            int q = find(0, F_QUICK, s) != 0;
            grade(K_QUICK, s, qc[s], q);
            if (q)
                a[s].speed = 0xFFFFF;
        }
    if (a[0].kind != ACT_NONE && a[1].kind != ACT_NONE && a[0].slot != 5 && a[1].slot != 5 && log_first >= 0) {
        p = first_p(b, &a[log_first], &a[log_first ^ 1]);
        if (p > 0 && p < 1) {
            V.decisions[K_TIE]++;
            rate_add(K_TIE, 0.5, log_first == 0);       /* a Speed tie: did side 0 win it */
        } else if (p <= 0) {
            V.zero[K_TIE]++;
            finding("order", "\"first_log\": %d, \"mon0\": \"%s\", \"move0\": \"%s\", \"prio0\": %d, \"speed0\": %d, "
                    "\"mon1\": \"%s\", \"move1\": \"%s\", \"prio1\": %d, \"speed1\": %d, \"trick_room\": %d, "
                    "\"ability0\": \"%s\", \"ability1\": \"%s\", \"item0\": \"%s\", \"item1\": \"%s\"", log_first,
                    sim_species_name[b->party[0][0].species],
                    a[0].kind == ACT_MOVE && a[0].slot >= 0 ? sim_move_name[a[0].slot < 4 ? b->party[0][0].moves[a[0].slot] : M_STRUGGLE] : "switch",
                    a[0].prio, a[0].speed, sim_species_name[b->party[1][0].species],
                    a[1].kind == ACT_MOVE && a[1].slot >= 0 ? sim_move_name[a[1].slot < 4 ? b->party[1][0].moves[a[1].slot] : M_STRUGGLE] : "switch",
                    a[1].prio, a[1].speed, b->trick_room, sim_ability_name[b->v[0].ability],
                    sim_ability_name[b->v[1].ability], sim_item_name[b->party[0][0].item], sim_item_name[b->party[1][0].item]);
        }
        order[0] = log_first, order[1] = log_first ^ 1;
    } else {
        order[0] = first_p(b, &a[0], &a[1]) >= 0.5 ? 0 : 1;
        order[1] = order[0] ^ 1;
        if (log_first >= 0)
            order[0] = log_first, order[1] = log_first ^ 1;
    }
    for (i = 0; i < 2; i++) {
        Act2 *x = &a[order[i]];
        s = x->side;
        if (b->winner >= 0)
            break;
        V.cur = action_seg(s);
        V.hit_i = 0;
        if (V.cur)
            V.cur->used = 1;
        if (x->kind == ACT_SWITCH) {
            if (x->slot > 0 && sim_alive(&b->party[s][x->slot])) {
                switch_in(b, s, x->slot, 0);
                b->v[s].moved = 1;
            }
        } else if (x->kind == ACT_MOVE && x->slot >= 0 && sim_alive(&b->party[s][0]) && b->v[s].moved != 2)
            use_move(b, s, x->slot, pol);
        b->v[s].moved = b->v[s].moved == 2 ? 2 : 1;
        check_end(b);
    }
    V.cur = 0;
    if (b->winner < 0) {
        end_of_turn(b);
        check_end(b);
    }
    replace_fainted(b, pol);
    V.cur = 0;
    for (s = 0; s < 2; s++)
        if (sim_alive(&b->party[s][0]) && b->v[s].moved == 2)
            b->v[s].moved = 0;
    compare_turn(b);
    return 1;
}

/* ---------------------------------------------------------------- what happened, both ways */

static const char *NNAME[N_N] = { "status", "confuse", "stat", "faint", "sendin", "weather", "terrain", "item", "hazard",
                                  "protect", "miss", "fail", "selfhit", "flinch", "sub", "noeffect", "hit" };

/* the log fact that matches a simulator note: same category, side and (where both say it) the value */
static Fact *match(int code, int side, int a, int c)
{
    int i, k;
    for (i = 0; i < V.T->nseg; i++) {
        Seg *sg = &V.T->seg[i];
        for (k = 0; k < sg->nf; k++) {
            Fact *x = &sg->f[k];
            if (x->used & 2)
                continue;
            switch (code) {
            case N_STATUS: if (x->code == F_STATUS && x->side == side && x->a == a) return x; break;
            case N_CONFUSE: if ((x->code == F_CONFUSE || x->code == F_FATIGUE) && x->side == side) return x; break;
            case N_STAT: if (x->code == F_STAT && x->side == side && x->a == a && x->b == c) return x; break;
            case N_FAINT: if (x->code == F_FAINT && x->side == side) return x; break;
            case N_SENDIN: if (x->code == F_SENDIN && x->side == side && x->a == a) return x; break;
            case N_WEATHER: if (x->code == F_WEATHER && x->a == a) return x; break;
            case N_TERRAIN: if (x->code == F_TERRAIN && x->a == a) return x; break;
            case N_HAZARD: if (c ? x->code == F_HAZARD_HIT && x->side == side && x->a == a : x->code == F_HAZARD && x->side == side && x->a == a) return x; break;
            case N_PROTECT: if ((a ? x->code == F_PROTECTED : x->code == F_PROTECT)) return x; break;
            case N_MISS: if (x->code == F_MISS && x->side == side) return x; break;
            /* the move did nothing: the engine's line ("But it failed", "It doesn't affect") may differ from ours */
            case N_NOEFFECT: if ((x->code == F_NOEFFECT && x->side == side) || x->code == F_FAIL) return x; break;
            case N_FAIL:    /* or "already asleep", "HP is full", "the terrain protects it" (turnlog.py OTHER 10, 12, 13) */
                if (x->code == F_FAIL || x->code == F_NOEFFECT || (x->code == F_OTHER && (x->a == 10 || x->a == 12 || x->a == 13)))
                    return x;
                break;
            case N_SELFHIT: if (x->code == F_SELFHIT) return x; break;
            case N_FLINCH: if (x->code == F_FLINCH && x->side == side) return x; break;
            case N_ITEM:
                if ((x->code == F_ITEM && (x->side == side || x->side < 0) && x->a == a && x->b != 3) ||
                    ((x->code == F_HEAL || x->code == F_CHIP) && x->side == side && x->b == a))
                    return x;
                break;
            }
        }
    }
    return 0;
}

static const char *fact_detail(const Fact *x, char *buf, size_t n)
{
    switch (x->code) {
    case F_STAT: snprintf(buf, n, "\"stat\": %d, \"delta\": %d", x->a, x->b); break;
    case F_STATUS: snprintf(buf, n, "\"st\": %d", x->a); break;
    case F_ITEM: snprintf(buf, n, "\"item_kind\": %d, \"item\": \"%s\"", x->b, x->a > 0 && x->a < sim_nitems ? sim_item_name[x->a] : ""); break;
    case F_WEATHER: case F_TERRAIN: snprintf(buf, n, "\"v\": %d", x->a); break;
    case F_SENDIN: snprintf(buf, n, "\"set\": %d", x->a); break;
    case F_HAZARD: case F_HAZARD_HIT: snprintf(buf, n, "\"kind\": %d", x->a); break;
    default: snprintf(buf, n, "\"a\": %d", x->a);
    }
    return buf;
}

static void compare_turn(Battle *b)
{
    static const int logcodes[] = { F_HIT, F_STATUS, F_CONFUSE, F_FATIGUE, F_STAT, F_FAINT, F_SENDIN, F_WEATHER, F_TERRAIN,
                                    F_HAZARD, F_HAZARD_HIT, F_PROTECT, F_PROTECTED, F_MISS, F_NOEFFECT, F_FAIL, F_SELFHIT,
                                    F_FLINCH, F_ITEM };
    int i, k, j, net[2][2][7];
    char buf[160];
    /* stat changes compare as each stat's net change in the turn (Weakness Policy prints +2 twice for its +4) */
    memset(net, 0, sizeof net);
    for (i = 0; i < V.nnote; i++)
        if (V.note[i].code == N_STAT && V.note[i].side >= 0 && V.note[i].a < 7)
            net[0][V.note[i].side][V.note[i].a] += V.note[i].c;
    for (i = 0; i < V.T->nseg; i++) {
        Seg *sg = &V.T->seg[i];
        for (k = 0; k < sg->nf; k++) {
            Fact *x = &sg->f[k];
            int j2, gone = 0;
            if (x->code != F_STAT || x->side < 0 || x->side > 1 || x->a > 6)
                continue;
            x->used |= 2;
            for (j2 = k + 1; j2 < sg->nf; j2++)
                gone |= sg->f[j2].code == F_FAINT && sg->f[j2].side == x->side;
            if (!gone)          /* a change on a Pokemon the hit knocked out: the engine applies it before the faint */
                net[1][x->side][x->a] += x->b;
        }
    }
    for (i = 0; i < 2; i++)
        for (k = 0; k < 7; k++)
            if (net[0][i][k] != net[1][i][k]) {
                const Mon *m = &b->party[i][0];
                Seg *sg = action_seg(i ^ 1);
                finding(net[1][i][k] && !net[0][i][k] ? "log_only" : !net[1][i][k] ? "sim_only" : "stat_size",
                        "\"what\": \"stat\", \"side\": %d, \"stat\": %d, \"sim\": %d, \"log\": %d, \"mon\": \"%s\", "
                        "\"ability\": \"%s\", \"item\": \"%s\", \"move\": \"%s\", \"own_move\": \"%s\"", i, k, net[0][i][k],
                        net[1][i][k], sim_species_name[m->species], sim_ability_name[b->v[i].ability], sim_item_name[m->item],
                        sg && sg->kind == SG_ACT && sg->arg > 0 && sg->arg < sim_nmoves ? sim_move_name[sg->arg] : "",
                        action_seg(i) && action_seg(i)->kind == SG_ACT && action_seg(i)->arg > 0 ? sim_move_name[action_seg(i)->arg] : "");
            }
    for (i = 0; i < V.nnote; i++) {
        Note *n = &V.note[i];
        Fact *x;
        if (n->code == N_STAT)
            continue;
        if (n->code == N_ITEM && n->side >= 0 && find(0, F_FAINT, n->side))
            continue;           /* an item used by a Pokemon that fell this turn: the engine prints no line for it */
        x = match(n->code, n->side, n->a, n->c);
        if (x)
            x->used |= 2;
        else if (n->code != N_FAINT || 1) {
            const Mon *m = n->side >= 0 ? &b->party[n->side][0] : 0;
            Seg *sg = n->seg >= 0 ? &V.T->seg[n->seg] : 0;
            finding("sim_only", "\"what\": \"%s\", \"side\": %d, \"a\": %d, \"c\": %d, \"mon\": \"%s\", \"move\": \"%s\", "
                    "\"ability\": \"%s\", \"item\": \"%s\", \"aname\": \"%s\"", NNAME[n->code], n->side, n->a, n->c,
                    m ? sim_species_name[m->species] : "", sg && sg->kind == SG_ACT ? sim_move_name[sg->arg] : "",
                    m ? sim_ability_name[b->v[n->side].ability] : "", m ? sim_item_name[m->item] : "",
                    n->code == N_ITEM ? sim_item_name[n->a] : "");
        }
    }
    for (i = 0; i < V.T->nseg; i++) {
        Seg *sg = &V.T->seg[i];
        for (k = 0; k < sg->nf; k++) {
            Fact *x = &sg->f[k];
            if (x->used & 2)
                continue;
            for (j = 0; j < (int)(sizeof logcodes / sizeof *logcodes); j++)
                if (logcodes[j] == x->code)
                    break;
            if (j == (int)(sizeof logcodes / sizeof *logcodes))
                continue;
            if (x->code == F_ITEM && (x->b == 3 || x->b == 7 || x->b == 2))  /* the balloon's announcement, Knock Off, "used" */
                continue;
            if (x->code == F_HIT) {
                if (!(x->used & 1))
                    finding("log_only", "\"what\": \"hit\", \"side\": %d, \"dmg\": %d, \"move\": \"%s\", \"user\": %d", x->side,
                            x->a, sg->kind == SG_ACT && sg->arg > 0 && sg->arg < sim_nmoves ? sim_move_name[sg->arg] : "", sg->side);
                continue;
            }
            if (x->code == F_FAIL && sg->kind != SG_ACT)
                continue;
            if (x->code == F_STAT || x->code == F_STATUS || x->code == F_CONFUSE) {
                int j2, gone = 0;
                for (j2 = k + 1; j2 < sg->nf; j2++)
                    gone |= sg->f[j2].code == F_FAINT && sg->f[j2].side == x->side;
                if (gone)
                    continue;       /* a secondary effect on a Pokemon the hit knocked out: the engine applies it first */
            }
            {
                int side = x->side >= 0 ? x->side : sg->side;
                const Mon *m = side >= 0 && side < 2 ? &b->party[side][0] : 0;
                finding("log_only", "\"what\": \"%s\", \"side\": %d, %s, \"mon\": \"%s\", \"move\": \"%s\", \"user\": %d, "
                        "\"ability\": \"%s\", \"item\": \"%s\"",
                        x->code == F_STATUS ? "status" : x->code == F_CONFUSE || x->code == F_FATIGUE ? "confuse" :
                        x->code == F_STAT ? "stat" : x->code == F_FAINT ? "faint" : x->code == F_SENDIN ? "sendin" :
                        x->code == F_WEATHER ? "weather" : x->code == F_TERRAIN ? "terrain" : x->code == F_HAZARD ? "hazard" :
                        x->code == F_HAZARD_HIT ? "hazard_hit" : x->code == F_PROTECT ? "protect" : x->code == F_PROTECTED ? "protected" :
                        x->code == F_MISS ? "miss" : x->code == F_NOEFFECT ? "noeffect" : x->code == F_FAIL ? "fail" :
                        x->code == F_SELFHIT ? "selfhit" : x->code == F_FLINCH ? "flinch" : "item",
                        side, fact_detail(x, buf, sizeof buf), m ? sim_species_name[m->species] : "",
                        sg->kind == SG_ACT && sg->arg > 0 && sg->arg < sim_nmoves ? sim_move_name[sg->arg] : "", sg->side,
                        m ? sim_ability_name[b->v[side].ability] : "", m ? sim_item_name[m->item] : "");
            }
        }
    }
}

/* ---------------------------------------------------------------- the command */

static void setup(Battle *b, const GameObs *g)
{
    int s, i;
    memset(b, 0, sizeof *b);
    for (s = 0; s < 2; s++) {
        int base = s ? 13 : 1;
        b->n[s] = g->n[s];
        for (i = 0; i < g->n[s]; i++)
            sim_build_mon(&b->party[s][i], &sim_teams[g->mteam[s][i]].mon[g->mslot[s][i]], g->level, base + i, g->slots[s][i]);
        b->rand_team[s] = sim_teams[g->mteam[s][0]].pool == POOL_RANDOM;
    }
}

int cmd_validate(int argc, char **argv)
{
    const char *path = 0;
    int only = -1, i, k;
    long games = 0, turns = 0, stopped = 0;
    FILE *f;
    GameObs g;
    Battle *b = malloc(sizeof *b);
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--ai"))
            val_ai = 1;
        else if (!strcmp(argv[i], "--orig-dump") && i + 1 < argc)
            orig_dump = fopen(argv[++i], "w");
        else if (!strcmp(argv[i], "--orig-eval") && i + 1 < argc)
            orig_eval = fopen(argv[++i], "w");
        else if (!strcmp(argv[i], "--game") && i + 1 < argc)
            only = atoi(argv[++i]);
        else
            path = argv[i];
    }
    if (!path || !(f = fopen(path, "r"))) {
        fprintf(stderr, "usage: sim validate OBS [--ai] [--game N] [--orig-dump FILE] [--orig-eval FILE]\n");
        return 2;
    }
    memset(&g, 0, sizeof g);
    memset(&V, 0, sizeof V);
    V.base.yes = o_yes, V.base.pick = o_pick, V.base.damage = o_damage, V.base.note = o_note;
    if (val_ai)
        g_adv = policy_advanced();
    if (getenv("VAL_PARITY"))
        parity = fopen(getenv("VAL_PARITY"), "w");
    VB = b;
    for (V.gi = 0; read_game(f, &g); V.gi++) {
        int ti;
        if (only >= 0 && V.gi != only)
            continue;
        V.g = &g;
        V.T = 0;
        setup(b, &g);
        b->oracle = &V.base;
        V.quiet = 1;            /* the entry effects before turn 1 are not in the turns */
        sim_start(b, 0x5EED0000ULL + (u64)V.gi + (getenv("VAL_SEED") ? (u64)atoll(getenv("VAL_SEED")) << 20 : 0));
        V.quiet = 0;
        if (val_ai)
            g_adv.battle_start(b, g_adv.ctx);
        printf("{\"game\": %d, \"path\": \"%s\", \"turns\": %d}\n", V.gi, g.path, g.nturn);
        if (getenv("VAL_DUMP"))
            fprintf(stderr, "game %d %s\n", V.gi, g.path);
        games++;
        for (ti = 0; ti < g.nturn; ti++) {
            V.T = &g.t[ti];
            resync(b, V.T, ti ? &g.t[ti - 1] : 0);
            if (b->winner >= 0) {
                finding("ended", "\"why\": \"the simulator ended the battle before the log\"");
                stopped++;
                break;
            }
            if (!play_turn(b, &g, ti)) {
                stopped++;
                break;
            }
            turns++;
        }
    }
    fclose(f);
    for (k = 0; k < K_N; k++)
        for (i = 0; i < V.nb[k]; i++)
            printf("{\"rate\": \"%s\", \"p\": %.6f, \"n\": %ld, \"yes\": %ld, \"exp\": %.3f}\n", KNAME[k], V.bucket_p[k][i],
                   V.rate[k][i].n, V.rate[k][i].yes, V.rate[k][i].exp);
    printf("{\"summary\": 1, \"games\": %ld, \"turns\": %ld, \"stopped\": %ld, \"hits\": %ld, \"hits_exact\": %ld, "
           "\"hits_clamp\": %ld, \"hits_out\": %ld, \"hits_unlogged\": %ld", games, turns, stopped, V.hits, V.hits_exact,
           V.hits_clamp, V.hits_out, V.hits_unmatched);
    for (k = 0; k < K_N; k++)
        printf(", \"dec_%s\": %ld, \"zero_%s\": %ld", KNAME[k], V.decisions[k], KNAME[k], V.zero[k]);
    if (val_ai)
        printf(", \"value_decisions\": %ld, \"value_exact\": %ld, \"value_top_same\": %ld, \"value_shown\": %ld, "
               "\"value_shown_exact\": %ld, \"value_absdiff\": %.1f, \"strong_n\": %ld, \"strong_same\": %ld, "
               "\"repl\": %ld, \"repl_same\": %ld", VS.decisions, VS.exact, VS.top_same, VS.shown, VS.shown_exact,
               VS.absdiff, VS.strong_n, VS.strong_same, VS.repl, VS.repl_same);
    printf("}\n");
    free(b);
    return 0;
}
