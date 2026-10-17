"""Run parity scenarios (3 emulators at a time) and compare them with the calc.
Usage: .venv/bin/python work/tools/damage_parity/run_all.py RUN_NAME [spec ...]   (default: every spec)
Output: work/build/parity/RUN_NAME/<spec>/ plus summary.json; then mkfix.py rebuilds the test fixtures."""
import os, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
run = sys.argv[1]
specs = sys.argv[2:] or sorted(f[:-5] for f in os.listdir(os.path.join(HERE, 'specs')) if f.endswith('.json'))
base = os.path.join(ROOT, 'work', 'build', 'parity', run)
os.makedirs(base, exist_ok=True)
env = dict(os.environ, SDL_AUDIODRIVER='dummy')


def one(spec):
    with open(os.path.join(base, spec + '.out.txt'), 'w') as log:
        subprocess.run([sys.executable, os.path.join(HERE, 'scen.py'), os.path.join(HERE, 'specs', spec + '.json'),
                        os.path.join(base, spec)], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    return spec


with ThreadPoolExecutor(3) as pool:
    for spec in pool.map(one, specs):
        print('ran', spec, flush=True)
subprocess.run([sys.executable, os.path.join(HERE, 'summarize.py'), base], check=True)
