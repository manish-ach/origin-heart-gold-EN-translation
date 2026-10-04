# Approved warning corrections and continued investigation — 2026-10-04

The user's 16 reviewed proposals were applied exactly to 10 message banks. The
candidate is `work/build/approved-warning-followup/candidate/origin_hg_v4.0.3_en_wip.nds`,
SHA-256 `4ec3b3441736d4e25f659e46c476ee024d571e34f2357dd421a5247171b26f87`.
No ROM is committed or distributed.

## Artifact scope

`application/applied.json` records the approved changes and bank backups. The
candidate also includes 11 word-list edits in banks 0279–0281 already present
before this work began. They were preserved and explicitly accounted for in
`application/rom-delta.json`. Against the preceding reviewed ROM, exactly those
27 records differ; all 550 non-message files, ARM9, ARM7 and overlay tables are
byte-identical. Message counts, seeds and trailers are unchanged.

Quality evidence under `work/build/approved-warning-followup/final-quality/`
passes 450 tool tests, 25 documentation tests, workspace QA (zero errors), build
artifact verification (76,862 strings), and 791 item-description buffer checks.
Raw heuristic warnings remain visible; they are not 9,116 demonstrated defects.
The subsequent final capacity-test run passes 453 tool tests and 25 documentation
tests. The stable static rerun detects exactly the three capacity failures plus
the existing 51 control-contract findings. Binary structure, change boundaries
and input stability pass; coverage limitations remain explicit. Evidence is in
`final-capacity-quality/` and `stable-final-static/`. An earlier static run
rejected a concurrent change to `work/tools/docs/gen_docs.py`; the rerun used
stable inputs, and that unrelated edit was preserved.

## Confirmed existing dialogue defect

Continued consumer-buffer investigation found three oversized English messages.
These records were unchanged by the 16 approved edits. Original Chinese event
scripts call each through the normal NPCMsg opcode:

| Record | Script file / byte offsets | English stored units | Chinese stored units |
| --- | --- | ---: | ---: |
| `0065#60` | 31 / 2026, 4464, 4504 | 1,242 | 395 |
| `0525#57` | 829 / 3353 | 1,114 | 284 |
| `0389#56` | 249 / 2587 | 1,094 | 393 |

The field consumer has a **1,024-unit String including EOS**. Exact records were
injected into isolated copies of a known trainer-dialogue fixture, using the
unchanged native reader/printer. All three English copies were rejected by
`02026EB8` (caller `0200B941`); all three Chinese copies passed. Native behavior
is assert-and-skip-copy, potentially leaving missing or stale dialogue. No heap
corruption was detected. This is a real translation defect, not proof of a
crash. Loading into an automatically sized String does not catch this smaller
receiving-buffer limit. Adding page breaks does not reduce whole-message storage.

`long-dialogue/proposals.json` and `long-dialogue/review.html` contain small
wording changes for review, not applied translations. Their encoded lengths are
1,018 / 1,022 / 1,018 units. All three pass static QA (only two irrelevant ability
name heuristic warnings on the first), native copy acceptance, and 74 sampled
heap checks per fixture. None contains variable substitutions. Screenshots show
initial pages in the fixture; these tests do not claim to traverse the original
story events or render every page. Exact before/after strings and evidence are
kept under ignored `work/build/`, not duplicated in this note.

## Other investigations

- The two embedded-FFFF controls `0763#66/#80` now have a guarded native copy
  and formatter proof with mutation tests. The complete 76,862-entry native
  sweep and independent validator pass, including six controlled formatter
  cases. See `native_load_verification.md` and `investigations/native-final/`.
- The six certificate messages now have a proven 512-unit stored-text consumer
  check. Header substitution bounds remain a separate limitation.
- The 50 blanked messages are **not proven unreachable in the Chinese hack**.
  Further tracing of `0267#147` finds a real Pokéwalker mode-1 renderer and its
  state transitions, but no exhaustive proof of how mode 1 can be selected.
  No unused-content exception was added. See
  `investigations/blank-state-followup.json`.
- Ribbon descriptions `0417#155/#164` retain Semifinalist. Neighboring years and
  ranks support a source typo (extra 准), but no alternative intended rank is
  proven. Recorded as D-1477; no speculative text fix.
- Compressed-name caller tracing identifies 64-unit temporaries in overlay 41;
  all producer bounds and indirect callers remain unproved. This is a coverage
  limitation, not a demonstrated overflow. See `text_buffer_verification.md`.
- Battle input navigation was corrected and a separate two-Pokémon save fixture
  was made without altering original saves or ROM code. Paired battle results
  and their explicit coverage limitations are in
  `investigations/battle-pair-final/report.json`. Both scenarios pass paired
  memory, text-copy and environment checks; the two-slot fixture also passes
  party identity checks. They remain incomplete: the paired repeat missed one
  English field-return resource assertion and one Chinese move-menu resource
  assertion, and resource loads alone do not certify exact UI/battler state.
  An earlier Chinese heap observation did not recur in two repeats and is not
  classified as a confirmed source bug.

The critical dialogue defect and proposed corrections are recorded as D-1480.

Existing control-contract findings remain explicit: 50 unresolved blanks and
Pryce's separately tested SIZE pagination deviation. The new dialogue buffer
findings must not be hidden by those old failures or by passing loader tests.
