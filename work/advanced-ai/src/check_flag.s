@ check_flag, taken from the Spanish translation's tools/asm/hardmode.s (commit dc8577c, lines 18-20, 29-31 and
@ 39-50) with only what it needs: the three engine functions it calls. Hard mode itself is not ported.
@ aiselect.s calls it to read the advanced AI's setting flags.

    .syntax unified
    .cpu arm946e-s
    .thumb

    .thumb_set GetSaveData, 0x02001194
    .thumb_set SaveVarsFlags, 0x0204F858
    .thumb_set CheckFlag, 0x0204F864          @ (vars/flags, flag) -> bool

    .text

    .global check_flag
    .thumb_func
check_flag:                     @ r0 = flag -> r0 = 1 if set (starter.s uses it too)
    push {r4, lr}
    movs r4, r0
    bl GetSaveData
    bl SaveVarsFlags
    movs r1, r4
    bl CheckFlag
    pop {r4, pc}
