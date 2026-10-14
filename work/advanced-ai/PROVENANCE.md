# Provenance

Every file in this directory that comes from the Spanish translation's workspace. The source is the Spanish workspace
repository at commit `dc8577cd8f9f81729e056c7b68c91e6ed034b567` (release rc44), by luisvent, **reused with the
author's permission (luisvent, 2026-10-13)**.

The files were taken with `git show dc8577c:<path>`, never from the Spanish working tree. "sha256 here" is the file as
first committed in this repository. A later change to one of these files is its own commit, so `git log -p` on the
file shows every difference from the Spanish original.

## Taken unchanged

| File here | Spanish path | sha256 of the Spanish original | sha256 here |
|---|---|---|---|
| `src/advai.c` | `work_es/tools/ai/advai.c` | `768f507b210c5d5379365a6e4f212fecb5364af66820125e6ccbbcaecf98a16b` | `768f507b210c5d5379365a6e4f212fecb5364af66820125e6ccbbcaecf98a16b` |
| `src/replace.c` | `work_es/tools/ai/replace.c` | `d2f9f6050ce639c2420ce4b53fc7efc90b3353c87e3a46fe39163de74e0bdb61` | `d2f9f6050ce639c2420ce4b53fc7efc90b3353c87e3a46fe39163de74e0bdb61` |
| `src/lead.c` | `work_es/tools/ai/lead.c` | `21cb9228001bc8fc478a3714276244f805c2ed2a4ac2bda7c6581cb332363a7a` | `21cb9228001bc8fc478a3714276244f805c2ed2a4ac2bda7c6581cb332363a7a` |
| `src/engine.h` | `work_es/tools/ai/engine.h` | `74fe10b1167fb7a8a9b94bdf0a3769036c3ae1adeb7de83d2fb9c6df1f5fb2a6` | `74fe10b1167fb7a8a9b94bdf0a3769036c3ae1adeb7de83d2fb9c6df1f5fb2a6` |
| `src/tune.h` | `work_es/tools/ai/tune.h` | `62362021f7496d4576e749e0fc34c854aa35d69f787cc9af234fee8195d0d679` | `62362021f7496d4576e749e0fc34c854aa35d69f787cc9af234fee8195d0d679` |
| `src/link.ld` | `work_es/tools/ai/link.ld` | `61bb601b010fe99b6e66a4f3448e18f05a5e57d01e982bf6898cea4a65817997` | `61bb601b010fe99b6e66a4f3448e18f05a5e57d01e982bf6898cea4a65817997` |
| `src/aiselect.s` | `work_es/tools/asm/aiselect.s` | `b3b19d12478bd3353a17bc8248d021a1ec00a41e5ed24dc60086813823a8b2ba` | `b3b19d12478bd3353a17bc8248d021a1ec00a41e5ed24dc60086813823a8b2ba` |

## Taken in part

| File here | Spanish source | sha256 of the Spanish original | sha256 here | What was taken |
|---|---|---|---|---|
| `src/check_flag.s` | `work_es/tools/asm/hardmode.s` | `e4fc5a74952dbae415c8100de57689f3b76f7340e4c586dcb77effa35f09e861` | `44e457379038a5fe46cd6fd8f94fd2ed83b6720965a9e93fea69c33501b7a1f1` | Lines 18–20 (directives), 29–31 (`GetSaveData`, `SaveVarsFlags`, `CheckFlag`) and 39–50 (`check_flag`), unchanged, under a new header comment. Hard mode is not taken |
| `src/ids.h` | the output of `ai_ids_header()` in `work_es/tools/build.py` (sha256 `bb91a409fcd8c88c1add705f0c5264ccd1b7f257a4888b91a545006458856624`), run on the Spanish workspace's English rc3 ROM | – | `f19be38bb47855fe27ac4df4387e684ca5f74b70a6594271a36842197a8fb48b` | Every generated line, in order; only the first comment line is replaced. `testbench/unit/test_ids.py` checks it against a fresh generation |

## Ported, not copied

| File here | Spanish source | What it is |
|---|---|---|
| `builder/build.py` | `work_es/tools/build.py` at the same commit: `AI_CFLAGS`, `link_ai`, `resident_sections`, `reached_sections`, `map_sections`, `map_entries`, `slot_spill`, `largest_first`, `ROOM_REGION`, `room_line`; the fields of `ai_overlay_entry` | The AI's compile and link steps, rewritten as one standalone builder that reads its memory layout from `builder/layouts/`. The y9 entry's fields go into `payload.json` (`overlay10`); the installer writes the entry |

## Changes made here

Each change to a taken file is its own commit. They are all behind switches the `es` layout leaves off, so
`testbench/unit/test_golden.py` still rebuilds rc44's bytes from these files.

| File | Change |
|---|---|
| `src/advai.c` | `AI_NO_STEER` (set by `builder/layouts/en.json`): `steer_marked` returns 0, which compiles luck steering out; zeroed definitions of `steer_stash`, `steer_ledgers` and `steer_dstash`, which the Spanish build kept in `steer.s` |
