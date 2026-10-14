"""The test bench's one entry point: run a tier on an AI build and judge it against the recorded references.

  .venv/bin/python work/advanced-ai/testbench/run.py static|quick|deep --rom ROM --payload PAYLOAD [--workers N]
                   [--only STEP,...] [--list] [--record] [--options-receipt RECEIPT]

static  no emulator: the bench's claim checks against the ROM's data, the ported tools' self-tests, and the unit,
        host-AI, simulator and tuning tests (testbench-b's, when present)
quick   every AI build: the 365 graded bench scenarios, the behaviour checks, a short property-test run
deep    any change to the AI or to the engine code it calls, every release candidate: 80 AI-vs-AI games (seed 101)
        against the reference logs, the full property-test run, foresight, doubles fuzzing, story battles

STEPS below is the one list of what each tier runs. A step whose tool is not in the test bench yet is listed as pending
and skipped with a message (testbench-b owns checks/, fuzz/, sim/, hostai/, dev/; unit/ comes with the builder). The
exit status is 1 when any step that ran failed, else 0; pending and skipped steps (a step's own "nothing to check"
exit code, e.g. sim/bench_check.py's 2 without a bench record) do not fail a tier.

References (testbench/references/<layout>/, the payload's layout: 'en' for our build, 'es' for the Spanish rc44):
  bench.json     the bench score and every scenario's action; quick passes when the score is at or above it, with 0
                 fallbacks, every decision from overlay 10, 0 errors and no more runs with clipped text (bench_record.json: the whole run, which hostai/replay.py
                 and sim/bench_check.py replay)
  aivsai.json    the 80 games' log digests and the win count; deep passes when every log is byte-identical (only
                 compared when the saves are the reference ones: lib/saves.py), else when
                 the advanced AI wins 80-94% of the counted games (the differing games are printed); either way no
                 more fallbacks than the reference
  aiprops.json   the property tests' seeds and sizes; a run passes with no violation other than the reference's
                 'known' ones (each with a reviewer's reason), some checks made, and no more sides the AI did not
                 serve (fallbacks, misread positions) than the reference
Every judged step reports the AI's fallbacks (decisions overlay 11's code made for it) and fails on more than the
reference has, so an AI that silently hands its turns back never passes.
--record writes the references from this run (a new reference needs a reviewer's sign-off: see references/README.md;
it needs the reference test saves). Every tier prints where its saves came from (lib/saves.py describe).
Run output: work/build/advanced-ai/runs/tiers/<tier>_<time>/.
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'lib'))
import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)
import payload  # noqa: E402
import saves  # noqa: E402

PY = sys.executable
REFS = os.path.join(HERE, 'references')
WIN_RANGE = (0.80, 0.94)            # the Spanish 95% range of the advanced AI's wins against the hack's AI
VERSUS = {'scenarios': 40, 'seed': 101}
PROPS = {'quick': {'n': 20, 'seed': 1}, 'deep': {'n': 100, 'seed': 1}}


class Step:
    """One thing a tier runs. kind: 'cmd' (passes on exit 0), 'unittest' (unittest discovery in the tool's folder), or
    'bench' / 'versus' / 'props' (judged against the references). tool: its script (or folder) under the test bench,
    pending when missing; args: a function of the run's context. Every step gets ADVAI_PAYLOAD in its environment."""

    def __init__(self, name, tiers, owner, tool, args=None, kind='cmd', skip_codes=(), when=None):
        self.name, self.tiers, self.owner, self.tool, self.args, self.kind = name, tiers, owner, tool, args, kind
        self.skip_codes = skip_codes        # exit codes that mean "nothing to check here" (a skip, not a failure)
        self.when = when                    # when(c): None to run, else why the step does not apply to this run

    @property
    def path(self):
        return os.path.join(HERE, self.tool)

    def pending(self):
        return not os.path.exists(self.path)


def rom_payload(c):
    return ['--rom', c.rom, '--payload', c.payload]


def workers(c):
    return ['--workers', str(c.workers)]


def needs_options(c):
    """The Options row checks need the difficulty build's receipt of a ROM with the TRAINER AI row."""
    return None if c.options_receipt else 'no --options-receipt (only a difficulty build with the TRAINER AI row has one)'


STEPS = [
    # --- static: no emulator
    Step('unit', ('static',), 'builder', 'unit', kind='unittest'),
    Step('bench-claims', ('static',), 'testbench-a', 'bench/aibench.py', lambda c: ['--check', '--rom', c.rom]),
    Step('selftest-aiprops', ('static',), 'testbench-a', 'props/aiprops.py', lambda c: ['--selftest', '--rom', c.rom]),
    Step('selftest-report', ('static',), 'testbench-a', 'versus/aivsai_report.py', lambda c: ['--selftest']),
    Step('selftest-live', ('static',), 'testbench-a', 'versus/aivsai_live.py', lambda c: ['--selftest']),
    Step('selftest-score', ('static',), 'testbench-a', 'versus/score_round.py', lambda c: ['--selftest']),
    Step('versus-tests', ('static',), 'testbench-a', 'versus', kind='unittest'),    # versus/test_*.py
    Step('lib-tests', ('static',), 'testbench-a', 'lib', kind='unittest'),          # lib/test_*.py (the saves)
    Step('hostai-replay', ('static',), 'testbench-b', 'hostai/replay.py', lambda c: ['--rom', c.rom, '--layout', c.layout],
         skip_codes=(2,)),          # 2: no bench record on this ROM yet (the quick tier makes one)
    Step('sim-bench-check', ('static',), 'testbench-b', 'sim/bench_check.py', lambda c: ['--rom', c.rom, '--layout', c.layout],
         skip_codes=(2,)),
    Step('aitune-tests', ('static',), 'testbench-b', 'dev/aitune.py', lambda c: ['--selftest']),
    # --- quick: every AI build
    Step('bench', ('quick',), 'testbench-a', 'bench/aibench.py', kind='bench'),
    Step('settings', ('quick',), 'testbench-b', 'checks/aimode_check.py', lambda c: rom_payload(c) + workers(c)),
    Step('lead', ('quick',), 'testbench-b', 'checks/lead_check.py', lambda c: rom_payload(c) + workers(c)),
    Step('read', ('quick',), 'testbench-b', 'checks/read_check.py', rom_payload),
    # only the foe's no-PP cases: the other menulock cases test Spanish fixes this project does not have
    Step('menulock', ('quick',), 'testbench-b', 'checks/menulock.py',
         lambda c: rom_payload(c) + ['--advanced', 'foe_pp4', 'foe_pp4_one', 'foe_pp4_bench', 'foe_pp4_double']),
    Step('ai-smoke', ('quick',), 'testbench-b', 'checks/ai_smoke.py',
         lambda c: rom_payload(c) + (['--options', c.options_receipt] if c.options_receipt else [])),
    Step('options-row', ('quick',), 'options', 'checks/options_trainer_ai.py',
         lambda c: ['--rom', c.rom, '--receipt', c.options_receipt], when=needs_options),
    Step('props-short', ('quick',), 'testbench-a', 'props/aiprops.py', kind='props'),
    # --- deep: AI or engine changes, every release candidate
    Step('versus', ('deep',), 'testbench-a', 'versus/aivsai.py', kind='versus'),
    Step('props-full', ('deep',), 'testbench-a', 'props/aiprops.py', kind='props'),
    Step('foresight', ('deep',), 'testbench-b', 'checks/fscheck.py', lambda c: rom_payload(c) + workers(c)),
    Step('story-ai', ('deep',), 'testbench-b', 'checks/storycheck.py', rom_payload),   # INHERITED cases pass (exit 0)
    Step('itcm-arena', ('deep',), 'testbench-b', 'checks/itcm_arena.py', rom_payload),
    Step('fuzz-doubles', ('deep',), 'testbench-b', 'fuzz/aifuzz.py',
         lambda c: rom_payload(c) + workers(c) + ['--double', '--mode', 'advanced']),
]


def run(cmd, log):
    """Run cmd with its output in log; (exit code, output)."""
    t = time.time()
    with open(log, 'w') as f:
        p = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT, cwd=tbpaths.REPO)
    out = open(log, encoding='utf-8', errors='replace').read()
    print('    %s (%.0f s, exit %d, log %s)' % (' '.join(os.path.basename(x) if x.startswith('/') else x for x in cmd[1:4]),
                                              time.time() - t, p.returncode, tbpaths.rel(log)), flush=True)
    return p.returncode, out


def ref_path(c, name):
    return os.path.join(REFS, c.layout, name)


def load_ref(c, name):
    p = ref_path(c, name)
    return json.load(open(p, encoding='utf-8')) if os.path.exists(p) else None


def write_ref(c, name, data):
    p = ref_path(c, name)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    text = json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False)
    text = text.replace(tbpaths.REPO + os.sep, '')        # no machine paths in committed files
    with open(p, 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print('    recorded %s' % tbpaths.rel(p))


def rom_ids(rom):
    h1, h2 = hashlib.sha1(), hashlib.sha256()
    with open(rom, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h1.update(block)
            h2.update(block)
    return {'rom_sha1': h1.hexdigest(), 'rom_sha256': h2.hexdigest()}


# --- judged steps
def bench_numbers(results):
    """The judged numbers of a bench run's results."""
    import aibench
    scores = aibench.scores(results)
    adv = [x for x in results if x.get('slot') == aibench.AI_OVERLAY]
    failed = lambda x: [f for f in x.get('failures') or [] if not f.startswith('clipped')]  # noqa: E731
    return {'scenarios': len(scores), 'score': round(100 * sum(v[0] for v in scores.values()) / max(1, len(scores)), 2),
            'fallbacks': sum(1 for x in adv if (x.get('adv') or {}).get('fallback')),
            'not_overlay10': len(results) - len(adv),
            'errors': sum(1 for x in results if x.get('grade') == 'error' or failed(x)),
            # text drawn past its window's declared size (inside its buffer): the English ability pop-ups do it with
            # the AI on or off, so it is held to the reference, not to 0
            'clipped': sum(1 for x in results if any(f.startswith('clipped') for f in x.get('failures') or [])),
            'actions': {x['id']: x['action'] for x in results}}


def bench_step(c, step):
    import aibench
    name = 'tier_%s_%s' % (c.layout, c.stamp)
    code, _ = run([PY, step.path, '--rom', c.rom, '--payload', c.payload, '--advanced', '--repeats', '1',
                   '--workers', str(c.workers), '--save', name], os.path.join(c.out, 'bench.log'))
    saved = os.path.join(aibench.BASELINES, name + '.json')
    if code or not os.path.exists(saved):
        return False, 'aibench failed (exit %d)' % code
    got = bench_numbers(json.load(open(saved))['results'])
    bad = got['fallbacks'] or got['not_overlay10'] or got['errors']
    text = 'score %.1f%% on %d scenarios, %d fallbacks, %d decisions not from overlay 10, %d errors, %d runs with ' \
        'clipped text' % tuple(got[k] for k in ('score', 'scenarios', 'fallbacks', 'not_overlay10', 'errors', 'clipped'))
    if c.record:
        write_ref(c, 'bench.json', dict(got, **rom_ids(c.rom), recorded=c.stamp))
        write_ref(c, 'bench_record.json', json.load(open(saved)))    # the full record (hostai/, sim/ replay it)
        return not bad, text + ' (recorded)'
    ref = load_ref(c, 'bench.json')
    if ref is None:
        return False, text + '; no reference (references/%s/bench.json): run with --record after review' % c.layout
    changed = sorted(k for k, v in got['actions'].items() if ref['actions'].get(k) != v)
    ok = got['score'] + 1e-9 >= ref['score'] and not bad and got['clipped'] <= ref.get('clipped', 0)
    return ok, text + '; reference %.1f%%, %d clipped; %d scenarios changed their action%s' % (
        ref['score'], ref.get('clipped', 0), len(changed), (': ' + ', '.join(changed[:12])) if changed else '')


def props_step(c, step):
    size = PROPS[c.tier]
    ref = load_ref(c, 'aiprops.json') or {}
    seed, n = ref.get(c.tier, size)['seed'], ref.get(c.tier, size)['n']
    code, out = run([PY, step.path, '--rom', c.rom, '--payload', c.payload, '--n', str(n), '--seed', str(seed),
                     '--workers', str(c.workers)], os.path.join(c.out, 'aiprops_%s.log' % c.tier))
    line = next((x for x in out.splitlines() if x.startswith('results: ')), None)
    if code or not line:
        return False, 'aiprops failed (exit %d)' % code
    saved = json.load(open(os.path.join(tbpaths.REPO, line.split(': ', 1)[1].strip())))
    found = sorted('%s %s %s' % (v['invariant'], v['pos'], v['run'])
                   for f in saved['invariants'].values() for v in f['violations'])
    checked = sum(f['checked'] for f in saved['invariants'].values())
    # sides the AI should have decided but did not (a fallback to overlay 11's code, a misread position, no battle)
    unserved = sum(len(v) for k, v in saved['skipped'].items() if k.startswith(('fallback', 'snapshot', 'no ', 'not ')))
    tier_ref = ref.get(c.tier, {})
    allowed, known = tier_ref.get('unserved', 0), tier_ref.get('known', {})
    new = [v for v in found if v not in known]
    text = 'seed %d, %d positions: %d checks, %d violations%s, %d sides the AI did not serve (%s)' % (
        seed, n, checked, len(found), (' (%s)' % ', '.join(found)) if found else '', unserved,
        ', '.join('%s %d' % (k, len(v)) for k, v in sorted(saved['skipped'].items())) or 'none')
    if c.record:
        # a violation becomes 'known' only when a reviewer writes why next to it (references/README.md)
        ref[c.tier] = dict(tier_ref, seed=seed, n=n, checked=checked, violations=len(found), unserved=unserved,
                           known={v: known[v] for v in found if v in known}, **rom_ids(c.rom))
        write_ref(c, 'aiprops.json', ref)
        return not new and checked > 0, text + ' (recorded)'
    ok = not new and checked > 0 and unserved <= allowed
    return ok, text + '; reference allows %d unserved%s' % (
        allowed, '; known: %s' % ', '.join(v for v in found if v in known) if len(new) < len(found) else '')


def log_digests(log_dir):
    out = {}
    for p in sorted(glob.glob(os.path.join(log_dir, '*.log'))):
        with open(p, 'rb') as f:
            out[os.path.basename(p)] = hashlib.sha256(f.read()).hexdigest()
    return out


def versus_step(c, step):
    log_dir = os.path.join(c.out, 'aivsai_logs')
    code, out = run([PY, step.path, str(VERSUS['scenarios']), '--seed', str(VERSUS['seed']), '--rom', c.rom,
                     '--payload', c.payload, '--workers', str(c.workers), '--log-dir', log_dir],
                    os.path.join(c.out, 'aivsai.log'))
    report = next((x.split(': ', 1)[1].strip() for x in out.splitlines() if x.startswith('Report: ')), None)
    if code or not report:
        return False, 'aivsai failed (exit %d)' % code
    s = json.load(open(os.path.splitext(report)[0] + '.json'))['summary']
    wins, counted = s['wins'], s['counted']
    fallbacks = sum(v for k, v in s['fallbacks'].items() if k != '0')     # decisions overlay 11's code made for the AI
    digests = log_digests(log_dir)
    review = s['failures']['review']
    clipped = sum(1 for x in review['items'] if x['failure'].startswith('clipped'))
    text = 'advanced AI won %d of %d counted games (%d played); %d fallbacks of %d decisions %s; %d failures to ' \
        'review (%d of them clipped text) in %d games' % (wins, counted, s['games'], fallbacks, sum(s['fallbacks'].values()),
                                                         s['fallbacks'], review['count'], clipped, len(review['battles']))
    if c.record:
        write_ref(c, 'aivsai.json', {'command': 'aivsai %d --seed %d' % (VERSUS['scenarios'], VERSUS['seed']),
                                     'wins': wins, 'counted': counted, 'games': s['games'], 'fallbacks': fallbacks,
                                     'logs': digests, **rom_ids(c.rom), 'recorded': c.stamp})
        return counted > 0, text + ' (recorded)'
    ref = load_ref(c, 'aivsai.json')
    if ref is None:
        return False, text + '; no reference (references/%s/aivsai.json): run with --record after review' % c.layout
    if fallbacks > ref.get('fallbacks', 0):
        return False, text + '; more fallbacks than the reference (%d)' % ref.get('fallbacks', 0)
    rate = wins / counted if counted else 0
    ok = WIN_RANGE[0] <= rate <= WIN_RANGE[1]
    if not c.saves_reference:       # the logs were recorded from the reference saves: only the win range can judge
        return ok, text + ' (%.1f%%, range %d-%d%%); logs not compared: the saves are not the reference ones' % (
            100 * rate, 100 * WIN_RANGE[0], 100 * WIN_RANGE[1])
    differ = sorted(k for k in set(ref['logs']) | set(digests) if ref['logs'].get(k) != digests.get(k))
    if not differ:
        return True, text + '; all %d logs byte-identical to the reference' % len(digests)
    return ok, text + ' (%.1f%%, range %d-%d%%); %d logs differ from the reference: %s' % (
        100 * rate, 100 * WIN_RANGE[0], 100 * WIN_RANGE[1], len(differ), ', '.join(differ))


JUDGES = {'bench': bench_step, 'props': props_step, 'versus': versus_step}


def main():
    ap = argparse.ArgumentParser(description='Run a test bench tier on an AI build.')
    ap.add_argument('tier', choices=('static', 'quick', 'deep'))
    ap.add_argument('--rom', required=True)
    ap.add_argument('--payload', required=True)
    ap.add_argument('--workers', type=int, default=3)
    ap.add_argument('--only', help='run only these steps (comma list; see --list)')
    ap.add_argument('--list', action='store_true', help='print the tier\'s steps and whether each is pending')
    ap.add_argument('--record', action='store_true', help='write the references from this run (after review)')
    ap.add_argument('--options-receipt', help='a difficulty build with the TRAINER AI row: its difficulty receipt (runs '
                    'the Options row check, and ai_smoke sets the AI through the row)')
    c = ap.parse_args()
    c.rom, c.payload = os.path.abspath(c.rom), payload.path_from(c.payload)
    c.layout = payload.load().name
    steps = [s for s in STEPS if c.tier in s.tiers and (not c.only or s.name in c.only.split(','))]
    if c.list:
        for s in steps:
            print('%-18s %-12s %-28s %s' % (s.name, s.owner, s.tool, 'PENDING' if s.pending() else 'ready'))
        return 0
    c.stamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    c.saves_reference, saves_line = saves.reference(), saves.describe()
    if c.record and not c.saves_reference:
        ap.error('--record needs the reference saves (%s)' % saves_line)
    c.out = tbpaths.run_dir('tiers', '%s_%s_%s' % (c.tier, c.layout, c.stamp))
    print('%s tier on %s (payload %s, layout %s), %d workers; output %s' % (
        c.tier, tbpaths.rel(c.rom), tbpaths.rel(c.payload), c.layout, c.workers, tbpaths.rel(c.out)), flush=True)
    print(saves_line, flush=True)
    rows, t0 = [], time.time()
    for s in steps:
        print('- %s' % s.name, flush=True)
        if s.pending():
            rows.append((s.name, 'PENDING', '%s is not in the test bench yet (owner %s): skipped' % (s.tool, s.owner)))
            print('    ' + rows[-1][2], flush=True)
            continue
        why = s.when(c) if s.when else None
        if why:
            rows.append((s.name, 'SKIP', 'not applicable: %s' % why))
            print('    ' + rows[-1][2], flush=True)
            continue
        t = time.time()
        if s.kind in JUDGES:
            ok, text = JUDGES[s.kind](c, s)
        else:
            cmd = [PY, '-m', 'unittest', 'discover', '-s', s.path] if s.kind == 'unittest' else [PY, s.path] + s.args(c)
            code, _ = run(cmd, os.path.join(c.out, s.name + '.log'))
            ok, text = (None if code in s.skip_codes else code == 0), 'exit %d' % code
        rows.append((s.name, {True: 'pass', False: 'FAIL', None: 'SKIP'}[ok], '%s (%.0f s)' % (text, time.time() - t)))
        print('    %s: %s' % (rows[-1][1], rows[-1][2]), flush=True)
    summary = ['%s tier: %s' % (c.tier, tbpaths.rel(c.rom))] + ['  %-18s %-7s %s' % r for r in rows] + ['  ' + saves_line]
    failed = [r for r in rows if r[1] == 'FAIL']
    summary.append('%d passed, %d failed, %d skipped, %d pending in %.0f s' % (
        sum(r[1] == 'pass' for r in rows), len(failed), sum(r[1] == 'SKIP' for r in rows),
        sum(r[1] == 'PENDING' for r in rows), time.time() - t0))
    text = '\n'.join(summary)
    with open(os.path.join(c.out, 'summary.txt'), 'w', encoding='utf-8') as f:
        f.write(text + '\n')
    print('\n' + text)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
