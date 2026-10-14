#!/usr/bin/env python3
"""release - the release patch with the advanced trainer AI: difficulty's verified candidate, the AI installed and
verified on it, the xdelta against the USA ROM, and a receipt that chains every hash.

    .venv/bin/python work/advanced-ai/builder/release.py --difficulty-receipt RECEIPT --out-dir DIR
        [--difficulty-verification JSON] [--candidate ROM] [--tag TAG] [--base ROM] [--allow-development]

It is the third step of the release chain: the standard build (work/tools/build.py), difficulty in release mode
(work/research/difficulty-armips/build.py, then its verify.py), this script. The AI's three test tiers then run on
the ROM it writes (RELEASING.md, step 3).

1. Difficulty's candidate. RECEIPT is difficulty's receipt.json. The candidate is --candidate, else the first of
   the receipt's output path, candidate.nds beside the receipt and <name>.nds beside <name>.receipt.json whose
   size and sha256 are the receipt's output. --difficulty-verification is the verification.json that difficulty's
   verify.py wrote for that receipt: it must say passed, for the same receipt and candidate.
2. The AI. builder/install.py installs the committed payload and trainer marks into a copy,
   DIR/origin_hg_v4.0.3_en_ai.nds, with its receipt beside it. builder/verify.py then re-reads the written file,
   with the candidate as its input.
3. The patch, made as work/tools/build.py makes it (stage 6, make_patch): xdelta3 -e -9 -S lzma against the USA
   ROM, with build.py's standard file names in the application header. It is re-applied to the USA ROM and must
   give the AI ROM. DIR/Origin_HeartGold_v4.0.3_EN_<tag>.xdelta.
4. DIR/release.json: the standard build, difficulty's receipt, verification and candidate, the AI payload (its
   commit and sha256s), the AI ROM, the USA ROM and the xdelta, each by hash; and the README.txt lines.

A release needs difficulty built in release mode (tool_mode release, every tool on its release pin) and its
verification, xdelta3 at build.py's pin, and payload/, data/ and builder/ as committed. Without them it refuses,
unless --allow-development is given. That output is marked not releasable: release.json says "releasable": false
with the reasons, and the patch is named <...>-development.xdelta.

Always refused (exit 1): a candidate that is not the receipt's output, a verification of another receipt or ROM, a
USA ROM with another SHA-1, a DIR under work/release/ (the AI ROM is never put in a release package), a difficulty
publication that needs recovery, and every refusal of install.py and verify.py. Only those two come after a write: a
previous release.json in DIR is deleted before the install, and the new one is written last, so it exists only for
a complete run.
"""
import argparse
import hashlib
import importlib.util
import json
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_DIR = HERE.parent
REPO = AI_DIR.parents[1]
TOOLS = REPO / "work" / "tools"
RELEASES = REPO / "work" / "release"
sys.path.insert(0, str(HERE))
import install  # noqa: E402
import verify  # noqa: E402
from install import Refused, require, sha256  # noqa: E402


def load_tools_build():
    """work/tools/build.py under its own name: builder/ has a build.py too. Its imports need work/tools on the path
    only while it loads."""
    saved = list(sys.path)
    try:
        sys.path.insert(0, str(TOOLS))
        spec = importlib.util.spec_from_file_location("tools_build", TOOLS / "build.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules["tools_build"] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = saved


tb = load_tools_build()

AI_ROM = "origin_hg_v4.0.3_en_ai.nds"
RECEIPT = "release.json"
COMMITTED = ("work/advanced-ai/payload", "work/advanced-ai/data", "work/advanced-ai/builder")
PUBLICATION_JOURNAL = ".publication.json"       # difficulty's publication.py: present while a pair needs recovery


def patch_name(tag, releasable):
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", tag), f"--tag {tag!r}: letters, digits, '.', '_', '-'")
    return f"Origin_HeartGold_v4.0.3_EN_{tag}{'' if releasable else '-development'}.xdelta"


def git_state():
    """HEAD, the last commit that changed payload/, and the paths under payload/, data/ and builder/ that differ from
    HEAD (None without git)."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()
    try:
        return {"head": git("rev-parse", "HEAD"),
                "payload_commit": git("log", "-1", "--format=%H", "--", COMMITTED[0]),
                "changed": git("status", "--porcelain", "--untracked-files=all", "--", *COMMITTED).splitlines()}
    except (OSError, subprocess.CalledProcessError):
        return None


def xdelta3_state():
    try:
        return tb.check_xdelta3()
    except tb.ToolchainError as e:
        raise Refused(str(e)) from None


def find_candidate(receipt_path, output, given=None):
    """The file that is the receipt's output (size and sha256): --candidate, else where the receipt says, else
    beside the receipt."""
    tried = [Path(given)] if given else [
        Path(output["path"]), receipt_path.with_name("candidate.nds"),
        receipt_path.with_name(receipt_path.name.removesuffix(".receipt.json") + ".nds")]
    for path in dict.fromkeys(tried):
        if path.is_file() and path.stat().st_size == output["bytes"]:
            data = path.read_bytes()
            if sha256(data) == output["sha256"]:
                return path, data
    raise Refused(f"no file is difficulty's candidate (sha256 {output['sha256']}, {output['bytes']} bytes): "
                  + ", ".join(str(p) for p in dict.fromkeys(tried)))


def read_difficulty(receipt_path, verification_path, candidate):
    raw = receipt_path.read_bytes()
    r = json.loads(raw)
    require(isinstance(r.get("output"), dict) and {"path", "bytes", "sha256"} <= set(r["output"])
            and isinstance(r.get("input"), dict), f"{receipt_path} is not a difficulty receipt (no input and output)")
    require(not (receipt_path.parent / PUBLICATION_JOURNAL).exists(),
            f"difficulty's publication in {receipt_path.parent} needs recovery ({PUBLICATION_JOURNAL}): rerun its build")
    path, data = find_candidate(receipt_path, r["output"], candidate)
    out = {"receipt": {"path": str(receipt_path), "sha256": sha256(raw)},
           "tool_mode": r.get("tool_mode", "release"), "status": r.get("status"),
           "tools_off_release_pin": sorted(name for name, t in r.get("tools", {}).items()
                                           if isinstance(t, dict) and t.get("matches_release_pin") is False),
           "native_gameplay_acceptance": r.get("native_gameplay_acceptance"),
           "candidate": install.identity(data, path), "verification": None}
    if verification_path:
        vraw = verification_path.read_bytes()
        v = json.loads(vraw)
        require(str(v.get("status", "")).split("; ")[-1] == "passed",
                f"{verification_path}: difficulty's verification did not pass ({v.get('status')!r})")
        require(v.get("receipt", {}).get("sha256") == out["receipt"]["sha256"],
                f"{verification_path} verifies another receipt")
        require(v.get("output", {}).get("sha256") == out["candidate"]["sha256"],
                f"{verification_path} verifies another ROM")
        out["verification"] = {"path": str(verification_path), "sha256": sha256(vraw),
                               "status": v["status"], "tool_mode": v.get("tool_mode", "release")}
    return r, out, path, data


def blockers(difficulty, xdelta, git):
    """Why this would not be a release (empty: it is one)."""
    out = []
    if difficulty["tool_mode"] != "release":
        out.append(f"difficulty was built in {difficulty['tool_mode']} mode")
    if difficulty["tools_off_release_pin"]:
        out.append("difficulty's tools off their release pins: " + ", ".join(difficulty["tools_off_release_pin"]))
    v = difficulty["verification"]
    if v is None:
        out.append("no --difficulty-verification (the verification.json of difficulty's verify.py)")
    elif v["tool_mode"] != "release":
        out.append(f"difficulty's verification ran in {v['tool_mode']} mode")
    if not xdelta[1]:
        out.append(f"xdelta3 {xdelta[0]} is not build.py's pin {tb.XDELTA3_VERSION}")
    if git is None:
        out.append("no git: the payload's commit is unknown")
    elif git["changed"]:
        out.append("payload/, data/ or builder/ differ from HEAD: " + "; ".join(git["changed"]))
    return out


def release(difficulty_receipt, out_dir, *, difficulty_verification=None, candidate=None, tag="wip",
            base=tb.ROM_US, allow_development=False, payload_dir=install.DEF_PAYLOAD, marks_path=install.DEF_MARKS,
            pins=None, base_sha1=tb.US_SHA1, xdelta=xdelta3_state, git=git_state):
    """Make the AI ROM, the xdelta and release.json in out_dir; returns release.json's data. Its own checks raise
    Refused before anything is written; install.py's and verify.py's come after an earlier release.json is deleted."""
    receipt_path = Path(difficulty_receipt).resolve()
    out_dir = Path(out_dir).resolve()
    base = Path(base).resolve()
    pins = pins or install.Pins()
    require(not out_dir.is_relative_to(RELEASES.resolve()),
            f"--out-dir {out_dir} is under work/release/: the AI ROM is never put in a release package")
    r, difficulty, cand_path, cand = read_difficulty(
        receipt_path, Path(difficulty_verification).resolve() if difficulty_verification else None, candidate)
    xd, gs = xdelta(), git()
    reasons = blockers(difficulty, xd, gs)
    require(allow_development or not reasons,
            "not a release: " + "; ".join(reasons) + ". --allow-development builds it, marked not releasable")
    releasable = not allow_development
    name = patch_name(tag, releasable)
    base_data = base.read_bytes()
    require(hashlib.sha1(base_data).hexdigest() == base_sha1,
            f"--base {base} is not Pokémon HeartGold (USA) (SHA-1 {base_sha1})")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / RECEIPT).unlink(missing_ok=True)
    ai_rom, patch = out_dir / AI_ROM, out_dir / name
    inst = install.install(cand_path, ai_rom, payload_dir, marks_path, pins, difficulty_receipt=receipt_path)
    data = ai_rom.read_bytes()
    require(sha256(data) == inst["output"]["sha256"], "the AI ROM on disk is not the one install.py wrote")
    report = verify.verify(data, payload_dir, marks_path, input_data=cand, overlay11_sha256=pins.overlay11_sha256)
    require(report["ok"], "verify.py rejects the AI ROM: " + "; ".join(report["errors"]))

    patch.unlink(missing_ok=True)
    tb.make_patch(base, ai_rom, patch, out_dir)
    with tempfile.TemporaryDirectory(dir=out_dir, prefix="reapply-") as td:
        back = Path(td) / "reapplied.nds"
        subprocess.run(["xdelta3", "-d", "-s", str(base), str(patch), str(back)], check=True)
        require(back.read_bytes() == data, "the xdelta applied to the USA ROM does not give the AI ROM")
    patch_data = patch.read_bytes()
    ai = install.identity(data, ai_rom)
    xdelta_id = install.identity(patch_data, patch)

    receipt = {
        "format": 1,
        "tool": "work/advanced-ai/builder/release.py",
        "releasable": releasable,
        "not_releasable_because": [] if releasable else reasons or ["--allow-development"],
        "tag": tag,
        "standard_build": r["input"],
        "difficulty": difficulty,
        "advanced_ai": {
            "git": gs,
            "payload": {"payload.json": inst["payload"]["payload.json"], "files": inst["payload"]["files"]},
            "marks_sha256": inst["marks"]["sha256"],
            "install_receipt": {"path": str(ai_rom) + ".receipt.json",
                                "sha256": sha256(Path(str(ai_rom) + ".receipt.json").read_bytes())},
            "verify": {"ok": report["ok"], "checked": report["checked"], "input_sha256": sha256(cand)},
        },
        "ai_rom": ai,
        "base": install.identity(base_data, base),
        "xdelta": xdelta_id | {"command": "xdelta3 -e -9 -S lzma", "xdelta3": xd[0], "xdelta3_pinned": xd[1],
                               "application_header": {"source": tb.PATCH_SOURCE_NAME, "target": tb.PATCH_TARGET_NAME},
                               "reapplied_to_ai_rom": True},
        "toolchain": {"python": platform.python_version()},
        "readme_lines": [f"Patch:    {name}", f"  SHA-1   {xdelta_id['sha1']}", f"Result ROM SHA-1: {ai['sha1']}"],
    }
    install.atomic_write(out_dir / RECEIPT, (json.dumps(receipt, indent=1, ensure_ascii=False) + "\n").encode())
    return receipt


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--difficulty-receipt", required=True, type=Path, help="difficulty's receipt.json")
    ap.add_argument("--difficulty-verification", type=Path,
                    help="the verification.json of difficulty's verify.py for that receipt (required for a release)")
    ap.add_argument("--candidate", type=Path, help="difficulty's candidate ROM (default: found from the receipt)")
    ap.add_argument("--out-dir", required=True, type=Path, help="where the AI ROM, the xdelta and release.json go "
                    "(not under work/release/)")
    ap.add_argument("--tag", default="wip", help="the release tag in the xdelta's name, e.g. v1.0.0-rc9 (default wip)")
    ap.add_argument("--base", type=Path, default=tb.ROM_US, help=f"the USA ROM (default {tb.ROM_US})")
    ap.add_argument("--allow-development", action="store_true",
                    help="build from a development difficulty, an unpinned xdelta3 or an uncommitted payload; the "
                         "output is marked not releasable")
    a = ap.parse_args(argv)
    try:
        r = release(a.difficulty_receipt, a.out_dir, difficulty_verification=a.difficulty_verification,
                    candidate=a.candidate, tag=a.tag, base=a.base, allow_development=a.allow_development)
    except Refused as e:
        print(f"release.py: refused: {e}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f"release.py: {e}", file=sys.stderr)
        return 1
    rom = r["ai_rom"]["path"]
    if not r["releasable"]:
        print("NOT RELEASABLE: " + "; ".join(r["not_releasable_because"]))
    print(f"AI ROM  {rom} (sha1 {r['ai_rom']['sha1']})")
    print(f"xdelta  {r['xdelta']['path']} (sha1 {r['xdelta']['sha1']}); re-applied to the USA ROM: the AI ROM")
    print(f"receipt {Path(r['xdelta']['path']).with_name(RECEIPT)}")
    print("README.txt:\n  " + "\n  ".join(r["readme_lines"]))
    print("Next, the AI's three tiers on the AI ROM (RELEASING.md, step 3):\n"
          f'  ROM="{rom}"\n  P=work/advanced-ai/payload/payload.json\n'
          '  .venv/bin/python work/tools/check.py --full --strict-release --ai-rom "$ROM"\n'
          '  .venv/bin/python work/advanced-ai/testbench/run.py quick --rom "$ROM" --payload $P --workers 3 '
          f'--options-receipt "{r["difficulty"]["receipt"]["path"]}"\n'
          '  .venv/bin/python work/advanced-ai/testbench/run.py deep --rom "$ROM" --payload $P --workers 3')
    return 0


if __name__ == "__main__":
    sys.exit(main())
