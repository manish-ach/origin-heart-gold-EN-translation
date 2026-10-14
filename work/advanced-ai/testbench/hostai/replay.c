/* Replay driver: each case of a case file (tools/hostai/replay.py writes them) through the host build of the
   advanced AI, polled as the battle client polls it, one JSON line per case on stdout.

     replay [--reps N] [--no-formula] [--dump DIR] CASES

   Each case runs N times from a fresh battle (the AI's globals cleared), and the line keeps the fastest run's time
   and retired instructions (proc_pid_rusage, this process's counter), with the instructions of each poll. The
   counting build (replay_count, ai_unit.c compiled with -finstrument-functions) adds the calls of host_counted.
   An engine simulation the case does not record is answered by the AI's own formula (host_formula_ai), or by 0 with
   --no-formula, and counted as missing. --dump writes each case's DS address space as built, before the first poll
   (DIR/ID.bin, from 0x01FF8000), for tools/hostai/thumbcount.py. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <libproc.h>
#include <sys/resource.h>
#include "host_engine.h"
#include "host.h"

#define MAX_POLLS 64
#define MAX_COUNTED 16

int host_formula_ai(const HostCase *c, int a, int d, int move);
int (*host_formula)(const HostCase *c, int a, int d, int move) = host_formula_ai;
static unsigned long long g_counts[MAX_COUNTED];

__attribute__((no_instrument_function)) void __cyg_profile_func_enter(void *fn, void *site)
{
    int k;
    for (k = 0; k < host_ncounted; k++)
        if (fn == host_counted[k])
            g_counts[k]++;
}
__attribute__((no_instrument_function)) void __cyg_profile_func_exit(void *fn, void *site) {}

static unsigned long long instructions(void)
{
    struct rusage_info_v4 ri;
    if (proc_pid_rusage(getpid(), RUSAGE_INFO_V4, (rusage_info_t *)&ri))
        return 0;
    return ri.ri_instructions;
}

static unsigned long long now_ns(void) { return clock_gettime_nsec_np(CLOCK_UPTIME_RAW); }

static int read_case(FILE *f, HostCase *c)
{
    char tag[16];
    memset(c, 0, sizeof *c);
    if (fscanf(f, "%15s", tag) != 1)
        return 0;
    if (strcmp(tag, "case")) {
        fprintf(stderr, "case file: expected 'case', got '%s'\n", tag);
        exit(2);
    }
    {
        unsigned d, w, t, s, i0, i1, i2, i3, n0, n1;
        if (fscanf(f, "%79s %u %u %u %u %u %u %u %u %u %u", c->id, &d, &w, &t, &s, &i0, &i1, &i2, &i3, &n0, &n1) != 11)
            exit(3);
        c->doubles = d, c->weather_raw = w, c->terrain = t, c->seed = s;
        c->items[0] = i0, c->items[1] = i1, c->items[2] = i2, c->items[3] = i3;
        c->nparty[0] = n0, c->nparty[1] = n1;
    }
    while (fscanf(f, "%15s", tag) == 1 && strcmp(tag, "end")) {
        unsigned v[48];
        int i, n = !strcmp(tag, "mon") ? 41 : !strcmp(tag, "dmg") ? 4 : -1;
        if (n < 0) {
            fprintf(stderr, "case file: unknown line '%s'\n", tag);
            exit(2);
        }
        for (i = 0; i < n; i++)
            if (fscanf(f, "%u", &v[i]) != 1)
                exit(3);
        if (n == 4) {
            HostDamage *d = &c->dmg[c->ndmg++];
            if (c->ndmg > HOST_MAX_DMG)
                exit(4);
            d->a = v[0], d->d = v[1], d->move = v[2], d->v = v[3];
        } else {
            HostMon *m = &c->mon[v[0] & 1][v[1] % 6];
            m->id = v[2], m->species = v[3], m->level = v[4], m->hp = v[5], m->maxhp = v[6];
            for (i = 0; i < 5; i++)
                m->stats[i] = v[7 + i];
            for (i = 0; i < 3; i++)
                m->types[i] = v[12 + i];
            m->ability = v[15], m->item = v[16];
            for (i = 0; i < 4; i++) {
                m->moves[i] = v[17 + i];
                m->pp[i] = v[21 + i];
            }
            m->status = v[25], m->toxic = v[26];
            for (i = 0; i < 7; i++)
                m->stages[i] = v[27 + i];
            m->unselectable = v[34], m->trapped = v[35];
            /* v[36..40] spare */
        }
    }
    return 1;
}

typedef struct {
    int ret, polls;
    unsigned long long ns, ins, poll_ins[MAX_POLLS];
} Run;

static void run_once(const HostCase *c, Run *r, unsigned long long overhead)
{
    unsigned long long t0, i0, i1;
    host_build(c);
    host_ai_reset();
    r->polls = 0;
    r->ins = 0;
    t0 = now_ns();
    do {
        i0 = instructions();
        r->ret = adv_entry(host_param(), host_st(), 1);
        i1 = instructions();
        r->poll_ins[r->polls] = i1 - i0 > overhead ? i1 - i0 - overhead : 0;
        r->ins += r->poll_ins[r->polls];
        r->polls++;
    } while (!r->ret && r->polls < MAX_POLLS);
    r->ns = now_ns() - t0;
}

int main(int argc, char **argv)
{
    int reps = 1, i, k;
    const char *path = 0, *dump = 0;
    FILE *f;
    HostCase *c = malloc(sizeof *c);
    unsigned long long overhead = ~0ull;
    for (i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--reps") && i + 1 < argc)
            reps = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--no-formula"))
            host_formula = 0;
        else if (!strcmp(argv[i], "--dump") && i + 1 < argc)
            dump = argv[++i];
        else
            path = argv[i];
    }
    if (!path || !(f = fopen(path, "r"))) {
        fprintf(stderr, "usage: replay [--reps N] CASES\n");
        return 1;
    }
    for (i = 0; i < 64; i++) {      /* the counter's own cost, read twice in a row */
        unsigned long long a = instructions(), b = instructions();
        if (b - a < overhead)
            overhead = b - a;
    }
    host_map();
    while (read_case(f, c)) {
        Run best = { 0 }, r;
        const u8 *dbg;
        for (k = 0; k < MAX_COUNTED; k++)
            g_counts[k] = 0;
        if (dump) {
            char name[512];
            FILE *o;
            host_build(c);
            snprintf(name, sizeof name, "%s/%s.bin", dump, c->id);
            if (!(o = fopen(name, "wb")) || fwrite(host_arena(), 1, host_arena_size(), o) != host_arena_size())
                exit(5);
            fclose(o);
        }
        for (i = 0; i < reps; i++) {
            run_once(c, &r, overhead);
            if (!i || r.ns < best.ns)
                best.ns = r.ns;
            if (!i || r.ins < best.ins)
                memcpy(best.poll_ins, r.poll_ins, sizeof r.poll_ins), best.ins = r.ins;
            best.ret = r.ret, best.polls = r.polls;
        }
        dbg = host_debug(0);
        printf("{\"id\": \"%s\", \"ret\": %d, \"polls\": %d, \"ns\": %llu, \"ins\": %llu, \"overhead\": %llu, \"poll_ins\": [",
               c->id, best.ret, best.polls, best.ns, best.ins, overhead);
        for (i = 0; i < best.polls; i++)
            printf("%s%llu", i ? ", " : "", best.poll_ins[i]);
        printf("], \"sims\": %d, \"missing\": %d, \"ov11\": %d, \"call\": [\"%c\", %d, %d, %d], \"counts\": {",
               host_stats.sims, host_stats.missing, host_stats.ov11, host_stats.call[0] ? host_stats.call[0] : '-',
               host_stats.call[1], host_stats.call[2], host_stats.call[3]);
        for (k = 0; k < host_ncounted; k++)
            printf("%s\"%s\": %llu", k ? ", " : "", host_counted_names[k], g_counts[k] / (unsigned long long)reps);
        printf("}, \"stand_in\": [");
        for (i = 0; i < host_stats.missing && i < HOST_MAX_DMG; i++)
            printf("%s[%d, %d, %d, %d]", i ? ", " : "", host_stats.stand_in[i].a, host_stats.stand_in[i].d,
                   host_stats.stand_in[i].move, host_stats.stand_in[i].v);
        printf("], \"debug\": \"");
        for (i = 0; i < 256; i++)
            printf("%02x", dbg[i]);
        printf("\"}\n");
    }
    return 0;
}
