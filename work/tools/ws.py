#!/usr/bin/env python3
"""ws - translation workspace for the 起源心金 (Origin HeartGold v4.0.3) English translation.

Workspace layout: work/translate/banks/<narc>/<NNNN>.json
    {"narc": "a027", "bank": 232, "source": "work/extract/v4/a027/0232.json",
     ["category": "species"],                      # optional QA box category override
     "strings": [{"id": 0, "zh": "...", "en": null | "...",
                  "status": "todo"|"tm"|"draft"|"reviewed",
                  "origin": null|"tm_v3"|"glossary"|"pokeapi-index"|"agent"|"copy"|...,
                  "notes": "" , ["category": ...], ["qa_ignore": ["code", "glossary:术语", ...]]}]}

Commands
    init    [--extract work/extract/v4] [--ws work/translate/banks] [--narc a027 ...]
            create/refresh the workspace from msgtool extracts. Never overwrites an existing en,
            status, origin or notes. If a source zh changed, the entry gets "zh_changed": true.
            Strings with nothing to translate (empty, dashes, pure ASCII) get en = zh, origin "copy".
            Banks in qa_config.json "passthrough_banks" (foreign-language dex data, not published)
            are regenerated entirely as copies. A zh redaction marker (zh_redact.py) that matches
            the source text is kept.
    export  [--ws ...] [--extract ...] [--out work/build] [--status tm,draft,reviewed] [--lenient]
            write msgtool-format bank JSON (work/build/<narc>/NNNN.json + _meta.json) with en
            substituted for zh wherever en is set and its status is selected; zh otherwise.
            Every substituted en is encoded with charmap_en.tsv first; failures abort unless
            --lenient (then that string falls back to zh). Banks listed in qa_config.json
            "compressed_banks" (trainer names, a027/0719) are written {COMPRESSED}, like US, except
            their raw_ids; a name that does not fit the game's fixed buffer counts as unencodable.
    stats   [--ws ...] [--by-bank] [--json]
    import  FILE.jsonl [--force] [--status tm] [--origin tm_v3]
            merge lines {"narc","bank","id","en"[,"zh","status","origin","notes"]}; lines whose
            "zh" differs from the workspace zh are skipped; existing en is kept unless --force.
    set     NARC BANK ID [--en TEXT] [--status S] [--origin O] [--notes N]
    redact  NARC BANK ID [ID ...] [--extract ...]
            replace the zh of these strings (song lyrics) with a redaction marker holding the hash
            of the source text; export/init/QA treat it as the source text (see zh_redact.py).
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
WORK = TOOLS.parent
ROOT = WORK.parent
sys.path.insert(0, str(TOOLS))

import textmetrics as tm  # noqa: E402
import zh_redact  # noqa: E402

DEFAULT_EXTRACT = WORK / "extract" / "v4"
DEFAULT_WS = WORK / "translate" / "banks"
DEFAULT_OUT = WORK / "build"
STATUSES = ("todo", "tm", "draft", "reviewed")

_COPY_OK = re.compile(r"^[\x20-\x7E]*$")


def rel(p: Path) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def needs_translation(zh: str) -> bool:
    """True if the source has anything a translator must touch (CJK, kana, full-width forms)."""
    vis = tm.visible_text(zh)
    return bool(tm.CJK_RE.search(vis) or tm.FULLWIDTH_RE.search(vis))


def passthrough_language(narc: str, bank: int) -> str | None:
    """qa_config.json "passthrough_banks": language of a foreign-language data bank, or None."""
    return tm.load_config().get("passthrough_banks", {}).get("%s/%04d" % (narc, bank))


def initial_entry(sid: int, zh: str, passthrough: str | None = None) -> dict:
    e = {"id": sid, "zh": zh, "en": None, "status": "todo", "origin": None, "notes": ""}
    if not needs_translation(zh):
        vis = tm.visible_text(zh)
        if _COPY_OK.match(vis):
            e["en"] = zh
            e["origin"] = "copy"
            # nothing but punctuation/digits/tags -> final; Latin prose (English leftovers) -> review
            e["status"] = "draft" if re.search(r"[A-Za-z]{2}", vis) else "reviewed"
    if passthrough and e["en"] is None:
        e.update(en=zh, status="draft", origin="copy", notes=f"foreign-language data, kept as is ({passthrough})")
    return e


def iter_extract_banks(extract: Path, narcs=None):
    for nd in sorted(p for p in extract.iterdir() if p.is_dir()):
        if narcs and nd.name not in narcs:
            continue
        for bf in sorted(nd.glob("[0-9]*.json")):
            yield nd.name, bf


def ws_path(ws: Path, narc: str, bank: int) -> Path:
    return ws / narc / f"{bank:04d}.json"


def load_json(p: Path):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def save_json(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(p)


# --------------------------------------------------------------------------------------
# init
# --------------------------------------------------------------------------------------

def init_bank(narc: str, src_file: Path, ws: Path) -> dict:
    src = load_json(src_file)
    counts = Counter()
    if "strings" not in src:
        counts["skipped_raw_bank"] += 1
        return counts
    p = ws_path(ws, narc, src["bank"])
    old = load_json(p) if p.exists() else None
    old_by_id = {e["id"]: e for e in old["strings"]} if old else {}
    out = {"narc": narc, "bank": src["bank"], "source": rel(src_file)}
    lang = passthrough_language(narc, src["bank"])
    if old:
        for k, v in old.items():
            if k not in ("strings", "narc", "bank", "source"):
                out[k] = v
    strings = []
    for s in src["strings"]:
        sid, zh = s["id"], s["text"]
        o = old_by_id.pop(sid, None)
        if o is None:
            strings.append(initial_entry(sid, zh, lang))
            counts["new"] += 1
            continue
        e = dict(o)
        if not zh_redact.matches(e.get("zh"), zh):
            if e.get("en") is not None:
                e["zh_changed"] = True
                e.setdefault("zh_old", e.get("zh"))
                counts["zh_changed"] += 1
            e["zh"] = zh
            if e.get("en") is None:
                e.update({k: v for k, v in initial_entry(sid, zh, lang).items() if k != "id"})
        counts["kept"] += 1
        strings.append(e)
    for sid, o in sorted(old_by_id.items()):   # ids that vanished from the source: keep, flagged
        o = dict(o)
        o["orphan"] = True
        strings.append(o)
        counts["orphan"] += 1
    out["strings"] = strings
    if old != out:
        save_json(p, out)
        counts["files_written"] += 1
    return counts


def cmd_init(a):
    total = Counter()
    for narc, bf in iter_extract_banks(Path(a.extract), a.narc):
        total.update(init_bank(narc, bf, Path(a.ws)))
    print("init:", dict(total))


# --------------------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------------------

def export(ws: Path, extract: Path, out: Path, statuses=("tm", "draft", "reviewed"), lenient=False, narcs=None):
    import msgtool as m
    cm_en = m.Charmap.load([str(tm.CHARMAP_EN)])
    counts = Counter()
    problems = []
    done_narcs = set()
    for narc, bf in iter_extract_banks(extract, narcs):
        src = load_json(bf)
        od = out / narc
        if narc not in done_narcs:
            od.mkdir(parents=True, exist_ok=True)
            meta = extract / narc / "_meta.json"
            if meta.exists():
                shutil.copyfile(meta, od / "_meta.json")
            done_narcs.add(narc)
        if "strings" in src:
            # names the game copies into a fixed buffer: stored {COMPRESSED} like US (qa_config "compressed_banks")
            cspec = tm.compressed_spec(narc, src["bank"])
            wp = ws_path(ws, narc, src["bank"])
            wsb = {e["id"]: e for e in load_json(wp)["strings"]} if wp.exists() else {}
            for s in src["strings"]:
                e = wsb.get(s["id"])
                counts["strings"] += 1
                if not e or e.get("en") is None or e.get("status") not in statuses:
                    counts["zh"] += 1
                    continue
                if not zh_redact.matches(e.get("zh"), s["text"]):
                    problems.append((narc, src["bank"], s["id"], "workspace zh differs from extract; kept zh"))
                    counts["zh"] += 1
                    continue
                en = e["en"]
                try:
                    m.encode_text(en, cm_en)
                    if cspec is not None:
                        en = m.stored_name_text(en, cm_en, compress=s["id"] not in cspec["raw_ids"],
                                                max_units=cspec["max_units"])
                        counts["compressed"] += en.startswith("{COMPRESSED}")
                except ValueError as ex:
                    problems.append((narc, src["bank"], s["id"], f"unencodable: {ex}"))
                    counts["zh"] += 1       # falls back to zh; non-lenient export exits 1 afterwards
                    continue
                s["text"] = en
                counts["en"] += 1
        (od / bf.name).write_text(json.dumps(src, ensure_ascii=False, indent=1), encoding="utf-8")
    return counts, problems


def cmd_export(a):
    statuses = tuple(x.strip() for x in a.status.split(",") if x.strip())
    counts, problems = export(Path(a.ws), Path(a.extract), Path(a.out), statuses, a.lenient, a.narc)
    for p in problems[:50]:
        print("  %s/%04d #%d: %s" % p, file=sys.stderr)
    if len(problems) > 50:
        print(f"  ... {len(problems) - 50} more", file=sys.stderr)
    print("export:", dict(counts), "problems:", len(problems), "->", a.out)
    unenc = [p for p in problems if p[3].startswith("unencodable")]
    if unenc and not a.lenient:
        print(f"{len(unenc)} unencodable strings fell back to zh (use qa.py check to see why)", file=sys.stderr)
        sys.exit(1)


# --------------------------------------------------------------------------------------
# stats
# --------------------------------------------------------------------------------------

def iter_ws_files(ws: Path):
    ws = Path(ws)
    if ws.is_file():
        yield ws
        return
    yield from sorted(ws.rglob("[0-9]*.json"))


def stats(ws: Path, by_bank=False) -> dict:
    res = {"narcs": {}, "total": Counter()}
    banks = []
    for p in iter_ws_files(ws):
        b = load_json(p)
        c = Counter()
        for e in b["strings"]:
            c["strings"] += 1
            c["status:" + e.get("status", "todo")] += 1
            if e.get("origin"):
                c["origin:" + e["origin"]] += 1
            # redacted song lyrics hide their Chinese behind a marker; they still count
            if needs_translation(e["zh"]) or zh_redact.is_marker(e["zh"]):
                c["translatable"] += 1
                if e.get("en") is not None:
                    c["translatable_done"] += 1
            if e.get("zh_changed"):
                c["zh_changed"] += 1
        res["narcs"].setdefault(b["narc"], Counter()).update(c)
        res["total"].update(c)
        if by_bank:
            banks.append({"narc": b["narc"], "bank": b["bank"], **c})
    if by_bank:
        res["banks"] = banks
    return res


def cmd_stats(a):
    r = stats(Path(a.ws), a.by_bank)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return
    t = r["total"]
    def line(name, c):
        tr = c.get("translatable", 0)
        done = c.get("translatable_done", 0)
        st = " ".join(f"{s}={c.get('status:' + s, 0)}" for s in STATUSES)
        return f"{name:14s} strings={c.get('strings', 0):6d} translatable={tr:6d} done={done:6d} ({100.0 * done / max(1, tr):5.1f}%)  {st}"
    for n, c in sorted(r["narcs"].items()):
        print(line(n, c))
    print(line("TOTAL", t))
    origins = {k[7:]: v for k, v in t.items() if k.startswith("origin:")}
    print("origins:", origins)
    if a.by_bank:
        for b in r["banks"]:
            if b.get("translatable_done"):
                print(f"  {b['narc']}/{b['bank']:04d}: {b.get('translatable_done', 0)}/{b.get('translatable', 0)}")


# --------------------------------------------------------------------------------------
# import / set
# --------------------------------------------------------------------------------------

def apply_updates(ws: Path, updates, force=False, default_status="tm", default_origin=None):
    """updates: iterable of dicts {narc, bank, id, en, [zh, status, origin, notes]}."""
    by_file = defaultdict(list)
    for u in updates:
        by_file[(u["narc"], int(u["bank"]))].append(u)
    c = Counter()
    for (narc, bank), us in by_file.items():
        p = ws_path(ws, narc, bank)
        if not p.exists():
            c["missing_bank"] += len(us)
            continue
        b = load_json(p)
        idx = {e["id"]: e for e in b["strings"]}
        changed = False
        for u in us:
            e = idx.get(int(u["id"]))
            if e is None:
                c["missing_id"] += 1
                continue
            if "zh" in u and u["zh"] is not None and not zh_redact.matches(e["zh"], u["zh"]):
                c["zh_mismatch"] += 1
                continue
            if e.get("en") is not None and not force and e.get("origin") != "copy":
                c["kept_existing"] += 1
                continue
            e["en"] = u["en"]
            e["status"] = u.get("status") or default_status
            e["origin"] = u.get("origin") or default_origin
            if u.get("notes"):
                e["notes"] = u["notes"]
            e.pop("zh_changed", None)
            e.pop("zh_old", None)
            changed = True
            c["applied"] += 1
        if changed:
            save_json(p, b)
    return c


def cmd_import(a):
    ups = []
    with open(a.file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                ups.append(json.loads(line))
    print("import:", dict(apply_updates(Path(a.ws), ups, a.force, a.status, a.origin)))


def cmd_set(a):
    p = ws_path(Path(a.ws), a.narc, a.bank)
    b = load_json(p)
    for e in b["strings"]:
        if e["id"] == a.id:
            if a.en is not None:
                e["en"] = a.en.replace("\\n", "\n") if a.literal_newlines else a.en
            if a.status:
                e["status"] = a.status
            if a.origin:
                e["origin"] = a.origin
            if a.notes is not None:
                e["notes"] = a.notes
            save_json(p, b)
            print(json.dumps(e, ensure_ascii=False))
            return
    sys.exit(f"no string {a.id} in {p}")


def redact(ws: Path, extract: Path, narc: str, bank: int, ids) -> int:
    """Replace the zh of `ids` with redaction markers; each must equal the extract text. Returns count."""
    p = ws_path(ws, narc, bank)
    b = load_json(p)
    src = {s["id"]: s.get("text") for s in load_json(Path(extract) / narc / f"{bank:04d}.json")["strings"]}
    by_id = {e["id"]: e for e in b["strings"]}
    n = 0
    for sid in ids:
        e = by_id.get(sid)
        if e is None or sid not in src:
            sys.exit(f"no string {sid} in {p} or its extract")
        if zh_redact.is_marker(e["zh"]):
            continue
        if e["zh"] != src[sid]:
            sys.exit(f"{narc}/{bank:04d} #{sid}: workspace zh differs from the extract; refusing to redact")
        e["zh"] = zh_redact.marker(src[sid])
        n += 1
    if n:
        save_json(p, b)
    return n


def cmd_redact(a):
    n = redact(Path(a.ws), Path(a.extract), a.narc, a.bank, a.ids)
    print(f"redacted {n} strings in {a.narc}/{a.bank:04d}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ws", default=str(DEFAULT_WS))
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init")
    p.add_argument("--extract", default=str(DEFAULT_EXTRACT))
    p.add_argument("--narc", nargs="*")
    p = sub.add_parser("export")
    p.add_argument("--extract", default=str(DEFAULT_EXTRACT))
    p.add_argument("--out", default=str(DEFAULT_OUT))
    p.add_argument("--status", default="tm,draft,reviewed")
    p.add_argument("--lenient", action="store_true")
    p.add_argument("--narc", nargs="*")
    p = sub.add_parser("stats")
    p.add_argument("--by-bank", action="store_true")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("import")
    p.add_argument("file")
    p.add_argument("--force", action="store_true")
    p.add_argument("--status", default="tm")
    p.add_argument("--origin", default=None)
    p = sub.add_parser("set")
    p.add_argument("narc")
    p.add_argument("bank", type=int)
    p.add_argument("id", type=int)
    p.add_argument("--en")
    p.add_argument("--status", choices=STATUSES)
    p.add_argument("--origin")
    p.add_argument("--notes")
    p.add_argument("--literal-newlines", action="store_true", help="turn \\n in --en into real newlines")
    p = sub.add_parser("redact")
    p.add_argument("narc")
    p.add_argument("bank", type=int)
    p.add_argument("ids", type=int, nargs="+")
    p.add_argument("--extract", default=str(DEFAULT_EXTRACT))
    a = ap.parse_args(argv)
    {"init": cmd_init, "export": cmd_export, "stats": cmd_stats, "import": cmd_import, "set": cmd_set,
     "redact": cmd_redact}[a.cmd](a)


if __name__ == "__main__":
    main()
