# English AI build: the recorded references

Recorded by `run.py quick --record` and `run.py deep --record` on 2026-10-13 (3 emulators), and carried over to the
relinked AI build the same day after every result held (below).

| Input | Identity |
|---|---|
| Reference ROM | `work/build/advanced-ai/layout/rom/rc8_ai.nds` (the rc8 release + the AI installer at `3f0abd7`), sha256 `9b62fe11082f12e049c0e7487863744e25d1bf7f2369e40974f4351f586cb38a`, SHA-1 `7fbc923d713a36629293ae359e70f282016195a2` |
| Payload | `work/advanced-ai/payload/payload.json` at commit `8362032` (layout `en`: ITCM origin 0x01FF9500, two more functions in main RAM), sha256 `f22a59c1…f036` |
| First recording | the same ROM built from the payload at `cb4ca7e` (ITCM origin 0x01FF8FC0), sha256 `1e91ce1f7f7f6a45c5b10adae6071395d7d1c1a2bd06a74c8ff200497a98665b` |

| File | Command | Result |
|---|---|---|
| `bench.json`, `bench_record.json` | `aibench --advanced --repeats 1`, 364 scenarios | 98.1%; 0 fallbacks, 364 of 364 decisions from overlay 10, polls max 5, 0 errors; 30 runs with clipped text (below) |
| `aiprops.json` quick | `aiprops --n 20 --seed 1` | 109 checks, 0 violations, every side served |
| `aiprops.json` deep | `aiprops --n 100 --seed 1` | 549 checks, 1 violation, every side served. The violation (`hp p0072 T`) is listed as known: the archived Spanish tool reports the same one on the Spanish rc44 ROM, so it belongs to the Spanish AI, not to the port or our build. A reviewer must confirm it |
| `aivsai.json` | `aivsai 40 --seed 101` | 72 of 80 (90.0%, Wilson 81.5-94.8%); 32 scenarios 2-0, 8 split; 18.5 turns; 0 fallbacks of 1,474 decisions, polls max 8; 0 wrong decisions; 0 asserts, freezes or NULL allocations; 156 clipped-text notes in 63 games |

The other steps passed: `aimode_check`, `lead_check`, `read_check`, `menulock` (the four foe cases), `ai_smoke`,
`fscheck`, `storycheck` (its Route 3 case INHERITED), `itcm_arena`, and `aifuzz --double --mode advanced` (50 battles,
0 with problems, 6 with the inherited animation asserts, 0 fallbacks of 586 decisions).

## Runs judged against these references

| ROM | Run | Result |
|---|---|---|
| `rc8_ai.nds` at `cb4ca7e` | static; `deep --only versus` | 9 of 9 in 28 s; all 80 logs byte-identical |
| `difficulty_dev_ai.nds` at `cb4ca7e` (sha256 `10ad6aab…ae40`) | quick with `--options-receipt .../difficulty_dev.receipt.json` | 8 of 8 in 20.3 min, every bench action the reference's, the Options row check passed |
| `rc8_ai.nds` at `8362032` (the reference ROM) | static, quick, deep | static 10 of 10 (31 s, once the quick tier had made the ROM's bench record); quick 7 of 7 + the Options row not applicable (18.5 min); deep 6 of 6 (51 min). Bench: all 364 actions, setter calls, debug records (every option value) and overlay-11 diagnostics identical to the first recording; 2 runs reached the decision one frame earlier (the AI's code moved; same decision and record). AI-vs-AI: 72 of 80, **all 80 logs byte-identical**. Props: the same counts, the known violation only |
| `main_dev_ai.nds` at `8362032` (sha256 `849ab3c305570321bfb90211485febbbe8f014b6278826bc480105e80100e7d0`: main's standard build, the re-pinned development difficulty build with the TRAINER AI row, the AI) | quick with `--options-receipt .../difficulty_dev_main.receipt.json` | 8 of 8 in 20.4 min, the Options row check included. Bench: every scenario's action, setter call, debug record and overlay-11 diagnostics identical to the reference ROM's run; 1 run reached the decision one frame later or earlier (`b03_psychic_terrain_priority`, same decision and record); the same 30 clipped runs. Props: 109 checks, 0 violations |

The references were then pointed at the relinked ROM (its hashes, its bench record) with the numbers, actions and log
digests unchanged.

## Notes

- **Clipped text.** Our ROM draws some ability pop-ups past the window's declared size (inside its buffer: a 'clipped'
  note, not an 'outside' failure), e.g. 'Blazing Awe', 'PsychicSurge', 'Inner Focus'. The same bench scenarios clip
  with the AI off (the hack's AI deciding), and the Spanish rc44 has none, so it is our build's text, not the AI. The
  bench holds the count to the reference; the AI-vs-AI report lists them for review.
- **Win rate.** 72 of 80 here against 71 of 80 on the Spanish rc44: the same AI code, other data (the Spanish build
  edits Pikachu's and Butterfree's base stats, among others).
- **The fuzz.** The first deep run failed `aifuzz`: four battles had the Searing Shot and Fire Pledge animation
  asserts the Chinese ROM has too, but our ROM breaks 'used' and the move name over two lines, so `lib/failures.py`
  neither found the message nor read the move (and named the battle's previous move instead). Fixed: `USED` also
  matches the line-broken message and `move_id` reads a line break as a space.
- **The AI-vs-AI games on `main_dev_ai.nds`** were not run (the user's decision); the quick tier was.
