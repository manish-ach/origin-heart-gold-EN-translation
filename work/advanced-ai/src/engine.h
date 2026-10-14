/* The hack's battle engine (overlay 14, a port of the Gen 5 server/client design) as the advanced AI
   uses it. Every address and offset here was mapped in qa/advanced_ai_research.md and checked by
   tools/aibench.py (the snapshot test compares what the AI reads with the scenario it set up). */
#ifndef AI_ENGINE_H
#define AI_ENGINE_H

typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef signed short s16;
typedef unsigned int u32;
typedef signed int s32;
typedef void *vptr;      /* for AT(): the volatile goes on the read, not the pointee */
typedef u8 *bptr;

#define AT(type, addr) (*(volatile type *)(addr))
#define CALL(addr, ret, ...) ((ret (*)(__VA_ARGS__))((u32)(addr) | 1))

#define RAM_LO 0x02000000u
#define RAM_HI 0x02400000u
/* test only (tools/aivsai.py --self): the magic in the last word of ITCM RAM makes ai_replace serve the player's
   side too. Nothing in the game writes ITCM RAM past .itcm_bss, which ends below REPLACED_AT (link.ld) */
#define SELFPLAY_FLAG 0x01FFFFFCu
#define SELFPLAY_MAGIC 0x53454C46u      /* "SELF" */
#define SELFPLAY() (AT(u32, SELFPLAY_FLAG) == SELFPLAY_MAGIC)
/* test only (tools/aibench.py, tools/aiprops.py): this magic in the word below the Read records keeps the trainer's
   party order (lead.c), so a set position starts with its own lead */
#define NOLEAD_FLAG 0x01FFFF98u
#define NOLEAD_MAGIC 0x444C4F4Eu        /* "NOLD" */
#define NOLEAD() (AT(u32, NOLEAD_FLAG) == NOLEAD_MAGIC)
/* test only (tools/aibench.py, tools/aiprops.py): this magic in the word below NOLEAD makes the trainer's side decide
   without waiting for the player's committed action (advai.c foe_choice), so a set position grades the blind decision */
#define NOREAD_FLAG 0x01FFFF94u
#define NOREAD_MAGIC 0x44524F4Eu        /* "NORD" */
#define NOREAD() (AT(u32, NOREAD_FLAG) == NOREAD_MAGIC)
#define REPLACED_AT 0x01FFFFBCu         /* replace.c's two Replaced records, up to the flag */
/* advai.c's two Read records (the foe's play so far), the trainer side's first, below the Replaced records; at a fixed
   address so that tools/aibench.py (strong=True) can write a pinned one */
#define READS_AT 0x01FFFF9Cu
/* test only (tools/aivsai.py, synced luck): the battle's LCG word, kept aside while an AI call runs on its side's own
   stream, as FS_WORD_MAGIC then the word, in the 8 bytes below NOREAD; the foresight predicts from it (advai.c
   fs_trust) */
#define FS_WORD_AT 0x01FFFF8Cu
#define FS_WORD_MAGIC 0x44575346u       /* "FSWD" */
#define OK_PTR(p) ((u32)(p) >= RAM_LO && (u32)(p) < RAM_HI && !((u32)(p) & 3))

/* main battle module, its fields */
#define MAIN_PTR 0x02255BACu
#define MAIN_SETUP 0x10          /* BattleSetup: type +0, trainer[i] at +0x28 + 0x34 i (items u16[4] at +4) */
#define MAIN_RNG 0x24C           /* battle LCG state; read once to seed our own RNG, never advanced */
#define MAIN_SLOT 0x26C          /* overlay in the battle slot (SwitchSlotOverlay) */
#define MAIN_CLIENTS 0x234       /* per-client work, passed to the trapped check */
#define MAIN_FIELD 0x58          /* the field state; byte 0 the weather (WX_*), byte 1 its turns left (255: no end) */
#define TYPE_CHART 0x0224DA40u   /* 18 x 18, attacker row; 0/2/4/8 = x0/x0.5/x1/x2 */
#define OV11_ENTRY 0x021E4DA0u   /* the original AI's entry, in our overlay image too */
/* the field effects that only the engine's other copy keeps (f = E_POKECON0()): effect e on while +0x89+e is 1, its
   length in bits 3-8 of the u32 at +0x14+8e, the turn ends passed at +0x99+e; the terrain's kind at +6 */
#define FLD_ON(f, e) AT(u8, (u32)(f) + 0x89 + (e))
#define FLD_LEFT(f, e) (FLD_ON(f, e) ? (int)((AT(u32, (u32)(f) + 0x14 + 8 * (e)) >> 3) & 63) - AT(u8, (u32)(f) + 0x99 + (e)) : 0)
#define FLD_TERRAIN(f) AT(u8, (u32)(f) + 6)
enum { FE_TERRAIN = 0, FE_TRICK_ROOM = 2 };
enum { TERRAIN_GRASSY = 1, TERRAIN_MISTY, TERRAIN_ELECTRIC, TERRAIN_PSYCHIC };
/* the side effects (screens, hazards...): per side 19 entries of 12 bytes, side 0 the player's; the u16 at +10
   counts layers (measured by RAM diffs with Stealth Rock, Spikes and Toxic Spikes set by either side) */
#define SIDE_EFF 0x02255C84u
#define SIDE_EFF_STRIDE 0xE4
#define SIDE_LAYERS(side, eff) AT(u16, SIDE_EFF + SIDE_EFF_STRIDE * (side) + 12 * (eff) + 10)
/* turns left, this one included, of a counted side effect (Tailwind): length in bits 3-8 of the state at +4, turn ends
   passed at +8 (measured, round 3) */
#define SIDE_LEFT(side, eff) (SIDE_LAYERS(side, eff) ? (int)((AT(u32, SIDE_EFF + SIDE_EFF_STRIDE * (side) + 12 * (eff) + 4) >> 3) & 63) - \
                              AT(u16, SIDE_EFF + SIDE_EFF_STRIDE * (side) + 12 * (eff) + 8) : 0)
/* Safeguard: measured (rc28, the player's Safeguard turned on its side's effect 2) */
enum { SE_REFLECT = 0, SE_LIGHT_SCREEN = 1, SE_SAFEGUARD = 2, SE_TAILWIND = 4, SE_SPIKES = 6, SE_TOXIC_SPIKES = 7, SE_STEALTH_ROCK = 8 };

enum { W_NONE, W_RAIN, W_SUN, W_SAND, W_HAIL };     /* W_HAIL is snow here: no chip damage (measured) */
/* the weather byte's other values (measured with the abilities that set them) */
enum { WX_STRONG_WINDS = 7, WX_HEAVY_RAIN = 8, WX_HARSH_SUN = 9 };
enum { T_NORMAL, T_FIGHTING, T_FLYING, T_POISON, T_GROUND, T_ROCK, T_BUG, T_GHOST, T_STEEL, T_FAIRY,
       T_FIRE, T_WATER, T_GRASS, T_ELECTRIC, T_PSYCHIC, T_ICE, T_DRAGON, T_DARK, T_NONE };
enum { S_NONE, S_PAR, S_SLP, S_FRZ, S_BRN, S_PSN };     /* main status (BPP_GetPokeSick) */

/* battle Pokemon (bpp), the client's copy */
#define B_SPECIES(b) AT(u16, (u32)(b) + 0x00)
#define B_ID(b)      AT(u8, (u32)(b) + 0x14)
#define B_ABILITY(b) AT(u16, (u32)(b) + 0x16)
#define B_MAXHP(b)   AT(u16, (u32)(b) + 0x1C)
#define B_HP(b)      AT(u16, (u32)(b) + 0x1E)
#define B_ITEM(b)    AT(u16, (u32)(b) + 0x20)
#define B_LEVEL(b)   AT(u8, (u32)(b) + 0x24)
#define B_STAT(b, i) AT(u16, (u32)(b) + 0x22C + 2 * (i))   /* 0 Atk 1 Def 2 SpA 3 SpD 4 Spe */
#define B_TYPE(b, i) AT(u8, (u32)(b) + 0x236 + (i))         /* 2 = added type, 18 = none */
#define B_STAGE(b, i) AT(u8, (u32)(b) + 0x240 + (i))        /* Atk Def SpA SpD Spe Acc Eva; 6 = neutral */
#define B_MOVE(b, i) AT(u16, (u32)(b) + 0x25A + 0x12 * (i))
#define B_PP(b, i)   AT(u8, (u32)(b) + 0x25C + 0x12 * (i))
#define B_NMOVES(b)  AT(u8, (u32)(b) + 0x29E)
/* turns since it came out, +1 at every turn's end (measured: a turn blocked by Protect counts; +0x2A8, used before,
   is reset by a blocked move). One that came in by U-turn during the last turn is at 1 */
#define B_TURNS_OUT(b) AT(u16, (u32)(b) + 0x2A4)
/* bit 0: it has acted since it came out, clear on its first turn (Fake Out works: measured after U-turn entries and
   a move blocked by Protect); bit 1: it must recharge this turn (measured after Hyper Beam) */
#define B_TURNFLAGS(b) AT(u8, (u32)(b) + 0x2BA)
/* poison's condition word (condition 5): above bit 2 set for bad poison; and bad poison's turn count, 0 on its first
   turn, which takes 1/16 of max HP, then 2/16... (measured) */
#define B_POISON_WORD(b) AT(u32, (u32)(b) + 0x3C + 8 * 5)
#define B_TOXIC_TURNS(b) AT(u8, (u32)(b) + 0x1C5)
#define B_PROTECTS(b) AT(u8, (u32)(b) + 0x2DD)     /* Protects in a row that worked (measured: 0 1 0 1 using it each turn) */
/* the last move it used, and the engine's count of that move's uses in a row that worked: 0 when the last one failed,
   missed or had no effect (measured: Spore and Leech Seed into a Grass type, Leech Seed on a seeded target, a miss,
   Swords Dance at +6; not reset by Last Resort's failure or a failed Protect) */
#define B_LAST_MOVE(b) AT(u16, (u32)(b) + 0x2B2)
#define B_WORKED(b) AT(u16, (u32)(b) + 0x2A8)
/* move slot i used since it came out (bit 0, set whether the move worked or not; measured with Last Resort, which
   worked once its other moves were used) */
#define B_USED(b, i) (AT(u8, (u32)(b) + 0x25F + 0x12 * (i)) & 1)
/* conditions (the move data's WP_SICK numbering): the state word of condition i, bits 0-2 its kind (0 off), 3-8 its
   length, 9-24 a parameter (Encore, charging: the move); its count of turn ends passed (measured, round 3 mapping).
   Sleep (2): its length is 2-4 and it skips that many turns minus one, then acts on the turn it wakes; its count goes
   up at each skipped turn, only in E_POKECON(0)'s copy, and survives a switch (measured) */
#define B_COND(b, i)       AT(u32, (u32)(b) + 0x3C + 8 * (i))
#define B_COND_ON(b, i)    (B_COND(b, i) & 7)
#define B_COND_COUNT(b, i) AT(u8, (u32)(b) + 0x1C0 + (i))
/* Aqua Ring (and Damp's water veil, the same message) is condition 36, kind 1 (measured with --dump, round 4) */
enum { C_CONFUSION = 6, C_NIGHTMARE = 9, C_TAUNT = 11, C_YAWN = 14, C_LEECH_SEED = 18, C_INGRAIN = 21, C_ENCORE = 23,
       C_PERISH = 20, C_CHARGE = 27, C_AQUA_RING = 36 };
/* Perish Song is condition 20, kind 2, length 4; its count reads 1, 2, 3 on the three turns after the song, and the
   Pokemon faints at the end of the turn it reads 3 (measured with factprobe --dump, round S3 unit C) */
#define PERISH_LAST 3
/* semi-invulnerable since the turn after its charge, until the move hits: 0x20 under water, 0x40 in the air, 0x80
   underground, 0x100 vanished (Phantom Force, Shadow Force) */
#define B_SEMI(b) (AT(u16, (u32)(b) + 0x2BA) & 0x1E0)
enum { SEMI_DIVE = 0x20, SEMI_FLY = 0x40, SEMI_DIG = 0x80 };
/* the substitute's HP, current only in the engine's other copy of the battle (E_POKECON(0)) */
#define B_SUB_HP(b) AT(u16, (u32)(b) + 0x3E6)

/* move data getter params (WAZADATA_GetParam 0x0201A274) */
enum { WP_TYPE = 0, WP_QUALITY = 1, WP_CLASS = 2, WP_POWER = 3, WP_ACC = 4, WP_PRIO = 6, WP_SICK = 9,
       WP_SICK_PER = 10, WP_RANK_TYPE1 = 14, WP_RANK_VAL1 = 17, WP_RANK_PER1 = 20, WP_CRIT = 23, WP_FLINCH = 24, WP_EFFECT = 25, WP_DRAIN = 26,
       WP_HEAL = 27, WP_TARGET = 28, WP_FLAG0 = 29 };
enum { Q_DAMAGE, Q_SICK, Q_EFFECT, Q_RECOVER, Q_DAMAGE_SICK, Q_EFFECT_SICK, Q_DAMAGE_EFFECT,
       Q_DAMAGE_EFFECT_USER, Q_DRAIN, Q_OHKO, Q_FIELD, Q_SIDE, Q_PUSHOUT, Q_OTHER };
enum { F_CONTACT, F_CHARGE, F_RECHARGE, F_PROTECT, F_MAGICCOAT, F_SNATCH, F_MIRROR, F_PUNCH, F_SOUND };
#define F_POWDER 28      /* powder and spore moves (flag params are WP_FLAG0 + bit; bit 28 is set on exactly those 7) */
#define F_CRIT 30        /* MoveInfo.flags only: it always lands a critical hit (crit stage 3 or more with its user's ability and item) */
#define TARGET_USER 7

/* engine functions (Thumb) */
#define E_POKECON(w)            CALL(0x02215170, void *, int)(w)
#define E_PARTY(pc, client)     CALL(0x02230934, void *, void *, int)(pc, client)
#define E_PARTY_COUNT(party)    (CALL(0x02215038, int, void *)(party) & 0xFF)
#define E_PARTY_MEMBER(party, i) CALL(0x022151A0, void *, void *, int)(party, i)
#define E_CLIENT_OF(id)         (CALL(0x022157D4, int, int)(id) & 0xFF)
#define E_ACTIVES(client)       (CALL(0x022287C8, int, int)(client) & 0xFF)
#define E_POS_OF(id)            (CALL(0x02228740, int, int)(id) & 0xFF)
#define E_POS_INDEX(pos)        (CALL(0x02228838, int, int)(pos) & 0xFF)
#define E_POKESICK(b)           CALL(0x02216C64, int, void *)(b)
#define E_FIGHTABLE(b)          CALL(0x02216548, int, void *)(b)
#define E_WAZA(move, param)     CALL(0x0201A274, int, int, int)(move, param)
/* E_WAZA's parts. E_WAZA keeps the last 4 move records in WAZA_CACHE, entries of 0x2C bytes (the move u16 at +0, its
   40-byte record at +4). A miss loads the record into the entry after the u8 at WAZA_LAST, and leaves WAZA_LAST there,
   with the NARC loader (0x02007424 on the move data, NARC 0x114), which opens the file and reads its header every time:
   140 k cycles (measured). E_NARC_OPEN opens the file once (NULL if the heap is full), E_NARC_READ reads one member into
   dest, 59 k cycles for a record (measured), and E_NARC_CLOSE frees it. E_WAZA_PARAM reads a record by words: keep it
   word aligned */
#define WAZA_NARC 0x114
#define E_NARC_OPEN(narc, heap) CALL(0x02007590, void *, int, int)(narc, heap)
#define E_NARC_READ(f, member, dest) CALL(0x02007694, void, void *, int, void *)(f, member, dest)
#define E_NARC_CLOSE(f)         CALL(0x02007614, void, void *)(f)
#define E_WAZA_PARAM(rec, param) CALL(0x0201A2E0, int, const void *, int)(rec, param)
#define WAZA_REC 40
#define WAZA_CACHE 0x021CFFE4u
#define WAZA_LAST 0x021CFFE0u
#define E_POKECON0()            CALL(0x022157A0, void *, void)()
#define E_UNSELECTABLE(b, move, pc, x) CALL(0x0222C304, int, void *, int, void *, void *)(b, move, pc, x)
#define E_TRAPPED(cw, b, o1, o2) CALL(0x0222C958, int, void *, void *, u8 *, u16 *)(cw, b, o1, o2)
#define E_SIM_DAMAGE(a, d, move) (CALL(0x02223390, int, int, int, int, int, int)(a, d, move, 1, 0) & 0xFFFF)
/* the damage core always rolls 85-100 with the battle RNG (0x022264AC(85, 100)); from this state the next
   LCG step (x 0x41C64E6D + 0x6073) is 0x000F0000, whose roll is 85 + 15 = 100 */
#define RNG_PRE_MAX 0xD52061A1u
#define RNG_AFTER_MAX 0x000F0000u
/* the battle's event handlers, a list of factors: next +4, flags +0x14, kind +0x18 (4 an item, 5 an ability). A
   simulation whose attacker is off the field puts its side's Pokemon on the field's item and ability factors to sleep
   (flag bit 25) to add the attacker's own, and never wakes them (0x022234DC); the turn's flow wakes every factor
   before the moves (0x022100FC) */
#define FACTORS 0x02252D40u
#define FCT_ASLEEP 0x02000000u
#define E_SET_NONE(p)           CALL(0x0220091C, void, void *)(p)
#define E_SET_FIGHT(p, move, pos, id) CALL(0x02200960, void, void *, int, int, int, int)(p, move, pos, 0, id)
#define E_SET_ITEM(p, item, id) CALL(0x02200A30, void, void *, int, int, int, int)(p, item, id, 0, id)
#define E_SET_CHANGE(p, posidx, partyidx) CALL(0x022009AC, void, void *, int, int)(p, posidx, partyidx)
#define E_OV11(p, st, arg)      CALL(OV11_ENTRY, int, void *, void *, int)(p, st, arg)
/* the battle heap, created before the battle and destroyed after it; overlay 11 allocates its own scratch there during
   its polls (0x021E64AA, freed before it returns) */
#define HEAP_BATTLE 5
#define E_ALLOC(heap, size)     CALL(0x0201B2AC, void *, u32, u32)(heap, size)     /* AllocFromHeap: NULL when full */
#define E_FREE(p)               CALL(0x0201B33C, void, void *)(p)                  /* FreeToHeap */
#define E_SWITCH_SLOT(ov)       CALL(0x02215914, void, int)(ov)    /* SwitchSlotOverlay: the battle slot's overlay, at main+0x26C */

#endif
