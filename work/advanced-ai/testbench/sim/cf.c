/* sim cf: win rates per matchup, and counterfactual replays of the advanced AI's decisions (tools/sim/counterfactual.py
   drives both and writes the report).

     sim cf rate    --pairs FILE [--reps R] [--seed S] [--p0 P] [--p1 P] [--level L] [--max-turns T] [--per-game]
     sim cf analyze --pairs FILE [--reps R] [--seed S] [--p0 P] [--level L] [--lost-only] [--screen N] [--confirm N]
                    [--gap G] [--gap2 G2] [--rollout-p0 P] [--max-turns T]
     sim cf check   --pairs FILE [--reps R] [--seed S] [--p0 P]
     sim cf show    --pairs FILE [--rep R | --reps R] [--seed S] [--p0 P]    (the turns on stderr)
     sim cf trace   --pairs FILE --rep R --turn T [--nth J] --act m:SLOT|s:INDEX [--n N] [--seed S] [--p0 P] [--rollout-p0 P]
                    (N replays of that decision with that action, as analyze plays them, their turns on stderr)
     sim cf mc      --pairs FILE [--reps R] [--n N] [--margin M] [--rollout-p0 P [--general 1|2]] ...
                    (a rollout policy on side 1; --general: its replays use the game's foe, and an action counts only
                    if its replays against P are no worse (1) or better (2) than the AI's own choice's)
     sim cf features --pairs FILE [--reps R] [--lost-only] [--seed S] [--p0 P]   (analyze's decision lines, no replays)
     sim cf teams
     sim cf luck    --pairs FILE [--reps R] [--seed S] [--p0 P] [--p1 P] [--luck-k K] [--tune-s1 V,..] [--tune-s0 V,..]
                    [--lines A:B] [--feat FILE] [--leaf-w W,..]   (one line per game: its result and its luck, below)
     sim cf serve   --pairs FILE --p0 adv --p1 adv [--luck-k K] [--leaf-w W,..]   (SPSA's head-to-head pairs, below)

   A game is a pairs line (play.c's format: trainer side first) and a rep; its seed comes from the line's teams and the
   rep, not from its place in the file, so a split file, another build or another command plays the same game. The
   original AI's model keeps its own RNG across games (origbot.c); here it is set from the game's seed, so every game
   replays alone. Side 1 of the engine (the trainer's, pokeIDs 13-18) is the analyzed side and plays --p1 (adv).

   rate: one line per pairs line: SCENARIO GAME TEAM_T TEAM_P WINS DRAWS LOSSES TURNS, the trainer side's results;
   --per-game adds each game (up to 400) as its result (W, D, L) and a hash of the final battle.

   analyze: plays each game, keeps a snapshot at every turn's start (the battle, the advanced AI's memory, the model's
   RNG), and replays every free decision of side 1 with each legal action: every move it can select, every switch,
   every Pokemon it can send in after a faint or a pivot. A replay starts from the decision's turn: a choice at the
   turn's start is replayed with new luck for the whole turn (the foe's choice too); a replacement is reached with the
   turn's own luck, then the luck changes. Both players then play their own policies to the end. Replay i of every
   action of one decision draws the same luck (common random numbers). Each action gets --screen replays (default
   48); the chosen action and the best other one are then played --confirm more times (default 200) with fresh luck
   when the screen puts the other --gap or more above (default 0.04), and the chosen action always is, so its value
   is its policy's value at that point. When the confirmed gap is --gap2 or more (default 0.05), both values are
   measured again from 2 x --confirm fresh replays, which replace the first ones (so the selection does not bias them),
   and with --rollout-p0 P (adv) both are also played --confirm times with side 0
   played by P from the changed luck on (vc2, vb2): the same decision against another foe, which tells a general
   mistake from one that pays only against the original AI. A draw counts half. One JSON line per decision, then one
   per game.
   At a forced decision the AI still decides first (its memory records its own choice, as on the DS), then the action
   is replaced.

   luck: each game as rate plays it (the same game byte for byte), plus its luck. At every turn, once both sides have
   chosen, the turn's random part (order and its ties, Quick Claw, hits, crits, rolls, secondary effects, sleep,
   paralysis, confusion...) is played --luck-k more times (default 8) from the same point with fresh luck, side 0's
   model with fresh luck too, and the turn's luck is the judge's value after the real turn minus the replays' mean.
   The judge is fixed: the learned leaf (leaf.c), side 1's win chance, which is the result once the battle is over. It
   is evaluated before the replacements after faints. Each turn's luck has mean 0 given the turn's start, whatever the
   judge, so result - luck has the plain result's mean with less noise (backgammon's luck adjustment). --luck-k 0 plays
   rate's games with luck 0. --tune-s1/--tune-s0: the advanced AI's tuning (tune.h's order) on engine side 1 (the
   trainer's) or 0. Line: INDEX REP W|D|L LUCK TURNS HASH (INDEX: the pairs line, from 0).
   serve: reads "ID INDEX REP SEED" and two tunings (tune.h's order, theta+ then theta-) per stdin line, plays the pair
   theta+ on side 1 against theta- on side 0 (game A) and the sides swapped (game B), the same game seed, with luck,
   and prints "ID RA LUCKA RB LUCKB TURNSA TURNSB" (side 1's results). tools/sim/luck_spsa.py drives it.

   check: the snapshot test. Every game is replayed from each turn's snapshot with the game's own luck, and from each
   decision with its own action forced, and must end in the same battle byte for byte. */
#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#include "sim.h"
#include "internal.h"
#include "policy.h"
#include "origbot.h"
#include "lapol.h"
#include "leaf.h"

/* the second AI build of a dual binary (its own policy_advanced_b overrides this one); here none */
__attribute__((weak)) Policy policy_advanced_b(void)
{
    Policy p = { 0 };
    return p;
}

typedef struct {
    int team[2], n[2], slots[2][6], mteam[2][6], mslot[2][6];   /* [0] the trainer side (engine side 1) */
    char scenario[16];
    int game;
    u64 key;
} Line;

enum { D_CHOOSE, D_REPLACE };

typedef struct {
    u16 turn;
    u8 nth, kind;               /* nth: side 1's free decisions earlier in this turn */
    Action chosen;              /* as the battle carries it out */
    int nalt;
    Action alt[11];
} Dec;

/* side 1's policy wrapped: it records the decisions, or forces one action at one decision and changes the luck */
typedef struct {
    const Policy *inner;
    int nth;
    int recording;
    Dec *dec;
    int ndec, cap;
    int force_turn, force_nth;
    Action force;
    int reseed_at_force;
    u64 reseed;
    u64 pending;                /* a reading side's forced choice: the new luck, set once the turn's choices are made */
    Battle *capture;            /* if set, the battle as it is at the forced decision */
    u8 cap_act[3];              /* and the foe's committed action there (kind, idx) and whether foresight was trusted */
} Ctl;

extern unsigned char sim_foe_act[2];    /* battle.c read_side: side 0's committed action while side 1 chooses */
extern int sim_foe_valid;
int sim_fs_trusted(void);               /* bridge.c */

/* SIM_READ_SIDE=1: side 1, the analyzed one, chooses knowing side 0's committed action and, with SIM_FS, foresees the
   turn's rolls. A replay of its choice then keeps side 0's committed action (the game's own luck up to side 1's choice)
   and the turn's rolls when it foresaw them; the luck changes after (play_on) */
static int read_mode(void)
{
    static int v = -1;
    if (v < 0) {
        const char *e = getenv("SIM_READ_SIDE");
        v = e && *e == '1';
    }
    return v;
}

typedef struct {
    Battle b;
    u64 orng;
    unsigned char *ai;
} Snap;

static u64 mix(u64 x)
{
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}

/* g_alt0: the replay's luck has changed, so side 0 now plays the rollout policy (--rollout-p0) if this replay uses it
   (g_use_p0r) */
static int g_alt0, g_use_p0r;
static int g_trace;             /* sim cf trace: the replays print their turns */

static void reseed(Battle *b, u64 seed)
{
    g_alt0 = 1;
    b->rng = mix(seed) | 1;
    orig_rng_set(mix(seed ^ 0x6F726967626F74ULL));
}

/* ---------------------------------------------------------------- the pairs file */

static int read_lines(const char *path, Line **out)
{
    FILE *f = fopen(path, "r");
    char buf[512];
    int n = 0, cap = 0;
    Line *v = 0;
    if (!f) {
        fprintf(stderr, "cf: cannot open %s\n", path);
        exit(2);
    }
    while (fgets(buf, sizeof buf, f)) {
        Line l;
        char *p = buf + 5, *e;
        int k, i;
        if (strncmp(buf, "pair ", 5))
            continue;
        memset(&l, 0, sizeof l);
        if (sscanf(p, "%15s %d", l.scenario, &l.game) != 2)
            continue;
        while (*p == ' ') p++;
        while (*p && *p != ' ') p++;
        strtol(p, &e, 10);
        p = e;
        l.key = 0xCBF29CE484222325ULL;
        for (k = 0; k < 2; k++) {
            l.team[k] = (int)strtol(p, &e, 10), p = e;
            l.n[k] = (int)strtol(p, &e, 10), p = e;
            if (l.n[k] < 1 || l.n[k] > 6 || l.team[k] < -1 || l.team[k] >= sim_nteams) {
                fprintf(stderr, "cf: bad line %s", buf);
                exit(2);
            }
            l.key = (l.key ^ (u64)(l.team[k] + 7)) * 0x100000001B3ULL;
            for (i = 0; i < l.n[k]; i++) {
                l.slots[k][i] = (int)strtol(p, &e, 10), p = e;
                l.mteam[k][i] = l.team[k], l.mslot[k][i] = l.slots[k][i];
                if (l.team[k] < 0) {
                    l.mteam[k][i] = (int)strtol(p, &e, 10), p = e;
                    l.mslot[k][i] = (int)strtol(p, &e, 10), p = e;
                }
                l.key = (l.key ^ (u64)(l.mteam[k][i] * 8 + l.mslot[k][i] + 1)) * 0x100000001B3ULL;
            }
        }
        if (n == cap)
            v = realloc(v, sizeof *v * (size_t)(cap = cap ? 2 * cap : 256));
        v[n++] = l;
    }
    fclose(f);
    *out = v;
    return n;
}

static void setup(Battle *b, const Line *l, int level)
{
    int k, i;
    memset(b, 0, sizeof *b);
    for (k = 0; k < 2; k++) {
        int side = 1 - k, base = side ? 13 : 1;
        b->n[side] = l->n[k];
        for (i = 0; i < l->n[k]; i++)
            sim_build_mon(&b->party[side][i], &sim_teams[l->mteam[k][i]].mon[l->mslot[k][i]], level, base + i,
                          l->slots[k][i]);
        b->rand_team[side] = sim_teams[l->mteam[k][0]].pool == POOL_RANDOM;
    }
}

static u64 game_seed(u64 seed, const Line *l, int rep) { return mix(mix(seed) ^ mix(l->key + (u64)rep * 0x9E3779B97F4A7C15ULL)); }

/* ---------------------------------------------------------------- side 1's wrapper */

/* the action battle.c carries out for a policy's choice (its choose() and replacement() checks) */
static Action carried(const Battle *b, int s, int kind, Action a)
{
    int k, any = 0;
    if (kind == D_REPLACE) {
        if (a.idx < 1 || a.idx >= b->n[s] || !sim_alive(&b->party[s][a.idx]))
            for (a.idx = 1; a.idx < b->n[s] && !sim_alive(&b->party[s][a.idx]); a.idx++)
                ;
        a.kind = ACT_SWITCH;
        return a;
    }
    for (k = 0; k < 4; k++)
        any |= sim_legal_move(b, s, k);
    if (a.kind == ACT_SWITCH && (a.idx < 1 || a.idx >= b->n[s] || !sim_alive(&b->party[s][a.idx]) || sim_trapped(b, s)))
        a.kind = ACT_MOVE, a.idx = 4;
    if (a.kind == ACT_MOVE && a.idx < 4 && !sim_legal_move(b, s, a.idx))
        a.idx = 4;
    if (a.kind == ACT_MOVE && a.idx == 4 && any)
        for (k = 0; k < 4; k++)
            if (sim_legal_move(b, s, k)) {
                a.idx = k;
                break;
            }
    if (a.kind == ACT_NONE)
        a.kind = ACT_MOVE, a.idx = 4;
    return a;
}

static void record(Ctl *c, const Battle *b, int s, int kind, int nth, Action a)
{
    Dec d;
    int k, i;
    memset(&d, 0, sizeof d);
    d.turn = b->turn;
    d.nth = nth;
    d.kind = kind;
    d.chosen = carried(b, s, kind, a);
    if (kind == D_CHOOSE) {
        for (k = 0; k < 4; k++)
            if (b->party[s][0].moves[k] && sim_legal_move(b, s, k))
                d.alt[d.nalt++] = (Action){ ACT_MOVE, k };
        if (!d.nalt)
            d.alt[d.nalt++] = (Action){ ACT_MOVE, 4 };
        if (!sim_trapped(b, s))
            for (i = 1; i < b->n[s]; i++)
                if (sim_alive(&b->party[s][i]))
                    d.alt[d.nalt++] = (Action){ ACT_SWITCH, i };
    } else
        for (i = 1; i < b->n[s]; i++)
            if (sim_alive(&b->party[s][i]))
                d.alt[d.nalt++] = (Action){ ACT_SWITCH, i };
    if (d.nalt < 2)
        return;
    if (c->ndec == c->cap)
        c->dec = realloc(c->dec, sizeof *c->dec * (size_t)(c->cap = c->cap ? 2 * c->cap : 64));
    c->dec[c->ndec++] = d;
}

static void reached(Ctl *c, Battle *b, int s, int kind, Action *a)
{
    int nth = c->nth++;
    if (c->recording)
        record(c, b, s, kind, nth, *a);
    if (c->force_turn == b->turn && c->force_nth == nth) {
        if (c->capture) {
            *c->capture = *b;
            c->cap_act[0] = kind == D_CHOOSE && sim_foe_valid ? sim_foe_act[0] : 0;
            c->cap_act[1] = sim_foe_act[1];
            c->cap_act[2] = kind == D_CHOOSE && sim_fs_trusted();
        }
        *a = c->force;
        if (c->reseed_at_force) {
            if (kind == D_CHOOSE)
                c->pending = c->reseed;
            else
                reseed(b, c->reseed);
        }
        c->force_turn = -1;
    }
}

static Action w_choose(Battle *b, int s, void *ctx)
{
    Ctl *c = ctx;
    Action a = c->inner->choose(b, s, c->inner->ctx);
    reached(c, b, s, D_CHOOSE, &a);
    return a;
}

static int w_replace(Battle *b, int s, void *ctx)
{
    Ctl *c = ctx;
    Action a = { ACT_SWITCH, (u8)c->inner->replace(b, s, c->inner->ctx) };
    reached(c, b, s, D_REPLACE, &a);
    return a.idx;
}

static void w_start(Battle *b, void *ctx)
{
    Ctl *c = ctx;
    if (c->inner->battle_start)
        c->inner->battle_start(b, c->inner->ctx);
}

/* ---------------------------------------------------------------- games and replays */

typedef struct {
    Policy p0, p1, w1;          /* w1: side 1's policy wrapped in ctl */
    Policy p0r, w0;             /* p0r: side 0 in the generality replays; w0: side 0 as the game or the replay has it */
    int has_p0r;
    Ctl ctl;
    int level, max_turns;
    Snap *snap;                 /* snap[t]: before turn t is played */
    int nsnap, capsnap;
    unsigned long ai_size;
} Run;

static void snap_save(Run *r, Snap *s, const Battle *b)
{
    s->b = *b;
    s->orng = orig_rng_get();
    if (!s->ai)
        s->ai = malloc(r->ai_size);
    sim_ai_state_save(s->ai);
}

static void snap_load(const Snap *s, Battle *b)
{
    g_alt0 = 0;
    *b = s->b;
    b->verbose = g_trace;
    orig_rng_set(s->orng);
    sim_ai_state_load(s->ai);
}

static const Policy *side0(Run *r) { return g_use_p0r && g_alt0 && r->has_p0r ? &r->p0r : &r->p0; }
static Action w0_choose(Battle *b, int s, void *ctx)
{
    const Policy *p = side0(ctx);
    return p->choose(b, s, p->ctx);
}
static int w0_replace(Battle *b, int s, void *ctx)
{
    const Policy *p = side0(ctx);
    return p->replace(b, s, p->ctx);
}
static void w0_start(Battle *b, void *ctx)
{
    Run *r = ctx;
    if (r->p0.battle_start)
        r->p0.battle_start(b, r->p0.ctx);
}

static double result(const Battle *b) { return b->winner == 1 ? 1.0 : b->winner == 2 ? 0.5 : 0.0; }

static void play_on(Run *r, Battle *b)
{
    const Policy *pol[2] = { &r->w0, &r->w1 };
    Action act[2];
    while (b->winner < 0 && b->turn < r->max_turns) {
        r->ctl.nth = 0;
        if (!sim_turn_choose(b, pol, act))
            break;
        if (r->ctl.pending && !sim_fs_trusted()) {
            reseed(b, r->ctl.pending);
            r->ctl.pending = 0;
        }
        sim_turn_resolve(b, pol, act);
        if (r->ctl.pending) {
            reseed(b, r->ctl.pending);
            r->ctl.pending = 0;
        }
        if (!sim_turn_finish(b, pol))
            break;
    }
    if (b->winner < 0)
        b->winner = 2;
}

/* the game from its start; keep: a snapshot before every turn and side 1's decisions recorded */
static int g_verbose, g_rep = -1;
static void play_game(Run *r, Battle *b, const Line *l, u64 gs, int keep)
{
    setup(b, l, r->level);
    sim_leads(b, &r->p0, &r->p1);
    b->verbose = g_verbose;
    sim_start(b, gs);
    w0_start(b, r);
    w_start(b, &r->ctl);
    orig_rng_set(mix(gs ^ 0x6F726967626F74ULL));
    r->ctl.ndec = 0;
    r->ctl.recording = keep;
    r->ctl.force_turn = -1;
    r->nsnap = 0;
    while (b->winner < 0 && b->turn < r->max_turns) {
        if (keep) {
            if (r->nsnap == r->capsnap) {
                r->snap = realloc(r->snap, sizeof *r->snap * (size_t)(r->capsnap = r->capsnap ? 2 * r->capsnap : 64));
                memset(r->snap + r->nsnap, 0, sizeof *r->snap * (size_t)(r->capsnap - r->nsnap));
            }
            snap_save(r, &r->snap[r->nsnap++], b);
        }
        r->ctl.nth = 0;
        if (!sim_turn(b, &r->w0, &r->w1))
            break;
    }
    if (b->winner < 0)
        b->winner = 2;
    r->ctl.recording = 0;
    b->verbose = 0;
}

/* one replay of decision d with action a from snapshot sn (taken before d's turn); seed 0 keeps the game's own luck */
static double replay_from(Run *r, Battle *b, const Snap *sn, const Dec *d, Action a, u64 seed)
{
    int rd = d->kind == D_CHOOSE && read_mode();
    snap_load(sn, b);
    r->ctl.force_turn = d->turn;
    r->ctl.force_nth = d->nth;
    r->ctl.force = a;
    r->ctl.reseed_at_force = seed && (d->kind == D_REPLACE || rd);
    r->ctl.reseed = seed;
    r->ctl.pending = 0;
    if (seed && d->kind == D_CHOOSE && !rd)
        reseed(b, seed);
    play_on(r, b);
    r->ctl.force_turn = -1;
    return result(b);
}

static double replay(Run *r, Battle *b, const Dec *d, Action a, u64 seed)
{
    return replay_from(r, b, &r->snap[d->turn - 1], d, a, seed);
}

/* alt0: side 0 plays the rollout policy once the luck changes */
static double replays(Run *r, Battle *b, const Dec *d, Action a, u64 base, int n, int alt0)
{
    double sum = 0;
    int i;
    g_use_p0r = alt0;
    for (i = 0; i < n; i++)
        sum += replay(r, b, d, a, mix(base + (u64)i) | 1);
    g_use_p0r = 0;
    return n ? sum / n : 0;
}

static int same(Action x, Action y) { return x.kind == y.kind && x.idx == y.idx; }

/* ---------------------------------------------------------------- a rollout policy (sim cf mc) */

/* One step of policy improvement by rollouts: at every turn where side 1 has a free choice, each legal action is played
   n times from the turn's start with new luck (side 0: --rollout-p0 when given, else the game's p0), the AI's own policy
   after it, and the best one is taken when it beats the AI's own choice by margin or more; the turn itself is then
   played with the game's luck. Replacements stay the AI's. Returns side 1's result; *changed counts overridden
   choices. */
static double mc_game(Run *r, Battle *b, const Line *l, u64 gs, int n, double margin, int general, int *changed,
                      int *choices)
{
    Snap cur = { 0 };
    setup(b, l, r->level);
    sim_leads(b, &r->p0, &r->p1);
    sim_start(b, gs);
    w0_start(b, r);
    w_start(b, &r->ctl);
    orig_rng_set(mix(gs ^ 0x6F726967626F74ULL));
    r->ctl.recording = 0;
    r->ctl.force_turn = -1;
    while (b->winner < 0 && b->turn < r->max_turns) {
        Dec d;
        Action own = { ACT_NONE, 0 }, best;
        int i, k, oi = -1, bi = -1;
        double w[11], wa[11];
        snap_save(r, &cur, b);
        /* the AI's own choice this turn: the turn played once with its luck, recording */
        r->ctl.recording = 1;
        r->ctl.ndec = 0;
        r->ctl.nth = 0;
        sim_turn(b, &r->w0, &r->w1);
        r->ctl.recording = 0;
        for (k = 0; k < r->ctl.ndec; k++)
            if (r->ctl.dec[k].nth == 0 && r->ctl.dec[k].kind == D_CHOOSE)
                own = r->ctl.dec[k].chosen, d = r->ctl.dec[k];
        best = own;
        if (own.kind != ACT_NONE) {
            u64 base = mix(gs ^ (u64)d.turn * 0xD1B54A32D192ED03ULL);
            for (i = 0; i < d.nalt; i++) {
                w[i] = wa[i] = 0;
                g_use_p0r = !general;
                for (k = 0; k < n; k++)
                    w[i] += replay_from(r, b, &cur, &d, d.alt[i], mix(base + (u64)k) | 1);
                g_use_p0r = 1;
                for (k = 0; general && k < n; k++)
                    wa[i] += replay_from(r, b, &cur, &d, d.alt[i], mix(base + (u64)k) | 1);
                g_use_p0r = 0;
                w[i] /= n;
                wa[i] /= n;
                if (same(d.alt[i], own))
                    oi = i;
            }
            /* --general 1: only actions no worse than the AI's own with the rollout foe (--rollout-p0); 2: better */
            for (i = 0; oi >= 0 && i < d.nalt; i++)
                if (i == oi || !general || (general == 1 ? wa[i] >= wa[oi] : wa[i] > wa[oi]))
                    if (bi < 0 || w[i] > w[bi])
                        bi = i;
            (*choices)++;
            if (oi >= 0 && bi != oi && w[bi] - w[oi] >= margin) {
                best = d.alt[bi];
                (*changed)++;
            }
        }
        snap_load(&cur, b);
        r->ctl.force_turn = own.kind != ACT_NONE ? b->turn + 1 : -1;
        r->ctl.force_nth = 0;
        r->ctl.force = best;
        r->ctl.reseed_at_force = 0;
        r->ctl.nth = 0;
        if (!sim_turn(b, &r->w0, &r->w1))
            break;
        r->ctl.force_turn = -1;
    }
    r->ctl.force_turn = -1;
    if (b->winner < 0)
        b->winner = 2;
    free(cur.ai);
    return result(b);
}

/* ---------------------------------------------------------------- lookahead with a cheap playout policy (sim cf la) */

/* mc_game with the playouts of la_decide (lapol.c): both sides play the cheap policy from the decision's turn on, so
   neither the original AI's model nor the advanced AI runs inside a playout. --general keeps mc's filter: an action
   counts only if its full replays against --rollout-p0 (the advanced AI on both sides) are no worse (1) or better (2)
   than the AI's own choice's. --stats writes one line per decision (its work); --dump writes every K-th decision's
   root battle, actions, settings and values for lathumb.py. */
static FILE *g_stats, *g_dump;
static int g_la_only;               /* --only move|switch: overrides only into that kind of action */
static double g_la_veto = 9;        /* --veto V: override only when the AI's own choice is worth less than V */
static Policy g_la_pp[2];           /* --la-foe P / --la-self P: one side's playout policy instead of --play (host only) */
static const Policy *g_la_pol[2];
static int g_dump_every = 0;
static long g_ndec;

static double la_game(Run *r, Battle *b, const Line *l, u64 gs, const LaCfg *lc, double margin, int general, int *changed,
                      int *choices)
{
    Snap cur = { 0 };
    Battle *work = malloc(sizeof *work);
    setup(b, l, r->level);
    sim_leads(b, &r->p0, &r->p1);
    sim_start(b, gs);
    w0_start(b, r);
    w_start(b, &r->ctl);
    orig_rng_set(mix(gs ^ 0x6F726967626F74ULL));
    r->ctl.recording = 0;
    r->ctl.force_turn = -1;
    while (b->winner < 0 && b->turn < r->max_turns) {
        Dec d;
        Action own = { ACT_NONE, 0 }, best;
        int i, k, oi = -1, bi = -1;
        double w[11], wa[11];
        snap_save(r, &cur, b);
        r->ctl.recording = 1;
        r->ctl.ndec = 0;
        r->ctl.nth = 0;
        sim_turn(b, &r->w0, &r->w1);
        r->ctl.recording = 0;
        for (k = 0; k < r->ctl.ndec; k++)
            if (r->ctl.dec[k].nth == 0 && r->ctl.dec[k].kind == D_CHOOSE)
                own = r->ctl.dec[k].chosen, d = r->ctl.dec[k];
        best = own;
        if (own.kind != ACT_NONE) {
            u64 base = mix(gs ^ (u64)d.turn * 0xD1B54A32D192ED03ULL);
            LaCfg c = *lc;
            LaWork cnt = { 0, 0 };
            s32 wi[11];
            c.base_lo = (u32)base, c.base_hi = (u32)(base >> 32);
            la_decide(&cur.b, d.alt, d.nalt, &c, g_la_pol[0] ? g_la_pol[0] : la_policy(c.pol),
                      g_la_pol[1] ? g_la_pol[1] : la_policy(c.pol), work, wi, &cnt);
            for (i = 0; i < d.nalt; i++) {
                w[i] = wi[i] / (1000.0 * c.n);
                wa[i] = 0;
                g_use_p0r = 1;
                for (k = 0; general && k < c.n; k++)
                    wa[i] += replay_from(r, b, &cur, &d, d.alt[i], mix(base + (u64)k) | 1);
                g_use_p0r = 0;
                wa[i] /= c.n;
                if (same(d.alt[i], own))
                    oi = i;
            }
            for (i = 0; oi >= 0 && i < d.nalt; i++)
                if (i == oi || ((!general || (general == 1 ? wa[i] >= wa[oi] : wa[i] > wa[oi])) &&
                                (!g_la_only || d.alt[i].kind == g_la_only)))
                    if (bi < 0 || w[i] > w[bi])
                        bi = i;
            (*choices)++;
            if (oi >= 0 && bi != oi && w[bi] - w[oi] >= margin && w[oi] < g_la_veto) {
                best = d.alt[bi];
                (*changed)++;
            }
            if (g_stats)
                fprintf(g_stats, "%s %d %d %d %u %u %d %d %d %.3f %.3f\n", l->scenario, l->game, d.turn, d.nalt, cnt.turns,
                        cnt.calls, !same(best, own), own.kind, best.kind, oi >= 0 ? w[oi] : -1, bi >= 0 ? w[bi] : -1);
            if (g_dump && g_dump_every && g_ndec % g_dump_every == 0) {
                const unsigned char *q = (const unsigned char *)&cur.b;
                size_t z;
                fprintf(g_dump, "dec %s %d %d ", l->scenario, l->game, d.turn);
                for (z = 0; z < offsetof(Battle, verbose); z++)
                    fprintf(g_dump, "%02x", q[z]);
                fprintf(g_dump, " %d", d.nalt);
                for (i = 0; i < d.nalt; i++)
                    fprintf(g_dump, " %d %d", d.alt[i].kind, d.alt[i].idx);
                fprintf(g_dump, " %d %d %d %d %d %u %u", c.n, c.depth, c.eval, c.pol, c.max_turns, c.base_lo, c.base_hi);
                for (i = 0; i < d.nalt; i++)
                    fprintf(g_dump, " %d", wi[i]);
                fprintf(g_dump, " %u %u\n", cnt.turns, cnt.calls);
            }
            g_ndec++;
        }
        snap_load(&cur, b);
        r->ctl.force_turn = own.kind != ACT_NONE ? b->turn + 1 : -1;
        r->ctl.force_nth = 0;
        r->ctl.force = best;
        r->ctl.reseed_at_force = 0;
        r->ctl.nth = 0;
        if (!sim_turn(b, &r->w0, &r->w1))
            break;
        r->ctl.force_turn = -1;
    }
    r->ctl.force_turn = -1;
    if (b->winner < 0)
        b->winner = 2;
    free(cur.ai);
    free(work);
    return result(b);
}

/* ---------------------------------------------------------------- what the report reads about a decision */

static const char *move_cat(int mv)
{
    const MoveRec *m = &sim_moves[mv];
    int k;
    if (m->cls)
        return "attack";
    if (m->heal > 0)
        return "heal";
    if (m->sick == SICK_SLP || m->sick == SICK_PAR || m->sick == SICK_BRN || m->sick == SICK_PSN || m->sick == SICK_FRZ)
        return "status";
    for (k = 0; k < 3; k++)
        if (m->rank_type[k] && m->rank_val[k] > 0 && (m->target == TG_USER || m->target == TG_USER_SIDE ||
                                                      m->target == TG_USER_OR_ALLY || m->target == TG_USER_SIDE_MONS))
            return "boost";
    for (k = 0; k < 3; k++)
        if (m->rank_type[k] && m->rank_val[k] < 0)
            return "debuff";
    if (m->quality == Q_SIDE)
        return "side";
    if (m->quality == Q_FIELD)
        return "field";
    return "other";
}

/* what a damaging move also does: raises or lowers the user's stats, switches it out, hurts it */
enum { E_PIVOT_CODE = 228 };     /* move.c E_PIVOT: U-turn, Volt Switch */
static const char *attack_fx(int mv)
{
    const MoveRec *m = &sim_moves[mv];
    int k;
    if (!m->cls)
        return "";
    if (m->effect == E_PIVOT_CODE)
        return "pivot";
    for (k = 0; k < 3; k++)
        if (m->quality == Q_DAMAGE_EFFECT_USER && m->rank_type[k] && m->rank_val[k] > 0)
            return "boost";
    for (k = 0; k < 3; k++)
        if (m->quality == Q_DAMAGE_EFFECT_USER && m->rank_type[k] && m->rank_val[k] < 0)
            return "drop";
    if (m->drain < 0)
        return "recoil";
    if (m->flags & FL_RECHARGE)
        return "recharge";
    return "";
}

/* the report's damage features: side s's moves against the foe on the field, as the battle deals them (not the engine's
   simulation, which misses Air Balloon), one hit at the lowest and highest roll times the mean hit count, no crit */
typedef struct { int legal, dmin, dmax, first; } Feat;
static void feat_moves(const Battle *b, int s, Feat f[4])
{
    const Mon *me = &b->party[s][0], *foe = &b->party[s ^ 1][0];
    OrigMove o[4];
    int k;
    orig_moves(b, s, o);
    for (k = 0; k < 4; k++) {
        const MoveRec *m = &sim_moves[me->moves[k]];
        DamageQ q;
        f[k].legal = o[k].legal;
        f[k].first = o[k].first;
        f[k].dmin = f[k].dmax = 0;
        if (!me->moves[k] || m->cls == CLS_STATUS || !sim_alive(foe))
            continue;
        memset(&q, 0, sizeof q);
        q.a = me, q.d = foe, q.va = &b->v[s], q.vd = &b->v[s ^ 1];
        q.a_active = q.d_active = 1;
        q.weather = sim_weather(b), q.terrain = b->terrain;
        q.screen = m->cls == CLS_PHYSICAL ? b->side[s ^ 1].reflect || b->side[s ^ 1].veil :
                   b->side[s ^ 1].screen || b->side[s ^ 1].veil;
        q.roll = 100;
        f[k].dmax = sim_damage(&q, me->moves[k]) * (m->hits_min + m->hits_max) / 2;
        q.roll = 85;
        f[k].dmin = q.fixed ? f[k].dmax : sim_damage(&q, me->moves[k]) * (m->hits_min + m->hits_max) / 2;
    }
}

static void json_mon(const Mon *m)
{
    printf("{\"sp\": \"%s\", \"hp\": %d, \"max\": %d, \"st\": %d}", sim_species_name[m->species], m->hp, m->maxhp, m->status);
}

static int alive_count(const Battle *b, int s)
{
    int i, n = 0;
    for (i = 0; i < b->n[s]; i++)
        n += sim_alive(&b->party[s][i]);
    return n;
}

/* the battle at the decision: its turn's snapshot replayed with the game's own luck up to it */
static void print_state(Run *r, Battle *b, const Dec *d)
{
    Feat mine[4], theirs[4];
    int k, threat = 0, i, fmax = 0;
    r->ctl.capture = b + 1;
    replay(r, b, d, d->chosen, 0);
    r->ctl.capture = 0;
    b = b + 1;
    feat_moves(b, 1, mine);
    feat_moves(b, 0, theirs);
    for (k = 0; k < 4; k++) {
        if (theirs[k].legal && theirs[k].dmax >= b->party[1][0].hp && b->party[1][0].hp)
            threat = threat > 1 ? threat : theirs[k].dmin >= b->party[1][0].hp ? 2 : 1;
        if (theirs[k].legal && theirs[k].dmax > fmax)
            fmax = theirs[k].dmax;
    }
    printf("\"me\": ");
    json_mon(&b->party[1][0]);
    printf(", \"foe\": ");
    json_mon(&b->party[0][0]);
    printf(", \"alive\": [%d, %d], \"faster\": %d, \"threat\": %d, \"fmax\": %d, \"fbusy\": %d, ",
           alive_count(b, 1), alive_count(b, 0),
           sim_eff_speed(b, 1) > sim_eff_speed(b, 0) ? 1 : sim_eff_speed(b, 1) < sim_eff_speed(b, 0) ? -1 : 0, threat, fmax,
           b->v[0].recharge ? 1 : b->v[0].charging ? 2 : 0);   /* the foe must recharge (1) or lands a charged move (2) */
    {   /* the foe's committed action (kind 1 move, 2 switch; 0 blind), foresight trusted, the foe's moves on my active,
           and the stage of my attacking stat (that of my highest-dmax attack) */
        int best = -1, cls;
        printf("\"fact\": [%d, %d], \"fs\": %d, \"fdmg\": [", r->ctl.cap_act[0], r->ctl.cap_act[1], r->ctl.cap_act[2]);
        for (k = 0; k < 4; k++)
            printf("%s[%d, %d]", k ? ", " : "", theirs[k].legal ? theirs[k].dmin : 0, theirs[k].legal ? theirs[k].dmax : 0);
        for (k = 0; k < 4; k++)
            if (mine[k].legal && mine[k].dmax > 0 && (best < 0 || mine[k].dmax > mine[best].dmax))
                best = k;
        cls = best >= 0 ? sim_moves[b->party[1][0].moves[best]].cls : CLS_PHYSICAL;
        printf("], \"stgm\": %d, \"opts\": [", b->v[1].stage[cls == CLS_SPECIAL ? STAT_SPA : STAT_ATK]);
    }
    for (i = 0; i < d->nalt; i++) {
        Action a = d->alt[i];
        printf("%s{", i ? ", " : "");
        if (a.kind == ACT_MOVE && a.idx < 4) {
            const Feat *o = &mine[a.idx];
            int mv = b->party[1][0].moves[a.idx], fhp = b->party[0][0].hp;
            printf("\"a\": \"move:%s\", \"cat\": \"%s\", \"fx\": \"%s\", \"dmin\": %d, \"dmax\": %d, \"ko\": %d, "
                   "\"first\": %d, \"acc\": %d", sim_move_name[mv], move_cat(mv), attack_fx(mv), o->dmin, o->dmax,
                   fhp && o->dmin >= fhp ? 2 : fhp && o->dmax >= fhp ? 1 : 0, o->first, sim_moves[mv].acc);
        } else if (a.kind == ACT_MOVE)
            printf("\"a\": \"move:Struggle\", \"cat\": \"attack\"");
        else {
            /* the Pokemon as if it were on the field against the foe now: its best hit on the foe and the foe's on it
               (% of the target's HP, the lowest and highest roll), and which is faster */
            const Mon *m = &b->party[1][a.idx];
            Battle *h = malloc(sizeof *h);
            Feat in[4], out[4];
            int hit_lo = 0, hit_hi = 0, took_lo = 0, took_hi = 0, fhp = b->party[0][0].hp;
            *h = *b;
            h->party[1][0] = b->party[1][a.idx];
            h->party[1][a.idx] = b->party[1][0];
            reset_volatile(h, 1, 0);
            feat_moves(h, 1, in);
            feat_moves(h, 0, out);
            for (k = 0; k < 4; k++) {
                if (fhp && in[k].dmax * 100 / fhp > hit_hi)
                    hit_hi = in[k].dmax * 100 / fhp, hit_lo = in[k].dmin * 100 / fhp;
                if (out[k].legal && m->hp && out[k].dmax * 100 / m->hp > took_hi)
                    took_hi = out[k].dmax * 100 / m->hp, took_lo = out[k].dmin * 100 / m->hp;
            }
            printf("\"a\": \"%s:%s\", \"cat\": \"%s\", \"hp\": %d, \"max\": %d, \"hit\": [%d, %d], \"took\": [%d, %d], "
                   "\"fast\": %d", d->kind == D_CHOOSE ? "switch" : "send", sim_species_name[m->species],
                   d->kind == D_CHOOSE ? "switch" : "send", m->hp, m->maxhp, hit_lo, hit_hi, took_lo, took_hi,
                   sim_eff_speed(h, 1) > sim_eff_speed(h, 0) ? 1 : sim_eff_speed(h, 1) < sim_eff_speed(h, 0) ? -1 : 0);
            free(h);
        }
        printf("}");
    }
    printf("]");
}


static void analyze_game(Run *r, Battle *b, const Line *l, int rep, u64 gs, double res, int turns, int screen, int confirm,
                         double gap, double gap2)
{
    int di, i;
    double v0 = -1;
    Dec *dec = malloc(sizeof *dec * (size_t)(r->ctl.ndec + 1));
    int ndec = r->ctl.ndec;
    memcpy(dec, r->ctl.dec, sizeof *dec * (size_t)ndec);
    for (di = 0; di < ndec; di++) {
        const Dec *d = &dec[di];
        double w[11], vc, vb = -1, vc2 = -1, vb2 = -1;
        int ci = -1, bi = -1, nb = 0;
        u64 base = mix(gs ^ (u64)(di + 1) * 0xD1B54A32D192ED03ULL);
        for (i = 0; i < d->nalt; i++) {
            w[i] = replays(r, b, d, d->alt[i], base, screen, 0);
            if (same(d->alt[i], d->chosen))
                ci = i;
        }
        for (i = 0; i < d->nalt; i++)
            if (i != ci && (bi < 0 || w[i] > w[bi]))
                bi = i;
        base = mix(base ^ 0xC0FFEE);
        vc = ci >= 0 ? replays(r, b, d, d->chosen, base, confirm, 0) : -1;
        if (bi >= 0 && ci >= 0 && w[bi] - w[ci] >= gap) {
            vb = replays(r, b, d, d->alt[bi], base, confirm, 0);
            nb = confirm;
            if (vb - vc >= gap2) {          /* a candidate: both values again from twice as many fresh replays, which
                                               the selection never saw */
                u64 b2 = mix(base ^ 0xBEEF);
                vc = replays(r, b, d, d->chosen, b2, 2 * confirm, 0);
                vb = replays(r, b, d, d->alt[bi], b2, 2 * confirm, 0);
                nb = 2 * confirm;
            }
            if (r->has_p0r && vb - vc >= gap2) {    /* the same two actions when side 0 plays the rollout policy */
                u64 b3 = mix(base ^ 0xFACE);
                vc2 = replays(r, b, d, d->chosen, b3, confirm, 1);
                vb2 = replays(r, b, d, d->alt[bi], b3, confirm, 1);
            }
        }
        if (v0 < 0)
            v0 = vc;
        printf("{\"type\": \"dec\", \"m\": \"%s/%d\", \"tt\": %d, \"tp\": %d, \"rep\": %d, \"seed\": %llu, \"res\": %.1f, "
               "\"turns\": %d, \"d\": %d, \"turn\": %d, \"nth\": %d, \"kind\": \"%s\", ",
               l->scenario, l->game, l->team[0], l->team[1], rep, (unsigned long long)gs, res, turns, di, d->turn, d->nth,
               d->kind == D_CHOOSE ? "choose" : "replace");
        print_state(r, b, d);
        printf(", \"w\": [");
        for (i = 0; i < d->nalt; i++)
            printf("%s%.4f", i ? ", " : "", w[i]);
        printf("], \"screen\": %d, \"chosen\": %d, \"alt\": %d, \"vc\": %.4f, \"vb\": %.4f, \"nb\": %d, \"vc2\": %.4f, "
               "\"vb2\": %.4f}\n", screen, ci, bi, vc, vb, nb, vc2, vb2);
    }
    printf("{\"type\": \"game\", \"m\": \"%s/%d\", \"tt\": %d, \"tp\": %d, \"rep\": %d, \"seed\": %llu, \"res\": %.1f, "
           "\"turns\": %d, \"ndec\": %d, \"v0\": %.4f}\n",
           l->scenario, l->game, l->team[0], l->team[1], rep, (unsigned long long)gs, res, turns, ndec, v0);
    fflush(stdout);
    free(dec);
}

/* ---------------------------------------------------------------- luck-adjusted results (sim cf luck, sim cf serve) */

/* SIM_LUCK_DIR=D: one line per rate game in D/luck_<pid>.txt (rc31 L): the teams, the rep, the result, the turns, the
   luck counters (battle.c sim_luck_emit) and the steering counts (bridge.c sim_steer_emit) */
void sim_steer_emit(FILE *f);
static void luck_line(const Line *l, int rep, const Battle *b)
{
    static FILE *f;
    static int tried;
    if (!tried) {
        const char *d = getenv("SIM_LUCK_DIR");
        char path[1024];
        tried = 1;
        if (d) {
            snprintf(path, sizeof path, "%s/luck_%d.txt", d, (int)getpid());
            f = fopen(path, "w");
        }
    }
    if (!f)
        return;
    fprintf(f, "%d %d %d %c %d", l->team[0], l->team[1], rep, "WDL"[b->winner == 1 ? 0 : b->winner == 2 ? 1 : 2], b->turn);
    sim_luck_emit(f);
    sim_steer_emit(f);
    fputc('\n', f);
    fflush(f);
}

/* SIM_CTR_DIR=D: one line per rate game in D/ctr_<pid>.txt (rc33 RD): the teams, the rep, the result, the turns, then
   per engine side (0 first) battle.c's perfect counters and RD's outcomes (sim_ctr_emit) */
static void ctr_line(const Line *l, int rep, const Battle *b)
{
    static FILE *f;
    static int tried;
    if (!tried) {
        const char *d = getenv("SIM_CTR_DIR");
        char path[1024];
        tried = 1;
        if (d) {
            snprintf(path, sizeof path, "%s/ctr_%d.txt", d, (int)getpid());
            f = fopen(path, "w");
        }
    }
    if (!f)
        return;
    fprintf(f, "%d %d %d %c %d", l->team[0], l->team[1], rep, "WDL"[b->winner == 1 ? 0 : b->winner == 2 ? 1 : 2], b->turn);
    sim_ctr_emit(f);
    fputc('\n', f);
    fflush(f);
}

static u32 battle_hash(const Battle *b)
{
    Battle h = *b;
    u64 x = 0xCBF29CE484222325ULL;
    const u8 *q = (const u8 *)&h;
    size_t k;
    h.oracle = 0;
    for (k = 0; k < sizeof h; k++)
        x = (x ^ q[k]) * 0x100000001B3ULL;
    return (u32)(x ^ (x >> 32));
}

static int g_luck_k = 8;
static FILE *g_feat;                /* --feat FILE: the judge's features at each judged state, and each game's result */
static int g_cur_li, g_cur_rep;
static Snap g_turn0, g_turn1;       /* the turn after both choices, and after its real random part */

static double judge(const Battle *b, const LeafCache *lc) { return leaf_value(b, lc) / 1000.0; }

/* --feat: one row per judged state (the real turn's first, then each replay's): the result if the battle is over
   (else -1), then the leaf's features; luck_fit.py fits a judge on them */
static void feat_row(const Battle *b, const LeafCache *lc)
{
    s32 f[LEAF_NF];
    int j;
    leaf_features(b, lc, f);
    fprintf(g_feat, "%.1f", b->winner < 0 ? -1.0 : result(b));
    for (j = 0; j < LEAF_NF; j++)
        fprintf(g_feat, " %d", f[j]);
    fprintf(g_feat, "\n");
}

/* the game as play_game plays it (keep 0); returns side 1's summed luck */
static double play_game_luck(Run *r, Battle *b, const Line *l, u64 gs)
{
    const Policy *pol[2] = { &r->w0, &r->w1 };
    double luck = 0;
    setup(b, l, r->level);
    sim_leads(b, &r->p0, &r->p1);
    b->verbose = 0;
    sim_start(b, gs);
    w0_start(b, r);
    w_start(b, &r->ctl);
    orig_rng_set(mix(gs ^ 0x6F726967626F74ULL));
    r->ctl.ndec = 0;
    r->ctl.recording = 0;
    r->ctl.force_turn = -1;
    while (b->winner < 0 && b->turn < r->max_turns) {
        Action act[2];
        r->ctl.nth = 0;
        if (!sim_turn_choose(b, pol, act))
            break;
        if (g_luck_k > 0) {
            LeafCache lc;
            double real, mean = 0;
            int k;
            leaf_cache(b, &lc);
            snap_save(r, &g_turn0, b);
            sim_turn_resolve(b, pol, act);
            real = judge(b, &lc);
            if (g_feat) {
                fprintf(g_feat, "T %d %d %d\n", g_cur_li, g_cur_rep, b->turn);
                feat_row(b, &lc);
            }
            snap_save(r, &g_turn1, b);
            for (k = 0; k < g_luck_k; k++) {
                u64 x = mix(gs ^ (u64)b->turn * 0xD1B54A32D192ED03ULL ^ (u64)(k + 1) * 0x9E3779B97F4A7C15ULL);
                snap_load(&g_turn0, b);
                b->rng = x | 1;
                orig_rng_set(mix(x ^ 0x6F726967626F74ULL));
                sim_turn_resolve(b, pol, act);
                mean += judge(b, &lc);
                if (g_feat)
                    feat_row(b, &lc);
            }
            snap_load(&g_turn1, b);
            luck += real - mean / g_luck_k;
        } else
            sim_turn_resolve(b, pol, act);
        if (!sim_turn_finish(b, pol))
            break;
    }
    if (b->winner < 0)
        b->winner = 2;
    return luck;
}

static int parse_tune(const char *str, u16 *v)
{
    int n = 0, nt = sim_ai_tune_n();
    char *e;
    while (n < nt) {
        long x = strtol(str, &e, 10);
        if (e == str)
            break;
        v[n++] = (u16)x;
        str = *e == ',' ? e + 1 : e;
    }
    if (n != nt) {
        fprintf(stderr, "cf: a tuning needs %d values, got %d\n", nt, n);
        exit(2);
    }
    return n;
}

static int cmd_serve(Run *r, Battle *b, const Line *lines, int nlines)
{
    char buf[1024];
    int nt = sim_ai_tune_n();
    u16 tp[32], tm[32];
    while (fgets(buf, sizeof buf, stdin)) {
        long id;
        int li, rep, off, j;
        unsigned long long seed;
        char *p = buf, *e;
        double ra, la, rb, lb;
        int ta;
        if (sscanf(p, "%ld %d %d %llu%n", &id, &li, &rep, &seed, &off) != 4 || li < 0 || li >= nlines)
            break;
        p += off;
        for (j = 0; j < 2 * nt; j++) {
            long x = strtol(p, &e, 10);
            if (e == p)
                break;
            (j < nt ? tp : tm)[j % nt] = (u16)x, p = e;
        }
        if (j != 2 * nt)
            break;
        sim_ai_tune_set(0, tp);
        sim_ai_tune_set(1, tm);
        la = play_game_luck(r, b, &lines[li], game_seed(seed, &lines[li], rep));
        ra = result(b);
        ta = b->turn;
        sim_ai_tune_set(0, tm);
        sim_ai_tune_set(1, tp);
        lb = play_game_luck(r, b, &lines[li], game_seed(seed, &lines[li], rep));
        rb = result(b);
        printf("%ld %.1f %.6f %.1f %.6f %d %d\n", id, ra, la, rb, lb, ta, b->turn);
        fflush(stdout);
    }
    return 0;
}

/* ---------------------------------------------------------------- the command */

static Policy pick(const char *name)
{
    if (!strcmp(name, "greedy"))
        return policy_greedy;
    if (!strcmp(name, "gswitch"))
        return policy_gswitch;
    if (!strcmp(name, "gko"))
        return policy_gko;
    if (!strcmp(name, "gsw2"))
        return policy_gsw2;
    if (!strcmp(name, "adv"))
        return policy_advanced();
    if (!strcmp(name, "advb") && policy_advanced_b().name)
        return policy_advanced_b();
    if (!strcmp(name, "orig"))
        return policy_orig;
    fprintf(stderr, "cf: unknown policy %s (adv, orig, greedy%s)\n", name, policy_advanced_b().name ? ", advb" : "");
    exit(2);
}

static int same_battle(const Battle *x, const Battle *y)
{
    Battle a = *x, c = *y;
    a.oracle = c.oracle = 0;
    a.verbose = c.verbose = 0;
    return !memcmp(&a, &c, sizeof a);
}

/* sim cf teams: index, trainer id, level-80 pool flag, size, name, species */
static int cmd_teams(void)
{
    int t, i;
    for (t = 0; t < sim_nteams; t++) {
        printf("%d\t%d\t%d\t%d\t%s\t", t, sim_teams[t].trainer, sim_teams[t].pool, sim_teams[t].n, sim_teams[t].name);
        for (i = 0; i < sim_teams[t].n; i++)
            printf("%s%s", i ? "," : "", sim_species_name[sim_teams[t].mon[i].species]);
        printf("\n");
    }
    return 0;
}

int cmd_cf(int argc, char **argv)
{
    const char *mode = argc > 1 ? argv[1] : "", *pairs = 0, *p0 = "orig", *p1 = "adv";
    int reps = 1, lost_only = 0, per_game = 0, screen = 48, confirm = 200, i, li, rep;
    double gap = 0.04, gap2 = 0.05;
    int t_turn = 0, t_nth = 0, t_n = 3;
    double mc_margin = 0.05;
    int mc_general = 0;
    const char *t_act = 0;
    const char *p0r = 0;
    const char *tune_s1 = 0, *tune_s0 = 0;
    int l_from = 0, l_to = 1 << 30;
    LaCfg lc = { 32, 0, LA_EVAL_HP, LA_POL_GREEDY, 200, 0, 0 };
    u64 seed = 1;
    Line *lines;
    int nlines;
    Run *r = calloc(1, sizeof *r);
    Battle *b = malloc(2 * sizeof *b), *fin = malloc(sizeof *fin);     /* b[1]: print_state's capture */
    r->level = 100;
    r->max_turns = 200;
    if (!strcmp(mode, "teams"))
        return cmd_teams();
    for (i = 2; i < argc; i++) {
        if (!strcmp(argv[i], "--pairs") && i + 1 < argc) pairs = argv[++i];
        else if (!strcmp(argv[i], "--reps") && i + 1 < argc) reps = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--seed") && i + 1 < argc) seed = strtoull(argv[++i], 0, 10);
        else if (!strcmp(argv[i], "--p0") && i + 1 < argc) p0 = argv[++i];
        else if (!strcmp(argv[i], "--p1") && i + 1 < argc) p1 = argv[++i];
        else if (!strcmp(argv[i], "--level") && i + 1 < argc) r->level = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--max-turns") && i + 1 < argc) r->max_turns = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--screen") && i + 1 < argc) screen = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--confirm") && i + 1 < argc) confirm = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--gap") && i + 1 < argc) gap = atof(argv[++i]);
        else if (!strcmp(argv[i], "--gap2") && i + 1 < argc) gap2 = atof(argv[++i]);
        else if (!strcmp(argv[i], "--rollout-p0") && i + 1 < argc) p0r = argv[++i];
        else if (!strcmp(argv[i], "--lost-only")) lost_only = 1;
        else if (!strcmp(argv[i], "--per-game")) per_game = 1;
        else if (!strcmp(argv[i], "--turn") && i + 1 < argc) t_turn = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--nth") && i + 1 < argc) t_nth = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--act") && i + 1 < argc) t_act = argv[++i];
        else if (!strcmp(argv[i], "--n") && i + 1 < argc) t_n = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--margin") && i + 1 < argc) mc_margin = atof(argv[++i]);
        else if (!strcmp(argv[i], "--general") && i + 1 < argc) mc_general = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--depth") && i + 1 < argc) lc.depth = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--eval") && i + 1 < argc) {
            i++;
            lc.eval = !strcmp(argv[i], "count") ? LA_EVAL_COUNT : !strcmp(argv[i], "mix") ? LA_EVAL_MIX :
                      !strcmp(argv[i], "race") ? LA_EVAL_RACE : LA_EVAL_HP;
        } else if (!strcmp(argv[i], "--play") && i + 1 < argc) {
            i++;
            lc.pol = !strcmp(argv[i], "gswitch") ? LA_POL_GSWITCH : !strcmp(argv[i], "gko") ? LA_POL_GKO :
                     !strcmp(argv[i], "gsw2") ? LA_POL_GSW2 : LA_POL_GREEDY;
        } else if (!strcmp(argv[i], "--stats") && i + 1 < argc) g_stats = fopen(argv[++i], "w");
        else if (!strcmp(argv[i], "--dump") && i + 1 < argc) g_dump = fopen(argv[++i], "w");
        else if (!strcmp(argv[i], "--dump-every") && i + 1 < argc) g_dump_every = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--only") && i + 1 < argc) i++, g_la_only = !strcmp(argv[i], "switch") ? ACT_SWITCH : ACT_MOVE;
        else if (!strcmp(argv[i], "--veto") && i + 1 < argc) g_la_veto = atof(argv[++i]);
        else if (!strcmp(argv[i], "--la-foe") && i + 1 < argc) g_la_pp[0] = pick(argv[++i]), g_la_pol[0] = &g_la_pp[0];
        else if (!strcmp(argv[i], "--la-self") && i + 1 < argc) g_la_pp[1] = pick(argv[++i]), g_la_pol[1] = &g_la_pp[1];
        else if (!strcmp(argv[i], "--rep") && i + 1 < argc) g_rep = atoi(argv[++i]), reps = reps > g_rep ? reps : g_rep + 1;
        else if (!strcmp(argv[i], "--luck-k") && i + 1 < argc) g_luck_k = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--feat") && i + 1 < argc) g_feat = fopen(argv[++i], "w");
        else if (!strcmp(argv[i], "--tune-s1") && i + 1 < argc) tune_s1 = argv[++i];
        else if (!strcmp(argv[i], "--tune-s0") && i + 1 < argc) tune_s0 = argv[++i];
        else if (!strcmp(argv[i], "--lines") && i + 1 < argc) sscanf(argv[++i], "%d:%d", &l_from, &l_to);
        else if (!strcmp(argv[i], "--leaf-w") && i + 1 < argc) {
            const char *q = argv[++i];
            char *e;
            int k;
            for (k = 0; k <= LEAF_NF; k++, q = *e == ',' ? e + 1 : e)
                g_leaf_w[k] = strtod(q, &e);
        }
        else {
            fprintf(stderr, "cf: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    if (!strcmp(mode, "show"))
        g_verbose = 1;
    if (!pairs || (strcmp(mode, "rate") && strcmp(mode, "analyze") && strcmp(mode, "check") && strcmp(mode, "show") &&
                   strcmp(mode, "trace") && strcmp(mode, "mc") && strcmp(mode, "features") && strcmp(mode, "la") &&
                   strcmp(mode, "lead") && strcmp(mode, "luck") && strcmp(mode, "serve"))) {
        fprintf(stderr, "usage: sim cf rate|analyze|check --pairs FILE [options] (see cf.c)\n");
        return 2;
    }
    nlines = read_lines(pairs, &lines);
    r->p0 = pick(p0);
    r->p1 = pick(p1);
    if (p0r) {
        r->p0r = pick(p0r);
        r->has_p0r = 1;
    }
    r->w0 = (Policy){ r->p0.name, w0_choose, w0_replace, w0_start, r };
    r->ctl.inner = &r->p1;
    r->w1 = (Policy){ r->p1.name, w_choose, w_replace, w_start, &r->ctl };
    r->ai_size = sim_ai_state_size();
    {
        u16 v[32];
        if (tune_s1)
            parse_tune(tune_s1, v), sim_ai_tune_set(0, v);
        if (tune_s0)
            parse_tune(tune_s0, v), sim_ai_tune_set(1, v);
    }
    if (!strcmp(mode, "serve")) {
        if (strcmp(p0, "adv") || strcmp(p1, "adv")) {
            fprintf(stderr, "cf serve: head to head needs --p0 adv --p1 adv\n");
            return 2;
        }
        return cmd_serve(r, b, lines, nlines);
    }
    if (!strcmp(mode, "luck")) {
        for (li = l_from; li < nlines && li < l_to; li++)
            for (rep = 0; rep < reps; rep++) {
                double luck;
                g_cur_li = li, g_cur_rep = rep;
                luck = play_game_luck(r, b, &lines[li], game_seed(seed, &lines[li], rep));
                if (g_feat)
                    fprintf(g_feat, "E %d %d %.1f\n", li, rep, result(b));
                printf("%d %d %c %.6f %d %08x\n", li, rep, "WDL"[b->winner == 1 ? 0 : b->winner == 2 ? 1 : 2], luck, b->turn,
                       battle_hash(b));
            }
        return 0;
    }
    if (!strcmp(mode, "lead")) {        /* each line's leads as the policies pick them (tools/lead_check.py) */
        for (li = 0; li < nlines; li++) {
            int s;
            setup(b, &lines[li], r->level);
            sim_leads(b, &r->p0, &r->p1);
            printf("lead %s %d", lines[li].scenario, lines[li].game);
            for (s = 1; s >= 0; s--)
                printf(" %d %s", b->party[s][0].id - (s ? 13 : 1), mon_name(&b->party[s][0]));
            printf("\n");
        }
        return 0;
    }
    if (!strcmp(mode, "show")) {        /* the games' turns on stderr, as sim play -v prints them */
        for (li = 0; li < nlines; li++)
            for (rep = 0; rep < reps; rep++) {
                if (g_rep >= 0 && rep != g_rep)
                    continue;
                fprintf(stderr, "=== %s/%d rep %d\n", lines[li].scenario, lines[li].game, rep);
                play_game(r, b, &lines[li], game_seed(seed, &lines[li], rep), 0);
            }
        return 0;
    }
    if (!strcmp(mode, "trace")) {       /* replays of one decision with one action, their turns on stderr */
        int di, k;
        double sum = 0;
        if (g_rep < 0 || !t_turn || !t_act) {
            fprintf(stderr, "trace: --rep, --turn and --act m:SLOT|s:INDEX are needed\n");
            return 2;
        }
        play_game(r, b, &lines[0], game_seed(seed, &lines[0], g_rep), 1);
        for (di = 0; di < r->ctl.ndec; di++) {
            Dec *d = &r->ctl.dec[di];
            Action a = { t_act[0] == 's' ? ACT_SWITCH : ACT_MOVE, (u8)atoi(t_act + 2) };
            u64 base = mix(game_seed(seed, &lines[0], g_rep) ^ (u64)(di + 1) * 0xD1B54A32D192ED03ULL);
            if (d->turn != t_turn || d->nth != t_nth)
                continue;
            for (k = 0; k < t_n; k++) {
                double v;
                fprintf(stderr, "=== replay %d\n", k);
                g_trace = 1;
                g_use_p0r = r->has_p0r;
                v = replay(r, b, d, a, mix(base + (u64)k) | 1);
                g_use_p0r = 0;
                g_trace = 0;
                fprintf(stderr, "=== result %.1f (turn %d)\n", v, b->turn);
                sum += v;
            }
            printf("%d replays: %.3f\n", t_n, sum / t_n);
            return 0;
        }
        fprintf(stderr, "trace: no free decision at turn %d, nth %d\n", t_turn, t_nth);
        return 1;
    }
    if (!strcmp(mode, "features")) {    /* each decision's state, as analyze prints it, without the replays */
        for (li = 0; li < nlines; li++)
            for (rep = 0; rep < reps; rep++) {
                u64 gs = game_seed(seed, &lines[li], rep);
                int di;
                play_game(r, b, &lines[li], gs, 1);
                if (lost_only && result(b) >= 1.0)
                    continue;
                for (di = 0; di < r->ctl.ndec; di++) {
                    Dec d = r->ctl.dec[di];
                    printf("{\"type\": \"feat\", \"tt\": %d, \"tp\": %d, \"rep\": %d, \"d\": %d, \"turn\": %d, ",
                           lines[li].team[0], lines[li].team[1], rep, di, d.turn);
                    print_state(r, b, &d);
                    printf("}\n");
                }
            }
        return 0;
    }
    if (!strcmp(mode, "mc")) {          /* the rollout policy: one line per pairs line, as rate prints, plus its overrides */
        for (li = 0; li < nlines; li++) {
            int res[3] = { 0, 0, 0 }, changed = 0, choices = 0;
            for (rep = 0; rep < reps; rep++) {
                double v = mc_game(r, b, &lines[li], game_seed(seed, &lines[li], rep), t_n, mc_margin, mc_general, &changed,
                                   &choices);
                res[v == 1.0 ? 0 : v == 0.5 ? 1 : 2]++;
            }
            printf("%s %d %d %d %d %d %d 0 %d %d\n", lines[li].scenario, lines[li].game, lines[li].team[0], lines[li].team[1],
                   res[0], res[1], res[2], changed, choices);
            fflush(stdout);
        }
        return 0;
    }
    if (!strcmp(mode, "la")) {          /* as mc prints, plus each game's result */
        lc.n = t_n;
        lc.max_turns = r->max_turns;
        for (li = 0; li < nlines; li++) {
            int res[3] = { 0, 0, 0 }, changed = 0, choices = 0;
            char games[1024] = "";
            for (rep = 0; rep < reps; rep++) {
                double v = la_game(r, b, &lines[li], game_seed(seed, &lines[li], rep), &lc, mc_margin, mc_general, &changed,
                                   &choices);
                res[v == 1.0 ? 0 : v == 0.5 ? 1 : 2]++;
                if (rep < 400)
                    games[rep] = "WDL"[v == 1.0 ? 0 : v == 0.5 ? 1 : 2], games[rep + 1] = 0;
            }
            printf("%s %d %d %d %d %d %d 0 %d %d %s\n", lines[li].scenario, lines[li].game, lines[li].team[0],
                   lines[li].team[1], res[0], res[1], res[2], changed, choices, games);
            fflush(stdout);
            if (g_stats)
                fflush(g_stats);
        }
        if (g_dump)
            fclose(g_dump);
        return 0;
    }
    if (!strcmp(mode, "rate")) {
        for (li = 0; li < nlines; li++) {
            int res[3] = { 0, 0, 0 };
            long turns = 0;
            char games[4096];
            for (rep = 0; rep < reps; rep++) {
                play_game(r, b, &lines[li], game_seed(seed, &lines[li], rep), 0);
                res[b->winner == 1 ? 0 : b->winner == 2 ? 1 : 2]++;
                turns += b->turn;
                luck_line(&lines[li], rep, b);
                ctr_line(&lines[li], rep, b);
                if (per_game && rep < 400) {   /* the result and a hash of the final battle: equal hashes, the same game */
                    Battle h = *b;
                    u64 x = 0xCBF29CE484222325ULL;
                    const u8 *q = (const u8 *)&h;
                    size_t k;
                    h.oracle = 0;
                    for (k = 0; k < sizeof h; k++)
                        x = (x ^ q[k]) * 0x100000001B3ULL;
                    snprintf(games + 10 * rep, sizeof games - 10 * (size_t)rep, " %c%08x", "WDL"[b->winner == 1 ? 0 : b->winner == 2 ? 1 : 2],
                             (unsigned)(x ^ (x >> 32)));
                }
            }
            printf("%s %d %d %d %d %d %d %ld%s\n", lines[li].scenario, lines[li].game, lines[li].team[0], lines[li].team[1],
                   res[0], res[1], res[2], turns, per_game ? games : "");
        }
        return 0;
    }
    if (!strcmp(mode, "check")) {
        long games = 0, tests = 0, bad = 0;
        for (li = 0; li < nlines; li++)
            for (rep = 0; rep < reps; rep++) {
                u64 gs = game_seed(seed, &lines[li], rep);
                int t, di;
                play_game(r, b, &lines[li], gs, 1);
                *fin = *b;
                games++;
                for (t = 0; t < r->nsnap; t++) {
                    snap_load(&r->snap[t], b);
                    play_on(r, b);
                    tests++;
                    if (!same_battle(b, fin)) {
                        bad++;
                        fprintf(stderr, "check: %s/%d rep %d: the replay from turn %d's snapshot ends otherwise\n",
                                lines[li].scenario, lines[li].game, rep, t + 1);
                    }
                }
                for (di = 0; di < r->ctl.ndec; di++) {
                    Dec d = r->ctl.dec[di];
                    replay(r, b, &d, d.chosen, 0);
                    tests++;
                    if (!same_battle(b, fin)) {
                        bad++;
                        fprintf(stderr, "check: %s/%d rep %d: decision %d (turn %d, %s) forced to its own action ends otherwise\n",
                                lines[li].scenario, lines[li].game, rep, di, d.turn, d.kind == D_CHOOSE ? "choose" : "replace");
                    }
                }
            }
        printf("check: %ld games, %ld replays, %ld differ\n", games, tests, bad);
        return bad != 0;
    }
    for (li = 0; li < nlines; li++)
        for (rep = 0; rep < reps; rep++) {
            u64 gs = game_seed(seed, &lines[li], rep);
            double res;
            int turns;
            play_game(r, b, &lines[li], gs, 1);
            res = result(b);
            turns = b->turn;
            if (lost_only && res >= 1.0)
                continue;
            analyze_game(r, b, &lines[li], rep, gs, res, turns, screen, confirm, gap, gap2);
        }
    return 0;
}
