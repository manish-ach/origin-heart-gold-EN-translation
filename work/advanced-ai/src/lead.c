/* The trainer's lead (rc28), when the advanced AI serves the trainer (its setting, flags 0x2C2 and 0x2C3:
   tools/asm/aiselect.s ai_serves). The ROM's party order put slot 0 first; instead the trainer leads with the
   Pokemon that wins the one on one against the player's lead most clearly, by the matchup rule of
   qa/aivsai/AI_RESEARCH_NEW.md section 5: for each of its Pokemon, the turns it needs to knock the player's lead out
   and the turns the player's lead needs to knock it out, each by the best expected hit (the move's damage at the
   92.5% roll, accuracy and hit count, no stat stages); score 2 x (their turns - mine), plus 1 when it is faster;
   the best score leads, ties keep the earlier slot. The lead swaps places with slot 0, so the rest of the order
   stays.

   Single battles only: overlay 14's single-battle setup (0x022152F4) has built both copies of the parties
   (E_POKECON(0) and E_POKECON(1), party lists by client) and the server, and calls the server's start at
   0x022153C2; ai_lead takes that call. The damage is the AI's own formula (formula_damage, with move_damage's
   immunities and the defender's modifiers that pair_damage adds off the field), not the engine's simulation: before
   anything is out, the simulation leaves out some of the attacker's modifiers it applies in battle (measured: Life
   Orb, Sheer Force, Magnet), which the simulator's host build could not follow. Doubles and multi battles (the other
   two setups) keep their order, and so does a partner (client 2). build.py links ai_lead first in main RAM
   (link.ld), so the hook's target stays put. */

#define SERVER_START 0x02223A40
#define NO_LEAD 99
/* BattleSetup: client c's trainer header copy at +0x28 + 0x34 c; byte 2 bit 1 (build.KEEP_LEAD_MARK) marks a trainer
   whose battles depend on its first Pokemon (build.KEEP_LEAD_TRAINERS: it walks beside it, a line names it) */
#define KEEP_LEAD(setup, c) (AT(u8, (u32)(setup) + 0x2A + 0x34 * (c)) & 2)

int ai_serves(int client);      /* tools/asm/aiselect.s: 1 if the advanced AI decides for that client's trainer */

/* turns a needs to knock d out at d's HP, NO_LEAD if never: its best expected hit */
static int lead_turns(const Mon *a, const Mon *d)
{
    s32 best = 0, v;
    int k;
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &a->mv[k];
        if (!a->legal[k] || !m->cls)
            continue;
        v = clamp(defender_mods(a, d, m, formula_damage(a, d, m, W_NONE)), 0, 0xFFFF);
        v = expected(a, d, move_damage(a, d, m, v), m, W_NONE);
        if (v > best)
            best = v;
    }
    return best > 0 ? (d->hp + best - 1) / best : NO_LEAD;
}

/* the party index of client cl's Pokemon that leads, from the client copy's party lists (0: the party's own order,
   also when anything is off). An Illusion user keeps its party's order: the setup picked its disguise by the order */
typedef struct { Mon foe, me; MoveCache wz; } LeadWork;
int ai_lead_pick(int cl)
{
    void *pc = E_POKECON(1), *mine, *theirs;
    LeadWork *w;
    s32 v, top = 0;
    int k, n, best = -1;
    if (!OK_PTR(pc) || !OK_PTR(mine = E_PARTY(pc, cl)) || !OK_PTR(theirs = E_PARTY(pc, cl ^ 1)))
        return 0;
    n = E_PARTY_COUNT(mine);
    if (n < 2 || n > 6 || !(w = E_ALLOC(HEAP_BATTLE, sizeof *w)))
        return 0;
    g_wz = &w->wz;
    g_wz->n = 0;
    if (read_mon(&w->foe, E_PARTY_MEMBER(theirs, 0), 0) && w->foe.alive)
        for (k = 0; k < n; k++) {
            if (!read_mon(&w->me, E_PARTY_MEMBER(mine, k), k) || w->me.ability == AB_ILLUSION) {
                best = -1;
                break;
            }
            if (!w->me.alive)
                continue;
            v = 2 * (lead_turns(&w->foe, &w->me) - lead_turns(&w->me, &w->foe)) +
                (w->me.stat[4] > w->foe.stat[4]);
            if (best < 0 || v > top) {
                top = v;
                best = k;
            }
        }
    waza_close();
    g_wz = 0;
    E_FREE(w);
    return best > 0 ? best : 0;
}

/* party member k and member 0 change places in a client's party list in both copies of the parties, p0 and p1 (k
   checked by the caller) */
static void lead_swap(void *p0, void *p1, int k)
{
    void *party = p0;
    int copy;
    for (copy = 0; copy < 2; copy++, party = p1) {
        u32 t = AT(u32, party);
        AT(u32, party) = AT(u32, (u32)party + 4 * k);
        AT(u32, (u32)party + 4 * k) = t;
    }
}

/* the single battle setup's call to the server's start: both sides' picks are made from the parties as built, then
   swapped in, then the server starts. Client 1 when the advanced AI serves its trainer and the AI plays it (the
   client's kind byte, 1 for an AI client); client 0 too in self-play tests (engine.h SELFPLAY), whose two picks are
   then made against each other's party order, as the simulator makes them. The bench and aiprops keep their set
   positions (engine.h NOLEAD). A trainer of build.KEEP_LEAD_TRAINERS keeps its order */
void ai_lead(void *server)
{
    u8 *main = AT(bptr, MAIN_PTR);
    void *c1, *p0, *p1, *setup;
    int k[2] = { 0, 0 }, cl;
    if (OK_PTR(main) && !NOLEAD() && OK_PTR(setup = AT(vptr, (u32)main + MAIN_SETUP))) {
        c1 = AT(vptr, (u32)main + MAIN_CLIENTS + 4);
        for (cl = 0; cl < 2; cl++)
            if ((cl ? OK_PTR(c1) && AT(u8, c1) == 1 : SELFPLAY()) && !KEEP_LEAD(setup, cl) && ai_serves(cl))
                k[cl] = ai_lead_pick(cl);
        for (cl = 0; cl < 2; cl++) {
            p0 = E_PARTY(E_POKECON(0), cl);
            p1 = E_PARTY(E_POKECON(1), cl);
            if (k[cl] && OK_PTR(p0) && OK_PTR(p1) && k[cl] < E_PARTY_COUNT(p0) && k[cl] < E_PARTY_COUNT(p1))
                lead_swap(p0, p1, k[cl]);
        }
    }
    CALL(SERVER_START, void, void *)(server);
}
