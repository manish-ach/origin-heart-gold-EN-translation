# Development tools mode

2026-10-13. Lets the difficulty feature build on a machine whose tools differ
from the pinned release tools. The release path is unchanged and stays the
default.

## Why

`install.py` compares `/usr/bin/clang`, Rust `ld.lld` and armips with the
sha256 pins in `options-source-pins.json` ("tools"): Apple clang 21, LLD
21.1.3 and one armips v0.11.0 binary. On another machine the build stops with
`REJECTED: tool guard clang`. That guard is right for a release candidate, but
it blocks development work such as a new Options row.

## How to use it

Set `DIFFICULTY_DEV_TOOLS=1` (exactly `1`; any other value is release):

```sh
DIFFICULTY_DEV_TOOLS=1 .venv/bin/python work/research/difficulty-armips/build.py --enable-difficulty --input work/build/origin_hg_v4.0.3_en_wip.nds
DIFFICULTY_DEV_TOOLS=1 .venv/bin/python work/research/difficulty-armips/verify.py --receipt work/build/difficulty-v2/integration-impl-dev/receipt.json --out work/build/<dir>
DIFFICULTY_DEV_TOOLS=1 .venv/bin/python work/research/difficulty-armips/tests/run.py
```

## What changes in development mode

| Part | Release (default) | Development |
|---|---|---|
| Tool pins | Each tool must equal its pin | Each tool is pinned as found: path, bytes, sha256, its own `--version` line, the release pin and `matches_release_pin` |
| Rust LLD | Run as is | Run with `DYLD_FALLBACK_LIBRARY_PATH` set to the toolchain's `lib/`: a current rustup `rust-lld` loads `libLLVM.dylib` from there, which its rpath does not name. The receipt records it, and pins `libLLVM.dylib` |
| Output folder | `work/build/difficulty-v2/integration-impl/` | `work/build/difficulty-v2/integration-impl-dev/`, so a development candidate never replaces or poses as the release one |
| Receipt | `tool_mode: release` | `tool_mode: development`; `status` starts with "development build, local tools, not a release candidate" |
| Output | Unchanged | The same label on stderr before the build and in the printed summary |
| `verify.py` | Requires a release receipt | Requires a development receipt (a mode mismatch is refused) |
| Tests | Bind `integration-impl/receipt.json` (`support.RECEIPT`, from `build.RECEIPT`) | Bind `integration-impl-dev/receipt.json` |
| `candidate_binding` (`tests/native_ui.py`) | Refuses a receipt whose `tool_mode` is not `release` | Refuses a receipt whose `tool_mode` is not `development` |
| `tests/run.py` report | `tool_mode` from the bound receipt; `host_build_mode: release` | The same, `development`; the summary line carries the label |

Everything else is unchanged in both modes: the input ROM guard, the source
guards and `source_overrides`, every hook, edit and dependency guard, the
logical byte census, the negative checks and the rebuild-and-compare in
`verify.py`. Code: `build.py` (`dev_tools`, `tool_mode`, `tool_env`),
`install.py` (`check_tools`, receipt), `verify.py`, `tests/run.py`,
`tests/support.py`, `tests/native_ui.py`; `tests/test_installer.py`
`ToolModeTests` covers the switch, the output folder and the binding refusal.

## Proof: a development build of unchanged rc8 sources

Input: the rc8 standard build (`work/build/origin_hg_v4.0.3_en_wip.nds`, sha256
`f23e2263…`). Local tools: Apple clang 17.0.0 (clang-1700.6.4.2), LLD 23.1.1,
armips v0.11.0 built on 2026-10-13. The build, install, reopen and the 53
negative checks passed, and `verify.py` passed. Output sha256
`05477e4ba7700c3ae2670fd57022e00db9a8cf89a1db752faa123f6baeafa32e`.

Compared byte for byte with `rc8_release.nds` (sha256 `d0185cfa…`), the ROMs
are **not identical**. Every difference has one cause: clang 17 emits 268 more
bytes of Thumb code than clang 21.

| Where | Difference | Cause |
|---|---|---|
| Resident autoload 0x023DC000 | 8940 bytes, release 8672. The C image is 8356 bytes, release 8088; the 584 stub bytes match in size | Compiler output. Function starts drift steadily from +12 bytes (`dg_growth_share_enabled`) to +256 (`dg_battle_root_free`). All 16 text strings of `.rodata` occur verbatim in the release image; the only other `.rodata` item is a table of absolute addresses |
| Stubs (item 336, Options 72, runtime 176 bytes) | Only the C addresses they hold | They follow the C image. Every other word is identical, and the addresses map one to one |
| 21 hook sites: ARM9 4, overlay 9 4, overlay 14 8, overlay 50 5 (38 bytes) | Branch and pointer encodings | Each still reaches the same stub, which sits 268 bytes later |
| ARM9 0x02000BA0, 0x02000BA4 (4 bytes) | Autoload table start and end | The resident section is larger |
| ROM header 0x2C, 0x15E | ARM9 size, header CRC | Same |

No other byte differs: the 548 other files, ARM7, both overlay tables, the
ITCM and DTCM sections, the 24 compatibility edits and the banner are
identical. armips output differs only in the stub addresses that it encodes.

## What the maintainer must redo with the release tools

A development build is never a release candidate. For a release:

1. Build without `DIFFICULTY_DEV_TOOLS` on the machine that matches the pins
   (or re-pin the tools in `options-source-pins.json` after review).
2. Run `verify.py` and `tests/run.py` in release mode.
3. Run the native checks on that build, then install the advanced AI on it.
