# Payload

The English advanced AI as compiled code: the reviewed output of `builder/build.py --layout en`. The installer
writes these bytes into a ROM, so normal builds need no compiler. The schema is in
[../docs/build-contract.md](../docs/build-contract.md).

| File | What it holds |
|---|---|
| `payload.json` | Toolchain, sha256 of every source and `.bin`, the regions (RAM address, size, bss, limit), overlay 10's shape, every placed symbol (Thumb functions with bit 0 set), the 5 hooks with their old and new bytes, the 2 arena words (the ITCM arena start accepts any input whose ITCM block ends at or below the itcm origin), the room report |
| `slot.bin` | 32,800 B: the AI code that follows overlay 11's image in overlay 10, from 0x021F6E20 (`adv_entry` first). Its bss (2,656 B) follows it in RAM |
| `itcm.bin` | 22,444 B: the resident code for the new ITCM autoload section at the fixed 0x01FF9500 (`aiselect.s`, `check_flag.s`, `ai_replace`, `g_tune`, libgcc, the shared AI code). The section's bss (`regions.itcm.bss`, 0x112C B) runs through the AI's work RAM to 0x01FFFDD8, so every boot zeroes it |
| `main.bin` | 25,784 B: the resident code for the new main-RAM autoload section at 0x023D4000 (`ai_lead` first) |

These files hold only our compiled code. Overlay 11's image, which overlay 10 starts with, is never in the
payload: the installer copies it from the input ROM. No other ROM bytes are here either, except the 4-byte
`before` values of the hook sites and arena words, which the installer checks.

## Regenerate

Only after a change to `src/`, `builder/build.py` or `builder/layouts/en.json`. It needs arm-none-eabi-gcc 16.2.0
and binutils 2.47 (see [../builder/README.md](../builder/README.md)). From the repository root:

```sh
.venv/bin/python work/advanced-ai/builder/build.py --layout en --out work/advanced-ai/payload
```

Review the diff of `payload.json` (symbols, room, hooks) and commit the four files together with the change that
caused them.

## Verify

```sh
.venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit -p 'test_build*.py'
```

`test_committed_payload_is_this_build` rebuilds the payload and requires these files to be byte-identical. A
difference means a source changed without a rebuild, or another toolchain. The other tests check the schema, the
region limits, the hooks, that steering is compiled out, and that no overlay 11 bytes are in the payload.
