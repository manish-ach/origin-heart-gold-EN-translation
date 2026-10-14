/* Lookahead with a self-contained playout policy: what a DS build could run without overlay 11 or the advanced AI
   inside a playout. Both sides play a cheap policy from the decision's turn on; side 1's first choice is forced to
   the action under test. The same code is compiled for the host (sim cf la) and for the DS CPU (lathumb.py). */
#ifndef LAPOL_H
#define LAPOL_H
#include "sim.h"

enum { LA_POL_GREEDY, LA_POL_GSWITCH, LA_POL_GKO, LA_POL_GSW2, LA_POL_N };
enum { LA_EVAL_HP, LA_EVAL_COUNT, LA_EVAL_MIX, LA_EVAL_RACE, LA_EVAL_N };

typedef struct {
    s32 n;              /* playouts per action */
    s32 depth;          /* turns per playout; 0: to the end of the battle */
    s32 eval;           /* LA_EVAL_*: the value of a playout that stops before the end */
    s32 pol;            /* LA_POL_*: both sides' policy inside a playout */
    s32 max_turns;      /* the battle's turn limit (a draw) */
    u32 base_lo, base_hi;   /* playout k draws its luck from la_mix(base + k) | 1 */
} LaCfg;

typedef struct {
    u32 turns;          /* turns simulated */
    u32 calls;          /* playout-policy decisions: choices and replacements */
} LaWork;

u64 la_mix(u64 x);
s32 la_leaf(const Battle *b, int eval);     /* side 1's value per mille */
/* w[i]: the sum of action i's n playout values, per mille (win 1000, draw 500, loss 0, a leaf la_leaf) */
void la_decide(const Battle *root, const Action *alt, int nalt, const LaCfg *c, const Policy *pol0, const Policy *pol1,
               Battle *work, s32 *w, LaWork *cnt);
extern const Policy policy_gswitch, policy_gko, policy_gsw2;
const Policy *la_policy(int pol);

#endif
