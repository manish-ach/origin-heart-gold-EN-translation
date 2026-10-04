# Chinese-source findings: v4.0.3 quest verification

2026-10-04. Findings only. No guide, generated docs, translation, decisions or production tools changed. Freshly loaded `work/rom/origin_v4.0.3_cn.nds`, SHA256 `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8`; all 966 event-script members match the existing documentation cache byte for byte. Fresh ARM9 disassembly and map/event bytes supplement the script checks. Scratch dumps and machine-readable facts are in ignored `work/build/source-verify-quests/`.

`file @offset` means a member of `a/0/1/2` and its byte offset. Dialogue annotations in dumps use current translated banks; opcode arguments and branches come from the Chinese ROM. This is binary/static verification, not a clean full-game replay. Script provenance cannot by itself establish emulator presentation, save-history effects or absence of indirect native code writes.

## Disposition register

| Finding | Result against v4.0.3 | Evidence / limits |
|---|---|---|
| K01 / REF02 — Lavender exchange | **Confirmed.** Repeatable Big Pearl → Heart Scale, not the reversed legacy location. | 772 script4 @296–391: HasItem89×1 @330; TakeItem89×1 @358; item93×1 @371–383. No one-time flag. Route12 file200 separately awards Big Pearl89 @366/429/492. Current item docs correct; guide connection remains useful. |
| K02 — allegedly missing fossil restoration | **Withdraw original omission and Pewter corroboration.** Current guide already explains correct restoration at Cinnabar. | Guide05:288 explicitly names side door, scientist, seven fossils and Lv20. Actual fossil commands occur only in file905; Pewter753 @517–535 is part of a photography routine ending in CameronPhoto @4280/4342. The earlier review mistook an external-message annotation for fossil interaction. Optional Mt.Moon cross-link is all that remains of the omission claim. See full trace below. |
| K03 — lava Egg | **Confirmed guide / rejected Togepi claim.** | 812 @4605 species252; @4613 GiveEgg[252,14] = Treecko. |
| K04 — Gloom-auction money | **Confirmed guide / rejected $100,000 requirement.** | 798 @558 HasEnoughMoneyImmediate[32780,65535]; no payment at this access gate. Later783 @3125/$50,000 check and @3146 deduction. The source's $100,000 advice is unnecessary. |
| K05 / GJ01 — romance fixes / home scenes | **Static PC invitation blocker confirmed; universal normal-play outcome remains qualified.** | Starter738 @3946/4080 sets106; no decoded ClearFlag106 in all966 files. 843 PC script1 when0x40B5=6 reaches @363 CheckFlag106 and @367 jumps to End4292. Separate map-trigger scene4 can select Cynthia via106; see expanded reachability below. This does not prove the commenter used the same build/save. |
| GJ02 — Falkner three vs four | **Confirmed current guide.** | 856 @971 count; @975/981 rejects5, @988/994 rejects6. Four is not rejected by this count gate; species restrictions still apply. No battle smoke test performed. |
| GJ03 — Morty 3v3 vs six | **Confirmed six-member gate and current trainer data.** | 918 @1055–1133 rejects counts1–5. @13687 TrainerBattle[31,31,0,0]. Fresh trainer31 has6 records: Gengar94, Dusclops356, Mismagius429 Lv80; Mimikyu778, Dhelmise781, Sinistcha1013 Lv1. Two equal trainer IDs alone do not prove which six enemies the double-battle engine displays. |
| GJ04 — Jasmine100 vs130 | **Reject old threshold; retain fixed-list caveat.** | 909 @461 dialogue says130; @796–832 rejects counts4–6; long PlayerHasSpecies refusal chain follows. Actual enforcement is enumerated species, not a live Defense-stat comparison. This pass verifies source/version mismatch, not every exception in the list. |
| GJ05 — Boot Camp14246 | **Confirmed.** | 881 first digit menu @2503–2559, subsequent checks @2575–2653 reject all except1; second rejects all except4 @2753–2837; third except2 @2931–3015; fourth except4 @3109–3193; fifth except6 in following block. Numerals are menu values0–7, not one-based menu positions. |
| GJ06 — trio Wednesday /31224 | **Both confirmed statically; numeric shortcut upgraded from lead.** | 935 clean quiz path @938–1386 permits zero-based choices2,0,1,1,3 = one-based31224. Answers5/Snorunt/2/14/Relaxed+Naive. Success @1404 clears649. Lake934 map-init needs0x40B2≥5 and0x4037=61993 @126/1749, then unhides completed-question encounters. ARM9 0x0203A580 fresh disassembly checks flag202, maps88/45 and weekday3 @0x0203A5B6 before calm-state setter. |
| GJ07 — legacy learned-HM checklist | **Existing script distinction supported; shared engine finding.** | Previously traced command GetPartySlotWithMove behavior and Surf/Fly/Flash separation belong to the common-mechanics verification. This quest pass introduces no new blanket 'all HMs identical' claim. |
| GJ08 — Murkrow coin / Greninja metadata | **Coin acquisition confirmed; episode-location inference rejected.** | 247 @1728 sets item223 (Amulet Coin), standard award follows. Return branch @1013 possession/@1034 TakeItem223. A video episode order supplies no ROM grant evidence; Ninja Scroll/form engine verification belongs to reference review. |
| V02 — Celadon colour/password clues | **Narrow corroboration retained.** | 172 @993 message51 provides bottom-to-top/right-to-left order; @1859 message57 lists red/orange/yellow/green/blue/purple. This verifies those clues; no fresh exhaustive weekday/hour password-table audit was performed. |
| V03 — fossil $5,000 | **Confirmed, including payment and item IDs.** | 133 @2149 check5000, @2175 deduction, @2183 item101 (Helix); @2216 check5000, @2242 deduction, @2250 item102 (Dome). No purchase-completed flag is set in those branches, supporting repeatability. |
| V05 — Victory Road progression fragment | **Corroborated at relevant gates, not an exhaustive qualifier audit.** | 110 @305/436/565/642/788 check Janine2F trainer flag1924 before reveal branches; guards @869/921 require1496; reveal @10157 sets1496. Password dialogue @1014/5049/5143 remains570819. The screenshot does not add a different route or password. |

## K02 correction: actual fossil restoration

File905 script14 starts @946. Map412's current map section is **Cinnabar Island**, despite its recycled vanilla Global Terminal identifier. Its event bank368 and current guide locate the fossil scientist in the room entered through the west-side door north of the Pokémon Center, separate from the disguised restaurant/Gym entrance.

There is **no badge or story flag gate inside the scientist's interaction**. It loads script overlay2 @954; if temporary/pending flag1 is set, @958–962 goes to the waiting message @1565. Otherwise nonzero pending species variable0x407F (16511) branches to collection @1578. Without a pending fossil it counts fossils @985. Selection maps an item to species with GetFossilPokemon @2738 or3079, removes exactly one @2744 or3127, then sets flag1 @1565. Collection requires party count not6 @1589–1599, gives the pending species at **Lv20** @2586 and clears variable0x407F @2604.

Overlay22 fossil table read by the ROM maps Old Amber103→Aerodactyl142, Helix101→Omanyte138, Dome102→Kabuto140, Root99→Lileep345, Claw100→Anorith347, Armor104→Shieldon410, Skull105→Cranidos408. No timer is read in this event routine. The exact engine lifetime/reset of flag1 was not newly audited, so do not promote “walk N steps” or “wait N minutes” as verified instructions. Current “come back later” wording is conservative; a return-to-map smoke test can sharpen it.

## K05 / GJ01: why the home-scene report does not disprove the PC blocker

Fresh map64 (Pallet player house2F) event bank61 binds the **PC background object at(6,3) to script1**; bed at(2,10) uses script3. All ten people on that map have talk-script0. Therefore the blocking script1 is an actual player-interaction path, not merely unused script data.

The map's conditional header is member618, raw `010100000000b5400800040000000000`: conditional map scene on variable0x40B5=8 invokes **script4**. These are distinct routes:

1. Mom-visit file736 sets0x40B5=6 at @849/1153/1463/1767. With starter flag106 still set, PC843 script1 checks badge1 and state6, then jumps @367 straight to End4292 before Mail or partner handling.
2. If a save already has a partner living downstairs and state≥7, downstairs842 scripts12–15 provide the rest-in-room menu (e.g. @957 state gate, @6462 Mail check, menu option1 at @6506). Those paths warp upstairs and set state8 at @7867/8131/8302/8473.
3. Map-trigger843 script4 checks106 at @287 and selects **Cynthia's scene** @1041 before partner-specific checks. Scene completion resets state7 @1668. Thus a save that reaches state7/8 by some other history can show the wrong partner even though the ordinary state6 PC invitation remains blocked.

All decoded writes to106 are sets:738@3946,738@4080,840@238. All decoded state8 writes are in842; all state7 writes are in843. No ordinary event-script escape from the state6 invitation block was found. Fresh ARM9 shows ordinary CheckFlag handling at0x020404D8 and ordinary flag addressing at0x0204F8E4: flag106 uses byte save-flags-block+0x2ED, mask4, without a special alias. A limited scan of ARM9 plus all overlays for immediate `movs r1,#106` near direct flag-check/set/clear calls found no candidate; **this is not a whole-program dataflow proof** and cannot rule out computed IDs, bulk writes, save import or memory corruption.

Accordingly retain the warning's “appears blocked” qualification. The sources cannot establish either a universal romance fix or a clean-v4.0.3 successful route. No emulator reproduction was performed; direct script traces should not be described as a clean romance playthrough. Neither code fixes nor a behavior-changing patch is proposed.

## What is genuinely still open

- Clean late-game female-player romance save, normal state6 PC interaction, and state7/8 provenance; compare untouched CN and English build under matching conditions.
- Morty's actual battle-engine roster selection from TrainerBattle[31,31], as opposed to the trainer table and count gate.
- Fossil pending flag1 reset on exiting/re-entering the room, if replacing conservative wording with an exact wait instruction.
- Exhaustive Gym species-list behavior and all dynamic Celadon-password combinations were not required by the archived discrepancies and are not claimed verified here.

The most consequential correction from this pass is to **our previous K02 review finding**, not to the current guide: it already documented fossil restoration correctly, and the alleged Pewter evidence was a photography script.
