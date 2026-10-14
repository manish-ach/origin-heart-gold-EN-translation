"""Seed bookkeeping of the AI-vs-AI games: the round seeds, the held-out seeds and the tuning ledger.

Taken from the Spanish workspace's tools/aitune.py (dc8577c) into lib/ because three tools use it: dev/aitune.py,
versus/score_round.py and versus/aiplay.py (which never draws a held-out seed). The files live under the run output
(RUNS/aivsai/holdout/seeds.json, RUNS/aivsai/tune/ledger.jsonl) instead of the Spanish qa/aivsai/.

One change: holdout_seeds() of a missing file is the empty set (no round has been held out on this project yet); a
file that exists but holds no seed still raises, as the Spanish one did, so a format change never draws a held-out seed.
"""
import datetime
import json
import os
import random
import sys
import threading

import tbpaths

TUNE_DIR = os.path.join(tbpaths.RUNS, 'aivsai', 'tune')
HOLDOUT = os.path.join(tbpaths.RUNS, 'aivsai', 'holdout', 'seeds.json')
ROUND_SEEDS = (101, 202, 303, 404, 505)          # the Spanish rounds' training seeds (its qa/aivsai/LOOP.md)


def holdout_seeds(path=HOLDOUT):
    """Every integer in the held-out file, in any round and under any key: a superset of the held-out seeds. A missing
    file holds none; an unreadable one raises, so no seed is drawn without the check."""
    if not os.path.exists(path):
        return set()
    with open(path) as f:
        data = json.load(f)
    out = set()

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, int):
            out.add(x)
        elif isinstance(x, dict):
            for y in x.values():
                walk(y)
        elif isinstance(x, list):
            for y in x:
                walk(y)
    walk(data)
    if not out:
        raise ValueError('%s holds no seed: its format changed, refusing to draw' % path)
    return out


def refusal(seed, held, used):
    """Why a seed may not be used for tuning, or None."""
    if seed in held:
        return 'held out (%s)' % tbpaths.rel(HOLDOUT)
    if seed in ROUND_SEEDS:
        return 'a round seed'
    if seed in used:
        return 'already in the ledger'
    return None


def fresh_seed(held, used, rng=None, tries=1000):
    rng = rng or random.SystemRandom()
    for _ in range(tries):
        seed = rng.randrange(1 << 31)
        if refusal(seed, held, used) is None:
            return seed
    raise RuntimeError('no allowed seed in %d draws' % tries)


class Ledger:
    """RUNS/aivsai/tune/ledger.jsonl: one JSON record per line, appended and never rewritten. Kinds: 'plan' (a
    pass's identity), 'block' (a block's seed and vectors, written before its first game), 'game' (each game as it
    finishes; the newest record of a game wins), 'seed' (a reserved seed), 'result'."""

    def __init__(self, path):
        self.path, self.lock, self.records, self.cut = path, threading.Lock(), [], False
        if not os.path.exists(path):
            return
        with open(path, 'rb') as f:
            raw = f.read()
        self.cut = bool(raw) and not raw.endswith(b'\n')       # a write cut short: the next append starts a new line
        for n, line in enumerate(raw.decode('utf-8', 'replace').splitlines(), 1):
            if not line.strip():
                continue
            try:
                self.records.append(json.loads(line))
            except ValueError:
                print('ledger %s line %d is not JSON (a write cut short?): skipped' % (path, n), file=sys.stderr)

    def append(self, rec):
        rec = dict(rec, time=datetime.datetime.now().isoformat(timespec='seconds'))
        with self.lock:
            os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
            with open(self.path, 'a') as f:
                f.write(('\n' if self.cut else '') + json.dumps(rec, sort_keys=True) + '\n')
                f.flush()
                os.fsync(f.fileno())
            self.cut = False
            self.records.append(rec)
        return rec

    def seeds(self):
        return {r['seed'] for r in self.records if r.get('kind') in ('block', 'seed') and isinstance(r.get('seed'), int)}

    def plan(self, name):
        return next((r for r in reversed(self.records) if r.get('kind') == 'plan' and r.get('name') == name), None)

    def blocks(self, name):
        return {r['block']: r for r in self.records if r.get('kind') == 'block' and r.get('name') == name}

    def games(self, name):
        out = {}
        for r in self.records:
            if r.get('kind') == 'game' and r.get('name') == name:
                out[(r['block'], r['scenario'], r['game'])] = r
        return out
