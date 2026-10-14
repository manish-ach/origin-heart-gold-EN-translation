# Trainer marks

`trainer_marks.json` lists the trainers the advanced AI treats specially. `builder/install.py` writes them into byte 2
of each trainer's header in `a/0/5/5` (20 bytes per trainer, 1,024 trainers).

```json
{"important": [1, 2, 3, ...], "keep_lead": [2, 3, 7, ...]}
```

| Key | Count | Bit of header byte 2 | Read by |
|---|---|---|---|
| `important` | 453 | bit 0 (value 1) | `ai_serves` in `src/aiselect.s`: with flags 0x2C2 and 0x2C3 both set (the KEY setting), the AI serves only these trainers |
| `keep_lead` | 129 | bit 1 (value 2) | `ai_lead` in `src/lead.c`: the AI keeps the party order of these trainers in singles, whatever the setting |

A trainer can be in both lists (68 are), so byte 2 can be 1, 2 or 3. The Spanish build's bit 2 (boss aura, 208
trainers) is not ported: aura is out of scope ([PLAN.md](../PLAN.md), "Not ported").

The lists are copied unchanged from `IMPORTANT_TRAINERS` and `KEEP_LEAD_TRAINERS` in the Spanish workspace's
`work_es/tools/build.py` at commit `dc8577c` (luisvent, reused with their permission). They equal bits 0 and 1 of
byte 2 in the Spanish rc44 ROM. `testbench/unit/test_marks.py` checks both. The Spanish generator
(`work_es/tools/trainers/important.py`) and its trainer catalog are not ported.

## The selection rules

These are the Spanish author's rules, restated from `important.py` and `build.py`.

**Important.** A trainer is important when it fights in an important battle. That is the case when one of these is
true:

- Its catalog group is Gym Leader, Elite Four, Champion, rival, Rocket boss or Rocket Executive.
- Its class is a story class:
  - Rocket Elite;
  - PKMN Trainer or Johto Trainer (named story characters);
  - Cerulean Trnr (Misty);
  - a class that only one-of-a-kind characters have, such as Steven, Cynthia, Eusine, the Kimono Girls, Goh and the
    Frontier Brains.
- It is a named one-of-a-kind character in a class that generic trainers share, in any of its teams. Examples:
  Jessie and James, Mom, Prof. Oak, Molly and her clones, the Elders, Sage Zhishen, Karate King Kiyo, Granny Mae,
  Paxton.
- It is a legendary Pokémon staged as a trainer battle.
- It is fought inside a Gym, either as a sight trainer or in a battle that an event starts.
- It fights as a foe in the same script battle as a trainer that is important for one of the reasons above. Example:
  the unnamed second team in an Executive's multi battle.
- Its class is Ace Trainer or Veteran. These are strong trainers but not bosses, so their teammates are not
  counted.
- It fights on the player's side in a multi battle (a partner). Its foes are not counted.

Trainer 0 is the empty record and is never marked.

**Keep lead.** The trainer's single battles depend on its first Pokémon. That Pokémon may walk beside the trainer in
the field, a line of text may name it, or the script may stage it. The Spanish story audit found these 129 trainers,
each with more than one Pokémon in those battles.

## Byte 2 is free

The hack never uses byte 2, so the marks change no behaviour of their own. This was checked on 2026-10-13 against
the Chinese ROM and the rc8 release:

- **The data.** Byte 2 is 0 in all 1,024 headers of the Chinese ROM, the rc8 standard build and the rc8 release.
  The installer refuses an input where any header has byte 2 set.
- **Who loads the headers.** `TrainerData_ReadTrData` (0x02072700) is the only code that reads `a/0/5/5`. It
  tail-calls the NARC member reader with archive 0x37. No other call into the NARC module passes 0x37 as an archive
  ID. ARM9, ITCM, every autoload section and all 120 overlays were scanned for Thumb BL and BLX instructions.
- **What the callers read.** `ReadTrData` has 4 callers:
  - `EnemyTrainerSet_Init` (0x02072544) copies each header, 0x34 bytes as a block, into the BattleSetup at
    +0x28 + 0x34 × client. It reads only byte 1 (class 0x17 takes the rival's name) and the word at +0x10 (the
    doubles flag).
  - `TrainerData_GetAttr` (0x020725F4) has a case for attribute 2, but its only 2 callers ask for attribute 9
    (0x0203FC40) and attribute 1 (0x020541EE).
  - The overlay 14 reader at 0x0222C1BC reads bytes 1 and 3.
  - The overlay 92 reader at 0x021F1EB0 reads byte 3.
- **The BattleSetup copies.** In the emulator, read watchpoints were set on byte 2 of all four trainer headers in
  the BattleSetup during a single and a double trainer battle, including the trainer's AI turns, the Bag, the party
  and a faint. Only one read hit them: a block copy of client 0's header to client 2 at 0x02051786. The method is in
  [docs/memory-layout.md](../docs/memory-layout.md).

`test_marks.py` fails if a new caller of `ReadTrData` or `GetAttr` appears, if `GetAttr` is asked for attribute 2,
or if the reviewed readers' code in the rc8 release differs from the Chinese ROM.
