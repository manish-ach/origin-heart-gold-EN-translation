#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "items.h"
#include "policy.h"
#include "masks.h"
#define BASE 0x02000000u
#define ROOT 0x02010000u
#define SETUP 0x02011000u
#define BAG 0x02012000u
#define TRAINER_INFO 0x02013000u
#define UI 0x02014000u
#define ARGS 0x02016000u
#define CTRL 0x02017000u
#define TARGET 0x02018000u
static unsigned char ram[0x400000], before[0x400000];
static DG_GrowthSnapshot snap;
static int present;
static unsigned attrs,counts,accepts,writes,last_item,last_attr,last_heap;
static unsigned count_result,accept_result;
static unsigned effect_original=1;
static size_t off(uintptr_t p,unsigned n){assert(p>=BASE && p<=BASE+sizeof ram-n);return p-BASE;}
uint8_t dg_items_test_read8(uintptr_t p){return ram[off(p,1)];}
uint16_t dg_items_test_read16(uintptr_t p){unsigned i=off(p,2);return ram[i]|ram[i+1]<<8;}
uint32_t dg_items_test_read32(uintptr_t p){unsigned i=off(p,4);return ram[i]|ram[i+1]<<8|ram[i+2]<<16|(uint32_t)ram[i+3]<<24;}
static void set32(uintptr_t p,uint32_t v){unsigned i=off(p,4);for(unsigned j=0;j<4;j++)ram[i+j]=v>>(j*8);}
void dg_items_test_write8(uintptr_t p,uint8_t v){ram[off(p,1)]=v;writes++;}
void dg_items_test_write16(uintptr_t p,uint16_t v){unsigned i=off(p,2);ram[i]=v;ram[i+1]=v>>8;writes++;}
const DG_GrowthSnapshot *dg_growth_snapshot(void){return present?&snap:0;}
uint32_t dg_items_test_native_attr(uint32_t i,uint32_t a,uint32_t h){assert(i>=1&&i<=790);attrs++;last_item=i;last_attr=a;last_heap=h;return a==13?masks[i]:(a==38?effect_original:0x91);}
uint32_t dg_items_test_native_count(void *b,uint32_t i,uint32_t q,uint32_t h){assert((uintptr_t)b==BAG&&q==1&&h==5&&i>0&&i<=790);counts++;return count_result;}
uint32_t dg_items_test_native_accept(void *u){assert((uintptr_t)u==UI);accepts++;return accept_result;}
static void seed(unsigned item){dg_items_test_write16(ARGS+0x18,item);dg_items_test_write8(ARGS+0x1a,2);writes=0;attrs=counts=accepts=0;}
static void reset(void){memset(ram,0,sizeof ram);set32(0x02255bac,ROOT);set32(ROOT+0x10,SETUP);set32(SETUP,1);set32(SETUP+0x108,BAG);set32(SETUP+0xf8,TRAINER_INFO);set32(UI,ARGS);set32(ARGS,TRAINER_INFO);set32(ARGS+4,BAG);set32(ARGS+8,5);set32(CTRL+0x5c8,ARGS);set32(CTRL+0x584,0x02019000);set32(CTRL+0x588,0x0201a000);ram[CTRL-BASE+0x599]=1;memset(ram+0x1a000,0xa5,24);snap=(DG_GrowthSnapshot){0,42,1,ROOT,1};present=1;count_result=7;accept_result=9;seed(17);}
static unsigned expanded(unsigned i){switch(i){case 18:case 19:case 20:case 21:case 22:case 27:case 42:case 54:return 8;case 23:return 12;case 24:case 25:case 28:case 29:case 34:case 35:case 37:return 4;case 38:case 39:case 40:case 41:return 16;default:return 0;}}
static unsigned expected(unsigned i,unsigned flags){if(!i||i>790)return 0;return flags&4?masks[i]|expanded(i):masks[i];}
static void only_cancel(void){for(unsigned i=0;i<sizeof ram;i++)if(i!=ARGS-BASE+0x18&&i!=ARGS-BASE+0x19&&i!=ARGS-BASE+0x1a)assert(before[i]==ram[i]);assert(dg_items_test_read16(ARGS+0x18)==0&&dg_items_test_read8(ARGS+0x1a)==4);}

#define MON1 0x02020000u
#define MON2 0x02021000u
static void bind_mon(uint32_t mon,unsigned id) {
 ram[mon-BASE+0x14]=(unsigned char)id;
 set32(ROOT+0x1d0+4*id,mon);
}
static unsigned effect(unsigned item,unsigned attr,uintptr_t actor,uintptr_t target) {
 return dg_bag_effect_attr(item,attr,5,(void*)actor,(void*)target);
}
static void effect_reset(void) {
 reset();snap.flags=4;effect_original=1;
 bind_mon(MON1,1);bind_mon(MON2,2);
}
static void revival_checks(void) {
 effect_reset();
 /* Exhaustive item/option gate, not a second implementation of native effects. */
 for(unsigned flags=0;flags<8;flags++) {
  snap.flags=flags;
  for(unsigned item=0;item<65536;item++) {
   unsigned old=attrs;
   unsigned want=item>=1&&item<=790;
   if((flags&4)&&(item==28||item==29||item==37))want=0;
   assert(effect(item,38,MON1,MON2)==want);
   assert(attrs-old==(item>=1&&item<=790));
  }
 }
 assert(effect(0xffffffffu,38,MON1,MON2)==0);
 /* All native attrs except redundant HP preserve original return, including
  * revival23 and quantity54, in all eight flag settings. */
 for(unsigned flags=0;flags<8;flags++)for(unsigned attr=0;attr<=58;attr++) {
  snap.flags=flags;
  for(unsigned i=0;i<3;i++) {
   unsigned item=(unsigned[]){28,29,37}[i];
   unsigned want=attr==13?masks[item]:attr==38?((flags&4)?0:1):0x91;
   assert(effect(item,attr,MON1,MON2)==want);
  }
 }
 /* Both local doubles actors and every local bench/active recipient. */
 for(unsigned actor=1;actor<=6;actor++)for(unsigned target=1;target<=6;target++) {
  effect_reset();bind_mon(MON1,actor);
  if(actor!=target)bind_mon(MON2,target);
  uintptr_t to=actor==target?MON1:MON2;
  assert(effect(28,38,MON1,to)==0);
 }
 for(unsigned mode=0;mode<22;mode++) {
  effect_reset();uintptr_t actor=MON1,target=MON2;
  switch(mode) {
  case 0:present=0;break;case 1:snap.epoch=0;break;
  case 2:snap.allowed=0;break;case 3:snap.flags=12;break;
  case 4:snap.root+=4;break;case 5:set32(0x02255bac,0);break;
  case 6:set32(ROOT+0x10,0);break;case 7:set32(SETUP,0);break;
  case 8:set32(SETUP,0x81);break;case 9:set32(SETUP,0x401);break;
  case 10:bind_mon(MON1,13);break;case 11:bind_mon(MON2,7);break;
  case 12:bind_mon(MON1,0);break;case 13:bind_mon(MON2,25);break;
  case 14:set32(ROOT+0x1d4,MON1+4);break;
  case 15:set32(ROOT+0x1d8,MON2+4);break;
  case 16:actor=0;break;case 17:target=MON2+1;break;
  case 18:actor=0x023dc000;break;case 19:target=0x023dbfe4;break;
  case 20:set32(ROOT+0x10,0x023dbf00);break;
  case 21:snap.root=0x023dbf00;set32(0x02255bac,snap.root);break;
  }
  assert(effect(28,38,actor,target)==1);
 }
 /* A bound mon is accepted up to the advanced AI's code at 0x023D4000 and
  * refused inside it (0x023D4000..0x023DC000), where the old bound accepted it. */
 for(unsigned n=0;n<4;n++) {
  uintptr_t mon=(uintptr_t[]){0x023d3fe0,0x023d3fe4,0x023d4000,0x023dbfe0}[n];
  effect_reset();bind_mon(mon,2);
  assert(effect(28,38,MON1,mon)==(n==0?0:1));
 }
 /* Scope bound follows provider on each call: no stale/pending token survives
  * invalidation, same-address root reuse, or an interleaved NPC operation. */
 effect_reset();assert(effect(28,38,MON1,MON2)==0);
 snap.epoch=0;assert(effect(28,38,MON1,MON2)==1);
 snap.epoch=3;snap.flags=0;assert(effect(28,38,MON1,MON2)==1);
 snap.flags=4;bind_mon(MON1,13);assert(effect(28,38,MON1,MON2)==1);
 bind_mon(MON1,1);assert(effect(28,38,MON1,MON2)==0);
 effect_original=0;assert(effect(28,38,MON1,MON2)==0);
 /* Read-only filter even after full HP: do not hide an extra callback by
  * relying on maxHP clipping. Neither HP, pending commands nor queues change. */
 for(unsigned item=28;item<=37;item++)if(item==28||item==29||item==37) {
  effect_reset();dg_items_test_write16(MON2+0x1e,item==28?15:31);
  memcpy(before,ram,sizeof ram);unsigned oldwrites=writes;
  assert(effect(item,23,MON1,MON2)==0x91);
  assert(effect(item,38,MON1,MON2)==0);
  assert(writes==oldwrites&&!memcmp(before,ram,sizeof ram));
 }
}

int main(void){
 revival_checks();
 /* Reproduce both source-bound frame5503 fixtures from candidate bb625d52.
  * +108 is the cloned battle Bag; +168 is zero; +F8 is TrainerInfo.
  * Keep literal offsets independent of shipping constants to catch regressions.
  */
 const uint32_t captured[2][6] = {
  {36441908u,36349884u,36360736u,36351872u,36494332u,36494252u},
  {36441988u,36349964u,36360816u,36351952u,36494412u,36494332u}
 };
 for(unsigned fixture=0;fixture<2;fixture++) {
  reset();const uint32_t *p=captured[fixture];
  snap.root=p[0];set32(0x02255bac,p[0]);set32(p[0]+0x10,p[1]);
  set32(p[1],1);set32(p[1]+0x108,p[2]);set32(p[1]+0xf8,p[3]);
  set32(p[4],p[5]);set32(p[5],p[3]);set32(p[5]+4,p[2]);set32(p[5]+8,5);
  assert(dg_items_test_read32(p[1]+0x168)==0);
  for(unsigned flags=0;flags<8;flags++) {
   snap.flags=flags;
   assert(dg_bag_item_attr(17,13,5,(void*)(uintptr_t)p[4])==4u);
   assert(dg_bag_item_attr(18,13,5,(void*)(uintptr_t)p[4])==((flags&4)?8u:0u));
  }
 }
 reset();set32(SETUP+0x168,BAG+4);
 for(unsigned flags=0;flags<8;flags++){
  snap.flags=flags;
  for(unsigned i=0;i<65536;i++){
   unsigned a=attrs;assert(dg_bag_item_attr(i,13,5,(void*)UI)==expected(i,flags));assert(attrs-a==(i>0&&i<=790));
  }
 }
 assert(dg_bag_item_attr(0xffffffffu,13,5,(void*)UI)==0);
 assert(dg_bag_item_attr(17,7,123,(void*)UI)==0x91&&last_item==17&&last_attr==7&&last_heap==123);
 for(unsigned mode=0;mode<22;mode++){
  reset();snap.flags=4;
  switch(mode){case 0:present=0;break;case 1:snap.epoch=0;break;case 2:snap.allowed=0;break;case 3:snap.flags=8;break;case 4:snap.root+=4;break;case 5:set32(0x02255bac,0);snap.root=0;break;case 6:set32(ROOT+0x10,0);break;case 7:set32(ROOT+0x10,0x023ffffc);break;case 8:set32(SETUP,0);break;case 9:set32(SETUP,0x81);break;case 10:set32(SETUP,0x401);break;case 11:set32(ARGS+0xc,1);break;case 12:set32(ARGS+0x10,1);break;case 13:set32(ARGS,TRAINER_INFO+4);break;case 14:set32(SETUP+0x108,BAG+4);break;case 15:set32(0x02255bac,ROOT+1);snap.root=ROOT+1;break;case 16:set32(SETUP+0x108,0);break;case 17:set32(SETUP+0x108,BAG+1);break;case 18:set32(SETUP+0x108,0x023ffffc);set32(ARGS+4,0x023ffffc);break;case 19:set32(SETUP+0xf8,0);break;case 20:set32(SETUP+0xf8,TRAINER_INFO+1);break;case 21:set32(SETUP+0xf8,0x023ffffc);set32(ARGS,0x023ffffc);break;}
  for(unsigned i=1;i<=790;i++)assert(dg_bag_item_attr(i,13,5,(void*)UI)==masks[i]);
  seed(17);assert(dg_bag_accept((void*)UI)==9&&accepts==1&&attrs==0&&writes==0);
  assert(dg_bag_remembered((void*)BAG,17,1,5,(void*)UI)==7&&counts==1);
  assert(dg_bag_commit_item((void*)ARGS)==17&&writes==0);
  assert(dg_bag_commit_target((void*)CTRL,(void*)TARGET)==0&&writes==0);
 }
 reset();
 for(unsigned flags=0;flags<8;flags++)for(unsigned item=1;item<=791;item++){
  snap.flags=flags;seed(item);unsigned allow=expected(item,flags)!=0;
  assert(dg_bag_accept((void*)UI)==(allow?9:13));assert(accepts==allow);assert(attrs==(item<=790));
  seed(item);assert(dg_bag_remembered((void*)BAG,item,1,5,(void*)UI)==(allow?7:0));assert(counts==(item<=790));
  seed(item);assert(dg_bag_commit_item((void*)ARGS)==(allow?item:0));
  seed(item);assert(dg_bag_commit_target((void*)CTRL,(void*)TARGET)==(allow?0:6));
 }
 reset();count_result=0;assert(dg_bag_remembered((void*)BAG,149,1,5,(void*)UI)==0&&attrs==0&&counts==1);
 reset();seed(18);memcpy(before,ram,sizeof ram);assert(dg_bag_accept((void*)UI)==13);only_cancel();
 reset();seed(18);memcpy(before,ram,sizeof ram);assert(dg_bag_commit_item((void*)ARGS)==0);only_cancel();
 reset();seed(18);memcpy(before,ram,sizeof ram);assert(dg_bag_commit_target((void*)CTRL,(void*)TARGET)==6);only_cancel();
 reset();ram[TARGET-BASE+0xd]=6;assert(dg_bag_commit_target((void*)CTRL,(void*)TARGET)==6&&writes==0&&attrs==0);
 reset();ram[CTRL-BASE+2]=1;assert(dg_bag_commit_target((void*)CTRL,(void*)TARGET)==0&&writes==0&&attrs==0);
 for(unsigned i=0;i<2;i++){reset();seed(i?65535:0);assert(dg_bag_accept((void*)UI)==13&&attrs==0&&accepts==0);seed(i?65535:0);assert(dg_bag_remembered((void*)BAG,i?65535:0,1,5,(void*)UI)==0&&attrs==0&&counts==0);}
 /* Category capacity from actual CN metadata, independent bit->category map. */
 for(unsigned mode=0;mode<3;mode++){unsigned totals[5]={0};unsigned map[5]={2,3,0,1,0};for(unsigned i=1;i<=790;i++){unsigned m=mode==0?masks[i]:expected(i,mode==1?4:0);assert((m&20)!=20);for(unsigned b=0;b<5;b++)if(m&(1u<<b))totals[map[b]]++;}const unsigned want[3][5]={{11,10,25,10,0},{23,19,25,10,0},{11,10,25,10,0}};assert(!memcmp(totals,want[mode],sizeof totals));}
 puts("PASS shipping C: 524288 list cases, all item/flag gates, native delegation, context fallbacks, cancel-only writes, sentinels, inventory, CN category capacities; 524288 revival attribute gates, local/foreign identities, read-only lifecycle checks");
}
