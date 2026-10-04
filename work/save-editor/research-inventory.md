# Origin inventory and money layout

Read-only investigation of the untouched Chinese v4.0.3 ARM9 and six local raw saves, 2026-10-04. No game data or text is bundled here.

## Save data

All offsets below are relative to the selected general block. Items are four-byte little-endian pairs `{u16 item ID, u16 quantity}`; empty pairs are zero.

| Pocket | ROM pocket number | Save offset | Capacity |
|---|---:|---:|---:|
| Items | 0 | 0x644 | 165 |
| Key Items | 7 | 0x8D8 | 50 |
| TMs/HMs | 3 | 0x9A0 | 151 |
| Mail | 5 | 0xBFC | 12 |
| Medicine | 1 | 0xC2C | 40 |
| Berries | 4 | 0xCCC | 64 |
| Poké Balls | 2 | 0xDCC | 24 |
| Battle Items | 6 | 0xE2C | 30 |

Bag size is 0x864, including two registered item IDs at relative bag offsets 0x860 and 0x862 (save offsets 0xEA4, 0xEA6). Native size function is 0x020767EC; pocket dispatch is 0x020768A4. The full-bag fixture matches all boundaries and pocket membership from the ROM item records. Other saves agree with these boundaries.

Money is u32 at general-relative 0x78. Native trainer accessor 0x0202933C returns SaveArrayGet(1)+4; money getter 0x020294B4 reads trainer+0x14. The native setter 0x020294B8 clamps at **9,999,999**, literal at 0x020294C8. All six active fixture saves contain 3690 at 0x78. Vanilla's smaller money cap is incorrect for this hack.

## Native constraints and operations

The item allocation lookup at 0x020769B0 limits pocket 3 (TMs/HMs) to **99**, and every other pocket to **999** (literal at 0x020769F0). Native code does not impose a one-item limit on the Key Items pocket, though the full-bag fixture uses quantity 1 there.

Native add routine 0x02076A08 sorts TMs/HMs and Berries by ascending item ID after adding, calling 0x02076C64. Other pockets preserve insertion order. Native remove routine 0x02076AA4 clears zero-quantity item IDs and compacts the pocket using 0x02076C18. Existing fixture berry order is not necessarily sorted, so do not reject existing data for order alone.

Native unregister routine 0x0207686C clears registered slot 2 if it matches the removed ID. If registered slot 1 matches, it shifts slot 2 into slot 1 and clears slot 2. Registration bytes must otherwise remain unchanged. Registration references IDs, not pocket positions.

## ROM item metadata

Archive `a/0/1/7` contains 791 records of 34 bytes. The pocket number is `(u16(record+8) >> 7) & 15`. There are more possible items in some pockets than bag capacity; capacity must be enforced on the actual stored distinct items.

- Whole NARC SHA256: `e28535d77ab2c5fdb7914279b2338a354122303a864c65ed524b79f7c0648637`
- Concatenated member SHA256: `f132fe4dfe44f848af668d7b3d29afe8d00d41800537b444df352506170db6c6`
- Names archive: `a/0/2/7`, member 219, encoded using the game's existing message format. Extract locally from the user's ROM; never bundle copied game text.

## Independent runtime verification

SaveArrayGet at 0x02027740 preserves requested index in r4 and native save owner in r5. At return hook 0x0202775C, r0 is the array address. Pointer calculation is `owner + 0x10 + u32(owner + 0x2E01C + index*16)`. Index 1 is trainer data, 2 party, 3 bag. The bag accessor at 0x02076E28 is a tail-call to SaveArrayGet(3).

The verifier chains the pre-existing party hook, records the native save owner, independently resolves bag and trainer arrays with bounded reads, and requires the same owner to resolve the known party address. It copies the full 0x864 bag and four money bytes before emulator destruction. Decoder output is independently rechecked against copied bytes and expected JSON at load and after a real in-game save/reset/reload. The exported battery save is also CRC-validated and decoded separately using the documented on-disk offsets. Input ROM/save hashes must remain unchanged.

`--expect-inventory` accepts `{money, pockets, registeredItems?}`. All eight named pockets are required: `items`, `keyItems`, `tmHm`, `mail`, `medicine`, `berries`, `balls`, `battle`; entries are compact `{id, quantity}` lists. Use `--persistence` to require a native save-counter increase and compare the exported battery plus reset/reload state. The verifier validates native trainer/money/bag accessor signatures before running.
