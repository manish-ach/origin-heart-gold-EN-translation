/* Two-page native overlay50 companion. Original project code; no game text or
 * graphics copied. Reuses native windows/font, with one owned footer window.
 * Difficulty drawing/input never previews normal settings. The retained normal
 * drafts and their Cancel preview restoration stay owned by the native exit. */
#include "options.h"
#define U32(p,o) (*(uint32_t *)((uint8_t *)(p)+(o)))
#define U16(p,o) (*(uint16_t *)((uint8_t *)(p)+(o)))
#ifdef DG_OPTIONS_HOST_TEST
#define PTR(p,o) dg_menu_test_pointer(U32(p,o))
#define READ32(a) dg_menu_test_read32(a)
#define READ16(a) dg_menu_test_read16(a)
#define CALL(a,b,c,d,e,f,g,h,i) dg_menu_test_call(a,(uintptr_t)(b),(uintptr_t)(c),(uintptr_t)(d),(uintptr_t)(e),(uintptr_t)(f),(uintptr_t)(g),(uintptr_t)(h),(uintptr_t)(i))
#else
#define PTR(p,o) ((void *)(uintptr_t)U32(p,o))
#define READ32(a) (*(const volatile uint32_t *)(uintptr_t)(a))
#define READ16(a) (*(const volatile uint16_t *)(uintptr_t)(a))
#define CALL(a,b,c,d,e,f,g,h,i) (((uintptr_t (*)(uintptr_t,uintptr_t,uintptr_t,uintptr_t,uintptr_t,uintptr_t,uintptr_t,uintptr_t))(uintptr_t)(a))((uintptr_t)(b),(uintptr_t)(c),(uintptr_t)(d),(uintptr_t)(e),(uintptr_t)(f),(uintptr_t)(g),(uintptr_t)(h),(uintptr_t)(i)))
#endif
#define C1(a,b) CALL(a,b,0,0,0,0,0,0,0)
#define C2(a,b,c) CALL(a,b,c,0,0,0,0,0,0)
#define C3(a,b,c,d) CALL(a,b,c,d,0,0,0,0,0)
/* gSystem +0x48 is native new D-pad/A/B input. +0x44 is held.
 * Native touch sample is gSystem+0x40+0x20/22/24 (x/y/new press).
 * Use the game's input publication, not direct SPI or hardware key sampling. */
#define SYSTEM 0x021d0094u
#define KEY_A 1u
#define KEY_B 2u
#define KEY_RIGHT 16u
#define KEY_LEFT 32u
#define KEY_UP 64u
#define KEY_DOWN 128u
#define KEY_L 512u
#define KEY_R 256u
static struct {
    uintptr_t options, args;
    uint32_t epoch, requested;
} pending;
static uint32_t next_epoch;
static struct {
    struct DG_SettingsTxn txn;
    void *manager, *state, *string;
    uint32_t epoch, focus, closing, fault;
    uint32_t mode, nav_live, cursor_live;
    uint8_t rows[3][0x54];
    void *choices[6];
    uint32_t nav[4]; /* Native Window, independently owned on Options heap38. */
    /* TRAINER AI: the stored flag pair (dg_ai_encode bits) and the draft
     * (DG_AiSetting). Appended so the earlier field offsets that native test
     * drivers read stay unchanged. */
    uint32_t ai_stored, ai_draft;
} page;
static int last_apply;
static void load_page_rows(void *d);
static void release_page_rows(void);
static int owned(void *state) { return page.manager && page.state == state; }
/* TRAINER AI uses the hack's own saved-flag path, the same one the AI's
 * selector reads: GetSaveData 02001194, Save_VarsFlags_Get 0204F858, then
 * CheckFlag 0204F864, SetFlag 0204F890 or ClearFlag 0204F8B8. */
static void *ai_vars(void) {
    return (void *)C1(0x0204f859u,CALL(0x02001195u,0,0,0,0,0,0,0,0));
}
/* The stored pair as dg_ai_encode bits: bit0 0x2C2, bit1 0x2C3. */
static uint32_t ai_read(void) {
    void *v=ai_vars();
    return ((uint32_t)C2(0x0204f865u,v,DG_AI_FLAG_ON)!=0) |
           ((uint32_t)(C2(0x0204f865u,v,DG_AI_FLAG_KEY)!=0)<<1);
}
static void ai_write(uint32_t value) {
    void *v=ai_vars(); uint32_t f=dg_ai_encode(value);
    C2((f&1u)?0x0204f891u:0x0204f8b9u,v,DG_AI_FLAG_ON);
    C2((f&2u)?0x0204f891u:0x0204f8b9u,v,DG_AI_FLAG_KEY);
}
static int custom(void *state) { return owned(state) && page.mode; }
static uint32_t epoch_next(void) {
    ++next_epoch;
    if (!next_epoch) ++next_epoch;
    return next_epoch;
}
uint16_t *dg_menu_field_getter(void *save) {
    uint16_t *p = (uint16_t *)C1(0x02029349u, save);
    /* A new launch always replaces an unconsumed ticket. No transaction or
     * saved write occurs here. launch then binds the exact Args object. */
    pending.options = (uintptr_t)p; pending.args = 0;
    pending.epoch = epoch_next();
    pending.requested = (READ32(SYSTEM + 0x44) & KEY_L) != 0;
    return p;
}
void dg_menu_launch(void *field, void *args) {
    if (args && pending.options == (uintptr_t)PTR(args,4)) pending.args = (uintptr_t)args;
    else pending.requested = 0;
    C2(0x0203e521u, field, args);
}
int dg_menu_init(void *manager, int *step) {
    void *args = (void *)C1(0x020071c1u, manager);
    uint32_t request = pending.args == (uintptr_t)args && pending.epoch;
    uint32_t mode = pending.requested;
    uintptr_t expected = pending.options;
    uint32_t epoch = pending.epoch;
    pending.requested = 0; pending.options = 0; pending.args = 0; pending.epoch = 0;
    int result = (int)C2(0x021e4981u, manager, step);
    void *d = (void *)C1(0x020071adu, manager);
    if (!result || !request || !d || page.manager ||
        (uintptr_t)PTR(d,0x24) != expected) return result;
    void *str = (void *)C2(0x02026865u, 40, U32(d,0));
    /* Custom allocation failure falls back before any custom row suppression.
     * Native allocation failures inside original init retain native behavior. */
    if (!str) return result;
    if (dg_options_begin((uint16_t *)expected, (uintptr_t)manager, epoch, &page.txn) < 0) {
        C1(0x02026891u, str); return result;
    }
    page.manager = manager; page.state = d; page.string = str; page.epoch = epoch;
    page.focus = 0; page.closing = 0; page.fault = 0; last_apply = 0;
    page.mode = mode; page.nav_live = 0; page.cursor_live = 0;
    page.ai_stored = ai_read();
    page.ai_draft = dg_ai_decode(page.ai_stored&1u,page.ai_stored&2u);
    load_page_rows(d);
    if (page.fault) {
        release_page_rows(); C1(0x02026891u,str); dg_options_cancel(&page.txn);
        page.manager=0; page.state=0; page.string=0; return result;
    }
    for (unsigned i=0;i<4;++i) page.nav[i]=0;
    return result;
}
void dg_menu_load_rows(void *d) {
    /* Keep native rows and their drafts alive across page navigation. The
     * original teardown remains their sole owner in both page modes. */
    C1(0x01ff8a0du, d);
}
/* These character codes are from the existing charmap.tbl (letters are
 * consecutive). Only this bounded project-authored ASCII subset is accepted. */
static uint16_t glyph(unsigned c) {
    if (c>='A' && c<='Z') return (uint16_t)(0x12b+c-'A');
    if (c>='a' && c<='z') return (uint16_t)(0x145+c-'a');
    if (c>='0' && c<='9') return (uint16_t)(0x121+c-'0');
    if (c=='<') return 0x1b7; /* Existing double-chevron font glyphs. */
    if (c=='>') return 0x1b8;
    if (c=='/') return 0x1b1;
    if (c=='-') return 0x1be;
    if (c=='.') return 0x1ae;
    if (c==',') return 0x1ad;
    if (c==':') return 0x1c4;
    return 0x1de;
}
static void set_string(void *str, const char *s) {
    uint16_t chars[40]; unsigned n=0;
    while (s[n] && n<39) { chars[n]=glyph((unsigned char)s[n]); ++n; }
    chars[n++]=0xffff;
    C3(0x02026eb9u,str,chars,n);
}
static void text(void *d, unsigned offset, unsigned x, unsigned y,
                 const char *s, unsigned color) {
    set_string(page.string,s);
    CALL(0x02020835u,(uint8_t *)d+offset,0,page.string,x,y,0xff,color,0);
}
static void bytes_copy(uint8_t *to, const uint8_t *from, unsigned n) {
    for (unsigned i=0;i<n;++i) to[i]=from[i];
}
static void release_page_rows(void) {
    for (unsigned i=0;i<6;++i) {
        if (page.choices[i]) C1(0x02026891u,page.choices[i]);
        page.choices[i]=0;
    }
}
static void load_page_rows(void *d) {
    static const char *const choices[6]={"DEFAULT","ALL","ON","OFF","OFF","ON"};
    static const uint8_t bits[3]={DG_ITEMS_ALL,DG_SHARE_OFF,DG_CAP_ON};
    for (unsigned i=0;i<6;++i) page.choices[i]=0;
    for (unsigned i=0;i<6;++i) {
        page.choices[i]=(void *)C2(0x02026865u,40,U32(d,0));
        if (!page.choices[i]) { page.fault=1; return; }
        set_string(page.choices[i],choices[i]);
    }
    for (unsigned r=0;r<3;++r) {
        for (unsigned i=0;i<0x54;++i) page.rows[r][i]=0;
        U16(page.rows[r],4)=2;
        U16(page.rows[r],6)=(page.txn.draft_flags&bits[r])!=0;
        U32(page.rows[r],8)=(uintptr_t)page.choices[2*r];
        U32(page.rows[r],12)=(uintptr_t)page.choices[2*r+1];
    }
}
static void native_row(void *d, unsigned row) {
    /* Both pages supply the original overlay50 row record layout. Borrow its
     * active slot only for the synchronous native row renderer, then restore
     * the ordinary record verbatim. Native exit still owns its original rows.
     * Rows0..2 never run title/music/frame preview branches3..5. */
    uint8_t saved[0x54];
    uint8_t *slot=(uint8_t *)d+0x80+row*0x54;
    bytes_copy(saved,slot,0x54);
    bytes_copy(slot,page.rows[row],0x54);
    C2(0x021e53edu,d,row);
    bytes_copy(slot,saved,0x54);
}
static void fill(void *d, unsigned offset, unsigned color) {
    C2(0x0201e1a9u,(uint8_t *)d+offset,color);
}
static void copy(void *d, unsigned offset) { C1(0x0201dda9u,(uint8_t *)d+offset); }
#define SELECTED 0x00030200u
#define NORMAL 0x00010200u
static void ai_row(void *d) {
    /* Native slot3 would run the renderer's row-3 preview (0200589C), so draw
     * TRAINER AI with the renderer's own steps: erase the value area as
     * 021E53EC does, then each value at its 48-pixel pitch, the chosen one
     * in SELECTED colour. Row y 65 matches the native slot3 outline. */
    static const char *const values[DG_AI_COUNT]={"OFF","KEY","ALL"};
    CALL(0x0201e2a5u,(uint8_t *)d+0x44,0x22,108,65,320,20,0,0);
    for (unsigned i=0;i<DG_AI_COUNT;++i)
        text(d,0x44,108+48*i,65,values[i],i==page.ai_draft?SELECTED:NORMAL);
    copy(d,0x44);
}
static void navigation(void *d) {
    if (!page.nav_live) {
        /* BG1 native windows own tiles10..633. Reserve the immediately
         * following 36 tiles634..669, below the 1024-tile BG limit. This
         * 96x24 window occupies the unused footer at screen(8,168). */
#ifdef DG_OPTIONS_HOST_TEST
        C3(0x0201dc3du,PTR(d,0x14),page.nav,634);
#else
        ((void (*)(void *,void *,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned))
            (uintptr_t)0x0201dc3du)(PTR(d,0x14),page.nav,1,1,21,12,3,13,634);
#endif
        if (!U32(page.nav,12)) return;
        page.nav_live=1;
    }
    fill(page.nav,0,0);
    text(page.nav,0,0,6,"<",0x000f0200u);
    text(page.nav,0,14,6,"L",0x000f0200u);
    text(page.nav,0,35,6,page.mode?"2/2":"1/2",0x000f0200u);
    text(page.nav,0,66,6,"R",0x000f0200u);
    text(page.nav,0,80,6,">",0x000f0200u);
    copy(page.nav,0);
}
static void footer(void *d) {
    /* Reuse the original Options button sprites and their native focus state. */
    /* Keep the native footer text windows unchanged across page switches. */
    if (!page.cursor_live) return;
    if (page.mode) {
        uint32_t flags=U32(d,0x10); uint16_t choice=U16(d,0x2d2);
        unsigned row=page.focus<4?page.focus:7;
        U32(d,0x10)=(flags&~28u)|(row<<2);
        U16(d,0x2d2)=page.focus==5?1:0;
        C2(0x021e5945u,d,row);
        U32(d,0x10)=flags; U16(d,0x2d2)=choice;
    } else C2(0x021e5945u,d,(U32(d,0x10)>>2)&7);
}
static void native_footer_labels(void *d) {
    /* Direct held-L entry never runs the ordinary page's draw. Load its exact
     * native message IDs and use its existing button windows/placement/color;
     * do not preview the ordinary rows just to initialize these two labels.
     * overlay50 021E5298..52E6 owns Confirm8/ Quit7 and these coordinates. */
    C3(0x0200bb0du,PTR(d,0x28),8,page.string);
    CALL(0x02020835u,(uint8_t *)d+0x64,0,page.string,12,6,0xff,0x000f0200u,0);
    C3(0x0200bb0du,PTR(d,0x28),7,page.string);
    CALL(0x02020835u,(uint8_t *)d+0x74,0,page.string,4,6,0xff,0x000f0200u,0);
}
static void refresh_focus(void *d) {
    fill(d,0x54,0xff);
    const char *first="Apply changes. Save to keep them.";
    const char *second="Cancel discards changes.";
    if (page.focus==0) {
        first=(page.txn.draft_flags & DG_ITEMS_ALL)?
            "ALL: enables healing/status/PP items.":
            "DEFAULT: original Chinese hack rules.";
        second="Trainer Bag only. Held items unchanged.";
    }
    if (page.focus==1) { first="OFF blocks benched EXP and EVs."; second="Level caps still apply."; }
    if (page.focus==2) { first="Gym-based cap. Never decreases."; second="Candy and Day Care unchanged."; }
    if (page.focus==3) { first="Advanced AI: OFF for no trainers, KEY"; second="for important trainers, ALL for all."; }
    if (page.fault) { first="Settings changed. Cancel and reopen."; second="No difficulty changes applied."; }
    text(d,0x54,4,0,first,0x0001020fu);
    text(d,0x54,4,16,second,0x0001020fu);
    copy(d,0x54); footer(d);
}
void dg_menu_draw(void *d) {
    if (!custom(d)) {
        if (owned(d)) {
            /* Native redraw updates individual text runs rather than erasing
             * the previous page. Clear every shared window before rebuilding
             * the normal rows so difficulty glyphs cannot remain underneath. */
            fill(d,0x34,0); fill(d,0x44,0x22); fill(d,0x54,0xff);
            fill(d,0x64,0); fill(d,0x74,0);
        }
        C1(0x021e5211u,d);
        if (owned(d)) { footer(d); navigation(d); }
        return;
    }
    fill(d,0x34,0); fill(d,0x44,0x22); fill(d,0x54,0xff);
    text(d,0x34,2,5,"DIFFICULTY",0x000f0200u);
    static const char *const names[4]={"ITEMS IN BATTLE","SHARE","CAP","TRAINER AI"};
    for (unsigned r=0;r<4;++r) text(d,0x44,4,5+20*r,names[r],NORMAL);
    for (unsigned r=0;r<3;++r) native_row(d,r);
    ai_row(d);
    native_footer_labels(d);
    footer(d);
    refresh_focus(d);
    copy(d,0x34); copy(d,0x44); copy(d,0x54); copy(d,0x64); copy(d,0x74);
    navigation(d);
}
void dg_menu_cursor_plane(unsigned bg, unsigned enabled) {
    if (bg==0 && owned(page.state)) {
        page.cursor_live=1;
        /* Original text-speed setup owns sprites0..4; only frame arrows5/6
         * belong to the ordinary page. Footer buttons7/8 remain visible. */
        for (unsigned i=5;i<9;++i)
            C2(0x02024e49u,PTR(page.state,0x32c+4*i),i>=7 || !page.mode);
    }
    C2(0x0201c459u,bg,enabled);
    if (bg==0 && owned(page.state)) footer(page.state);
}
static void switch_page(void *d) {
    page.mode=!page.mode;
    for (unsigned i=5;i<9;++i)
        C2(0x02024e49u,PTR(d,0x32c+4*i),i>=7 || !page.mode);
    dg_menu_draw(d);
    if (!page.mode) {
        unsigned row=(U32(d,0x10)>>2)&7;
        if (row<7) C2(0x021e53edu,d,row);
        C2(0x021e5945u,d,row);
    }
}
static void choose(unsigned row, unsigned value) {
    static const uint8_t bits[3]={DG_ITEMS_ALL,DG_SHARE_OFF,DG_CAP_ON};
    U16(page.rows[row],6)=value;
    uint32_t mask=bits[row];
    uint32_t f=(page.txn.draft_flags & ~mask) | (value?mask:0);
    if (dg_options_set_draft(&page.txn,(uintptr_t)page.manager,page.epoch,f)<0) page.fault=1;
}
static void row_draw(void *d, unsigned row) {
    if (row<3) native_row(d,row); else ai_row(d);
}
static void finish(void *d, unsigned apply, unsigned touch) {
    if (apply && (page.fault || !page.txn.active ||
        (READ16(page.txn.options_identity)&DG_DIFFICULTY_MASK) !=
        (page.txn.original_word&DG_DIFFICULTY_MASK) || ai_read()!=page.ai_stored)) {
        page.fault=1; refresh_focus(d); return;
    }
    /* Match native input-mode bookkeeping; no title/audio/background preview.
     * Keep footer animation suppressed: exit_animation adapter returns zero. */
    C2(0x02017c49u,PTR(d,0x20),touch);
    if (touch) U32(d,0x374)=1;
    U32(d,0x10)=(U32(d,0x10)&~3u)|(apply?1u:2u);
    page.closing=1;
}
void dg_menu_input(void *d) {
    if (!owned(d)) { C1(0x021e578du,d); return; }
    if (page.closing || (U32(d,0x10)&3u)) return;
    uint32_t keys=READ32(SYSTEM+0x48);
    /* B always cancels, including simultaneous touch. Native +0x64 is a
     * one-frame touch-down event, not held touch, as in 021E5792. */
    if (keys&KEY_B) { finish(d,0,0); return; }
    if (keys&(KEY_L|KEY_R)) { switch_page(d); return; }
    if (READ16(SYSTEM+0x64)) {
        unsigned x=READ16(SYSTEM+0x60), y=READ16(SYSTEM+0x62);
        if (page.nav_live && y>=168 && y<192 &&
            ((x>=8 && x<32) || (x>=72 && x<104))) {
            switch_page(d); return;
        }
    }
    if (!custom(d)) {
        if (READ16(SYSTEM+0x64)) {
            unsigned x=READ16(SYSTEM+0x60), y=READ16(SYSTEM+0x62);
            if (y>=168 && y<192 && x>=112 && x<240) {
                finish(d,x<176,1); return;
            }
        }
        if ((keys&KEY_A) && ((U32(d,0x10)>>2)&7)==7) {
            finish(d,U16(d,0x2d2)==1,0); return;
        }
        C1(0x021e578du,d);
        if (keys || READ16(SYSTEM+0x64)) footer(d);
        return;
    }
    if (READ16(SYSTEM+0x64)) {
        unsigned x=READ16(SYSTEM+0x60), y=READ16(SYSTEM+0x62);
        for (unsigned r=0;r<4;++r) {
            if (y>=22+20*r && y<42+20*r && x>=8 && x<248) {
                page.focus=r;
                /* Value bands start 4 pixels left of each value's screen x. */
                if (x>=108 && r<3) choose(r,x>=160);
                if (x>=108 && r==3) page.ai_draft=x<160?DG_AI_OFF:x<208?DG_AI_KEY:DG_AI_ALL;
                row_draw(d,r); refresh_focus(d); return;
            }
        }
        if (y>=168 && y<192 && x>=112 && x<240) {
            page.focus=x<176?5:4;
            finish(d,page.focus==5,1); return;
        }
        return; /* Empty/unused rows and other touch regions are inert. */
    }
    if (keys&KEY_UP) page.focus=page.focus? page.focus-1:5;
    else if (keys&KEY_DOWN) page.focus=page.focus==5?0:page.focus+1;
    else if (page.focus<3 && (keys&(KEY_LEFT|KEY_RIGHT|KEY_A))) {
        CALL(0x021e5541u,d,page.focus,page.rows[page.focus]+4,1,0,0,0,0);
        choose(page.focus,U16(page.rows[page.focus],6));
    } else if (page.focus==3 && (keys&(KEY_LEFT|KEY_RIGHT|KEY_A))) {
        /* Three values: Left steps back, Right and A step forward, wrapping.
         * No division: the resident link has no runtime helpers. */
        if (keys&(KEY_RIGHT|KEY_A)) page.ai_draft=page.ai_draft+1<DG_AI_COUNT?page.ai_draft+1:0;
        else page.ai_draft=page.ai_draft?page.ai_draft-1:DG_AI_COUNT-1;
    } else if (page.focus>=4 && (keys&(KEY_LEFT|KEY_RIGHT))) {
        page.focus=page.focus==4?5:4;
    } else if (page.focus>=4 && (keys&KEY_A)) {
        finish(d,page.focus==5,0); return;
    } else return;
    if (page.focus<4) row_draw(d,page.focus);
    refresh_focus(d);
}
int dg_menu_exit_animation(void *d) {
    /* This hook precedes native window/BG destruction. Remove our sixth
     * window while its BG config is still alive, exactly once. */
    if (owned(d) && page.nav_live && (U32(d,0x10)&3u)) {
        C1(0x0201dd51u,page.nav); page.nav_live=0;
        for (unsigned i=0;i<4;++i) page.nav[i]=0;
    }
    return owned(d) && (page.closing || page.mode)?0:(int)C1(0x021e5b79u,d);
}
int dg_menu_exit(void *manager, int *step) {
    /* The native free clears manager+0x1c. A repeated callback must not run
     * either normal setters or heap destruction on already freed data. */
    if (page.manager!=manager) {
        if (!C1(0x020071adu,manager)) return 1;
        return (int)C2(0x021e4a69u,manager,step);
    }
    /* Native main callback already destroyed windows/strings/sprites. Capture
     * heap before free, then invalidate ownership BEFORE either native free.
     * Never enter native exit setters/Cancel previews/text-speed commit. */
    void *d=(void *)C1(0x020071adu,manager);
    if (!d || d!=page.state) {
        /* Lifetime violation: do not touch a replaced allocation. No saved
         * write and no speculative free. Integration tests must reject this. */
        last_apply=DG_SETTINGS_STALE;
        dg_options_cancel(&page.txn);
        page.manager=0; page.state=0; page.string=0; page.epoch=0;
        return 1;
    }
    if ((U32(d,0x10)&3u)!=1) last_apply=DG_SETTINGS_NO_CHANGE;
    else if (ai_read()!=page.ai_stored) last_apply=DG_SETTINGS_STALE; /* No write at all. */
    else {
        last_apply=dg_options_apply((uint16_t *)PTR(d,0x24),(uintptr_t)manager,page.epoch,&page.txn);
        /* TRAINER AI commits with the Options word, never after its failure. */
        /* Compare pairs, not values: Confirm also rewrites the stray 0x2C3
         * of 0x2C2-clear (OFF) as the canonical pair, both clear. */
        if (last_apply>=0 && dg_ai_encode(page.ai_draft)!=page.ai_stored) {
            ai_write(page.ai_draft); last_apply=DG_SETTINGS_CHANGED;
        }
    }
    dg_options_cancel(&page.txn);
    void *str=page.string;
    page.manager=0; page.state=0; page.string=0; page.epoch=0; page.closing=0;
    release_page_rows();
    C1(0x02026891u,str);
    /* Both pages share one Confirm/Back transaction. Native exit commits or
     * cancels all seven retained ordinary drafts and frees their owner. Its
     * disjoint setters preserve the separately merged difficulty bits. */
    return (int)C2(0x021e4a69u,manager,step);
}
int dg_menu_last_apply_result(void) { return last_apply; }
