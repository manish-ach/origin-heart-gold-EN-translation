"""Unit tests for emu_textfit (no emulator, no PIL): selection from a git ref, window mapping, the expected
views, the fill-ins and the fit judge on synthetic pixel buffers."""
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import emu_textfit as T

BG, INK = (248, 248, 248), (80, 80, 88)
BOX = T.WINDOWS["field"]


def bank(narc, no, strings):
    return {"narc": narc, "bank": no, "strings": [{"id": i, "zh": zh, "en": en} for i, (zh, en) in enumerate(strings)]}


class Selection(unittest.TestCase):
    def git(self, d, *args):
        subprocess.run(["git", *args], cwd=d, check=True, capture_output=True)

    def test_changed_since_a_ref(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "work/translate/banks/a027"
            root.mkdir(parents=True)
            (root / "0001.json").write_text(json.dumps(bank("a027", 1, [("甲", "One"), ("乙", "Two"), ("丙", None)])))
            (root / "0002.json").write_text(json.dumps(bank("a027", 2, [("甲", "Same")])))
            self.git(d, "init", "-q")
            self.git(d, "-c", "user.email=t@t", "-c", "user.name=t", "add", ".")
            self.git(d, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x")
            self.git(d, "tag", "rel")
            (root / "0001.json").write_text(json.dumps(bank("a027", 1, [("甲", "One"), ("乙", "Two!"), ("丙", "New")])))
            bs = Path(d) / "work/translate/banks/battle_string"
            bs.mkdir()
            (bs / "0002.json").write_text(json.dumps(bank("battle_string", 2, [("甲", "A"), ("乙", None)])))
            refs = T.changed_refs("rel", cwd=d)
            self.assertEqual(refs, [("a027", 1, 1), ("a027", 1, 2), ("battle_string", 2, 0)])
            with self.assertRaises(RuntimeError):
                T.changed_refs("no-such-ref", cwd=d)

    def test_diff_strings(self):
        old = bank("a027", 1, [("a", "x"), ("b", "y")])
        new = bank("a027", 1, [("a", "x"), ("b", "z"), ("c", "w")])
        self.assertEqual(T.diff_strings(old, new), [1, 2])
        self.assertEqual(T.diff_strings(None, new), [0, 1, 2])

    def test_parse_ref_and_sample(self):
        self.assertEqual(T.parse_ref("60#27"), ("a027", 60, 27))
        self.assertEqual(T.parse_ref("a027/0060#27"), ("a027", 60, 27))
        self.assertEqual(T.parse_ref("battle_string/0002#32"), ("battle_string", 2, 32))
        self.assertEqual(T.ref_str(("a027", 60, 27)), "a027/0060#27")
        with self.assertRaises(ValueError):
            T.parse_ref("60-27")
        refs = list(range(10))
        self.assertEqual(T.sample(refs, 5), [0, 2, 4, 6, 8])
        self.assertEqual(T.sample(refs, None), refs)
        self.assertEqual(T.sample(refs, 50), refs)


class SpanishTargets(unittest.TestCase):
    def test_explicit_locale_selection(self):
        self.assertEqual(T.target_locales("en,es"), ["en", "es"])
        for value in ("", "en,en", "es,fr", " en"):
            with self.assertRaises(ValueError):
                T.target_locales(value)

    def test_spanish_diff_and_inventory(self):
        old = {"strings": [{"ref": "a027/0060#27", "text": "Hola"}]}
        new = {"strings": [{"ref": "a027/0060#27", "text": "¡Hola!"},
                           {"ref": "a027/0060#28", "text": None}]}
        self.assertEqual(T.diff_strings(old, new, "es"), [27])
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "a027"
            p.mkdir()
            (p / "0060.json").write_text(json.dumps(new))
            self.assertEqual(T.all_refs(folder, "es"), [("a027", 60, 27)])

    def test_spanish_text_and_fillers_never_use_english(self):
        from unittest.mock import patch
        source = bank("a027", 60, [("甲", "English")])
        es = {"strings": [{"ref": "a027/0060#0", "text": "¡Hola, {VAR:0100:0}!"}]}
        def load(narc, number, root=str(T.BANKS)):
            return es if root == str(T.ES_BANKS) else source
        with patch.object(T, "load_bank", side_effect=load), patch.object(T, "fillers", return_value={0: "Ñandú"}) as fill:
            plan = T.item_plan(("a027", 60, 0), lang="es")
            self.assertEqual(plan["expanded"], "¡Hola, Ñandú!")
            self.assertEqual(fill.call_args.args[-1], "es")
            es["strings"][0]["text"] = None
            with self.assertRaises(ValueError):
                T.item_plan(("a027", 60, 0), lang="es")

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "image checks require pinned Pillow")
    def test_dex_reader_checks_actual_glyphs_and_locale_font(self):
        from unittest.mock import patch
        from PIL import Image
        font = T.Font({65: ("A", 2, (2, 2))})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "screen.png"
            im = Image.new("RGB", (256, 192), (248, 248, 248))
            im.putpixel((120, 41), (88, 88, 88))
            im.putpixel((121, 41), (208, 216, 216))
            im.save(path)
            for lang, font_id in (("en", 4), ("es", 0)):
                with patch.object(T, "rom_font", return_value=font) as native:
                    proof = T.read_dex_category(path, "A", "native.nds", lang)
                    self.assertEqual(proof["verdict"], "pass")
                    native.assert_called_with("native.nds", font_id)
                    self.assertEqual(T.read_dex_category(path, "AA", "native.nds", lang)["verdict"], "fail")
            self.assertEqual(T.read_dex_category(path, "A", "native.nds", "cn")["verdict"], "unsupported")
            Image.new("RGB", (512, 384)).save(path)
            self.assertEqual(T.read_dex_category(path, "A", "native.nds", "es")["verdict"], "incomplete")

    def test_native_font_width_is_used(self):
        exp = T.expected_views("ABC", width_of=lambda text: len(text) * 11)
        self.assertEqual(exp["widths"], [[33, 0]])

    def test_missing_locale_input_is_error(self):
        from unittest.mock import patch
        with patch.object(T, "window_for", side_effect=FileNotFoundError("es bank")):
            todo, rows = T.plan_rows([("a027", 60, 0)], ["field"], "es")
        self.assertEqual(rows[0]["verdict"], "error")
        self.assertEqual(rows[0]["lang"], "es")
        self.assertEqual(todo["field"], [])

    def test_no_rendered_refs_cannot_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            result = T.summarise([{"ref": "a027/0803#1", "lang": "es", "window": None,
                                   "verdict": "unsupported", "reason": "dex category"}],
                                 "refs", 1, folder, 0, {}, {})
            self.assertFalse(result["pass"])
            self.assertFalse(result["coverage_complete"])

    def test_sampled_success_is_not_complete_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            result = T.summarise([{"ref": "a027/0060#27", "lang": "es",
                                   "window": "field", "verdict": "pass"}],
                                 {"es": {"selected": 20, "sampled": 1}}, 20, folder, 0, {}, {})
            self.assertTrue(result["pass"])
            self.assertFalse(result["coverage_complete"])

    def test_matrix_runs_distinct_roms_and_locale_results(self):
        import argparse
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ("en", "es"):
                (root / (name + ".nds")).write_bytes(name.encode())
            args = argparse.Namespace(rejudge=None, out=str(root / "run"), locales="en,es",
                                      rom_en=str(root / "en.nds"), rom_es=str(root / "es.nds"),
                                      pairs=False, windows="field", chunk=2, jobs=1,
                                      buffers="typ", limit=None)
            def batches(a, groups, out, jobs):
                self.assertEqual([(g[1], g[2]) for g in groups], [("en", args.rom_en), ("es", args.rom_es)])
                return [{"ref": "a027/0060#27", "lang": lang, "window": "field", "verdict": "pass"}
                        for lang in ("en", "es")]
            with patch.object(T, "select", return_value=([("a027", 60, 27)], "refs", 1)), \
                 patch.object(T, "plan_rows", return_value=({"field": [("a027", 60, 27)]}, [])), \
                 patch.object(T, "_run_batches", side_effect=batches):
                self.assertEqual(T.run(args), 0)
            summary = json.loads((root / "run/summary.json").read_text())
            self.assertEqual(set(summary["roms"]), {"en", "es"})
            self.assertTrue(summary["by_locale"]["es"]["pass"])
            args.out = str(root / "strict")
            args.require_complete = True
            with patch.object(T, "select", return_value=([("a027", 60, 27)], "refs", 1)), \
                 patch.object(T, "plan_rows", side_effect=lambda refs, windows, lang: (
                     {"field": [("a027", 60, 27)]}, [{"ref": "a027/0803#252", "lang": lang,
                     "window": None, "verdict": "unsupported", "reason": "dex category"}])), \
                 patch.object(T, "_run_batches", side_effect=batches):
                self.assertEqual(T.run(args), 1)
            args.out = str(root / "missing")
            args.rom_es = None
            self.assertEqual(T.run(args), 2)
            self.assertFalse((root / "missing").exists())


class Windows(unittest.TestCase):
    def test_real_banks(self):
        self.assertEqual(T.window_for("battle_string", 1, 0), ("battle", None))
        self.assertEqual(T.window_for("battle_string", 2, 32), ("battle", None))
        self.assertEqual(T.window_for("battle_string", 0, 1)[0], "unsupported")
        self.assertIn("battle_info", T.window_for("battle_string", 0, 1)[1])
        self.assertIn("battle_menu", T.window_for("battle_string", 3, 1)[1])
        self.assertEqual(T.window_for("a027", 60, 27), ("field", None))
        self.assertEqual(T.window_for("a027", 218, 5), ("unsupported", "window type item_desc"))

    def test_synthetic_bank(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a027"
            p.mkdir()
            (p / "0999.json").write_text(json.dumps(bank("a027", 999, [
                ("一{SCROLL}二", "One{SCROLL}two"),
                ("一{NEWLINE}二{NEWLINE}三{SCROLL}", "One{NEWLINE}two{NEWLINE}three"),
                ("", "{SCROLL}"),
            ])))
            self.assertEqual(T.window_for("a027", 999, 0, root=d), ("field", None))
            w, why = T.window_for("a027", 999, 1, root=d)
            self.assertEqual(w, "unsupported")
            self.assertIn("dialogue_large", why)
            self.assertEqual(T.window_for("a027", 999, 2, root=d)[0], "empty")


class ExpectedViews(unittest.TestCase):
    def test_scroll_clear_and_the_final_wait(self):
        e = T.expected_views("Third place goes to{NEWLINE}Ace Tom,{CLEAR}who caught a Pidgey!{SCROLL}")
        self.assertEqual(e["views"], [["Third place goes to", "Ace Tom,"], ["Ace Tom,", "who caught a Pidgey!"],
                                      ["Ace Tom,", "who caught a Pidgey!"]])
        self.assertEqual(e["waits"], 3)
        self.assertEqual(e["lost"], [])

    def test_lost_line_and_widths(self):
        e = T.expected_views("aaa{NEWLINE}bbb{NEWLINE}ccc{SCROLL}ddd")
        self.assertEqual(e["lost"], [{"view": 0, "row": 2, "text": "ccc"}])
        self.assertEqual(e["views"], [["aaa", "bbb"], ["ddd", ""]])
        self.assertEqual(e["widths"][0], [T._width("aaa"), T._width("bbb")])

    def test_battle_merges_identical_views(self):
        e = T.expected_views("Hi!{SCROLL}", battle=True)
        self.assertEqual(e["views"], [["Hi!", ""]])

    def test_flags(self):
        self.assertTrue(T.expected_views("Quit?{VAR:0200:0}")["prompt"])
        # the prompt icons sit on the view that waits with {VAR:0200}, also when a {SCROLL} follows it
        self.assertEqual(T.expected_views("Quit?{VAR:0200:0}")["prompt_view"], 0)
        e = T.expected_views("Give Poliwag a nickname?{VAR:0200:0}{SCROLL}")
        self.assertEqual((e["prompt_view"], len(e["views"])), (0, 2))
        self.assertEqual(T.expected_views("Hi!{SCROLL}Quit?{VAR:0200:0}")["prompt_view"], 1)
        self.assertTrue(T.expected_views("{VAR:FF01:200}BIG")["size"])


class FillIns(unittest.TestCase):
    def test_fill_and_expand(self):
        en = "{VAR:0100:0} used {VAR:0106:1}! {VAR:0134:2}"
        fill = T.fillers(en)
        self.assertEqual(set(fill), {0, 1, 2})
        self.assertEqual(fill[2], "888")                       # kind 0x34: three digits
        self.assertLessEqual(T._width(fill[0]), 54)            # species: QA's typical 54 px
        self.assertLessEqual(T._width(fill[1]), 60)
        self.assertGreaterEqual(T._width(fill[0]), 42)
        self.assertEqual(T.expand(en, fill), f"{fill[0]} used {fill[1]}! 888")
        self.assertGreaterEqual(T._width(T.filler("VAR:0100:0", mode="max")), T._width(fill[0]))

    def test_inline_buffers(self):
        units = [0x10, T.CMD, 0x0100, 2, 11, 0, 0x11, T.CMD, 0xFF00, 1, 3, T.CMD, 0x0106, 1, 1]
        self.assertEqual(T._inline_buffers(units, {11: [7, 8]}),
                         [0x10, 7, 8, 0x11, T.CMD, 0xFF00, 1, 3, T.CMD, 0x0106, 1, 1])
        self.assertEqual(T._buffer_indices(units), [11, 1])


# ----------------------------------------------------------------------------- synthetic pixels

def glyph(pattern, w):
    """A glyph: column masks from a pattern of row bits (rows 2-12) per column; width w (advance)."""
    return tuple(pattern[i] & T.ROWMASK if i < len(pattern) else 0 for i in range(w))


GLYPHS = {
    1: ("a", 6, glyph([0b0001111111100, 0b0001000100100, 0b0001000100100, 0b0001111111100, 0, 0], 6)),
    2: ("b", 6, glyph([0b0001111111110, 0b0001000100010, 0b0001000100010, 0b0000111011100, 0, 0], 6)),
    3: ("c", 5, glyph([0b0000111111000, 0b0001000000100, 0b0001000000100, 0, 0], 5)),
    4: (" ", 4, (0, 0, 0, 0)),
}
FONT = T.Font(GLYPHS)
BY_CHAR = {ch: (w, cols) for ch, w, cols in GLYPHS.values()}


def screen(lines, box=BOX):
    """A 256x192 pixel grid with the window's background and `lines` (row texts) printed and clipped as the
    game does (nothing past the window's width)."""
    rows = [[(0, 0, 0)] * 256 for _ in range(192)]
    x0, y0, x1, y1 = box["interior"]
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            rows[y][x] = BG
    for r, text in enumerate(lines[:box["lines"]]):
        x = box["x0"]
        for ch in text:
            w, cols = BY_CHAR[ch]
            for i, m in enumerate(cols):
                if x + i >= box["x0"] + box["width"]:
                    break
                for yy in range(16):
                    if m >> yy & 1:
                        rows[box["y0"] + 16 * r + yy][x + i] = INK
            x += w
    return T.Pixels(rows=rows)


def decode(*views):
    return [T.decode_view(screen(v), BOX, FONT) for v in views]


class Judge(unittest.TestCase):
    def test_decoder_reads_the_synthetic_glyphs(self):
        v = decode(["ab c", "cab"])[0]
        self.assertEqual([r["text"] for r in v["rows"]], ["ab c", "cab"])
        self.assertEqual(v["rows"][0]["right"], 6 + 6 + 4 + 3)   # last ink column of 'c' + 1
        self.assertEqual(v["ink_outside"], 0)

    def test_pass(self):
        exp = T.expected_views("ab{NEWLINE}c{SCROLL}ba")
        res = T.judge(decode(["ab", "c"], ["ba", ""]), exp, BOX)
        self.assertEqual(res["verdict"], "pass", res["reasons"])
        self.assertEqual(res["pages"], 2)

    def test_overflow_cut_at_the_window_edge(self):
        text = "c" + "ab" * 20                                     # 245 px > 216; ink in column 215
        exp = T.expected_views(text)
        res = T.judge(decode([text, ""]), exp, BOX)
        self.assertEqual(res["verdict"], "fail")
        self.assertEqual([r["code"] for r in res["reasons"]], ["overflow"])
        self.assertEqual(res["overflow_px"], T._width(text) - 216)   # QA font widths
        self.assertTrue(decode([text, ""])[0]["rows"][0]["last_col"])

    def test_third_line_is_lost(self):
        exp = T.expected_views("a{NEWLINE}b{NEWLINE}c")
        res = T.judge(decode(["a", "b"]), exp, BOX)
        self.assertEqual([r["code"] for r in res["reasons"]], ["lines"])
        self.assertEqual(res["overflow_lines"], 1)

    def test_missing_page_and_wrong_text(self):
        exp = T.expected_views("ab{SCROLL}ca")
        res = T.judge(decode(["ab", ""]), exp, BOX)
        self.assertIn("pages", [r["code"] for r in res["reasons"]])
        res = T.judge(decode(["ab", ""], ["cb", ""]), exp, BOX)
        self.assertEqual([(r["code"], r["view"], r["row"]) for r in res["reasons"]], [("text", 2, 1)])

    def test_partial_capture_during_a_pause_is_merged(self):
        exp = T.expected_views("abc{SCROLL}a")
        res = T.judge(decode(["ab", ""], ["abc", ""], ["a", ""]), exp, BOX)
        self.assertEqual(res["verdict"], "pass", res["reasons"])

    def test_a_clear_view_that_extends_the_last_is_not_merged(self):
        exp = T.expected_views("ab{NEWLINE}a{CLEAR}ab")
        res = T.judge(decode(["ab", "a"], ["a", "ab"]), exp, BOX)
        self.assertEqual(res["verdict"], "pass", res["reasons"])
        exp = T.expected_views("a{NEWLINE}a{CLEAR}ab")
        res = T.judge(decode(["a", "a"], ["a", "ab"]), exp, BOX)
        self.assertEqual(res["verdict"], "pass", res["reasons"])

    def test_ink_outside_the_text_area(self):
        px = screen(["ab", ""])
        px.rows[BOX["y0"] + 33][100] = INK                       # below the text area, inside the panel
        res = T.judge([T.decode_view(px, BOX, FONT)], T.expected_views("ab"), BOX)
        self.assertEqual([r["code"] for r in res["reasons"]], ["ink"])

    def test_pixels_only_without_a_font(self):
        text = "c" + "ab" * 20
        decoded = [T.decode_view(screen([text, ""]), BOX, None)]
        res = T.judge(decoded, T.expected_views(text), BOX, readback=False)
        self.assertFalse(res["readback"])
        self.assertEqual(sorted({r["code"] for r in res["reasons"]}), ["ink", "overflow"])

    def test_battle_prompt_icons(self):
        box = T.WINDOWS["battle"]
        text = "ab" * 17                                           # 204 px: fits, but past the prompt's 195
        exp = T.expected_views(text + "{VAR:0200:0}", battle=True)
        res = T.judge([T.decode_view(screen([text, ""], box), box, FONT)], exp, box, battle=True)
        self.assertEqual([r["code"] for r in res["reasons"]], ["prompt"])
        res = T.judge([T.decode_view(screen(["ab", ""], box), box, FONT)],
                      T.expected_views("ab{VAR:0200:0}", battle=True), box, battle=True)
        self.assertEqual(res["verdict"], "pass")

    def test_field_prompt_view_is_read_up_to_the_icons(self):
        exp = T.expected_views("ab{VAR:0200:0}")
        px = screen(["ab", ""])
        for y in range(BOX["y0"] + 3, BOX["y0"] + 28):          # the two icons at x 211-228
            for x in range(BOX["x0"] + 195, BOX["x0"] + 213):
                px.rows[y][x] = INK
        res = T.judge([T.decode_view(px, BOX, FONT, limit=BOX["prompt_px"])], exp, BOX)
        self.assertEqual(res["verdict"], "pass", res["reasons"])
        long = "ab" * 17                                           # 204 px: under the icons
        res = T.judge([T.decode_view(screen([long, ""]), BOX, FONT, limit=BOX["prompt_px"])],
                      T.expected_views(long + "{VAR:0200:0}"), BOX)
        self.assertEqual([r["code"] for r in res["reasons"]], ["prompt"])


class ScenarioKind(unittest.TestCase):
    def test_text_fit_observation_validates(self):
        import emu_scenarios as S
        S.check_step("s", {"observe": "fit", "text_fit": "60#27"})
        with self.assertRaises(S.ScenarioError):
            S.check_step("s", {"observe": "fit", "text_fit": "battle_string/0002#32"})


if __name__ == "__main__":
    unittest.main()
