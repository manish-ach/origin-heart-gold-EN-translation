#!/usr/bin/env python3
"""textmetrics - pixel metrics for 起源心金 (Origin HeartGold v4.0.3) message text.

Shared by qa.py (checks, auto-wrap) and ws.py. Also regenerates font_widths.json:

    python3 work/tools/textmetrics.py build-widths work/rom/preview_v4.nds [--vanilla DIR]
    python3 work/tools/textmetrics.py width "Some {VAR:0101:0,0} text" [--font 1]

Facts used here (see work/notes/text_metrics.md):
  * font NARC a/0/1/6; font 0 = FONT_SYSTEM, 1 = FONT_MESSAGE (dialogue), 2/4 = other UI fonts.
  * glyph advance = width-table byte (includes the 1px shadow column); letterSpacing = 0 for all
    fonts (pret src/font.c sFontInfos), so a string's width is the plain sum of glyph widths.
  * hanzi (codes >= 0x200) are outside the 512-entry width table and render at a fixed width
    (12 px; 13 px in font 4).
  * standard dialogue / battle message window: 27x4 tiles = 216x32 px -> 2 lines of 16 px.
  * control codes (pret src/render_text.c): 0x25BC = {SCROLL} tag = wait, CLEAR box, restart at the
    top line (pret "\\r"); 0x25BD = {CLEAR} tag = wait, scroll up ONE line and continue on the
    current (bottom) line (pret "\\f"). NB the msgtool tag names are the other way round from
    the behaviour; the tags are just labels, the behaviour here is what the engine does.
"""
from __future__ import annotations

import argparse
import json
import re
import struct
import sys
from functools import lru_cache
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
WIDTHS_PATH = TOOLS / "font_widths.json"
CONFIG_PATH = TOOLS / "qa_config.json"
CHARMAP_EN = TOOLS / "charmap_en.tsv"
CHARMAP_ZH = TOOLS / "charmaps" / "charmap_zh_xzonn_gen4.tsv"

LAYOUT_TAGS = ("NEWLINE", "SCROLL", "CLEAR")
TAG_RE = re.compile(r"\{([^{}]*)\}")
# CJK ideographs, kana, hangul, CJK symbols/punctuation, full-width forms
CJK_RE = re.compile(r"[⺀-⿿぀-ヿ㄀-ㇿ㐀-䶿一-鿿가-힯豈-﫿]")
FULLWIDTH_RE = re.compile(r"[　-〿！-｠￠-￮《》]")


# --------------------------------------------------------------------------------------
# tokenising
# --------------------------------------------------------------------------------------

def tokenize(text: str):
    """-> list of (kind, value): kind in {'text','layout','var','tag'}.
    'layout' value = NEWLINE/SCROLL/CLEAR; 'var' value = 'VAR:XXXX[:args]'; 'tag' = other {..}.
    A literal '\\n' counts as NEWLINE (msgtool accepts it on insert)."""
    out = []
    pos = 0
    for m in TAG_RE.finditer(text):
        if m.start() > pos:
            _plain(text[pos:m.start()], out)
        t = m.group(1)
        if t in LAYOUT_TAGS:
            out.append(("layout", t))
        elif t.startswith("VAR:"):
            out.append(("var", t))
        else:
            out.append(("tag", t))
        pos = m.end()
    if pos < len(text):
        _plain(text[pos:], out)
    return out


def _plain(s, out):
    parts = s.split("\n")
    for i, p in enumerate(parts):
        if i:
            out.append(("layout", "NEWLINE"))
        if p:
            out.append(("text", p))


def var_cmd(tag: str) -> int:
    return int(tag.split(":")[1], 16)


def var_args(tag: str):
    parts = tag.split(":")
    return [int(a, 0) for a in parts[2].split(",")] if len(parts) > 2 and parts[2] else []


def non_layout_tags(text: str):
    """All {..} tags except NEWLINE/SCROLL/CLEAR, in order (VAR:..., COMPRESSED, U+XXXX)."""
    return [v for k, v in tokenize(text) if k in ("var", "tag")]


def layout_tags(text: str):
    return [v for k, v in tokenize(text) if k == "layout"]


def visible_text(text: str) -> str:
    return "".join(v for k, v in tokenize(text) if k == "text")


# --------------------------------------------------------------------------------------
# config + widths
# --------------------------------------------------------------------------------------

@lru_cache(maxsize=None)
def load_widths(path: str | None = None) -> dict:
    return json.loads(Path(path or WIDTHS_PATH).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def load_config(path: str | None = None) -> dict:
    return json.loads(Path(path or CONFIG_PATH).read_text(encoding="utf-8"))


def compressed_spec(narc: str, bank: int, cfg: dict | None = None) -> dict | None:
    """qa_config.json "compressed_banks" entry for a bank (names stored {COMPRESSED}), or None."""
    cfg = cfg or load_config()
    spec = cfg.get("compressed_banks", {}).get("%s/%04d" % (narc, bank))
    if spec is None:
        return None
    return {"raw_ids": set(spec.get("raw_ids", [])), "raw_max_chars": spec.get("raw_max_chars", 7),
            "max_units": spec.get("max_units", 8)}


def font_set(name: str | None = None) -> dict:
    """One font set from font_widths.json: 'hack_v4' (the v4.0.3 ROM as shipped) or 'vanilla_us'.
    Default: qa_config.json "font_set", else the file's default_set."""
    full = load_widths()
    name = name or load_config().get("font_set") or full["default_set"]
    fs = full["font_sets"][name]
    fs.setdefault("name", name)
    return fs


def char_width(ch: str, font: int = 1, widths: dict | None = None):
    """Pixel advance of one character, or None if the font has no glyph for it (width 0).
    widths = a font set (see font_set())."""
    w = widths or font_set()
    f = w["fonts"][str(font)]
    if ch in f["widths"]:
        v = f["widths"][ch]
        return v if v > 0 else None
    if CJK_RE.match(ch) or FULLWIDTH_RE.match(ch):
        return f["cjk_width"]
    return None


def var_width(tag: str, cfg: dict | None = None, narc: str | None = None, which: str = "typ") -> int:
    """Estimated pixel width of a {VAR:...} placeholder once expanded.
    which = 'typ' (typical) or 'max' (worst case)."""
    cfg = cfg or load_config()
    vw = cfg["var_widths"]
    cmd = var_cmd(tag)
    key = "%04X" % cmd
    table = dict(vw["by_cmd"])
    if narc and narc in vw.get("by_narc", {}):
        table.update(vw["by_narc"][narc])
    if key in table:
        e = table[key]
        return e[which] if isinstance(e, dict) else int(e)
    hi, lo = cmd >> 8, cmd & 0xFF
    if hi in (0x02, 0xFF):          # YESNO/PAUSE/WAIT/CURSOR/ALIGN/COLOR/SIZE: no glyphs
        return 0
    if hi == 0x01 and 0x32 <= lo <= 0x3B:   # STRVAR_1 number kinds: digits = kind - 49
        return (lo - 49) * vw["digit_px"]
    e = vw["default"]
    return e[which]


def measure_lines(text: str, font: int = 1, cfg: dict | None = None, narc: str | None = None,
                  which: str = "typ", widths: dict | None = None):
    """Split text on layout tags and measure each line.
    -> list of dicts {px, has_var, missing:[chars], text, brk} where brk is the layout tag that ENDS
    the line (None for the last line). Handles CURSOR_X (0x0203: absolute x); SIZE (0xFF01) changes only the
    height (see page_lines), not the width."""
    cfg = cfg or load_config()
    widths = widths or font_set()
    lines = []
    cur = {"px": 0.0, "has_var": False, "missing": [], "text": "", "brk": None}
    scale = 1.0
    for kind, val in tokenize(text):
        if kind == "layout":
            cur["brk"] = val
            lines.append(cur)
            cur = {"px": 0.0, "has_var": False, "missing": [], "text": "", "brk": None}
            continue
        if kind == "text":
            cur["text"] += val
            for ch in val:
                w = char_width(ch, font, widths)
                if w is None:
                    cur["missing"].append(ch)
                    w = widths["fonts"][str(font)].get("default_width", 6)
                cur["px"] += w * scale
        elif kind == "var":
            cmd = var_cmd(val)
            args = var_args(val)
            if cmd == 0x0203 and args:        # CURSOR_X: absolute pixel x
                cur["px"] = float(args[0])
            elif cmd == 0xFF01 and args:      # SIZE (percent): taller glyphs only; the width stays 1x
                pass                          # (seen in game: 200 % text is as wide as normal text; the
                                              # Chinese 16-glyph 200 % shouts fit the 216 px box only at 1x)
            else:
                w = var_width(val, cfg, narc, which)
                if w:
                    cur["has_var"] = True
                cur["px"] += w * scale
            cur["text"] += "{" + val + "}"
        else:
            cur["text"] += "{" + val + "}"
    lines.append(cur)
    for ln in lines:
        ln["px"] = int(round(ln["px"]))
    return lines


def text_width(text: str, font: int = 1, **kw) -> int:
    """Width of the widest line."""
    return max(ln["px"] for ln in measure_lines(text, font, **kw))


def page_lines(text: str):
    """Simulate the text printer's line position. -> max line slots used in any box view.
    NEWLINE: next line; {SCROLL} (0x25BC): clear, y=0; {CLEAR} (0x25BD): scroll one line, y kept.
    SIZE (0xFF01) above 100% makes a line taller: a 200% line takes 2 slots and the next line starts 2 slots
    lower. The printer does not clip at the bottom of the window: a line past it is drawn over the memory
    after the window's pixel buffer (heap corruption, crash; rc3 Misty scene, work/notes/heap_audit.md)."""
    y = 0
    pending = 0          # slots to move down at the next printable (a trailing NEWLINE is harmless)
    maxy = 0
    scale = 1            # current SIZE, in line slots (200% -> 2)
    cur_h = 1            # slots used by the line being printed
    for kind, val in tokenize(text):
        if kind == "layout":
            if val == "NEWLINE":
                pending += cur_h
                cur_h = 1
            elif val == "SCROLL":
                y, pending, cur_h = 0, 0, 1
            else:   # CLEAR = scroll one line; the printer stays on its current line
                y += pending
                pending = 0
            continue
        if kind == "var" and var_cmd(val) == 0xFF01:
            args = var_args(val)
            scale = max(1, -(-(args[0] if args else 100) // 100))
            continue
        if kind == "text" or (kind == "var" and (var_cmd(val) >> 8) not in (0x02, 0xFF)):
            y += pending
            pending = 0
            cur_h = max(cur_h, scale)
            maxy = max(maxy, y + cur_h - 1)
    return maxy + 1


# --------------------------------------------------------------------------------------
# building font_widths.json from a ROM
# --------------------------------------------------------------------------------------

FONT_ROLES = {0: "FONT_SYSTEM (menus/UI)", 1: "FONT_MESSAGE (dialogue, battle messages)",
              2: "FONT_SPECIAL", 3: "unused vanilla-size font (509 glyphs)", 4: "FONT_UNOWN/other UI"}


def _read_font(data: bytes):
    hs, wo, cnt, mw, mh, tw, th = struct.unpack_from("<IIIBBBB", data, 0)
    return {"hdr": hs, "wo": wo, "count": cnt, "max_w": mw, "max_h": mh, "tiles": (tw, th), "data": data}


def _font_table(narc_files, cm, fi):
    f = _read_font(narc_files[fi])
    d = f["data"]
    widths, missing = {}, []
    for ch, code in sorted(cm.enc.items(), key=lambda kv: kv[1]):
        if not (0 < code <= f["count"]) or len(ch) != 1 or ch == "\n":
            continue
        w = d[f["wo"] + code - 1]
        widths[ch] = w
        if w == 0 and 0x121 <= code <= 0x1EA:
            missing.append(ch)
    return {"role": FONT_ROLES.get(fi), "glyphs": (len(d) - f["hdr"]) // (16 * f["tiles"][0] * f["tiles"][1]),
            "width_table_len": f["count"], "cjk_width": 13 if fi == 4 else 12, "default_width": 6,
            "missing_latin": missing, "widths": widths}


def build_widths(rom_path: str, us_rom: str | None = None) -> dict:
    """Width tables for the hack ROM ('hack_v4') and, if given, the vanilla US ROM ('vanilla_us')."""
    sys.path.insert(0, str(TOOLS))
    import msgtool as m
    cm = m.Charmap.load([str(CHARMAP_EN)])
    out = {"note": "width = glyph advance in px incl. 1px shadow column; letterSpacing is 0 for every font "
                   "(pret src/font.c), so string width = sum of advances. Characters from charmap_en.tsv. "
                   "0 = no glyph (blank). cjk_width = fixed hanzi advance (hanzi are outside the 512-entry table).",
           "default_set": "vanilla_us" if us_rom else "hack_v4", "font_sets": {}}
    for name, path in (("hack_v4", rom_path), ("vanilla_us", us_rom)):
        if not path:
            continue
        narc = m.Narc.parse(m.get_file(m.load_rom(path), m.FONT_NARC_PATH))
        out["font_sets"][name] = {"source": str(path), "narc": m.FONT_NARC_PATH,
                                  "fonts": {str(fi): _font_table(narc.files, cm, fi) for fi in (0, 1, 2, 4)
                                            if fi < len(narc.files)}}
    if us_rom:
        diffs = {}
        for fi, hf in out["font_sets"]["hack_v4"]["fonts"].items():
            vf = out["font_sets"]["vanilla_us"]["fonts"].get(fi)
            if not vf:
                continue
            d = {ch: {"vanilla_us": vf["widths"].get(ch), "hack_v4": w} for ch, w in hf["widths"].items()
                 if cm.enc[ch] >= 0x121 and vf["widths"].get(ch) != w}
            diffs[fi] = d
        out["latin_width_diffs_hack_vs_vanilla"] = diffs
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-widths")
    b.add_argument("rom")
    b.add_argument("--us", help="vanilla US HeartGold ROM (adds the 'vanilla_us' set and a diff)")
    b.add_argument("--out", default=str(WIDTHS_PATH))
    w = sub.add_parser("width")
    w.add_argument("text")
    w.add_argument("--font", type=int, default=1)
    a = ap.parse_args(argv)
    if a.cmd == "build-widths":
        res = build_widths(a.rom, a.us)
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
        print("wrote", a.out)
    else:
        for ln in measure_lines(a.text, a.font):
            print(ln["px"], repr(ln["text"]), ln["brk"] or "", ("missing " + "".join(ln["missing"])) if ln["missing"] else "")


if __name__ == "__main__":
    main()
