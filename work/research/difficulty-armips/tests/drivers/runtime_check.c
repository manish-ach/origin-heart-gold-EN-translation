#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "runtime.h"
#include "caps.h"
#include "settings.h"
static uint8_t ram[0x400000];
static uintptr_t save=0x02280000, root=0x02300000, setup=0x02301000, opts=0x02280100;
static uint32_t badges,erika,clair,begins,frees,reads;
static void w32(uintptr_t p,uint32_t n){memcpy(ram+(p-0x02000000),&n,4);}
static void w16(uintptr_t p,uint16_t n){memcpy(ram+(p-0x02000000),&n,2);}
uint32_t dg_runtime_test_read32(uintptr_t p){uint32_t v;assert(p>=0x02000000 && p<=0x023ffffc);memcpy(&v,ram+(p-0x02000000),4);return v;}
uint16_t dg_runtime_test_read16(uintptr_t p){uint16_t v;assert(p>=0x02000000 && p<=0x023ffffe);memcpy(&v,ram+(p-0x02000000),2);return v;}
uintptr_t dg_runtime_test_save(void){return save;}
uintptr_t dg_runtime_test_options(uintptr_t s){assert(s==save);return opts;}
void dg_runtime_test_begin(void){++begins;w32(0x02255bac,root);w32(root+0x10,setup);}
uintptr_t dg_runtime_test_free(void *p){assert((uintptr_t)p==root);assert(!dg_growth_snapshot());++frees;return 0x12345678;}
uintptr_t dg_caps_test_profile(uintptr_t s){assert(s==save);return 0x02290000;}
uintptr_t dg_caps_test_vars(uintptr_t s){assert(s==save);return 0x02291000;}
uint32_t dg_caps_test_badge(uintptr_t p,uint32_t i){assert(p==0x02290000 && i<16);++reads;return badges&(1u<<i);}
uint32_t dg_caps_test_flag(uintptr_t p,uint32_t i){assert(p==0x02291000 && (i==1220 || i==209));++reads;return i==1220?erika:clair;}
static void fixture(uint32_t flags,uint32_t control,uint32_t policy){
 w32(setup,flags);w32(setup+0x18c,control);w32(setup+0x1c0,save);w32(setup+0x130,opts+2);
 w16(opts,dg_settings_merge(4,policy));w16(opts+2,dg_settings_merge(4,policy));
}
int main(void){
 assert(!dg_growth_snapshot());
 /* 0x801 = loss-allowed TrainerBattle (script third operand nonzero). */
 unsigned allowed[]={0,1,3,0x13,0x4a,0x4b,0x100,0x801};
 for(unsigned f=0;f<65536;++f){unsigned want=0;for(unsigned i=0;i<8;++i)want|=f==allowed[i];
  assert(dg_runtime_ordinary(f,0)==want);assert(!dg_runtime_ordinary(f,0x10));assert(!dg_runtime_ordinary(f,1));assert(dg_runtime_ordinary(f,8)==(f==0));}
 /* Exact control whitelist, including replay of scripted wild (8|10h),
  * tutorial/special1, unknown bits, and no expansion to trainer/double8. */
 for(unsigned control=0;control<65536;++control)for(unsigned i=0;i<8;++i)
  assert(dg_runtime_ordinary(allowed[i],control)==(control==0 || (control==8 && i==0)));
 for(unsigned bit=16;bit<32;++bit){
  assert(!dg_runtime_ordinary(0,1u<<bit));assert(!dg_runtime_ordinary(0,8u|(1u<<bit)));
 }
 assert(!dg_runtime_ordinary(0x10000,0));
 unsigned ids[]={0,1,2,3,5,6,4,7,8,9,10,11,13,12,14,15};
 /* Independent explicit policy oracle, not the shipping running-max algorithm. */
 unsigned caps[]={12,20,25,38,55,65,80,100,100,100,100,100,100,100,100,100};
 unsigned transitions=0;
 for(unsigned b=0;b<65536;++b)for(unsigned e=0;e<2;++e)for(unsigned c=0;c<2;++c){
  unsigned expected=100;for(unsigned i=0;i<16;++i){if(!(b&(1<<ids[i])) && !(ids[i]==3 && e) && !(ids[i]==15 && c)){expected=caps[i];break;}}
  unsigned got=dg_cap_resolve(b,e,c);assert(got==expected);
  assert(got>=12 && got<=100);
  /* Each edge of the completion lattice: proves monotonicity for every
   * completion sequence, including out-of-order/skipped gyms. */
  for(unsigned i=0;i<16;++i){assert(dg_cap_resolve(b|(1u<<i),e,c)>=got);++transitions;}
  assert(dg_cap_resolve(b,1,c)>=got);assert(dg_cap_resolve(b,e,1)>=got);transitions+=2;
  /* Flag/badge substitution and nonboolean native flag truthiness. */
  assert(dg_cap_resolve(b,e,c)==dg_cap_resolve(b|(e<<3)|(c<<15),0,0));
  assert(dg_cap_resolve(b,e?0x80000000u:0,c?0xffffffffu:0)==got);
  assert(dg_cap_resolve(b|0xffff0000u,e,c)==got);
  badges=b;erika=e;clair=c;unsigned before=reads;
  assert(dg_cap_for_save(save)==got && reads==before+18);
 }
 assert(transitions==4718592);
 /* Delayed Erika win, flag-to-badge handoff; skipped Koga despite all later
  * badges; gap closure jumps over completed rows. */
 assert(dg_cap_resolve(7,0,0)==38);assert(dg_cap_resolve(7,1,0)==55);
 assert(dg_cap_resolve(15,0,0)==55);
 assert(dg_cap_resolve(0xffffu&~(1u<<5),0,0)==55);
 assert(dg_cap_resolve(0xffff,0,0)==100);
 /* Both former decreases removed; Morty and delayed Clair remain cap100.
  * Clair completion itself needs native flag evidence: cap equality cannot
  * distinguish unfinished from completed at this plateau. */
 assert(dg_cap_resolve(0x7f,0,0)==100);assert(dg_cap_resolve(0xff,0,0)==100);
 assert(dg_cap_resolve(0x3ff,0,0)==100);assert(dg_cap_resolve(0x7ff,0,0)==100);
 assert(dg_cap_resolve(0xffffu&~(1u<<11),0,0)==100);
 assert(dg_cap_resolve(0x7fff,0,0)==100);assert(dg_cap_resolve(0x7fff,0,1)==100);
 badges=erika=clair=0;
 for(unsigned i=0;i<9;++i)for(unsigned p=0;p<8;++p){
  unsigned flags=i==8?0:allowed[i],control=i==8?8:0;
  fixture(flags,0,p);
  /* Native scripted path: constructor returns0, caller ORs8 BEFORE begin.
   * Original begin publishes the root but does not change setup control. */
  w32(setup+0x18c,control);
  unsigned n=begins;dg_battle_begin();assert(begins==n+1);
  const DG_GrowthSnapshot *s=dg_growth_snapshot();assert(s && s->epoch && s->flags==p && s->cap_level==12 && s->root==root);
  unsigned epoch=s->epoch;
  /* Settings/progress and entry control are immutable for this generation. */
  badges=0xffff;w16(opts,0);w32(setup+0x18c,0x10);
  assert(dg_growth_snapshot() && s->flags==p && s->cap_level==12 && s->epoch==epoch);
  assert(dg_battle_root_free((void *)root)==0x12345678 && !dg_growth_snapshot());
  badges=0;fixture(flags,control,p);dg_battle_begin();assert(dg_growth_snapshot()->epoch!=epoch);
 }
 fixture(1,0x10,7);dg_battle_begin();assert(!dg_growth_snapshot());
 fixture(0,0x18,7);dg_battle_begin();assert(!dg_growth_snapshot());
 fixture(0,1,7);dg_battle_begin();assert(!dg_growth_snapshot());
 fixture(0x400,8,7);dg_battle_begin();assert(!dg_growth_snapshot());
 fixture(4,8,7);dg_battle_begin();assert(!dg_growth_snapshot());
 fixture(0x80,8,7);dg_battle_begin();assert(!dg_growth_snapshot());
 /* Loss-allowed 0x801 is accepted only as that exact value with control0:
  * no other 0x800 combination, no control8/replay/special variant. */
 fixture(0x801,8,7);dg_battle_begin();assert(!dg_growth_snapshot());
 fixture(0x801,0x10,7);dg_battle_begin();assert(!dg_growth_snapshot());
 fixture(0x801,1,7);dg_battle_begin();assert(!dg_growth_snapshot());
 {unsigned other[]={0x800,0x802,0x803,0x809,0x811,0x813,0x821,0x841,0x84a,0x84b,0x881,0x900,0x901,0xa01,0xc01,0x1801,0x8801,0x10801};
  for(unsigned i=0;i<sizeof other/sizeof other[0];++i){
   assert(!dg_runtime_ordinary(other[i],0));fixture(other[i],0,7);dg_battle_begin();assert(!dg_growth_snapshot());}}
 fixture(0x801,0,7);dg_battle_begin();assert(dg_growth_snapshot() && dg_growth_snapshot()->flags==7);
 w32(setup,0x1);assert(!dg_growth_snapshot()); /* frozen exact setup flags */
 fixture(1,0,7);w32(setup+0x1c0,save+4);dg_battle_begin();assert(!dg_growth_snapshot());
 fixture(1,0,7);w16(opts+2,0);dg_battle_begin();assert(!dg_growth_snapshot());
 fixture(1,0,7);dg_battle_begin();assert(dg_growth_snapshot());save+=4;assert(!dg_growth_snapshot());save-=4;assert(!dg_growth_snapshot());
 fixture(1,0,7);dg_battle_begin();w32(root+0x10,setup+4);assert(!dg_growth_snapshot());w32(root+0x10,setup);assert(!dg_growth_snapshot());
 fixture(1,0,7);dg_battle_begin();w32(setup,3);assert(!dg_growth_snapshot());
 assert(!dg_runtime_ram(0x23e0000,4,4));assert(!dg_runtime_ram(0xfffffff0,0x100,4));assert(!dg_runtime_ram(0x2000001,4,4));
 assert(!dg_runtime_ram(0x2000000,0xffffffff,4));assert(!dg_runtime_ram(0x2000000,4,3));

 /* Allocation edges, stale pointer restoration, replay with familiar flags,
  * high unknown bits, and original Options bits differing outside policy. */
 assert(dg_runtime_ram(0x02000000,4,4));assert(dg_runtime_ram(0x023d3ffc,4,4));
 assert(dg_runtime_ram(0x02000000,0x003d4000,4));assert(!dg_runtime_ram(0x02000000,0x003d4004,4));
 /* The advanced AI's resident code 0x023D4000..0x023DC000 and difficulty's own reservation are not data. */
 assert(!dg_runtime_ram(0x023d4000,4,4));assert(!dg_runtime_ram(0x023d3ffd,4,1));assert(!dg_runtime_ram(0x023dbffc,4,4));
 assert(!dg_runtime_ram(0x023dc000,4,4));assert(!dg_runtime_ram(0x01fffffc,4,4));
 for(unsigned bit=9;bit<32;bit++)assert(!dg_runtime_ordinary(1u<<bit,0));
 for(unsigned i=0;i<8;i++){fixture(allowed[i],0x10,7);dg_battle_begin();assert(!dg_growth_snapshot());}
 fixture(1,0,7);w16(opts+2,dg_settings_merge(0x5544,7));dg_battle_begin();assert(dg_growth_snapshot());
 unsigned epoch=dg_growth_snapshot()->epoch;w32(0x02255bac,root+4);assert(!dg_growth_snapshot());w32(0x02255bac,root);assert(!dg_growth_snapshot());
 fixture(1,0,7);dg_battle_begin();assert(dg_growth_snapshot()->epoch!=epoch);
 w32(setup+0x1c0,save+4);assert(!dg_growth_snapshot());w32(setup+0x1c0,save);assert(!dg_growth_snapshot());
 fixture(1,0,7);dg_battle_begin();dg_runtime_invalidate();assert(!dg_growth_snapshot());
 assert(reads && frees==72);
 /* Every guide-route transition reaches a fresh native-entry snapshot;
  * progression changes never mutate the currently frozen battle cap. */
 badges=erika=clair=0;
 for(unsigned i=0;i<16;++i){
  fixture(1,0,2);dg_battle_begin();
  const DG_GrowthSnapshot *s=dg_growth_snapshot();assert(s && s->cap_level==caps[i]);
  unsigned old_epoch=s->epoch;badges|=1u<<ids[i];
  assert(dg_growth_snapshot() && s->cap_level==caps[i] && s->epoch==old_epoch);
  dg_battle_begin();s=dg_growth_snapshot();
  assert(s && s->epoch!=old_epoch && s->cap_level==(i==15?100:caps[i+1]));
 }
 dg_runtime_invalidate();
 puts("PASS shipping runtime/caps: 262144 cap states and save-reader cases, 4718592 monotonic completion edges, flag equivalence/skipped gyms/former drops, 262144 flags/control plus 524288 exact control cases, 72 policy/context lifecycles including loss-allowed trainer0x801 and scripted-wild0/8, other0x800 combinations rejected, replay0/18h and special/link/facility negatives, reuse/freeze/invalidation/native-free/bounds negatives");
}
