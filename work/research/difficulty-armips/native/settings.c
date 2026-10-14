#include "settings.h"
uint32_t dg_settings_decode(uint16_t w) {
    return ((w >> 15) & 1u) | ((w >> 2) & 2u) | ((w >> 3) & 4u);
}
uint16_t dg_settings_merge(uint16_t w, uint32_t f) {
    if (f & ~DG_KNOWN_MASK) return w;
    return (uint16_t)((w & ~DG_DIFFICULTY_MASK) | ((f & 1u) << 15) |
                      ((f & 2u) << 2) | ((f & 4u) << 3));
}
static int identity(const struct DG_SettingsTxn *t, uintptr_t owner, uint32_t epoch) {
    return t && t->active && owner && epoch && t->owner == owner && t->epoch == epoch;
}
int dg_options_begin(const uint16_t *p, uintptr_t owner, uint32_t epoch,
                     struct DG_SettingsTxn *t) {
    if (!t || t->active || !p || ((uintptr_t)p & 1u) || !owner || !epoch)
        return DG_SETTINGS_INVALID;
    t->original_word = *(const volatile uint16_t *)p;
    t->original_flags = (uint8_t)dg_settings_decode(t->original_word);
    t->draft_flags = t->original_flags;
    t->options_identity = (uintptr_t)p;
    t->owner = owner;
    t->epoch = epoch;
    t->active = 1;
    return 1;
}
int dg_options_set_draft(struct DG_SettingsTxn *t, uintptr_t owner,
                         uint32_t epoch, uint32_t flags) {
    if (!identity(t, owner, epoch) || (flags & ~DG_KNOWN_MASK))
        return DG_SETTINGS_INVALID;
    t->draft_flags = flags;
    return 1;
}
int dg_options_apply(uint16_t *p, uintptr_t owner, uint32_t epoch,
                     struct DG_SettingsTxn *t) {
    if (!identity(t, owner, epoch) || !p || ((uintptr_t)p & 1u) ||
        t->options_identity != (uintptr_t)p || (t->draft_flags & ~DG_KNOWN_MASK))
        return DG_SETTINGS_INVALID;
    uint16_t live = *(const volatile uint16_t *)p;
    if ((live & DG_DIFFICULTY_MASK) != (t->original_word & DG_DIFFICULTY_MASK))
        return DG_SETTINGS_STALE;
    int changed = t->draft_flags != t->original_flags;
    if (changed) *(volatile uint16_t *)p = dg_settings_merge(live, t->draft_flags);
    dg_options_cancel(t);
    return changed;
}
void dg_options_cancel(struct DG_SettingsTxn *t) {
    if (!t) return;
    t->active = 0; t->owner = 0; t->epoch = 0; t->options_identity = 0;
    t->original_word = 0; t->original_flags = 0; t->draft_flags = 0;
}
uint32_t dg_ai_decode(uint32_t on, uint32_t key) {
    return !on ? DG_AI_OFF : key ? DG_AI_KEY : DG_AI_ALL;
}
uint32_t dg_ai_encode(uint32_t v) {
    return v == DG_AI_KEY ? 3u : v == DG_AI_ALL ? 1u : 0u;
}
