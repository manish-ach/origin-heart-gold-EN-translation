#include <stdio.h>
#include <stddef.h>
#include "sim.h"
#define P(f) printf("_Static_assert(offsetof(Battle, " #f ") == %zu, \"" #f "\");\n", offsetof(Battle, f))
int main(void)
{
    P(party); P(n); P(v); P(side); P(weather); P(weather_turns); P(terrain); P(terrain_turns); P(trick_room); P(turn);
    P(rng); P(winner); P(last_faint); P(tally); P(last_used); P(last_hit); P(tf_saved); P(verbose);
    printf("_Static_assert(sizeof(Mon) == %zu, \"Mon\");\n", sizeof(Mon));
    printf("_Static_assert(sizeof(Volatile) == %zu, \"Volatile\");\n", sizeof(Volatile));
    printf("_Static_assert(sizeof(Side) == %zu, \"Side\");\n", sizeof(Side));
    printf("_Static_assert(sizeof(Tally) == %zu, \"Tally\");\n", sizeof(Tally));
    printf("_Static_assert(sizeof(Action) == %zu, \"Action\");\n", sizeof(Action));
    printf("_Static_assert(sizeof(LaCfg) == 28, \"LaCfg\");\n");
    printf("/* host sizeof(Battle) = %zu */\n", sizeof(Battle));
    return 0;
}
