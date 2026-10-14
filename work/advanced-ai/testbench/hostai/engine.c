/* The host's stand-in for the battle engine the advanced AI reads (host_engine.h): the DS address space as an arena,
   a singles or doubles battle built from a HostCase at turn 1, and the engine entry points the AI calls. The engine's
   damage simulation answers from the case's own table (the numbers the DS run recorded). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include "host_engine.h"
#include "host.h"

#define LO 0x01FF8000u          /* ITCM */
#define HI 0x02400000u          /* end of main RAM */

/* where the stand-in keeps its objects (DS addresses, clear of every fixed address the AI reads) */
#define MAIN_OBJ 0x02100000u
#define SETUP_OBJ 0x02101000u
#define CLIENT_OBJ 0x02102000u  /* + 0x100 per client */
#define FIELD_OBJ 0x02103000u
#define POKECON1 0x02104000u
#define POKECON0 0x02104100u
#define FIELD0_OBJ 0x02105000u  /* the engine's other copy of the field (terrain, Trick Room) */
#define PARTY_OBJ 0x02106000u   /* + 0x200 per copy + 0x40 per client: count, member[6] */
#define BPP_OBJ 0x02110000u     /* + 0x400 per (copy, client, slot) */
#define BPP_SIZE 0x400u
#define ST_OBJ 0x02120000u      /* the AI state the client passes (st): +4 the deciding Pokemon */
#define PARAM_OBJ 0x02121000u
#define HEAP_LO 0x02300000u
#define HEAP_HI 0x023F0000u

extern const unsigned char host_chart[324];
static u8 *g_arena;
static const HostCase *g_case;
/* the simulator's read of the other side's committed action (tools/sim/battle.c read_side), which advai.c's host
   foe_choice takes: a replay case has none, so the AI decides blind, as the bench grades it */
unsigned char sim_foe_act[2];
int sim_foe_valid;
/* the simulator's steer half (tools/sim/bridge.c, rc31 unit L): a replay case never steers (steer_k is 0) */
u32 host_steer_tag;
int host_steer_fill(int side, int i, int kf, void *t, int n) { return 0; }
void host_steer_apply(int side, int i, int kf, const void *t, int k) {}
void host_steer_note(int decisive, int nominal, int ko, int visible) {}
/* RD's outcome counter (tools/sim/battle.c): a replay counts nothing */
void sim_rd_note(int u) {}
static u32 g_heap;
HostStats host_stats;

static void w8(u32 a, u32 v) { AT(u8, a) = (u8)v; }
static void w16(u32 a, u32 v) { AT(u16, a) = (u16)v; }
static void w32(u32 a, u32 v) { AT(u32, a) = v; }
static u32 ds(const void *p) { return (u32)(host_u64)p; }
static void *hp(u32 a) { return a ? (void *)(HOST_BASE + a) : 0; }

/* fixed placement fails rather than replacing a mapping already there */
void host_map(void)
{
    mach_vm_address_t a = HOST_BASE + LO;
    kern_return_t k = mach_vm_allocate(mach_task_self(), &a, HI - LO, VM_FLAGS_FIXED);
    if (k != KERN_SUCCESS) {
        fprintf(stderr, "host arena at 0x%llx: mach_vm_allocate %d\n", HOST_BASE + LO, k);
        exit(2);
    }
    g_arena = (u8 *)a;
}

static u32 bpp_addr(int copy, int client, int slot) { return BPP_OBJ + BPP_SIZE * (u32)(copy * 24 + client * 6 + slot); }
static u32 party_addr(int copy, int client) { return PARTY_OBJ + 0x200u * (u32)copy + 0x40u * (u32)client; }

static const HostMon *mon_of(u32 b)
{
    u32 k;
    if (b < BPP_OBJ || b >= BPP_OBJ + 48 * BPP_SIZE)
        return 0;
    k = (b - BPP_OBJ) / BPP_SIZE % 24;
    return &g_case->mon[k / 6][k % 6];
}

static void write_bpp(u32 b, const HostMon *m)
{
    int i, n = 0;
    w16(b + 0x00, m->species);
    w8(b + 0x14, m->id);
    w16(b + 0x16, m->ability);
    w16(b + 0x1C, m->maxhp);
    w16(b + 0x1E, m->hp);
    w16(b + 0x20, m->item);
    w8(b + 0x24, m->level);
    for (i = 0; i < 5; i++)
        w16(b + 0x22C + 2 * i, m->stats[i]);
    for (i = 0; i < 3; i++)
        w8(b + 0x236 + i, m->types[i]);
    for (i = 0; i < 7; i++)
        w8(b + 0x240 + i, m->stages[i]);
    for (i = 0; i < 4; i++) {
        w16(b + 0x25A + 0x12 * i, m->moves[i]);
        w8(b + 0x25C + 0x12 * i, m->pp[i]);
        n += m->moves[i] != 0;
    }
    w8(b + 0x29E, n);
    if (m->status == S_PSN)     /* poison's condition word: a length above bit 2 is bad poison (engine.h) */
        w32(b + 0x3C + 8 * 5, m->toxic ? 1 | (15 << 3) : 1);
    /* sleep's condition word: the length the battle builds from the bench's three turns of party sleep, counted
       twice by Early Bird (ability 48), as sim/bridge.c writes it for a bench case (sim/bench.c: sleep 2, length
       2k + 1). advai.c reads the turns left from it; without it the AI took every sleeper for one waking now */
    if (m->status == S_SLP)
        w32(b + 0x3C + 8 * S_SLP, 2 | (u32)(m->ability == 48 ? 5 : 3) << 3);
}

/* the battle at its first decision: both copies of every Pokemon, the parties, the field, the setup's items */
void host_build(const HostCase *c)
{
    int copy, cl, s, k;
    g_case = c;
    memset(g_arena, 0, HI - LO);
    memcpy(g_arena + (0x0224DA40u - LO), host_chart, 324);
    memset(&host_stats, 0, sizeof host_stats);
    g_heap = HEAP_LO;
    w32(MAIN_PTR, MAIN_OBJ);
    w32(MAIN_OBJ + MAIN_SETUP, SETUP_OBJ);
    w32(MAIN_OBJ + 0x24C, c->seed);
    w32(MAIN_OBJ + MAIN_SLOT, 10);
    for (cl = 0; cl < 4; cl++)
        w32(MAIN_OBJ + MAIN_CLIENTS + 4 * cl, CLIENT_OBJ + 0x100u * (u32)cl);
    w32(MAIN_OBJ + MAIN_FIELD, FIELD_OBJ);
    w8(FIELD_OBJ, c->weather_raw);
    w8(FIELD_OBJ + 1, c->weather_raw ? (c->weather_raw >= WX_STRONG_WINDS ? 255 : 5) : 0);
    if (c->terrain) {
        w8(FIELD0_OBJ + 0x89 + FE_TERRAIN, 1);
        w8(FIELD0_OBJ + 6, c->terrain);
    }
    w8(SETUP_OBJ, c->doubles ? 2 : 1);
    for (k = 0; k < 4; k++)
        w16(SETUP_OBJ + 0x2C + 0x34 * 1 + 2 * k, c->items[k]);
    for (copy = 0; copy < 2; copy++)
        for (cl = 0; cl < 2; cl++) {
            u32 p = party_addr(copy, cl);
            w32(p, c->nparty[cl]);
            for (s = 0; s < c->nparty[cl]; s++) {
                write_bpp(bpp_addr(copy, cl, s), &c->mon[cl][s]);
                w32(p + 4 + 4 * s, bpp_addr(copy, cl, s));
            }
        }
    w32(ST_OBJ + 4, bpp_addr(1, 1, 0));
}

void *host_st(void) { return hp(ST_OBJ); }
const void *host_arena(void) { return g_arena; }
unsigned long host_arena_size(void) { return HI - LO; }
void *host_param(void) { return hp(PARAM_OBJ); }

/* ---------------------------------------------------------------- the engine entry points */

static void *e_pokecon(int w) { return hp(w ? POKECON1 : POKECON0); }
static void *e_pokecon0(void) { return hp(FIELD0_OBJ); }

static void *e_party(void *pc, int client)
{
    if (client < 0 || client > 1 || !g_case->nparty[client])
        return 0;
    return hp(party_addr(ds(pc) == POKECON1, client));
}

static int e_party_count(void *party) { return (int)AT(u32, ds(party)); }

static void *e_party_member(void *party, int i)
{
    if (i < 0 || i >= e_party_count(party))
        return 0;
    return hp(AT(u32, ds(party) + 4 + 4 * i));
}

static const u8 client_base[4] = { 1, 13, 7, 19 };
static int e_client_of(int id)
{
    int c;
    for (c = 0; c < 4; c++)
        if (id >= client_base[c] && id <= client_base[c] + 5)
            return c;
    return 0;
}

static int e_actives(int client) { return client > 1 ? 0 : g_case->doubles ? 2 : 1; }

static int e_pos_of(int id)
{
    int c = e_client_of(id), slot = id - client_base[c];
    if (slot >= e_actives(c))
        return 5;
    return c + 2 * slot;        /* even positions are the player's side */
}

static int e_pos_index(int pos) { return pos >> 1; }

static int e_pokesick(void *b)
{
    const HostMon *m = mon_of(ds(b));
    return m ? m->status : 0;
}

static int e_fightable(void *b)
{
    const HostMon *m = mon_of(ds(b));
    return m && m->hp > 0;
}

extern const int host_nmoves;
extern const unsigned char host_moves[][40];
extern const unsigned char host_waza_param[][3];
enum { P_ZERO, P_U8, P_S8, P_U16, P_LO4, P_HI4, P_BIT };
static int e_waza(int move, int param)
{
    const u8 *r;
    const u8 *p;
    if (move < 0 || move >= host_nmoves || param < 0 || param > 0x52)
        return 0;
    r = host_moves[move];
    p = host_waza_param[param];
    switch (p[0]) {
    case P_U8: return r[p[1]];
    case P_S8: return (s8)r[p[1]];
    case P_U16: return r[p[1]] | r[p[1] + 1] << 8;
    case P_LO4: return r[p[1]] & 15;
    case P_HI4: return r[p[1]] >> 4;
    case P_BIT: return (int)((((u32)r[p[1]] | (u32)r[p[1] + 1] << 8 | (u32)r[p[1] + 2] << 16 | (u32)r[p[1] + 3] << 24) >> p[2]) & 1);
    }
    return 0;
}

/* the move data file (engine.h E_NARC_OPEN, E_NARC_READ, E_NARC_CLOSE) and one param of a record (E_WAZA_PARAM), as
   e_waza reads them */
static char host_narc;
static void *e_narc_open(int narc, int heap) { return &host_narc; }
static void e_narc_close(void *f) {}
static void e_narc_read(void *f, int move, void *rec)
{
    memset(rec, 0, 40);
    if (move >= 0 && move < host_nmoves)
        memcpy(rec, host_moves[move], 40);
}

static int e_waza_param(const void *rec, int param)
{
    const u8 *r = rec;
    const u8 *p;
    if (param < 0 || param > 0x52)
        return 0;
    p = host_waza_param[param];
    switch (p[0]) {
    case P_U8: return r[p[1]];
    case P_S8: return (s8)r[p[1]];
    case P_U16: return r[p[1]] | r[p[1] + 1] << 8;
    case P_LO4: return r[p[1]] & 15;
    case P_HI4: return r[p[1]] >> 4;
    case P_BIT: return (int)((((u32)r[p[1]] | (u32)r[p[1] + 1] << 8 | (u32)r[p[1] + 2] << 16 | (u32)r[p[1] + 3] << 24) >> p[2]) & 1);
    }
    return 0;
}

static int e_unselectable(void *b, int move, void *pc, void *x)
{
    const HostMon *m = mon_of(ds(b));
    int i;
    for (i = 0; m && i < 4; i++)
        if (m->moves[i] == move)
            return (m->unselectable >> i) & 1;
    return 0;
}

static int e_trapped(void *cw, void *b, u8 *o1, u16 *o2)
{
    const HostMon *m = mon_of(ds(b));
    return m ? m->trapped : 0;
}

/* the case's damage table, from the run's own simulations; one it lacks is counted and answered by the stand-in
   formula when the build has one (host_formula), else 0 */
static int e_sim_damage(int a, int d, int move, int one, int zero)
{
    int i;
    host_stats.sims++;
    AT(u32, MAIN_OBJ + 0x24C) = RNG_AFTER_MAX;     /* the roll was the maximum: no unsure scaling */
    for (i = 0; i < g_case->ndmg; i++)
        if (g_case->dmg[i].a == a && g_case->dmg[i].d == d && g_case->dmg[i].move == move)
            return g_case->dmg[i].v;
    i = host_formula ? host_formula(g_case, a, d, move) : 0;
    if (host_stats.missing < HOST_MAX_DMG) {
        HostDamage *s = &host_stats.stand_in[host_stats.missing];
        s->a = a, s->d = d, s->move = move, s->v = i;
    }
    host_stats.missing++;
    return i;
}

static void e_set_none(void *p) { host_stats.call[0] = 'n'; }
static void e_set_fight(void *p, int move, int pos, int zero, int id)
{
    host_stats.call[0] = 'm';
    host_stats.call[1] = move;
    host_stats.call[2] = pos;
    host_stats.call[3] = id;
}
static void e_set_item(void *p, int item, int id, int zero, int id2)
{
    host_stats.call[0] = 'i';
    host_stats.call[1] = item;
    host_stats.call[2] = id;
    host_stats.call[3] = id2;
}
static void e_set_change(void *p, int posidx, int partyidx)
{
    host_stats.call[0] = 's';
    host_stats.call[1] = posidx;
    host_stats.call[2] = partyidx;
    host_stats.call[3] = 13;
}
static int e_ov11(void *p, void *st, int arg)
{
    host_stats.ov11++;
    return 1;
}

static void *e_alloc(u32 heap, u32 size)
{
    u32 a = g_heap;
    if (a + size > HEAP_HI)
        return 0;
    g_heap = (a + size + 31) & ~31u;
    return hp(a);
}
static void e_free(void *p) {}

static void e_unknown(void)
{
    fprintf(stderr, "the AI called an engine function the host does not stand in for\n");
    abort();
}

int ai_serves(int client) { return 1; }

host_fp host_fn(u32 addr)
{
    switch (addr) {
    case 0x02215170: return (host_fp)e_pokecon;
    case 0x02230934: return (host_fp)e_party;
    case 0x02215038: return (host_fp)e_party_count;
    case 0x022151A0: return (host_fp)e_party_member;
    case 0x022157D4: return (host_fp)e_client_of;
    case 0x022287C8: return (host_fp)e_actives;
    case 0x02228740: return (host_fp)e_pos_of;
    case 0x02228838: return (host_fp)e_pos_index;
    case 0x02216C64: return (host_fp)e_pokesick;
    case 0x02216548: return (host_fp)e_fightable;
    case 0x0201A274: return (host_fp)e_waza;
    case 0x02007590: return (host_fp)e_narc_open;
    case 0x02007694: return (host_fp)e_narc_read;
    case 0x02007614: return (host_fp)e_narc_close;
    case 0x0201A2E0: return (host_fp)e_waza_param;
    case 0x022157A0: return (host_fp)e_pokecon0;
    case 0x0222C304: return (host_fp)e_unselectable;
    case 0x0222C958: return (host_fp)e_trapped;
    case 0x02223390: return (host_fp)e_sim_damage;
    case 0x0220091C: return (host_fp)e_set_none;
    case 0x02200960: return (host_fp)e_set_fight;
    case 0x02200A30: return (host_fp)e_set_item;
    case 0x022009AC: return (host_fp)e_set_change;
    case OV11_ENTRY: return (host_fp)e_ov11;
    case 0x0201B2AC: return (host_fp)e_alloc;
    case 0x0201B33C: return (host_fp)e_free;
    }
    return e_unknown;
}
