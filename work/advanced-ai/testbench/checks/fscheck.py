"""The advanced AI's foresight at run time (src/advai.c fs_predict; the Spanish qa/aivsai/rc29_F.md).

  .venv/bin/python work/advanced-ai/testbench/checks/fscheck.py --rom ROM --payload PAYLOAD [--games N] [--seed S]
                   [--rng synced|legacy] [--human [--switch P]] [--first K] [--workers W] [--tag T] [--teams GAMES.json]
                   [-o OUT]

Ported from the Spanish workspace's tools/fscheck.py (dc8577c). Changes: the harness is versus/aivsai.py (the AI
setting in the save in RAM, addresses from the payload); the luck steering checks (--steer, --steer-drop,
--steer-trace) are not ported, since this project compiles steering out (AI_NO_STEER); the crit message and the
party screen's "no energy left" refusal are the ROM's own strings (battle_string.narc 2:77, a/0/2/7 6:77), so English
and Spanish builds read alike; results go to RUNS/fscheck/. Exit status 1 when a known part is wrong (neither exact
nor a knockout after chip damage), when no decision of the advanced AI was seen, when it fell back (any code but 6, no
usable option), or with --human when the AI changed the battle's luck or saw a harness word.

AI-vs-AI singles battles on the emulator, aivsai's harness: the level-80 trainer teams, the advanced AI on the trainer
side, overlay 11 on the player's. At each decision of the advanced AI that trusted the LCG word, its cell of the pair
then played (its move, the player's move) is compared with the turn, for each part the cell knows: the damage the move
dealt (0 when it missed, was stopped or flinched) and the crit message after its hit.

--teams plays a set list of games (the Spanish tools/fs_teams.py wrote them, built to meet the rc31 F2 classes)
instead of the drawn trainer teams. The summary's by_class counts each checked part (status moves' own parts left
out) under the classes its pair falls in (class_tags: slp, conf, prot, none, ng, self, or base).

--first K skips the first K games of the seed's list; --workers W splits the games over W processes (each its own
emulator, under ADVAI_EMU_SLOTS) and adds their results up. Synced luck hands the AI the battle's word (aivsai
FS_WORD_AT); legacy luck leaves it the live word, trusted only once overlay 11 has answered.
--human: the shipping path. A scripted person plays the player's side through vanilla's menus (aivsai's human mode:
the controller entries are left alone): at each FIGHT menu it touches FIGHT and one of the four move buttons, chosen
by a random generator seeded per game (B goes back when the game refuses the move); with --switch P it switches
instead, with chance P, through POKEMON, a random other able Pokemon's panel and SHIFT (the party screen loads its
overlay into the AI's slot: the AI's ai_resume path); after a faint or its own pivot it touches a panel and SHIFT,
the next panel at each try (the battle's party order is not the screen's), and B after "no energy left to battle"; A
advances everything else. Luck is legacy, so the AI reads the live battle word; the run counts any FS_WORD_AT magic
and any NOREAD word it sees (both must stay 0). The player's move is the committed record the AI read (adapter
0x02252D20[0]: +0xA answered, +0 the records; word 0 kind in bits 0-3, 1 a move, the move in bits 8-23, word 2 the
user's pokeID). The run also checks every poll of the trainer side's AI and every trainer-side replacement call: the
battle RNG word (main+0x24C) at the return must equal the word at the call (the AI reads the luck, never steers it).
A part counts as 'ko' (not exact) when a knockout was predicted and played but chip damage between the decision and
the hit (Rough Skin, recoil, a hazard) left less HP to take.
Prints one JSON line per checked part and a summary; -o writes the summary and the rows as JSON.
"""
import argparse
import json
import os
import random
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402
import aibench  # noqa: E402
import aivsai  # noqa: E402
import emu  # noqa: E402
import payload  # noqa: E402

FS_MAGIC = 0x46534947
ITCM = (0x01FF8000, 0x02000000)
CELL, CELLS = 14, 40               # struct FsState: the cells' size and offset
CRIT = ('battle/string/battle_string.narc', 2, 77)      # "A critical hit!" (singles)
# --human: the player's routines (aitime.py), its committed records (read_check.py), its touch points (aifuzz.py,
# aiplay.py)
HUMAN_SELECT, HUMAN_REPLACE = 0x02203654, 0x02203F00
ADAPTERS = 0x02252D20
FIGHT, MOVE_BUTTONS, POKEMON, SHIFT = (128, 90), [(64, 53), (192, 53), (64, 109), (192, 109)], (221, 165), (128, 108)
BACK = (236, 170)                  # the party screen's return arrow (a chosen Pokemon's menu back to the list)
TICK = 40                          # frames between the scripted player's actions
REFUSED = ('a/0/2/7', 6, 77)      # "<name> has no energy left to battle!": a fainted Pokemon chosen on the party screen


def flat(text):
    """A message as one line: its line and page breaks as spaces, its commands left out."""
    t = re.sub(r'\\[nrf]', ' ', text or '')
    return ' '.join(re.sub(r'\{[^}]*\}', '', t).split())


def rom_text(rom, where):
    """The longest literal part of a ROM string (narc, bank, index): what every printing of it contains."""
    from romio import read_narc
    from text import decode_bank
    narc, _ = read_narc(rom, where[0])
    t = decode_bank(narc.files[where[1]])[1][where[2]][0]
    parts = [flat(p) for p in re.split(r'\{STRVAR[^}]*\}', t)]
    return max(parts, key=len)


def panel(i):
    """The middle of party member i's panel on the battle's party screen: two columns of three."""
    return 64 + 128 * (i % 2), 28 + 48 * (i // 2)


# rc31 F2: the classes a part's pair falls in (rc31_F2.md), from both active Pokemon at the decision and the two moves:
# slp either asleep (condition 2), conf either confused (6), prot either move a Protect (effects 111, 355, 361, 383,
# 441, 451), none a status move before the other's (effects advai.c fs_quiet lists), ng No Guard on either side or an
# armor on the part's target, self a damaging move that changes its user's stats (quality 7); base: none of them
PROTECT_EFFECTS = {111, 355, 361, 383, 441, 451}
QUIET_EFFECTS = {10, 50, 52, 53, 212, 270, 277, 312, 316, 321, 327, 47, 390, 98, 85, 225, 266, 112, 249, 340}
NO_GUARD, ARMORS = 99, (4, 75)
QUICK_CLAW, QUICK_DRAW = 217, 259


def mon_state(mu, b):
    """What the class tags need of a battle Pokemon."""
    return {'slp': mu.read_long(b + 0x3C + 16) & 7, 'conf': mu.read_long(b + 0x3C + 48) & 7, 'ability': mu.read_short(b + 0x16),
            'item': mu.read_short(b + 0x20), 'spe': mu.read_short(b + 0x22C + 8)}


def class_tags(d, me, op, my_move, foe_move, part):
    mv = lambda i: d.moves_info[i] if hasattr(d, 'moves_info') else d.move(i)  # noqa: E731
    tags = set()
    if me['slp'] or op['slp']:
        tags.add('slp')
    if me['conf'] or op['conf']:
        tags.add('conf')
    eff = [mv(my_move)['effect'], mv(foe_move)['effect']]
    cls = [mv(my_move)['class'], mv(foe_move)['class']]
    if any(e in PROTECT_EFFECTS for e in eff):
        tags.add('prot')
    if any(c == 0 and e in QUIET_EFFECTS for e, c in zip(eff, cls)):
        tags.add('none')
    if any(c and mv(x)['quality'] == 7 for x, c in zip((my_move, foe_move), cls)):
        tags.add('self')
    for x, c in zip((my_move, foe_move), cls):
        q, st = mv(x)['quality'], mv(x)['status']
        if c == 0 and ((q == 1 and st in (1, 4, 5)) or st == 18 or mv(x)['effect'] == 175):
            tags.add('acc')         # rc33 F3_ACC: a status move whose only draw is accuracy
        if c == 0 and q in (1, 5) and st in (2, 6):
            tags.add('sicklen')     # rc33 F3_LEN: a sleep or confusion move
    target = op if part == 'mine' else me
    if NO_GUARD in (me['ability'], op['ability']) or target['ability'] in ARMORS:
        tags.add('ng')
    if QUICK_CLAW in (me.get('item'), op.get('item')) or QUICK_DRAW in (me['ability'], op['ability']):
        tags.add('qc')              # rc33 F3_ORD: a Quick Claw or Quick Draw draw before the moves
    if me.get('spe') is not None and me.get('spe') == op.get('spe'):
        tags.add('tie')             # rc33 F3_ORD: equal Speed stats (stages not read)
    status_move = cls[0 if part == 'mine' else 1] == 0
    return sorted(tags) or ['base'], status_move


def read_record(mu, at):
    b = lambda o: mu.read_byte(at + o)  # noqa: E731
    s16 = lambda o: (lambda v: v - 0x10000 if v & 0x8000 else v)(mu.read_short(at + o))  # noqa: E731
    rec = {'word': mu.read_long(at + 4), 'me_hp': mu.read_long(at + 8), 'opp_hp': mu.read_long(at + 12),
           'trusted': b(21), 'steer': b(23), 'first': [[b(24 + 4 * i + k) for k in range(4)] for i in range(4)], 'cell': []}
    for i in range(4):
        row = []
        for k in range(4):
            o = CELLS + CELL * (4 * i + k)
            f = [b(o + j) for j in range(10)]
            row.append(dict(zip(('mine', 'foe', 'stopped', 'flinched', 'missed', 'crit', 'flinch_foe', 'f_stopped',
                                 'f_missed', 'f_crit'), f), dmg=s16(o + 10), f_dmg=s16(o + 12)))
        rec['cell'].append(row)
    return rec


class Check(aivsai.Duel):
    game_id = None

    def __init__(self, rom, state, rows):
        super().__init__(rom, state, 'adv')
        self.rows, self.fs_at, self.turn = rows, None, None
        self.decisions = self.trusted = 0
        self.untrusted = {}                # --human: decisions not trusted, by the committed record's kind
        self.crit_text = rom_text(rom, CRIT)

    def fs_record(self):
        mu = self.mu
        if self.fs_at is None or mu.read_long(self.fs_at) != FS_MAGIC:
            self.fs_at = next((a for a in range(ITCM[0], ITCM[1], 4) if mu.read_long(a) == FS_MAGIC), None)
        return read_record(mu, self.fs_at) if self.fs_at is not None else None

    def _setter(self, kind):
        base = super()._setter(kind)

        def f(a, s):
            c = self.cur
            if c is not None and c.get('injected') and self.turn is not None and self.side is not None:
                lr = self.reg.r14 & ~1
                if self.adv_code[0] <= lr < self.adv_code[1] and self.side == 1 and self.deciding:
                    me = self.deciding
                    opb = (self.party(0) or [0])[0]
                    self.turn['state'] = [mon_state(self.mu, me), mon_state(self.mu, opb) if opb else None]
                    self.turn['mine'] = {'kind': kind, 'move': self.reg.r1, 'species': self.mu.read_short(me),
                                         'moves': [self.mu.read_short(me + 0x25A + 0x12 * i) for i in range(4)],
                                         'rec': self.fs_record(),
                                         'live_word': self.mu.read_long(self.mu.read_long(aibench.MAIN_PTR) +
                                                                        aibench.RNG)}
                    if self.human:
                        self.turn['foe'] = self.committed()
                elif self.orig_code[0] <= lr < self.orig_code[1] and self.side == 0 and self.deciding:
                    op = self.deciding
                    self.turn['foe'] = {'kind': kind, 'move': self.reg.r1, 'species': self.mu.read_short(op),
                                        'moves': [self.mu.read_short(op + 0x25A + 0x12 * i) for i in range(4)]}
            base(a, s)
        return f

    def event(self, ev):
        k = ev.get('kind')
        if k == 'turn':
            self.close()
            self.turn = {'n': ev['turn'], 'hits': [], 'crits': [], 'texts': [], 'kos': [],
                         'view': [ev.get('adv'), ev.get('orig')]}
        elif k == 'end':
            self.close()
            self.turn = None
        elif self.turn is not None and k == 'hit':
            self.turn['hits'].append((ev.get('move'), [(t[0], t[1]) for t in ev.get('targets') or []]))
            for side in (0, 1):             # the damage is already off the HP: a target at 0 fell to this hit
                b = (self.party(side) or [0])[0]
                if b and not self.mu.read_short(b + 0x1E):
                    self.turn['kos'].append((ev.get('move'), self.species_of(b)))
        elif self.turn is not None and k == 'message':
            self.turn['texts'].append(ev.get('text') or ev.get('ability'))
            if self.crit_text in flat(str(ev.get('text', ''))) and self.turn['hits']:
                self.turn['crits'].append(self.turn['hits'][-1][0])

    def close(self):
        t = self.turn
        if not t or 'mine' not in t:
            return
        self.decisions += 1
        mine, foe, rec = t['mine'], t.get('foe'), t['mine']['rec']
        if not rec or not rec['trusted']:
            if self.human:
                key = (foe or {}).get('kind', 'none')
                self.untrusted[key] = self.untrusted.get(key, 0) + 1
            return
        self.trusted += 1
        if mine['kind'] != 'move' or not foe or foe['kind'] != 'move' or mine['move'] not in mine['moves'] or \
                foe['move'] not in foe['moves']:
            return
        i, k = mine['moves'].index(mine['move']), foe['moves'].index(foe['move'])
        cell = rec['cell'][i][k]
        name = self.d.move_name
        sp = self.d.species_name if hasattr(self.d, 'species_name') else {}
        my_name, foe_name = name.get(mine['move'], '?'), name.get(foe['move'], '?')
        me_sp, op_sp = sp.get(mine['species']), sp.get(foe['species'])

        def dealt(move, target):
            return sum(d for m, ts in t['hits'] if m == move for n, d in ts if target is None or n == target)
        for part, mv, target, hp in (('mine', my_name, op_sp, rec['opp_hp']), ('foe', foe_name, me_sp, rec['me_hp'])):
            p = '' if part == 'mine' else 'f_'
            if not cell[part] or (my_name == foe_name and (target is None or me_sp == op_sp)):    # the same move on the same species: hits not told apart
                continue
            void = cell[p + 'stopped'] or cell[p + 'missed'] or (part == 'mine' and cell['flinched'])
            pred = 0 if void else min(cell[p + 'dmg'], hp)
            real = min(dealt(mv, target), hp)
            crit_pred = bool(cell[p + 'crit']) and not void
            crit_real = mv in t['crits'] and (my_name != foe_name)
            row = {'turn': t['n'], 'part': part, 'move': mv, 'first': rec['first'][i][k], 'pred': pred, 'real': real,
                   'crit': [crit_pred, crit_real], 'missed': bool(cell[p + 'missed']), 'stopped': bool(cell[p + 'stopped']),
                   'ok': pred == real and (void or crit_pred == crit_real or my_name == foe_name),
                   # a knockout predicted and played, the target's HP lowered between the decision and the hit
                   # (Rough Skin, recoil, a hazard): the damage dealt is the HP it had left
                   'ko': not void and 0 < real < pred and any(m == mv and (target is None or n == target)
                                                            for m, n in t['kos']),
                   'game': self.game_id, 'word': '%08X' % rec['word'], 'live_word': '%08X' % mine['live_word']}
            st = t.get('state')
            if st and st[1]:
                row['tags'], row['status_move'] = class_tags(self.d, st[0], st[1], mine['move'], foe['move'], part)
            if not row['ok']:
                row.update(pair=[my_name, foe_name], cell=cell, hits=t['hits'], texts=t['texts'], view=t['view'],
                           hp=[rec['me_hp'], rec['opp_hp']])
            self.rows.append(row)
            print(json.dumps(row), flush=True)


class HumanCheck(Check):
    """Check with a scripted person on the player's side (see --human above)."""

    def __init__(self, rom, state, rows):
        super().__init__(rom, state, rows)
        self.human = True
        self.refused_text = rom_text(rom, REFUSED)
        self.mem.register_exec(HUMAN_SELECT, lambda a, s: self._routine('sel'))
        self.mem.register_exec(HUMAN_REPLACE, lambda a, s: self._routine('rep'))
        self.seen_at = {'sel': -10 ** 9, 'rep': -10 ** 9}
        self.luck = {'polls': 0, 'changed': [], 'replace_calls': 0, 'replace_changed': [], 'slots': {},
                     'fs_magic': 0, 'noread': 0}
        self.pending, self.policy, self.k, self.driving = None, random.Random(0), 0, False
        self.rep_try, self.rep_last, self.refused = 0, -10 ** 9, False
        self.choices = {'moves': 0, 'switch': 0, 'back': 0, 'replace': 0}
        self.switch_rate = 0.0
        self._raw_step = self.r.step
        self.r.step = self._step

    def _routine(self, kind):
        if self.cur is not None and self.cur.get('injected'):
            self.seen_at[kind] = self.r.frames

    def committed(self):
        """The player's committed action, as the AI read it: kind, move, the user's species and moves."""
        mu = self.mu
        ad = mu.read_long(ADAPTERS)
        if not mu.read_byte(ad + 0xA):
            return {'kind': 'none'}
        w = [mu.read_long(mu.read_long(ad) + 4 * j) for j in range(3)]
        party = self.party(0) or []
        me = party[0] if party else 0
        out = {'kind': {1: 'move', 2: 'item', 3: 'switch'}.get(w[0] & 15, 'other %d' % (w[0] & 15)),
               'record': ['%08X' % x for x in w]}
        if out['kind'] == 'move' and me:
            out.update(move=(w[0] >> 8) & 0xFFFF, species=mu.read_short(me), user=w[2], poke=mu.read_byte(me + 0x14),
                       moves=[mu.read_short(me + 0x25A + 0x12 * i) for i in range(4)])
        return out

    # --- the AI's polls and replacement calls leave the battle's luck alone; harness words stay clear
    def _words(self):
        mu = self.mu
        self.luck['fs_magic'] += mu.read_long(self.words['FS_WORD_AT']) == self.words['FS_WORD_MAGIC']
        self.luck['noread'] += mu.read_long(self.words['NOREAD_FLAG']) == self.words['NOREAD_MAGIC']
        return mu.read_long(aibench.MAIN_PTR) + aibench.RNG

    def _poll(self, a, s):
        super()._poll(a, s)
        self.pending = None
        if self.cur is None or not self.cur.get('injected') or not self.in_battle():
            return
        if self.mu.read_byte(self.reg.r4 + aivsai.CLIENT_SIDE) & 1:
            at = self._words()
            slot = self.mu.read_long(self.mu.read_long(aibench.MAIN_PTR) + aivsai.MAIN_SLOT)
            self.luck['slots'][str(slot)] = self.luck['slots'].get(str(slot), 0) + 1
            self.pending = ('poll', at, self.mu.read_long(at), self.r.frames)

    def _poll_ret(self, a, s):
        p, self.pending = self.pending, None
        if p and p[0] == 'poll':
            at = self._words()
            self.luck['polls'] += 1
            now = self.mu.read_long(at)
            if at != p[1] or now != p[2]:
                self.luck['changed'].append({'game': self.game_id, 'frame': p[3], 'in': '%08X' % p[2],
                                             'out': '%08X' % now, 'ret': self.reg.r0})
        super()._poll_ret(a, s)

    def _replace_call(self, a, s):
        super()._replace_call(a, s)
        self.pending_rep = None
        if self.cur is not None and self.cur.get('injected') and self.in_battle() and \
                self.mu.read_byte(self.reg.r5 + aivsai.CLIENT_SIDE) & 1:
            at = self._words()
            self.pending_rep = (at, self.mu.read_long(at), self.r.frames)

    def _leave_ai(self, a=None, s=None):
        p = getattr(self, 'pending_rep', None)
        if a == aivsai.REPLACE_RET and p:
            self.pending_rep = None
            self.luck['replace_calls'] += 1
            now = self.mu.read_long(p[0])
            if now != p[1]:
                self.luck['replace_changed'].append({'game': self.game_id, 'frame': p[2], 'in': '%08X' % p[1],
                                                     'out': '%08X' % now})
        super()._leave_ai(a, s)

    # --- the scripted person
    def _step(self, n=1):
        for _ in range(n):
            if self.human_control and not self.driving:
                self.k += 1
                if self.k % TICK >= TICK - 2:
                    self.r.skip_render = False          # the next action looks at the screen
                elif self.k % TICK == 0:
                    self.driving = True
                    try:
                        self.act()
                    finally:
                        self.driving = False
            self._raw_step(1)

    def act(self):
        r, f = self.r, self.r.frames
        if f - self.seen_at['rep'] <= 2:
            # the battle's party order is not always the screen's (seen: a fainted Pokemon's panel where the container
            # had a live one), so each try takes the next panel: the live ones by the container first, then the rest
            hp = [self.mu.read_short(b + 0x1E) for b in self.party(0) or []]
            order = [i for i in range(1, len(hp)) if hp[i]] + [i for i in range(1, len(hp)) if not hp[i]]
            if not order:
                r.hold('A', 4, release=4)
                return
            if f - self.rep_last > 600:          # a new replacement (a try with its touches takes about 120 frames)
                self.rep_try = 0
            self.rep_last = f
            if self.refused:                    # "no energy left": B for the message, then back to the list
                self.refused = False
                r.hold('B', 4, release=12)
                r.touch(*BACK)
                r.step(40)
                return
            self.choices['replace'] += 1
            r.touch(*panel(order[self.rep_try % len(order)]))
            self.rep_try += 1
            r.step(60)                          # the panel's menu takes over 30 frames to take a touch
            r.touch(*SHIFT)
            r.step(30)
        elif f - self.seen_at['sel'] <= 2:
            hp = [self.mu.read_short(b + 0x1E) for b in self.party(0) or []]
            able = [i for i in range(1, len(hp)) if hp[i]]
            if r.seen(emu.STATES['fight_menu']) and able and self.policy.random() < self.switch_rate:
                self.choices['switch'] += 1
                r.touch(*POKEMON)
                r.step(42)
                r.touch(*panel(self.policy.choice(able)))
                r.step(60)
                r.touch(*SHIFT)
                r.step(30)
            elif r.seen(emu.STATES['fight_menu']):
                self.choices['moves'] += 1
                r.touch(*FIGHT)
                r.step(32)
                r.touch(*self.policy.choice(MOVE_BUTTONS))
                r.step(12)
            else:                                       # the move menu after a refused move, or a message
                self.choices['back'] += 1
                r.hold('B', 4, release=4)
        else:
            r.hold('A', 4, release=4)

    def event(self, ev):
        super().event(ev)
        if ev.get('kind') == 'message' and self.refused_text in flat(str(ev.get('text', ''))):
            self.refused = True

    def play(self, game, frame_hook=None):
        self.refused = False
        self.policy = random.Random(game['seed'] * 31 + game['game'])
        self.k, self.rep_try, self.rep_last = 0, 0, -10 ** 9
        self.seen_at = {'sel': -10 ** 9, 'rep': -10 ** 9}
        return super().play(game, frame_hook)


def summarize(meta, counts, rows):
    out = dict(meta, decisions=counts['decisions'], trusted=counts['trusted'])
    if meta['human']:
        luck = counts['luck']
        out.update(untrusted=counts['untrusted'], choices=counts['choices'], luck=dict(
            luck, changed=len(luck['changed']), changed_list=luck['changed'][:20],
            replace_changed=len(luck['replace_changed']), replace_changed_list=luck['replace_changed'][:20]))
    for part in ('mine', 'foe'):
        r = [x for x in rows if x['part'] == part]
        out[part] = {'known': len(r), 'right': sum(x['ok'] for x in r), 'ko_after_chip': sum(x['ko'] for x in r),
                     'by_first': {str(f): [sum(x['ok'] for x in r if x['first'] == f),
                                           sum(1 for x in r if x['first'] == f)] for f in (0, 1)}}
    tags = {}
    for x in rows:
        if x.get('status_move'):
            continue                    # a status move's own part (it deals 0) checks nothing
        for tg in x.get('tags', ['base']):
            n = tags.setdefault(tg, [0, 0])
            n[0] += x['ok'] or x['ko']
            n[1] += 1
    out['by_class'] = {k: {'exact_or_ko': v[0], 'known': v[1]} for k, v in sorted(tags.items())}
    out['wrong'] = [x for x in rows if not x['ok']]
    return out


def added(a, b):
    """Two runs' counts together: numbers summed, lists joined, dicts merged key by key."""
    if isinstance(a, dict):
        return {k: added(a[k], b[k]) if k in a and k in b else a.get(k, b.get(k)) for k in a.keys() | b.keys()}
    return a + b


def play(a, log_dir):
    """This process's games, on one emulator: (counts, rows, results)."""
    if a.teams:                         # set games (tools/fs_teams.py) in place of the drawn trainer teams
        games = [dict(g, rng=a.rng) for g in json.load(open(a.teams))][a.first:a.first + a.games]
    else:
        scen = aivsai.draw_scenarios((a.first + a.games + 1) // 2 + 1, 'trainers', a.level, a.seed, rom=a.rom)
        games = [dict(g, rng=a.rng) for g in aivsai.games_of(scen, True)][a.first:a.first + a.games]
    rom, state, save = aivsai.prepare(os.path.abspath(a.rom), False, a.tag)
    rows = []
    duel = (HumanCheck if a.human else Check)(rom, state, rows)
    duel.switch_rate = a.switch
    duel.live = duel.event
    results = []
    for g in games:
        duel.game_id = '%s/%d' % (g['scenario'], g['game'])
        res = aivsai.logged_play(duel, g, os.path.join(log_dir, '%s_%s.log' % (a.tag, aivsai.log_name(g)[:-4])))
        results.append(dict({x: res.get(x) for x in ('end', 'turns', 'winner', 'freezes', 'fallbacks')},
                            game=duel.game_id))
        print('game', g['scenario'], g['game'], results[-1], flush=True)
    for p in (rom, os.path.join(aibench.DSV_DIR, '%s.dsv' % a.tag)):
        if os.path.lexists(p):
            os.remove(p)
    counts = {'decisions': duel.decisions, 'trusted': duel.trusted, 'untrusted': duel.untrusted,
              'choices': getattr(duel, 'choices', {}), 'luck': getattr(duel, 'luck', {})}
    return counts, rows, results


def play_workers(a, log_dir):
    """--workers W: the games split by --first over W processes of this tool (each its own tag, emulator and log)."""
    import subprocess
    per, procs = -(-a.games // a.workers), []
    for k in range(a.workers):
        n = min(per, a.games - k * per)
        if n <= 0:
            break
        tag = '%s_w%d' % (a.tag, k)
        out = os.path.join(log_dir, tag + '.json')
        if os.path.exists(out):
            os.remove(out)
        cmd = [sys.executable, os.path.abspath(__file__), '--rom', a.rom, '--games', str(n), '--first', str(a.first + k * per),
               '--seed', str(a.seed), '--level', str(a.level), '--rng', a.rng, '--tag', tag, '--raw', out]
        cmd += ['--human', '--switch', str(a.switch)] if a.human else []
        cmd += ['--teams', a.teams] if a.teams else []
        log = open(os.path.join(log_dir, tag + '.out'), 'w')
        procs.append((subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), out))
    total = None
    for p, out in procs:
        p.wait()
        if p.returncode or not os.path.exists(out):
            sys.exit('a worker failed: see %s' % (out[:-5] + '.out'))
        part = json.load(open(out))
        total = part if total is None else [added(x, y) for x, y in zip(total, part)]
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', required=True, help='an AI build')
    ap.add_argument('--payload', help="the AI build's payload.json (default: ADVAI_PAYLOAD)")
    ap.add_argument('--games', type=int, default=4)
    ap.add_argument('--first', type=int, default=0)
    ap.add_argument('--seed', type=int, default=2961)
    ap.add_argument('--level', type=int, default=100)
    ap.add_argument('--rng', choices=aivsai.RNG_MODES, default='synced')
    ap.add_argument('--human', action='store_true')
    ap.add_argument('--switch', type=float, default=0.0)
    ap.add_argument('--workers', type=int, default=1, help='emulator processes (lib/emupool.py caps the machine)')
    ap.add_argument('--tag', help='the work files\' name (default fscheck_<ROM name>)')
    ap.add_argument('--teams', help='a JSON list of games (as the Spanish tools/fs_teams.py wrote) to play instead of '
                    'drawn trainer teams')
    ap.add_argument('--raw', help=argparse.SUPPRESS)       # a worker's counts, rows and results, for play_workers
    ap.add_argument('-o', dest='out')
    a = ap.parse_args()
    a.tag = a.tag or 'fscheck_' + os.path.splitext(os.path.basename(a.rom))[0]
    payload.path_from(a.payload)            # exported for the workers
    if a.human:
        a.rng = 'legacy'                 # no harness word: the AI reads the live battle word
    log_dir = os.path.join(tbpaths.RUNS, 'fscheck')
    os.makedirs(log_dir, exist_ok=True)
    counts, rows, results = play_workers(a, log_dir) if a.workers > 1 else play(a, log_dir)
    if a.raw:
        json.dump([counts, rows, results], open(a.raw, 'w'))
        return
    summary = summarize({'games': len(results), 'rng': a.rng, 'human': a.human}, counts, rows)
    print(json.dumps(summary, indent=1))
    if a.out:
        json.dump({'summary': summary, 'rows': rows, 'results': results}, open(a.out, 'w'), indent=1)
    bad = [x for x in rows if not x['ok'] and not x['ko']]
    luck = summary.get('luck') or {}
    harness = a.human and (luck.get('changed') or luck.get('replace_changed') or luck.get('fs_magic') or luck.get('noread'))
    # the advanced AI's fallbacks (src/advai.c FB_*; 6 with no usable option is by design): a run where it fell back
    # checks nothing and would pass
    fallbacks = {}
    for r in results:
        for code, n in ((r.get('fallbacks') or {}).get('advanced') or {}).items():
            fallbacks[code] = fallbacks.get(code, 0) + n
    loud = {c: n for c, n in fallbacks.items() if c not in ('0', '6')}
    problems = ['%d of %d known parts wrong' % (len(bad), len(rows))] if bad else []
    if harness:
        problems.append('the AI changed the luck or saw a harness word')
    if not summary['decisions']:
        problems.append('no decision of the advanced AI was seen: nothing was checked')
    if loud:
        problems.append('the advanced AI fell back: %s (code: decisions)' % loud)
    print('fscheck: %d decisions, %d trusted, %d known parts, fallbacks %s: %s' % (
        summary['decisions'], summary['trusted'], len(rows), fallbacks or 'none', '; '.join(problems) or 'PASS'))
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
