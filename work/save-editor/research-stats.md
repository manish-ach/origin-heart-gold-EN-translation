# Origin v4.0.3 stats field verification

Read-only disassembly of the user's untouched Chinese ROM on 2026-10-04 using ndspy and capstone from the original repository's .venv. No downloaded data or extracted ROM bytes are included here.

## Box fields

Logical blocks A/B use the existing verified PID block table. Native getter setup at 0x0206D9A8 establishes r6=A, r5=B.

- EVs: six u8 at A+0x10 through A+0x15: HP, Attack, Defense, Speed, Special Attack, Special Defense. Native getters at 0x0206DC3E..0x0206DC52, fields 0x0D..0x12. Native recalculation consumes them in this order.
- IVs: little-endian u32 at B+0x10, six 5-bit fields in the same order, shifts 0,5,10,15,20,25. Native getters 0x0206DCD0..0x0206DCFC, fields 0x46..0x4B. Preserve upper two bits: bit30 is egg, bit31 nickname flag (getters 0x0206DD00 /0x0206DD12).
- Experience: u32 A+8 (native getter 0x0206DC18).
- Form: upper five bits of B+0x18, native getter 0x0206DD78.

## Origin nature override (important difference from vanilla)

Native GetNature entry 0x0206F198 jumps to 0x0206F1A0. It reads field 0xBE; nonzero returns value-1, zero falls back to PID modulo25 (helper 0x0206F1E0).

Field0xBE getter at 0x0206DC24 reads little-endian u32 B+0x14 then computes (word<<1)>>>26, equivalent to (word>>>25)&63. Thus nature override is bits25..30 of B+20; preserve all these bits when editing IVs/EVs. Valid override values 1..25 encode effective nature0..24. Unknown higher values should fail closed for stat recalculation.

## Party tail

Party record is236 bytes, boxed prefix136. Getter at0x0206D848 decrypts tail at record+0x88, size0x64, seed PID (native0x0206D858..0x0206D860), separately from boxed checksum-seeded payload. Same XOR LCG as boxed payload. Tail does not contribute to boxed checksum; save block checksum still covers it.

Relative to decrypted tail:

| Offset | Field |
| --- | --- |
| 0 | u32 status |
| 4 | u8 level |
| 5 | u8 capsule field |
| 6 | u16 current HP |
| 8 | u16 max HP |
| 10 | u16 Attack |
| 12 | u16 Defense |
| 14 | u16 Speed |
| 16 | u16 Special Attack |
| 18 | u16 Special Defense |

Native getter dispatch0x0206D8C0 uses fields0xA0..0xA9; individual reads0x0206D8EE..0x0206D926. Preserve all other100-byte tail contents and original status/capsule.

## HP update behavior from native recalculation

Native0x0206D7F0..0x0206D836: if old currentHP=0 and old maxHP!=0, stay fainted. Otherwise Shedinja species292 uses currentHP1. If old currentHP=0 with old maxHP=0, use new maxHP. If new maxHP>=old maxHP, add the maxHP increase to currentHP. If maxHP decreases, clamp currentHP to new maxHP (rather than subtracting the difference). An editor can mirror this exactly while recalculating; avoid unintended healing on fainted imports.

## Calculation and local ROM data

Native CalcMonStats at 0x0206D584 reads IVs directly (no hypertraining interception), EVs, species/form base stats and effective nature. It computes `floor((2*base + IV + floor(EV/4))*level/100)`, then adds level+10 for HP or 5 for other stats. Species292 has maximum HP1. The 25-nature matrix at0x020FE869 follows Attack/Defense/Speed/Special Attack/Special Defense order. The native nature routine narrows the multiplied value to16 bits before dividing; the editor mirrors that behavior.

Local ROM personal NARC `a/0/0/2` contains1441 records of52 bytes. First six bytes are HP/Attack/Defense/Speed/Special Attack/Special Defense; growth is byte19. Form table at ARM9 RAM0x020FEDC0 contains415 six-byte entries {species,personal index,form}. Native lookup0x020721C0 uses the base species record for zero or unmatched forms.

Growth NARC `a/0/0/3` contains eight records of101 u32 experience thresholds. Native0x0206F0B0/0x0206F0CC load the archive and index by level. The editor reads exact local-ROM thresholds; no growth formulas or extracted game tables are bundled. SHA-256 checks of personal, growth and form data match between the untouched Chinese ROM and current English build.

Origin's adventure tip a027/0444#83 specifies IV0–31, EV0–255 individually and510 total. These bounds are enforced. Invalid pre-existing EV totals remain viewable; stat edits require correcting the EV total first. Eggs remain viewable, with stat editing disabled.

## Verification scope

All13 Pokémon in six local fixture saves have valid IV/EV inputs. Seven Pokémon from normal route/trainer/shop saves exactly match the native-derived formulas. All six Pokémon in the deliberately modified full-party fixture retain the same stale Charmander cached stats despite differing species; a no-op export preserves them, and applying a real stat change recalculates the selected Pokémon from its actual species/form.

The independent Python runtime decoder checks all six IVs, all six EVs, effective nature, form, experience, level, current HP, cached battle stats, status, PID and species against TypeScript-generated expectations. Runtime evidence is stored only in ignored `local/`.
