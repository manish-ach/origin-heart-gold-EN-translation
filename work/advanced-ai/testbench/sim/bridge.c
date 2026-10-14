/* The advanced AI as a simulator policy: before each decision the battle is written into the DS address space the
   host build reads (tools/hostai/host_engine.h: AT() on an arena at HOST_BASE + DS address), in the layout
   tools/ai/engine.h maps; the AI is polled as the battle client polls it, and the action setter it calls is the
   decision. The engine entry points it calls are answered from the simulator: the parties, the move data, the
   selectable and trapped checks, and the damage simulation (damage.c with q.sim: the maximum roll, 1 against an
   immunity, the defender's ability and item only on the field). Replacements go through ai_replace (replace.c) with
   the self-play flag set, so it serves both sides as `aivsai --self` does. A fallback to overlay 11, which the host
   does not have, is answered by the greedy bot and counted. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#include "../hostai/host_engine.h"
#define SIM_NO_ENUMS
#include "sim.h"
#include "policy.h"

#define LO 0x01FF8000u
#define HI 0x02400000u
#define MAIN_OBJ 0x02100000u
#define SETUP_OBJ 0x02101000u
#define CLIENT_OBJ 0x02102000u      /* + 0x100 per client: +2 its number, +0x1C its party (ai_replace) */
#define FIELD_OBJ 0x02103000u
#define POKECON1 0x02104000u
#define POKECON0 0x02104100u
#define FIELD0_OBJ 0x02105000u
#define PARTY_OBJ 0x02106000u       /* + 0x200 per copy + 0x40 per client: count, member[6] */
#define BPP_OBJ 0x02110000u         /* + 0x400 per (copy, client, slot) */
#define BPP_SIZE 0x400u
#define ST_OBJ 0x02120000u          /* the AI state per client: +4 the deciding Pokemon */
#define PARAM_OBJ 0x02121000u
#define OUT_OBJ 0x02122000u         /* the chooser's candidate list */
#define OBJ_END 0x02130000u
#define HEAP_LO 0x02300000u
#define HEAP_HI 0x023F0000u
#define CHOOSER 0x02203974u

extern const unsigned char host_chart[324];
int adv_entry(void *param, void *st, int arg);
int ai_replace(void *client, u8 *out, int n, void *opp, int x);
void sim_ai_new_phase(void);
void host_ai_reset(void);

static u8 *g_arena;
static Battle *g_b;
static int g_pre;              /* before the battle (the lead): no Pokemon on the field yet */
static u32 g_heap;
static Action g_act;
static int g_wrote;
int sim_ai_call[4];            /* the setter the last decision called: 'm' move, 's' switch, 'i' item, 'n' none, and its arguments */
static long g_fallbacks, g_decisions, g_replacements;

static void w8(u32 a, u32 v) { AT(u8, a) = (u8)v; }
static void w16(u32 a, u32 v) { AT(u16, a) = (u16)v; }
static void w32(u32 a, u32 v) { AT(u32, a) = v; }
static u32 ds(const void *p) { return (u32)(host_u64)p; }
static void *hp(u32 a) { return a ? (void *)(HOST_BASE + a) : 0; }
static u32 bpp_addr(int copy, int client, int slot) { return BPP_OBJ + BPP_SIZE * (u32)(copy * 12 + client * 6 + slot); }
/* the battle Pokemon of party member idx: like the engine's, each Pokemon keeps its own address whatever its place in
   the party list (by pokeID), so the AI sees a switch as another Pokemon at another address (its strength() read) */
static u32 bpp_of(int copy, int client, int idx) { return bpp_addr(copy, client, g_b->party[client][idx].id - (client ? 13 : 1)); }
static u32 party_addr(int copy, int client) { return PARTY_OBJ + 0x200u * (u32)copy + 0x40u * (u32)client; }

/* a dual binary (Makefile.dual) links a second AI build with its own copy of this file; both share one arena */
#ifdef BRIDGE_B
extern u8 *sim_shared_arena;
#else
u8 *sim_shared_arena;
#endif

static void map_arena(void)
{
    mach_vm_address_t a = HOST_BASE + LO;
    if (g_arena)
        return;
    if (sim_shared_arena) {
        g_arena = sim_shared_arena;
        return;
    }
    if (mach_vm_allocate(mach_task_self(), &a, HI - LO, VM_FLAGS_FIXED) != KERN_SUCCESS) {
        fprintf(stderr, "sim: cannot map the AI's arena at 0x%llx\n", HOST_BASE + LO);
        exit(2);
    }
    g_arena = sim_shared_arena = (u8 *)a;
    memcpy(g_arena + (TYPE_CHART - HOST_BASE - LO), host_chart, 324);
}

/* the (side, party index) a battle Pokemon address stands for; -1 if none */
static int locate(u32 b, int *side, int *idx)
{
    u32 k;
    int i;
    if (b < BPP_OBJ || b >= BPP_OBJ + 24 * BPP_SIZE || (b - BPP_OBJ) % BPP_SIZE)
        return -1;
    k = (b - BPP_OBJ) / BPP_SIZE % 12;
    *side = k / 6;
    for (i = 0; i < g_b->n[*side]; i++)
        if (g_b->party[*side][i].id - (*side ? 13 : 1) == (int)(k % 6)) {
            *idx = i;
            return 0;
        }
    return -1;
}

static const Mon *mon_at(u32 b)
{
    int s, i;
    return locate(b, &s, &i) ? 0 : &g_b->party[s][i];
}

static void cond(u32 b, int i, u32 kind, u32 len, u32 param, int count)
{
    w32(b + 0x3C + 8 * i, kind | len << 3 | param << 9);
    w8(b + 0x1C0 + i, count);
}

static void write_bpp(int copy, int side, int idx)
{
    const Mon *m = &g_b->party[side][idx];
    const Volatile *v = idx || g_pre ? 0 : &g_b->v[side];
    u32 b = bpp_of(copy, side, idx);
    int i, n = 0;
    w16(b + 0x00, m->species);
    w8(b + 0x14, m->id);
    w16(b + 0x16, v ? v->ability : m->ability);
    w16(b + 0x1C, m->maxhp);
    w16(b + 0x1E, m->hp);
    w16(b + 0x20, m->item);
    w8(b + 0x24, m->level);
    for (i = 0; i < 5; i++)
        w16(b + 0x22C + 2 * i, m->stat[i]);
    for (i = 0; i < 3; i++)
        w8(b + 0x236 + i, v ? v->types[i] : i < 2 ? m->types[i] : T_NONE);
    for (i = 0; i < 7; i++)
        w8(b + 0x240 + i, 6 + (v ? v->stage[i] : 0));
    for (i = 0; i < 4; i++) {
        w16(b + 0x25A + 0x12 * i, m->moves[i]);
        w8(b + 0x25C + 0x12 * i, m->pp[i]);
        w8(b + 0x25F + 0x12 * i, (m->used >> i) & 1);
        n += m->moves[i] != 0;
    }
    w8(b + 0x29E, n);
    if (m->status == S_PSN) {
        cond(b, 5, 1, m->toxic ? 15 : 0, 0, 0);
        w8(b + 0x1C5, m->tox_n);
    }
    if (m->status == S_SLP)
    {   /* the count only in copy 0; Early Bird counts 2 per attempt on the DS, so its length is doubled to match */
        int k = (v ? v->ability : m->ability) == 48 ? 2 : 1;      /* Early Bird */
        cond(b, S_SLP, 2, k * (m->sleep + m->slept) + 1, 0, copy ? 0 : k * m->slept);
    }
    if (!v)
        return;
    w16(b + 0x2A4, v->turns_out);
    w16(b + 0x2BA, (v->acted ? 1 : 0) | (v->recharge ? 2 : 0) | v->semi);
    w8(b + 0x2DD, v->protects);
    w16(b + 0x2B2, v->last_move);
    w16(b + 0x2B0, v->last_move);       /* the move before, which the Protect handler reads: equal to +0x2B2 in every T4c turn */
    w16(b + 0x2A8, v->worked);
    if (!copy)
        w16(b + 0x3E6, v->sub);
    if (v->confused)
        cond(b, C_CONFUSION, 2, v->confused, 0, 0);
    if (v->seeded)
        cond(b, C_LEECH_SEED, 1, 0, 0, 0);
    if (v->taunt)
        cond(b, C_TAUNT, 2, 3, 0, 3 - v->taunt);
    if (v->yawn)
        cond(b, C_YAWN, 2, 2, 0, 2 - v->yawn);
    if (v->encore)
        cond(b, C_ENCORE, 2, 3, m->moves[v->encore_slot], 3 - v->encore);
    if (v->charging)
        cond(b, C_CHARGE, 2, 2, m->moves[v->charging - 1], 1);
    if (v->aqua)
        cond(b, C_AQUA_RING, 1, 0, 0, 0);
    if (v->ingrain)
        cond(b, C_INGRAIN, 1, 0, 0, 0);
    if (v->nightmare)
        cond(b, C_NIGHTMARE, 1, 0, 0, 0);
    if (v->perish)
        cond(b, C_PERISH, 2, 4, 0, copy ? 0 : 4 - v->perish);
}

static void side_eff(int side, int eff, int layers, int left)
{
    u32 a = SIDE_EFF + SIDE_EFF_STRIDE * (u32)side + 12 * (u32)eff;
    w16(a + 10, layers);
    w32(a + 4, left ? 2u | (u32)left << 3 : 0);
    w16(a + 8, 0);
}

/* the battle as the engine keeps it, for the AI's reads */
static void project(Battle *b)
{
    int copy, cl, i;
    g_b = b;
    memset(g_arena + (MAIN_OBJ - LO), 0, OBJ_END - MAIN_OBJ);
    memset(g_arena + (SIDE_EFF - LO), 0, 2 * SIDE_EFF_STRIDE);
    g_heap = HEAP_LO;
    w32(MAIN_PTR, MAIN_OBJ);
    w32(MAIN_OBJ + MAIN_SETUP, SETUP_OBJ);
    w32(MAIN_OBJ + 0x24Cu, (u32)(b->rng >> 16));
    w32(MAIN_OBJ + MAIN_SLOT, 10);
    for (cl = 0; cl < 4; cl++)
        w32(MAIN_OBJ + MAIN_CLIENTS + 4 * cl, CLIENT_OBJ + 0x100u * (u32)cl);
    w32(MAIN_OBJ + MAIN_FIELD, FIELD_OBJ);
    w8(FIELD_OBJ, b->weather);
    w8(FIELD_OBJ + 1, b->weather ? b->weather_turns : 0);
    if (b->terrain) {
        w8(FIELD0_OBJ + 0x89 + FE_TERRAIN, 1);
        w8(FIELD0_OBJ + 6, b->terrain);
        w32(FIELD0_OBJ + 0x14 + 8 * FE_TERRAIN, 2u | (u32)b->terrain_turns << 3);
    }
    if (b->trick_room) {
        w8(FIELD0_OBJ + 0x89 + FE_TRICK_ROOM, 1);
        w32(FIELD0_OBJ + 0x14 + 8 * FE_TRICK_ROOM, 2u | (u32)b->trick_room << 3);
    }
    w8(SETUP_OBJ, 1);
    for (cl = 0; cl < 2; cl++) {
        const Side *sd = &b->side[cl];
        w8(CLIENT_OBJ + 0x100u * (u32)cl + 2, cl);
        w32(CLIENT_OBJ + 0x100u * (u32)cl + 0x1C, party_addr(1, cl));
        side_eff(cl, SE_REFLECT, sd->reflect || sd->veil, sd->reflect ? sd->reflect : sd->veil);
        side_eff(cl, SE_LIGHT_SCREEN, sd->screen || sd->veil, sd->screen ? sd->screen : sd->veil);
        side_eff(cl, SE_TAILWIND, sd->tailwind > 0, sd->tailwind);
        /* Safeguard is side effect 2 (engine.h SE_SAFEGUARD since rc28, measured); a number, as a dual binary's older
           second AI has no name for it */
        side_eff(cl, 2, sd->safeguard > 0, sd->safeguard);
        side_eff(cl, SE_SPIKES, sd->spikes, 0);
        side_eff(cl, SE_TOXIC_SPIKES, sd->tspikes, 0);
        side_eff(cl, SE_STEALTH_ROCK, sd->rocks, 0);
        for (copy = 0; copy < 2; copy++) {
            u32 p = party_addr(copy, cl);
            w32(p, b->n[cl]);
            for (i = 0; i < b->n[cl]; i++) {
                write_bpp(copy, cl, i);
                w32(p + 4 + 4 * i, bpp_of(copy, cl, i));
            }
        }
    }
    w32(SELFPLAY_FLAG, SELFPLAY_MAGIC);
}

/* ---------------------------------------------------------------- the engine entry points */

static void *e_pokecon(int w) { return hp(w ? POKECON1 : POKECON0); }
static void *e_pokecon0(void) { return hp(FIELD0_OBJ); }

static void *e_party(void *pc, int client)
{
    if (client < 0 || client > 1 || !g_b->n[client])
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

static int e_client_of(int id) { return id >= 13 && id <= 18 ? 1 : id >= 7 && id <= 12 ? 2 : id >= 19 ? 3 : 0; }
static int e_actives(int client) { return client > 1 ? 0 : 1; }

static int e_pos_of(int id)
{
    int c = e_client_of(id);
    if (c > 1 || g_pre)
        return 5;
    return g_b->party[c][0].id == id ? c : 5;
}

static int e_pos_index(int pos) { return pos >> 1; }

static int e_pokesick(void *b)
{
    const Mon *m = mon_at(ds(b));
    return m && m->hp ? m->status : 0;
}

static int e_fightable(void *b)
{
    const Mon *m = mon_at(ds(b));
    return m && m->hp > 0;
}

extern const int host_nmoves;
extern const unsigned char host_moves[][40];
extern const unsigned char host_waza_param[][3];
enum { P_ZERO, P_U8, P_S8, P_U16, P_LO4, P_HI4, P_BIT };
static int e_waza(int move, int param)
{
    const u8 *r, *p;
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
    int s, i, k;
    if (locate(ds(b), &s, &i) || i)
        return 0;
    for (k = 0; k < 4; k++)
        if (g_b->party[s][0].moves[k] == move)
            return !sim_legal_move(g_b, s, k);
    return 0;
}

static int e_trapped(void *cw, void *b, u8 *o1, u16 *o2)
{
    int s, i;
    if (locate(ds(b), &s, &i) || i)
        return 0;
    return sim_trapped(g_b, s);
}

static int find_id(int id, int *side, int *idx)
{
    int s = id >= 13, i;
    for (i = 0; i < g_b->n[s]; i++)
        if (g_b->party[s][i].id == id) {
            *side = s;
            *idx = i;
            return 1;
        }
    return 0;
}

static int e_sim_damage(int a, int d, int move, int one, int zero)
{
    int sa, ia, sd, id, v;
    DamageQ q;
    AT(u32, MAIN_OBJ + 0x24Cu) = RNG_AFTER_MAX;
    if (!find_id(a, &sa, &ia) || !find_id(d, &sd, &id) || move <= 0 || move >= host_nmoves)
        return 0;
    memset(&q, 0, sizeof q);
    q.a = &g_b->party[sa][ia];
    q.d = &g_b->party[sd][id];
    q.va = ia || g_pre ? 0 : &g_b->v[sa];
    q.vd = id || g_pre ? 0 : &g_b->v[sd];
    q.a_active = !ia && !g_pre;
    q.d_active = !id && !g_pre;
    q.weather = sim_weather(g_b);
    q.terrain = g_b->terrain;
    {
        const Side *sdd = &g_b->side[sd];
        int cls = sim_moves[move].cls;
        q.screen = sdd->veil || (cls == 1 && sdd->reflect) || (cls == 2 && sdd->screen);
    }
    q.roll = 100;
    q.sim = 1;
    v = sim_damage(&q, move);
    if (q.fixed)            /* no roll: the RNG stays where the AI put it, and it scales the number as unsure */
        AT(u32, MAIN_OBJ + 0x24Cu) = RNG_PRE_MAX;
    return v > 0xFFFF ? 0xFFFF : v;
}

static void e_set_none(void *p) { g_act.kind = ACT_NONE, g_wrote = 1, sim_ai_call[0] = 'n'; }
static void e_set_fight(void *p, int move, int pos, int zero, int id)
{
    int s, i, k;
    g_act.kind = ACT_MOVE;
    g_act.idx = 4;
    sim_ai_call[0] = 'm', sim_ai_call[1] = move, sim_ai_call[2] = pos, sim_ai_call[3] = id;
    if (find_id(id, &s, &i))
        for (k = 0; k < 4; k++)
            if (g_b->party[s][0].moves[k] == move)
                g_act.idx = k;
    g_wrote = 1;
}
static void e_set_item(void *p, int item, int id, int zero, int id2)
{
    g_act.kind = ACT_NONE, g_wrote = 1;
    sim_ai_call[0] = 'i', sim_ai_call[1] = item, sim_ai_call[2] = id, sim_ai_call[3] = id2;
}
static void e_set_change(void *p, int posidx, int partyidx)
{
    g_act.kind = ACT_SWITCH;
    g_act.idx = partyidx;
    g_wrote = 1;
    sim_ai_call[0] = 's', sim_ai_call[1] = posidx, sim_ai_call[2] = partyidx, sim_ai_call[3] = 13;
}

/* overlay 11's entry: the host has no original AI, so the greedy bot decides and the fallback is counted */
static int g_side;
const void *host_debug(int side);
static long g_fb_why[16];
static int e_ov11(void *p, void *st, int arg)
{
    const u8 *dbg = host_debug((arg & 1) ^ 1);
    g_fallbacks++;
    g_fb_why[dbg[7] & 15]++;            /* Debug.fallback: FB_* */
    g_act = policy_greedy.choose(g_b, g_side, 0);
    g_wrote = 1;
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

/* the engine's own replacement order (0x02203974): candidates by their best move's power x effectiveness on the foe */
static int e_chooser(void *client, u8 *out, int n, void *opp, int x)
{
    int s = AT(u8, ds(client) + 2), i, j, c = 0, score[6];
    const Mon *f = mon_at(ds(opp));
    for (i = 1; i < g_b->n[s] && c < n; i++) {
        const Mon *m = &g_b->party[s][i];
        int k, best = 0;
        if (!sim_alive(m))
            continue;
        for (k = 0; f && k < 4; k++) {
            const MoveRec *r = &sim_moves[m->moves[k]];
            u8 ft[3] = { f->types[0], f->types[1], T_NONE };
            int v = m->moves[k] && r->cls ? r->power * sim_type_eff(r->type, ft, m->moves[k]) : 0;
            best = v > best ? v : best;
        }
        out[c] = i;
        score[c++] = best;
    }
    for (i = 1; i < c; i++)
        for (j = i; j > 0 && score[j] > score[j - 1]; j--) {
            int t = score[j];
            u8 o = out[j];
            score[j] = score[j - 1], score[j - 1] = t;
            out[j] = out[j - 1], out[j - 1] = o;
        }
    return c ? out[0] : 0;
}

static void e_unknown(void)
{
    fprintf(stderr, "sim: the AI called an engine function the simulator does not stand in for\n");
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
    case CHOOSER: return (host_fp)e_chooser;
    }
    return e_unknown;
}

/* ---------------------------------------------------------------- the policy */

/* the lead the AI picks for side s before the battle (tools/ai/lead.c ai_lead_pick); an AI build without lead.c keeps the
   party's order (this weak stand-in) */
__attribute__((weak)) int ai_lead_pick(int cl) { return 0; }
static int adv_lead(Battle *b, int s, void *ctx)
{
    int k;
    map_arena();
    g_pre = 1;
    project(b);
    k = ai_lead_pick(s);
    g_pre = 0;
    return k;
}

#ifndef BRIDGE_B
static void steer_game_start(void);
#endif
static void adv_start(Battle *b, void *ctx)
{
    map_arena();
    memset(g_arena, 0, HI - LO);            /* a new battle: no Read or Replaced records, no ITCM memory */
    memcpy(g_arena + (TYPE_CHART - HOST_BASE - LO), host_chart, 324);
    host_ai_reset();
#ifndef BRIDGE_B
    steer_game_start();
#endif
}

long sim_ai_ov11(void) { return g_fallbacks; }

/* foresight (tools/ai/advai.c fs): every pair of moves played for one turn on a copy of the battle, its RNG included,
   before the AI decides; the AI keeps what the DS predictor could know (fs_settle) and reads the cells. A dual
   binary's second AI has its own fs and fs_level (Makefile.dual renames them) and fills its own cells */
typedef struct {
    u8 mine, foe, stopped, flinched, missed, crit, flinch_foe, f_stopped, f_missed, f_crit;
    s16 dmg, f_dmg;
} FsCell;
struct FsState {
    u32 magic, word;
    s32 me_hp, opp_hp;
    u16 me_species, opp_species;
    u8 on, trusted;
    s8 rep, pad;
    u8 first[4][4];
    FsCell cell[4][4];
    u8 ofirst[4][4];                    /* the real order per pair, for advai.c's FO_ORD oracle (rc33 F3 step 0) */
};
int fs_level;                           /* tentative: advai.c defines them, an AI build without foresight does not */
int rd_t, rd_pct;                       /* tentative: RD's knobs (advai.c rd_gate); 0 uses every read, as rc32 */
struct FsState fs;
extern unsigned char sim_foe_act[2];    /* battle.c read_side: the other side's action, for the reading side's choice */
extern int sim_foe_valid;
static Action g_fix[2];
static int g_fs_turn;           /* the turn the cells were filled for: a forced move asks no policy */
static Action fix_choose(Battle *b, int s, void *ctx) { return g_fix[s]; }
static int fix_replace(Battle *b, int s, void *ctx)
{
    int i;
    for (i = 1; i < b->n[s]; i++)
        if (sim_alive(&b->party[s][i]))
            return i;
    return 0;
}
/* side s's cell from a played turn: a move not reached (its user fell first) is stopped; a side whose status or stages
   changed before its move (a chance effect landed) is not known, as the DS predictor stops there */
/* rc33 F3: a second mover whose status or stages a first status move changed is known, as the DS walk plays it (a
   paralysis adds its 25 roll, a sleep stops it); advai.c's fs_settle drops the moves such a change alters (a burn on a
   physical move, Swagger's raise...) and every first status move outside its classes */
static int fs_known(const FsRec *r, int s)
{
    const FsSide *x = &r->s[s];
    if (!x->chg || x->called != 2 || sim_moves[r->mv[s ^ 1]].cls)
        return !x->chg;
    return x->stg || x->st_at != 0;
}
static void fs_cell_of(FsCell *c, const FsRec *r, int s)
{
    const FsSide *x = &r->s[s], *y = &r->s[s ^ 1];
    c->mine = fs_known(r, s);
    c->stopped = x->stopped || !x->called;
    c->flinched = x->flinched;
    c->missed = x->missed;
    c->crit = x->crit;
    c->flinch_foe = x->flinch_foe;
    c->dmg = x->dmg;
    c->foe = fs_known(r, s ^ 1);
    c->f_stopped = y->stopped || y->flinched || !y->called;
    c->f_missed = y->missed;
    c->f_crit = y->crit;
    c->f_dmg = y->dmg;
}
/* one turn of side s's move i against the other side's move k on a copy of b, its RNG stepped `steps` times first,
   recorded in r; nothing of it reaches the real game (the luck counters muted, the read-choice globals put back) */
static void play_pair(const Battle *b, int s, int i, int k, int steps, FsRec *r)
{
    static const Policy fixp = { "fix", fix_choose, fix_replace, 0, 0, 0 };
    Battle c = *b;
    int side = g_fs_side, foe_valid = sim_foe_valid, j;
    unsigned char foe_act[2] = { sim_foe_act[0], sim_foe_act[1] };
    c.verbose = 0;
    c.oracle = 0;
    for (j = 0; j < steps; j++)
        sim_rand(&c, 0);
    memset(r, 0, sizeof *r);
    g_fix[s].kind = g_fix[s ^ 1].kind = ACT_MOVE;
    g_fix[s].idx = i;
    g_fix[s ^ 1].idx = k;
    g_fs_side = -1;
    sim_luck_mute++;
    g_fsr = r;
    sim_turn(&c, &fixp, &fixp);
    g_fsr = 0;
    sim_luck_mute--;
    g_fs_side = side;
    sim_foe_valid = foe_valid;          /* the played copy's turn told its own choices (battle.c read_side) */
    sim_foe_act[0] = foe_act[0];
    sim_foe_act[1] = foe_act[1];
}

static void fs_fill(Battle *b, int s)
{
    int i, k;
    u32 me = bpp_of(1, s, 0), op = bpp_of(1, s ^ 1, 0);
    memset(fs.cell, 0, sizeof fs.cell);
    fs.trusted = 0;
    g_fs_turn = b->turn;
    fs.me_species = AT(u16, me);
    fs.me_hp = AT(u16, me + 0x1E);
    fs.opp_species = AT(u16, op);
    fs.opp_hp = AT(u16, op + 0x1E);
    for (i = 0; i < 4; i++) {
        if (!sim_legal_move(b, s, i))
            continue;
        for (k = 0; k < 4; k++) {
            FsRec r;
            if (!b->party[s ^ 1][0].moves[k] || !sim_legal_move(b, s ^ 1, k))
                continue;
            play_pair(b, s, i, k, 0, &r);
            fs_cell_of(&fs.cell[i][k], &r, s);
            fs.ofirst[i][k] = r.s[s].called == 1 ? 0 : r.s[s ^ 1].called == 1 ? 1 : 2;
        }
    }
}

#ifndef BRIDGE_B
/* luck steering (rc31 unit L, tools/ai/advai.c steer_*): the AI that chooses last fills one candidate per RNG position
   w_k (the real battle's RNG stepped k times) with the turn its chosen move and the foe's committed move play from
   there; advai.c's shared rules (steer_pick) choose k, and the bridge steps the real battle k times before the turn.
   The knobs (SIM_STEER_K, SIM_STEER_RULES, SIM_STEER_OPT) set advai.c's steer_* variables; a dual binary's second AI
   has none of this */
typedef struct {
    FsCell cell;
    u8 roll, f_roll, landed, f_landed, f_par, f_pre, sig, pad;
} SteerCand;
int steer_k, steer_rules, steer_side = -1, steer_strict, steer_bank, steer_class, steer_cap = 1, steer_vis, steer_kow = 2000;
int steer_slack[5];
u32 host_steer_tag;
static int g_steer_k, g_steer_turn = -1, g_steer_i, g_steer_kf, g_steer_side;
static SteerCand g_steer_c0, g_steer_ck;
/* per game: steered turns, the k summed, player-roll mismatches on steered turns, steered cells that did not come true,
   decisive trusted turns, the nominal KO chance on them summed (per mille), KOs dealt on them, visible steers, booked
   turns, the ledger's bank at the end; per process the same summed and a k histogram */
enum { SG_STEERS, SG_KSUM, SG_MISMATCH, SG_WRONG, SG_DECISIVE, SG_NOMINAL, SG_KO, SG_VISIBLE, SG_BOOKED, SG_N };
static long g_sg[SG_N], g_sg_all[SG_N], g_khist[9];

int host_steer_fill(int side, int i, int kf, SteerCand *t, int n)
{
    int k;
    for (k = 0; k < n; k++) {
        FsRec r;
        const FsSide *x = &r.s[side], *y = &r.s[side ^ 1];
        play_pair(g_b, side, i, kf, k, &r);
        memset(&t[k], 0, sizeof t[k]);
        fs_cell_of(&t[k].cell, &r, side);
        t[k].roll = x->roll1 ? x->roll1 - 1 : 255;
        t[k].f_roll = y->roll1 ? y->roll1 - 1 : 255;
        t[k].landed = x->landed;
        t[k].f_landed = y->landed;
        t[k].f_par = y->par && y->stopped;
        t[k].f_pre = y->flinched || !y->called;
        t[k].sig = !r.oth[side ^ 1];    /* no player roll outside its move's own (end of turn, Focus Band, contact) */
    }
    return n;
}

void host_steer_apply(int side, int i, int kf, const SteerCand *t, int k)
{
    g_steer_k = k;
    g_steer_turn = g_b->turn;
    g_steer_i = i;
    g_steer_kf = kf;
    g_steer_side = side;
    g_steer_c0 = t[0];
    g_steer_ck = t[k];
}

/* what advai.c's host half tells after each booked turn: decisive, the nominal KO chance (per mille), KO dealt at the k
   played, visible */
void host_steer_note(int decisive, int nominal, int ko, int visible)
{
    g_sg[SG_BOOKED]++;
    if (decisive) {
        g_sg[SG_DECISIVE]++;
        g_sg[SG_NOMINAL] += nominal;
        g_sg[SG_KO] += ko;
    }
    g_sg[SG_VISIBLE] += visible;
}

/* the real turn of a steered decision against the candidates: the player's signature must be k = 0's whenever its move
   is played in both, and my part of the steered cell must come true */
static void steer_check(const FsRec *r, int s, Action mine, Action foe)
{
    FsCell real;
    const FsSide *y = &r->s[s ^ 1], *x = &r->s[s];
    int pre = y->flinched || !y->called, roll = y->roll1 ? y->roll1 - 1 : 255, myroll = x->roll1 ? x->roll1 - 1 : 255;
    if (g_steer_turn < 0 || g_steer_turn != g_b->turn || s != g_steer_side || mine.kind != ACT_MOVE || foe.kind != ACT_MOVE ||
        mine.idx != g_steer_i || foe.idx != g_steer_kf)
        return;
    g_steer_turn = -1;
    fs_cell_of(&real, r, s);
    if (!pre && !g_steer_c0.f_pre &&
        ((y->par && y->stopped) != g_steer_c0.f_par || real.f_missed != g_steer_c0.cell.f_missed ||
         real.f_crit != g_steer_c0.cell.f_crit || roll != g_steer_c0.f_roll || y->landed != g_steer_c0.f_landed ||
         real.f_dmg != g_steer_c0.cell.f_dmg))
        g_sg[SG_MISMATCH]++;
    if (real.stopped != g_steer_ck.cell.stopped || real.missed != g_steer_ck.cell.missed ||
        real.crit != g_steer_ck.cell.crit || real.dmg != g_steer_ck.cell.dmg || myroll != g_steer_ck.roll)
        g_sg[SG_WRONG]++;
}

/* the real battle starts the steered turn from w_k */
static void steer_step(Battle *b)
{
    int j;
    if (!g_steer_k || g_steer_turn != b->turn)
        return;
    for (j = 0; j < g_steer_k; j++)
        sim_rand(b, 0);
    sim_steered_turn = b->turn;
    g_sg[SG_STEERS]++;
    g_sg[SG_KSUM] += g_steer_k;
    g_khist[g_steer_k < 2 ? 0 : g_steer_k < 4 ? 1 : g_steer_k < 8 ? 2 : g_steer_k < 16 ? 3 : g_steer_k < 32 ? 4 :
            g_steer_k < 64 ? 5 : g_steer_k < 128 ? 6 : g_steer_k < 256 ? 7 : 8]++;
    g_steer_k = 0;
}

static void steer_game_start(void)
{
    int j;
    host_steer_tag++;
    for (j = 0; j < SG_N; j++)
        g_sg_all[j] += g_sg[j], g_sg[j] = 0;
    g_steer_turn = -1;
    g_steer_k = 0;
}

/* this game's steering counts, for cf rate's per-game luck line */
void sim_steer_emit(FILE *f)
{
    int j;
    for (j = 0; j < SG_N; j++)
        fprintf(f, " %ld", g_sg[j]);
}

static void steer_knobs(void)
{
    const char *e = getenv("SIM_STEER_K"), *r = getenv("SIM_STEER_RULES"), *o = getenv("SIM_STEER_OPT"),
               *rs = getenv("SIM_READ_SIDE");
    steer_k = e ? atoi(e) : 0;
    if (steer_k > 256)
        steer_k = 256;
    steer_side = rs && (*rs == '0' || *rs == '1') ? *rs - '0' : -1;
    steer_rules = 0;
    for (; r && *r; r++)
        if (*r >= 'a' && *r <= 'd')
            steer_rules |= 1 << (*r - 'a');
    while (o && *o) {
        char name[16];
        int v = 0, n = 0;
        if (sscanf(o, "%15[a-z]=%d%n", name, &v, &n) < 2 || !n) {
            fprintf(stderr, "sim: SIM_STEER_OPT: cannot read '%s'\n", o);
            exit(2);
        }
        if (!strcmp(name, "strict")) steer_strict = v;
        else if (!strcmp(name, "bank")) steer_bank = v;
        else if (!strcmp(name, "class")) steer_class = v;
        else if (!strcmp(name, "cap")) steer_cap = v;
        else if (!strcmp(name, "vis")) steer_vis = v;
        else if (!strcmp(name, "kow")) steer_kow = v;
        else if (!strcmp(name, "sacc")) steer_slack[0] = v;
        else if (!strcmp(name, "scrit")) steer_slack[1] = v;
        else if (!strcmp(name, "sdmg")) steer_slack[2] = v;
        else if (!strcmp(name, "sch")) steer_slack[3] = v;
        else if (!strcmp(name, "spar")) steer_slack[4] = v;
        else {
            fprintf(stderr, "sim: SIM_STEER_OPT: no knob '%s'\n", name);
            exit(2);
        }
        o += n;
        while (*o == ',' || *o == ' ')
            o++;
    }
}

static void steer_report(void)
{
    int j;
    if (!steer_k)
        return;
    for (j = 0; j < SG_N; j++)
        g_sg_all[j] += g_sg[j], g_sg[j] = 0;
    fprintf(stderr, "  steer K %d rules %d: %ld steered turns (k summed %ld), %ld player-roll mismatches, %ld steered cells wrong; "
            "%ld booked, %ld decisive (nominal KO %.1f, KO %ld), %ld visible; k histogram <2 <4 <8 <16 <32 <64 <128 <256 256:",
            steer_k, steer_rules, g_sg_all[SG_STEERS], g_sg_all[SG_KSUM], g_sg_all[SG_MISMATCH], g_sg_all[SG_WRONG],
            g_sg_all[SG_BOOKED], g_sg_all[SG_DECISIVE], g_sg_all[SG_NOMINAL] / 1000.0, g_sg_all[SG_KO], g_sg_all[SG_VISIBLE]);
    for (j = 0; j < 9; j++)
        fprintf(stderr, " %ld", g_khist[j]);
    fprintf(stderr, "\n");
}
#endif

#ifndef BRIDGE_B
/* sim cf: the AI's last decision trusted its foresight cells (a committed move it read, this turn) */
int sim_fs_trusted(void) { return fs_level && fs.trusted && g_fs_turn == g_b->turn; }

void fs_compare(const FsRec *r, int s, Action mine, Action foe)
{
    FsCell real, *c;
    steer_check(r, s, mine, foe);
    if (mine.kind != ACT_MOVE || foe.kind != ACT_MOVE || mine.idx > 3 || foe.idx > 3)
        return;
    c = &fs.cell[mine.idx][foe.idx];
    if (!fs.trusted || g_fs_turn != g_b->turn || !(c->mine || c->foe))
        return;
    fs_cell_of(&real, r, s);
    g_fs_check[0]++;
    if (c->mine) {
        g_fs_check[1]++;
        g_fs_check[2] += real.stopped == c->stopped && real.missed == c->missed && real.crit == c->crit && real.dmg == c->dmg;
    }
    if (c->foe) {
        g_fs_check[3]++;
        g_fs_check[4] += real.f_stopped == c->f_stopped && real.f_missed == c->f_missed && real.f_dmg == c->f_dmg;
    }
    if (getenv("FS_DEBUG") && c->mine && !(real.stopped == c->stopped && real.missed == c->missed && real.crit == c->crit && real.dmg == c->dmg))
        fprintf(stderr, "fs mismatch: side %d move %d (%s) vs foe move %d (%s): predicted dmg %d crit %d miss %d stop %d, real dmg %d crit %d miss %d stop %d\n",
                s, mine.idx, sim_move_name[g_b->party[s][0].moves[mine.idx]], foe.idx, sim_move_name[g_b->party[s ^ 1][0].moves[foe.idx]],
                c->dmg, c->crit, c->missed, c->stopped, real.dmg, real.crit, real.missed, real.stopped);
}
#endif

static Action adv_choose(Battle *b, int s, void *ctx)
{
    int polls = 0, ret;
    sim_ai_call[0] = '-';
    u32 st = ST_OBJ + 0x40u * (u32)s;
    project(b);
    sim_ai_new_phase();
    g_side = s;
    g_wrote = 0;
    g_act.kind = ACT_MOVE;
    g_act.idx = 4;
    w32(st + 4, bpp_of(1, s, 0));
    if (fs_level)
        fs_fill(b, s);
    do
        ret = adv_entry(hp(PARAM_OBJ), hp(st), s);
    while (!ret && ++polls < 64);
    g_decisions++;
    if (!g_wrote)
        g_fallbacks++, g_act = policy_greedy.choose(b, s, 0);
#ifndef BRIDGE_B
    steer_step(b);
#endif
    return g_act;
}

static int adv_replace(Battle *b, int s, void *ctx)
{
    u8 *out = hp(OUT_OBJ);
    int n = 0, i;
    project(b);
    for (i = 1; i < b->n[s]; i++)
        n += sim_alive(&b->party[s][i]);
    if (!n)
        return 0;
    g_replacements++;
    ai_replace(hp(CLIENT_OBJ + 0x100u * (u32)s), out, n, hp(bpp_of(1, s ^ 1, 0)), 0);
    return out[0];
}

#ifndef BRIDGE_B
/* FS_COUNT=1: the foresight check's counts at exit (decisions; real turns with a known cell; my part known, right;
   the foe's known, right), one line per process, for the coverage of a foresight class */
static void fs_count_print(void)
{
    fprintf(stderr, "fscount %ld %ld %ld %ld %ld %ld\n", g_decisions, g_fs_check[0], g_fs_check[1], g_fs_check[2],
            g_fs_check[3], g_fs_check[4]);
}
#endif

Policy policy_advanced(void)
{
    Policy p = { "adv", adv_choose, adv_replace, adv_start, 0, adv_lead };
#ifndef BRIDGE_B
    static int once;
    if (!once++ && getenv("FS_COUNT"))
        atexit(fs_count_print);
#endif
    const char *e = getenv("SIM_FS"), *side = getenv("SIM_FS_SIDE");
    fs_level = e ? atoi(e) : 0;
    if (fs_level)
        g_fs_side = side ? atoi(side) : 1;
#ifndef BRIDGE_B
    steer_knobs();
    e = getenv("SIM_RD_T");
    rd_t = e ? atoi(e) : 700;
    e = getenv("SIM_RD_P");
    rd_pct = e ? atoi(e) : 300;
#else
    e = getenv("SIM_RD_T_B");      /* advb's RD knobs (rd_t is rd_t_b here), else advb takes adv's */
    if (!e)
        e = getenv("SIM_RD_T");
    rd_t = e ? atoi(e) : 700;
    e = getenv("SIM_RD_P_B");
    if (!e)
        e = getenv("SIM_RD_P");
    rd_pct = e ? atoi(e) : 300;
#endif
    map_arena();
    return p;
}

/* the AI's whole memory between decisions, for sim cf's snapshots: its globals and the ITCM range of the arena (the Read
   and Replaced records, ai_replace's scratch); the rest of the arena is written again before every decision */
unsigned long sim_ai_globals_size(void);
void sim_ai_globals_save(unsigned char *p);
void sim_ai_globals_load(const unsigned char *p);
#define ITCM_HI 0x02000000u
unsigned long sim_ai_state_size(void) { return sim_ai_globals_size() + (ITCM_HI - LO); }
void sim_ai_state_save(void *dst)
{
    map_arena();
    memcpy(dst, g_arena, ITCM_HI - LO);
    sim_ai_globals_save((unsigned char *)dst + (ITCM_HI - LO));
}
void sim_ai_state_load(const void *src)
{
    map_arena();
    memcpy(g_arena, src, ITCM_HI - LO);
    sim_ai_globals_load((const unsigned char *)src + (ITCM_HI - LO));
}

void sim_ai_counts(long *decisions, long *fallbacks, long *replacements)
{
    int k;
    for (k = 0; k < 16; k++)
        if (g_fb_why[k])
            fprintf(stderr, "  fallback reason %d (FB_* in tools/ai/advai.c): %ld\n", k, g_fb_why[k]);
#ifndef BRIDGE_B
    if (fs_level)
        fprintf(stderr, "  foresight %d: %ld real turns with a known cell; my part known %ld, right %ld; the foe's known %ld, right %ld\n",
                fs_level, g_fs_check[0], g_fs_check[1], g_fs_check[2], g_fs_check[3], g_fs_check[4]);
    steer_report();
#endif
    *decisions = g_decisions;
    *fallbacks = g_fallbacks;
    *replacements = g_replacements;
}
