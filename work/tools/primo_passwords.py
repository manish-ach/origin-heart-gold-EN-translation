#!/usr/bin/env python3
"""primo_passwords - Primo's Easy Chat passwords (Violet City Pokémon Center) for a Trainer ID.

    python3 work/tools/primo_passwords.py 12345            # all 11 passwords for Trainer ID 12345
    python3 work/tools/primo_passwords.py 12345 --ids      # also show the Easy Chat word ids
    python3 work/tools/primo_passwords.py --decode 12345 1106 1200 1300 1400   # what would Primo do?
    python3 work/tools/primo_passwords.py --self-test      # encoder/decoder round trip, all IDs
    python3 work/tools/primo_passwords.py --cross-check work/rom/origin_v4.0.3_cn.nds
    python3 work/tools/primo_passwords.py --solver-json out.json   # minimal data for a web solver
    python3 work/tools/primo_passwords.py --site           # write site/src/data/primo.json (website solver)

Everything game-specific is read from the ROM at run time (default: our English build,
work/build/origin_hg_v4.0.3_en_wip.nds; pass --rom for another). The only generated file that is
kept is the website's data, site/src/data/primo.json (--site): the word list, picker categories and
positions come from the ROM, but the English words and reward names come from our translation
source, work/translate/banks/a027/*.json, so a renamed Easy Chat word only needs a rerun of --site
(no ROM build). The page's encoder is site/src/lib/primo.mjs; `node work/tools/site/test_primo.mjs`
compares it with encode() below for every Trainer ID and reward.

How the game checks the password (script file 857, Primo = script 5; event-script commands
498 PrimoPasswordCheck1 / 499 PrimoPasswordCheck2; same code in the CN hack and in US HeartGold,
only the word list differs):

  * The player gives two Easy Chat phrases of two words each: w1 w2 / w3 w4 (word ids).
  * idx_i = position of w_i in the "password word list" (NARC a/2/1/2 member 0, a sorted u32 list
    of Easy Chat word ids; 360 entries in the hack, 351 in US HeartGold). Not in the list -> fail.
  * b0 = idx_1 (must be <= 255); b_i = (idx_i - idx_{i-1}) mod N for i = 2..4 (must be <= 255).
  * The 32-bit big-endian value b0b1b2b3 is rotated right by 5 bits.
  * m = (b3 & 0xF0) | (b3 >> 4); b0 ^= m; b1 ^= m; b2 ^= m.
  * The 24-bit big-endian value b0b1b2 is rotated right by (b3 & 0x0F) bits.
  * reward = b0 & 0x0F; b1 ^= b0; b2 ^= b0.
  * Valid iff (b1 << 8 | b2) == Trainer ID (the 16-bit public ID; the Secret ID is not used),
    (b0 >> 4) == 6 and b3 == ((b0 + b1) * b2) & 0xFF.
  * Check1 accepts reward 0-7 (bonus Box wallpaper #reward; unlocked once, later tries get the
    normal "thank you" line), Check2 accepts 8-10 (Egg: 8 Mareep, 9 Wooper, 10 Slugma; flags
    345/346/347, once each, needs a free party slot).

So every Trainer ID has exactly one password per reward; the encoder below inverts the steps.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)

DEFAULT_ROM = os.path.join(REPO, 'work', 'build', 'origin_hg_v4.0.3_en_wip.nds')
CHARMAP_EN = os.path.join(HERE, 'charmap_en.tsv')
BANKS_DIR = os.path.join(REPO, 'work', 'translate', 'banks', 'a027')
SITE_JSON = os.path.join(REPO, 'site', 'src', 'data', 'primo.json')

ARM9_BASE = 0x02000000
OV2_ID, OV2_BASE = 2, 0x02245F40
# Easy Chat word banks: u16 msg bank[11] then u16 count[11]; word id = running sum of counts
PMS_TABLE = 0x020F2B3C
PMS_BANKS = 11
NARC_PATH_TABLE = 0x0210E21C   # char* table, index = NARC id
# Easy Chat picker categories: 12 x {u32 filter fn, u32 u16* word list, u32 count}, in display
# order; the word lists hold the order the picker shows (the hack's Chinese order, not A-Z)
CATEGORY_TABLE, CATEGORY_COUNT = 0x02105FF0, 12
PASSWORD_NARC_ID = 214         # loaded by 0x020158EC (= "a/2/1/2" member 0)
MSG_NARC = 'a/0/2/7'
CATEGORY_BANK = 275            # Easy Chat category labels
WALLPAPER_BANK, WALLPAPER_FIRST = 23, 51   # bank 23 #51-58: the 8 bonus wallpapers, in bit order
SPECIES_BANK = 232
EGGS = {8: 179, 9: 194, 10: 218}           # GiveEgg species in script 857 (Mareep, Wooper, Slugma)
EGG_FLAGS = {8: 345, 9: 346, 10: 347}
ROTATE_ALL = 5                 # movs r2, #5 at ov2 0x0224EE50 / 0x0224EF90
MARKER = 6                     # cmp r0, #6 (high nibble of b0)

# Fingerprints (first 16 hex digits of SHA-256) of the code this script re-implements, taken from
# the untouched CN hack v4.0.3; our English build is byte-identical here. A mismatch means the
# ROM is not 起源心金 v4.0.3 (or the code moved), so the result must not be trusted.
FINGERPRINTS = {
    ('arm9', 0x02044C88, 0x02044DFC): 'af4657f917f6b08f',  # ScrCmd 498/499 handlers
    ('arm9', 0x02015788, 0x02015978): '4df4d681a501a9da',  # word id -> bank/msg, password list index
    ('arm9', 0x02029418, 0x02029420): '379a47b2e97a10d5',  # PlayerProfile_GetTrainerID (low 16 bits)
    ('ov2', 0x0224ED40, 0x0224F098): 'dd914727a5e2f314',   # rotate, decode/verify (both checks)
}


# ------------------------------------------------------------------ algorithm (pure functions)

def _rotr(buf, n_bytes, count):
    """In-place: rotate the big-endian bit string buf[0:n_bytes] right by `count` bits
    (port of ov2 0x0224ED40)."""
    for _ in range(count):
        carry = buf[n_bytes - 1] & 1
        for j in range(n_bytes - 1, 0, -1):
            buf[j] = (buf[j] >> 1) | ((buf[j - 1] & 1) << 7)
        buf[0] = (buf[0] >> 1) | (carry << 7)


def _rotl(buf, n_bytes, count):
    total = 8 * n_bytes
    _rotr(buf, n_bytes, (total - count % total) % total)


def decode(tid, words, wordlist):
    """Port of ov2 0x0224EDA0 (Check1) / 0x0224EEE0 (Check2) without the range split.
    Returns the reward number 0-15 the password encodes, or None if it is invalid for `tid`."""
    pos = {w: i for i, w in enumerate(wordlist)}
    n = len(wordlist)
    idx = [pos.get(w, -1) for w in words]
    b = [0, 0, 0, 0]
    for i in range(4):
        if idx[i] < 0:
            return None
        if i == 0:
            d = idx[0]
        elif idx[i] >= idx[i - 1]:
            d = idx[i] - idx[i - 1]
        else:
            d = n - (idx[i - 1] - idx[i])
        if d > 0xFF:
            return None
        b[i] = d
    _rotr(b, 4, ROTATE_ALL)
    m = (b[3] & 0xF0) | (b[3] >> 4)
    for i in range(3):
        b[i] ^= m
    _rotr(b, 3, b[3] & 0x0F)
    reward = b[0] & 0x0F
    b[1] ^= b[0]
    b[2] ^= b[0]
    if (b[1] << 8 | b[2]) != (tid & 0xFFFF) or (b[0] >> 4) != MARKER:
        return None
    if b[3] != ((b[0] + b[1]) * b[2]) & 0xFF:
        return None
    return reward


def primo_result(tid, words, wordlist):
    """What the script does: ('wallpaper', 0-7), ('egg', 8-10) or None (normal thank-you line)."""
    r = decode(tid, words, wordlist)
    if r is None:
        return None
    if r <= 7:
        return ('wallpaper', r)       # Check1: 0..7
    if 8 <= r <= 10:
        return ('egg', r)             # Check2: 8..10
    return None                       # 11..15: both checks return -1


def encode(tid, reward, wordlist):
    """The four Easy Chat word ids that make Primo give `reward` (0-10) to Trainer ID `tid`."""
    if not 0 <= reward <= 10:
        raise ValueError('reward must be 0-10')
    tid &= 0xFFFF
    hi, lo = tid >> 8, tid & 0xFF
    b0 = (MARKER << 4) | reward
    b = [b0, hi ^ b0, lo ^ b0, ((b0 + hi) * lo) & 0xFF]
    _rotl(b, 3, b[3] & 0x0F)
    m = (b[3] & 0xF0) | (b[3] >> 4)
    for i in range(3):
        b[i] ^= m
    _rotl(b, 4, ROTATE_ALL)
    n = len(wordlist)
    idx = [b[0]]
    for i in range(1, 4):
        idx.append((idx[-1] + b[i]) % n)
    return [wordlist[i] for i in idx]


# ------------------------------------------------------------------ ROM access

class RomData:
    def __init__(self, path, text='rom'):
        """text='rom': message text from the ROM; 'banks': the `en` of work/translate/banks/a027/."""
        import ndspy.rom
        import msgtool
        self.path = path
        rom = ndspy.rom.NintendoDSRom.fromFile(path)
        self.arm9 = bytes(rom.arm9)
        self.ov2 = bytes(rom.loadArm9Overlays([OV2_ID])[OV2_ID].data)
        self.fingerprint_ok = all(self.fingerprint(k) == v for k, v in FINGERPRINTS.items())
        # word id -> (bank, msg no)
        vals = struct.unpack_from('<%dH' % (2 * PMS_BANKS), self.arm9, PMS_TABLE - ARM9_BASE)
        self.banks, self.counts = list(vals[:PMS_BANKS]), list(vals[PMS_BANKS:])
        # password word list
        p = struct.unpack_from('<I', self.arm9, NARC_PATH_TABLE - ARM9_BASE + 4 * PASSWORD_NARC_ID)[0]
        o = p - ARM9_BASE
        self.password_narc = self.arm9[o:self.arm9.index(b'\0', o)].decode()
        import ndspy.narc
        d = ndspy.narc.NARC(rom.getFileByName(self.password_narc)).files[0]
        self.wordlist = list(struct.unpack('<%dI' % (len(d) // 4), d))
        # picker categories: word id -> (category no, 1-based position in that category)
        self.category_of = {}
        for c in range(CATEGORY_COUNT):
            _, ptr, cnt = struct.unpack_from('<3I', self.arm9, CATEGORY_TABLE - ARM9_BASE + 12 * c)
            for i, w in enumerate(struct.unpack_from('<%dH' % cnt, self.arm9, ptr - ARM9_BASE)):
                self.category_of.setdefault(w, (c, i + 1))
        # text
        self._cm = msgtool.Charmap.load([CHARMAP_EN])
        self._msg = msgtool.Narc.parse(msgtool.get_file(rom, MSG_NARC))
        self._msgtool = msgtool
        self._bank_cache = {}
        self.text = text

    def fingerprint(self, key):
        where, s, t = key
        blob, base = (self.arm9, ARM9_BASE) if where == 'arm9' else (self.ov2, OV2_BASE)
        return hashlib.sha256(blob[s - base:t - base]).hexdigest()[:16]

    def bank(self, num):
        if num not in self._bank_cache and self.text == 'banks':
            with open(os.path.join(BANKS_DIR, '%04d.json' % num), encoding='utf-8') as fh:
                strings = json.load(fh)['strings']
            out = []
            for i, st in enumerate(strings):
                assert st['id'] == i, 'bank %d: ids out of order at %d' % (num, i)
                out.append(st['en'])
            self._bank_cache[num] = out
        if num not in self._bank_cache:
            _, strings, _ = self._msgtool.decrypt_bank(self._msg.files[num])
            self._bank_cache[num] = [self._msgtool.decode_units(u, self._cm) for u in strings]
        return self._bank_cache[num]

    def word_source(self, wid):
        base = 0
        for k, (b, c) in enumerate(zip(self.banks, self.counts)):
            if wid < base + c:
                return k, b, wid - base
            base += c
        raise ValueError('word id %d out of range' % wid)

    def word(self, wid):
        _, b, i = self.word_source(wid)
        return self.bank(b)[i]

    def group(self, wid):
        """Easy Chat category label the word is listed under in the picker (types are under
        ABILITY), e.g. 'PEOPLE'."""
        c = self.category_of.get(wid)
        return self.bank(CATEGORY_BANK)[c[0]] if c else '?'

    def position(self, wid):
        """1-based position of the word in its category list (picker order)."""
        c = self.category_of.get(wid)
        return c[1] if c else 0

    def reward_name(self, r):
        if r <= 7:
            return '%s wallpaper' % self.bank(WALLPAPER_BANK)[WALLPAPER_FIRST + r]
        return '%s Egg' % self.bank(SPECIES_BANK)[EGGS[r]]


def default_rom():
    return DEFAULT_ROM


# ------------------------------------------------------------------ CLI

def table(rd, tid, show_ids=False):
    rows = []
    for r in list(range(8, 11)) + list(range(8)):
        w = encode(tid, r, rd.wordlist)
        assert primo_result(tid, w, rd.wordlist) == (('egg' if r >= 8 else 'wallpaper'), r)
        fmt = (lambda x: '%s (%s %d, id %d)' % (rd.word(x), rd.group(x), rd.position(x), x)) if show_ids else rd.word
        rows.append((rd.reward_name(r), '%s %s' % (fmt(w[0]), fmt(w[1])), '%s %s' % (fmt(w[2]), fmt(w[3])), w))
    return rows


def cross_check(rd, other_path):
    other = RomData(other_path)
    ok = True
    for k in FINGERPRINTS:
        same = rd.fingerprint(k) == other.fingerprint(k)
        ok &= same
        print('  %-4s %08X-%08X  %s' % (k[0], k[1], k[2], 'identical' if same else 'DIFFERENT'))
    for name, a, b in (('word bank table', (rd.banks, rd.counts), (other.banks, other.counts)),
                       ('password list NARC', rd.password_narc, other.password_narc),
                       ('password word list', rd.wordlist, other.wordlist)):
        same = a == b
        ok &= same
        print('  %-22s %s' % (name, 'identical' if same else 'DIFFERENT'))
    return ok


def solver_json(rd):
    words = {}
    for w in rd.wordlist:
        words[str(w)] = {'en': rd.word(w), 'category': rd.group(w), 'position': rd.position(w)}
    return {
        'about': 'Primo Easy Chat passwords, Origin HeartGold v4.0.3 English patch. Word texts '
                 'are the English translation; ids are Easy Chat word ids; category/position = '
                 'where the word sits in the Easy Chat picker (1-based).',
        'algorithm': [
            'tid = 16-bit public Trainer ID; N = len(wordlist); reward r in 0..10',
            'b0 = 0x60 | r; hi = tid >> 8; lo = tid & 0xFF',
            'b = [b0, hi ^ b0, lo ^ b0, ((b0 + hi) * lo) & 0xFF]',
            'rotate b[0..2] (24-bit big-endian) LEFT by (b[3] & 0x0F) bits',
            'm = (b[3] & 0xF0) | (b[3] >> 4); b[0] ^= m; b[1] ^= m; b[2] ^= m',
            'rotate b[0..3] (32-bit big-endian) LEFT by 5 bits',
            'i0 = b[0]; i1 = (i0 + b[1]) % N; i2 = (i1 + b[2]) % N; i3 = (i2 + b[3]) % N',
            'phrase 1 = wordlist[i0], wordlist[i1]; phrase 2 = wordlist[i2], wordlist[i3]',
        ],
        'word_count': len(rd.wordlist),
        'tid_bits': 16,
        'uses_secret_id': False,
        'marker': MARKER,
        'rotate_all_bits': ROTATE_ALL,
        'wordlist': rd.wordlist,
        'words': words,
        'rewards': [{'value': r, 'kind': 'wallpaper' if r <= 7 else 'egg', 'en': rd.reward_name(r),
                     **({'flag': EGG_FLAGS[r], 'species': EGGS[r]} if r >= 8 else {'wallpaper_bit': r})}
                    for r in range(11)],
    }


def has_cjk(s):
    return any('\u3000' <= ch <= '\u9fff' or '\uff00' <= ch <= '\uffef' for ch in s)


def site_json(rd):
    """The website solver's data (site/src/data/primo.json): words in password-list order."""
    words = []
    for w in rd.wordlist:
        en = rd.word(w)
        words.append({'id': w, 'en': en, 'category': rd.group(w), 'position': rd.position(w)})
    rewards = [{'value': r, 'kind': 'wallpaper' if r <= 7 else 'egg', 'en': rd.reward_name(r)}
               for r in list(range(8, 11)) + list(range(8))]
    for x in words + rewards:
        for k in [k for k in ('en', 'category') if k in x]:
            v = x[k]
            if not isinstance(v, str) or not v.strip() or has_cjk(v) or '{' in v:
                raise SystemExit('primo site data: bad text %r for %s (untranslated, empty or a text code?)' % (v, x))
    if any(x['position'] < 1 for x in words):
        raise SystemExit('primo site data: a password word is in no Easy Chat picker category')
    return {
        '_generated': 'python3 work/tools/primo_passwords.py --site (words from work/translate/banks/a027; '
                      'list, categories and positions from %s). Do not edit by hand.' % os.path.basename(rd.path),
        'marker': MARKER,
        'rotate_all_bits': ROTATE_ALL,
        'words': words,
        'rewards': rewards,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('tid', nargs='?', type=int, help='Trainer ID (0-65535, the number on the Trainer Card)')
    ap.add_argument('--rom', default=None, help='ROM to read (default: %s)' % os.path.relpath(DEFAULT_ROM, REPO))
    ap.add_argument('--ids', action='store_true',
                    help='show each word\'s picker category, its position in that category and its word id')
    ap.add_argument('--decode', nargs=5, type=int, metavar=('TID', 'W1', 'W2', 'W3', 'W4'))
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--cross-check', metavar='ROM')
    ap.add_argument('--solver-json', metavar='OUT')
    ap.add_argument('--site', action='store_true',
                    help='write %s (English from the translation banks)' % os.path.relpath(SITE_JSON, REPO))
    a = ap.parse_args(argv)
    rd = RomData(a.rom or default_rom(), text='banks' if a.site else 'rom')
    if not rd.fingerprint_ok:
        print('WARNING: the password code in %s does not match 起源心金 v4.0.3; results may be wrong.'
              % rd.path, file=sys.stderr)
    did = False
    if a.cross_check:
        did = True
        print('cross-check %s vs %s' % (rd.path, a.cross_check))
        print('result:', 'IDENTICAL' if cross_check(rd, a.cross_check) else 'DIFFERENCES FOUND')
    if a.self_test:
        did = True
        wl = rd.wordlist
        bad = 0
        for tid in range(65536):
            for r in range(11):
                w = encode(tid, r, wl)
                if decode(tid, w, wl) != r or decode(tid ^ 1, w, wl) is not None:
                    bad += 1
        print('self-test: %d IDs x 11 rewards, %d failures; list N=%d (%s), fingerprints %s'
              % (65536, bad, len(wl), rd.password_narc, 'OK' if rd.fingerprint_ok else 'MISMATCH'))
        if bad:
            return 1
    if a.decode:
        did = True
        tid, *w = a.decode
        print('words:', ' / '.join('%s (%s %d, id %d)' % (rd.word(x), rd.group(x), rd.position(x), x) if x < sum(rd.counts) else '#%d' % x
                                   for x in w))
        res = primo_result(tid, w, rd.wordlist)
        print('result:', 'no reward (normal thank-you line)' if res is None else rd.reward_name(res[1]))
    if a.solver_json:
        did = True
        with open(a.solver_json, 'w', encoding='utf-8') as fh:
            json.dump(solver_json(rd), fh, ensure_ascii=False, indent=1)
        print('wrote', a.solver_json)
    if a.site:
        did = True
        if not rd.fingerprint_ok:
            print('not writing the site data: wrong ROM', file=sys.stderr)
            return 1
        data = site_json(rd)
        tmp = SITE_JSON + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
            fh.write('\n')
        os.replace(tmp, SITE_JSON)
        print('wrote %s (%d words)' % (os.path.relpath(SITE_JSON, REPO), len(data['words'])))
    if a.tid is not None:
        did = True
        if not 0 <= a.tid <= 65535:
            ap.error('Trainer ID must be 0-65535')
        print('Trainer ID %05d (the public ID on the Trainer Card; the Secret ID is not used)' % a.tid)
        print('Tell Primo phrase 1, then phrase 2 (two words each):')
        rows = table(rd, a.tid, a.ids)
        wr = max(len(r[0]) for r in rows)
        w1 = max(len(r[1]) for r in rows)
        for name, p1, p2, _ in rows:
            print('  %-*s  %-*s  /  %s' % (wr, name, w1, p1, p2))
    if not did:
        ap.print_help()
    return 0


if __name__ == '__main__':
    sys.exit(main())
