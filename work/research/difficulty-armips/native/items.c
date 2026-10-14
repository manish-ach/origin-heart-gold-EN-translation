#include "items.h"
#include "policy.h"

#define ROOT_SLOT ((uintptr_t)0x02255BACu)
#define RAM_START ((uintptr_t)0x02000000u)
/* Exclude the advanced AI's resident code (0x023D4000..0x023DC000), the
 * integration-owned resident reservation and ARM7 memory. */
#define RAM_END ((uintptr_t)0x023D4000u)

#ifdef DG_ITEMS_HOST_TEST
#define read8 dg_items_test_read8
#define read16 dg_items_test_read16
#define read32 dg_items_test_read32
#define write8 dg_items_test_write8
#define write16 dg_items_test_write16
#define native_attr dg_items_test_native_attr
#define native_count dg_items_test_native_count
#define native_accept dg_items_test_native_accept
#else
static uint8_t read8(uintptr_t p) { return *(const volatile uint8_t *)p; }
static uint16_t read16(uintptr_t p) { return *(const volatile uint16_t *)p; }
static uint32_t read32(uintptr_t p) { return *(const volatile uint32_t *)p; }
static void write8(uintptr_t p, uint8_t v) { *(volatile uint8_t *)p = v; }
static void write16(uintptr_t p, uint16_t v) { *(volatile uint16_t *)p = v; }
#define native_attr \
    ((uint32_t (*)(uint32_t, uint32_t, uint32_t))(uintptr_t)0x02076411u)
#define native_count \
    ((uint32_t (*)(void *, uint32_t, uint32_t, uint32_t))(uintptr_t)0x02076B21u)
#define native_accept ((uint32_t (*)(void *))(uintptr_t)0x021EB299u)
#endif

static uint32_t ram_words(uintptr_t p, uint32_t bytes)
{
    return (p & 3u) == 0u && p >= RAM_START && p <= RAM_END - bytes;
}

static uint32_t valid_item(uint32_t item)
{
    /* Archive has members 0..790; zero is the native cancel/empty sentinel. */
    return item != 0u && item <= 790u;
}

static uintptr_t ui_args(void *ui)
{
    uintptr_t p = (uintptr_t)ui;
    uintptr_t args;
    if (!ram_words(p, 4u)) return 0;
    args = read32(p);
    return ram_words(args, 0x30u) ? args : 0;
}

static const DG_GrowthSnapshot *context(uintptr_t args)
{
    const DG_GrowthSnapshot *s;
    uintptr_t root, setup, bag, trainer_info;
    uint32_t flags;
    if (!ram_words(args, 0x30u) || read32(args + 0xCu) != 0u ||
        read32(args + 0x10u) != 0u) return 0;
    s = dg_growth_snapshot();
    if (s == 0 || s->epoch == 0u || s->allowed == 0u ||
        (s->flags & ~DG_KNOWN_MASK) != 0u) return 0;
    root = read32(ROOT_SLOT);
    if (root != s->root || !ram_words(root, 0x14u)) return 0;
    setup = read32(root + 0x10u);
    if (!ram_words(setup, 0x10Cu)) return 0;
    flags = read32(setup);
    /* These are additional observed vetoes, NOT an ordinary-mode allowlist. */
    if ((flags & 1u) == 0u || (flags & 0x480u) != 0u) return 0;
    /* 02202A50..56 computes 0x42 << 2 = 0x108 (NOT 0x168).
     * This is the separately allocated battle Bag, copied from SaveData entry3;
     * owner0 consumption uses the same slot at 02215A66..6E. Args+0 is the
     * owner's 32-byte TrainerInfo at setup+F8, not a Pokemon party (setup+4).
     * See research/items-binding-pins.json for creator/copy/accessor guards.
     */
    bag = read32(setup + 0x108u);
    trainer_info = read32(setup + 0xF8u);
    if (!ram_words(bag, 0x864u) || !ram_words(trainer_info, 0x20u) ||
        read32(args + 4u) != bag || read32(args) != trainer_info) return 0;
    return s;
}

static uint32_t addition(uint32_t item)
{
    /* Exactly the twenty CN-zero ordinary medicines certified in items.md.
     * Do not infer battle usability from a pocket or replace archive records.
     */
    switch (item) {
    case 18: case 19: case 20: case 21: case 22:
    case 27: case 42: case 54: return 8u;
    case 23: return 12u;
    case 24: case 25: case 28: case 29:
    case 34: case 35: case 37: return 4u;
    case 38: case 39: case 40: case 41: return 16u;
    default: return 0u;
    }
}

static uint32_t mask(uint32_t item, uint32_t original,
                     const DG_GrowthSnapshot *s)
{
    return dg_item_battle_mask(item, original, original | addition(item),
                               s != 0, s != 0 && (s->flags & DG_ITEMS_ALL) != 0u);
}

static uint32_t denied(uintptr_t args, uint32_t item, uint32_t heap)
{
    const DG_GrowthSnapshot *s;
    /* Bounds precede ANY native metadata lookup, even for stale sentinels. */
    if (!valid_item(item)) return 1u;
    s = context(args);
    if (s == 0) return 0u;
    return mask(item, native_attr(item, 13u, heap), s) == 0u;
}

static void cancel(uintptr_t args)
{
    write16(args + 0x18u, 0u);
    write8(args + 0x1Au, 4u);
}

uint32_t dg_bag_item_attr(uint32_t item, uint32_t attr, uint32_t heap, void *ui)
{
    uint32_t original;
    if (!valid_item(item)) return 0u;
    original = native_attr(item, attr, heap);
    if (attr != 13u) return original;
    return mask(item, original, context(ui_args(ui)));
}

uint32_t dg_bag_remembered(void *bag, uint32_t item, uint32_t quantity,
                           uint32_t heap, void *ui)
{
    uint32_t original;
    uintptr_t args;
    /* Native inventory lookup may itself request metadata: validate first. */
    if (!valid_item(item)) return 0u;
    original = native_count(bag, item, quantity, heap);
    if (original == 0u) return original;
    args = ui_args(ui);
    if (args == 0 || read32(args + 4u) != (uintptr_t)bag) return original;
    return denied(args, item, heap) ? 0u : original;
}

uint32_t dg_bag_accept(void *ui)
{
    uintptr_t args = ui_args(ui);
    if (args != 0 && denied(args, read16(args + 0x18u), read32(args + 8u))) {
        cancel(args);
        return 13u; /* Native fade/close state, NOT Boolean false/state zero. */
    }
    return native_accept(ui);
}

uint32_t dg_bag_commit_item(void *bag_args)
{
    uintptr_t args = (uintptr_t)bag_args;
    uint32_t item;
    /* Native hook already dereferences args: it retains that precondition. */
    item = read16(args + 0x18u);
    if (ram_words(args, 0x30u) && denied(args, item, read32(args + 8u))) {
        cancel(args);
        return 0u;
    }
    return item;
}

uint32_t dg_bag_commit_target(void *controller, void *party_args)
{
    uintptr_t ctrl = (uintptr_t)controller;
    uintptr_t args;
    uint32_t target = read8((uintptr_t)party_args + 0xDu);
    if (target == 6u || !ram_words(ctrl, 0x5CCu)) return target;
    args = read32(ctrl + 0x5C8u);
    /* Controller and Bag ownership must agree. Never touch the other slot. */
    if (ram_words(args, 0x30u) && read8(ctrl + 2u) == read32(args + 0xCu) &&
        denied(args, read16(args + 0x18u), read32(args + 8u))) {
        cancel(args);
        return 6u;
    }
    return target;
}

static uint32_t local_mon(uintptr_t root, uintptr_t mon)
{
    uint32_t id;
    if (!ram_words(mon, 0x20u)) return 0u;
    id = read8(mon + 0x14u);
    /* CN owner0 is IDs1..6, including bench and both local doubles actors.
     * Resolver identity is required; a plausible ID alone is not ownership. */
    return id >= 1u && id <= 6u &&
           read32(root + 0x1D0u + 4u * id) == mon;
}

uint32_t dg_bag_effect_attr(uint32_t item, uint32_t attr, uint32_t heap,
                            void *actor, void *target)
{
    const DG_GrowthSnapshot *s;
    uintptr_t root, setup;
    uint32_t original, flags;
    if (!valid_item(item)) return 0u;
    original = native_attr(item, attr, heap);
    if (original == 0u || attr != 38u ||
        (item != 28u && item != 29u && item != 37u)) return original;
    s = dg_growth_snapshot();
    if (s == 0 || s->epoch == 0u || s->allowed == 0u ||
        (s->flags & ~DG_KNOWN_MASK) != 0u ||
        (s->flags & DG_ITEMS_ALL) == 0u) return original;
    root = read32(ROOT_SLOT);
    if (root != s->root || !ram_words(root, 0x1ECu)) return original;
    setup = read32(root + 0x10u);
    if (!ram_words(setup, 0x10Cu)) return original;
    flags = read32(setup);
    if ((flags & 1u) == 0u || (flags & 0x480u) != 0u ||
        !local_mon(root, (uintptr_t)actor) ||
        !local_mon(root, (uintptr_t)target)) return original;
    /* ONLY 022218C0's item-effect loop: attr23 already dispatched revival.
     * These three newly enabled records also contain attr38, whose later
     * ordinary-heal callback would heal again (even a full revive must not
     * queue a redundant clipped heal). Keep revival/events/consumption intact.
     * No global getter/effect change, HP write or pending-event state.
     */
    return 0u;
}
