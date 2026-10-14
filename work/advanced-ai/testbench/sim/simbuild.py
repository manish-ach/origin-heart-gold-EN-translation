"""Where the simulator for a ROM is built, and how to build it: the one place sim/'s drivers ask.

  .venv/bin/python work/advanced-ai/testbench/sim/simbuild.py [--rom ROM] [--layout es|en] [-v]   # make it; prints
                                                                                                # the binary's path

The simulator's data comes from one ROM (gen_simdata.py), so each ROM gets its own build directory,
work/build/advanced-ai/sim/<ROM file name without .nds>[_<layout>] (the Makefile's B). The default ROM is the untouched
Chinese hack, whose battle data the English build keeps unchanged.

The AI compiles as the builder compiles it for a layout: --layout NAME passes the -D switches of
builder/layouts/NAME.json's cflags (en: AI_NO_STEER, steering compiled out) to the Makefile's AI_DEFS. Without a layout
the AI is the Spanish sources' default (steering compiled in, though the simulator never steers unless SIM_STEER_K is
set). hostai/replay.py takes the same --layout through layout_defs().
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib'))
import tbpaths  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROM = os.path.join(tbpaths.WORK, 'rom', 'origin_v4.0.3_cn.nds')
OUT = os.path.join(tbpaths.BUILD, 'sim')
BUILDER = os.path.join(tbpaths.ADV, 'builder')


def layout_defs(layout):
    """The -D switches of a builder layout's cflags (builder/layouts/LAYOUT.json), as the host builds pass them."""
    if not layout:
        return []
    cfg = json.load(open(os.path.join(BUILDER, 'layouts', layout + '.json'), encoding='utf-8'))
    return [f for f in cfg.get('cflags', []) if f.startswith('-D')]


def builder_cflags(layout=None):
    """The builder's own compiler flags for the DS (builder/build.py AI_CFLAGS) plus the layout's cflags."""
    spec = importlib.util.spec_from_file_location('advai_builder', os.path.join(BUILDER, 'build.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    extra = []
    if layout:
        extra = json.load(open(os.path.join(BUILDER, 'layouts', layout + '.json'), encoding='utf-8')).get('cflags', [])
    return list(mod.AI_CFLAGS) + extra


def tag(rom, layout=None):
    """A build directory's name: the ROM's file name without .nds, then _LAYOUT."""
    return os.path.splitext(os.path.basename(rom))[0] + ('_' + layout if layout else '')


def build_dir(rom=DEFAULT_ROM, layout=None):
    """The build directory of the simulator for a ROM: its data, objects and binary."""
    return os.path.join(OUT, tag(rom, layout))


def binary(rom=DEFAULT_ROM, layout=None):
    """The simulator binary for a ROM (not built here)."""
    return os.path.join(build_dir(rom, layout), 'sim')


def build(rom=DEFAULT_ROM, layout=None, quiet=True, target='sim'):
    """Make the simulator for a ROM (its data first when the ROM or the generator changed); the target's path."""
    b = build_dir(rom, layout)
    subprocess.run(['make'] + (['-s'] if quiet else []) + ['-C', HERE, 'ROM=' + os.path.abspath(rom), 'B=' + b,
                                                           'AI_DEFS=' + ' '.join(layout_defs(layout)),
                                                           os.path.join(b, target)], check=True)
    return os.path.join(b, target)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', default=DEFAULT_ROM)
    ap.add_argument('--layout', help="a builder layout whose switches the AI compiles with (en: the English build's)")
    ap.add_argument('--target', default='sim', help='sim (default) or protect_check')
    ap.add_argument('-v', action='store_true', help="print make's commands")
    a = ap.parse_args()
    print(build(a.rom, a.layout, quiet=not a.v, target=a.target))


if __name__ == '__main__':
    main()
