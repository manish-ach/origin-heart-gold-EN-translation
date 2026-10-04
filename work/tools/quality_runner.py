#!/usr/bin/env python3
"""Run local unittest suites and translation QA with an auditable JSON report."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import signal
import struct
from pathlib import Path
import subprocess
import sys
import time
import unittest

import runtime_reproducibility as REPRO
import runtime_rendering as RENDER

ROOT = Path(__file__).resolve().parents[2]
CHECKS = ("tools", "docs", "qa", "runtime", "artifacts", "buffers", "text_static", "native_loading")
DEFAULT_CHECKS = CHECKS[:3]


def write_json(path, data):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_suite(directory, output):
    """Child-process entry point: structured results without parsing unittest output."""
    try:
        suite = unittest.defaultTestLoader.discover(str(directory), pattern="test_*.py")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        unavailable = any("ModuleNotFoundError:" in detail for _, detail in result.errors)
        summary = {
            "tests": result.testsRun, "failures": len(result.failures),
            "errors": len(result.errors), "skipped": len(result.skipped),
            "skip_details": [{"test": str(test), "reason": reason} for test, reason in result.skipped],
            "failure_details": [{"test": str(test), "traceback": detail} for test, detail in result.failures],
            "error_details": [{"test": str(test), "traceback": detail} for test, detail in result.errors],
            "status": "unavailable" if unavailable else (
                ("incomplete" if result.skipped else "passed")
                if result.wasSuccessful() and result.testsRun else "failed"),
        }
        if not result.testsRun:
            summary["reason"] = "Discovery returned zero tests"
    except Exception as exc:
        summary = {"status": "unavailable", "reason": f"{type(exc).__name__}: {exc}"}
    write_json(output, summary)
    return 0 if summary["status"] == "passed" else 1


def run_check(name, command, output_dir, timeout, payload_path):
    log_path = output_dir / f"{name}.log"
    record = {"name": name, "command": command, "cwd": str(ROOT),
              "log": str(log_path), "returncode": None, "status": "failed"}
    start = time.monotonic()
    with log_path.open("w", encoding="utf-8") as log:
        try:
            process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=os.name == "posix")
            try:
                record["returncode"] = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == "posix":
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                else:
                    process.kill()
                process.wait()
                raise
        except subprocess.TimeoutExpired:
            record.update(status="timeout", reason=f"Exceeded {timeout:g} seconds")
        except OSError as exc:
            record.update(status="unavailable", reason=f"{type(exc).__name__}: {exc}")
    record["duration_seconds"] = round(time.monotonic() - start, 3)
    if record["status"] in ("timeout", "unavailable"):
        return record
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        if name == "qa":
            summary = payload["summary"]
            record["summary"] = summary
            record["details"] = str(payload_path)
            valid = summary["banks"] > 0 and summary["strings_checked"] > 0
            record["status"] = "passed" if valid and not summary["errors"] and record["returncode"] == 0 else "failed"
            if not valid:
                record["reason"] = "QA checked zero banks or zero translated strings"
        elif name == "artifacts":
            record.update(summary=payload.get("export", {}).get("counts", {}),
                          details=str(payload_path), status=artifact_status(payload))
            if payload.get("reason"):
                record["reason"] = payload["reason"]
            if record["returncode"] != 0 and record["status"] == "passed":
                record.update(status="failed", reason="Process failed despite passing result payload")
        elif name == "text_static":
            from static_text_check import aggregate_report
            record.update(summary=payload.get("counts", {}), details=str(payload_path),
                          status=aggregate_report(payload))
            if record["returncode"] != 0 and record["status"] == "passed":
                record.update(status="failed", reason="Process failed despite passing result payload")
        elif name == "native_loading":
            from native_load_validation import validate_file
            validation = validate_file(payload_path)
            write_json(output_dir / "native-loading-validation.json", validation)
            verified = validation["status"]
            status = {"pass": "passed", "passed_with_semantic_gaps": "incomplete", "fail": "failed"}[verified]
            record.update(details=str(payload_path), status=status, summary={
                "entries": validation["entry_count"], "semantic_gaps": validation["semantic_gaps"],
                "native_calls": payload.get("native_calls"), "heap_checks": payload.get("heap_checks"),
                "validation": str(output_dir / "native-loading-validation.json")})
            if record["returncode"] != 0:
                record.update(status="failed", reason="Native loading process did not complete successfully")
        elif name == "buffers":
            record.update(summary={key: payload.get(key) for key in
                          ("capacity", "checked_strings", "maximum_stored_units")},
                          details=str(payload_path), status=buffer_status(payload))
            record["summary"]["overflows"] = len(payload.get("findings", []))
            record["summary"]["workspace_overflows"] = len(payload.get("workspace", {}).get("findings", []))
            if record["returncode"] != 0 and record["status"] == "passed":
                record.update(status="failed", reason="Process failed despite passing result payload")
        elif name == "runtime":
            record.update(summary=payload["counts"], details=str(payload_path),
                          status=runtime_status(payload))
            record["summary"]["findings"] = sum(len(entry.get("findings", []))
                for entry in payload["scenarios"].values())
            record["summary"]["memory_passed"] = sum(entry.get("memory_status") == "passed"
                for entry in payload["scenarios"].values())
            record["summary"]["coverage_passed"] = sum(objective_coverage_complete(entry)
                for entry in payload["scenarios"].values())
            record["summary"]["text_passed"] = sum(text_evidence_complete(entry)
                for entry in payload["scenarios"].values())
            record["summary"]["state_passed"] = sum(state_evidence_status(entry) == "passed"
                for entry in payload["scenarios"].values())
            record["summary"]["state_not_configured"] = sum(state_evidence_status(entry) == "not_configured"
                for entry in payload["scenarios"].values())
            record["summary"]["summary_state_passed"] = sum(summary_evidence_status(entry) == "passed"
                for entry in payload["scenarios"].values())
            record["summary"]["move_state_passed"] = sum(move_evidence_status(entry) == "passed"
                for entry in payload["scenarios"].values())
            record["summary"]["rendering_passed"] = sum(rendering_evidence_status(entry) == "passed"
                for entry in payload["scenarios"].values())
            record["summary"]["reproducibility_status"] = runtime_provenance_status(payload)
            record["prerequisite_errors"] = payload.get("errors", [])
            if record["returncode"] != 0 and record["status"] == "passed":
                record.update(status="failed", reason="Process failed despite passing result payload")
        else:
            record["summary"] = payload
            record["status"] = payload["status"]
            if record["returncode"] != 0 and record["status"] == "passed":
                record.update(status="failed", reason="Process failed despite passing result payload")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        record.update(status="failed", reason=f"Missing or invalid result payload: {exc}")
    return record


def aggregate_status(statuses):
    for status in ("failed", "timeout", "unavailable", "incomplete"):
        if status in statuses:
            return status
    return "passed" if statuses and all(s == "passed" for s in statuses) else "failed"


def buffer_status(payload):
    status = payload["status"]
    if status not in ("passed", "failed", "incomplete"):
        raise ValueError("Unknown buffer status")
    if status != "passed":
        return status
    capacity = payload["capacity"]
    if not isinstance(capacity, int) or isinstance(capacity, bool) or capacity <= 0:
        return "failed"
    for result in (payload, payload["workspace"]):
        count = result["checked_strings"]
        maximum = result["maximum_stored_units"]
        if (not isinstance(count, int) or isinstance(count, bool) or count <= 0
                or not isinstance(maximum, int) or isinstance(maximum, bool)
                or not 0 < maximum <= capacity or result["status"] != "passed"
                or result["findings"]):
            return "failed"
    return "passed"


def artifact_status(payload):
    status = payload["status"]
    if status not in ("passed", "failed", "incomplete"):
        raise ValueError("Unknown artifact status")
    if status != "passed":
        return status
    counts = payload["export"]["counts"]
    if (not isinstance(counts.get("strings"), int) or isinstance(counts["strings"], bool)
            or counts["strings"] <= 0 or payload["export"].get("problems")
            or any(payload.get("checks", {}).get(key) != "passed" for key in ("identity", "export", "artifact"))
            or not isinstance(payload.get("verification"), dict) or not payload["verification"]):
        return "failed"
    return "passed"


def objective_coverage_complete(entry):
    return (isinstance(entry.get("coverage"), dict)
            and set(entry["coverage"]) == {"zh", "en"}
            and all(isinstance(coverage, dict) and coverage.get("status") == "passed" and coverage.get("gaps") == []
                    and isinstance(coverage.get("scope"), str) and bool(coverage["scope"].strip())
                    for coverage in entry.get("coverage", {}).values()))


def text_evidence_complete(entry):
    if entry.get("text_status") != "passed":
        return False
    gaps = entry.get("text_evidence_gaps")
    if not isinstance(gaps, dict) or set(gaps) != {"zh", "en"} or any(value != [] for value in gaps.values()):
        return False
    runs = entry.get("runs", {})
    if not isinstance(runs, dict) or set(runs) != {"zh", "en"}:
        return False
    for run in runs.values():
        if not isinstance(run, dict):
            return False
        raw = run.get("raw")
        if not isinstance(raw, dict):
            return False
        checks = raw.get("text_copy_checks")
        if (not isinstance(checks, int) or isinstance(checks, bool) or checks <= 0
                or raw.get("text_probe_errors") != []):
            return False
    return True


def state_evidence_status(entry):
    """Recheck configured party permutations rather than trusting a status label."""
    status = entry.get("state_status")
    if status == "failed":
        return "failed"
    expectations = entry.get("state_expectations")
    if not isinstance(expectations, dict):
        return "incomplete"
    if not expectations:
        return "not_configured" if status == "not_configured" else "incomplete"
    count = entry.get("party_size")
    if status != "passed" or type(count) is not int or not 1 <= count <= 6:
        return "incomplete"
    evidence, runs = entry.get("state_evidence"), entry.get("runs")
    if (not isinstance(evidence, dict) or set(evidence) != {"zh", "en"}
            or not isinstance(runs, dict) or set(runs) != {"zh", "en"}):
        return "incomplete"
    for tag in ("zh", "en"):
        proof = evidence[tag]
        if not isinstance(proof, dict) or proof.get("gaps") != [] or proof.get("mismatches") != []:
            return "incomplete"
        if not isinstance(runs[tag], dict):
            return "incomplete"
        raw = runs[tag].get("raw")
        checkpoints = raw.get("checkpoints") if isinstance(raw, dict) else None
        if not isinstance(checkpoints, dict):
            return "incomplete"
        for name, expected in expectations.items():
            if not isinstance(expected, dict):
                return "incomplete"
            order, relative = expected.get("order"), expected.get("relative_to")
            if (not isinstance(relative, str) or not isinstance(order, list)
                    or any(type(i) is not int for i in order) or sorted(order) != list(range(count))):
                return "incomplete"
            snapshots = []
            frames = []
            for checkpoint_name in (relative, name):
                checkpoint = checkpoints.get(checkpoint_name)
                if not isinstance(checkpoint, dict) or type(checkpoint.get("frame")) is not int:
                    return "incomplete"
                frames.append(checkpoint["frame"])
                party = checkpoint.get("party")
                if (not isinstance(party, dict) or party.get("status") != "passed"
                        or type(party.get("count")) is not int or party["count"] != count
                        or party.get("error")):
                    return "incomplete"
                address = party.get("address")
                if (type(address) is not int or address % 4
                        or not 0x02000000 <= address <= 0x02400000 - (8 + 6 * 236)):
                    return "incomplete"
                identities = party.get("identities")
                if (not isinstance(identities, list) or len(identities) != count
                        or any(type(identity) is not int or not 0 <= identity <= 0xFFFFFFFF for identity in identities)
                        or len(set(identities)) != count):
                    return "incomplete"
                snapshots.append(identities)
            if not 0 <= frames[0] < frames[1] or snapshots[1] != [snapshots[0][i] for i in order]:
                return "incomplete"
    return "passed"


def summary_evidence_status(entry):
    """Require a fresh summary selection tied to a bounded party identity."""
    status, expectations = entry.get("summary_status"), entry.get("summary_expectations")
    if status == "failed":
        return "failed"
    if not isinstance(expectations, dict):
        return "incomplete"
    if not expectations:
        return "not_configured" if status == "not_configured" else "incomplete"
    count = entry.get("party_size")
    if status != "passed" or type(count) is not int or not 1 <= count <= 6:
        return "incomplete"
    evidence, runs = entry.get("summary_evidence"), entry.get("runs")
    if (not isinstance(evidence, dict) or set(evidence) != {"zh", "en"}
            or not isinstance(runs, dict) or set(runs) != {"zh", "en"}):
        return "incomplete"
    for tag in ("zh", "en"):
        proof = evidence[tag]
        if not isinstance(proof, dict) or proof.get("gaps") != [] or proof.get("mismatches") != []:
            return "incomplete"
        if not isinstance(runs[tag], dict):
            return "incomplete"
        raw = runs[tag].get("raw")
        checkpoints = raw.get("checkpoints") if isinstance(raw, dict) else None
        if not isinstance(checkpoints, dict):
            return "incomplete"
        for name, expected in expectations.items():
            if not isinstance(expected, dict) or not isinstance(expected.get("since"), str):
                return "incomplete"
            slot = expected.get("slot")
            if type(slot) is not int or not 0 <= slot < count:
                return "incomplete"
            start, stop = checkpoints.get(expected["since"]), checkpoints.get(name)
            if not isinstance(start, dict) or not isinstance(stop, dict):
                return "incomplete"
            if (type(start.get("frame")) is not int or type(stop.get("frame")) is not int
                    or not 0 <= start["frame"] < stop["frame"]):
                return "incomplete"
            selection, party = stop.get("summary"), stop.get("party")
            if not isinstance(selection, dict) or not isinstance(party, dict):
                return "incomplete"
            if any(obj.get("status") != "passed" or obj.get("error") for obj in (selection, party)):
                return "incomplete"
            address, context = party.get("address"), selection.get("context_address")
            screen = selection.get("screen_address")
            if (type(address) is not int or address % 4
                    or not 0x02000000 <= address <= 0x02400000 - (8 + 6 * 236)
                    or type(context) is not int or context % 4 or not 0x02000000 <= context <= 0x02400000 - 0x15
                    or type(screen) is not int or screen % 4 or not 0x02000000 <= screen <= 0x02400000 - 0x240):
                return "incomplete"
            identities = party.get("identities")
            if (type(party.get("count")) is not int or party['count'] != count
                    or not isinstance(identities, list) or len(identities) != count
                    or any(type(i) is not int or not 0 <= i <= 0xFFFFFFFF for i in identities)
                    or len(set(identities)) != count):
                return "incomplete"
            observed = selection.get("observed_frame")
            if (type(observed) is not int or not start["frame"] < observed <= stop["frame"]
                    or type(selection.get("slot")) is not int or selection["slot"] != slot
                    or type(selection.get("identity")) is not int or selection["identity"] != identities[slot]
                    or type(selection.get("party_address")) is not int or selection["party_address"] != address
                    or type(selection.get("address")) is not int or selection["address"] != address + 8 + 236 * slot):
                return "incomplete"
    return "passed"


# Physical offsets for logical block B, independently checked against the guarded
# Chinese ROM table at 0x020FE963 (32 rows, selected by PID bits 13..17).
MOVE_BLOCK_OFFSETS = (32, 32, 64, 96, 64, 96, 0, 0, 0, 0, 0, 0, 64, 96, 32, 32,
                      96, 64, 64, 96, 32, 32, 96, 64, 32, 32, 64, 96, 64, 96, 0, 0)


def decode_stored_moves(payload):
    """Independently check a copied encrypted box record; never access emulator RAM."""
    if not isinstance(payload, str) or len(payload) != 272:
        return None
    try:
        data = bytes.fromhex(payload)
    except ValueError:
        return None
    if len(data) != 136:
        return None
    identity, flags, checksum = struct.unpack_from('<IHH', data)
    if flags != 0:
        return None
    state = checksum
    words = []
    for encoded in struct.unpack_from('<64H', data, 8):
        state = (state * 0x41C64E6D + 0x6073) & 0xFFFFFFFF
        words.append(encoded ^ (state >> 16))
    if sum(words) & 0xFFFF != checksum:
        return None
    offset = MOVE_BLOCK_OFFSETS[(identity >> 13) & 31]
    return {'identity': identity, 'checksum': checksum,
            'moves': words[offset // 2:offset // 2 + 4]}


def move_evidence_status(entry):
    """Verify copied stored data and exact permutations, independent of the probe decoder."""
    status, expectations = entry.get('move_status'), entry.get('move_expectations')
    if status == 'failed':
        return 'failed'
    if not isinstance(expectations, dict):
        return 'incomplete'
    if not expectations:
        return 'not_configured' if status == 'not_configured' else 'incomplete'
    count = entry.get('party_size')
    if status != 'passed' or type(count) is not int or not 1 <= count <= 6:
        return 'incomplete'
    evidence, runs = entry.get('move_evidence'), entry.get('runs')
    if (not isinstance(evidence, dict) or set(evidence) != {'zh', 'en'}
            or not isinstance(runs, dict) or set(runs) != {'zh', 'en'}):
        return 'incomplete'
    for tag in ('zh', 'en'):
        proof = evidence[tag]
        if not isinstance(proof, dict) or proof.get('gaps') != [] or proof.get('mismatches') != []:
            return 'incomplete'
        if not isinstance(runs[tag], dict):
            return "incomplete"
        raw = runs[tag].get('raw')
        checkpoints = raw.get('checkpoints') if isinstance(raw, dict) else None
        if not isinstance(checkpoints, dict):
            return 'incomplete'
        for name, expected in expectations.items():
            if not isinstance(expected, dict) or not isinstance(expected.get('relative_to'), str):
                return 'incomplete'
            if 'summary_closed' in expected and expected['summary_closed'] is not True:
                return 'incomplete'
            order, target = expected.get('order'), expected.get('slot')
            if (type(target) is not int or not 0 <= target < count or not isinstance(order, list)
                    or any(type(i) is not int for i in order) or order != [1, 0, 2, 3]):
                return 'incomplete'
            pair = []
            for checkpoint_name in (expected['relative_to'], name):
                point = checkpoints.get(checkpoint_name)
                if not isinstance(point, dict) or type(point.get('frame')) is not int or point['frame'] < 0:
                    return 'incomplete'
                party, snapshot = point.get('party'), point.get('moves')
                if not isinstance(party, dict) or not isinstance(snapshot, dict):
                    return 'incomplete'
                if any(value.get('status') != 'passed' or value.get('error') for value in (party, snapshot)):
                    return 'incomplete'
                address, identities = party.get('address'), party.get('identities')
                if (type(address) is not int or address % 4
                        or not 0x02000000 <= address <= 0x02400000 - (8 + 6 * 236)
                        or type(party.get('count')) is not int or party['count'] != count
                        or not isinstance(identities, list) or len(identities) != count
                        or any(type(i) is not int or not 0 <= i <= 0xFFFFFFFF for i in identities)
                        or len(set(identities)) != count
                        or type(snapshot.get('party_address')) is not int or snapshot['party_address'] != address
                        or type(snapshot.get('observed_frame')) is not int or snapshot['observed_frame'] != point['frame']):
                    return 'incomplete'
                slots = snapshot.get('slots')
                if not isinstance(slots, list) or len(slots) != count:
                    return 'incomplete'
                decoded_slots = []
                for index, saved in enumerate(slots):
                    if (not isinstance(saved, dict) or type(saved.get('slot')) is not int or saved['slot'] != index
                            or type(saved.get('address')) is not int or saved['address'] != address + 8 + 236 * index):
                        return 'incomplete'
                    decoded = decode_stored_moves(saved.get('boxed_hex'))
                    if (decoded is None or decoded['identity'] != identities[index]
                            or type(saved.get('identity')) is not int or saved['identity'] != decoded['identity']
                            or type(saved.get('checksum')) is not int or saved['checksum'] != decoded['checksum']
                            or not isinstance(saved.get('moves'), list)
                            or any(type(i) is not int for i in saved['moves']) or saved['moves'] != decoded['moves']):
                        return 'incomplete'
                    decoded_slots.append(decoded)
                pair.append((point['frame'], address, decoded_slots))
            before, after = pair
            if before[0] >= after[0] or before[1] != after[1]:
                return 'incomplete'
            if expected.get('summary_closed'):
                previous = checkpoints[expected['relative_to']].get('summary')
                closed = checkpoints[name].get('summary')
                if (not isinstance(previous, dict) or previous.get('status') != 'passed' or previous.get('error')
                        or type(previous.get('identity')) is not int or previous['identity'] != before[2][target]['identity']
                        or type(previous.get('address')) is not int or previous['address'] != before[1] + 8 + 236 * target
                        or not isinstance(closed, dict) or closed.get('status') != 'incomplete'
                        or 'context_address' not in closed or closed['context_address'] is not None
                        or 'screen_address' not in closed or closed['screen_address'] is not None
                        or type(closed.get('observed_frame')) is not int or closed['observed_frame'] != -1):
                    return 'incomplete'
            for index, (old, new) in enumerate(zip(before[2], after[2])):
                if old['identity'] != new['identity']:
                    return 'incomplete'
                wanted = [old['moves'][i] for i in order] if index == target else old['moves']
                if index == target and (not all(old['moves'][:2]) or old['moves'][0] == old['moves'][1]
                                        or wanted == old['moves']):
                    return 'incomplete'
                if new['moves'] != wanted:
                    return 'incomplete'
    return 'passed'


def runtime_text_rejection_status(entry):
    """Rebuild paired rejection signatures so a stale summary cannot hide a rejection."""
    signatures = {}
    runs = entry.get("runs")
    if not isinstance(runs, dict) or set(runs) != {"zh", "en"}:
        return "incomplete"
    for tag, run in runs.items():
        raw = run.get("raw") if isinstance(run, dict) else None
        events = raw.get("text_rejections") if isinstance(raw, dict) else None
        if not isinstance(events, list):
            return "incomplete"
        signatures[tag] = set()
        for event in events:
            if not isinstance(event, dict):
                return "incomplete"
            keys = ("caller", "capacity", "item", "item_caller") if "item" in event else ("caller", "capacity", "units")
            if any(type(event.get(key)) is not int or event[key] < 0 for key in keys):
                return "incomplete"
            signatures[tag].add(("item" if "item" in event else "generic", *(event[key] for key in keys)))
    if signatures["en"] - signatures["zh"]:
        return "failed"
    return "incomplete" if signatures["zh"] - signatures["en"] else "passed"


def validate_runtime_shape(payload):
    """Reject malformed report containers before walking nested evidence."""
    if not isinstance(payload, dict) or not isinstance(payload.get("counts"), dict) or not isinstance(payload.get("scenarios"), dict):
        raise ValueError("Runtime report, counts and scenarios must be objects")
    if not isinstance(payload.get("errors", []), list):
        raise ValueError("Runtime errors must be a list")
    for entry in payload["scenarios"].values():
        if not isinstance(entry, dict):
            raise ValueError("Runtime scenario must be an object")
        findings, runs = entry.get("findings", []), entry.get("runs", {})
        if not isinstance(findings, list) or any(not isinstance(finding, dict) or not isinstance(finding.get("category"), str) for finding in findings):
            raise ValueError("Runtime findings must contain category objects")
        if not isinstance(runs, dict) or any(not isinstance(run, dict) for run in runs.values()):
            raise ValueError("Runtime runs must contain objects")


def rendering_evidence_status(entry):
    fresh = RENDER.evaluate(entry.get("rendering_expectations"), entry.get("runs"))
    if fresh["status"] == "failed" or entry.get("rendering_status") == "failed":
        return "failed"
    if fresh != entry.get("rendering_evidence") or fresh["status"] != entry.get("rendering_status"):
        return "incomplete"
    return fresh["status"]


def runtime_provenance_status(payload):
    scenarios = payload["scenarios"]
    roles = ("checker", "manifest", "rom_zh", "rom_en", "helper_rendering", "helper_reproducibility",
             *("save:" + name for name in scenarios))
    proof = payload.get("reproducibility")
    if REPRO.evidence_status(proof, required_roles=roles) != "passed":
        return "incomplete"
    for name, entry in scenarios.items():
        fixture = entry.get("fixture_integrity")
        if REPRO.evidence_status(fixture, required_roles=("fixture",)) != "passed":
            return "incomplete"
        if any(fixture[phase]["fixture"] != proof[phase]["save:" + name] for phase in ("before", "after")):
            return "incomplete"
        runs = entry.get("runs")
        if not isinstance(runs, dict) or set(runs) != {"zh", "en"}:
            return "incomplete"
        environments = []
        for tag in ("zh", "en"):
            raw = runs[tag].get("raw") if isinstance(runs[tag], dict) else None
            environments.append(raw.get("environment") if isinstance(raw, dict) else None)
        if entry.get("environment_status") != "passed" or REPRO.pair_environment_status(*environments) != "passed":
            return "incomplete"
    return "passed"


def runtime_status(payload):
    validate_runtime_shape(payload)
    counts = payload["counts"]
    scenarios = payload["scenarios"]
    for key in ("selected", "executed", "passed", "failed", "incomplete"):
        if not isinstance(counts[key], int) or isinstance(counts[key], bool) or counts[key] < 0:
            raise ValueError("Runtime counts must be nonnegative integers")
    if any(entry["status"] not in ("passed", "failed", "incomplete") for entry in scenarios.values()):
        raise ValueError("Unknown runtime scenario status")
    if payload["status"] not in ("passed", "failed", "incomplete"):
        raise ValueError("Unknown runtime report status")
    actual = {status: sum(entry["status"] == status for entry in scenarios.values())
              for status in ("passed", "failed", "incomplete")}
    if any(counts[key] != value for key, value in actual.items()):
        raise ValueError("Runtime counts contradict scenario statuses")
    if counts["selected"] <= 0:
        return "failed"
    finding_categories = {finding.get("category") for entry in scenarios.values()
                          for finding in entry.get("findings", [])}
    if counts["failed"] or payload["status"] == "failed" or "english_regression" in finding_categories:
        return "failed"
    rejection_statuses = [runtime_text_rejection_status(entry) for entry in scenarios.values()]
    if "failed" in rejection_statuses:
        return "failed"
    rendering_statuses = [rendering_evidence_status(entry) for entry in scenarios.values()]
    if "failed" in rendering_statuses:
        return "failed"
    if payload.get("errors") and not counts["executed"]:
        return "unavailable"
    child_statuses = [run["status"] for entry in scenarios.values()
                      for run in entry.get("runs", {}).values()]
    if "timeout" in child_statuses:
        return "timeout"
    if "unavailable" in child_statuses:
        return "unavailable"
    complete = (counts["selected"] == counts["executed"] == len(scenarios)
                and counts["passed"] == counts["selected"]
                and not payload.get("errors")
                and all(set(entry.get("runs", {})) == {"zh", "en"} for entry in scenarios.values())
                and all(s == "completed" for s in child_statuses)
                and all(isinstance(run.get("raw"), dict) for entry in scenarios.values()
                        for run in entry.get("runs", {}).values()))
    memory_statuses = [entry.get("memory_status") for entry in scenarios.values()]
    if "failed" in memory_statuses or any(entry.get("text_status") == "failed"
                                         or entry.get("state_status") == "failed"
                                         or entry.get("summary_status") == "failed"
                                         or entry.get("move_status") == "failed"
                                         for entry in scenarios.values()):
        return "failed"
    objective_complete = all(entry.get("memory_status") == "passed"
                             and objective_coverage_complete(entry)
                             for entry in scenarios.values())
    if not objective_complete or "baseline_chinese" in finding_categories:
        return "incomplete"
    if payload["status"] == "passed" and not complete:
        return "failed"
    if runtime_provenance_status(payload) != "passed":
        return "incomplete"
    if any(status not in ("passed", "not_configured") for status in rendering_statuses):
        return "incomplete"
    if any(status != "passed" for status in rejection_statuses):
        return "incomplete"
    if not all(text_evidence_complete(entry) for entry in scenarios.values()):
        return "incomplete"
    state_statuses = [state_evidence_status(entry) for entry in scenarios.values()]
    if any(status not in ("passed", "not_configured") for status in state_statuses):
        return "incomplete"
    if any(summary_evidence_status(entry) not in ("passed", "not_configured") for entry in scenarios.values()):
        return "incomplete"
    if any(move_evidence_status(entry) not in ("passed", "not_configured") for entry in scenarios.values()):
        return "incomplete"
    return "passed" if complete and payload["status"] == "passed" else "incomplete"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checks", nargs="+", choices=CHECKS, default=list(DEFAULT_CHECKS))
    parser.add_argument("--timeout", type=float, default=300, help="Per-check timeout in seconds (default: 300)")
    parser.add_argument("--output", type=Path, help="New report directory under work/build (must not exist)")
    parser.add_argument("--rom", type=Path, help="English ROM for runtime, artifacts, buffers, text_static, and native_loading checks")
    parser.add_argument("--build-report", type=Path, help="Build manifest for the artifacts check")
    parser.add_argument("--runtime-scenarios", "--scenario", default="summary", help="Comma-separated runtime scenarios or all (default: summary)")
    parser.add_argument("--runtime-timeout", type=float, default=120, help="Seconds per emulator child")
    parser.add_argument("--suite-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--suite-result", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.suite_dir:
        if not args.suite_result:
            parser.error("--suite-result is required with --suite-dir")
        return run_suite(args.suite_dir, args.suite_result)
    if "native_loading" in args.checks and not args.rom:
        parser.error("--rom is required for native_loading")
    if not all(0 < value < float("inf") for value in (args.timeout, args.runtime_timeout)):
        parser.error("--timeout must be finite and positive")
    build = (ROOT / "work/build").resolve()
    output = (args.output or build / "quality" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")).resolve()
    if not output.is_relative_to(build) or output == build:
        parser.error("--output must be a new directory inside work/build")
    output.mkdir(parents=True, exist_ok=False)
    records = []
    for name in dict.fromkeys(args.checks):
        payload = output / f"{name}.json"
        if name == "qa":
            command = [sys.executable, str(ROOT / "work/tools/qa.py"), "check",
                       str(ROOT / "work/translate/banks"), "--json", str(payload)]
        elif name == "artifacts":
            command = [sys.executable, str(ROOT / "work/tools/artifact_check.py"),
                       "--output", str(output / "artifact-checks"), "--json", str(payload)]
        elif name == "text_static":
            command = [sys.executable, str(ROOT / "work/tools/static_text_check.py"),
                       "--output", str(output / "static-text"), "--json", str(payload)]
        elif name == "buffers":
            command = [sys.executable, str(ROOT / "work/tools/text_buffer_check.py"),
                       "--workspace", str(ROOT / "work/translate/banks/a027/0218.json"),
                       "--json", str(payload)]
        elif name == "native_loading":
            payload = output / "native-loading" / "report.json"
            command = [sys.executable, str(ROOT / "work/tools/native_load_check.py"),
                       "--rom", str(args.rom.resolve()), "--out", str(payload.parent)]
        elif name == "runtime":
            command = [sys.executable, str(ROOT / "work/tools/memcheck.py"), "run",
                       "--scenario", args.runtime_scenarios, "--timeout", str(args.runtime_timeout),
                       "--out", str(output / "runtime"), "--json", str(payload)]
        else:
            directory = ROOT / "work/tools" / ("docs" if name == "docs" else "")
            command = [sys.executable, str(Path(__file__).resolve()), "--suite-dir", str(directory),
                       "--suite-result", str(payload)]
        if args.rom and name in ("runtime", "artifacts", "buffers", "text_static"):
            command.extend(["--rom", str(args.rom.resolve())])
        if args.build_report and name == "artifacts":
            command.extend(["--build-report", str(args.build_report.resolve())])
        print(f"Running {name}…", flush=True)
        record = run_check(name, command, output, args.timeout, payload)
        records.append(record)
        summary = record.get("summary", {})
        counts = (f"{summary.get('errors', '?')} errors, {summary.get('warnings', '?')} warnings"
                  if name == "qa" else
                  f"{summary.get('selected', '?')} selected, {summary.get('executed', '?')} executed, "
                  f"{summary.get('passed', '?')} passed, {summary.get('failed', '?')} failed, "
                  f"{summary.get('incomplete', '?')} incomplete, {summary.get('findings', '?')} findings; "
                  f"{summary.get('memory_passed', '?')} memory/{summary.get('coverage_passed', '?')} objective/"
                  f"{summary.get('text_passed', '?')} text evidence passed"
                  if name == "runtime" else
                  f"{summary.get('strings', '?')} exported strings; {record.get('reason', 'artifact verified')}"
                  if name == "artifacts" else
                  f"capacity {summary.get('capacity', '?')}, {summary.get('checked_strings', '?')} strings, "
                  f"{summary.get('overflows', '?')} ROM/{summary.get('workspace_overflows', '?')} workspace overflows"
                  if name == "buffers" else
                  "binary grammar, inventories and change boundary checked"
                  if name == "text_static" else
                  f"{summary.get('entries', '?')} native entries; {len(summary.get('semantic_gaps', []))} semantic gaps"
                  if name == "native_loading" else
                  f"{summary.get('tests', '?')} tests, {summary.get('failures', '?')} failures, "
                  f"{summary.get('errors', '?')} errors, {summary.get('skipped', '?')} skipped")
        print(f"{name}: {record['status']} ({record['duration_seconds']}s); {counts}", flush=True)
    status = aggregate_status([record["status"] for record in records])
    passed = status == "passed"
    report = {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
              "python": sys.executable, "python_version": sys.version, "status": status,
              "checks": records}
    write_json(output / "report.json", report)
    print(f"Report: {output / 'report.json'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
