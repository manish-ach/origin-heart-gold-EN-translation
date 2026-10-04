# Origin Pokémon record research

Read-only investigation of existing project code and local saves, 2026-10-04.
No ROM or save contents are included here. No external downloads were used.

## Confirmed by the existing Chinese-ROM signature guards

`work/tools/memcheck.py:80-100,563-579` guards the party structure, native
checksum/crypto routines, PID-selected logical-block table, and move getter.
Party records are 236 bytes. Their initial boxed portion is 136 bytes:

- +0: u32 personality/identity, little-endian.
- +4: u16 flags. Current safe decoder rejects any nonzero value.
- +6: u16 checksum.
- +8: 128 encrypted bytes (64 little-endian u16 words).

Start an unsigned 32-bit seed at the checksum. For each word, advance
`seed = (seed * 0x41C64E6D + 0x6073) modulo 2^32`, then XOR the word with
`seed >>> 16`. Sum the decrypted words modulo 65536 to validate the checksum.
The same XOR stream encrypts. After editing, recompute the checksum and
regenerate the entire 128-byte ciphertext using the new checksum seed.
JavaScript should use `Math.imul` and unsigned coercion for exact arithmetic.

The block row index is `(pid >>> 13) & 31`. Each row below gives the byte
offsets of logical A, B, C, D inside the decrypted 128-byte payload:

```
0,32,64,96; 0,32,96,64; 0,64,32,96; 0,96,32,64;
0,64,96,32; 0,96,64,32; 32,0,64,96; 32,0,96,64;
64,0,32,96; 96,0,32,64; 64,0,96,32; 96,0,64,32;
32,64,0,96; 32,96,0,64; 64,32,0,96; 96,32,0,64;
64,96,0,32; 96,64,0,32; 32,64,96,0; 32,96,64,0;
64,32,96,0; 96,32,64,0; 64,96,32,0; 96,64,32,0;
0,32,64,96; 0,32,96,64; 0,64,32,96; 0,96,32,64;
0,64,96,32; 0,96,64,32; 32,0,64,96; 32,0,96,64
```

This is a direct extraction of the guarded table at Chinese RAM address
0x020FE963, not a guessed permutation ordering. Moves are four u16 values
at logical B+0, +2, +4, +6. Existing independent tests cover all 32 rows.

## Observations from existing local raw saves

A read-only scan decrypting checksum-valid candidates found occupied party
records at 0x98 + 236*n and 0x40098 + 236*n. The container research should
establish which save generation is authoritative; never choose by presence alone.

Logical A+0 species and A+2 held item are consistent with all sampled records.
The existing full-party fixture contains expanded species IDs 1018, 999 and
1010 stored directly as u16. A+8 u32 experience, A+12 friendship and A+16..21
six EV bytes also look plausible, but were not independently confirmed against
native getters in this small investigation.

**Do not assume vanilla ability storage.** A Charmander in these saves has
A+13 = 1, unlike its vanilla ability ID 66. This may be an ability-slot selector
or another hack-specific field. Ability editing needs separate research.
The other source project documentation confirms personal-table abilities are
u16 (including hidden abilities), but that does not establish save encoding.

Party tail (last 100 bytes), IV packing, forms, nickname encoding,
and stat recalculation were not verified here. PP verification is recorded below. Preserve them for the initial
move-only edit. Existing RAM probes explicitly do not prove save/reload
persistence, which still needs an emulator round-trip.

## Follow-up: PP verified against native getter

Read-only extraction from the Chinese ROM's decompressed ARM9 confirms:
move getter at 0x0206DC94 uses logical B plus twice (field ID minus 0x36).
Next branch subtracts 0x3A and performs `ldrb r4,[r0,#8]`, giving four
PP bytes at B+8..11. Next branch subtracts 0x3E and performs
`ldrb r4,[r0,#12]`, giving four PP Ups bytes at B+12..15.
The following maximum-PP getter reads the move u16 and PP Ups byte.

`src/pokemon.ts` implements immutable decode and complete move-slot edits.
Manual Node assertions passed for all six records in the existing local
full-party fixture: exact unchanged export, swapped move/PP/PP Ups decode,
unchanged party tails and source buffers, and exact restoration after swapping
back. This is binary codec validation, not an emulator persistence test.
