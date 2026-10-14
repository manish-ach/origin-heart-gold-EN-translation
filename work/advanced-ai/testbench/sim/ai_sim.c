/* The advanced AI's unit for the simulator: tools/hostai/ai_unit.c (advai.c and replace.c in one unit, as the DS
   build compiles them), plus the reset of the slot overlay's bss, which the DS reloads every selection phase while
   the ITCM memory (mem, memo, habit, the Read records) lasts the whole battle. */
#include "../hostai/ai_unit.c"

void sim_ai_new_phase(void)
{
    ai_memset(live, 0, sizeof live);
    ai_memset(ai_debug, 0, sizeof ai_debug);
    ai_memset(g_alt, 0, sizeof g_alt);
    g_nalt = 0;
    g_ko1 = g_ko3 = g_dealt = g_sure = g_fo = g_fell = 0;
}

/* every global the AI keeps between decisions, for sim cf's snapshots (cf.c): the ITCM memory and the slot's bss */
#define AI_STATE(X) X(live) X(ai_debug) X(mem) X(memo) X(habit) X(rctx) X(g_alt) X(g_nalt) X(g_tr_left) \
    X(r_unsure) X(g_tp) X(g_ko1) X(g_ko3) X(g_dealt) X(g_sure) X(g_fo) X(g_fell)
#define AI_SIZE(v) + sizeof(v)
#define AI_SAVE(v) __builtin_memcpy(p, &v, sizeof v), p += sizeof v;
#define AI_LOAD(v) __builtin_memcpy(&v, p, sizeof v), p += sizeof v;
unsigned long sim_ai_globals_size(void) { return 0 AI_STATE(AI_SIZE); }
void sim_ai_globals_save(unsigned char *p) { AI_STATE(AI_SAVE) }
void sim_ai_globals_load(const unsigned char *p) { AI_STATE(AI_LOAD) }

/* the tuning table's copy for one side (tune.h; v[0] the trainer side's, engine side 1), for sim cf luck's per-side
   constants: a head-to-head game of two tunings in one binary */
int sim_ai_tune_n(void) { return TUNE_N; }
void sim_ai_tune_get(int tside, u16 *v) { __builtin_memcpy(v, g_tune.v[tside], sizeof g_tune.v[tside]); }
void sim_ai_tune_set(int tside, const u16 *v) { __builtin_memcpy(g_tune.v[tside], v, sizeof g_tune.v[tside]); }

/* side's strength record s (advai.c Read: the evidence that its foe plays well, 0-1000; engine side 1 the trainer's),
   -1 when the AI has not written it: the drama observer's strong and weak kinds */
int sim_ai_read_s(int side)
{
    extern unsigned char *sim_shared_arena;
    const Read *r = (const Read *)READS_AT + ((side & 1) ^ 1);
    return sim_shared_arena && r->magic == READ_MAGIC ? r->s : -1;
}
