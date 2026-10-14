/* The greedy bot, for sanity games: always its strongest damaging move (expected damage of a max roll, times
   accuracy and the average hit count), never a switch; after a faint, the bench member with the strongest such move
   against the foe on the field. */
#include <stdlib.h>
#include <string.h>
#include "sim.h"
#include "policy.h"

static int expected(const Battle *b, const Mon *a, const Volatile *va, int a_active, int s, int move)
{
    const MoveRec *m = &sim_moves[move];
    const Mon *d = &b->party[s ^ 1][0];
    DamageQ q;
    int v, acc = m->acc >= 101 ? 100 : m->acc, hits10;
    if (!move || m->cls == CLS_STATUS)
        return 0;
    memset(&q, 0, sizeof q);
    q.a = a, q.d = d, q.va = va, q.vd = &b->v[s ^ 1];
    q.a_active = a_active, q.d_active = 1;
    q.weather = sim_weather(b), q.terrain = b->terrain;
    q.roll = 100;
    v = sim_damage(&q, move);
    if (!q.type_eff)
        return 0;
    hits10 = m->hits_max <= 1 ? 10 : m->hits_min == m->hits_max ? 10 * m->hits_max : m->hits_min == 2 && m->hits_max == 5 ? 31 :
             5 * (m->hits_min + m->hits_max);
    return v * acc / 100 * hits10 / 10;
}

static Action greedy_choose(Battle *b, int s, void *ctx)
{
    Action a = { ACT_MOVE, 4 };
    int k, best = -1;
    for (k = 0; k < 4; k++)
        if (sim_legal_move(b, s, k)) {
            int v = expected(b, &b->party[s][0], &b->v[s], 1, s, b->party[s][0].moves[k]);
            if (v > best)
                best = v, a.idx = k;
        }
    return a;
}

static int greedy_replace(Battle *b, int s, void *ctx)
{
    int i, k, best = -1, pick = 0;
    for (i = 1; i < b->n[s]; i++) {
        const Mon *m = &b->party[s][i];
        Volatile v;
        if (!sim_alive(m))
            continue;
        memset(&v, 0, sizeof v);
        v.types[0] = m->types[0], v.types[1] = m->types[1], v.types[2] = T_NONE;
        v.ability = m->ability;
        for (k = 0; k < 4; k++) {
            int x = expected(b, m, &v, 0, s, m->moves[k]);
            if (x > best)
                best = x, pick = i;
        }
    }
    return pick;
}

const Policy policy_greedy = { "greedy", greedy_choose, greedy_replace, 0, 0 };

/* The random player: uxcheck's human path as tools/aifuzz.py plays it (FIGHT, then a uniformly random move button; a
   refused move is touched again, so the pick is uniform over the usable moves), never a switch by choice, and after
   a faint the first able member in the party's order (uxcheck's replacement walk). SIM_RANDOM_SWITCH=0,1,2 switches
   by choice at those choices (counted from 0), to that first able member, as uxcheck's `switch`. Its own generator,
   seeded from the battle's seed and never drawn from the battle's. */
static u64 random_state;
static unsigned random_calls, random_switch;    /* choices made this battle; bit k: switch at choice k */

static unsigned random_next(void)
{
    random_state = random_state * 6364136223846793005ULL + 1442695040888963407ULL;
    return (unsigned)(random_state >> 33);
}

static void random_start(Battle *b, void *ctx)
{
    const char *e = getenv("SIM_RANDOM_SWITCH");
    random_state = b->rng ^ 0xA5A5F00DULL;
    random_next();
    random_calls = 0, random_switch = 0;
    for (; e && *e; e++)
        if (*e >= '0' && *e <= '9') {
            random_switch |= 1u << atoi(e);
            while (e[1] >= '0' && e[1] <= '9')
                e++;
        }
}

static int random_replace(Battle *b, int s, void *ctx);

static Action random_choose(Battle *b, int s, void *ctx)
{
    Action a = { ACT_MOVE, 4 };
    int k, legal[4], n = 0, sw;
    if (random_calls < 32 && (random_switch >> random_calls++ & 1) && sim_can_switch(b, s) && (sw = random_replace(b, s, ctx)))
        return (Action){ ACT_SWITCH, (u8)sw };
    for (k = 0; k < 4; k++)
        if (sim_legal_move(b, s, k))
            legal[n++] = k;
    if (n)
        a.idx = legal[random_next() % (unsigned)n];
    return a;
}

static int random_replace(Battle *b, int s, void *ctx)
{
    int i;
    for (i = 1; i < b->n[s]; i++)
        if (sim_alive(&b->party[s][i]))
            return i;
    return 0;
}

const Policy policy_random = { "random", random_choose, random_replace, random_start, 0, 0 };
