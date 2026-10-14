"""Research: dump the battle state the AI sees, in a bench battle with known teams, to map the engine's structures.

  .venv/bin/python work/advanced-ai/testbench/dev/bpp_dump.py SCENARIO_ID --rom ROM [--payload P]
                                                              -> RUNS/aibench/dump_<id>.json

Ported from the Spanish workspace's qa/ai_research/bpp_dump.py (dc8577c) into the test bench: its imports
(lib/tbpaths.py), the ROM as an argument (a link, not a copy), the Violet Gym save from lib/saves.py, the payload
(ADVAI_PAYLOAD or --payload) for the bench's addresses."""
import json
import os
import subprocess
import sys
import shutil

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402,F401
import aibench  # noqa: E402
import payload  # noqa: E402
import saves  # noqa: E402
from aidata import Data  # noqa: E402

if len(sys.argv) < 2 or '--rom' not in sys.argv:
    sys.exit(__doc__)
sid = sys.argv[1]
rom_src = sys.argv[sys.argv.index('--rom') + 1]
payload.path_from(sys.argv[sys.argv.index('--payload') + 1] if '--payload' in sys.argv else None)
out = aibench.OUT
os.makedirs(out, exist_ok=True)
rom = os.path.join(out, 'dump.nds')
state = os.path.join(out, 'dump.dst')
if '--child' not in sys.argv:
    aibench.link_rom(rom_src, rom)
    shutil.copy(saves.path('violet_gym'), os.path.join(aibench.DSV_DIR, 'dump.dsv'))
    with open(os.path.join(out, 'template.bin'), 'wb') as f:
        f.write(aibench.template_mon())
    subprocess.run([sys.executable, aibench.__file__, '--make-state', rom, state], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([sys.executable, __file__] + sys.argv[1:] + ['--child'])
    os.remove(rom)
    os.remove(os.path.join(aibench.DSV_DIR, 'dump.dsv'))
    sys.exit(0)

d = Data(rom)
template = open(os.path.join(out, 'template.bin'), 'rb').read()
CUSTOM = {   # distinct values for mapping fields: level 47 vs 53, abilities, items, statuses, HP
    'map1': {'player': [{'species': 'Garchomp', 'level': 53, 'moves': ['Earthquake', 'Dragon Claw', 'Fire Fang', 'Swords Dance'],
                         'ability': 'Rough Skin', 'item': 'Choice Scarf', 'hp': 0.6, 'status': 'brn'}],
             'enemy': [{'species': 'Gengar', 'level': 47, 'moves': ['Shadow Ball', 'Sludge Bomb', 'Thunderbolt', 'Nasty Plot'],
                        'ability': 'Levitate', 'item': 'Leftovers', 'hp': 0.7, 'status': 'par'},
                       {'species': 'Scizor', 'level': 44, 'moves': ['Bullet Punch', 'X-Scissor'], 'ability': 'Technician', 'item': 'Life Orb'},
                       {'species': 'Vaporeon', 'level': 41, 'moves': ['Surf'], 'ability': 'Water Absorb', 'hp': 0.3, 'status': 'tox'}],
             'items': ['Full Restore']},
}
sc = CUSTOM.get(sid) or {s['id']: s for s in aibench.scenarios()}[sid]
mons = {k: [aibench.build_mon(d, template, spec, 99 + i) for i, spec in enumerate(sc[k])] for k in ('player', 'enemy')}
b = aibench.Bench(rom, state)
mu = b.mu
dump = {}


def at_entry(a, s):
    c = b.cur
    if c is None or c.get('slot') != 11 or 'state' in dump:
        return
    st = b.reg.r1
    me = mu.read_long(st + 4)
    main = mu.read_long(aibench.MAIN_PTR)
    dump['state'] = st
    dump['args'] = [b.reg.r0, b.reg.r1, b.reg.r2]
    dump['me'] = me
    dump['me_bytes'] = bytes(mu[me:me + 0x400]).hex()
    dump['main'] = main
    dump['main_bytes'] = bytes(mu[main:main + 0x800]).hex()
    dump['state_bytes'] = bytes(mu[st:st + 0x440]).hex()
    # every word in main that points into RAM, with 0x400 bytes behind it
    ptrs = {}
    for k in range(0, 0x800, 4):
        p = mu.read_long(main + k)
        if 0x02200000 <= p < 0x02400000 and p not in ptrs:
            ptrs[p] = (k, bytes(mu[p:p + 0x300]).hex())
    dump['main_ptrs'] = {'%08X' % p: v for p, v in ptrs.items()}
    with open(os.path.join(out, 'ram_%s.bin' % sid), 'wb') as f:
        f.write(bytes(mu[0x02000000:0x02400000]))


b.mem.register_exec(b.layout.orig_code[0], at_entry)      # overlay 11's entry (the payload's orig_code)
res = b.run(mons, [d.id('item', x) for x in sc.get('items', [])], 1234)
dump['result'] = res
dump['views'] = {k: [aibench.mon_view(d, m) for m in sc[k]] for k in ('player', 'enemy')}
with open(os.path.join(out, 'dump_%s.json' % sid), 'w') as f:
    json.dump(dump, f)
print('dumped', sid, 'decision', res['call'], 'me', hex(dump.get('me', 0)))
