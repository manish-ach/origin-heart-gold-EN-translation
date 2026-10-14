@ Advanced trainer AI selection: the Pokemon Center NPC's third question has three settings, kept in two script
@ flags (set = on; build.FLAG_AI, build.FLAG_AI_IMPORTANT): 0x2C2 clear = off; 0x2C2 set = every trainer (what it
@ meant before the three settings, so older saves keep it); 0x2C2 and 0x2C3 set = important trainers only, those whose
@ trainer header has bit 0 of byte 2 set (build.IMPORTANT_TRAINERS). EnemyTrainerSet_Init copies each trainer's
@ header into the BattleSetup by client (0 the player, 1 the first foe, 2 the partner, 3 the second foe): ids at
@ +0x18 + 4 i, headers (0x34 bytes) at +0x28 + 0x34 i.
@ The battle loads the trainer AI into its slot overlay at the start of each selection phase: overlay 11 (the hack's
@ AI), through SwitchSlotOverlay (0x02215914) at 0x02223D10 in overlay 14. ai_slot_select loads overlay 10 instead
@ (vanilla's empty AI overlay ID, now overlay 11's code plus the advanced AI, tools/ai/advai.c) when the advanced AI
@ serves any trainer of the battle. Each AI client polls the AI's entry at 0x02203736 with its client number in r2;
@ ai_entry sends the poll to adv_entry when overlay 10 is in the slot and the advanced AI serves that client's trainer,
@ else to overlay 11's entry (in overlay 10's image too, byte for byte). Both tail-call, keeping the caller's return
@ address and arguments. While the trainer's side waits for the player's action (advai.c foe_choice), the player's Bag
@ or party screen loads its own overlay into the slot: ai_entry then asks ai_resume (advai.c, in ITCM), which holds the
@ poll until the player has chosen and then brings overlay 10 back. The Bag loads its overlay only once every AI client
@ is done: ai_bag_check counts an advanced client that only waits for the player as done (advai.c ai_slot_free).
@ ai_replace (tools/ai/replace.c) asks ai_serves
@ too. Appended to arm9's ITCM block with the other new code by build.py.

    .syntax unified
    .cpu arm946e-s
    .thumb

    .equ FLAG_AI, 0x2C2
    .equ FLAG_AI_IMPORTANT, 0x2C3
    .equ AI_OVERLAY, 10
    .equ OLD_AI_OVERLAY, 11
    .equ ANY_TRAINER, 4                  @ ai_serves: any trainer of the battle (foes or partner)
    .equ MAIN_PTR, 0x02255BAC
    .equ SETUP_HEADER_MARK, 0x2A         @ BattleSetup: byte 2 of client 0's trainer header; 0x34 per client
    .equ SWITCH_SLOT, 0x02215915
    .equ OV11_ENTRY, 0x021E4DA1
    .equ ADV_ENTRY, 0x021F6E21           @ the first function of the new code (build.py checks it)

    .text

    .global ai_serves
    .thumb_func
ai_serves:                  @ r0 = client 0-3, or ANY_TRAINER -> r0 = 1 if the advanced AI decides for that trainer
    push {r4, r5, lr}
    movs r4, r0
    ldr r0, =FLAG_AI
    bl check_flag
    cmp r0, #0
    beq 9f                  @ off
    ldr r5, =MAIN_PTR
    ldr r5, [r5]
    ldr r5, [r5, #0x10]     @ BattleSetup
    movs r0, #0
    cmp r5, #0
    beq 9f
    ldr r1, [r5]            @ battle type: bit 0 = against a trainer
    lsls r1, r1, #31
    beq 9f
    ldr r0, =FLAG_AI_IMPORTANT
    bl check_flag
    movs r1, r0
    movs r0, #1
    cmp r1, #0
    beq 9f                  @ every trainer
    movs r2, r4             @ important trainers only: the client's mark, or any of clients 3, 2, 1
    cmp r4, #ANY_TRAINER
    blo 1f
    movs r2, #3
1:  movs r1, #0x34
    muls r1, r2, r1
    adds r1, #SETUP_HEADER_MARK
    ldrb r1, [r5, r1]
    lsls r1, r1, #31
    bne 9f                  @ marked: r0 = 1
    cmp r4, #ANY_TRAINER
    blo 8f
    subs r2, #1
    bne 1b
8:  movs r0, #0
9:  pop {r4, r5, pc}

    .global ai_slot_select
    .thumb_func
ai_slot_select:             @ r0 = overlay to load into the battle slot
    cmp r0, #OLD_AI_OVERLAY
    bne 9f
    push {r4, lr}
    movs r0, #ANY_TRAINER
    bl ai_serves
    movs r1, #OLD_AI_OVERLAY
    subs r0, r1, r0         @ 10 when the advanced AI serves a trainer of this battle, else 11
    pop {r4}
    pop {r3}
    mov lr, r3
9:  ldr r3, =SWITCH_SLOT
    bx r3

    .global ai_entry
    .thumb_func
ai_entry:                   @ r0-r2 = the AI's arguments, r1 the AI state, r2 the client
    ldr r3, =MAIN_PTR
    ldr r3, [r3]
    push {r4}
    ldr r4, =0x26C          @ the overlay in the slot
    ldr r3, [r3, r4]
    pop {r4}
    cmp r3, #AI_OVERLAY
    beq 2f
    cmp r3, #OLD_AI_OVERLAY
    beq 1f
    push {r0-r2, lr}        @ neither: the player's Bag or party screen took the slot (tools/ai/advai.c ai_resume)
    movs r0, r1
    bl ai_resume
    mov r12, r0
    pop {r0-r3}
    mov lr, r3
    mov r3, r12
    cmp r3, #1
    blo 1f                  @ 0: no advanced decision in progress, as before
    bhi 2f                  @ 2: overlay 10 is back
    movs r0, #0             @ 1: the player is still choosing
    bx lr
2:  push {r0-r2, lr}
    lsls r0, r2, #24
    lsrs r0, r0, #24
    bl ai_serves
    mov r12, r0
    pop {r0-r3}
    mov lr, r3
    mov r3, r12
    cmp r3, #0
    beq 1f
    ldr r3, =ADV_ENTRY
    bx r3
1:  ldr r3, =OV11_ENTRY
    bx r3

    .global ai_bag_check
    .thumb_func
ai_bag_check:               @ overlay 14's Bag (0x022029CC): may it load overlay 9 into the slot? (advai.c ai_slot_free)
    push {r3, lr}
    bl ai_slot_free
    pop {r3, pc}
