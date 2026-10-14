/* sim bench CASES: the trainer AI bench's recorded first decisions (tools/hostai/replay.py writes the case file) as
   simulator battles, decided by the advanced AI through the simulator's bridge, one JSON line per case in
   tools/hostai/replay.c's format (id, ret, ov11, call, debug). The engine's simulations come from damage.c, not
   from the record, so this checks the bridge's view of the battle and the damage port together against the DS.
   tools/sim/bench_check.py grades it. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sim.h"
#include "policy.h"

extern int sim_ai_call[4];
long sim_ai_ov11(void);
const void *host_debug(int side);

static int read_case(FILE *f, Battle *b, char *id, int *items)
{
    char tag[16];
    unsigned d, w, t, s, it[4], n0, n1;
    memset(b, 0, sizeof *b);
    if (fscanf(f, "%15s", tag) != 1)
        return 0;
    if (strcmp(tag, "case") || fscanf(f, "%79s %u %u %u %u %u %u %u %u %u %u", id, &d, &w, &t, &s, &it[0], &it[1], &it[2],
                                      &it[3], &n0, &n1) != 11) {
        fprintf(stderr, "bench: bad case header\n");
        exit(2);
    }
    *items = it[0] || it[1] || it[2] || it[3] || d;
    b->weather = w;
    b->weather_turns = w ? (w >= 7 ? 255 : 5) : 0;
    b->terrain = t;
    b->terrain_turns = t ? 5 : 0;
    b->rng = (u64)s << 16;
    b->n[0] = n0;
    b->n[1] = n1;
    while (fscanf(f, "%15s", tag) == 1 && strcmp(tag, "end")) {
        unsigned v[48];
        int i, n = !strcmp(tag, "mon") ? 41 : !strcmp(tag, "dmg") ? 4 : -1;
        if (n < 0) {
            fprintf(stderr, "bench: unknown line %s\n", tag);
            exit(2);
        }
        for (i = 0; i < n; i++)
            if (fscanf(f, "%u", &v[i]) != 1)
                exit(3);
        if (n == 41) {
            int cl = v[0] & 1, k = v[1] % 6;
            Mon *m = &b->party[cl][k];
            Volatile *vo = &b->v[cl];
            m->id = v[2], m->species = v[3], m->level = v[4], m->hp = v[5], m->maxhp = v[6];
            for (i = 0; i < 5; i++)
                m->stat[i] = v[7 + i];
            m->types[0] = v[12], m->types[1] = v[13];
            m->ability = v[15], m->item = v[16];
            for (i = 0; i < 4; i++)
                m->moves[i] = v[17 + i], m->pp[i] = v[21 + i];
            m->status = v[25], m->toxic = v[26];
            if (m->status == ST_SLP)
                m->sleep = 2;
            m->set = k;
            if (!k) {
                vo->types[0] = v[12], vo->types[1] = v[13], vo->types[2] = v[14];
                vo->ability = v[15];
                for (i = 0; i < 7; i++)
                    vo->stage[i] = (int)v[27 + i] - 6;
                vo->trapped = v[35];
                *items |= v[34] != 0;           /* an unselectable move the simulator would not know */
            }
        }
    }
    return 1;
}

int cmd_bench(int argc, char **argv)
{
    FILE *f = argc > 1 ? fopen(argv[argc - 1], "r") : 0;
    Battle *b = malloc(sizeof *b);
    Policy adv = policy_advanced();
    char id[80];
    int unsupported, i;
    if (!f) {
        fprintf(stderr, "usage: sim bench CASES\n");
        return 2;
    }
    while (read_case(f, b, id, &unsupported)) {
        long ov = sim_ai_ov11();
        Action a;
        const u8 *dbg;
        b->winner = -1;
        adv.battle_start(b, 0);
        a = adv.choose(b, 1, 0);
        (void)a;
        dbg = host_debug(0);
        printf("{\"id\": \"%s\", \"ret\": 1, \"unsupported\": %d, \"ov11\": %ld, \"call\": [\"%c\", %d, %d, %d], \"debug\": \"",
               id, unsupported, sim_ai_ov11() - ov, sim_ai_call[0], sim_ai_call[1], sim_ai_call[2], sim_ai_call[3]);
        for (i = 0; i < 256; i++)
            printf("%02x", dbg[i]);
        printf("\"}\n");
    }
    fclose(f);
    free(b);
    return 0;
}
