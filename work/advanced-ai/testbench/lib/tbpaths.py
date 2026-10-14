"""Where the test bench, its run output and its inputs live, and the one import convention of the test bench.

Every test bench script starts with these two lines, then imports any test bench module by its bare name
(`import emu`, `import aibench`, `import aiteams`, `import aicalc`), wherever it lives:

    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
    import tbpaths  # noqa: E402,F401  (puts every test bench directory on sys.path)

A script one level deeper (e.g. bench/tests/) adds one more os.path.dirname. Module names are therefore unique across
the test bench directories. Nothing here touches the emulator, so importing it is cheap.

Paths (all ignored by git except the test bench itself):
  WORK      the repository's work/ folder
  ADV       work/advanced-ai
  TESTBENCH work/advanced-ai/testbench
  BUILD     work/build/advanced-ai (ROMs, payloads, saves, run output)
  RUNS      work/build/advanced-ai/runs (every tool's work files and reports; ADVAI_RUNS overrides it)
  SAVES     work/build/advanced-ai/saves (the pre-battle battery saves, made by lib/saves.py)
"""
import os
import sys

LIB = os.path.dirname(os.path.abspath(__file__))
TESTBENCH = os.path.dirname(LIB)
ADV = os.path.dirname(TESTBENCH)
WORK = os.path.dirname(ADV)
REPO = os.path.dirname(WORK)
BUILD = os.path.join(WORK, 'build', 'advanced-ai')
RUNS = os.environ.get('ADVAI_RUNS') or os.path.join(BUILD, 'runs')
SAVES = os.path.join(BUILD, 'saves')
PYTHON = sys.executable

# every directory whose modules other directories import (testbench-b owns checks/, fuzz/, sim/, hostai/, dev/)
TOOL_DIRS = ('lib', 'bench', os.path.join('bench', 'tests'), 'props', 'versus', 'checks', 'fuzz', 'sim', 'hostai', 'dev')
for _d in reversed(TOOL_DIRS):
    _p = os.path.join(TESTBENCH, _d)
    if _p not in sys.path:
        sys.path.insert(1 if sys.path and sys.path[0] == LIB else 0, _p)


def run_dir(*parts):
    """A directory under RUNS, created on first use."""
    path = os.path.join(RUNS, *parts)
    os.makedirs(path, exist_ok=True)
    return path


def rel(path):
    """`path` relative to the repository root, for messages and reports."""
    try:
        return os.path.relpath(path, REPO)
    except ValueError:
        return path
