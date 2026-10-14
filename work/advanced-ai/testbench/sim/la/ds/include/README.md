# sim/la/ds/include: freestanding C headers

`stdio.h`, `stdlib.h` and `string.h` stand in for the C library when `lathumb.py` compiles the simulator's turn engine
for the DS (`-ffreestanding -nostdlib`): they declare only what that code calls, which `../ds_libc.c` implements.
Taken unchanged from the Spanish workspace's `tools/sim/la/ds/include/` (commit `dc8577c`).
