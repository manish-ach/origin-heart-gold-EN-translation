/* sim play: games between trainer teams, one JSON line per game (tools/sim/logstats.py's schema). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include "sim.h"
#include "policy.h"
#include "origbot.h"

typedef struct {
    int team[2], n[2], slots[2][6];   /* [0] the trainer side (engine side 1), [1] the player side (engine side 0) */
    int mteam[2][6], mslot[2][6];     /* each member's source team and slot (team -1: a mixed team, aivsai --teams mixed) */
    char scenario[16];
    int game;
    int level[2];                     /* per side from a pairs line's `lv T P` (0: --level) */
} Match;

static u64 mix(u64 x)
{
    x += 0x9E3779B97F4A7C15ULL;
    x = (x ^ (x >> 30)) * 0xBF58476D1CE4E5B9ULL;
    x = (x ^ (x >> 27)) * 0x94D049BB133111EBULL;
    return x ^ (x >> 31);
}

static void json_str(const char *s)
{
    putchar('"');
    for (; *s; s++)
        if (*s == '"' || *s == '\\')
            printf("\\%c", *s);
        else
            putchar(*s);
    putchar('"');
}

static void print_team(const Match *mt, int k, int level)
{
    level = mt->level[k] ? mt->level[k] : level;
    const TeamRec *t = mt->team[k] >= 0 ? &sim_teams[mt->team[k]] : 0;
    int i, j;
    printf("{\"name\": ");
    json_str(t ? t->name : "Mixed");
    printf(", \"trainer\": %d, \"slots\": ", t ? t->trainer : -1);
    if (mt->n[k] < (t ? t->n : 6)) {
        printf("[");
        for (i = 0; i < mt->n[k]; i++)
            printf("%s%d", i ? ", " : "", mt->slots[k][i]);
        printf("]");
    } else
        printf("null");
    printf(", \"mons\": [");
    for (i = 0; i < mt->n[k]; i++) {
        const SetRec *s = &sim_teams[mt->mteam[k][i]].mon[mt->mslot[k][i]];
        printf("%s{\"species\": ", i ? ", " : "");
        json_str(sim_species_name[s->species]);
        printf(", \"level\": %d, \"ability\": ", level);
        json_str(sim_ability_name[s->ability]);
        printf(", \"item\": ");
        if (s->item)
            json_str(sim_item_name[s->item]);
        else
            printf("null");
        printf(", \"moves\": [");
        for (j = 0; j < 4 && s->moves[j]; j++) {
            printf("%s", j ? ", " : "");
            json_str(sim_move_name[s->moves[j]]);
        }
        printf("]}");
    }
    printf("]}");
}

static int left(const Battle *b, int s)
{
    int i, n = 0;
    for (i = 0; i < b->n[s]; i++)
        n += sim_alive(&b->party[s][i]);
    return n;
}

/* JSON side k (0 trainer, 1 player) is engine side 1 - k */
static void print_game(const Match *mt, const Battle *b, u64 seed, int level, int max_turns)
{
    const Tally *t = &b->tally;
    int w = b->winner;
    printf("{\"src\": \"sim\", \"run\": \"sim\", \"scenario\": \"%s\", \"game\": %d, \"seed\": %llu, \"sizes\": [%d, %d], \"teams\": [",
           mt->scenario, mt->game, (unsigned long long)seed, mt->n[0], mt->n[1]);
    print_team(mt, 0, level);
    printf(", ");
    print_team(mt, 1, level);
    printf("], \"finished\": %s, \"winner\": %s, \"turns\": %d, \"left\": [%d, %d], \"moves\": [%d, %d], \"switches\": [%d, %d], "
           "\"items\": [0, 0], \"other\": [0, 0], \"faints\": [%d, %d], \"replacements\": [%d, %d], \"first_faint_turn\": ",
           b->turn < max_turns ? "true" : "false", w == 1 ? "0" : w == 0 ? "1" : "null", b->turn, left(b, 1), left(b, 0),
           t->moves[1], t->moves[0], t->switches[1], t->switches[0], t->faints[1], t->faints[0], t->replacements[1],
           t->replacements[0]);
    if (t->first_faint_turn)
        printf("%d}\n", t->first_faint_turn);
    else
        printf("null}\n");
}

static void setup(Battle *b, const Match *mt, int level)
{
    int k, i;
    memset(b, 0, sizeof *b);
    for (k = 0; k < 2; k++) {
        int side = 1 - k, base = side ? 13 : 1;
        b->n[side] = mt->n[k];
        for (i = 0; i < mt->n[k]; i++)
            sim_build_mon(&b->party[side][i], &sim_teams[mt->mteam[k][i]].mon[mt->mslot[k][i]], mt->level[k] ? mt->level[k] : level, base + i,
                          mt->slots[k][i]);
        b->rand_team[side] = sim_teams[mt->mteam[k][0]].pool == POOL_RANDOM;
    }
}

/* the trainer's ace for the drama observer: the member of the highest level in its record (the battle's level is
   the same for all), the last if tied, -1 for a team of fewer than 3, as battleux.c ace_of picks by pokeID (rc39) */
static int ace_of(const Match *mt)
{
    int i, best = 0;
    if (mt->n[0] < 3)
        return -1;
    for (i = 1; i < mt->n[0]; i++)
        if (sim_teams[mt->mteam[0][i]].mon[mt->mslot[0][i]].level >= sim_teams[mt->mteam[0][best]].mon[mt->mslot[0][best]].level)
            best = i;
    return best;
}

/* aivsai.cut_team's 'random' pick needs Python's RNG; here a seeded shuffle stands in (the pairs file gives the
   emulator's own slots) */
static void cut(Match *mt, int k, int size, int pick, u64 key)
{
    int n = sim_teams[mt->team[k]].n, order[6], i, j;
    for (i = 0; i < n; i++)
        order[i] = i;
    if (pick && size < n)
        for (i = n - 1; i > 0; i--) {
            key = mix(key);
            j = (int)(key % (u64)(i + 1));
            int x = order[i];
            order[i] = order[j];
            order[j] = x;
        }
    mt->n[k] = size < n ? size : n;
    for (i = 0; i < mt->n[k]; i++)
        mt->slots[k][i] = order[i];
    for (i = 0; i < mt->n[k]; i++)              /* keep the team's own order */
        for (j = i + 1; j < mt->n[k]; j++)
            if (mt->slots[k][j] < mt->slots[k][i]) {
                int x = mt->slots[k][i];
                mt->slots[k][i] = mt->slots[k][j];
                mt->slots[k][j] = x;
            }
    for (i = 0; i < mt->n[k]; i++)
        mt->mteam[k][i] = mt->team[k], mt->mslot[k][i] = mt->slots[k][i];
}

static int read_pairs(const char *path, Match **out)
{
    FILE *f = fopen(path, "r");
    char line[512];
    int n = 0, cap = 0;
    Match *m = 0;
    if (!f) {
        fprintf(stderr, "pairs: cannot open %s\n", path);
        exit(2);
    }
    /* pair SCENARIO GAME TEAM_T n s s s ... TEAM_P n s s s ... [lv LEVEL_T LEVEL_P]; a mixed team: -1 n (set team slot)*n */
    while (fgets(line, sizeof line, f)) {
        Match mt;
        char *p = line, *e;
        int k, i;
        if (strncmp(line, "pair ", 5))
            continue;
        memset(&mt, 0, sizeof mt);
        p += 5;
        if (sscanf(p, "%15s %d", mt.scenario, &mt.game) != 2)
            continue;
        while (*p == ' ') p++;
        while (*p && *p != ' ') p++;
        strtol(p, &e, 10);
        p = e;
        for (k = 0; k < 2; k++) {
            mt.team[k] = (int)strtol(p, &e, 10), p = e;
            mt.n[k] = (int)strtol(p, &e, 10), p = e;
            for (i = 0; i < mt.n[k] && i < 6; i++) {
                mt.slots[k][i] = (int)strtol(p, &e, 10), p = e;
                mt.mteam[k][i] = mt.team[k], mt.mslot[k][i] = mt.slots[k][i];
                if (mt.team[k] < 0) {
                    mt.mteam[k][i] = (int)strtol(p, &e, 10), p = e;
                    mt.mslot[k][i] = (int)strtol(p, &e, 10), p = e;
                    if (mt.mteam[k][i] < 0 || mt.mteam[k][i] >= sim_nteams || mt.mslot[k][i] >= sim_teams[mt.mteam[k][i]].n)
                        mt.n[k] = -1;
                }
            }
            if (mt.team[k] < -1 || mt.team[k] >= sim_nteams || mt.n[k] < 1 || mt.n[k] > 6) {
                fprintf(stderr, "pairs: bad line %s", line);
                exit(2);
            }
        }
        while (*p == ' ') p++;
        if (!strncmp(p, "lv ", 3) && sscanf(p + 3, "%d %d", &mt.level[0], &mt.level[1]) != 2) {
            fprintf(stderr, "pairs: bad levels %s", line);
            exit(2);
        }
        if (n == cap)
            m = realloc(m, sizeof *m * (cap = cap ? 2 * cap : 256));
        m[n++] = mt;
    }
    fclose(f);
    *out = m;
    return n;
}

static double now(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec + ts.tv_nsec * 1e-9;
}

static Policy pick_policy(const char *name)
{
    if (!strcmp(name, "greedy"))
        return policy_greedy;
    if (!strcmp(name, "adv"))
        return policy_advanced();
    if (!strcmp(name, "orig"))
        return policy_orig;
    if (!strcmp(name, "random"))
        return policy_random;
    fprintf(stderr, "unknown policy %s (adv, orig, greedy, random)\n", name);
    exit(2);
}

int cmd_play(int argc, char **argv)
{
    int games = 100, level = 100, sizes[2] = { 6, 6 }, pick = 0, max_turns = 200, verbose = 0, reps = 1, i, g, k;
    u64 seed = 1;
    const char *pairs = 0, *p0 = "adv", *p1 = "adv";
    Match *list = 0;
    int nlist = 0, pool[256], npool = 0;
    Policy pol[2];
    Battle *b = malloc(sizeof *b);
    double t0, dt;
    long turns = 0;
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--games") && i + 1 < argc) games = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--seed") && i + 1 < argc) seed = strtoull(argv[++i], 0, 10);
        else if (!strcmp(argv[i], "--level") && i + 1 < argc) level = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--sizes") && i + 1 < argc) sscanf(argv[++i], "%d:%d", &sizes[0], &sizes[1]);
        else if (!strcmp(argv[i], "--pick") && i + 1 < argc) pick = !strcmp(argv[++i], "random");
        else if (!strcmp(argv[i], "--pairs") && i + 1 < argc) pairs = argv[++i];
        else if (!strcmp(argv[i], "--reps") && i + 1 < argc) reps = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--p0") && i + 1 < argc) p0 = argv[++i];
        else if (!strcmp(argv[i], "--p1") && i + 1 < argc) p1 = argv[++i];
        else if (!strcmp(argv[i], "--max-turns") && i + 1 < argc) max_turns = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-v")) verbose = 1;
        else {
            fprintf(stderr, "play: unknown option %s\n", argv[i]);
            return 2;
        }
    }
    pol[0] = pick_policy(p0);
    pol[1] = pick_policy(p1);
    if (pairs) {
        Match *base;
        int nb = read_pairs(pairs, &base);
        list = malloc(sizeof *list * (size_t)(nb * reps + 1));
        for (k = 0; k < reps; k++)
            for (i = 0; i < nb; i++)
                list[nlist++] = base[i];
        free(base);
    } else {
        int order[256], left = 0;
        u64 r = mix(seed);
        for (i = 0; i < sim_nteams; i++)
            if (sim_teams[i].pool == POOL_80)
                pool[npool++] = i;
        list = malloc(sizeof *list * (size_t)(games + 2));
        for (g = 0; nlist < games; g++) {
            Match mt;
            int a, c;
            if (left < 2) {
                for (i = 0; i < npool; i++)
                    order[i] = pool[i];
                for (i = npool - 1; i > 0; i--) {
                    int j, x;
                    r = mix(r);
                    j = (int)(r % (u64)(i + 1));
                    x = order[i], order[i] = order[j], order[j] = x;
                }
                left = npool;
            }
            a = order[--left];
            c = order[--left];
            for (k = 0; k < 2 && nlist < games; k++) {
                memset(&mt, 0, sizeof mt);
                snprintf(mt.scenario, sizeof mt.scenario, "s%03d", g + 1);
                mt.game = k;
                mt.team[0] = k ? c : a;
                mt.team[1] = k ? a : c;
                cut(&mt, 0, sizes[0], pick, mix(seed ^ (u64)(g * 2 + (k ? 1 : 0))));
                cut(&mt, 1, sizes[1], pick, mix(seed ^ (u64)(g * 2 + (k ? 0 : 1)) ^ 0x55));
                list[nlist++] = mt;
            }
        }
    }
    if (getenv("SIM_DRAMA_TRACE"))
        drama_obs_open(getenv("SIM_DRAMA_TRACE"));
    t0 = now();
    for (g = 0; g < nlist; g++) {
        u64 gs = mix(seed * 1000003ULL + (u64)g);
        setup(b, &list[g], level);
        sim_leads(b, &pol[0], &pol[1]);
        b->verbose = verbose;
        sim_start(b, gs);
        drama_obs_battle(b, gs, list[g].team[0] >= 0 ? sim_teams[list[g].team[0]].trainer : 0xFFFF,
                         list[g].level[0] ? list[g].level[0] : level,
                         !strcmp(p0, "adv") ? 0 : !strcmp(p0, "orig") ? 1 : !strcmp(p0, "random") ? 3 : 2, getenv("SIM_HARD") && atoi(getenv("SIM_HARD")),
                         ace_of(&list[g]));
        sim_play(b, &pol[0], &pol[1], max_turns);
        drama_obs_end(b, max_turns);
        turns += b->turn;
        print_game(&list[g], b, gs, level, max_turns);
    }
    drama_obs_close();
    dt = now() - t0;
    fprintf(stderr, "%d games, %ld turns in %.2f s: %.1f games/s, %.0f turns/s (p0 %s, p1 %s)\n", nlist, turns, dt,
            nlist / (dt > 0 ? dt : 1e-9), turns / (dt > 0 ? dt : 1e-9), pol[0].name, pol[1].name);
    if (!strcmp(p0, "adv") || !strcmp(p1, "adv")) {
        long dec, fb, rep;
        sim_ai_counts(&dec, &fb, &rep);
        fprintf(stderr, "advanced AI: %ld decisions, %ld fallbacks to the greedy stand-in for overlay 11, %ld replacements\n",
                dec, fb, rep);
    }
    free(b);
    return 0;
}
