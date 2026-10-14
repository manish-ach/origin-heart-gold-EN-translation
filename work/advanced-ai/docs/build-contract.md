# Build contract

What each part of `work/advanced-ai/` hands to the next. The builder, the installer, the test bench and the Options row
are written in parallel against this contract; a change to it is agreed first and recorded here.

## Inputs (local, never committed)

| Input | Path | Identity |
|---|---|---|
| Untouched Chinese hack | `work/rom/origin_v4.0.3_cn.nds` | sha256 `4807ab2c130581cb9d4f6110fc64b41ca4807b8d28e7622ebd3c9740baed95c8` |
| USA HeartGold | `work/rom/Pokemon - HeartGold Version (USA).nds` | SHA-1 `4fcded0e2713dc03929845de631d0932ea2b5a37` |
| English rc8 release (standard build + difficulty) | `work/build/advanced-ai/base/rc8_release.nds`, from the rc8 release xdelta | SHA-1 `a54a647599d59ed0060dfc4375c289d6e041318a`, sha256 `d0185cfa37f329f4236aafbaa671b3dbb49fcdc4d7094bc27e491dc2894cf87f` |
| English rc8 standard build | `work/build/origin_hg_v4.0.3_en_wip.nds` (`work/tools/build.py`) | sha256 `f23e22632620454698c9a8f96b6e834737327b86fa5e5b9c3247d58f7a4d492d` |
| Spanish rc44 | `work/build/advanced-ai/es/rc44.nds`, from `advanced-ia-spanish.xdelta` | SHA-1 `5477043f03f3d145176d15dd9f92e4972f9a99f1` |
| Spanish sources | the Spanish workspace repository, commit `dc8577c` (read only, through `git show`/`git archive`) | `PROVENANCE.md` |

The AI is installed on an English build that already has difficulty: the rc8 release, or a later difficulty build. The
installer checks the bytes it depends on, not one whole-ROM hash, and records the input's hash in its receipt.

## Builder → payload (`builder/build.py`)

`build.py --layout es` reproduces the Spanish rc44 bytes (golden test only). `build.py --layout en` writes the English
payload. A layout is a JSON file in `builder/layouts/` that names the memory regions:

| Region | Spanish (`es.json`) | English (`en.json`, option A until phase 0 decides) |
|---|---|---|
| `slot` | 0x021F6E20 (after overlay 11's image and bss) up to 0x022007E0 | the same |
| `itcm` (resident code) | 0x01FF8620 (after the original ITCM block) | a fixed 0x01FF9500, a new autoload section past the largest ITCM block any locale can have (text speed, then trainer full names: at most 0x01FF9320; `builder/README.md` has the derivation) |
| `itcm_ram` (work RAM) | 0x01FFEE00–0x01FFFF8C | the same |
| `main` (resident code) | 0x0226D4C0 (inside the Spanish main block) | 0x023D4000–0x023DC000, a new autoload section below difficulty's |

The payload is committed in `payload/` after review. It holds only our compiled code, never ROM bytes:

```
payload/payload.json    format, layout name, toolchain versions, sha256 of every source and every .bin,
                        regions with their RAM address, size and bss, every symbol, the hooks and words below
payload/slot.bin        the AI code placed after overlay 11's image in overlay 10
payload/itcm.bin        the resident code for the itcm region (aiselect.s first, then ai_replace, g_tune, libgcc, ...)
payload/main.bin        the resident code for the main region (ai_lead first)
```

`payload.json` keys:

```json
{
  "format": 1,
  "layout": "en",
  "toolchain": {"gcc": "16.2.0", "binutils": "2.47"},
  "sources": {"src/advai.c": "<sha256>", "...": "..."},
  "regions": {
    "slot": {"ram": "0x021F6E20", "file": "slot.bin", "size": 0, "bss": 0, "limit": "0x022007E0"},
    "itcm": {"ram": "0x01FF9500", "file": "itcm.bin", "size": 0, "bss": 0},
    "itcm_ram": {"ram": "0x01FFEE00", "size": 0, "limit": "0x01FFFF8C"},
    "main": {"ram": "0x023D4000", "file": "main.bin", "size": 0, "bss": 0, "limit": "0x023DC000"}
  },
  "overlay10": {"base_from": "overlay 11 of the input ROM", "ram": "0x021E4DA0", "bss": "0x9E0",
                "static_init": ["0x021F6DE8", "0x021F6DEC"]},
  "symbols": {"adv_entry": "0x021F6E21", "ai_slot_select": "0x...", "...": "..."},
  "hooks": [{"file": "overlay14", "address": "0x02223D10", "before": "f1f700fe", "target": "ai_slot_select", "kind": "bl"}],
  "words": [{"file": "arm9", "address": "0x020D1A28", "before": "itcm_end", "before_max": "0x01FF9500", "after": "00000002",
             "purpose": "ITCM arena start"},
            {"file": "arm9", "address": "0x020D1970", "before": "00c03d02", "after": "00403d02", "purpose": "main arena high"}],
  "files": {"slot.bin": "<sha256>", "itcm.bin": "<sha256>", "main.bin": "<sha256>"}
}
```

Thumb symbols carry bit 0. `symbols` lists every global and static function and object the linker placed, so the test
bench never hard-codes an address. Linker interworking veneers (`__*_from_thumb`) are not listed.

Added by the builder (2026-10-13): each hook also carries `after` (the BL bytes for that layout); `regions.itcm` has a
`limit`; `overlay10.copied` gives overlay 11's expected size and bss; a `room` block reports used and free bytes per
region. `payload.json` pins `builder/build.py` and every source by sha256, so editing either needs a payload rebuild.
The Spanish-layout payload for the test bench is written to `work/build/advanced-ai/es/payload/`.

Added after review (2026-10-13): in the English layout `regions.itcm.bss` is non-zero. It runs from the end of the
itcm code through `.itcm_bss` (0x01FFECAC–0x01FFFDD8), so the boot's autoload zeroes the AI's work RAM; real hardware
does not clear ITCM at power-on. The test records from 0x01FFFF8C stay outside it. The installer writes every
region's bss into its autoload entry and the verifier checks it.

## Installer (`builder/install.py`) and verifier (`builder/verify.py`)

`install.py --input <English ROM with difficulty> --out <ROM>` writes into a copy, never in place:

1. Overlay 10: the input's overlay 11 image, its 0x20-byte bss as zeros, then `slot.bin`; y9 entry 10 gets the new
   size, bss and overlay 11's static initialisers.
2. Two new ARM9 autoload sections: `itcm` and `main`, as `payload.json` places them.
3. The words in `words` (arena bounds), each checked against `before`: either the 4 bytes the word must hold, or
   `"itcm_end"`, which accepts any value that equals the end of the input's ITCM block (0x01FF8000 + its size) and is
   at most `before_max` (the itcm origin). The ITCM block's end differs per locale (trainer full names, D-2487), so
   the ITCM arena start has no fixed `before`. Each word gets `after` (the ITCM arena start becomes 0x02000000).
4. The 5 hooks, each a Thumb BL written only if the site holds `before`.
5. The trainer marks: bits 0 (important) and 1 (keep lead) of header byte 2 in `a/0/5/5`, for the IDs in
   `data/trainer_marks.json`, each checked to be clear in the input.
6. A receipt (`<out>.receipt.json`): input and output hashes, payload hashes, every byte range written.

It refuses an input that already has the AI, an unknown overlay 11, a hook site or word that differs from `before`, a
region that would overlap anything already loaded there, and a ROM without difficulty (three autoload sections).

`verify.py <ROM>` re-reads the result with its own code (not the installer's) and checks all of the above, plus that
overlay 10's first 0x12060 bytes equal overlay 11.

## Settings

| Flag | Meaning |
|---|---|
| 0x2C2 clear | AI off |
| 0x2C2 set, 0x2C3 clear | every trainer |
| 0x2C2 set, 0x2C3 set | important trainers only (bit 0 of header byte 2) |

The Options row writes these flags. The test bench sets them directly in RAM.

## Test bench

The test bench reads `payload/payload.json` for every address (symbols, regions) and takes the ROM as an argument. For
the Spanish rc44 ROM it uses the payload that `build.py --layout es` writes to `work/build/advanced-ai/es/payload/`.
Run output goes to `work/build/advanced-ai/runs/`.
