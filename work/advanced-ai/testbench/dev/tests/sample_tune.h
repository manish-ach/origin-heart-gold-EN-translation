/* A sample of tools/ai/tune.h in the format of the tuning design (task T1 writes the real one).
 * tune.h: name, default, lo, hi, step (tools/aitune.py parses this list) */
#ifndef TUNE_H
#define TUNE_H

#define TUNE_VERSION 1
#define TUNE_LIST(X) \
    X(TEMPO,          100,  40,  200,  40) \
    X(WORTH_BASE,     250, 100,  450, 100) \
    X(MY_ROLL,        890, 850,  924,  20) /* my damage per hit, per-mille of the max roll */ \
    X(THEIR_ROLL,     960, 926, 1000,  20) \
    X(SWITCH_COST,     60,  10,  150,  24) \
    X(KO_TEMPO,       120,   0,  300,  48) \
    X(DAMAGE_CREDIT,   90,   0,  200,  36) \
    X(ROLE_W,        1000,   0, 2000, 400) \
    X(LAST_BONUS,     500, 200, 1500, 200)

#define TUNE_ENUM(n, d, lo, hi, st) TU_##n,
#define TUNE_DEF(n, d, lo, hi, st) d,
enum { TUNE_LIST(TUNE_ENUM) TUNE_N };
#define TUNE_MAGIC 0x454E5554u          /* "TUNE" */

#endif
