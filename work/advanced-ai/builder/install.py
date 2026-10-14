#!/usr/bin/env python3
"""install - write the advanced trainer AI into a copy of an English Origin HeartGold ROM that has difficulty.

    .venv/bin/python work/advanced-ai/builder/install.py --input ROM --out ROM [--payload DIR] [--marks JSON]
        [--difficulty-receipt JSON]

The input is an English build with the difficulty settings installed (the rc8 release, or a later difficulty
build). The output is a new file: the input is never written. What it writes (docs/build-contract.md, "Installer"):

1. Overlay 10: the input's overlay 11 image, overlay 11's 0x20-byte bss as zeros, then payload slot.bin. Its y9
   entry gets the new size, the payload's bss and overlay 11's static initialisers. The y9 table is patched in
   place, so every other entry keeps its bytes.
2. Two new ARM9 autoload sections, after difficulty's: the payload's itcm and main regions, each with the payload's
   bss. The itcm section's bss runs through the AI's work RAM, so the boot zeroes it; it must stop before the
   fixed records at itcm_ram's limit.
3. The arena words of payload.json `words` (the SDK's initial ITCM arena start and main arena end), each only
   if it holds `before`. The ITCM arena start is the exception: the input's ITCM code (the hack's block, text
   speed, trainer display) ends at a different place per build, so it must equal that end, which must be at or
   below the AI's itcm origin (and at or below `before_max` when the payload gives one). It becomes 0x02000000.
4. The hooks of payload.json `hooks`: a Thumb BL to the target symbol, each only if the site holds `before`.
5. The trainer marks of data/trainer_marks.json: bit 0 (important) and bit 1 (keep lead) of header byte 2 in
   a/0/5/5. Byte 2 must be 0 in every record of the input.
6. A receipt, <out>.receipt.json: input, output, payload and marks hashes; the input's ITCM end and the
   headroom below the AI's itcm origin; the input's difficulty build mode
   (from --difficulty-receipt, else 'release' for the known rc8 release, else 'unknown'); every check; the logical
   writes above, byte range by byte range; and what saving moved in the ROM container (header offsets and sizes,
   the header CRC, the used-size copy at 0x1000, the autoload table pointers, the files' ROM offsets).

It refuses (exit 1, nothing written) an input that already has the AI, one without difficulty (its fourth
autoload section), an overlay 10 or 11 that is not the Chinese hack's, a hook site or word that does not hold
`before`, a region that would overlap an autoload section, an overlay that can be in RAM with the battle slot,
or the arenas, a main arena too small for the root heaps, a trainer header with byte 2 set, and a
--difficulty-receipt for another ROM. It then reopens the output with ndspy, and runs builder/verify.py (its own
parsing) on it before publishing it.

Memory layout and the measurements behind its checks: docs/memory-layout.md.
"""
import argparse
import hashlib
import json
import os
import struct
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import ndspy.code
import ndspy.rom

HERE = Path(__file__).resolve().parent
AI_DIR = HERE.parent
DEF_PAYLOAD = AI_DIR / "payload"
DEF_MARKS = AI_DIR / "data" / "trainer_marks.json"

# The hack's own code, as the English builds keep it (sha256 of the ROM files in the Chinese v4.0.3 ROM).
CN_OVERLAY11_SHA256 = "d2b35343756f9b3ca457db7cdfe8b59901a667173c1f71072b32ab11a1db7508"   # the hack's trainer AI
CN_OVERLAY10_SHA256 = "66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925"   # its 0x20-byte stub

ARM9_RAM = 0x02000000
ITCM_START, ITCM_END = 0x01FF8000, 0x02000000
CODE_SETTINGS = 0xBA0              # _start_ModuleParams: autoload table start/end, data start, bss start/end
# Autoload sections of an input with difficulty: ITCM (with text speed), DTCM, difficulty's resident code.
INPUT_AUTOLOADS = (0x01FF8000, 0x027E0000, 0x023DC000)
# SDK literals (arm9 ARM code, read by OS_GetInitArenaLo/Hi; docs/memory-layout.md): the main arena's start and
# end, the ITCM arena's start.
MAIN_ARENA_LO_WORD = 0x020D1A1C
MAIN_ARENA_HI_WORD = 0x020D1970
ITCM_ARENA_LO_WORD = 0x020D1A28
# The root heaps (InitHeapSystem 0x0201AFDC): 4 x {u32 size, u32 arena} at 0x020F2EAC, all from the main arena.
HEAP_TABLE, HEAP_COUNT = 0x020F2EAC, 4
# What the heap system takes from the main arena at boot besides the root heaps (its tables and the 0x0201AA1C
# allocations): measured on rc8_release.nds, main arena low 0x02264920 -> 0x023C116C, minus the root heaps.
HEAP_OVERHEAD = 0x023C116C - 0x02264920 - (0xD200 + 0x2E600 + 0x10 + 0x11D000)
SLOT_OVERLAY = 8                   # the battle slot's largest overlay: [0x021E4DA0, 0x022007E0), beside overlay 14
TRAINER_NARC = "a/0/5/5"
TRAINER_HEADER = 20
MARK_BYTE = 2
IMPORTANT, KEEP_LEAD = 1, 2


class Refused(Exception):
    """The input, the payload or the marks fail a check: nothing is written."""


def require(cond, message):
    if not cond:
        raise Refused(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def hx(value):
    return f"0x{value:08X}"


def num(text):
    return int(text, 16) if isinstance(text, str) else int(text)


def word_value(text):
    """A word in payload.json: 8 hex digits are its little-endian bytes (as `before` and `after` are written);
    "0x..." is the value itself."""
    if isinstance(text, str) and text.lower().startswith("0x"):
        return int(text, 16)
    raw = bytes.fromhex(text)
    require(len(raw) == 4, f"payload: {text!r} is not a word")
    return struct.unpack("<I", raw)[0]


@dataclass(frozen=True)
class Pins:
    """What the installer expects of the hack's code; the tests' synthetic ROMs bring their own."""
    overlay11_sha256: str = CN_OVERLAY11_SHA256
    overlay10_sha256: str = CN_OVERLAY10_SHA256
    heap_overhead: int = HEAP_OVERHEAD


# ----------------------------------------------------------------------------- payload and marks

class Payload:
    """payload.json and its .bin files, checked against each other (docs/build-contract.md)."""

    def __init__(self, directory):
        self.dir = Path(directory)
        raw = (self.dir / "payload.json").read_bytes()
        self.json_sha256 = sha256(raw)
        p = json.loads(raw)
        require(p.get("format") == 1, "payload.json: format is not 1")
        require(p.get("layout") == "en", f"payload.json: layout {p.get('layout')!r}, the installer takes 'en'")
        self.raw = p
        self.symbols = {name: num(v) for name, v in p["symbols"].items()}
        self.regions = {}
        self.bins = {}
        for name in ("slot", "itcm", "main"):
            r = p["regions"][name]
            data = (self.dir / r["file"]).read_bytes()
            require(sha256(data) == p["files"][r["file"]], f"payload: {r['file']} does not match its sha256")
            require(len(data) == r["size"] and len(data) % 4 == 0, f"payload: {r['file']} size")
            self.bins[name] = data
            self.regions[name] = {"ram": num(r["ram"]), "size": r["size"], "bss": r["bss"],
                                  "limit": num(r["limit"]) if "limit" in r else None}
        r = p["regions"]["itcm_ram"]
        self.regions["itcm_ram"] = {"ram": num(r["ram"]), "size": r["size"], "bss": 0, "limit": num(r["limit"])}
        o = p["overlay10"]
        self.ov10 = {"ram": num(o["ram"]), "bss": num(o["bss"]), "static_init": [num(x) for x in o["static_init"]]}
        require(self.ov10["bss"] == self.regions["slot"]["bss"], "payload: overlay 10 bss is not the slot's bss")
        self.hooks = [dict(h, address=num(h["address"]), before=bytes.fromhex(h["before"])) for h in p["hooks"]]
        # `before` is the word's exact old value, except for the ITCM arena start: the input's ITCM code ends at a
        # different place per build (text speed, trainer display), so that word may give no exact value ("itcm_end",
        # or no `before`) or a ceiling (`before_max`); the installer always requires it to equal the input's ITCM end,
        # at or below the itcm region's origin.
        self.words = []
        for w in p["words"]:
            address, before = num(w["address"]), w.get("before")
            exact = None if before in (None, "itcm_end") else word_value(before)
            require(exact is not None or address == ITCM_ARENA_LO_WORD, f"payload: word {hx(address)} has no before")
            self.words.append(dict(w, address=address, before=exact,
                                   before_max=word_value(w["before_max"]) if "before_max" in w else None,
                                   after=bytes.fromhex(w["after"])))
        require({w["address"] for w in self.words} == {ITCM_ARENA_LO_WORD, MAIN_ARENA_HI_WORD},
                "payload: words must be exactly the ITCM arena start and the main arena end")

    def word(self, address):
        return next(w for w in self.words if w["address"] == address)

    def receipt(self):
        return {"dir": str(self.dir), "payload.json": self.json_sha256, "files": dict(self.raw["files"]),
                "sources": dict(self.raw.get("sources", {})), "toolchain": self.raw.get("toolchain")}


class Marks:
    """data/trainer_marks.json: the important and keep-lead trainer ids."""

    def __init__(self, path):
        self.path = Path(path)
        raw = self.path.read_bytes()
        self.sha256 = sha256(raw)
        m = json.loads(raw)
        require(set(m) == {"important", "keep_lead"}, "marks: keys must be important and keep_lead")
        self.important, self.keep_lead = m["important"], m["keep_lead"]
        for name, ids in m.items():
            require(all(isinstance(i, int) for i in ids) and ids == sorted(set(ids)),
                    f"marks: {name} must be sorted unique integers")
            require(not ids or ids[0] > 0, f"marks: {name} lists trainer 0 (the empty record)")

    def value(self, trainer):
        return (IMPORTANT if trainer in self.important else 0) | (KEEP_LEAD if trainer in self.keep_lead else 0)

    def marked(self):
        return sorted(set(self.important) | set(self.keep_lead))


# ----------------------------------------------------------------------------- encodings

def thumb_bl(site, target):
    """A Thumb BL at site to the Thumb function target (bit 0 set): the two halfwords, little endian."""
    require(target & 1, f"BL target {hx(target)} is not a Thumb symbol")
    offset = (target & ~1) - (site + 4)
    require(-0x400000 <= offset < 0x400000, f"BL at {hx(site)} cannot reach {hx(target)}")
    return struct.pack("<HH", 0xF000 | (offset >> 12) & 0x7FF, 0xF800 | (offset >> 1) & 0x7FF)


def narc_members(data):
    """(start, end) of every member of a NARC in its file (BTAF), checked against GMIF."""
    require(data[:4] == b"NARC", "a/0/5/5 is not a NARC")
    pos = struct.unpack_from("<H", data, 0xC)[0]
    require(data[pos:pos + 4] == b"BTAF", "NARC: no BTAF block")
    count = struct.unpack_from("<H", data, pos + 8)[0]
    fat = [struct.unpack_from("<2I", data, pos + 12 + 8 * i) for i in range(count)]
    pos += struct.unpack_from("<I", data, pos + 4)[0]
    require(data[pos:pos + 4] == b"BTNF", "NARC: no BTNF block")
    pos += struct.unpack_from("<I", data, pos + 4)[0]
    require(data[pos:pos + 4] == b"GMIF", "NARC: no GMIF block")
    base, size = pos + 8, struct.unpack_from("<I", data, pos + 4)[0] - 8
    require(all(0 <= s <= e <= size for s, e in fat), "NARC: member outside GMIF")
    return [(base + s, base + e) for s, e in fat]


def overlap(a, b):
    return a[0] < b[1] and b[0] < a[1]


# ----------------------------------------------------------------------------- the installer

class Install:
    """One installation: checks the input, builds the output in memory, records every write."""

    def __init__(self, data, payload, marks, pins=None):
        self.data, self.payload, self.marks, self.pins = data, payload, marks, pins or Pins()
        self.checks, self.writes = [], []
        self.rom = ndspy.rom.NintendoDSRom(data)
        self.arm = self.rom.loadArm9()
        self.ovs = self.rom.loadArm9Overlays()
        require(self.arm.codeSettingsOffs == CODE_SETTINGS, "arm9: code settings are not at 0xBA0")
        self.main = self.arm.sections[0]
        require(self.main.ramAddress == ARM9_RAM, "arm9: main section is not at 0x02000000")

    def check(self, name, value):
        self.checks.append({"check": name, "value": value})

    def arm9_word(self, address):
        off = address - ARM9_RAM
        require(0 <= off <= len(self.main.data) - 4, f"arm9 word {hx(address)} outside the main section")
        return bytes(self.main.data[off:off + 4])

    def ov14_site(self, address, size=4):
        o = self.ovs[14]
        off = address - o.ramAddress
        require(0 <= off <= len(o.data) - size, f"hook {hx(address)} outside overlay 14")
        return off

    # -- refusals -----------------------------------------------------------------------------------------
    def refuse_installed(self):
        """Any sign of an earlier installation: a clear message, before the other checks would fail."""
        p = self.payload
        found = []
        if len(self.arm.sections) > len(INPUT_AUTOLOADS) + 1:
            found.append(f"{len(self.arm.sections) - 1} autoload sections")
        ours = {p.regions["itcm"]["ram"], p.regions["main"]["ram"]}
        found += [f"an autoload section at {hx(s.ramAddress)}" for s in self.arm.sections[1:] if s.ramAddress in ours]
        if 10 in self.ovs and len(self.rom.files[self.ovs[10].fileID]) != 0x20:
            found.append("overlay 10 is not the 0x20-byte stub")
        for w in p.words:
            if self.arm9_word(w["address"]) == w["after"]:
                found.append(f"arm9 word {hx(w['address'])} already {w['after'].hex()}")
        for h in p.hooks:
            if h["target"] in p.symbols:
                off = self.ov14_site(h["address"])
                if bytes(self.ovs[14].data[off:off + 4]) == thumb_bl(h["address"], p.symbols[h["target"]]):
                    found.append(f"hook {hx(h['address'])} already calls {h['target']}")
        require(not found, "the input already has the advanced AI: " + "; ".join(found))
        self.check("not installed", True)

    def check_input(self):
        rom, arm, ovs, p = self.rom, self.arm, self.ovs, self.payload
        have = tuple(s.ramAddress for s in arm.sections[1:])
        require(have != INPUT_AUTOLOADS[:2], "the input has no difficulty: 3 autoload sections, without "
                "difficulty's resident code at 0x023DC000 (install difficulty first)")
        require(have == INPUT_AUTOLOADS, f"autoload sections {[hx(a) for a in have]}, expected "
                f"{[hx(a) for a in INPUT_AUTOLOADS]} (the English build with difficulty)")
        self.check("autoload sections", [hx(a) for a in have])
        cs = struct.unpack_from("<5I", self.main.data, CODE_SETTINGS)
        require(cs[3] == ARM9_RAM + len(self.main.data), "arm9: the main section does not end at the bss start")
        require(not any(s.implicit for s in arm.sections[1:]), "arm9: unexpected implicit autoload section")
        self.bss = (cs[3], cs[4])
        for i in (10, 11, 14, SLOT_OVERLAY):
            require(i in ovs and not ovs[i].compressed, f"overlay {i} missing or compressed")
            require(bytes(rom.files[ovs[i].fileID]) == bytes(ovs[i].data), f"overlay {i}: file and table disagree")
        o10, o11 = ovs[10], ovs[11]
        require(sha256(bytes(o11.data)) == self.pins.overlay11_sha256,
                "overlay 11 is not the Chinese hack's trainer AI (sha256 " + sha256(bytes(o11.data)) + ")")
        require(sha256(bytes(o10.data)) == self.pins.overlay10_sha256, "overlay 10 is not the hack's 0x20-byte stub")
        require(o10.ramAddress == o11.ramAddress == p.ov10["ram"], "overlays 10 and 11 must load at overlay 10's RAM")
        require([o11.staticInitStart, o11.staticInitEnd] == p.ov10["static_init"],
                "overlay 11's static initialisers are not the payload's")
        self.check("overlay 11 sha256", sha256(bytes(o11.data)))
        self.check("overlay 10 sha256 (stub)", sha256(bytes(o10.data)))
        # ITCM: the input's ITCM code (the hack's block, text speed, trainer display, any other autoload section in
        # ITCM) must end at or below the AI's itcm origin, and the SDK's ITCM arena must start exactly there.
        itcm_end = max(s.ramAddress + len(s.data) + s.bssSize for s in self.arm.sections[1:]
                       if ITCM_START <= s.ramAddress < ITCM_END)
        origin = p.regions["itcm"]["ram"]
        require(itcm_end <= origin, f"the input's ITCM code ends at {hx(itcm_end)}, past the AI's itcm origin "
                f"{hx(origin)}: the payload needs a later origin")
        self.input_itcm = {"end": hx(itcm_end), "ai_itcm_origin": hx(origin), "headroom": origin - itcm_end}
        for w in p.words:
            have = struct.unpack("<I", self.arm9_word(w["address"]))[0]
            if w["address"] == ITCM_ARENA_LO_WORD:
                require(have == itcm_end, f"the ITCM arena start word {hx(w['address'])} holds {hx(have)}, not the "
                        f"input's ITCM end {hx(itcm_end)}")
                self.input_itcm["arena_start_word"] = hx(have)
            if w["before"] is not None:
                require(have == w["before"], f"arm9 word {hx(w['address'])} holds {hx(have)}, not {hx(w['before'])}")
            if w["before_max"] is not None:
                require(have <= w["before_max"], f"arm9 word {hx(w['address'])} holds {hx(have)}, above "
                        f"{hx(w['before_max'])}")
            w["found"] = struct.pack("<I", have)
        self.check("input ITCM end", self.input_itcm)
        self.check("words hold before", [hx(w["address"]) for w in p.words])
        for h in p.hooks:
            off = self.ov14_site(h["address"])
            have = bytes(ovs[14].data[off:off + 4])
            require(h["kind"] == "bl", f"hook {hx(h['address'])}: kind {h['kind']!r}")
            require(have == h["before"], f"hook site {hx(h['address'])} holds {have.hex()}, not {h['before'].hex()}")
            require(h["target"] in p.symbols, f"hook {hx(h['address'])}: no symbol {h['target']}")
            encoded = thumb_bl(h["address"], p.symbols[h["target"]])
            require("after" not in h or bytes.fromhex(h["after"]) == encoded,
                    f"hook {hx(h['address'])}: payload 'after' is not the BL to {h['target']}")
        sites = sorted(h["address"] for h in p.hooks)
        require(all(b - a >= 4 for a, b in zip(sites, sites[1:])), "hook sites overlap")
        self.check("hooks hold before", [hx(h["address"]) for h in p.hooks])

    def check_regions(self):
        """No region of the AI may overlap anything that can be in RAM with it (docs/memory-layout.md)."""
        p, ovs = self.payload, self.ovs
        R = p.regions
        span = {name: (r["ram"], r["ram"] + r["size"] + r["bss"]) for name, r in R.items()}
        for name in ("slot", "main"):
            require(span[name][1] <= R[name]["limit"], f"region {name} ends past its limit")
        # ITCM: the AI owns [itcm, ITCM end): code, work RAM and the fixed records from itcm_ram's limit up. The
        # code stays below its limit and the work RAM; the itcm section's bss, when the payload has one, runs from
        # the code's end through the work RAM, so every boot zeroes it (a DS does not clear ITCM), and must stop
        # before the fixed records.
        itcm = (span["itcm"][0], ITCM_END)
        code_end = R["itcm"]["ram"] + R["itcm"]["size"]
        work = (R["itcm_ram"]["ram"], R["itcm_ram"]["ram"] + R["itcm_ram"]["size"])
        require(ITCM_START <= itcm[0] and code_end <= R["itcm"]["limit"] <= work[0], "region itcm ends past its limit")
        require(work[1] <= R["itcm_ram"]["limit"] <= ITCM_END, "region itcm_ram ends past its limit")
        require(R["itcm"]["bss"] % 4 == 0 and span["itcm"][1] <= R["itcm_ram"]["limit"],
                "the itcm section's bss would reach the fixed records at itcm_ram's limit")
        require(R["itcm"]["bss"] == 0 or span["itcm"][1] >= work[1], "the itcm section's bss must cover the work RAM")
        # main: inside the main arena's free tail, which the new arena end gives up.
        lo_word = struct.unpack("<I", self.arm9_word(MAIN_ARENA_LO_WORD))[0]
        hi_before = self.payload.word(MAIN_ARENA_HI_WORD)["before"]
        hi_after = struct.unpack("<I", self.payload.word(MAIN_ARENA_HI_WORD)["after"])[0]
        itcm_lo_after = struct.unpack("<I", self.payload.word(ITCM_ARENA_LO_WORD)["after"])[0]
        require(itcm_lo_after == ITCM_END, "the ITCM arena start must move to the end of ITCM (an empty arena)")
        require(hi_after == span["main"][0] and span["main"][1] <= hi_before,
                "the main arena end must move to the start of region main, which must lie below the old end")
        max_overlay = max(o.ramAddress + o.ramSize + o.bssSize for o in ovs.values())
        require(max(max_overlay, self.bss[1]) <= lo_word < hi_after, "main arena start / overlays / region main")
        heaps = struct.unpack_from(f"<{2 * HEAP_COUNT}I", self.main.data, HEAP_TABLE - ARM9_RAM)
        require(all(arena == 0 for arena in heaps[1::2]), "root heaps outside the main arena")
        need = sum(heaps[0::2]) + self.pins.heap_overhead
        require(hi_after - lo_word >= need, f"the main arena keeps {hi_after - lo_word} bytes; the root heaps "
                f"need {need}")
        self.check("main arena after", {"lo": hx(lo_word), "hi": hx(hi_after), "root_heaps": sum(heaps[0::2]),
                                        "heap_overhead": self.pins.heap_overhead,
                                        "spare_after_boot": hi_after - lo_word - need})
        # autoload sections: none may overlap the AI's ITCM or main regions
        for s in self.arm.sections:
            have = (s.ramAddress, s.ramAddress + len(s.data) + s.bssSize)
            for name, r in (("itcm", itcm), ("main", span["main"])):
                require(not overlap(have, r), f"region {name} overlaps the autoload section at {hx(s.ramAddress)}")
        # overlay 10 takes overlay 11's place in the battle slot: it must stay inside the slot (overlay 8's range,
        # which ends where overlay 14 starts) and may only overlap overlays the slot's own overlay 8 overlaps.
        o8, o11, o14 = ovs[SLOT_OVERLAY], ovs[11], ovs[14]
        slot = (o8.ramAddress, o8.ramAddress + o8.ramSize + o8.bssSize)
        require(slot[1] == o14.ramAddress == R["slot"]["limit"], "the battle slot must end where overlay 14 starts")
        require(R["slot"]["ram"] == o11.ramAddress + o11.ramSize + o11.bssSize == p.ov10["ram"] + 0x12060 + 0x20,
                "region slot must start after overlay 11's image and bss")
        new10 = (p.ov10["ram"], span["slot"][1])
        require(slot[0] <= new10[0] and new10[1] <= slot[1], "overlay 10 does not fit the battle slot")
        for i, o in ovs.items():
            r = (o.ramAddress, o.ramAddress + o.ramSize + o.bssSize)
            if i not in (10, SLOT_OVERLAY) and overlap(r, new10):
                require(overlap(r, slot), f"overlay 10 would overlap overlay {i}, which the slot does not")
        self.check("regions", {k: [hx(a), hx(b)] for k, (a, b) in span.items()} | {"overlay10": [hx(x) for x in new10]})

    def check_marks(self):
        narc_id = self.rom.filenames.idOf(TRAINER_NARC)
        require(narc_id is not None, "no a/0/5/5 in the ROM")
        narc = bytes(self.rom.files[narc_id])
        members = narc_members(narc)
        require(all(e - s == TRAINER_HEADER for s, e in members), "a/0/5/5: a record is not 20 bytes")
        require(self.marks.marked()[-1] < len(members), "marks: a trainer id past the last record")
        set_bytes = [i for i, (s, e) in enumerate(members) if narc[s + MARK_BYTE]]
        require(not set_bytes, f"trainer header byte 2 is set in {len(set_bytes)} records, e.g. {set_bytes[:5]}")
        self.narc_id, self.narc, self.members = narc_id, narc, members
        self.check("trainer header byte 2 clear", len(members))

    # -- writes ---------------------------------------------------------------------------------------------
    def build(self):
        p, rom, arm, ovs = self.payload, self.rom, self.arm, self.ovs
        # 1. overlay 10 and its y9 entry
        o11 = ovs[11]
        image = bytes(o11.data) + bytes(o11.bssSize) + p.bins["slot"]
        require(o11.bssSize == 0x20 and len(o11.data) == 0x12060, "overlay 11's size or bss is not the hack's")
        rom.files[ovs[10].fileID] = image
        table = bytearray(rom.arm9OverlayTable)
        old = bytes(table[32 * 10:32 * 11])
        entry = struct.unpack_from("<8I", table, 32 * 10)
        require(entry[0] == 10 and entry[6] == ovs[10].fileID and entry[7] == 0, "y9 entry 10 is not plain")
        struct.pack_into("<8I", table, 32 * 10, 10, p.ov10["ram"], len(image), p.ov10["bss"],
                         o11.staticInitStart, o11.staticInitEnd, entry[6], 0)
        rom.arm9OverlayTable = bytes(table)
        self.writes.append({"what": "overlay 10 (ROM file)", "file_id": ovs[10].fileID, "ram": hx(p.ov10["ram"]),
                            "before_size": 0x20, "size": len(image), "sha256": sha256(image),
                            "parts": {"overlay11": [0, 0x12060], "overlay11_bss_zeros": [0x12060, 0x12080],
                                      "slot.bin": [0x12080, len(image)]}})
        self.writes.append({"what": "y9 entry 10", "offset": hx(32 * 10), "before": old.hex(),
                            "after": bytes(table[32 * 10:32 * 11]).hex()})
        # 3. arena words (in the main section, before it is saved)
        for w in p.words:
            off = w["address"] - ARM9_RAM
            self.main.data[off:off + 4] = w["after"]
            self.writes.append({"what": "arm9 word", "address": hx(w["address"]), "before": w["found"].hex(),
                                "after": w["after"].hex(), "purpose": w.get("purpose", "")})
        # 2. the autoload sections
        for name in ("itcm", "main"):
            r = p.regions[name]
            arm.sections.append(ndspy.code.MainCodeFile.Section(p.bins[name], r["ram"], r["bss"]))
            self.writes.append({"what": f"arm9 autoload section ({name})", "ram": hx(r["ram"]),
                                "size": r["size"], "bss": r["bss"], "sha256": sha256(p.bins[name])})
        rom.arm9 = arm.save(compress=False)
        # 4. hooks
        o14 = ovs[14]
        data14 = bytearray(rom.files[o14.fileID])
        for h in p.hooks:
            off = self.ov14_site(h["address"])
            bl = thumb_bl(h["address"], p.symbols[h["target"]])
            data14[off:off + 4] = bl
            self.writes.append({"what": "hook (overlay 14)", "address": hx(h["address"]), "before": h["before"].hex(),
                                "after": bl.hex(), "target": h["target"], "target_address": hx(p.symbols[h["target"]])})
        rom.files[o14.fileID] = bytes(data14)
        # 5. trainer marks
        narc = bytearray(self.narc)
        marked = []
        for trainer in self.marks.marked():
            start = self.members[trainer][0]
            narc[start + MARK_BYTE] = self.marks.value(trainer)
            marked.append([trainer, self.marks.value(trainer)])
        rom.files[self.narc_id] = bytes(narc)
        self.writes.append({"what": "trainer marks (a/0/5/5 header byte 2)", "file_id": self.narc_id,
                            "records": len(self.members), "before": 0, "marks": marked})
        return rom.save()

    def reopen(self, out):
        """The output as ndspy reads it back: exactly the sections, overlay 10 and files written."""
        p = self.payload
        rom = ndspy.rom.NintendoDSRom(out)
        arm = rom.loadArm9()
        want = [(s.ramAddress, bytes(s.data), s.bssSize) for s in self.arm.sections]
        have = [(s.ramAddress, bytes(s.data), s.bssSize) for s in arm.sections]
        # ndspy rewrites the module parameters' autoload table start and end and the data start when it saves
        main = bytearray(have[0][1])
        table = struct.unpack_from("<3I", main, CODE_SETTINGS)
        main[CODE_SETTINGS:CODE_SETTINGS + 12] = want[0][1][CODE_SETTINGS:CODE_SETTINGS + 12]
        have[0] = (have[0][0], bytes(main), have[0][2])
        require(have == want, "reopened arm9 sections differ from the ones written")
        require(table[2] == ARM9_RAM + len(main) and table[1] - table[0] == 12 * (len(have) - 1),
                "reopened autoload table pointers")
        o10 = rom.loadArm9Overlays()[10]
        require(bytes(o10.data) == bytes(self.rom.files[o10.fileID]) and o10.bssSize == p.ov10["bss"],
                "reopened overlay 10 differs")
        require(len(rom.files) == len(self.rom.files), "reopened file count differs")
        self.check("reopened with ndspy", True)

    def run(self):
        self.refuse_installed()
        self.check_input()
        self.check_regions()
        self.check_marks()
        out = self.build()
        self.reopen(out)
        return out


RC8_RELEASE_SHA256 = "d0185cfa37f329f4236aafbaa671b3dbb49fcdc4d7094bc27e491dc2894cf87f"
HEADER_FIELDS = {0x2C: "ARM9 size", 0x30: "ARM7 ROM offset", 0x40: "FNT offset", 0x48: "FAT offset",
                 0x50: "ARM9 overlay table offset", 0x58: "ARM7 overlay table offset", 0x68: "banner offset",
                 0x80: "used ROM size", 0x1000: "used ROM size (copy in the header padding)"}


def difficulty_mode(input_sha256, receipt_path=None):
    """The input's difficulty build mode: from difficulty's receipt (which must describe this input), else
    'release' for the known rc8 release and 'unknown' for anything else."""
    if receipt_path:
        raw = Path(receipt_path).read_bytes()
        r = json.loads(raw)
        require(r.get("output", {}).get("sha256") == input_sha256,
                "--difficulty-receipt describes another ROM (its output sha256 is not the input's)")
        return {"mode": r.get("tool_mode", "release"), "from": "difficulty receipt",
                "receipt": str(Path(receipt_path).resolve()), "receipt_sha256": sha256(raw)}
    if input_sha256 == RC8_RELEASE_SHA256:
        return {"mode": "release", "from": "the input is the rc8 release (sha256 d0185cfa...)"}
    return {"mode": "unknown", "from": "no --difficulty-receipt and not a known input"}


def container_changes(before, after):
    """What saving the ROM moved besides the logical writes: header fields, the header CRC, the copy of the used
    size at 0x1000, the arm9 module parameters' autoload table pointers, and the ROM offsets of files."""
    u32 = lambda d, o: struct.unpack_from("<I", d, o)[0]   # noqa: E731
    header = [{"offset": hx(o), "field": HEADER_FIELDS.get(o, "?"), "before": hx(u32(before, o)),
               "after": hx(u32(after, o))} for o in range(0, 0x4000, 4) if o != 0x15C and u32(before, o) != u32(after, o)]
    crc = [struct.unpack_from("<H", d, 0x15E)[0] for d in (before, after)]
    params = []
    for d, name in ((before, "before"), (after, "after")):
        base = u32(d, 0x20) + CODE_SETTINGS
        params.append(struct.unpack_from("<6I", d, base))
    labels = ("autoload table start", "autoload table end", "autoload data start", "bss start", "bss end",
              "compressed end")
    fat = [[struct.unpack_from("<2I", d, u32(d, 0x48) + 8 * i) for i in range(u32(d, 0x4C) // 8)] for d in (before, after)]
    moved = [i for i, (a, b) in enumerate(zip(*fat)) if a[0] != b[0]]
    return {"note": "ndspy rewrites the ROM container on save: these bytes change with no change in content (the "
                    "verifier checks every moved table and file against the input)",
            "header": header, "header_crc": [hex(c) for c in crc],
            "module_params": [{"address": hx(ARM9_RAM + CODE_SETTINGS + 4 * k), "field": labels[k],
                               "before": hx(params[0][k]), "after": hx(params[1][k])}
                              for k in range(6) if params[0][k] != params[1][k]],
            "files_moved": {"count": len(moved), "first_id": moved[0] if moved else None,
                            "last_id": moved[-1] if moved else None}}


def identity(data, path=None):
    out = {"size": len(data), "sha1": hashlib.sha1(data).hexdigest(), "sha256": sha256(data)}
    return {"path": str(path)} | out if path else out


def atomic_write(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def install(input_path, out_path, payload_dir=DEF_PAYLOAD, marks_path=DEF_MARKS, pins=None,
            difficulty_receipt=None):
    """Install into a copy; returns the receipt. Raises Refused before writing anything."""
    pins = pins or Pins()
    import verify    # builder/verify.py: its own parsing of the written ROM

    input_path, out_path = Path(input_path).resolve(), Path(out_path).resolve()
    require(input_path != out_path and not (out_path.exists() and out_path.samefile(input_path)),
            "--out must be a new file, not the input")
    data = input_path.read_bytes()
    payload, marks = Payload(payload_dir), Marks(marks_path)
    difficulty = difficulty_mode(sha256(data), difficulty_receipt)
    job = Install(data, payload, marks, pins)
    out = job.run()
    report = verify.verify(out, payload_dir=payload.dir, marks_path=marks.path, input_data=data,
                           overlay11_sha256=pins.overlay11_sha256)
    require(report["ok"], "verify.py rejects the output: " + "; ".join(report["errors"]))
    require(input_path.read_bytes() == data, "the input changed while installing")
    receipt = {
        "format": 1,
        "tool": "work/advanced-ai/builder/install.py",
        "input": identity(data, input_path),
        "difficulty": difficulty,
        "input_itcm": job.input_itcm,
        "output": identity(out, out_path),
        "payload": payload.receipt(),
        "marks": {"path": str(marks.path), "sha256": marks.sha256, "important": len(marks.important),
                  "keep_lead": len(marks.keep_lead)},
        "checks": job.checks,
        "logical_writes": job.writes,
        "container": container_changes(data, out),
        "verify": {k: v for k, v in report.items() if k != "errors"},
    }
    atomic_write(out_path, out)
    atomic_write(Path(str(out_path) + ".receipt.json"), (json.dumps(receipt, indent=1) + "\n").encode())
    return receipt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--input", required=True, help="English ROM with difficulty (never written)")
    ap.add_argument("--out", required=True, help="the new ROM; <out>.receipt.json is written next to it")
    ap.add_argument("--payload", default=DEF_PAYLOAD, help=f"payload directory (default {DEF_PAYLOAD})")
    ap.add_argument("--marks", default=DEF_MARKS, help=f"trainer marks (default {DEF_MARKS})")
    ap.add_argument("--difficulty-receipt", help="difficulty's receipt for the input: its build mode goes into ours")
    a = ap.parse_args(argv)
    try:
        receipt = install(a.input, a.out, a.payload, a.marks, difficulty_receipt=a.difficulty_receipt)
    except Refused as e:
        print(f"install.py: refused: {e}", file=sys.stderr)
        return 1
    print(f"wrote {receipt['output']['path']} (sha256 {receipt['output']['sha256']})")
    print(f"receipt {receipt['output']['path']}.receipt.json; verify: {receipt['verify']['checked']} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
