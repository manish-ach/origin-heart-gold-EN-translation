"""Shared helpers for the TM / manifest pipeline (work/translate/scripts)."""
import json, os, re, unicodedata
from collections import Counter

WORK = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
EXTRACT = os.path.join(WORK, 'extract')
OUT = os.path.join(WORK, 'translate')

CJK_RE = re.compile(r'[㐀-䶿一-鿿豈-﫿]')
KANA_RE = re.compile(r'[぀-ヿ]')
TAG_RE = re.compile(r'\{[^{}]*\}')
BREAK_TAGS = ('{NEWLINE}', '{SCROLL}', '{CLEAR}')
VAR_RE = re.compile(r'\{VAR:([0-9A-F]{4})(?::([0-9,]*))?\}')


def load_narc(version, narc='a027'):
    d = os.path.join(EXTRACT, version, narc)
    banks = {}
    for f in sorted(os.listdir(d)):
        if not re.match(r'\d{4}\.json$', f):
            continue
        j = json.load(open(os.path.join(d, f), encoding='utf-8'))
        banks[j['bank']] = [s['text'] for s in sorted(j['strings'], key=lambda s: s['id'])]
    return banks


def has_cjk(t):
    return bool(CJK_RE.search(TAG_RE.sub('', t)))


def cjk_count(t):
    return len(CJK_RE.findall(TAG_RE.sub('', t)))


PUNCT_FOLD = str.maketrans({'〜': '~', '⋯': '…', '•': '·', '─': '-', '―': '-', '—': '-'})

# variant fold (v3 ACG table has some traditional/variant glyphs); filled by learn_fold()
FOLD = {}


def set_fold(d):
    FOLD.clear()
    FOLD.update(d)


def norm(t, loose=False):
    """Matching key: NFKC, drop line/page breaks and whitespace, fold variants.
    loose=True also replaces every {VAR..}/{U+..} tag with a placeholder '§'."""
    t = unicodedata.normalize('NFKC', t)
    t = t.translate(PUNCT_FOLD)
    for b in BREAK_TAGS:
        t = t.replace(b, '')
    t = re.sub(r'\s+', '', t)
    if FOLD:
        t = ''.join(FOLD.get(c, c) for c in t)
    if loose:
        t = TAG_RE.sub('§', t)
        t = t.replace('...', '…').replace('~', '').rstrip('.。!?…')
    return t


def var_sig(t):
    """Multiset of command ids (ignoring colour/size/format commands args)."""
    return Counter(m.group(1) for m in VAR_RE.finditer(t))
