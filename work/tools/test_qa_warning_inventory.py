"""Synthetic checks that warning reconciliation never loses duplicate findings."""
import unittest
import qa_warning_inventory as audit


def issue(code="number_missing", msg="number 3 from zh not found in en"):
    return dict(narc="a027", bank=1, id=2, level="warning", code=code, msg=msg)


def report(issues):
    return {"summary": {"warnings": sum(i["level"] == "warning" for i in issues),
                        "errors": sum(i["level"] == "error" for i in issues)}, "issues": issues}


class WarningInventoryTests(unittest.TestCase):
    def test_duplicate_numbers_are_independently_accounted(self):
        result = audit.reconcile(report([issue(), issue()]), report([issue()]))
        self.assertEqual(result["summary"]["still_reported"], 1)
        self.assertEqual(result["summary"]["no_longer_reported"], 1)
        self.assertEqual([r["baseline_index"] for r in result["baseline_ledger"]], [0, 1])

    def test_new_number_warning_is_not_hidden_by_net_reduction(self):
        result = audit.reconcile(report([issue(), issue()]), report([issue(msg="number 4 missing")]))
        self.assertEqual(result["summary"]["no_longer_reported"], 2)
        self.assertEqual(result["summary"]["newly_reported"], 1)
        self.assertEqual(result["summary"]["current_warnings"], 1)

    def test_spacing_projection_change_does_not_fake_a_resolution(self):
        result = audit.reconcile(report([issue("whitespace", "old excerpt")]),
                                 report([issue("whitespace", "new excerpt")]))
        self.assertEqual(result["summary"]["still_reported"], 1)

    def test_review_requires_exact_reference_and_unique_index(self):
        row = {"baseline_index": 0, "ref": "a027/0001#2", "classification": "candidate"}
        result = audit.reconcile(report([issue()]), report([issue()]), [[row]])
        self.assertEqual(result["baseline_ledger"][0]["translation_acceptance"], "not_granted")
        for rows in ([row, row], [dict(row, ref="a027/0002#2")], [dict(row, baseline_index=True)]):
            with self.assertRaises(ValueError):
                audit.reconcile(report([issue()]), report([issue()]), [rows])

    def test_bad_counts_and_issue_types_fail(self):
        for data in ({}, {"summary": {"warnings": 0, "errors": 0}, "issues": [issue()]},
                     report([dict(issue(), id=True)])):
            with self.assertRaises(ValueError):
                audit.reconcile(data, report([]))
