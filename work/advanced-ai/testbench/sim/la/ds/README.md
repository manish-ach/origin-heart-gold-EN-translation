# sim/la/ds: the lookahead compiled for the DS (research)

`lathumb.py` compiles the simulator's turn engine and the lookahead (`lapol.c`, `battle.c`, `move.c`, `damage.c`,
`policy.c`, the ROM's `simdata.c`) with the builder's DS flags (`builder/build.py` AI_CFLAGS, minus `-Werror`, plus
`-DSIM_DS`), links them with libgcc, and runs root battles the host dumped (`sim cf la --dump`) in unicorn, counting
Thumb instructions and ideal ARM9E-S cycles the way `hostai/thumbcount.py` does. `ds_entry.c`, `ds_libc.c`, `layout.c`,
`layout.h` and `include/` are its freestanding entry point, C library stand-ins and the layout check.

Ported unchanged from the Spanish workspace's `tools/sim/la/ds/` (commit `dc8577c`) except `lathumb.py`'s paths. It
needs arm-none-eabi-gcc and a Python with `unicorn` (not in the project venv), and the simulator built for `--rom`
(`sim/simbuild.py`).

```
PY=<python with unicorn> work/advanced-ai/testbench/sim/la/ds/lathumb.py DUMP [DUMP ...] [--rom ROM] [--max N] [--sizes]
```
