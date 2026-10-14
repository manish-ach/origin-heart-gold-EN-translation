#include "runtime.h"
#include "settings.h"
#include "caps.h"
#define ROOT_SLOT 0x02255BACu
/* These singleton objects are interior BSS, materialized as loader zeros.
 * Cold boot and native reset copy those zeros before any hooked overlay runs. */
static DG_GrowthSnapshot snapshot;
static uintptr_t setup_owner, save_owner;
static uint32_t generation, setup_flags;
#ifdef DG_RUNTIME_HOST_TEST
#define read32 dg_runtime_test_read32
#define read16 dg_runtime_test_read16
#define current_save dg_runtime_test_save
#define native_options dg_runtime_test_options
#define native_begin dg_runtime_test_begin
#define native_free dg_runtime_test_free
#else
static uint32_t read32(uintptr_t p) { return *(const volatile uint32_t *)p; }
static uint16_t read16(uintptr_t p) { return *(const volatile uint16_t *)p; }
#define current_save ((uintptr_t (*)(void))(uintptr_t)0x02001195u)
#define native_options ((uintptr_t (*)(uintptr_t))(uintptr_t)0x02029349u)
#define native_begin ((void (*)(void))(uintptr_t)0x02215D15u)
#define native_free ((uintptr_t (*)(void *))(uintptr_t)0x0201B33Du)
#endif
/* Main RAM below the advanced AI's resident code (0x023D4000..0x023DC000,
 * work/advanced-ai/docs/memory-layout.md), difficulty's own reservation and ARM7. */
uint32_t dg_runtime_ram(uintptr_t p, uint32_t size, uint32_t alignment) {
    return size <= 0x003D4000u && alignment && !(alignment & (alignment-1u)) &&
        !(p & (alignment-1u)) && p >= 0x02000000u && p <= 0x023D4000u-size;
}
uintptr_t dg_runtime_save(void) {
    uintptr_t p=current_save();
    return dg_runtime_ram(p,4,4)?p:0;
}
uint32_t dg_runtime_ordinary(uint32_t flags, uint32_t control) {
    /* Script WildBattle 0204352A..3A passes implicit arg5=1 (arg6 is form).
     * Its flags0 constructor 02050418 ORs 8 at 02050458 BEFORE overlay entry.
     * Native trace ctor LR02050433 confirms that path. This is not replay
     * bit10h or special control1. Only this proven flags/control pair is added;
     * do not mask 8 out of other modes. See runtime-classifier.md. */
    if (control == 8u) return flags == 0u;
    if (control != 0u) return 0;
    /* 0x801: script TrainerBattle with nonzero third operand (a story battle
     * the player may lose; the script has its own loss branch). Handler
     * 02048BAE..DA passes that byte as constructor stack arg0; 02050798..A2
     * ORs 0x800 only on the single-trainer path, so 0x801 is the only value
     * it can produce. Exact value; 0x800 is not masked out of other modes. */
    switch (flags) {
    case 0: case 1: case 3: case 0x13: case 0x4A: case 0x4B: case 0x100:
    case 0x801:
        return 1;
    default: return 0;
    }
}
void dg_runtime_invalidate(void) {
    snapshot.epoch=0; snapshot.allowed=0; snapshot.root=0;
    snapshot.flags=0; snapshot.cap_level=0;
    setup_owner=0; save_owner=0; setup_flags=0;
    ++generation;
    if (!generation) ++generation;
}
void dg_battle_begin(void) {
    uintptr_t root,setup,save,options,copy;
    uint32_t cap;
    native_begin(); /* Displaced call FIRST, exactly once. */
    dg_runtime_invalidate();
    root=read32(ROOT_SLOT);
    if (!dg_runtime_ram(root,0x274u,4)) return;
    setup=read32(root+0x10u);
    if (!dg_runtime_ram(setup,0x1D4u,4) ||
        !dg_runtime_ordinary(read32(setup),read32(setup+0x18Cu))) return;
    save=dg_runtime_save();
    /* Ordinary constructor 02051250..52 binds SaveData at setup+1C0.
     * A copied replay or foreign setup is not sufficient ownership. */
    if (!save || read32(setup+0x1C0u)!=save) return;
    options=native_options(save);
    copy=read32(setup+0x130u);
    if (!dg_runtime_ram(options,2,2) || !dg_runtime_ram(copy,2,2)) return;
    if ((read16(options)^read16(copy)) & DG_DIFFICULTY_MASK) return;
    cap=dg_cap_for_save(save);
    if (cap<1 || cap>100 || dg_runtime_save()!=save) return;
    snapshot.flags=dg_settings_decode(read16(copy));
    snapshot.cap_level=cap; snapshot.root=root; snapshot.allowed=1;
    setup_owner=setup; save_owner=save; setup_flags=read32(setup);
    snapshot.epoch=generation; /* Publish last, before returning to engine init. */
}
uintptr_t dg_battle_root_free(void *root) {
    dg_runtime_invalidate(); /* Native root slot remains stale after free. */
    return native_free(root);
}
const DG_GrowthSnapshot *dg_growth_snapshot(void) {
    if (!snapshot.epoch || snapshot.epoch!=generation) return 0;
    /* Control classification is frozen at entry too: native code may update
     * setup+18C during battle. Only a NEW entry may classify a replay.
     * Never refresh settings/cap midway through a battle. Losing ownership
     * permanently invalidates this generation until the next begin seam. */
    if (dg_runtime_save()!=save_owner || read32(ROOT_SLOT)!=snapshot.root ||
        !dg_runtime_ram(snapshot.root,0x274u,4) ||
        read32(snapshot.root+0x10u)!=setup_owner ||
        !dg_runtime_ram(setup_owner,0x1D4u,4) ||
        read32(setup_owner+0x1C0u)!=save_owner ||
        read32(setup_owner)!=setup_flags) {
        dg_runtime_invalidate(); return 0;
    }
    return &snapshot;
}
