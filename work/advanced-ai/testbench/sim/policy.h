/* The policies that play the simulator (policy.c: the greedy bot; bridge.c: the advanced AI through the host build),
   and the play command (play.c). */
#ifndef POLICY_H
#define POLICY_H
#include "sim.h"

extern const Policy policy_greedy;
extern const Policy policy_random;     /* uxcheck's random-move player (rc33 V) */
Policy policy_advanced(void);           /* the host build of tools/ai/advai.c and replace.c, both sides at once */
int cmd_play(int argc, char **argv);
int cmd_bench(int argc, char **argv);
int cmd_validate(int argc, char **argv);
void sim_ai_counts(long *decisions, long *fallbacks, long *replacements);
unsigned long sim_ai_state_size(void);  /* the advanced AI's memory between decisions (sim cf's snapshots) */
void sim_ai_state_save(void *dst);
void sim_ai_state_load(const void *src);
int sim_ai_tune_n(void);                 /* the advanced AI's tuning table (tune.h), one copy per side: */
void sim_ai_tune_get(int tside, u16 *v); /* tside 0 the trainer side (engine side 1), 1 the player side */
void sim_ai_tune_set(int tside, const u16 *v);
int cmd_cf(int argc, char **argv);

#endif
