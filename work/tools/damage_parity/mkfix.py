"""Write site/tests/damage-calc-parity.fixtures.json from a summarized run (real hits only, one per line).
Usage: mkfix.py work/build/parity/RUN [OUT]"""
import json, os, sys
D = sys.argv[1]
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "site", "tests", "damage-calc-parity.fixtures.json")
fx = []; seen = set()
for s in sorted(os.listdir(D)):
    p = f'{D}/{s}/{s}.final.cmp.json'
    if not os.path.exists(p):
        continue
    for c in json.load(open(p)):
        if c['obsLr'] != '0x221c441' or c['verdict'] != 'PASS':
            continue
        tag = c['case']
        key = (tag, c['move'], c['roll'], c['crit'], c['obs'])
        if key in seen:
            continue
        seen.add(key)
        def clean(st):
            st = {k: v for k, v in st.items() if v not in (None, '', [], {}) and k not in ('caveats',)}
            st.pop('moveIds', None)
            if 'curHPPercent' in st:
                st['curHPPercent'] = round(st['curHPPercent'], 4)
                if st['curHPPercent'] >= 100: st.pop('curHPPercent')
            return st
        f = dict(case=tag, move=c['move'], moveId=c['moveId'], roll=c['roll'], crit=bool(c['crit']), damage=c['obs'],
                 field={k: v for k, v in c['fieldUsed'].items() if k != 'crit' and v not in ({}, None)},
                 attackerStats=c['obsAtk'][:4], defenderStats=c['obsDef'][:4])
        tr = c.get('trainerRef') or {}
        f['attacker'] = {'trainer': tr['attacker'], 'curHPPercent': round(c['setA'].get('curHPPercent', 100), 4), 'boosts': c['setA'].get('boosts')} if tr.get('attacker') else clean(c['setA'])
        f['defender'] = {'trainer': tr['defender'], 'curHPPercent': round(c['setD'].get('curHPPercent', 100), 4), 'boosts': c['setD'].get('boosts')} if tr.get('defender') else clean(c['setD'])
        for side in ('attacker', 'defender'):
            if 'trainer' in f[side]:
                f[side] = {k: v for k, v in f[side].items() if v not in (None, 100)}
        if c.get('hitIndex'):
            f['hitIndex'] = c['hitIndex']
        fx.append(f)
with open(OUT, 'w') as f:
    f.write('[\n' + ',\n'.join(json.dumps(x, separators=(',', ':'), ensure_ascii=False) for x in fx) + '\n]\n')
print(len(fx), 'fixtures', os.path.getsize(OUT), 'bytes')
