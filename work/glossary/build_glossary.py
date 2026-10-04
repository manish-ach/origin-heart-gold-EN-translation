#!/usr/bin/env python3
"""Build the zh-Hans -> English terminology glossary for Pokémon Origin HeartGold (起源心金) v4.0.3.

Usage:  python3 work/glossary/build_glossary.py [--download]

Reads the author's spreadsheets in the project root (read-only), the PokéAPI CSVs in
work/glossary/src/ (fetched with --download or when missing), and the curated overrides in
work/glossary/manual_overrides.py. Writes species/moves/abilities/items/types/natures/
locations/general.json, unmatched.md and the stats block of README.md into work/glossary/.

Matching order per term (first hit wins):
  1. manual      - curated table in manual_overrides.py (old 汉化 names, abbreviations, custom hack terms)
  2. pokeapi-zh-Hans - exact match on official Simplified Chinese name (language id 12)
  3. pokeapi-zh-Hant - exact match on the Traditional name (language id 4), after converting it to
                       Simplified with a char map learned from aligned zh-Hant/zh-Hans name pairs
  4. fuzzy       - rule-based normalisation (TM/HM numbers, full-width digits, form suffixes) or
                   difflib similarity against official names (medium/low confidence)
"""
import csv
import difflib
import json
import os
import re
import sys
import urllib.request
from collections import OrderedDict, defaultdict

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
SRC = os.path.join(HERE, "src")
sys.path.insert(0, HERE)
import manual_overrides as MO  # noqa: E402

PKAPI = "https://raw.githubusercontent.com/PokeAPI/pokeapi/master/data/v2/csv/"
CSVS = ["pokemon_species_names", "move_names", "ability_names", "item_names", "type_names",
        "nature_names", "location_names", "region_names", "pokemon_form_names", "items",
        "pokemon_species", "moves", "abilities", "locations", "languages", "stat_names", "item_game_indices"]
EN, HANS, HANT = "9", "12", "4"

F_SPECIES = os.path.join(ROOT, "Pokémon Origin HeartGold v4.0.3 Cn List of Pokemons.xlsx")
F_ITEMS = os.path.join(ROOT, "Pokémon Origin HeartGold v4.0.3 Cn Items.xlsx")
F_ENC = os.path.join(ROOT, "Pokémon Origin HeartGold v4.0.3 Cn Encounters.xlsx")
F_V3 = os.path.join(ROOT, "Pokémon Origin HeartGold v3 Cn Documents.xls")

# DS text limits used for the length audit (characters)
LIMITS = {"species": 10, "moves": 12, "abilities": 12, "items": 12}


# --------------------------------------------------------------------------- sources
def download(force=False):
    os.makedirs(SRC, exist_ok=True)
    for name in CSVS:
        p = os.path.join(SRC, name + ".csv")
        if force or not os.path.exists(p):
            print("fetch", name)
            urllib.request.urlretrieve(PKAPI + name + ".csv", p)


def read_csv(name):
    with open(os.path.join(SRC, name + ".csv"), encoding="utf-8") as f:
        return list(csv.DictReader(f))


def names_table(csvname, idcol, namecol="name"):
    """-> (en_by_id, hans->id, hant->id)"""
    en, hans, hant = {}, {}, {}
    for r in read_csv(csvname):
        i, lang, n = int(r[idcol]), r["local_language_id"], (r[namecol] or "").strip()
        if not n:
            continue
        if lang == EN:
            en[i] = n
        elif lang == HANS:
            hans.setdefault(n, i)
        elif lang == HANT:
            hant.setdefault(n, i)
    return en, hans, hant


# --------------------------------------------------------------------------- script conversion
FW = str.maketrans("０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ　：（）",
                   "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz :()")


def norm(s):
    s = str(s).translate(FW).strip()
    s = s.replace("•", "·").replace("・", "·")
    return s


def learn_t2s():
    """Learn a Traditional->Simplified character map from aligned official name pairs."""
    votes = defaultdict(lambda: defaultdict(int))
    for csvname, idcol in [("pokemon_species_names", "pokemon_species_id"), ("move_names", "move_id"),
                           ("ability_names", "ability_id"), ("item_names", "item_id"),
                           ("location_names", "location_id")]:
        by = defaultdict(dict)
        for r in read_csv(csvname):
            if r["local_language_id"] in (HANS, HANT):
                by[r[idcol]][r["local_language_id"]] = r["name"]
        for d in by.values():
            a, b = d.get(HANT, ""), d.get(HANS, "")
            if a and b and len(a) == len(b):
                for x, y in zip(a, b):
                    votes[x][y] += 1
    return {t: max(v.items(), key=lambda kv: kv[1])[0] for t, v in votes.items()}


# --------------------------------------------------------------------------- extraction
def xlsx_rows(path, sheet):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    return [tuple(r) for r in wb[sheet].iter_rows(values_only=True)]


def xls_rows(path, sheet):
    import xlrd
    wb = xlrd.open_workbook(path)
    s = wb.sheet_by_name(sheet)
    return [tuple(s.row_values(i)) for i in range(s.nrows)]


ID_PREFIX = re.compile(r"^\s*\d+_\d+\s*[:：]\s*")
FORM_SUFFIX = re.compile(r"[（(]([^）)]*)[）)]\s*$")


def strip_id(s):
    return ID_PREFIX.sub("", str(s)).strip()


def cell(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


class Terms:
    """Ordered set of terms with provenance and (optional) official index from the sheet."""

    def __init__(self):
        self.d = OrderedDict()
        self.idx = {}

    def add(self, term, where, idx=None):
        term = cell(term)
        if not term or term in ("None", "？？？", "???", "无", "-", "—", "------", "空"):
            return
        self.d.setdefault(term, set()).add(where)
        if idx is not None:
            self.idx.setdefault(term, set()).add(idx)

    def __iter__(self):
        return iter(self.d)

    def __len__(self):
        return len(self.d)


def split_list(s):
    out = []
    for x in re.split(r"[、，,；;/／\n]", cell(s)):
        x = re.sub(r"^[^：:]*[：:]", "", x.strip()).strip()  # "大量出现：超音蝠" -> "超音蝠"
        if x:
            out.append(x)
    return out


def extract():
    T = {k: Terms() for k in ["species", "moves", "abilities", "items", "types", "locations"]}
    forms = Terms()  # species strings carrying a form annotation, e.g. 蛇纹熊（形态1）

    def add_species(raw, where, idx=None):
        raw = cell(raw)
        if not raw:
            return
        m = FORM_SUFFIX.search(raw)
        if m:
            forms.add(raw, where)
            raw = raw[:m.start()].strip()
        T["species"].add(raw, where, idx)

    def num(v, hi):
        try:
            v = int(float(v))
        except (TypeError, ValueError):
            return None
        return v if 1 <= v <= hi else None

    def sheet_idx(a):
        m = re.match(r"^\s*\d+_(\d+)", cell(a))
        return int(m.group(1)) if m else None

    # ---- v4 species sheet (col A = national dex number for #1-493)
    rows = xlsx_rows(F_SPECIES, "4.0精灵数据")
    for r in rows[1:]:
        add_species(r[1], "v4 精灵数据", num(r[0], 493))
        for c in r[2:5]:
            T["abilities"].add(c, "v4 精灵数据")
        for c in r[5:7]:
            T["types"].add(c, "v4 精灵数据")
    # ---- v4 move changes / new TMs
    for r in xlsx_rows(F_SPECIES, "4.0招式变动")[1:]:
        T["moves"].add(r[1], "v4 招式变动", num(r[0], 919))
        T["types"].add(r[2], "v4 招式变动")
    for r in xlsx_rows(F_SPECIES, "4.0新增技能机")[1:]:
        T["moves"].add(r[2], "v4 新增技能机", num(r[0], 919))
        T["types"].add(r[3], "v4 新增技能机")
        loc = cell(r[10])
        if loc:
            T["locations"].add(re.sub(r"(商店|百货)$", "", loc), "v4 新增技能机 位置")
    for r in xlsx_rows(F_SPECIES, "4.0特性")[1:]:
        T["abilities"].add(r[0], "v4 特性")
    rr = xlsx_rows(F_SPECIES, "特性适用范围")
    for c in rr[0][1:]:
        T["abilities"].add(c, "v4 特性适用范围")
    for r in rr[1:]:
        for c in r[1:]:
            T["moves"].add(c, "v4 特性适用范围")
    # ---- v4 items (+ move tutor list appended at the bottom of the sheet)
    for r in xlsx_rows(F_ITEMS, "3.2道具")[1:]:
        a = cell(r[0])
        if not a:
            continue
        if ID_PREFIX.match(a):
            T["items"].add(strip_id(a), "v4 道具", ("gen4", sheet_idx(a)))
        elif re.search(r"\d{3}$", a) or a in ("收音机卡",):
            T["items"].add(re.sub(r"^原", "", re.sub(r"\d+$", "", a)), "v4 道具 (notes)")
        else:
            T["moves"].add(a, "v4 道具 (move tutor list)")
    # ---- encounters
    for r in xlsx_rows(F_ENC, "地图概览")[2:]:
        T["locations"].add(norm_loc(r[0]), "v4 遭遇 地图概览")
        for c in r[1:11]:
            for s in split_list(c):
                add_species(s, "v4 遭遇 地图概览")
    for r in xlsx_rows(F_ENC, "遭遇索引")[2:]:
        for part in split_maps(r[0]):
            T["locations"].add(part, "v4 遭遇索引")
        for s in split_list(r[3]):
            add_species(s, "v4 遭遇索引")
    for r in xlsx_rows(F_ENC, "遭遇明细")[2:]:
        for part in split_maps(r[0]):
            T["locations"].add(part, "v4 遭遇明细")
        add_species(r[4], "v4 遭遇明细")
    # ---- v3 documents
    for r in xls_rows(F_V3, "新种族值")[1:]:
        add_species(r[1], "v3 新种族值", num(r[0], 493))
        for c in r[2:4]:
            T["abilities"].add(c, "v3 新种族值")
        for c in r[4:6]:
            T["types"].add(c, "v3 新种族值")
    for r in xls_rows(F_V3, "道具")[1:]:
        if ID_PREFIX.match(cell(r[0])):
            T["items"].add(strip_id(r[0]), "v3 道具", ("gen4", sheet_idx(r[0])))
    for r in xls_rows(F_V3, "技能")[1:]:
        T["moves"].add(strip_id(r[0]), "v3 技能", num(sheet_idx(r[0]), 467))
        T["types"].add(r[1], "v3 技能")
    for r in xls_rows(F_V3, "特性")[1:]:
        T["abilities"].add(strip_id(r[0]), "v3 特性", num(sheet_idx(r[0]), 123))
    for r in xls_rows(F_V3, "精灵分布笔记")[1:]:
        add_species(r[1], "v3 精灵分布笔记", num(r[0], 493))
    for r in xls_rows(F_V3, "联动公园设置")[1:]:
        add_species(r[3], "v3 联动公园设置", num(r[2], 493))
        for c in r[4:6]:
            T["types"].add(c, "v3 联动公园设置")
    return T, forms


def strip_map_id(s):
    return re.sub(r"^\s*\d+\s*[:：]\s*", "", cell(s))


def split_maps(s):
    return [norm_loc(strip_map_id(x)) for x in cell(s).split("、") if x.strip()]


def norm_loc(s):
    return norm(cell(s))


# --------------------------------------------------------------------------- matching
RENAME = re.compile(r"^(.*?)[（(](?:已|预计)?(?:改名|改为|为)(.+?)[）)]$")


class Matcher:
    """Resolves one category. `idx` maps term -> set of official ids suggested by the sheet's own
    numbering (national dex / Gen 4 move, ability and item indices)."""

    def __init__(self, en, hans, hant, t2s, manual, idx=None, idmap=None, word_ids=False, check=None):
        self.en, self.hans, self.manual = en, hans, manual
        self.word_ids, self.check = word_ids, check
        self.hans_by_id = {}
        for n, i in hans.items():
            self.hans_by_id.setdefault(i, n)
        self.hant_s = {}
        for n, i in hant.items():
            self.hant_s.setdefault(n, i)
            self.hant_s.setdefault("".join(t2s.get(c, c) for c in n), i)
        self.en_rev = {}
        for i, n in sorted(en.items()):
            self.en_rev.setdefault(n.lower(), i)
        self.idx, self.idmap = idx or {}, idmap or (lambda x: x)
        self.pool = list(hans.items())

    def name(self, i):
        return self.en.get(i)

    def from_manual(self, v):
        if isinstance(v, str):
            v = (v,)
        en = v[0]
        conf = v[1] if len(v) > 1 else "high"
        note = v[2] if len(v) > 2 else None
        i = None
        if en and en.startswith("="):  # reference to an official zh-Hans name
            i = self.hans.get(en[1:])
            en = self.name(i)
        elif en:
            i = self.en_rev.get(en.lower())
            if i is None and self.word_ids:  # species forms: "Heat Rotom" -> Rotom's id
                for w in re.sub(r"[()]", " ", en).split():
                    if w.lower() in self.en_rev:
                        i = self.en_rev[w.lower()]
                        break
        r = {"en": en, "id": i, "source": "manual", "confidence": conf}
        if note:
            r["note"] = note
        return r

    def match(self, term, rules=None, _depth=0):
        t = norm(term)
        for k in (term, t):
            if k in self.manual:
                return self.from_manual(self.manual[k])
        for cand in (term, t):
            if cand in self.hans:
                i = self.hans[cand]
                return {"en": self.name(i), "id": i, "source": "pokeapi-zh-Hans", "confidence": "high"}
        for cand in (term, t):
            if cand in self.hant_s:
                i = self.hant_s[cand]
                return {"en": self.name(i), "id": i, "source": "pokeapi-zh-Hant", "confidence": "high"}
        mm = RENAME.match(t)
        if mm and _depth == 0:  # "暗黑球（改名黑暗球）": the hack renamed/repurposed this slot -> use the new name
            r = self.match(mm.group(2).strip(), rules, 1)
            if r and r.get("en"):
                r = dict(r)
                r["note"] = ("renamed in hack: %s -> %s. " % (mm.group(1), mm.group(2)) + r.get("note", "")).strip()
                return r
        if rules:
            r = rules(t, self)
            if r:
                return r
        if _depth == 0:
            ids = {self.idmap(x) for x in self.idx.get(term, ())} - {None}
            if len(ids) == 1:
                i = ids.pop()
                off = self.hans_by_id.get(i, "")
                sim = difflib.SequenceMatcher(None, t, off).ratio()
                if self.name(i):
                    # The sheets' own numbering (national dex / Gen 4 internal move, ability, item index) is
                    # authoritative for slots the hack kept; repurposed slots are caught by `check` or overridden
                    # in manual_overrides.py. All index hits were reviewed by hand.
                    conf, note = "high", "sheet index -> official #%d (official zh-Hans %s; name sim %.2f)" % (i, off, sim)
                    problem = self.check(term, i) if self.check else None
                    if problem:
                        conf, note = "medium", note + "; " + problem
                    return {"en": self.name(i), "id": i, "source": "fuzzy", "confidence": conf, "note": note}
        # difflib against official zh-Hans names
        best, score = None, 0.0
        for n, i in self.pool:
            if abs(len(n) - len(t)) > 1:
                continue
            s = difflib.SequenceMatcher(None, t, n).ratio()
            if s > score:
                best, score = (n, i), s
        if best and score >= 0.66 and len(t) >= 3:
            conf = "medium" if score >= 0.8 else "low"
            return {"en": self.name(best[1]), "id": best[1], "source": "fuzzy", "confidence": conf,
                    "note": "difflib %.2f vs official %s" % (score, best[0])}
        return None


def tm_rules(t, m):
    mm = re.match(r"^(技能机|招式学习器|学习器|TM)\s*(\d+)$", t)
    if mm:
        return {"en": "TM%02d" % int(mm.group(2)), "id": m.hans.get("招式学习器%02d" % int(mm.group(2))),
                "source": "fuzzy", "confidence": "high", "note": "TM number rule"}
    mm = re.match(r"^(秘传机|秘传学习器|HM)\s*(\d+)$", t)
    if mm:
        return {"en": "HM%02d" % int(mm.group(2)), "id": m.hans.get("秘传学习器%02d" % int(mm.group(2))),
                "source": "fuzzy", "confidence": "high", "note": "HM number rule"}
    return None


LOC_IDS = {}


def loc_rules(t, m):
    mm = re.match(r"^(\d+)号(道路|路|水路)$", t)
    if mm:
        n = int(mm.group(1))
        region = "kanto" if n <= 28 else "johto"
        return {"en": "Route %d" % n, "id": LOC_IDS.get("%s-route-%d" % (region, n)), "source": "fuzzy",
                "confidence": "high", "note": "route number rule (%s)" % region.title()}
    return None


# --------------------------------------------------------------------------- main
def main():
    if "--download" in sys.argv or not os.path.exists(os.path.join(SRC, "move_names.csv")):
        download("--download" in sys.argv)
    t2s = learn_t2s()
    T, forms = extract()

    tables = {
        "species": names_table("pokemon_species_names", "pokemon_species_id"),
        "moves": names_table("move_names", "move_id"),
        "abilities": names_table("ability_names", "ability_id"),
        "items": names_table("item_names", "item_id"),
        "types": names_table("type_names", "type_id"),
        "natures": names_table("nature_names", "nature_id"),
        "locations": names_table("location_names", "location_id"),
    }
    # regions share the location namespace (id=null, English from region_names)
    ren, rhans, rhant = names_table("region_names", "region_id")
    manual = {k: getattr(MO, k.upper(), {}) for k in tables}
    for n, i in rhans.items():
        manual["locations"].setdefault(n, ren[i])
    gen4 = {}
    for r in read_csv("item_game_indices"):
        if r["generation_id"] == "4":
            gen4.setdefault(int(r["game_index"]), int(r["item_id"]))
    idmaps = {"items": lambda x: gen4.get(x[1]) if isinstance(x, tuple) else x}
    for r in read_csv("locations"):
        LOC_IDS[r["identifier"]] = int(r["id"])
    checks = {"moves": move_type_check(T, tables["types"])}

    rules = {"items": tm_rules, "locations": loc_rules}
    out, unmatched, stats = {}, {}, {}
    for cat, (en, hans, hant) in tables.items():
        m = Matcher(en, hans, hant, t2s, manual[cat], T[cat].idx if cat in T else None, idmaps.get(cat),
                    word_ids=(cat == "species"), check=checks.get(cat))
        terms = list(T[cat]) if cat in T else list(hans.keys())
        if cat == "natures":
            terms = sorted(hans, key=lambda n: hans[n])
        if cat == "locations":  # also carry every curated Johto/Kanto name + regions, even if unseen in sheets
            terms = terms + [n for n in manual[cat] if n not in terms]
        if cat == "types":  # always carry the full official type list
            terms = terms + [n for n in sorted(hans, key=lambda n: hans[n]) if hans[n] < 10000 and n not in terms]
        res, un = OrderedDict(), []
        for term in terms:
            r = m.match(term, rules.get(cat))
            if r is None or r.get("en") is None:
                un.append(term)
                res[term] = {"en": None, "id": None, "source": "manual", "confidence": "low"}
                continue
            if r["confidence"] != "high":
                un.append(term)
            res[term] = r
        out[cat], unmatched[cat] = res, un

    # species forms: add annotated variants (e.g. 蛇纹熊（形态1）) to species.json
    for f in forms:
        base = FORM_SUFFIX.sub("", f).strip()
        b = out["species"].get(base)
        if b and b["en"]:
            label = FORM_SUFFIX.search(f).group(1).translate(FW).strip()
            fn = MO.FORM_NAMES.get(f)
            if fn:
                fn = (fn,) if isinstance(fn, str) else fn
                out["species"][f] = dict(b, en=fn[0], confidence=fn[1] if len(fn) > 1 else "high",
                                         note=fn[2] if len(fn) > 2 else "regional form (encounter sheet 形态1)")
                continue
            lab = MO.FORM_LABELS.get(label) or MO.FORM_LABELS.get(re.sub(r"^\d+", "", label))
            out["species"][f] = dict(b, en="%s (%s)" % (b["en"], lab or label), confidence="high" if lab else "low",
                                     note="form annotation from encounter sheet")

    for f in forms:
        r = out["species"].get(f)
        if r and r["confidence"] != "high" and f not in unmatched["species"]:
            unmatched["species"].append(f)
    for cat, res in out.items():
        stats[cat] = {
            "terms": len(res),
            "by_source": dict(sorted(count(r["source"] for r in res.values()).items())),
            "high": sum(1 for r in res.values() if r["confidence"] == "high" and r["en"]),
            "unresolved": sum(1 for r in res.values() if not r["en"]),
        }
    for cat, res in out.items():
        with open(os.path.join(HERE, cat + ".json"), "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
    with open(os.path.join(HERE, "general.json"), "w", encoding="utf-8") as f:
        json.dump(OrderedDict((k, {"en": v[0], "note": v[1]} if isinstance(v, tuple) else {"en": v})
                              for k, v in MO.GENERAL.items()), f, ensure_ascii=False, indent=1)

    write_unmatched(out, unmatched, T)
    long_names = length_audit(out)
    write_readme(stats, long_names)
    for cat, s in stats.items():
        print("%-10s %4d terms  high=%4d  unresolved=%3d  %s" % (cat, s["terms"], s["high"], s["unresolved"], s["by_source"]))


def move_type_check(T, types_table):
    """Flag index matches whose sheet type differs from the official type (slot repurposed by the hack)."""
    import xlrd  # noqa
    en_t, hans_t, _ = types_table
    abbrev = {k: v[0] if isinstance(v, tuple) else v for k, v in MO.TYPES.items()}
    sheet_type = {}
    for r in xls_rows(F_V3, "技能")[1:]:
        sheet_type[strip_id(r[0])] = cell(r[1])
    official = {int(r["id"]): int(r["type_id"]) for r in read_csv("moves")}

    def check(term, i):
        st = sheet_type.get(term)
        if not st or i not in official:
            return None
        st_en = en_t.get(hans_t.get(st)) or abbrev.get(st)
        if st_en and st_en != en_t.get(official[i]):
            return "sheet type %s != official %s (possible repurposed slot / Fairy retype)" % (st_en, en_t.get(official[i]))
        return None
    return check


def count(it):
    d = defaultdict(int)
    for x in it:
        d[x] += 1
    return d


def write_unmatched(out, unmatched, T):
    L = ["# Unmatched / low-confidence glossary terms", "",
         "Generated by `build_glossary.py`. Every term below is either not an official PokéAPI name "
         "(custom hack content, old fan-translation wording, abbreviations) or was matched with medium/low "
         "confidence. Resolved guesses live in `manual_overrides.py`; edit there and re-run the script.", ""]
    for cat, terms in unmatched.items():
        if not terms:
            continue
        L += ["## %s (%d)" % (cat, len(terms)), "", "| 中文 | best guess | conf | source | reasoning / where seen |",
              "|---|---|---|---|---|"]
        for t in terms:
            r = out[cat][t]
            why = MO.NOTES.get(t) or r.get("note") or ""
            seen = ", ".join(sorted(T[cat].d.get(t, []))) if cat in T else ""
            L.append("| %s | %s | %s | %s | %s |" % (t, r["en"] or "?", r["confidence"], r["source"],
                                                     "; ".join(x for x in (why, "seen: " + seen if seen else "") if x)))
        L.append("")
    with open(os.path.join(HERE, "unmatched.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L))


def length_audit(out):
    rows = []
    for cat, lim in LIMITS.items():
        seen = set()
        for zh, r in out[cat].items():
            en = r["en"]
            if cat == "species" and ("（" in zh or "(" in zh) and "(" in (en or ""):
                continue  # form annotations are documentation labels, not in-game species strings
            if en and len(en) > lim and en not in seen:
                seen.add(en)
                rows.append((cat, zh, en, len(en), lim, MO.ABBREV.get(en, "?")))
    return rows


def write_readme(stats, long_names):
    p = os.path.join(HERE, "README.md")
    head = open(p, encoding="utf-8").read().split("<!-- STATS -->")[0] if os.path.exists(p) else "# Glossary\n\n"
    L = ["<!-- STATS -->", "", "## Counts (auto-generated)", "",
         "| category | terms | high-confidence | unresolved | sources |", "|---|---|---|---|---|"]
    for cat, s in stats.items():
        L.append("| %s | %d | %d (%.0f%%) | %d | %s |" % (cat, s["terms"], s["high"], 100.0 * s["high"] / max(1, s["terms"]),
                                                        s["unresolved"], ", ".join("%s %d" % kv for kv in s["by_source"].items())))
    L += ["", "## Names over DS text limits (auto-generated)", "",
          "Limits: species 10, moves 12, abilities 12, items 12 characters. Proposed abbreviations "
          "follow Gen 5+ in-game truncations where one exists.", "",
          "| category | 中文 | official English | len | limit | proposed |", "|---|---|---|---|---|---|"]
    for row in long_names:
        L.append("| %s | %s | %s | %d | %d | %s |" % row)
    with open(p, "w", encoding="utf-8") as f:
        f.write(head + "\n".join(L) + "\n")


if __name__ == "__main__":
    main()
