/* The host replay's data: one bench case at its first decision (both parties, the field, the setup's items, and the
   engine damage the DS run recorded), and what one decision did. */
#ifndef HOST_H
#define HOST_H

typedef struct {
    u8 id, level, status, toxic;            /* status S_*; toxic: bad poison */
    u16 species, hp, maxhp, ability, item;
    u16 stats[5];                           /* Atk Def SpA SpD Spe */
    u8 types[3], stages[7];
    u16 moves[4];
    u8 pp[4];
    u8 unselectable;                        /* bit i: the engine refuses move i (E_UNSELECTABLE) */
    u8 trapped;                             /* E_TRAPPED for this Pokemon */
} HostMon;

typedef struct { u8 a, d; u16 move, v; } HostDamage;

#define HOST_MAX_DMG 128
typedef struct {
    char id[80];
    u8 doubles, weather_raw, terrain, nparty[2];      /* terrain: TERRAIN_*, 0 none */
    u32 seed;
    u16 items[4];
    HostMon mon[2][6];                      /* [client][party slot]; client 0 the player, 1 the AI's trainer */
    int ndmg;
    HostDamage dmg[HOST_MAX_DMG];
} HostCase;

typedef struct {
    int sims, missing, ov11;
    int call[4];                            /* the setter the decision wrote: 'm' move, 's' switch, 'i' item, 'n' none */
    HostDamage stand_in[HOST_MAX_DMG];      /* the simulations the case lacked, as the stand-in answered them */
} HostStats;

extern HostStats host_stats;
/* the damage stand-in for simulations the case lacks (NULL: 0); damage.c sets it when built in */
extern int (*host_formula)(const HostCase *c, int a, int d, int move);

void host_map(void);
void host_build(const HostCase *c);
void *host_st(void);
const void *host_arena(void);           /* the DS address space from 0x01FF8000 */
unsigned long host_arena_size(void);
void *host_param(void);

/* ai_unit.c */
int adv_entry(void *param, void *st, int arg);
void host_ai_reset(void);
const void *host_debug(int side);
extern const void *const host_counted[];
extern const char *const host_counted_names[];
extern const int host_ncounted;

#endif
