"""Machine-wide simulator pool: every simulator process (sim/'s build, a dual build, a batch runner) runs inside one
slot of a shared pool, so overlapping jobs queue instead of oversubscribing the machine. The emulators have their own
pool (lib/emupool.py).

  .venv/bin/python work/advanced-ai/testbench/lib/simpool.py                      # the slots and who holds them
  .venv/bin/python work/advanced-ai/testbench/lib/simpool.py run -- CMD ARG ...   # run CMD in a slot
  .venv/bin/python work/advanced-ai/testbench/lib/simpool.py --selftest           # queueing, both entry points, kills

Ported from the Spanish workspace's tools/simpool.py (dc8577c); only the pool's place and the variable names changed.
From Python: simpool.run(cmd, ...) and simpool.popen(cmd, ...) take subprocess.run's and Popen's arguments; each waits
for a free slot, then starts cmd holding it.

A slot is an exclusive lock (flock) on POOL/slot_K, K below ADVAI_SIM_SLOTS (default 6); POOL is
$TMPDIR/advai_sim_pool, or ADVAI_SIM_POOL. The locked file descriptor is handed to the child and the parent closes its
copy, so the slot is held exactly as long as the simulator process runs: it frees at once when that process exits,
however it exits, and a driver killed while its simulators still run does not free their slots. The pid in a slot file
only labels the holder. ADVAI_SIM_SLOTS=0 turns the pool off. Inside a slot (ADVAI_SIM_SLOT set: a command started by
`run --` or by the helpers), the helpers take no further slot: run() runs its commands one at a time under the
inherited slot, so do not wrap a driver that already uses the helpers: it would lose its parallelism.
"""
import fcntl
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ENV, DEFAULT_SLOTS = 'ADVAI_SIM_SLOTS', 6
HELD_ENV = 'ADVAI_SIM_SLOT'
POLL_SECONDS = 0.2

_nested = threading.Lock()    # serializes run() inside an inherited slot
_warned = set()


def pool_dir():
    return os.environ.get('ADVAI_SIM_POOL') or os.path.join(tempfile.gettempdir(), 'advai_sim_pool')


def size():
    raw = os.environ.get(ENV, '').strip()
    if not raw:
        return DEFAULT_SLOTS
    if not raw.isdigit():
        sys.exit('%s=%r: give a number of simulator slots (0 = no pool)' % (ENV, raw))
    return int(raw)


def slot_path(k, pool=None):
    return os.path.join(pool or pool_dir(), 'slot_%d' % k)


def label_slot(fd, pid, label):
    os.ftruncate(fd, 0)
    os.pwrite(fd, ('%d %s\n' % (pid, label)).encode(), 0)


def try_slot(k, label):
    """The fd of slot k, locked and labelled with this process, or None when another holder has it."""
    fd = os.open(slot_path(k), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    label_slot(fd, os.getpid(), label)
    return fd


def note_once(key, text):
    if key not in _warned:
        _warned.add(key)
        print('simulator pool: ' + text, file=sys.stderr, flush=True)


def acquire(label):
    """(slot, locked fd), waiting while every slot is taken; None with the pool off or inside a held slot. The caller
    owns the fd: the slot is held while any process keeps it open."""
    n = size()
    if n == 0 or os.environ.get(HELD_ENV):
        return None
    os.makedirs(pool_dir(), exist_ok=True)
    waited = None
    while True:
        for k in range(n):
            fd = try_slot(k, label)
            if fd is not None:
                if waited is not None and time.time() - waited >= 5:
                    note_once('got', 'got a slot after waiting %.0f s' % (time.time() - waited))
                return k, fd
        if waited is None:
            waited = time.time()
            note_once('wait', 'all %d slots in use (%s), waiting' % (
                n, ', '.join('pid %d' % h[1] for h in holders(n) if h[3])))
        time.sleep(POLL_SECONDS)


def popen(cmd, label=None, **kw):
    """subprocess.Popen(cmd, **kw) once a slot is free; the child holds the slot until it exits."""
    held = acquire(label or os.path.basename(str(cmd[0])))
    if held is None:
        if os.environ.get(HELD_ENV):
            note_once('nested', 'already inside slot %s: no further slots taken' % os.environ[HELD_ENV])
        return subprocess.Popen(cmd, **kw)
    k, fd = held
    try:
        env = dict(kw.pop('env', None) or os.environ, **{HELD_ENV: str(k)})
        pr = subprocess.Popen(cmd, pass_fds=tuple(kw.pop('pass_fds', ())) + (fd,), env=env, **kw)
        label_slot(fd, pr.pid, '%s (from pid %d)' % (label or ' '.join(os.path.basename(str(c)) for c in cmd[:2]),
                                                     os.getpid()))
        return pr
    finally:
        os.close(fd)


def run(cmd, label=None, check=False, input=None, **kw):
    """subprocess.run(cmd, check=..., input=..., **kw) inside a slot (capture_output, stdout, text... as usual)."""
    if kw.pop('capture_output', False):
        kw['stdout'] = kw['stderr'] = subprocess.PIPE
    if input is not None:
        kw['stdin'] = subprocess.PIPE
    nested = size() and os.environ.get(HELD_ENV)
    if nested:
        _nested.acquire()
    try:
        with popen(cmd, label, **kw) as pr:
            out, err = pr.communicate(input)
    finally:
        if nested:
            _nested.release()
    if check and pr.returncode:
        raise subprocess.CalledProcessError(pr.returncode, cmd, out, err)
    return subprocess.CompletedProcess(cmd, pr.returncode, out, err)


def exec_in_slot(cmd):
    """`simpool.py run -- cmd`: become cmd while holding a slot (the slot is cmd's: it frees when cmd exits)."""
    if not cmd:
        sys.exit('usage: simpool.py run -- CMD [ARG ...]')
    held = acquire(' '.join(os.path.basename(c) for c in cmd[:2]))
    if held is not None:
        k, fd = held
        os.set_inheritable(fd, True)
        os.environ[HELD_ENV] = str(k)
    try:
        os.execvp(cmd[0], cmd)
    except OSError as e:
        sys.exit('simpool.py run: %s: %s' % (cmd[0], e))


def holders(n=None, pool=None):
    """[(slot, pid, label, alive)] for each slot file of the first n (default: all on disk) that names a process.
    Read only: a free slot can still name its last holder, whose pid is then dead."""
    out, pool = [], pool or pool_dir()
    names = sorted(os.listdir(pool)) if os.path.isdir(pool) else []
    for name in names:
        k = int(name[5:]) if name.startswith('slot_') and name[5:].isdigit() else None
        if k is None or (n is not None and k >= n):
            continue
        try:
            pid, _, label = open(slot_path(k, pool)).read().strip().partition(' ')
            pid = int(pid)
        except (OSError, ValueError):
            continue
        out.append((k, pid, label, held(k, pool) and alive(pid)))
    return out


def held(k, pool=None):
    """Is slot k locked right now (probed with a non-blocking lock that is dropped at once)."""
    try:
        fd = os.open(slot_path(k, pool), os.O_RDONLY)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return False
    except BlockingIOError:
        return True
    finally:
        os.close(fd)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def main():
    n = size()
    rows = holders()
    print('simulator pool %s: %d slots (%s), %d held' % (pool_dir(), n, '%s=%d' % (ENV, n) if os.environ.get(ENV)
                                                          else 'default', sum(1 for r in rows if r[3] and r[0] < n)))
    for k, pid, label, live in rows:
        print('  slot %d: pid %d %s%s' % (k, pid, label, '' if live else '  (free)'))


HOLDER = """
import json, sys, time
start = time.time()
time.sleep(float(sys.argv[2]))
print(json.dumps({'who': sys.argv[1], 'start': start, 'done': time.time()}), flush=True)
"""

HELPER_JOB = """
import concurrent.futures, sys
sys.path.insert(0, %r)
import simpool
cmds = [[sys.executable, '-c', sys.argv[1], '%%s%%d' %% (sys.argv[2], i), sys.argv[3]] for i in range(int(sys.argv[4]))]
with concurrent.futures.ThreadPoolExecutor(len(cmds)) as ex:
    for r in ex.map(lambda c: simpool.run(c, stdout=simpool.subprocess.PIPE, text=True, check=True), cmds):
        print(r.stdout, end='', flush=True)
""" % HERE

ORPHANER = """
import sys, time
sys.path.insert(0, %r)
import simpool
pr = simpool.popen(['sleep', sys.argv[1]])
print(pr.pid, flush=True)
time.sleep(60)
""" % HERE


def peak(runs):
    now = top = 0
    for _, step in sorted([(r['done'], -1) for r in runs] + [(r['start'], 1) for r in runs]):
        now += step
        top = max(top, now)
    return top


def selftest():
    pool = tempfile.mkdtemp(prefix='simpool_')
    env = dict(os.environ, ADVAI_SIM_POOL=pool)
    env.pop(HELD_ENV, None)

    def wrapped(who, seconds, slots):
        return subprocess.Popen([sys.executable, __file__, 'run', '--', sys.executable, '-c', HOLDER, who, str(seconds)],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=dict(env, **{ENV: str(slots)}))

    def wait_held(k):
        t = time.time()
        while not held(k, pool):
            assert time.time() - t < 10, 'slot %d never taken' % k
            time.sleep(0.05)

    t0 = time.time()
    jobs = [wrapped('W%d' % i, 2, 2) for i in range(3)]
    jobs.append(subprocess.Popen([sys.executable, '-c', HELPER_JOB, HOLDER, 'H', '2', '3'], stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, text=True, env=dict(env, **{ENV: '2'})))
    runs = [json.loads(line) for p in jobs for line in p.communicate()[0].splitlines()]
    assert len(runs) == 6 and all(p.returncode == 0 for p in jobs), runs
    top, span = peak(runs), max(r['done'] for r in runs) - t0
    assert top <= 2 and span >= 5.5, (top, span, runs)
    print('two jobs of 3 (simpool.py run, simpool.run in 3 threads) in a 2-slot pool: at most %d at once, '
          'all done in %.1f s (6 x 2 s on 2 slots)' % (top, span))

    victim = wrapped('victim', 60, 1)
    wait_held(0)
    os.kill(victim.pid, signal.SIGKILL)
    victim.wait()
    t = time.time()
    after = json.loads(wrapped('after', 0, 1).communicate()[0])
    assert after['start'] - t < 1.5, after
    print('a holder killed with SIGKILL: the next one started %.2f s later' % (after['start'] - t))

    parent = subprocess.Popen([sys.executable, '-c', ORPHANER, '3'], stdout=subprocess.PIPE, text=True,
                              env=dict(env, **{ENV: '1'}))
    child = int(parent.stdout.readline())
    os.kill(parent.pid, signal.SIGKILL)
    parent.wait()
    assert held(0, pool), 'the slot freed with the driver while its simulator still ran'
    t = time.time()
    after = json.loads(wrapped('after2', 0, 1).communicate()[0])
    assert after['start'] - t > 1.5 and not alive(child), after
    print('a driver killed with SIGKILL while its child ran: the slot stayed held until the child exited (%.1f s)' % (
        after['start'] - t))
    shutil.rmtree(pool)
    print('selftest passed')


if __name__ == '__main__':
    if sys.argv[1:2] == ['run']:
        exec_in_slot(sys.argv[3:] if sys.argv[2:3] == ['--'] else sys.argv[2:])
    elif sys.argv[1:] == ['--selftest']:
        selftest()
    elif sys.argv[1:]:
        sys.exit(__doc__)
    else:
        main()
