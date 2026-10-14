#!/usr/bin/env python3
"""verify - re-read a ROM with the advanced trainer AI installed and check every part of the installation.

    .venv/bin/python work/advanced-ai/builder/verify.py ROM [--input ROM] [--payload DIR] [--marks JSON] [--json OUT]

Independent of install.py and of ndspy: it parses the NDS header, the FAT and FNT, the y9 overlay table, the
ARM9 module parameters and autoload table, and the a/0/5/5 NARC with its own code, and disassembles every hook with
capstone. It checks (docs/build-contract.md, "Installer and verifier"):

- the ROM layout: header CRC, every file inside the ROM, no two files or tables overlapping;
- the autoload table: ITCM, DTCM, difficulty's section, then the AI's itcm and main sections, each equal to the
  payload's bytes and bss, none overlapping another; every other section in ITCM (the hack's block with text speed
  and trainer display) ends at or below the AI's itcm origin; the itcm bss stops before the fixed records;
- the arena words: the payload's values; the ITCM arena empty; the main arena ending where region main starts and
  still holding the root heaps (the heap table at 0x020F2EAC);
- each hook: capstone reads a Thumb `bl` to its target symbol;
- overlay 10: its y9 entry (RAM, size, bss, overlay 11's static initialisers, uncompressed); its first 0x12060
  bytes equal overlay 11, then 0x20 zero bytes, then slot.bin; inside the battle slot; overlay 11 the hack's;
- a/0/5/5: byte 2 of every header holds the trainer's marks (bit 0 important, bit 1 keep lead), 0 elsewhere.

With --input (the ROM the installer read), it also checks that nothing else changed: every other ROM file, the
ARM7 binary, the banner, the FNT, the other y9 entries, the arm9 main section outside the two words, the input's
autoload sections, overlay 14 outside the hook sites and a/0/5/5 outside byte 2 of the marked records; the header
outside the fields saving moves, and 0x160-0x3FFF outside the used-size copy; and that the input's ITCM arena started
at its ITCM end, at or below the AI's itcm origin.

Exit 0 when every check passes, 1 otherwise (each failure is printed).
"""
import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DIR = HERE.parent
DEF_PAYLOAD = AI_DIR / "payload"
DEF_MARKS = AI_DIR / "data" / "trainer_marks.json"

OVERLAY11_SHA256 = "d2b35343756f9b3ca457db7cdfe8b59901a667173c1f71072b32ab11a1db7508"   # Chinese v4.0.3
OV11_SIZE, OV11_BSS = 0x12060, 0x20
ITCM_LO, ITCM_HI = 0x01FF8000, 0x02000000
ARM9_BASE = 0x02000000
MODULE_PARAMS_AT = 0xBA0
NITRO_MAGIC = struct.pack("<2I", 0xDEC00621, 0x2106C0DE)
ORIGINAL_AUTOLOADS = (0x01FF8000, 0x027E0000, 0x023DC000)     # ITCM (text speed), DTCM, difficulty
ITCM_ARENA_START, MAIN_ARENA_START, MAIN_ARENA_END = 0x020D1A28, 0x020D1A1C, 0x020D1970
ROOT_HEAPS = 0x020F2EAC
SLOT_OVERLAY, ENGINE_OVERLAY = 8, 14


def h32(x):
    return f"0x{x:08X}"


def as_int(v):
    return int(v, 16) if isinstance(v, str) else int(v)


def crc16(data):
    """CRC-16/MODBUS, the NDS header checksum."""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class NdsImage:
    """A raw NDS ROM read field by field (GBATEK layout)."""

    def __init__(self, data):
        self.data = data
        u32 = lambda o: struct.unpack_from("<I", data, o)[0]   # noqa: E731
        self.arm9_off, self.arm9_entry, self.arm9_ram, self.arm9_size = (u32(0x20 + 4 * i) for i in range(4))
        self.arm7_off, self.arm7_entry, self.arm7_ram, self.arm7_size = (u32(0x30 + 4 * i) for i in range(4))
        self.fnt = (u32(0x40), u32(0x44))
        self.fat = (u32(0x48), u32(0x4C))
        self.y9 = (u32(0x50), u32(0x54))
        self.y7 = (u32(0x58), u32(0x5C))
        self.banner_off = u32(0x68)
        self.used_size = u32(0x80)
        n = self.fat[1] // 8
        self.files = [struct.unpack_from("<2I", data, self.fat[0] + 8 * i) for i in range(n)]

    def file(self, i):
        s, e = self.files[i]
        return self.data[s:e]

    def blob(self, span):
        return self.data[span[0]:span[0] + span[1]]

    def arm9(self):
        return self.data[self.arm9_off:self.arm9_off + self.arm9_size]

    def arm7(self):
        return self.data[self.arm7_off:self.arm7_off + self.arm7_size]

    def banner(self):
        """The icon/title block; its size follows its version (1: 0x840, 2: 0x940, 3: 0xA40, 0x103: 0x23C0)."""
        if not self.banner_off:
            return b""
        version = struct.unpack_from("<H", self.data, self.banner_off)[0]
        size = {1: 0x840, 2: 0x940, 3: 0xA40, 0x103: 0x23C0}.get(version, 0x840)
        return self.data[self.banner_off:self.banner_off + size]

    def y9_entries(self):
        t = self.blob(self.y9)
        return {e[0]: e for e in (struct.unpack_from("<8I", t, o) for o in range(0, len(t), 32))}

    def paths(self):
        """{path: file id} from the FNT (directory tables, then sub-tables of names)."""
        fnt = self.blob(self.fnt)
        out = {}

        def walk(dir_id, prefix):
            sub, first, _ = struct.unpack_from("<IHH", fnt, 8 * (dir_id & 0xFFF))
            pos, fid = sub, first
            while True:
                n = fnt[pos]
                pos += 1
                if n == 0:
                    return
                name = fnt[pos:pos + (n & 0x7F)].decode("latin-1")
                pos += n & 0x7F
                if n & 0x80:
                    child = struct.unpack_from("<H", fnt, pos)[0]
                    pos += 2
                    walk(child, prefix + name + "/")
                else:
                    out[prefix + name] = fid
                    fid += 1
        walk(0xF000, "")
        return out


class Arm9:
    """The ARM9 binary: module parameters, the main section and the autoload sections."""

    def __init__(self, blob, ram):
        self.blob, self.ram = blob, ram
        at = blob.find(NITRO_MAGIC)
        self.params_at = at - 0x1C if at >= 0 else None
        p = struct.unpack_from("<7I", blob, self.params_at) if self.params_at is not None else (0,) * 7
        self.list_start, self.list_end, self.data_start, self.bss_start, self.bss_end = p[:5]
        self.main = blob[:self.data_start - ram]
        self.sections = []
        src = self.data_start - ram
        for o in range(self.list_start - ram, self.list_end - ram, 12):
            dest, size, bss = struct.unpack_from("<3I", blob, o)
            self.sections.append({"ram": dest, "size": size, "bss": bss, "data": blob[src:src + size]})
            src += size
        self.table_at = src          # the autoload data ends where the table starts

    def word(self, address):
        return struct.unpack_from("<I", self.main, address - ARM9_BASE)[0]


def narc_records(narc):
    """The members of a NARC (its own parsing: BTAF, BTNF, GMIF)."""
    if narc[:4] != b"NARC":
        raise ValueError("not a NARC")
    pos = struct.unpack_from("<H", narc, 12)[0]
    btaf_size, count = struct.unpack_from("<IH", narc, pos + 4)
    spans = [struct.unpack_from("<2I", narc, pos + 12 + 8 * i) for i in range(count)]
    pos += btaf_size
    pos += struct.unpack_from("<I", narc, pos + 4)[0]       # BTNF
    if narc[pos:pos + 4] != b"GMIF":
        raise ValueError("NARC without GMIF")
    img = pos + 8
    return [(img + s, img + e) for s, e in spans]


def thumb_bl_target(code, address):
    """The target of the Thumb BL at address, read by capstone (None if it is not a BL)."""
    from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
    ins = list(Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(code, address))
    if len(ins) != 1 or ins[0].mnemonic != "bl" or ins[0].size != 4:
        return None
    return int(ins[0].op_str.lstrip("#"), 16)


class Checker:
    def __init__(self):
        self.errors, self.passed = [], []

    def __call__(self, name, ok, detail=""):
        (self.passed if ok else self.errors).append(name if ok else f"{name}: {detail}" if detail else name)
        return ok


def load_payload(directory):
    """payload.json and its .bin files, with the names of the files whose sha256 is not payload.json's."""
    directory = Path(directory)
    p = json.loads((directory / "payload.json").read_text())
    bins = {name: (directory / r["file"]).read_bytes() for name, r in p["regions"].items() if "file" in r}
    bad = [p["regions"][name]["file"] for name, b in bins.items()
           if hashlib.sha256(b).hexdigest() != p.get("files", {}).get(p["regions"][name]["file"])]
    return p, bins, bad


# Header fields that saving a ROM may move (ndspy lays the container out again): checked against the parsed layout
MOVABLE_HEADER = {0x2C: "ARM9 size", 0x30: "ARM7 ROM offset", 0x40: "FNT offset", 0x48: "FAT offset",
                  0x50: "ARM9 overlay table offset", 0x68: "banner offset", 0x80: "used ROM size"}
USED_SIZE_COPY = 0x1000           # a copy of the used ROM size in the header padding (ndspy's container pointer)


def verify(data, payload_dir=DEF_PAYLOAD, marks_path=DEF_MARKS, input_data=None, overlay11_sha256=OVERLAY11_SHA256):
    """Check an installed ROM (bytes). Returns {"ok", "errors", "checked", "rom", ...}."""
    p, bins, bad_bins = load_payload(payload_dir)
    marks = json.loads(Path(marks_path).read_text())
    check = Checker()
    check("payload .bin files match payload.json", not bad_bins, str(bad_bins))
    rom = NdsImage(data)
    R = {k: v for k, v in p["regions"].items()}
    ram = {k: as_int(v["ram"]) for k, v in R.items()}
    symbols = {k: as_int(v) for k, v in p["symbols"].items()}
    u32 = lambda d, o: struct.unpack_from("<I", d, o)[0]   # noqa: E731

    # -- ROM layout --------------------------------------------------------------------------------------------
    check("header CRC", crc16(data[:0x15E]) == struct.unpack_from("<H", data, 0x15E)[0])
    check("ROM size covers the used area", rom.used_size <= len(data))
    check("used-size copy at 0x1000", u32(data, USED_SIZE_COPY) == rom.used_size)
    spans = [("arm9", rom.arm9_off, rom.arm9_size), ("arm7", rom.arm7_off, rom.arm7_size),
             ("fnt", *rom.fnt), ("fat", *rom.fat), ("y9", *rom.y9), ("y7", *rom.y7),
             ("banner", rom.banner_off, len(rom.banner()))]
    spans += [(f"file {i}", s, e - s) for i, (s, e) in enumerate(rom.files) if e > s]
    inside = all(0x4000 <= s and s + n <= rom.used_size for _, s, n in spans if n)
    check("every file and table inside the ROM", inside)
    ordered = sorted((s, s + n, name) for name, s, n in spans if n)
    clashes = [(a[2], b[2]) for a, b in zip(ordered, ordered[1:]) if b[0] < a[1]]
    check("no two files or tables overlap", not clashes, str(clashes[:3]))

    # -- ARM9 autoloads ------------------------------------------------------------------------------------------
    arm9 = Arm9(rom.arm9(), rom.arm9_ram)
    check("ARM9 module parameters at 0xBA0", arm9.params_at == MODULE_PARAMS_AT, str(arm9.params_at))
    hook = u32(data, 0x70)
    check("header autoload hook points at the module parameters",
          0 <= hook - 4 - rom.arm9_ram < len(arm9.main) and arm9.word(hook - 4) == ARM9_BASE + MODULE_PARAMS_AT)
    check("ARM9 entry inside the main section", ARM9_BASE <= rom.arm9_entry < ARM9_BASE + len(arm9.main))
    check("ARM9 size ends at the autoload table", rom.arm9_size == arm9.list_end - arm9.ram)
    check("main section ends at the BSS start", arm9.bss_start == arm9.data_start)
    y9 = rom.y9_entries()
    lowest_overlay = min((e[1] for e in y9.values()), default=0)
    check("BSS ends at or below the lowest overlay", arm9.data_start <= arm9.bss_end <= lowest_overlay)
    check("autoload table follows the autoload data", arm9.table_at == arm9.list_start - arm9.ram)
    want_order = list(ORIGINAL_AUTOLOADS) + [ram["itcm"], ram["main"]]
    have_order = [s["ram"] for s in arm9.sections]
    check("autoload sections: ITCM, DTCM, difficulty, AI itcm, AI main", have_order == want_order,
          str([h32(a) for a in have_order]))
    by_ram = {s["ram"]: s for s in arm9.sections}
    for name in ("itcm", "main"):
        s = by_ram.get(ram[name])
        check(f"autoload {name}: payload bytes and bss",
              s is not None and s["data"] == bins[name] and s["bss"] == R[name]["bss"] and s["size"] % 4 == 0 and
              s["bss"] % 4 == 0)
    dests = sorted((s["ram"], s["ram"] + s["size"] + s["bss"]) for s in arm9.sections)
    check("no two autoload destinations overlap", all(b[0] >= a[1] for a, b in zip(dests, dests[1:])))
    itcm_block = by_ram.get(ITCM_LO)
    others_in_itcm = [s["ram"] + s["size"] + s["bss"] for s in arm9.sections
                      if ITCM_LO <= s["ram"] < ITCM_HI and s["ram"] != ram["itcm"]]
    check("every other ITCM section ends at or below the AI's itcm origin", itcm_block is not None and
          max(others_in_itcm) <= ram["itcm"], f"ends at {h32(max(others_in_itcm, default=0))}")
    code_end = ram["itcm"] + R["itcm"]["size"]
    work = (ram["itcm_ram"], ram["itcm_ram"] + R["itcm_ram"]["size"])
    fixed_records = as_int(R["itcm_ram"]["limit"])
    check("AI itcm code below its limit and its work RAM, inside ITCM",
          code_end <= as_int(R["itcm"]["limit"]) <= work[0] and work[1] <= fixed_records <= ITCM_HI)
    itcm_sec = by_ram.get(ram["itcm"])
    bss_end = code_end + (itcm_sec["bss"] if itcm_sec else 0)
    check("AI itcm bss stops before the fixed records", bss_end <= fixed_records, f"ends at {h32(bss_end)}")
    check("AI itcm bss is none, or covers the work RAM", itcm_sec is not None and
          (itcm_sec["bss"] == 0 or bss_end >= work[1]), f"ends at {h32(bss_end)}, work RAM ends at {h32(work[1])}")

    # -- arena words -----------------------------------------------------------------------------------------------
    for w in p["words"]:
        a = as_int(w["address"])
        check(f"word {h32(a)} = {w['after']}", arm9.main[a - ARM9_BASE:a - ARM9_BASE + 4] == bytes.fromhex(w["after"]))
    check("ITCM arena empty (starts at the end of ITCM)", arm9.word(ITCM_ARENA_START) == ITCM_HI)
    lo, hi = arm9.word(MAIN_ARENA_START), arm9.word(MAIN_ARENA_END)
    main_end = ram["main"] + R["main"]["size"] + R["main"]["bss"]
    diff = by_ram.get(ORIGINAL_AUTOLOADS[2])
    check("main arena ends at region main, which ends at difficulty's section",
          hi == ram["main"] and diff is not None and main_end <= diff["ram"])
    overlay_end = max((e[1] + e[2] + e[3] for e in y9.values()), default=0)
    check("main arena starts above the BSS and every overlay", max(arm9.bss_end, overlay_end) <= lo < hi)
    heaps = struct.unpack_from("<8I", arm9.main, ROOT_HEAPS - ARM9_BASE)
    check("root heaps fit the main arena", sum(heaps[0::2]) < hi - lo and not any(heaps[1::2]),
          f"{sum(heaps[0::2])} bytes of heaps, arena {hi - lo}")

    # -- overlays --------------------------------------------------------------------------------------------------
    e10, e11, e8, e14 = (y9.get(i) for i in (10, 11, SLOT_OVERLAY, ENGINE_OVERLAY))
    missing = [i for i, e in ((10, e10), (11, e11), (SLOT_OVERLAY, e8), (ENGINE_OVERLAY, e14)) if e is None]
    check("y9 entries for overlays 8, 10, 11 and 14", not missing, f"missing {missing}")
    ov10 = p["overlay10"]
    image = rom.file(e10[6]) if e10 else b""
    ov11 = rom.file(e11[6]) if e11 else b""
    ov14 = rom.file(e14[6]) if e14 else b""
    check("overlay 11 is the hack's", hashlib.sha256(ov11).hexdigest() == overlay11_sha256)
    check("y9 entry 11", e11 is not None and e11[1:4] == (as_int(ov10["ram"]), OV11_SIZE, OV11_BSS) and e11[7] == 0)
    check("y9 entry 10: RAM, size, bss, static initialisers, uncompressed",
          e10 is not None and e11 is not None and e10[1] == as_int(ov10["ram"]) and e10[2] == len(image) ==
          OV11_SIZE + OV11_BSS + len(bins["slot"]) and e10[3] == as_int(ov10["bss"]) and
          e10[4:6] == e11[4:6] and e10[7] == 0)
    check("overlay 10 = overlay 11, 0x20 zero bytes, slot.bin",
          bool(image) and image[:OV11_SIZE] == ov11 and image[OV11_SIZE:OV11_SIZE + OV11_BSS] == bytes(OV11_BSS) and
          image[OV11_SIZE + OV11_BSS:] == bins["slot"])
    check("region slot starts after overlay 11's image and bss", ram["slot"] == as_int(ov10["ram"]) + OV11_SIZE + OV11_BSS)
    if not missing:
        end10 = e10[1] + e10[2] + e10[3]
        slot = (e8[1], e8[1] + e8[2] + e8[3])
        check("overlay 10 inside the battle slot, which ends at overlay 14",
              slot[0] <= e10[1] and end10 <= slot[1] == e14[1] == as_int(R["slot"]["limit"]))
        alone = [i for i, e in y9.items() if i not in (10, SLOT_OVERLAY) and e[1] < end10 and e10[1] < e[1] + e[2] + e[3]
                 and not (e[1] < slot[1] and slot[0] < e[1] + e[2] + e[3])]
        check("overlay 10 overlaps only slot overlays", not alone, str(alone))

    # -- hooks (capstone) ------------------------------------------------------------------------------------------
    for hk in p["hooks"]:
        a = as_int(hk["address"])
        off = a - e14[1] if e14 else -1
        target = thumb_bl_target(ov14[off:off + 4], a) if 0 <= off <= len(ov14) - 4 else None
        want = symbols.get(hk["target"], 1) & ~1
        check(f"hook {h32(a)}: bl {hk['target']}", target == want and symbols.get(hk["target"], 0) & 1,
              f"found {h32(target) if target is not None else 'no bl'}, want {h32(want)}")

    # -- trainer marks ---------------------------------------------------------------------------------------------
    narc_id = rom.paths().get("a/0/5/5")
    narc = rom.file(narc_id) if narc_id is not None else b""
    records = narc_records(narc) if narc else []
    important, keep = set(marks["important"]), set(marks["keep_lead"])
    want = [(1 if i in important else 0) | (2 if i in keep else 0) for i in range(len(records))]
    have = [narc[s + 2] for s, _ in records]
    check("a/0/5/5 records are 20 bytes", records and all(e - s == 20 for s, e in records))
    check("trainer header byte 2 = marks", have == want and 0 not in important | keep,
          f"{sum(a != b for a, b in zip(have, want))} records differ")

    # -- nothing else changed --------------------------------------------------------------------------------------
    if input_data is not None:
        old = NdsImage(input_data)
        old9 = Arm9(old.arm9(), old.arm9_ram)
        moved = {o + k for o in MOVABLE_HEADER for k in range(4)}
        header_diff = [o for o in range(0x15E) if data[o] != input_data[o] and o not in moved]
        check("header unchanged except the fields saving moves", not header_diff, str([hex(o) for o in header_diff[:8]]))
        check("moved header fields agree with the layout", rom.used_size == len(data) and
              rom.arm9_size == arm9.list_end - arm9.ram and rom.fnt[1] == old.fnt[1] and rom.fat[1] == old.fat[1] and
              rom.y9[1] == old.y9[1] and rom.arm7_size == old.arm7_size)
        pad = [o for o in range(0x160, 0x4000) if data[o] != input_data[o] and not USED_SIZE_COPY <= o < USED_SIZE_COPY + 4]
        check("header padding 0x160-0x3FFF unchanged except the used-size copy", not pad, str([hex(o) for o in pad[:8]]))
        check("ARM9 footer after the binary unchanged",
              data[rom.arm9_off + rom.arm9_size:rom.arm9_off + rom.arm9_size + 12] ==
              input_data[old.arm9_off + old.arm9_size:old.arm9_off + old.arm9_size + 12])
        check("ARM7 binary unchanged", rom.arm7() == old.arm7() and rom.blob(rom.y7) == old.blob(old.y7))
        check("banner unchanged", rom.banner() == old.banner())
        check("FNT unchanged", rom.blob(rom.fnt) == old.blob(old.fnt))
        check("file count unchanged", len(rom.files) == len(old.files))
        oy9 = old.y9_entries()
        check("y9 unchanged except entry 10", set(oy9) == set(y9) and all(oy9[i] == y9[i] for i in y9 if i != 10))
        if not missing:
            hooks = {as_int(hk["address"]) - e14[1] for hk in p["hooks"]}
            allowed = {e10[6]: None, e14[6]: {o + k for o in hooks for k in range(4)},
                       narc_id: {s + 2 for i, (s, _) in enumerate(records) if want[i]}}
            changed = []
            for i in range(min(len(rom.files), len(old.files))):
                a, b = rom.file(i), old.file(i)
                if a == b or (i in allowed and allowed[i] is None):
                    continue
                if i not in allowed or len(a) != len(b) or any(a[k] != b[k] for k in range(len(a))
                                                               if k not in allowed[i]):
                    changed.append(i)
            check("every other ROM file unchanged; overlay 14 only at the hooks; a/0/5/5 only at byte 2",
                  not changed, str(changed[:5]))
        words = {as_int(w["address"]) - ARM9_BASE + k for w in p["words"] for k in range(4)}
        main_diff = [k for k in range(len(old9.main)) if k < len(arm9.main) and old9.main[k] != arm9.main[k]
                     and k not in words and not MODULE_PARAMS_AT <= k < MODULE_PARAMS_AT + 8]
        check("arm9 main section unchanged except the words and the autoload table pointers",
              len(old9.main) == len(arm9.main) and not main_diff, str([h32(ARM9_BASE + k) for k in main_diff[:5]]))
        old_itcm_end = max((s["ram"] + s["size"] + s["bss"] for s in old9.sections if ITCM_LO <= s["ram"] < ITCM_HI),
                           default=0)
        check("input's ITCM arena started at its ITCM end, at or below the AI's itcm origin",
              old9.word(ITCM_ARENA_START) == old_itcm_end <= ram["itcm"],
              f"word {h32(old9.word(ITCM_ARENA_START))}, ITCM end {h32(old_itcm_end)}, origin {h32(ram['itcm'])}")
        check("input's autoload sections unchanged",
              [(s["ram"], s["data"], s["bss"]) for s in old9.sections] ==
              [(s["ram"], s["data"], s["bss"]) for s in arm9.sections[:len(old9.sections)]])

    return {"ok": not check.errors, "errors": check.errors, "checked": len(check.passed),
            "passed": check.passed,
            "rom": {"size": len(data), "sha1": hashlib.sha1(data).hexdigest(),
                    "sha256": hashlib.sha256(data).hexdigest()}}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("rom")
    ap.add_argument("--input", help="the ROM the installer read: also check that nothing else changed")
    ap.add_argument("--payload", default=DEF_PAYLOAD)
    ap.add_argument("--marks", default=DEF_MARKS)
    ap.add_argument("--json", help="write the report here")
    a = ap.parse_args(argv)
    report = verify(Path(a.rom).read_bytes(), a.payload, a.marks,
                    Path(a.input).read_bytes() if a.input else None)
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1) + "\n")
    for e in report["errors"]:
        print("FAIL", e)
    print(f"{report['checked']} checks passed, {len(report['errors'])} failed")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
