# Tooling notes: 起源心金 / Origin HeartGold English translation

**Status (reviewed 2026-09-29): historical.** The first tooling pass (2026-09-28), kept as a record of how the text format, charmaps and base ROM were worked out. The engine and format facts still hold; the open questions in §0 and §8 are answered in §8. For current usage see each tool's `--help`.

Status date: 2026-09-28. Author: tooling pass #1.
Tools live in `work/tools/`. Run the tests with `python3 -m unittest -v work/tools/test_msgtool.py`.

---

## 0. Summary

| Question | Answer |
|---|---|
| Can we read the Chinese text without the base ROM? | **Yes.** The v4.0.3 patch carries 99.57% of the target ROM as literal data. The message NARC `a/0/2/7` and the font do not depend on the base at all. See §2. |
| Which charmap does v4.0.3 use? | **Xzonn's unified Gen-4 Chinese table.** Hanzi run `0x01FF`=一 … `0x1C9B`=龠 (6813 glyphs), sorted by Unicode within blocks. Latin and kana stay at the vanilla codes. Every code in all 817 banks decodes, and the text reads correctly. See §4. |
| Which charmap do v3 Cn / v3 Eng use? | **A different one: the ACG HGSS table.** `0x01FE`=一 and so on. 85 (v3 Cn) / ~1150 (v3 Eng) code tags are still unknown. See §4. |
| Base ROM required | **Settled later: Pokémon HeartGold (USA) `IPKE`, CRC32 `C180A0E9`** (see `credits_and_sources.md`). The original analysis: **not determined yet.** It is a 128 MiB HeartGold dump. The header game code is `IPK?`, and the fourth character is **not** `J`, because the patch overwrites it with `J`. Most likely USA `IPKE`. `msgtool.py check-base` settles it in one command once a dump is available. See §1. |
| Is a Chinese charmap needed for the English build? | For *reading*: yes, use Xzonn's table (already in `work/tools/charmaps/`). For *writing* English: no new charmap is needed, because Latin glyphs sit at the vanilla US codes (`charmap_en.tsv`). Keep the CJK table stacked on top while any Chinese strings remain. See §4.4. |
| v3 Eng | This is **partial translation memory only**. It was translated "until Cerulean" (r/PokemonROMhacks thread). 17,655 of 52,131 Chinese strings (34%) have no CJK left. 642 CJK-bearing banks are untouched. See §7. |

---

## 1. Base ROM

### 1.1 What the patches tell us
All four `.delta` files are xdelta3 VCDIFF, secondary compressor lzma. They have **no app header**, so no embedded file names (`xdelta3 printhdr`).

Window 0 copies source header bytes `[0,15)`, `[21,44)`, `[51,65)`, `[85,105)`, `[110,128)` and `[132,350)`, and adds the rest. Decoding against a zero source (see §2) gives the target header:

- **Title and code:** title and `IPK` are copied from the base. Offset `0x0F` is *added* as `'J'` in every patch. xdelta extends a source match forward byte by byte, so the base byte at `0x0F` differs from `'J'`. **The base is therefore not the Japanese IPKJ dump**, unless it is a hacked dump with a changed code. The target calls itself `IPKJ`.
- **Capacity:** the device-capacity byte `0x14` changes to `0x0B` (256 MiB, v3) or `0x0C` (512 MiB, v4). Retail is `0x0A`.
- **Base size:** the highest source offset any patch reads is `0x7FFC006` (v4) or `0x75CA7D4` (v3 Eng), so the base is a full 128 MiB (134,217,728-byte) dump, not a trimmed one.
- **What the base still supplies:** arm9 offset, entry and RAM address, arm7 entry/RAM/size, the logo and the secure-area CRC. In total 311 of the first 512 header bytes come from the base.

### 1.2 Circumstantial evidence

**Pointing to an English (USA) base**
- The v3 Eng patch copies `a/0/5/7`, `a/0/5/9`, `a/0/6/2`, `a/0/6/3` and `a/0/6/4` 100% from the base, and `a/0/5/8` 87%. The v3 Cn patches take ≤10% of those files from the base.
- The v4 ROM still contains many English strings: 24 mostly-Latin banks, plus English leftovers mixed into the Chinese banks. `battle/string/battle_string.narc`, which does not exist in retail, has English lines such as "Whoa! A wild {VAR:0102:0,0} leaped out!".

This suggests an English code/data lineage, possibly an hg-engine-style expansion, which targets USA IPKE.

**Pointing to a Japanese lineage**
- The ACG 汉化组 Chinese HGSS (2010, HH-0060) and Xzonn's revision are built on the Japanese ROM.
- `pbr/msg.narc` in v4 holds Japanese kana text.

**Author and v3 Eng patch**
- The original author is Bilibili **雁南飞TB** (UID 1461403176). The "完结版" came out 2024-02-09 in three skins, 起源赤红 / 无印小智 / 特别篇, which match our "v3 Cn Origins/Special" patches. <https://www.bilibili.com/video/BV1pp421R78c/>
- The partial v3 English patch is by u/Shake69, who gave permission to reuse it (see the README credits). The Reddit thread is <https://www.reddit.com/r/PokemonROMhacks/comments/1wsbpj6/the_best_pokémon_ds_rom_hack_is_chinese_and/>.

### 1.3 Known clean dumps (No-Intro, via the libretro-database DAT)
All are 134,217,728 bytes.

| Dump | Serial | CRC32 | MD5 | SHA-1 |
|---|---|---|---|---|
| Pokemon - HeartGold Version (USA) | IPKE | `C180A0E9` | `258cea3a62ac0d6eb04b5a0fd764d788` | `4fcded0e2713dc03929845de631d0932ea2b5a37` (= pret/pokeheartgold target) |
| Pocket Monsters - HeartGold (Japan) | IPKJ | `FC7D8F28` | `e3f7933aee8cc2694629293f16c1c0a8` | `82451ee0ca9c3b768ba21367b92d8aa0e8defda7` |
| Pokemon - HeartGold Version (Europe) | IPKP/E | `B64A5EFB` | `80c1024a03aa2c1e3d66ba168db97739` | `eb47ab4ba0326ae842135f62c7ec68cf85c9785f` |
| … Goldene Edition (Germany) | IPKD | `0A994C0C` | `5582a09af4fc2a9873712497c9cd425b` | `13b6853aa93121069df1d17446d3ecb36872aecf` |
| … Version Or (France) | IPKF | `533A6E55` | `1f937c6376a25ff36358ca5819c83f5a` | `f09016569ee5dbac9dd0098d04927987c47645b9` |
| … Versione Oro (Italy) | IPKI | `2646AE79` | `7aae450618f86f8d9e6f43aca52ac919` | `6b7f9bff57eb58bc8d6e48e9e5c370719458c721` |
| … Edicion Oro (Spain) | IPKS | `0E3670CD` | `b101936ad60a33e3c06b72c6ea15a99a` | `237cc2e34e51dc291eb61238b8e75f9e78ba1285` |
| Pocket Monsters - HeartGold (Korea) | IPKK | `23850525` | `7d4c656de7baabc455aacdec85b18ad5` | `52516d1690d01b59e03c7fe3b1259239f5daea38` |

**Other variants**
- **Encrypted-secure-area variants.** These are also listed on DAT-o-MATIC; *which* set is which has not been verified.
  - USA: CRC `4723410A`, MD5 `228c1598f040d5d71f62c73563dcb2c2`.
  - JP: CRC `B71CC560`, MD5 `bc93a1536f3b1d0c6e165c765fa30b1a`.
- **Chinese ACG HH-0060:** no published checksum found.
- **Xzonn revision outputs (HG):** MD5 `07fc5de0…` (v2.0.0), `e05ae6d7…` (v2.1.0), `4235f6e2…` (v2.1.1). These are unlikely bases.

### 1.4 How to settle it
Run this with the user's dump:
```
python3 work/tools/msgtool.py check-base <dump.nds> --patch "Pokémon Origin HeartGold v4.0.3 Cn.delta"
```
It prints size, header, CRC32/MD5/SHA-1 and the matching No-Intro entry. It then decodes the patch **with checksum verification on**; xdelta3 checks an adler32 for every window. A wrong base fails in the first window that copies from the base. Try the USA IPKE dump first.

---

## 2. Previewing the targets without the base ROM (important)

`msgtool.py patch-preview <patch> <out.nds> [--report r.json]` works like this:
1. It decodes the patch twice with `xdelta3 -d -n`, once against an all-`0x00` fake base and once against an all-`0xFF` fake base.
2. Bytes that come out identical are exact. Bytes that differ came from the base, and are reported per file.
3. It fills the few standard header fields (arm9 offset `0x4000`, entry `0x02000800`, RAM `0x02000000`, arm7 `0x02380000`, title) so that ndspy can parse the result.

| Patch | Target size | Bytes that need the base | Message NARC `a/0/2/7` | Font `a/0/1/6` |
|---|---|---|---|---|
| v4.0.3 Cn | 512 MiB | 2.3 MB (0.43%), mostly `pokepic_m/f.narc`, `clothes*/a081.narc`, sound | **complete** | 414 bytes missing |
| v3 Eng | 141 MiB | 12.9 MB (8.75%) | 450 bytes missing | 40 KB missing |
| v3 Cn Origins / Special | 140 MiB | 4.9 MB (3.3%) | ≈complete | small |

This means **text extraction, translation and charmap work can start now.** Only building and play-testing the final ROM needs the base. Do not ship anything built from a preview.

Regenerate the previews into `work/rom/`. They are derived from our own patches; the tool does not download anything.
```
python3 work/tools/msgtool.py patch-preview "Pokémon Origin HeartGold v4.0.3 Cn.delta" work/rom/preview_v4.0.3.nds --report work/rom/preview_v4.0.3.json
```

The v4 file system has 431 named files and 120 arm9 overlays. Text-bearing NARCs found so far:
- `a/0/2/7`: 817 banks, the main text.
- `pbr/msg.narc`: 610 banks. Japanese/multilingual PBR-link text, probably no translation needed.
- `battle/string/battle_string.narc`: **4 banks, a non-retail file added by the hack.** It holds 164 / 2207 / 487 / 23 strings of Chinese battle messages with English leftovers, and **must be translated**.

All three round-trip byte-identically with `--narc <path>`.

---

## 3. HGSS text format (verified against pret/pokeheartgold `tools/msgenc` and against the ROM data)

### 3.1 Files
- **Messages:** NitroFS `a/0/2/7`, which is `files/msgdata/msg.narc` in pret (`filesystem.mk`: `arc_strip_name`). US retail has 814 banks; v3 has 814; v4 has 817.
- **Useful US bank numbers (pret):** 0222 items, 0237 species, 0279 locations, 0720 abilities, 0728 trainer battle text, 0729 trainer names, 0730/0731 trainer classes, 0735 types, 0750 moves.
- **The hack renumbers banks.** In v4, bank **232** is species names (1439 entries, forms included) and bank 237 is TV-show text. Build a bank map (v3→v4 and US→v4) before reusing any US numbering.
- **NARC layout:** BTAF, then BTNF (8-byte stub `04000000 0000 0100`), then GMIF. Files are 4-aligned with **0xFF** padding. The v3 NARC has inconsistent size fields: the total is 96 bytes too big and GMIF 8 bytes too big. `Narc` preserves both quirks. ndspy's `NARC.save()` is **not** byte-identical (it rewrites BTNF), so `msgtool` has its own NARC writer.

### 3.2 Bank encryption (pret `MessagesConverter.h`)
```
u16 count; u16 seed; { u32 offset; u32 length_in_u16 } [count]; u16 data...
entry i (1-based):   k = (seed * 0x2FD * i) & 0xFFFF;  k |= k << 16;  offset ^= k; length ^= k
string i chars:      key = (0x91BD3 * i) & 0xFFFF;  for each u16: c ^= key; key = (key + 0x493D) & 0xFFFF
```
XOR is symmetric, so encrypting and decrypting are the same operation. Strings are stored back to back with no padding.
- The **seed** differs per bank. `msgtool` stores it in the JSON so rebuilt banks are identical.
- **v3 builds quirk 1:** strings sit in fixed-size slots filled with extra `0xFFFF` units (up to 281). JSON records these as `"pad": k`.
- **v3 builds quirk 2:** some banks have a 2-byte trailer, recorded as `"trailer_hex"`.

### 3.3 Control codes
| Code | Meaning | JSON tag |
|---|---|---|
| `0xFFFF` | end of string | (implicit) |
| `0xE000` | newline | `{NEWLINE}` (a literal `\n` is also accepted on insert) |
| `0x25BC` | wait for button, **clear box, new page** (pret `\r`) — corrected, see text_metrics.md §2 | `{SCROLL}` |
| `0x25BD` | wait for button, **scroll up one line**, continue on the bottom line (pret `\f`) — corrected | `{CLEAR}` |
| `0xFFFE, cmd, argc, args…` | command | `{VAR:CMD:a,b}` (hex cmd, decimal args) |
| `0xF100` first unit | 9-bit packed string (trainer and Pokémon names) | `{COMPRESSED}` prefix |
| anything unmapped | raw code unit | `{U+XXXX}` |

**Command IDs** (pret charmap and MessagesDecoder):
- `0x01xx` STRVAR_1. The low byte is the var kind (1 = Pokémon name, 0 = player/trainer, 3 = trainer class?, …). The args are buffer index and 0.
- `0x03xx` STRVAR_3 and `0x04xx` STRVAR_4 (numbers), `0x34xx` STRVAR_34.
- `0x0200` YESNO, `0x0201` PAUSE, `0x0202` WAIT, `0x0203`/`0x0204` CURSOR_X/Y, `0x0205`/`0x0206` align center/right.
- `0xFF00` COLOR, `0xFF01` SIZE, `0xFF02` ?.

**Compressed strings:** codes are 9 bits each, packed LSB-first into 15-bit units. The last partial unit is filled with 1-bits, and a final `0xFFFF` unit also provides the `0x1FF` end marker. This was verified on v3 Eng: "Don" encodes as `F100 272E 7A95 FFFF`. These strings only hold codes < `0x1FF`, i.e. no hanzi.

### 3.4 Glyph and character codes (vanilla US, pret `charmap.txt`)
- `0x0001`–`0x0120`: full-width kana and symbols.
- `0x0121`–`0x012A`: 0–9; `0x012B`–`0x0144`: A–Z; `0x0145`–`0x015E`: a–z.
- `0x015F`–`0x01A2`: Latin-1 accents and Œœ; `0x01A3`–`0x01EA`: punctuation and symbols. `0x01DE` is the space; `0x01AB` `!`, `0x01AC` `?`, `0x01AD` `,`, `0x01AE` `.`, `0x01AF` `…`.
- `0x0400`–`0x0D65`: Hangul (Korean glyphs in the US font table). These are **excluded** from `charmap_en.tsv` because the Chinese hacks reuse the range for hanzi.

---

## 4. Chinese character table and font

### 4.1 Tables
Both Chinese tables leave kana and Latin at their vanilla codes (≤`0x01EA`) and put hanzi above them. They are **incompatible with each other**. Compatibility matrix: <https://xzonn.top/PokemonChineseTranslationRevise/CharTable.html>

| Table | File | Hanzi range | Used by |
|---|---|---|---|
| Xzonn unified Gen-4 table (`CharTable.txt`, 2023-10) | `work/tools/charmaps/charmap_zh_xzonn_gen4.tsv` | `0x01FF`=一 … `0x1C9B`=龠 | **v4.0.3**. All codes in all 817 banks decode, and the text reads correctly. |
| ACG 汉化组 HGSS table (`CharTable_HGSS_ACG.txt`) | `work/tools/charmaps/charmap_zh_acg_hgss.tsv` | `0x01FE`=一 … `0x0E81` (3201 hanzi) | **v3 Cn and v3 Eng**. 85 codes in v3 Cn text are not in it (e.g. `0BF9`, `0AAB`, `092A`). Recover them with `glyph` + `charmap-guess`. |

Sources: <https://github.com/Xzonn/PokemonChineseTranslationRevise/tree/master/files>. The files were converted with `msgtool.py charmap-import`.

The Xzonn and ACG tables differ from pret at four codes: `0001` (U+2007 vs U+3000), `00F1` (ー vs －), `00F5` (～ vs ｚ) and `01B0` (• vs ·). Stack order decides which wins.

**Example:** 的 is `0x096F` in v4 and `0x09C3` in v3. The same Chinese sentence is stored as different codes in v3 and v4. **Always decode each build with its own table before comparing.**

### 4.2 How we confirmed it empirically (method for future builds)
1. **Decrypt the text.** Frequency of code units gives: `0x096F` is by far the most common hanzi code, so it must be 的.
2. **Read the font `a/0/1/6`** from the preview. Files 0, 1, 2 and 4 are the text fonts. Each is 469,267 bytes:
   - Header `u32 hdr=0x10, u32 widthTableOff=0x72710, u32 numGlyphs=0x200, u8 maxW, maxH, tilesW=2, tilesH=2`.
   - **7324 glyphs** of 64 bytes each (16×16 px, 2bpp). Glyph index = code − 1.
   - The width table only covers the first 512 glyphs. Hanzi have fixed width 12, or 13 in font 4, which the patched code must supply.
   - File 3 is the vanilla-sized 509-glyph font.
   - **Pixel order:** tiles are row-major (TL, TR, BL, BR); each tile row is 2 bytes; the pixel at x (0–7) inside a tile is bit pair `(7−x)` counted LSB-first. The value is 1 = ink, 2 = shadow, 0/3 = background.
   - `msgtool.py glyph <rom> 096F 012B` renders glyphs as ASCII.
3. **Match glyphs to characters.** The hanzi are sorted by Unicode inside several blocks: resets at `0x0DD9`, `0x0EA4` and `0x1117`. That structure let a monotone alignment recover ~99% of the table by glyph matching alone:
   - render GBK hanzi with Songti/STHeiti at 12 px;
   - correlate them with the ROM glyphs;
   - run piecewise-monotone dynamic programming.

   We then found that Xzonn's published table matches exactly. Keep this method in mind for any build that uses an unpublished table. The scratch scripts were not kept; they need pillow + numpy.
4. **`msgtool.py charmap-guess`** cross-checks a table against known strings:
   - `--pairs file.tsv` takes lines of `知道的文本<TAB>hex units`.
   - `--rom X --bank N --known list.txt [--offset k]` aligns line i with string i+k.
   - It votes per code, and with `--charmap` reports agreements, disagreements and new codes.

   The glossary xlsx is ordered by the hack's own 4.0 dex numbers, not by bank index: 47 of 493 species lines had mismatched lengths. Use it only on lists whose order is known.

### 4.3 Chinese 汉化 font background
- ACG and Xzonn render hanzi from 中易宋体 (SimSun) at 12 px, width 12.
- Xzonn's tools (PCTRTools, NitroPatcher) handle font generation, text import/export and NARC replacement: <https://github.com/Xzonn/PCTRTools>. Their Gen-4 code is ported from JackHack96's DS-Text-Editor.

### 4.4 Restoring English output
- **Encoding:** English text needs **no new charmap**. `charmap_en.tsv` (pret, ≤`0x01FF`) encodes it at the vanilla codes, and the hack's font still has Latin glyphs there with a width table.
- **Font width:** (corrected, see `text_metrics.md` §1: these Latin glyphs/widths are *identical* to the vanilla US font, which is itself near-monospaced 6 px; only … “ ” 《 》 are 12 px and some accented glyphs are blank in font 1) the hack's Latin glyphs are a **condensed 5–6 px set** (i=3, l=4, m=6, W=6, space=4). v3 Eng shipped with it. For readability, replace glyphs `0x0121`–`0x01EA` (index code−1) in font files 0/1/2/4 with the vanilla US glyphs and their widths. Take them from the user's USA ROM font or from the pret font assets. Keep the width-table length at 512.
- **Hanzi glyphs:** keep them while any Chinese remains, and always stack `--charmap charmap_en.tsv --charmap charmaps/charmap_zh_xzonn_gen4.tsv`. Once everything is translated, the unused glyph space can be dropped or reused.
- **Line fitting:** English runs ~2× longer than Chinese. We need a line-wrapper that uses the font width table: sum the widths per line, then split with `{NEWLINE}` / `{SCROLL}` / `{CLEAR}`. **OPEN:** measure the message-box pixel width, about 208–224 px for the standard box, and check whether the hack's patched renderer applies Latin widths correctly.

---

## 5. Other text sources
- **Trainer text:** trainer names, classes and battle text are message banks (US 729 / 730+731 / 728). Battle text is indexed via `a/0/5/7` (trtbl) and `a/1/3/1`. Trainer data is `a/0/5/5`; parties are `a/0/5/6`. v3 Eng stores trainer names as `{COMPRESSED}` strings.
- **Scripts:** script commands reference message IDs inside the banks, so the text lives in `a/0/2/7`. The hack adds banks, so map-script ↔ bank links have to be recomputed; DSPRE shows them. Retail also has `msgdata/scenario/scr_msg.narc`.
- **Hardcoded text:** check arm9 and the 120 overlays for GB2312/UTF-16/ASCII strings. The Wi-Fi/DWC error screens are known hardcoded places, and Chinese hacks usually patch them (e.g. DS-Internet-CHS). Most in-game text is in banks. The v4 arm9 has 385 bytes that depend on the base, so byte-level patching needs the base.
- **Graphics with baked-in text:** title screen, Pokégear, Pokédex headers, trainer card, battle UI labels, bag and menu tabs. The ACG/Xzonn projects redrew these (see Xzonn's HGSS page). Candidates: `a/0/5/8`–`a/0/6/4` (language-dependent per the v3 Eng/Cn copy pattern), the title-screen NARCs and `data/nfont.NCGR`. Use Tinke or NitroPaint to find and redraw them.
- **Existing tools:**
  - DSPRE (HGSS script/text/map editor), PokEditor.
  - Tinke (generic NDS viewer/graphics).
  - ndspy (Python FS/NARC).
  - pret `msgenc` (gmm/JSON ↔ bin).
  - Xzonn PCTRTools / NitroPatcher.
  - JackHack96 DS-Text-Editor, PokeFontDS (font glyph editor).
  - PPRE, VenusSoul's tools: not evaluated.

---

## 6. `work/tools/msgtool.py` reference

```
python3 work/tools/msgtool.py unpack        ROM OUTDIR
python3 work/tools/msgtool.py extract       ROM OUTDIR   --charmap work/tools/charmap_en.tsv --charmap work/tools/charmaps/charmap_zh_xzonn_gen4.tsv [--narc a/0/2/7]
python3 work/tools/msgtool.py insert        ROM INDIR OUT.nds --charmap ... [--narc ...]
python3 work/tools/msgtool.py roundtrip     ROM --charmap ... [--narc ...] [--rebuild-rom]
python3 work/tools/msgtool.py charmap-guess (--pairs P.tsv | --rom ROM --bank N --known L.txt [--offset K]) [--charmap ...] [--out G.tsv]
python3 work/tools/msgtool.py charmap-import SRC OUT.tsv [--min HEX --max HEX]
python3 work/tools/msgtool.py patch-preview PATCH OUT.nds [--report R.json]
python3 work/tools/msgtool.py check-base    ROM [--patch P]...
python3 work/tools/msgtool.py glyph         ROM CODE... [--font N]
```

**JSON bank format:**
```
{"bank": N, "seed": S, ["trailer_hex": ...], "strings": [{"id": i, "text": "...", ["pad": k], ["raw_hex": "..."]}]}
```
- `raw_hex` appears only when the text cannot reproduce the exact units, for example junk after the terminator or a missing terminator.
- On insert, `raw_hex` is used only while `text` is unchanged.
- In the charmap stack, later `--charmap` files override earlier ones. When two codes share a character, the lowest code is canonical and the others come out as `{U+XXXX}`, which keeps round trips exact.

**Verified round trips (byte-identical message NARC):**

| Build | NARC | raw_hex strings | `{U+}` tags |
|---|---|---|---|
| v4.0.3 preview | `a/0/2/7` (817 banks) | 0 | 0 |
| v4.0.3 preview | `pbr/msg.narc` | 0 | 0 |
| v4.0.3 preview | `battle/string/battle_string.narc` | 0 | 1 |
| v3 Cn preview | `a/0/2/7` | 2 | 85 |
| v3 Eng preview | `a/0/2/7` | 5 | 1156 |

In v3 Eng most `{U+}` tags are `U+0000`, `U+FF01`, `U+FFFE` or `U+FF00`: broken or overlong commands left by the v3 Eng tool, plus the 450 bytes that depend on the base.

**Tests:** `work/tools/test_msgtool.py` has 23 tests (20 at the time of this pass), all passing. They cover:
- encrypt/decrypt against an independent pret-formula implementation;
- tag, command, `{U+}`, compressed-string and mixed Latin+CJK round trips;
- `pad`, `trailer` and `raw_hex` handling;
- NARC quirks;
- a synthetic ROM run end to end through extract → edit → insert and `roundtrip --rebuild-rom`;
- `charmap-guess`.

---

## 7. Using v3 Eng as translation memory (plan)
- **Coverage:** v3 Eng is **unfinished**, "until Cerulean". Of the v3 Cn strings that contain CJK, 17,655 are CJK-free in v3 Eng and 34,476 still contain Chinese.
  - 120 banks are fully translated and 10 partially; 642 are untranslated.
  - Banks are mixed-language, and the extractor handles that: the stacked charmap decodes Latin and CJK together.
- **Harvesting:** for each (bank, id), pair v3 Cn and v3 Eng, both decoded with the ACG table. Keep a pair only if the English side has no CJK and differs from the Chinese side. Store it keyed on the *Chinese text*, not on the code units or bank/id, because banks and tables changed in v4.
- **Matching into v4:** decode v4 with the Xzonn table. Match exact Chinese strings first, then fuzzy matches, and flag v4 strings whose Chinese changed.
- **Quality:** v3 Eng has broken commands (`{U+FFFE}` fragments). Treat its lines as suggestions and validate the `{VAR}` tags against the Chinese source.

---

## 8. Open questions / next steps

All answered since (review 2026-09-29):
- 1: the base is the USA dump, CRC32 `C180A0E9`; v4.0.3 Cn and v3 Eng apply cleanly (`credits_and_sources.md`).
- 2: the v3 English is u/Shake69's, reused with their permission (`credits_and_sources.md`).
- 3: v4 is credited as built on hg-engine (`credits_and_sources.md`), but its data formats are not stock hg-engine (`work/docs/README.md`, "Data sources").
- 4: box widths are measured in `text_metrics.md`, and `qa.py wrap` is the wrapper.
- 5: graphics are inventoried and patched (`graphics_inventory.md`).
- 6: the bank maps are `work/translate/bank_map_v3_v4.json` and `bank_map_us_v4.json` (`tm_and_manifest.md`).
- 7: not pursued; v3 was only needed as translation memory.

The original list:

1. **Base ROM:** run `check-base` on the user's USA dump (expected), and on the JP dump if the USA one fails.
2. **v3 Eng credits:** read the Reddit thread body (blocked for us) for the translator's name and permission to reuse the v3 Eng work.
3. **Engine:** is the v4 engine derived from hg-engine or another English base? Check the extra FS paths (`battle/string/`, `extra/`, `data/clothes*/`, `pokepic_m/f.narc`, 1439-entry species bank). That affects where hardcoded strings live.
4. **Line widths:** measure message-box widths and the Latin width behaviour of the patched renderer, then build the wrapper.
5. **Graphics text:** inventory graphics with baked-in Chinese text (§5).
6. **Bank maps:** v3 (814) → v4 (817) and US → v4.
7. **v3 codes:** recover the 85 v3 codes missing from the ACG table, using `glyph` + `charmap-guess`.
