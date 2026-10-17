"""Compare every scenario of a run with the calc (trainer runs use trainers.json via fromTrainerMon) and
write <spec>.final.cmp.json and summary.json. Real hits: caller 0x0221C441; other rows are the AI's own damage
estimates (same routine; immune/unmodelled ones are skipped). Usage: summarize.py work/build/parity/RUN"""
import json, sys, os, subprocess
from collections import Counter, defaultdict
D = sys.argv[1]
W = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..'))
specs = sorted(x[:-8] for x in os.listdir(D) if x.endswith('.out.txt'))
tot = Counter(); table = []
for s in specs:
    base = f'{D}/{s}/{s}'
    if not os.path.exists(base + '.records.json'):
        print('MISSING', s); continue
    env = dict(os.environ)
    if s.startswith('trainers'):
        env['TRAINER_REF'] = '1'
    out = subprocess.run(['node', os.path.dirname(os.path.abspath(__file__)) + '/calc_cmp.mjs', base + '.records.json'],
                         cwd=W + '/site', env=env, capture_output=True, text=True).stdout
    cmp = json.loads(out); rec = json.load(open(base + '.records.json'))
    json.dump(cmp, open(base + '.final.cmp.json', 'w'), indent=1)
    per = defaultdict(Counter)
    for c, r in zip(cmp, rec):
        real = r['obs'].get('lr') == '0x221c441'
        kind = 'real' if real else 'ai'
        if not real and (r['obs']['eff'] == 0 or c['verdict'] == 'N/A'):
            kind = 'ai-skip'
        tag = c['case'].split('/', 2)[2]
        per[tag][(kind, c['verdict'])] += 1
        tot[(kind, c['verdict'])] += 1
        if c['verdict'] == 'FAIL' and kind != 'ai-skip':
            print('FAIL', kind, c['case'], c['move'], 'obs', c['obs'], 'exp', c['expected'], 'stats', c['statsOk'])
    for tag, cnt in per.items():
        table.append((s, tag, dict(cnt)))
json.dump([[a, b, {f'{k[0]}:{k[1]}': v for k, v in c.items()}] for a, b, c in table], open(D + '/summary.json', 'w'), indent=1)
print({f'{k[0]}:{k[1]}': v for k, v in tot.items()})
