#!/usr/bin/env python3
"""Reconcile QA warning reports without suppressing or accepting any findings."""
import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1] / "build"


def checked_issues(report):
    if not isinstance(report, dict) or not isinstance(report.get("issues"), list):
        raise ValueError("QA report must contain an issues list")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("Missing QA summary")
    for issue in report["issues"]:
        if (not isinstance(issue, dict) or issue.get("level") not in ("warning", "error")
                or any(not isinstance(issue.get(k), str) or not issue[k] for k in ("narc", "code", "msg"))
                or any(type(issue.get(k)) is not int or issue[k] < 0 for k in ("bank", "id"))):
            raise ValueError("Malformed QA issue")
    for level, field in (("warning", "warnings"), ("error", "errors")):
        if type(summary.get(field)) is not int or summary[field] != sum(i["level"] == level for i in report["issues"]):
            raise ValueError("QA summary contradicts actual issues")
    return report["issues"]


def issue_key(issue):
    # Whitespace projection can change the diagnostic excerpt without changing
    # which entry has a real spacing warning. Other messages distinguish multiple
    # terms/numbers/lines within the same string. Duplicates remain a multiset.
    return tuple(issue[k] for k in ("narc", "bank", "id", "level", "code")) + (
        "" if issue["code"] == "whitespace" else issue["msg"],)


def reference(issue):
    return f"{issue['narc']}/{issue['bank']:04d}#{issue['id']}"


def reconcile(baseline, current, reviews=()):
    old, new = checked_issues(baseline), checked_issues(current)
    annotations = {}
    for review in reviews:
        if not isinstance(review, list):
            raise ValueError("A review must be a list of baseline-indexed records")
        for row in review:
            index = row.get("baseline_index") if isinstance(row, dict) else None
            if (type(index) is not int or not 0 <= index < len(old)
                    or old[index]["level"] != "warning" or index in annotations
                    or row.get("ref") != reference(old[index])):
                raise ValueError("Review has duplicate, invalid, or mismatched baseline index")
            annotations[index] = row
    available = defaultdict(deque)
    for index, issue in enumerate(new):
        if issue["level"] == "warning":
            available[issue_key(issue)].append(index)
    ledger = []
    for index, issue in enumerate(old):
        if issue["level"] != "warning":
            continue
        matches = available[issue_key(issue)]
        current_index = matches.popleft() if matches else None
        ledger.append({"baseline_index": index, "ref": reference(issue), "issue": issue,
                       "current_index": current_index,
                       "emission": "still_reported" if current_index is not None else "not_reported_after_checker_change",
                       "review": annotations.get(index), "translation_acceptance": "not_granted"})
    added = [{"current_index": index, "ref": reference(new[index]), "issue": new[index],
              "emission": "newly_reported", "translation_acceptance": "not_granted"}
             for index in sorted(i for matches in available.values() for i in matches)]
    surviving = sum(row["emission"] == "still_reported" for row in ledger)
    summary = {"baseline_warnings": len(ledger), "current_warnings": current["summary"]["warnings"],
               "still_reported": surviving, "no_longer_reported": len(ledger) - surviving,
               "newly_reported": len(added), "annotated_baseline_warnings": len(annotations),
               "current_unique_strings": len({reference(i) for i in new if i["level"] == "warning"}),
               "current_by_code": dict(Counter(i["code"] for i in new if i["level"] == "warning")),
               "current_errors": current["summary"]["errors"],
               "policy": "Every current warning remains open in QA. Review classification is not acceptance or suppression."}
    assert surviving + len(added) == summary["current_warnings"]
    return {"summary": summary, "baseline_ledger": ledger, "new_warnings": added}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--review", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    output = args.out.resolve()
    if output == BUILD.resolve() or not output.is_relative_to(BUILD.resolve()) or output.exists():
        parser.error("--out must be a new directory under ignored work/build")
    paths = [args.baseline, args.current, *args.review]
    contents = [path.read_bytes() for path in paths]
    payloads = [json.loads(content) for content in contents]
    result = reconcile(payloads[0], payloads[1], payloads[2:])
    result["inputs"] = [{"path": str(path.resolve()), "sha256": hashlib.sha256(content).hexdigest()}
                        for path, content in zip(paths, contents)]
    output.mkdir(parents=True)
    (output / "ledger.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    (output / "summary.json").write_text(json.dumps(result["summary"], indent=2) + "\n")
    print(json.dumps(result["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
