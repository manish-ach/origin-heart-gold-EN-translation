# Chinese-source findings checked against the v4.0.3 ROMs

2026-10-04. **All 33 labelled findings from the source review were revisited. They are not all confirmed bugs or fully reproduced gameplay scenarios.** This report separates fresh binary verification, controlled emulator checks, overturned review claims, and remaining uncertainty. Guides/reference pages, translation banks, production tools and ROMs were not changed.

## Inputs and strength of evidence

- Untouched Chinese: `work/rom/origin_v4.0.3_cn.nds`, CRC32 **59CBBDAA**, SHA-256 `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8`. Its entire 536,870,912-byte contents match all **32,769 target-window checksums** in the supplied Chinese 4.0.3 delta. No ROM rebuild or download was needed.
- Existing English WIP: `work/build/origin_hg_v4.0.3_en_wip.nds`, CRC32 **8CDE8229**, SHA-256 `caf987949ea7e208f8cae1c49c76b1cf3fd596338cafeb7270693116bb448b3b`. Fresh comparison found all members identical in personal, items, moves, encounters, scripts, trainer headers and trainer parties. Specifically examined engine ranges also match. This identifies the actual local artifact reviewed, not every English release.
- `preview_v4.nds` is a different patch-preview artifact, not an independent authoritative 4.0.3 release. It was not used as gameplay authority.
- Four bounded subagent sections and coordinator checks used fresh ROM reads/disassembly. **Fresh emulator replay** covered automatic EXP/EV awards and summary/battle-information controls. Most other results are **static code/data verification**. A clean whole-game replay was not performed.

Raw evidence and isolated harnesses are ignored under `work/build/source-verify-{common,quests,data,mechanics}/`. The reports below retain precise offsets, conditions and limits without distributing game data.

## Material results and corrections to our earlier review

1. **Withdraw K02's fossil-restoration omission.** Chapter 5 already documents the correct Cinnabar restoration room. The prior reviewer mistook a Pewter photography routine for restoration. A Mt. Moon cross-link would be optional; a missing walkthrough is not a real defect.
2. **Lavender trade remains confirmed.** One Big Pearl gives one Heart Scale, repeatably. This is the useful guide omission; the old article reversed the locations.
3. **Chain labels disagree with the implementation.** Actual completed-count bands are **0–5, 6–9, 10–19, 20+**. Chain identity includes form; a different-species/form shiny initializes a new chain at count 1 instead of leaving zero. Static source labels and blanket reset advice must not be copied as exact rules. The visible-shiny record is explicitly zeroed by the boot initialization loop, and its sound cue and nearby respawn-coordinate logic were also found.
4. **Tool availability is implemented outside event-script grants.** Chain Logger has an initialization grant; EV Allocator is ensured during post-battle synchronization. “No extracted script source” cannot mean “not in the game.” Allocator redistributes existing EVs and requires preserving each member's total.
5. **Mother has three traced charm rewards, not four.** Catching/EXP/Shiny at savings thresholds 30,000/40,000/50,000, each costing 3,000. Oval Charm is absent from both inspected reward paths; this is not proof of global unavailability.
6. **Native calendar encounters are real and omitted from the static tables.** Eight date/map/form records were decoded. Their existence is not universal capture proof: Lake of Rage's Volcanion row has zero land rate, and Diancie's raw form 4 needs runtime resolution. Exact configured dates and caveats are in the calendar report.
7. **Forms and typings are confirmed.** Charizardite plus Timid/Modest selects Mega Y; other natures Mega X. Steel Armor transforms Mewtwo; Ninja Scroll transforms Greninja. Both **Servine and Serperior are Grass/Dragon**, and Staraptor is Fighting/Flying.
8. **Several old tips fail the current binary.** Treecko Egg, current Gym count gates, auction amounts, Metal Claw power 60 and its paid tutor path remain supported. Route 31 radio selection reads Whismur/Linoone; Roselia's normal held item is Poison Barb, not Shiny Stone.
9. **Core battle/training changes are verified with limits.** Fresh battle replay awarded 26 EXP to the participant, 13 to the benched member, and 1 EV each. No native sharing toggle is read. Pickup calls the bag adder directly. Held-item restoration has exception branches. Hatching uses an 8-cycle decrement for both Flame Body and Magma Armor, with a slower final remainder; Everstone's dual-holder and cross-language paths prevent an unconditional guarantee.
10. **Romance remains a qualified issue.** The ordinary invitation PC path is statically blocked by starter flag 106. A separate map scene in pre-existing state 8 explains how a wrong-partner home scene can coexist with that blocker. No clean successful state 6→7 route was found or reproduced, and no universal engine-state impossibility is claimed.

## Full disposition ledger

“Verified” below refers to the stated table/branch/claim, not every downstream runtime condition. “Partial” means the evidence resolves part of the finding while the companion report retains explicit open checks.

| Prior ID | Disposition | Evidence report / result |
|---|---|---|
| K01 | Verified | Quest: repeatable Lavender trade; guide omission retained. |
| K02 | **Overturned** | Quest: Cinnabar restoration already documented; Pewter evidence was photography. |
| K03 | Verified rejection | Quest: GiveEgg species 252, Treecko. |
| K04 | Verified rejection | Quest:65,535 access check and50,000 payment, not100,000. |
| K05 | Partial | Quest romance paths; broad release “fixes” cannot remove warnings. |
| GJ-01 | Partial | Quest: actual PC/map-trigger bindings, state 7/8 and flag 106 traced; clean playthrough unresolved. |
| GJ-02 | Verified | Quest: Falkner count gate rejects 5/6, not 4. |
| GJ-03 | Verified data; runtime limited | Quest: six-member gate and trainer 31 six records; duplicate-trainer battle presentation not replayed. |
| GJ-04 | Verified | Quest:130 source rule and fixed species-list enforcement; old 100 rule rejected. |
| GJ-05 | Verified | Quest: password 14246 checks. |
| GJ-06 | Verified | Quest: Wednesday engine gate and current quiz shortcut 31224. |
| GJ-07 | Verified handler; menu limits | Common: scripted field selection ignores learned move/compatibility; not a universal party-menu claim. |
| GJ-08 | Verified existing coverage | Quest: Murkrow coin routes; data: Ninja Scroll form hook. Episode ordering does not prove a new grant location. |
| REF-01 | Verified classification problem | Data/mechanics: automatic grants and three mother charms. No proof every absent-source item is obtainable. |
| REF-02 | Verified rejection | Quest: old article reverses exchanges. |
| REF-03 | Rejected normal-source claims; bounded residual | Data: Life Orb documented gift and unused ball template; Roselia normal held-item path rejects Shiny Stone advice. Safari-specific completeness limits retained. |
| REF-04 | Verified | Data: active held-item form handlers and dispatch; generated source summaries omit the mechanism. |
| REF-05 | Verified and expanded | Data: Staraptor/Serperior match author; Servine independently resolved from ROM. |
| REF-06 | Verified radio handler | Data: Route 31 Hoenn radio reads actual Whismur/Linoone entries; no Ralts substitution in that path. |
| REF-07 | Verified missing native coverage | Mechanics/calendar: visible spawns and date-table replacement are separate from static encounter output. |
| REF-08 | Verified rejection | Data: Metal Claw60 power; Charmander takes the paid Level Ball path. |
| REF-09 | Partially verified scope | Common: automatic EV sharing confirmed. No author/video statement validates every trainer team or future change. |
| V01 | Verified naming conflict | Data: reward IDs distinguish Iapapa/Lum; source infographic is not correction authority. Berry mechanics have their own scope below. |
| V02 | Verified clues | Quest: colour/order clues; all dynamic password combinations not replayed. |
| V03 | Verified | Quest: fossil 5,000 prices and menu. |
| V04 | Verified | Data: engine period table 04–10/10–20/20–04. |
| V05 | Partial corroboration | Quest: qualifier gates and reveal flags; screenshot is incomplete, not whole-route proof. |
| COM-01 | Verified behavior; intent external | Common: first healthy non-Egg for scripted obstacles; source release establishes design intent. |
| COM-02 | Verified + fresh runtime | Common: unconditional sharing and26/13 EXP +1 EV each; no native toggle. |
| COM-03 | Verified core, acquisition timing limited | Mechanics/common: tools, controls, chain bands/reset, EV redistribution; every acquisition/UI sequence not played. |
| COM-04 | Verified core, persistence limits | Mechanics/calendar: six slots, retention record, native dates; exact compound odds and every spawn condition remain bounded. |
| COM-05 | Mixed verified/partial | Common: Pickup, selective restoration, breeding code, fresh battle-info controls; full exception matrices and opponent-ability reveals remain untested. |
| ARCH-01 | Verified non-ROM defect | Common: original announcement exists in raw  search-0, absent from derived excerpt file; indexing cause retained. |

## Detailed reports

- [Quest and progression verification](chinese_source_rom_verify_quests.md): trade, fossils, Gym gates, romance, passwords and weekdays.
- [Data and forms verification](chinese_source_rom_verify_data.md): raw tables, active form hooks, radio, items, tutoring, types and berry evidence.
- [Chains, grants and visible encounters](chinese_source_rom_verify_mechanics.md): corrected chain bands, reset branches, mother rewards, allocator and retention.
- [Calendar table verification](chinese_source_rom_verify_calendar.md): all eight records with exact map IDs, periods and availability caveats. Coordinator also confirmed loader `0203AD24–0203ADAC`, table `020F6A64–020F6AA4` and normal caller bytes match the English WIP (`calendar-code-parity.json`).
- [Common mechanics and controlled runtime checks](chinese_source_rom_verify_common.md): ROM provenance, EXP/EV, HM handler, controls, Pickup/restoration and breeding exceptions.

## Remaining verification boundaries

The highest-value remaining **runtime** cases are a clean late-game romance state, chain-boundary/shiny-form catches, retained shiny re-entry/reset behavior, unusual calendar forms, Morty's actual battle roster, mother delivery and first tool acquisition screens, plus breeding/restoration exception matrices. Static verification provides strong evidence for implementation; it does not replace those play scenarios.

Do not convert these remaining questions into confirmed bugs or silently repair the Chinese behavior. No guide edit, code fix, decision-register change, download of game material, or release action was performed. The previous source-review report remains historical; this report explicitly supersedes its K02 conclusion and its unresolved chain/Servine/calendar leads.

Final integrity comparison: **all 32 baseline Markdown files under guide/ and work/docs/ remain byte-identical**, with no added/removed Markdown files in those directories. Findings reports and ignored scratch evidence are the only outputs of this task.
