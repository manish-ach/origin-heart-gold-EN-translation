import json
from pathlib import Path
import tempfile
import unittest

import qa
import ws
import zh_redact

LYRIC = "测试歌词一"


class RedactionTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.extract = self.root / "extract"
        self.ws = self.root / "banks"
        (self.extract / "a027").mkdir(parents=True)
        self.src = {"bank": 48, "seed": 1, "strings": [{"id": 0, "text": LYRIC}, {"id": 1, "text": "你好"}]}
        (self.extract / "a027" / "0048.json").write_text(json.dumps(self.src, ensure_ascii=False), encoding="utf-8")
        ws.init_bank("a027", self.extract / "a027" / "0048.json", self.ws)
        self.path = self.ws / "a027" / "0048.json"
        b = ws.load_json(self.path)
        for e in b["strings"]:
            e.update(en="Hum" if e["id"] == 0 else "Hello", status="draft", origin="agent")
        ws.save_json(self.path, b)

    def bank(self):
        return ws.load_json(self.path)

    def test_marker_matches_only_its_text(self):
        mk = zh_redact.marker(LYRIC)
        self.assertNotIn(LYRIC, mk)
        self.assertTrue(zh_redact.matches(mk, LYRIC))
        self.assertTrue(zh_redact.matches(LYRIC, LYRIC))
        self.assertFalse(zh_redact.matches(mk, "你好"))
        self.assertFalse(zh_redact.matches(mk, None))

    def test_redact_then_export_init_and_hydrate(self):
        self.assertEqual(ws.redact(self.ws, self.extract, "a027", 48, [0]), 1)
        self.assertEqual(ws.redact(self.ws, self.extract, "a027", 48, [0]), 0)       # idempotent
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn(LYRIC, raw)
        # export still uses the English for the redacted string
        out = self.root / "out"
        counts, problems = ws.export(self.ws, self.extract, out, narcs=["a027"])
        self.assertEqual(problems, [])
        texts = [s["text"] for s in json.loads((out / "a027" / "0048.json").read_text(encoding="utf-8"))["strings"]]
        self.assertEqual(texts, ["Hum", "Hello"])
        # init keeps the marker and does not flag zh_changed
        ws.init_bank("a027", self.extract / "a027" / "0048.json", self.ws)
        self.assertEqual(self.path.read_text(encoding="utf-8"), raw)
        # QA sees the real text in memory; the file is untouched
        hyd, n = zh_redact.hydrate(self.bank(), self.extract)
        self.assertEqual((n, hyd["strings"][0]["zh"]), (1, LYRIC))
        self.assertTrue(zh_redact.is_marker(self.bank()["strings"][0]["zh"]))

    def test_changed_source_is_not_matched(self):
        ws.redact(self.ws, self.extract, "a027", 48, [0])
        self.src["strings"][0]["text"] = "测试歌词二"
        (self.extract / "a027" / "0048.json").write_text(json.dumps(self.src, ensure_ascii=False), encoding="utf-8")
        zh_redact._source_texts.cache_clear()
        _, problems = ws.export(self.ws, self.extract, self.root / "out", narcs=["a027"])
        self.assertEqual([p[2] for p in problems], [0])
        hyd, n = zh_redact.hydrate(self.bank(), self.extract)
        self.assertEqual(n, 0)

    def test_redact_refuses_edited_zh(self):
        b = self.bank()
        b["strings"][1]["zh"] = "改过"
        ws.save_json(self.path, b)
        with self.assertRaises(SystemExit):
            ws.redact(self.ws, self.extract, "a027", 48, [1])

    def test_qa_check_hydrates(self):
        ws.redact(self.ws, self.extract, "a027", 48, [0])
        old = qa.EXTRACT_DIR
        qa.EXTRACT_DIR = self.extract
        try:
            zh_redact._source_texts.cache_clear()
            r = qa.run_check(self.path)
        finally:
            qa.EXTRACT_DIR = old
        self.assertEqual(r["summary"]["errors"], 0)


class PassthroughTests(unittest.TestCase):
    def test_init_regenerates_foreign_language_bank_as_copies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "extract" / "a027").mkdir(parents=True)
            src = {"bank": 794, "seed": 1, "strings": [{"id": 0, "text": "Pokémon Graine"}, {"id": 1, "text": "-----"}]}
            (root / "extract" / "a027" / "0794.json").write_text(json.dumps(src, ensure_ascii=False), encoding="utf-8")
            ws.init_bank("a027", root / "extract" / "a027" / "0794.json", root / "banks")
            s = ws.load_json(root / "banks" / "a027" / "0794.json")["strings"]
            self.assertEqual(s[0], {"id": 0, "zh": "Pokémon Graine", "en": "Pokémon Graine", "status": "draft",
                                    "origin": "copy", "notes": "foreign-language data, kept as is (French)"})
            self.assertEqual((s[1]["en"], s[1]["origin"], s[1]["notes"]), ("-----", "copy", ""))


if __name__ == "__main__":
    unittest.main()
