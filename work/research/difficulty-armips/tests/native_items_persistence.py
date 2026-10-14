#!/usr/bin/env python3
"""Authentic ALL Hyper Potion (an addition; Potion is allowed in DEFAULT) -> native KO -> Options -> restricted trainer Bag.

No remembered-input injection, state reload, or player/inventory reset between battles.
Parent alone launches this supervised diagnostic.
"""
import argparse
from copy import deepcopy
import hashlib
import os
from pathlib import Path
import sys
import traceback
from support import ROOT, OUTPUT, sha256, RECEIPT
from evidence import write_json, utc
from native_ui import candidate_binding
from native_battle_helpers import NativeSession, registers, capture_failure
from native_battle_oracles import require
from native_battle_input import BattleInput
from native_items_fixture import prepare, install_player, install_enemy_at_launch, TRAINER
from native_items_trace import ram_pointer, mon_state, read_inventory
from native_items_gates_trace import GateTrace
from native_items_oracles import events, trainer_entry
from native_items_cases import CASES, GATE_ITEM


class PersistenceTrace(GateTrace):
    def __init__(self,s,run):
        super().__init__(s,run)
        s.hook(0x02076E90,self.remember_set)
        s.hook(0x021EC250,self.remember_check,overlay=9)
        s.hook(0x02214D14,lambda:self.event('teardown'))
        s.hook(s.labels['dg_battle_root_free']&~1,self.root_free)
        s.hook(0x02224BF8,self.award)

    def remember_set(self):
        r=registers(self.h);p=ram_pointer(r[0],0x24,'native Bag cursor')
        row=self.event('remember_set',cursor=p,item=r[1],category=r[2])
        self.s.returned(lambda:row.update(stored_item=self.h.u16(p+0x1e),stored_category=self.h.u16(p+0x20)))

    def remember_check(self):
        ui=ram_pointer(registers(self.h)[0],4,'remembered UI');a=ram_pointer(self.h.u32(ui),0x30,'remembered args')
        row=self.event('remember_check',ui=ui,before=self.args(a),raw_before=self.h.read(a,0x30).hex())
        self.s.returned(lambda:row.update(result=registers(self.h)[0],after=self.args(a),
            raw_after=self.h.read(a,0x30).hex()),overlay=9)

    def root_free(self):
        row=self.event('root_free',root=registers(self.h)[0],before=self.snapshot())
        self.s.returned(lambda:row.update(after=self.snapshot()))

    def award(self):
        if registers(self.h)[0]==0x1f:
            root=self.snapshot()['root']
            self.event('award_actor',actor=mon_state(self.h,self.h.u32(root+0x1d4)),
                       enemy=mon_state(self.h,self.h.u32(root+0x1d0+4*13)))


def fixture(receipt,out):
    from emu_harness import encode_pokemon
    import save_core
    from ndspy.rom import NintendoDSRom
    from ndspy.narc import NARC
    f=prepare(receipt,out,GATE_ITEM)
    moves=NARC(NintendoDSRom.fromFile(receipt['output']['path']).getFileByName('a/0/1/1')).files
    pp=[moves[82][6],moves[150][6],0,0]
    require(pp==[10,40,0,0],'candidate Dragon Rage/Splash PP changed')
    f['metadata']['move_payloads']={str(i):list(moves[i]) for i in (82,150)}
    f['damaged']=encode_pokemon(f['damaged'],moves=[82,150,0,0],pp=pp)
    enemy=encode_pokemon(f['healthy'],currentHp=1)
    for name,raw in (('damaged',f['damaged']),('persistence-enemy',enemy)):
        decoded=save_core.request('decodePokemon',raw,diagnostic=False)
        require(decoded['flags']==0 and decoded['checksumOk'] and not decoded['isEgg'],'invalid persistence typed record')
        p=out/(name+'.bin');p.write_bytes(raw)
        f['metadata'][name]=dict(path=str(p),sha256=sha256(p),decoded=decoded)
    f['metadata']['purpose']='First-entry only: actor HP1 Dragon Rage/Splash; enemy HP1 Splash. No later player/inventory reset.'
    # Replace the original damaged metadata row with its actual final input.
    f['metadata']['records'][0]=f['metadata']['damaged']
    write_json(out/'items-fixture.json',f['metadata']);write_json(f['battery'].parent/'provenance.json',f['metadata'])
    return f,dict(f,healthy=enemy)


def field_state(h):
    import save_core
    require(h.in_field(),'field state requested during battle')
    p=ram_pointer(h.array(2),8+236*6,'field party')
    require(h.u32(p)==6 and h.u32(p+4)==3,'field party shape changed')
    raw=[h.read(p+8+i*236,236) for i in range(3)]
    decoded=[save_core.request('decodePokemon',x,diagnostic=False) for x in raw]
    require(all(x['flags']==0 and x['checksumOk'] and not x['isEgg'] for x in decoded),'invalid closed field party')
    return dict(party=p,hashes=[hashlib.sha256(x).hexdigest() for x in raw],decoded=decoded,
                inventory=read_inventory(h,h.array(3),GATE_ITEM))


def potion_oracle(run):
    trainer_entry(run)
    before,after=run['before'],run['after_potion'];expected=deepcopy(before)
    require(before['quantity']==3 and before['mons']['1']['hp']==1 and before['mons']['13']['hp']==1,
            'wrong persistence HP/quantity inputs')
    expected['mons']['1']['hp']=min(before['mons']['1']['maxhp'],before['mons']['1']['hp']+CASES[GATE_ITEM]['healing'])
    expected['mons']['13']['pp'][0]-=1;expected['mons']['13']['original_pp'][0]-=1
    expected['quantity']=2;bag=bytearray.fromhex(expected['bag']);at=expected['item_offset']+2
    bag[at:at+2]=(2).to_bytes(2,'little');expected['bag']=bag.hex()
    require(after==expected,'native Hyper Potion did not produce exact HP/Bag/enemy PP effect')
    for name in ('accept','commit_item','commit_target','command','effect','consume','outcome','remember_set'):
        require(len(events(run,name))==1,'missing/duplicate native Hyper Potion '+name)
    effect=events(run,'effect')[0];outcome=events(run,'outcome')[0];consume=events(run,'consume')[0]
    require(effect['item']==GATE_ITEM and effect['actor']['id']==1 and effect['target_id']==1 and
            outcome['words']==[0,1,0] and consume['item']==GATE_ITEM and consume['owner']==0,'wrong Potion actor/target/consume')
    command=events(run,'command')[0];encoded=bytes.fromhex(command['after'])
    require(command['item']==GATE_ITEM and command['target']==1 and len(encoded)==12 and
            int.from_bytes(encoded[:4],'little')==GATE_ITEM*16+2 and int.from_bytes(encoded[4:8],'little')==1,
            'wrong native item command')
    remembered=events(run,'remember_set')[0]
    require(remembered['item']==remembered['stored_item']==GATE_ITEM and
            remembered['category']==remembered['stored_category']==0,'Potion was not remembered by native setter')
    require([(e['actor']['id'],e['move']) for e in events(run,'action')]==[(13,150)],'Potion used wrong turn')


def validate(result):
    first,second=result['battles'];potion_oracle(dict(first,events=first['events'][:first['potion_event_count']]))
    require(not any(events(r,n) for r in (first,second) for n in ('fault_input','remembered_fault_input','exception')),
            'authentic persistence contains fault input/exception')
    moves=events(first,'move_verified');require(len(moves)==1 and moves[0]['actor']==1 and moves[0]['move']==82,
        'native KO input not verified')
    require(events(first,'award_actor') and all(e['enemy']['hp']==0 for e in events(first,'award_actor')),
            'opponent KO not observed natively')
    frees=events(first,'root_free')
    require(len(frees)==1 and events(first,'teardown') and frees[0]['root']==first['before']['snapshot']['root'] and
            frees[0]['after']['epoch']==0,'native battle teardown/invalidation missing')
    boundary=result['boundary']
    require(boundary['after_ko']==boundary['after_options']==boundary['before_second'] and
            boundary['snapshot']['epoch']==0,'party/inventory changed across field Options/second entry')
    require(boundary['after_ko']['inventory']['quantity']==2,'native field Bag did not retain consumed Potion')
    ctor=events(second,'constructor');caps=events(second,'captured')
    require(len(ctor)==len(caps)==len(events(second,'begin'))==1,'second native entry missing')
    cap=caps[0];c=cap['context'];snap=cap['snapshot']
    require(ctor[0]['lr'] in (0x020507AD, 0x02048EEF) and ctor[0]['flags']==c['flags']==1 and
            ctor[0]['control']==c['control']==0 and c['setup']==ctor[0]['setup']==cap['setup_owner'] and
            c['save']==c['published_save']==cap['save_owner'] and c['save']!=0,'second native constructor/owner mismatch')
    require(snap['allowed']==1 and snap['flags']==0 and snap['epoch']==cap['generation']>
            first['before']['snapshot']['epoch'] and c['options_copy']==second['options']['after'],
            'second entry did not capture new restricted settings/lifetime')
    require(second['before']==second['after'] and second['before']['quantity']==2 and
            second['before']['bag']==boundary['before_second']['inventory']['bag'],'second Bag open/cancel changed state')
    require(second['player_backing_hashes']==boundary['before_second']['hashes'],
            'second native player party is not the carried field party')
    require(second['command_before']==second['command_after'],'second Bag changed actor/command/slot')
    checks=events(second,'remember_check');wrappers=events(second,'remembered')
    require(len(checks)==len(wrappers)==1,'second remembered native check missing/duplicate')
    ck,w=checks[0],wrappers[0]
    require(ck['before']['remembered']==w['item']==GATE_ITEM and w['quantity']==1 and w['result']==ck['result']==0 and
            ck['after']['remembered']==0 and ck['before']['bag']==w['bag']==second['before']['bag_address'],
            'authentic remembered Hyper Potion was not natively denied')
    raw=bytearray.fromhex(ck['raw_before']);raw[0x1b:0x1e]=bytes(3)
    require(bytes(raw)==bytes.fromhex(ck['raw_after']),'remembered native clear changed other args')
    require(events(second,'lists') and all(not any(x['item']==GATE_ITEM for ls in e['lists'] for x in ls) and
            e['args']['remembered']==0 for e in events(second,'lists')),'Hyper Potion leaked into restricted list/shortcut')
    for name in ('accept','commit_target','command','effect','consume','outcome','action','remember_set','enemy_fixture','player_fixture'):
        require(not events(second,name),'unexpected second-battle '+name)


def play(s,t,result,flush,installed,token):
    from emu_harness import BATTLE_BUTTONS,PARTY_SLOTS
    h=s.h;first=result['battles'][0]
    def point(name):s.checkpoint(name,result);flush()
    require(h.wait_screen('battle_menu',1800),'first trainer menu absent');trainer_entry(first)
    require(len(installed)==1,'first pre-entry enemy fixture not applied')
    # No fixture callback survives into the second native construction.
    s.callbacks[0x0204FCE4].remove(token)
    first['before']=t.state();point('first-menu')
    s.touch(*BATTLE_BUTTONS['bag'],after=180);point('first-bag')
    require(events(first,'lists')[-1]['lists'][0]==[dict(item=GATE_ITEM,quantity=3)],'actual Potion list changed')
    s.touch(64,40,after=90);s.touch(64,32,after=60);s.touch(100,170,after=180)
    mapping=t.party_mapping();binding=t.actor_binding()
    choices=[e for e in mapping['entries'] if e['id']==1 and e['mon']==binding['ui'] and
             e['source_sha256']==e['copy_sha256']==binding['ui_backing_sha256']]
    require(len(choices)==1,'Potion UI target does not resolve to actor');point('first-party')
    s.touch(*PARTY_SLOTS[choices[0]['ui_slot']],after=120)
    for elapsed in range(0,2400,15):
        h.step(15)
        if events(first,'effect') and h.on_screen('battle_menu'):break
        if elapsed%120==105:s.press('A',after=0)
    else:raise AssertionError('native Hyper Potion turn did not finish')
    first['after_potion']=t.state();first['potion_event_count']=len(first['events']);potion_oracle(first);point('first-potion-used')
    require(BattleInput(s,t,first).move(0,82,1,'remembered-ko')=='field','native Dragon Rage did not finish trainer')
    h.step(180);result['boundary']=dict(after_ko=field_state(h),snapshot=t.snapshot());point('field-after-ko')
    options=s.options(0);result['boundary']['after_options']=field_state(h);point('field-restricted')
    second=dict(name='remembered-restricted',flags=0,item=GATE_ITEM,events=[],options=options)
    result['battles'].append(second);t.run=second;t.controller=None
    result['boundary']['before_second']=field_state(h)
    h.trainer_battle(TRAINER)
    require(h.wait_screen('battle_menu',1800),'second native trainer menu absent')
    second['before']=t.state()
    second['player_backing_hashes']=[hashlib.sha256(h.read(ram_pointer(h.u32(
        second['before']['mons'][str(i)]['address']+0x10),236,'second backing'),236)).hexdigest() for i in (1,2,3)]
    point('second-menu')
    s.touch(*BATTLE_BUTTONS['bag'],after=180);point('second-bag')
    second['command_before']=t.command_state()
    s.touch(236,170,after=180)
    require(h.wait_screen('battle_menu',600),'restricted Bag Back did not return')
    second['command_after']=t.command_state();second['after']=t.state();point('second-returned')
    validate(result)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    a=p.parse_args();out=a.out.resolve()
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize or not out.is_relative_to(OUTPUT):p.error('repo root/owned output/assertions required')
    out.mkdir(parents=True,exist_ok=True)
    first=dict(name='remembered-all',flags=4,item=GATE_ITEM,events=[])
    result=dict(status='running',driver='native_items_persistence.py',layer='native ARM gameplay remembered persistence',
        nonce=os.environ.get('DG_TEST_NONCE'),old_state_loaded=False,started_utc=utc(),cases={},battles=[first],
        scope='Authentic valid Potion persistence slice; malformed IDs separately required for broad acceptance')
    def flush():write_json(out/'result.json',result)
    flush()
    try:
        receipt,binding=candidate_binding(a.receipt);result['binding']=binding
        f,enemy=fixture(receipt,out);result['fixture']=f['metadata'];flush()
        from emu_harness import Harness
        os.environ['SDL_AUDIODRIVER']='dummy'
        with Harness(rom=Path(receipt['output']['path']),sav=f['battery'],out=out,verbose=False,emulator='desmume') as h,capture_failure(h,out):
            s=NativeSession(h,receipt,out);t=PersistenceTrace(s,first);result['inputs']=s.inputs
            s.boot();first['options']=s.options(4);install_player(s,t,f)
            installed=install_enemy_at_launch(s,t,enemy)
            token=s.callbacks[0x0204FCE4][-1]
            h.trainer_battle(TRAINER)
            play(s,t,result,flush,installed,token);s.resident()
            write_json(out/'persistence-trace.json',result)
            artifacts=[out/'persistence-trace.json',out/'items-fixture.json',out/'persistence-enemy.bin',
                       out/'damaged.bin',out/'enemy-native-before.bin']
            artifacts += [out/(name+'.png') for name in ('first-menu','first-potion-used','field-after-ko','field-restricted','second-menu','second-bag','second-returned')]
            result['checkpoint_artifacts']=[dict(path=str(x),sha256=sha256(x)) for x in artifacts]
            result.update(status='passed',checkpoint='passed')
    except BaseException:result.update(status='failed',failure=traceback.format_exc())
    finally:result['finished_utc']=utc();flush()
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
