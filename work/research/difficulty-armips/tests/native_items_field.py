#!/usr/bin/env python3
"""Parent-only original CN/candidate field Revive baseline, no battle acceptance."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
import uuid
from support import ROOT, OUTPUT, CN, CN_SHA256, sha256, RECEIPT
from evidence import write_json, utc, bound_process
from native_items_control import OriginalSession, identity
from native_items_fixture import prepare
from native_battle_helpers import registers, capture_failure
from native_battle_oracles import require
from native_items_trace import ram_pointer, read_inventory
from emu_harness import Harness, FIELD_MENU, POCKET_TABS, BAG_SLOTS, BAG_USE, PARTY_SLOTS


HP_OFFSET=0x8e  # ciphertext byte positions only; never interpret these bytes as HP.
# Strict save-core decrypts the PID-encrypted party tail. Stable PID/key means
# an HP-only edit changes just this ciphertext pair; numeric HP comes from decode.


def sealed_state(h,out,label):
    import save_core
    party=ram_pointer(h.array(2),8+6*236,'field party')
    require(h.u32(party)==6 and h.u32(party+4)==3,'field party allocation/count')
    records=[]
    for slot in range(3):
        address=party+8+236*slot;raw=h.read(address,236)
        path=out/f'{label}-slot{slot}.bin';path.write_bytes(raw)
        mon=save_core.request('decodePokemon',raw,diagnostic=False)
        require(mon['flags']==0 and mon['checksumOk'] and not mon['isEgg'],'field record not sealed/valid; no repair')
        records.append(dict(slot=slot,address=address,raw=raw.hex(),sha256=sha256(path),decoded=mon))
    return dict(party=party,save=h.save,records=records,inventory=read_inventory(h,h.array(3),28))


class FieldTrace:
    def __init__(self,session,run,party):
        self.s,self.h,self.run,self.party=session,session.h,run,party
        self.armed=False
        for address,name in ((0x0209002C,'select'),(0x0208FA50,'apply'),
                             (0x020901C4,'heal'),(0x0206D848,'get_mon'),(0x0206DF70,'set_mon'),(0x02076AA4,'consume')):
            session.hook(address,getattr(self,name))

    def event(self,name,**data):
        require(len(self.run['events'])<200,'field diagnostic event overflow')
        r=registers(self.h)
        row=dict(name=name,frame=self.h.frame,lr=r[14],sp=r[13],**data)
        self.run['events'].append(row);return row

    def get_mon(self):
        if not self.armed:return
        r=registers(self.h)
        if r[0]!=self.party+8+236 or r[1] not in (0xa3,0xa4):return
        row=self.event('field_hp_get',mon=r[0],attr=r[1])
        self.s.returned(lambda:row.update(value=registers(self.h)[0]))

    def select(self):
        if not self.armed:return
        r=registers(self.h)
        if r[1]!=28:return
        row=self.event('field_select',party=r[0],item=r[1],slot=r[2],move_slot=r[3])
        require(r[0]==self.party and r[2]==1,'native field selection used wrong party/slot')
        self.s.returned(lambda:row.update(result=registers(self.h)[0]))

    def apply(self):
        if not self.armed:return
        r=registers(self.h)
        if r[1]!=28:return
        row=self.event('field_apply',mon=r[0],item=r[1],registers=r)
        require(r[0]==self.party+8+236,'native field effect used wrong fainted record')
        self.s.returned(lambda:row.update(result=registers(self.h)[0]))

    def heal(self):
        if not self.armed:return
        r=registers(self.h)
        row=self.event('field_heal',mon=r[0],hp_argument=r[1],maxhp_argument=r[2],amount=r[3])
        require(r[0]==self.party+8+236,'field healing changed another record')
        self.s.returned(lambda:row.update(returned=True))

    def set_mon(self):
        if not self.armed:return
        r=registers(self.h)
        if r[1]!=0xa3:return
        row=self.event('field_hp_set',mon=r[0],value_address=r[2],value=self.h.u16(r[2]))
        require(r[0]==self.party+8+236,'field HP setter changed another record')
        self.s.returned(lambda:row.update(returned=True))

    def consume(self):
        if not self.armed:return
        r=registers(self.h)
        if r[1]!=28:return
        row=self.event('field_consume',bag=r[0],item=r[1],quantity=r[2],heap=r[3])
        self.s.returned(lambda:row.update(result=registers(self.h)[0]))


def observe(run):
    before,after=run['before'],run['after']
    require(before['party']==after['party'] and before['save']==after['save'],'field ownership changed')
    require(len(before['records'])==len(after['records'])==3,'field record count changed')
    target=before['party']+8+236
    for i,(old,new) in enumerate(zip(before['records'],after['records'])):
        require(old['address']==new['address']==before['party']+8+236*i and old['slot']==new['slot']==i,
                'field slot identity changed')
        expected=bytearray.fromhex(old['raw']);actual=bytearray.fromhex(new['raw'])
        require(len(expected)==len(actual)==236,'short field record')
        expected_decoded=copy.deepcopy(old['decoded'])
        if i==1:expected_decoded['party']['currentHp']=new['decoded']['party']['currentHp']
        require(expected_decoded==new['decoded'],'field item changed decoded fields outside selected HP')
        if i==1:expected[HP_OFFSET:HP_OFFSET+2]=actual[HP_OFFSET:HP_OFFSET+2]
        require(expected==actual,'field item changed bytes outside selected HP')
    oldinv,newinv=before['inventory'],after['inventory']
    require(oldinv['bag_address']==newinv['bag_address'] and oldinv['item']==newinv['item']==28 and
            oldinv['item_offset']==newinv['item_offset']==0x5e8 and
            oldinv['quantity']==3 and newinv['quantity']==2,'field inventory identity/consumption mismatch')
    expected=bytearray.fromhex(oldinv['bag']);expected[0x5ea:0x5ec]=(2).to_bytes(2,'little')
    require(len(expected)==0x864 and expected.hex()==newinv['bag'],'unexpected field Bag mutation')
    def ev(name):return [e for e in run['events'] if e['name']==name]
    for name in ('field_select','field_apply','field_consume'):
        require(len(ev(name))==1,'missing/duplicate native '+name)
    selection,apply,consume=(ev(n)[0] for n in ('field_select','field_apply','field_consume'))
    require(selection['party']==before['party'] and selection['slot']==1 and selection['item']==28 and selection['result']==1,
            'field UI did not select fainted bench slot')
    require(apply['mon']==target and apply['item']==28 and apply['result']==1,'native field effect identity/result')
    require(consume['bag']==oldinv['bag_address'] and consume['item']==28 and consume['quantity']==1 and consume['result']==1,
            'native field quantity call mismatch')
    hp=after['records'][1]['decoded']['party']['currentHp']
    maximum=before['records'][1]['decoded']['party']['stats']['hp']
    require(before['records'][1]['decoded']['party']['currentHp']==0 and maximum==31 and 0<hp<=maximum,
            'field baseline must start fainted and end revived')
    heals,sets=ev('field_heal'),ev('field_hp_set')
    require(heals and sets and all(e['mon']==target for e in heals+sets),'native field HP evidence missing/wrong target')
    getters=ev('field_hp_get')
    require(getters and all(e['mon']==target and e['attr'] in (0xa3,0xa4) and 'value' in e for e in getters),
            'missing/wrong native HP getter evidence')
    first_heal=run['events'].index(heals[0])
    initial_getters=run['events'][:first_heal]
    require(any(e['name']=='field_hp_get' and e['attr']==0xa3 and e['value']==0 for e in initial_getters) and
            any(e['name']=='field_hp_get' and e['attr']==0xa4 and e['value']==maximum for e in initial_getters),
            'native getters did not establish fainted HP/maxHP before healing')
    require(heals[0]['hp_argument']==0 and all(e['maxhp_argument']==maximum and e.get('returned') for e in heals),
            'native field heal arguments/return mismatch')
    require(all(e.get('returned') and 0<e['value']<=maximum for e in sets) and sets[-1]['value']==hp,
            'native HP setter argument and final strict decoded HP disagree')
    return dict(initial_hp=0,final_hp=hp,maxhp=maximum,half_hp=maximum//2,
                healing_calls=len(heals),hp_setter_calls=len(sets),quantity_before=3,quantity_after=2,
                battle_equivalence_proven=False,scope='Observed field Revive only; D-2322 not resolved automatically')


def play(session,run,fixture,out,flush):
    h=session.h
    require(h.in_field(),'field baseline must begin in field')
    party=ram_pointer(h.array(2),8+6*236,'field fixture party')
    require(h.u32(party)==6,'field fixture capacity')
    raws=[fixture['healthy'],fixture['damaged'],fixture['healthy']]
    for i,raw in enumerate(raws):h.write(party+8+236*i,raw)
    h.w32(party+4,3)  # input fixture only, before any Bag UI/action
    run['player_fixture']=dict(party=party,frame=h.frame,hashes=[hashlib.sha256(r).hexdigest() for r in raws])
    run['before']=sealed_state(h,out,'before');flush()
    trace=FieldTrace(session,run,party)
    def point(name):session.checkpoint(name,run);flush()
    point('field-before')
    session.touch(*FIELD_MENU['bag'],after=180);point('field-bag')
    session.touch(*POCKET_TABS['medicine'],after=120);point('field-medicine')
    session.touch(*BAG_SLOTS[0],after=90);point('field-item-detail')
    trace.armed=True
    session.touch(*BAG_USE,after=180);point('field-party-targets')
    # Field wrapper0209002C passes the selected index directly to0207339C;
    # unlike battle's reordered roster, no inferred BattleMon index is used.
    session.touch(*PARTY_SLOTS[1],after=180);point('field-party-selected')
    for elapsed in range(0,1200,15):
        if any(e['name']=='field_consume' and 'result' in e for e in run['events']):break
        h.step(15)
        if elapsed%120==105:session.press('A',after=0)
    else:raise AssertionError('native field Revive use not observed; inspect UI captures, do not force selection')
    # One confirmation dismisses the healing text. Observe a bounded settling
    # interval without selecting another item or forcing an exit result.
    session.press('A',after=180);h.step(300)
    run['after']=sealed_state(h,out,'after');point('field-after')
    trace.armed=False
    run['observation']=observe(run)


def child(args):
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    run=dict(item=28,variant=args.child,events=[])
    result=dict(status='running',diagnostic_only=True,cases={},old_state_loaded=False,field=run,
                nonce=os.environ.get('DG_TEST_NONCE'),pair=os.environ.get('DG_ITEMS_FIELD_PAIR'),started_utc=utc())
    def flush():write_json(out/'result.json',result)
    flush()
    try:
        receipt,binding=identity(args.receipt);result['binding']=binding
        fixture=prepare(receipt,out,28);result['fixture']=fixture['metadata'];flush()
        rom=CN if args.child=='cn-field' else Path(receipt['output']['path'])
        result['executed_rom']=dict(path=str(rom),sha256=sha256(rom))
        os.environ['SDL_AUDIODRIVER']='dummy'
        with Harness(rom=rom,sav=fixture['battery'],out=out,verbose=False,emulator='desmume') as h, capture_failure(h,out):
            # Field has no DG dependency. Bind the same read-only static native
            # hooks to each actual ROM; never borrow CN hook bytes for candidate.
            session=OriginalSession(h,rom,out);result['inputs']=session.inputs
            session.boot();play(session,run,fixture,out,flush)
        require(identity(args.receipt)[1]==binding,'field baseline source/input changed')
        result['artifacts']=[dict(path=str(p),sha256=sha256(p)) for p in sorted(out.rglob('*'))
            if p.is_file() and p.suffix in ('.png','.bin','.sav','.json') and p.name!='result.json']
        result.update(status='passed',diagnostic_complete=True)
    except BaseException:result.update(status='failed',failure=traceback.format_exc());print(result['failure'],flush=True)
    finally:result['finished_utc']=utc();flush()
    return 0 if result['status']=='passed' else 1


def compare(rows,pair):
    require(len(rows)==2 and [r['field']['variant'] for r in rows]==['cn-field','candidate-field'],'field variants mismatch')
    require(all(r['status']=='passed' and r['diagnostic_only'] and not r['cases'] and r['pair']==pair and
                r['old_state_loaded'] is False and r.get('nonce') for r in rows),'unfinished/unbound field pair')
    require(rows[0]['nonce']!=rows[1]['nonce'] and rows[0]['binding']==rows[1]['binding'],'field nonce/source mismatch')
    require(rows[0]['executed_rom']['sha256']==CN_SHA256 and
            rows[1]['executed_rom']['sha256']==rows[1]['binding']['candidate']['candidate_sha256'],'field ROM mismatch')
    for key in ('input_battery_sha256','source_battery_sha256','payload','splash'):
        require(rows[0]['fixture'][key]==rows[1]['fixture'][key],'field input mismatch')
    require(rows[0]['field']['player_fixture']['hashes']==rows[1]['field']['player_fixture']['hashes'],'field party inputs differ')
    observations=[observe(r['field']) for r in rows]
    return dict(cn=observations[0],candidate=observations[1],same_field_observation=observations[0]==observations[1],
                battle_equivalence_proven=False,decision='D-2322 pending parent/user interpretation; field evidence only')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    p.add_argument('--native-timeout',type=int,default=180)
    p.add_argument('--child',choices=('cn-field','candidate-field'));p.add_argument('--out',type=Path)
    args=p.parse_args()
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run from root with assertions enabled')
    if not 1<=args.native_timeout<=600:p.error('Timeout must be1..600')
    if args.child:
        if args.out is None or not args.out.resolve().is_relative_to(OUTPUT):p.error('Child output must be owned')
        return child(args)
    _,binding=identity(args.receipt);pair=uuid.uuid4().hex
    root=OUTPUT/'native-tests/items-field'/pair;root.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',diagnostic_only=True,cases={},pair=pair,binding=binding,processes={},results=[])
    write_json(root.parent/'latest.json',dict(pair=pair,report=str(root/'report.json')))
    try:
        for variant in ('cn-field','candidate-field'):
            out=root/variant;out.mkdir()
            report['processes'][variant]=bound_process([sys.executable,Path(__file__),'--child',variant,
                '--receipt',args.receipt,'--out',out],out,args.native_timeout,env={'DG_ITEMS_FIELD_PAIR':pair})
            report['results'].append(str(out/'result.json'));write_json(root/'report.json',report)
        require(all(p['status']=='passed' for p in report['processes'].values()),'field child failed; inspect retained UI/trace')
        report['comparison']=compare([json.loads(Path(p).read_text()) for p in report['results']],pair)
        require(identity(args.receipt)[1]==binding,'field sources changed during pair')
        report['status']='passed'
    except BaseException:report.update(status='failed',failure=traceback.format_exc())
    finally:write_json(root/'report.json',report)
    print('Field diagnostic report:',root/'report.json',flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
