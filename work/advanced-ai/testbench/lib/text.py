"""Gen 4 (HGSS) message text: game codes to and from the test bench's text form, and the message bank decoder.

Ported from the Spanish workspace's tools/gen4text.py (dc8577c) for the parts the test bench uses: codes_to_text (the
emulator's text hooks, battle messages in logs), text_to_codes (nicknames written into built Pokémon) and decode_bank
(trainer names read from the ROM). The character table is ours, work/tools/charmap_en.tsv: pret's charmap.txt, the
same table the Spanish tool reads, without the Hangul block (checked equal on every other code on 2026-10-13), so the
English and the Spanish ROMs decode the same way.

A bank is one member of the message NARC (a/0/2/7): u16 count, u16 seed, then `count` encrypted (u32 offset, u32
length) pairs, then the encrypted strings. Strings are u16 codes ending in 0xFFFF; 0xFFFE starts a command (FFFE, cmd,
argc, args...); a leading 0xF100 marks a 9-bit packed string.

Text form (lossless): characters via the charmap, \\n \\r \\f for E000/25BC/25BD, {NAME a, b} or {X:CCCC a, b} for
commands, {U:CCCC} for codes not in the charmap.
"""
import os
import re
import struct

import tbpaths

CHARMAP = os.path.join(tbpaths.WORK, 'tools', 'charmap_en.tsv')
ESCAPES = {0xE000: '\\n', 0x25BC: '\\r', 0x25BD: '\\f'}
ESCAPES_REV = {v: k for k, v in ESCAPES.items()}
# the command entries of pret's charmap.txt (HEXCODE={NAME}), which the TSV leaves out
CMDS = {0x0100: 'STRVAR_1', 0x0200: 'YESNO', 0x0201: 'PAUSE', 0x0202: 'WAIT', 0x0203: 'CURSOR_X', 0x0204: 'CURSOR_Y',
        0x0205: 'ALN_CENTER', 0x0206: 'ALN_RIGHT', 0x0207: 'UNK_207', 0x0208: 'UNK_208', 0x0300: 'STRVAR_3',
        0x0400: 'STRVAR_4', 0x3400: 'STRVAR_34', 0xFF00: 'COLOR', 0xFF01: 'SIZE', 0xFF02: 'UNK_FF02'}
CMDS_REV = {v: k for k, v in CMDS.items()}


def load_charmap(path=CHARMAP):
    """(code -> character, character -> lowest code) from a code<TAB>text table."""
    dec = {}
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            if not line or line.startswith('#') or '\t' not in line:
                continue
            code, ch = line.split('\t', 1)
            code = int(code, 16)
            if code in ESCAPES or code in (0xFFFE, 0xFFFF) or len(ch) != 1:
                continue
            dec.setdefault(code, ch)
    enc = {}
    for code, ch in sorted(dec.items()):
        enc.setdefault(ch, code)  # first (lowest) code wins for duplicates
    return dec, enc


DEC, ENC = load_charmap()


def _cmd_name(cmd):
    base = cmd & 0xFF00
    if base in CMDS and CMDS[base].startswith('STRVAR'):
        return CMDS[base], cmd & 0xFF  # subtype is always written, even 0
    if cmd in CMDS:
        return CMDS[cmd], None
    return 'X:%04X' % cmd, None


def codes_to_text(codes):
    out, i = [], 0
    while i < len(codes):
        c = codes[i]
        if c == 0xFFFE:
            cmd, argc = codes[i + 1], codes[i + 2]
            args = codes[i + 3:i + 3 + argc]
            name, sub = _cmd_name(cmd)
            vals = ([sub] if sub is not None else []) + list(args)
            out.append('{%s%s}' % (name, (' ' + ', '.join(map(str, vals))) if vals else ''))
            i += 3 + argc
            continue
        if c in ESCAPES:
            out.append(ESCAPES[c])
        elif c in DEC and c != 0:
            ch = DEC[c]
            out.append('\\' + ch if ch in '{}\\' else ch)
        else:
            out.append('{U:%04X}' % c)
        i += 1
    return ''.join(out)


_TOKEN = re.compile(r'\{([^{}]*)\}|\\([nrf{}\\])')


def text_to_codes(text):
    codes, i = [], 0
    while i < len(text):
        m = _TOKEN.match(text, i)
        if m:
            if m.group(2) is not None:
                e = '\\' + m.group(2)
                codes.append(ESCAPES_REV[e] if e in ESCAPES_REV else ENC[m.group(2)])
            else:
                codes.extend(_parse_cmd(m.group(1)))
            i = m.end()
            continue
        c = ENC.get(text[i])
        if c is None:
            raise ValueError('no code for %r at %d in %r' % (text[i], i, text))
        codes.append(c)
        i += 1
    return codes


def _parse_cmd(body):
    name, _, rest = body.partition(' ')
    vals = [int(v, 0) for v in rest.split(',')] if rest.strip() else []
    if name.startswith('U:'):
        return [int(name[2:], 16)]
    if name.startswith('X:'):
        cmd = int(name[2:], 16)
    elif name.startswith('STRVAR') and name in CMDS_REV:
        cmd = CMDS_REV[name] | vals.pop(0)
    elif name in CMDS_REV:
        cmd = CMDS_REV[name]
    else:
        raise ValueError('unknown command {%s}' % body)
    return [0xFFFE, cmd, len(vals)] + vals


def _unpack9(codes):
    """Expand a 0xF100 packed string (codes after the marker): 9-bit characters carried 15 bits
    per word, ending at 0x1FF (bank 719, the trainer names, is stored this way)."""
    out, buf, bits = [], 0, 0
    for c in codes:
        buf |= (c & 0x7FFF) << bits
        bits += 15
        while bits >= 9:
            v = buf & 0x1FF
            buf >>= 9
            bits -= 9
            if v == 0x1FF:
                return out
            out.append(v)
    return out


def decode_bank(data):
    """Return (seed, [(text, compressed), ...])."""
    count, seed = struct.unpack_from('<HH', data, 0)
    key = (seed * 0x2FD) & 0xFFFF
    entries = []
    for i in range(count):
        k2 = (key * (i + 1)) & 0xFFFF
        k = k2 | (k2 << 16)
        off, ln = struct.unpack_from('<II', data, 4 + 8 * i)
        off ^= k
        ln ^= k
        ck = (0x91BD3 * (i + 1)) & 0xFFFF
        codes = []
        for j in range(ln):
            (c,) = struct.unpack_from('<H', data, off + 2 * j)
            codes.append(c ^ ck)
            ck = (ck + 0x493D) & 0xFFFF
        if codes and codes[-1] == 0xFFFF:
            codes.pop()
        compressed = bool(codes) and codes[0] == 0xF100
        if compressed:
            codes = _unpack9(codes[1:])
        entries.append((codes_to_text(codes), compressed))
    return seed, entries
