/* protect_check: the simulator's Protect streak against the DS traces of tools/rngtrace.py groups T4c and T4d
   (qa/aivsai/rc33_PR.md). Snorlax (side 1, slower) and Breloom (side 0) play scripted moves. An oracle answers every
   roll: each K_PROTECT roll holds and its p is recorded, full paralysis and flinches happen only in the scripted lost
   turns, every other chance below 1 fails. Each turn compares Snorlax's roll (1 in n, 0: none) and its streak byte
   after the turn with the trace. Exit 1 on a mismatch.   make build/protect_check && build/protect_check */
#include <stdio.h>
#include <string.h>
#include "sim.h"
#include "sim_ids.h"
#include "internal.h"

#define T 8
typedef struct {
    const char *name;
    u16 xmoves[4], fmoves[4];
    u8 xstatus, lost;           /* lost: the turn (1-based) whose full paralysis or flinch stops Snorlax */
    s8 x[T], f[T];              /* the slot each side uses per turn, -1: the script ends */
    unsigned roll[T];           /* Snorlax's K_PROTECT roll that turn: 1 in n, 0 none */
    u8 byte[T];                 /* its streak byte after the turn (the next turn's trace watch) */
} Case;

static const Case cases[] = {
    { "endure", { M_PROTECT, M_ENDURE, M_CRAFTYSHIELD, M_TACKLE }, { M_SPLASH }, 0, 0,
      { 0, 1, 0, 0, 3, 0, 1, -1 }, { 0, 0, 0, 0, 0, 0, 0 }, { 0, 3, 9, 27, 0, 0, 3 }, { 1, 2, 3, 4, 4, 1, 2 } },
    { "crafty", { M_PROTECT, M_ENDURE, M_CRAFTYSHIELD, M_TACKLE }, { M_SPLASH }, 0, 0,
      { 0, 2, 0, 0, 2, 2, -1 }, { 0, 0, 0, 0, 0, 0 }, { 0, 0, 0, 3, 0, 0 }, { 1, 1, 1, 2, 2, 2 } },
    { "par", { M_PROTECT, M_ENDURE, M_CRAFTYSHIELD, M_TACKLE }, { M_SPLASH }, ST_PAR, 2,
      { 0, 0, 0, -1 }, { 0, 0, 0 }, { 0, 0, 0 }, { 1, 0, 1 } },
    { "par_tackle", { M_PROTECT, M_ENDURE, M_CRAFTYSHIELD, M_TACKLE }, { M_SPLASH }, ST_PAR, 2,
      { 0, 3, 0, 0, -1 }, { 0, 0, 0, 0 }, { 0, 0, 0, 3 }, { 1, 0, 1, 2 } },
    { "flinch", { M_PROTECT, M_ENDURE, M_CRAFTYSHIELD, M_TACKLE }, { M_SPLASH, M_BITE }, 0, 2,
      { 0, 3, 0, 0, -1 }, { 0, 1, 0, 0 }, { 0, 0, 0, 3 }, { 1, 0, 1, 2 } },
    { "guards", { M_PROTECT, M_WIDEGUARD, M_QUICKGUARD, M_MATBLOCK }, { M_SPLASH }, 0, 0,
      { 0, 1, 2, 0, 3, 0, 2, -1 }, { 0, 0, 0, 0, 0, 0, 0 }, { 0, 0, 0, 27, 0, 0, 0 }, { 1, 2, 3, 4, 0, 1, 2 } },
    /* Breloom protects first in turns 1 and 3, so Snorlax's Protect moves last and fails (the DS draws first at s > 0;
       the simulator's draw is its own, so only the byte is compared there) */
    { "last", { M_PROTECT, M_ENDURE, M_CRAFTYSHIELD, M_TACKLE }, { M_SPLASH, M_PROTECT }, 0, 0,
      { 0, 0, 0, 0, 0, -1 }, { 1, 0, 1, 0, 0 }, { 0, 0, 0, 0, 3 }, { 0, 1, 0, 1, 2 } },
};

static int g_turn, g_lost;
static unsigned g_roll;

static int o_yes(Oracle *o, Battle *b, int kind, int side, double p)
{
    if (kind == K_PROTECT) {
        if (side == 1)
            g_roll = p < 1 ? (unsigned)(1 / p + 0.5) : 0;     /* p 1: the streak is 0, the DS draws nothing */
        return 1;
    }
    if (kind == K_PARA || kind == K_FLINCH)
        return g_turn == g_lost;
    return p >= 0.999;
}
static int o_pick(Oracle *o, Battle *b, int kind, int side, int n, const double *p) { return 0; }
static int o_damage(Oracle *o, Battle *b, int side, int hit, int crit, const int *cand) { return cand[0]; }
static void o_note(Oracle *o, Battle *b, int code, int side, int a, int c) {}

static const Case *g_case;
static Action script(Battle *b, int side, void *ctx)
{
    Action a = { ACT_MOVE, (u8)(side ? g_case->x[g_turn - 1] : g_case->f[g_turn - 1]) };
    return a;
}
static int no_replace(Battle *b, int side, void *ctx) { return 0; }

int main(void)
{
    static Oracle oracle = { o_yes, o_pick, o_damage, o_note, 0 };
    const Policy pol = { "script", script, no_replace, 0, 0, 0 };
    int bad = 0;
    for (size_t c = 0; c < sizeof cases / sizeof *cases; c++) {
        const Case *k = g_case = &cases[c];
        SetRec x = { S_SNORLAX, 0, 0, { 0 }, 100, 0, 31, { 252, 0, 252, 0, 0, 0 } };
        SetRec f = { S_BRELOOM, 0, 0, { 0 }, 100, 0, 31, { 0 } };
        Battle b;
        memcpy(x.moves, k->xmoves, sizeof x.moves);
        memcpy(f.moves, k->fmoves, sizeof f.moves);
        memset(&b, 0, sizeof b);
        sim_build_mon(&b.party[0][0], &f, 100, 1, 0);
        sim_build_mon(&b.party[1][0], &x, 100, 13, 0);
        b.party[1][0].status = k->xstatus;
        b.n[0] = b.n[1] = 1;
        sim_start(&b, 1);
        b.oracle = &oracle;
        g_lost = k->lost;
        for (g_turn = 1; g_turn <= T && k->x[g_turn - 1] >= 0; g_turn++) {
            int t = g_turn - 1, ok;
            g_roll = 0;
            sim_turn(&b, &pol, &pol);
            ok = g_roll == k->roll[t] && b.v[1].protects == k->byte[t];
            if (!strcmp(k->name, "last") && (t == 2))
                ok = b.v[1].protects == k->byte[t];
            bad += !ok;
            printf("%-10s t%d %-12s roll 1/%u byte %u%s\n", k->name, g_turn, sim_move_name[k->xmoves[k->x[t]]], g_roll,
                   b.v[1].protects, ok ? "" : "   MISMATCH");
            if (!ok)
                printf("           the DS: roll 1/%u byte %u\n", k->roll[t], k->byte[t]);
        }
    }
    printf("%s: %d mismatches\n", bad ? "FAIL" : "PASS", bad);
    return bad != 0;
}
