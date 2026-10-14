/* The battle: Pokemon built from the ROM's sets, a turn (actions, order, moves, the end of the turn), switching,
   entries, faints and the end of the battle. Moves are in move.c. */
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sim.h"
#include "sim_ids.h"
#include "internal.h"

FsRec *g_fsr;
int sim_steered_turn = -1;
int g_fs_side = -1;
long g_fs_check[5];
void fs_compare(const FsRec *r, int s, Action mine, Action foe);    /* bridge.c: the real turn against the cell */

/* ---------------------------------------------------------------- RNG (xorshift64*: a seed replays a game) */

u32 sim_rand(Battle *b, u32 n)
{
    u64 x = b->rng;
    x ^= x >> 12;
    x ^= x << 25;
    x ^= x >> 27;
    b->rng = x;
    if (g_fsr && g_owner >= 0 && !g_tracked && g_fsr->oth[g_owner] < 255)
        g_fsr->oth[g_owner]++;
    return n ? (u32)(((x * 0x2545F4914F6CDD1DULL) >> 32) % n) : 0;
}

int chance(Battle *b, int pct) { return pct >= 100 || (pct > 0 && (int)sim_rand(b, 100) < pct); }

/* the luck counters (sim.h): per side and class the count, the summed probability (the index mean 7.5 for damage) and
   the summed outcome; each side's longest run of rolls that went its way in this game */
int sim_luck_mute;
int g_owner = -1, g_tracked;
static struct { long n[2][LUCK_N]; double sp[2][LUCK_N], sx[2][LUCK_N]; int cur[2], best[2]; } g_luck;
void luck_roll(int side, int cls, double p, double x, int good)
{
    if (sim_luck_mute || side < 0 || side > 1 || (cls != LUCK_DMG && (p <= 0 || p >= 1)))
        return;
    g_luck.n[side][cls]++;
    g_luck.sp[side][cls] += p;
    g_luck.sx[side][cls] += x;
    g_luck.cur[side] = good ? g_luck.cur[side] + 1 : 0;
    if (g_luck.cur[side] > g_luck.best[side])
        g_luck.best[side] = g_luck.cur[side];
}
void sim_luck_emit(FILE *f)
{
    int s, c;
    for (s = 0; s < 2; s++)
        for (c = 0; c < LUCK_N; c++)
            fprintf(f, " %ld %.4f %.0f", g_luck.n[s][c], g_luck.sp[s][c], g_luck.sx[s][c]);
    fprintf(f, " %d %d", g_luck.best[0], g_luck.best[1]);
}

/* a 1-in-n roll of the side's own (the Protect streak's BattleRandom(3^s) == 0); n = 1 holds with no draw */
int yes_1in(Battle *b, int kind, int side, unsigned n)
{
    int o = g_owner, r;
    if (b->oracle)
        return b->oracle->yes(b->oracle, b, kind, side, 1.0 / n);
    g_owner = side;
    r = n <= 1 || sim_rand(b, n) == 0;
    g_owner = o;
    return r;
}

/* perfect counters (rc33 RD), per side and game, counted as both actions are chosen: CTR_RESIST, a switch into a Pokemon
   that resists or is immune to the other side's chosen attack; CTR_SUPER, an attack super effective on the other
   side's chosen switch-in while another usable attack of the user is neutral on it; CTR_TURNS, the turns counted. RD's
   outcomes (advai.c rd_use, RD_ODDS 1, RD_DRAW 2, RD_BLIND 3) by sim_rd_note */
enum { CTR_RESIST, CTR_SUPER, CTR_TURNS, CTR_ODDS, CTR_DRAW, CTR_BLIND, CTR_N };
static long g_ctr[2][CTR_N];
static int g_ctr_side = -1;
void sim_rd_note(int u)
{
    if (!sim_luck_mute && g_ctr_side >= 0 && u >= 1 && u <= 3)
        g_ctr[g_ctr_side][CTR_ODDS + u - 1]++;
}
void sim_ctr_emit(FILE *f)
{
    int s, k;
    for (s = 0; s < 2; s++)
        for (k = 0; k < CTR_N; k++)
            fprintf(f, " %ld", g_ctr[s][k]);
}
static int ctr_eff(const Battle *b, int s, const Mon *d, int move)
{
    DamageQ q;
    memset(&q, 0, sizeof q);
    q.a = &b->party[s][0];
    q.va = &b->v[s];
    q.d = d;
    q.a_active = q.d_active = 1;
    q.weather = sim_weather(b);
    q.terrain = b->terrain;
    q.roll = 100;
    sim_damage(&q, move);
    return q.type_eff;
}
static int ctr_attack(const Battle *b, int s, const Action *a)
{
    int m = a->kind == ACT_MOVE && a->idx < 4 ? b->party[s][0].moves[a->idx] : 0;
    return m && sim_moves[m].cls ? m : 0;
}
static void count_counters(const Battle *b, const Action act[2])
{
    int s, o, m, k, alt;
    if (sim_luck_mute)
        return;
    for (s = 0; s < 2; s++) {
        o = s ^ 1;
        g_ctr[s][CTR_TURNS]++;
        if (act[s].kind == ACT_SWITCH && (m = ctr_attack(b, o, &act[o])) && ctr_eff(b, o, &b->party[s][act[s].idx], m) < 4)
            g_ctr[s][CTR_RESIST]++;
        if (act[o].kind == ACT_SWITCH && (m = ctr_attack(b, s, &act[s])) &&
            ctr_eff(b, s, &b->party[o][act[o].idx], m) > 4) {
            for (k = alt = 0; k < 4; k++)
                if (k != act[s].idx && sim_legal_move(b, s, k) && b->party[s][0].moves[k] &&
                    sim_moves[b->party[s][0].moves[k]].cls &&
                    ctr_eff(b, s, &b->party[o][act[o].idx], b->party[s][0].moves[k]) == 4)
                    alt = 1;
            g_ctr[s][CTR_SUPER] += alt;
        }
    }
}

/* a chance effect of the moving side's move (status, stat change, flinch) and full paralysis are the steering rolls
   (rc31 L): recorded for the turn's record and counted; any other decision is a draw for its owner */
int yes(Battle *b, int kind, int side, int pct)
{
    int r, owner, cls = kind == K_PARA ? LUCK_PAR : kind == K_SICK || kind == K_FLINCH || kind == K_RANK ? LUCK_CHANCE : -1;
    if (b->oracle)
        return b->oracle->yes(b->oracle, b, kind, side, pct >= 100 ? 1.0 : pct <= 0 ? 0.0 : pct / 100.0);
    owner = cls == LUCK_CHANCE ? (g_owner >= 0 ? g_owner : side ^ 1) : kind == K_CONTACT ? side ^ 1 : side;
    if (cls < 0) {
        int o = g_owner;
        g_owner = owner;
        r = chance(b, pct);
        g_owner = o;
        return r;
    }
    g_tracked++;
    r = chance(b, pct);
    g_tracked--;
    if (cls == LUCK_PAR) {
        if (g_fsr)
            g_fsr->s[owner].par = r;
        luck_roll(owner, cls, 1 - pct / 100.0, !r, !r);
    } else {
        if (g_fsr && r)
            g_fsr->s[owner].landed = 1;
        luck_roll(owner, cls, pct / 100.0, r, r);
    }
    return r;
}

void note(Battle *b, int code, int side, int a, int c)
{
    if (b->oracle)
        b->oracle->note(b->oracle, b, code, side, a, c);
}

#ifndef SIM_DS
void sim_log(const Battle *b, const char *fmt, ...)
{
    va_list ap;
    if (!b->verbose)
        return;
    va_start(ap, fmt);
    vfprintf(stderr, fmt, ap);
    va_end(ap);
    fputc('\n', stderr);
}
#endif

const char *mon_name(const Mon *m) { return sim_species_name[m->species]; }

/* ---------------------------------------------------------------- building */

/* ROM stat order HP Atk Def Spe SpA SpD -> the bpp's Atk Def SpA SpD Spe */
static const int rom_to_slot[6] = { -1, STAT_ATK, STAT_DEF, STAT_SPE, STAT_SPA, STAT_SPD };

/* SIM_HARD=1 (rc31 L): hard mode's boosts on the trainer side (pokeIDs 13-18): IVs 31, and 85 x SIM_HARD_BADGES / 16
   EVs in every stat (default 16 badges) when the record has none; the level stays the global one (at 100 hard mode's
   +15% is capped away) */
static int hard_evs(void)
{
    static int v = -1;
    if (v < 0) {
        const char *e = getenv("SIM_HARD"), *n = getenv("SIM_HARD_BADGES");
        v = e && atoi(e) ? 85 * (n ? atoi(n) : 16) / 16 + 1 : 0;
    }
    return v;
}

void sim_build_mon(Mon *m, const SetRec *s0, int level, int id, int set)
{
    SetRec hs = *s0;
    const SetRec *s = &hs;
    const SpeciesRec *sp = &sim_species[s->species];
    int k, n = s->nature;
    if (hard_evs() && id >= 13) {
        hs.ivs = 31;
        if (!(hs.evs[0] | hs.evs[1] | hs.evs[2] | hs.evs[3] | hs.evs[4] | hs.evs[5]))
            for (k = 0; k < 6; k++)
                hs.evs[k] = hard_evs() - 1;
    }
    memset(m, 0, sizeof *m);
    m->species = s->species;
    m->ability = s->ability;
    m->item = s->item;
    m->level = level;
    m->id = id;
    m->set = set;
    m->types[0] = sp->types[0];
    m->types[1] = sp->types[1];
    for (k = 0; k < 6; k++) {
        int core = (2 * sp->base[k] + s->ivs + s->evs[k] / 4) * level / 100;
        if (!k) {
            m->maxhp = sp->base[0] == 1 ? 1 : core + level + 10;
            continue;
        }
        core += 5;
        if (n / 5 != n % 5 && k - 1 == n / 5)
            core = core * 110 / 100;
        else if (n / 5 != n % 5 && k - 1 == n % 5)
            core = core * 90 / 100;
        m->stat[rom_to_slot[k]] = core;
    }
    m->hp = m->maxhp;
    for (k = 0; k < 4; k++) {
        m->moves[k] = s->moves[k];
        m->pp[k] = s->moves[k] ? sim_moves[s->moves[k]].pp : 0;
    }
}

/* ---------------------------------------------------------------- queries */

int sim_alive(const Mon *m) { return m->hp > 0; }

int has_type_v(const Volatile *v, int t) { return v->types[0] == t || v->types[1] == t || v->types[2] == t; }

int ability_of(const Battle *b, int s) { return b->v[s].ability; }

int item_of(const Battle *b, int s)
{
    const Mon *m = &b->party[s][0];
    int it = m->item;
    if (!it || it >= sim_nitems || !sim_item_handled[it] || it == I_SOULDEW || b->v[s].ability == A_KLUTZ ||
        b->magic_room || b->v[s].embargo)
        return 0;
    return it;
}

int sim_weather(const Battle *b)
{
    int s;
    for (s = 0; s < 2; s++)
        if (sim_alive(&b->party[s][0]) && (b->v[s].ability == A_CLOUDNINE || b->v[s].ability == A_AIRLOCK))
            return W_NONE;
    return b->weather;
}

int is_sun(int w) { return w == W_SUN || w == WX_HARSH_SUN; }
int is_rain(int w) { return w == W_RAIN || w == WX_HEAVY_RAIN; }

int grounded(const Battle *b, int s)
{
    int it = item_of(b, s);
    if (it == I_IRONBALL || b->gravity)
        return 1;
    return !has_type_v(&b->v[s], T_FLYING) && b->v[s].ability != A_LEVITATE && it != I_AIRBALLOON && !b->v[s].magnet &&
           !b->v[s].tele;
}

static int staged_stat(int stat, int stage)
{
    return stage >= 0 ? stat * (2 + stage) / 2 : stat * 2 / (2 - stage);
}

int staged(int stat, int stage) { return staged_stat(stat, stage); }

int sim_eff_speed(const Battle *b, int s)
{
    const Mon *m = &b->party[s][0];
    const Volatile *v = &b->v[s];
    int sp = staged_stat(m->stat[STAT_SPE], v->stage[STAT_SPE]), it = item_of(b, s), ab = v->ability, w = sim_weather(b);
    if (it == I_CHOICESCARF)
        sp = sp * 3 / 2;
    if (it == I_MACHOBRACE || it == I_IRONBALL || (it >= I_POWERBRACER && it <= I_POWERWEIGHT))
        sp /= 2;
    if (it == I_QUICKPOWDER && m->species == S_DITTO)
        sp *= 2;
    if ((ab == A_SWIFTSWIM && is_rain(w)) || (ab == A_CHLOROPHYLL && is_sun(w)) || (ab == A_SANDRUSH && w == W_SAND) ||
        (ab == A_SLUSHRUSH && w == W_SNOW) || (ab == A_UNBURDEN && v->unburden) ||
        (ab == A_SURGESURFER && b->terrain == TERRAIN_ELECTRIC) || (ab == A_DESERTHAWK && w == W_SAND))
        sp *= 2;
    if (ab == A_QUICKFEET && m->status)
        sp = sp * 3 / 2;
    if (b->side[s].tailwind)
        sp *= 2;
    if (m->status == ST_PAR && ab != A_QUICKFEET)   /* halves last; Quick Feet lifts it (rc27 engine fix) */
        sp /= 2;
    return sp;
}

/* the move it must use this turn, or -1: a charge to finish, a lock (Outrage), a recharge (slot 5) */
int forced_slot(const Battle *b, int s)
{
    const Volatile *v = &b->v[s];
    if (v->recharge)
        return 5;
    if (v->charging)
        return v->charging - 1;
    if (v->lock)
        return v->lock_slot;
    return -1;
}

int sim_legal_move(const Battle *b, int s, int slot)
{
    const Mon *m = &b->party[s][0];
    const Volatile *v = &b->v[s];
    int mv = m->moves[slot];
    if (slot < 0 || slot > 3 || !mv || !m->pp[slot])
        return 0;
    if (v->taunt && sim_moves[mv].cls == CLS_STATUS)
        return 0;
    if ((mv == M_BELCH && !m->ate_berry) || (v->torment && mv == v->last_move && mv != M_STRUGGLE) ||
        (v->disabled && mv == v->disabled_move))
        return 0;           /* Belch is not selectable before a Berry is eaten (DS logs) */
    if (b->v[s ^ 1].imprison) {
        const Mon *f = &b->party[s ^ 1][0];
        int k;
        for (k = 0; k < 4; k++)
            if (f->moves[k] == mv)
                return 0;
    }
    if (v->encore && slot != v->encore_slot)
        return 0;
    if (v->choice && slot != v->choice - 1 && m->moves[v->choice - 1] && m->pp[v->choice - 1])
        return 0;
    return 1;
}

int sim_trapped(const Battle *b, int s)
{
    int f = s ^ 1, fab = b->v[f].ability;
    if (item_of(b, s) == I_SHEDSHELL || has_type_v(&b->v[s], T_GHOST))
        return 0;
    if (b->v[s].trapped || b->v[s].bind)
        return 1;
    if (!sim_alive(&b->party[f][0]))
        return 0;
    if (fab == A_SHADOWTAG && b->v[s].ability != A_SHADOWTAG)
        return 1;
    if (fab == A_ARENATRAP && grounded(b, s))
        return 1;
    if (fab == A_MAGNETPULL && has_type_v(&b->v[s], T_STEEL))
        return 1;
    return 0;
}

int bench_count(const Battle *b, int s)
{
    int i, n = 0;
    for (i = 1; i < b->n[s]; i++)
        n += sim_alive(&b->party[s][i]);
    return n;
}

int sim_can_switch(const Battle *b, int s) { return bench_count(b, s) > 0 && !sim_trapped(b, s); }

static int able_count(const Battle *b, int s)
{
    int i, n = 0;
    for (i = 0; i < b->n[s]; i++)
        n += sim_alive(&b->party[s][i]);
    return n;
}

/* ---------------------------------------------------------------- HP and stats */

void heal(Battle *b, int s, int amount)
{
    Mon *m = &b->party[s][0];
    if (!sim_alive(m) || amount <= 0)
        return;
    m->hp = m->hp + amount > m->maxhp ? m->maxhp : m->hp + amount;
}

/* lose HP outside an attack (chip, recoil); returns 1 if it fainted */
int chip(Battle *b, int s, int amount)
{
    Mon *m = &b->party[s][0];
    if (!sim_alive(m))
        return 0;
    if (amount < 1)
        amount = 1;
    m->hp = amount >= m->hp ? 0 : m->hp - amount;
    berry_check(b, s);
    return !m->hp;
}

/* a stat stage change on side s's Pokemon; by_foe: the foe caused it (Clear Body, Defiant); returns the change made */
int boost(Battle *b, int s, int stat, int n, int by_foe)
{
    Volatile *v = &b->v[s];
    int ab = v->ability, old, nw;
    if (!sim_alive(&b->party[s][0]) || !n)
        return 0;
    if (ab == A_CONTRARY)
        n = -n;
    if (ab == A_SIMPLE)
        n *= 2;
    if (n < 0 && by_foe) {
        if (ab == A_CLEARBODY || ab == A_WHITESMOKE || ab == A_FULLMETALBDY || item_of(b, s) == I_CLEARAMULET ||
            b->side[s].safeguard * 0)
            return 0;
        if ((ab == A_HYPERCUTTER || ab == A_MEGACLAWS) && stat == STAT_ATK)
            return 0;
        if (ab == A_KEENEYE && stat == STAT_ACC)
            return 0;
    }
    old = v->stage[stat];
    nw = old + n > 6 ? 6 : old + n < -6 ? -6 : old + n;
    v->stage[stat] = nw;
    if (nw != old)
        note(b, N_STAT, s, stat, nw - old);
    if (nw < old && by_foe) {
        if (ab == A_DEFIANT)
            boost(b, s, STAT_ATK, 2, 0);
        if (ab == A_COMPETITIVE)
            boost(b, s, STAT_SPA, 2, 0);
        white_herb(b, s);
    }
    return nw - old;
}

/* White Herb restores the lowered stats (after any drop: the logs show it after Leaf Storm's own drop too) */
void white_herb(Battle *b, int s)
{
    Volatile *v = &b->v[s];
    int k, any = 0;
    if (item_of(b, s) != I_WHITEHERB || !sim_alive(&b->party[s][0]))
        return;
    for (k = 0; k < 7; k++)
        if (v->stage[k] < 0)
            v->stage[k] = 0, any = 1;
    if (any)
        consume(b, s);
}

void consume(Battle *b, int s)
{
    Mon *m = &b->party[s][0];
    note(b, N_ITEM, s, m->item, 0);
    if (m->item >= I_CHERIBERRY && m->item <= I_ROWAPBERRY)
        m->ate_berry = 1;
    m->lost_item = m->item;
    m->item = 0;
    if (b->v[s].ability == A_UNBURDEN)
        b->v[s].unburden = 1;
}

static int is_berry(int it) { return it >= I_CHERIBERRY && it <= I_ROWAPBERRY; }

/* HP berries and pinch berries after HP falls; Unnerve stops them */
void berry_check(Battle *b, int s)
{
    Mon *m = &b->party[s][0];
    int it = item_of(b, s), q = m->maxhp / 4 ? m->maxhp / 4 : 1;
    if (!sim_alive(m) || !it || !is_berry(it))
        return;
    if (sim_alive(&b->party[s ^ 1][0]) && (b->v[s ^ 1].ability == A_UNNERVE || b->v[s ^ 1].ability == A_ASONE))
        return;
    if (it == I_SITRUSBERRY && m->hp * 2 <= m->maxhp) {
        heal(b, s, m->maxhp / 4);
        consume(b, s);
        sim_log(b, "  %s ate its Sitrus Berry", mon_name(m));
    } else if (it == I_ORANBERRY && m->hp * 2 <= m->maxhp) {
        heal(b, s, 10);
        consume(b, s);
    } else if (m->hp <= q || (b->v[s].ability == A_GLUTTONY && m->hp * 2 <= m->maxhp)) {
        int stat = it == I_LIECHIBERRY ? STAT_ATK : it == I_GANLONBERRY ? STAT_DEF : it == I_SALACBERRY ? STAT_SPE :
                   it == I_PETAYABERRY ? STAT_SPA : it == I_APICOTBERRY ? STAT_SPD : -1;
        if (stat >= 0) {
            boost(b, s, stat, 1, 0);
            consume(b, s);
        } else if (it == I_FIGYBERRY || it == I_WIKIBERRY || it == I_MAGOBERRY || it == I_AGUAVBERRY || it == I_IAPAPABERRY) {
            heal(b, s, m->maxhp / 3);
            consume(b, s);
        }
    }
}

/* a status-curing berry right after the status lands */
void status_berry(Battle *b, int s)
{
    Mon *m = &b->party[s][0];
    int it = item_of(b, s), st = m->status;
    if (!it || !st)
        return;
    if (it == I_LUMBERRY || (it == I_CHESTOBERRY && st == ST_SLP) || (it == I_CHERIBERRY && st == ST_PAR) ||
        (it == I_PECHABERRY && st == ST_PSN) || (it == I_RAWSTBERRY && st == ST_BRN) || (it == I_ASPEARBERRY && st == ST_FRZ)) {
        m->status = 0;
        m->toxic = m->tox_n = 0;
        m->sleep = 0;
        consume(b, s);
        sim_log(b, "  %s's berry cured it", mon_name(m));
    }
    if (it == I_LUMBERRY || it == I_PERSIMBERRY) {
        if (b->v[s].confused && sim_alive(m)) {
            b->v[s].confused = 0;
            if (m->item)
                consume(b, s);
        }
    }
}

/* ---------------------------------------------------------------- faints and the end */

/* a Pokemon on the field that just fell: the tally, Destiny Bond's partner was settled by the caller */
void fainted(Battle *b, int s)
{
    Mon *m = &b->party[s][0];
    if (b->v[s].moved == 2)        /* already counted */
        return;
    b->v[s].moved = 2;
    note(b, N_FAINT, s, m->set, 0);
    OBS(obs_faint(b, s, m->id));
    extreme_weather_leaves(b, s);
    b->last_faint = s;
    b->tally.faints[s]++;
    if (!b->tally.first_faint_turn)
        b->tally.first_faint_turn = b->turn;
    sim_log(b, "  %s (side %d) fainted", mon_name(m), s);
}

int check_end(Battle *b)
{
    int a0 = able_count(b, 0), a1 = able_count(b, 1);
    if (b->winner >= 0)
        return 1;
    if (a0 && a1)
        return 0;
    /* both sides out at once: the side whose Pokemon fell last loses (Flare Blitz's recoil KO lost the game in the logs) */
    b->winner = !a0 && !a1 ? b->last_faint ^ 1 : a0 ? 0 : 1;
    return 1;
}

/* ---------------------------------------------------------------- switching and entries */

void reset_volatile(Battle *b, int s, int keep_pass)
{
    Volatile *v = &b->v[s], old = *v;
    const Mon *m = &b->party[s][0];
    memset(v, 0, sizeof *v);
    if (keep_pass) {                /* Baton Pass */
        memcpy(v->stage, old.stage, sizeof v->stage);
        v->confused = old.confused, v->focus = old.focus, v->sub = old.sub, v->seeded = old.seeded;
        v->aqua = old.aqua, v->ingrain = old.ingrain, v->cursed = old.cursed, v->trapped = old.trapped;
    }
    v->types[0] = m->types[0];
    v->types[1] = m->types[1];
    v->types[2] = T_NONE;
    v->ability = m->ability;
}

static void entry_hazards(Battle *b, int s)
{
    Mon *m = &b->party[s][0];
    Side *sd = &b->side[s];
    int it = item_of(b, s);
    if (!sim_alive(m) || v_magic_guard(b, s) || it == I_HVYDUTYBOOTS)
        return;
    if (sd->rocks) {
        int e = sim_type_eff(T_ROCK, b->v[s].types, 0);
        note(b, N_HAZARD, s, 0, 1);
        chip(b, s, m->maxhp * e / 32);
        sim_log(b, "  Stealth Rock hurt %s", mon_name(m));
    }
    if (sd->spikes && grounded(b, s) && sim_alive(m) && (note(b, N_HAZARD, s, 1, 1), 1))
        chip(b, s, sd->spikes == 1 ? m->maxhp / 8 : sd->spikes == 2 ? m->maxhp / 6 : m->maxhp / 4);
    if (sd->tspikes && grounded(b, s) && sim_alive(m)) {
        if (has_type_v(&b->v[s], T_POISON))
            sd->tspikes = 0;
        else if (!m->status && !has_type_v(&b->v[s], T_STEEL))
            inflict(b, s, ST_PSN, sd->tspikes >= 2, -1);
    }
    if (sd->sticky && grounded(b, s) && sim_alive(m))
        boost(b, s, STAT_SPE, -1, 1);
    if (!sim_alive(m))
        fainted(b, s);
}

void set_weather(Battle *b, int w, int setter_side, int turns)
{
    int it = setter_side >= 0 ? item_of(b, setter_side) : 0;
    if (b->weather == w || (b->weather >= WX_STRONG_WINDS && w < WX_STRONG_WINDS))
        return;
    if (!turns)
        turns = ((w == W_RAIN && it == I_DAMPROCK) || (w == W_SUN && it == I_HEATROCK) || (w == W_SAND && it == I_SMOOTHROCK) ||
                 (w == W_SNOW && it == I_ICYROCK)) ? 8 : 5;
    b->weather = w;
    b->weather_turns = turns;
    note(b, N_WEATHER, -1, w, 0);
    sim_log(b, "  weather %d for %d turns", w, turns);
}

void set_terrain(Battle *b, int t, int setter_side)
{
    if (b->terrain == t)
        return;
    note(b, N_TERRAIN, -1, t, 0);
    b->terrain = t;
    b->terrain_turns = setter_side >= 0 && item_of(b, setter_side) == I_TERRAINEXTDR ? 8 : 5;
}

/* entry abilities of side s's Pokemon */
static void entry_ability(Battle *b, int s)
{
    int f = s ^ 1, ab = b->v[s].ability;
    if (!sim_alive(&b->party[s][0]))
        return;
    switch (ab) {
    case A_INTIMIDATE: case A_BLAZINGAWE:
        if (sim_alive(&b->party[f][0]) && !b->v[f].sub) {
            int fab = b->v[f].ability;
            if (fab == A_INNERFOCUS || fab == A_OBLIVIOUS || fab == A_OWNTEMPO || fab == A_SCRAPPY || fab == A_GUARDDOG)
                break;
            boost(b, f, STAT_ATK, -1, 1);
            if (fab == A_RATTLED)
                boost(b, f, STAT_SPE, 1, 0);
        }
        break;
    case A_DOWNLOAD:
        if (sim_alive(&b->party[f][0])) {
            const Mon *o = &b->party[f][0];
            int d = staged_stat(o->stat[STAT_DEF], b->v[f].stage[STAT_DEF]), sd = staged_stat(o->stat[STAT_SPD], b->v[f].stage[STAT_SPD]);
            boost(b, s, d < sd ? STAT_ATK : STAT_SPA, 1, 0);
        }
        break;
    case A_DRIZZLE: set_weather(b, W_RAIN, s, 0); break;
    case A_DROUGHT: case A_WILDFIRE: case A_ORICHLCMPLSE: set_weather(b, W_SUN, s, 0); break;
    case A_SANDSTREAM: set_weather(b, W_SAND, s, 0); break;
    case A_SNOWWARNING: set_weather(b, W_SNOW, s, 0); break;
    case A_DESOLATELAND: set_weather(b, WX_HARSH_SUN, s, 255); break;
    case A_PRIMRDIALSEA: set_weather(b, WX_HEAVY_RAIN, s, 255); break;
    case A_DELTASTREAM: set_weather(b, WX_STRONG_WINDS, s, 255); break;
    case A_ELECSURGE: case A_THUNDERROAR: case A_HADRONENGINE: set_terrain(b, TERRAIN_ELECTRIC, s); break;
    case A_PSYCHICSURGE: set_terrain(b, TERRAIN_PSYCHIC, s); break;
    case A_MISTYSURGE: set_terrain(b, TERRAIN_MISTY, s); break;
    case A_GRASSYSURGE: set_terrain(b, TERRAIN_GRASSY, s); break;
    case A_AURORASHINE:
        if (!b->side[s].veil)
            b->side[s].veil = 5;
        break;
    case A_DAMP: case A_THERMALEXCHG: case A_WATERBUBBLE: case A_WATERVEIL:
        b->v[s].aqua = 1;           /* a water veil: 1/16 at each turn's end (Damp measured; Water Bubble, Water Veil: logs) */
        break;
    case A_TRACE:
        if (sim_alive(&b->party[f][0]))
            b->v[s].ability = b->v[f].ability;
        break;
    case A_IMPOSTER:
        if (sim_alive(&b->party[f][0]))
            transform(b, s, f);
        break;
    }
}

static void switch_out_in(Battle *b, int s, int i, int pass);
static void entry(Battle *b, int s)
{
    entry_hazards(b, s);
    if (sim_alive(&b->party[s][0]))
        entry_ability(b, s);
}

/* side s sends party member i onto the field (i > 0); the one there leaves */
void switch_in(Battle *b, int s, int i, int pass)
{
    switch_out_in(b, s, i, pass);
    entry(b, s);
}

/* the extreme weathers end when the Pokemon that keeps them leaves the field, unless the other side keeps the same one */
void extreme_weather_leaves(Battle *b, int s)
{
    int ab = b->v[s].ability, w = ab == A_DESOLATELAND ? WX_HARSH_SUN : ab == A_PRIMRDIALSEA ? WX_HEAVY_RAIN :
                                    ab == A_DELTASTREAM ? WX_STRONG_WINDS : 0;
    if (w && b->weather == w && !(sim_alive(&b->party[s ^ 1][0]) && b->v[s ^ 1].ability == ab))
        b->weather = W_NONE, b->weather_turns = 0;
}

static void switch_out_in(Battle *b, int s, int i, int pass)
{
    Mon tmp, *out = &b->party[s][0];
    int ab = b->v[s].ability;
    extreme_weather_leaves(b, s);
    if (b->v[s].transformed) {
        Mon *o = &b->tf_saved[s];
        int k;
        out->species = o->species;
        for (k = 0; k < 5; k++)
            out->stat[k] = o->stat[k];
        for (k = 0; k < 4; k++)
            out->moves[k] = o->moves[k], out->pp[k] = o->pp[k];
    }
    if (b->v[s].stats_saved)
        memcpy(out->stat, b->v[s].saved_stat, sizeof out->stat);
    if (b->v[s].mimic_slot)
        out->moves[b->v[s].mimic_slot - 1] = b->v[s].mimic_move;
    if (sim_alive(out)) {
        if (ab == A_REGENERATOR)
            heal(b, s, out->maxhp / 2);         /* the hack's Regenerator: half (its text; logs) */
        if (out->toxic)
            out->tox_n = 0;
    }
    tmp = b->party[s][0];
    b->party[s][0] = b->party[s][i];
    b->party[s][i] = tmp;
    reset_volatile(b, s, pass);
    b->v[s].entered = b->turn;
    note(b, N_SENDIN, s, b->party[s][0].set, 0);
    OBS(obs_sendin(b, s, b->party[s][0].id));
    sim_log(b, "  side %d sends out %s", s, mon_name(&b->party[s][0]));
}

/* each side whose policy picks its lead (the advanced AI, tools/ai/lead.c) swaps it with party slot 0; both picks see
   the parties as they were filled, as the DS makes them before anything is sent out */
void sim_leads(Battle *b, const Policy *p0, const Policy *p1)
{
    int k[2], s;
    k[0] = p0->lead ? p0->lead(b, 0, p0->ctx) : 0;
    k[1] = p1->lead ? p1->lead(b, 1, p1->ctx) : 0;
    for (s = 0; s < 2; s++)
        if (k[s] > 0 && k[s] < b->n[s]) {
            Mon t = b->party[s][0];
            b->party[s][0] = b->party[s][k[s]];
            b->party[s][k[s]] = t;
        }
}

void sim_start(Battle *b, u64 seed)
{
    int s;
    b->rng = seed ? seed : 0x9E3779B97F4A7C15ULL;
    b->winner = -1;
    b->turn = 0;
    sim_steered_turn = -1;
    memset(&b->tally, 0, sizeof b->tally);
    memset(&g_luck, 0, sizeof g_luck);
    memset(g_ctr, 0, sizeof g_ctr);
    for (s = 0; s < 2; s++)
        reset_volatile(b, s, 0);
    /* entry abilities in Speed order */
    if (sim_eff_speed(b, 1) > sim_eff_speed(b, 0)) {
        entry_ability(b, 1);
        entry_ability(b, 0);
    } else {
        entry_ability(b, 0);
        entry_ability(b, 1);
    }
}

/* the party index side s's policy sends in (0: no one left) */
static int replacement(Battle *b, int s, const Policy *p)
{
    int i;
    if (!bench_count(b, s))
        return 0;
    i = p->replace(b, s, p->ctx);
    if (i < 1 || i >= b->n[s] || !sim_alive(&b->party[s][i]))
        for (i = 1; i < b->n[s] && !sim_alive(&b->party[s][i]); i++)
            ;
    b->tally.replacements[s]++;         /* as the logs print every chooser call: faints, U-turn, Baton Pass */
    return i;
}

/* the replacement for side s's pivoting Pokemon (U-turn, Baton Pass), from its policy */
int replace(Battle *b, int s, const Policy *p, int pivot)
{
    int i = replacement(b, s, p);
    if (i)
        switch_in(b, s, i, pivot == 2);
    return i > 0;
}

/* the turn's end: both sides choose their replacements for the Pokemon that fell, both come out, and then their
   entry hazards and abilities act, the faster one's first (the logs show either side's send-in first) */
void replace_fainted(Battle *b, const Policy *const pol[2])
{
    int s, pick[2] = { 0, 0 }, first = 0, again = 0;
    for (s = 0; s < 2; s++)
        if (b->winner < 0 && !sim_alive(&b->party[s][0]))
            pick[s] = replacement(b, s, pol[s]);
    for (s = 0; s < 2; s++)
        if (pick[s]) {
            switch_out_in(b, s, pick[s], 0);
            b->v[s].turns_out = 1;      /* the engine's counter reads 1 at every first decision, after a faint too (DS traces) */
        }
    if (pick[0] && pick[1]) {
        int s0 = sim_eff_speed(b, 0), s1 = sim_eff_speed(b, 1);
        first = s1 > s0 || (s1 == s0 && sim_rand(b, 2));
    } else
        first = pick[1] != 0;
    for (s = 0; s < 2; s++)
        if (pick[first ^ s])
            entry(b, first ^ s);
    /* one that fell to the hazards on its way in is replaced at once (logs: Shedinja into Stealth Rock, then Forretress) */
    for (s = 0; s < 2; s++)
        again |= pick[s] && !sim_alive(&b->party[s][0]) && bench_count(b, s);
    if (again && !check_end(b))
        replace_fainted(b, pol);
}

/* ---------------------------------------------------------------- the end of the turn */

int v_magic_guard(const Battle *b, int s) { return b->v[s].ability == A_MAGICGUARD; }

static void end_of_turn_side_(Battle *b, int s);
static void end_of_turn_side(Battle *b, int s)
{
    int o = g_owner;
    g_owner = s;
    end_of_turn_side_(b, s);
    g_owner = o;
}
static void end_of_turn_side_(Battle *b, int s)
{
    Mon *m = &b->party[s][0];
    Volatile *v = &b->v[s];
    int w = sim_weather(b), it, ab = v->ability, f = s ^ 1;
    if (!sim_alive(m))
        return;
    /* weather */
    if (w == W_SAND && !has_type_v(v, T_ROCK) && !has_type_v(v, T_GROUND) && !has_type_v(v, T_STEEL) && ab != A_SANDVEIL &&
        ab != A_SANDRUSH && ab != A_SANDFORCE && ab != A_OVERCOAT && ab != A_DESERTHAWK && !v_magic_guard(b, s) &&
        item_of(b, s) != I_SAFETYGOGGLS && !v->semi)
        chip(b, s, m->maxhp / 16);
    if (ab == A_DRYSKIN && is_rain(w))
        heal(b, s, m->maxhp / 8);
    if ((ab == A_DRYSKIN || ab == A_SOLARPOWER) && is_sun(w))
        chip(b, s, m->maxhp / 8);
    if (ab == A_RAINDISH && is_rain(w))
        heal(b, s, m->maxhp / 8);               /* 1/8 here (logs) */
    if (ab == A_HYDRATION && is_rain(w))
        heal(b, s, m->maxhp / 8);               /* the hack's Hydration also heals in rain (its text; logs: 1/8) */
    if (ab == A_ICEBODY && w == W_SNOW)
        heal(b, s, m->maxhp / 8);               /* 1/8 here (logs) */
    if (!sim_alive(m))
        return fainted(b, s);
    /* healing */
    it = item_of(b, s);
    if (it == I_LEFTOVERS)
        heal(b, s, m->maxhp / 16);
    if (it == I_BLACKSLUDGE) {
        if (has_type_v(v, T_POISON))
            heal(b, s, m->maxhp / 16);
        else if (!v_magic_guard(b, s))
            chip(b, s, m->maxhp / 8);
    }
    if (v->aqua)
        heal(b, s, m->maxhp / 16 * (it == I_BIGROOT ? 13 : 10) / 10);
    if (v->ingrain)
        heal(b, s, m->maxhp / 16);
    if (b->terrain == TERRAIN_GRASSY && grounded(b, s))
        heal(b, s, m->maxhp / 16);
    if (m->status && ((ab == A_SHEDSKIN && yes(b, K_SHEDSKIN, s, 30)) || (ab == A_HYDRATION && is_rain(w)))) {
        m->status = 0;
        m->toxic = m->tox_n = 0;
    }
    /* Leech Seed */
    if (v->seeded && !v_magic_guard(b, s) && sim_alive(&b->party[f][0])) {
        int d = m->maxhp / 8 ? m->maxhp / 8 : 1;
        d = d > m->hp ? m->hp : d;
        chip(b, s, d);
        heal(b, f, d);
    }
    if (!sim_alive(m))
        return fainted(b, s);
    /* poison and burn */
    if (m->status == ST_PSN && ab == A_POISONHEAL)
        heal(b, s, m->maxhp / 8);
    else if (m->status == ST_PSN && !v_magic_guard(b, s)) {
        if (m->toxic) {
            chip(b, s, m->maxhp / 16 * (m->tox_n + 1));
            if (m->tox_n < 14)
                m->tox_n++;
        } else
            chip(b, s, m->maxhp / 8);
    }
    if (m->status == ST_BRN && !v_magic_guard(b, s) && ab != A_QUICKFEET)
        chip(b, s, m->maxhp / 16);              /* Quick Feet takes no burn damage here (logs) */
    if (m->status == ST_SLP && sim_alive(&b->party[f][0]) && b->v[f].ability == A_BADDREAMS && !v_magic_guard(b, s))
        chip(b, s, m->maxhp / 8);               /* Bad Dreams (logs) */
    if (v->cursed && !v_magic_guard(b, s))
        chip(b, s, m->maxhp / 4);
    if (v->nightmare && m->status == ST_SLP && !v_magic_guard(b, s))
        chip(b, s, m->maxhp / 4);
    if (v->bind) {
        if (!v_magic_guard(b, s))
            chip(b, s, m->maxhp / (item_of(b, f) == I_BINDINGBAND ? 6 : 8));
        v->bind--;
    }
    if (!sim_alive(m))
        return fainted(b, s);
    /* counted conditions */
    if (v->taunt)
        v->taunt--;
    if (v->encore && !--v->encore)
        v->encore_slot = 0;
    if (v->yawn && !--v->yawn && !m->status)
        inflict(b, s, ST_SLP, 0, -1);
    if (v->perish && !--v->perish) {
        m->hp = 0;
        return fainted(b, s);
    }
    /* abilities and orbs */
    if (ab == A_SPEEDBOOST && v->entered != b->turn)        /* not on the turn it came out (a replacement boosts) */
        boost(b, s, STAT_SPE, 1, 0);
    if (ab == A_MOODY) {
        int up, down;
        if (b->oracle) {
            static const double p5[5] = { .2, .2, .2, .2, .2 }, p4[4] = { .25, .25, .25, .25 };
            up = b->oracle->pick(b->oracle, b, K_MOODY, s, 5, p5);
            down = b->oracle->pick(b->oracle, b, K_MOODY_DOWN, s, 4, p4);
        } else
            up = sim_rand(b, 5), down = sim_rand(b, 4);
        if (down >= up)
            down++;
        boost(b, s, up, 2, 0);
        boost(b, s, down, -1, 0);
    }
    if (it == I_FLAMEORB && !m->status)
        inflict(b, s, ST_BRN, 0, -1);
    if (it == I_TOXICORB && !m->status)
        inflict(b, s, ST_PSN, 1, -1);
    v->protecting = v->flinched = v->endure = 0;
    v->coat = v->powder = v->snatch = 0;
    if (v->tele) v->tele--;
    if (v->magnet) v->magnet--;
    if (v->embargo) v->embargo--;
    if (v->disabled) v->disabled--;
    v->turns_out++;
}

void end_of_turn(Battle *b)
{
    int s, order[2] = { 0, 1 };
    if (sim_eff_speed(b, 1) > sim_eff_speed(b, 0))
        order[0] = 1, order[1] = 0;
    /* weather in its last turn ends before it acts (logs: no sandstorm damage on the turn it subsides) */
    if (b->weather && b->weather_turns != 255 && !--b->weather_turns)
        b->weather = W_NONE;
    for (s = 0; s < 2; s++)
        future_lands(b, order[s]);
    for (s = 0; s < 2; s++) {
        Side *sd = &b->side[s];
        if (sd->wish && !--sd->wish)
            heal(b, s, sd->wish_hp);
    }
    for (s = 0; s < 2; s++)
        end_of_turn_side(b, order[s]);
    if (b->terrain && !--b->terrain_turns)
        b->terrain = TERRAIN_NONE;
    if (b->trick_room)
        b->trick_room--;
    if (b->gravity) b->gravity--;
    if (b->wonder_room) b->wonder_room--;
    if (b->magic_room) b->magic_room--;
    if (b->mud_sport) b->mud_sport--;
    if (b->water_sport) b->water_sport--;
    for (s = 0; s < 2; s++) {
        Side *sd = &b->side[s];
        if (sd->reflect) sd->reflect--;
        if (sd->screen) sd->screen--;
        if (sd->veil) sd->veil--;
        if (sd->tailwind) sd->tailwind--;
        if (sd->safeguard) sd->safeguard--;
    }
}

/* ---------------------------------------------------------------- the turn */

typedef struct {
    int side, kind, slot, prio, speed, tie;
} Turn;

static int action_prio(const Battle *b, int s, int slot)
{
    const Mon *m = &b->party[s][0];
    int mv = slot == 4 ? M_STRUGGLE : slot == 5 ? 0 : m->moves[slot], p, ab = b->v[s].ability;
    if (!mv)
        return 0;
    p = sim_moves[mv].prio;
    if (ab == A_PRANKSTER && sim_moves[mv].cls == CLS_STATUS)
        p++;
    if (ab == A_GALEWINGS && sim_moves[mv].type == T_FLYING)
        p++;                        /* at any HP (measured) */
    if (ab == A_TRIAGE && (sim_moves[mv].heal > 0 || sim_moves[mv].drain > 0))
        p += 3;
    return p;
}

/* positive when x acts before y */
static int before(const Battle *b, const Turn *x, const Turn *y)
{
    if (x->kind != y->kind)
        return x->kind == ACT_SWITCH ? 1 : -1;
    if (x->prio != y->prio)
        return x->prio > y->prio ? 1 : -1;
    if (x->speed != y->speed)
        return (x->speed > y->speed) != (b->trick_room > 0) ? 1 : -1;
    return x->tie > y->tie ? 1 : -1;
}

static Action choose(Battle *b, int s, const Policy *p)
{
    Action a = { ACT_MOVE, 4 };
    int f = forced_slot(b, s), k, any = 0;
    if (f >= 0) {
        a.idx = f;
        return a;
    }
    for (k = 0; k < 4; k++)
        any |= sim_legal_move(b, s, k);
    a = p->choose(b, s, p->ctx);
    if (a.kind == ACT_SWITCH && (a.idx < 1 || a.idx >= b->n[s] || !sim_alive(&b->party[s][a.idx]) || sim_trapped(b, s)))
        a.kind = ACT_MOVE, a.idx = 4;
    if (a.kind == ACT_MOVE && a.idx < 4 && !sim_legal_move(b, s, a.idx))
        a.idx = 4;
    if (a.kind == ACT_MOVE && a.idx == 4 && any)
        for (k = 0; k < 4; k++)
            if (sim_legal_move(b, s, k)) {
                a.idx = k;
                break;
            }
    if (a.kind == ACT_NONE)
        a.kind = ACT_MOVE, a.idx = 4;
    return a;
}

/* read_choice: SIM_READ_SIDE=0|1 makes that side choose second, told the other side's action (sim_foe_act: Action.kind,
   Action.idx), which an AI build that reads it (tools/ai foe_choice) uses; unset: both choose blind, side 0 first */
unsigned char sim_foe_act[2];
int sim_foe_valid;
static int read_side(void)
{
    static int v = -2;
    if (v == -2) {
        const char *e = getenv("SIM_READ_SIDE");
        v = e && (*e == '0' || *e == '1') ? *e - '0' : -1;
    }
    return v;
}

/* a turn in three phases, so sim cf luck can replay the random part (resolve) from the chosen actions */
int sim_turn_choose(Battle *b, const Policy *const pol[2], Action act[2])
{
    int s, keep = g_ctr_side;           /* a turn played inside a choice (the bridge's foresight) keeps the chooser's */
    if (check_end(b))
        return 0;
    b->turn++;
    sim_log(b, "--- turn %d: %s %d/%d vs %s %d/%d", b->turn, mon_name(&b->party[0][0]), b->party[0][0].hp,
            b->party[0][0].maxhp, mon_name(&b->party[1][0]), b->party[1][0].hp, b->party[1][0].maxhp);
    if (read_side() < 0)
        for (s = 0; s < 2; s++) {
            g_ctr_side = s;
            act[s] = choose(b, s, pol[s]);
        }
    else {
        s = read_side() ^ 1;
        g_ctr_side = s;
        act[s] = choose(b, s, pol[s]);
        sim_foe_act[0] = act[s].kind, sim_foe_act[1] = act[s].idx;
        sim_foe_valid = 1;
        g_ctr_side = s ^ 1;
        act[s ^ 1] = choose(b, s ^ 1, pol[s ^ 1]);
        sim_foe_valid = 0;
    }
    g_ctr_side = keep;
    count_counters(b, act);
    return 1;
}

void sim_turn_resolve(Battle *b, const Policy *const pol[2], const Action act[2])
{
    Turn t[2];
    int s, i, first;
    FsRec fsr_real, *fsr_save = g_fsr;
    int fs_on = g_fs_side >= 0 && !g_fsr;
    if (fs_on) {
        memset(&fsr_real, 0, sizeof fsr_real);
        g_fsr = &fsr_real;
    }
    for (s = 0; g_fsr && s < 2; s++) {
        g_fsr->st0[s] = b->party[s][0].status;
        memcpy(g_fsr->stg0[s], b->v[s].stage, sizeof b->v[s].stage);
    }
    for (s = 0; s < 2; s++) {
        int forced = forced_slot(b, s) >= 0;
        t[s].side = s;
        t[s].kind = act[s].kind;
        t[s].slot = act[s].idx;
        t[s].prio = act[s].kind == ACT_MOVE ? action_prio(b, s, act[s].idx) : 0;
        t[s].speed = sim_eff_speed(b, s);
        t[s].tie = sim_rand(b, 1 << 30);
        if (act[s].kind == ACT_MOVE && !forced) {
            int it = item_of(b, s);
            /* Quick Draw 30%: IsOccurPer(30) every turn, the holder first 7 times of 16, each time the roll was below
               30 (DS trace Q_quickdraw, qa/aivsai/rc33_PR.md) */
            if ((it == I_QUICKCLAW && chance(b, 20)) || (b->v[s].ability == A_QUICKDRAW && chance(b, 30)))
                t[s].speed = 0xFFFFF, t[s].prio += 0;   /* first in its bracket */
            else if (it == I_LAGGINGTAIL || it == I_FULLINCENSE)
                t[s].speed = b->trick_room ? 0xFFFFF : -1;
            else if (it == I_CUSTAPBERRY && b->party[s][0].hp * 4 <= b->party[s][0].maxhp) {
                t[s].speed = 0xFFFFF;
                consume(b, s);
            }
        }
        if (act[s].kind == ACT_SWITCH)
            b->tally.switches[s]++;
        else if (!forced)
            b->tally.moves[s]++;
        b->v[s].moved = 0;
        b->v[s].hit_by_move = b->v[s].hit_dmg = 0;
        b->v[s].planned = act[s].kind == ACT_MOVE ? (act[s].idx < 4 ? b->party[s][0].moves[act[s].idx] : act[s].idx == 4 ? M_STRUGGLE : 0) : 0;
    }
    first = before(b, &t[0], &t[1]) > 0 ? 0 : 1;
    OBS(obs_turn(b, act));
    for (i = 0; i < 2; i++) {
        Turn *x = &t[i ? first ^ 1 : first];
        s = x->side;
        if (b->winner >= 0)
            break;
        OBS(obs_begin(b, s));
        if (x->kind == ACT_SWITCH) {
            if (sim_alive(&b->party[s][x->slot]) && x->slot > 0) {
                switch_in(b, s, x->slot, 0);
                b->v[s].moved = 1;
            }
        } else if (sim_alive(&b->party[s][0]) && b->v[s].moved != 2)
            use_move(b, s, x->slot, pol);
        b->v[s].moved = b->v[s].moved == 2 ? 2 : 1;
        check_end(b);
        OBS(obs_end(b));
    }
    if (fs_on) {
        g_fsr = fsr_save;
        fs_compare(&fsr_real, g_fs_side, act[g_fs_side], act[g_fs_side ^ 1]);
    }
    if (b->winner < 0) {
        OBS(obs_begin(b, -1));
        end_of_turn(b);
        check_end(b);
        OBS(obs_end(b));
    }
}

int sim_turn_finish(Battle *b, const Policy *const pol[2])
{
    int s;
    OBS(obs_begin(b, -1));
    replace_fainted(b, pol);
    OBS(obs_end(b));
    for (s = 0; s < 2; s++)
        if (sim_alive(&b->party[s][0]) && b->v[s].moved == 2)
            b->v[s].moved = 0;
    return !check_end(b);
}

int sim_turn(Battle *b, const Policy *p0, const Policy *p1)
{
    const Policy *pol[2] = { p0, p1 };
    Action act[2];
    if (!sim_turn_choose(b, pol, act))
        return 0;
    sim_turn_resolve(b, pol, act);
    return sim_turn_finish(b, pol);
}

int sim_play(Battle *b, const Policy *p0, const Policy *p1, int max_turns)
{
    if (p0->battle_start)
        p0->battle_start(b, p0->ctx);
    if (p1->battle_start && p1 != p0)
        p1->battle_start(b, p1->ctx);
    while (b->winner < 0 && b->turn < max_turns && sim_turn(b, p0, p1))
        ;
    if (b->winner < 0)
        b->winner = 2;
    return b->winner;
}
