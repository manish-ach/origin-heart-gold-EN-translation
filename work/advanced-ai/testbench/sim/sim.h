/* A singles battle simulator for this hack: the ROM's own data (build/simdata.c, tools/sim/gen_simdata.py), the
   battle rules as the hack's engine has them where they were measured (qa/aivsai/ENGINE_FACTS.md) and the official
   ones elsewhere, and the policies that play it (the host build of the advanced AI, a greedy bot).

   Sides are the engine's clients: side 0 the player's (pokeIDs 1-6), side 1 the trainer's (13-18). party[s][0] is
   the Pokemon on the field, as the engine orders its party lists. */
#ifndef SIM_H
#define SIM_H

#include <stdint.h>
#include <stdio.h>

typedef uint8_t u8;
typedef int8_t s8;
typedef uint16_t u16;
typedef int16_t s16;
typedef uint32_t u32;
typedef int32_t s32;
typedef uint64_t u64;

/* ---------------------------------------------------------------- the ROM's data (generated) */

typedef struct {
    u8 base[6];             /* HP Atk Def Spe SpA SpD, the ROM's order */
    u8 types[2];
    u16 abil[3];            /* slot 1, slot 2, hidden */
    u8 gender, evolves;
} SpeciesRec;

typedef struct {
    u8 type, quality, cls, power, acc, pp;      /* cls 0 status, 1 physical, 2 special; acc 101 never misses */
    s8 prio;
    u8 hits_min, hits_max;
    u16 sick;               /* SICK_*: the status or condition it inflicts */
    u8 sick_per, sick_cont, sick_tmin, sick_tmax;   /* cont 1 lasting, 2 counted turns, 4 binding; bad poison: tmin 15 */
    u8 crit, flinch;
    u16 effect;             /* the AI's effect code, shared by moves that work alike */
    s8 drain, heal;         /* drain: % of the damage, negative = recoil; heal: % of max HP (negative: Struggle) */
    u8 target;              /* TG_* */
    u8 rank_type[3];        /* 1 Atk 2 Def 3 SpA 4 SpD 5 Spe 6 Acc 7 Eva 9 all five */
    s8 rank_val[3];
    u8 rank_per[3];         /* 0 on a status move: always */
    u32 flags;              /* FL_* bits */
} MoveRec;

typedef struct {
    u16 species, ability, item, moves[4];
    u8 level, nature, ivs, evs[6];          /* evs in the game's order: HP Atk Def Spe SpA SpD */
} SetRec;

typedef struct {
    u16 trainer;
    const char *name;
    u8 n, pool;             /* POOL_80: all six at level 80 or above, the teams aivsai draws from; POOL_RANDOM:
                               an extra team (gen_simdata.py --extra-teams), aivsai's random teams */
    SetRec mon[6];
} TeamRec;
enum { POOL_OTHER, POOL_80, POOL_RANDOM };

extern const SpeciesRec sim_species[];
extern const MoveRec sim_moves[];
extern const u8 sim_chart[18][18];          /* attacker row; 0/2/4/8 = x0/x0.5/x1/x2 */
extern const u16 sim_weight[];              /* tenths of a kg; 0 unknown (species past 493) */
extern const u8 sim_item_handled[], sim_item_boost[], sim_item_resist[];   /* boost/resist: type + 1, 0 none */
extern const TeamRec sim_teams[];
extern const int sim_nspecies, sim_nmoves, sim_nitems, sim_nteams, sim_nabilities;
extern const char *const sim_species_name[], *const sim_move_name[], *const sim_ability_name[], *const sim_item_name[];

#ifndef SIM_NO_ENUMS     /* bridge.c takes the same values from tools/ai/engine.h */
enum { T_NORMAL, T_FIGHTING, T_FLYING, T_POISON, T_GROUND, T_ROCK, T_BUG, T_GHOST, T_STEEL, T_FAIRY, T_FIRE, T_WATER,
       T_GRASS, T_ELECTRIC, T_PSYCHIC, T_ICE, T_DRAGON, T_DARK, T_NONE };
enum { CLS_STATUS, CLS_PHYSICAL, CLS_SPECIAL };
enum { Q_DAMAGE, Q_SICK, Q_EFFECT, Q_RECOVER, Q_DAMAGE_SICK, Q_EFFECT_SICK, Q_DAMAGE_EFFECT, Q_DAMAGE_EFFECT_USER,
       Q_DRAIN, Q_OHKO, Q_FIELD, Q_SIDE, Q_PUSHOUT, Q_OTHER };
/* move targets (singles reading): the user, its side, or the foe */
enum { TG_OTHER = 0, TG_USER_OR_ALLY = 1, TG_ALLY = 2, TG_ENEMY = 3, TG_ALL_OTHERS = 4, TG_ALL_ENEMIES = 5,
       TG_USER_SIDE_MONS = 6, TG_USER = 7, TG_ALL = 8, TG_RANDOM = 9, TG_FIELD = 10, TG_ENEMY_SIDE = 11,
       TG_USER_SIDE = 12, TG_CURSE = 13 };
enum { FL_CONTACT = 1u << 0, FL_CHARGE = 1u << 1, FL_RECHARGE = 1u << 2, FL_PROTECT = 1u << 3, FL_PUNCH = 1u << 7,
       FL_SOUND = 1u << 8, FL_POWDER = 1u << 28, FL_BITE = 1u << 29, FL_BALL = 1u << 30 };
/* the move data's condition numbering (WP_SICK), as the battle Pokemon's condition slots use it */
enum { SICK_NONE, SICK_PAR, SICK_SLP, SICK_FRZ, SICK_BRN, SICK_PSN, SICK_CONFUSION, SICK_ATTRACT, SICK_BIND,
       SICK_NIGHTMARE, SICK_CURSE = 10, SICK_TAUNT = 11, SICK_TORMENT = 12, SICK_DISABLE = 13, SICK_YAWN = 14,
       SICK_LEECH_SEED = 18, SICK_PERISH = 20, SICK_INGRAIN = 21, SICK_ENCORE = 23, SICK_CHARGE = 27, SICK_AQUA_RING = 36 };
enum { ST_NONE, ST_PAR, ST_SLP, ST_FRZ, ST_BRN, ST_PSN };      /* main status */
/* the weather byte as the engine keeps it ([main+0x58]); snow does no chip damage here (measured) */
enum { W_NONE, W_RAIN, W_SUN, W_SAND, W_SNOW, WX_STRONG_WINDS = 7, WX_HEAVY_RAIN = 8, WX_HARSH_SUN = 9 };
enum { TERRAIN_NONE, TERRAIN_GRASSY, TERRAIN_MISTY, TERRAIN_ELECTRIC, TERRAIN_PSYCHIC };
/* stat stage slots: Atk Def SpA SpD Spe Acc Eva (the bpp's order); stat slots the first five */
enum { STAT_ATK, STAT_DEF, STAT_SPA, STAT_SPD, STAT_SPE, STAT_ACC, STAT_EVA };
#endif

/* ---------------------------------------------------------------- the battle */

typedef struct {
    u16 species, ability, item, hp, maxhp;
    u16 stat[5];                /* Atk Def SpA SpD Spe, before stages */
    u16 moves[4];
    u8 pp[4], used;             /* used: bit i, move slot i used since it came out */
    u8 level, types[2], id;     /* id: the pokeID */
    u8 status, sleep;           /* sleep: turns it still sleeps through (it acts on the turn this reaches 0) */
    u8 slept;                   /* turns slept through so far (the engine's count, which survives a switch) */
    u8 toxic, tox_n;            /* bad poison, and its turn count (1/16 x (count + 1)) */
    u8 set;                     /* its place in the team as listed (logs) */
    u16 lost_item;              /* the item it used up (Recycle) */
    u8 ate_berry;               /* it ate a Berry in this battle (Belch) */
} Mon;

/* what leaves the field with the Pokemon on it */
typedef struct {
    s8 stage[7];
    u8 confused;                /* turns left */
    u8 seeded, taunt, yawn, aqua, ingrain, cursed, trapped, nightmare;
    u8 encore, encore_slot;     /* turns left, the slot it locks */
    u8 bind, bind_by;           /* binding turns left */
    u8 charging;                /* slot + 1 of the move it charges, which lands next turn */
    u16 semi;                   /* SEMI_* while charging Fly, Dig, Dive or Phantom Force */
    u8 recharge;                /* it must recharge this turn */
    u8 lock, lock_slot;         /* Outrage and its like: turns left */
    u8 choice;                  /* slot + 1 its Choice item locks */
    u8 protects;                /* the engine's streak byte (+0x2DD): kept after a move of IS_STREAK_MOVE, zeroed by a
                                   lost turn or a failed Protect; the next Protect restarts it after any other move */
    u8 ran;                     /* this turn's move got past what can stop it (else the streak is zeroed) */
    u8 protecting, flinched, destiny, focus, endure;
    u8 acted;                   /* it has acted since it came out (Fake Out) */
    u16 turns_out;
    u16 last_move, worked;      /* the engine's count of that move's uses in a row that worked */
    u16 sub;                    /* substitute HP */
    u16 hit_by_move;            /* this turn: the last damaging move that hit it, its damage, the class */
    u16 hit_dmg;
    u8 hit_cls;
    u16 hit_last;               /* the damage of its last hit (Counter against multi-hit: 2x the last, seen in logs) */
    u8 moved;                   /* it has moved this turn (2: it fainted) */
    u16 planned;                /* the move it chose this turn (Sucker Punch) */
    u8 flash_fire, unburden, stockpile, roosted;
    u8 types[3];                /* the types in battle (Roost, Soak...), types[2] an added one */
    u16 ability;                /* the ability in battle (Role Play...) */
    u8 perish;                  /* turns left + 1, 0 none */
    u8 transformed;
    u8 conf_n;                  /* the validator only: move attempts while confused (its confusion has no drawn length) */
    u8 failed;                  /* its last move failed (Stomping Tantrum) */
    u16 entered;                /* the turn it came out (Speed Boost skips that turn's end) */
    u8 coat, powder, snatch;    /* this turn: Magic Coat bounces, Powder burns a Fire move, Snatch takes the next move */
    u8 identified;              /* Odor Sleuth (1): Normal and Fighting hit its Ghost type; Miracle Eye (2): Psychic its Dark */
    u8 tele, magnet;            /* Telekinesis and Magnet Rise: turns it floats */
    u8 embargo, torment, imprison, grudge;
    u8 stats_saved;                         /* Guard/Power Split, Power Trick: saved_stat holds the stats to restore */
    u16 saved_stat[5];                      /* as it leaves */
    u8 mimic_slot;                          /* Mimic: slot + 1, and the move it replaced */
    u16 mimic_move;
    u8 disabled;                            /* Disable: turns left on disabled_move */
    u16 disabled_move;
} Volatile;

#ifndef SIM_NO_ENUMS
enum { SEMI_DIVE = 0x20, SEMI_FLY = 0x40, SEMI_DIG = 0x80, SEMI_SHADOW = 0x100 };    /* the engine's B_SEMI bits */
#endif

typedef struct {
    u8 spikes, tspikes, rocks;
    u8 reflect, screen, veil, tailwind, safeguard;      /* turns left */
    u8 wish;                    /* turns until it lands */
    u8 sticky;                  /* Sticky Web */
    u16 wish_hp;
} Side;

/* one game's counts, for the logs (tools/sim/logstats.py's schema) */
typedef struct {
    u16 moves[2], switches[2], items[2], faints[2], replacements[2];
    u16 first_faint_turn;
} Tally;

struct Oracle;

typedef struct {
    Mon party[2][6];
    u8 n[2];
    Volatile v[2];
    Side side[2];
    u8 weather, weather_turns;  /* turns 255: no end */
    u8 terrain, terrain_turns, trick_room;
    u8 gravity, wonder_room, magic_room, mud_sport, water_sport;    /* turns left */
    u16 turn;
    u8 rand_team[2];            /* the side's team is a POOL_RANDOM one: the original-AI bot plays its random-team model
                                   (in what was padding, so a trainer game's bytes and battle_hash stay as they were) */
    u8 future[2];               /* Future Sight / Doom Desire on side t: end-of-turn passes until it lands (padding too) */
    u8 future_by[2];            /* its user's pokeID, bit 7 set for Doom Desire */
    u64 rng;
    s8 winner;                  /* -1 still on, 0/1 the side that won, 2 a draw */
    s8 last_faint;              /* the side of the last Pokemon to faint */
    Tally tally;
    u16 last_used;              /* the last move used in the battle (Copycat) */
    u16 last_hit[2];
    Mon tf_saved[2];            /* the Pokemon before Transform, restored as it leaves */
    int verbose;                /* print the turns (sim_log) */
    struct Oracle *oracle;      /* the turn-level validator (validate.c): it decides the random outcomes; 0: sample */
} Battle;

/* ---------------------------------------------------------------- actions and policies */

enum { ACT_NONE, ACT_MOVE, ACT_SWITCH };
typedef struct { u8 kind, idx; } Action;     /* ACT_MOVE: idx the move slot (4 = Struggle); ACT_SWITCH: the party index */

typedef struct Policy {
    const char *name;
    Action (*choose)(Battle *b, int side, void *ctx);
    int (*replace)(Battle *b, int side, void *ctx);     /* the party index sent in after a faint or a pivot */
    void (*battle_start)(Battle *b, void *ctx);
    void *ctx;
    int (*lead)(Battle *b, int side, void *ctx);        /* the party index that leads (0: the party's order), or none */
} Policy;

/* foresight (rng_foresight): what one turn did to each side's move, recorded while g_fsr is set */
/* chg: its status or stages changed this turn before its move (a chance effect landed on it: the DS predictor stops) */
/* steering (rc31 L): roll1 the first hit's damage index + 1 (0 none), landed its chance effect landed, par its own full
   paralysis stopped it; oth[s]: draws the turn made for side s outside its move's own rolls (its end-of-turn rolls, its
   Focus Band or contact ability on the other's move, a status length), which a shifted stream would change */
typedef struct { u8 called, reached, stopped, flinched, missed, crit, flinch_foe, chg; s16 dmg; u8 roll1, landed, par, st_at, stg; } FsSide;
typedef struct { FsSide s[2]; u8 n, st0[2]; s8 stg0[2][7]; u8 oth[2]; u16 mv[2]; } FsRec;   /* st_at: the status at the call, stg: its stages changed; mv: the move called */   /* called: the move's place in the turn (1 first) */
extern FsRec *g_fsr;
extern int g_fs_side;                   /* the engine side whose foresight is checked (SIM_FS_SIDE); -1 none */
extern long g_fs_check[5];              /* real turns with a known cell; my part known, right; the foe's known, right */
/* luck counters (rc31 L): per side and roll class the real game's rolls with 0 < p < 1 (the damage index always),
   muted while the bridge plays copies of a turn; the classes in tools/ai advai.c's STC_* order */
enum { LUCK_ACC, LUCK_CRIT, LUCK_DMG, LUCK_CHANCE, LUCK_PAR, LUCK_N };
extern int sim_luck_mute;
void luck_roll(int side, int cls, double p, double x, int good);
void sim_luck_emit(FILE *f);
void sim_ctr_emit(FILE *f);         /* battle.c: the perfect counters and RD's outcomes of this game (rc33 RD) */

/* the drama observer (drama_obs.c, SIM_DRAMA_TRACE): the trace of every battle sim play plays; the turn a steered
   choice moved the RNG (bridge.c steer_step), -1 none */
extern int sim_steered_turn;
void drama_obs_open(const char *path);
void drama_obs_close(void);
void drama_obs_battle(const Battle *b, u64 seed, int trainer, int level, int bot, int hard, int ace);
void drama_obs_end(const Battle *b, int max_turns);

/* ---------------------------------------------------------------- the API */

void sim_build_mon(Mon *m, const SetRec *s, int level, int id, int set);
void sim_leads(Battle *b, const Policy *p0, const Policy *p1);  /* after the parties are filled: the policies' leads */
void sim_start(Battle *b, u64 seed);            /* after the parties are filled: entry effects */
int sim_turn(Battle *b, const Policy *p0, const Policy *p1);    /* one turn; returns 1 while the battle goes on */
int sim_turn_choose(Battle *b, const Policy *const pol[2], Action act[2]);   /* sim_turn = choose, resolve, finish */
void sim_turn_resolve(Battle *b, const Policy *const pol[2], const Action act[2]);
int sim_turn_finish(Battle *b, const Policy *const pol[2]);
int sim_play(Battle *b, const Policy *p0, const Policy *p1, int max_turns);

/* rules the policies and the AI bridge share */
int sim_legal_move(const Battle *b, int side, int slot);
int sim_can_switch(const Battle *b, int side);
int sim_trapped(const Battle *b, int side);
int sim_alive(const Mon *m);
int sim_eff_speed(const Battle *b, int side);
int sim_weather(const Battle *b);               /* the weather the field acts with (Cloud Nine: none) */
u32 sim_rand(Battle *b, u32 n);                 /* 0..n-1 */

/* damage (damage.c). The defender's ability and item count only when def_active (the engine's simulation);
   roll 85-100; returns one hit's damage, 0 when the move does not affect it (eff_out: 0, 2, 4, 8, 16...) */
typedef struct {
    const Mon *a, *d;
    const Volatile *va, *vd;        /* may be NULL: no stages, the species' types */
    int a_active, d_active;
    int weather, terrain;
    int screen;                     /* the defender's side has Reflect / Light Screen / Aurora Veil for this class */
    int crit, roll, hit;            /* hit: 0 the first hit of the move (Multiscale, resist berries) */
    int sim;                        /* the engine's simulation: 1 against an immunity, no "no effect" abilities */
    int foe_moved;                  /* the target already moved this turn (Payback, Bolt Beak...) */
    int type_eff;                   /* out: x4 effectiveness (0 immune, 4 neutral, 8 super, 16 double) */
    int fixed;                      /* out: the damage was fixed (no roll) */
} DamageQ;
int sim_damage(DamageQ *q, int move);
int sim_move_type(const Mon *a, const Volatile *va, int move, int weather, int terrain);
int sim_type_eff(int type, const u8 *types, int move);   /* x4 per type, multiplied (4 = neutral) */

#ifdef SIM_DS            /* the DS build prints nothing */
#define sim_log(...) ((void)0)
#else
void sim_log(const Battle *b, const char *fmt, ...);
#endif

#endif
