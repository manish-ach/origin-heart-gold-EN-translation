/* The drama observer's stand-in. The Spanish simulator's observer (drama_obs.c) traced trainer reactions for the battle
   experience, which this project does not port. battle.c, move.c and play.c keep their calls to it unchanged: with no
   observer open (g_obs NULL) the OBS() hooks do nothing, and these entry points do nothing either. sim play's output
   was byte-identical with or without the Spanish observer, so it is here too. */
#include "sim.h"
#include "internal.h"

struct DramaObs *g_obs;

void drama_obs_open(const char *path) {}
void drama_obs_close(void) {}
void drama_obs_battle(const Battle *b, u64 seed, int trainer, int level, int bot, int hard, int ace) {}
void drama_obs_end(const Battle *b, int max_turns) {}
void obs_turn(const Battle *b, const Action act[2]) {}
void obs_begin(const Battle *b, int side) {}
void obs_end(const Battle *b) {}
void obs_faint(const Battle *b, int s, int id) {}
void obs_sendin(const Battle *b, int s, int id) {}
void obs_crit(const Battle *b, int s, int stage) {}
void obs_miss(const Battle *b, int s, int acc) {}
