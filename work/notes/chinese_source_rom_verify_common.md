# Chinese-source findings: common engine verification

2026-10-04. Findings only; no guide/reference/game changes. Primary input is untouched Chinese v4.0.3, CRC32 **59CBBDAA**, SHA-256 **4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8**. Scratch evidence is in ignored `work/build/source-verify-common/`.

## Provenance and comparison

Read the supplied Chinese `.delta` metadata with `xdelta3 printhdrs`, without applying/building a ROM. All **32,769** target-window Adler32 checksums match consecutive bytes of the local Chinese ROM; windows cover its full **536,870,912 bytes**. This establishes correspondence to the supplied patch, not an independent author signature. Results: `patch-target-check.json`, original metadata: `patch-all-headers.txt`.

The existing English WIP is `work/build/origin_hg_v4.0.3_en_wip.nds`, CRC32 **8CDE8229**, SHA-256 **caf987949ea7e208f8cae1c49c76b1cf3fd596338cafeb7270693116bb448b3b**. It is the existing local artifact, not a newly built release. Reviewed breeding, Pickup/restoration, and scripted field-move code ranges are byte-identical (`common-code-parity.json`). Whole overlay 1 is identical; overlay 14 differs only within `0224C88B–0224CA66`, outside these routines. The data report separately compares entire gameplay NARCs. No global claim that every runtime path is identical follows from this.

`work/rom/preview_v4.nds` has a different checksum (**28E4B93B**) and different overlays; its accompanying JSON describes patch preview reconstruction. It was identified, not treated as a second authoritative release. Full input hashes are in `rom-provenance.json`.

## COM-02 — EXP and EV sharing: confirmed, with fresh controlled replay

Overlay 14 `022157C0` is `movs r0,#1; bx lr`. The caller in the per-recipient EXP calculation (`022289EA`) therefore receives enabled unconditionally; it does not read an Options setting, held item, flag or input. This confirms the prior `exp_share_research.md` result and rejects the video description's native toggle claim.

A fresh DeSmuME replay loaded the existing isolated two-party test battle, **without a cheat or code patch**. The award hooks recorded participant **26 EXP**, benched **13 EXP**, and **1 EV each**. Final decoded party values were EXP532/519 versus fixture baseline506/506; HP EV2/2 versus1/1. Evidence: `runtime-exp.log`, `runtime_exp.py`, `latest.png`. The fixture is a controlled prior test state, not a natural fresh playthrough. Fainted members, eggs, doubles and all special battle modes were not exhausted. The existing earlier CN/EN test is supplementary evidence, not a new EN replay in this pass.

## COM-01 / GJ-07 — HM-free scripted paths: confirmed in code

Fresh ARM9 disassembly confirms script command handler `0204C8D4` reads its move argument but selects the Pokémon through overlay 1 `02205200`, calling `02053500`. That function iterates party slots and calls `02053354`, which tests HP selector `0xA3` and egg selector `0x4C`; it does not test moves or learnability. It returns the first healthy non-Egg slot. Preserve valid-party assumptions: the no-healthy-member tail calls an assertion and returns slot0, not a clean universal fallback.

Surf's water interaction checks badge index3 at overlay 1 `021E65EE–021E65F6`; the patched Waterfall eligibility path sets its move-availability bit unconditionally at `021E5C86`. Actual scripted badge gating remains separate. This strengthens the existing precise guide rather than the video's added move-compatibility requirement. Fly/Flash party-menu availability was not swept anew; do not generalize the obstacle handler to every menu. ROM code proves behavior, while the archived announcement supplies intent.

## COM-03 / COM-05 — Summary and battle-information controls: fresh runtime verification

`runtime_controls.py` used isolated original-CN summary and battle states. Screenshots were visually inspected.

- Summary stats/moves page: **L** opens IV/EV information. **R** alone did not open it in normal-button mode (`summary-L.png`, `summary-R.png`). Earlier L/B closing results remain in `in_game_shortcuts.md`.
- Battle command menu: **Y** opens the information panel; **B** closes it. In this fixture the first Y press activated button focus and the second opened the panel, so a first-press timing/focus caveat matters (`battle-before.png`, `battle-Y.png`, `battle-Y2.png`, `battle-B.png`).
- Touching the information button at bottom-screen coordinate **(220,15)** also opened it (`battle-touch.png`). Own ability and stage rows were visible. Every opposing-ability reveal condition, status row and battle mode was not tested.

The first sandboxed DeSmuME process aborted during startup; the same isolated harness completed outside the sandbox. An initial misnamed field fixture was discarded and replaced with the visually verified battle fixture. No failed/field screenshot is used as battle proof.

## COM-05 — Pickup: direct bag deposit and table confirmed

Overlay 14 routine around `0222BCD0–0222BDB2` checks non-Egg status (selector `0x4C`), ability **53**, then a 10-percent gate (`0222BD2A` → `022264C0`). On success it chooses from 22 weighted entries by `min((level−1)/10,9)`, with a 0–99 roll. Every level-band weight column sums to100.

At `0222BD6C–0222BD7E` it calls **Bag_AddItem `02076A08`**, quantity1, directly. It does not require an empty held-item slot in this inspected routine. The table and weights are preserved in `pickup-table.json`: item IDs at `0224E3AC`, weights at `0224E3D8`. The patch really has an altered table, rather than just a source description.

This confirms deposit destination and implemented selection logic statically. Full-bag handling, all battle eligibility callers, and displayed success messaging were not reproduced. The helper uses an RNG remainder, so nominal percentages are implementation thresholds rather than a proof of perfectly uniform statistical output.

## COM-05 — Held-item restoration: implemented, but not unconditional

Party synchronization `0222B910` calls `0222BA00`, which invokes reconciliation `0222BA58` per party member, comparing original and battle-result held items. The ordinary branch writes the original item back at `0222BB08–0222BB0E`, with exceptions involving item-transfer records and battle flags.

A separate classifier at `02225F6C` checks a 67-item table at `0224D58C`: IDs149–212 plus664–666 (the berry range and later berries). Those take the special branch at `0222BA94–0222BAD4`; absent the relevant transfer record it writes item0 rather than blindly restoring the original. Thus the author's word **“most”** matters. Do not promise all consumed berries/items are restored.

The restoration system is confirmed. A publishable exhaustive exception list and consumption/Knock Off/Thief matrix still require controlled battle cases. This report does not pretend the existence of the reconciliation routine proves every advertised scenario.

## COM-05 — Breeding claims: confirmed core changes, important qualifications

### Hatching

ARM9 `0206BDCC–0206BE1E` scans the party for ability **40 or49** (Magma Armor or Flame Body) and returns **8**, otherwise **1**. Caller `0206C060` uses that value to reduce egg-cycle counters. At `0206C0A6–0206C0B2`, a remaining counter at least8 loses8, but a smaller nonzero remainder loses only1. Zero is handled on a later check.

Therefore **eight-cycle decrement applies to both abilities**, not only Flame Body, and “exactly eight times fewer steps for every egg” is too strong. Multiple holders do not stack in this routine: it returns at the first matching ability. No full hatching run was performed.

### Destiny Knot

`0206B5A0` starts inheritance count at3. Held-item checks for either parent compare item **280** at `0206B5FC–0206B602`; a match sets count **5** at `0206B604`. Selection removes chosen stats from the available list, and the subsequent parent/IV transfer loops run to that count. The power-item-selected stat is accounted for in the same total, not five extra slots. This confirms the advertised five-stat inheritance in code, not a guarantee of five perfect IVs.

### Everstone

`0206B494` checks both parents for item **229**. With exactly one holder, it returns that parent without the usual 50-percent reject branch. With **two** holders, `0206B4CA–0206B4F6` randomly selects a parent and retains a second RNG rejection at threshold `0x7FFF`, returning−1 on rejection. `0206B510` then follows either random PID generation or a bounded nature-matching loop (up to2401 attempts).

Additionally, egg construction `0206BC48` checks the different-language/Masuda helper at `0206BC6A`; when not already shiny it can reroll PID without a nature recheck. Consequently the release's blanket “Everstone guarantees nature” should not be published without these exceptions being addressed by testing. Single-holder same-language intended inheritance is supported; two-holder and cross-language paths undermine an unconditional promise. No native breeding code was changed and no runtime egg matrix is claimed.

## ARCH-01 and non-ROM findings

The missing derived search excerpts are an archive-indexing issue, not a ROM behavior. Source review inspected the actual `index_archive.py` first-line-before-strip condition and preserved raw search blocks. Guide coverage/wording questions likewise require checking the text, not just the binary. No archive index, guide or docs were edited in this pass.

## Evidence boundaries

Code was freshly loaded from the local Chinese ROM and disassembled with Capstone; snippets and binary/code hashes are retained locally. A public pret file/tree was fetched as a navigation aid but did not establish these hack behaviors; every address and conclusion above comes from the supplied ROM. No game download or rebuilt ROM was needed. Runtime evidence is expressly limited to EXP/EV and control checks; static evidence is labelled as such. Chain/allocator/spawn/calendar/forms and quest details are in the companion reports.
