/* Which Pokemon the trainer sends in after a faint, when the advanced AI serves that trainer (its setting, flags 0x2C2
   and 0x2C3: tools/asm/aiselect.s ai_serves; otherwise the engine's own pick stands). The battle client
   picks it in overlay 14 (0x02203974: every candidate's best move power x effectiveness, then sorted best
   first into `out`) during turn playback, while overlay 8 holds the battle slot. build.py compiles this file
   in one unit with advai.c and keeps ai_replace and every section it reaches resident (link_ai: ITCM, and main
   RAM for what only ai_replace runs and for what does not fit ITCM); its working state is in ITCM RAM (.itcm_bss)
   and, for select_value, in the battle heap.

   After a faint in singles, against the foe on the field, the three best candidates by the free-entry value below are
   valued again as the selection AI would value their first decision there (select_value): the best of its move values
   against the foe's reply odds, less what the hazards on entry take, and go before the others (three caps the pause
   on the faint message). That value sees the state after the faint, so it cannot be planned at the turn's start.
   Otherwise (doubles, after my U-turn or Volt Switch, no foe on the field) each candidate keeps the value of the
   selection AI's free entry after a faint:
   its first turn against the foe on the field, where each side uses the move likeliest to knock the other out
   (the odds of each roll, hit count and miss), then the race (entries, race), with the candidate's statuses,
   Intimidate, the hazards on its side, Sash, Counter, recoil, priority finishers, and the next entry when it falls.
   So a candidate that moves first and knocks the foe out surely goes first (a slower one takes the foe's hit before
   its KO), and one the foe knocks out before it acts goes last. Losing the only answer to a foe off the field costs
   that foe's worth (roles). A foe whose Hyper Beam knocked mine out spends the candidate's first turn recharging.
   A candidate with a burn move also gets the race where it burns a physical foe first. A sleeping candidate never
   goes before an awake one that survives its race. In singles, after my U-turn or Volt
   Switch (my Pokemon on the field still standing) when it moved first against the foe my decision faced (one that
   switched in this turn has spent its move), the foe's move is still to come and lands on the candidate: each
   candidate takes the foe's moves at the odds the selection AI gives them against my Pokemon, and half weighs the
   likely one that hurts it most; an Explosion takes the foe out with it. When no foe stands (my U-turn or Volt Switch knocked it
   out, or both sides' Pokemon fell), the engine gives no foe and its chooser keeps the party order (0x022039C2); the
   foe then picks after seeing mine, so each candidate is valued against each foe that can still fight, off the field,
   and keeps the worst. The candidates are sorted again by that value (rank), which is what tools/aivsai.py prints;
   equal values keep the original order. */

#define CHOOSER 0x02203974
#define NO_PLAN (-0x7FFFFFFF)
#define SELECT_LOST (-100000)       /* select_value: the hazards knock the candidate out, or it has no move to use */

/* `out` is a byte array on the caller's stack, in DTCM and unaligned: OK_PTR (word pointers in main RAM)
   rejected it */
#define OK_BYTES(p) (((u32)(p) >= RAM_LO && (u32)(p) < RAM_HI) || ((u32)(p) >= 0x027E0000u && (u32)(p) < 0x027E4000u))

int ai_serves(int client);      /* tools/asm/aiselect.s: 1 if the advanced AI decides for that client's trainer */

static Ctx rctx __attribute__((section(".itcm_bss")));
static u8 r_unsure __attribute__((section(".itcm_bss")));
/* each side's last replacement valued here, the trainer's first, for tools/aivsai.py (at REPLACED_AT, so it needs
   no symbol): seq counts them; orig is the chooser's order, out and v the order and values after the sort */
typedef struct { u8 seq, n, orig[MAX_BENCH], out[MAX_BENCH]; s32 v[MAX_BENCH]; } Replaced;

static int asleep(const Mon *m) { return m->status == S_SLP || m->status == S_FRZ; }

/* the chance (per-mille) that a's move m, one hit at most raw, knocks out a foe at hp in one use: the 85-100 rolls, a
   2-5 hit move's hit count (35/35/15/15%), its accuracy; endure: Focus Sash or Sturdy stops a single hit */
static s32 ko_odds(const Mon *a, const Mon *d, const MoveInfo *m, s32 raw, s32 hp, int weather, int endure)
{
    s32 p = 0, mx, mn, q, w;
    int h, lo = m->hits_min, hi = m->hits_max;
    if (raw <= 0)
        return 0;
    if (hi <= 1)
        lo = hi = 1;
    for (h = lo; h <= hi; h++) {
        w = lo == hi ? 1000 : lo == 2 && hi == 5 ? (h <= 3 ? 350 : 150) : 1000 / (hi - lo + 1);
        mx = raw * h;
        mn = mx * 85 / 100;
        q = mn >= hp ? 1000 : mx < hp ? 0 : 1000 * (mx - hp) / (mx - mn + 1);
        if (endure && h == 1)
            q = 0;
        p += w * q / 1000;
    }
    return p * move_acc(a, d, m, weather) / 100;
}

/* the best odds (per-mille) that a's moves knock d (at hp) out this turn, from the raw damage table, the higher
   priority and then the lower cost breaking ties; *prio: that move's priority (unchanged without a chance); *cost: the HP
   that knockout costs a (Life Orb, contact, recoil on the hp it takes; drain heals) */
static s32 best_ko(const Ctx *c, const Mon *a, const Mon *d, const u16 *raw, s32 hp, int endure, s8 *prio, s32 *cost)
{
    s32 best = 0, e, r;
    int k;
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &a->mv[k];
        if (!a->legal[k] || !m->cls || self_ko_move(m->id) || m->id == MV_FAKE_OUT || charges(a, m, c->weather))
            continue;
        e = ko_odds(a, d, m, move_damage(a, d, m, raw[k]), hp, c->weather, endure && !multi(a, m));
        r = life_orb_recoil(a, m) + contact_recoil(a, d, m) -
            (m->drain > 0 || (a->ability != AB_ROCK_HEAD && a->ability != AB_MAGIC_GUARD) ? hp * m->drain / 100 : 0);
        if (e > best || (e == best && e && (m->prio > *prio || (m->prio == *prio && r < *cost)))) {
            best = e;
            *prio = m->prio;
            *cost = r;
        }
    }
    return best;
}

/* candidate i's first turn on the field (x, as it comes in) against the foe (y), then the race: a side that knocks
   the other out this turn ends it there, at those odds; otherwise its race attack lands. Order by the priority of
   each side's move and speed. A faster candidate gets its hit in before it falls; a foe it knocks out first still gets
   in a priority hit that goes before its move (none through Psychic Terrain on a grounded one: move_damage). *falls:
   the foe knocks it out before it acts */
static s32 first_turn(const Ctx *c, int i, Fighter x, Fighter y, u8 *falls)
{
    const Mon *s = &c->bench[i], *d = &c->opp;
    s32 v_fo = x.fo ? race(c, x, y, 0) : NO_PLAN, v;     /* or its Fake Out first, as the race opens with it */
    s8 prx = x.prio, pry = y.prio;
    s32 cost = 0x7FFF, cy = 0;
    s32 px = x.sleep ? 0 : best_ko(c, s, d, c->d_bo[i], y.hp, y.endure && y.hp == y.maxhp, &prx, &cost);
    s32 py = y.sleep || y.recharge ? 0 : best_ko(c, d, s, c->d_ob[i], x.hp, x.endure && x.hp == x.maxhp, &pry, &cy);
    s32 v_ko, v_dead, v_go;
    Fighter a, b;
    int me_first = prx > pry || (prx == pry && faster(x.spe, y.spe)), up = !y.sleep && !y.recharge;
    if (!me_first && up && x.dmg >= y.hp && counter_slot(s, d, y.cls) >= 0)
        px = 1000, cost = 0;        /* its Counter (Mirror Coat, Metal Burst) returns the hit it lives through */
    s32 hit = !up ? 0 : !me_first ? y.dmg : y.pprio > prx ? y.pdmg : 0;
    *falls = !me_first && py >= 900;
    x.fo = 0;
    a = x;
    b = y;
    a.hp -= hit < a.hp ? hit : a.hp - 1;      /* the candidate knocks the foe out after its hit, and pays the knockout's cost */
    a.hp -= px ? cost : 0;
    if (a.hp > a.maxhp)
        a.hp = a.maxhp;
    b.hp = 0;
    v_ko = outcome(c, &a, &b, 1);
    a = x;
    b = y;
    a.hp = 0;
    if (me_first && !x.sleep)
        b.hp -= x.dmg < b.hp ? x.dmg : b.hp - 1;
    v_dead = outcome(c, &a, &b, 1);       /* the foe knocks the candidate out */
    a = x;
    b = y;
    if (px < 1000 && !x.sleep)
        b.hp -= x.dmg < b.hp ? x.dmg : b.hp - 1;
    if (py < 1000 && up)
        a.hp -= y.dmg < a.hp ? y.dmg : a.hp - 1;
    end_of_turn(&a);
    end_of_turn(&b);
    b.recharge = 0;                 /* a foe that must recharge spent this turn on it */
    v_go = a.hp > 0 && b.hp > 0 ? race(c, a, b, 1) : outcome(c, &a, &b, 1);
    if (me_first)
        v = (px * v_ko + (1000 - px) * ((py * v_dead + (1000 - py) * v_go) / 1000)) / 1000;
    else
        v = (py * v_dead + (1000 - py) * ((px * v_ko + (1000 - px) * v_go) / 1000)) / 1000;
    if (v_fo > v && (px < 500 || !me_first)) {
        *falls = 0;                 /* its Fake Out goes first */
        return v_fo;
    }
    return v;
}

/* the same after the foe's move this turn lands on the candidate as it comes in (k: that move), at its odds */
static s32 pivot_turn(const Ctx *c, int i, int k)
{
    Fighter x = c->ent_me[i], y = c->ent_foe[i];
    s32 hit, v = 0;
    u8 t;
    int ko = entry_hit(c, i, k, &hit);
    take(&x, hit, (unsigned)k < 4 && multi(&c->opp, &c->opp.mv[k]));
    if ((unsigned)k < 4 && self_ko_move(c->opp.mv[k].id))
        y.hp = 0;                   /* its Explosion (Memento...) takes it out too */
    if (x.hp > 0)
        v = y.hp ? first_turn(c, i, x, y, &t) : outcome(c, &x, &y, 1);
    else
        ko = 100;
    x.hp = 0;
    return (ko * outcome(c, &x, &y, 1) + (100 - ko) * v) / 100;
}

/* the turn candidate x spends on its burn move, then the race; a burn halves the foe's physical damage and
   takes 1/16 a turn (as value_status counts it) */
static s32 burn_turn(const Ctx *c, Fighter x, Fighter y, int me_first, int lands)
{
    x.fo = 0;
    if (!me_first)
        strike(&y, &x, 100, x.sleep > 0);
    if (x.hp <= 0)
        return outcome(c, &x, &y, 1);
    if (lands) {
        y.dmg /= 2;
        y.dmg64 /= 2;
        y.chip += c->opp.maxhp / 16;
    }
    if (me_first)
        strike(&y, &x, 100, x.sleep > 0);
    if (x.hp <= 0)
        return outcome(c, &x, &y, 1);
    end_of_turn(&x);
    end_of_turn(&y);
    return y.hp > 0 ? race(c, x, y, 1) : outcome(c, &x, &y, 1);
}

/* candidate i burns the foe first, when a burn halves the foe's best attack on it (burn_cuts) */
static s32 burn_first(const Ctx *c, int i)
{
    const Mon *s = &c->bench[i], *d = &c->opp;
    const Fighter *x = &c->ent_me[i], *y = &c->ent_foe[i];
    s8 prio;
    int k, slot, acc, me_first;
    best_rate(d, s, c->d_ob[i], c->weather, &prio, &slot, THEIR_ROLL, 0);
    if (!burn_cuts(d, slot))
        return NO_PLAN;
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &s->mv[k];
        if (!s->legal[k] || m->quality != Q_SICK || m->sick != S_BRN || m->target == TARGET_USER || status_blocked(c, s, d, m))
            continue;
        acc = move_acc(s, d, m, c->weather);
        me_first = m->prio > y->prio || (m->prio == y->prio && faster(x->spe, y->spe));
        return (acc * burn_turn(c, *x, *y, me_first, 1) + (100 - acc) * burn_turn(c, *x, *y, me_first, 0)) / 100;
    }
    return NO_PLAN;
}

/* the foe (at party slot fi: 0 on the field) and the candidates as the selection AI's snapshot reads them; 0 if
   anything is off */
static int replace_snapshot(Ctx *c, void *client, const u8 *out, int n, void *opp, int fi)
{
    u8 *main = AT(bptr, MAIN_PTR);
    void *pc = E_POKECON(1), *party = AT(vptr, (u32)client + 0x1C), *op, *field;
    int i, raw, shield, lo = SELFPLAY() ? 1 : 13;
    memset(c, 0, sizeof *c);
    c->unsure = &r_unsure;
    if (!OK_PTR(pc) || !OK_PTR(party) || !read_mon(&c->opp, opp, fi) || !c->opp.alive)
        return 0;
    for (i = 0; i < n; i++) {
        void *b = out[i] <= 5 ? E_PARTY_MEMBER(party, out[i]) : 0;
        if (!OK_PTR(b) || B_ID(b) < lo || B_ID(b) >= 24)   /* the player's side picks for itself */
            return 0;
        if (!read_mon(&c->bench[i], b, out[i]) || !c->bench[i].alive)
            return 0;
    }
    c->nbench = n;
    c->client = E_CLIENT_OF(c->bench[0].id);
    c->opp_client = E_CLIENT_OF(c->opp.id);
    if (!fi) {                          /* the foe on the field: its substitute and its Choice lock, as snapshot reads them */
        c->opp.subbed = subbed(c->opp_client, 0);
        lock_foe(&c->opp);
        for (i = 0; i < n; i++)         /* an Imposter candidate comes in as its copy (A1B_IMPOSTER) */
            imposter_copy(c, &c->bench[i]);
    }
    op = E_PARTY(pc, c->opp_client);
    if (OK_PTR(op))
        for (i = 0; i < E_PARTY_COUNT(op) && i < 6; i++) {
            void *b = E_PARTY_MEMBER(op, i);
            Mon t;
            if (b == opp || !OK_PTR(b) || !B_HP(b) || !E_FIGHTABLE(b))
                continue;
            c->opp_others++;
            if (!c->spare.bpp && !read_mon(&c->spare, b, i))
                c->spare.bpp = 0;
            if (read_mon(&t, b, i))
                foe_hazards(c, &t);     /* what one more layer of my hazards is worth (select_value's hazard moves) */
        }
    field = AT(vptr, (u32)main + MAIN_FIELD);
    raw = OK_PTR(field) ? AT(u8, field) : 0;
    c->weather = raw <= W_HAIL ? raw : raw == WX_HARSH_SUN ? W_SUN : raw == WX_HEAVY_RAIN ? W_RAIN : W_NONE;
    shield = terrain_shield(c);
    for (i = -2; i < n; i++) {
        Mon *m = i == -2 ? &c->opp : i == -1 ? &c->spare : &c->bench[i];
        int sh = shield;
        if (!m->bpp)
            continue;
        weather_moves(m, c->weather, raw);
        if (i >= 0)                     /* a candidate's Surge sets its terrain as it comes in, before the foe moves */
            sh = m->ability == AB_PSYCHICSURGE ? SHIELD_PRIO : m->ability == AB_MISTY_SURGE ? SHIELD_STATUS :
                 m->ability == AB_ELEC__SURGE ? SHIELD_SLEEP : m->ability == AB_GRASSY_SURGE ? SHIELD_HEAL :
                 m->ability == AB_THUNDER_ROAR ? SHIELD_SLEEP | SHIELD_PRIO : shield;
        m->shield = grounded(m) ? sh : 0;
        if (SIDE_LAYERS((c->client & 1) ^ (i < 0), SE_SAFEGUARD))
            m->shield |= SHIELD_STATUS;     /* Safeguard on its side, as snapshot_common has it */
    }
    return 1;
}

/* the candidates' values are final here, before the sort (the place for team-plan rules). A sleeping candidate never goes
   before an awake one that survives its race (awake: the best of those). One the foe knocks out before it acts (f 1)
   never goes before one that acts, and one the hazards knock out on entry (f 2) before one that comes in alive: either
   only hands the foe a knockout */
static void rank(const Ctx *c, s32 *v, const u8 *f, int n, int awake)
{
    int i, l;
    s32 top;
    for (i = 0; i < n; i++)
        if (awake >= 0 && asleep(&c->bench[i]) && v[i] >= v[awake])
            v[i] = v[awake] - 1;
    for (l = 1; l <= 2; l++) {
        for (i = 0, top = NO_PLAN; i < n; i++)
            if (f[i] < l && v[i] > top)
                top = v[i];
        for (i = 0; i < n; i++)
            if (f[i] == l && top > NO_PLAN && v[i] >= top)
                v[i] = top - 1;
    }
}

/* select_value's working memory (battle heap): the Ctx it values a candidate in, and the foe's Pokemon off the field
   (the team plan's columns), read once */
typedef struct { Ctx k; Mon foe[MAX_BENCH], t; u8 col[MAX_BENCH], nfoe; } Select;

/* a singles battle, as the selection AI's snapshot tells it: one Pokemon out a side, no partner and no second foe */
static int singles(int cl)
{
    void *pc = E_POKECON(1), *partner = E_PARTY(pc, cl ^ 2), *opp2 = E_PARTY(pc, cl ^ 3);
    return E_ACTIVES(cl) == 1 && E_ACTIVES(cl ^ 1) == 1 && !(OK_PTR(partner) && E_PARTY_COUNT(partner)) &&
           !(OK_PTR(opp2) && E_PARTY_COUNT(opp2));
}

static void select_foes(const Ctx *c, Select *w)
{
    void *op = E_PARTY(E_POKECON(1), c->opp_client);
    int i, n = OK_PTR(op) ? E_PARTY_COUNT(op) : 0;
    w->nfoe = 0;
    for (i = 1; i < n && i < 6; i++) {
        void *b = E_PARTY_MEMBER(op, i);
        if (b != c->opp.bpp && OK_PTR(b) && B_HP(b) && E_FIGHTABLE(b) && read_mon(&w->foe[w->nfoe], b, i))
            w->col[w->nfoe++] = i - 1;
    }
}

/* candidate i as the selection AI values its first decision on the field after my Pokemon fainted: its entry hazards,
   then the best of its move values (mixed, against the foe's reply odds), less what the hazards took. The other
   candidates' team-plan rows and entries are c's (roles, entries: the same Pokemon against the same foe); only the
   candidate's own are new */
static s32 select_value(const Ctx *c, int i, Select *w)
{
    Ctx *k = &w->k;
    Pair p;
    s32 top = NO_PLAN, v, hp0, chip;
    int j, m, b;
    *k = *c;
    k->me = c->bench[i];
    for (m = 0; m < 4; m++) {
        k->d_mo[m] = c->d_bo[i][m];
        k->d_om[m] = c->d_ob[i][m];
    }
    k->nbench = c->nbench - 1;
    for (j = 0; j < MAX_BENCH; j++) {
        b = j < i ? j : j + 1;
        for (m = 0; m < MAX_BENCH; m++)
            k->need[j][m] = j < k->nbench ? c->need[b][m] : 0;
        if (j >= k->nbench)
            continue;
        k->bench[j] = c->bench[b];
        for (m = 0; m < 4; m++) {
            k->d_bo[j][m] = c->d_bo[b][m];
            k->d_ob[j][m] = c->d_ob[b][m];
        }
        k->ent_me[j] = c->ent_me[b];
        k->ent_me[j].who = j;
        k->ent_foe[j] = c->ent_foe[b];
        k->ent_foe[j].recharge = 0;
    }
    k->trapped = k->xin = 0;
    k->me.fresh = k->me.turns = 1;
    k->me.protects = 0;
    hp0 = k->me.hp;
    k->me.hp -= hazard_hp(k, &k->me, &chip);
    if (k->me.hp <= 0)
        return SELECT_LOST;
    if (chip > 0)
        k->me.status = S_PSN;           /* Toxic Spikes poisoned it on entry */
    g_nalt = 0;
    for (j = 0; j < w->nfoe; j++) {
        w->t = w->foe[j];               /* role_of lowers its HP */
        role_of(k, &w->t, w->col[j], k->nbench);
    }
    pair_data(k, &p);
    reply_odds(k, &p);
    entries_from(k, &p, k->nbench);
    for (m = 0; m < 4; m++) {
        const MoveInfo *mv = &k->me.mv[m];
        if (!mv->id || !k->me.legal[m] || vetoed(k, m))
            continue;
        v = mixed(k, &p, mv->cls || mv->id == MV_SLEEP_TALK ? K_MOVE : K_MOVE + 3, m);
        if (v > top)
            top = v;
    }
    g_nalt = 0;
    return top == NO_PLAN ? SELECT_LOST : top - (worth(hp0, k->me.maxhp) - worth(k->me.hp, k->me.maxhp));
}

static void replace_sort(void *client, u8 *out, int n, void *opp, int cl)
{
    Ctx *c = &rctx;
    Replaced *rec;
    Pair p;
    s32 v[MAX_BENCH], vf[MAX_BENCH], b;
    u8 t[MAX_BENCH], fi[6];
    void *foe[6], *out0, *op;
    int i, j, k, f, nf = 0, alive, awake, pivot;
    tune_side((cl & 1) ^ 1);           /* before any value code (replace_snapshot reads no tuned value) */
    g_wb = WORTH_BASE;
    rec = (Replaced *)REPLACED_AT + ((cl & 1) ^ 1);
    if (OK_PTR(opp) && B_HP(opp)) {
        foe[0] = opp;
        fi[nf++] = 0;
    } else if (E_ACTIVES(cl) == 1) {
        op = E_PARTY(E_POKECON(1), cl ^ 1);
        for (i = 1; OK_PTR(op) && i < E_PARTY_COUNT(op) && i < 6; i++) {
            foe[nf] = E_PARTY_MEMBER(op, i);
            if (OK_PTR(foe[nf]) && B_HP(foe[nf]) && E_FIGHTABLE(foe[nf]))
                fi[nf++] = i;
        }
    }
    for (f = 0; f < nf; f++) {
        Select *sel;
        if (!replace_snapshot(c, client, out, n, foe[f], fi[f]))
            return;
        c->strong = strength_of(c);     /* the foe as the selection AI's last decision read it */
        memset(&p, 0, sizeof p);
        p.my_slot = p.opp_slot = p.rep = -1;
        pivot = 0;
        awake = -1;
        out0 = E_PARTY_MEMBER(AT(vptr, (u32)client + 0x1C), 0);
        if (E_ACTIVES(c->client) == 1 && OK_PTR(out0) && B_HP(out0) && read_mon(&c->me, out0, 0) && c->me.alive) {
            weather_moves(&c->me, c->weather, c->weather);
            sims_active(c);
            pair_data(c, &p);
            /* the foe's move is still to come, unless it came in this turn (a switch is its move) */
            pivot = !fi[f] && (reads(c)->magic != READ_MAGIC || reads(c)->foe == c->opp.bpp) &&
                    faster(eff_speed(&c->me, c->weather), eff_speed(&c->opp, c->weather));
        }
        for (i = 0; i < n; i++)
            damage_bench(c, i);
        sel = !fi[f] && !c->me.bpp && singles(c->client) ? E_ALLOC(HEAP_BATTLE, sizeof *sel) : 0;
        if (sel)
            select_foes(c, sel);
        roles(c);                          /* my Pokemon on the field, if any, counts among the answers */
        if (pivot)
            reply_odds(c, &p);
        entries(c, &p);
        if (!c->me.bpp)
            c->ent_me[MAX_BENCH].hp = 0;   /* the Pokemon that fainted: no entry after it */
        if (!fi[f] && !pivot && (B_TURNFLAGS(c->opp.bpp) & 2))
            for (i = 0; i < n; i++)        /* its Hyper Beam knocked mine out: it spends the next turn recharging */
                c->ent_foe[i].recharge = 1;
        for (i = 0; i < n; i++) {
            rec->orig[i] = out[i];
            t[i] = 0;
            if (c->ent_me[i].hp <= 0) {     /* the hazards knock it out on entry, and the next one comes in free */
                vf[i] = outcome(c, &c->ent_me[i], &c->ent_foe[i], 0);
                t[i] = 2;
                continue;
            }
            race_ex(c, c->ent_me[i], c->ent_foe[i], 0, &alive);
            if (pivot) {
                s32 sum = 0, w = 0, mn = 0x7FFFFFFF, pv;
                for (k = 0; k < 4; k++)
                    if (p.w[k] && (!p.ko || p.w[k] >= 5)) {      /* as switches() weighs a switch-in's hit */
                        pv = pivot_turn(c, i, k);
                        sum += p.w[k] * pv;
                        w += p.w[k];
                        if (p.w[k] >= 5 && c->opp.mv[k].cls && pv < mn)
                            mn = pv;
                    }
                vf[i] = w ? sum / w : first_turn(c, i, c->ent_me[i], c->ent_foe[i], &t[i]);
                if (mn < vf[i])
                    vf[i] = (vf[i] + mn) / 2;
            } else
                vf[i] = first_turn(c, i, c->ent_me[i], c->ent_foe[i], &t[i]);
            b = burn_first(c, i);
            if (b > vf[i]) {                /* it burns the foe first (Prankster): it acts */
                vf[i] = b;
                t[i] = 0;
            }
            if (alive && !asleep(&c->bench[i]) && (awake < 0 || vf[i] > vf[awake]))
                awake = i;
        }
        rank(c, vf, t, n, awake);
        if (sel) {      /* the entry race's best three, each as the selection AI values it; the others after them */
            u8 ord[MAX_BENCH], o;
            for (i = 0; i < n; i++)
                for (j = i, ord[i] = i; j > 0 && vf[ord[j]] > vf[ord[j - 1]]; j--) {
                    o = ord[j];
                    ord[j] = ord[j - 1];
                    ord[j - 1] = o;
                }
            for (i = 0; i < n; i++)
                vf[ord[i]] = i < 3 ? select_value(c, ord[i], sel) : NO_PLAN + n - i;
            E_FREE(sel);
        }
        for (i = 0; i < n; i++)
            if (!f || vf[i] < v[i])
                v[i] = vf[i];
    }
    if (!nf)
        return;
    for (i = 1; i < n; i++)            /* insertion sort, best first; equal values keep the original order */
        for (j = i; j > 0 && v[j] > v[j - 1]; j--) {
            s32 sv = v[j];
            u8 o = out[j];
            v[j] = v[j - 1];
            v[j - 1] = sv;
            out[j] = out[j - 1];
            out[j - 1] = o;
        }
    for (i = 0; i < n; i++) {
        rec->out[i] = out[i];
        rec->v[i] = v[i];
    }
    rec->n = n;
    rec->seq++;
}

/* the move records the call reads are kept in the battle heap until it returns (none if that fails: E_WAZA then) */
int ai_replace(void *client, u8 *out, int n, void *opp, int x)
{
    int r = CALL(CHOOSER, int, void *, u8 *, int, void *, int)(client, out, n, opp, x);
    u8 *main = AT(bptr, MAIN_PTR);
    int cl = AT(u8, (u32)client + 2);
    /* the client's number is at +2 (the poll's argument, overlay 14 0x0220372E); ai_serves checks the trainer battle */
    if (n < 2 || n > MAX_BENCH || !OK_BYTES(out) || !OK_PTR(main) || !ai_serves(cl))
        return r;
    g_wz = E_ALLOC(HEAP_BATTLE, sizeof *g_wz);
    if (g_wz)
        g_wz->n = 0;
    replace_sort(client, out, n, opp, cl);
    waza_close();
    if (g_wz)
        E_FREE(g_wz);
    g_wz = 0;
    return r;
}
