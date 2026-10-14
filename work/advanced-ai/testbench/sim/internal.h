/* What battle.c and move.c share. */
#ifndef SIM_INTERNAL_H
#define SIM_INTERNAL_H
#include "sim.h"

int chance(Battle *b, int pct);

/* The random decisions, by kind. Without an oracle they sample exactly as before (a seed replays a game); with one
   (validate.c) the oracle picks the outcome the log shows and grades the model's probability of it. */
enum { K_TIE, K_QUICK, K_ACC, K_OHKO, K_CRIT, K_HITS, K_SICK, K_RANK, K_FLINCH, K_CONTACT, K_SPORE, K_FOCUSBAND,
       K_WAKE, K_THAW, K_PARA, K_CONF_END, K_CONF_HIT, K_PROTECT, K_SHEDSKIN, K_MOODY, K_LOCK_END, K_BIND_LEN,
       K_PHAZE, K_METRONOME, K_SLEEPTALK, K_ROLL, K_MOODY_DOWN, K_ACUPRESSURE, K_CALL, K_N };
extern const u16 *g_call_cand;      /* K_CALL: the moves Assist can call (the validator picks the logged one) */
extern int g_called;                /* the called move as it starts (K_CALL with n = 0 moves the validator's cursor) */
/* what the simulator did, for the validator to compare with the log's messages */
enum { N_STATUS, N_CONFUSE, N_STAT, N_FAINT, N_SENDIN, N_WEATHER, N_TERRAIN, N_ITEM, N_HAZARD, N_PROTECT, N_MISS,
       N_FAIL, N_SELFHIT, N_FLINCH, N_SUB, N_NOEFFECT, N_HIT, N_N };
typedef struct Oracle Oracle;
struct Oracle {
    int (*yes)(Oracle *o, Battle *b, int kind, int side, double p);                  /* 1: it happens */
    int (*pick)(Oracle *o, Battle *b, int kind, int side, int n, const double *p);   /* one of n outcomes */
    int (*damage)(Oracle *o, Battle *b, int side, int hit, int crit, const int *cand); /* a hit: the 16 rolls' damage */
    void (*note)(Oracle *o, Battle *b, int code, int side, int a, int c);
    int arg;            /* set before a K_SICK (the condition) or K_RANK (rank type, x16 if lowering) decision */
};
int yes(Battle *b, int kind, int side, int pct);
int yes_1in(Battle *b, int kind, int side, unsigned n);
extern int g_owner, g_tracked;      /* the side whose move or end of turn draws now (-1 none); a tracked roll draws */
void note(Battle *b, int code, int side, int a, int c);
void end_of_turn(Battle *b);
void reset_volatile(Battle *b, int s, int keep_pass);
int staged(int stat, int stage);
const char *mon_name(const Mon *m);
int has_type_v(const Volatile *v, int t);
void transform(Battle *b, int s, int t);
void future_lands(Battle *b, int t);      /* the end of a turn: a pending Future Sight or Doom Desire on side t */     /* side s becomes side t's Pokemon (Transform, Imposter) */
int item_of(const Battle *b, int s);
int is_sun(int w);
int is_rain(int w);
int grounded(const Battle *b, int s);
int forced_slot(const Battle *b, int s);
int bench_count(const Battle *b, int s);
int v_magic_guard(const Battle *b, int s);
void heal(Battle *b, int s, int amount);
int chip(Battle *b, int s, int amount);
int boost(Battle *b, int s, int stat, int n, int by_foe);
void consume(Battle *b, int s);
void white_herb(Battle *b, int s);
void extreme_weather_leaves(Battle *b, int s);
void berry_check(Battle *b, int s);
void status_berry(Battle *b, int s);
void fainted(Battle *b, int s);
int check_end(Battle *b);
void set_weather(Battle *b, int w, int setter_side, int turns);
void set_terrain(Battle *b, int t, int setter_side);
void switch_in(Battle *b, int s, int i, int pass);
int replace(Battle *b, int s, const Policy *p, int pivot);
void replace_fainted(Battle *b, const Policy *const pol[2]);

/* the drama observer (drama_obs.c): a call does nothing unless SIM_DRAMA_TRACE opened it, and only for the battle it
   watches (copies of the battle are ignored); it never draws from the RNG */
struct DramaObs;
extern struct DramaObs *g_obs;
#ifdef SIM_DS                       /* the DS build of the turn engine (la/ds) has no observer */
#define OBS(call) ((void)0)
#else
#define OBS(call) (g_obs ? (void)(call) : (void)0)
#endif
void obs_turn(const Battle *b, const Action act[2]);
void obs_begin(const Battle *b, int side);         /* a window: one action (side), the end of the turn or the */
void obs_end(const Battle *b);                     /* replacements (-1); its events become one moment */
void obs_faint(const Battle *b, int s, int id);
void obs_sendin(const Battle *b, int s, int id);
void obs_crit(const Battle *b, int s, int stage);
void obs_miss(const Battle *b, int s, int acc);

/* move.c */
void use_move(Battle *b, int s, int slot, const Policy *const pol[2]);
/* main status on side s's Pokemon (ST_*); bad: bad poison; by: the side that caused it (-1 none); returns 1 if it took */
int inflict(Battle *b, int s, int st, int bad, int by);

#endif
