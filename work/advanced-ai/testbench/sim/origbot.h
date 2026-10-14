/* A model of the hack's original trainer AI (overlay 11), for games against the advanced AI (origbot.c). */
#ifndef ORIGBOT_H
#define ORIGBOT_H
#include <stdio.h>
#include "sim.h"

/* what the model reads about one of a Pokemon's moves against the foe on the field */
typedef struct {
    int slot, move, legal;
    int cls, type, power, prio, acc, effect, quality, sick, target;
    int eff;                    /* x4 effectiveness in the engine's simulation (0 immune, 4 neutral, 16 double) */
    int dmin, dmax;             /* one hit at the lowest and highest roll, no crit, times the usual hit count */
    int ko_min, ko_max;         /* dmin / dmax reach the foe's HP */
    int first;                  /* it acts before the foe's fastest-priority reply (priority, then Speed) */
    int works;                  /* a status move whose effect can take (model of the original AI's -10 checks) */
    int fkey[5];                /* its foe row's level in the fitted table (foe_key): kind, KO, strongest, eff, priority */
} OrigMove;

extern const Policy policy_orig;
/* the model's own RNG, which lasts across games: sim cf sets it per game and keeps it in its snapshots */
u64 orig_rng_get(void);
void orig_rng_set(u64 r);

void orig_moves(const Battle *b, int s, OrigMove f[4]);
/* the model's probability of each option: p[0..3] the move slots, p[4] Struggle, p[5 + i] a switch to party index i */
void orig_choice(const Battle *b, int s, double p[11]);
int orig_replace_pick(const Battle *b, int s, double p[6]);

/* the original AI's logged factor sums, one per move: its rows on one target (aivsai's 'scores' lines) */
typedef struct { int n; short move[4], val[4]; } OrigScores;

/* one JSON line per logged decision for fitting (tools/sim/origfit.py): the model's inputs, the logged choice and the
   logged rows on the user ('scores') and on the foe ('foe_scores', logs from 2026-10-05) */
void orig_dump_decision(FILE *f, const Battle *b, int s, int gi, int turn, int kind, int arg, const OrigScores *own,
                        const OrigScores *foe);
void orig_dump_replace(FILE *f, const Battle *b, int s, int gi, int turn, int set);

#endif
