/* The simulator's command line.

     sim play [--games N] [--seed S] [--p0 adv|orig|greedy] [--p1 adv|orig|greedy] [--level L] [--sizes N:M] [--pick first|random]
              [--pairs FILE] [--reps R] [--max-turns T] [-v]
     sim damage < QUERIES
     sim bench CASES
     sim validate OBS [--ai] [--game N] [--orig-dump FILE] [--orig-eval FILE]

   play: N games (default 100) between trainer teams of the level-80 pool (aivsai's), drawn with the seed, or the
   matchups of a pairs file (tools/sim/run.py writes them from the emulator's logs); one JSON line per game on stdout
   in tools/sim/logstats.py's schema (side index 0 = the trainer side = engine client 1), the speed on stderr.
   Side 0 of the engine (the player's) plays --p0, side 1 (the trainer's) --p1; orig is the model of the original
   AI (origbot.c), greedy the baseline bot. A pairs line names a mixed team (aivsai --teams mixed) as -1 n, then
   (set, team, slot) per member.
   bench: the AI bench's recorded decisions through the bridge (bench.c; tools/sim/bench_check.py grades them).
   validate: the emulator's logged turns replayed and graded (validate.c; tools/sim/validate.py runs and reads it).
   damage: one line per query, the engine simulation's damage (the maximum roll, no crit) for
     q MOVE WEATHER TERRAIN  then for the attacker and the defender:
       SPECIES LEVEL HP MAXHP ATK DEF SPA SPD SPE TYPE0 TYPE1 TYPE2 ABILITY ITEM STATUS STAGE*7 (stages -6..6) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "sim.h"
#include "policy.h"

static int read_mon_q(Mon *m, Volatile *v)
{
    unsigned sp, lv, hp, mhp, st[5], t[3], ab, it, status;
    int sg[7], i;
    if (scanf("%u %u %u %u %u %u %u %u %u %u %u %u %u %u %u %d %d %d %d %d %d %d", &sp, &lv, &hp, &mhp, &st[0], &st[1],
              &st[2], &st[3], &st[4], &t[0], &t[1], &t[2], &ab, &it, &status, &sg[0], &sg[1], &sg[2], &sg[3], &sg[4],
              &sg[5], &sg[6]) != 22)
        return 0;
    memset(m, 0, sizeof *m);
    memset(v, 0, sizeof *v);
    m->species = sp, m->level = lv, m->hp = hp, m->maxhp = mhp, m->ability = ab, m->item = it, m->status = status;
    for (i = 0; i < 5; i++)
        m->stat[i] = st[i];
    m->types[0] = t[0], m->types[1] = t[1];
    for (i = 0; i < 3; i++)
        v->types[i] = t[i];
    for (i = 0; i < 7; i++)
        v->stage[i] = sg[i];
    v->ability = ab;
    return 1;
}

static int cmd_damage(void)
{
    char tag[8];
    while (scanf("%7s", tag) == 1) {
        unsigned move, weather, terrain;
        Mon a, d;
        Volatile va, vd;
        DamageQ q;
        if (strcmp(tag, "q") || scanf("%u %u %u", &move, &weather, &terrain) != 3 || !read_mon_q(&a, &va) ||
            !read_mon_q(&d, &vd)) {
            fprintf(stderr, "damage: bad query\n");
            return 2;
        }
        memset(&q, 0, sizeof q);
        q.a = &a, q.d = &d, q.va = &va, q.vd = &vd;
        q.a_active = q.d_active = 1;
        q.weather = weather, q.terrain = terrain;
        q.roll = 100;
        q.sim = 1;
        printf("%d\n", move < (unsigned)sim_nmoves ? sim_damage(&q, move) : 0);
    }
    return 0;
}

int main(int argc, char **argv)
{
    if (argc >= 2 && !strcmp(argv[1], "damage"))
        return cmd_damage();
    if (argc >= 2 && !strcmp(argv[1], "play"))
        return cmd_play(argc - 1, argv + 1);
    if (argc >= 2 && !strcmp(argv[1], "bench"))
        return cmd_bench(argc - 1, argv + 1);
    if (argc >= 2 && !strcmp(argv[1], "cf"))
        return cmd_cf(argc - 1, argv + 1);
    if (argc >= 2 && !strcmp(argv[1], "validate"))
        return cmd_validate(argc - 1, argv + 1);
    fprintf(stderr, "usage: sim play [options] | sim damage < queries | sim bench CASES | sim validate OBS [--ai]\n");
    return 1;
}
