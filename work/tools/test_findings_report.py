#!/usr/bin/env python3
"""Tests for findings_report.py.   Run:  python3 -m unittest -v work/tools/test_findings_report.py"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import findings_report as F  # noqa: E402


class FindingsReportTest(unittest.TestCase):
    def test_report_groups_and_merges_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "ws" / "a027").mkdir(parents=True)
            (tmp / "ws" / "a027" / "0548.json").write_text(json.dumps({"narc": "a027", "bank": 548, "strings": [
                {"id": 114, "zh": "唉,我的玛力露丽就这样走了……", "en": "My Azumarill just left like that..."}]},
                ensure_ascii=False), encoding="utf-8")
            reg = tmp / "decisions.jsonl"
            reg.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
                {"id": "D-0001", "type": "question", "subtype": "hack-finding", "status": "open",
                 "refs": ["a027/0548#114"], "en": "Says 玛力露丽 (Azumarill); the rest of the scene says Marill (wrong Pokémon name)."},
                {"id": "D-0002", "type": "term", "subtype": "character", "refs": ["a027/0001#1"], "en": "Red"},
            ]) + "\n", encoding="utf-8")
            imp = tmp / "import.jsonl"
            imp.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
                {"ref": "a027/0548#114", "zh_excerpt": "dup", "what_looks_wrong": "duplicate of D-0001",
                 "current_en": "x", "action": "reverted", "kind": "pokemon-or-name"},
                {"ref": "a027/0608#34", "zh_excerpt": "看不见的官材", "what_looks_wrong": "官材 for 棺材",
                 "current_en": "I call it the Invisible Coffin.", "action": "kept-typo", "related_question_ids": []},
                {"ref": "a027/0369#146", "zh_excerpt": "小蓝『你看呐", "what_looks_wrong": "Red-branch line labelled 小蓝.",
                 "current_en": "Green: Look.", "action": "reverted", "related_question_ids": ["D-0532"]},
            ]) + "\n", encoding="utf-8")
            out = tmp / "HACK_FINDINGS.md"
            F.main(["--register", str(reg), "--import", str(imp), "--ws", str(tmp / "ws"), "--out", str(out)])
            md = out.read_text(encoding="utf-8")

        self.assertIn("| **Total** | **3** |", md)          # term record ignored, duplicate import skipped
        name = md.index("## Wrong Pokémon or name")
        label = md.index("## Speaker label")
        typo = md.index("## Typo")
        self.assertLess(name, md.index("### a027/0548#114"))
        self.assertLess(md.index("### a027/0548#114"), label)
        self.assertLess(label, md.index("### a027/0369#146"))
        self.assertLess(typo, md.index("### a027/0608#34"))
        self.assertIn("`My Azumarill just left like that...`", md)   # current English read from the bank
        self.assertIn("`看不见的官材`", md)
        self.assertIn("**Related:** D-0532", md)
        self.assertNotIn("duplicate of D-0001", md)

    def test_classify_keywords(self):
        self.assertEqual(F.classify({"en": "zh calls Red 她; Red is male"}), "gender")
        self.assertEqual(F.classify({"what_looks_wrong": "asks for at least 6 Pokémon for a 3-on-3"}), "number")
        self.assertEqual(F.classify({"action": "kept-typo", "what_looks_wrong": "x"}), "typo")
        self.assertEqual(F.classify({"kind": "label"}), "speaker-label")


if __name__ == "__main__":
    unittest.main()
