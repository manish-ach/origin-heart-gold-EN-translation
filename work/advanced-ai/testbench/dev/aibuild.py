"""Fast advanced-AI build for development: compile the AI and install it into a copy of an English ROM, in seconds.

  .venv/bin/python work/advanced-ai/testbench/dev/aibuild.py --out ROM [--input ROM] [--layout en] [--src DIR]
                                                             [--payload-dir DIR] [--marks JSON]

The Spanish workspace's tools/aibuild.py (dc8577c) rebuilt overlay 10 of a full Spanish build, so a change to the AI
did not wait for its build.py's minutes. Here the builder and the installer are already that fast path, and this
tool only chains them (it calls them, it copies none of their code):
1. builder/build.py's build() compiles src/ (or --src, a copy of the AI sources to try a change on) for --layout into
   --payload-dir (default RUNS/aibuild/<out name>/payload);
2. builder/install.py's install() writes that payload into a copy of --input (default the English rc8 release,
   work/build/advanced-ai/base/rc8_release.nds: an English build with difficulty and without the AI), runs
   builder/verify.py on it, and writes --out and its receipt.
It prints the room line (each region's used and free bytes) and the two paths every test bench tool then takes:
--rom OUT --payload <payload-dir>/payload.json. Give each ROM its own file name: the bench and aibatch tag their
work files and results by it. The installer refuses an input that already has the AI; start from the pre-AI ROM.

--src works by pointing the builder's SRC at the directory for this run (builder/build.py has no --src flag); the
payload's source hashes then name the files of --src.
"""
import argparse
import importlib.util
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402

BUILDER = os.path.join(tbpaths.ADV, 'builder')
DEFAULT_INPUT = os.path.join(tbpaths.BUILD, 'base', 'rc8_release.nds')


def builder_module(name):
    """builder/<name>.py as a module, with builder/ on the path (install.py imports verify.py by name)."""
    if BUILDER not in sys.path:
        sys.path.insert(0, BUILDER)
    spec = importlib.util.spec_from_file_location('advai_builder_' + name, os.path.join(BUILDER, name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', required=True, help='the AI build to write (a new file)')
    ap.add_argument('--input', default=DEFAULT_INPUT, help='an English ROM with difficulty and without the AI')
    ap.add_argument('--layout', default='en', help="a layout in builder/layouts/ (the installer takes 'en')")
    ap.add_argument('--src', help='a copy of the AI sources (src/ by default)')
    ap.add_argument('--payload-dir', help='where the payload goes (default RUNS/aibuild/<out name>/payload)')
    ap.add_argument('--marks', help='trainer marks (default data/trainer_marks.json)')
    a = ap.parse_args()
    t0 = time.time()
    out = os.path.abspath(a.out)
    if os.path.abspath(a.input) == out:
        sys.exit('--out must not be --input: write a ROM of your own')
    pdir = os.path.abspath(a.payload_dir or tbpaths.run_dir('aibuild', os.path.splitext(os.path.basename(out))[0],
                                                              'payload'))
    build = builder_module('build')
    if a.src:
        from pathlib import Path
        build.SRC = Path(a.src).resolve()
    try:
        _, room = build.build(a.layout, pdir)
    except build.BuildError as e:
        sys.exit('build.py: %s' % e)
    print(build.room_line(room))
    install = builder_module('install')
    kw = {'marks_path': a.marks} if a.marks else {}
    try:
        receipt = install.install(a.input, out, pdir, **kw)
    except install.Refused as e:
        sys.exit('install.py: refused: %s' % e)
    print('wrote %s (sha256 %s), verify %s checks; %.1f s' % (tbpaths.rel(out), receipt['output']['sha256'][:16],
                                                             receipt['verify'].get('checked'), time.time() - t0))
    print('test bench: --rom %s --payload %s' % (tbpaths.rel(out), tbpaths.rel(os.path.join(pdir, 'payload.json'))))


if __name__ == '__main__':
    main()
