#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
#include <stdlib.h>
#include "options.h"
#define W32(p,o) (*(uint32_t *)((unsigned char *)(p)+(o)))
#define W16(p,o) (*(uint16_t *)((unsigned char *)(p)+(o)))
static unsigned char *data, *manager, *args;
static uint16_t *opts;
static uint32_t keys,held,touch,x,y;
static int fail_alloc, frees,heaps,deletes,normal_rows,normal_draw,normal_input,normal_exit,hidden,printed;
static int data_live, bg0_enabled, bg_calls, sprite_setup;
static int nav_created, nav_removed, cursor_row, native_choices, footer_confirm, footer_quit;
/* TRAINER AI: saved flags behind the native flag routines, and what the page draws. */
#define SAVE_TOKEN 0x02009000u
#define VARS_TOKEN 0x0200a000u
static unsigned flag_on, flag_key;
static int flag_reads, flag_writes, ai_fills, ai_labels, footer_choice;
static uint32_t ai_colors[3];
static uint16_t help_first[40], help_second[40];
void *dg_menu_test_pointer(uint32_t address) {
 if (!address) return 0;
 assert(address==0x02003000); return opts;
}
static uintptr_t string_token=0x02007000;
static uint16_t last_text[40];
/* charmap.tbl codes, independent of options.c's glyph(). */
static int text_is(const uint16_t *t,const char *s){
 unsigned n=0;
 for(;s[n];++n){
  unsigned c=(unsigned char)s[n];
  uint16_t g=c>='A'&&c<='Z'?0x12b+c-'A':c>='a'&&c<='z'?0x145+c-'a':c==' '?0x1de:c==','?0x1ad:c==':'?0x1c4:c=='.'?0x1ae:0;
  assert(g);if(t[n]!=g)return 0;
 }
 return t[n]==0xffff;
}
static unsigned shown_ai(void){
 /* Exactly one value in SELECTED colour, the others NORMAL. */
 unsigned shown=3;
 for(unsigned i=0;i<3;++i){assert(ai_colors[i]==0x30200||ai_colors[i]==0x10200);if(ai_colors[i]==0x30200){assert(shown==3);shown=i;}}
 assert(shown<3);return shown;
}
uint32_t dg_menu_test_read32(uintptr_t a) {
 if(a==0x21d0094+0x44) return held;
 if(a==0x21d0094+0x48) return keys;
 assert(0); return 0;
}
uint16_t dg_menu_test_read16(uintptr_t a) {
 if(a==0x21d0094+0x64) return (uint16_t)touch;
 if(a==0x21d0094+0x60) return (uint16_t)x;
 if(a==0x21d0094+0x62) return (uint16_t)y;
 assert(a==(uintptr_t)opts);return *opts;
}
uintptr_t dg_menu_test_call(uintptr_t a,uintptr_t b,uintptr_t c,uintptr_t d,uintptr_t e,uintptr_t f,uintptr_t g,uintptr_t h,uintptr_t i) {
 (void)i;
 switch(a) {
 case 0x2001195: return SAVE_TOKEN;
 case 0x204f859: assert(b==SAVE_TOKEN);return VARS_TOKEN;
 case 0x204f865: assert(b==VARS_TOKEN && (c==0x2c2 || c==0x2c3));++flag_reads;return c==0x2c2?flag_on:flag_key;
 case 0x204f891: case 0x204f8b9:
   assert(b==VARS_TOKEN && (c==0x2c2 || c==0x2c3));++flag_writes;
   *(c==0x2c2?&flag_on:&flag_key)=a==0x204f891;return 0;
 case 0x201e2a5:
   assert(b==(uintptr_t)data+0x44 && c==0x22 && d==108 && e==65 && f==320 && g==20);++ai_fills;return 0;
 case 0x2029349: return (uintptr_t)opts;
 case 0x203e521: assert(c==(uintptr_t)args);return 0;
 case 0x20071c1: assert(b==(uintptr_t)manager);return (uintptr_t)args;
 case 0x21e4981:
   memset(data,0,0x378);W32(data,0)=38;W32(data,0x24)=0x02003000;
   data_live=1;return 1;
 case 0x20071ad: return data_live?(uintptr_t)data:0;
 case 0x2026865: assert(b==40 && c==38);return fail_alloc?0:string_token;
 case 0x2026891: assert(b==string_token);++deletes;return 0;
 case 0x20071b1: assert(b==(uintptr_t)manager);++frees;data_live=0;return 0;
 case 0x201b1e5: assert(b==38);++heaps;return 0;
 case 0x1ff8a0d:
   ++normal_rows;
   for(unsigned row=0;row<7;++row) W16(data,0x84+row*0x54)=2;
   W16(data,0x86)=*opts&3;return 0;
 case 0x21e5211: ++normal_draw;return 0;
 case 0x21e578d: ++normal_input;return 0;
 case 0x21e4a69:
   ++normal_exit;
   if((W32(data,0x10)&3)==1) *opts=(*opts&~3u)|W16(data,0x86);
   ++frees;++heaps;data_live=0;return 1;
 case 0x21e5b79: return 17;
 case 0x1ff8b35: ++sprite_setup;return 0;
 case 0x201c459: assert(b==0 && c<=1);bg0_enabled=(int)c;++bg_calls;return 0;
 case 0x2024e49: assert(c<=1);if(!c)++hidden;return 0;
 case 0x21e5945: assert(b==(uintptr_t)data && c<8);cursor_row=(int)c;if(c==7)footer_choice=W16(data,0x2d2);return 0;
 case 0x21e53ed: assert(b==(uintptr_t)data && c<7);return 0;
 case 0x21e5541:
   assert(b==(uintptr_t)data && c<3 && W16((void *)d,0)==2);
   W16((void *)d,2)=(W16((void *)d,2)+e)%2; ++native_choices; return 0;
 case 0x201dc3d:
   assert(d==634);W32((void *)c,12)=0x02008000;++nav_created;return 0;
 case 0x201dd51:
   assert(W32((void *)b,12)==0x02008000);++nav_removed;return 0;
 case 0x2026eb9: assert(b==string_token && d<=40);memcpy(last_text,(void *)c,d*2);assert(last_text[d-1]==0xffff);return 0;
 case 0x200bb0d:
   assert(d==string_token && (c==7 || c==8));
   if(c==8)++footer_confirm;else ++footer_quit;return 0;
 case 0x2020835:
   assert(d==string_token && g==0xff);++printed;
   if(b==(uintptr_t)data+0x44 && f==65 && e>=108){
    static const char *const v[3]={"OFF","KEY","ALL"};
    assert((e-108)%48==0 && (e-108)/48<3 && text_is(last_text,v[(e-108)/48]));ai_colors[(e-108)/48]=(uint32_t)h;
   }
   if(b==(uintptr_t)data+0x44 && e==4 && f==65){assert(text_is(last_text,"TRAINER AI"));++ai_labels;}
   if(b==(uintptr_t)data+0x54 && e==4) memcpy(f?help_second:help_first,last_text,sizeof last_text);
   return 0;
 case 0x201e1a9: case 0x201dda9: case 0x2017c49: return 0;
 default: fprintf(stderr,"unexpected native call %lx\n",(unsigned long)a);assert(0);return 0;
 }
}
static void input(uint32_t k){keys=k;touch=0;dg_menu_input(data);keys=0;}
static void tap(unsigned tx,unsigned ty){touch=1;x=tx;y=ty;keys=0;dg_menu_input(data);touch=0;}
static void open_page(unsigned difficulty) {
 int step=0; held=difficulty?512:0;keys=touch=0;
 W32(args,4)=0x02003000;
 assert(dg_menu_field_getter((void *)1)==opts);
 dg_menu_launch((void *)2,args);
 assert(dg_menu_init(manager,&step)==1);
 int old_confirm=footer_confirm,old_quit=footer_quit;
 dg_menu_load_rows(data);dg_menu_draw(data);
 if(difficulty && !fail_alloc) assert(footer_confirm==old_confirm+1 && footer_quit==old_quit+1);
 /* Unpatched native init calls the existing TEXT SPEED setup first. */
 int old_hidden=hidden, old_calls=bg_calls, old_setup=sprite_setup;
 dg_menu_test_call(0x1ff8b35,(uintptr_t)data,0,0,0,0,0,0,0);
 dg_menu_cursor_plane(0,1);
 assert(sprite_setup==old_setup+1 && bg_calls==old_calls+1);
 assert(bg0_enabled);
 assert(hidden==old_hidden+(fail_alloc?0:difficulty?2:0));
}
static void close_page(void){int step=0;if(data_live){if(!(W32(data,0x10)&3))W32(data,0x10)|=2;dg_menu_exit_animation(data);}assert(dg_menu_exit(manager,&step)==1);}
int main(void) {
 /* Codec and merge exhaustive; independently check each owned bit and ALL
  * unrelated bits, including bit15 dropping out of native frame extraction. */
 for(unsigned w=0;w<65536;++w) for(unsigned f=0;f<8;++f) {
  uint16_t v=dg_settings_merge((uint16_t)w,f);
  assert((v&~0x8028u)==(w&~0x8028u));assert(dg_settings_decode(v)==f);
  assert(((v>>15)&1)==(f&1));assert(((v>>3)&1)==((f>>1)&1));assert(((v>>5)&1)==((f>>2)&1));
  assert((v&3)==(w&3));assert(((v>>2)&1)==((w>>2)&1));assert(((v>>4)&1)==((w>>4)&1));
  assert(((v>>6)&3)==((w>>6)&3));assert(((v>>8)&3)==((w>>8)&3));assert(((v>>10)&31)==((w>>10)&31));
 }
 for(unsigned bad=8;bad<=0x10000;bad<<=1) assert(dg_settings_merge(0x4444,bad)==0x4444);
 /* TRAINER AI codec: 0x2C2 clear is OFF whatever 0x2C3 holds; OFF clears both. */
 assert(dg_ai_decode(0,0)==DG_AI_OFF && dg_ai_decode(0,1)==DG_AI_OFF);
 assert(dg_ai_decode(1,0)==DG_AI_ALL && dg_ai_decode(1,1)==DG_AI_KEY && dg_ai_decode(7,9)==DG_AI_KEY);
 assert(dg_ai_encode(DG_AI_OFF)==0 && dg_ai_encode(DG_AI_ALL)==1 && dg_ai_encode(DG_AI_KEY)==3);
 assert(dg_ai_encode(DG_AI_COUNT)==0 && dg_ai_encode(0xffffffffu)==0);
 for(unsigned v=0;v<DG_AI_COUNT;++v) assert(dg_ai_decode(dg_ai_encode(v)&1,dg_ai_encode(v)&2)==v);
 long ps=sysconf(_SC_PAGESIZE);unsigned char *guard=mmap(0,(size_t)ps*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);
 assert(guard!=MAP_FAILED);assert(!mprotect(guard+ps,(size_t)ps,PROT_NONE));
 uint16_t *edge=(uint16_t *)(guard+ps-2);*edge=0x1404;
 struct DG_SettingsTxn t={0};
 assert(dg_options_begin(edge,1,1,&t)==1);assert(dg_options_begin(edge,1,1,&t)<0);
 assert(dg_options_set_draft(&t,1,1,0x100)<0);assert(t.draft_flags==0);
 assert(dg_options_set_draft(&t,2,1,7)<0);assert(dg_options_set_draft(&t,1,2,7)<0);
 assert(dg_options_set_draft(&t,1,1,7)==1);*edge^=0x100;
 assert(dg_options_apply(edge,2,1,&t)<0);assert(dg_options_apply(edge,1,2,&t)<0);
 uint16_t other=*edge;assert(dg_options_apply(&other,1,1,&t)<0);
 assert(dg_options_apply(edge,1,1,&t)==1);assert(*edge==0x952c);assert(!t.active);
 assert(dg_options_begin(edge,1,3,&t)==1);assert(dg_options_apply(edge,1,3,&t)==0);
 assert(dg_options_begin(edge,1,6,&t)==1);*edge^=0x400;
 assert(!mprotect(guard,(size_t)ps,PROT_READ));
 assert(dg_options_apply(edge,1,6,&t)==0); /* Must issue NO store. */
 assert(!mprotect(guard,(size_t)ps,PROT_READ|PROT_WRITE));
 assert(dg_options_begin(edge,1,4,&t)==1);*edge^=8;assert(dg_options_apply(edge,1,4,&t)==-2);
 dg_options_cancel(&t);assert(dg_options_begin((uint16_t *)(guard+1),1,1,&t)<0);
 assert(dg_options_begin(edge,0,1,&t)<0);assert(dg_options_begin(edge,1,0,&t)<0);
 assert(dg_options_begin(edge,1,5,&t)==1);t.draft_flags=0x100;assert(dg_options_apply(edge,1,5,&t)<0);dg_options_cancel(&t);
 /* Portable ABI mocks, not native UI acceptance. Same input/render C executes;
  * no test setter for page mode, selection, transaction flags or exit result. */
 unsigned char *low=calloc(1,0x8000);
 assert(low);data=low;manager=low+0x1000;args=low+0x2000;opts=(uint16_t *)(low+0x3000);
 int writes=flag_writes;
 for(unsigned flags=0;flags<8;++flags) {
  *opts=0x5144;unsigned before_frees=frees,before_heaps=heaps,before_deletes=deletes;
  open_page(1);assert(dg_menu_exit_animation(data)==0);
  for(unsigned row=0;row<7;++row) assert(W16(data,0x84+row*0x54)==2);
  int cursor_calls=bg_calls;
  /* Visit all three rows and both footer choices, then wrap to ITEMS. */
  /* Four rows, then CANCEL and APPLY, then wrap to ITEMS. */
  for(unsigned focus=0;focus<6;++focus) {
   assert(bg0_enabled && bg_calls==cursor_calls);assert(cursor_row==(int)(focus<4?focus:7));
   if(focus>=4) assert(footer_choice==(focus==5));
   input(128);
  }
  assert(bg0_enabled && bg_calls==cursor_calls);
  if(flags&4) input(16);input(128);if(flags&1)input(16);input(128);if(flags&2)input(16);
  input(128);input(128);input(128);input(1);assert((W32(data,0x10)&3)==1);
  assert(*opts==0x5144); /* Draft does not write live Options. */
  close_page();assert(*opts==dg_settings_merge(0x5144,flags));
  assert(frees==(int)before_frees+1 && heaps==(int)before_heaps+1 && deletes==(int)before_deletes+7);
  close_page();assert(frees==(int)before_frees+1 && heaps==(int)before_heaps+1);
 }
 assert(flag_writes==writes); /* The Options word alone; no TRAINER AI change. */
 *opts=0x4144;open_page(1);tap(192,35);tap(192,55);tap(192,75);tap(149,180);close_page();assert(dg_settings_decode(*opts)==7);
 unsigned keep=*opts;open_page(1);input(16);input(2);close_page();assert(*opts==keep);
 open_page(1);tap(116,35);tap(200,180);close_page();assert(*opts==keep);
 open_page(1);input(16);input(32);tap(149,180);close_page();assert(*opts==keep);assert(dg_menu_last_apply_result()==0);
 open_page(1);tap(192,145);tap(50,180);assert(!(W32(data,0x10)&3));input(2);close_page();
 open_page(1);*opts^=8;tap(149,180);assert(!(W32(data,0x10)&3));input(2);close_page();
 assert(!normal_draw && !normal_input);
 /* Actual page controls preserve both drafts; a shared Confirm commits them
  * together and Back cancels both. No held-L entry is needed. */
 *opts=0x4144;open_page(0);W16(data,0x86)=2;
 input(256);tap(192,35);assert(*opts==0x4144);
 input(512);assert(W16(data,0x86)==2 && *opts==0x4144);
 tap(85,180);tap(149,180);close_page();
 assert(*opts==dg_settings_merge(0x4146,4));
 keep=*opts;open_page(0);W16(data,0x86)=0;
 tap(85,180);tap(116,35);tap(18,180);input(2);close_page();assert(*opts==keep);
 /* TRAINER AI row. Each starting flag pair shows its value; B and touch Cancel
  * write no flag, and neither does an unchanged Apply, except that Apply turns
  * the stray pair (0x2C2 clear, 0x2C3 set) into canonical OFF. The Options word
  * is left alone throughout. */
 static const unsigned start[4][3]={{0,0,DG_AI_OFF},{0,1,DG_AI_OFF},{1,0,DG_AI_ALL},{1,1,DG_AI_KEY}};
 *opts=0x4144;
 for(unsigned st=0;st<4;++st) for(unsigned way=0;way<3;++way) {
  flag_on=start[st][0];flag_key=start[st][1];writes=flag_writes;
  int labels=ai_labels,fills=ai_fills;
  open_page(1);assert(shown_ai()==start[st][2] && ai_labels==labels+1 && ai_fills==fills+1);
  if(way==0)input(2);else if(way==1)tap(200,180);else tap(149,180);
  close_page();
  unsigned canonical=way==2 && st==1;
  assert(flag_writes==writes+(canonical?2:0) && flag_on==start[st][0] &&
         flag_key==(canonical?0:start[st][1]) && *opts==0x4144);
  assert(dg_menu_last_apply_result()==(int)canonical);
 }
 /* D-pad: three DOWNs reach the row, with the native outline on slot3 and its
  * help. RIGHT and A step forward, LEFT back, wrapping; no write before Apply. */
 flag_on=flag_key=0;writes=flag_writes;
 open_page(1);for(unsigned n=0;n<3;++n)input(128);
 assert(cursor_row==3 && text_is(help_first,"Advanced AI: OFF for no trainers, KEY") &&
        text_is(help_second,"for important trainers, ALL for all."));
 static const uint32_t step_keys[7]={16,16,16,32,32,1,32};
 static const unsigned step_values[7]={DG_AI_KEY,DG_AI_ALL,DG_AI_OFF,DG_AI_ALL,DG_AI_KEY,DG_AI_ALL,DG_AI_KEY};
 for(unsigned n=0;n<7;++n){input(step_keys[n]);assert(shown_ai()==step_values[n] && cursor_row==3);}
 assert(flag_writes==writes && !flag_on && !flag_key);
 input(128);input(128);assert(cursor_row==7 && footer_choice==1);
 input(1);assert((W32(data,0x10)&3)==1 && flag_writes==writes);
 close_page();
 assert(flag_on && flag_key && flag_writes==writes+2 && *opts==0x4144 && dg_menu_last_apply_result()==1);
 /* Touch: value bands at screen x 108..159, 160..207 and 208..247 in y 82..101;
  * the label area only focuses; y 81 is CAP's band and y 102 is inert. */
 writes=flag_writes;open_page(1);
 tap(150,95);assert(shown_ai()==DG_AI_OFF && cursor_row==3);
 tap(159,82);assert(shown_ai()==DG_AI_OFF);
 tap(160,101);assert(shown_ai()==DG_AI_KEY);
 tap(207,90);assert(shown_ai()==DG_AI_KEY);
 tap(208,90);assert(shown_ai()==DG_AI_ALL);
 tap(50,95);assert(shown_ai()==DG_AI_ALL && cursor_row==3);
 tap(130,102);assert(shown_ai()==DG_AI_ALL && cursor_row==3);
 tap(130,81);assert(shown_ai()==DG_AI_ALL && cursor_row==2);
 assert(flag_writes==writes);tap(149,180);close_page();
 assert(flag_on && !flag_key && flag_writes==writes+2 && *opts==0x4144);
 /* Page 1 Confirm commits the TRAINER AI draft with the ordinary drafts; B cancels both. */
 writes=flag_writes;
 open_page(0);input(256);for(unsigned n=0;n<3;++n)input(128);input(32);assert(shown_ai()==DG_AI_KEY);
 input(512);input(2);close_page();assert(flag_on && !flag_key && flag_writes==writes);
 open_page(0);input(256);for(unsigned n=0;n<3;++n)input(128);input(32);input(512);tap(149,180);close_page();
 assert(flag_on && flag_key && flag_writes==writes+2);
 /* Flags changed under the page: Apply is refused on the page and at exit,
  * and neither the flags nor the Options word is written. */
 flag_on=1;flag_key=0;writes=flag_writes;
 open_page(1);input(16);for(unsigned n=0;n<3;++n)input(128);input(16);
 flag_key=1;tap(149,180);assert(!(W32(data,0x10)&3));input(2);close_page();
 assert(flag_writes==writes && flag_on && flag_key && *opts==0x4144);
 flag_key=0;open_page(1);input(16);for(unsigned n=0;n<3;++n)input(128);input(16);tap(149,180);
 assert((W32(data,0x10)&3)==1);flag_on=0;close_page();
 assert(flag_writes==writes && !flag_on && !flag_key && *opts==0x4144 && dg_menu_last_apply_result()==-2);
 /* The Options word changed after Apply: its STALE result also blocks the flags. */
 open_page(1);for(unsigned n=0;n<3;++n)input(128);input(16);tap(149,180);
 assert((W32(data,0x10)&3)==1);*opts^=8;close_page();
 assert(flag_writes==writes && !flag_on && !flag_key && dg_menu_last_apply_result()==-2);
 *opts^=8;
 assert(nav_created==nav_removed);
 int old_rows=normal_rows,old_draw=normal_draw,old_input=normal_input,old_exit=normal_exit;
 open_page(0);input(16);assert(dg_menu_exit_animation(data)==17);close_page();
 assert(normal_rows==old_rows+1 && normal_draw==old_draw+1 && normal_input==old_input+1 && normal_exit==old_exit+1);
 int reads=flag_reads;
 fail_alloc=1;open_page(1);close_page();assert(flag_reads==reads); /* Fallback never reads the flags. */assert(normal_rows==old_rows+2 && normal_draw==old_draw+2 && normal_exit==old_exit+2);
 assert(native_choices>0);
 printf("PASS 524288 codec cases; halfword guard page; transaction invalid/stale/no-op; 8 draft/apply patterns; input/touch/cancel/hidden-row/cleanup/fallback ABI mocks; TRAINER AI codec, 4 flag states x 3 exits (canonical stray pair), D-pad/touch/shared-confirm/stale flag writes. Native UI acceptance NOT claimed.\n");
}
