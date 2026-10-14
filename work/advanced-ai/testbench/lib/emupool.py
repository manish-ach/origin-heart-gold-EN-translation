"""Machine-wide emulator pool: every process that starts an emulator (lib/emu.py Runner) first takes one slot of a
shared pool and keeps it until it exits, so overlapping jobs queue instead of oversubscribing the machine.

  .venv/bin/python work/advanced-ai/testbench/lib/emupool.py              # the slots and who holds them
  .venv/bin/python work/advanced-ai/testbench/lib/emupool.py --selftest   # two jobs in a 2-slot pool, a killed holder

Ported from the Spanish workspace's tools/emupool.py (dc8577c). A slot is an exclusive lock (flock) on
POOL/slot<K>.lock, K below ADVAI_EMU_SLOTS. The pool is the one our own harness uses (work/tools/emu_harness.py:
$TMPDIR/emu_harness_slots, same file names), so the test bench and the harness share one machine-wide cap. The default
size is the harness's (EMU_HARNESS_MAX_EMULATORS, default 6); a job with a smaller ADVAI_EMU_SLOTS competes only for the
first slots. The kernel drops a lock when its process exits, however it exits, so a dead holder's slot is free at once:
the pid written into the slot file only says who holds it. ADVAI_EMU_SLOTS=0 turns the pool off (the interactive tools,
aiplay and aivsai --live, set it for themselves: a person watching never waits). ADVAI_EMU_POOL=DIR uses another pool.
"""
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
POOL = os.environ.get('ADVAI_EMU_POOL') or os.path.join(tempfile.gettempdir(), 'emu_harness_slots')
ENV = 'ADVAI_EMU_SLOTS'
DEFAULT_SLOTS = int(os.environ.get('EMU_HARNESS_MAX_EMULATORS', '6'))
POLL_SECONDS = 1.0
SLOT_NAME = re.compile(r'slot(\d+)\.lock$')

_held = None        # (slot, fd) of this process


def size():
    raw = os.environ.get(ENV, '').strip()
    if not raw:
        return DEFAULT_SLOTS
    if not raw.isdigit():
        sys.exit('%s=%r: give a number of emulator slots (0 = no pool)' % (ENV, raw))
    return int(raw)


def slot_path(k, pool=None):
    return os.path.join(pool or POOL, 'slot%d.lock' % k)


def try_slot(k, label):
    """The fd of slot k, locked and labelled with this process, or None when another process holds it."""
    fd = os.open(slot_path(k), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    os.ftruncate(fd, 0)
    os.pwrite(fd, ('%d %s\n' % (os.getpid(), label)).encode(), 0)
    return fd


def acquire(label=None):
    """Hold a slot for the rest of this process (once per process: one emulator per process). Waits while every
    slot is taken. Returns the slot number, or None with the pool off."""
    global _held
    n = size()
    if _held is not None or n == 0:
        return _held and _held[0]
    os.makedirs(POOL, exist_ok=True)
    label = label or ' '.join(os.path.basename(a) for a in sys.argv[:3])
    waited = None
    while True:
        for k in range(n):
            fd = try_slot(k, label)
            if fd is not None:
                _held = (k, fd)
                if waited is not None:
                    print('emulator pool: got slot %d after %.0f s' % (k, time.time() - waited), file=sys.stderr, flush=True)
                return k
        if waited is None:
            waited = time.time()
            print('emulator pool: all %d slots in use (%s), waiting' % (n, ', '.join(
                'pid %s' % h[1] for h in holders(n))), file=sys.stderr, flush=True)
        time.sleep(POLL_SECONDS)


def holders(n=None, pool=None):
    """[(slot, pid, label, alive)] for each slot file of the first n (default: all on disk) that names a process.
    Read only: a free slot can still name its last holder, whose pid is then dead."""
    out, pool = [], pool or POOL
    names = sorted(os.listdir(pool)) if os.path.isdir(pool) else []
    for name in names:
        m = SLOT_NAME.match(name)
        k = int(m.group(1)) if m else None
        if k is None or (n is not None and k >= n):
            continue
        try:
            pid, _, label = open(slot_path(k, pool)).read().strip().partition(' ')
            pid = int(pid)
        except (OSError, ValueError):
            continue
        out.append((k, pid, label, alive(pid)))
    return out


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
    print('emulator pool %s: %d slots (%s), %d held' % (POOL, n, '%s=%d' % (ENV, n) if os.environ.get(ENV) else 'default',
                                                         sum(1 for r in rows if r[3] and r[0] < n)))
    for k, pid, label, live in rows:
        print('  slot %d: pid %d %s%s' % (k, pid, label, '' if live else '  (exited: free)'))


HOLDER = """
import json, os, sys, time
os.environ['ADVAI_EMU_POOL'] = sys.argv[1]
sys.path.insert(0, %r)
import emupool
asked = time.time()
slot = emupool.acquire('selftest ' + sys.argv[2])
got = time.time()
time.sleep(float(sys.argv[3]))
print(json.dumps({'who': sys.argv[2], 'slot': slot, 'asked': asked, 'got': got, 'done': time.time()}))
""" % HERE


def selftest():
    pool = tempfile.mkdtemp(prefix='emupool_')

    def holder(who, seconds, slots):
        return subprocess.Popen([sys.executable, '-c', HOLDER, pool, who, str(seconds)], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, text=True, env=dict(os.environ, **{ENV: str(slots)}))
    jobs = [holder('X%d' % i, 2, 2) for i in range(3)]
    time.sleep(0.3)
    jobs += [holder('Y%d' % i, 2, 2) for i in range(3)]
    runs = [json.loads(p.communicate()[0]) for p in jobs]
    now = peak = 0
    for _, step in sorted([(r['got'], 1) for r in runs] + [(r['done'], -1) for r in runs]):
        now += step
        peak = max(peak, now)
    assert len(runs) == 6 and peak <= 2 and {r['slot'] for r in runs} <= {0, 1}, runs
    print('two jobs of 3 holders in a 2-slot pool: at most %d at once, waits %s' % (
        peak, ', '.join('%s %.1f s' % (r['who'], r['got'] - r['asked']) for r in runs)))
    victim = holder('victim', 60, 1)
    while not any(h[1] == victim.pid for h in holders(pool=pool)):
        time.sleep(0.1)
    os.kill(victim.pid, signal.SIGKILL)
    victim.wait()
    t = time.time()
    after = json.loads(holder('after', 0, 1).communicate()[0])
    assert after['slot'] == 0 and after['got'] - t < 1.5, after
    print('a holder killed with SIGKILL: the next one got its slot %.2f s later' % (after['got'] - t))
    print('selftest passed')


if __name__ == '__main__':
    selftest() if sys.argv[1:] == ['--selftest'] else main()
