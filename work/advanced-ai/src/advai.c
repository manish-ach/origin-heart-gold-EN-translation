/* Advanced trainer AI. Built into overlay 10 after a byte copy of overlay 11 (the original AI) and
   loaded instead of it when flag 0x2C2 is set in a trainer battle (tools/asm/aiselect.s). The battle
   client polls adv_entry once per frame with the original AI's arguments; it returns 0 while working
   and 1 once one action is written through the engine's setters.

   Each turn it reads both sides, then values every legal option (each move, each switch, each usable
   trainer item) by simulating it: the option's turn against the player's best reply, ordered by
   priority and speed, then both sides trading their best moves until one faints (the race, common.h).
   Values are on a team scale: what each side's Pokemon lose (a Pokemon is worth more the more HP it
   has), the KO that ends the battle, and, when mine faints first, the free entry of my best Pokemon
   left. Moves that cannot work are vetoed before any of that.

   On the trainer's side it then waits for the player's committed action (foe_choice: the player client's records,
   read once its adapter has answered the server), so each option is valued against that action instead of the odds
   of the player's replies: a known move is the only reply, a known switch puts the newcomer in front, a known item
   heals or cures first. The player's side never waits, so two advanced AIs never wait for each other. Since rc33
   (RD, rd_gate) the read is used only when the blind foe model expected that action (odds of at least rd_t per mille)
   or on the AI's own 20% draw; otherwise the decision is the blind one.

   Safety: every engine pointer and value is range checked; work is spread over polls; any failed
   check, an unsupported battle (doubles) or too many polls hands the turn to the original AI (whose
   code is in this same overlay image), so the battle always gets a legal action. */
#include "engine.h"
#include "ids.h"
#include "tune.h"

/* the tuning table (tune.h): an initialized array in arm9's ITCM code block (section .itcm.tune), which the game
   copies at boot and never writes, so the real game runs the defaults; the bench finds it by its magic and writes
   each side's copy after a state load. v[0] the trainer side's, as ai_debug. g_tp: the copy of the side deciding,
   set by adv_entry at every poll and by ai_replace before any value code. TP(NAME): its NAME (the ## keeps a
   `#define NAME TP(NAME)` from expanding again) */
#define TUNE_ENUM(n, d, lo, hi, st) TU_##n,
#define TUNE_DEF(n, d, lo, hi, st) d,
enum { TUNE_LIST(TUNE_ENUM) TUNE_N };
#define TUNE_MAGIC 0x454E5554u          /* "TUNE" */
struct Tune { u32 magic; u16 version, n; u16 v[2][TUNE_N]; };
__attribute__((section(".itcm.tune"), used)) struct Tune g_tune =
    { TUNE_MAGIC, TUNE_VERSION, TUNE_N, { { TUNE_LIST(TUNE_DEF) }, { TUNE_LIST(TUNE_DEF) } } };
static const u16 *g_tp __attribute__((section(".itcm_bss")));
#define TP(n) ((s32)g_tp[TU_##n])

static void tune_side(int side)
{
    g_tp = g_tune.v[side];
}

#define MAX_CTX 3            /* AI clients deciding at once: 3 at most in the game (a tag battle with a partner) */
#define MAX_OPT 16
#define POLL_LIMIT 20
#define DEBUG_MAGIC 0x49414441u     /* "ADAI" */
#define SWITCH_COST TP(SWITCH_COST)
#define KO_TEMPO TP(KO_TEMPO)        /* knocking the foe out this turn: no reply, no crit, no comeback */
/* options within NEAR of the best value are comparable: among them the surest KO wins, then the least committed
   move, then the value. Below LOST every option loses the Pokemon: the band widens a little and the KO this turn
   counts (the branches where it gets to act are in the values: the foe misses, rolls low or is too slow). An option
   that loses my Pokemon this turn for nothing (FELL_SLACK more often than the best value does) is never preferred */
#define NEAR 16
#define NEAR_LOST 40
#define LOST (-800)
#define FELL_SLACK 50       /* Option.fell units (4 per-mille): 20% more often */
#define EFFECT_LOCK 27      /* move effect of Outrage, Thrash, Petal Dance: locked in, then confused */
#define DAMAGE_CREDIT TP(DAMAGE_CREDIT)    /* this turn's expected damage, below one turn's cost (100): separates equal races */
#define WAKE_CREDIT 30      /* asleep: the move is used only if it wakes this turn; ranks the attacks for that case */
#define LAST_BONUS TP(LAST_BONUS)      /* the KO that ends the battle */

#define RACE_TURNS 16
#define MAX_BENCH 5                   /* a party's Pokemon off the field */
#define WHO_ACTIVE MAX_BENCH          /* Fighter.who: bench Pokemon are 0..MAX_BENCH-1 */
#define WHO_LAST 8                    /* Fighter.who bit: a free entry, after which no further entry is counted */
#define WHO_FOLLOW (WHO_LAST | 7)     /* such an entry of no Pokemon in particular (no roles) */
#define WORTH_BASE TP(WORTH_BASE)      /* a Pokemon's worth at 1 HP, of 1000 at full, against a weak player */
#define WORTH_STRONG TP(WORTH_STRONG)  /* the same against a strong player (set_worth) */
#define ROLE_W TP(ROLE_W)       /* per-mille scale of role_loss */
#define TEMPO TP(TEMPO)           /* per turn a won race takes: crits, misses, setup and switches have time to happen */

/* move effect classes. The move data's effect code is shared by every move that works alike (Protect, King's
   Shield...); effect_class pairs class << 9 with that code (every code listed is below 512). X_FANG: Super Fang,
   Ruination (half the target's HP); X_ERUPT: Eruption, Water Spout (power by the user's HP); X_HELP: Helping Hand;
   X_CURE: Heal Bell, Aromatherapy; X_GLAIVE: Glaive Rush (hits on its user do double until it moves again); X_SMASH:
   Shell Smash; X_TROOM: Trick Room; X_PRESS: Body Press (the user's Defense for Attack); X_RAIN..X_SNOW in W_* order.
   X_WISH is Healing Wish only: this hack's Lunar Dance raises Speed and Sp. Atk and the user stays (32 of 32 in logs) */
enum { X_NONE, X_PIVOT, X_PROTECT, X_DESTINY, X_PAIN_SPLIT, X_MEMENTO, X_WISH, X_TAUNT, X_FANG, X_ERUPT, X_HELP, X_CURE,
       X_GLAIVE, X_SMASH, X_TROOM, X_PRESS, X_RAIN, X_SUN, X_SAND, X_SNOW, X_ROCKS, X_SPIKES, X_TSPIKES };
_Static_assert(X_TSPIKES < 128, "effect_class holds the class in 7 bits");
static const u16 effect_class[] = {
    X_PIVOT << 9 | 228, X_PROTECT << 9 | 111, X_PROTECT << 9 | 355, X_PROTECT << 9 | 361, X_PROTECT << 9 | 383,
    X_PROTECT << 9 | 441, X_PROTECT << 9 | 451, X_DESTINY << 9 | 98, X_PAIN_SPLIT << 9 | 91, X_MEMENTO << 9 | 168,
    X_WISH << 9 | 220, X_TAUNT << 9 | 175, X_ROCKS << 9 | 266, X_SPIKES << 9 | 112,
    X_TSPIKES << 9 | 249, X_FANG << 9 | 40, X_ERUPT << 9 | 190, X_HELP << 9 | 176, X_CURE << 9 | 102,
    X_GLAIVE << 9 | 456, X_SMASH << 9 | 308, X_TROOM << 9 | 259, X_PRESS << 9 | 433,
    X_RAIN << 9 | 136, X_SUN << 9 | 137, X_SAND << 9 | 115, X_SNOW << 9 | 164, X_SNOW << 9 | 465,
};

typedef struct {
    u16 id;
    u8 type, cls, power, acc, quality, target, hits_min, hits_max;
    s8 prio, drain, heal;
    u16 sick;
    u8 sick_per, secondary;          /* secondary: a chance effect (Sheer Force drops it, and Life Orb's recoil) */
    u8 rank_type[3];
    s8 rank_val[3];
    u8 ate;                          /* an -ate ability made it a stronger move of another type (x1.2, measured) */
    u8 flinch;                       /* percent chance a hit makes the target flinch */
    u8 efx;                          /* X_*: what the move does beyond damage and status, by its effect code */
    u8 fails;                        /* the weather makes it fail (Water moves in harsh sun, Fire in heavy rain) */
    u32 flags;
} MoveInfo;

typedef struct {
    void *bpp;
    u8 id, party, level, status, nmoves, alive, fresh;   /* fresh: its first turn out */
    u8 types[3];
    u16 species, ability, item;
    s32 hp, maxhp;
    u16 stat[5];
    s8 stage[7];
    MoveInfo mv[4];
    u8 pp[4], legal[4];
    u8 turns;                        /* turns since it came out */
    u8 protects, tailwind;           /* Protects in a row; turns left of the Tailwind on its side (speed x2), this one included */
    u8 shield;                       /* SHIELD_*: what the terrain stops against it */
    u8 subbed;                       /* a substitute is up (read for the foes on the field) */
    u8 slept;                        /* asleep: the turns it slept through so far (0-3) */
    u16 semi;                        /* SEMI_*: out of reach this turn (B_SEMI) */
    u16 charging;                    /* the move it charged last turn, which lands this turn (0 none) */
    u8 sleep;                        /* turns it still sleeps through (frozen: 2); 0 the turn it wakes, when it acts */
    u8 drowsy;                       /* Yawn: it falls asleep at this turn's end */
} Mon;

/* a terrain protects grounded Pokemon: Psychic from priority moves, Misty from statuses, Electric from sleep; Grassy
   heals them a sixteenth at each turn's end (seen in logs: s009_g1 of run 20261003_133101_self, turn 14) */
enum { SHIELD_PRIO = 1, SHIELD_STATUS = 2, SHIELD_SLEEP = 4, SHIELD_HEAL = 8 };

/* one side of a race. recoil: HP each of its strikes costs it (Life Orb, contact, move recoil; drain heals);
   endure: Sash or Sturdy still up at full HP; multi: its attack hits several times, which goes through that;
   hp0: its HP when the turn was chosen; who: which of my Pokemon (WHO_*), for the free entry after a faint;
   dmg64, spe64: what boosts and statuses gained in the race did to its damage and speed (x64), which the next
   Pokemon it meets still faces; tox: badly poisoned, the sixteenths its next tick takes; wish: (the foe's side)
   a Healing Wish waits for my next Pokemon; dream: its Dream Eater, which lands while the foe sleeps through the turn;
   nap: (the foe's side) per-mille odds it puts my awake fighter to sleep on a turn, as the race's first move;
   drowsy: turn ends until Yawn puts it to sleep; pdmg, pprio: its best priority attack, used when it knocks the
   other out; drain: the percent of the damage dealt its race attack drains (recoil: negative), already in recoil at
   full dmg; healed: recovery moves used in the race; fo: (my side) a newcomer's Fake Out, on its first turn out;
   fang: its race attack is Super Fang, which takes this percent of the other's HP left (half, times its accuracy);
   berry: what its Sitrus Berry heals once at half HP or below (seen in logs: a quarter); boost: (the foe's side) the stat
   its boost move raises (1 Attack, 3 Sp. Atk) | the stages << 2; para: 1 paralyzed (para_mix also plays the race where
   it loses actions); 2-5 in that race, its place in a cycle of four actions whose first is lost */
typedef struct {
    s32 hp, maxhp, dmg, spe, chip, heal, recoil, hp0, dream, pdmg;
    s16 dmg64, spe64, nap;
    union { s16 fo, boost; };                           /* fo my side, boost the foe's */
    s8 prio, heal_prio, who, pprio, drain;
    u8 sleep, recharge, endure, multi, flinch, talk;    /* talk: Sleep Talk or Snore, so it attacks while asleep */
    u8 tox, wish, drowsy, healed;
    u8 cls;                                             /* class of its race attack (1 physical, 2 special; 0 fixed damage) */
    u8 tw;                                              /* turns its side's Tailwind lasts, this one included (spe has it) */
    u8 fang;
    u8 orb;                                             /* its Flame (Toxic) Orb at the next turn's end: orb_code; 1 gone off */
    u8 grow;                                            /* stages its boost move adds to its race attack (Swords Dance 2);
                                                           MIRROR: it only returns hits (Counter, Mirror Coat) */
    u8 berry;
    u8 para;
    u8 moody;                                           /* Moody (A1B_MOODY): its stages climb at each turn's end */
} Fighter;
#define MIRROR 0x80

/* the race counts conservatively: my damage below average, the player's above */
#define MY_ROLL TP(MY_ROLL)
#define THEIR_ROLL TP(THEIR_ROLL)

/* a foe's action this turn, committed before my decision (read_choice). kind FK_*; idx its move slot (FK_MOVE), party
   index (FK_SWITCH) or its item's target pokeID (FK_ITEM); item its item; hits (doubles) which of mine its move lands
   on, HIT_*; tgt, once its switch-in replaced it, the pokeID my move aims at (the position stays) */
typedef struct { u8 kind, idx, hits, tgt; u16 item; } Known;
enum { FK_NONE, FK_MOVE, FK_SWITCH, FK_ITEM };
enum { HIT_ME = 1, HIT_ALLY = 2, HIT_HALF = 4 };     /* HIT_HALF: a random foe, one of the two */

/* ko1: chance (per-mille) of a KO this turn; ko3: the chances of a KO by turns 1, 2 and 3 added up, both only for the
   turns its user gets to act; cost: what the move commits me to (counted between moves that KO); selfko: the user
   faints; dealt: the foe's HP it takes this turn on average, in eighths of its max HP; sure: it KOs whenever it is
   used, and its user is likely to act; fell: the chance (4 per-mille units) that my Pokemon on the field faints this
   turn while the foe does not; st: a status move, whose ko1 is only the lost position's sleep or paralysis; spared: a
   move whose user surely falls this turn, its value if the foe's move does nothing to it (a miss, a boost, a switch),
   which breaks a tie of moves that all faint without acting */
typedef struct { u8 kind, idx; s16 extra; s32 value; s16 ko1, ko3; u8 cost, selfko, dealt, sure, fell, st; s16 spared; } Option;

typedef struct {
    void *st;
    u8 mode, phase, polls, client, opp_client, trainer, nbench, fallback;
    Mon me, opp;
    Mon bench[MAX_BENCH];
    u16 d_mo[4], d_om[4];                 /* raw (max roll) damage: my moves -> opponent, its moves -> me */
    u16 d_bo[MAX_BENCH][4], d_ob[MAX_BENCH][4];  /* doubles: per foe, what bench_doubles sums up */
    u8 trapped, weather, opp_others;      /* opponent's other Pokemon still able to fight */
    u8 absorb[4];                         /* the foe's Pokemon off the field that my move i does nothing to */
    u8 covered[2];                        /* doubles: my partner knocks foe f out before it moves */
    u8 removed[2];                        /* doubles: my partner knocks foe f out this turn, in either order */
    u16 ally_dmg[2];                      /* doubles: my partner's best expected damage on foe f */
    u8 before[2];                         /* doubles: my partner knocks foe f out before it moves (covered, kept) */
    u8 ally_sure[2];                      /* doubles: my partner's best attack lands on f whatever it aims at */
    u16 ally_on_me;                       /* doubles: what my partner's spread move (Earthquake) takes from me */
    u16 lead_dmg[2];                      /* doubles: what my partner's action, chosen before mine this turn, deals f */
    u8 haz[3];                            /* foe_hazards: one more layer of Stealth Rock, Spikes, Toxic Spikes */
    u8 terrain;                           /* TERRAIN_* on the field, 0 none */
    /* doubles: the foes on the field, my partner, raw damage between all of them (engine simulation) */
    u8 doubles, nfoes, has_ally;
    Mon foes[2], ally;
    Mon spare;                            /* one of the foe's Pokemon off the field (bpp 0: none) */
    Fighter ent_me[MAX_BENCH + 1], ent_foe[MAX_BENCH + 1];   /* each of mine (WHO_ACTIVE last) against the foe */
    u16 d_mf[2][4], d_ma[4], d_fm[2][4], d_fa[2][4];
    u8 *unsure;                           /* counts simulations that drew more than the roll (ai_debug) */
    /* the team plan (roles): by Fighter.who and foe off the field (its party slot - 1), the HP my Pokemon needs to beat
       that foe, in 255ths of its max HP (0: it does not); per foe, what losing such an answer costs */
    u8 need[MAX_BENCH + 1][MAX_BENCH];
    u16 stake[MAX_BENCH];
    /* the same for my active with the stages of its boost move (by slot; 4: none), against each foe after its entry
       hazards; per foe, its worth halved per answer of mine besides my active (boost_carry) */
    u8 bneed[5][MAX_BENCH];
    u16 bstake[MAX_BENCH];
    /* singles: xslot, my attack the foe expects (the strongest); foes[0], the foe's Pokemon off the field it hurts least,
       the likely switch-in; xin: d_mf[0] and d_mf[1] hold the raw damage of my moves on that one and of its moves on me
       (switch_in) */
    u8 xin;
    s8 xslot;
    struct Debug *dbg;                    /* this side's ai_debug record */
    s16 strong;                           /* 0-1000: the foe's play so far says it is a strong player (strength) */
    s16 xhaz;                             /* what the hazards on its side take from the switch-in, on the team scale */
    /* read_choice: each foe's action this turn, committed before my decision (foe_choice; singles kn[0], doubles by
       foes[]); known once foe_choice answered; fcl the client of each of foes[]; swapped bit f: foes[f] is the switch-in
       that replaced the foe on the field (doubles; singles swaps it into opp); waiting: everything but the reply is
       decided and the foe has not chosen yet (ai_slot_free) */
    Known kn[2];
    u8 known, swapped, fcl[2], waiting;
    u8 fs_move;                           /* singles: the foe committed a move (its slot + 1), read or not (RD): foresight's cells hold */
    s16 xw;                               /* singles: foe_switch's odds of the switch to foes[0], per mille (0: none) */
    Option held;                          /* phase PH_STEER: the option decided, written after the steer */
} Ctx;

enum { M_NEW, M_WORK, M_FALLBACK };
enum { FB_NONE, FB_MAIN, FB_ME, FB_NOT_SINGLES, FB_OPP, FB_POLLS, FB_NO_OPTION, FB_SNAPSHOT, FB_ALLOC };
enum { K_MOVE, K_SWITCH, K_ITEM };


/* why pick() took an option that is not the best value (ai_debug.why); WHY_STATUS: sleep or paralysis in a lost position */
enum { WHY_TOP, WHY_KO, WHY_COST, WHY_DEALT, WHY_STATUS };

/* read by tools/aibench.py at the start of this overlay's bss; one per side (version 3), the trainer's first. Version 4
   adds strong, and the foe's likely switch-in with the weight its case got (per-mille); version 5 role, what my active's
   roles are worth at its HP (role_loss down to 0 HP: tools/aiprops.py adds it to the absolute scale) */
typedef struct Debug {
    u32 magic;
    u16 version;
    u8 polls, fallback;
    u32 decisions;
    u16 me_species, opp_species;
    u16 me_hp, me_maxhp, opp_hp, opp_maxhp;
    u16 me_stat[5], opp_stat[5];
    u8 me_types[3], opp_types[3];
    u8 me_level, opp_level, me_status, opp_status;
    u16 me_ability, opp_ability, me_item, opp_item;
    u16 me_moves[4], opp_moves[4];
    u16 d_mo[4], d_om[4], f_mo[4], f_om[4];    /* engine simulation and our formula, active pair */
    u8 weather, nbench, nopt, chosen, trapped, doubles, sim_unsure, legal;   /* legal: bit i = move i selectable */
    u8 why, lost;                              /* WHY_*: the pick against the best value; lost: the LOST band applied */
    struct { u8 kind, idx; s16 extra; s32 value; } opt[MAX_OPT];
    u16 strong, sw_species, sw_w, role;
} Debug;
_Static_assert(sizeof(Debug) == 256, "tools/aibench.py DEBUG_SIZE_V4");

__attribute__((section(".bss.debug"))) Debug ai_debug[2];
/* the decisions in progress, by client (st). A context lives in the battle heap from its decision's first poll to the
   poll that writes the action. The table is in ITCM RAM, not the slot's bss: while my side waits for the player's
   action (foe_choice), the player's Bag or party screen loads its own overlay into the slot, and ai_resume brings
   overlay 10 back once the player has chosen, which clears the slot's bss. tag: the battle's (battle_tag), so an entry
   a reset left behind is never taken for a later battle's. c 0: no memory, overlay 11 decides */
static struct { void *st; Ctx *c; u32 tag; } live[MAX_CTX] __attribute__((section(".itcm_bss")));

/* this battle: its main module and the RTC seed of its setup (BattleSetup+0x19C) */
static inline __attribute__((always_inline)) u32 battle_tag(void)
{
    u8 *main = AT(bptr, MAIN_PTR);
    void *setup = OK_PTR(main) ? AT(vptr, (u32)main + MAIN_SETUP) : 0;
    return (u32)main ^ (OK_PTR(setup) ? AT(u32, (u32)setup + 0x19C) : 0);
}

/* Trick Room's turns left, this one included (0: none): within a priority bracket the slower Pokemon moves first.
   In ITCM RAM, so that the replacement after a faint (ai_replace, which runs while the slot holds overlay 8) reads it
   too */
static u8 g_tr_left __attribute__((section(".itcm_bss")));

/* Memory across turns. The slot's bss is cleared every turn (overlay 8 holds the slot during turn playback), so what
   the AI keeps from one decision to the next lives in ITCM RAM (.itcm_bss, beside ai_replace's working state): the
   move each of my Pokemon chose (by pokeID), and the status moves seen failing on a target, vetoed against it until it
   leaves the field. An entry ends when its target is not out at a decision, or has fewer turns out than when the
   failure was seen (it left and came back, or a new battle began: every Pokemon starts a battle at 0 turns, and an
   entry is made at 1 or more) */
#define FAILS 8
typedef struct { u16 move, species; u8 pp, target, turns, live; } Chosen;
typedef struct { u16 move, species, turns, odds; u8 target, live; } Failed;    /* odds: per-mille, all were misses */
static struct { Chosen chosen[24]; Failed fail[FAILS]; } mem __attribute__((section(".itcm_bss")));
/* memory across turns (the overlay and its bss are loaded again every selection phase): per client, my last switch,
   with the pokeID it took out and the foe on the field then; in ITCM RAM (.itcm_bss, apart from the replacement's
   scratch), uninitialized at boot, so an entry counts only with its magic and the same foe one turn later */
#define MEMO_MAGIC 0xA5
#define BACK_COST 100       /* switching straight back: the foe gets a second free turn for nothing */
typedef struct { void *foe; u8 foe_turns, streak, left, magic; } Memo;     /* streak: my voluntary switches in a row */
#define MEMO_MOVE 0x5A     /* A2_LOOP: my last decision was a move; foe holds the foe team's HP then (foe_team_hp) */
#define LOOP_STEP 100       /* A2_LOOP: the margin over staying that each earlier switch of the streak adds */
static Memo memo[4] __attribute__((section(".itcm_bss")));

/* What the foe has done this battle, per side (the trainer's first), at READS_AT (engine.h): the foe on the field at my
   last decision and its PP then; llr, the evidence that the foe plays well (log odds x 100), and s, the strength it gives
   (0-1000; strength); seen, unused; miss, the predictions of the named switch-in (Habit) it did not bring in a row,
   with what my last decision found (READ_*). A new foe party (sig) starts over. pinned 1 (tests only) keeps llr as
   written.
   ITCM RAM past .itcm_bss is never written by the game, but it is not cleared at boot either: magic */
#define READ_MAGIC 0xA5C3
#define READ_PREDICTED 0x40     /* I weighed its switch at READ_W or more */
#define READ_WINS 0x80          /* its Pokemon on the field won the exchange by staying */
#define READ_W 200
/* Evidence in small steps (no single event moves s by more than a third). A switch by choice is judged by what my move
   then did to the newcomer: resisted, blanked or failed, it was a read (LLR_GOOD, even out of an exchange it was
   winning); super effective, or out of an exchange it was winning, a turn thrown away; else a little for it. A status
   move counts against it only when it failed, missed or did nothing (the engine's count of uses that worked is 0, which
   a failed Protect does not reset: its Protect count is then 0; half for a move that can miss); one that worked, a
   little for it, an attack a little against it */
#define LLR0 (-100)
#define LLR_GOOD 100
#define LLR_SWITCH 50
#define LLR_WASTE 50
#define LLR_WORKED 10
#define LLR_FAILED 100
#define LLR_ATTACK 10
#define LLR_MAX 300
typedef struct {
    void *foe;
    u16 magic, sig;
    s16 llr, s;
    u8 pp, pinned, seen, miss;
} Read;
/* beside each Read record (cleared with it): the foe's last switch by choice, by species (my Pokemon on the field, the
   foe's it took out, the one it brought); the switch-in my last prediction named, whose misses in a row are Read.miss */
typedef struct { u16 me, out, in, named; } Habit;
static Habit habit[2] __attribute__((section(".itcm_bss")));

/* ---------------------------------------------------------------- small helpers */

/* freestanding: gcc emits these for struct copies; built so they cannot turn into calls to themselves */
__attribute__((optimize("no-tree-loop-distribute-patterns"))) void *memcpy(void *d, const void *s, unsigned n)
{
    u8 *a = d;
    const u8 *b = s;
    while (n--)
        *a++ = *b++;
    return d;
}

__attribute__((optimize("no-tree-loop-distribute-patterns"))) void *memset(void *d, int v, unsigned n)
{
    u8 *a = d;
    while (n--)
        *a++ = (u8)v;
    return d;
}

static s32 clamp(s32 v, s32 lo, s32 hi) { return v < lo ? lo : v > hi ? hi : v; }

/* residual damage, a fraction of max HP: at least 1, so a 1-HP Shedinja falls to any of it */
__attribute__((noinline)) static s32 tick(s32 maxhp, int n) { return maxhp / n | (maxhp < n); }

static s32 stage_mult(s32 v, int stage)   /* stage 0..12, 6 neutral */
{
    int s = stage - 6;
    if (s > 0)
        return v * (2 + s) / 2;
    if (s < 0)
        return v * 2 / (2 - s);
    return v;
}

static int has_type(const Mon *m, int t) { return m->types[0] == t || m->types[1] == t || m->types[2] == t; }

/* a moves before b in the same priority bracket, from their speeds; turn: race turns after this one (Trick Room
   ends) */
static int faster_at(s32 a, s32 b, int turn) { return g_tr_left > turn ? a < b : a > b; }
static int faster(s32 a, s32 b) { return faster_at(a, b, 0); }

/* the move is aimed at a Pokemon on the other side (one, every foe, every other, a random foe) */
static int at_mon(const MoveInfo *m) { return m->target == 0 || m->target == 3 || m->target == 4 || m->target == 5 || m->target == 9; }

/* a status move aimed at one foe: the kind the memory keeps */
static int aimed(const MoveInfo *m) { return !m->cls && (m->target == 0 || m->target == 3); }

static int grounded(const Mon *m)
{
    return !has_type(m, T_FLYING) && m->ability != AB_LEVITATE && m->item != IT_AIR_BALLOON;
}

static int eff_permille(int mtype, const Mon *d)   /* type effectiveness x1000 */
{
    const u8 *chart = (const u8 *)TYPE_CHART;
    s32 e = 1000;
    int i, j;
    if (mtype >= 18)
        return 1000;
    for (i = 0; i < 3; i++) {
        int t = d->types[i];
        if (t >= 18)
            continue;
        for (j = 0; j < i; j++)
            if (d->types[j] == t)
                break;
        if (j < i)
            continue;
        e = e * chart[mtype * 18 + t] / 4;
    }
    return e;
}

/* a's move on d: Scrappy hits Ghosts with Normal and Fighting moves, an Iron Ball lets Ground hit a Flier */
static s32 eff_move(const Mon *a, const Mon *d, const MoveInfo *m)
{
    const u8 *chart = (const u8 *)TYPE_CHART;
    s32 e = 1000;
    int i, j;
    if (m->type >= 18)
        return 1000;
    for (i = 0; i < 3; i++) {
        int t = d->types[i], f;
        if (t >= 18)
            continue;
        for (j = 0; j < i; j++)
            if (d->types[j] == t)
                break;
        if (j < i)
            continue;
        f = chart[m->type * 18 + t];
        if (!f && ((a->ability == AB_SCRAPPY && t == T_GHOST && (m->type == T_NORMAL || m->type == T_FIGHTING)) ||
                   (d->item == IT_IRON_BALL && t == T_FLYING && m->type == T_GROUND)))
            continue;
        e = e * f / 4;
    }
    return e;
}

static int breaks_mold(const Mon *a)
{
    return a->ability == AB_MOLD_BREAKER || a->ability == AB_TERAVOLT || a->ability == AB_TURBOBLAZE;
}

/* the defender's ability makes this move do nothing (the damage simulation does not see these) */
static int ability_blocks(const Mon *a, const Mon *d, const MoveInfo *m)
{
    int powder = (m->flags >> F_POWDER) & 1;
    if (d->item == IT_AIR_BALLOON && m->type == T_GROUND)    /* an item: Mold Breaker does not get past it */
        return 1;
    if (powder && (has_type(d, T_GRASS) || d->item == IT_SAFETYGOGGLS))     /* Grass seen in logs; the goggles not measured */
        return 1;
    if (breaks_mold(a))
        return 0;
    switch (d->ability) {
    case AB_LEVITATE: case AB_EARTH_EATER:
        return m->type == T_GROUND && d->item != IT_IRON_BALL;
    case AB_FLASH_FIRE: case AB_WELLBAKEDBDY: case AB_BLAZING_AWE:     /* Blazing Awe "draws Fire to up Sp. Atk" (logs) */
        return m->type == T_FIRE;
    case AB_OVERCOAT:
        return powder;
    case AB_QUEENLYMJSTY: case AB_DAZZLING: case AB_ARMOR_TAIL:          /* priority moves at it fail (not measured) */
        return m->prio > 0;
    case AB_GOOD_AS_GOLD:                                               /* status moves at it fail (not measured) */
        return !m->cls && (m->target == 0 || m->target == 3 || m->target == 5);
    case AB_WATER_ABSORB: case AB_STORM_DRAIN: case AB_DRY_SKIN:
        return m->type == T_WATER;
    case AB_VOLT_ABSORB: case AB_LIGHTNINGROD: case AB_MOTOR_DRIVE:
        return m->type == T_ELECTRIC;
    case AB_SAP_SIPPER:
        return m->type == T_GRASS;
    case AB_SOUNDPROOF:
        return (m->flags >> F_SOUND) & 1;
    case AB_BULLETPROOF:
        return IS_BALL_MOVE(m->id);
    case AB_WONDER_GUARD:
        return m->cls != 0 && eff_permille(m->type, d) <= 1000;
    case AB_MAGIC_BOUNCE:
        return m->cls == 0 && m->target != TARGET_USER && ((m->flags >> F_MAGICCOAT) & 1);
    }
    return 0;
}

/* d's ability takes a's move m and gains from it: 1 a quarter of its max HP (Water Absorb, Volt Absorb, Dry Skin, Earth
   Eater; Volt Absorb on Thunder Wave seen in logs), 2 Sp. Atk +1 (Storm Drain, Lightningrod), 3 Attack +1 (Sap Sipper),
   4 Speed +1 (Motor Drive); official, the others not measured */
static const u16 absorb_tab[] = {
    AB_WATER_ABSORB, T_WATER | 1 << 8, AB_DRY_SKIN, T_WATER | 1 << 8, AB_VOLT_ABSORB, T_ELECTRIC | 1 << 8,
    AB_EARTH_EATER, T_GROUND | 1 << 8, AB_STORM_DRAIN, T_WATER | 2 << 8, AB_LIGHTNINGROD, T_ELECTRIC | 2 << 8,
    AB_SAP_SIPPER, T_GRASS | 3 << 8, AB_MOTOR_DRIVE, T_ELECTRIC | 4 << 8,
};
__attribute__((noinline)) static int absorbs(const Mon *d, const Mon *a, const MoveInfo *m)
{
    unsigned k;
    for (k = 0; m->id && !breaks_mold(a) && k < sizeof absorb_tab / sizeof absorb_tab[0]; k += 2)
        if (absorb_tab[k] == d->ability && (absorb_tab[k + 1] & 0xFF) == m->type)
            return absorb_tab[k + 1] >> 8;
    return 0;
}

/* what absorbs() gives y's fighter: the heal, or one stage on its race attack (2 special, 3 physical) or its Speed */
__attribute__((noinline)) static void gain(Fighter *y, int g)
{
    if (g == 1)
        y->hp += y->maxhp / 4;
    else if (g == 4) {
        y->spe = y->spe * 3 / 2;
        y->spe64 = y->spe64 * 3 / 2;
    } else if (g && g == 4 - y->cls) {      /* the stage stays for my next Pokemon (follow_up) */
        y->dmg = y->dmg * 3 / 2;
        y->dmg64 = y->dmg64 * 3 / 2;
    }
    if (y->hp > y->maxhp)
        y->hp = y->maxhp;
}

/* a recovery move on the user (Recover, Roost...; Life Dew, which heals my side) */
static int self_heal(const MoveInfo *m) { return m->quality == Q_RECOVER && m->target >= 6; }

static int self_ko_move(int id)
{
    return id == MV_EXPLOSION || id == MV_SELFDESTRUCT || id == MV_MEMENTO || id == MV_FINAL_GAMBIT ||
           id == MV_HEALING_WISH || id == MV_MISTYEXPLOSN;
}

static int hits_x10(const MoveInfo *m)
{
    if (m->hits_max <= 1)
        return 10;
    if (m->hits_min == m->hits_max)
        return 10 * m->hits_min;
    if (m->hits_min == 2 && m->hits_max == 5)
        return 31;
    return 5 * (m->hits_min + m->hits_max);
}

/* a's move m hits more than once, which goes through Focus Sash and Sturdy: a multi-hit move, or any attack with
   Parental Bond */
static int multi(const Mon *a, const MoveInfo *m) { return m->hits_max > 1 || (a->ability == AB_PARENTAL_BOND && m->cls); }

/* Focus Sash, or Sturdy (Mold Breaker ignores it): a one-hit KO from full HP leaves d at 1 HP */
static int endures(const Mon *d, const Mon *a)
{
    return d->hp == d->maxhp && (d->item == IT_FOCUS_SASH || (d->ability == AB_STURDY && !breaks_mold(a)));
}

/* HP a's Life Orb takes when the move hits: none with Magic Guard, or with Sheer Force on a move it powers up */
static s32 life_orb_recoil(const Mon *a, const MoveInfo *m)
{
    if (a->item != IT_LIFE_ORB || a->ability == AB_MAGIC_GUARD || !m->cls)
        return 0;
    return a->ability == AB_SHEER_FORCE && m->secondary ? 0 : a->maxhp / 10;
}

/* HP a loses touching d: Rough Skin, Iron Barbs and (here) Battle Armor (measured) and Magma Armor (seen in logs) an
   eighth, a Rocky Helmet a sixth, per hit */
static s32 contact_recoil(const Mon *a, const Mon *d, const MoveInfo *m)
{
    s32 v = 0;
    if (!((m->flags >> F_CONTACT) & 1) || !m->cls || a->ability == AB_MAGIC_GUARD)
        return 0;
    if (d->ability == AB_ROUGH_SKIN || d->ability == AB_IRON_BARBS || d->ability == AB_BATTLE_ARMOR || d->ability == AB_MAGMA_ARMOR)
        v += a->maxhp / 8;
    if (d->item == IT_ROCKY_HELMET)
        v += a->maxhp / 6;
    return v * (m->hits_max > 1 ? hits_x10(m) : 10) / 10;
}

static int fixed_damage(const Mon *a, const Mon *d, const MoveInfo *m, s32 *out)
{
    s32 v;
    switch (m->efx == X_FANG ? MV_SUPER_FANG : m->id) {
    case MV_ENDEAVOR: v = d->hp > a->hp ? d->hp - a->hp : 0; break;
    case MV_SUPER_FANG: v = d->hp / 2 > 0 ? d->hp / 2 : 1; break;
    case MV_NIGHT_SHADE: case MV_SEISMIC_TOSS: case MV_PSYWAVE: v = a->level; break;
    case MV_DRAGON_RAGE: v = 40; break;
    case MV_SONICBOOM: v = 20; break;
    case MV_FINAL_GAMBIT: v = a->hp; break;
    default: return 0;
    }
    *out = eff_permille(m->type, d) ? v : 0;
    return 1;
}

/* a burn halves m's damage with its move `slot`: a physical one that is not of fixed damage (Seismic Toss), unless Guts
   or Quick Feet turn the burn into a boost */
static int burn_cuts(const Mon *m, int slot)
{
    const MoveInfo *mv = &m->mv[slot & 3];
    s32 v;
    return slot >= 0 && mv->cls == 1 && !fixed_damage(m, m, mv, &v) && m->ability != AB_GUTS && m->ability != AB_QUICK_FEET;
}

/* the type the owner's ability gives a move: Normalize, the -ate abilities on Normal moves, Liquid Voice on
   sound moves. Engine and simulation use the changed type, so vetoes and immunities must too */
static int ate_type(int ability)
{
    switch (ability) {
    case AB_REFRIGERATE: return T_ICE;
    case AB_PIXILATE: return T_FAIRY;
    case AB_AERILATE: return T_FLYING;
    case AB_GALVANIZE: return T_ELECTRIC;
    case AB_BURNING_SKIN: return T_FIRE;
    case AB_AZURE_SKIN: return T_WATER;
    case AB_GRASS_SKIN: return T_GRASS;
    case AB_DARK_SKIN: return T_DARK;
    case AB_DRAGONIZE: return T_DRAGON;
    }
    return T_NONE;
}

/* The move records one decision (or one ai_replace call) reads, by move: E_WAZA keeps only 4, and the AI reads the moves
   of every Pokemon in the battle, so through E_WAZA alone most reads reloaded a record from the cartridge
   (qa/ai_think_time.md: 61% of a decision). Here each record is read once (copied from E_WAZA's cache when it holds
   it), its params come from the engine's own getter on that copy, and the engine calls that read a move (the damage
   simulation, the selectable check) find it lent to E_WAZA's cache. The records never change, so every value is
   E_WAZA's. g_wz: the cache of the poll running (adv_entry sets it at every poll, ai_replace for its call); 0: none,
   every read goes to E_WAZA. g_narc: the move data file, opened at the poll's first read and closed when it returns, so
   a record costs its own reads only */
#define WZ_MAX 64
typedef struct { u8 n, last; u16 id[WZ_MAX]; u32 rec[WZ_MAX][WAZA_REC / 4]; } MoveCache;
static MoveCache *g_wz __attribute__((section(".itcm_bss")));
static void *g_narc __attribute__((section(".itcm_bss")));

static void waza_close(void)
{
    if (g_narc)
        E_NARC_CLOSE(g_narc);
    g_narc = 0;
}

/* E_WAZA's cache entry that holds the move, or 0 */
__attribute__((noinline)) static u32 waza_entry(int move)
{
    u32 e;
    for (e = WAZA_CACHE; e < WAZA_CACHE + 4 * 0x2C; e += 0x2C)
        if (AT(u16, e) == move)
            return e;
    return 0;
}

/* the move's record in g_wz, read the first time it is asked for; 0 with no cache, or a full one */
static const u32 *waza_rec(int move)
{
    MoveCache *w = g_wz;
    u32 e;
    int i;
    if (!w)
        return 0;
    if (w->n && w->id[w->last] == move)
        return w->rec[w->last];
    for (i = 0; i < w->n; i++)
        if (w->id[i] == move)
            return w->rec[w->last = i];
    if (w->n == WZ_MAX)
        return 0;
    if ((e = waza_entry(move)))
        for (i = 0; i < WAZA_REC / 4; i++)
            w->rec[w->n][i] = AT(u32, e + 4 + 4 * i);
    else if (g_narc || (g_narc = E_NARC_OPEN(WAZA_NARC, HEAP_BATTLE)))
        E_NARC_READ(g_narc, move, w->rec[w->n]);
    else
        return 0;
    w->id[w->n] = move;
    return w->rec[w->last = w->n++];
}

static int waza(int move, int param)
{
    const u32 *r = waza_rec(move);
    return r ? E_WAZA_PARAM(r, param) : E_WAZA(move, param);
}

/* the move's record into E_WAZA's cache, where its own miss would load it, before an engine call that reads the move */
static void waza_lend(int move)
{
    const u32 *r;
    u32 e;
    int i;
    if (waza_entry(move) || !(r = waza_rec(move)))
        return;
    i = (AT(u8, WAZA_LAST) + 1) & 3;
    AT(u8, WAZA_LAST) = i;
    e = WAZA_CACHE + 0x2C * i;
    AT(u16, e) = move;
    for (i = 0; i < WAZA_REC / 4; i++)
        AT(u32, e + 4 + 4 * i) = r[i];
}

static void read_move(MoveInfo *mi, int id, int ability)
{
    int k, j;
    mi->id = id;
    mi->type = waza(id, WP_TYPE);
    mi->quality = waza(id, WP_QUALITY);
    mi->cls = waza(id, WP_CLASS);
    mi->power = waza(id, WP_POWER);
    mi->acc = waza(id, WP_ACC);
    mi->prio = (s8)waza(id, WP_PRIO);
    mi->hits_min = waza(id, 7);
    mi->hits_max = waza(id, 8);
    mi->sick = waza(id, WP_SICK);
    mi->sick_per = waza(id, WP_SICK_PER);
    mi->drain = (s8)waza(id, WP_DRAIN);
    mi->heal = (s8)waza(id, WP_HEAL);
    mi->target = waza(id, WP_TARGET);
    mi->flinch = clamp(waza(id, WP_FLINCH), 0, 100);
    mi->secondary = mi->sick_per > 0 || mi->flinch > 0;
    for (k = 0; k < 3; k++) {     /* a stat change that only may happen (Meteor Mash's 20%) is not counted on */
        int per = waza(id, WP_RANK_PER1 + k);
        mi->rank_type[k] = waza(id, WP_RANK_TYPE1 + k);
        mi->rank_val[k] = per % 100 ? 0 : (s8)waza(id, WP_RANK_VAL1 + k);
        if (per > 0)
            mi->secondary = 1;
    }
    k = waza(id, WP_EFFECT);
    mi->efx = X_NONE;
    for (j = 0; j < (int)(sizeof effect_class / sizeof effect_class[0]); j++)
        if ((effect_class[j] & 0x1FF) == k)
            mi->efx = effect_class[j] >> 9;
    mi->fails = 0;
    mi->flags = 0;
    for (k = 0; k < 9; k++)
        mi->flags |= (u32)(waza(id, WP_FLAG0 + k) & 1) << k;
    mi->flags |= (u32)(waza(id, WP_FLAG0 + F_POWDER) & 1) << F_POWDER;
    mi->ate = 0;
    if (ability == AB_NORMALIZE)
        mi->type = T_NORMAL;
    else if (mi->type == T_NORMAL && ate_type(ability) != T_NONE) {
        mi->type = ate_type(ability);
        mi->ate = 1;
    } else if (ability == AB_LIQUID_VOICE && ((mi->flags >> F_SOUND) & 1))
        mi->type = T_WATER;
    if ((ability == AB_GALE_WINGS && mi->type == T_FLYING) || (ability == AB_PRANKSTER && !mi->cls))    /* Prankster: seen in logs */
        mi->prio++;
}

/* rc31 F2 (qa/aivsai/rc31_F2.md): the classes predicted beyond rc29's, each only after a DS trace showed its draws and
   fscheck found no miss. F2_SHIP holds the shipped ones. The host reads the mask FS2 from the environment for the
   simulator's screens: the bridge fills every cell from the real turn, so a class's mask alone measures its gain.
   F2_SLP: a sleeper's turn (it draws nothing while asleep); F2_SLPN: read_mon's exact turns of sleep left;
   F2_PROT: a Protect moving first (no draw at streak 0, one after); F2_NONE: a first move that draws nothing and
   leaves the second as simulated (fs_quiet); F2_NG: No Guard (no accuracy draw), Battle Armor and Shell Armor (no
   crit draw); F2_CONF: confusion before a move (its countdown, the 33 roll, a self-hit's 16 roll); F2_SELF: a
   damaging move that changes its user's Attack, Sp. Atk or accuracy (one draw, fs_self_ok). Focus Energy
   changes no crit roll in this hack (rc31 trace T5: stage 0 and n 24 after it, bpp+0x2A0 stays 0) */
enum { F2_SLP = 1, F2_PROT = 2, F2_NONE = 4, F2_NG = 8, F2_CONF = 16, F2_SLPN = 32, F2_SELF = 64 };
#define F2_SHIP 63
#ifdef HOST_ENGINE_H
char *getenv(const char *);
long strtol(const char *, char **, int);
static int fs2(int bit)
{
    static int m = -1;
    if (m < 0) {
        const char *e = getenv("FS2");
        m = e ? (int)strtol(e, 0, 0) : F2_SHIP;
    }
    return m & bit;
}
#else
#define fs2(bit) (F2_SHIP & (bit))
#endif

/* rc33 A1 (qa/aivsai/rc33_A1.md): moves of random sets the valuation read wrong (two-turn moves out of reach, Dark Void,
   Future Sight, Protean). AI_A1 is a mask of the A1_* rules; 0 values them as rc32 did. The host reads it from the
   environment (default all) */
#ifdef HOST_ENGINE_H
static int a1_knob(void)
{
    static int m = -1;
    if (m < 0) {
        const char *e = getenv("AI_A1");
        m = e ? (int)strtol(e, 0, 0) : 31;
    }
    return m;
}
#define AI_A1 a1_knob()
#elif !defined(AI_A1)
#define AI_A1 31
#endif
#define A1(bit) (AI_A1 & (bit))
enum { A1_REACH = 1, A1_VOID = 2, A1_DELAY = 4, A1_PROTEAN = 8, A1_LOCK = 16 };

/* rc33 A1b (qa/aivsai/rc33_A1b.md): Imposter, Moody and a Choice-locked Sucker Punch, which random sets carry. AI_A1B
   is a mask of the A1B_* rules; 0 values them as RD and A1 did. The host reads it from the environment (default all) */
#ifdef HOST_ENGINE_H
static int a1b_knob(void)
{
    static int m = -1;
    if (m < 0) {
        const char *e = getenv("AI_A1B");
        m = e ? (int)strtol(e, 0, 0) : 7;
    }
    return m;
}
#define AI_A1B a1b_knob()
#elif !defined(AI_A1B)
#define AI_A1B 7
#endif
#define A1B(bit) (AI_A1B & (bit))
enum { A1B_IMPOSTER = 1, A1B_MOODY = 2, A1B_SUCKER = 4 };
/* rarely run code that stays in main RAM though ai_replace reaches it (build.py resident_sections), so ITCM keeps room */
#define MAIN_TEXT(name) __attribute__((noinline, section(".main.text." #name)))
#define SPECIES_DARKRAI 491       /* the only user Dark Void works for (census s014_g0, s019_g0: "But it failed!") */
#define SEMI_GONE 0x100           /* Shadow Force, Phantom Force: vanished, no move reaches it */

/* rc33 A2 (qa/aivsai/rc33_A2.md): progress rules for random sets, one bit each. A2_LOOP: each voluntary switch in a row
   needs a larger margin over staying; A2_SAC: a switch-in the read hit knocks out never beats staying unless staying
   loses my Pokemon too; A2_SETUP: a boost counts only when it changes the race in front or my Pokemon can knock the foe
   out. 0 is RD's AI; the host reads AI_A2 from the environment (default A2_SHIP) */
enum { A2_LOOP = 1, A2_SAC = 2, A2_SETUP = 4 };
/* shipped: LOOP and SETUP; SAC stays behind its bit, off (rc33 merge, qa/decisions.tsv 2026-10-08T15:46) */
#define A2_SHIP (A2_LOOP | A2_SETUP)
#ifdef HOST_ENGINE_H
static int a2_knob(void)
{
    static int m = -1;
    if (m < 0) {
        const char *e = getenv("AI_A2");
        m = e ? (int)strtol(e, 0, 0) : A2_SHIP;
    }
    return m;
}
#define AI_A2 a2_knob()
#elif !defined(AI_A2)
#define AI_A2 A2_SHIP
#endif

/* rc33 F3 (qa/aivsai/rc33_F3.md): the classes predicted beyond F2, each only after a DS trace (tools/rngtrace.py
   groups T1, T2, F) showed its draws and fscheck found no miss. F3_SHIP holds the shipped ones; the host reads FS3.
   F3_ACC: a first status move whose only draw is accuracy (paralysis, burn, poison, Leech Seed, Taunt; fs_acc_kind);
   F3_LEN: a first sleep or confusion move, Swagger, Flatter or Yawn and their length draws (fs_len_kind); F3_ORD: the
   order draws (speed ties, Quick Claw, Quick Draw; fs_ord_kind) */
enum { F3_ACC = 1, F3_LEN = 2, F3_ORD = 4 };
#define F3_SHIP 7
#ifdef HOST_ENGINE_H
static int fs3(int bit)
{
    static int m = -1;
    if (m < 0) {
        const char *e = getenv("FS3");
        m = e ? (int)strtol(e, 0, 0) : F3_SHIP;
    }
    return m & bit;
}
#else
#define fs3(bit) (F3_SHIP & (bit))
#endif

/* rc33 F3 step 0 (qa/aivsai/rc33_F3.md): host-only oracle bits. The bridge fills every cell from the real turn, so a
   bit of FS3O that lets the AI trust a class's cells measures that class at perfect prediction: the classes not
   predicted yet, FO_FRZ a frozen Pokemon, FO_MULTI multi-hit moves, FO_CHANCE a first move with more than one chance
   roll or a sure effect (step 0 also screened the order, accuracy-only and length classes, now F3_ORD, F3_ACC and
   F3_LEN). The DS has none of it */
enum { FO_FRZ = 1, FO_MULTI = 4, FO_CHANCE = 8 };
#ifdef HOST_ENGINE_H
static int fso(int bit)
{
    static int m = -1;
    if (m < 0) {
        const char *e = getenv("FS3O");
        m = e ? (int)strtol(e, 0, 0) : 0;
    }
    return m & bit;
}
#else
#define fso(bit) 0
#endif

/* rc34 AIFIX (qa/aivsai/rc34_AIFIX.md): two correctness fixes, each a bit of AI_FIX (0 builds the AI as before; the host
   reads AI_FIX from the environment). AIF_READS: foresight does not trust a second move that reads a stat the first
   move changed (fs_reads_first, fs_settle); AIF_RDMEMO: RD's blind decision for a committed switch leaves the memory
   across turns as it found it when the read is then used (rd_gate) */
enum { AIF_READS = 1, AIF_RDMEMO = 2 };
#define AI_FIX_SHIP 3
#ifdef HOST_ENGINE_H
static int aifix(int bit)
{
    static int m = -1;
    if (m < 0) {
        const char *e = getenv("AI_FIX");
        m = e ? (int)strtol(e, 0, 0) : AI_FIX_SHIP;
    }
    return m & bit;
}
#else
#define aifix(bit) (AI_FIX_SHIP & (bit))
#endif

/* Pokemon `id` in the engine's other copy of the battle, the only one that counts the turns of sleep and Perish Song
   (0 when it is not found) */
static void *copy0(int id)
{
    void *pc = E_POKECON(0), *party, *s;
    int i;
    party = OK_PTR(pc) ? E_PARTY(pc, E_CLIENT_OF(id)) : 0;
    for (i = 0; OK_PTR(party) && i < E_PARTY_COUNT(party) && i < 6; i++) {
        s = E_PARTY_MEMBER(party, i);
        if (OK_PTR(s) && B_ID(s) == id)
            return s;
    }
    return 0;
}

/* the turns sleeping Pokemon `id` slept through so far, as the player can count them */
static int sleep_count(int id)
{
    void *s = copy0(id);
    return !s ? 0 : B_COND_COUNT(s, S_SLP) > 3 ? 3 : B_COND_COUNT(s, S_SLP);
}

static int read_mon(Mon *m, void *b, int party)
{
    int i;
    if (!OK_PTR(b))
        return 0;
    m->bpp = b;
    m->party = party;
    m->id = B_ID(b);
    m->species = B_SPECIES(b);
    m->ability = B_ABILITY(b);
    m->item = B_ITEM(b);
    m->hp = B_HP(b);
    m->maxhp = B_MAXHP(b);
    m->level = B_LEVEL(b);
    m->fresh = !(B_TURNFLAGS(b) & 1);
    m->turns = B_TURNS_OUT(b) > 255 ? 255 : B_TURNS_OUT(b);
    m->shield = 0;
    if (m->maxhp == 0 || m->hp > m->maxhp || m->level == 0 || m->level > 100 || m->species == 0 || m->species > 1500 ||
        m->id >= 24)
        return 0;
    m->protects = B_PROTECTS(b);
    m->semi = B_SEMI(b);
    m->charging = B_COND_ON(b, C_CHARGE) ? (B_COND(b, C_CHARGE) >> 9) & 0xFFFF : 0;
    m->subbed = 0;
    i = E_CLIENT_OF(m->id) & 1;
    m->tailwind = SIDE_LAYERS(i, SE_TAILWIND) ? clamp(SIDE_LEFT(i, SE_TAILWIND), 1, 8) : 0;
    for (i = 0; i < 5; i++)
        m->stat[i] = B_STAT(b, i) ? B_STAT(b, i) : 1;
    for (i = 0; i < 7; i++)
        m->stage[i] = clamp(B_STAGE(b, i), 0, 12);
    for (i = 0; i < 3; i++)
        m->types[i] = B_TYPE(b, i) <= T_NONE ? B_TYPE(b, i) : T_NONE;
    m->status = m->hp ? clamp(E_POKESICK(b), 0, 5) : 0;
    /* the turns it still sleeps through: sleep skips 1-3 turns (the length is 2-4, the turns skipped one fewer;
       measured), two on average, less the turns it slept (sleep_cases weighs the other cases) */
    m->slept = m->status == S_SLP ? sleep_count(m->id) : 0;
    m->sleep = m->status == S_SLP ? (m->slept >= 2 ? 0 : 2 - m->slept) : m->status == S_FRZ ? 2 : 0;
    if (m->status == S_SLP && fs2(F2_SLPN)) {      /* F2_SLPN: the exact attempts it still sleeps through (fs_dozes) */
        void *s = copy0(m->id);
        int k = m->ability == AB_EARLY_BIRD ? 2 : 1;
        if (s)
            m->sleep = clamp(((int)((B_COND(s, S_SLP) >> 3) & 63) - B_COND_COUNT(s, S_SLP) + k - 1) / k - 1, 0, 63);
    }
    m->drowsy = !m->status && B_COND_ON(b, C_YAWN);
    m->alive = m->hp > 0 && E_FIGHTABLE(b);
    m->nmoves = B_NMOVES(b) <= 4 ? B_NMOVES(b) : 4;
    for (i = 0; i < 4; i++) {
        int id = i < m->nmoves ? B_MOVE(b, i) : 0;
        if (id >= 1000)
            id = 0;
        m->pp[i] = id ? B_PP(b, i) : 0;
        m->legal[i] = id && m->pp[i];
        if (id) {
            MoveInfo *mi = &m->mv[i];
            read_move(mi, id, m->ability);
            /* crit stage 3 always crits here (Night Slash 13 of 13 with Super Luck and Scope Lens, seen in logs) */
            if (mi->cls && waza(id, WP_CRIT) + (m->ability == AB_SUPER_LUCK) + (m->item == IT_SCOPE_LENS || m->item == IT_RAZOR_CLAW) >= 3)
                mi->flags |= 1u << F_CRIT;
            if (!mi->flinch && mi->cls && (m->item == IT_KINGS_ROCK || m->item == IT_RAZOR_FANG))
                mi->flinch = 10;
            if (m->ability == AB_SHEER_FORCE && mi->secondary)
                mi->flinch = 0;
            if (m->ability == AB_SERENE_GRACE)
                mi->flinch = mi->flinch > 50 ? 100 : 2 * mi->flinch;
            if (m->ability == AB_SKILL_LINK)
                mi->hits_min = mi->hits_max;
            if (mi->efx == X_SMASH) {         /* no stages in its data: +2 Attack, Sp. Atk, Speed, -1 Defense, Sp. Def (logs) */
                mi->quality = Q_EFFECT;
                mi->rank_type[0] = 1;
                mi->rank_type[1] = 3;
                mi->rank_type[2] = 5;
                mi->rank_val[0] = mi->rank_val[1] = mi->rank_val[2] = 2;
            }
            if (id == MV_BELLY_DRUM) {        /* no stages in its data either: Attack to +6 (official) */
                mi->quality = Q_EFFECT;
                mi->rank_type[0] = 1;
                mi->rank_val[0] = 6;
            }
            if (id == MV_CURSE && !has_type(m, T_GHOST)) {    /* its data has no stages: +1 Attack, +1 Defense, -1 Speed (logs) */
                mi->target = TARGET_USER;
                mi->quality = Q_EFFECT;
                mi->rank_type[0] = 1;
                mi->rank_type[1] = 2;
                mi->rank_type[2] = 5;
                mi->rank_val[0] = mi->rank_val[1] = 1;
                mi->rank_val[2] = -1;
            }
        } else
            memset(&m->mv[i], 0, sizeof m->mv[i]);
    }
    return 1;
}

/* a foe holding a Choice item that has used a move since it came in can use only that move (its last one) */
static void lock_foe(Mon *d)
{
    int k, j = -1;
    if (d->fresh || (d->item != IT_CHOICE_BAND && d->item != IT_CHOICE_SPECS && d->item != IT_CHOICE_SCARF))
        return;
    for (k = 0; k < 4; k++)
        if (d->legal[k] && d->mv[k].id == B_LAST_MOVE(d->bpp))     /* out of PP it Struggles: keep its moves */
            j = k;
    for (k = 0; k < 4 && j >= 0; k++)
        if (k != j)
            d->legal[k] = 0;
}

/* A1: a two-turn move another move called (Copycat called Fly in census s033_g0 turns 5-6; it landed next turn) lands
   although the foe does not know it: it takes the slot of the move that called it (its last move, else the first), so
   the reply and a switch-in's entry hit see it */
__attribute__((noinline)) static void called_charge(Mon *d)
{
    int k, j = 0;
    for (k = 0; k < 4; k++) {
        if (d->mv[k].id == d->charging)
            return;
        if (d->mv[k].id && d->mv[k].id == B_LAST_MOVE(d->bpp))
            j = k;
    }
    read_move(&d->mv[j], d->charging, d->ability);
    d->legal[j] = 1;
    d->pp[j] |= !d->pp[j];
}

/* A1B_IMPOSTER: the Pokemon a benched Imposter turns into as it comes in, the one on the field facing it (mine copies
   the foe, the foe's copies my Pokemon); 0 when there is none, or a substitute or a transformed Imposter stops it */
MAIN_TEXT(imposter_target) static const Mon *imposter_target(const Ctx *c, const Mon *m)
{
    const Mon *t;
    if (!A1B(A1B_IMPOSTER) || m->ability != AB_IMPOSTER || !m->party)
        return 0;
    t = (E_CLIENT_OF(m->id) & 1) == (c->client & 1) ? &c->opp : &c->me;
    return t->bpp && !t->party && t->hp > 0 && !t->subbed && t->ability != AB_IMPOSTER ? t : 0;
}

/* Imposter on the DS (rc33_A1b.md, measured): the copy takes the stats, types and moves (5 PP each) of the Pokemon it
   faces and keeps its own HP, item, level, species and ability field. Stages are copied as Transform copies them */
MAIN_TEXT(imposter_copy) static void imposter_copy(const Ctx *c, Mon *m)
{
    const Mon *t = imposter_target(c, m);
    int i;
    if (!t)
        return;
    memcpy(m->types, t->types, sizeof m->types);
    memcpy(m->stat, t->stat, sizeof m->stat);
    memcpy(m->stage, t->stage, sizeof m->stage);
    memcpy(m->mv, t->mv, sizeof m->mv);
    m->nmoves = t->nmoves;
    for (i = 0; i < 4; i++)
        m->legal[i] = m->pp[i] = t->mv[i].id ? 5 : 0;
}

/* the pokeID the engine simulation stands in for m with: a copy is the Pokemon it copied (the simulation of a Pokemon
   on itself gives what it gives on its copy, measured); -1, the formula stands in, for a copy whose model went stale
   (a read switch replaced the Pokemon it copied) */
MAIN_TEXT(sim_id) static int sim_id(const Ctx *c, const Mon *m)
{
    const Mon *t = imposter_target(c, m);
    int i, same = t != 0;
    if (!A1B(A1B_IMPOSTER) || m->ability != AB_IMPOSTER || !m->party)
        return m->id;
    for (i = 0; same && i < 5; i++)
        same = m->stat[i] == t->stat[i] && (i == 4 || m->mv[i].id == t->mv[i].id);
    if (same)
        return t->id;
    return m->stat[0] == B_STAT(m->bpp, 0) && m->stat[4] == B_STAT(m->bpp, 4) ? m->id : -1;
}

/* Weather Ball: a 100-power move of the weather's type in rain, sun, sand or snow, and a Fire one for Mega Sol, whose
   holder's moves act as in sun (measured in the simulation; a Normal Weather Ball let it eat an Occa Berry on the field);
   harsh sun (heavy rain) makes Water (Fire) attacks fail. raw: the weather byte as the engine has it */
static void weather_moves(Mon *m, int weather, int raw)
{
    int i;
    if (m->ability == AB_MEGA_SOL)
        weather = W_SUN;
    for (i = 0; i < 4; i++) {
        MoveInfo *mi = &m->mv[i];
        if (mi->id == MV_WEATHER_BALL && weather && m->ability != AB_NORMALIZE) {
            mi->type = weather == W_RAIN ? T_WATER : weather == W_SUN ? T_FIRE : weather == W_SAND ? T_ROCK : T_ICE;
            mi->power = 100;
            mi->ate = 0;
        }
        mi->fails = mi->cls && ((raw == WX_HARSH_SUN && mi->type == T_WATER) || (raw == WX_HEAVY_RAIN && mi->type == T_FIRE));
    }
}

/* the moves that reach a Pokemon out of reach in the air, underground or under water (official; the states measured,
   these moves not) */
static int reaches(const MoveInfo *m, int semi)
{
    int id = m->id;
    if (semi & SEMI_FLY)
        return id == MV_THUNDER || id == MV_HURRICANE || id == MV_GUST || id == MV_TWISTER || id == MV_SKY_UPPERCUT || id == MV_SMACK_DOWN;
    if (semi & SEMI_DIG)
        return id == MV_EARTHQUAKE || id == MV_MAGNITUDE || id == MV_FISSURE;
    if (semi & SEMI_DIVE)
        return id == MV_SURF || id == MV_WHIRLPOOL;
    return 0;
}

static s32 eff_speed(const Mon *m, int weather);

/* hit chance in percent: never-miss moves (accuracy over 100) and No Guard always hit; weather; the user's accuracy
   stage against the target's evasion stage, 3/(3+n) or (3+n)/3 (measured: +2 61%, +4 36%, +6 31%), which Unaware looks
   past; Compound Eyes x1.3; Hustle x0.8 on physical moves; the target's BrightPowder x0.9 (measured) */
static int move_acc(const Mon *a, const Mon *d, const MoveInfo *m, int weather)
{
    int acc = m->acc, n;
    if (a->ability == AB_NO_GUARD || d->ability == AB_NO_GUARD)
        return 100;
    if (!A1(A1_REACH) && d->semi && at_mon(m) && !reaches(m, d->semi))
        return 0;
    if (acc > 100)
        return 100;
    if ((m->id == MV_THUNDER || m->id == MV_HURRICANE) && weather == W_RAIN)
        return 100;
    if ((m->id == MV_THUNDER || m->id == MV_HURRICANE) && weather == W_SUN)
        acc = 50;
    if (m->id == MV_BLIZZARD && weather == W_HAIL)
        return 100;
    n = clamp((d->ability == AB_UNAWARE ? 6 : a->stage[5]) - (a->ability == AB_UNAWARE ? 6 : d->stage[6]), -6, 6);
    acc = n >= 0 ? acc * (3 + n) / 3 : acc * 3 / (3 - n);
    if (a->ability == AB_COMPOUND_EYES)
        acc = acc * 13 / 10;
    if (a->ability == AB_HUSTLE && m->cls == 1)
        acc = acc * 8 / 10;
    if (d->item == IT_BRIGHTPOWDER)
        acc = acc * 9 / 10;
    if (a->item == IT_WIDE_LENS)       /* x1.1, and Zoom Lens x1.2 moving last (official; not measured here) */
        acc = acc * 11 / 10;
    if (a->item == IT_ZOOM_LENS && faster(eff_speed(d, weather), eff_speed(a, weather)))
        acc = acc * 6 / 5;
    return acc > 100 ? 100 : acc;
}

/* move_acc this turn, d out of reach as it is now (A1: move_acc is the accuracy of the race's turns, when d lands) */
static int acc_now(const Mon *a, const Mon *d, const MoveInfo *m, int weather)
{
    if (d->semi && at_mon(m) && !reaches(m, d->semi) && a->ability != AB_NO_GUARD && d->ability != AB_NO_GUARD)
        return 0;
    return move_acc(a, d, m, weather);
}

/* our Gen 5 formula: the stand-in where the engine simulation is not used (sim_fix, a resist berry's hit) */
static s32 formula_damage(const Mon *a, const Mon *d, const MoveInfo *m, int weather)
{
    s32 at, df, base, v;
    int e;
    if (m->cls == 0 || m->power == 0)
        return 0;
    if (m->cls == 1) {
        at = stage_mult(a->stat[0], a->stage[0]);
        df = stage_mult(d->stat[1], d->stage[1]);
    } else {
        at = stage_mult(a->stat[2], a->stage[2]);
        df = stage_mult(d->stat[3], d->stage[3]);
    }
    if (df <= 0)
        df = 1;
    base = (2 * a->level / 5 + 2) * m->power * at / df / 50 + 2;
    if (m->ate)
        base = base * 6 / 5;
    if (weather == W_RAIN)
        base = m->type == T_WATER ? base * 3 / 2 : m->type == T_FIRE ? base / 2 : base;
    else if (weather == W_SUN)
        base = m->type == T_FIRE ? base * 3 / 2 : m->type == T_WATER ? base / 2 : base;
    v = base;
    if (has_type(a, m->type))
        v = v * 3 / 2;
    e = eff_move(a, d, m);
    v = v * e / 1000;
    if (a->status == S_BRN && m->cls == 1)
        v /= 2;
    return e && v < 1 ? 1 : v;
}

/* raw max-roll damage of one hit, after the vetoes the simulation does not know */
static s32 move_damage(const Mon *a, const Mon *d, const MoveInfo *m, s32 sim)
{
    s32 v;
    if (!m->id || m->fails || ability_blocks(a, d, m) || (m->prio > 0 && (d->shield & SHIELD_PRIO)) ||
        (m->id == MV_POLTERGEIST && !d->item) || (m->id == MV_DREAM_EATER && d->status != S_SLP))
        return 0;
    if (fixed_damage(a, d, m, &v))
        return v;
    if (m->cls == 0)
        return 0;
    /* the simulation gives 1, not 0, against a type immunity */
    if (eff_move(a, d, m) == 0)
        return 0;
    /* a sure critical hit, x1.5 (seen in logs; Shell Armor stops it, official) */
    return (m->flags >> F_CRIT) & 1 && d->ability != AB_SHELL_ARMOR ? sim * 3 / 2 : sim;
}

/* expected damage per use at a roll (per-mille of the max roll), hit chance, hit count */
static s32 expected_at(const Mon *a, const Mon *d, s32 raw, const MoveInfo *m, int weather, int roll)
{
    return raw * roll / 1000 * move_acc(a, d, m, weather) / 100 * hits_x10(m) / 10;
}

static s32 expected(const Mon *a, const Mon *d, s32 raw, const MoveInfo *m, int weather)
{
    return expected_at(a, d, raw, m, weather, 925);
}

static int charges(const Mon *a, const MoveInfo *m, int weather)
{
    if ((m->id == MV_SOLARBEAM || m->id == MV_SOLAR_BLADE) && (weather == W_SUN || a->ability == AB_MEGA_SOL))
        return 0;
    if (a->item == IT_POWER_HERB)       /* fires at once, the herb used up */
        return 0;
    return (m->flags >> F_CHARGE) & 1;
}

/* A1: Future Sight and Doom Desire hit two turns later, and fail while one is on its way (census s049_g1: used turn 24,
   "But it failed!" turn 25, the hit at turn 26's end) */
static int delayed(const MoveInfo *m)
{
    return A1(A1_DELAY) && (m->id == MV_FUTURE_SIGHT || m->id == MV_DOOM_DESIRE);
}

/* A1: where the charge turn of a's move m takes a, by its effect code (0: it stays in reach). Measured in the census:
   Dig and Shadow Force (s045_g0 turns 10-15, s042_g1 turns 8-10): the user vanishes, the foe's move after it misses,
   and it lands at its own turn order next turn; the other effects as the official games */
static int vanishes(const Mon *a, const MoveInfo *m, int weather)
{
    if (!charges(a, m, weather))
        return 0;
    switch (waza(m->id, WP_EFFECT)) {
    case 155: case 311: return SEMI_FLY;     /* Fly, Sky Drop */
    case 256: return SEMI_DIG;
    case 255: return SEMI_DIVE;
    case 272: return SEMI_GONE;              /* Shadow Force, Phantom Force */
    }
    return 0;
}

/* A1: my move m finds d out of reach this turn: d is up, under or gone now and I move first (it lands at its turn), or
   its reply rm (the foe's move valued) is a charge turn that takes it there before my move */
static int unreachable(const Ctx *c, const MoveInfo *m, const MoveInfo *rm, int me_first)
{
    const Mon *a = &c->me, *d = &c->opp;
    int semi = me_first ? d->semi : rm && rm->id != d->charging ? vanishes(d, rm, c->weather) : 0;
    return A1(A1_REACH) && semi && at_mon(m) && !reaches(m, semi) && a->ability != AB_NO_GUARD && d->ability != AB_NO_GUARD;
}

/* the team scale: what a Pokemon is worth to its side, x1000 at full HP; at 1 HP it still counts (it can
   take a hit for a free switch, or chip). In a decision that floor, g_wb, rises from WORTH_BASE to WORTH_STRONG as the
   foe's play shows strength (Ctx.strong): against a strong player a Pokemon kept alive at low HP still counts for
   more. set_worth runs at every poll, as the two sides' polls interleave in self-play. ai_replace keeps WORTH_BASE
   (with the blend there it gained nothing in the simulator). In ITCM RAM, which ai_replace reaches */
static s16 g_wb __attribute__((section(".itcm_bss")));
static void set_worth(int strong)
{
    g_wb = WORTH_BASE + (WORTH_STRONG - WORTH_BASE) * strong / 1000;
}
static s32 worth(s32 hp, s32 maxhp)
{
    return hp <= 0 ? 0 : g_wb + (1000 - g_wb) * hp / maxhp;
}

/* a healer heals when attacking (and paying its recoil) would leave it to be knocked out by the next hit,
   and the heal outpaces that hit (stalling) */
static int heals(const Fighter *x, const Fighter *y)
{
    return !x->sleep && !x->recharge && x->heal > y->dmg && x->hp - (x->recoil > 0 ? x->recoil : 0) <= y->dmg;
}

/* x uses its priority attack this turn: it knocks y out (Gale Wings, Sucker Punch, Aqua Jet...) */
static int finisher(const Fighter *x, const Fighter *y)
{
    return x->pdmg >= y->hp && x->pprio > x->prio && !x->sleep && !x->recharge;
}

/* turn order, `turn` turns after this one: a healing turn moves at its recovery move's priority (Prankster adds one),
   a finishing one at its priority attack's */
static int first(const Fighter *a, const Fighter *b, int turn)
{
    int pa = finisher(a, b) ? a->pprio : heals(a, b) ? a->heal_prio : a->prio;
    int pb = finisher(b, a) ? b->pprio : heals(b, a) ? b->heal_prio : b->prio;
    return pa > pb || (pa == pb && faster_at(a->spe, b->spe, turn));
}

/* a Sitrus Berry heals its holder once, as soon as anything leaves it at half HP or below */
static void ripe(Fighter *f)
{
    if (f->berry && f->hp > 0 && 2 * f->hp <= f->maxhp) {
        f->hp += f->berry;
        f->berry = 0;
    }
}

/* x takes a hit: from full HP, Focus Sash or Sturdy leaves 1 HP unless the attack hits several times */
static void take(Fighter *x, s32 dmg, int multi)
{
    if (x->endure && x->hp == x->maxhp && dmg >= x->hp && !multi) {
        x->hp = 1;
        x->endure = 0;      /* the Sash is spent; a 1-HP Shedinja is at full HP again and must not endure forever */
    } else
        x->hp -= dmg;
    ripe(x);
}

/* keep: percent of the strike that happens on average (the rest of the time x flinched); asleep: y sleeps through
   this turn, so x's Dream Eater lands */
static void strike(Fighter *x, Fighter *y, int keep, int asleep)
{
    s32 dmg, before, dealt;
    int fin;
    if (x->hp <= 0)
        return;
    if (x->sleep) {
        x->sleep--;
        if (!x->talk)
            return;
        keep = keep * 2 / 3;      /* Sleep Talk calls one of its moves at random */
    }
    if (x->recharge) {
        x->recharge = 0;
        return;
    }
    if (x->para > 1 && x->para++ == 2)      /* fully paralyzed: this action, then every fourth */
        return;
    if (x->para > 5)
        x->para = 2;
    fin = finisher(x, y);
    if (!fin && heals(x, y)) {
        x->hp = x->hp + x->heal * keep / 100 > x->maxhp ? x->maxhp : x->hp + x->heal * keep / 100;
        x->healed++;
        return;
    }
    dmg = (fin ? x->pdmg : asleep && x->dream > x->dmg ? x->dream : x->fang ? (y->hp * x->fang / 100 ? y->hp * x->fang / 100 : 1) : x->dmg) *
          keep / 100;
    before = y->hp;
    take(y, dmg, x->multi);
    x->hp -= x->recoil * keep / 100;
    dealt = before - (y->hp > 0 ? y->hp : 0);
    if (!fin && dealt < dmg)        /* recoil and drain follow the damage dealt, not an overkill */
        x->hp += (dealt - dmg) * x->drain / 100;
    if (x->hp > x->maxhp)
        x->hp = x->maxhp;
    ripe(x);
}

/* the foe's turn: a foe whose hit my recovery outpaces, and does not knock me out, uses its boost move instead (a strong
   player breaks a heal loop that way, and the original AI boosts often) */
static void foe_turn(Fighter *b, Fighter *a, int keep, int asleep)
{
    if ((b->boost & 3) == 2 * b->cls - 1 && !b->sleep && !b->recharge && !(b->grow & MIRROR) && a->heal > b->dmg &&
        b->dmg < a->hp && b->dmg64 < 256) {
        b->dmg = b->dmg * (2 + (b->boost >> 2)) / 2;
        b->dmg64 = b->dmg64 * (2 + (b->boost >> 2)) / 2;
        return;
    }
    strike(b, a, keep, asleep);
}

static void end_of_turn(Fighter *f)
{
    int k = f->orb & 3;
    if (f->hp <= 0)
        return;
    if (f->drowsy && !--f->drowsy && !f->sleep)
        f->sleep = 2;
    if (f->orb > 1 && !f->sleep) {      /* its orb goes off: burned (badly poisoned) from now, which no sleep move gets past */
        f->dmg = f->dmg * (f->orb >> 2) >> 1;
        f->dmg64 = f->dmg64 * (f->orb >> 2) >> 1;
        if (k != 1)
            f->chip += k ? (k == 2 ? -f->maxhp >> 3 : 0) : f->maxhp >> 4;
        f->tox = k == 1;
        f->orb = 1;
    }
    if (f->tw && !--f->tw) {        /* its side's Tailwind ends: every turn that passes, stalled or not, counts */
        f->spe /= 2;
        f->spe64 /= 2;
    }
    f->hp -= f->chip;
    if (f->tox)
        f->hp -= tick(f->maxhp * f->tox++, 16);
    if (f->hp > f->maxhp)
        f->hp = f->maxhp;
    ripe(f);
}

/* Moody at the end of race turn t (A1B_MOODY): +2 to one of Attack, Defense, Sp. Atk, Sp. Def, Speed and -1 to another
   (193 of 193 in the A0 census logs; never accuracy or evasion). x's attack grows by that turn's expected multiplier
   from neutral stages (per mille), up to +6; y's attack on x loses 2% a turn from the second (the Defense drift) */
static const u16 moody_gain[10] = { 1136, 1112, 1094, 1082, 1069, 1060, 1054, 1047, 1043, 1038 };
MAIN_TEXT(moody_turn) static void moody_turn(Fighter *x, Fighter *y, int t)
{
    if (!x->moody || x->hp <= 0)
        return;
    if (x->dmg64 < 256) {
        int g = t < 10 ? moody_gain[t] : 1035;
        x->dmg = x->dmg * g / 1000;
        x->dmg64 = x->dmg64 * g / 1000;
    }
    if (t)
        y->dmg = y->dmg * 49 / 50;
}

/* both use their best move each turn from here on, until one faints or RACE_TURNS pass; returns the turns.
   flinching: the slower side's strikes land at the faster side's flinch odds (on average); *chances: turns
   the faster side could make it flinch */
static int race_core(Fighter *a, Fighter *b, int flinching, int *chances)
{
    int t, ka;
    s32 fo = a->fo;
    a->fo = 0;
    if (b->grow & MIRROR)         /* it only returns hits, and mine holds its attack until one knocks it out */
        b->dmg = b->pdmg = 0;
    if (a->sleep || b->sleep || b->recharge || (first(a, b, 1) && (a->dmg >= b->hp || finisher(a, b))))
        fo = 0;                   /* a free turn already, or a KO this turn */
    *chances = 0;
    for (t = 0; t < RACE_TURNS && a->hp > 0 && b->hp > 0; t++) {
        int as = a->sleep > 0, bs = b->sleep > 0;
        ka = !(b->grow & MIRROR) || a->dmg >= b->hp || finisher(a, b) ? 100 : 0;
        if (!ka && !a->sleep) {
            if ((a->grow & 7) && a->dmg64 < 256) {     /* it boosts instead, up to +6, until one hit knocks the foe out */
                a->dmg = a->dmg * (a->dmg64 + 32 * (a->grow & 7)) / a->dmg64;
                a->dmg64 += 32 * (a->grow & 7);
            } else if (b->chip <= 0 && !b->tox && a->chip <= 0 && !a->tox)   /* a standoff nothing wears down */
                break;
        }
        if (fo) {                 /* my newcomer's Fake Out: the foe flinches */
            take(b, fo, 0);
            fo = 0;
        } else if (first(a, b, t + 1)) {
            strike(a, b, ka, bs);
            if (b->hp > 0) {
                *chances += a->flinch > 0;
                foe_turn(b, a, flinching ? 100 - a->flinch : 100, as);
            }
        } else {
            foe_turn(b, a, 100, as);
            if (a->hp > 0) {
                *chances += b->flinch > 0;
                strike(a, b, ka && flinching ? 100 - b->flinch : ka, bs);
            }
        }
        end_of_turn(a);
        end_of_turn(b);
        if (a->moody | b->moody) {
            moody_turn(a, b, t);
            moody_turn(b, a, t);
        }
    }
    return t;
}

static s32 eff_speed(const Mon *m, int weather)
{
    s32 s = stage_mult(m->stat[4], m->stage[4]);
    if (m->item == IT_LAGGING_TAIL || m->item == IT_FULL_INCENSE)   /* moves last in its bracket (Trick Room or not: official) */
        return g_tr_left ? 0xFFFF : 0;
    if (m->item == IT_CHOICE_SCARF)
        s = s * 3 / 2;
    if (m->item == IT_MACHO_BRACE || m->item == IT_IRON_BALL || (m->item >= IT_POWER_BRACER && m->item <= IT_POWER_WEIGHT))
        s /= 2;
    if (m->status && m->ability == AB_QUICK_FEET)
        s = s * 3 / 2;
    if ((m->ability == AB_SWIFT_SWIM && weather == W_RAIN) || (m->ability == AB_CHLOROPHYLL && weather == W_SUN) ||
        (m->ability == AB_SAND_RUSH && weather == W_SAND) || (m->ability == AB_SLUSH_RUSH && weather == W_HAIL) ||
        (m->ability == AB_UNBURDEN && !m->item))      /* its item gone (seen in logs; one that never held one is rare) */
        s *= 2;
    if (m->tailwind)
        s *= 2;
    return m->status == S_PAR && m->ability != AB_QUICK_FEET ? s / 2 : s;   /* last; Quick Feet lifts it (rc27 engine fix) */
}

/* HP poison takes at a turn's end: an eighth; bad poison the average of its next three turns. Poison Heal heals an
   eighth instead, whatever the poison (seen in logs) */
static s32 poison_chip(const Mon *m)
{
    if (m->status != S_PSN || m->ability == AB_MAGIC_GUARD)
        return 0;
    if (m->ability == AB_POISON_HEAL)
        return -m->maxhp / 8;
    return B_POISON_WORD(m->bpp) >> 3 ? tick(m->maxhp, 16) * (B_TOXIC_TURNS(m->bpp) + 2) : tick(m->maxhp, 8);
}

static int cond_on(const Mon *m, int i) { return OK_PTR(m->bpp) && B_COND_ON(m->bpp, i); }

static s32 chip_of(const Mon *m, int weather)
{
    s32 c = 0;
    if (weather == W_SAND && !has_type(m, T_ROCK) && !has_type(m, T_GROUND) && !has_type(m, T_STEEL) &&
        m->ability != AB_SAND_VEIL && m->ability != AB_SAND_RUSH && m->ability != AB_SAND_FORCE &&
        m->ability != AB_OVERCOAT && m->ability != AB_MAGIC_GUARD)
        c += tick(m->maxhp, 16);
    if (weather == W_HAIL && m->ability == AB_ICE_BODY)
        c -= m->maxhp / 16;
    if (m->status == S_BRN && m->ability != AB_MAGIC_GUARD)
        c += tick(m->maxhp, 16);
    if (m->ability == AB_DRY_SKIN && (weather == W_RAIN || weather == W_SUN))     /* sun: seen in logs; rain: official */
        c += weather == W_SUN ? m->maxhp / 8 : -m->maxhp / 8;
    c += poison_chip(m);
    if (m->item == IT_LEFTOVERS || (m->item == IT_BLACK_SLUDGE && has_type(m, T_POISON)))
        c -= m->maxhp / 16;
    if (m->ability == AB_DAMP || m->ability == AB_THERMALEXCHG || cond_on(m, C_AQUA_RING))   /* a water veil (Damp measured) */
        c -= m->maxhp / 16;
    if (cond_on(m, C_INGRAIN))
        c -= m->maxhp / 16;
    if (cond_on(m, C_LEECH_SEED) && m->ability != AB_MAGIC_GUARD)     /* the foe's side drains it (pair_fighters, entries) */
        c += tick(m->maxhp, 8);
    if (m->shield & SHIELD_HEAL)
        c -= m->maxhp / 16;
    {
        void *s = copy0(m->id);
        if (s && B_COND_ON(s, C_PERISH) && B_COND_COUNT(s, C_PERISH) >= PERISH_LAST)     /* its perish count ends this turn */
            c += m->maxhp;
    }
    return c;
}

/* Fishious Rend and Bolt Beak double only against a target that has not moved yet; the simulation runs
   before anyone moves and always doubles them */
static int doubles_first(const MoveInfo *m) { return m->id == MV_FISHIOUS_REND || m->id == MV_BOLT_BEAK; }

/* Avalanche and Revenge double after a hit from the target this turn; the simulation runs before anyone moves */
static int doubles_last(const MoveInfo *m) { return m->id == MV_AVALANCHE || m->id == MV_REVENGE; }

static s32 order_fix(const Mon *a, const Mon *d, const MoveInfo *m, s32 raw, int weather)
{
    int slower = m->prio <= 0 && !faster(eff_speed(a, weather), eff_speed(d, weather));
    if (doubles_first(m) && slower)
        return raw / 2;
    if (doubles_last(m) && slower)
        return raw * 2;
    return raw;
}

/* what mv returns of a hit of class cls, x10: Counter twice a physical hit, Mirror Coat twice a special one, Metal
   Burst 1.5 times either */
static int returns10(const MoveInfo *mv, int cls)
{
    if (!cls)
        return 0;
    if (mv->id == MV_METAL_BURST)
        return 15;
    return (mv->id == MV_COUNTER && cls == 1) || (mv->id == MV_MIRROR_COAT && cls == 2) ? 20 : 0;
}

/* what d's move k returns of a's hits of class cls, x10, when it can. Metal Burst has no negative priority: it
   works only from the slower side */
static int answer10(const Mon *d, const Mon *a, int k, int cls)
{
    const MoveInfo *mv = &d->mv[k];
    int r = d->legal[k] ? returns10(mv, cls) : 0;
    if (!r || !eff_move(d, a, mv) || (mv->prio >= 0 && !faster(eff_speed(a, W_NONE), eff_speed(d, W_NONE))))
        return 0;
    return r;
}

/* the slot of d's move that answers a's hits of class cls, or -1 */
static int counter_slot(const Mon *d, const Mon *a, int cls)
{
    int k;
    for (k = 0; k < 4; k++)
        if (answer10(d, a, k, cls))
            return k;
    return -1;
}

/* expected damage per turn of a's move m on d from its raw damage; a charge or recharge turn halves it */
static s32 move_rate(const Mon *a, const Mon *d, const MoveInfo *m, s32 raw, int weather, int roll)
{
    s32 e = expected_at(a, d, move_damage(a, d, m, order_fix(a, d, m, raw, weather)), m, weather, roll);
    return charges(a, m, weather) || ((m->flags >> F_RECHARGE) & 1) || delayed(m) ? e / 2 : e;
}

/* d answers a's move k: its Counter (Mirror Coat, Metal Burst) returns the hit, or (wp) the hit sets off its Weakness
   Policy */
static int answered(const Mon *a, const Mon *d, int k, int wp)
{
    return counter_slot(d, a, a->mv[k].cls) >= 0 || (wp && eff_move(a, d, &a->mv[k]) > 1000);
}

/* best expected damage per turn of `a` against `d` from a raw damage table (after the immunities the
   simulation does not see); *prio its priority. Against a Counter (Mirror Coat, Metal Burst) that lives through
   the hit, the race uses the best move it does not return, when that does a third of the damage or more; mine (my
   roll) also keep a Weakness Policy holder's super-effective hit for the KO */
static s32 best_rate(const Mon *a, const Mon *d, const u16 *raw, int weather, s8 *prio, int *slot, int roll, s32 *free)
{
    s32 e[4];
    int i, b = -1, o = -1, wp = roll == MY_ROLL && d->item == IT_WEAK__POLICY;
    for (i = 0; i < 4; i++) {
        const MoveInfo *m = &a->mv[i];
        e[i] = 0;
        if (!a->legal[i] || self_ko_move(m->id) || m->id == MV_DREAM_EATER || m->id == MV_SNORE || m->id == MV_FOCUS_PUNCH ||
            m->id == MV_FAKE_OUT)      /* works on the first turn out only */
            continue;
        e[i] = move_rate(a, d, m, raw[i], weather, roll);
        if (e[i] > 0 && (b < 0 || e[i] > e[b]))
            b = i;
    }
    if (free)
        *free = b >= 0 ? e[b] : 0;
    if (b >= 0 && answered(a, d, b, wp) && (e[b] < d->hp || endures(d, a))) {
        for (i = 0; i < 4; i++)
            if (e[i] > 0 && !answered(a, d, i, wp) && (o < 0 || e[i] > e[o]))
                o = i;
        if (o >= 0 && 3 * e[o] >= e[b])
            b = o;
    }
    *prio = b >= 0 ? a->mv[b].prio : 0;
    if (slot)
        *slot = b;
    return b >= 0 ? e[b] : 0;
}

static int choice_locks(const Mon *a, const MoveInfo *m);

/* f's best priority attack (a's on d, from a raw damage table): the race uses it when it knocks the other out. On my
   side (roll MY_ROLL) not Sucker Punch, which a status move stops, nor under a Choice item, which keeps the race attack */
static void prime(Fighter *f, const Mon *a, const Mon *d, const u16 *raw, int weather, int roll)
{
    int i;
    for (i = 0; i < 4; i++) {
        const MoveInfo *m = &a->mv[i];
        s32 e;
        if (!a->legal[i] || m->prio <= 0 || !m->cls || m->id == MV_FAKE_OUT || self_ko_move(m->id) ||
            (roll == MY_ROLL && (m->id == MV_SUCKER_PUNCH || choice_locks(a, m))))
            continue;
        e = move_rate(a, d, m, raw[i], weather, roll);
        if (e > f->pdmg) {
            f->pdmg = e;
            f->pprio = m->prio;
        }
    }
}

/* percent of max HP a recovery move restores: Morning Sun, Moonlight and Synthesis two thirds in sun and a quarter in
   other weather (official; half outside weather is seen in the logs) */
static int heal_pct(const MoveInfo *mv, int weather)
{
    if ((mv->id == MV_MORNING_SUN || mv->id == MV_MOONLIGHT || mv->id == MV_SYNTHESIS) && weather)
        return weather == W_SUN ? 66 : 25;
    return mv->heal > 0 ? mv->heal : 50;
}

/* HP a Pokemon's recovery move restores (Recover, Roost...; not Rest, which also puts it to sleep) */
static s32 heal_move(const Mon *m, int weather)
{
    int i;
    for (i = 0; i < 4; i++)
        if (m->legal[i] && self_heal(&m->mv[i]) && m->mv[i].id != MV_REST)
            return m->maxhp * heal_pct(&m->mv[i], weather) / 100;
    return 0;
}

static Fighter fighter(const Mon *m, s32 rate, s8 prio, int weather)
{
    Fighter f;
    int i;
    f.hp = f.hp0 = m->hp;
    f.maxhp = m->maxhp;
    f.who = WHO_ACTIVE;
    f.dmg64 = f.spe64 = 64;
    f.dmg = rate;
    f.spe = eff_speed(m, weather);
    f.tw = m->tailwind;
    f.prio = prio;
    f.chip = chip_of(m, weather);
    f.sleep = m->sleep;
    f.drowsy = m->drowsy;
    f.dream = f.nap = f.fo = 0;
    f.talk = f.fang = 0;
    for (i = 0; i < 4; i++)
        if (m->status == S_SLP && m->legal[i] && (m->mv[i].id == MV_SLEEP_TALK || m->mv[i].id == MV_SNORE))
            f.talk = 1;
    f.recharge = 0;
    f.heal = heal_move(m, weather);
    f.heal_prio = 0;
    for (i = 0; i < 4; i++)
        if (m->legal[i] && self_heal(&m->mv[i]) && m->mv[i].id != MV_REST)
            f.heal_prio = m->mv[i].prio;
    f.recoil = 0;
    f.endure = 0;
    f.multi = 0;
    f.flinch = 0;
    f.tox = f.wish = f.healed = f.orb = f.grow = 0;
    f.cls = 0;
    f.pdmg = 0;
    f.pprio = f.drain = 0;
    f.berry = m->item == IT_SITRUS_BERRY && 2 * m->hp > m->maxhp ? m->maxhp / 4 : 0;
    f.para = m->status == S_PAR;
    f.moody = A1B(A1B_MOODY) && m->ability == AB_MOODY;
    return f;
}

static int can_flinch(const Mon *d, const Mon *a)
{
    return breaks_mold(a) || (d->ability != AB_INNER_FOCUS && d->ability != AB_SHIELD_DUST);
}


/* a Flame Orb (Toxic Orb) burns (badly poisons) its holder at the end of its first turn out that it is awake (trainers
   give them to Pokemon that can get the status): then its race attack mv does x/2 (Guts x1.5 on a physical one and
   Facade x2 with a status, as aicalc fits the logs), and the status costs it a sixteenth a turn (bad poison its own way,
   Poison Heal heals an eighth, Magic Guard nothing). x << 2 | kind (0 burn, 1 bad poison, 2 Poison Heal, 3 no chip),
   0 without an orb */
static int orb_code(const Mon *m, const MoveInfo *mv)
{
    int t = m->item == IT_TOXIC_ORB, x = 2 + (mv->cls == 1 && m->ability == AB_GUTS);
    if ((!t && m->item != IT_FLAME_ORB) || m->status)
        return 0;
    return x << (2 + (mv->id == MV_FACADE)) | (m->ability == AB_MAGIC_GUARD ? 3 : t && m->ability == AB_POISON_HEAL ? 2 : t);
}

static int boost_kind(const MoveInfo *m);

/* m's fighter against foe, attacking with its move `slot`: its guard, what each strike costs it, its boost move */
static void arm(Fighter *f, const Mon *m, const Mon *foe, int slot)
{
    const MoveInfo *mv = slot >= 0 && slot < 4 ? &m->mv[slot] : 0;
    s32 v;
    int k;
    f->endure = endures(m, foe);
    if (!mv || !mv->id)
        return;
    f->cls = fixed_damage(m, foe, mv, &v) ? 0 : mv->cls;    /* Seismic Toss: no stage or burn changes it */
    for (k = 0; k < 4; k++)
        if (m->legal[k] && boost_kind(&m->mv[k]) && m->mv[k].rank_type[0] == 2 * f->cls - 1 && m->mv[k].rank_val[0] > 0)
            f->grow = m->mv[k].rank_val[0] & 7;
    f->fang = mv->efx == X_FANG && v ? (mv->acc > 100 ? 100 : mv->acc) / 2 : 0;
    f->orb = orb_code(m, mv);
    f->multi = multi(m, mv);
    f->flinch = mv->cls && can_flinch(foe, m) ? mv->flinch : 0;
    f->recoil = life_orb_recoil(m, mv) + contact_recoil(m, foe, mv);
    f->drain = 0;
    if (mv->drain > 0 || (m->ability != AB_ROCK_HEAD && m->ability != AB_MAGIC_GUARD))
        f->drain = mv->drain;
    f->recoil -= f->dmg * f->drain / 100;
}

/* Counter, Mirror Coat or Metal Burst returns the hit x took after it, when x lives through that hit: against a
   foe whose best attack it returns, it is x's attack in the race */
static void counter_fight(Fighter *x, const Mon *xm, const Mon *ym, int yslot, s32 yrate)
{
    int k = yslot >= 0 && yslot < 4 ? counter_slot(xm, ym, ym->mv[yslot].cls) : -1;
    s32 v;
    if (k < 0)
        return;
    v = returns10(&xm->mv[k], ym->mv[yslot].cls) * yrate / 10;
    if (v <= x->dmg || (yrate >= xm->hp && !endures(xm, ym)))
        return;
    if (8 * x->dmg < v)
        x->grow |= MIRROR;
    x->dmg = v;
    x->prio = xm->mv[k].prio;
    x->multi = x->flinch = x->fang = 0;
    x->recoil = 0;
    x->drain = 0;
}

/* the type a resist berry weakens (halves once, super effective hits; Chilan any Normal hit), or T_NONE */
static int resist_berry(int item)
{
    switch (item) {
    case IT_OCCA_BERRY: return T_FIRE;
    case IT_PASSHO_BERRY: return T_WATER;
    case IT_WACAN_BERRY: return T_ELECTRIC;
    case IT_RINDO_BERRY: return T_GRASS;
    case IT_YACHE_BERRY: return T_ICE;
    case IT_CHOPLE_BERRY: return T_FIGHTING;
    case IT_KEBIA_BERRY: return T_POISON;
    case IT_SHUCA_BERRY: return T_GROUND;
    case IT_COBA_BERRY: return T_FLYING;
    case IT_PAYAPA_BERRY: return T_PSYCHIC;
    case IT_TANGA_BERRY: return T_BUG;
    case IT_CHARTI_BERRY: return T_ROCK;
    case IT_KASIB_BERRY: return T_GHOST;
    case IT_HABAN_BERRY: return T_DRAGON;
    case IT_COLBUR_BERRY: return T_DARK;
    case IT_BABIRI_BERRY: return T_STEEL;
    case IT_CHILAN_BERRY: return T_NORMAL;
    case IT_ROSELI_BERRY: return T_FAIRY;
    }
    return T_NONE;
}

static int berry_fires(const Mon *a, const Mon *d, const MoveInfo *m)
{
    int t = resist_berry(d->item);
    return t != T_NONE && t == m->type && m->cls && (t == T_NORMAL || eff_move(a, d, m) > 1000);
}

/* the defender's own damage modifiers, which the simulation leaves out when the defender is off the field
   (each measured on the field in this hack, except Unaware) */
static s32 defender_mods(const Mon *a, const Mon *d, const MoveInfo *m, s32 v)
{
    int t = m->type, full = d->hp == d->maxhp, se = eff_move(a, d, m) > 1000;
    if (!breaks_mold(a))
        switch (d->ability) {
        case AB_THICK_FAT: if (t == T_FIRE || t == T_ICE) v /= 2; break;
        case AB_MULTISCALE: if (full) v /= 2; break;
        case AB_FUR_COAT: if (m->cls == 1) v /= 2; break;
        case AB_FILTER: case AB_SOLID_ROCK: case AB_SWARM: if (se) v = v * 3 / 4; break;   /* Swarm acts as Filter here */
        case AB_SHELL_ARMOR: if (m->cls == 1) v = v * 4 / 5; break;                       /* measured x0.8 */
        case AB_ICE_SCALES: if (m->cls == 2) v /= 2; break;
        case AB_FLUFFY:
            if ((m->flags >> F_CONTACT) & 1)
                v /= 2;
            if (t == T_FIRE)
                v *= 2;
            break;
        case AB_HEATPROOF: case AB_WATER_BUBBLE: if (t == T_FIRE) v /= 2; break;
        case AB_DRY_SKIN: if (t == T_FIRE) v = v * 5 / 4; break;
        case AB_PUNK_ROCK: if ((m->flags >> F_SOUND) & 1) v /= 2; break;
        case AB_PURIFYNGSALT: if (t == T_GHOST) v /= 2; break;
        case AB_MARVEL_SCALE: if (d->status) v = v * 2 / 3; break;     /* both defences here */
        case AB_UNAWARE: {                                              /* the attacker's boosts do not count */
            int st = a->stage[m->cls == 1 ? 0 : 2];
            if (st > 6)
                v = v * 64 / stage_mult(64, st);
            break;
        }
        }
    if (d->ability == AB_SHADOW_SHIELD && full)
        v /= 2;
    if (d->ability == AB_PRISM_ARMOR && se)
        v = v * 3 / 4;
    if (d->item == IT_ASSAULT_VEST && m->cls == 2)
        v = v * 2 / 3;
    if (d->item == IT_EVIOLITE)        /* trainers give it only to Pokemon that still evolve */
        v = v * 2 / 3;
    if (berry_fires(a, d, m))
        v /= 2;
    return v;
}

static s32 restage(s32 v, int cur, int nxt);

/* what the newcomer's Intimidate (or Blazing Awe, the same drop here; both measured) does on entry, before the foe's
   reply lands, to the foe's damage with moves of class cls, x64: Attack -1, which Defiant answers with Attack +2 and
   Competitive with Sp. Atk +2 (both seen in logs) */
static s32 entry_mult(const Mon *s, const Mon *d, int cls)
{
    int st = d->stage[cls == 2 ? 2 : 0], up;
    if ((s->ability != AB_INTIMIDATE && s->ability != AB_BLAZING_AWE) || !d->stage[0])
        return 64;
    switch (d->ability) {
    case AB_CLEAR_BODY: case AB_HYPER_CUTTER: case AB_WHITE_SMOKE: case AB_FULLMETALBDY: case AB_INNER_FOCUS:
    case AB_OBLIVIOUS: case AB_OWN_TEMPO: case AB_SCRAPPY: case AB_MEGA_CLAWS: case AB_GUARD_DOG:
        return 64;
    }
    up = cls == 1 ? (d->ability == AB_DEFIANT ? 1 : -1) : cls == 2 && d->ability == AB_COMPETITIVE ? 2 : 0;
    return restage(64, st, clamp(st + up, 0, 12));
}

/* every item and ability factor awake again, as the turn's flow has them: a simulation with an attacker off the field
   leaves those of its side's Pokemon on the field asleep, so every later simulation, by either side's AI, left out their
   abilities and items (measured: a Multiscale Snorlax took full damage in them, and the two sides valued mirror-image
   positions differently, by the order the clients ran in) */
static void wake_factors(void)
{
    void *f = AT(vptr, FACTORS);
    int k;
    for (k = 0; OK_PTR(f) && k < 64; k++, f = AT(vptr, (u32)f + 4))
        if ((u8)(AT(u8, (u32)f + 0x18) - 4) < 2)
            AT(u32, (u32)f + 0x14) &= ~FCT_ASLEEP;
}

/* the engine's damage at its maximum roll, without touching the battle's randomness: the RNG is set
   so that the roll is 100, then put back; if the simulation drew anything else first, the value is
   taken as an average roll */
static s32 sim_max(int a, int d, int move, u8 *unsure)
{
    volatile u32 *rng = (volatile u32 *)((u32)AT(bptr, MAIN_PTR) + MAIN_RNG);
    u32 saved = *rng, after;
    s32 v;
    *rng = RNG_PRE_MAX;
    wake_factors();
    waza_lend(move);
    v = E_SIM_DAMAGE(a, d, move);
    wake_factors();
    after = *rng;
    *rng = saved;
    if (after != RNG_AFTER_MAX) {
        ++*unsure;
        v = v * 1081 / 1000;
    }
    return v;
}

/* the simulation gives 1 when it thinks a move does nothing, and it does not know Mold Breaker or a grounding
   Iron Ball: when our rules say the move connects, our formula stands in */
static s32 sim_fix(int weather, const Mon *a, const Mon *d, const MoveInfo *m, s32 v)
{
    if (v <= 1 && m->id && m->cls && m->power > 1 && !ability_blocks(a, d, m) && eff_move(a, d, m) > 0) {
        s32 f = formula_damage(a, d, m, weather);
        if (f > v)
            v = f > 0xFFFF ? 0xFFFF : f;
    }
    return v;
}

/* ---------------------------------------------------------------- the race */

static s32 race_run(const Ctx *c, Fighter a, Fighter b, int t0);

/* my free entry after a faint: the best Pokemon that can still come in against the foe as the race left it,
   with no hit on entry (one step deep); dead: who fainted; tw: the turns left on my side's Tailwind */
static s32 follow_up(const Ctx *c, int dead, int tw, const Fighter *f, int *any)
{
    s32 best = 0, v;
    int k;
    *any = 0;
    for (k = 0; k <= MAX_BENCH; k++) {
        Fighter e, g;
        if (k == dead || (k < MAX_BENCH && k >= c->nbench) || (k == MAX_BENCH && dead == WHO_ACTIVE))
            continue;
        e = c->ent_me[k];
        if (f->wish) {          /* it comes in at full HP, cured */
            e.hp += e.maxhp - e.hp0;
            e.sleep = e.para = 0;
            if (k < c->nbench && c->bench[k].status == S_PAR)
                e.spe *= 2;
        }
        if (e.hp <= 0)
            continue;
        if (!e.tw != !tw)       /* my side's Tailwind as the race left it (e.spe has the one read this turn) */
            e.spe = tw ? 2 * e.spe : e.spe / 2;
        e.tw = tw;
        e.who = k | WHO_LAST;   /* what its race costs its roles counts, as for a switch-in */
        g = c->ent_foe[k];
        g.hp = g.hp0 = f->hp;
        g.sleep = f->sleep;
        g.drowsy = f->drowsy;
        g.para = f->para;
        g.recharge = f->recharge;
        g.chip = f->chip;
        g.tox = f->tox;
        g.orb = f->orb;
        g.berry = f->berry;
        g.tw = f->tw;
        g.dmg = g.dmg * f->dmg64 / 64;
        g.spe = g.spe * f->spe64 / 64;
        g.dmg64 = f->dmg64;
        g.spe64 = f->spe64;
        v = race_run(c, e, g, 0);
        if (!*any || v > best)
            best = v;
        *any = 1;
    }
    return best;
}

/* what my fighter's HP lost (or gained) costs its roles: per foe off the field it beats, that foe's stake by how surely
   it still wins the one on one, rising evenly from half its max HP below the HP it needs to half its max HP above
   (rolls, crits, chip and the foe's own choices move the real line either way, so each HP near it is worth a little,
   not a whole foe); a fainted one wins none. The biggest such loss counts in full and the others half (a fight that
   drains it for several foes is one it could not have spared for all of them anyway). Half again for a free entry
   after a faint, a turn further off (the replacement is picked then) */
static s32 role_loss(const Ctx *c, const Fighter *a)
{
    int j, w = a->who & 7;
    s32 v = 0, top = 0, m = a->maxhp + 1, h, l;
    for (j = 0; j < MAX_BENCH && w <= WHO_ACTIVE; j++)
        if (c->need[w][j]) {
            h = c->need[w][j] * a->maxhp / 255 - a->maxhp / 2;
            v += l = c->stake[j] * (clamp(a->hp0 - h, 0, m) - (a->hp > 0 ? clamp(a->hp - h, 0, m) : 0)) / m;
            if (l > top)
                top = l;
        }
    v = (v + top) / 2 * ROLE_W / 1000;
    return a->who & WHO_LAST ? v / 2 : v;
}

/* the race's end on the team scale: what my side's fighter lost against what the foe lost, a KO that ends
   the battle, and my free entry when mine fainted first */
static s32 outcome(const Ctx *c, const Fighter *a, const Fighter *b, int turns)
{
    s32 v = worth(b->hp0, b->maxhp) - worth(b->hp, b->maxhp);
    /* the foe's last Pokemon only returns hits: the HP mine keeps (or heals) is worth nothing, and turns risk little */
    int any = 1, idle = !c->opp_others && (b->grow & MIRROR);
    if (a->hp <= 0 || !idle)
        v += worth(a->hp, a->maxhp) - worth(a->hp0, a->maxhp) - role_loss(c, a);
    if (b->hp <= 0) {
        if (!c->opp_others)
            v += LAST_BONUS;
        if (a->hp > 0)
            v -= (idle ? TEMPO / 4 : TEMPO) * turns;
    }
    if (a->hp <= 0 && !(a->who & WHO_LAST)) {
        if (b->hp > 0)
            v += follow_up(c, a->who, a->tw, b, &any);
        else
            any = c->nbench > 0 || a->who != WHO_ACTIVE;
        /* both sides' last Pokemon falling the same turn is the player's loss (the game's end text, 4 of 4 in logs): the
           trainer's win, the player's loss with nothing gained */
        if (!any)
            v -= b->hp > 0 || c->opp_others ? LAST_BONUS : c->client & 1 ? 0 : 2 * LAST_BONUS + worth(b->hp0, b->maxhp);
    }
    return v;
}

/* a race still open after RACE_TURNS where one side kept healing and the other, which recovers too (Leftovers, Black
   Sludge, its own recovery move), lost less than a quarter of what it had: the heal loop does not win (its recovery
   runs out of PP first), so the healer counts as lost */
static int stalls(const Fighter *a, const Fighter *b)
{
    return a->healed && (b->chip < 0 || b->healed) && 4 * b->hp >= 3 * b->hp0;
}

/* a healer that lives through the race ends it anywhere in its heal cycle, which runs from at most the other's hit up
   to that plus its heal: it counts at the middle, so a hit before the race does not count for where the end falls */
static void cycle(Fighter *x, const Fighter *y)
{
    if (x->healed && x->hp > 0)
        x->hp = clamp((y->dmg + x->heal) / 2, 1, x->maxhp);
}

static void stall(Fighter *a, Fighter *b, int t)
{
    if (t >= RACE_TURNS && a->hp > 0 && b->hp > 0) {
        if (stalls(a, b))
            a->hp = 0;
        else if (stalls(b, a))
            b->hp = 0;
    }
    cycle(a, b);
    cycle(b, a);
}

static s32 race_once(const Ctx *c, Fighter a, Fighter b, int t0, int *turns)
{
    int n, t = race_core(&a, &b, 0, &n);
    stall(&a, &b, t);
    *turns = t;
    return outcome(c, &a, &b, t0 + t);
}

/* a paralyzed side loses each action it tries a quarter of the time (measured: qa/aivsai/paralysis.md). v is the race
   where it loses none, which took t turns; at the odds that it loses one of those, 1 - (3/4)^t, the race where it loses
   its first action and every fourth after it */
static s32 para_mix(const Ctx *c, const Fighter *a, const Fighter *b, int t0, int t, s32 v)
{
    int k, odds = 1000;
    s32 v0 = v;
    for (k = 0; k < t && k < 8; k++)
        odds = odds * 3 / 4;
    for (k = 0; k < 2; k++) {
        Fighter a1 = *a, b1 = *b, *f = k ? &b1 : &a1;
        if (f->para != 1)
            continue;
        f->para = 2;
        v += (1000 - odds) * (race_once(c, a1, b1, t0, &t) - v0) / 1000;
    }
    return v;
}

__attribute__((noinline)) static s32 race_run(const Ctx *c, Fighter a, Fighter b, int t0)
{
    int t;
    s32 v = race_once(c, a, b, t0, &t);
    return para_mix(c, &a, &b, t0, t, v);
}

/* a faster side whose attack can make the foe flinch: with the odds that at least one flinch comes in the
   turns that decide the race, the race where the foe's strikes land at those odds */
static s32 race_ex(const Ctx *c, Fighter a, Fighter b, int t0, s32 *left)
{
    Fighter a1 = a, b1 = b;
    int n, k, t, p = first(&a, &b, 1) ? a.flinch : b.flinch;
    s32 v0, v1, none = 1000, dp;
    t = race_core(&a, &b, 0, &n);
    stall(&a, &b, t);
    if (left)
        *left = a.hp;
    v0 = outcome(c, &a, &b, t0 + t);
    dp = para_mix(c, &a1, &b1, t0, t, v0) - v0;
    if (n && p) {
        Fighter a2 = a1, b2 = b1;
        for (k = 0; k < n && k < 3; k++)
            none = none * (100 - p) / 100;
        t = race_core(&a2, &b2, 1, &k);
        stall(&a2, &b2, t);
        v1 = outcome(c, &a2, &b2, t0 + t);
        v0 += (1000 - none) * (v1 - v0) / 1000;
    }
    v0 += dp;
    /* or the foe's first move is its sleep move: mine sleeps through two turns on average (1-3, measured), this
       one among them when the foe moves first */
    if (b1.nap > 0 && !a1.sleep && a1.orb != 1 && !b1.sleep && !b1.recharge) {
        k = first(&a1, &b1, 1);
        b1.nap = a1.fo = 0;
        if (k)
            strike(&a1, &b1, 100, 0);
        a1.sleep = k ? 2 : 1;
        end_of_turn(&a1);
        end_of_turn(&b1);
        v1 = a1.hp > 0 && b1.hp > 0 ? race_run(c, a1, b1, t0 + 1) : outcome(c, &a1, &b1, t0 + 1);
        v0 += (v1 - v0) * b.nap / 1000;
    }
    return v0;
}

static s32 race(const Ctx *c, Fighter a, Fighter b, int t0)
{
    return race_ex(c, a, b, t0, 0);
}

/* ---------------------------------------------------------------- vetoes */

static int status_blocked(const Ctx *c, const Mon *a, const Mon *d, const MoveInfo *m)
{
    int sick = m->sick;
    if (ability_blocks(a, d, m) || (A1(A1_VOID) && m->id == MV_DARK_VOID && a->species != SPECIES_DARKRAI))
        return 1;
    if ((d->shield & SHIELD_PRIO) && m->prio > 0)
        return 1;
    if (m->id == MV_LEECH_SEED)      /* Magic Guard: the seed drains nothing */
        return has_type(d, T_GRASS) || d->ability == AB_MAGIC_GUARD || B_COND_ON(d->bpp, C_LEECH_SEED);
    if (m->sick == C_YAWN)           /* fails on a drowsy or statused target, or one that cannot fall asleep */
        return d->status || d->drowsy || (d->shield & (SHIELD_STATUS | SHIELD_SLEEP)) ||
               (!breaks_mold(a) && (d->ability == AB_INSOMNIA || d->ability == AB_VITAL_SPIRIT || d->ability == AB_SWEET_VEIL ||
                                    d->ability == AB_COMATOSE || d->ability == AB_PURIFYNGSALT));
    if (m->quality == Q_SICK && sick == C_CONFUSION)     /* Confuse Ray, Supersonic, Sweet Kiss: not on a confused foe */
        return (d->ability == AB_OWN_TEMPO && !breaks_mold(a)) || (d->shield & SHIELD_STATUS) || cond_on(d, C_CONFUSION);
    if (sick < S_PAR || sick > S_PSN)
        return 0;
    if (d->status != S_NONE || (d->shield & SHIELD_STATUS) || (sick == S_SLP && (d->shield & SHIELD_SLEEP)))
        return 1;
    if (d->ability == AB_COMATOSE || d->ability == AB_PURIFYNGSALT || (d->ability == AB_LEAF_GUARD && c->weather == W_SUN))
        return !breaks_mold(a);
    if (m->type == T_ELECTRIC && has_type(d, T_GROUND))
        return 1;
    switch (sick) {
    case S_PAR: return has_type(d, T_ELECTRIC) || (d->ability == AB_LIMBER && !breaks_mold(a));
    case S_SLP: return !breaks_mold(a) && (d->ability == AB_INSOMNIA || d->ability == AB_VITAL_SPIRIT || d->ability == AB_SWEET_VEIL);
    case S_PSN: return ((has_type(d, T_POISON) || has_type(d, T_STEEL)) && a->ability != AB_CORROSION) ||     /* Corrosion poisons both (measured) */
                       d->ability == AB_POISON_HEAL || d->ability == AB_MAGIC_GUARD ||
                       (!breaks_mold(a) && (d->ability == AB_IMMUNITY || d->ability == AB_PASTEL_VEIL));
    case S_BRN: return has_type(d, T_FIRE) || (!breaks_mold(a) && (d->ability == AB_WATER_VEIL || d->ability == AB_WATER_BUBBLE ||
                                                                       d->ability == AB_THERMALEXCHG));
    case S_FRZ: return has_type(d, T_ICE) || (d->ability == AB_MAGMA_ARMOR && !breaks_mold(a));
    }
    return 0;
}

static int boost_kind(const MoveInfo *m)   /* 1 if it raises the user's stats and lowers none */
{
    int k, up = 0;
    if (m->target != TARGET_USER || (m->quality != Q_EFFECT && m->quality != Q_EFFECT_SICK))
        return 0;
    for (k = 0; k < 3; k++) {
        if (!m->rank_type[k])
            continue;
        if (m->rank_val[k] > 0)
            up = 1;
    }
    return up;
}

static Failed *failed_entry(int move, const Mon *t)
{
    int i;
    for (i = 0; i < FAILS; i++)
        if (mem.fail[i].live && mem.fail[i].move == move && mem.fail[i].target == t->id)
            return &mem.fail[i];
    return 0;
}

/* at each decision, with the foes out (n of them): end the entries whose target is not out, then learn from my
   Pokemon's last turn. Its move failed on the target when it used the move it chose (its PP went down and the engine
   has it as its last move) and the engine counts that use as failed (B_WORKED 0), with the target out all turn, not
   protected, out of reach or behind a substitute. A move that can miss is kept, but vetoed only once misses alone
   explain its failures less than 1 time in 20. The other side's entries (an AI on both sides: a tag partner, or
   tools/aivsai.py --self) target my Pokemon on the field, and stay */
__attribute__((noinline)) static int is_target(const Mon *m, const Failed *f)
{
    return m->bpp && m->id == f->target && m->species == f->species && m->turns >= f->turns;
}

static void remember(Ctx *c, const Mon *out, int n)
{
    Chosen *ch = &mem.chosen[c->me.id];
    const Mon *t = 0;
    int i, k;
    for (i = 0; i < FAILS; i++) {
        Failed *f = &mem.fail[i];
        int on = is_target(&c->me, f) || (c->doubles && c->has_ally && is_target(&c->ally, f));
        for (k = 0; k < n; k++)
            on |= is_target(&out[k], f);
        if (!on)
            f->live = 0;
    }
    for (k = 0; k < n; k++)
        if (out[k].id == ch->target)
            t = &out[k];
    for (k = 0; k < 4 && ch->live && t && ch->species == c->me.species && ch->turns + 1 == c->me.turns; k++) {
        const MoveInfo *m = &c->me.mv[k];
        Failed *f;
        if (m->id != ch->move)
            continue;
        if (B_PP(c->me.bpp, k) >= ch->pp || B_LAST_MOVE(c->me.bpp) != m->id || B_WORKED(c->me.bpp) || !t->turns || t->protects ||
            t->semi || t->subbed || t->stage[6] > 6 || c->me.stage[5] < 6 || (t->ability == AB_SAND_VEIL && c->weather == W_SAND) ||
            (t->ability == AB_SNOW_CLOAK && c->weather == W_HAIL))      /* evasion: a miss move_acc does not count */
            break;
        f = failed_entry(m->id, t);
        for (i = 0; !f && i < FAILS; i++)
            if (!mem.fail[i].live) {
                f = &mem.fail[i];
                f->live = 1;
                f->move = m->id;
                f->target = t->id;
                f->species = t->species;
                f->turns = t->turns;
                f->odds = 1000;
            }
        if (f)
            f->odds = f->odds * (100 - acc_now(&c->me, t, m, c->weather)) / 100;
        break;
    }
    ch->live = 0;
}

/* the side effect each hazard move lays (X_ROCKS on), and its most layers */
static const u8 haz_eff[3] = { SE_STEALTH_ROCK, SE_SPIKES, SE_TOXIC_SPIKES }, haz_max[3] = { 1, 3, 2 };

/* the move cannot work against `d`, or wastes the turn, whatever else happens */
static int vetoed_vs(const Ctx *c, int slot, const Mon *d, s32 raw)
{
    const Mon *a = &c->me;
    const MoveInfo *m = &a->mv[slot];
    int asleep = a->status == S_SLP && a->sleep;     /* it sleeps through this turn */
    if (!a->legal[slot])
        return 1;
    if (m->id == MV_SNORE || m->id == MV_SLEEP_TALK)
        return !asleep;
    if (asleep && m->cls == 0)      /* a status move gets no credit for the turn it might wake */
        return 1;
    if (m->id == MV_DREAM_EATER && d->status != S_SLP)     /* asleep, it still meets the type chart below */
        return 1;
    if (m->quality == Q_SICK && m->sick == C_NIGHTMARE)     /* only on a sleeping foe, and once */
        return d->status != S_SLP || B_COND_ON(d->bpp, C_NIGHTMARE);
    if (m->id == MV_FAKE_OUT && !a->fresh)       /* fails after the first turn out */
        return 1;
    if (delayed(m) && !a->fresh && B_LAST_MOVE(a->bpp) == m->id)    /* the last one is still on its way */
        return 1;
    if (aimed(m)) {                              /* failed here before */
        const Failed *f = failed_entry(m->id, d);
        if (f && f->odds < 50)
            return 1;
    }
    /* a substitute stops a status move at it, one at every foe too (measured: Dark Void fails), but not a sound move
       (measured: Sing gets through) */
    if (!m->cls && at_mon(m) && d->subbed && m->quality == Q_SICK && m->sick != 7 && !((m->flags >> F_SOUND) & 1) &&
        a->ability != AB_INFILTRATOR)
        return 1;
    if (!m->cls && at_mon(m) && ability_blocks(a, d, m))
        return 1;
    if (m->id == MV_TAILWIND)                    /* fails while my side's own is up */
        return SIDE_LAYERS(c->client & 1, SE_TAILWIND) > 0;
    if (m->efx >= X_ROCKS)                       /* the foe's side has every layer already */
        return SIDE_LAYERS((c->client & 1) ^ 1, haz_eff[m->efx - X_ROCKS]) >= haz_max[m->efx - X_ROCKS];
    if (m->target == TARGET_USER && (m->id == MV_AQUA_RING ? B_COND_ON(a->bpp, C_AQUA_RING) :
                                     m->sick > S_PSN && m->sick < 40 && B_COND_ON(a->bpp, m->sick)))
        return 1;                                /* Aqua Ring, Ingrain...: on me already */
    if (m->id == MV_STEEL_ROLLER && !c->terrain) /* fails with no terrain to remove */
        return 1;
    if (m->id == MV_LAST_RESORT) {               /* fails until each of my other moves was used since I came out */
        int k, others = 0;
        for (k = 0; k < 4; k++)
            if (k != slot && a->mv[k].id) {
                if (!B_USED(a->bpp, k))
                    return 1;
                others++;
            }
        if (!others || a->turns < others)
            return 1;
    }
    if (m->id == MV_ENCORE)                      /* fails on an encored foe, or one that has not moved yet */
        return B_COND_ON(d->bpp, C_ENCORE) || !B_LAST_MOVE(d->bpp);
    if (m->efx == X_TAUNT && B_COND_ON(d->bpp, C_TAUNT))
        return 1;
    if ((m->id == MV_FOLLOW_ME || m->id == MV_RAGE_POWDER || m->efx == X_HELP) && !c->doubles)    /* nothing to draw or help in singles */
        return 1;
    if (m->efx == X_CURE) {                      /* Heal Bell: no status on my side to cure */
        int k, any = a->status || (c->doubles && c->has_ally && c->ally.status);
        for (k = 0; k < c->nbench; k++)
            any |= c->bench[k].status;
        return !any;
    }
    if (m->id == MV_REFLECT || m->id == MV_LIGHT_SCREEN || m->id == MV_AURORA_VEIL) {   /* up already, or no snow */
        int side = c->client & 1;
        return m->id == MV_AURORA_VEIL ? c->weather != W_HAIL || (SIDE_LAYERS(side, SE_REFLECT) && SIDE_LAYERS(side, SE_LIGHT_SCREEN))
                                        : SIDE_LAYERS(side, m->id == MV_REFLECT ? SE_REFLECT : SE_LIGHT_SCREEN) > 0;
    }
    if (m->id == MV_HEALING_WISH) {   /* faints to heal the next one: only for a hurt teammate */
        int k;
        for (k = 0; k < c->nbench; k++)
            if (c->bench[k].hp * 2 < c->bench[k].maxhp || c->bench[k].status != S_NONE)
                return 0;
        return 1;
    }
    if (m->id == MV_SUCKER_PUNCH) {              /* fails unless the target attacks, with a move that can touch me */
        int k, attacks = 0;
        for (k = 0; k < 4; k++)
            attacks |= d->legal[k] && move_damage(d, a, &d->mv[k], 1) > 0;
        if (!attacks)
            return 1;
    }
    if (m->id == MV_COUNTER || m->id == MV_MIRROR_COAT) {   /* only against an attack of its kind */
        int k, cls = m->id == MV_COUNTER ? 1 : 2;
        for (k = 0; k < 4; k++)
            if (d->legal[k] && d->mv[k].cls == cls)
                return eff_move(a, d, m) == 0;
        return 1;
    }
    if (m->quality == Q_OHKO)
        return d->level > a->level || eff_permille(m->type, d) == 0;
    if (m->id == MV_BELLY_DRUM)
        return a->hp * 2 <= a->maxhp || a->stage[0] >= 12;
    if (m->id == MV_REST)
        return a->hp * 10 >= a->maxhp * 7 || a->ability == AB_INSOMNIA || a->ability == AB_VITAL_SPIRIT;
    if (self_heal(m))
        return a->hp * 10 >= a->maxhp * 9;
    if (m->id == MV_ENDEAVOR)        /* it works from the HP I have when it lands: after the foe's hit, when I move second */
        return !eff_move(a, d, m) || ability_blocks(a, d, m) ||
               (a->hp >= d->hp && faster(eff_speed(a, c->weather), eff_speed(d, c->weather)));
    if (m->cls != 0)
        return move_damage(a, d, m, raw) == 0;
    if (m->target != TARGET_USER && m->quality == Q_SICK)
        return status_blocked(c, a, d, m);
    if (boost_kind(m)) {
        int k, useful = 0;
        for (k = 0; k < 3; k++) {
            int t = m->rank_type[k];
            if (!t || m->rank_val[k] <= 0)
                continue;
            if (t >= 1 && t <= 7 && a->stage[t - 1] < 12) {
                if ((t == 1 || t == 3) && d->ability == AB_UNAWARE && !breaks_mold(a))
                    continue;
                useful = 1;
            }
        }
        return !useful;
    }
    return 0;
}

static int vetoed(const Ctx *c, int slot)
{
    return vetoed_vs(c, slot, &c->opp, c->d_mo[slot]);
}

/* ---------------------------------------------------------------- option values */

typedef struct Pair {
    s32 my_rate, opp_rate;     /* best expected damage per turn, me -> opp, opp -> me */
    s32 my_free;               /* my best one when that is a hit the foe's Counter returns */
    s8 my_prio, opp_prio;
    int my_slot, opp_slot;     /* my best attack; the player's best attack on my active Pokemon (the race) */
    s32 opp_hit;               /* the reply's expected damage on my active Pokemon this turn */
    s8 rep, rep_prio;          /* the reply valued: the player's move this turn (-1 none), its priority */
    u8 w[4];                   /* the odds of each of the player's moves this turn (reply_odds) */
    u8 ko;                     /* the player has a move that knocks my active Pokemon out */
} Pair;

/* m sleeps (or stays frozen) through this turn, with no Sleep Talk or Snore to act with */
static int dozes(const Mon *m)
{
    int k;
    for (k = 0; k < 4; k++)
        if (m->status == S_SLP && m->legal[k] && (m->mv[k].id == MV_SLEEP_TALK || m->mv[k].id == MV_SNORE))
            return 0;
    return m->sleep > 0;
}

/* a resist berry halves one hit only (the raw tables halve every hit): the race after it meets the full damage */
static const u16 *unberried(const Mon *a, const Mon *d, const u16 *raw, u16 *buf)
{
    int k;
    for (k = 0; k < 4; k++)
        buf[k] = berry_fires(a, d, &a->mv[k]) ? clamp(2 * raw[k], 0, 0xFFFF) : raw[k];
    return buf;
}

static void pair_data(Ctx *c, Pair *p)
{
    s32 best = -1, base, e, r;
    int i;
    u16 buf[4];
    p->my_rate = best_rate(&c->me, &c->opp, c->d_mo, c->weather, &p->my_prio, &p->my_slot, MY_ROLL, &p->my_free);
    p->opp_rate = best_rate(&c->opp, &c->me, unberried(&c->opp, &c->me, c->d_om, buf), c->weather, &p->opp_prio, &p->opp_slot,
                            THEIR_ROLL, 0);
    p->opp_hit = base = p->opp_rate;
    /* a move that knocks me out this turn comes first in their choice: a priority move before all, then a move
       that costs a recharge turn (the race halves its rate, not its one hit) when their best otherwise does not */
    for (i = 0; i < 4; i++) {
        const MoveInfo *m = &c->opp.mv[i];
        if (!c->opp.legal[i] || m->cls == 0)
            continue;
        e = expected(&c->opp, &c->me, move_damage(&c->opp, &c->me, m, c->d_om[i]), m, c->weather);
        if (e < c->me.hp || (endures(&c->me, &c->opp) && !multi(&c->opp, m)))
            continue;
        r = m->prio > 0 ? e + 0x10000 : ((m->flags >> F_RECHARGE) & 1) && base < c->me.hp ? e : -1;
        if (r > best) {
            best = r;
            p->opp_slot = i;
            p->opp_hit = e;
            p->opp_prio = m->prio;
        }
    }
    p->rep = p->opp_slot;
    p->rep_prio = p->opp_prio;
    if ((B_TURNFLAGS(c->opp.bpp) & 2) || dozes(&c->opp)) {     /* it spends this turn recharging or asleep */
        p->rep = -1;
        p->opp_hit = 0;
    }
}

/* the player's move k this turn on my Pokemon x: expected damage at a roll (nothing while it charges; the move it
   charged last turn lands now) */
static s32 hit_now(const Ctx *c, const Mon *x, int k, s32 raw, int roll)
{
    const Mon *d = &c->opp;
    const MoveInfo *m = &d->mv[k];
    if (!m->cls || (charges(d, m, c->weather) && m->id != d->charging))
        return 0;
    return expected_at(d, x, move_damage(d, x, m, raw), m, c->weather, roll);
}

/* a hit of up to maxd (rolls 85-100) at acc percent on h HP: the odds in percent that it knocks out, and in *hit the
   average damage when it does not (a miss counts as nothing) */
static int roll_ko(s32 maxd, s32 h, int acc, int endure, s32 *hit)
{
    s32 r = maxd < h || endure ? 0 : clamp((maxd - h) * 667 / maxd, 0, 100);
    int ko = r * acc / 100;
    *hit = ko < 100 ? acc * (100 - r) / 100 * (r ? (maxd * 85 / 100 + h - 1) / 2 : maxd * 925 / 1000) / (100 - ko) : 0;
    return ko;
}

static int sickens(const MoveInfo *m)
{
    return m->target != TARGET_USER && m->quality == Q_SICK && m->sick >= S_PAR && m->sick <= S_PSN;
}

/* the weight of a status move that can work, for the top attack's 10: the original AI picks one 7 times for that
   attack's 10 (measured); the advanced AI as a foe, a strong player, about 5 times when it inflicts a status and 3
   for boosts and the rest (self-play, run 20261003_133101). Between the two by c->strong. A sleep move the other
   way, about 13 at full strength: from a foe that moves first, the original AI uses one 35.5% of the time and the
   advanced AI 53.1% (round S1, unit C) */
static int status_w(const Ctx *c, const MoveInfo *m)
{
    if (sickens(m) && m->sick == S_SLP)
        return 7 + 6 * c->strong / 1000;
    return 7 - (sickens(m) ? 2 : 4) * c->strong / 1000;
}

/* the player's status move can work on my Pokemon x (the original AI scores the others down) */
static int foe_status_ok(const Ctx *c, const Mon *x, const MoveInfo *m)
{
    const Mon *d = &c->opp;
    int k;
    if (m->id == MV_PROTECT || m->id == MV_DETECT)     /* left out: the race has no turn where my move is stopped */
        return 0;
    if (m->efx >= X_RAIN && m->efx < X_ROCKS && m->efx - X_RAIN + W_RAIN == c->weather)   /* its weather is up: it fails */
        return 0;          /* the original AI did that 2 times in 91 weather moves (logs) */
    if (m->id == MV_SLEEP_TALK)
        return d->status == S_SLP;
    if (self_heal(m))
        return d->hp * 10 < d->maxhp * 9;
    if (m->target != TARGET_USER && m->quality == Q_SICK)
        return !status_blocked(c, d, x, m);
    k = m->rank_type[0] - 1;              /* a boost: its first stat below +4 */
    return !boost_kind(m) || (unsigned)k > 4 || d->stage[k] < 10;
}

/* how the original AI, on the player's side, picks its move against my active Pokemon (measured over its 4,588
   move choices in the AI-vs-AI logs): a move that knocks mine out almost always, evenly among those, except that a
   priority one is picked about 9 times in 10 and Sucker Punch half as often as the others; otherwise its strongest
   attack about 8 times in 10 attacks, and each status move that can work 7 times for that attack's 10. Counter and
   Mirror Coat answer my best attack's class. Status moves with no effect the race models share one branch. It
   simulates with a random roll, so a move that knocks out on some rolls only counts as a KO that often */
static void reply_odds(const Ctx *c, Pair *p)
{
    const Mon *d = &c->opp, *a = &c->me;
    s32 e[4], top = 0;
    int k, ko = 0, quiet = -1, sure = -8;      /* sure: the highest priority of a KO that surely lands first */
    p->ko = 0;
    for (k = 0; k < 4; k++)            /* the move it charged last turn: the engine makes it go on with it */
        p->w[k] = d->charging && d->mv[k].id == d->charging ? 10 : 0;
    if (p->w[0] + p->w[1] + p->w[2] + p->w[3])
        return;
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &d->mv[k];
        e[k] = !d->legal[k] || (B_TURNFLAGS(d->bpp) & 2) || dozes(d) || (m->id == MV_FAKE_OUT && !d->fresh) ? -1 : move_damage(d, a, m, c->d_om[k]) * hits_x10(m) / 10 * THEIR_ROLL / 1000;
        if (e[k] > top)
            top = e[k];
        if (e[k] >= a->hp)
            ko = 1;
        /* it lands first (priority, Speed, or mine sleeps) and knocks out at the lowest roll: a strong player always
           takes it, the one of highest priority, so my move fires only when it misses (mixed1's branch); Sucker Punch
           stays a guess on my move */
        if (e[k] * 1000 / THEIR_ROLL * 85 / 100 >= a->hp && m->id != MV_SUCKER_PUNCH && m->prio > sure &&
            !charges(d, m, c->weather) && !(endures(a, d) && !multi(d, m)) &&
            (m->prio > 0 || faster(eff_speed(d, c->weather), eff_speed(a, c->weather)) || dozes(a)))
            sure = m->prio;
    }
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &d->mv[k];
        int w = 0;
        if (e[k] < 0)
            ;
        else if (m->id == MV_COUNTER || m->id == MV_MIRROR_COAT || m->id == MV_METAL_BURST)
            w = !ko && p->my_slot >= 0 && answer10(d, a, k, a->mv[p->my_slot].cls) ? 10 : 0;
        else if (m->cls && ko) {
            s32 r, h;
            w = m->id == MV_SUCKER_PUNCH ? 5 : m->prio > 0 ? 200 : 10;
            r = roll_ko(e[k] * 1000 / THEIR_ROLL, a->hp, 100, 0, &h);
            w = !e[k] || (sure > -8 && (r < 100 || m->prio < sure)) ? 0 : 1 + (w - 1) * r / 100;
        } else if (m->cls)
            w = !e[k] ? 0 : e[k] == top ? 10 : 1;
        else if (!ko && foe_status_ok(c, a, m)) {
            w = status_w(c, m);
            if (!boost_kind(m) && !sickens(m)) {
                if (quiet >= 0) {
                    p->w[quiet] += w;
                    w = 0;
                } else
                    quiet = k;
            }
        }
        p->w[k] = w;
    }
    p->ko = ko;
}

/* the stat stage (1 Attack, 2 Defense, 3 Sp. Atk) that u's race attack (its move slot, of class cls) hits with: Body Press
   uses its Defense */
__attribute__((noinline)) static int att_stat(const Mon *u, int slot, int cls)
{
    return (unsigned)slot < 4 && u->mv[slot].efx == X_PRESS ? 2 : 2 * cls - 1;
}

/* v as a stat stage change from cur to nxt leaves it */
__attribute__((noinline)) static s32 restage(s32 v, int cur, int nxt)
{
    return stage_mult(v * 64, nxt) / stage_mult(64, cur);
}

/* m's fighter f is paralyzed now: Speed x1/2 (Quick Feet instead x1.5: the rc27 engine fix lifts the halving), and it
   loses an action a quarter of the time (measured: qa/aivsai/paralysis.md); its damage does not change */
static void paralyze(Fighter *f, const Mon *m)
{
    int qf = m->ability == AB_QUICK_FEET;
    f->spe = qf ? f->spe * 3 / 2 : f->spe / 2;
    f->spe64 = qf ? f->spe64 * 3 / 2 : f->spe64 / 2;
    f->para = 1;
}

/* what the player's move this turn leaves for the race: the stages its status move or its attack (Close Combat,
   Overheat) gives itself on y (the player's fighter), its status on x (mine, the Pokemon xm) */
static void reply_after(const Ctx *c, const Pair *p, Fighter *x, const Mon *xm, Fighter *y)
{
    const Mon *d = &c->opp;
    const MoveInfo *m;
    int k;
    if (p->rep < 0 || p->rep > 3)
        return;
    m = &d->mv[p->rep];
    if (m->cls ? m->quality == Q_DAMAGE_EFFECT_USER : boost_kind(m)) {
        for (k = 0; k < 3; k++) {
            int t = m->rank_type[k], cur, nxt;
            if (!t || t > 5)
                continue;
            cur = d->stage[t - 1];
            nxt = clamp(cur + m->rank_val[k], 0, 12);
            if (t == 5 || t == att_stat(d, p->opp_slot, y->cls)) {     /* its Speed, or the attack stat of its race attack */
                s32 *v = t == 5 ? &y->spe : &y->dmg;
                s16 *v64 = t == 5 ? &y->spe64 : &y->dmg64;
                *v = restage(*v, cur, nxt);
                *v64 = restage(*v64, cur, nxt);
            }
            if (t == 2 * x->cls)                            /* the defence my race attack hits */
                x->dmg = restage(x->dmg, nxt, cur);
        }
    } else if (!m->cls && m->sick == C_YAWN && !status_blocked(c, d, xm, m)) {
        x->drowsy = 2;
    } else if (!m->cls && sickens(m) && !status_blocked(c, d, xm, m)) {
        switch (m->sick) {
        case S_SLP: x->sleep = 2; break;
        case S_PAR: paralyze(x, xm); break;
        case S_BRN:
            if (x->cls == 1 && xm->ability != AB_GUTS && xm->ability != AB_QUICK_FEET)
                x->dmg /= 2;
            x->chip += tick(x->maxhp, 16);
            break;
        case S_PSN:
            if (m->id == MV_TOXIC)
                x->tox = 1;
            else
                x->chip += tick(x->maxhp, 8);
            break;
        }
    }
}

/* the active pair's fighters for the race after this turn (the foe's priority finisher, Dream Eater, the foe's sleep
   move from entries); a turn of sleep passes for the foe, which sleeps through this one */
static void pair_fighters(const Ctx *c, const Pair *p, Fighter *A, Fighter *B)
{
    *A = fighter(&c->me, p->my_rate, p->my_prio, c->weather);
    *B = fighter(&c->opp, p->opp_rate, p->opp_prio, c->weather);
    prime(B, &c->opp, &c->me, c->d_om, c->weather, THEIR_ROLL);
    A->dream = c->ent_me[MAX_BENCH].dream;
    B->dream = c->ent_foe[MAX_BENCH].dream;
    B->boost = c->ent_foe[MAX_BENCH].boost;
    A->chip = c->ent_me[MAX_BENCH].chip;            /* with the foe's Leech Seed draining into it (entries) */
    if (cond_on(&c->me, C_LEECH_SEED))
        B->chip -= c->me.maxhp / 8;
    B->nap = c->ent_foe[MAX_BENCH].nap;
    if (B->sleep)
        B->sleep--;
}

static s32 value_move(Ctx *c, const Pair *p, int slot);
static s32 value_status(Ctx *c, const Pair *p, int slot);
static s32 value_switch(Ctx *c, const Pair *p, int i);
static s32 value_item(Ctx *c, const Pair *p, int item);
static s32 value_stay(Ctx *c, const Pair *p, int slot);

/* what value_move found besides the value: Option.ko1, ko3, sure; dealt in per-mille of the foe's max HP; fo: the
   damage of a Fake Out that surely makes the foe skip its turn, or -1; fell: Option.fell in per-mille (-1: not known,
   mixed() judges it by the reply's hit). In ITCM RAM, as ai_replace runs value_move too (select_value) */
static s32 __attribute__((section(".itcm_bss"))) g_ko1, g_ko3, g_dealt, g_sure, g_fo, g_fell;

/* foresight (qa/aivsai/rc29_F.md): the coming turn's rolls, known before deciding. The battle LCG word, both actions and
   the battle state fix every draw of the turn, so for each pair of my move i and the foe's move k the predictor
   (fs_predict on the DS, the simulator's bridge on the host) plays the turn's draws and fills fs.cell[i][k]: mine, my
   move's outcome is known: stopped (my paralysis, or a knockout before it), flinched, missed, crit, the damage it deals,
   a flinch it causes; foe, the foe's move's: stopped (its paralysis, my flinch or knockout), missed, crit, the damage
   to me. fs_static and fs_settle keep only what the DS predictor can know, the same rules on both builds, so the
   simulator measures the DS's coverage. Level 1 reads my move's outcome (value_move), 2 the foe's too (mixed1). The
   cells are trusted only when the foe's committed action is a move (c->fs_move, read_choice). When RD uses the read,
   known_reply's one-hot reply weights pick the exact cell of the move the foe chose; when it does not, the blind
   reply weights spread over every pair's cells. A committed switch or item draws before the moves (a message variant,
   0x0222AAF8) and is not predicted. fs.on is set only while decide runs with trusted cells,
   so ai_replace never reads them. The AI only reads the LCG word: the engine simulation it runs from a predicted word
   is put back as sim_max does */
typedef struct {
    u8 mine, foe, stopped, flinched, missed, crit, flinch_foe, f_stopped, f_missed, f_crit;
    s16 dmg, f_dmg;
} FsCell;
#define FS_MAGIC 0x46534947u        /* "GISF": tools/fscheck.py finds the record in ITCM RAM by it */
struct FsState {
    u32 magic, word;                /* the LCG word the turn starts from */
    s32 me_hp, opp_hp;              /* the position the cells are for */
    u16 me_species, opp_species;
    u8 on, trusted;
    s8 rep;                         /* rep: the foe's reply valued + 1 (0 none) */
    u8 steer;                       /* k of a steered turn (word and the played cell are then w_k's), 0 none */
    u8 first[4][4];                 /* who moves first in the pair: 0 me, 1 the foe, 2 not known */
    FsCell cell[4][4];
#ifdef HOST_ENGINE_H
    u8 ofirst[4][4];                /* the bridge's real order per pair (F3_ORD), as first */
#endif
};
#ifdef HOST_ENGINE_H
int fs_level;
#else
#define fs_level 2
#endif
struct FsState fs __attribute__((section(".itcm_bss")));
#define FS_ATTRACT 7                /* infatuation in the WP_SICK numbering (Gen 5's order; not measured) */

/* asleep through this turn's attempt: the wake check (0x0221748C) adds 1 to the counter in copy 0 (2 with Early Bird)
   and wakes it, to act this turn with no draw, once the counter reaches the length (bits 3-8 of the condition word);
   1 asleep, 0 awake or waking, -1 not known */
static int fs_dozes(const Mon *m)
{
    void *s;
    if (m->status != S_SLP)
        return 0;
    if (!fs2(F2_SLP) || !(s = copy0(m->id)))
        return -1;
    return B_COND_COUNT(s, S_SLP) + (m->ability == AB_EARLY_BIRD ? 2 : 1) < (int)((B_COND(s, S_SLP) >> 3) & 63);
}

/* the most a confused Pokemon's self-hit takes (0x02220914: ((2L/5+2)*40*A/D)/50+2 with its staged Attack and
   Defense, times (100 - a 16 roll)/100), with a margin */
static s32 fs_self_max(const Mon *m)
{
    s32 a = stage_mult(m->stat[0], m->stage[0]), d = stage_mult(m->stat[1], m->stage[1]);
    s32 base = (2 * m->level / 5 + 2) * 40 * a / (d > 0 ? d : 1) / 50 + 2;
    return base + base / 10 + 2;
}

static int fs_here(const Ctx *c)
{
    return fs_level && fs.on && c->me.species == fs.me_species && c->me.hp == fs.me_hp &&
           c->opp.species == fs.opp_species && c->opp.hp == fs.opp_hp;
}
/* the cell of my move in `slot` against the reply valued, when its part (0 mine, 1 the foe's) is known */
static const FsCell *fs_get(const Ctx *c, int slot, int part)
{
    const FsCell *f;
    if (!fs.rep || (unsigned)slot > 3 || !fs_here(c))
        return 0;
    f = &fs.cell[slot][fs.rep - 1];
    return (part ? f->foe : f->mine) ? f : 0;
}

/* who moves first, my move mm against the foe's fm: 0 me, 1 the foe, 2 not known (a speed tie draws in the action sort,
   and eff_speed is an estimate: within 2% counts as a tie) */
static int fs_first(const Ctx *c, const MoveInfo *mm, const MoveInfo *fm)
{
    s32 a, b;
    if (mm->prio != fm->prio)
        return mm->prio < fm->prio;
    a = eff_speed(&c->me, c->weather);
    b = eff_speed(&c->opp, c->weather);
    if (a * 50 < b * 51 && b * 50 < a * 51)
        return 2;
    return !faster(a, b);
}

/* F3_ORD (trace Q2). The action sort draws for a speed tie in one priority bracket: BattleRandom(2) (0x02249C70) once in
   its first pass and twice in its second, and the three values' parity orders the pair (odd: client 1 first, even:
   client 0 first), plus once more before the second move. A Quick Claw (IsOccurPer(20), 0x0220CF5E) or Quick Draw
   (IsOccurPer(30)) holder draws once between the passes, client 0's first, whatever the brackets; an activation puts it
   first in its bracket and the sort draws nothing more. A speed is exact when nothing but its stage changes it (the
   AI's eff_speed estimates the rest: then the 2% band stays). ORD_UNKNOWN: Trick Room with a tie, two holders in one
   bracket, a speed not exact within the band */
enum { ORD_NONE, ORD_WALK, ORD_UNKNOWN };
static int fs_holder(const Mon *m) { return m->item == IT_QUICK_CLAW ? 20 : m->ability == AB_QUICK_DRAW ? 30 : 0; }
static int fs_plain_speed(const Ctx *c, const Mon *m)
{
    return m->item != IT_CHOICE_SCARF && m->item != IT_MACHO_BRACE && m->item != IT_IRON_BALL && m->item != IT_LAGGING_TAIL &&
           m->item != IT_FULL_INCENSE && !(m->item >= IT_POWER_BRACER && m->item <= IT_POWER_WEIGHT) && !m->status &&
           !m->tailwind && m->ability != AB_SWIFT_SWIM && m->ability != AB_CHLOROPHYLL && m->ability != AB_SAND_RUSH &&
           m->ability != AB_SLUSH_RUSH && m->ability != AB_UNBURDEN;
}
/* *first: the order when no draw decides it (0 me, 1 the foe, 2 a tie) */
static int fs_ord_kind(const Ctx *c, const MoveInfo *mm, const MoveInfo *fm, int *first)
{
    const Mon *a = &c->me, *d = &c->opp;
    s32 x, y;
    int ha = fs_holder(a), hd = fs_holder(d);
    *first = fs_first(c, mm, fm);
    if (!fs3(F3_ORD))
        return ORD_NONE;
    if (mm->prio != fm->prio)
        return ha || hd ? ORD_WALK : ORD_NONE;
    if (ha && hd)
        return ORD_UNKNOWN;
    if (fs_plain_speed(c, a) && fs_plain_speed(c, d)) {
        x = stage_mult(a->stat[4], a->stage[4]);
        y = stage_mult(d->stat[4], d->stage[4]);
        *first = x == y ? 2 : !faster(x, y);
        if (x == y && g_tr_left)
            return ORD_UNKNOWN;
    }
    if (*first == 2 && !(fs_plain_speed(c, a) && fs_plain_speed(c, d)))
        return ORD_UNKNOWN;
    return *first == 2 || ha || hd ? ORD_WALK : ORD_NONE;
}
#ifdef HOST_ENGINE_H
#define FS_ORD(i, k) fs.ofirst[i][k]        /* the bridge's real order */
#else
static u8 g_fs_ord[4][4];                   /* the walk's order (fs_ord_walk), slot bss: used within one poll */
#define FS_ORD(i, k) g_fs_ord[i][k]
#endif

/* a Pokemon whose part of the turn is not played: asleep (unless F2_SLP: fs_dozes), frozen (the thaw roll), confused
   (unless F2_CONF: fs_move walks the countdown and its rolls) or infatuated (its roll), out of reach or charging, a Quick Claw or Quick Draw (rolls in the action sort), a pinch
   berry (Liechi to Custap: stats, crit stage, accuracy or a random stat once a hit takes it low), a Speed eff_speed
   does not know (Quick Powder, Protosynthesis, Quark Drive, Surge Surfer, Slow Start; seen: a Quick Powder Ditto moved
   first), a form its own move changes (Stance Change: rc31 fscheck saw Aegislash's Iron Head deal 432 where 276 was
   simulated) */
static int fs_unplayed(const Mon *m)
{
    return (m->status == S_SLP && !fs2(F2_SLP)) || (m->status == S_FRZ && !fso(FO_FRZ)) || m->semi || m->charging ||
           (cond_on(m, C_CONFUSION) && !fs2(F2_CONF)) ||
           cond_on(m, FS_ATTRACT) || ((m->item == IT_QUICK_CLAW || m->ability == AB_QUICK_DRAW) && !fs3(F3_ORD)) ||
           (m->item >= IT_LIECHI_BERRY && m->item <= IT_CUSTAP_BERRY) || m->item == IT_QUICK_POWDER ||
           m->ability == AB_PROTOSYNTHSS || m->ability == AB_QUARK_DRIVE || m->ability == AB_SURGE_SURFER ||
           m->ability == AB_SLOW_START || m->ability == AB_STANCE_CHANGE;
}

/* x's damaging move m on y is one the predictor plays: one hit (multi-hit counts and their per-hit rolls are not
   modelled), no fixed or random damage (a simulation that draws more than the roll is caught too), no charge turn, a type and ability that let it land, no substitute, an accuracy
   roll the move data decides (No Guard and the weather's sure hits skip it), a crit roll of its own (Battle Armor and
   Shell Armor, Merciless and Sniper change it), no type change on use (Protean), no lock-in length roll (Outrage), no
   power by the order or by the foe's action (Fishious Rend, Avalanche, Sucker Punch, Focus Punch), no resist berry
   (the simulation would use it up), no Leek or Lucky Punch (crit stages by species), none of the cases where the
   simulation thinks the move does nothing and sim_fix stands in (Mold Breaker, Scrappy, a grounding Iron Ball; the
   bench showed Earthquake simulated at 1 HP) */
/* a power that follows what happened before the move, which the simulation does not see: the user's last move failed
   (Stomping Tantrum, Temper Flare; fscheck: Stomping Tantrum simulated at 60 dealt 118), an ally fell last turn
   (Retaliate), a use streak (Rollout, Ice Ball, Fury Cutter, Echoed Voice), or this turn's order (Payback, Assurance,
   Lash Out); and moves that raise their user's Sp. Atk before they hit in this hack (Meteor Beam, Electro Shot;
   fscheck --human: a Meteor Beam simulated at 72 dealt 108) */
static int fs_history(const MoveInfo *m)
{
    switch (m->id) {
    case MV_STOMPNGTNTRM: case MV_TEMPER_FLARE: case MV_RETALIATE: case MV_ROLLOUT: case MV_ICE_BALL:
    case MV_FURY_CUTTER: case MV_ECHOED_VOICE: case MV_PAYBACK: case MV_ASSURANCE: case MV_LASH_OUT:
    case MV_METEOR_BEAM: case MV_ELECTRO_SHOT:
        return 1;
    }
    return 0;
}

/* a damaging move that fails on a condition the simulation does not check: Fake Out and First Impression after the
   user's first turn out (fscheck --human: a person's late Fake Out, simulated at 43 to 159, failed four times), and
   moves that need a sleeping target, a held item, a berry eaten, a type, terrain, every other move used, or the
   target's own action (Dream Eater, Poltergeist, Belch, Burn Up, Double Shock, Synchronoise, Steel Roller, Last
   Resort, Thunderclap, Upper Hand), and the moves that return the damage their user took this turn (Counter, Mirror
   Coat, Metal Burst, Comeuppance, Bide: power 1 in the data; fscheck at the rc31 merge: Counter after Swords Dance
   simulated at 2, failed) */
static int fs_may_fail(const Mon *x, const MoveInfo *m)
{
    switch (m->id) {
    case MV_FAKE_OUT: case MV_FIRSTIMPRESN:
        return !x->fresh;
    case MV_DREAM_EATER: case MV_POLTERGEIST: case MV_BELCH: case MV_BURN_UP: case MV_DOUBLE_SHOCK:
    case MV_SYNCHRONOISE: case MV_STEEL_ROLLER: case MV_LAST_RESORT: case MV_THUNDERCLAP: case MV_UPPER_HAND:
    case MV_COUNTER: case MV_MIRROR_COAT: case MV_METAL_BURST: case MV_COMEUPPANCE: case MV_BIDE:
        return 1;
    }
    return 0;
}

static int fs_plain(const Ctx *c, const Mon *x, const Mon *y, const MoveInfo *m)
{
    s32 v;
    if (!m->id || !m->cls || (multi(x, m) && !fso(FO_MULTI)) || charges(x, m, c->weather) || fixed_damage(x, y, m, &v) || m->fails ||
        fs_history(m) || fs_may_fail(x, m) || waza(m->id, WP_CRIT) >= 6 ||
        m->efx == X_FANG || m->id == MV_MAGNITUDE || ability_blocks(x, y, m) || eff_move(x, y, m) <= 0 ||
        y->subbed || berry_fires(x, y, m) || waza(m->id, WP_EFFECT) == EFFECT_LOCK || doubles_first(m) || doubles_last(m) ||
        m->id == MV_SUCKER_PUNCH || m->id == MV_FOCUS_PUNCH)
        return 0;
    if (((x->ability == AB_NO_GUARD || y->ability == AB_NO_GUARD || y->ability == AB_BATTLE_ARMOR ||
          y->ability == AB_SHELL_ARMOR) && !fs2(F2_NG)) || x->ability == AB_MERCILESS || x->ability == AB_SNIPER ||
        x->ability == AB_PROTEAN || x->ability == AB_LIBERO || x->item == IT_LEEK || x->item == IT_LUCKY_PUNCH ||
        breaks_mold(x) || x->ability == AB_SCRAPPY || y->item == IT_IRON_BALL ||   /* the simulation gives 1 there (sim_fix) */
        y->ability == AB_DISGUISE || y->ability == AB_ICE_FACE)        /* a disguise takes the first hit */
        return 0;
    if (((m->id == MV_THUNDER || m->id == MV_HURRICANE) && (c->weather == W_RAIN || c->weather == W_SUN)) ||
        (m->id == MV_BLIZZARD && c->weather == W_HAIL))
        return 0;
    return 1;
}

/* the chance rolls after m's hit: their number (each kind draws once, even when it cannot apply: the trace in
   qa/aivsai/rng_foresight.md) and, for one roll, its chance and kind (1 a status or stat change, 2 a flinch); 9: not
   modelled (a sure effect, whose draw is not known; a condition other than the five statuses, as Hurricane's
   confusion, whose length is drawn before the chance roll: fscheck saw one land where the walk said it missed; and a
   sleep, whose length is drawn first too, 0x0220965C before 0x022096DA; always-crit moves skip the crit draw,
   0x02208A30, and fs_plain drops them) */
static int fs_rolls(const Mon *x, const MoveInfo *m, int *chance, int *kind)
{
    int k, n = 0, per, sg = x->ability == AB_SERENE_GRACE ? 2 : 1;
    if (m->sick && (m->sick_per <= 0 || m->sick < S_PAR || m->sick > S_PSN || m->sick == S_SLP))
        return 9;
    if (m->sick && m->sick_per > 0) {
        if (m->sick_per >= 100)
            return 9;
        n++, *chance = m->sick_per * sg, *kind = 1;
    }
    for (k = 0; k < 3; k++)
        if ((per = waza(m->id, WP_RANK_PER1 + k)) > 0) {
            if (per >= 100)
                return 9;
            n++, *chance = per * sg, *kind = 1;
        }
    if ((per = waza(m->id, WP_FLINCH)) > 0) {
        if (per >= 100)
            return 9;
        n++, *chance = per * sg, *kind = 2;
    }
    return n;
}

/* F2_SELF: x's damaging move m changes only its user's Attack, Sp. Atk or accuracy (Draco Meteor, Overheat, Leaf
   Storm, Psycho Boost, Power-Up Punch, Charge Beam...): the engine draws one BattleRandom(100) for all of them after
   the hit's own rolls (0x022069BC, whatever the chance), and the foe's move this turn is left as simulated (not a
   Speed change, which the action sort before the second move could tie; not a raise that Opportunist or a Mirror Herb
   copies); no other chance effect on the move */
static int fs_self_ok(const Mon *y, const MoveInfo *m)
{
    int k, n = 0;
    if (!fs2(F2_SELF) || m->quality != Q_DAMAGE_EFFECT_USER || m->sick || waza(m->id, WP_FLINCH) > 0)
        return 0;
    for (k = 0; k < 3; k++)
        if (waza(m->id, WP_RANK_TYPE1 + k)) {
            int t = waza(m->id, WP_RANK_TYPE1 + k), v = (s8)waza(m->id, WP_RANK_VAL1 + k);
            if ((t != 1 && t != 3 && t != 6) || (v > 0 && (y->ability == AB_OPPORTUNIST || y->item == IT_MIRROR_HERB)))
                return 0;
            n++;
        }
    return n > 0;
}

/* the draws of x's move m on y, moving first, are all counted: a played move, chance rolls of one kind or none,
   nothing on the hit that rolls (King's Rock, Stench, Pressure: this hack's Pressure gives a move with no flinch a 10%
   one, ability table 0x0224FF2C entry 46, its event 0x72 handler 0x02232708 (fscheck --human: a Pressure Dusknoir's
   Shadow Sneak drew a flinch roll the walk did not count); Poison Touch, Toxic Chain; the moves whose handlers draw
   after the hit (Tri Attack 0x0223CC5A, Dire Claw 0x02246620, Secret Power 0x0223FE7C); a flinch chance against Inner
   Focus, which draws no flinch roll (0x0223245C, 0x02208DEA); the target's Static,
   Flame Body, Poison Point, Effect Spore, Cute Charm, Cursed Body, Gulp Missile; Focus Band; a scan of the ability
   table for handlers that reach BattleRandom found no other), nothing that skips or adds a chance roll (Sheer Force,
   Shield Dust, Covert Cloak), no move that sends its user out or changes its own stats (their draws are not traced;
   Flip Turn sends its user out through U-turn's handler, 0x02240A6C on event 0xC7, though this hack's data gives it
   effect 0, not 228: fscheck saw a move predicted against the Pokemon that left), and no target whose item or ability
   sends a Pokemon out after the hit (Eject Button, Red Card, Wimp Out, Emergency Exit) */
static int fs_counted(const Ctx *c, const Mon *x, const Mon *y, const MoveInfo *m)
{
    int ch, kd;
    if (!fs_plain(c, x, y, m) || (m->quality == Q_DAMAGE_EFFECT_USER && !fs_self_ok(y, m)) || m->efx == X_PIVOT || m->id == MV_FLIP_TURN ||
        y->item == IT_EJECT_BUTTON || y->item == IT_RED_CARD || y->ability == AB_WIMP_OUT || y->ability == AB_EMERGNCYEXIT ||
        x->item == IT_KINGS_ROCK ||
        x->item == IT_RAZOR_FANG || x->ability == AB_STENCH || x->ability == AB_PRESSURE || x->ability == AB_POISON_TOUCH ||
        x->ability == AB_TOXIC_CHAIN || x->ability == AB_SHEER_FORCE || m->id == MV_TRI_ATTACK || m->id == MV_DIRE_CLAW ||
        m->id == MV_SECRET_POWER || (waza(m->id, WP_FLINCH) > 0 && y->ability == AB_INNER_FOCUS) || y->item == IT_FOCUS_BAND || y->item == IT_COVERT_CLOAK ||
        y->ability == AB_SHIELD_DUST)
        return 0;
    switch (y->ability) {
    case AB_STATIC: case AB_FLAME_BODY: case AB_POISON_POINT: case AB_EFFECT_SPORE: case AB_CUTE_CHARM: case AB_CURSED_BODY:
    case AB_GULP_MISSILE:
        return 0;
    }
    return fs_self_ok(y, m) || fs_rolls(x, m, &ch, &kd) <= 1 || fso(FO_CHANCE);
}

/* F2_PROT: x's Protect (Detect, King's Shield, Spiky Shield, Baneful Bunker, Obstruct, Silk Trap, Burning Bulwark)
   moving first, before y's damaging move: it holds at streak 0 with no draw, after that on one BattleRandom(3^streak)
   that comes out 0 (0x0223D48E, trace T4); a held move draws nothing after its user's own checks and misses. The
   streak byte is left as it was when another move follows, and the engine counts from 0 again then (trace T4_alt:
   Protect after Tackle at byte 1 held with no draw 9 of 9, after Protect it drew 4 of 4): fs_streak. Not with a taunt on x, nor after Endure, Wide Guard, Quick
   Guard, Mat Block or Crafty Shield at a nonzero byte (whether they keep the count is not traced), nor a move that
   goes through (no protect flag, as Feint; an Unseen Fist contact move) */
static int fs_streak(const Mon *x)
{
    int n = x->protects > 6 ? 6 : x->protects, e = n && OK_PTR(x->bpp) && B_LAST_MOVE(x->bpp) ? waza(B_LAST_MOVE(x->bpp), WP_EFFECT) : 0;
    return e == 111 || e == 355 || e == 361 || e == 383 || e == 441 || e == 451 ? n : 0;
}

static int fs_guard(const Mon *x, const Mon *y, const MoveInfo *xm, const MoveInfo *ym)
{
    int e = x->protects && OK_PTR(x->bpp) && B_LAST_MOVE(x->bpp) ? waza(B_LAST_MOVE(x->bpp), WP_EFFECT) : 0;
    return fs2(F2_PROT) && xm->efx == X_PROTECT && xm->prio > ym->prio && !cond_on(x, C_TAUNT) && ym->cls &&
           e != 116 && e != 278 && e != 306 && e != 376 && e != 349 &&
           ((ym->flags >> F_PROTECT) & 1) && !(y->ability == AB_UNSEEN_FIST && ((ym->flags >> F_CONTACT) & 1));
}

/* F2_NONE: x's status move m, moving first, draws nothing (no target is checked, no roll) and leaves the foe's move
   this turn as simulated: raises of Attack, Sp. Atk, Speed or accuracy only (the effects of Meditate, Swords Dance,
   Agility, Nasty Plot, Dragon Dance, this hack's Lunar Dance, Hone Claws, Shift Gear, Growth, Tail Glow, Work Up;
   not Autotomize or Fillet Away), Focus Energy, Laser Focus, Destiny Bond, Splash, Tailwind (the order is set at the
   turn's start), and hazards unless they bounce (Stealth Rock, Spikes, Toxic Spikes, Sticky Web) */
static int fs_quiet(const Mon *x, const Mon *y, const MoveInfo *m)
{
    int k;
    if (!fs2(F2_NONE) || m->cls)
        return 0;
    if (y->ability == AB_OPPORTUNIST || y->item == IT_MIRROR_HERB)     /* they copy a raise at once */
        return 0;
    switch (waza(m->id, WP_EFFECT)) {
    case 10: case 50: case 52: case 53: case 212: case 270: case 277: case 312: case 316: case 321: case 327:
        if (m->quality != Q_EFFECT)
            return 0;
        for (k = 0; k < 3; k++)
            if (m->rank_type[k] && (m->rank_val[k] <= 0 || (m->rank_type[k] != 1 && m->rank_type[k] != 3 &&
                                                             m->rank_type[k] != 5 && m->rank_type[k] != 6)))
                return 0;
        return 1;
    case 47: case 390: case 98: case 85: case 225:
        return 1;
    case 266: case 112: case 249: case 340:
        return y->ability != AB_MAGIC_BOUNCE;
    }
    return 0;
}

/* F3_ACC: x's status move m on y draws one accuracy number (0x02206846, a hit when value < accuracy, also at
   accuracy 100) and nothing else; it fails with no draw on a target already statused, a type the move or its status
   cannot affect (Thunder Wave on Ground, Toxic on Poison or Steel, a powder or Leech Seed on Grass) or one already
   seeded; Toxic from a Poison type, and any of them with No Guard on either side, lands with no draw (trace T1). FA_NONE: not this class, or a case not traced (a
   bounce, a substitute, a terrain or Safeguard, Prankster into a Dark type, Mold Breaker, Overcoat or Safety Goggles,
   an Electric or Fire type against its status, an ability or a berry that stops or cures it, a taunted or oblivious
   target) */
enum { FA_NONE, FA_FAIL, FA_DRAW, FA_SURE };
static int fs_acc_kind(const Ctx *c, const Mon *x, const Mon *y, const MoveInfo *m)
{
    int sick = m->sick, seed = m->id == MV_LEECH_SEED, taunt = m->efx == X_TAUNT;
    if (!fs3(F3_ACC) || m->cls || m->target == TARGET_USER ||
        (!seed && !taunt && (m->quality != Q_SICK || (sick != S_PAR && sick != S_BRN && sick != S_PSN))))
        return FA_NONE;
    if (y->ability == AB_MAGIC_BOUNCE || y->subbed || y->shield || breaks_mold(x) ||
        (x->ability == AB_PRANKSTER && has_type(y, T_DARK)) || !OK_PTR(y->bpp))
        return FA_NONE;
    if ((m->flags >> F_POWDER) & 1) {
        if (has_type(y, T_GRASS))
            return FA_FAIL;
        if (y->ability == AB_OVERCOAT || y->item == IT_SAFETYGOGGLS)
            return FA_NONE;
    }
    if (seed) {
        if (has_type(y, T_GRASS) || B_COND_ON(y->bpp, C_LEECH_SEED))
            return FA_FAIL;
    } else if (taunt) {
        if (cond_on(y, C_TAUNT) || y->ability == AB_OBLIVIOUS || y->ability == AB_AROMA_VEIL)
            return FA_NONE;
    } else {
        if (y->status != S_NONE || (m->type == T_ELECTRIC && has_type(y, T_GROUND)) ||
            (sick == S_PSN && (has_type(y, T_POISON) || has_type(y, T_STEEL)) && x->ability != AB_CORROSION))
            return FA_FAIL;
        if ((sick == S_PAR && has_type(y, T_ELECTRIC)) || (sick == S_BRN && has_type(y, T_FIRE)) || status_blocked(c, x, y, m) ||
            y->item == IT_LUM_BERRY || (sick == S_PAR && y->item == IT_CHERI_BERRY) ||
            (sick == S_BRN && y->item == IT_RAWST_BERRY) || (sick == S_PSN && y->item == IT_PECHA_BERRY))
            return FA_NONE;
        if (m->id == MV_TOXIC && has_type(x, T_POISON))
            return FA_SURE;
    }
    /* No Guard skips the accuracy draw for status moves too (the hit check 0x0220670C is shared; fscheck: a Stun
       Spore into No Guard drew none) */
    return m->acc > 100 || (fs2(F2_NG) && (x->ability == AB_NO_GUARD || y->ability == AB_NO_GUARD)) ? FA_SURE : FA_DRAW;
}

/* F3_LEN: x's sleep or confusion move m on y (trace T2). A sleep or confusion move draws its length (RandRange,
   BattleRandom(max - min + 1), 0x022237B4) before its checks, then accuracy, then on a hit the length again, the one
   kept; a powder move into a Grass type fails with no draw, a target already statused or with Insomnia (sleep), or
   already confused (confusion), fails after the first length draw. Swagger and Flatter draw accuracy, raise the
   stat, then one length (on a confused target too). Yawn draws its length (n 1) twice, once on a drowsy or statused
   target. FL_NONE: not this class or not traced (as fs_acc_kind, plus Own Tempo, Vital Spirit, Sweet Veil, Comatose,
   Purifying Salt, Leaf Guard, a curing berry, Swagger or Flatter at +6) */
enum { FL_NONE, FL_FAIL0, FL_FAIL1, FL_PLAY };
#define WP_SICK_TMIN 12             /* the move data's length range (bytes 12 and 13 of the record) */
#define WP_SICK_TMAX 13
static int fs_len_kind(const Ctx *c, const Mon *x, const Mon *y, const MoveInfo *m)
{
    int slp = m->quality == Q_SICK && m->sick == S_SLP, conf = m->quality == Q_SICK && m->sick == C_CONFUSION,
        swag = m->quality == Q_EFFECT_SICK && m->sick == C_CONFUSION, yawn = m->sick == C_YAWN;
    if (!fs3(F3_LEN) || m->cls || m->target == TARGET_USER || !(slp || conf || swag || yawn))
        return FL_NONE;
    if (y->ability == AB_MAGIC_BOUNCE || y->subbed || y->shield || breaks_mold(x) ||
        (x->ability == AB_PRANKSTER && has_type(y, T_DARK)) || !OK_PTR(y->bpp) || y->item == IT_LUM_BERRY)
        return FL_NONE;
    if ((m->flags >> F_POWDER) & 1) {
        if (has_type(y, T_GRASS))
            return FL_FAIL0;
        if (y->ability == AB_OVERCOAT || y->item == IT_SAFETYGOGGLS)
            return FL_NONE;
    }
    if (slp || yawn) {
        if (y->status != S_NONE || (yawn && y->drowsy))
            return FL_FAIL1;
        if (y->ability == AB_VITAL_SPIRIT || y->ability == AB_SWEET_VEIL || y->ability == AB_COMATOSE ||
            y->ability == AB_PURIFYNGSALT || y->ability == AB_LEAF_GUARD || (yawn && y->ability == AB_INSOMNIA) ||
            y->item == IT_CHESTO_BERRY)
            return FL_NONE;
        return slp && y->ability == AB_INSOMNIA ? FL_FAIL1 : FL_PLAY;
    }
    if (y->ability == AB_OWN_TEMPO || y->item == IT_PERSIM_BERRY)
        return FL_NONE;
    if (swag)
        return y->stage[m->rank_type[0] - 1] >= 12 ? FL_NONE : FL_PLAY;
    return cond_on(y, C_CONFUSION) ? FL_FAIL1 : FL_PLAY;
}

/* a status that lands on y before its move ym changes ym's damage: a burn on a physical move, Guts, Toxic Boost or
   Flare Boost */
static int fs_landed_hurts(const Mon *y, const MoveInfo *ym, int sick)
{
    return (ym->cls == 1 && (sick == S_BRN || y->ability == AB_GUTS || (sick == S_PSN && y->ability == AB_TOXIC_BOOST))) ||
           (ym->cls == 2 && sick == S_BRN && y->ability == AB_FLARE_BOOST);
}

/* x's status move, moving first before y's ym, whose draws are known; a status it lands may still change ym
   (fs_landed_hurts, applied in fs_settle) */
static int fs_status_first(const Ctx *c, const Mon *x, const Mon *y, const MoveInfo *xm, const MoveInfo *ym)
{
    return !xm->cls && (fs_quiet(x, y, xm) || fs_guard(x, y, xm, ym) || fs_acc_kind(c, x, y, xm) || fs_len_kind(c, x, y, xm));
}

/* AIF_READS: y's move ym, moving second, reads a stat of x that x's first move xm changed, which the simulation (run
   with the state at the decision) does not see: Foul Play x's Attack (rc34 LAYOUT's fscheck: Swords Dance first, then
   Foul Play simulated at 241, dealt 381), Gyro Ball and Electro Ball x's Speed (Tailwind too), Punishment any raise.
   No move reads the foe's Defense, Sp. Def or accuracy as these do; Body Press reads its user's own Defense */
static int fs_reads_first(const MoveInfo *xm, const MoveInfo *ym)
{
    int k, e = waza(ym->id, WP_EFFECT), atk = 0, spe = xm->id == MV_TAILWIND, any = 0;
    if (!aifix(AIF_READS) || (xm->cls && xm->quality != Q_DAMAGE_EFFECT_USER))     /* a hit's stat change is the foe's */
        return 0;
    for (k = 0; k < 3; k++)
        if (xm->rank_type[k]) {
            any = 1;
            atk |= xm->rank_type[k] == 1;
            spe |= xm->rank_type[k] == 5;
        }
    return (ym->id == MV_FOUL_PLAY && atk) || ((e == 219 || e == 293) && spe) || (e == 245 && any);
}

/* y, hit first by x's move xm for dmg (crit), then uses ym with damage the simulation (run with the state at the
   decision) does not give: power by its HP (Eruption; Flail and the other moves whose power the engine computes, power
   0 or 1 in the data), Blaze, Torrent or Overgrow at a third of its HP or less, stats the hit raises or lowers for
   ym (Anger Point on a crit, Justified, Berserk and Anger Shell at half, Weakness Policy; Thermal Exchange, Cell
   Battery and Snowball for a physical ym, Absorb Bulb for a special one; Stamina, Weak Armor, Water Compaction and a
   Kee Berry for Body Press: fscheck --human saw a Stamina Steelix's Body Press deal 400 where 334 was simulated), a
   charge (Electromorphosis, Wind Power) for an Electric ym, the field it sets (Seed Sower, Sand Spit), x's ability
   it takes (Mummy), its types changed (Color Change) */
static int fs_shaken(const Mon *x, const MoveInfo *xm, const Mon *y, const MoveInfo *ym, s32 dmg, int crit)
{
    s32 left = y->hp - dmg;
    int phys = xm->cls == 1;
    if (dmg <= 0)
        return 0;
    return ym->efx == X_ERUPT || ym->power <= 1 || y->ability == AB_COLOR_CHANGE || (crit && y->ability == AB_ANGER_POINT) ||
           ((y->ability == AB_BLAZE || y->ability == AB_TORRENT || y->ability == AB_OVERGROW) && left * 3 <= y->maxhp) ||
           ((y->ability == AB_BERSERK || y->ability == AB_ANGER_SHELL) && left * 2 <= y->maxhp) ||
           (y->ability == AB_JUSTIFIED && xm->type == T_DARK) || (y->item == IT_WEAK__POLICY && eff_move(x, y, xm) > 1000) ||
           (ym->cls == 1 && ((y->ability == AB_THERMALEXCHG && xm->type == T_FIRE) ||
                             (y->item == IT_CELL_BATTERY && xm->type == T_ELECTRIC) || (y->item == IT_SNOWBALL && xm->type == T_ICE))) ||
           (ym->cls == 2 && y->item == IT_ABSORB_BULB && xm->type == T_WATER) ||
           (ym->efx == X_PRESS && (y->ability == AB_STAMINA || (y->ability == AB_WEAK_ARMOR && phys) ||
                                   (y->ability == AB_WATERCOMPACT && xm->type == T_WATER) || (y->item == IT_KEE_BERRY && phys))) ||
           (ym->type == T_ELECTRIC && (y->ability == AB_ELECTROMORPH || y->ability == AB_WIND_POWER)) ||
           y->ability == AB_SEED_SOWER || y->ability == AB_SAND_SPIT || y->ability == AB_MUMMY;
}

/* what the DS predictor can know in the pair (my move i, the foe's move k): bit 0 my part, bit 1 the foe's; *first as
   fs_first. A side's part needs its own move played (a status move's is not), and the side moving second needs every
   draw before its own counted and a hit that leaves its damage as simulated */
static int fs_static(const Ctx *c, int i, int k, int *first)
{
    const Mon *a = &c->me, *d = &c->opp;
    const MoveInfo *mm = &a->mv[i], *fm = &d->mv[k];
    int ok = 0, za, zd;
    *first = 2;
    if (c->doubles || !mm->id || !fm->id || fs_unplayed(a) || fs_unplayed(d))
        return 0;
    if ((za = fs_ord_kind(c, mm, fm, first)) == ORD_UNKNOWN)
        return 0;
    if (za == ORD_WALK)
        *first = FS_ORD(i, k);
    if (*first == 2)
        return 0;
    /* F2_SLP: a side asleep through the turn draws nothing and its part is known (stopped); Sleep Talk and Snore act */
    za = fs_dozes(a);
    zd = fs_dozes(d);
    if (za < 0 || zd < 0 || (a->status == S_SLP && (mm->id == MV_SLEEP_TALK || mm->id == MV_SNORE)) ||
        (d->status == S_SLP && (fm->id == MV_SLEEP_TALK || fm->id == MV_SNORE)))
        return 0;
    if (za || fs_plain(c, a, d, mm) || (*first == 0 && fs_status_first(c, a, d, mm, fm)))
        ok |= 1;
    if (zd || fs_plain(c, d, a, fm) || (*first == 1 && fs_status_first(c, d, a, fm, mm)))
        ok |= 2;
    if (*first == 0 && !za && !zd && ((!fs_counted(c, a, d, mm) && !fs_status_first(c, a, d, mm, fm)) || fs_reads_first(mm, fm)))
        ok &= ~2;
    if (*first == 1 && !za && !zd && ((!fs_counted(c, d, a, fm) && !fs_status_first(c, d, a, fm, mm)) || fs_reads_first(fm, mm)))
        ok &= ~1;
    return ok;
}

/* a crit's damage is known only as a knockout: the DS predictor's x1.5 lands within 2 HP of the engine's crit, which
   comes before the roll (fscheck: 192 for 191, 40 for 41), so fs_move keeps a crit only when x1.5 knocks out with that
   margin; the stages and screens a crit ignores only add to the hit, so they cannot undo the knockout */
static int fs_crit_ok(const Mon *x, const Mon *y, const MoveInfo *m, int yside, s32 dmg)
{
    return dmg >= y->hp;
}

/* x may faint from its own hit of dmg (Life Orb, a Rocky Helmet or Rough Skin, recoil): the move after it then has
   no target */
static int fs_falls(const Mon *x, const Mon *y, const MoveInfo *m, s32 dmg)
{
    return life_orb_recoil(x, m) + contact_recoil(x, y, m) + (m->drain < 0 ? dmg * -m->drain / 100 + 1 : 0) >= x->hp;
}

/* the rules both builds apply to a filled cell: fs_static's; the side moving second, shaken by the first hit
   (fs_shaken) or left with no target (fs_falls); then a crit whose damage is not known clears its part and the part of the side moving after it (whether
   that one is knocked out first is not known) */
static void fs_settle(const Ctx *c, int i, int k, FsCell *f)
{
    int first, ok = fs_static(c, i, k, &first), me = c->client & 1, za = fs_dozes(&c->me) == 1, zd = fs_dozes(&c->opp) == 1;
    const MoveInfo *mm = &c->me.mv[i], *fm = &c->opp.mv[k];
    fs.first[i][k] = first;
    f->mine &= ok & 1;
    f->foe &= ok >> 1;
    /* F2_CONF: a confused first mover stopped (a self-hit takes up to fs_self_max of its HP first): the second hit is
       known only when it leaves that HP standing either way */
    if (first == 0 && f->foe && f->mine && f->stopped && cond_on(&c->me, C_CONFUSION) && !f->f_missed && !f->f_stopped &&
        f->f_dmg + fs_self_max(&c->me) >= c->me.hp)
        f->foe = 0;
    if (first == 1 && f->mine && f->foe && f->f_stopped && cond_on(&c->opp, C_CONFUSION) && !f->missed && !f->stopped &&
        !f->flinched && f->dmg + fs_self_max(&c->opp) >= c->opp.hp)
        f->mine = 0;
    /* F3_LEN: Swagger or Flatter landed raises the stat the second move uses (AIF_READS: or any, for Stored Power and
       Power Trip, whose power counts the raises); a fresh sleeper's Sleep Talk or Snore */
    if (first == 0 && f->foe && f->mine && !f->missed && fs_len_kind(c, &c->me, &c->opp, mm) == FL_PLAY &&
        ((mm->quality == Q_EFFECT_SICK && (fm->cls == (mm->rank_type[0] == 1 ? 1 : 2) ||
                                           (aifix(AIF_READS) && waza(fm->id, WP_EFFECT) == 305))) ||
         (mm->sick == S_SLP && (fm->id == MV_SLEEP_TALK || fm->id == MV_SNORE))))
        f->foe = 0;
    if (first == 1 && f->mine && f->foe && !f->f_missed && fs_len_kind(c, &c->opp, &c->me, fm) == FL_PLAY &&
        ((fm->quality == Q_EFFECT_SICK && (mm->cls == (fm->rank_type[0] == 1 ? 1 : 2) ||
                                           (aifix(AIF_READS) && waza(mm->id, WP_EFFECT) == 305))) ||
         (fm->sick == S_SLP && (mm->id == MV_SLEEP_TALK || mm->id == MV_SNORE))))
        f->mine = 0;
    /* F3_ACC: a status my first move landed that changes the foe's move, and the other way round */
    if (first == 0 && f->foe && f->mine && !f->missed && !f->stopped && fs_acc_kind(c, &c->me, &c->opp, mm) >= FA_DRAW &&
        fs_landed_hurts(&c->opp, fm, mm->sick))
        f->foe = 0;
    if (first == 1 && f->mine && f->foe && !f->f_missed && !f->f_stopped && fs_acc_kind(c, &c->opp, &c->me, fm) >= FA_DRAW &&
        fs_landed_hurts(&c->me, mm, fm->sick))
        f->mine = 0;
    /* a status move that can paralyze the other side this turn leaves that side's move unknown whenever it may move
       second, ties included (rc33 merge: fscheck --human saw a tied Pokemon paralyzed first move where the walk drew its
       full paralysis); it only removes trust */
    if (first != 1 && f->foe && mm->sick == S_PAR && fs_acc_kind(c, &c->me, &c->opp, mm) >= FA_DRAW)
        f->foe = 0;
    if (first != 0 && f->mine && fm->sick == S_PAR && fs_acc_kind(c, &c->opp, &c->me, fm) >= FA_DRAW)
        f->mine = 0;
    if (first == 0 && f->foe && !zd && (!f->mine || (!f->missed && !f->stopped && (fs_shaken(&c->me, mm, &c->opp, fm, f->dmg, f->crit) ||
                                                                          fs_falls(&c->me, &c->opp, mm, f->dmg)))))
        f->foe = 0;
    if (first == 1 && f->mine && !za && (!f->foe || (!f->f_missed && !f->f_stopped && (fs_shaken(&c->opp, fm, &c->me, mm, f->f_dmg, f->f_crit) ||
                                                                              fs_falls(&c->opp, &c->me, fm, f->f_dmg)))))
        f->mine = 0;
    if (f->mine && f->crit && !f->missed && !f->stopped && !fs_crit_ok(&c->me, &c->opp, &c->me.mv[i], me ^ 1, f->dmg)) {
        f->mine = 0;
        if (first == 0 && !zd)
            f->foe = 0;
    }
    if (f->foe && f->f_crit && !f->f_missed && !f->f_stopped && !fs_crit_ok(&c->opp, &c->me, &c->opp.mv[k], me, f->f_dmg)) {
        f->foe = 0;
        if (first == 1 && !za)
            f->mine = 0;
    }
}

/* ---- steer: rules (shared) ---- */
/* Luck steering (rc31 unit L; hard mode, an important trainer, the advanced AI serving it: steer_gate). After decide
   the AI plays its chosen move i against the foe's committed move kf from each RNG position w_k, k = 0..n-1 (w_0 the
   word the turn starts from), and may start the turn from another w_k. The rules are filters and a budget over that
   one candidate table: (a) the player's own rolls are never changed, (b) a zero-sum value ledger plus a per-class
   guard, (c) only decisive turns, at most steer_cap a battle, (d) quiet rolls before visible ones, at most steer_vis
   visible a battle. steer_k 0 turns it off (the build is rc30's) */
typedef struct {
    FsCell cell;        /* the pair (my chosen move i, the foe's committed move kf) played from w_k, after fs_settle */
    u8 roll, f_roll;    /* my / the foe's damage roll index 0-15 when the move hit and its damage is known, else 255 */
    u8 landed, f_landed;/* my / the foe's chance effect landed (status, stat change, flinch) */
    u8 f_par, f_pre;    /* the foe's stop split: its own full paralysis / pre-empted by my knockout or flinch */
    u8 sig;             /* the foe's whole signature is known (every roll of its move counted): rule (a) can judge it */
    u8 pad;
} SteerCand;
typedef struct {        /* one per steering side, reset when a new battle starts */
    u32 tag;            /* the battle it belongs to (steer_battle_tag()) */
    s32 bank;           /* rule (b): sum over trusted turns of E - v(k played), per mille units */
    s32 cls[5];         /* per-class sums of (outcome - probability) in 1/1000 rolls: STC_ACC, STC_CRIT, STC_DMG
                           (index - 7.5, in 1/1000 index steps), STC_CHANCE, STC_PAR (moved, not stopped, minus 0.75) */
    u8 steers, visible; /* rule (c) and (d) counts this battle */
    u8 pad[2];
} SteerLedger;
enum { STC_ACC, STC_CRIT, STC_DMG, STC_CHANCE, STC_PAR };
enum { SR_A = 1, SR_B = 2, SR_C = 4, SR_D = 8 };
#ifdef HOST_ENGINE_H
/* the simulator's knobs (tools/sim/bridge.c: SIM_STEER_K, SIM_STEER_RULES, SIM_STEER_OPT) */
int steer_k, steer_rules, steer_strict, steer_bank, steer_class, steer_cap, steer_vis, steer_kow;
int steer_slack[5];
#define STEER_KMAX 256
#else
/* the shipped form (rc31 L-sim, measured; shared/CHOSEN): (a), (c) with one steer a battle, (d) with one visible
   event a battle, and the per-class zero-sum guard standing in for (b) (the value ledger blocked nearly every steer) */
#define steer_k 64                                  /* candidates: w_0 .. w_63 */
#define steer_rules (SR_A | SR_C | SR_D)
#define steer_strict 0                              /* (a): a pre-emption by my knockout or flinch is my outcome */
#define steer_bank 0                                /* (b) value ledger (off in steer_rules): 0 passive, 1 active banking */
#define steer_class 1                               /* the per-class guard */
#define steer_cap 1                                 /* (c): steers a battle */
#define steer_vis 1                                 /* (d): visible steers a battle */
#define steer_kow 2000                              /* (b): a knockout's weight in the turn's value v */
/* the class guard's slack, 1/1000 rolls (STC_*): a steer never takes a class past it this battle; one roll for
   accuracy, chance and paralysis, two damage rolls' worth of index steps, and less than one crit */
static const s32 steer_slack[5] = { 1000, 850, 16000, 1000, 1000 };
#define STEER_KMAX 64
#endif
/* the last booked turn, for the host's counts and fscheck */
static struct { u8 booked, decisive, ko, visible; s16 nominal; } steer_last;

/* the turn's value at one candidate: dealt and taken in per mille of max HP, a knockout steer_kow either way */
static s32 steer_v(const Ctx *c, const SteerCand *t, int *kod, int *kot)
{
    s32 dealt = t->cell.dmg, taken = t->cell.f_dmg;
    dealt = dealt < 0 ? 0 : dealt > c->opp.hp ? c->opp.hp : dealt;
    taken = taken < 0 ? 0 : taken > c->me.hp ? c->me.hp : taken;
    *kod = dealt >= c->opp.hp;
    *kot = taken >= c->me.hp;
    return 1000 * dealt / c->opp.maxhp - 1000 * taken / c->me.maxhp + steer_kow * (*kod - *kot);
}

/* knockouts as one order: mine and not the foe's, both, neither, only the foe's */
static int steer_rank(int kod, int kot) { return 2 * (kod - kot) + kod; }

static int steer_usable(const SteerCand *t) { return t->sig && t->cell.mine && t->cell.foe; }

/* a battle count under its cap (a function, so a cap of 0 compares without a warning) */
static int steer_room(int used, int cap) { return used < cap; }

/* rule (a): the player's signature at k is k = 0's whenever its move is played in both; my knockout or flinch that
   pre-empts it at k is my outcome (not under steer_strict); a move pre-empted at k = 0 and played at k would roll anew */
static int steer_a(const SteerCand *t0, const SteerCand *tk)
{
    if (!(steer_rules & SR_A))
        return 1;
    if (t0->f_pre != tk->f_pre)
        return !t0->f_pre && !steer_strict;
    return t0->f_pre || (t0->f_par == tk->f_par && t0->cell.f_missed == tk->cell.f_missed &&
                         t0->cell.f_crit == tk->cell.f_crit && t0->f_roll == tk->f_roll &&
                         t0->f_landed == tk->f_landed && t0->cell.f_dmg == tk->cell.f_dmg);
}

/* my rolls at a candidate, as (outcome - probability) per class in 1/1000 rolls */
static void steer_cls(const Ctx *c, int i, int kf, const SteerCand *t, s32 *d)
{
    const MoveInfo *m = &c->me.mv[i];
    int kod, kot, acc, st, ch = 0, kd = 0, k;
    steer_v(c, t, &kod, &kot);
    for (k = 0; k < 5; k++)
        d[k] = 0;
    if (t->cell.flinched || (t->cell.stopped && kot && fs.first[i][kf] == 1))
        return;                 /* pre-empted: no roll of mine */
    if (c->me.status == S_PAR)
        d[STC_PAR] = (t->cell.stopped ? 0 : 1000) - 750;
    if (t->cell.stopped)
        return;
    acc = acc_now(&c->me, &c->opp, m, c->weather);
    if (acc < 100)
        d[STC_ACC] = (t->cell.missed ? 0 : 1000) - 10 * acc;
    if (t->cell.missed)
        return;
    st = waza(m->id, WP_CRIT) + (c->me.ability == AB_SUPER_LUCK) + (c->me.item == IT_SCOPE_LENS || c->me.item == IT_RAZOR_CLAW);
    if (st < 3)
        d[STC_CRIT] = (t->cell.crit ? 1000 : 0) - 1000 / (st == 2 ? 2 : st == 1 ? 8 : 24);
    if (t->roll < 16)
        d[STC_DMG] = 1000 * t->roll - 7500;
    if (fs_rolls(&c->me, m, &ch, &kd) == 1 && ch > 0 && ch < 100)
        d[STC_CHANCE] = (t->landed ? 1000 : 0) - 10 * ch;
}

/* rule (d): a candidate that shows what k = 0 does not (my crit, my chance effect landing, a flinch) */
static int steer_visible(const SteerCand *t0, const SteerCand *tk)
{
    return (tk->cell.crit && !t0->cell.crit) || (tk->landed && !t0->landed) || (tk->cell.flinch_foe && !t0->cell.flinch_foe);
}

/* how far a candidate's rolls sit above the average, in rolls (a damage index step is an eighth): the most ordinary
   roll that does the job wins a tie */
static s32 steer_surprise(const s32 *d)
{
    return d[STC_ACC] + d[STC_CRIT] + d[STC_CHANCE] + d[STC_PAR] + d[STC_DMG] / 8;
}

/* the turn's choice: t[0..n-1] filled for my move i against the foe's committed move kf. Returns the k to play
   (0: no steer) and books the turn in the ledger (every trusted turn under the gate is booked, steered or not) */
static int steer_pick(const Ctx *c, int i, int kf, const SteerCand *t, int n, SteerLedger *L)
{
    s32 e, sum = 0, v0, vb = 0, vk, d0[5], dk[5], db[5], sb = 0, s;
    int k, na = 0, kod, kot, ko_lo = 1, ko_hi = 0, kt_lo = 1, kt_hi = 0, decisive, r0, rb = 0, best = 0, qb = 0, q, j;
    int nko = 0, vis;
    steer_last.booked = 0;
    if (n < 1 || !steer_usable(&t[0]))
        return 0;
    for (k = 0; k < n; k++) {
        if (!steer_usable(&t[k]) || !steer_a(&t[0], &t[k]))
            continue;
        sum += steer_v(c, &t[k], &kod, &kot);
        na++;
        nko += kod;
        ko_lo = kod < ko_lo ? kod : ko_lo, ko_hi = kod > ko_hi ? kod : ko_hi;
        kt_lo = kot < kt_lo ? kot : kt_lo, kt_hi = kot > kt_hi ? kot : kt_hi;
    }
    e = sum / na;
    decisive = ko_lo != ko_hi || kt_lo != kt_hi;
    v0 = steer_v(c, &t[0], &kod, &kot);
    r0 = steer_rank(kod, kot);
    steer_cls(c, i, kf, &t[0], d0);
    for (j = 0; j < 5; j++)
        db[j] = d0[j];
    for (k = 1; k < n; k++) {
        if (!steer_usable(&t[k]) || !steer_a(&t[0], &t[k]))
            continue;
        if ((steer_rules & SR_C) && (!decisive || !steer_room(L->steers, steer_cap)))
            break;
        vk = steer_v(c, &t[k], &kod, &kot);
        steer_cls(c, i, kf, &t[k], dk);
        if ((steer_rules & SR_B) && vk > e && L->bank + e - vk < 0)
            continue;
        for (j = 0; j < 5; j++)                     /* the class guard: no class pushed past its slack */
            if (steer_class && dk[j] > d0[j] && L->cls[j] + dk[j] > steer_slack[j])
                break;
        if (j < 5)
            continue;
        vis = steer_visible(&t[0], &t[k]);
        if ((steer_rules & SR_D) && vis && !steer_room(L->visible, steer_vis))
            continue;
        q = (steer_rules & SR_D) ? !vis : 1;
        s = steer_surprise(dk);
        if (steer_rules & SR_C) {   /* the best knockouts, quiet first, the value nearest E, the most ordinary roll */
            int r = steer_rank(kod, kot);
            if (best && (r < rb || (r == rb && (q < qb || (q == qb && (vk - e > vb - e || (vk == vb && s >= sb)))))))
                continue;
            rb = r;
        } else if (best && (q < qb || (q == qb && (vk < vb || (vk == vb && s >= sb)))))
            continue;               /* the best value, quiet first */
        best = k, vb = vk, qb = q, sb = s;
        for (j = 0; j < 5; j++)
            db[j] = dk[j];
    }
    if (best && ((steer_rules & SR_C) ? rb <= r0 : vb <= v0))
        best = 0;
    if (!best && (steer_rules & SR_B) && steer_bank && !decisive && v0 > 0) {
        /* active banking: a lower roll that changes no knockout, is quiet, raises no class and keeps the hits my move
           needs to knock the foe out */
        s32 d0v = t[0].cell.dmg > 0 ? t[0].cell.dmg : 1, h0 = (c->opp.hp - t[0].cell.dmg + d0v - 1) / d0v;
        for (k = 1; k < n; k++) {
            if (!steer_usable(&t[k]) || !steer_a(&t[0], &t[k]) || steer_visible(&t[0], &t[k]) || t[k].cell.dmg <= 0)
                continue;
            vk = steer_v(c, &t[k], &kod, &kot);
            if (steer_rank(kod, kot) != r0 || vk >= v0 || (best && vk >= vb) ||
                (c->opp.hp - t[k].cell.dmg + d0v - 1) / d0v != h0)
                continue;
            steer_cls(c, i, kf, &t[k], dk);
            for (j = 0; j < 5 && dk[j] <= d0[j]; j++)
                ;
            if (j < 5)
                continue;
            best = k, vb = vk;
            for (j = 0; j < 5; j++)
                db[j] = dk[j];
        }
    }
    if (!best)
        vb = v0;
    vis = best && steer_visible(&t[0], &t[best]);
    L->bank += e - vb;
    for (j = 0; j < 5; j++)
        L->cls[j] += db[j];
    if (best && decisive && L->steers < 255)
        L->steers++;
    if (vis && L->visible < 255)
        L->visible++;
    steer_last.booked = 1;
    steer_last.decisive = decisive;
    steer_last.nominal = (s16)(1000 * nko / na);
    steer_v(c, &t[best], &kod, &kot);
    steer_last.ko = kod;
    steer_last.visible = vis;
    return best;
}
/* ---- steer: end rules ---- */

/* option i of a kind (K_*; a move is K_MOVE, a status move K_MOVE + 3, staying in with a vetoed move K_MOVE + 4)
   against the reply in p */
static s32 value_of(Ctx *c, const Pair *p, int kind, int i)
{
    switch (kind) {
    case K_MOVE: return value_move(c, p, i);
    case K_SWITCH: return value_switch(c, p, i);
    case K_ITEM: return value_item(c, p, i);
    case K_MOVE + 4: return value_stay(c, p, i);
    }
    return value_status(c, p, i);
}

/* an option's value: its value against each move the player may pick this turn, by the odds of each. A reply that
   can miss counts as two branches: a status move that lands or not at its accuracy (on whichever of mine is out after
   a switch), and an attack that can knock my Pokemon out, as the KO (its accuracy times the rolls that reach my HP) or
   the hit it lives through on average, not as its expected damage (a switch values its entry hit itself). When the
   player can knock my active Pokemon out it does so almost always, and a switch-in takes that move */
static s32 mixed1(Ctx *c, const Pair *p, int f, int i)
{
    Pair q = *p;
    const Mon *me = &c->me;
    s32 sum = 0, k1 = 0, k3 = 0, dl = 0, su = 0, fe = 0, fo = 0x7FFFFFFF, hit, surv = 0, top = 0, t[6];
    int k, n = 0, acc, b, split, wb, kw = 0, en = endures(me, &c->opp), fsall = 1;
    const FsCell *fc;
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &c->opp.mv[k];
        if (!p->w[k] || (f == K_SWITCH && p->ko && p->w[k] < 5))
            continue;
        q.rep_prio = m->prio;
        hit = hit_now(c, me, k, c->d_om[k], THEIR_ROLL);
        acc = acc_now(&c->opp, me, m, c->weather);
        split = acc < 100 && sickens(m);
        if (!split && f != K_SWITCH && hit) {
            top = move_damage(&c->opp, me, m, c->d_om[k]) * hits_x10(m) / 10;
            /* a Sash or Sturdy leaves 1 HP whatever the roll: only the miss is apart */
            kw = en && !multi(&c->opp, m) ? (acc < 100 && hit * 100 / acc >= me->hp ? acc : 0) : roll_ko(top, me->hp, acc, 0, &surv);
            if (en && !multi(&c->opp, m)) {
                top = hit * 100 / acc;
                surv = 0;
            }
            split = kw ? 2 : acc < 100 ? 1 : 0;     /* an attack that cannot knock out lands or misses too */
        }
        t[0] = t[1] = t[2] = t[3] = t[4] = t[5] = 0;
        fs.rep = k + 1;
        fc = (f == K_MOVE || f == K_MOVE + 3) && fs_level >= 2 ? fs_get(c, i, 1) : 0;
        if (fc)
            split = 0;
        else
            fsall = 0;
        for (b = 0; b <= (split > 0); b++) {     /* b 1: it missed, or did not knock out */
            wb = !split ? 100 : split == 1 ? (b ? 100 - acc : acc) : b ? 100 - kw : kw;
            q.rep = split == 1 && b ? -1 : k;
            q.opp_hit = split == 2 ? (b ? surv : top) : split && b ? 0 : split ? hit * 100 / acc : hit;
            if (fc) {
                q.rep = fc->f_stopped || fc->f_missed ? -1 : k;
                q.opp_hit = q.rep < 0 ? 0 : fc->f_dmg;
            }
            g_ko1 = g_ko3 = g_dealt = g_sure = 0;
            g_fo = g_fell = -1;
            t[0] += wb * value_of(c, &q, f, i);
            if (g_fell < 0)
                g_fell = q.opp_hit >= me->hp && !(en && !multi(&c->opp, m)) ? 1000 : 0;
            t[1] += wb * g_ko1;
            t[2] += wb * g_ko3;
            t[3] += wb * g_dealt;
            t[4] += wb * g_sure;
            t[5] += wb * g_fell;
            if (g_fo < fo)
                fo = g_fo;
        }
        sum += p->w[k] * (t[0] / 100);
        k1 += p->w[k] * (t[1] / 100);
        k3 += p->w[k] * (t[2] / 100);
        dl += p->w[k] * (t[3] / 100);
        su += p->w[k] * t[4];
        fe += p->w[k] * (t[5] / 100);
        n += p->w[k];
    }
    fs.rep = 0;
    if (!n) {
        g_ko1 = g_ko3 = g_dealt = g_sure = 0;
        g_fo = g_fell = -1;
        sum = value_of(c, p, f, i);
        if (g_fell < 0)
            g_fell = p->opp_hit >= me->hp && !en ? 1000 : 0;
        return sum;
    }
    sum /= n;
    k1 /= n;
    k3 /= n;
    dl /= n;
    fe /= n;
    if (c->opp.status == S_PAR && !(fs_level >= 2 && fsall)) {       /* paralyzed, the foe loses its move a quarter of the time (measured) */
        q = *p;
        q.rep = -1;
        q.opp_hit = 0;
        g_ko1 = g_ko3 = g_dealt = g_sure = 0;
        g_fo = g_fell = -1;
        sum = (3 * sum + value_of(c, &q, f, i)) / 4;
        k1 = (3 * k1 + g_ko1) / 4;
        k3 = (3 * k3 + g_ko3) / 4;
        dl = (3 * dl + g_dealt) / 4;
        fe = 3 * fe / 4 + (g_fell > 0 ? g_fell / 4 : 0);
        if (g_fo < fo)
            fo = g_fo;
    }
    g_ko1 = k1;
    g_ko3 = k3;
    g_dealt = dl;
    g_sure = 2 * su >= 100 * n;
    g_fell = fe;
    g_fo = fo;
    return sum;
}

/* a sleeper's turns asleep are a guess that the turns it slept so far narrow (sleep skips 1-3 turns, measured; each as
   likely, as official): after one it wakes now, sleeps one more or two more (1 in 3 each); after two it wakes now or
   sleeps one more (1 in 2); after three it wakes. read_mon's case counts, and decide adds the others (sleep_cases),
   the foe's and mine; a case where the foe dozes this turn otherwise than in the reply valued has its own (p) */
typedef struct { const struct Pair *p; s16 w; u8 who, sleep; } Alt;    /* who: 0 the foe, 1 my Pokemon on the field */
/* in ITCM RAM, as ai_replace runs mixed too (select_value) */
static Alt g_alt[4] __attribute__((section(".itcm_bss")));
static int g_nalt __attribute__((section(".itcm_bss")));

static void sleep_cases(const Mon *m, int who, const struct Pair *alt)
{
    int n = m->slept, k, frz = m->status == S_FRZ && m->sleep;
    for (k = 0; frz ? !k : m->status == S_SLP && n && k < 3 - n; k++) {
        Alt *a = &g_alt[g_nalt++ & 3];
        a->who = who;
        a->sleep = frz ? 0 : n == 1 ? 2 * k : 1;
        a->w = frz ? 200 : n == 1 ? 333 : 500;      /* a frozen Pokemon thaws one turn in five (official, not measured) */
        a->p = !who && !a->sleep != !m->sleep ? alt : 0;
    }
}

static void set_sleep(Ctx *c, int who, int s)
{
    int k;
    if (who) {
        c->me.sleep = s;
        c->ent_me[MAX_BENCH].sleep = s;
        return;
    }
    c->opp.sleep = s;
    for (k = 0; k <= MAX_BENCH; k++)
        c->ent_foe[k].sleep = s;
}

static s32 mixed(Ctx *c, const Pair *p, int f, int i)
{
    s32 v0 = mixed1(c, p, f, i), k1 = g_ko1, k3 = g_ko3, dl = g_dealt, fe = g_fell, v = v0, s1 = k1, s3 = k3, sd = dl, sf = fe;
    int su = g_sure, fo = g_fo, n, keep;
    for (n = 0; n < g_nalt && n < 4; n++) {
        const Alt *a = &g_alt[n];
        keep = a->who ? c->me.sleep : c->opp.sleep;
        set_sleep(c, a->who, a->sleep);
        v += (mixed1(c, a->p ? a->p : p, f, i) - v0) * a->w / 1000;
        set_sleep(c, a->who, keep);
        s1 += (g_ko1 - k1) * a->w / 1000;
        s3 += (g_ko3 - k3) * a->w / 1000;
        sd += (g_dealt - dl) * a->w / 1000;
        sf += (g_fell - fe) * a->w / 1000;
        su = su && g_sure;
        fo = fo < 0 || g_fo < 0 ? -1 : fo < g_fo ? fo : g_fo;
    }
    g_ko1 = s1;
    g_ko3 = s3;
    g_dealt = sd;
    g_fell = sf;
    g_sure = su;
    g_fo = fo;
    return v;
}

/* the class of my hardest-hitting attack on the foe (`none` without one) */
static int best_cls(const Ctx *c, int none)
{
    int k;
    s32 bestd = 0;
    for (k = 0; k < 4; k++)
        if (c->me.legal[k] && c->me.mv[k].cls && c->d_mo[k] > bestd) {
            bestd = c->d_mo[k];
            none = c->me.mv[k].cls;
        }
    return none;
}

/* stats my move costs or sure-raises me (Close Combat, Draco Meteor; Rapid Spin, Flame Charge), carried into the
   race: my damage for the stat my best attack uses, the player's damage for the defence its reply hits, my speed */
static void user_drops(const Ctx *c, const Pair *p, const MoveInfo *m, Fighter *x, Fighter *y)
{
    const Mon *a = &c->me;
    int k, best = best_cls(c, 0), opp_cls = c->opp.mv[p->opp_slot >= 0 ? p->opp_slot : 0].cls;
    for (k = 0; k < 3; k++) {
        int t = m->rank_type[k], cur, nxt;
        if (!t || t > 5)
            continue;
        cur = a->stage[t - 1];
        nxt = clamp(cur + m->rank_val[k], 0, 12);
        if ((t == 1 && best == 1) || (t == 3 && best == 2))
            x->dmg = stage_mult(x->dmg * 64, nxt) / stage_mult(64, cur);
        else if ((t == 2 && opp_cls == 1) || (t == 4 && opp_cls == 2))
            y->dmg = stage_mult(y->dmg * 64, cur) / stage_mult(64, nxt);
        else if (t == 5)
            x->spe = stage_mult(x->spe * 8, nxt) / stage_mult(8, cur);
    }
}

/* Weakness Policy: a super-effective hit that does not knock its holder out raises its Attack and Sp. Atk by
   four here (it goes off twice, measured; Unburden then doubles its Speed); the foe's damage x64 from then on, 64
   when m does not set it off */
static s32 policy(const Mon *d, const Mon *a, const MoveInfo *m, int yslot)
{
    int cur;
    if (d->item != IT_WEAK__POLICY || !m || !m->cls || yslot < 0 || yslot > 3 || eff_move(a, d, m) <= 1000)
        return 64;
    cur = d->stage[d->mv[yslot].cls == 2 ? 2 : 0];
    return stage_mult(64 * 64, clamp(cur + 4, 0, 12)) / stage_mult(64, cur);
}

static void policy_fight(Fighter *y, const Mon *d, s32 mult)
{
    if (mult == 64)
        return;
    y->dmg = y->dmg * mult / 64;
    y->dmg64 = y->dmg64 * mult / 64;
    y->pdmg = y->pdmg * mult / 64;
    if (d->ability == AB_UNBURDEN) {
        y->spe *= 2;
        y->spe64 *= 2;
    }
}

/* my Weakness Policy: the reply's super effective hit, which mine lives through, boosts my race attack */
__attribute__((noinline)) static void my_policy(const Ctx *c, const Pair *p, Fighter *x, s32 hit)
{
    if ((unsigned)p->rep < 4 && hit < c->me.hp)
        policy_fight(x, &c->me, policy(&c->me, &c->opp, &c->opp.mv[p->rep], p->my_slot));
}

/* what the foe's Weakness Policy going off now (mult: its damage x64 after) costs my Pokemon off the field: each races
   the foe at hp from a free entry, with and without the boost (none for one whose own race attack sets it off anyway,
   as entries counts). When one still beats the boosted foe, it answers it (the replacement sends it) and the cost is
   what it loses; otherwise the foe sweeps, and every loss counts */
static s32 policy_cost(const Ctx *c, s32 mult, s32 hp)
{
    s32 sum = 0, ans = -1, v;
    int i, n, t, u;
    s8 sp;
    for (i = 0; i < c->nbench; i++) {
        Fighter s = c->ent_me[i], b = c->ent_foe[i], s2, b2;
        s.who = WHO_FOLLOW;
        b.hp = b.hp0 = hp;
        s2 = s;
        b2 = b;
        best_rate(&c->bench[i], &c->opp, c->d_bo[i], c->weather, &sp, &n, MY_ROLL, 0);
        v = policy(&c->opp, &c->bench[i], n >= 0 ? &c->bench[i].mv[n] : 0, 0);
        if (v == 64)
            policy_fight(&b2, &c->opp, mult);
        else if (s.dmg >= hp) {     /* its first hit knocks the foe out at hp, before the item goes off */
            b.dmg = b.dmg * 64 / v;
            b.dmg64 = b.dmg64 * 64 / v;
        }
        t = race_core(&s, &b, 0, &n);
        u = race_core(&s2, &b2, 0, &n);
        v = outcome(c, &s, &b, t) - outcome(c, &s2, &b2, u);
        if (v < 0)
            v = 0;
        if (b2.hp <= 0 && s2.hp > 0 && (ans < 0 || v < ans))
            ans = v;
        sum += v;
    }
    return ans >= 0 ? ans : sum;
}

/* the foe's ability answering a hit of m (bank 712; Thermal Exchange and Stamina seen in logs): Thermal Exchange
   (Fire) and Justified (Dark) +1 Attack, Stamina +1 Defense, Weak Armor (physical) -1 Defense and +2 Speed. One stage
   on the race: y's attack if physical, x's attack on that defence if physical, y's Speed */
static void on_hit(const Mon *d, const MoveInfo *m, Fighter *x, Fighter *y)
{
    int st = -1, up = 1, cur;
    if (!m || !m->id || !m->cls)
        return;
    switch (d->ability) {
    case AB_THERMALEXCHG: if (m->type == T_FIRE) st = 0; break;
    case AB_JUSTIFIED: if (m->type == T_DARK) st = 0; break;
    case AB_STAMINA: st = 1; up = hits_x10(m) / 10; break;      /* every hit */
    case AB_WEAK_ARMOR:
        if (m->cls == 1) {
            st = 1;
            up = -1;
            cur = d->stage[4];
            y->spe = restage(y->spe, cur, clamp(cur + 2, 0, 12));
            y->spe64 = restage(y->spe64, cur, clamp(cur + 2, 0, 12));
        }
        break;
    }
    if (st < 0)
        return;
    cur = d->stage[st];
    if (st == 0 && y->cls == 1) {
        y->dmg = restage(y->dmg, cur, clamp(cur + up, 0, 12));
        y->dmg64 = restage(y->dmg64, cur, clamp(cur + up, 0, 12));
    } else if (st == 1 && x->cls == 1)
        x->dmg = restage(x->dmg, clamp(cur + up, 0, 12), cur);
}

/* HP a Pokemon coming in on my side loses to the hazards there; *chip: the poison Toxic Spikes give it */
static s32 hazard_hp(const Ctx *c, const Mon *m, s32 *chip)
{
    int side = c->client & 1, n, gr = grounded(m), hit;
    s32 v = 0;
    *chip = 0;
    if (m->ability == AB_MAGIC_GUARD)
        return 0;
    hit = SIDE_LAYERS(side, SE_STEALTH_ROCK) > 0;
    if (hit)
        v += m->maxhp * eff_permille(T_ROCK, m) / 8000;
    n = SIDE_LAYERS(side, SE_SPIKES);
    if (n && gr) {
        v += m->maxhp / (n >= 3 ? 4 : n == 2 ? 6 : 8);
        hit = 1;
    }
    n = SIDE_LAYERS(side, SE_TOXIC_SPIKES);
    if (n && gr && !has_type(m, T_POISON) && !has_type(m, T_STEEL) && m->status == S_NONE && m->ability != AB_IMMUNITY)
        *chip = m->ability == AB_POISON_HEAL ? -m->maxhp / 8 : n >= 2 ? m->maxhp * 3 / 16 : m->maxhp / 8;
    return v ? v : hit;     /* at least 1 HP: Stealth Rock knocks a Shedinja out (seen in logs) */
}

/* x (my Pokemon xm) takes the player's reply this turn, dmg of its move p->rep. The foe pays that move's recoil, Life
   Orb and contact damage and gets its drain, not its race attack's; recoil and drain follow the damage dealt, not an
   overkill (as in strike): a Brave Bird that knocks out a Pokemon at 80 HP costs its user a third of 80 */
__attribute__((noipa)) static void reply_turn(const Ctx *c, const Pair *p, Fighter *x, const Mon *xm, Fighter *y, s32 dmg)
{
    const Mon *d = &c->opp;
    const MoveInfo *m = (unsigned)p->rep < 4 ? &d->mv[p->rep] : 0;
    s32 before = x->hp;
    take(x, dmg, m && multi(d, m));
    if (!m || dmg <= 0 || !m->cls)
        return;
    y->hp -= life_orb_recoil(d, m) + contact_recoil(d, xm, m);
    if (m->drain > 0 || (d->ability != AB_ROCK_HEAD && d->ability != AB_MAGIC_GUARD))
        y->hp += (before - (x->hp > 0 ? x->hp : 0)) * m->drain / 100;
    if (y->hp > y->maxhp)
        y->hp = y->maxhp;
    ripe(y);
}

/* U-turn and Volt Switch: my best bench Pokemon comes in after the hit and races the foe as the hit left it;
   it takes the foe's reply when I moved first, and comes in free when the reply already hit me. refl: what the foe's
   Counter (Mirror Coat, Metal Burst: its move kc) returns of my hit lands on the newcomer instead (seen in logs) */
static s32 pivot_value(Ctx *c, const Pair *p, s32 foe_hp, int takes_reply, s32 refl, int kc)
{
    const Mon *d = &c->opp;
    s32 best = 0, v;
    int i, k = p->rep;
    for (i = 0; i < c->nbench; i++) {
        Fighter S = c->ent_me[i], B = c->ent_foe[i];
        B.hp = foe_hp;
        ripe(&B);
        if (B.sleep)
            B.sleep--;
        if (refl && eff_move(d, &c->bench[i], &d->mv[kc & 3]))
            take(&S, refl, 0);
        if (takes_reply && k >= 0 && k < 4 && d->legal[k])
            reply_turn(c, p, &S, &c->bench[i], &B, hit_now(c, &c->bench[i], k, c->d_ob[i][k], 925));
        reply_after(c, p, &S, &c->bench[i], &B);
        if (S.hp > 0) {
            end_of_turn(&S);
            end_of_turn(&B);
        }
        v = S.hp > 0 ? race(c, S, B, 1) : outcome(c, &S, &B, 1);
        if (!i || v > best)
            best = v;
    }
    return best;
}

/* the chances (per-mille) that using the move each turn knocks out a foe at hp: by turn 1 (*p1) and summed over
   turns 1-3. Each use hits at acc percent for mind..maxd; uses: how many of those turns it can be used, after
   `delay` turns it sleeps through; endure: Sash or Sturdy stops a KO by the first hit; loss: what the foe loses
   each turn on its own (a heal is negative); berry: what its Sitrus Berry heals before a KO by a later hit */
static s32 ko_chance(s32 hp, s32 mind, s32 maxd, int acc, int uses, int delay, int endure, s32 loss, s32 berry, s32 *p1)
{
    s32 dist[4] = { 1000, 0, 0, 0 }, sum = 0, p = 0, need, q;   /* dist[j]: j hits so far */
    int t, j, u;
    for (t = 1; t <= 3; t++) {
        u = t - delay;                                          /* uses so far */
        if (u >= 1 && u <= uses) {
            for (j = u; j > 0; j--)
                dist[j] = (dist[j] * (100 - acc) + dist[j - 1] * acc) / 100;
            dist[0] = dist[0] * (100 - acc) / 100;
            p = 0;
            for (j = endure ? 2 : 1; j <= u; j++) {
                need = hp - (t - 1) * loss + (j > 1 ? berry : 0);
                q = j * mind >= need ? 1000 : j * maxd < need ? 0 : 1000 * (j * maxd - need) / (j * (maxd - mind) + 1);
                p += dist[j] * q / 1000;
            }
        }
        if (t == 1)
            *p1 = p;
        sum += p;
    }
    return sum;
}

/* percent of rolls 85-100 of a hit doing mind..maxd that reach hp */
static s32 kop_at(s32 mind, s32 maxd, s32 hp)
{
    return mind >= hp ? 100 : maxd < hp ? 0 : (maxd - hp) * 100 / (maxd - mind + 1);
}

/* percent odds that a move of 2-5 hits (or another range) hits n times: 35, 35, 15, 15 */
static int hit_odds(const MoveInfo *m, int n)
{
    if (m->hits_min == 2 && m->hits_max == 5)
        return n <= 3 ? 35 : 15;
    return 100 / (m->hits_max - m->hits_min + 1);
}

/* a Choice item locks its holder into the move it uses (Trick and Switcheroo give the item away) */
static int choice_locks(const Mon *a, const MoveInfo *m)
{
    return (a->item == IT_CHOICE_BAND || a->item == IT_CHOICE_SPECS || a->item == IT_CHOICE_SCARF) &&
           m->id != MV_TRICK && m->id != MV_SWITCHEROO;
}


/* A1: raw, my move m's damage on d, once Protean or Libero made d its reply rm's type, which it does before every move
   it uses (census s052_g1 turns 14-16: Pluck made it Flying, then Poison Fang Poison, then Pluck Flying again; my
   Ground move "doesn't affect" it) */
__attribute__((noinline)) static s32 protean_raw(const Mon *a, const Mon *d, const MoveInfo *m, const MoveInfo *rm, s32 raw)
{
    Mon t = *d;
    s32 e0 = eff_move(a, d, m);
    t.types[0] = t.types[1] = rm->type;
    t.types[2] = T_NONE;
    return e0 ? raw * eff_move(a, &t, m) / e0 : raw;
}

/* the value of using my move `slot` this turn */
static s32 value_move(Ctx *c, const Pair *p, int slot)
{
    const Mon *a = &c->me, *d = &c->opp;
    const MoveInfo *m = &a->mv[slot];
    Fighter A, B;
    s32 raw = move_damage(a, d, m, c->d_mo[slot]);
    int slower = !(m->prio > p->rep_prio || (m->prio == p->rep_prio && faster(eff_speed(a, c->weather), eff_speed(d, c->weather))));
    int piv, kr = p->rep;
    const MoveInfo *rm = kr >= 0 && kr < 4 ? &d->mv[kr] : 0;      /* the reply valued */
    if (A1(A1_PROTEAN) && slower && rm && rm->type != T_NONE && (d->ability == AB_PROTEAN || d->ability == AB_LIBERO) && raw)
        raw = protean_raw(a, d, m, rm, raw);
    if (doubles_first(m) && slower)
        raw /= 2;
    if (doubles_last(m) && slower && p->opp_hit)
        raw *= 2;
    if (slower && rm && p->opp_hit < a->hp) {
        /* the reply lands first: its hit weakens my Eruption, its burn my physical hit (Prankster Will-O-Wisp) */
        if (m->efx == X_ERUPT)
            raw = raw * (a->hp - p->opp_hit) / a->hp;
        if (sickens(rm) && rm->sick == S_BRN && !status_blocked(c, d, a, rm) && burn_cuts(a, slot))
            raw /= 2;
    }
    int fl;                         /* percent chance my hit makes the foe flinch and lose its reply this turn */
    int fc;                         /* the foe's Counter, Mirror Coat or Metal Burst answers this hit: what it returns x10 */
    s32 wp_now, wp_race;            /* Weakness Policy set off by this move on a hit, or by my race attack later */
    s32 hitsx10 = hits_x10(m), acc = move_acc(a, d, m, c->weather);
    s32 maxd = raw * hitsx10 / 10, mind = maxd * 85 / 100, avgd = maxd * 925 / 1000;
    s32 kop, v_hit_ko = 0, v_hit = 0, v_miss = 0, total, fell[3];
    s32 act, hp_ko = d->hp, ko3, p1;    /* act: per-mille odds that I use the move this turn */
    int b, k, kc = 0, me_first, acted = 1, uses, n, delay;    /* acted: I get my attack off this turn (not knocked out first) */
    const FsCell *fsc;
    s32 fin = 0;                        /* Endeavor: my best priority attack (fin_prio) finishes what it left */
    s8 fin_prio = 0;
    s32 prate = m->prio > 0 && m->cls ? expected_at(a, d, raw, m, c->weather, MY_ROLL) : 0;
    int charging = charges(a, m, c->weather);
    /* asleep, the move goes off on the turn it wakes, when it acts: value a turn it sleeps through as that, which
       keeps switching honest, and let WAKE_CREDIT pick the attack for waking */
    int dozing = a->status == S_SLP && a->sleep && m->id != MV_SNORE && m->id != MV_SLEEP_TALK;
    int lock = m->cls && choice_locks(a, m);

    pair_fighters(c, p, &A, &B);
    if (m->id == MV_FAKE_OUT)                   /* the turn it buys feeds my priority attack */
        prime(&A, a, d, c->d_mo, c->weather, MY_ROLL);
    if (m->id == MV_SLEEP_TALK) {               /* calls one of my other moves at random */
        s32 sum = 0;
        int n = 0;
        for (k = 0; k < 4; k++)
            if (k != slot && a->mv[k].id && a->mv[k].cls) {
                sum += move_damage(a, d, &a->mv[k], c->d_mo[k]) * 925 / 1000;
                n++;
            }
        avgd = maxd = mind = n ? sum / n : 0;
        acc = 100;
    }
    if (fixed_damage(a, d, m, &raw))
        avgd = maxd = mind = raw;
    if ((m->id == MV_SLEEP_TALK || m->id == MV_SNORE) && !(a->status == S_SLP && a->sleep))    /* they fail on the turn it wakes */
        avgd = maxd = mind = 0;
    if (lock) {                     /* a Choice item locks me into this attack: the race goes on with it */
        A.dmg = m->id == MV_FAKE_OUT ? 0 : move_rate(a, d, m, c->d_mo[slot], c->weather, MY_ROLL);
        A.prio = m->prio;
        /* locked into Sucker Punch, it fails on every turn the foe uses a status move ("But it failed!", census s045_g1
           turns 1-2): when the foe's odds of a status move are a third or more, the race loses one more of my turns */
        if (A1B(A1B_SUCKER) && m->id == MV_SUCKER_PUNCH) {
            int hit = 0, all = 0;
            for (k = 0; k < 4; k++) {
                all += p->w[k];
                hit += d->mv[k].cls ? p->w[k] : 0;
            }
            A.recharge = 3 * hit < 2 * all;
        }
    }
    for (k = 0; k < 4 && m->id == MV_ENDEAVOR && !lock; k++) {     /* it leaves the foe to my best priority attack */
        s32 e = move_damage(a, d, &a->mv[k], c->d_mo[k]) * MY_ROLL / 1000;
        if (a->legal[k] && a->mv[k].prio > A.prio && e > fin) {
            fin = e;
            fin_prio = a->mv[k].prio;
        }
    }
    if (m->id == MV_COUNTER || m->id == MV_MIRROR_COAT || m->id == MV_METAL_BURST) {   /* returns the hit it took */
        int r = rm ? returns10(m, rm->cls) : 0;
        s32 taken = r ? p->opp_hit : 0;
        if (taken >= a->hp)
            taken = endures(a, d) && !multi(d, rm) ? a->hp - 1 : 0;
        if (r && rm->hits_max > 1)      /* several hits: it returns twice the last (seen in logs) */
            taken = taken * 10 / hits_x10(rm);
        avgd = maxd = mind = eff_move(a, d, m) ? r * taken / 10 : 0;
        acc = 100;
    }
    arm(&A, a, d, !lock ? p->my_slot : A.dmg ? slot : -1);
    arm(&B, d, a, p->opp_slot);
    if (!lock)
        counter_fight(&A, a, d, p->opp_slot, p->opp_rate);
    counter_fight(&B, d, a, p->my_slot, p->my_rate);
    me_first = m->prio > p->rep_prio || (m->prio == p->rep_prio && faster(A.spe, B.spe));
    reply_after(c, p, &A, a, &B);
    my_policy(c, p, &A, p->opp_hit);
    if (first(&A, &B, 1) || B.dmg < A.hp)     /* my race attack lands and feeds its ability */
        on_hit(d, lock ? m : p->my_slot >= 0 ? &a->mv[p->my_slot] : 0, &A, &B);
    if (rm && !rm->cls && !me_first && A.sleep && !a->status)    /* the reply puts me to sleep before I move */
        dozing = 1;
    piv = m->efx == X_PIVOT && c->nbench && !charging && !dozing;
    if (m->id == MV_SUCKER_PUNCH) {     /* works only when the foe attacks this turn and I move first */
        if (!(rm && rm->cls) || !me_first)
            avgd = maxd = mind = 0;
    }
    if (m->id == MV_METAL_BURST && me_first)     /* nothing to return yet */
        avgd = maxd = mind = 0;
    if (m->id == MV_FOCUS_PUNCH) {      /* moves last and fails if an attack lands on me first */
        if (rm && rm->cls && p->opp_hit > 0)
            avgd = maxd = mind = 0;
    }
    /* asleep, it uses the move only after the turns it sleeps through (delay; the reply's sleep move counts at its
       accuracy in mixed). act: the odds it is still there to use it, when a reply lands first (asleep, always): none in
       the branch where that reply knocks it out (mixed weighs that branch by accuracy and rolls), less its flinch */
    delay = dozing ? (A.sleep ? A.sleep : 1) : 0;
    act = 1000;
    if ((!me_first || dozing) && rm && rm->cls && !charges(d, rm, c->weather)) {
        if (p->opp_hit >= a->hp && !(endures(a, d) && !multi(d, rm)))
            act = 0;
        if (!dozing && can_flinch(a, d))
            act = act * (100 - rm->flinch) / 100;
    }
    if (A.para && (!me_first || a->status == S_PAR))     /* paralyzed (or by the faster reply): lost 1 time in 4 */
        act = act * 3 / 4;
    fsc = m->cls && !charging && !dozing && !delayed(m) ? fs_get(c, slot, 0) : 0;
    if (fsc) {
        act = 1000;
        if ((!me_first || dozing) && rm && rm->cls && !charges(d, rm, c->weather) && p->opp_hit >= a->hp &&
            !(endures(a, d) && !multi(d, rm)))
            act = 0;
        if (fsc->stopped || (fs_level >= 2 && fsc->flinched))
            act = 0;
        else if (fs_level < 2 && !me_first && rm && rm->cls && can_flinch(a, d))
            act = act * (100 - rm->flinch) / 100;
        acc = fsc->missed ? 0 : 100;
        if (!fsc->missed && fsc->dmg > 0)
            avgd = maxd = mind = fsc->dmg;
    }
    if (unreachable(c, m, rm, me_first))
        acc = 0;
    /* the foe's Counter, Mirror Coat or Metal Burst answers this hit: it is the reply valued, or the reply is an
       attack the foe would rather swap for it (when that hurts more) */
    fc = 0;
    if (m->cls && avgd && rm && (rm->id == MV_COUNTER || rm->id == MV_MIRROR_COAT || rm->id == MV_METAL_BURST)) {
        fc = answer10(d, a, kr, m->cls);
        kc = kr;
    } else if (m->cls && avgd && rm && rm->cls) {
        kc = counter_slot(d, a, m->cls);
        fc = kc >= 0 ? returns10(&d->mv[kc], m->cls) : 0;
        if (fc * avgd / hitsx10 <= p->opp_hit)
            fc = 0;
    }
    /* the uses of the three turns: after its sleep, until the foe's race attack (or the hit its Counter returns each
       time) knocks it out */
    uses = 3;
    n = fc ? fc * avgd / hitsx10 : 0;
    if (n < p->opp_rate)
        n = p->opp_rate;
    if (n > 0) {
        s32 pd = me_first && B.pprio > m->prio && B.pdmg < a->hp ? B.pdmg : 0;    /* its priority finisher goes first */
        n = (a->hp - pd + n - 1) / n + (A.endure && !B.multi);
        uses = clamp((me_first ? n : n - 1) - delay, !delay, 3);
    }
    if ((self_ko_move(m->id) || m->id == MV_FAKE_OUT || ((m->flags >> F_RECHARGE) & 1)) && uses > 1)
        uses = 1;
    /* a Sitrus Berry heals between the hits of a move that hits several times (seen in logs) */
    if (d->item == IT_SITRUS_BERRY && m->hits_max > 1 && raw < d->hp && 2 * d->hp > d->maxhp)
        hp_ko += d->maxhp / 4;
    kop = kop_at(mind, maxd, hp_ko);
    ko3 = p1 = 0;
    if (m->hits_min < m->hits_max && raw > 0) {     /* the hit count varies: each count at its odds */
        kop = 0;
        for (n = m->hits_min; n <= m->hits_max; n++) {
            s32 q1;
            kop += hit_odds(m, n) * kop_at(raw * n * 85 / 100, raw * n, hp_ko);
            ko3 += hit_odds(m, n) * ko_chance(hp_ko, raw * n * 85 / 100, raw * n, acc, uses, delay, 0, B.chip + B.recoil, 0, &q1) / 100;
            p1 += hit_odds(m, n) * q1 / 100;
        }
        kop /= 100;
    } else if (!charging)
        ko3 = ko_chance(hp_ko, mind, maxd, acc, uses, delay, endures(d, a) && !multi(a, m), B.chip + B.recoil, B.berry, &p1);
    if (endures(d, a) && !multi(a, m))
        kop = 0;
    if (fsc && !fsc->missed && fsc->dmg > 0) {
        kop = fsc->dmg >= d->hp ? 100 : 0;
        p1 = kop * 10;
        if (ko3 < p1)
            ko3 = p1;
    }
    if (charging || m->efx == X_FANG || delayed(m))    /* Super Fang never knocks out on its own */
        ko3 = p1 = 0;
    if (delayed(m))                      /* it lands two turns later: no KO now (the race takes the damage as dealt) */
        kop = 0;
    wp_now = policy(d, a, m, p->opp_slot);
    wp_race = policy(d, a, p->my_slot >= 0 ? &a->mv[p->my_slot] : 0, p->opp_slot);
    /* Fake Out on my first turn out always, any other flinching hit at its odds, when I move first */
    fl = !me_first || !m->cls || charging || dozing || !can_flinch(d, a) ? 0 : m->id == MV_FAKE_OUT ? 100 : m->flinch;
    if (fsc && fl)
        fl = fsc->flinch_foe ? 100 : 0;
    if (m->id == MV_FAKE_OUT && fl == 100 && p->my_slot >= 0 && !lock) {
        /* the free hit, the foe skips its turn, then my best attack on what is left: KOs by turns 2 and 3 */
        const MoveInfo *bm = &a->mv[p->my_slot];
        s32 bx = move_damage(a, d, bm, c->d_mo[p->my_slot]) * hits_x10(bm) / 10, rem = d->hp - avgd - B.chip, q1, sum;
        int u2 = 2;
        if (p->opp_rate > 0) {
            n = (a->hp + p->opp_rate - 1) / p->opp_rate;
            u2 = clamp(first(&A, &B, 1) ? n : n - 1, 0, 2);
        }
        if (rem > 0 && bx > 0 && u2) {
            sum = ko_chance(rem, bx * 85 / 100, bx, move_acc(a, d, bm, c->weather), u2, 0, 0, B.chip + B.recoil, 0, &q1);
            ko3 += (1000 - p1) * (q1 + (sum - q1) / 2) / 1000;
        }
        g_fo = avgd < d->hp ? avgd : d->hp - 1;
    }

    for (b = 0; b < 3; b++) {        /* 0 hit and KO, 1 hit without KO, 2 miss */
        s32 vb = 0, fb = 0;
        int r;
        for (r = 0; r < 2; r++) {      /* r 1: the foe flinched */
            int w = b == 2 ? (r ? 0 : 100) : r ? fl : 100 - fl;
            Fighter x = A, y = B;
            s32 dealt, v, rep = p->opp_hit, yd;
            int mf = me_first, landed = 0;
            if (!w)
                continue;
            if (b < 2 && m->quality == Q_DAMAGE_EFFECT_USER)
                user_drops(c, p, m, &x, &y);
            yd = y.dmg;                   /* the foe's damage once my move lowered my defence; a reply after it meets that */
            if (mf && B.dmg)
                rep = rep * (yd * 64 / B.dmg) / 64;
            dealt = b == 2 || charging || dozing ? 0 : b == 0 ? y.hp : (avgd < y.hp ? avgd : y.hp - 1);
            if (fc && b == 1) {           /* it moves last; after a KO or a miss it is the foe's attack that counts */
                mf = 1;
                rep = fc * dealt / hitsx10;   /* twice the last hit */
            }
            if (b == 1 && mf)
                rep = rep * wp_now / 64;
            if (m->efx == X_GLAIVE && mf)     /* the reply after it lands double */
                rep *= 2;
            if ((a->status == S_SLP || dozing) && x.sleep)    /* a turn of sleep passes whatever the move */
                x.sleep--;
            if (b == 1 && piv) {          /* the hit, then a switch: my Pokemon is kept */
                Fighter xx = A;
                if (!mf)
                    take(&xx, rep, B.multi);
                if (xx.hp > 0) {
                    vb += w * (worth(xx.hp, xx.maxhp) - worth(a->hp, a->maxhp) + pivot_value(c, p, d->hp - dealt, mf && !r && !fc, r ? 0 : rep * !!fc, kc));
                    continue;
                }
            }
            if (!mf)
                reply_turn(c, p, &x, a, &y, rep);
            if (b == 1 && x.hp <= 0)
                acted = 0;
            if (x.hp > 0) {
                if (b == 0 && dealt)          /* the KO takes what a draining reply left it, not what it had */
                    dealt = y.hp;
                if (m->id == MV_ENDEAVOR && b < 2)
                    dealt = y.hp > x.hp ? y.hp - x.hp : 0;
                y.hp -= dealt;
                landed = dealt > 0;
                if (dealt > 0)
                    x.hp -= life_orb_recoil(a, m) + contact_recoil(a, d, m);
                if (m->drain > 0 || (m->drain < 0 && a->ability != AB_ROCK_HEAD && a->ability != AB_MAGIC_GUARD))
                    x.hp += dealt * m->drain / 100;
                if (self_ko_move(m->id) && !dozing)
                    x.hp = 0;
                if (x.hp > x.maxhp)
                    x.hp = x.maxhp;
                ripe(&x);
                ripe(&y);
                if (rm && rm->efx == X_ERUPT)     /* its Eruption weakens with the HP my hit took */
                    rep = rep * y.hp / d->hp;
                if (mf && y.hp > 0 && x.hp > 0 && !r)
                    reply_turn(c, p, &x, a, &y, rep);
            }
            if (y.hp > y.maxhp)
                y.hp = y.maxhp;
            if (y.hp <= 0 && !mf && rm && rm->efx == X_DESTINY)     /* its Destiny Bond, up first, takes mine down too */
                x.hp = 0;
            policy_fight(&y, d, b == 1 && wp_now != 64 ? wp_now : wp_race);
            if (b == 1 && landed)
                on_hit(d, m, &x, &y);
            if (!lock && p->my_free > p->my_rate && y.hp < d->hp && p->my_free >= y.hp)    /* hurt, it cannot live to Counter */
                x.dmg = p->my_free;
            if (x.hp > 0 && y.hp > 0) {
                end_of_turn(&x);
                end_of_turn(&y);
                if ((m->flags >> F_RECHARGE) & 1 && !dozing)
                    x.recharge = 1;
                if (fin >= y.hp) {
                    x.dmg = fin;
                    x.prio = fin_prio;
                }
                if (m->efx == X_GLAIVE && !mf)    /* the faster foe's next hit lands double, before my next move */
                    x.hp -= y.dmg;
                v = race(c, x, y, 1);
                if (m->prio > 0 && prate && m->id != MV_FAKE_OUT) {     /* or keep using this priority move: moving first every turn can win the race */
                    Fighter x2 = x;
                    s32 v2;
                    x2.dmg = prate;
                    x2.fang = 0;
                    x2.prio = m->prio;
                    x2.multi = multi(a, m);
                    x2.flinch = can_flinch(d, a) ? m->flinch : 0;
                    v2 = race(c, x2, y, 1);
                    if (v2 > v)
                        v = v2;
                }
            } else {
                v = outcome(c, &x, &y, 1);
                fb += w * (y.hp > 0);         /* mine fell, for nothing */
                /* the tempo of a KO now: not when the foe falls to its end-of-turn damage anyway */
                if (y.hp <= 0 && x.hp > 0 && d->hp > B.chip)
                    v += KO_TEMPO;
                /* drowsy, mine falls asleep at this turn's end: the foe's next Pokemon gets the turns it sleeps through
                   (two, at half a turn's tempo each, as a switch out keeps them) */
                if (y.hp <= 0 && x.hp > 0 && x.drowsy == 1 && c->opp_others)
                    v -= TEMPO;
            }
            vb += w * v;
        }
        fell[b] = fb;
        if (b == 0) v_hit_ko = vb / 100; else if (b == 1) v_hit = vb / 100; else v_miss = vb / 100;
    }
    if (wp_now != 64 && !charging && !dozing)       /* the boost my hit sets off stays for the rest of my team */
        v_hit -= policy_cost(c, wp_now, clamp(d->hp - avgd, 1, d->hp));
    k = acc * act / 1000;            /* flinched by a faster reply, my move is lost as when it misses */
    total = (k * (kop * v_hit_ko + (100 - kop) * v_hit) / 100 + (100 - k) * v_miss) / 100;
    g_fell = (k * (kop * fell[0] + (100 - kop) * fell[1]) / 100 + (100 - k) * fell[2]) / 10;
    if (dozing)
        total += (acted ? WAKE_CREDIT : WAKE_CREDIT / 4) * (acc * (avgd < d->hp ? avgd : d->hp) / 100) / d->maxhp;
    else if (!charging)      /* knocked out before it moves, the attack only matters if the foe misses or rolls low */
        total += DAMAGE_CREDIT * act / 1000 * (acc * (avgd < d->hp ? avgd : d->hp) / 100) / d->maxhp;
    g_ko1 = p1 * act / 1000;
    g_ko3 = ko3 * act / 1000;
    g_sure = p1 >= 900 && act >= 500 && !self_ko_move(m->id);
    g_dealt = charging || dozing ? 0 : act * acc / 100 * (avgd < d->hp ? avgd : d->hp) / d->maxhp;
    if (g_fo >= 0 && act < 1000)
        g_fo = -1;
    /* after a KO with Glaive Rush the foe's next Pokemon, when faster, hits it double before it moves again: one more hit
       (the foe on the field's stands in) */
    if (m->efx == X_GLAIVE && c->spare.bpp && faster(eff_speed(&c->spare, c->weather), eff_speed(a, c->weather)))
        total -= acc * kop / 100 * (worth(a->hp, a->maxhp) - worth(a->hp - p->opp_rate, a->maxhp)) / 100;
    if (kop >= 100 && acted && !dozing)       /* among sure KOs, the bigger hit (margin against rolls and what the data misses) */
        total += clamp((mind - d->hp) * 20 / d->hp, 0, 20);
    if (m->quality == Q_DAMAGE_EFFECT_USER)      /* a clean move wins over one that costs stats, all else equal */
        for (k = 0; k < 3; k++)
            if (m->rank_type[k] && m->rank_val[k] < 0)
                total += 5 * m->rank_val[k];
    return total;
}

static s32 boost_carry(const Ctx *c, int slot, s32 hp);

/* the foe's reply this turn when my action is not an attack: Sucker Punch fails */
static s32 passive_hit(const Ctx *c, const Pair *p)
{
    int k = p->rep;
    return k >= 0 && k < 4 && c->opp.mv[k].id == MV_SUCKER_PUNCH ? 0 : p->opp_hit;
}

/* the hit chance of d's move k on a at evasion stage eva (6 neutral): 3/(3+n) or (3+n)/3 by the stage gap (measured) */
static s32 hit_at(const Mon *d, const Mon *a, int k, int eva)
{
    const MoveInfo *m = &d->mv[k];
    int n = clamp(d->stage[5] - eva, -6, 6), acc = m->acc;
    if (acc > 100 || d->ability == AB_NO_GUARD || a->ability == AB_NO_GUARD)
        return 100;
    acc = n >= 0 ? acc * (3 + n) / 3 : acc * 3 / (3 - n);
    return acc > 100 ? 100 : acc;
}

/* my paralyzed Pokemon's move v is lost a quarter of the time: a turn where only the foe's reply lands (x, y before it) */
static s32 lost_turn(const Ctx *c, const Pair *p, Fighter x, Fighter y, s32 hit, s32 v)
{
    reply_turn(c, p, &x, &c->me, &y, hit);
    return (3 * v + (x.hp > 0 ? race(c, x, y, 1) : outcome(c, &x, &y, 1))) / 4;
}

/* status moves: inflict a status, raise my stats, heal, or anything else */
static s32 value_status(Ctx *c, const Pair *p, int slot)
{
    const Mon *a = &c->me, *d = &c->opp;
    const MoveInfo *m = &a->mv[slot];
    Fighter A, B, A0, B0;           /* A0, B0: before the reply */
    Pair q = *p;
    int me_first;
    int acc = move_acc(a, d, m, c->weather), k, credit = 1, fm, troom = 0, tr0, pz, lost = 0;
    int ocls = d->mv[p->opp_slot >= 0 ? p->opp_slot : 0].cls;     /* the kind of the player's best attack */
    s32 v_ok, v_miss, bonus = 0, lasting = 0, hit = passive_hit(c, p), own, alive = 1;    /* alive: my HP after the race */
    int stuck = 0;                  /* A2_SETUP: my boost leaves me no attack on the foe in front */
    Fighter x, y, xl, yl;           /* xl, yl: my faster move paralyzed the foe, which then loses its reply */

    pair_fighters(c, p, &A, &B);
    me_first = m->prio > p->rep_prio || (m->prio == p->rep_prio && faster(A.spe, B.spe));
    k = p->rep;                     /* flinched by a faster reply, the move is lost as when it misses */
    if (!me_first && k >= 0 && k < 4 && d->mv[k].cls && !charges(d, &d->mv[k], c->weather) && can_flinch(a, d))
        acc = acc * (100 - d->mv[k].flinch) / 100;
    if (unreachable(c, m, k >= 0 && k < 4 ? &d->mv[k] : 0, me_first))
        acc = 0;
    k = choice_locks(a, m);         /* locked into it, the race has no attack */
    if (k)
        A.dmg = 0;
    arm(&A, a, d, k ? -1 : p->my_slot);
    arm(&B, d, a, p->opp_slot);
    own = B.dmg;
    if (!k)
        counter_fight(&A, a, d, p->opp_slot, p->opp_rate);
    counter_fight(&B, d, a, p->my_slot, p->my_rate);
    if (B.dmg <= own)               /* own: its own damage when it would rather return my hits (Counter, Mirror Coat) */
        own = -1;
    policy_fight(&B, d, policy(d, a, p->my_slot >= 0 ? &a->mv[p->my_slot] : 0, p->opp_slot));
    A0 = A;
    B0 = B;
    reply_after(c, p, &A, a, &B);
    my_policy(c, p, &A, m->efx == X_PROTECT ? a->hp : hit);     /* a Protect that works blocks the hit that sets it off */
    if (!k && (first(&A, &B, 1) || B.dmg < A.hp)) {
        on_hit(d, p->my_slot >= 0 ? &a->mv[p->my_slot] : 0, &A, &B);
        on_hit(d, p->my_slot >= 0 ? &a->mv[p->my_slot] : 0, &A0, &B0);
    }

    x = A;
    y = B;
    if ((!me_first && A.sleep && !a->status) || (a->status == S_SLP && a->sleep)) {
        /* the reply puts me to sleep before I move, or I sleep through this turn: the move is lost, and the turn is one
           of those it sleeps through */
        reply_turn(c, p, &x, a, &y, hit);
        x.sleep--;
        return x.hp > 0 ? race(c, x, y, 1) : outcome(c, &x, &y, 1);
    }
    pz = A.para && (!me_first || a->status == S_PAR);    /* paralyzed (or by the faster reply): the move is lost 1 time in 4 */
    if (m->efx == X_PROTECT) {                            /* nothing lands this turn; the end-of-turn damage still does */
        int odds = pz ? 75 : 100;                        /* a third as likely for each one in a row before it */
        s32 v_fail;
        for (k = 0; k < a->protects && k < 4; k++)
            odds /= 3;
        reply_turn(c, p, &x, a, &y, hit);                /* it failed: a wasted turn */
        g_fell = x.hp > 0 ? 0 : (100 - odds) * 10;
        if (x.hp > 0)
            end_of_turn(&x);
        end_of_turn(&y);
        v_fail = x.hp > 0 && y.hp > 0 ? race(c, x, y, 1) : outcome(c, &x, &y, 1);
        /* it worked: the hit is blocked (what the reply does besides is only put off, as the race has it); and a foe
           that can boost may take the free turn for that instead (the original AI does not see the Protect coming) */
        v_ok = 0x7FFFFFFF;
        for (k = -1; k < 4; k++) {
            int r = k < 0 ? p->rep : k;
            if (k >= 0 && (k == p->rep || !d->legal[k] || !boost_kind(&d->mv[k]) || !foe_status_ok(c, a, &d->mv[k])))
                continue;
            x = k < 0 ? A : A0;
            y = k < 0 ? B : B0;
            q.rep = r;
            if (k >= 0)
                reply_after(c, &q, &x, a, &y);
            end_of_turn(&x);
            end_of_turn(&y);
            if (a->ability == AB_SPEED_BOOST) {          /* the turn it buys still raises my Speed */
                int j, slow = !faster(x.spe, y.spe);
                s32 e;
                x.spe = x.spe * 3 / 2;
                for (j = 0; j < 4 && slow && faster(x.spe, y.spe); j++)    /* moving first now, Fishious Rend doubles */
                    if (a->legal[j] && doubles_first(&a->mv[j]) &&
                        (e = 2 * move_rate(a, d, &a->mv[j], c->d_mo[j], c->weather, MY_ROLL)) > x.dmg)
                        x.dmg = e;
            }
            v_miss = x.hp <= 0 || y.hp <= 0 ? outcome(c, &x, &y, 1) : race(c, x, y, 1) - 120;
            if (v_miss < v_ok)
                v_ok = v_miss;
        }
        return (odds * v_ok + (100 - odds) * v_fail) / 100;
    }
    if (m->id == MV_REFLECT || m->id == MV_LIGHT_SCREEN || m->id == MV_AURORA_VEIL) {
        /* the foe's attacks of that kind do half for the next turns, to whichever of mine is out */
        int match = ocls && ((m->id == MV_REFLECT && ocls == 1) || (m->id == MV_LIGHT_SCREEN && ocls == 2) || m->id == MV_AURORA_VEIL);
        reply_turn(c, p, &x, a, &y, me_first && match ? hit / 2 : hit);
        if (x.hp > 0) {
            g_fell = 0;                                  /* up first, it keeps mine alive through the hit */
            if (match) {
                y.dmg /= 2;
                y.dmg64 /= 2;
                bonus = c->nbench ? 40 : 0;
            }
            end_of_turn(&x);
            end_of_turn(&y);
        }
        v_ok = x.hp > 0 ? (y.hp > 0 ? race(c, x, y, 1) : outcome(c, &x, &y, 1)) + bonus : outcome(c, &x, &y, 1);
        return pz ? lost_turn(c, p, A, B, hit, v_ok) : v_ok;
    }
    if (self_heal(m)) {
        s32 heal = m->id == MV_REST ? a->maxhp : a->maxhp * heal_pct(m, c->weather) / 100;
        if (!me_first)
            reply_turn(c, p, &x, a, &y, hit);
        if (x.hp <= 0)
            return outcome(c, &x, &y, 1);
        x.hp = x.hp + heal > x.maxhp ? x.maxhp : x.hp + heal;
        if (m->id == MV_REST) {
            x.sleep = 2;
            x.chip = 0;
        }
        if (me_first)
            reply_turn(c, p, &x, a, &y, hit);
        if (x.hp <= 0)
            return outcome(c, &x, &y, 1);
        g_fell = 0;
        end_of_turn(&x);
        end_of_turn(&y);
        v_ok = race(c, x, y, 1);
        return pz ? lost_turn(c, p, A, B, hit, v_ok) : v_ok;
    }
    if (pz)
        acc = acc * 3 / 4;
    /* it fails or misses: a wasted turn */
    reply_turn(c, p, &x, a, &y, hit);
    v_miss = x.hp > 0 ? race(c, x, y, 1) : outcome(c, &x, &y, 1);
    fm = x.hp <= 0;

    /* it works: after the reply when I am slower; before it when I am faster, and the reply meets what it did. Taunted
       first, the foe loses its status move; asleep first, its sleep move waits until it wakes (two turns on average) */
    k = me_first && m->efx == X_TAUNT && p->rep >= 0 && !d->mv[p->rep].cls;
    x = k ? A0 : A;
    y = k ? B0 : B;
    if (me_first && sickens(m) && m->sick == S_SLP && x.sleep) {
        x.sleep = 0;
        x.drowsy = 2;
    }
    if (!me_first)
        reply_turn(c, p, &x, a, &y, hit);
    if (x.hp > 0) {
        if (m->target != TARGET_USER && m->quality == Q_SICK && m->id != MV_LEECH_SEED) {
            switch (m->sick) {
            case C_YAWN: y.drowsy = 2; break;            /* asleep at the next turn's end (measured) */
            case S_SLP: y.sleep = 2; break;
            case S_FRZ: y.sleep = 3; break;
            case S_PAR: paralyze(&y, d); break;
            case S_BRN:
                if (burn_cuts(d, p->opp_slot)) {
                    y.dmg /= 2;
                    y.dmg64 /= 2;
                }
                y.chip += tick(d->maxhp, 16);
                break;
            case S_PSN:
                if (m->id == MV_TOXIC)
                    y.tox = 1;
                else
                    y.chip += tick(d->maxhp, 8);
                break;
            case C_NIGHTMARE: y.hp -= d->maxhp / 4 * d->sleep; break;     /* each turn it sleeps through (logs) */
            default: credit = 0;
            }
        } else if (m->id == MV_LEECH_SEED) {           /* drains an eighth of the foe a turn into me */
            s32 t = tick(d->maxhp, 8);
            y.chip += t;
            x.chip -= t;
        } else if (m->efx == X_PAIN_SPLIT) {
            x.hp = y.hp = (x.hp + y.hp) / 2;
            if (x.hp > x.maxhp)
                x.hp = x.maxhp;
            if (y.hp > y.maxhp)
                y.hp = y.maxhp;
        } else if (m->efx == X_MEMENTO || m->efx == X_WISH) {
            /* I faint; my next Pokemon comes in free, healed, or against a foe at -2 Attack and Sp. Atk */
            x.hp = 0;
            if (m->efx == X_WISH)
                y.wish = 1;
            else
                y.dmg64 /= 2;
        } else if (m->efx == X_TAUNT && y.heal) {      /* a staller loses its recovery move */
            y.heal = 0;
        } else if (m->id == MV_TAILWIND) {             /* my side's Speed doubles for this turn's end and three more */
            x.spe *= 2;
            x.spe64 *= 2;
            x.tw = 4;
        } else if (m->efx >= X_ROCKS) {                /* every Pokemon of theirs that comes in later pays it */
            lasting = c->haz[m->efx - X_ROCKS] * 9;
            credit = lasting > 0;
        } else if (m->efx == X_TROOM) {                /* the slower side moves first for this turn's end and four more */
            troom = g_tr_left ? 0 : 5;
        } else if (m->target == TARGET_USER && (m->sick == C_INGRAIN || m->id == MV_AQUA_RING)) {
            x.chip -= a->maxhp / 16;
        } else if (boost_kind(m)) {
            /* a boost carries on: to the foe's next Pokemon, and through every turn a foe that cannot hurt me gives; not the
               race against a foe whose U-turn or Volt Switch takes it out this turn */
            int best = best_cls(c, 2), piv = p->rep >= 0 && d->mv[p->rep].efx == X_PIVOT && c->opp_others && hit;
            int att = att_stat(a, p->my_slot, best);
            s32 ba = 0, bs = 0;
            if (piv)
                best = att = 0;
            prime(&x, a, d, c->d_mo, c->weather, MY_ROLL);     /* my priority attack, boosted, may finish first */
            if (m->id == MV_BELLY_DRUM) {   /* half my max HP, or it fails at half or less */
                credit &= 2 * x.hp > x.maxhp;
                x.hp -= credit ? x.maxhp / 2 : 0;
            }
            for (k = 0; k < 3 && credit; k++) {
                int t = m->rank_type[k], v = m->rank_val[k], cur, nxt;
                if (!t || t > 7)
                    continue;
                cur = a->stage[t - 1];
                nxt = clamp(cur + v, 0, 12);
                if (t == 1 && p->opp_slot >= 0 && d->mv[p->opp_slot].id == MV_FOUL_PLAY)   /* it uses my Attack */
                    y.dmg = stage_mult(y.dmg * 64, nxt) / stage_mult(64, cur);
                if (t == att) {
                    if (!(d->ability == AB_UNAWARE && !breaks_mold(a))) {
                        x.dmg = restage(x.dmg, cur, nxt);
                        x.pdmg = restage(x.pdmg, cur, nxt);
                        ba += c->opp_others || !p->opp_rate ? 40 * (nxt - cur) : 0;
                    }
                } else if (t == 5) {
                    if (!piv)
                        x.spe = stage_mult(x.spe * 8, nxt) / stage_mult(8, cur);
                    bs += c->opp_others || !p->opp_rate ? 20 * (nxt - cur) : 0;
                } else if (t == 7 && p->opp_slot >= 0 && d->ability != AB_UNAWARE) {
                    /* evasion: the foe's race attack lands as often as its accuracy at the new stage gap allows */
                    s32 h0 = hit_at(d, a, p->opp_slot, cur);
                    if (h0)
                        y.dmg = y.dmg * hit_at(d, a, p->opp_slot, nxt) / h0;
                }
                if (t == 2 * ocls)
                    y.dmg = stage_mult(y.dmg * 64, cur) / stage_mult(64, nxt);
                if (piv && (t == 1 || t == 3))
                    bonus += 40 * (nxt - cur);
            }
            /* A2_SETUP: a boost is progress only through my attacks: with no attack that hurts the foe in front, I never
               knock it out, so the boost (lost when I switch) never reaches its next Pokemon: no credit for later */
            if ((AI_A2 & A2_SETUP) && x.dmg <= 0)
                stuck = 1, ba = bs = 0;
            bonus += ba + bs;
            if (m->efx == X_SMASH && a->item != IT_WHITE_HERB && ocls) {     /* -1 to the defence the foe hits; the herb undoes it (logs) */
                k = a->stage[2 * ocls - 1];
                y.dmg = restage(y.dmg, clamp(k - 1, 0, 12), k);
            }
        } else
            credit = 0;                                 /* field, screens, unknown effects: no credit */
        if ((y.chip > 0 || y.tox) && own >= 0 && !(y.grow & MIRROR)) {   /* then its end-of-turn damage does it, and no
                                                                            hit of mine (MIRROR: race_core holds it) */
            x.dmg = 0;
            y.dmg = own;
        }
        if (me_first && x.hp > 0) {
            s32 h = B.dmg > 0 ? hit * (y.dmg * 64 / B.dmg) / 64 : hit;
            if (y.sleep > B.sleep) {                    /* asleep before it moves: this turn is one it sleeps through */
                h = 0;
                y.sleep--;
            }
            if (y.para && !B.para) {                    /* paralyzed before it moves: a quarter of the time no reply */
                lost = 1;
                xl = x;
                yl = y;
            }
            reply_turn(c, p, &x, a, &y, h);
            if (m->efx == X_DESTINY && x.hp <= 0) {     /* its hit knocks me out: it goes down with me */
                y.hp = 0;
                credit = 1;
            }
        }
        if (m->efx == X_DESTINY && x.hp > 0) {
            /* it stays up until my next move (logs: s038_g1 of run 20261002_234540): the foe's next hit, when it comes
               first and knocks me out, takes it down with me */
            credit = first(&y, &x, 1) && y.dmg >= x.hp;
            if (credit)
                x.hp = y.hp = 0;
        }
    }
    /* mine falls this turn, the foe not, when the move works or not (the hit it stops or softens counts) */
    g_fell = (acc * (x.hp <= 0 && y.hp > 0) * (4 - lost) / 4 + (100 - acc) * fm) * 10;
    tr0 = g_tr_left;
    if (m->efx == X_TROOM)
        g_tr_left = troom;
    if (x.hp <= 0 || y.hp <= 0) {
        if (y.drowsy > 1)           /* mine fell this turn: the turn's end still counts down the foe's Yawn */
            y.drowsy--;
        v_ok = outcome(c, &x, &y, 1);
        alive = x.hp;
    } else {
        end_of_turn(&x);
        end_of_turn(&y);
        v_ok = race_ex(c, x, y, 1, &alive);
        for (k = 0; k < 4 && y.sleep > B.sleep && !(A1(A1_LOCK) && choice_locks(a, m)); k++) {
            /* or a turn it sleeps through goes to my Leech Seed or my boost, which then lasts the race */
            const MoveInfo *mk = &a->mv[k];
            Fighter x2 = x, y2 = y;
            int j;
            s32 v;
            if (!a->legal[k] || mk->cls)
                continue;
            if (mk->id == MV_LEECH_SEED) {
                if (status_blocked(c, a, d, mk))
                    continue;
                y2.chip += d->maxhp / 8;
                x2.chip -= d->maxhp / 8;
            } else {
                for (j = 0; j < 3; j++)
                    if (boost_kind(mk) && mk->rank_type[j] == 2 * x.cls - 1 && d->ability != AB_UNAWARE)
                        x2.dmg = restage(x2.dmg, 6, 6 + mk->rank_val[j]);
                if (x2.dmg == x.dmg)
                    continue;
            }
            x2.recharge = 1;
            v = race(c, x2, y2, 1);
            if (v > v_ok)
                v_ok = v;
        }
        if (y.sleep > B.sleep && c->nbench && !c->trapped) {
            /* or its sleep goes to my best teammate: the switch costs one sleeping turn and no hit */
            Fighter g = y;
            int any;
            s32 v;
            g.sleep--;
            v = follow_up(c, WHO_ACTIVE, x.tw, &g, &any) + worth(x.hp, x.maxhp) - worth(a->hp, a->maxhp) +
                worth(d->hp, d->maxhp) - worth(y.hp, y.maxhp) - SWITCH_COST;
            if (any && v > v_ok)
                v_ok = v;
        }
    }
    if (lost) {
        end_of_turn(&xl);
        end_of_turn(&yl);
        v_ok = (3 * v_ok + (xl.hp > 0 && yl.hp > 0 ? race(c, xl, yl, 1) : outcome(c, &xl, &yl, 1))) / 4;
    }
    g_tr_left = tr0;
    /* the boost lasts into the one on ones against the foe's other Pokemon */
    if (boost_kind(m) && credit && alive > 0 && !stuck)
        bonus += boost_carry(c, slot, alive);
    v_ok += (alive > 0 ? bonus : 0) + lasting - (credit ? 0 : 50);
    return (acc * v_ok + (100 - acc) * v_miss) / 100;
}

/* the odds (per-mille) that the foe puts my awake Pokemon x to sleep on a turn: the original AI's pick as reply_odds
   weighs it (none when an attack knocks x out), times the sleep move's accuracy */
static int sleep_odds(const Ctx *c, const Mon *x, const u16 *raw)
{
    const Mon *d = &c->opp;
    int k, slp = -1, w = 0, top = 0;
    s32 e;
    if (x->status || x->drowsy || x->hp <= 0)
        return 0;
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &d->mv[k];
        if (!d->legal[k])
            continue;
        if (m->cls) {
            e = move_damage(d, x, m, raw[k]) * hits_x10(m) / 10 * THEIR_ROLL / 1000;
            if (e >= x->hp)
                return 0;
            w += e > 0;
            top |= e > 0;
        } else if (foe_status_ok(c, x, m)) {
            w += status_w(c, m);
            if (sickens(m) && m->sick == S_SLP)
                slp = k;
        }
    }
    return slp < 0 ? 0 : 10 * status_w(c, &d->mv[slp]) * move_acc(d, x, &d->mv[slp], c->weather) / (w + 9 * top);
}

/* a's Dream Eater on d per turn d sleeps through (the race's `dream`) */
static s32 dream_rate(const Mon *a, const Mon *d, const u16 *raw, int weather, int roll)
{
    int k;
    for (k = 0; k < 4; k++)
        if (a->legal[k] && a->mv[k].id == MV_DREAM_EATER && eff_move(a, d, &a->mv[k]))
            return expected_at(a, d, raw[k], &a->mv[k], weather, roll);
    return 0;
}

/* a's Fake Out on d (the race's `fo`): it works on a's first turn out and the foe flinches; none against Inner Focus or
   Shield Dust, or under a Choice item, which would keep a on it */
static s32 fake_out(const Mon *a, const Mon *d, const u16 *raw, int weather)
{
    int k;
    for (k = 0; k < 4; k++)
        if (a->legal[k] && a->mv[k].id == MV_FAKE_OUT && can_flinch(d, a) && !choice_locks(a, &a->mv[k]))
            return move_rate(a, d, &a->mv[k], raw[k], weather, MY_ROLL);
    return 0;
}

/* my Pokemon racing the foe from a free entry, with its priority finisher and its Fake Out */
static void ent_mine(Ctx *c, Fighter *f, const Mon *s, const u16 *raw)
{
    prime(f, s, &c->opp, raw, c->weather, MY_ROLL);
    f->fo = fake_out(s, &c->opp, raw, c->weather);
}

/* each of my Pokemon racing the foe from a free entry: the bench from `first` on (WHO 0..; the rows before it are
   already in c), then the active Pokemon */
static void entries_from(Ctx *c, const Pair *p, int first)
{
    const Mon *d = &c->opp;
    int i, ss, ds;
    s8 sp, dp;
    s32 chip;
    u16 buf[4];
    for (i = first; i < c->nbench; i++) {
        const Mon *s = &c->bench[i];
        const u16 *full = unberried(d, s, c->d_ob[i], buf);
        s32 srate = best_rate(s, d, c->d_bo[i], c->weather, &sp, &ss, MY_ROLL, 0);
        s32 drate = best_rate(d, s, full, c->weather, &dp, &ds, THEIR_ROLL, 0);
        c->ent_me[i] = fighter(s, srate, sp, c->weather);
        c->ent_me[i].who = i;
        ent_mine(c, &c->ent_me[i], s, c->d_bo[i]);
        c->ent_foe[i] = fighter(d, drate, dp, c->weather);
        prime(&c->ent_foe[i], d, s, full, c->weather, THEIR_ROLL);
        arm(&c->ent_me[i], s, d, ss);
        arm(&c->ent_foe[i], d, s, ds);
        counter_fight(&c->ent_me[i], s, d, ds, drate);
        counter_fight(&c->ent_foe[i], d, s, ss, srate);
        policy_fight(&c->ent_foe[i], d, policy(d, s, ss >= 0 ? &s->mv[ss] : 0, ds));
        if (ds >= 0)                                       /* the stage its entry gave the foe stays for my next one */
            c->ent_foe[i].dmg64 = c->ent_foe[i].dmg64 * entry_mult(s, d, d->mv[ds].cls) / 64;
        c->ent_me[i].hp -= hazard_hp(c, s, &chip);        /* hp0 stays: what the hazards take is lost */
        c->ent_me[i].chip += chip;
        c->ent_me[i].dream = dream_rate(s, d, c->d_bo[i], c->weather, MY_ROLL);
        c->ent_foe[i].dream = dream_rate(d, s, c->d_ob[i], c->weather, THEIR_ROLL);
        c->ent_foe[i].nap = sleep_odds(c, s, c->d_ob[i]);
    }
    c->ent_me[MAX_BENCH] = fighter(&c->me, p->my_rate, p->my_prio, c->weather);
    ent_mine(c, &c->ent_me[MAX_BENCH], &c->me, c->d_mo);
    c->ent_foe[MAX_BENCH] = fighter(d, p->opp_rate, p->opp_prio, c->weather);
    prime(&c->ent_foe[MAX_BENCH], d, &c->me, c->d_om, c->weather, THEIR_ROLL);
    arm(&c->ent_me[MAX_BENCH], &c->me, d, p->my_slot);
    arm(&c->ent_foe[MAX_BENCH], d, &c->me, p->opp_slot);
    counter_fight(&c->ent_me[MAX_BENCH], &c->me, d, p->opp_slot, p->opp_rate);
    counter_fight(&c->ent_foe[MAX_BENCH], d, &c->me, p->my_slot, p->my_rate);
    policy_fight(&c->ent_foe[MAX_BENCH], d, policy(d, &c->me, p->my_slot >= 0 ? &c->me.mv[p->my_slot] : 0, p->opp_slot));
    c->ent_me[MAX_BENCH].dream = dream_rate(&c->me, d, c->d_mo, c->weather, MY_ROLL);
    c->ent_foe[MAX_BENCH].dream = dream_rate(d, &c->me, c->d_om, c->weather, THEIR_ROLL);
    c->ent_foe[MAX_BENCH].nap = sleep_odds(c, &c->me, c->d_om);
    for (i = 0, ds = 0; i < 4; i++) {        /* the foe's boost move on its race attack's stat (foe_turn) */
        const MoveInfo *m = &d->mv[i];
        if (d->legal[i] && boost_kind(m) && (m->rank_type[0] | 2) == 3)
            ds = m->rank_type[0] | m->rank_val[0] << 2;
    }
    chip = cond_on(d, C_LEECH_SEED) ? d->maxhp / 8 : 0;
    for (i = first; i <= MAX_BENCH; i++) {  /* the foe's Leech Seed drains into whichever of mine is out */
        c->ent_me[i].chip -= chip;
        c->ent_foe[i].boost = ds;
    }
    {   /* used for its entry after it went out, which cures Yawn, resets its stat stages and meets the hazards */
        Fighter *f = &c->ent_me[MAX_BENCH], *g = &c->ent_foe[MAX_BENCH];
        f->drowsy = 0;
        f->hp -= hazard_hp(c, &c->me, &chip);
        if (f->cls)
            f->dmg = restage(f->dmg, c->me.stage[2 * f->cls - 2], 6);
        if (g->cls)
            g->dmg = restage(g->dmg, 6, c->me.stage[2 * g->cls - 1]);
        f->spe = restage(f->spe, c->me.stage[4], 6);
    }
}

static void entries(Ctx *c, const Pair *p) { entries_from(c, p, 0); }

/* the player's move k lands on my bench Pokemon i as it comes in (a Sucker Punch fails on a switch): the odds in
   percent that it knocks it out (accuracy and the damage roll) and, in *hit, the average of the rolls it survives */
static int entry_hit(const Ctx *c, int i, int k, s32 *hit)
{
    const Mon *s = &c->bench[i], *d = &c->opp;
    const MoveInfo *m = &d->mv[k];
    s32 h = c->ent_me[i].hp;
    *hit = 0;
    if ((unsigned)k >= 4 || !d->legal[k] || !m->cls || m->id == MV_SUCKER_PUNCH || (charges(d, m, c->weather) && m->id != d->charging) ||
        h <= 0)
        return 0;
    return roll_ko(move_damage(d, s, m, c->d_ob[i][k]) * hits_x10(m) / 10, h, move_acc(d, s, m, c->weather),
                   c->ent_me[i].endure && h == s->maxhp && !multi(d, m), hit);    /* hazards break a Sash */
}

/* the reply was aimed at my active Pokemon; the newcomer takes it, as three branches: it knocks the newcomer out, it
   lands (the average of the rolls the newcomer survives, the drops it gives the newcomer, the newcomer's ability
   answering it, the foe's recoil), or it misses: an averaged hit would take a turn from the newcomer in every branch.
   g_fell counts a newcomer that falls this turn, or next turn before it acts, as lost for nothing */
static s32 value_switch(Ctx *c, const Pair *p, int i)
{
    const Mon *s = &c->bench[i], *d = &c->opp;
    const MoveInfo *m = (unsigned)p->rep < 4 ? &d->mv[p->rep] : 0;
    Fighter S, B;
    s32 v = 0, hit = 0, fell;
    int ko = entry_hit(c, i, p->rep, &hit), acc = hit ? move_acc(d, s, m, c->weather) : 100, b, j, wb;
    fell = ko * 10;
    if (acc > ko)               /* entry_hit counts a miss as no damage */
        hit = hit * (100 - ko) / (acc - ko);
    for (b = 0; b < 3; b++) {
        wb = !b ? ko : b == 1 ? acc - ko : 100 - acc;
        if (wb <= 0)
            continue;
        S = c->ent_me[i];
        B = c->ent_foe[i];
        if (B.sleep)
            B.sleep--;
        if (b < 2) {
            reply_after(c, p, &S, s, &B);
            if (m)              /* the newcomer's ability takes the move (Storm Drain, Volt Absorb...) */
                gain(&S, absorbs(s, d, m));
        }
        if (!b)
            S.hp = 0;
        else if (b == 1 && hit) {
            reply_turn(c, p, &S, s, &B, hit);
            B.recharge = (m->flags >> F_RECHARGE) & 1;
            on_hit(s, m, &B, &S);
            for (j = 0; m->quality == Q_DAMAGE_EFFECT && d->ability != AB_SHEER_FORCE && s->ability != AB_CLEAR_BODY &&
                        s->ability != AB_WHITE_SMOKE && s->ability != AB_FULLMETALBDY && j < 3; j++) {
                int t = m->rank_type[j], nx = clamp(6 + m->rank_val[j], 0, 12);
                if (t == 5)
                    S.spe = restage(S.spe, 6, nx);
                else if (t == 2 * S.cls - 1)
                    S.dmg = restage(S.dmg, 6, nx);
                else if (t && t == 2 * B.cls)
                    B.dmg = restage(B.dmg, nx, 6);
            }
        }
        if (S.hp > 0) {
            end_of_turn(&S);
            end_of_turn(&B);
            if (S.hp > 0 && first(&B, &S, 1) && !B.sleep && !B.recharge && (B.dmg >= S.hp || finisher(&B, &S)) &&
                !(S.endure && S.hp == S.maxhp))
                fell += wb * 10;
            /* the foe's U-turn or Volt Switch takes it out after the hit: no exchange with it, the HP lost counts */
            v += wb * (m && m->efx == X_PIVOT && c->opp_others ? outcome(c, &S, &B, 1) : race(c, S, B, 1));
        } else {
            fell += wb * 10;
            v += wb * outcome(c, &S, &B, 1);
        }
    }
    g_fell = c->ent_me[i].hp > 0 ? fell : 1000;
    if (c->ent_me[MAX_BENCH].hp <= 0)       /* the hazards knock my active Pokemon out if it comes back: the switch loses it */
        v -= 100 * worth(c->me.hp, c->me.maxhp);
    /* my sleeping Pokemon sleeps only on the field: going out, it keeps the turns it has left for later (measured), where
       staying in counts them as turns the race takes. Half, as it may never need to come back */
    return v / 100 - SWITCH_COST - (c->me.status == S_SLP ? c->me.sleep * TEMPO / 2 : 0);
}

static int heal_amount(int item, const Mon *m)
{
    switch (item) {
    case IT_POTION: return 20;
    case IT_SUPER_POTION: return 60;
    case IT_HYPER_POTION: return 120;
    case IT_MAX_POTION: case IT_FULL_RESTORE: return m->maxhp;
    }
    return 0;
}

static int cures(int item, int status)
{
    switch (item) {
    case IT_FULL_RESTORE: case IT_FULL_HEAL: return status != S_NONE;
    case IT_ANTIDOTE: return status == S_PSN;
    case IT_BURN_HEAL: return status == S_BRN;
    case IT_ICE_HEAL: return status == S_FRZ;
    case IT_AWAKENING: return status == S_SLP;
    case IT_PARLYZ_HEAL: return status == S_PAR;
    }
    return 0;
}

static s32 value_item(Ctx *c, const Pair *p, int item)
{
    const Mon *a = &c->me, *d = &c->opp;
    Fighter x, y;
    pair_fighters(c, p, &x, &y);
    arm(&x, a, d, p->my_slot);
    arm(&y, d, a, p->opp_slot);
    counter_fight(&x, a, d, p->opp_slot, p->opp_rate);
    counter_fight(&y, d, a, p->my_slot, p->my_rate);
    policy_fight(&y, d, policy(d, a, p->my_slot >= 0 ? &a->mv[p->my_slot] : 0, p->opp_slot));
    int heal = heal_amount(item, a), cure = cures(item, a->status);
    if (heal && a->hp * 4 >= a->maxhp * 3 && !cure)
        heal = 0;
    if (!heal && !cure)
        return -100000;
    x.hp = x.hp + heal > x.maxhp ? x.maxhp : x.hp + heal;
    if (cure) {
        x.sleep = 0;
        x.chip = chip_of(a, c->weather) - (a->status == S_BRN ? a->maxhp / 16 : poison_chip(a));
        if (a->status == S_PAR) {
            x.spe = a->ability == AB_QUICK_FEET ? x.spe * 2 / 3 : x.spe * 2;
            x.para = 0;
        }
    }
    if (x.sleep)
        x.sleep--;
    reply_after(c, p, &x, a, &y);
    reply_turn(c, p, &x, a, &y, passive_hit(c, p));
    if (x.hp <= 0)
        return outcome(c, &x, &y, 1);
    end_of_turn(&x);
    end_of_turn(&y);
    return race(c, x, y, 1) - 20;
}

/* every move vetoed: staying in is a turn that does nothing (or feeds the foe's absorbing ability), then the race (free
   when the foe cannot hurt me either) */
static s32 value_stay(Ctx *c, const Pair *p, int slot)
{
    const Mon *a = &c->me, *d = &c->opp;
    Fighter x, y;
    pair_fighters(c, p, &x, &y);
    arm(&x, a, d, p->my_slot);
    arm(&y, d, a, p->opp_slot);
    if (x.sleep)
        x.sleep--;
    reply_after(c, p, &x, a, &y);
    reply_turn(c, p, &x, a, &y, passive_hit(c, p));
    if (x.hp <= 0)
        return outcome(c, &x, &y, 1);
    if (!x.sleep && slot < 4)      /* slot 4: no move (a confused turn) */
        gain(&y, absorbs(d, a, &a->mv[slot]));
    end_of_turn(&x);
    end_of_turn(&y);
    return race(c, x, y, 1);
}

/* the move to stay in with: a legal one that costs me least (no self-KO, crash damage, recoil or stat drop, nothing the
   foe's ability feeds on) */
static int stay_slot(const Ctx *c)
{
    const Mon *a = &c->me;
    int k, h, b = -1, bh = 99;
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &a->mv[k];
        if (!a->legal[k])
            continue;
        /* every move is vetoed here: a status move at the foe fails on it (Sleep Powder on a Grass type, Nightmare on an
           awake one), so an attack goes first */
        h = 4 * self_ko_move(m->id) + 2 * (m->id == MV_JUMP_KICK || m->id == MV_HI_JUMP_KICK) + (m->drain < 0) +
            (m->quality == Q_DAMAGE_EFFECT_USER) + 8 * !!absorbs(&c->opp, a, m) + 2 * (!m->cls && at_mon(m));
        if (h < bh) {
            bh = h;
            b = k;
        }
    }
    return b;
}

/* out of usable moves (every move out of PP, or none selectable), the engine gives Struggle: a switch then only to a
   Pokemon with a move left, else Struggle through overlay 11's fallback. Switching between Pokemon out of PP never
   ends (41 switches in a row in menulock foe_pp4, rc41) */
static int has_move(const Mon *m)
{
    return m->legal[0] | m->legal[1] | m->legal[2] | m->legal[3];
}

/* ---------------------------------------------------------------- the turn */

static void fail(Ctx *c, int why)
{
    c->mode = M_FALLBACK;
    c->fallback = why;
    c->dbg->fallback = why;
    c->dbg->magic = DEBUG_MAGIC;         /* a fallback before debug_snapshot is still seen */
}

/* the terrain and Trick Room, which only the engine's other copy of the field keeps (measured); the terrain as what
   it stops against grounded Pokemon. Thunder Roar ("first-strike moves fail", not measured) also stops priority
   moves while its holder has been out under 5 turns */
static int terrain_shield(Ctx *c)
{
    const Mon *s[4] = { &c->me, &c->opp, &c->foes[1], &c->ally };
    void *f = E_POKECON0();
    int i, v;
    c->terrain = OK_PTR(f) && FLD_ON(f, FE_TERRAIN) && FLD_TERRAIN(f) <= TERRAIN_PSYCHIC ? FLD_TERRAIN(f) : 0;
    g_tr_left = OK_PTR(f) ? clamp(FLD_LEFT(f, FE_TRICK_ROOM), 0, 8) : 0;
    v = c->terrain == TERRAIN_PSYCHIC ? SHIELD_PRIO : c->terrain == TERRAIN_MISTY ? SHIELD_STATUS : c->terrain == TERRAIN_ELECTRIC ? SHIELD_SLEEP :
        c->terrain == TERRAIN_GRASSY ? SHIELD_HEAL : 0;
    for (i = 0; i < 4; i++) {
        if (i >= 2 && (!c->doubles || (i == 2 && c->nfoes < 2) || (i == 3 && !c->has_ally)))
            continue;
        if (s[i]->ability == AB_THUNDER_ROAR && s[i]->turns < 5)
            v |= SHIELD_PRIO;
    }
    return v;
}

/* a substitute up on the foe f (party slot i of client cl), from the engine's other copy, the only one it updates */
static int subbed(int cl, int i)
{
    void *pc = E_POKECON(0), *party = OK_PTR(pc) ? E_PARTY(pc, cl) : 0, *b = OK_PTR(party) ? E_PARTY_MEMBER(party, i) : 0;
    return OK_PTR(b) && B_SUB_HP(b) > 0;
}

static void snapshot_common(Ctx *c, void *pc, u8 *main)
{
    int i, raw, shield;
    void *x = E_POKECON0();
    for (i = 0; i < 4; i++) {
        if (!c->me.legal[i])
            continue;
        waza_lend(c->me.mv[i].id);
        if (E_UNSELECTABLE(c->me.bpp, c->me.mv[i].id, pc, x))
            c->me.legal[i] = 0;
    }
    {
        void *cw = AT(vptr, (u32)main + MAIN_CLIENTS + 4 * c->client);
        u8 o1 = 0;
        u16 o2 = 0;
        c->trapped = !OK_PTR(cw) || E_TRAPPED(cw, c->me.bpp, &o1, &o2) != 0;
    }
    {
        void *field = AT(vptr, (u32)main + MAIN_FIELD);
        raw = OK_PTR(field) ? AT(u8, field) : 0;
        c->weather = raw <= W_HAIL ? raw : raw == WX_HARSH_SUN ? W_SUN : raw == WX_HEAVY_RAIN ? W_RAIN : W_NONE;
    }
    shield = terrain_shield(c);
    for (i = 0; i < 6 + MAX_BENCH; i++) {
        Mon *m = i == 0 ? &c->me : i == 1 ? &c->opp : i == 2 ? &c->spare : i == 3 ? &c->foes[0] : i == 4 ? &c->foes[1] :
                 i == 5 ? &c->ally : &c->bench[i - 6];
        if ((i >= 3 && i <= 5 && !c->doubles) || (i >= 6 && i - 6 >= c->nbench))
            continue;
        weather_moves(m, c->weather, raw);
        /* Safeguard on its side (slots 1-4: the foes') stops what Misty Terrain stops, grounded or not (Infiltrator's
           way through it is not modeled) */
        m->shield = (grounded(m) ? shield : 0) | (SIDE_LAYERS((c->client & 1) ^ (i >= 1 && i <= 4), SE_SAFEGUARD) ? SHIELD_STATUS : 0);
    }
    c->trainer = c->trainer > 3 ? 1 : c->trainer;
}

/* doubles (one trainer with two Pokemon out, or a multi battle): the foes on the field, my partner on
   the field, my bench */
static int snapshot_doubles(Ctx *c, void *pc, u8 *main)
{
    int k, i, n;
    void *party = E_PARTY(pc, c->client);
    if (!OK_PTR(party))
        return FB_SNAPSHOT;
    c->nfoes = 0;
    c->spare.bpp = 0;
    for (k = 0; k < 2; k++) {
        int cl = (c->client ^ 1) ^ (2 * k);
        void *op = E_PARTY(pc, cl);
        if (!OK_PTR(op) || !E_PARTY_COUNT(op))
            continue;
        n = E_ACTIVES(cl);
        for (i = 0; i < n && i < E_PARTY_COUNT(op) && c->nfoes < 2; i++) {
            Mon *f = &c->foes[c->nfoes];
            if (read_mon(f, E_PARTY_MEMBER(op, i), i) && f->alive) {
                f->subbed = subbed(cl, i);
                lock_foe(f);
                c->fcl[c->nfoes++] = cl;
            }
        }
        for (i = n; i < E_PARTY_COUNT(op) && i < 6 && !c->spare.bpp; i++)
            if (!read_mon(&c->spare, E_PARTY_MEMBER(op, i), i) || !c->spare.alive)
                c->spare.bpp = 0;
    }
    if (!c->nfoes)
        return FB_OPP;
    c->opp = c->foes[0];
    c->has_ally = 0;
    n = E_ACTIVES(c->client);
    if (n == 2) {
        void *a = E_PARTY_MEMBER(party, 0), *b = E_PARTY_MEMBER(party, 1);
        if (a != c->me.bpp && b != c->me.bpp)
            return FB_SNAPSHOT;
        c->has_ally = read_mon(&c->ally, a == c->me.bpp ? b : a, a == c->me.bpp ? 1 : 0) && c->ally.alive;
    } else {
        void *partner = E_PARTY(pc, c->client ^ 2);
        if (E_PARTY_MEMBER(party, 0) != c->me.bpp)
            return FB_SNAPSHOT;
        if (OK_PTR(partner) && E_PARTY_COUNT(partner))
            c->has_ally = read_mon(&c->ally, E_PARTY_MEMBER(partner, 0), 0) && c->ally.alive;
    }
    c->nbench = 0;
    k = E_PARTY_COUNT(party);
    for (i = n; i < k && i < 6 && c->nbench < MAX_BENCH; i++) {
        Mon *m = &c->bench[c->nbench];
        if (read_mon(m, E_PARTY_MEMBER(party, i), i) && m->alive)
            c->nbench++;
    }
    c->opp_others = 0;
    snapshot_common(c, pc, main);
    remember(c, c->foes, c->nfoes);
    return FB_NONE;
}

/* what one more layer of each hazard on the player's side would cost its Pokemon t, off the field, when it comes
   in, in sixteenths of a thousandth of its HP (Toxic Spikes: the poison, as two turns of it, then the upgrade to
   bad poison) */
static void foe_hazards(Ctx *c, const Mon *t)
{
    int side = (c->client & 1) ^ 1, n;
    if (t->ability == AB_MAGIC_GUARD)
        return;
    if (!SIDE_LAYERS(side, SE_STEALTH_ROCK))
        c->haz[0] += eff_permille(T_ROCK, t) / 128;
    if (!grounded(t))
        return;
    n = SIDE_LAYERS(side, SE_SPIKES);
    if (n < 3)
        c->haz[1] += n == 0 ? 8 : n == 1 ? 3 : 5;
    n = SIDE_LAYERS(side, SE_TOXIC_SPIKES);
    if (n < 2 && !t->status && !has_type(t, T_POISON) && !has_type(t, T_STEEL) && t->ability != AB_IMMUNITY &&
        t->ability != AB_POISON_HEAL)
        c->haz[2] += 16 >> n;
}

/* a status (one a Flame Orb or Toxic Orb brings after its holder's first turn too): Facade doubles, Guts adds half and
   undoes the burn's halving */
static s32 sick_mods(const Mon *a, const MoveInfo *m, s32 v)
{
    if (m->id == MV_FACADE)
        v *= 2;
    if (a->ability == AB_GUTS && m->cls == 1)
        v = a->status == S_BRN ? v * 3 : v * 3 / 2;
    return v;
}

static int orb(const Mon *a) { return a->item == IT_FLAME_ORB || a->item == IT_TOXIC_ORB; }

/* the attacker's own multipliers on m that our formula leaves out (the role check only; the simulation has them all):
   the common items and abilities of the trainers' Pokemon (official rules, not measured here unless said) */
static s32 att_mods(const Mon *a, const Mon *d, const MoveInfo *m, s32 v)
{
    int phys = m->cls == 1;
    if (a->status || orb(a))
        v = sick_mods(a, m, v);
    switch (a->item) {
    case IT_CHOICE_BAND: if (phys) v = v * 3 / 2; break;
    case IT_CHOICE_SPECS: if (!phys) v = v * 3 / 2; break;
    case IT_LIFE_ORB: v = v * 13 / 10; break;
    case IT_EXPERT_BELT: if (eff_move(a, d, m) > 1000) v = v * 6 / 5; break;
    case IT_LIGHT_BALL: if (a->species == 25) v *= 2; break;                                    /* Pikachu (measured) */
    case IT_THICK_CLUB: if (phys && (a->species == 104 || a->species == 105)) v *= 2; break;    /* Cubone, Marowak (measured) */
    }
    switch (a->ability) {
    case AB_ADAPTABILITY: if (has_type(a, m->type)) v = v * 4 / 3; break;
    case AB_HUGE_POWER: case AB_PURE_POWER: if (phys) v *= 2; break;
    case AB_TECHNICIAN: if (m->power <= 60) v = v * 3 / 2; break;
    case AB_TOUGH_CLAWS: if ((m->flags >> F_CONTACT) & 1) v = v * 13 / 10; break;
    case AB_SHEER_FORCE: if (m->secondary) v = v * 13 / 10; break;
    }
    return v;
}

/* a's expected damage per turn on d with move m (the role check: no engine simulation for two Pokemon off the field):
   our formula with d's items and abilities, and a's own multipliers (items, abilities, terrain) as the simulation
   found them against the foe on the field (sim: its max roll, model: our formula's), else as att_mods has them */
static s32 rough1(const Mon *a, const Mon *d, const MoveInfo *m, int weather, int roll, s32 sim, s32 model)
{
    s32 f;
    if (!m->cls || self_ko_move(m->id))
        return 0;
    f = formula_damage(a, d, m, weather);
    f = model > 0 && sim > 1 ? f * clamp(sim * 64 / model, 0, 512) / 64 : att_mods(a, d, m, f);
    if (model > 0 && sim > 1 && !a->status && orb(a))     /* the simulation saw it before its orb's status */
        f = sick_mods(a, m, f);
    f = defender_mods(a, d, m, f);
    if (berry_fires(a, d, m))         /* a resist berry halves one hit, not the one on one */
        f *= 2;
    return move_rate(a, d, m, f, weather, roll);
}

/* the HP a needs to win the one on one against d from a free entry, as both are now (0: it does not win): with each of
   its attacks, fewer hits to a KO, the side whose move goes first (priority, then speed) breaking a tie, and every turn
   a sleeps through a free hit for d; a Counter (Mirror Coat) that lives through d's best attack returns it, moving last.
   A priority attack of d (not Fake Out) that beats my move's priority lands before each of my hits. When d raises the defence my
   attack meets (Iron Defense, Curse, Calm Mind; Stamina at each physical hit), my hits count at +6 there: a set-up wall
   is beaten from the other side. sim: a's raw damage on o, the foe on the field (0: none) */
static s32 beats(const Mon *a, const Mon *d, int weather, const u16 *sim, const Mon *o)
{
    int k, j, cls = 0, pd = 0, pp = 0, first, n, wall = d->ability == AB_STAMINA ? 4 : 0;
    s32 rd = 0, rp = 0, e, r, best = 0;
    for (k = 0; k < 4; k++) {          /* d's best attack on a, its best priority attack, the defences it raises */
        const MoveInfo *m = &d->mv[k];
        if (!d->legal[k])
            continue;
        for (j = 0; j < 3; j++)
            if (!m->cls && m->target == TARGET_USER && m->rank_val[j] > 0)
                wall |= 1 << m->rank_type[j];
        e = rough1(d, a, m, weather, THEIR_ROLL, 0, 0);
        if (e > rd) {
            rd = e;
            cls = m->cls;
            pd = m->prio;
        }
        if (m->prio > 0 && m->id != MV_FAKE_OUT && e > rp) {
            rp = e;
            pp = m->prio;
        }
    }
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &a->mv[k];
        if (!a->legal[k])
            continue;
        e = rough1(a, d, m, weather, MY_ROLL, sim ? sim[k] : 0,
                   sim && m->cls ? defender_mods(a, o, m, formula_damage(a, o, m, weather)) : 0);
        if (m->cls && (wall >> 2 * m->cls) & 1)
            e = restage(e, 12, d->stage[2 * m->cls - 1]);
        first = m->prio > pd || (m->prio == pd && faster(eff_speed(a, weather), eff_speed(d, weather)));
        if (k == counter_slot(a, d, cls) && rd < a->hp && returns10(m, cls) * rd / 10 > e) {
            e = returns10(m, cls) * rd / 10;
            first = 0;
        }
        if (e <= 0)
            continue;
        n = (d->hp + e - 1) / e + (dozes(a) ? a->sleep : 0);
        r = rd > 0 ? (n - first) * rd + 1 : 1;
        if (pp > m->prio && n * rp >= r)
            r = n * rp + 1;
        if (!best || r < best)
            best = r;
    }
    return a->hp >= best ? best : 0;
}

/* what my active needs to beat foe t (party slot j + 1) as it comes in after the hazards on its side, without and with
   each of its boost moves (formula damage on both sides, so that the stages count); others: my other answers to t */
static void boost_needs(Ctx *c, Mon *t, int j, int others)
{
    int k, i;
    s32 chip, r;
    Mon u;
    for (k = 0; k < 4 && !(c->me.legal[k] && boost_kind(&c->me.mv[k])); k++)
        ;
    if (k == 4)
        return;
    c->client ^= 1;
    r = hazard_hp(c, t, &chip);
    c->client ^= 1;
    if (r >= t->hp)
        return;
    t->hp -= r;
    c->bstake[j] = worth(t->hp, t->maxhp) >> others;
    for (k = 0; k < 5; k++) {
        const MoveInfo *m = &c->me.mv[k & 3];
        u = c->me;
        u.hp = u.maxhp;
        if (k < 4 && !(c->me.legal[k] && boost_kind(m)))
            continue;
        for (i = 0; i < 3 && k < 4; i++)
            if ((r = m->rank_type[i] - 1) >= 0 && r < 7)
                u.stage[r] = clamp(u.stage[r] + m->rank_val[i], 0, 12);
        if (t->ability == AB_INTIMIDATE && u.stage[0])
            u.stage[0]--;
        r = beats(&u, t, c->weather, 0, 0);
        c->bneed[k][j] = r ? (r * 255 + u.maxhp - 1) / u.maxhp : 0;
    }
}

/* what my boost move (slot) adds to my active's roles when it ends the race at hp: per foe off the field, its stake by
   how surely my active beats it with the stages against without them (as role_loss counts a loss) */
static s32 boost_carry(const Ctx *c, int slot, s32 hp)
{
    int j, k;
    s32 v = 0, top = 0, m = c->me.maxhp / 8 + 1, l, e[2];
    for (j = 0; j < MAX_BENCH; j++) {
        for (k = 0; k < 2; k++) {
            int need = c->bneed[k ? slot : 4][j];
            e[k] = need ? clamp(hp - need * c->me.maxhp / 255, 0, m) : 0;
        }
        v += l = c->bstake[j] * (e[1] - e[0]) / m;
        if (l > top)
            top = l;
    }
    return (v + top) / 2 * ROLE_W / 1000;
}

/* the team plan for foe t off the field (column j, its party slot - 1): which of my Pokemon beat it (its answers) and the
   HP each needs for it, every row or only my active's (from: c->nbench; the bench rows are already in c). Losing an
   answer costs that foe's worth when it is the only one, as the foe then beats the rest; with several, half as much per
   other answer (each may be lost before it is needed). boost_needs lowers t's HP */
static void role_of(Ctx *c, Mon *t, int j, int from)
{
    int k, wins = 0;
    s32 r;
    for (k = from; k <= c->nbench; k++) {
        const Mon *a = k < c->nbench ? &c->bench[k] : &c->me;
        r = beats(a, t, c->weather, a->bpp ? (k < c->nbench ? c->d_bo[k] : c->d_mo) : 0, &c->opp);
        c->need[k < c->nbench ? k : WHO_ACTIVE][j] = r ? (r * 255 + a->maxhp - 1) / a->maxhp : 0;
    }
    for (k = 0; k <= MAX_BENCH; k++)
        wins += c->need[k][j] > 0;
    c->stake[j] = wins ? worth(t->hp, t->maxhp) >> (wins - 1) : 0;
    boost_needs(c, t, j, wins - !!c->need[WHO_ACTIVE][j]);
}

static void roles(Ctx *c)
{
    void *op = E_PARTY(E_POKECON(1), c->opp_client);
    int i, n;
    Mon t;
    memset(c->need, 0, sizeof c->need);
    memset(c->stake, 0, sizeof c->stake);
    memset(c->bneed, 0, sizeof c->bneed);
    n = OK_PTR(op) ? E_PARTY_COUNT(op) : 0;
    for (i = 1; i < n && i < 6; i++) {
        void *b = E_PARTY_MEMBER(op, i);
        if (b != c->opp.bpp && OK_PTR(b) && B_HP(b) && E_FIGHTABLE(b) && read_mon(&t, b, i))
            role_of(c, &t, i - 1, 0);
    }
}

static u16 pair_damage(Ctx *c, const Mon *a, const Mon *d, const MoveInfo *m, int d_on_field);

_Static_assert(READS_AT + 2 * sizeof(Read) <= REPLACED_AT, "the two Read records end where the Replaced records start");

static Read *reads(const Ctx *c) { return (Read *)READS_AT + ((c->client & 1) ^ 1); }

/* the strength the record gives; none without a record (the bench, a battle's first decision) */
static int strength_of(const Ctx *c)
{
    const Read *r = reads(c);
    return r->magic == READ_MAGIC ? r->s : 0;
}

__attribute__((noinline)) static int pp_sum(void *b)
{
    int k, s = 0;
    for (k = 0; k < 4; k++)
        s += B_PP(b, k);
    return s & 0xFF;
}

/* at each decision in singles (sig: the foe's party, its species added up): what the foe did since my last decision. It
   stayed and used a move (its PP went down): an attack, or a status move that worked or not. It took out a Pokemon that
   can still fight for the one out now, with no move (not U-turn or Baton Pass) and not forced out by my Roar or Dragon
   Tail (priority -6): a switch, kept as its habit when my Pokemon stayed. A switch-in I named that did not come is a
   miss. Then c->strong */
static void strength(Ctx *c, int sig)
{
    Read *r = reads(c);
    Habit *h = &habit[(c->client & 1) ^ 1];
    const Mon *d = &c->opp, *a = &c->me;
    int k, pp = pp_sum(d->bpp), dl = 0, last = B_LAST_MOVE(a->bpp), f = r->miss, n = f & 7;
    if (r->magic != READ_MAGIC || (r->pinned != 1 && r->sig != (u16)sig)) {
        memset(r, 0, sizeof *r);
        memset(h, 0, sizeof *h);
        r->magic = READ_MAGIC;
        r->sig = sig;
        r->llr = LLR0;
        n = 0;
    } else if (OK_PTR(r->foe)) {
        if (f & READ_PREDICTED)
            n = r->foe != d->bpp && d->species == h->named ? 0 : n + (n < 7);
        if (r->foe == d->bpp) {
            for (k = 0; k < 4 && pp != r->pp; k++)
                if (d->mv[k].id == B_LAST_MOVE(d->bpp))
                    dl = d->mv[k].cls ? -LLR_ATTACK : B_WORKED(d->bpp) && (d->mv[k].efx != X_PROTECT || d->protects) ? LLR_WORKED :
                         d->mv[k].acc < 100 ? -LLR_FAILED / 2 : -LLR_FAILED;
        } else if (d->turns == 1 && B_HP(r->foe) && pp_sum(r->foe) == r->pp &&
                   !(a->turns > 1 && last && last < 1000 && (s8)waza(last, WP_PRIO) == -6)) {
            dl = f & READ_WINS ? -LLR_WASTE : LLR_SWITCH;
            for (k = 0; k < 4 && a->turns > 1; k++)
                if (a->mv[k].id == last) {
                    const MoveInfo *m = &a->mv[k];
                    s32 e = !m->cls ? 1000 * !!B_WORKED(a->bpp) : m->id == MV_SUCKER_PUNCH || !move_damage(a, d, m, 1) ? 0 : eff_move(a, d, m);
                    dl = e < 1000 ? LLR_GOOD : e > 1000 ? -LLR_WASTE : dl;
                }
            if (a->turns > 1) {
                h->me = a->species;
                h->out = B_SPECIES(r->foe);
                h->in = d->species;
            }
        }
        if (r->pinned != 1)
            r->llr = clamp(r->llr + dl, -LLR_MAX, LLR_MAX);
    }
    r->miss = n;
    r->foe = d->bpp;
    r->pp = pp;
    c->strong = r->s = 1000 * clamp(r->llr, 0, LLR_MAX) / LLR_MAX;
}

/* the foe's likely switch-in (foes[0]): what the hazards on its side take from it, and the damage both ways (its
   Intimidate lands before my move). None when the foe cannot switch: trapped, recharging, or its charged move lands */
static void switch_in(Ctx *c)
{
    u8 *main = AT(bptr, MAIN_PTR);
    void *cw = OK_PTR(main) ? AT(vptr, (u32)main + MAIN_CLIENTS + 4 * c->opp_client) : 0;
    Mon *x = &c->foes[0];
    s32 h, chip;
    int k;
    u8 o1 = 0;
    u16 o2 = 0;
    if (!OK_PTR(cw) || c->opp.charging || (B_TURNFLAGS(c->opp.bpp) & 2) || E_TRAPPED(cw, c->opp.bpp, &o1, &o2))
        return;
    weather_moves(x, c->weather, c->weather);
    c->client ^= 1;                        /* the hazards on the foe's side */
    h = hazard_hp(c, x, &chip);
    c->client ^= 1;
    if (h >= x->hp)
        return;
    c->xhaz = worth(x->hp, x->maxhp) - worth(x->hp - h, x->maxhp);
    x->hp -= h;
    for (k = 0; k < 4; k++) {
        c->d_mf[0][k] = clamp(pair_damage(c, &c->me, x, &c->me.mv[k], 0) * entry_mult(x, &c->me, c->me.mv[k].cls) / 64, 0, 0xFFFF);
        c->d_mf[1][k] = x->pp[k] ? pair_damage(c, x, &c->me, &x->mv[k], 1) : 0;
    }
    c->xin = 1;
}

/* my Pokemon's attack knocks t out at the HP it has before t moves (priority, or faster), Sash and Sturdy aside */
static int falls(const Ctx *c, const Mon *t)
{
    const Mon *a = &c->me;
    int k, f = faster(eff_speed(a, c->weather), eff_speed(t, c->weather));
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &a->mv[k];
        if (a->legal[k] && (m->prio > 0 || f) &&
            move_damage(a, t, m, formula_damage(a, t, m, c->weather)) * MY_ROLL / 1000 >= t->hp &&
            !(t->hp == t->maxhp && endures(t, a) && !multi(a, m)))
            return 1;
    }
    return 0;
}

/* read_choice: what foe d's committed action k changes before this turn's moves (op: its party). Its switch puts the
   newcomer on the field first: the newcomer, after the hazards on its side, becomes d, my move still aims at the
   position (k->tgt), and the foe does nothing else this turn; 1 then. Its item heals or cures its target first and is
   its turn. The records of the foe's play (remember, strength) keep the Pokemon that was on the field */
/* a foe's committed item on d, which acts before any move: its heal and cure */
static void item_on(Mon *d, int item)
{
    d->hp = clamp(d->hp + heal_amount(item, d), 0, d->maxhp);
    if (cures(item, d->status)) {
        d->status = S_NONE;
        d->slept = d->sleep = 0;
    }
}

static int foe_committed(Ctx *c, Mon *d, Known *k, void *op)
{
    if (k->kind == FK_SWITCH) {
        void *b = OK_PTR(op) ? E_PARTY_MEMBER(op, k->idx) : 0;
        Mon t;
        s32 h, chip;
        if (!OK_PTR(b) || b == c->opp.bpp || (c->doubles && (b == c->foes[0].bpp || b == c->foes[1].bpp)) ||
            !read_mon(&t, b, k->idx) || !t.alive) {
            k->kind = FK_NONE;
            return 0;
        }
        weather_moves(&t, c->weather, c->weather);
        c->client ^= 1;                        /* the hazards on the foe's side */
        h = hazard_hp(c, &t, &chip);
        c->client ^= 1;
        t.shield = (grounded(&t) ? terrain_shield(c) : 0) | (d->shield & SHIELD_STATUS);
        if (h >= t.hp) {                       /* it falls on entry: its replacement is unknown */
            k->kind = FK_NONE;
            return 0;
        }
        t.hp -= h;
        t.fresh = 1;
        k->tgt = d->id;
        if (!c->doubles)
            c->spare = *d;
        *d = t;
        return 1;
    }
    if (k->kind == FK_ITEM && k->idx == d->id)
        item_on(d, k->item);
    return 0;
}

static int snapshot(Ctx *c)
{
    u8 *main = AT(bptr, MAIN_PTR);
    void *pc, *party, *op;
    const Habit *hb;
    int n, i, k, sig;
    s32 e, least;
    c->strong = c->xin = c->xslot = 0;
    if (!OK_PTR(main) || !OK_PTR(c->st))
        return FB_MAIN;
    pc = E_POKECON(1);
    if (!OK_PTR(pc))
        return FB_MAIN;
    if (!read_mon(&c->me, AT(vptr, (u32)c->st + 4), 0) || !c->me.alive)
        return FB_ME;
    c->client = E_CLIENT_OF(c->me.id);
    if (c->client > 3)
        return FB_SNAPSHOT;
    c->opp_client = c->client ^ 1;
    hb = &habit[(c->client & 1) ^ 1];
    {
        int mine = E_ACTIVES(c->client), theirs = E_ACTIVES(c->opp_client);
        void *partner = E_PARTY(pc, c->client ^ 2), *opp2 = E_PARTY(pc, c->client ^ 3);
        int multi_me = OK_PTR(partner) && E_PARTY_COUNT(partner), multi_opp = OK_PTR(opp2) && E_PARTY_COUNT(opp2);
        if (mine > 2 || theirs > 2)
            return FB_NOT_SINGLES;
        c->doubles = mine == 2 || theirs == 2 || multi_me || multi_opp;
        if (c->doubles)
            return snapshot_doubles(c, pc, main);
    }
    party = E_PARTY(pc, c->client);
    op = E_PARTY(pc, c->opp_client);
    if (!OK_PTR(party) || !OK_PTR(op) || E_PARTY_MEMBER(party, 0) != c->me.bpp)
        return FB_SNAPSHOT;
    if (!read_mon(&c->opp, E_PARTY_MEMBER(op, 0), 0) || !c->opp.alive)
        return FB_OPP;
    c->opp.subbed = subbed(c->opp_client, 0);
    lock_foe(&c->opp);
    if (A1(A1_REACH) && c->opp.charging)
        called_charge(&c->opp);
    c->opp_others = 0;
    c->spare.bpp = 0;
    memset(c->absorb, 0, sizeof c->absorb);
    c->haz[0] = c->haz[1] = c->haz[2] = 0;
    for (i = 0, least = 0; i < 4; i++)     /* my strongest attack */
        if (c->me.legal[i] && (e = formula_damage(&c->me, &c->opp, &c->me.mv[i], W_NONE) * hits_x10(&c->me.mv[i])) > least) {
            least = e;
            c->xslot = i;
        }
    least = 0x7FFFFFFF;
    sig = c->opp.species;
    n = E_PARTY_COUNT(op);
    for (i = 1; i < n && i < 6; i++) {
        void *b = E_PARTY_MEMBER(op, i);
        Mon t;
        if (OK_PTR(b))
            sig += B_SPECIES(b);
        if (OK_PTR(b) && B_HP(b) && E_FIGHTABLE(b)) {
            c->opp_others++;
            if (read_mon(&t, b, i)) {
                const MoveInfo *m = &c->me.mv[c->xslot];
                s32 h;
                imposter_copy(c, &t);
                h = t.hp;
                if (!c->spare.bpp)
                    c->spare = t;
                /* the foe's answer to my strongest attack: the one it hurts least (an immunity or an absorbing ability
                   takes nothing), less half of what its best attack takes from my Pokemon (a counter over a wall), that
                   does not then fall to my next attack before it moves, nor to this one; first, the one it brought
                   before against my Pokemon (Habit) */
                t.hp -= e = move_damage(&c->me, &t, m, formula_damage(&c->me, &t, m, W_NONE));
                e = e * 1000 / t.maxhp + (t.hp <= 0 ? 4000 : falls(c, &t) ? 2000 : 0);
                t.hp = h;
                for (k = 0, h = 0; k < 4; k++) {
                    s32 x = formula_damage(&t, &c->me, &t.mv[k], W_NONE);
                    if (x > h)
                        h = x;
                }
                e -= clamp(h * 1000 / c->me.hp, 0, 1000) / 2;
                if (t.species == hb->in && c->opp.species == hb->out && c->me.species == hb->me)
                    e -= 8000;
                if (e < least) {
                    least = e;
                    c->foes[0] = t;
                }
                for (k = 0; k < 4; k++)
                    c->absorb[k] += !move_damage(&c->me, &t, &c->me.mv[k], 1);
                foe_hazards(c, &t);
            }
        }
    }
    c->nbench = 0;
    n = E_PARTY_COUNT(party);
    for (i = 1; i < n && i < 6 && c->nbench < MAX_BENCH; i++) {
        Mon *m = &c->bench[c->nbench];
        if (read_mon(m, E_PARTY_MEMBER(party, i), i) && m->alive) {
            m->sleep += m->slept == 2;      /* back on the field after two turns asleep, it sleeps one more half the time */
            imposter_copy(c, m);
            c->nbench++;
        }
    }
    snapshot_common(c, pc, main);
    remember(c, &c->opp, 1);
    strength(c, sig);
    return FB_NONE;
}

static void debug_snapshot(Ctx *c)
{
    int i;
    Debug *g = c->dbg;
    g->magic = DEBUG_MAGIC;
    g->version = 5;
    g->strong = c->strong;
    g->sw_species = g->sw_w = g->role = 0;
    g->me_species = c->me.species;
    g->opp_species = c->opp.species;
    g->me_hp = c->me.hp;
    g->me_maxhp = c->me.maxhp;
    g->opp_hp = c->opp.hp;
    g->opp_maxhp = c->opp.maxhp;
    for (i = 0; i < 5; i++) {
        g->me_stat[i] = c->me.stat[i];
        g->opp_stat[i] = c->opp.stat[i];
    }
    for (i = 0; i < 3; i++) {
        g->me_types[i] = c->me.types[i];
        g->opp_types[i] = c->opp.types[i];
    }
    g->me_level = c->me.level;
    g->opp_level = c->opp.level;
    g->me_status = c->me.status;
    g->opp_status = c->opp.status;
    g->me_ability = c->me.ability;
    g->opp_ability = c->opp.ability;
    g->me_item = c->me.item;
    g->opp_item = c->opp.item;
    for (i = 0; i < 4; i++) {
        g->me_moves[i] = c->me.mv[i].id;
        g->opp_moves[i] = c->opp.mv[i].id;
        g->d_mo[i] = c->d_mo[i];
        g->d_om[i] = c->d_om[i];
        g->f_mo[i] = c->me.mv[i].id ? formula_damage(&c->me, &c->opp, &c->me.mv[i], c->weather) : 0;
        g->f_om[i] = c->opp.mv[i].id ? formula_damage(&c->opp, &c->me, &c->opp.mv[i], c->weather) : 0;
    }
    g->weather = c->weather;
    g->nbench = c->nbench;
    g->trapped = c->trapped;
    g->doubles = c->doubles;
    g->legal = 0;
    for (i = 0; i < 4; i++)
        if (c->me.legal[i])
            g->legal |= 1 << i;
}

/* the attacker's own multipliers (ability, item) on move m, from a simulation against a Pokemon off the field,
   whose handlers are not registered: the defender's side first (its screens count), then the other side */
static s32 proxy_damage(Ctx *c, const Mon *a, const Mon *d, const MoveInfo *m)
{
    s32 f = formula_damage(a, d, m, c->weather);
    int k, n = c->nbench + 1, mine = (E_CLIENT_OF(d->id) & 1) == (c->client & 1), ai = sim_id(c, a);
    for (k = 0; k < n; k++) {
        int j = mine ? k : (k + n - 1) % n;      /* mine: my bench, then the spare; else the spare first */
        const Mon *p = j < c->nbench ? &c->bench[j] : &c->spare;
        s32 fp, sp;
        if (!p->bpp || p->id == a->id || p->id == d->id || sim_id(c, p) != p->id)
            continue;
        fp = formula_damage(a, p, m, c->weather);
        if (fp <= 0)
            continue;
        sp = sim_max(ai, p->id, m->id, c->unsure);
        if (sp <= 1)
            continue;
        f = f * sp / fp;
        break;
    }
    return f;
}

/* raw max-roll damage of a's move m on d. The simulation applies the attacker's ability and item wherever it
   is, the defender's only when it is on the field (measured), so for a defender off the field our table adds
   them. A resist berry on a defender on the field is never simulated: the simulation that sets off the
   berry leaves it spent for the real hit (measured: the berry is eaten and the damage is not halved) */
static u16 pair_damage(Ctx *c, const Mon *a, const Mon *d, const MoveInfo *m, int d_on_field)
{
    s32 v;
    int ai = sim_id(c, a), di = sim_id(c, d);
    if (!m->id || !m->cls)
        return 0;
    if (ai < 0 || di < 0)               /* a stale Imposter copy (sim_id): our formula */
        v = defender_mods(a, d, m, formula_damage(a, d, m, c->weather));
    else if (d_on_field && berry_fires(a, d, m))
        v = defender_mods(a, d, m, proxy_damage(c, a, d, m));
    else {
        v = sim_fix(c->weather, a, d, m, sim_max(ai, di, m->id, c->unsure));
        if (!d_on_field && di == d->id)     /* a copy's simulation stands on the field */
            v = defender_mods(a, d, m, v);
    }
    return clamp(v, 0, 0xFFFF);
}

static void sims_active(Ctx *c)
{
    const Mon *d = &c->opp;
    int i;
    for (i = 0; i < 4; i++) {
        c->d_mo[i] = pair_damage(c, &c->me, d, &c->me.mv[i], !d->party);
        c->d_om[i] = d->pp[i] ? pair_damage(c, d, &c->me, &d->mv[i], 1) : 0;
    }
}

static void damage_bench(Ctx *c, int b)
{
    const Mon *d = &c->opp;
    int i;
    Mon *s = &c->bench[b];
    for (i = 0; i < 4; i++) {
        const MoveInfo *m = &d->mv[i];
        c->d_bo[b][i] = pair_damage(c, s, d, &s->mv[i], !d->party);   /* ai_replace values foes off the field too */
        c->d_ob[b][i] = d->pp[i] ? clamp(pair_damage(c, d, s, m, 0) * entry_mult(s, d, m->cls) / 64, 0, 0xFFFF) : 0;
    }
}

/* the option to take: the best value, unless a comparable one (NEAR) knocks out more surely, commits less or deals
   more damage, without losing my Pokemon this turn for nothing more often than the best value does; KO chances count
   only the turns its user acts. ai_debug.why records what took it over the best value */
static int pick(const Ctx *c, const Option *opt, int n, Option *best)
{
    Debug *g = c->dbg;
    s32 top = -0x7FFFFFFF, key, pref, bp = 0, kb = 0, kt = 0, pt = 0;
    int i, b = -1, t = 0, lost, heal8, di, db;
    g->nopt = n;
    for (i = 0; i < n; i++) {
        g->opt[i].kind = opt[i].kind;
        g->opt[i].idx = opt[i].idx;
        g->opt[i].extra = opt[i].extra;
        g->opt[i].value = opt[i].value;
        if (opt[i].value > top) {
            top = opt[i].value;
            t = i;
        }
    }
    lost = top < LOST;
    /* lost, damage the foe heals back each turn is no reason to leave the top value */
    heal8 = lost ? heal_move(&c->opp, c->weather) * 8 / c->opp.maxhp : 0;
    for (i = 0; i < n; i++) {
        key = (lost ? 3 * opt[i].ko1 : opt[i].ko3) >> 6;     /* in 6.4% steps: a few points of KO chance are no surer KO */
        /* a move whose user mostly falls first knocks out only when the foe errs, which a strong foe does not */
        if (opt[i].fell * c->strong >= 125000)
            key = 0;
        /* what a move commits me to separates moves that KO alike; a self-KO always costs */
        pref = key * 256 - (key ? opt[i].cost : 0) - 255 * opt[i].selfko;
        if (i == t) {
            kt = key;
            pt = pref;
        }
        /* then the one that leaves the foe on less HP this turn, then the value */
        di = opt[i].dealt > heal8 ? opt[i].dealt : 0;
        db = b >= 0 && opt[b].dealt > heal8 ? opt[b].dealt : 0;
        if (opt[i].value >= top - (lost ? NEAR_LOST : NEAR) && opt[i].fell <= opt[t].fell + FELL_SLACK &&
            (b < 0 || pref > bp || (pref == bp && (di > db || (di == db && (opt[i].value > opt[b].value ||
                                    (opt[i].value == opt[b].value && opt[i].spared > opt[b].spared))))))) {
            b = i;
            bp = pref;
            kb = key;
        }
    }
    if (b < 0)
        return 0;
    *best = opt[b];
    g->chosen = b;
    g->why = opt[b].value == top ? WHY_TOP : kb != kt ? (opt[b].st ? WHY_STATUS : WHY_KO) : bp != pt ? WHY_COST : WHY_DEALT;
    g->lost = lost;
    return 1;
}

/* the HP (per-mille of its max) bench Pokemon i loses coming in, over the player's moves at their odds; a status that
   lands on it counts as half its HP, so a newcomer immune to the foe's status move goes first among equals */
static s32 entry_loss(const Ctx *c, const Pair *p, int i)
{
    s32 sum = 0, hit, h = c->ent_me[i].hp;
    int k, n = 0, ko;
    for (k = 0; k < 4; k++) {
        if (!p->w[k])
            continue;
        ko = entry_hit(c, i, k, &hit);
        sum += p->w[k] * (ko * h + (100 - ko) * hit) / 100;
        if (sickens(&c->opp.mv[k]) && !status_blocked(c, &c->opp, &c->bench[i], &c->opp.mv[k]))
            sum += p->w[k] * move_acc(&c->opp, &c->bench[i], &c->opp.mv[k], c->weather) * c->bench[i].maxhp / 200;
        n += p->w[k];
    }
    return h <= 0 ? 1000 : n ? sum * 1000 / n / c->bench[i].maxhp : 0;     /* the hazards knock it out */
}

/* my switches. The newcomer takes a move the player picked for my active Pokemon, and the player's choice is never
   sure: a strong player (c->strong) sees the switch coming and picks the attack or status move that hurts the newcomer
   most, up to half the weight (a Pokemon already statused takes a sleep move for nothing). Among switch-ins of about
   the same value, the one that loses the least HP coming in goes first */
static int switches(Ctx *c, const Pair *p, Option *opt, int n)
{
    const Mon *d = &c->opp;
    int i, j, k, n0 = n, low = -1, doom = n > 0, wmax = 0;
    s32 top = -0x7FFFFFFF, loss, lowloss = 0, v, w, best = 0, e[4];
    Pair q = *p;
    /* doom: every move loses my Pokemon this turn 4 times in 5, by the reply model (reply_odds: a KO that surely lands
       first gets all the weight) */
    for (j = 0; j < n0; j++)
        doom &= opt[j].fell >= 200;
    /* the attacks the player may well pick: its knockouts about as likely as the likeliest (a priority one that lands
       first, before the others), and with no knockout every attack two thirds as strong on my Pokemon as its best */
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &d->mv[k];
        e[k] = p->w[k] && m->cls ? move_damage(d, &c->me, m, c->d_om[k]) * hits_x10(m) / 10 : 0;
        if (e[k] > best)
            best = e[k];
        if (e[k] && p->w[k] > wmax)
            wmax = p->w[k];
    }
    for (i = 0; i < c->nbench && n < MAX_OPT; i++, n++) {
        opt[n].kind = K_SWITCH;
        opt[n].idx = i;
        opt[n].extra = c->bench[i].party;
        opt[n].value = mixed(c, p, K_SWITCH, i);
        opt[n].fell = clamp(g_fell / 4, 0, 250);
        /* a player that sees the switch coming takes, among those, the one that hurts the newcomer most: half the weight */
        for (k = 0, w = 0x7FFFFFFF; k < 4; k++)
            if (e[k] && (p->ko ? p->w[k] >= 5 && 4 * p->w[k] >= wmax : p->w[k] >= 5 || 3 * e[k] >= 2 * best)) {
                q.rep = k;
                v = value_switch(c, &q, i);
                if (v < w)
                    w = v;
            }
        if (w < opt[n].value)
            opt[n].value = (opt[n].value + w) / 2;
        /* not while the foe sleeps or recharges, nor when its committed action is known (known_reply keeps p->rep) */
        for (k = 0, w = 0x7FFFFFFF; c->strong && p->rep >= 0 && !c->kn[0].kind && k < 4; k++)
            if (d->legal[k] && (d->mv[k].cls || sickens(&d->mv[k]))) {
                q.rep = k;
                v = value_switch(c, &q, i);
                if (v < w)
                    w = v;
            }
        if (w < opt[n].value)
            opt[n].value -= (opt[n].value - w) * c->strong / 2000;
        if (opt[n].value > top)
            top = opt[n].value;
    }
    for (j = n0; j < n; j++) {
        if (opt[j].value < top - 2 * NEAR || (doom && opt[j].fell >= 125))     /* not one that falls first while mine is doomed */
            continue;
        loss = entry_loss(c, p, opt[j].idx);
        if (low < 0 || loss < lowloss) {
            low = j;
            lowloss = loss;
        }
    }
    if (low >= 0)                   /* also over switch-ins of the same value */
        opt[low].value = top + 1;
    return n;
}

static void swap_bytes(void *a, void *b, int n)
{
    u8 *x = a, *y = b, t;
    while (n--) {
        t = *x;
        *x++ = *y;
        *y++ = t;
    }
}

/* my move `slot` when the foe switches in the Pokemon in c->opp (swapped in): the switch is its action this turn, then
   the race; the hazards' toll on it counts. An attack it is immune to hits for nothing, and one its ability absorbs for a
   stage on its race attack makes that attack x1.5 (it comes in with about all its HP: a heal does little); a status move
   that cannot work on it is a turn that does nothing */
static s32 vs_switch(Ctx *c, Pair *q, int slot)
{
    const MoveInfo *m = &c->me.mv[slot];
    s32 rate = q->opp_rate, v;
    int g = absorbs(&c->opp, &c->me, m);
    if (g > 1 && (unsigned)q->opp_slot < 4 && c->opp.mv[q->opp_slot].cls == 4 - g)
        q->opp_rate = rate * 3 / 2;
    g_ko1 = g_ko3 = g_dealt = 0;
    v = c->xhaz + value_of(c, q, m->cls || m->id == MV_SLEEP_TALK ? K_MOVE : vetoed(c, slot) ? K_MOVE + 4 : K_MOVE + 3, slot);
    q->opp_rate = rate;
    return v;
}

/* what my move k's average hit takes from the foe on the field, on the team scale */
static s32 hit_loss(const Ctx *c, int k)
{
    const Mon *d = &c->opp;
    const MoveInfo *m = &c->me.mv[k];
    return worth(d->hp, d->maxhp) - worth(d->hp - expected(&c->me, d, move_damage(&c->me, d, m, c->d_mo[k]), m, c->weather), d->maxhp);
}

/* the exchange on the field if both stay, each with its best attack from now (priority finishers, Counter): 1 the foe's
   Pokemon falls first, 2 mine does, 0 neither within the race */
static int exchange(Ctx *c, const Pair *p)
{
    Fighter A, B;
    int n;
    pair_fighters(c, p, &A, &B);
    prime(&A, &c->me, &c->opp, c->d_mo, c->weather, MY_ROLL);
    arm(&A, &c->me, &c->opp, p->my_slot);
    arm(&B, &c->opp, &c->me, p->opp_slot);
    counter_fight(&A, &c->me, &c->opp, p->opp_slot, p->opp_rate);
    counter_fight(&B, &c->opp, &c->me, p->my_slot, p->my_rate);
    race_core(&A, &B, 0, &n);
    return A.hp <= 0 ? 2 : B.hp <= 0;
}

/* The foe's switch to its answer (c->foes[0]), unless its Pokemon on the field wins the exchange by staying (the caller
   checks). Its odds w (per-mille), from the foe's side: twice what the switch saves it, by my strongest attack (the one
   it expects) against each case, up to 70% (at a third of a Pokemon's worth), at any strength: from half to all of
   that as it plays strongly (c->strong); less after each prediction of this switch-in it did not make
   (2 / (2 + misses)); at least half when it made this switch before against my Pokemon. Each move is then worth
   (1 - w) x its value if the foe stays + w x its value against the switch-in (switch_case). A move vetoed against the
   foe on the field (vm, legal) joins as a lost turn if it stays, when the switch is likely and the move works on the
   switch-in. A sure KO on the Pokemon in front is never given up for the guess: then the other moves keep their
   values if the foe stays, and the sure KOs above them lose w x what each covers the switch-in worse than the best
   of them (which keeps its value), never down to the rest.
   Returns what the expected attack lost, which my switches and items lose too: what the foe's switch does to them is
   not valued, and it must not push me out of an exchange I win */
#define SURE_KO 750
/* my move k against the foe's switch-in (swapped into c->opp, q its pair): at least the expected attack's value
   there (vj, lj its hit on the foe on the field) plus the HP its hit takes beyond that attack's, unless the hit
   sets off a Weakness Policy (a race against a healer can end anywhere in its heal cycle); a jump kick it is immune
   to crashes (half my HP, on the team scale) */
static s32 switch_case(Ctx *c, Pair *q, int k, s32 vj, s32 lj)
{
    const Mon *a = &c->me;
    const MoveInfo *m = &a->mv[k];
    s32 v = vs_switch(c, q, k), d = vj + hit_loss(c, k) - lj;
    if (d > v && policy(&c->opp, a, m, q->opp_slot) == 64)
        v = d;
    if ((m->id == MV_HI_JUMP_KICK || m->id == MV_JUMP_KICK) && !move_damage(a, &c->opp, m, 1))
        v -= (1000 - WORTH_BASE) / 2;
    return v;
}

static s32 foe_switch(Ctx *c, const Pair *p, Option *opt, int *pn, int vm)
{
    Read *r = reads(c);
    Habit *h = &habit[(c->client & 1) ^ 1];
    const Mon *a = &c->me;
    Pair q;
    s32 w, v, vj, lj, sj = -100000, hi = -0x7FFFFFFF, vmax = -0x7FFFFFFF;
    int i, k, n = *pn, n0 = n, sure = 0, sp = c->foes[0].species,
        before = sp == h->in && c->opp.species == h->out && a->species == h->me;
    for (i = 0; i < n; i++) {
        if (opt[i].idx == c->xslot)
            sj = opt[i].value;
        if (opt[i].ko1 >= SURE_KO)
            sure = 1;
        else if (opt[i].value > hi)
            hi = opt[i].value;
    }
    for (k = 0; k < 4 && n < MAX_OPT; k++)
        if ((vm >> k) & 1) {
            opt[n].kind = K_MOVE;
            opt[n].idx = k;
            opt[n].value = mixed(c, p, K_MOVE + 4, k);
            opt[n++].fell = clamp(g_fell / 4, 0, 250);
        }
    swap_bytes(&c->opp, &c->foes[0], sizeof c->opp);
    swap_bytes(c->d_mo, c->d_mf, sizeof c->d_mo * 2);
    pair_data(c, &q);
    q.rep = -1;
    q.opp_hit = 0;
    vj = vs_switch(c, &q, c->xslot);
    lj = hit_loss(c, c->xslot);
    w = clamp(2 * (sj - vj), 0, 700) * (500 + c->strong / 2) / 1000;
    if (sp == h->named)
        w = w * 2 / (2 + (r->miss & 7));
    if (w && w < 500 && before)
        w = 500;
    for (i = 0; i < n0; i++)        /* the best switch case among the sure KOs above the rest */
        if (sure && opt[i].value > hi && (v = switch_case(c, &q, opt[i].idx, vj, lj)) > vmax)
            vmax = v;
    for (i = k = 0; i < n; i++) {
        Option *o = &opt[i];
        int x = sure && o->ko1 < SURE_KO ? 0 : w, top = sure && o->value > hi;
        if (i >= n0 && (x < READ_W || vetoed(c, o->idx)))
            continue;
        v = switch_case(c, &q, o->idx, vj, lj);
        if (top)                    /* a sure KO above the rest loses only what it covers the switch-in worse */
            v += o->value - vmax;
        o->value += (v - o->value) * x / 1000;
        o->ko1 += (g_ko1 - o->ko1) * x / 1000;
        o->ko3 += (g_ko3 - o->ko3) * x / 1000;
        o->dealt += (clamp(g_dealt / 125, 0, 8) - o->dealt) * x / 1000;
        o->fell = o->fell * (1000 - x) / 1000;    /* the switch-in does not hit me this turn */
        if (top && o->value <= hi)
            o->value = hi + 1;
        opt[k++] = *o;
    }
    *pn = k;
    swap_bytes(c->d_mo, c->d_mf, sizeof c->d_mo * 2);
    swap_bytes(&c->opp, &c->foes[0], sizeof c->opp);
    if (w >= READ_W) {
        if (sp != h->named)
            r->miss &= ~7;
        h->named = sp;
        r->miss |= READ_PREDICTED;
    }
    c->dbg->sw_species = sp;
    c->dbg->sw_w = w;
    c->xw = w;
    return (vj - sj) * w / 1000;
}

static int add_stay(Ctx *c, Pair *p, Option *opt, int n, int k)
{
    opt[n].kind = K_MOVE;
    opt[n].idx = k;
    opt[n].value = mixed(c, p, K_MOVE + 4, k);
    opt[n].fell = clamp(g_fell / 4, 0, 250);
    opt[n].selfko = self_ko_move(c->me.mv[k].id);
    return n + 1;
}

/* foe f's action this turn, committed before my decision (read_choice; singles: f 0): FK_NONE when not read (the
   player's side, the bench's NOREAD word, an action the setters do not describe); *idx its move slot (FK_MOVE), party
   index (FK_SWITCH) or its item's target pokeID (FK_ITEM). After a known switch, opp (foes[f]) is already the newcomer */
static int known_foe_action(const Ctx *c, int f, int *idx)
{
    *idx = c->kn[f].idx;
    return c->kn[f].kind;
}

/* read_choice: the foe's committed action makes its reply certain. Its move is the only reply, unless it cannot act in
   p's case (asleep, recharging: no reply there either); after its switch or its item it does nothing else */
static void known_reply(const Ctx *c, Pair *p)
{
    int k, i, kind = known_foe_action(c, 0, &i);
    if (kind == FK_MOVE && i < 4 && c->opp.legal[i] && p->w[0] + p->w[1] + p->w[2] + p->w[3]) {
        for (k = 0; k < 4; k++)
            p->w[k] = 0;
        p->w[i] = 10;
    } else if (kind == FK_SWITCH || kind == FK_ITEM) {
        for (k = 0; k < 4; k++)
            p->w[k] = 0;
        p->rep = -1;
        p->opp_hit = 0;
    }
}

/* the guard (rc33 F3, the plan's fsA): a knockout by the first mover that the trusted cells foresaw for the pair then
   played, and that did not happen (the second hit's target may have healed first: drain, Shell Bell), turns foresight off for the rest of the battle, so a wrong draw count (the order walk's above all) does
   not mislead twice. Per AI side, in main RAM: it outlives the slot's bss between turns. The host's cells are the real
   turn's, so it never fires there */
#ifdef HOST_ENGINE_H
#include <stdio.h>
#endif
static struct { u32 tag; u8 ko, off, pad[2]; } g_fsg[2] __attribute__((section(".main.data.fsg")));
static u32 steer_battle_tag(void);
static int fs_guard_off(const Ctx *c)
{
    u32 tag = steer_battle_tag();
    int ko;
    if (g_fsg[c->client & 1].tag != tag) {
        g_fsg[c->client & 1].tag = tag;
        g_fsg[c->client & 1].ko = g_fsg[c->client & 1].off = 0;
    }
    ko = g_fsg[c->client & 1].ko;
    if (ko && ((c->opp.id == ko && c->opp.hp > 0) || (c->me.id == ko && c->me.hp > 0))) {
        g_fsg[c->client & 1].off = 1;
#ifdef HOST_ENGINE_H
        if (getenv("FSG_DEBUG"))
            fprintf(stderr, "FSG fire ko %d me %d/%d hp %d opp %d/%d hp %d\n", ko, c->me.id, c->me.species, c->me.hp, c->opp.id, c->opp.species, c->opp.hp);
#endif
    }
    g_fsg[c->client & 1].ko = 0;
    return g_fsg[c->client & 1].off;
}
static void fs_guard_note(const Ctx *c, const Option *o)
{
    const FsCell *f;
    int first;
    if (!fs.on || !fs.trusted || !o || o->kind != K_MOVE || o->idx > 3 || !c->fs_move || c->fs_move > 4)
        return;
    f = &fs.cell[o->idx][c->fs_move - 1];
    first = fs.first[o->idx][c->fs_move - 1];
    if (first == 0 && f->mine && !f->stopped && !f->missed && f->dmg >= c->opp.hp)
        g_fsg[c->client & 1].ko = c->opp.id;
    else if (first == 1 && f->foe && !f->f_stopped && !f->f_missed && f->f_dmg >= c->me.hp)
        g_fsg[c->client & 1].ko = c->me.id;
}

#ifdef HOST_ENGINE_H
/* the host: the bridge filled every cell from the real turn; the DS predictor's rules keep what it could know (trusted:
   the cells were kept so, for the bridge's check of the turn then played) */
static void fs_predict(Ctx *c)
{
    int i, k;
    fs.on = 0;
    if (!fs_level || c->doubles || !c->fs_move || c->me.species != fs.me_species ||
        c->me.hp != fs.me_hp || c->opp.species != fs.opp_species || c->opp.hp != fs.opp_hp || fs_guard_off(c)) {
        fs.trusted = 0;
        return;
    }
    for (i = 0; i < 4; i++)
        for (k = 0; k < 4; k++)
            fs_settle(c, i, k, &fs.cell[i][k]);
    fs.on = fs.trusted = 1;
}
#else
/* The DS predictor. It trusts the LCG word only when nothing can draw between this decision and the turn: the foe's
   client has answered its choice with a move (foe_choice waited for it; a switch draws a message variant first,
   0x0222AAF8, and an item is not modelled), and a person's menu draws nothing (read from code: 0x02203654,
   0x02203F00). Doubles and tag battles (a partner's AI may draw after this decision) are not predicted. A value is
   BattleRandom's (0x0222646C): the signed word / 65536 truncated toward zero, as a u16, modulo n. Each played move draws, in order: its full paralysis roll (25, 0x0221DADE), accuracy
   (0x02206842: value < accuracy) unless the move data's accuracy is over 100, then on a hit the crit roll (0x0222622E:
   value 0 of 24, 8, 2, 1 by stage; 12, 4, 1, 1 for the player's Pokemon at friendship 255 unless hard mode is on, so
   a value the two disagree on is not known), the damage roll (0x022088E0), which the engine simulation draws itself
   from the word set just before it, and one roll per chance effect (0x022096DA, 0x022069BC, 0x02208DF8). A knockout
   of the player's Pokemon at friendship 180 or more may be survived on a roll (0x02208368): not known */
/* the word the turn starts from (the harness's, while aivsai's synced luck runs this call on my side's own stream), and
   whether the turn can be predicted from it */
static u32 fs_word(void)
{
    return AT(u32, FS_WORD_AT) == FS_WORD_MAGIC ? AT(u32, FS_WORD_AT + 4) : AT(u32, (u32)AT(bptr, MAIN_PTR) + MAIN_RNG);
}

static int fs_trust(const Ctx *c, u32 *word)
{
    *word = fs_word();
    return !c->doubles && c->fs_move;
}

static u32 g_fsx;                   /* the walk's LCG word */
static u32 fs_q(void)
{
    u32 q;
    g_fsx = g_fsx * 0x41C64E6Du + 0x6073u;
    q = g_fsx >> 16;
    if ((s32)g_fsx < 0 && (g_fsx & 0xFFFF))
        q = (q + 1) & 0xFFFF;
    return q;
}

/* the hit chance is the move data's own: no stage or modifier that move_acc may round otherwise than the engine */
static int fs_acc_exact(const Ctx *c, const Mon *x, const Mon *y)
{
    return x->stage[5] == 6 && y->stage[6] == 6 && x->ability != AB_COMPOUND_EYES && x->ability != AB_HUSTLE &&
           x->ability != AB_VICTORY_STAR && y->ability != AB_WONDER_SKIN && y->ability != AB_TANGLED_FEET &&
           y->item != IT_BRIGHTPOWDER && x->item != IT_WIDE_LENS && x->item != IT_ZOOM_LENS &&
           !(y->ability == AB_SAND_VEIL && c->weather == W_SAND) && !(y->ability == AB_SNOW_CLOAK && c->weather == W_HAIL);
}

/* the player's Pokemon (pokeIDs 1-12, the side the affection effects check) at friendship `at` or more */
static int fs_fond(const Mon *m, int at)
{
    return OK_PTR(m->bpp) && B_ID(m->bpp) <= 12 && AT(u8, (u32)m->bpp + 0x29F) >= at;
}

/* one move of the walk: own, its outcome known; after, every draw it makes counted (the next move's can be played);
   fell, it was flinched; flinch, it flinches the target; landed, its chance effect landed (the target's move changes);
   guard, its Protect holds (F2_PROT); roll, its damage roll index + 1 (0: no damage roll known); pre, knocked out
   before it moves */
typedef struct { u8 own, after, stopped, fell, missed, crit, flinch, landed, guard, roll, pre, par, slp, conf; s32 dmg; } FsOut;
static struct { u16 id, move; u32 word; s32 dmg; } g_fsd[16];   /* simulations done this decision */
static int g_nfsd;
/* the steer's walks (steer_fill): the engine simulation draws exactly one number, so its damage depends only on that
   roll's index (value % 16): one table of 16 per attacker and move instead of one simulation per word */
static u8 g_fs_byroll;
static struct { u16 id, move, have; s16 dmg[16]; } g_fsr[2];

/* the index (BattleRandom value % 16) of the draw after w: the damage roll's when w is the word before it */
static int fs_roll_ix(u32 w)
{
    u32 q;
    w = w * 0x41C64E6Du + 0x6073u;
    q = w >> 16;
    if ((s32)w < 0 && (w & 0xFFFF))
        q = (q + 1) & 0xFFFF;
    return q & 15;
}

static s32 fs_damage(const Mon *x, const Mon *y, const MoveInfo *m)
{
    volatile u32 *rng = (volatile u32 *)((u32)AT(bptr, MAIN_PTR) + MAIN_RNG);
    u32 saved = *rng, w = g_fsx;
    s32 dmg = -1;
    int j = 0, r = fs_roll_ix(w), e = 2;
    if (g_fs_byroll) {              /* the steer's walks: the table by roll index, not the per-word cache */
        for (e = 0; e < 2 && g_fsr[e].have && !(g_fsr[e].id == x->id && g_fsr[e].move == m->id); e++)
            ;
        if (e < 2 && g_fsr[e].have & (1 << r)) {
            g_fsx = w * 0x41C64E6Du + 0x6073u;
            return g_fsr[e].dmg[r];
        }
    } else
        for (j = 0; j < g_nfsd; j++)
            if (g_fsd[j].id == x->id && g_fsd[j].move == m->id && g_fsd[j].word == w)
                break;
    if (!g_fs_byroll && j < g_nfsd)
        dmg = g_fsd[j].dmg;
    else {
        *rng = w;
        wake_factors();
        waza_lend(m->id);
        dmg = E_SIM_DAMAGE(x->id, y->id, m->id);
        wake_factors();
        if (*rng != w * 0x41C64E6Du + 0x6073u || dmg <= 1)    /* it drew more than the roll, or thinks the move does nothing */
            dmg = -1;
        *rng = saved;
        if (e < 2) {
            g_fsr[e].id = x->id;
            g_fsr[e].move = m->id;
            g_fsr[e].have |= 1 << r;
            g_fsr[e].dmg[r] = dmg;
        } else if (!g_fs_byroll && g_nfsd < 16) {
            g_fsd[g_nfsd].id = x->id;
            g_fsd[g_nfsd].move = m->id;
            g_fsd[g_nfsd].word = w;
            g_fsd[g_nfsd++].dmg = dmg;
        }
    }
    g_fsx = w * 0x41C64E6Du + 0x6073u;
    return dmg;
}

/* x's move m on y (at yhp), x moving second or not; guarded: bit 0 y's Protect holds (F2_PROT), bit 1 the first move
   paralyzed x (F3_ACC: x draws its full paralysis roll), bit 2 it confused x (F3_LEN: x draws the 33 roll). The checks
   before a move
   run in the engine's order (0x0221D7A8): sleep (no draw), confusion, paralysis */
static void fs_move(const Ctx *c, const Mon *x, const Mon *y, const MoveInfo *m, s32 yhp, int second, int guarded, FsOut *o)
{
    static const u8 crit_n[4] = { 24, 8, 2, 1 }, fond_n[4] = { 12, 4, 1, 1 };
    static const u16 guard_n[7] = { 1, 3, 9, 27, 81, 243, 729 };
    u32 q;
    int acc, v, st, ch = 0, kd = 0, n, fl;
    s32 dmg;
    memset(o, 0, sizeof *o);
    if (fs_dozes(x) == 1) {
        o->stopped = o->own = o->after = 1;
        return;
    }
    if ((fs2(F2_CONF) && cond_on(x, C_CONFUSION)) || (guarded & 4)) {
        void *s = cond_on(x, C_CONFUSION) ? copy0(x->id) : 0;
        if (!s && !(guarded & 4))
            return;
        /* the countdown (0x02217508) ends it with no draw at the length; else the 33 roll (conf_roll), and a self-hit
           draws its damage roll (BattleRandom(16), 0x02220940) and ends the move */
        if ((!s || B_COND_COUNT(s, C_CONFUSION) + 1 < (int)((B_COND(s, C_CONFUSION) >> 3) & 63)) && fs_q() % 100 < 33) {
            fs_q();
            o->stopped = o->own = o->after = 1;
            return;
        }
    }
    if ((x->status == S_PAR || (guarded & 2)) && fs_q() % 100 < 25) {
        o->stopped = o->own = o->after = 1;
        return;
    }
    if (!m->cls) {
        if (m->efx == X_PROTECT && fs2(F2_PROT)) {
            n = fs_streak(x);
            o->guard = !n || fs_q() % guard_n[n] == 0;
            o->own = o->after = 1;
        } else if (fs_quiet(x, y, m))
            o->own = o->after = 1;
        else if ((v = fs_acc_kind(c, x, y, m)) != FA_NONE) {
            if (v == FA_DRAW) {
                u32 r = fs_q() % 100;
                acc = move_acc(x, y, m, c->weather);
                if (!fs_acc_exact(c, x, y) && r + 10 >= (u32)acc && r < (u32)acc + 10)
                    return;
                o->missed = r >= (u32)acc;
            } else
                o->missed = v == FA_FAIL;
            o->par = !o->missed && m->quality == Q_SICK && m->sick == S_PAR;
            o->own = o->after = 1;
        } else if ((v = fs_len_kind(c, x, y, m)) != FL_NONE) {
            int lo = waza(m->id, WP_SICK_TMIN), span = waza(m->id, WP_SICK_TMAX) - lo + 1;
            int swag = m->quality == Q_EFFECT_SICK;
            if (v != FL_FAIL0 && !swag)
                fs_q();                 /* the length drawn before the checks */
            o->own = o->after = o->missed = 1;
            if (v != FL_PLAY || span < 1)
                return;
            if (m->acc <= 100 && !(fs2(F2_NG) && (x->ability == AB_NO_GUARD || y->ability == AB_NO_GUARD))) {
                u32 r = fs_q() % 100;
                acc = move_acc(x, y, m, c->weather);
                if (!fs_acc_exact(c, x, y) && r + 10 >= (u32)acc && r < (u32)acc + 10) {
                    o->own = o->after = 0;
                    return;
                }
                if (r >= (u32)acc)
                    return;
            }
            o->missed = 0;
            n = fs_q() % span + lo;     /* the length kept */
            if (m->sick == S_SLP)
                o->slp = (y->ability == AB_EARLY_BIRD ? 2 : 1) < n ? 1 : 2;     /* sleeps through its attempt, or wakes */
            else if (m->sick == C_CONFUSION)
                o->conf = !cond_on(y, C_CONFUSION);
        }
        return;
    }
    if (guarded & 1) {
        o->missed = o->own = o->after = 1;
        return;
    }
    if (!fs_plain(c, x, y, m))
        return;
    if (m->acc <= 100 && !(fs2(F2_NG) && (x->ability == AB_NO_GUARD || y->ability == AB_NO_GUARD))) {
        v = fs_q() % 100;
        acc = acc_now(x, y, m, c->weather);
        if (!fs_acc_exact(c, x, y) && v + 10 >= acc && v < acc + 10)
            return;
        if (v >= acc) {
            o->missed = o->own = o->after = 1;
            return;
        }
    }
    st = waza(m->id, WP_CRIT) + (x->ability == AB_SUPER_LUCK) + (x->item == IT_SCOPE_LENS || x->item == IT_RAZOR_CLAW);
    st = st > 3 ? 3 : st;
    if (fs2(F2_NG) && (y->ability == AB_BATTLE_ARMOR || y->ability == AB_SHELL_ARMOR))
        o->crit = 0;                /* the no-crit flag: no draw (0x02208A28) */
    else {
        q = fs_q();
        o->crit = q % crit_n[st] == 0;
        if (fs_fond(x, 255) && (q % fond_n[st] == 0) != o->crit)
            return;
    }
    o->roll = fs_roll_ix(g_fsx) + 1;
    if ((dmg = fs_damage(x, y, m)) < 0) {
        o->roll = 0;
        return;
    }
    /* the engine applies a crit before the roll, the simulation has none (its last argument does not add one: fscheck
       saw a crit Razor Wind's 41 simulated at 27 with it set), and x3/2 after the roll lands within 2 HP of the hit:
       a crit is known only as a sure knockout (fscheck: 40 predicted for 41 when every crit was kept) */
    if (o->crit) {
        dmg = dmg * 3 / 2;
        if (dmg < yhp + dmg / 50 + 2)
            return;
    }
    if (dmg >= yhp && endures(y, x)) {
        if (second)                 /* its own recoil may have taken it off full HP */
            return;
        dmg = yhp - 1;
    }
    if (dmg >= yhp && fs_fond(y, 180))
        return;
    o->dmg = dmg < yhp ? dmg : yhp;
    o->own = 1;
    if (fs_self_ok(y, m)) {             /* the user's own stat change: one draw, nothing on the foe */
        fs_q();
        o->after = 1;
        return;
    }
    n = fs_rolls(x, m, &ch, &kd);
    fl = waza(m->id, WP_FLINCH);
    if (n == 1) {
        v = fs_q() % 100 < (u32)ch;
        if (kd == 2)
            o->flinch = v && can_flinch(y, x);
        else
            o->landed = v;
        o->after = 1;
    } else if (n > 1) {
        if (fl > 0 && fl < 100)
            o->own = 0;
        o->flinch = fl >= 100 && can_flinch(y, x);
    } else
        o->after = 1;
}

/* the pair (my move i, the foe's move k) from the word in g_fsx; first as fs_first; o: the two moves' outcomes, the
   first mover's first */
static void fs_pair(const Ctx *c, int i, int k, int first, int between, FsCell *f, FsOut *o)
{
    const Mon *x = first ? &c->opp : &c->me, *y = first ? &c->me : &c->opp;
    const MoveInfo *mx = first ? &c->opp.mv[k] : &c->me.mv[i], *my = first ? &c->me.mv[i] : &c->opp.mv[k];
    const FsOut *me, *foe;
    fs_move(c, x, y, mx, y->hp, 0, 0, &o[0]);
    memset(&o[1], 0, sizeof o[1]);
    if (o[0].after && o[0].own && o[0].dmg >= y->hp)
        o[1].own = o[1].stopped = o[1].pre = 1; /* knocked out before it moves */
    else if (o[0].after && o[0].flinch)
        o[1].own = o[1].fell = 1;
    else if (o[0].after && o[0].slp == 1) {     /* put to sleep: it sleeps through its attempt (Sleep Talk, Snore: not known) */
        if (my->id != MV_SLEEP_TALK && my->id != MV_SNORE)
            o[1].own = o[1].stopped = 1;
    } else if (o[0].after && !o[0].landed) {
        if (between)
            fs_q();                     /* F3_ORD: a tie's draw before the second move */
        fs_move(c, y, x, my, x->hp, 1, (o[0].guard && fs_guard(x, y, mx, my)) | (o[0].par ? 2 : 0) | (o[0].conf ? 4 : 0), &o[1]);
    }
    if (!o[1].own && fs_dozes(y) == 1)          /* asleep through it, whatever came first */
        o[1].own = o[1].stopped = 1;
    me = first ? &o[1] : &o[0];
    foe = first ? &o[0] : &o[1];
    f->mine = me->own;
    f->stopped = me->stopped;
    f->flinched = me->fell;
    f->missed = me->missed;
    f->crit = me->crit;
    f->dmg = me->dmg;
    f->flinch_foe = !first && me->flinch;
    f->foe = foe->own;
    f->f_stopped = foe->stopped || foe->fell;
    f->f_missed = foe->missed;
    f->f_crit = foe->crit;
    f->f_dmg = foe->dmg;
}

/* F3_ORD on the DS: the order draws of the pair from g_fsx (fs_ord_kind's rules); 0 me first, 1 the foe; *between: a
   draw before the second move */
static int fs_ord_walk(const Ctx *c, const MoveInfo *mm, const MoveInfo *fm, int first, int *between)
{
    int me = c->client & 1, h[2], up[2] = { 0, 0 }, j, t = 0, tie = first == 2 && mm->prio == fm->prio;
    h[me] = fs_holder(&c->me);
    h[me ^ 1] = fs_holder(&c->opp);
    *between = 0;
    if (tie)
        t = fs_q() & 1;
    for (j = 0; j < 2; j++)                 /* client 0's holder first */
        if (h[j])
            up[j] = fs_q() % 100 < (u32)h[j];
    if (mm->prio == fm->prio && (up[0] || up[1]))
        return up[me] ? 0 : 1;
    if (!tie)
        return first;
    t ^= (fs_q() ^ fs_q()) & 1;
    *between = 1;
    return (t ? 1 : 0) == me ? 0 : 1;
}

static void fs_predict(Ctx *c)
{
    int i, k, first, kind, between;
    u32 w;
    FsOut o[2];
    fs.on = 0;
    fs.steer = 0;
    fs.magic = FS_MAGIC;
    memset(fs.cell, 0, sizeof fs.cell);
    memset(fs.first, 2, sizeof fs.first);
    fs.trusted = fs_trust(c, &w);
    fs.word = w;
    fs.me_species = c->me.species;
    fs.me_hp = c->me.hp;
    fs.opp_species = c->opp.species;
    fs.opp_hp = c->opp.hp;
    g_nfsd = 0;
    if (!fs.trusted || c->doubles || fs_guard_off(c)) {
        fs.trusted = 0;
        return;
    }
    for (i = 0; i < 4; i++)
        for (k = 0; c->me.legal[i] && k < 4; k++)
        {
            g_fsx = w;
            between = 0;
            kind = fs_ord_kind(c, &c->me.mv[i], &c->opp.mv[k], &first);
            if (kind == ORD_WALK)
                g_fs_ord[i][k] = fs_ord_walk(c, &c->me.mv[i], &c->opp.mv[k], first, &between);
            if (kind != ORD_UNKNOWN && fs_static(c, i, k, &first)) {
                fs_pair(c, i, k, first, between, &fs.cell[i][k], o);
                fs_settle(c, i, k, &fs.cell[i][k]);
            }
        }
    fs.on = 1;
}

/* ---- steer: the DS's half (rc31 unit L, qa/aivsai/rc31_L.md). The gate: hard mode (flag 0x218), the trainer's
   important mark in its BattleSetup header (as aiselect.s ai_serves reads it), singles; the advanced AI serves the
   trainer, as the poll reached adv_poll. The candidates are F's own walk from w_k = step^k(fs.word) with the damage
   by roll index (g_fs_byroll); steer_apply leaves w_k in steer_stash (tools/asm/steer.s), which the turn start writes
   to the battle word only if that word is still fs.word. Nothing here writes the battle word */
#define FLAG_HARD 0x218
#define SETUP_MARK 0x2A             /* BattleSetup: byte 2 of client 0's trainer header (bit 0 the mark), 0x34 per client */
int check_flag(int flag);           /* tools/asm/hardmode.s */
typedef struct { u32 tag, expect, target; u16 k, pad; } SteerStash;
extern SteerStash steer_stash;      /* tools/asm/steer.s, main RAM */
extern SteerLedger steer_ledgers[2];

static int steer_marked(const Ctx *c)
{
#ifdef AI_NO_STEER
    return 0;                       /* the English build (builder/layouts/en.json): no hard mode, no steering */
#else
    u8 *main = AT(bptr, MAIN_PTR);
    void *setup = OK_PTR(main) ? AT(vptr, (u32)main + MAIN_SETUP) : 0;
    return OK_PTR(setup) && (AT(u8, (u32)setup + SETUP_MARK + 0x34 * c->client) & 1) && check_flag(FLAG_HARD);
#endif
}

static int steer_gate(const Ctx *c)
{
    return steer_k && !c->doubles && steer_marked(c);
}

static u32 steer_battle_tag(void)
{
    return battle_tag();
}

_Static_assert(sizeof(SteerCand) == 22 && sizeof(SteerLedger) == 32, "tools/fscheck.py STEER_CAND, steer.s steer_ledgers");

static SteerLedger *steer_ledger(const Ctx *c)
{
    SteerLedger *L = &steer_ledgers[(c->client & 1) ^ 1];
    u32 tag = steer_battle_tag();
    if (L->tag != tag) {
        memset(L, 0, sizeof *L);
        L->tag = tag;
    }
    return L;
}

/* the player's side draws at this candidate outside its own move's rolls, which the walk does not play, so rule (a)
   cannot judge them: its end-of-turn rolls (Shed Skin with a status, Moody, Harvest), on my hit its Focus Band, Cursed
   Body or Gulp Missile, and with my contact move its Static, Flame Body, Poison Point, Effect Spore or Cute Charm; on
   its own hit Toxic Chain, and Poison Touch with a contact move */
static int steer_player_draws(const Ctx *c, const FsCell *f, const MoveInfo *mm, const MoveInfo *fm)
{
    const Mon *p = &c->opp;
    int mine = f->mine && !f->stopped && !f->missed && !f->flinched, foe = f->foe && !f->f_stopped && !f->f_missed;
    if ((p->ability == AB_SHED_SKIN && p->status != S_NONE) || p->ability == AB_MOODY || p->ability == AB_HARVEST)
        return 1;
    if (mine && (p->item == IT_FOCUS_BAND || p->ability == AB_CURSED_BODY || p->ability == AB_GULP_MISSILE))
        return 1;
    if (mine && ((mm->flags >> F_CONTACT) & 1) && (p->ability == AB_STATIC || p->ability == AB_FLAME_BODY ||
                                                   p->ability == AB_POISON_POINT || p->ability == AB_EFFECT_SPORE ||
                                                   p->ability == AB_CUTE_CHARM))
        return 1;
    return foe && (p->ability == AB_TOXIC_CHAIN || (p->ability == AB_POISON_TOUCH && ((fm->flags >> F_CONTACT) & 1)));
}

static int steer_fill(Ctx *c, int i, int kf, SteerCand *t, int n)
{
    u32 w;
    int first, k, counted = fs_counted(c, &c->opp, &c->me, &c->opp.mv[kf]);
    FsOut o[2];
    /* Flip Turn sends its user out after the hit (this hack's data gives it effect 0, not U-turn's 228, so X_PIVOT and
       fs_counted miss it; fscheck: a player's Flip Turn moved first and my steered Megahorn hit its switch-in) */
    if (c->me.mv[i].id == MV_FLIP_TURN || c->opp.mv[kf].id == MV_FLIP_TURN ||
        !fs_trust(c, &w) || w != fs.word || !fs_static(c, i, kf, &first))
        return 0;
    n = n > STEER_KMAX ? STEER_KMAX : n;
    memset(g_fsr, 0, sizeof g_fsr);
    g_fs_byroll = 1;
    for (k = 0; k < n; k++) {
        SteerCand *x = &t[k];
        const FsOut *me = first ? &o[1] : &o[0], *foe = first ? &o[0] : &o[1];
        memset(x, 0, sizeof *x);
        g_fsx = w;
        fs_pair(c, i, kf, first, 0, &x->cell, o);
        fs_settle(c, i, kf, &x->cell);
        x->roll = x->cell.mine && me->roll && !me->stopped && !me->missed && !me->fell ? me->roll - 1 : 255;
        x->f_roll = x->cell.foe && foe->roll && !foe->stopped && !foe->missed && !foe->fell ? foe->roll - 1 : 255;
        x->landed = me->landed || me->flinch;
        x->f_landed = foe->landed || foe->flinch;
        x->f_par = foe->stopped && !foe->pre;
        x->f_pre = foe->pre || foe->fell;
        x->sig = x->cell.foe && (x->f_pre || (foe->after && counted)) &&
                 !steer_player_draws(c, &x->cell, &c->me.mv[i], &c->opp.mv[kf]);
        w = w * 0x41C64E6Du + 0x6073u;
    }
    g_fs_byroll = 0;
    return n;
}

static void steer_apply(Ctx *c, int i, int kf, const SteerCand *t, int k)
{
    u32 w = fs.word;
    int j;
    for (j = 0; j < k; j++)
        w = w * 0x41C64E6Du + 0x6073u;
    steer_stash.tag = steer_battle_tag();
    steer_stash.expect = fs.word;
    steer_stash.target = w;
    steer_stash.k = k;
    fs.word = w;
    fs.cell[i][kf] = t[k].cell;
    fs.steer = k;
}
#endif

/* ---- steer: the host's half (tools/sim/bridge.c fills the candidates and steps the real battle) ---- */
#ifdef HOST_ENGINE_H
int steer_side;                 /* the side that chooses last and steers (SIM_READ_SIDE) */
extern u32 host_steer_tag;
int host_steer_fill(int side, int i, int kf, SteerCand *t, int n);
void host_steer_apply(int side, int i, int kf, const SteerCand *t, int k);
void host_steer_note(int decisive, int nominal, int ko, int visible);
static int steer_gate(const Ctx *c)
{
#ifdef BRIDGE_B
    return 0;
#else
    return steer_k > 0 && !c->doubles && (c->client & 1) == steer_side;
#endif
}
/* each candidate a copy of the battle played from w_k (the bridge), then what the DS predictor could know of it */
static int steer_fill(Ctx *c, int i, int kf, SteerCand *t, int n)
{
    int k, counted = fs_counted(c, &c->opp, &c->me, &c->opp.mv[kf]);
    n = host_steer_fill(c->client & 1, i, kf, t, n);
    for (k = 0; k < n; k++) {
        fs_settle(c, i, kf, &t[k].cell);
        t[k].sig = t[k].sig && t[k].cell.foe && (t[k].f_pre || counted);
    }
    return n;
}
static void steer_apply(Ctx *c, int i, int kf, const SteerCand *t, int k)
{
    fs.cell[i][kf] = t[k].cell;     /* the bridge's check scores the steered prediction */
    host_steer_apply(c->client & 1, i, kf, t, k);
}
static u32 steer_battle_tag(void) { return host_steer_tag; }
static SteerLedger *steer_ledger(const Ctx *c)
{
    static SteerLedger led[2];
    SteerLedger *L = &led[c->client & 1];
    if (L->tag != steer_battle_tag()) {
        memset(L, 0, sizeof *L);
        L->tag = steer_battle_tag();
    }
    return L;
}
#endif


/* the steer phase (rc31 unit L): after decide, a move of mine against the foe's committed move, both parts of the
   unsteered cell known, under the gate; the next poll fills the candidates, picks one and writes the action */
#define PH_STEER 0xFE
static SteerCand g_st[STEER_KMAX];  /* the candidate table (slot bss: used within one poll) */
/* rc31 F2's walk rolls that neither rule (a) nor the class guard judges: a confusion roll and a self-hit's damage roll
   (F2_CONF) and a Protect's streak roll (F2_PROT), on either side; rc33 F3's status accuracy roll and the paralysis
   roll it may add (F3_ACC), the length, accuracy and confusion rolls of F3_LEN, the order draws of F3_ORD; such a turn
   is not steered */
static int steer_unjudged(const Ctx *c, int i, int kf)
{
    int f;
    return cond_on(&c->me, C_CONFUSION) || cond_on(&c->opp, C_CONFUSION) || c->me.mv[i].efx == X_PROTECT ||
           c->opp.mv[kf].efx == X_PROTECT || fs_acc_kind(c, &c->me, &c->opp, &c->me.mv[i]) ||
           fs_acc_kind(c, &c->opp, &c->me, &c->opp.mv[kf]) || fs_len_kind(c, &c->me, &c->opp, &c->me.mv[i]) ||
           fs_len_kind(c, &c->opp, &c->me, &c->opp.mv[kf]) || fs_ord_kind(c, &c->me.mv[i], &c->opp.mv[kf], &f) == ORD_WALK;
}
static int steer_wanted(const Ctx *c, const Option *o)
{
    int kf;
    return o->kind == K_MOVE && o->idx < 4 && fs.trusted && known_foe_action(c, 0, &kf) == FK_MOVE && kf < 4 &&
           fs.cell[o->idx][kf].mine && fs.cell[o->idx][kf].foe && !steer_unjudged(c, o->idx, kf) && steer_gate(c);
}

static void steer_turn(Ctx *c, const Option *o)
{
    int kf, n, k;
    known_foe_action(c, 0, &kf);
    n = steer_fill(c, o->idx, kf, g_st, steer_k < STEER_KMAX ? steer_k : STEER_KMAX);
    k = n ? steer_pick(c, o->idx, kf, g_st, n, steer_ledger(c)) : 0;
    if (k > 0)
        steer_apply(c, o->idx, kf, g_st, k);
#ifdef HOST_ENGINE_H
    if (steer_last.booked)
        host_steer_note(steer_last.decisive, steer_last.nominal, steer_last.ko, steer_last.visible);
#endif
}

/* A2: my voluntary switches (opt[n0..n)) against staying (the moves before n0). A switch is a guess that the newcomer
   does better against this foe; a loop of such guesses (both sides switching every turn, or every one of mine losing
   to the same foe in turn) takes hits and turns and makes no progress. A2_LOOP: after `streak` switches with no HP
   taken from the foe's team since the first, a switch must beat the best stay by (streak - 1) x LOOP_STEP, which no
   loop that returns to the same matchups can keep paying.
   A2_SAC: a newcomer the read move knocks out as it comes in (half the time or more) buys my Pokemon on the field a turn
   it needs only when it would fall this turn by staying (each stay move falls half the time or more), or when it
   comes back faster than the foe; otherwise the sacrifice is never preferred to the best stay: my Pokemon comes back
   to the same foe, which hits it first then, so the newcomer bought nothing */
/* the HP left in the foe's team (A2_LOOP's progress) */
static u32 foe_team_hp(const Ctx *c)
{
    void *op = E_PARTY(E_POKECON(1), (c->client & 1) ^ 1);
    u32 s = 0;
    int i, n = OK_PTR(op) ? E_PARTY_COUNT(op) : 0;
    for (i = 0; i < n && i < 6; i++) {
        void *b = E_PARTY_MEMBER(op, i);
        s += OK_PTR(b) ? B_HP(b) : 0;
    }
    return s;
}

static void progress(Ctx *c, Option *opt, int n0, int n, int streak)
{
    s32 stay = -0x7FFFFFFF, hit;
    int i, safe = 0, k = c->kn[0].idx, again = c->kn[0].kind == FK_MOVE && k < 4 &&
        (c->opp.mv[k].prio > 0 || faster(eff_speed(&c->opp, c->weather), eff_speed(&c->me, c->weather)));
    for (i = 0; i < n0; i++) {
        if (opt[i].kind != K_MOVE)
            continue;
        if (opt[i].value > stay)
            stay = opt[i].value;
        if (opt[i].fell < 125)
            safe = 1;
    }
    if (stay == -0x7FFFFFFF)
        return;
    for (i = n0; i < n; i++) {
        if ((AI_A2 & A2_LOOP) && streak > 1)
            opt[i].value -= (streak - 1) * LOOP_STEP;
        if ((AI_A2 & A2_SAC) && safe && again && entry_hit(c, opt[i].idx, k, &hit) >= 50 && opt[i].value >= stay)
            opt[i].value = stay - 1;
    }
}

__attribute__((noinline)) static int decide(Ctx *c, Option *best)
{
    Option opt[MAX_OPT];
    Pair p, alt;
    Read *r = reads(c);
    int n = 0, i, k, fo = -1, vm = 0, stay = -1, streak = 0;
    s32 sure = -0x7FFFFFFF, sw = -0x7FFFFFFF, fo_dealt = 0, shift = 0;
    void *setup;
    memset(opt, 0, sizeof opt);
    c->xw = 0;
    roles(c);
    {
        Fighter t;
        memset(&t, 0, sizeof t);
        t.who = WHO_ACTIVE;
        t.hp0 = c->me.hp;
        t.maxhp = c->me.maxhp;
        c->dbg->role = role_loss(c, &t);
    }
    pair_data(c, &p);
    reply_odds(c, &p);
    known_reply(c, &p);
    fs_predict(c);
    entries(c, &p);
    g_nalt = 0;
    if ((c->opp.slept && c->opp.slept < 3) || c->opp.status == S_FRZ) {    /* the reply when the foe dozes otherwise than in p */
        k = c->opp.sleep;
        c->opp.sleep = !k;
        pair_data(c, &alt);
        reply_odds(c, &alt);
        known_reply(c, &alt);
        c->opp.sleep = k;
    }
    sleep_cases(&c->opp, 0, &alt);
    sleep_cases(&c->me, 1, &alt);
    for (i = 0; i < 4; i++) {
        const MoveInfo *m = &c->me.mv[i];
        int f = m->cls || m->id == MV_SLEEP_TALK ? K_MOVE : K_MOVE + 3;
        if (!m->id)
            continue;
        if (vetoed(c, i)) {      /* a status move that fails on the foe in front is no read of its switch */
            vm |= (c->me.legal[i] && m->cls) << i;
            continue;
        }
        opt[n].kind = K_MOVE;
        opt[n].idx = i;
        g_ko1 = g_ko3 = 0;
        opt[n].value = mixed(c, &p, f, i);
        opt[n].ko1 = g_ko1;
        opt[n].ko3 = g_ko3;
        opt[n].fell = clamp(g_fell / 4, 0, 250);
        opt[n].dealt = clamp(g_dealt / 125, 0, 8);
        opt[n].sure = m->cls && g_sure;
        if (opt[n].sure && opt[n].value > sure)
            sure = opt[n].value;
        if (m->id == MV_FAKE_OUT && g_fo >= 0) {
            fo = n;
            fo_dealt = g_fo;
        }
        /* sleep or paralysis on the foe's last Pokemon, or on one my attacks barely scratch, keeps a lost position alive */
        if (!m->cls && m->quality == Q_SICK && (m->sick == S_SLP || m->sick == S_PAR) && (!c->opp_others || 3 * p.my_rate < c->opp.hp))
            opt[n].ko1 = acc_now(&c->me, &c->opp, m, c->weather) * (m->sick == S_SLP ? 10 : 5);
        opt[n].st = !m->cls;
        opt[n].selfko = self_ko_move(m->id);
        /* a move the foe's bench is immune to (its free switch-in, or a Choice lock into nothing), a lock, a recoil */
        opt[n].cost = 32 * c->absorb[i] + 8 * (waza(m->id, WP_EFFECT) == EFFECT_LOCK || ((m->flags >> F_RECHARGE) & 1)) +
                      4 * ((m->drain < 0 && c->me.ability != AB_ROCK_HEAD && c->me.ability != AB_MAGIC_GUARD) || m->efx == X_GLAIVE) +
                      /* a pivot that knocks the foe out picks my newcomer before its replacement is known */
                      16 * (m->efx == X_PIVOT && c->opp_others && g_ko1 >= 500);
        if (opt[n].fell >= 250) {
            Pair q = p;
            q.rep = -1;
            q.opp_hit = 0;
            opt[n].spared = clamp(value_of(c, &q, f, i), -0x7FFF, 0x7FFF);
        }
        n++;
    }
    k = exchange(c, &p);
    r->miss = (r->miss & 7) | (k == 2 ? READ_WINS : 0);
    if (c->xin && n && k != 2 && !c->kn[0].kind)
        shift = foe_switch(c, &p, opt, &n, vm);
    /* every move vetoed: staying in stays an option, never a forced switch; with a status move, only when no switch is
       left (it fails on the foe, and a sleeping Pokemon may wake and use it) */
    if (!n && (k = stay_slot(c)) >= 0) {
        stay = k;
        if (c->me.mv[k].cls || c->trapped)
            n = add_stay(c, &p, opt, n, k);
    }
    if (cond_on(&c->me, C_CONFUSION) && c->me.status != S_SLP) {
        /* confused: my move becomes a hit on myself (40 power, typeless) a quarter of the time (a third of the confused
           turns, and it may end first: measured), a turn that does nothing else */
        const Mon *a = &c->me;
        s32 df = stage_mult(a->stat[1], a->stage[1]), h, idle;
        h = ((2 * a->level / 5 + 2) * 40 * stage_mult(a->stat[0], a->stage[0]) / (df > 0 ? df : 1) / 50 + 2) * 925 / 1000;
        idle = mixed(c, &p, K_MOVE + 4, 4) - worth(a->hp, a->maxhp) + worth(a->hp - h, a->maxhp);
        for (i = 0; i < n; i++)
            opt[i].value = (3 * opt[i].value + idle) / 4;
    }
    {   /* the streak: the switch I made last turn brought my Pokemon on the field, or (A2_LOOP) my move then took no
           HP from the foe's team */
        const Memo *mm = &memo[c->client & 3];
        if (mm->magic == MEMO_MAGIC && c->me.turns == 1)
            streak = mm->streak;
        else if ((AI_A2 & A2_LOOP) && mm->magic == MEMO_MOVE && (u32)(unsigned long)mm->foe <= foe_team_hp(c))
            streak = mm->streak;
    }
    if (!c->trapped) {
        int n0 = n, j;
        const Memo *mm = &memo[c->client & 3];
        n = switches(c, &p, opt, n);
        if (!n0 && stay < 0) {
            for (i = j = n0; i < n; i++)
                if (has_move(&c->bench[opt[i].idx]))
                    opt[j++] = opt[i];
            n = j;
        }
        /* the Pokemon my switch took out last turn, against the same foe, still on the field */
        if (mm->magic == MEMO_MAGIC && mm->foe == c->opp.bpp && c->opp.turns == mm->foe_turns + 1 && c->me.turns == 1)
            for (i = n0; i < n; i++)
                if (c->bench[opt[i].idx].id == mm->left)
                    opt[i].value -= BACK_COST;
        if (AI_A2 & (A2_LOOP | A2_SAC))
            progress(c, opt, n0, n, streak);
        for (i = n0; i < n; i++) {
            opt[i].value += shift;
            if (opt[i].value > sw)
                sw = opt[i].value;
        }
    }
    if (!n && stay >= 0)
        n = add_stay(c, &p, opt, n, stay);
    for (i = 0; i < n; i++) {
        const MoveInfo *m = &c->me.mv[opt[i].idx];
        /* never heal while a move knocks the foe out whenever I get to use it (the foe's sleep move stops both) */
        if (opt[i].kind == K_MOVE && self_heal(m) && sure > -0x7FFFFFFF &&
            opt[i].value >= sure)
            opt[i].value = sure - 1;
    }
    /* a sure Fake Out first, then the switch: the free hit costs nothing */
    if (fo >= 0 && sw > -0x7FFFFFFF) {
        s32 v = sw + worth(c->opp.hp, c->opp.maxhp) - worth(c->opp.hp - fo_dealt, c->opp.maxhp);
        if (v > opt[fo].value)
            opt[fo].value = v;
    }
    setup = AT(vptr, (u32)AT(bptr, MAIN_PTR) + MAIN_SETUP);
    if (OK_PTR(setup))
        for (k = 0; k < 4 && n < MAX_OPT; k++) {
            int item = AT(u16, (u32)setup + 0x2C + 0x34 * c->trainer + 2 * k), j;
            s32 v;
            if (!item)
                continue;
            for (j = 0; j < k; j++)
                if (AT(u16, (u32)setup + 0x2C + 0x34 * c->trainer + 2 * j) == item)
                    break;
            if (j < k)
                continue;
            v = mixed(c, &p, K_ITEM, item);
            if (v <= -100000)
                continue;
            opt[n].kind = K_ITEM;
            opt[n].idx = k;
            opt[n].extra = item;
            opt[n].value = v + shift;
            opt[n].fell = clamp(g_fell / 4, 0, 250);
            n++;
        }
    g_nalt = 0;
    if (!pick(c, opt, n, best))
        return 0;
    memo[c->client & 3].magic = 0;
    if ((AI_A2 & A2_LOOP) && best->kind == K_MOVE && streak) {
        Memo *mm = &memo[c->client & 3];
        mm->foe = (void *)(unsigned long)foe_team_hp(c);
        mm->streak = streak;
        mm->magic = MEMO_MOVE;
    }
    if (best->kind == K_SWITCH) {
        Memo *mm = &memo[c->client & 3];
        mm->foe = c->opp.bpp;
        mm->foe_turns = c->opp.turns;
        mm->left = c->me.id;
        mm->streak = streak < 255 ? streak + 1 : 255;
        mm->magic = MEMO_MAGIC;
    }
    return 1;
}

/* doubles: the action of my Pokemon that decided first this turn, for its partner deciding after it (leader and
   follower), one per side (pokeIDs 1-12 and 13-24 by blocks of six, alternating sides), so the other side's decisions
   (self-play) do not overwrite it; turns and species guard against a record from an earlier turn */
static struct { u8 live, id, kind, slot, tgt, turns; u16 species; } g_leads[2];
#define SIDE_OF(id) ((((id) - 1) / 6) & 1)

/* ---- steer: doubles (rc33 unit DL, qa/aivsai/rc33_DL.md). The first-mover splice: under the same gate as singles
   (hard mode, the important mark of the deciding foe client, the advanced AI serving it) the AI steers only its own
   action. steer_action (tools/asm/steer.s, on the action loop's call of one action at 0x0222025C) writes w_k when that
   action starts and, when the action ends on the word the walk predicted (post_k), puts back the word the unsteered
   action would have left (post_0): every draw outside the action sees the numbers of the unsteered battle. Only a
   single-target damaging move that moves strictly first among the four, with both of the player's moves known; when
   the player's other Pokemon uses a move it must move before my target and before my partner (a knockout of the
   target, or my partner's move retargeted by it, then shifts none of the player's rolls: the plan's default, "allow
   pre-emption" reverses it). Every turn the walk can judge is armed, k = 0 too (a booking, nothing written), and the
   ledger books it once the action ended as walked, not at the decision. The stash's states: */
typedef struct { u32 tag, expect, target, post, resume; u8 id, k, state, side; SteerLedger pending; } SteerDStash;
enum { DS_IDLE, DS_ARMED, DS_LIVE, DS_APPLIED, DS_DONE, DS_TAG, DS_WORD, DS_END, DS_MISSED, DS_ALLY };
#ifndef HOST_ENGINE_H
extern SteerDStash steer_dstash;    /* tools/asm/steer.s, main RAM */
_Static_assert(sizeof(SteerDStash) == 56, "steer.s steer_dstash, tools/dlcheck.py DSTASH");
#ifdef AI_NO_STEER
/* the English build has no steer.s: steer_marked is 0, so nothing arms these and they stay zero (slot bss) */
SteerStash steer_stash;
SteerLedger steer_ledgers[2];
SteerDStash steer_dstash;
#endif
/* the steering Pokemon's order, for its partner deciding after it (dsteer_follow); p_*: the player's other Pokemon */
static struct { u8 live, id, p_live; s8 prio, p_prio; s32 spd, p_spd; } g_dlead;
static u8 g_dfell;                  /* bit (side): a client of that side answered through overlay 11 this turn */
static u32 g_dpost[STEER_KMAX];     /* the word after my action from each w_k */
static int redirected(const Ctx *c, const MoveInfo *m, int f);

/* priority pa at speed sa moves strictly before pb at sb: a higher priority, or the same and faster beyond the
   foresight's 2% margin (fs_first) */
static int dsteer_ahead(int pa, s32 sa, int pb, s32 sb)
{
    if (pa != pb)
        return pa > pb;
    return !(sa * 50 < sb * 51 && sb * 50 < sa * 51) && faster(sa, sb);
}

/* its place in the order is not one eff_speed and the move's priority give, or it draws before the actions */
static int dsteer_unordered(const Mon *m)
{
    return fs_unplayed(m) || m->ability == AB_STALL || m->ability == AB_TRIAGE || m->ability == AB_MYCELIUMMGHT;
}

/* the player's Pokemon rolls at the turn's end (Shed Skin with a status, Moody, Harvest): a pre-emption shifts it */
static int dsteer_end_draws(const Mon *p)
{
    return (p->ability == AB_SHED_SKIN && p->status != S_NONE) || p->ability == AB_MOODY || p->ability == AB_HARVEST;
}

/* the foe (index into foes) my move o aims at, -1 none */
static int dsteer_target(const Ctx *c, const Option *o)
{
    int f;
    for (f = 0; f < c->nfoes && f < 2; f++)
        if (c->foes[f].id == o->extra)
            return f;
    return -1;
}

/* the ledger of my side, the last armed turn booked first once its action ended (as walked, or otherwise: a steer was
   still written); a dropped or missed stash books nothing and is cleared */
static SteerLedger *dsteer_ledger(const Ctx *c)
{
    SteerDStash *s = &steer_dstash;
    if (s->state >= DS_DONE) {
        if ((s->state == DS_DONE || s->state == DS_END) && s->side < 2)
            steer_ledgers[s->side] = s->pending;
        s->state = DS_IDLE;
    }
    return steer_ledger(c);
}

/* the steer phase's conditions (the gate first, so that nothing else runs with it false) */
static int dsteer_wanted(const Ctx *c, const Option *o)
{
    const __typeof__(g_leads[0]) *g = &g_leads[SIDE_OF(c->me.id)];
    const MoveInfo *m = &c->me.mv[o->idx & 3];
    s32 sm = eff_speed(&c->me, c->weather), sp = 0, st;
    int f, k, idx, pp = 0, tp;
    const Mon *t, *p = 0;
    if (!steer_k || !c->doubles || !(c->client & 1) || !steer_marked(c) || o->kind != K_MOVE || o->idx >= 4 ||
        !m->cls || (m->target != 0 && m->target != 3) || (f = dsteer_target(c, o)) < 0 || c->swapped ||
        (steer_dstash.state != DS_IDLE && steer_dstash.state < DS_DONE) || (g_dfell >> ((c->client & 1) ^ 1) & 1))
        return 0;
    for (k = 0; k < c->nfoes && k < 2; k++) {
        const Mon *x = &c->foes[k];
        if (known_foe_action(c, k, &idx) != FK_MOVE || idx >= 4 || dsteer_unordered(x) || dsteer_end_draws(x) ||
            !dsteer_ahead(m->prio, sm, x->mv[idx].prio, eff_speed(x, c->weather)))
            return 0;
        if (k != f)
            p = x, pp = x->mv[idx].prio, sp = eff_speed(x, c->weather);
    }
    t = &c->foes[f];
    tp = t->mv[c->kn[f].idx].prio;
    st = eff_speed(t, c->weather);
    if (dsteer_unordered(&c->me) || cond_on(&c->me, C_CONFUSION) || cond_on(t, C_CONFUSION) || redirected(c, m, f) ||
        !fs_counted(c, &c->me, t, m) || (c->has_ally && (dsteer_unordered(&c->ally) || c->ally.ability == AB_VICTORY_STAR)) ||
        (p && !dsteer_ahead(pp, sp, tp, st)))
        return 0;
    g_dlead.live = 0;
    if (c->has_ally) {
        if (g->live && g->id == c->ally.id && g->species == c->ally.species && g->turns == c->ally.turns) {
            int ap = c->ally.mv[g->slot & 3].prio;
            s32 sa = eff_speed(&c->ally, c->weather);
            if (g->kind != K_MOVE || !dsteer_ahead(m->prio, sm, ap, sa) || (p && !dsteer_ahead(pp, sp, ap, sa)))
                return 0;
        } else {                    /* my partner decides after me: dsteer_follow */
            g_dlead.live = 1, g_dlead.id = c->me.id, g_dlead.prio = m->prio, g_dlead.spd = sm;
            g_dlead.p_live = p != 0, g_dlead.p_prio = pp, g_dlead.p_spd = sp;
        }
    }
    return 1;
}

/* my move i against the target (in opp) from each w_k: the candidate (the target's part only its pre-emption) and the
   word after my action */
static int dsteer_fill(Ctx *c, int i, int f, u32 w, SteerCand *t, int n)
{
    const MoveInfo *m = &c->me.mv[i];
    const Mon *y = &c->opp;
    FsOut o;
    int k, ko;
    n = n > STEER_KMAX ? STEER_KMAX : n;
    memset(g_fsr, 0, sizeof g_fsr);
    g_fs_byroll = 1;
    for (k = 0; k < n; k++) {
        SteerCand *x = &t[k];
        memset(x, 0, sizeof *x);
        g_fsx = w;
        fs_move(c, &c->me, y, m, y->hp, 0, 0, &o);
        g_dpost[k] = g_fsx;
        ko = o.own && !o.stopped && !o.missed && o.dmg >= y->hp;
        x->cell.mine = o.own;
        x->cell.stopped = o.stopped;
        x->cell.missed = o.missed;
        x->cell.crit = o.crit;
        x->cell.dmg = o.dmg;
        x->cell.flinch_foe = o.flinch && !ko;
        x->cell.foe = 1;
        x->roll = o.own && o.roll && !o.stopped && !o.missed ? o.roll - 1 : 255;
        x->f_roll = 255;
        x->landed = o.landed || o.flinch;
        x->f_pre = ko || x->cell.flinch_foe;
        x->sig = o.own && o.after && (ko || !o.landed) && !fs_falls(&c->me, y, m, o.dmg) &&
                 !steer_player_draws(c, &x->cell, m, &y->mv[c->kn[f].idx & 3]);
        w = w * 0x41C64E6Du + 0x6073u;
    }
    g_fs_byroll = 0;
    return n;
}

/* the steer poll: the candidates, the shared rules on a copy of my side's ledger, then the stash armed with the k
   chosen (0: the turn's booking only) */
static void dsteer_turn(Ctx *c, const Option *o)
{
    SteerDStash *s = &steer_dstash;
    int f = dsteer_target(c, o);
    SteerLedger L = *dsteer_ledger(c);
    u32 w = fs_word(), x;
    int n, k, j;
    swap_bytes(&c->opp, &c->foes[f], sizeof c->opp);
    n = dsteer_fill(c, o->idx, f, w, g_st, steer_k < STEER_KMAX ? steer_k : STEER_KMAX);
    k = n ? steer_pick(c, o->idx, 0, g_st, n, &L) : 0;
    swap_bytes(&c->opp, &c->foes[f], sizeof c->opp);
    if (!steer_last.booked)
        return;
    for (x = w, j = 0; j < k; j++)
        x = x * 0x41C64E6Du + 0x6073u;
    s->tag = steer_battle_tag();
    s->expect = w;
    s->target = x;
    s->post = g_dpost[k];
    s->resume = g_dpost[0];
    s->id = c->me.id;
    s->k = k;
    s->side = (c->client & 1) ^ 1;
    s->pending = L;
    s->state = DS_ARMED;
}

/* my partner armed a steer and decided before me: it stands only if my action comes after its own and after the
   player's other Pokemon (its draws then come before anything my partner's knockout could change) */
static void dsteer_follow(const Ctx *c, const Option *o)
{
    SteerDStash *s = &steer_dstash;
    if (s->state != DS_ARMED || s->side != ((c->client & 1) ^ 1) || s->id == c->me.id)
        return;
    if (!g_dlead.live || g_dlead.id != s->id || o->kind != K_MOVE || o->idx >= 4 || dsteer_unordered(&c->me) ||
        !dsteer_ahead(g_dlead.prio, g_dlead.spd, c->me.mv[o->idx].prio, eff_speed(&c->me, c->weather)) ||
        (g_dlead.p_live && !dsteer_ahead(g_dlead.p_prio, g_dlead.p_spd, c->me.mv[o->idx].prio, eff_speed(&c->me, c->weather))))
        s->state = DS_ALLY;
}

/* a client of my side answered through overlay 11 (a fallback): its action is not known, so an armed steer of my
   partner's is dropped, and none is armed after it this turn */
static void dsteer_drop(int client, int id)
{
    SteerDStash *s = &steer_dstash;
    g_dfell |= 1 << ((client & 1) ^ 1);
    if (s->state == DS_ARMED && s->side == ((client & 1) ^ 1) && s->id != id)
        s->state = DS_ALLY;
}
#else
static int dsteer_wanted(const Ctx *c, const Option *o) { return 0; }
static void dsteer_turn(Ctx *c, const Option *o) { }
static void dsteer_follow(const Ctx *c, const Option *o) { }
static void dsteer_drop(int client, int id) { }
#endif
/* ---- steer: end doubles ---- */

static void write_action(Ctx *c, void *param, const Option *o)
{
    if (c->doubles) {
        __typeof__(g_leads[0]) *g = &g_leads[SIDE_OF(c->me.id)];
        g->live = 1;
        g->id = c->me.id;
        g->kind = o->kind;
        g->slot = o->idx;
        g->tgt = o->kind == K_MOVE && c->me.mv[o->idx].target != TARGET_USER ? (o->extra ? o->extra : c->foes[0].id) : 0;
        g->turns = c->me.turns;
        g->species = c->me.species;
        dsteer_follow(c, o);
    }
    E_SET_NONE(param);
    if (o->kind == K_MOVE) {
        const MoveInfo *m = &c->me.mv[o->idx];
        int target = m->target == TARGET_USER ? c->me.id : o->extra ? o->extra : c->kn[0].tgt ? c->kn[0].tgt : c->opp.id;
        Chosen *ch = &mem.chosen[c->me.id];
        int k;
        ch->live = aimed(m) && !c->opp.semi;  /* out of reach when chosen: a failure would say nothing */
        for (k = 0; c->doubles && k < c->nfoes && k < 2; k++)
            if (c->foes[k].id == target && c->foes[k].semi)
                ch->live = 0;
        ch->move = m->id;
        ch->pp = c->me.pp[o->idx];
        ch->target = target;
        ch->turns = c->me.turns;
        ch->species = c->me.species;
        E_SET_FIGHT(param, m->id, E_POS_OF(target), c->me.id);
    } else if (o->kind == K_SWITCH) {
        E_SET_CHANGE(param, E_POS_INDEX(E_POS_OF(c->me.id)), c->bench[o->idx].party);
    } else {
        E_SET_ITEM(param, o->extra, c->me.id);
    }
}

/* ---------------------------------------------------------------- doubles */

#define SPREAD_ALL 4        /* move target: every adjacent Pokemon, my partner too */
#define SPREAD_FOES 5       /* move target: every adjacent foe */

/* a's best expected damage on d from the engine simulation (d_on_field: see pair_damage); *slot its move */
static s32 sim_best(Ctx *c, const Mon *a, const Mon *d, int d_on_field, int *slot)
{
    s32 best = 0, e;
    int k;
    for (k = 0; k < 4; k++) {
        const MoveInfo *m = &a->mv[k];
        if (!a->legal[k])
            continue;
        e = expected(a, d, move_damage(a, d, m, pair_damage(c, a, d, m, d_on_field)), m, c->weather);
        if (e > best) {
            best = e;
            *slot = k;
        }
    }
    return best;
}

/* a move of a's at priority prio lands before foe f attacks (its known move, else its fastest attack): higher
   priority, or as high and a is faster */
static int lands_first(const Ctx *c, const Mon *a, int prio, int f)
{
    const Mon *d = &c->foes[f];
    int k, fp = -8;
    for (k = 0; k < 4; k++)
        if (d->legal[k] && d->mv[k].cls && d->mv[k].prio > fp && (c->kn[f].kind != FK_MOVE || k == c->kn[f].idx))
            fp = d->mv[k].prio;
    return prio > fp || (prio == fp && faster(eff_speed(a, c->weather), eff_speed(d, c->weather)));
}

static int spread_targets(const Ctx *c, const MoveInfo *m, int foe_side);

/* my partner's spread move m on me */
static u16 ally_hit_me(Ctx *c, const MoveInfo *m)
{
    s32 e = expected(&c->ally, &c->me, move_damage(&c->ally, &c->me, m, pair_damage(c, &c->ally, &c->me, m, 1)), m, c->weather);
    return clamp(spread_targets(c, m, 0) > 1 ? e * 3 / 4 : e, 0, 0xFFFF);
}

static void sims_doubles(Ctx *c, int part)
{
    int i, f;
    if (!part)
        c->ally_on_me = 0;
    /* my partner knocks foe f out before it moves: my own KO on f adds little */
    for (f = 0; f < c->nfoes && !part; f++) {
        s32 e = c->has_ally && !c->ally.sleep ? sim_best(c, &c->ally, &c->foes[f], !(c->swapped >> f & 1), &i) : 0;
        c->ally_dmg[f] = clamp(e, 0, 0xFFFF);
        c->ally_sure[f] = e > 0 && spread_targets(c, &c->ally.mv[i], 0) > 0;
        c->removed[f] = e >= c->foes[f].hp;
        c->before[f] = c->covered[f] = c->removed[f] && lands_first(c, &c->ally, c->ally.mv[i].prio, f);
        if (e > 0 && c->ally.mv[i].target == SPREAD_ALL)
            c->ally_on_me = ally_hit_me(c, &c->ally.mv[i]);
    }
    for (i = 0; i < 4; i++) {
        const MoveInfo *m = &c->me.mv[i];
        int dmg = m->id && m->cls;
        if (part == 0) {
            for (f = 0; f < c->nfoes; f++)
                c->d_mf[f][i] = dmg ? pair_damage(c, &c->me, &c->foes[f], m, !(c->swapped >> f & 1)) : 0;
            c->d_ma[i] = dmg && c->has_ally ? pair_damage(c, &c->me, &c->ally, m, 1) : 0;
        } else {
            for (f = 0; f < c->nfoes; f++) {
                const MoveInfo *fm = &c->foes[f].mv[i];
                int fd = fm->id && fm->cls && c->foes[f].pp[i];
                c->d_fm[f][i] = fd ? pair_damage(c, &c->foes[f], &c->me, fm, 1) : 0;
                c->d_fa[f][i] = fd && c->has_ally ? pair_damage(c, &c->foes[f], &c->ally, fm, 1) : 0;
            }
        }
    }
}

/* how many Pokemon spread move m hits (0: not a spread move); foe_side: a foe uses it on my side. The engine takes a
   quarter off each hit when it has more than one target */
static int spread_targets(const Ctx *c, const MoveInfo *m, int foe_side)
{
    int mine = 1 + c->has_ally, theirs = c->nfoes;
    if (m->target != SPREAD_ALL && m->target != SPREAD_FOES)
        return 0;
    if (m->target == SPREAD_FOES)
        return foe_side ? mine : theirs;
    return mine + theirs - 1;
}

/* foe f's best expected damage on me, and on my partner; with its action known (read_choice), what that action does to
   it: its move where it lands, nothing after a switch or an item */
static s32 foe_best_at(const Ctx *c, int f, int on_ally, int *slot)
{
    const Mon *d = &c->foes[f];
    const Mon *v = on_ally ? &c->ally : &c->me;
    const u16 *raw = on_ally ? c->d_fa[f] : c->d_fm[f];
    const Known *kn = &c->kn[f];
    s32 best = 0, e;
    int i, sleeptalk = 0;
    if (kn->kind == FK_SWITCH || kn->kind == FK_ITEM || (kn->kind == FK_MOVE && !(kn->hits & (on_ally ? HIT_ALLY : HIT_ME))))
        return 0;
    for (i = 0; i < 4; i++)
        sleeptalk |= d->legal[i] && (d->mv[i].id == MV_SNORE || d->mv[i].id == MV_SLEEP_TALK);
    if ((d->status == S_SLP && d->sleep && !sleeptalk) || d->status == S_FRZ)   /* asleep or frozen: no attack this turn */
        return 0;
    for (i = 0; i < 4; i++) {
        if (!d->legal[i] || !d->mv[i].cls || (kn->kind == FK_MOVE && i != kn->idx))
            continue;
        e = expected(d, v, move_damage(d, v, &d->mv[i], raw[i]), &d->mv[i], c->weather);
        if (spread_targets(c, &d->mv[i], 1) > 1)
            e = e * 3 / 4;
        if (e > best) {
            best = e;
            *slot = i;
        }
    }
    return kn->hits & HIT_HALF ? best / 2 : best;
}

static s32 foe_best(const Ctx *c, int f, int on_ally)
{
    int slot;
    return foe_best_at(c, f, on_ally, &slot);
}

/* what foe f's attack this turn takes from my side, on the team scale (worth x 7/5; a KO 1400, as one of theirs): from me plus from
   my partner. A foe whose action is not known hits one of them (the larger loss) unless its best hit is a spread move */
static s32 threat_of(const Ctx *c, int f)
{
    s32 t[2] = {0, 0}, h;
    int k, slot = -1, other, one;
    for (k = 0; k < 1 + c->has_ally; k++) {
        const Mon *v = k ? &c->ally : &c->me;
        h = foe_best_at(c, f, k, k ? &other : &slot);
        t[k] = h >= v->hp ? 1400 : (worth(v->hp, v->maxhp) - worth(v->hp - h, v->maxhp)) * 7 / 5;
    }
    one = !c->kn[f].kind && !(slot >= 0 && spread_targets(c, &c->foes[f].mv[slot], 1) > 1);
    return one ? (t[0] > t[1] ? t[0] : t[1]) : t[0] + t[1];
}

/* how much foe f threatens my side, per-mille of a Pokemon's max HP (my partner counts too) */
static s32 foe_threat(const Ctx *c, int f)
{
    s32 t = foe_best(c, f, 0) * 1000 / c->me.maxhp, u;
    if (c->has_ally) {
        u = foe_best(c, f, 1) * 1000 / c->ally.maxhp;
        if (u > t)
            t = u;
    }
    return t > 1000 ? 1000 : t;
}

/* foe f's best hit, times x/2, knocks out me or my partner */
static int kills(const Ctx *c, int f, int x)
{
    return x * foe_best(c, f, 0) / 2 >= c->me.hp || (c->has_ally && x * foe_best(c, f, 1) / 2 >= c->ally.hp);
}

/* a foe that attacks before my move (priority prio) knocks me out with its best hit */
static int doomed(const Ctx *c, int prio)
{
    int f;
    for (f = 0; f < c->nfoes; f++)
        if (foe_best(c, f, 0) >= c->me.hp && !lands_first(c, &c->me, prio, f))
            return 1;
    return 0;
}

static s32 hit_value(const Ctx *c, int slot, int f, int spread)
{
    const MoveInfo *m = &c->me.mv[slot];
    const Mon *d = &c->foes[f];
    s32 raw = move_damage(&c->me, d, m, c->d_mf[f][slot]);
    s32 maxd = raw * hits_x10(m) / 10, avgd, mind, v, kop, t = threat_of(c, f), hp, both, turns;
    int guard = endures(d, &c->me) && !multi(&c->me, m) && !c->lead_dmg[f], k;   /* Sash or Sturdy: no KO from full HP */
    if (!raw)
        return 0;
    if (spread)
        maxd = maxd * 3 / 4;
    avgd = maxd * 925 / 1000;
    mind = maxd * 85 / 100;
    /* my partner's action, chosen before mine, lands this turn too: what it leaves is what I need */
    hp = c->lead_dmg[f] < d->hp ? d->hp - c->lead_dmg[f] : d->hp;
    if (guard && avgd >= hp)
        avgd = hp - 1;
    /* a KO is worth the whole Pokemon whatever HP it had left (finishing a weak threat counts as much as a fresh one) */
    kop = guard ? 0 : mind >= hp ? 1000 : maxd < hp ? 0 : 1000 * (maxd - hp) / (maxd - mind + 1);
    /* first to decide: a KO my partner's best attack and mine make together, sure when that attack lands on f anyway
       (a spread move, or the other foe out of its reach), else even odds that it joins (it decides after me) */
    if (kop < 1000 && !c->lead_dmg[f] && c->has_ally && c->ally_dmg[f] && c->ally_dmg[f] < hp && !guard) {
        s32 h2 = hp - c->ally_dmg[f], k2 = mind >= h2 ? 1000 : maxd < h2 ? 0 : 1000 * (maxd - h2) / (maxd - mind + 1);
        int sure = c->ally_sure[f] || (c->nfoes == 2 && !c->ally_dmg[f ^ 1]);
        k2 = sure ? k2 : k2 / 2;
        if (k2 > kop)
            kop = k2;
    }
    v = (avgd < hp ? avgd : hp) * 1000 / d->maxhp;
    /* without a KO, damage counts by the threat it ends, over the turns my two Pokemon together need for it */
    both = avgd + (c->lead_dmg[f] ? 0 : c->ally_dmg[f]);
    turns = both > 0 ? clamp((hp + both - 1) / both, 1, 4) : 4;
    v = v * (1000 + (t < 2000 ? t : 2000) / (2 * turns)) / 1000;
    /* a KO takes away the foe's next turn (what it would take from my side), and this one too when it lands first */
    v = (v * (1000 - kop) + (1400 + t) * kop) / 1000;
    if (kop && lands_first(c, &c->me, m->prio, f))
        v += kop * t / 1000;
    if (c->kn[f].kind == FK_MOVE && d->mv[c->kn[f].idx].efx == X_PROTECT) {   /* it protects: a third as likely per one in a row */
        int odds = 1000;
        for (k = 0; k < d->protects && k < 4; k++)
            odds /= 3;
        v = v * (1000 - odds) / 1000;
    }
    if (c->covered[f])
        return v / 2;
    /* a super-effective hit that leaves a Weakness Policy holder standing gives it +2 Attack and Sp. Atk: about
       twice its threat */
    if (kop < 1000 && d->item == IT_WEAK__POLICY && eff_move(&c->me, d, m) > 1000)
        v -= (1000 - kop) * (foe_threat(c, f) + (kills(c, f, 4) ? 1400 : 0)) / 1000;
    return v;
}

/* a single-target Electric (Water) move goes to any other Pokemon out with Lightningrod (Storm Drain), which
   absorbs it: my partner or the other foe (Mold Breaker ignores the ability) */
static int redirected(const Ctx *c, const MoveInfo *m, int f)
{
    int ab = m->type == T_ELECTRIC ? AB_LIGHTNINGROD : m->type == T_WATER ? AB_STORM_DRAIN : 0, k;
    if (!ab || breaks_mold(&c->me))
        return 0;
    if (c->has_ally && c->ally.ability == ab)
        return 1;
    for (k = 0; k < c->nfoes; k++)
        if (k != f && c->foes[k].ability == ab)
            return 1;
    return 0;
}

static s32 value_move_doubles(const Ctx *c, int slot, int f)
{
    const MoveInfo *m = &c->me.mv[slot];
    int acc = acc_now(&c->me, &c->foes[f], m, c->weather), k, spread = m->target == SPREAD_ALL || m->target == SPREAD_FOES;
    s32 v = 0;
    if (charges(&c->me, m, c->weather))
        acc /= 2;
    if (spread) {
        for (k = 0; k < c->nfoes; k++)
            v += hit_value(c, slot, k, spread_targets(c, m, 0) > 1);
        if (m->target == SPREAD_ALL && c->has_ally) {
            s32 raw = move_damage(&c->me, &c->ally, m, c->d_ma[slot]) * 3 / 4;
            s32 hurt = (raw * 925 / 1000 < c->ally.hp ? raw * 925 / 1000 : c->ally.hp) * 1000 / c->ally.maxhp;
            v -= hurt * 3 / 2;
            if (raw * 85 / 100 >= c->ally.hp)
                v -= 800;
        }
    } else {
        if (redirected(c, m, f))
            return -100000;
        v = hit_value(c, slot, f, 0);
        if (m->id == MV_FAKE_OUT && c->me.fresh && c->foes[f].ability != AB_INNER_FOCUS && c->foes[f].ability != AB_SHIELD_DUST)
            /* it flinches: the threat it posed this turn is gone, and its next turn too when my partner then knocks it out */
            v += threat_of(c, f) * (c->removed[f] && !c->before[f] ? 2 : 1);
        /* Rocky Helmet, Rough Skin: a KO of my own counts like one of theirs */
        k = contact_recoil(&c->me, &c->foes[f], m);
        v -= k >= c->me.hp ? 1400 : k * 1000 / c->me.maxhp;
    }
    if (self_ko_move(m->id))
        v -= 1000;
    if ((m->flags >> F_RECHARGE) & 1)
        v -= 150;
    return v * acc / 100;
}

/* Protect buys a turn only when something changes by the next one: a foe that hits me is gone or idle next turn (my
   partner knocks it out this turn, its self-KO move or Fake Out is spent, its charged move ends, it faints at
   the turn's end or falls asleep). Then the hits it takes this turn are saved, at its odds (a third per Protect in a
   row, three quarters when paralyzed), plus that foe's share again for the turn it no longer gets. Otherwise it only
   trades my action for theirs and the same position comes back */
static int faked_out(const Ctx *c, int on_ally);
static s32 protect_value(const Ctx *c)
{
    const Mon *a = &c->me;
    s32 H = 0, B = 0, h, saved;
    int f, k, odds = 1000;
    for (k = 0; k < a->protects && k < 4; k++)
        odds /= 3;
    if (a->status == S_PAR)
        odds = odds * 3 / 4;
    for (f = 0; f < c->nfoes; f++) {
        const Mon *d = &c->foes[f];
        const Known *kn = &c->kn[f];
        const MoveInfo *km = kn->kind == FK_MOVE ? &d->mv[kn->idx] : 0;
        if (!(h = foe_best(c, f, 0)) || (c->before[f] && !faked_out(c, 1)))
            continue;           /* my partner knocks it out before it moves: nothing to protect from */
        H += h;
        if ((c->removed[f] && !faked_out(c, 1)) || chip_of(d, c->weather) >= d->hp || d->drowsy ||
            (km && (self_ko_move(km->id) || (km->id == MV_FAKE_OUT && d->fresh) ||
                    (d->charging && d->charging == km->id))))
            B += (worth(a->hp, a->maxhp) - worth(a->hp - h, a->maxhp)) * 7 / 5;
    }
    if (c->ally_on_me && !faked_out(c, 1)) {     /* my partner's spread move: it hits freely while I protect */
        H += c->ally_on_me;
        B += (worth(a->hp, a->maxhp) - worth(a->hp - c->ally_on_me, a->maxhp)) * 7 / 5;
    }
    if (!B)
        return -50;
    saved = (worth(a->hp, a->maxhp) - worth(a->hp - H, a->maxhp)) * 7 / 5;
    return odds * (saved + B) / 1000 - 50;
}

static s32 value_status_doubles(const Ctx *c, int slot, int f)
{
    const Mon *a = &c->me;
    const MoveInfo *m = &a->mv[slot];
    s32 threat = 0, v;
    int k, acc = acc_now(a, &c->foes[f], m, c->weather);
    for (k = 0; k < c->nfoes; k++)
        threat += foe_best(c, k, 0);
    if (m->efx == X_PROTECT)
        return protect_value(c);
    if (self_heal(m)) {
        s32 heal = m->id == MV_REST ? a->maxhp : a->maxhp * heal_pct(m, c->weather) / 100;
        if (a->hp <= threat && a->hp + heal > threat)
            return 500;
        return heal * 300 / a->maxhp - 100;
    }
    if (boost_kind(m)) {
        int useful = 0;
        s32 h = a->hp - (m->id == MV_BELLY_DRUM ? a->maxhp / 2 : 0);
        for (k = 0; k < 3; k++)
            if (m->rank_type[k] && m->rank_type[k] <= 7 && m->rank_val[k] > 0 && a->stage[m->rank_type[k] - 1] < 12)
                useful += m->rank_val[k];
        if (threat >= h)
            return -200;
        return 150 * useful * (h - threat) / a->hp;
    }
    if (m->target != TARGET_USER && m->quality == Q_SICK) {
        const Mon *d = &c->foes[f];
        if (status_blocked(c, a, d, m))
            return -100000;
        switch (m->sick) {
        case S_SLP: v = 450; break;
        case S_FRZ: v = 300; break;
        case S_PAR: v = faster(eff_speed(d, c->weather), eff_speed(a, c->weather)) ? 300 : 150; break;
        case S_BRN: v = 120; break;
        case S_PSN: v = m->id == MV_TOXIC ? 200 : 120; break;
        default: v = 60; break;
        }
        if (d->hp * 10 < d->maxhp * 3)
            v /= 2;
        return v * acc / 100;
    }
    return 20;
}

/* bench Pokemon b against each foe on the field (engine simulation): its best expected damage, per-mille of the
   foe's max HP, in d_bo[b][f]; the foe's best on it in d_ob[b][f] */
static void bench_doubles(Ctx *c, int b)
{
    int f, k;
    for (f = 0; f < c->nfoes; f++) {
        const Mon *d = &c->foes[f];
        c->d_bo[b][f] = clamp(sim_best(c, &c->bench[b], d, !(c->swapped >> f & 1), &k) * 1000 / d->maxhp, 0, 1000);
        c->d_ob[b][f] = clamp(sim_best(c, d, &c->bench[b], 0, &k), 0, 0xFFFF);
    }
}

/* bench Pokemon i comes in: it takes the hazards and both foes' best hits, keeps my doomed Pokemon (counted like
   a KO of theirs) and hits back next turn */
static s32 value_switch_doubles(const Ctx *c, int i)
{
    const Mon *s = &c->bench[i];
    s32 off = 0, chip, hp = s->hp - hazard_hp(c, s, &chip);
    int f;
    for (f = 0; f < c->nfoes; f++) {
        const Known *kn = &c->kn[f];
        if (c->d_bo[i][f] > off)
            off = c->d_bo[i][f];
        if (!kn->kind || (kn->kind == FK_MOVE && (kn->hits & HIT_ME) && kn->idx < 4 && c->foes[f].mv[kn->idx].cls))
            hp -= kn->hits & HIT_HALF ? c->d_ob[i][f] / 2 : c->d_ob[i][f];  /* a known attack: its best one, a bound */
    }
    return (doomed(c, 0) ? worth(c->me.hp, c->me.maxhp) * 7 / 5 : 0) - (worth(s->hp, s->maxhp) - worth(hp, s->maxhp)) * 7 / 5 +
           (hp > 0 ? off / 2 : 0) - 200;
}

/* Sleep Talk calls one of my other attacks at a random foe: the average of their values */
static s32 sleep_talk_doubles(const Ctx *c, int slot)
{
    s32 sum = 0;
    int k, f, n = 0;
    for (k = 0; k < 4; k++)
        if (k != slot && c->me.mv[k].id && c->me.mv[k].cls)
            for (f = 0; f < c->nfoes; f++) {
                sum += value_move_doubles(c, k, f);
                n++;
            }
    return n ? sum / n : 0;
}

/* the foe whose known Follow Me (or Rage Powder, which Grass types, Overcoat and Safety Goggles ignore) draws my
   single-target moves this turn, -1 none */
static int lure(const Ctx *c)
{
    int f;
    for (f = 0; f < c->nfoes && c->nfoes == 2; f++) {
        const Known *k = &c->kn[f];
        int id = k->kind == FK_MOVE ? c->foes[f].mv[k->idx].id : 0;
        if (id == MV_FOLLOW_ME || (id == MV_RAGE_POWDER && !has_type(&c->me, T_GRASS) && c->me.ability != AB_OVERCOAT &&
                                   c->me.item != IT_SAFETYGOGGLS))
            return f;
    }
    return -1;
}

/* a known Fake Out from a foe on its first turn out lands on my Pokemon (on_ally: my partner) before it moves */
static int faked_out(const Ctx *c, int on_ally)
{
    const Mon *v = on_ally ? &c->ally : &c->me;
    int f;
    for (f = 0; f < c->nfoes && (!on_ally || c->has_ally); f++) {
        const Known *k = &c->kn[f];
        if (k->kind == FK_MOVE && c->foes[f].mv[k->idx].id == MV_FAKE_OUT && c->foes[f].fresh &&
            v->ability != AB_INNER_FOCUS && foe_best(c, f, on_ally) > 0)
            return 1;
    }
    return 0;
}

/* leader and follower. When my partner decided before me this turn, its action's expected damage on each foe
   (lead_dmg), and the foes it knocks out (covered, removed, before). Otherwise (I lead, or another client decides it) the
   guess from its best hit stays, and the follower reads my real action */
static void partner_plan(Ctx *c)
{
    __typeof__(g_leads[0]) *g = &g_leads[SIDE_OF(c->me.id)];
    int f;
    c->lead_dmg[0] = c->lead_dmg[1] = 0;
    if (!c->has_ally)
        return;
    if (g->live && g->id == c->ally.id && g->species == c->ally.species && g->turns == c->ally.turns) {
        const MoveInfo *lm = &c->ally.mv[g->slot & 3];
        c->ally_on_me = g->kind == K_MOVE && lm->cls && lm->target == SPREAD_ALL ? ally_hit_me(c, lm) : 0;
        for (f = 0; f < c->nfoes; f++) {
            Mon *d = &c->foes[f];
            s32 e = 0;
            if (g->kind == K_MOVE && lm->cls &&
                (spread_targets(c, lm, 0) || g->tgt == d->id || (c->kn[f].tgt && g->tgt == c->kn[f].tgt))) {
                e = expected(&c->ally, d, move_damage(&c->ally, d, lm, pair_damage(c, &c->ally, d, lm, !(c->swapped >> f & 1))),
                             lm, c->weather);
                if (spread_targets(c, lm, 0) > 1)
                    e = e * 3 / 4;
            }
            c->lead_dmg[f] = clamp(e, 0, 0xFFFF);
            c->removed[f] = c->covered[f] = e >= d->hp;
            c->before[f] = c->removed[f] && lands_first(c, &c->ally, lm->prio, f);
        }
    }
}

static int decide_doubles(Ctx *c, Option *best)
{
    Option opt[MAX_OPT];
    int n = 0, i, f, k;
    s32 best_move = -0x7FFFFFFF;
    void *setup;
    int lu, fake;
    partner_plan(c);
    lu = lure(c);
    fake = faked_out(c, 0);
    memset(opt, 0, sizeof opt);
    if (faked_out(c, 1))
        c->covered[0] = c->covered[1] = 0;      /* my partner flinches: it knocks nothing out */
    for (i = 0; i < 4 && n < MAX_OPT; i++) {
        const MoveInfo *m = &c->me.mv[i];
        int spread = m->target == SPREAD_ALL || m->target == SPREAD_FOES || m->target == TARGET_USER;
        if (!m->id || !c->me.legal[i])
            continue;
        for (f = 0; f < (spread || (m->cls == 0 && m->quality != Q_SICK) ? 1 : c->nfoes) && n < MAX_OPT; f++) {
            s32 v;
            if (lu >= 0 && f != lu && !spread && (m->cls || m->quality == Q_SICK))
                continue;           /* drawn to the foe using Follow Me: aiming at it is the same move */
            if (m->cls && !spread && vetoed_vs(c, i, &c->foes[f], c->d_mf[f][i]))
                continue;
            if (m->cls && spread) {
                int useful = 0;
                for (k = 0; k < c->nfoes; k++)
                    useful |= !vetoed_vs(c, i, &c->foes[k], c->d_mf[k][i]);
                if (!useful)
                    continue;
            }
            if (!m->cls && vetoed_vs(c, i, &c->foes[f], 0))
                continue;
            v = m->id == MV_SLEEP_TALK ? sleep_talk_doubles(c, i) : m->cls ? value_move_doubles(c, i, f) : value_status_doubles(c, i, f);
            if (m->cls && c->me.status == S_SLP && c->me.sleep && m->id != MV_SNORE)
                v /= 4;             /* asleep through this turn: the move waits for its waking */
            if (v <= -100000)
                continue;
            if (v > 0 && doomed(c, m->prio))
                v /= 3;             /* a faster foe knocks me out first: the move likely never happens */
            if (v > 0 && fake && m->prio <= 3)
                v /= 8;             /* a known Fake Out makes me flinch first */
            opt[n].kind = K_MOVE;
            opt[n].idx = i;
            opt[n].extra = spread ? 0 : c->kn[f].tgt ? c->kn[f].tgt : c->foes[f].id;
            opt[n].value = v;
            if (v > best_move)
                best_move = v;
            n++;
        }
    }
    if (!n && (k = stay_slot(c)) >= 0 && (c->me.mv[k].cls || c->trapped || !c->nbench)) {
        s32 threat = 0;     /* every move vetoed: stay, losing what the foes' hits take (a status move: no switch left) */
        for (f = 0; f < c->nfoes; f++)
            threat += foe_best(c, f, 0);
        opt[n].kind = K_MOVE;
        opt[n].idx = k;
        opt[n].extra = c->me.mv[k].target == TARGET_USER ? 0 : c->kn[0].tgt ? c->kn[0].tgt : c->foes[0].id;
        opt[n].value = -(worth(c->me.hp, c->me.maxhp) - worth(c->me.hp - threat, c->me.maxhp)) * 7 / 5;
        n++;
    }
    k = n || has_move(&c->me);
    if (!c->trapped && (best_move <= 0 || doomed(c, 0)))
        for (i = 0; i < c->nbench && n < MAX_OPT; i++) {
            if (!k && !has_move(&c->bench[i]))
                continue;
            opt[n].kind = K_SWITCH;
            opt[n].idx = i;
            opt[n].extra = c->bench[i].party;
            opt[n].value = value_switch_doubles(c, i);
            n++;
        }
    setup = AT(vptr, (u32)AT(bptr, MAIN_PTR) + MAIN_SETUP);
    if (OK_PTR(setup))
        for (k = 0; k < 4 && n < MAX_OPT; k++) {
            int item = AT(u16, (u32)setup + 0x2C + 0x34 * c->trainer + 2 * k), heal, cure;
            s32 threat = 0, v;
            if (!item)
                continue;
            for (f = 0; f < c->nfoes; f++)
                threat += foe_best(c, f, 0);
            heal = heal_amount(item, &c->me);
            cure = cures(item, c->me.status);
            if (heal && c->me.hp * 4 >= c->me.maxhp * 3)
                heal = 0;
            if (!heal && !cure)
                continue;
            v = heal && c->me.hp <= threat && c->me.hp + heal > threat ? 500 : heal && c->me.hp * 3 < c->me.maxhp ? 200 : 0;
            if (cure)
                v += c->me.status == S_SLP || c->me.status == S_FRZ ? 350 : 150;
            opt[n].kind = K_ITEM;
            opt[n].idx = k;
            opt[n].extra = item;
            opt[n].value = v;
            n++;
        }
    return pick(c, opt, n, best);
}

static int context(void *st)
{
    u32 tag = battle_tag();
    int i;
    for (i = 0; i < MAX_CTX; i++)
        if (live[i].st == st && live[i].tag == tag)
            return i;
    for (i = 0; i < MAX_CTX; i++)
        if (!live[i].st || live[i].tag != tag) {
            Ctx *c = E_ALLOC(HEAP_BATTLE, sizeof *c + sizeof(MoveCache));     /* its move records right after it */
            if (c) {
                memset(c, 0, sizeof *c + sizeof(MoveCache));
                c->st = st;
            }
            live[i].st = st;
            live[i].c = c;
            live[i].tag = tag;
            return i;
        }
    return -1;
}

static int done(int i)
{
    if (live[i].c)
        E_FREE(live[i].c);
    live[i].st = live[i].c = 0;
    g_wz = 0;
    return 1;
}

/* read_choice: fill c->kn with each foe's action this turn, committed before my decision; -1 while a foe has not chosen
   yet. Only the trainer's side reads, so two advanced AIs (aivsai --self, a tag partner) never wait for each other */
#ifdef HOST_ENGINE_H
extern unsigned char sim_foe_act[2];   /* tools/sim/battle.c: the other side's action (Action kind, idx), chosen first */
extern int sim_foe_valid;
static int foe_choice(Ctx *c)
{
    Known *k = &c->kn[0];
    memset(c->kn, 0, sizeof c->kn);
    if (!sim_foe_valid || c->doubles)
        return 0;
    k->idx = sim_foe_act[1];
    k->kind = sim_foe_act[0] == 1 ? FK_MOVE : sim_foe_act[0] == 2 ? FK_SWITCH : FK_NONE;
    return 0;
}
#else
/* Each client's adapter (pointers at ADAPTERS by client): +0xB the server's command (2: choose an action), +0xA set
   once the client has answered it, +0 then the answer, the client's action records (client+0x534, 12 bytes for each
   of its Pokemon on the field, in party order, +4 their size). The server starts the turn only when every adapter has
   answered, so waiting here holds the turn as long as the foe's menu does and no longer */
#define ADAPTERS 0x02252D20u
#define AD_ANSWERED 0xA
#define AD_CMD 0xB
#define CMD_SELECT 2
#define RANDOM_FOE 9           /* move target: one foe at random (Outrage) */
#define POS_UNSET 5            /* a record's target before the target screen sets one (singles never has one) */
#define AI_OVERLAY 10          /* overlay 11's image and this AI (tools/asm/aiselect.s) */

/* foe d's action record rec (the setters' format: word 0 bits 0-3 the kind; 1 a move, the target position in bits
   4-7 (POS_UNSET when the player's menu had no target screen: the server then picks), the move in bits 8-23, the
   user's pokeID in word 2; 2 an item in bits 4-19, its target's pokeID in word 1; 3 a
   switch, the position index in bits 4-6, the party index in bits 7-9, bit 10 clear) as a Known */
static void read_record(const Ctx *c, const Mon *d, const u32 *rec, Known *k)
{
    u32 w = rec[0];
    int i, t, pos;
    switch (w & 15) {
    case 1:
        for (i = 0; i < 4 && rec[2] == d->id; i++)
            if (d->mv[i].id == ((w >> 8) & 0xFFFF)) {
                k->kind = FK_MOVE;
                k->idx = i;
                t = d->mv[i].target;
                pos = (w >> 4) & 15;
                k->hits = t == SPREAD_ALL || t == SPREAD_FOES ? HIT_ME | HIT_ALLY :
                          t == RANDOM_FOE ? HIT_ME | HIT_ALLY | HIT_HALF :
                          t != 0 && t != 3 ? 0 :
                          pos == POS_UNSET ? (c->has_ally ? HIT_ME | HIT_ALLY | HIT_HALF : HIT_ME) :
                          (pos == E_POS_OF(c->me.id) ? HIT_ME : 0) | (c->has_ally && pos == E_POS_OF(c->ally.id) ? HIT_ALLY : 0);
            }
        break;
    case 2:
        k->kind = FK_ITEM;
        k->item = (w >> 4) & 0xFFFF;
        k->idx = rec[1];
        break;
    case 3:
        if (!(w & 0x400) && ((w >> 4) & 7) == E_POS_INDEX(E_POS_OF(d->id))) {
            k->kind = FK_SWITCH;
            k->idx = (w >> 7) & 7;
        }
        break;
    }
}

static int foe_choice(Ctx *c)
{
    int f, n = c->doubles ? c->nfoes : 1;
    memset(c->kn, 0, sizeof c->kn);
    if (!(c->client & 1) || NOREAD())
        return 0;
    for (f = 0; f < n; f++) {
        const Mon *d = c->doubles ? &c->foes[f] : &c->opp;
        u8 *ad = AT(bptr, ADAPTERS + 4 * (c->doubles ? c->fcl[f] : c->opp_client));
        const u32 *rec;
        if (!OK_PTR(ad) || AT(u8, ad + AD_CMD) != CMD_SELECT)
            continue;
        if (!AT(u8, ad + AD_ANSWERED))
            return -1;
        rec = AT(vptr, ad);
        if (OK_PTR(rec) && 12u * (d->party + 1) <= AT(u32, ad + 4))
            read_record(c, d, rec + 3 * d->party, &c->kn[f]);
    }
    return 0;
}

/* tools/asm/aiselect.s ai_entry, when the slot holds neither AI overlay: the player's Bag or party screen took it while
   my decision was in progress (its context in live[]). 0: no decision of mine in progress here (ai_entry goes on as
   before); 1: the player is still choosing, wait (my code is not in the slot); 2: the player has chosen, its UI is
   closed: overlay 10 is back in the slot and the decision goes on */
__attribute__((section(".itcm.text.ai_resume"))) int ai_resume(void *st)
{
    u32 tag = battle_tag();
    int i, f;
    for (i = 0; i < MAX_CTX; i++) {
        const Ctx *c = live[i].c;
        if (live[i].st != st || live[i].tag != tag || !c)
            continue;
        for (f = 0; f < (c->doubles ? c->nfoes : 1); f++) {
            u8 *ad = AT(bptr, ADAPTERS + 4 * (c->doubles ? c->fcl[f] : c->opp_client));
            if (OK_PTR(ad) && AT(u8, ad + AD_CMD) == CMD_SELECT && !AT(u8, ad + AD_ANSWERED))
                return 1;
        }
        E_SWITCH_SLOT(AI_OVERLAY);
        return 2;
    }
    return 0;
}

/* tools/asm/aiselect.s ai_bag_check, on overlay 14's Bag (0x022029CC), which loads overlay 9 into the battle slot only
   once every AI client is done (0x02215944: main+0x270 + client, set when that client's select routine ends). A trainer
   side waiting for the player's committed action is not done before the commit, so the Bag waited forever (found by
   hardmode_items_check at the rc29 merge: the Bag never opened with the advanced AI on). A client of mine that has
   decided everything but the reply counts as done here; while the Bag holds the slot, its polls go to ai_resume, as
   with the party screen. Any other client must be done, as before */
#define CLIENT_EXISTS(cl) CALL(0x022284A0, int, int)(cl)
#define MAIN_DONE 0x270
__attribute__((section(".itcm.text.ai_slot_free"))) int ai_slot_free(void)
{
    u8 *main = AT(bptr, MAIN_PTR);
    u32 tag = battle_tag();
    int cl, i;
    for (cl = 1; cl < 4; cl++) {
        if (!CLIENT_EXISTS(cl) || AT(u8, main + MAIN_DONE + cl))
            continue;
        for (i = 0; i < MAX_CTX; i++) {
            const Ctx *c = live[i].c;
            if (c && live[i].tag == tag && c->client == cl && c->waiting)
                break;
        }
        if (i == MAX_CTX)
            return 0;
    }
    return 1;
}
#endif

/* RD, reading discipline (rc33): a committed action read by foe_choice is used only when the blind foe model gave it
   odds of at least rd_t per mille, or else on a draw of rd_pct per mille from the AI's own keyed LCG (rd_draw), never
   the battle RNG. An unused read is forgotten: the decision is the blind one, and foresight keeps every pair's cells
   (c->fs_move) but not the foe's move (known_reply, steering). The odds: a move's blind reply weight (reply_odds,
   normalized); a switch, foe_switch's w when the newcomer is the modelled switch-in, else 0; an item 0. Doubles: 1000
   for the move foe_best_at expects on my Pokemon or my partner, else 0. Read.seen keeps the last outcome (RD_*): in
   singles also the odds / 16 above bit 1; in doubles foe 0's outcome in bits 0-1, foe 1's in bits 2-3 */
#ifdef HOST_ENGINE_H
int rd_t, rd_pct;                   /* tools/sim/bridge.c: SIM_RD_T, SIM_RD_P; rd_t 0 uses every read (rc32) */
#else
#define rd_t 700
#define rd_pct 300
#endif
enum { RD_NONE, RD_ODDS, RD_DRAW, RD_BLIND };

static u32 rd_lcg(u32 x, u32 v)
{
    return (x ^ v) * 1103515245u + 12345u;
}

/* the AI's own draw about foe d this turn: an LCG seeded by the battle (its setup's RTC seed, BattleSetup+0x19C, and
   the species of the first foe client's party) and keyed by the turn (d's pokeID, turns out and HP, my side's HP), so
   both my Pokemon in a double draw the same and a replay draws the same. No address goes in (battle_tag has the main
   module's), so a build that moves main RAM code draws the same (rc33 merge, qa/decisions.tsv 2026-10-08T14:45) */
static int rd_draw(const Ctx *c, const Mon *d)
{
    u8 *main = AT(bptr, MAIN_PTR);
    void *setup = OK_PTR(main) ? AT(vptr, (u32)main + MAIN_SETUP) : 0;
    void *op = E_PARTY(E_POKECON(1), (c->client & 1) ^ 1);
    u32 x = OK_PTR(setup) ? AT(u32, (u32)setup + 0x19C) : 0;
    int i, n = OK_PTR(op) ? E_PARTY_COUNT(op) : 0;
    for (i = 0; i < n && i < 6; i++) {
        void *b = E_PARTY_MEMBER(op, i);
        x = rd_lcg(x, OK_PTR(b) ? B_SPECIES(b) : 0);
    }
    x = rd_lcg(x, d->id | (u32)d->turns << 8 | (u32)d->hp << 16);
    x = rd_lcg(x, c->me.hp + (c->has_ally ? c->ally.hp : 0));
    x = rd_lcg(x, 0);
    return (x >> 16) % 1000 < (u32)rd_pct;
}

#ifdef HOST_ENGINE_H
void sim_rd_note(int u);            /* tools/sim/battle.c: the outcomes per game (SIM_CTR_DIR) */
#else
#define sim_rd_note(u) ((void)0)
#endif
/* whether the read of foe d's action, of blind odds p, is used: RD_ODDS, RD_DRAW or RD_BLIND */
static int rd_use(const Ctx *c, const Mon *d, int p)
{
    int u = p >= rd_t ? RD_ODDS : rd_draw(c, d) ? RD_DRAW : RD_BLIND;
    sim_rd_note(u);
    return u;
}

/* singles: the blind odds of the foe's move in slot k */
static int rd_move_odds(Ctx *c, int k)
{
    Pair p;
    int s;
    pair_data(c, &p);
    reply_odds(c, &p);
    s = p.w[0] + p.w[1] + p.w[2] + p.w[3];
    return s ? 1000 * p.w[k] / s : 0;
}

/* singles, once the foe's action is read: keeps c->kn[0] or forgets it. A committed switch needs the blind decision
   for its odds (foe_switch): made here, into o and *k, it is final (returns 1) when the read is not used. When it is
   used, decide runs again (adv_poll), and AIF_RDMEMO puts back what the blind run wrote across turns first: my switch
   memory (memo: BACK_COST and A2_LOOP's streak read last turn's), the Read record's miss bits and the Habit's named
   switch-in (a used read names none, as rc32) */
static int rd_gate(Ctx *c, void *op, Option *o, int *k)
{
    Known kn = c->kn[0];
    int p = 0, u;
    Memo m0 = memo[c->client & 3];
    Read r0 = *reads(c);
    Habit h0 = habit[(c->client & 1) ^ 1];
    if (!kn.kind || rd_t <= 0)
        return 0;
    if (kn.kind == FK_MOVE)
        p = rd_move_odds(c, kn.idx);
    else if (kn.kind == FK_SWITCH) {
        memset(c->kn, 0, sizeof c->kn);
        *k = decide(c, o);
        p = c->xw && OK_PTR(op) && E_PARTY_MEMBER(op, kn.idx) == c->foes[0].bpp ? c->xw : 0;
    }
    u = rd_use(c, &c->opp, p);
    if (kn.kind == FK_SWITCH && u != RD_BLIND && aifix(AIF_RDMEMO)) {
        memo[c->client & 3] = m0;
        *reads(c) = r0;
        habit[(c->client & 1) ^ 1] = h0;
    }
    reads(c)->seen = u | (p / 16) << 2;
    memset(c->kn, 0, sizeof c->kn);
    if (u != RD_BLIND)
        c->kn[0] = kn;
    return kn.kind == FK_SWITCH && u == RD_BLIND;
}

/* doubles: keeps or forgets each foe's read */
static void rd_gate_doubles(Ctx *c)
{
    int f, s0, s1, p, u, seen = 0;
    for (f = 0; f < c->nfoes && rd_t > 0; f++) {
        Known kn = c->kn[f];
        if (!kn.kind)
            continue;
        memset(&c->kn[f], 0, sizeof kn);
        s0 = s1 = -1;
        foe_best_at(c, f, 0, &s0);
        if (c->has_ally)
            foe_best_at(c, f, 1, &s1);
        p = kn.kind == FK_MOVE && (kn.idx == s0 || kn.idx == s1) ? 1000 : 0;
        u = rd_use(c, &c->foes[f], p);
        seen |= u << 2 * f;
        if (u != RD_BLIND)
            c->kn[f] = kn;
    }
    if (rd_t > 0)
        reads(c)->seen = seen;
}

static int adv_poll(void *param, void *st, int arg)
{
    tune_side((arg & 1) ^ 1);         /* the deciding side's tuning (the two sides' polls interleave in self-play) */
    int s = context(st), k = 0;
    Ctx *c;
    Option o;
    if (s < 0) {
        dsteer_drop(arg, 0);
        return E_OV11(param, st, arg);
    }
    c = live[s].c;
    g_wz = c ? (MoveCache *)(c + 1) : 0;
    if (!c) {
        ai_debug[(arg & 1) ^ 1].fallback = FB_ALLOC;
        ai_debug[(arg & 1) ^ 1].magic = DEBUG_MAGIC;
    }
    if (!c || c->mode == M_FALLBACK) {
        dsteer_drop(arg, c ? c->me.id : 0);
        return E_OV11(param, st, arg) ? done(s) : 0;
    }
    set_worth(c->strong);
    if (c->mode == M_NEW) {
        int why;
        c->mode = M_WORK;
        c->phase = 0;
        c->polls = 0;
        c->fallback = FB_NONE;
        c->trainer = arg & 0xFF;
        c->dbg = &ai_debug[(arg & 1) ^ 1];      /* arg: the client, whose bit 0 is its side */
        c->unsure = &c->dbg->sim_unsure;
        c->dbg->fallback = FB_NONE;
        c->dbg->nopt = 0;
        why = snapshot(c);
        if (why) {
            fail(c, why);
            return 0;
        }
        return 0;
    }
    if (++c->polls > POLL_LIMIT) {
        fail(c, FB_POLLS);
        return 0;
    }
    c->dbg->polls = c->polls;
    if (c->phase == PH_STEER) {
        if (c->doubles)
            dsteer_turn(c, &c->held);
        else
            steer_turn(c, &c->held);
        write_action(c, param, &c->held);
        c->dbg->decisions++;
        return done(s);
    }
    if (c->doubles) {
        if (c->phase < 2) {
            sims_doubles(c, c->phase);
            if (++c->phase == 2) {
                int i;
                for (i = 0; i < 4; i++) {
                    c->d_mo[i] = c->d_mf[0][i];
                    c->d_om[i] = c->d_fm[0][i];
                }
                debug_snapshot(c);
            }
            return 0;
        }
        if (c->phase < 2 + c->nbench) {
            bench_doubles(c, c->phase - 2);
            c->phase++;
            return 0;
        }
        if (!c->known) {        /* read_choice: wait for both foes' choices, then decide knowing them */
            void *pc = E_POKECON(1);
            int f;
            if (foe_choice(c) < 0) {
                c->polls--;     /* waiting polls do not count against POLL_LIMIT */
                c->waiting = 1;
                return 0;
            }
            c->waiting = 0;
            c->known = 1;
            rd_gate_doubles(c);
            for (f = 0; f < c->nfoes; f++)
                c->swapped |= foe_committed(c, &c->foes[f], &c->kn[f], OK_PTR(pc) ? E_PARTY(pc, c->fcl[f]) : 0) << f;
            for (f = 0; f < c->nfoes && c->nfoes == 2; f++)     /* an item used on its partner (items go before moves) */
                if (c->kn[f].kind == FK_ITEM && c->kn[f].idx == c->foes[f ^ 1].id && !(c->swapped >> (f ^ 1) & 1))
                    item_on(&c->foes[f ^ 1], c->kn[f].item);
            if (c->swapped) {   /* a switch-in is the foe there this turn: the simulations again, in this poll */
                sims_doubles(c, 0);
                sims_doubles(c, 1);
                for (f = 0; f < c->nbench; f++)
                    bench_doubles(c, f);
            }
        }
        if (!decide_doubles(c, &o)) {
            fail(c, FB_NO_OPTION);
            return 0;
        }
        if (dsteer_wanted(c, &o)) {
            c->held = o;
            c->phase = PH_STEER;
            return 0;
        }
        write_action(c, param, &o);
        c->dbg->decisions++;
        return done(s);
    }
    if (c->phase == 0) {
        sims_active(c);
        debug_snapshot(c);
        c->phase = 1;
        return 0;
    }
    if (c->phase <= c->nbench) {
        damage_bench(c, c->phase - 1);
        c->phase++;
        return 0;
    }
    if (c->phase == c->nbench + 1 && c->opp_others && !c->kn[0].kind) {
        c->phase++;
        switch_in(c);
        return 0;
    }
    if (!c->known) {            /* read_choice: wait for the foe's choice, then decide knowing it (RD: rd_gate) */
        void *pc, *op;
        if (foe_choice(c) < 0) {
            c->polls--;         /* waiting polls do not count against POLL_LIMIT */
            c->waiting = 1;
            return 0;
        }
        c->waiting = 0;
        c->known = 1;
        c->fs_move = c->kn[0].kind == FK_MOVE ? c->kn[0].idx + 1 : 0;      /* the committed slot + 1 (fs_guard_note) */
        pc = E_POKECON(1);
        op = OK_PTR(pc) ? E_PARTY(pc, c->opp_client) : 0;
        if (rd_gate(c, op, &o, &k))
            goto decided;
        /* a switch: the newcomer is the foe this turn, so its simulations again, in this poll (the player waits now);
           the rest of the snapshot is the same (the party order changes only during the turn) */
        if (foe_committed(c, &c->opp, &c->kn[0], op)) {
            int b;
            c->xin = 0;
            sims_active(c);
            debug_snapshot(c);
            for (b = 0; b < c->nbench; b++)
                damage_bench(c, b);
        }
    }
    k = decide(c, &o);
decided:
    fs_guard_note(c, k ? &o : 0);
    fs.on = 0;
    if (!k) {
        fail(c, FB_NO_OPTION);
        return 0;
    }
    if (steer_wanted(c, &o)) {
        c->held = o;
        c->phase = PH_STEER;
        return 0;
    }
    write_action(c, param, &o);
    c->dbg->decisions++;
    return done(s);
}

__attribute__((section(".text.entry"))) int adv_entry(void *param, void *st, int arg)
{
    int r = adv_poll(param, st, arg);
    waza_close();
    return r;
}
