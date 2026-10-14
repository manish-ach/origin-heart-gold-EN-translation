/* A learned position value (ai_research_new's leaf, AUC 0.849 on held-out matchups): features of a battle from side 1's
   view, a logistic model fitted on simulator self-play, and a per-turn cache of the pairwise damage they need. sim cf
   luck uses it as the fixed judge of the luck at each turn. */
#ifndef LEAF_H
#define LEAF_H
#include "sim.h"
#define LEAF_NF 18
typedef struct {
    s32 dmg[2][6][6];       /* [side][set of attacker][set of defender]: best expected hit, mean roll x accuracy x hits */
    s32 spe[2][6];          /* raw Speed by set */
    s8 prio[2][6][6];       /* priority of that best hit */
} LeafCache;
void leaf_cache(const Battle *b, LeafCache *c);
void leaf_features(const Battle *b, const LeafCache *c, s32 *f);
s32 leaf_value(const Battle *b, const LeafCache *c);     /* side 1's win chance per mille */
extern double g_leaf_w[LEAF_NF + 1];
#endif
