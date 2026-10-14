"""Installer tests: builder/install.py writes the AI into a copy, refuses every input it must refuse, and its receipt
records what it checked and wrote.

    .venv/bin/python -m unittest discover -s work/advanced-ai/testbench/unit -p 'test_install*.py'

Synthetic cases need no game data: `synthetic_rom()` builds a small NDS ROM with the shape of an English build with
difficulty (the four autoload sections, overlays 8, 10, 11 and 14 at the hack's addresses, the arena words, the root
heap table and an a/0/5/5 of 1024 empty trainer headers), and `synthetic_payload()` a payload in the contract's
format. Inputs come with the rc8 release's ITCM end (0x01FF8FC0) and main's (0x01FF9140, trainer full names), below
the payload's itcm origin. Each refusal mutates one thing. The real-ROM cases install the committed payload onto the
rc8 release (work/build/advanced-ai/base/rc8_release.nds) and main's difficulty build
(work/build/advanced-ai/options/difficulty_dev_main.nds), and run the refusals on the Chinese ROM, the rc8 and main
standard builds and Spanish rc44; they skip when a ROM is missing. test_verify.py reuses the synthetic builders.
"""
import hashlib
import json
import random
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import ndspy.code
import ndspy.fnt
import ndspy.narc
import ndspy.rom

AI_DIR = Path(__file__).resolve().parents[2]
REPO = AI_DIR.parents[1]
sys.path.insert(0, str(AI_DIR / "builder"))
import install  # noqa: E402
import verify  # noqa: E402

RC8_RELEASE = REPO / "work" / "build" / "advanced-ai" / "base" / "rc8_release.nds"
RC8_RELEASE_SHA256 = "d0185cfa37f329f4236aafbaa671b3dbb49fcdc4d7094bc27e491dc2894cf87f"
CN_ROM = REPO / "work" / "rom" / "origin_v4.0.3_cn.nds"
RC8_STANDARD = REPO / "work" / "build" / "origin_hg_v4.0.3_en_wip.nds"
RC44 = REPO / "work" / "build" / "advanced-ai" / "es" / "rc44.nds"
MAIN_STANDARD = REPO / "work" / "build" / "advanced-ai" / "base" / "main_standard.nds"
MAIN_DEV = REPO / "work" / "build" / "advanced-ai" / "options" / "difficulty_dev_main.nds"   # main + difficulty
PAYLOAD = AI_DIR / "payload"
MARKS = AI_DIR / "data" / "trainer_marks.json"

MAIN_LEN = 0x1106A0
HOOKS = [(0x02223D10, "f1f700fe", "ai_slot_select"), (0x02203736, "e1f733fb", "ai_entry"),
         (0x02203C06, "fff7b5fe", "ai_replace"), (0x022029CC, "12f0baff", "ai_bag_check"),
         (0x022153C2, "0ef03dfb", "ai_lead")]
# The AI's itcm origin, fixed with headroom above every input's ITCM code: the rc8 release's ends at 0x01FF8FC0 (the
# hack's block and text speed), main's at 0x01FF9140 (and trainer display)
ORIGIN = 0x01FF9400
RC8_ITCM, MAIN_ITCM = 0xFC0, 0x1140
SYMBOLS = {"ai_slot_select": ORIGIN + 0x01, "ai_entry": ORIGIN + 0x11, "ai_replace": ORIGIN + 0x21,
           "ai_bag_check": ORIGIN + 0x31, "ai_lead": 0x023D4001, "adv_entry": 0x021F6E21}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def blob(seed, n):
    return random.Random(seed).randbytes(n)


def synthetic_rom(autoloads=3, itcm_len=RC8_ITCM, itcm_word=None, heap4=0x11D000, ov8_size=0x1BA40, mutate=None):
    """An NDS ROM shaped like the English build with difficulty (autoloads=3 adds difficulty's section). Its ITCM
    block is itcm_len bytes; the ITCM arena start word is its end unless itcm_word says otherwise."""
    main = bytearray(MAIN_LEN)
    struct.pack_into("<I", main, 0xAA8, 0x02000BA0)                  # the code settings pointer's target
    struct.pack_into("<9I", main, 0xBA0, 0, 0, 0x02000000 + MAIN_LEN, 0x02000000 + MAIN_LEN, 0x021E4980, 0,
                     0x04027533, 0xDEC00621, 0x2106C0DE)
    itcm_word = 0x01FF8000 + itcm_len if itcm_word is None else itcm_word
    for addr, value in ((0x020D1A1C, 0x02264920), (0x020D1970, 0x023DC000), (0x020D1A28, itcm_word)):
        struct.pack_into("<I", main, addr - 0x02000000, value)
    struct.pack_into("<8I", main, 0x020F2EAC - 0x02000000, 0xD200, 0, 0x2E600, 0, 0x10, 0, heap4, 0)
    arm = ndspy.code.MainCodeFile.__new__(ndspy.code.MainCodeFile)
    arm.ramAddress, arm.codeSettingsOffs = 0x02000000, 0xBA0
    S = ndspy.code.MainCodeFile.Section
    arm.sections = [S(main, 0x02000000, 0, implicit=True), S(blob(1, itcm_len), 0x01FF8000, 0),
                    S(blob(2, 0x60), 0x027E0000, 0x20)]
    if autoloads >= 3:
        arm.sections.append(S(blob(3, 0x21E0), 0x023DC000, 0))
    ov14 = bytearray(0x52540)
    for addr, before, _ in HOOKS:
        ov14[addr - 0x022007E0:addr - 0x022007E0 + 4] = bytes.fromhex(before)
    overlays = {i: (0x021E4980, b"\0" * 0x20, 0, 0x021E4980, 0x021E4980) for i in range(15)}
    overlays[8] = (0x021E4DA0, blob(8, ov8_size), 0, 0x021E4DA0, 0x021E4DA4)
    overlays[10] = (0x021E4DA0, b"\x10" * 0x20, 0, 0x021E4DA0, 0x021E4DA4)
    overlays[11] = (0x021E4DA0, blob(11, 0x12060), 0x20, 0x021F6DE8, 0x021F6DEC)
    overlays[14] = (0x022007E0, bytes(ov14), 0x33C0, 0x02252CA8, 0x02252CAC)
    table = bytearray()
    files = []
    for i in range(15):
        ram, data, bss, si, se = overlays[i]
        table += struct.pack("<8I", i, ram, len(data), bss, si, se, i, 0)
        files.append(data)
    narc = ndspy.narc.NARC.fromFilesAndNames([bytes([3, 1, 0, 1]) + bytes(16) for _ in range(1024)]).save()
    files.append(narc)
    rom = ndspy.rom.NintendoDSRom()
    rom.name, rom.idCode = b"POKEMON HG", b"IPKJ"
    rom.arm9CodeSettingsPointerAddress = 0x02000AAC
    rom.arm9 = arm.save(compress=False)
    rom.arm9OverlayTable = bytes(table)
    rom.files = files
    rom.filenames = ndspy.fnt.Folder(folders=[("a", ndspy.fnt.Folder(folders=[("0", ndspy.fnt.Folder(
        folders=[("5", ndspy.fnt.Folder(files=["5"], firstID=15))], firstID=15))], firstID=15))], firstID=15)
    if mutate:
        mutate(rom)
    return rom.save()


# itcm code ORIGIN + 0x200; its bss runs through the work RAM 0x01FFEE00 + 0x100, as the builder's en payload
ITCM_BSS = 0x01FFEF00 - (ORIGIN + 0x200)
ITCM_WORD = {"before_max": f"0x{ORIGIN:08X}"}      # the ITCM arena start: no exact before (it is the input's ITCM end)


def synthetic_payload(directory, slot_bss=0x40, itcm_bss=ITCM_BSS, itcm_word=None, **overrides):
    """A payload in the contract's format (docs/build-contract.md) for the synthetic ROM, written to directory."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    bins = {"slot.bin": blob(20, 0x400), "itcm.bin": blob(21, 0x200), "main.bin": blob(22, 0x100)}
    for name, data in bins.items():
        (directory / name).write_bytes(data)
    p = {
        "format": 1, "layout": "en", "toolchain": {"gcc": "16.2.0", "binutils": "2.47"}, "sources": {},
        "regions": {
            "slot": {"ram": "0x021F6E20", "file": "slot.bin", "size": 0x400, "bss": slot_bss, "limit": "0x022007E0"},
            "itcm": {"ram": f"0x{ORIGIN:08X}", "file": "itcm.bin", "size": 0x200, "bss": itcm_bss,
                     "limit": "0x01FFEE00"},
            "itcm_ram": {"ram": "0x01FFEE00", "size": 0x100, "limit": "0x01FFFF8C"},
            "main": {"ram": "0x023D4000", "file": "main.bin", "size": 0x100, "bss": 0, "limit": "0x023DC000"}},
        "overlay10": {"base_from": "overlay 11 of the input ROM", "ram": "0x021E4DA0", "bss": hex(slot_bss),
                      "static_init": ["0x021F6DE8", "0x021F6DEC"]},
        "symbols": {k: f"0x{v:08X}" for k, v in SYMBOLS.items()},
        "hooks": [{"file": "overlay14", "address": f"0x{a:08X}", "before": b, "target": t, "kind": "bl"}
                  for a, b, t in HOOKS],
        "words": [{"file": "arm9", "address": "0x020D1A28", "after": "00000002", **(itcm_word or ITCM_WORD)},
                  {"file": "arm9", "address": "0x020D1970", "before": "00c03d02", "after": "00403d02"}],
        "files": {name: sha256(data) for name, data in bins.items()},
    }
    p.update(overrides)
    (directory / "payload.json").write_text(json.dumps(p, indent=1))
    return directory


def write_marks(path, important=(1, 2, 5, 1023), keep_lead=(2, 7)):
    Path(path).write_text(json.dumps({"important": list(important), "keep_lead": list(keep_lead)}))
    return path


def synthetic_pins(rom_bytes):
    rom = ndspy.rom.NintendoDSRom(rom_bytes)
    return install.Pins(overlay11_sha256=sha256(rom.files[11]), overlay10_sha256=sha256(rom.files[10]),
                        heap_overhead=0x4000)


class Synthetic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.payload = synthetic_payload(self.dir / "payload")
        self.marks = write_marks(self.dir / "marks.json")
        self.rom = synthetic_rom()
        self.pins = synthetic_pins(self.rom)
        self.input = self.dir / "in.nds"
        self.input.write_bytes(self.rom)

    def tearDown(self):
        self.tmp.cleanup()

    def install(self, rom=None, payload=None, out="out.nds", difficulty_receipt=None):
        path = self.input
        if rom is not None:
            path = self.dir / "mutated.nds"
            path.write_bytes(rom)
        return install.install(path, self.dir / out, payload or self.payload, self.marks, self.pins,
                               difficulty_receipt=difficulty_receipt)

    def refused(self, fragment, rom=None, payload=None, difficulty_receipt=None):
        with self.assertRaises(install.Refused) as cm:
            self.install(rom, payload, difficulty_receipt=difficulty_receipt)
        self.assertIn(fragment, str(cm.exception))
        self.assertFalse((self.dir / "out.nds").exists(), "a refused install wrote its output")
        self.assertFalse((self.dir / "out.nds.receipt.json").exists())

    def test_installs_into_a_copy_and_verifies(self):
        receipt = self.install()
        out = (self.dir / "out.nds").read_bytes()
        self.assertEqual(self.input.read_bytes(), self.rom, "the input was written")
        report = verify.verify(out, self.payload, self.marks, self.rom, overlay11_sha256=self.pins.overlay11_sha256)
        self.assertTrue(report["ok"], report["errors"])
        rom = ndspy.rom.NintendoDSRom(out)
        arm = rom.loadArm9()
        self.assertEqual([(s.ramAddress, s.bssSize) for s in arm.sections],
                         [(0x02000000, 0), (0x01FF8000, 0), (0x027E0000, 0x20), (0x023DC000, 0),
                          (ORIGIN, ITCM_BSS), (0x023D4000, 0)])
        o10 = rom.loadArm9Overlays()[10]
        self.assertEqual(bytes(o10.data), rom.files[11] + bytes(0x20) + (self.payload / "slot.bin").read_bytes())
        self.assertEqual((o10.ramSize, o10.bssSize, o10.staticInitStart), (0x12080 + 0x400, 0x40, 0x021F6DE8))
        main = arm.sections[0].data
        self.assertEqual(struct.unpack_from("<I", main, 0xD1A28)[0], 0x02000000)
        self.assertEqual(struct.unpack_from("<I", main, 0xD1970)[0], 0x023D4000)
        ov14 = rom.files[14]
        self.assertEqual(ov14[0x02223D10 - 0x022007E0:][:4], install.thumb_bl(0x02223D10, SYMBOLS["ai_slot_select"]))
        narc = ndspy.narc.NARC(rom.files[15])
        self.assertEqual([f[2] for f in narc.files[:8]], [0, 1, 3, 0, 0, 1, 0, 2])
        self.assertEqual(narc.files[1023][2], 1)
        self.assertEqual(receipt["output"]["sha256"], sha256(out))

    def test_receipt_contents(self):
        self.install()
        out = (self.dir / "out.nds").read_bytes()
        r = json.loads((self.dir / "out.nds.receipt.json").read_text())
        self.assertEqual(r["input"]["sha256"], sha256(self.rom))
        self.assertEqual(r["output"]["sha256"], sha256(out))
        self.assertEqual(r["output"]["sha1"], hashlib.sha1(out).hexdigest())
        self.assertEqual(r["payload"]["payload.json"], sha256((self.payload / "payload.json").read_bytes()))
        self.assertEqual(r["payload"]["files"]["slot.bin"], sha256((self.payload / "slot.bin").read_bytes()))
        self.assertEqual(r["marks"]["sha256"], sha256(Path(self.marks).read_bytes()))
        kinds = [w["what"] for w in r["logical_writes"]]
        self.assertEqual(kinds.count("hook (overlay 14)"), 5)
        self.assertEqual(kinds.count("arm9 word"), 2)
        self.assertIn("arm9 autoload section (itcm)", kinds)
        self.assertIn("arm9 autoload section (main)", kinds)
        self.assertIn("overlay 10 (ROM file)", kinds)
        self.assertIn("y9 entry 10", kinds)
        hooks = {w["address"]: w for w in r["logical_writes"] if w["what"] == "hook (overlay 14)"}
        for addr, before, target in HOOKS:
            w = hooks[f"0x{addr:08X}"]
            self.assertEqual((w["before"], w["after"]), (before, install.thumb_bl(addr, SYMBOLS[target]).hex()))
        marks = next(w for w in r["logical_writes"] if w["what"].startswith("trainer marks"))
        self.assertEqual(marks["marks"], [[1, 1], [2, 3], [5, 1], [7, 2], [1023, 1]])
        itcm = next(w for w in r["logical_writes"] if w["what"] == "arm9 autoload section (itcm)")
        self.assertEqual(itcm["bss"], ITCM_BSS)
        # what saving moved: the ARM9 grew, so the autoload table pointers, the header CRC and offsets changed
        moved = {h["field"] for h in r["container"]["header"]}
        self.assertIn("ARM9 size", moved)
        self.assertEqual([m["field"] for m in r["container"]["module_params"]],
                         ["autoload table start", "autoload table end"])
        self.assertEqual(r["difficulty"]["mode"], "unknown")
        self.assertEqual(r["input_itcm"], {"end": "0x01FF8FC0", "ai_itcm_origin": f"0x{ORIGIN:08X}",
                                           "headroom": ORIGIN - 0x01FF8FC0, "arena_start_word": "0x01FF8FC0"})
        self.assertTrue(r["verify"]["ok"])
        self.assertIn("not installed", [c["check"] for c in r["checks"]])

    def test_refuses_its_own_output(self):
        self.install()
        installed = (self.dir / "out.nds").read_bytes()
        (self.dir / "out.nds").unlink()
        (self.dir / "out.nds.receipt.json").unlink()
        self.refused("already has the advanced AI", rom=installed)

    def test_refuses_writing_over_the_input(self):
        with self.assertRaises(install.Refused):
            install.install(self.input, self.input, self.payload, self.marks, self.pins)
        self.assertEqual(self.input.read_bytes(), self.rom)

    def test_refuses_without_difficulty(self):
        self.refused("no difficulty", rom=synthetic_rom(autoloads=2))

    def test_refuses_an_unknown_overlay_11(self):
        def edit(rom):
            data = bytearray(rom.files[11])
            data[0x100] ^= 1
            rom.files[11] = bytes(data)
        self.refused("overlay 11 is not the Chinese hack's", rom=synthetic_rom(mutate=edit))

    def test_refuses_a_changed_overlay_10_stub(self):
        def edit(rom):
            rom.files[10] = b"\x11" * 0x20
        self.refused("overlay 10 is not the hack's 0x20-byte stub", rom=synthetic_rom(mutate=edit))

    def test_refuses_each_hook_site_that_differs(self):
        for addr, _, _ in HOOKS:
            def edit(rom, addr=addr):
                data = bytearray(rom.files[14])
                data[addr - 0x022007E0 + 1] ^= 0x40
                rom.files[14] = bytes(data)
            with self.subTest(hook=hex(addr)):
                self.refused(f"hook site 0x{addr:08X}", rom=synthetic_rom(mutate=edit))

    def test_refuses_a_main_arena_end_that_differs(self):
        def edit(rom):
            arm = rom.loadArm9()
            arm.sections[0].data[0x020D1970 - 0x02000000] ^= 0x20
            rom.arm9 = arm.save(compress=False)
        self.refused("arm9 word 0x020D1970", rom=synthetic_rom(mutate=edit))

    def test_installs_on_an_input_with_more_itcm_code(self):
        # main's English build: text speed and trainer display, ITCM code to 0x01FF9140
        rom = synthetic_rom(itcm_len=MAIN_ITCM)
        self.pins = synthetic_pins(rom)
        receipt = self.install(rom=rom)
        self.assertEqual(receipt["input_itcm"]["end"], "0x01FF9140")
        self.assertEqual(receipt["input_itcm"]["headroom"], ORIGIN - 0x01FF9140)
        word = next(w for w in receipt["logical_writes"] if w.get("address") == "0x020D1A28")
        self.assertEqual((word["before"], word["after"]), ("4091ff01", "00000002"))
        out = (self.dir / "out.nds").read_bytes()
        report = verify.verify(out, self.payload, self.marks, rom, overlay11_sha256=self.pins.overlay11_sha256)
        self.assertTrue(report["ok"], report["errors"])

    def test_refuses_itcm_code_past_the_origin(self):
        self.refused("ends at 0x01FF9500, past the AI's itcm origin 0x01FF9400", rom=synthetic_rom(itcm_len=0x1500))

    def test_refuses_an_itcm_arena_word_off_the_itcm_end(self):
        self.refused("holds 0x01FF8FC0, not the input's ITCM end 0x01FF9140",
                     rom=synthetic_rom(itcm_len=MAIN_ITCM, itcm_word=0x01FF8FC0))
        self.refused("holds 0x01FF9200, not the input's ITCM end 0x01FF8FC0", rom=synthetic_rom(itcm_word=0x01FF9200))

    def test_itcm_word_forms(self):
        # an exact `before` still works where the input matches it; "itcm_end" leaves only the rule
        receipt = self.install(payload=synthetic_payload(self.dir / "exact", itcm_word={"before": "c08fff01"}),
                               out="exact.nds")
        self.assertEqual(receipt["input_itcm"]["end"], "0x01FF8FC0")
        self.install(payload=synthetic_payload(self.dir / "token", itcm_word={"before": "itcm_end"}), out="token.nds")
        self.refused("not 0x01FF9140", payload=synthetic_payload(self.dir / "stale", itcm_word={"before": "4091ff01"}))
        self.refused("above 0x01FF8F00",
                     payload=synthetic_payload(self.dir / "ceiling", itcm_word={"before_max": "0x01FF8F00"}))

    def test_refuses_a_slot_that_does_not_reach_overlay_14(self):
        self.refused("the battle slot must end where overlay 14 starts", rom=synthetic_rom(ov8_size=0x18000))

    def test_refuses_a_slot_past_its_limit(self):
        payload = synthetic_payload(self.dir / "big", slot_bss=0x9800)
        self.refused("region slot ends past its limit", payload=payload)

    def test_refuses_root_heaps_that_no_longer_fit(self):
        self.refused("the root heaps need", rom=synthetic_rom(heap4=0x170000))

    def test_refuses_a_trainer_header_with_byte_2_set(self):
        def edit(rom):
            narc = ndspy.narc.NARC(rom.files[15])
            narc.files[300] = narc.files[300][:2] + b"\x04" + narc.files[300][3:]
            rom.files[15] = narc.save()
        self.refused("byte 2 is set in 1 records", rom=synthetic_rom(mutate=edit))

    def test_refuses_an_itcm_bss_reaching_the_fixed_records(self):
        payload = synthetic_payload(self.dir / "bss", itcm_bss=0x01FFFF90 - (ORIGIN + 0x200))
        self.refused("would reach the fixed records", payload=payload)

    def test_refuses_an_itcm_bss_that_misses_the_work_ram(self):
        payload = synthetic_payload(self.dir / "short", itcm_bss=0x100)
        self.refused("must cover the work RAM", payload=payload)

    def test_installs_a_payload_without_itcm_bss(self):
        receipt = self.install(payload=synthetic_payload(self.dir / "nobss", itcm_bss=0))
        itcm = next(w for w in receipt["logical_writes"] if w["what"] == "arm9 autoload section (itcm)")
        self.assertEqual(itcm["bss"], 0)

    def test_difficulty_mode_from_its_receipt(self):
        receipt = self.dir / "difficulty.receipt.json"
        receipt.write_text(json.dumps({"tool_mode": "development", "output": {"sha256": sha256(self.rom)}}))
        self.assertEqual(self.install(difficulty_receipt=receipt)["difficulty"]["mode"], "development")

    def test_refuses_a_difficulty_receipt_for_another_rom(self):
        receipt = self.dir / "other.receipt.json"
        receipt.write_text(json.dumps({"tool_mode": "release", "output": {"sha256": "0" * 64}}))
        self.refused("describes another ROM", difficulty_receipt=receipt)

    def test_refuses_a_payload_bin_that_does_not_match(self):
        (self.payload / "slot.bin").write_bytes(blob(99, 0x400))
        self.refused("slot.bin does not match its sha256")

    def test_refuses_marks_with_trainer_0(self):
        write_marks(self.marks, important=(0, 1))
        self.refused("lists trainer 0")


class ThumbBl(unittest.TestCase):
    def test_encoding_matches_the_builder(self):
        # the builder's `after` for the first hook in payload.json (ai_slot_select 0x01FF900F)
        self.assertEqual(install.thumb_bl(0x02223D10, 0x01FF900F).hex(), "d5f57df9")
        self.assertEqual(verify.thumb_bl_target(install.thumb_bl(0x022153C2, 0x023D4001), 0x022153C2), 0x023D4000)

    def test_refuses_arm_targets_and_out_of_range(self):
        with self.assertRaises(install.Refused):
            install.thumb_bl(0x02200000, 0x01FF9000)
        with self.assertRaises(install.Refused):
            install.thumb_bl(0x02200000, 0x02700001)


@unittest.skipUnless(RC8_RELEASE.exists() and (PAYLOAD / "payload.json").exists(),
                     "needs work/build/advanced-ai/base/rc8_release.nds and the committed payload/")
class RealRom(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_installs_on_the_rc8_release(self):
        self.assertEqual(sha256(RC8_RELEASE.read_bytes()), RC8_RELEASE_SHA256)
        r1 = install.install(RC8_RELEASE, self.dir / "a.nds", PAYLOAD, MARKS)
        r2 = install.install(RC8_RELEASE, self.dir / "b.nds", PAYLOAD, MARKS)
        self.assertEqual(r1["output"]["sha256"], r2["output"]["sha256"], "two installs differ")
        report = verify.verify((self.dir / "a.nds").read_bytes(), PAYLOAD, MARKS, RC8_RELEASE.read_bytes())
        self.assertTrue(report["ok"], report["errors"])
        self.assertEqual(r1["input"]["sha256"], RC8_RELEASE_SHA256)
        self.assertEqual(r1["difficulty"]["mode"], "release")
        marks = next(w for w in r1["logical_writes"] if w["what"].startswith("trainer marks"))
        self.assertEqual(len(marks["marks"]), 514)
        with self.assertRaises(install.Refused) as cm:
            install.install(self.dir / "a.nds", self.dir / "c.nds", PAYLOAD, MARKS)
        self.assertIn("already has the advanced AI", str(cm.exception))

    @unittest.skipUnless(MAIN_DEV.exists(), "needs work/build/advanced-ai/options/difficulty_dev_main.nds")
    def test_installs_on_mains_difficulty_build(self):
        # main's English build: trainer full names put its ITCM end at 0x01FF9140
        receipt_path = MAIN_DEV.with_suffix(".receipt.json")
        r = install.install(MAIN_DEV, self.dir / "m.nds", PAYLOAD, MARKS,
                            difficulty_receipt=receipt_path if receipt_path.exists() else None)
        self.assertEqual(r["input_itcm"]["end"], "0x01FF9140")
        self.assertEqual(r["input_itcm"]["arena_start_word"], "0x01FF9140")
        report = verify.verify((self.dir / "m.nds").read_bytes(), PAYLOAD, MARKS, MAIN_DEV.read_bytes())
        self.assertTrue(report["ok"], report["errors"])

    def test_refuses_roms_without_difficulty_or_with_an_ai(self):
        for rom, fragment in ((CN_ROM, "no difficulty"), (RC8_STANDARD, "no difficulty"),
                              (MAIN_STANDARD, "no difficulty"), (RC44, "already has the advanced AI")):
            if not rom.exists():
                continue
            with self.subTest(rom=rom.name), self.assertRaises(install.Refused) as cm:
                install.install(rom, self.dir / "x.nds", PAYLOAD, MARKS)
            self.assertIn(fragment, str(cm.exception))
            self.assertFalse((self.dir / "x.nds").exists())


if __name__ == "__main__":
    unittest.main()
