"""Sorting the failures of an AI battle: inherited from the Chinese hack, by design, or for review.

Taken from the Spanish workspace's tools/aifuzz.py (dc8577c) into lib/ because fuzz/aifuzz.py and
versus/aivsai_report.py both use it. One change: move_id reads the move from a battle message in English ('X used
Y!') as well as in Spanish ('X usó Y!'), with the names the ROM under test prints (its own move-name bank, use_rom)
over the frozen English names (lib/names.json); the Spanish tool read its text/en and text/es files.
"""
import json
import os
import re

from payload import AI_OVERLAY

INHERITED = {'020733B2'}
MENU_MOVE, MENU_TARGET = '0221200B', '02212673'   # the player's move menu sets the move, the target screen its target
# move animations that fail the same way in the Chinese ROM, from either side (qa/ai_research/animcheck.py);
# any other failure during a move is left for review
KNOWN_ANIM = {304: {'assert 020056FE'},                              # Hyper Voice: the cry's second channel
              519: {'assert 021E895E'},                              # Fire Pledge
              536: {'assert 021E5EFC', 'freeze ', 'null 5'},         # Leaf Tornado: battle heap leak, freezes after ~16 uses
              545: {'assert 02004786', 'assert 021E895E'},           # Searing Shot
              553: {'assert 02004786', 'assert 021E895E'}}           # Freeze Shock
STRUGGLE = 165
# a move's message: Spanish '¡X usó Y!', English 'X used Y!'; our ROM may break the line after 'used', which
# lib/text.py writes as \\n (\\r, \\f: other breaks), so `any(m in text for m in USED)` finds those messages too
USED = ('usó ', ' used ') + tuple(m + '\\' + c for m in ('usó', ' used') for c in 'nrf')
MOVE_NAMES = 739                    # the message bank of move names (a/0/2/7)
NAMES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'names.json')

_MOVE_IDS = {}
_ROM = [None]


def use_rom(rom):
    """Read move names from `rom`'s own bank too (the language its battle messages are in)."""
    if rom != _ROM[0]:
        _ROM[0] = rom
        _MOVE_IDS.clear()


def _load():
    with open(NAMES, encoding='utf-8') as f:
        for k, name in json.load(f)['move'].items():
            _MOVE_IDS.setdefault(name, int(k))
    if _ROM[0]:
        from romio import TEXT_NARC, read_narc
        from text import decode_bank
        narc, _ = read_narc(_ROM[0], TEXT_NARC)
        for i, (name, _) in enumerate(decode_bank(narc.files[MOVE_NAMES])[1]):
            if name and i:
                _MOVE_IDS[name] = i


def move_id(text):
    """The move in a battle message '...usó <move>!' or '... used <move>!' (a line break in it, which lib/text.py writes
    as \\n, \\r or \\f, reads as a space: our ROM breaks 'used' / 'Searing Shot!' over two lines)."""
    if not _MOVE_IDS:
        _load()
    text = ' '.join(re.sub(r'\\[nrf]', ' ', text).split()) + ' ' if text else text
    marker = next((m for m in USED if text and m in text), None)
    if marker is None:
        return None
    return _MOVE_IDS.get(text.split(marker, 1)[1].split('!')[0].strip())


def move_names():
    """{id: name} of the names move_id knows (the ROM's last when it has one)."""
    if not _MOVE_IDS:
        _load()
    return {v: k for k, v in _MOVE_IDS.items()}


def no_option_ok(fb, move):
    """A 'no option' fallback (code 6) that is by design, from the AI's legal-move mask: no move was legal and
    overlay 11 used Struggle, or every legal move was one the AI vetoes (a Choice lock, Encore, no bench to
    switch to) and overlay 11 used one of them."""
    legal = fb.get('legal')
    if legal is None or 'me' not in fb:
        return False
    if legal == 0:
        return move == STRUGGLE
    return any(legal >> i & 1 and fb['me']['moves'][i] == move for i in range(4))


def player_stuck(actions):
    """The battle stopped at the player's move menu: its last moves were all refused (no target set, no AI move)."""
    tail = actions[-4:]
    return len(tail) == 4 and all(a[5] == MENU_MOVE for a in tail)


def classify(x, advanced):
    """'review': failures the AI may own or nothing explains yet; 'inherited': failures the Chinese ROM has too;
    'stuck'/'slow': a battle that did not end, at the player's refused menu / still playing; 'struggle': fallbacks
    where no move was usable and overlay 11 used Struggle."""
    out = {'review': [], 'inherited': [], 'stuck': False, 'slow': False, 'struggle': 0, 'locked': 0}
    details = x.get('fail_detail') or [{'ev': f, 'text': None} for f in x['failures']]
    end = [f for f in details if f['ev'].split()[0] == 'assert' and f['ev'].split()[-1] in INHERITED]
    if len(end) > 5:
        out['review'].append('%d end-of-battle asserts' % len(end))
    for f in details:
        if f in end:
            continue
        m = move_id(f.get('move_text') or f.get('text'))
        if m in KNOWN_ANIM and f['ev'] in KNOWN_ANIM[m]:
            out['inherited'].append('%s (move %d)' % (f['ev'].strip(), m))
        else:
            out['review'].append(f['ev'].strip() + (' during %r' % f['text'][:60] if f.get('text') else ''))
    if not x['injected']:
        out['review'].append('no battle')
    elif x['frozen'] and not any(i.startswith('freeze') for i in out['inherited']):
        out['review'].append('freeze')
    elif x['ended'] is None and not x['frozen']:
        if player_stuck(x.get('actions', [])):
            out['stuck'] = True
        else:
            out['slow'] = True
    if advanced:
        ai_actions = [a for a in x.get('actions', []) if a[5] == 'ai']
        fallbacks = iter(x.get('fallbacks', []))
        for k, dd in enumerate(x['decisions']):
            fb = next(fallbacks, {}) if dd['fallback'] else {}   # one record per decision with a fallback code
            if dd['slot'] != AI_OVERLAY:
                out['review'].append('a decision came from overlay %s' % dd['slot'])
            elif dd['fallback'] not in (0, None, 3):
                act = ai_actions[k] if k < len(ai_actions) else None
                if dd['fallback'] == 6 and act and act[1] == 'move' and no_option_ok(fb, act[2]):
                    out['struggle' if act[2] == STRUGGLE else 'locked'] += 1
                else:
                    out['review'].append('advanced AI fell back: code %s' % dd['fallback'])
    return out


def problems(x, advanced):
    return classify(x, advanced)['review']
