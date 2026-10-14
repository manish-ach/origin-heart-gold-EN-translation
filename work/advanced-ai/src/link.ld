/* The ITCM code and the advanced AI, linked together by tools/build.py link_ai (which writes ai_layout.ld,
   the MEMORY regions, and renames .itcm.* or .main.* every section ai_replace reaches).
   ITCM, after arm9's original ITCM block: the code of tools/asm first, in build.py's order, so the hooks into it
   stay put; then ai_replace, the tuning table (tools/aivsai.py find_tune reads it in ITCM) and libgcc; then what
   ai_replace reaches that the selection AI runs too (ai_replace runs during turn playback, while overlay 8 holds
   the battle slot) and the part of the AI that does not fit in the slot (link_ai's slot_spill picks it, the fewest
   bytes that leave the rest fitting, and renames it .itcm.spill*). .itcm_spill (then .main_spill, when ITCM is full)
   would take a slot section that still did not fit (link_ai stops the build then). ITCM_RAM: ai_replace's working
   memory.
   MAIN, main RAM after the event table (always resident, as fast as the slot): ai_lead first (lead.c; its hook in
   overlay 14 needs it to stay put), what only ai_replace or ai_lead runs, and the fewest bytes of .itcm_ai's sections that leave the rest fitting ITCM (link_ai renames both .main.*). Its .itcm.*
   patterns only let link_ai's measuring link finish before that pick (ld tries ITCM first:
   --enable-non-contiguous-regions); link_ai stops the build if the final link uses them.
   SLOT: after overlay 11's image (0x12060 bytes) and its 0x20-byte bss, up to overlay 14. adv_entry is first
   (tools/asm/aiselect.s jumps to 0x021F6E20) and write_action stays in the slot (the bench and aivsai tell the
   advanced AI's decisions by the setters' return address). The bss starts where the overlay file ends,
   ai_debug first. */
INCLUDE ai_layout.ld
SECTIONS
{
    .itcm : {
        KEEP(*.s.o(.text))
        KEEP(*(.itcm.text.ai_replace))
        KEEP(*(.itcm.tune))
        *libgcc.a:(.text .text.*)
    } > ITCM
    .itcm_ai : { *(.itcm.*) } > ITCM
    .main : {
        KEEP(*(.main.text.ai_lead))
        *(.main.*)
        *(.itcm.text.* .itcm.rodata.* .itcm.spill.*)
    } > MAIN
    .text : {
        KEEP(*(.text.entry))
        *(.text.write_action)
        *(.text .text.* .rodata .rodata.* .data .data.*)
        . = ALIGN(32);
    } > SLOT
    .itcm_spill : { *(.text .text.* .rodata .rodata.*) } > ITCM
    .main_spill : { *(.text .text.* .rodata .rodata.*) } > MAIN
    .bss ADDR(.text) + SIZEOF(.text) (NOLOAD) : {
        __bss_start = .;
        KEEP(*(.bss.debug))
        *(.bss .bss.* COMMON)
        . = ALIGN(32);
        __bss_end = .;
    }
    .itcm_bss (NOLOAD) : { *(.itcm_bss) } > ITCM_RAM
    ASSERT(ADDR(.itcm_bss) + SIZEOF(.itcm_bss) <= 0x01FFFF8C, "the foresight word, the read, lead and self-play flags, the Read and replacement records (engine.h) are the last 116 bytes of ITCM RAM")
    /DISCARD/ : { *(.ARM.exidx*) *(.ARM.extab*) *(.ARM.attributes) *(.comment) *(.note*) }
}
