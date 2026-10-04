# Chinese-source findings: fresh v4.0.3 binary verification, data and forms

2026-10-04. Findings only. No guides, reference pages, translation banks, production tools or ROMs changed. This is static binary verification, not a claim of emulator playthrough coverage.

## Input and reproducibility

Untouched input: `work/rom/origin_v4.0.3_cn.nds`, SHA-256 `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8`.

Loaded directly with ndspy; regenerated an isolated cache at `work/build/source-verify-data/fresh.pkl`, not the existing documentation cache. Used the established record layouts in `work/tools/docs/romdata.py`; decoded Thumb engine functions independently with Capstone and manually checked their literals/branches. Scratch `raw.json`, `disassembly.txt`, `script748.txt`, `script854.txt`, and `en_comparison.json` retain the extracted evidence. All addresses below are loaded RAM addresses; script offsets are decimal offsets within their NARC member.

Fresh comparison with the existing `work/build/origin_hg_v4.0.3_en_wip.nds` found **every member identical** in personal (1,441), item (791), moves (921), encounters (149), scripts (966), trainer headers (1,024), and trainer parties (1,024). The form routines `02070E74–02070F73`, time routines `02014430–02014467`, and time table `020F2A94–020F2AAB` are identical too. This verifies these data/logic regions, not all behavior of either ROM or any other downloadable patch.

## Finding dispositions

### REF-01 — confirmed automatic Chain Logger grant; absence classification is unsound

Overlay 37 routine `021E4C48` obtains the save's bag via `02076E28`; at `021E4C6C` it constructs item 744 (`0xBA << 2`), sets quantity 1, and calls the bag-add routine `02076A08` at `021E4C74`. This is an engine grant outside map-script source extraction. The routine is in initialization code and confirms real grant logic, rather than merely an unused item description. Fresh-start end-to-end delivery was not emulated here. EV Allocator and mother charm grants are covered by the separate mechanics verification.

### REF-02 — exchanges delegated to quest verification

See `chinese_source_rom_verify_quests.md` for fresh script confirmation of Lavender/Route 12. This report does not count the legacy article as evidence against the current binary.

### REF-03 — legacy Life Orb ball and Roselia Shiny Stone advice not established

**Life Orb:** map-script member 233 at 1974 sets gift item 270, quantity 1 at 1980, and invokes reward standard script 2033 at 1986. This confirms the documented Route 32 Pokémon Center gift. Standard item-ball member 141 has a Life Orb entry at 1566 (entry index 27 / standard script 7027), but no parsed map object in the current map table uses script 7027 and no decoded script invokes it with CallStd. An unused ball-template entry is not evidence of an obtainable Cerulean ball. The old location/starter exception remains unsupported; do not add it.

**Roselia:** personal member 315 has held-item fields at offsets 12 and 14 equal to **0 and 245 (Poison Barb)**. Shiny Stone is **107**, not 245. Thus the default species-held-item data does not support the claimed Shiny Stone route. Safari object/day encounter selection and any Safari-specific held-item override were not fully traced; the object/day requirements remain unresolved, and this does not prove impossibility through a separate custom routine.

### REF-04 — confirmed held-item form routines and species dispatch

These are runtime form setters, not evolution-table entries:

| Base | Engine evidence | Result |
|---|---|---|
| Charizard 6 | `02070E74`: held-item selector 6 compared with literal 325 at `02070EC8`; nature getter `0206F1A0`, comparisons 10 and 15 at `02070EA4/EA8`; setter selector `0x70` at `02070EB2` | Holding Charizardite: Timid (10) or Modest (15) → form 2 / personal 1028 (Mega Y); other natures → form 1 / personal 1027 (Mega X). No stone → form 0. |
| Mewtwo 150 | `02070ED4`: held item compared with `0x72` (114), form written through `0206E0A0` | Steel Armor → form 3 / personal 1440; otherwise 0. |
| Greninja 658 | `02070F20`: held item compared with literal 761 at `02070F54`, form written through `0206E0A0` | Ninja Scroll → form 1 / personal 1194; otherwise 0. |

Species/form/personal mappings were freshly read from the arm9 table at `020FEDC0`. Overlay 85 explicitly dispatches species 6/150/658 in `021E4A12–021E4A72` to the Charizard trampoline `02070ECC`, Mewtwo wrapper `02070F04`, and Greninja wrapper `02070F58`. The Charizard trampoline's literal is `02070E75`, entering the routine above. This rules out merely orphaned setter code. Full animation/timing, every alternate invocation, and interaction with other form systems were not emulated.

### REF-05 — confirmed all three typings, including Servine

Personal NARC `a/0/0/2`, offsets 6–7:

| Member | Bytes | Current typing |
|---|---|---|
| 398 Staraptor | `01 02` | Fighting/Flying |
| 496 Servine | `0c 10` | Grass/Dragon |
| 497 Serperior | `0c 10` | Grass/Dragon |

Servine is no longer unresolved as a **current-ROM value**. The author excerpt still mentions only Serperior, so it does not prove when or why Servine changed. No current type correction is warranted.

### REF-06 — radio data confirms current table, not Ralts comment

Route 31's map metadata selects encounter member 4. Its Hoenn slots at `0x5C` are bytes `25 01 08 01`, species **293 Whismur / 264 Linoone**; Sinnoh slots at `0x60` are `a2 01 8f 01`. Ralts 280 is absent from the Hoenn pair. This is fresh verification of the published table. Custom radio availability/replacement hooks were not comprehensively traced, so retain the existing runtime qualification rather than declaring every possible radio state tested.

### REF-07 — scope caveat remains; engine systems covered separately

Encounter tables are identical in Chinese and English WIP. Their bytes alone do not establish that overworld/calendar generation uses identical probabilities. See the mechanics/root verification for engine results. Do not transform a source-coverage limitation into a numerical table correction.

### REF-08 — 60-power Metal Claw confirmed; free Charmander lesson rejected

Move member **232** in `extra/new_move_data.narc` has type 8, physical category 1, power **60** at offset 3, accuracy 100, PP 35 and priority 0. The legacy 50-power number is stale.

Pewter script member **748**, tutor entry **888**, takes the Yes branch at 911 to **2346**, which requires one **Level Ball 493** before party selection. Species 4/5/6 at **4702/4715/4728** merely join the compatibility whitelist. Both successful paths charge the same ball: new move slot sets move 232 at **5875** then TakeItem 493 at **5922**; replacement sets move 232 at **6041**, joins **6156**, and takes item 493 at **6165**. No starter exemption appears in the reachable tutor path. Do not document a free Charmander lesson.

### REF-09 — no external trainer specification to correct against

All trainer header/party members are identical across the current CN/EN inputs. The author's generic trainer redesign/EV statements and future-change comments supply no exact counterexample. This confirms translation parity, not independent accuracy of every generated EV field. No team replacement follows from this finding.

## Screenshot findings

### V01 — current berry reward IDs confirmed; infographic naming rejected

Violet script member **854** grants Yellow's last berry **163 Iapapa** at **3571** then consumes Yellow Shard 74 at **3587**. Green grants **157 Lum** at **3719** then consumes Green Shard 75 at **3751**. Blue grants **160 Wiki** at **3407**. The same mapping is independently present in Pewter member 748 at 3973/4121/3809 respectively. The four-colour listing in the guide is correct.

Fresh item records distinguish Iapapa and Lum: item 163 hold-effect byte 2 = **18**, parameter byte 3 = **8**; Wiki 160 effect **15**, parameter **8**; Lum 157 effect **12**, and its medicine status bits differ. This supports rejecting the infographic's assertion that Iapapa is Lum. It does **not** by itself establish the held-effect dispatch's activation threshold or final healing amount. The claimed Wiki below-quarter/one-eighth mechanics remain a battle-code/runtime lead; do not promote the parameter 8 into a tested formula.

### V02, V03, V05 — quest-scoped visual claims

Celadon colour/order clues, fossil prices and Victory Road progression are assigned to the quest report. Their old screenshots remain supplementary evidence, not proof of a current ROM version.

### V04 — time boundaries confirmed in engine

`02014430` indexes the 24-byte hour table at **020F2A94**. Values are 4 for hours 0–3, 0 for 4–9, 1 for 10–16, 2 for 17–19, and 3 for 20–23. `02014448` folds 0 → morning, 1/2 → day, remaining values → night. Thus **04:00–09:59**, **10:00–19:59**, **20:00–03:59** are confirmed by engine code, not just the older manual screenshot.

## Follow-up engine tracing

### REF-06: the active radio handler uses the published species pair

Further tracing narrows the earlier qualification. Overlay 2's land encounter paths call **02246E94** at **0224716E** and **022475CA**. This handler asks **02254590** for the radio mode. Mode 3 loads the encounter record's `+0x5C/+0x5E` directly and writes each species into two land slots (slot indices 2/3 and 4/5, respectively). Mode 4 uses `+0x60/+0x62`. Consequently the actual Hoenn replacement handler selects Whismur/Linoone from Route 31's current record; it contains no Ralts override. This closes the particular comment-versus-table conflict at engine level. Availability of the radio program in a particular save/weekday was not emulated, and unrelated special encounter methods remain separate.

### REF-03: common wild held-item generation also rejects Shiny Stone

The active held-item generator is **0207138C**. It rejects battle masks intersecting `0x81`, obtains species and form, reads personal attributes **16/17** through **0206EF84** at **020713CA/020713D8**, and writes one of those two values to held-item field 6. The attribute getter **0206EE44**, cases 16/17, reads record offsets **12/14** at **0206EF08/0206EF0C**. There is no species-based item substitution in this routine. Its thresholds at **020FE716** are `(45,95)` for the normal mode and `(20,80)` for the enhanced mode; Roselia therefore gets no item or Poison Barb on this path, never Shiny Stone.

Overlay 2 wild finalization **022489DC** invokes this at **02248A12**; its mode selector recognizes lead ability 14. Finalization callers were found at **02247D5A**, **02247E68**, and **02247F04**. The subsequent inspected code modifies forms/abilities, not Roselia's item. This is stronger than simply reading the personal table. A complete traversal of Safari-specific object/day selection and every alternate wild construction path was not completed, so the old Safari claim is rejected as documentation authority while the exhaustive absence claim remains unmade. Scratch `wild-code.txt`, `wild2-code.txt`, `ov2.txt`, and `pokemon-code.txt` preserve the traced paths.

## Remaining bounded questions

- Safari object/day selection and custom item overrides.
- Radio program availability in particular save/weekday states (the actual replacement species handler is now verified).
- Wiki/Iapapa berry battle activation threshold and amount.
- End-to-end normal play delivery and visual timing of initialization/forms (static active engine routes confirmed).

These limits are explicit; no unperformed emulator tests or source claims are labelled binary-verified.
