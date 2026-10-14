# Native Difficulty implementation candidate

This opt-in research implementation is awaiting current-source native acceptance:
**0/69 required native cases accepted for the rebuilt source**. The parent ran
five earlier UI cases before a driver error and identified the stationary red
cursor bug; its fix is included, with a fresh native rerun pending. Host/static checks do not establish native
UI, battle, save/reload or soft-reset acceptance. GPT6 Astra final review follows
the full native work. See the [test gaps and required evidence](tests/README.md)
and [required native cases](tests/required_native.json).

Run from the repository root using the existing local toolchain:

```sh
.venv/bin/python work/research/difficulty-armips/build.py --enable-difficulty --input work/build/double-target-armips/final/origin_hg_v4.0.3_en_wip.nds
.venv/bin/python work/research/difficulty-armips/tests/run.py
```

The first command compiles, links, assembles, installs and independently verifies
a real candidate. The second runs host/static tests without launching an emulator.
`tests/run.py --require-complete` also requires all native evidence and currently
fails that gate. Native runs require the parent's separate approval.
On a machine whose tools differ from the pinned ones, `DIFFICULTY_DEV_TOOLS=1`
builds a development candidate that is never a release candidate, in its own
folder `work/build/difficulty-v2/integration-impl-dev/`; see
[development tools mode](research/dev-tools-mode.md).

The installer accepts only the completed English input above, SHA-256
`a5a418b277bf07390e7282413923ec34f1c364f4a96c88936d65a73a80d51f40`.
The top-level English WIP is not interchangeable with that pinned fixture.
Generated ROM, receipt and isolated build artifacts stay under ignored
`work/build/difficulty-v2/integration-impl/`; `candidate.nds` and `receipt.json`
use [recoverable publication](research/publication.md) after verification.
Never commit or distribute the ROM. The default
production build does not install this feature.

Hold **L while opening Options from the field menu** to select DIFFICULTY.
Normal entry retains all seven ordinary Options, including TEXT SPEED. Use
D-pad/touch to choose ITEMS, SHARE, CAP and TRAINER AI; select APPLY or CANCEL, or press B
to cancel. TRAINER AI (OFF/KEY/ALL) is stored in event flags 0x2C2/0x2C3, not
in the Options word, and defaults to OFF; see [the TRAINER AI row](research/options-trainer-ai.md). Defaults are **DEFAULT (Chinese item permissions), Share ON, Cap OFF**. Apply changes RAM;
**save normally to persist**. Cancel discards the draft; no automatic save occurs.

- **ITEMS IN BATTLE (D-2412):** `DEFAULT` preserves the untouched Chinese hack's
  item permissions; `ALL` enables the existing expanded ordinary item set. Native
  validity, targeting and special-mode exclusions remain. Held items, NPC use,
  wild battles and field use retain native behavior.
- **Share OFF:** blocks benched Pokémon from shared EXP **and EVs**, except a
  Pokémon holding an Exp. Share (216), which keeps the ordinary bench share (D-2403).
  It does not bypass caps or native eligibility for participants.
- **Battles covered:** wild battles and ordinary trainer battles, including
  story battles the player is allowed to lose (script `TrainerBattle` with a
  nonzero third operand, setup flags `0x801`, e.g. Blue in Pewter City).
  Link, facility, Safari, replay, tutorial and other special modes keep native
  behaviour. See [runtime-classifier.md](research/runtime-classifier.md).
- **Cap ON:** limits newly awarded battle EXP at the final per-recipient award.
  Rejected EXP is neither redistributed nor banked. Existing levels/EXP and EV
  awards are not reduced. Caps follow the first unfinished gym in guide order:
  `12,20,25,38,55,65,80,100`, then100 throughout Johto and after all gyms.
  D-2312 confirms “Keep gym-only; never decrease”: take the running maximum
  of researched gym maxima through the earliest unfinished row. Later completed
  gyms cannot bypass an earlier gap or raise its cap; closing that gap skips
  already completed later rows. Raw gym maxima remain separate research data.
  See [progression and completion predicates](research/progression.md).
- **Rare Candy and Day Care remain unchanged**, explicitly deferred under the
  user's risk authorization D-2304/D-2307. They are cap exceptions.

Storage uses the existing aligned two-byte Options record, mask `0x8028`, with
no version tag. Valid legacy settings with zero repurposed bits get defaults;
arbitrary edited/corrupt reserved bits cannot be distinguished from difficulty
choices. Downgrades may interpret reused title/text-speed bits differently;
lossless mixed-version behavior is not guaranteed. Native save CRC/mirror logic
still controls save validity.

The [integration handoff](research/integration-impl-handoff.md) records hooks,
lifetimes, layout, source guards, deliberate exceptions and remaining proof.
The [Options handoff](research/options-handoff.md) describes menu/transaction ABI.
Historical `README.md` remains protected provenance.
