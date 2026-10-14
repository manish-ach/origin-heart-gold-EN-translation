/* The advanced AI as the DS build compiles it (tools/build.py link_ai: advai.c and replace.c in one unit), plus the
   host's hooks into the unit's statics. host_engine.h is force-included (Makefile). */
/* Mach-O section names need a segment: the DS link sections mean nothing here */
#define section(name) used
/* the AI's own freestanding memcpy/memset keep their code under these names; struct copies use libc's */
#define memcpy ai_memcpy
#define memset ai_memset

#include "advai.c"
#include "replace.c"
#if __has_include("lead.c")     /* the AI builds since rc28 (an older copy, as a dual binary's second AI, has none) */
#include "lead.c"
#endif

/* every global the AI keeps, cleared as a battle's first decision finds them: the slot's bss is loaded fresh each
   selection phase, and the ITCM memory only counts entries a decision in this battle made */
void host_ai_reset(void)
{
    ai_memset(live, 0, sizeof live);
    ai_memset(ai_debug, 0, sizeof ai_debug);
    ai_memset(&mem, 0, sizeof mem);
    ai_memset(memo, 0, sizeof memo);
    ai_memset(habit, 0, sizeof habit);
    ai_memset(&rctx, 0, sizeof rctx);
    ai_memset(g_alt, 0, sizeof g_alt);
    g_tr_left = r_unsure = 0;
    g_ko1 = g_ko3 = g_dealt = g_sure = g_fo = g_fell = 0;
    g_nalt = 0;
    g_tp = 0;
}

const void *host_debug(int side) { return &ai_debug[side]; }

/* the functions whose calls the counting build tallies (-finstrument-functions): statics, so named here */
const void *const host_counted[] = { (const void *)race_core, (const void *)race_run, (const void *)race_ex,
                                     (const void *)mixed, (const void *)mixed1, (const void *)follow_up,
                                     (const void *)formula_damage, (const void *)decide };
const char *const host_counted_names[] = { "race_core", "race_run", "race_ex", "mixed", "mixed1", "follow_up",
                                           "formula_damage", "decide" };
const int host_ncounted = sizeof host_counted / sizeof host_counted[0];

#include "host.h"

/* the stand-in for an engine simulation the case does not record: the AI's own formula (formula_damage, the same
   stand-in sim_fix uses), on both Pokemon as read_mon reads them */
static void *host_find(int id, int *slot)
{
    void *pc = E_POKECON(1);
    int cl, i;
    for (cl = 0; cl < 2; cl++) {
        void *party = E_PARTY(pc, cl);
        for (i = 0; party && i < E_PARTY_COUNT(party); i++)
            if (B_ID(E_PARTY_MEMBER(party, i)) == id) {
                *slot = i;
                return E_PARTY_MEMBER(party, i);
            }
    }
    return 0;
}

int host_formula_ai(const HostCase *hc, int a, int d, int move)
{
    static Mon ma, md;
    MoveInfo mi;
    void *main = AT(vptr, MAIN_PTR), *field = AT(vptr, (u32)main + MAIN_FIELD);
    int sa, sd, raw = AT(u8, field), weather, k;
    void *ba = host_find(a, &sa), *bd = host_find(d, &sd);
    s32 v;
    if (!ba || !bd || !read_mon(&ma, ba, sa) || !read_mon(&md, bd, sd))
        return 0;
    weather = raw <= W_HAIL ? raw : raw == WX_HARSH_SUN ? W_SUN : raw == WX_HEAVY_RAIN ? W_RAIN : W_NONE;
    for (k = 0; k < 4 && ma.mv[k].id != move; k++)
        ;
    if (k < 4)
        mi = ma.mv[k];
    else
        read_move(&mi, move, ma.ability);
    v = formula_damage(&ma, &md, &mi, weather);
    return v < 0 ? 0 : v > 0xFFFF ? 0xFFFF : v;
}
