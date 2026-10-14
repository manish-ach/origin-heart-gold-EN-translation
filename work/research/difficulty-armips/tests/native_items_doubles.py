#!/usr/bin/env python3
"""One native doubles constructor/pending-action diagnostic. Parent launch only."""
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
from native_items_fixture import install_player, launch_diagnostic
from native_items_gates import fixture
from native_items_gates_trace import GateTrace
from native_items_gates_oracles import GATES
from native_items_trace import ram_pointer, mon_state, read_inventory
from native_items_oracles import events
from native_items_cases import GATE_ITEM

GATE_BYTES = GATE_ITEM.to_bytes(2,'little')+b'\0'


class DoublesTrace(GateTrace):
    def __init__(self,s,run):
        super().__init__(s,run)
        s.hook(0x02202068,self.select_actor)
        s.hook(0x02200960,self.move_command)
        s.hook(0x022151D0,self.position_resolver)

    def select_actor(self):
        c=registers(self.h)[0]
        if self.h.u8(c+2)!=0:return
        self.controller=c
        self.s.returned(lambda:self.event('local_actor_selected',command=self.command_state()))

    def command_state(self):
        row=super().command_state();c=row['controller'];h=self.h
        row.update(slot_count=h.u8(c+1),prefix_counts=list(h.read(c+0x594,2)))
        return row

    def actor_binding(self):
        h=self.h;c=self.command_state();root=self.snapshot()['root']
        view=ram_pointer(h.u32(c['controller']+0x28),0xf0,'doubles UI view')
        self.event('doubles_actor_probe',command=c,root=root,view=view)
        require(view==root+0x54 and c['owner']==0 and c['slot_count']==2 and c['slot'] in (0,1),
                'native doubles controller/owner/slot mapping changed')
        roster=view+0xc;require(c['slot']<h.u8(roster+0x18)<=6,'doubles actor roster out of bounds')
        ui=h.u32(roster+4*c['slot']);require(ui==c['actor'],'doubles roster/actor mismatch')
        rid=c['actor_id'];require(1<=rid<=6,'doubles actor not local')
        require(h.u32(view+0x8c+4*rid)==ui,'doubles UI ID table mismatch')
        engine=ram_pointer(h.u32(root+0x1d0+4*rid),0x2a4,'doubles engine actor')
        a,b=mon_state(h,ui),mon_state(h,engine)
        require(a==dict(b,address=ui),'doubles UI/engine actor state mismatch')
        backing=[ram_pointer(h.u32(x+0x10),236,'doubles backing') for x in (ui,engine)]
        hashes=[hashlib.sha256(h.read(x,236)).hexdigest() for x in backing]
        require(hashes[0]==hashes[1],'doubles backing copies differ')
        return dict(root=root,view=view,roster=roster,ui=ui,engine=engine,id=rid,command=c,
                    ui_state=a,engine_state=b,backing=backing,hashes=hashes)

    def state(self):
        h=self.h;root=ram_pointer(self.snapshot()['root'],0x274,'doubles root')
        mons={}
        for rid in range(1,25):
            p=h.u32(root+0x1d0+4*rid)
            if p:
                m=mon_state(h,p);require(m['id']==rid,'doubles engine registry mismatch');mons[str(rid)]=m
        return dict(mons=mons,snapshot=self.snapshot(),
                    **read_inventory(h,h.u32(h.u32(root+0x10)+0x108),GATE_ITEM))

    def position_resolver(self):
        # Native022151D0 maps battle position through02228580 to owner/slot,
        # then returns that view's roster pointer. Observe, never call/override.
        r=registers(self.h)
        row=self.event('position_resolver',view=r[0],position=r[1])
        self.s.returned(lambda:row.update(result=registers(self.h)[0]))

    def move_command(self):
        r=registers(self.h)
        if self.controller is None or r[0]!=self.h.u32(self.controller+0x588):return
        phases={0x0221200B:'preliminary',0x02212673:'selected'}
        phase=phases.get(r[14],'unexpected');callsite=(r[14]&~1)-4
        require(phase!='unexpected','unknown native local move encoder caller')
        expected=self.s.code(callsite,4,overlay=14)
        require(self.h.read(callsite,4)==expected,'native move encoder callsite identity changed')
        row=self.event('move_command',destination=r[0],move=r[1],target_position=r[2],command=self.command_state(),
            encoder_phase=phase,callsite=callsite,callsite_bytes=expected.hex(),
            target_bindings=[dict(e) for e in events(self.run,'position_resolver')
                if phase=='selected' and e['position']==r[2] and
                e['view']==self.h.u32(self.controller+0x28) and 'result' in e])
        self.s.returned(lambda:row.update(encoded=self.h.read(r[0],12).hex()))

    def pending(self):
        if self.run['fault_slot']==0:return dict(state='not_yet_selected',slot=1)
        p=self.run['first_command']['destination']
        return dict(destination=p,bytes=self.h.read(p,12).hex())

    def fault(self,gate,args,target=None):
        if not self.armed or gate!=self.run['gate']:return
        require(not self.injected,'double injection repeated')
        self.armed=False;self.injected=True;self.in_gate=True
        old=self.args(args);binding=self.actor_binding();c=binding['command']
        require(c['slot']==self.run['fault_slot'] and old['owner']==old['tutorial']==0 and
                old['item']==(0 if gate=='item' else 151) and old['category']==(4 if gate=='item' else 1) and
                old['bag']==self.run['before']['bag_address'],'wrong native slot/Bag input before fault')
        if gate=='target':require(target is not None and target<6,'target already cancelled')
        row=self.event('double_fault',kind='nativeFaultInput',gate=gate,target=target,address=args,before=self.h.read(args,0x30).hex(),
            registers_before=registers(self.h),binding=binding,command_before=c,pending_before=self.pending())
        self.h.write(args+0x18,GATE_BYTES)
        row.update(after=self.h.read(args,0x30).hex(),registers_after=registers(self.h),pending_after=self.pending(),command_after=self.command_state())
        def finish():
            row.update(result=registers(self.h)[0],args_after=self.args(args),command_return=self.command_state(),
                       pending_return=self.pending())
            self.in_gate=False
        self.s.returned(finish)


def enemy_inputs(s,t,f):
    import save_core
    from ndspy.rom import NintendoDSRom
    from ndspy.narc import NARC
    r=NintendoDSRom.fromFile(s.receipt['output']['path']);meta=bytes(NARC(r.getFileByName('a/0/5/5')).files[6])
    require(len(meta)==20 and meta[3]==2 and not any(meta[4:12]) and not any(meta[16:20]),'trainer6 metadata changed')
    t.run['trainer_metadata']=dict(id=6,sha256=hashlib.sha256(meta).hexdigest(),bytes=meta.hex())
    def launch():
        h=s.h;regs=registers(h);launch_diagnostic(s,t,regs);setup=regs[1]
        require(not events(t.run,'double_fixture') and not events(t.run,'begin') and h.in_field() and
                t.snapshot()['epoch']==0 and regs[14]==0x02050815,'late/wrong doubles launch')
        require(h.u32(setup)==3 and h.u32(setup+0x18c)==0 and h.u32(setup+0x1c0)==h.save,
                'native TrainerBattle6,6 did not produce3/0')
        records=[]
        # Native builder may populate both equal trainer IDs. Preserve actual
        # capacity/count and replace only existing valid enemy INPUT records.
        for owner in (1,3):
            party=ram_pointer(h.u32(setup+4+4*owner),8+236*6,'enemy input party')
            capacity,count=h.u32(party),h.u32(party+4)
            require(capacity==6 and count in (0,2),'unexpected native doubles enemy party shape')
            for slot in range(count):
                address=party+8+236*slot;raw=h.read(address,236)
                p=s.out/f'enemy-owner{owner}-slot{slot}-before.bin';p.write_bytes(raw)
                decoded=save_core.request('decodePokemon',raw,diagnostic=False)
                require(decoded['flags']==0 and decoded['checksumOk'] and not decoded['isEgg'],'invalid native enemy; no repair')
                h.write(address,f['healthy'])
                records.append(dict(owner=owner,slot=slot,address=address,before_path=str(p),before_sha256=sha256(p),
                    after_sha256=hashlib.sha256(f['healthy']).hexdigest(),decoded=decoded))
        require(len(records)>=2,'native trainer enemy team absent')
        t.event('double_fixture',setup=setup,records=records,before_begin=True)
    s.hook(0x0204FCE4,launch)


def selected_command(rows,actor):
    # Native touch preparation uses literal selector5 at02211FF8. Actual
    # selection reads the target-position byte at02212666. Neither is an action yet.
    require(len(rows)==2,'expected native preliminary+selected encoder pair')
    pre,final=rows
    require(pre['encoder_phase']=='preliminary' and final['encoder_phase']=='selected' and
            pre['lr']==0x0221200B and final['lr']==0x02212673 and
            pre['callsite']==0x02212006 and final['callsite']==0x0221266E and
            pre['callsite_bytes']=='eef7abfc' and final['callsite_bytes']=='eef777f9' and
            pre['target_position']==5 and 0<=final['target_position']<4 and pre['frame']<=final['frame'],
            'native encoder stages/callers/selection mismatch')
    bindings=final['target_bindings']
    require(bool(bindings) and all(e['name']=='position_resolver' and
            e['position']==final['target_position'] and e['view']==actor['view'] and
            e['result']==actor['ui'] and e['frame']<=final['frame'] for e in bindings),
            'selected Splash position does not natively resolve to its actor')
    for e in rows:
        require(e['move']==150 and e['destination']==actor['command']['destination'] and
                e['command']['actor']==actor['ui'] and e['command']['actor_id']==actor['id'] and
                e['command']['owner']==0 and e['command']['slot']==actor['command']['slot'],
                'native encoder belongs to another actor/command')
        raw=bytes.fromhex(e['encoded']);word=int.from_bytes(raw[:4],'little')
        require(len(raw)==12 and word&15==1 and (word>>8)&65535==150 and (word>>4)&15==e['target_position'],
                'encoder arguments disagree with native output')
    pre_bytes=bytearray.fromhex(pre['encoded']);word=(int.from_bytes(pre_bytes[:4],'little')&~0xf0)|(final['target_position']<<4)
    pre_bytes[:4]=word.to_bytes(4,'little')
    require(pre_bytes==bytes.fromhex(final['encoded']),'encoder stages changed more than selected target position')
    return final


def validate_denial(run):
    gate,slot=run['gate'],run['fault_slot']
    require(gate in GATES and slot in (0,1),'unknown doubles gate/slot')
    prefix=run['events'][:run['denied_event_count']]
    rows=[x for x in prefix if x['name']=='double_fault'];require(len(rows)==1,'missing/repeated doubles fault')
    e=rows[0];actor=run['first_actor'] if slot==0 else run['second_actor']
    raw=bytearray.fromhex(e['before']);old_item=int.from_bytes(raw[0x18:0x1a],'little')
    require(old_item==(0 if gate=='item' else 151) and raw[0x1a]==(4 if gate=='item' else 1),
            'wrong native input before doubles fault')
    raw[0x18:0x1b]=GATE_BYTES
    require(e['kind']=='nativeFaultInput' and e['gate']==gate and len(raw)==0x30 and e['after']==raw.hex() and
            e['registers_before']==e['registers_after'] and e['result']==GATES[gate][1] and
            e['args_after']['item']==0 and e['args_after']['category']==4,'doubles gate did not deny input natively')
    require(e['command_before']==e['command_after']==e['command_return']==run['command_denied'] and
            e['command_before']['actor_id']==actor['id'] and e['command_before']['actor']==actor['ui'] and
            e['command_before']['owner']==0 and e['command_before']['slot']==slot,'denial changed command/actor')
    pending=run['pending_initial']
    if slot==1:
        first=run['first_command'];word=int.from_bytes(bytes.fromhex(pending['bytes'])[:4],'little')
        require(pending['destination']==first['destination'] and word&15==1 and
                (word>>8)&65535==150,'finalized pending action is not first Splash')
        selected_command([x for x in prefix if x['name']=='move_command'],run['first_actor'])
    else:
        require(pending==dict(state='not_yet_selected',slot=1) and
                not any(x['name']=='move_command' or
                        (x['name']=='local_actor_selected' and x['command']['slot']!=0) for x in prefix),
                'first-slot probe falsely claims another pending action')
    require(e['pending_before']==e['pending_after']==e['pending_return']==run['pending_denied']==pending,
            'denial changed other pending-action state')
    require(run['before']==run['queued']==run['denied'],'queue/denial consumed a turn or changed Bag/mons')
    forbidden=('command','effect','consume','outcome','action','target_resolved','ordinary_hp','status_effect',
               'pp_one','pp_all','revive','exception','slot_advance','blocked_native_accept')
    require(not any(x['name'] in forbidden for x in prefix),'denial committed item/effect/turn/slot')
    lists=[x for x in prefix if x['name']=='lists']
    require(lists and all(x['lists'][1]==[dict(item=151,quantity=3)] and
            not any(i['item']==GATE_ITEM for ls in x['lists'] for i in ls) for x in lists),'restricted doubles list wrong')
    require(any(x['name']=='schedule' and x['handler']==0x02202445 for x in prefix),
            'native command-selection continuation missing')
    if gate=='target':
        mapping=run['party_mapping'];ui_slot=run['selected_ui_slot'];binding=e['binding']
        require(mapping['controller']==e['command_before']['controller'] and 0<=ui_slot<mapping['count'],
                'target UI mapping belongs to another controller')
        entry=mapping['entries'][ui_slot]
        require(entry['ui_slot']==ui_slot==e['target'] and entry['id']==actor['id'] and entry['mon']==actor['ui'] and
                entry['backing']==binding['backing'][0] and
                entry['source_sha256']==entry['copy_sha256']==actor['hashes'][0] and
                entry['hp']==actor['ui_state']['hp'] and entry['maxhp']==actor['ui_state']['maxhp'],
                'target UI copy does not identify acting local mon')
        require(len(lists)>=2 and lists[-1]['frame']>=e['frame'] and
                run['reopened_list']==lists[-1],'target denial did not natively rebuild Bag')
        accepts=[x for x in prefix if x['name']=='accept'];commits=[x for x in prefix if x['name']=='commit_item']
        require(accepts and accepts[-1]['after']['item']==151 and commits and commits[0]['result']==151,
                'target gate bypassed native allowed Berry Use')


def validate(run):
    """Completed four-actor continuation only; denial uses validate_denial."""
    require('after' in run, 'completed doubles continuation/readback missing')
    ctor,caps=events(run,'constructor'),events(run,'captured')
    require(len(ctor)==len(caps)==len(events(run,'begin'))==1,'doubles lifecycle missing')
    c=ctor[0];cap=caps[0];ctx=cap['context'];snap=cap['snapshot']
    require(c['flags']==ctx['flags']==3 and c['control']==ctx['control']==0 and c['lr'] in (0x020507AD, 0x02048EEF) and
            c['setup']==ctx['setup']==cap['setup_owner'] and ctx['save']==ctx['published_save']==cap['save_owner'] and
            snap['allowed']==1 and snap['flags']==0 and snap['epoch']==cap['generation']>0 and
            ctx['options_copy']==run['options']['after'],'native doubles context binding failed')
    require(len(events(run,'double_fixture'))==1 and events(run,'double_fixture')[0]['frame']<=events(run,'begin')[0]['frame'],
            'doubles input fixture not pre-entry')
    a,b=run['first_actor'],run['second_actor']
    require(a['command']['owner']==b['command']['owner']==0 and a['command']['slot']==0 and b['command']['slot']==1 and
            a['command']['slot_count']==b['command']['slot_count']==2 and a['id']!=b['id'] and
            1<=a['id']<=6 and 1<=b['id']<=6,'two local native actors not proven')
    for binding in (a,b):
        cmd=binding['command']
        require(binding['view']==snap['root']+0x54 and binding['root']==snap['root'] and
                binding['ui']==cmd['actor'] and binding['id']==cmd['actor_id'] and
                binding['engine']==run['before']['mons'][str(binding['id'])]['address'] and
                binding['hashes'][0]==binding['hashes'][1] and len(binding['hashes'][0])==64 and
                binding['ui_state']==dict(binding['engine_state'],address=binding['ui']), 'doubles actor views mismatch')
        require(any(e['view']==binding['view'] and e['owner']==0 and e['slot']==cmd['slot'] and
                    e.get('result')==binding['ui'] for e in events(run,'controller_actor_lookup')),'native actor lookup missing')
    first_rows=[e for e in events(run,'move_command') if e['command']['actor_id']==a['id']]
    require(run['first_command']==selected_command(first_rows,a),'pending first command is not native selected encoding')
    first=run['first_command'];word=int.from_bytes(bytes.fromhex(first['encoded'])[:4],'little')
    require(first['move']==150 and word&15==1 and (word>>8)&65535==150 and
            first['destination']==a['command']['destination'] and first['destination']!=b['command']['destination'],
            'first Splash command not natively queued in separate slot')
    validate_denial(run)
    second_rows=[e for e in events(run,'move_command') if e['command']['actor_id']==b['id']]
    selected_command(second_rows,b)
    require(len(events(run,'move_command'))==4,'unexpected additional native local move encoding')
    actions=events(run,'action');ids=[x['actor']['id'] for x in actions]
    require(len(actions)==len(set(ids))==4 and {a['id'],b['id']}.issubset(ids) and
            all(x['move']==150 for x in actions) and all(i in (a['id'],b['id']) or 13<=i<=24 for i in ids),
            'continuation did not execute both pending local Splashes and two enemy turns')
    expected=deepcopy(run['denied'])
    for rid in ids:
        expected['mons'][str(rid)]['pp'][0]-=1;expected['mons'][str(rid)]['original_pp'][0]-=1
    require(run['after']==expected,'doubles continuation changed unexpected inventory/HP/status/PP')
    require(not any(events(run,n) for n in ('command','effect','consume','outcome','exception')),'item escaped denial')


def play(s,t,run,flush):
    from emu_harness import BATTLE_BUTTONS,MOVE_BUTTONS,PARTY_SLOTS
    h=s.h
    def point(name):s.checkpoint(name,run);flush()
    def choose_first():
        s.touch(*BATTLE_BUTTONS['fight'],after=60);s.touch(*MOVE_BUTTONS[0],after=80)
        for elapsed in range(0,1200,10):
            h.step(10)
            if h.on_screen('battle_menu') and t.command_state()['slot']==1:break
            if elapsed%120==110:s.press('A',after=0)
        else:raise AssertionError('first Splash did not reach native second-slot menu')
        run['first_command']=selected_command(events(run,'move_command'),run['first_actor'])
        run['second_actor']=t.actor_binding();point('double-second-pending')
    require(h.wait_screen('battle_menu',1800),'doubles entry did not reach menu')
    run['before']=t.state();run['first_actor']=t.actor_binding();point('double-first-menu')
    if run['fault_slot']==1:choose_first()
    run['pending_initial']=t.pending();run['queued']=t.state()
    s.touch(*BATTLE_BUTTONS['bag'],after=180);point('double-bag')
    lists=events(run,'lists')
    require(lists and lists[-1]['lists'][1]==[dict(item=151,quantity=3)] and
            not any(i['item']==GATE_ITEM for ls in lists[-1]['lists'] for i in ls),'wrong restricted Bag before input')
    if run['gate']=='item':
        t.armed=True;s.touch(236,170,after=180)
    else:
        s.touch(64,112,after=90);point('double-berry-list')
        s.touch(64,32,after=60);point('double-berry-detail')
        if run['gate']=='accept':t.armed=True
        s.touch(100,170,after=180)
        if run['gate']=='target':
            run['party_mapping']=t.party_mapping();actor=t.actor_binding()
            targets=[e for e in run['party_mapping']['entries'] if e['id']==actor['id'] and e['mon']==actor['ui']]
            require(len(targets)==1 and targets[0]['source_sha256']==targets[0]['copy_sha256']==actor['hashes'][0],
                    'doubles native party target identity/copy mismatch')
            run['selected_ui_slot']=targets[0]['ui_slot'];point('double-party-targets')
            count=len(events(run,'lists'));t.armed=True
            s.touch(*PARTY_SLOTS[run['selected_ui_slot']],after=120)
            for _ in range(120):
                if len(events(run,'lists'))>count:break
                h.step(5)
            else:raise AssertionError('doubles target denial did not rebuild Bag')
            run['reopened_list']=deepcopy(events(run,'lists')[-1]);point('double-bag-reopened')
            s.touch(236,170,after=180)
    require(h.wait_screen('battle_menu',600) and t.injected and not t.in_gate,'gate did not return to same local menu')
    run['denied']=t.state();run['command_denied']=t.command_state();run['pending_denied']=t.pending()
    run['denied_event_count']=len(run['events']);point('double-denied');validate_denial(run)
    if run['fault_slot']==0:choose_first()
    s.touch(*BATTLE_BUTTONS['fight'],after=60);s.touch(*MOVE_BUTTONS[0],after=80)
    for elapsed in range(0,3000,15):
        h.step(15)
        if len(events(run,'action'))>=4 and h.on_screen('battle_menu'):break
        require(not h.in_field(),'doubles unexpectedly ended')
        if elapsed%120==105:s.press('A',after=0)
    else:raise AssertionError('both native doubles commands did not finish')
    run['after']=t.state();validate(run);point('double-continued')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--gate',choices=tuple(GATES),default='item')
    p.add_argument('--slot',type=int,choices=(0,1),default=1)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    a=p.parse_args();out=a.out.resolve()
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize or not out.is_relative_to(OUTPUT):p.error('repo root/owned output/assertions required')
    out.mkdir(parents=True,exist_ok=True);run=dict(name=f'double-{a.gate}-slot{a.slot}',item=GATE_ITEM,fault_item=GATE_ITEM,flags=0,gate=a.gate,fault_slot=a.slot,events=[])
    result=dict(status='running',driver='native_items_doubles.py',layer='native ARM gameplay doubles diagnostic',
        nonce=os.environ.get('DG_TEST_NONCE'),old_state_loaded=False,started_utc=utc(),cases={},battle=run,
        scope='One native doubles gate/slot case; no artificial pending action or backtracking claim')
    def flush():write_json(out/'result.json',result)
    flush()
    try:
        receipt,binding=candidate_binding(a.receipt);result['binding']=binding;f=fixture(receipt,out);result['fixture']=f['metadata']
        from emu_harness import Harness,script_bytes
        os.environ['SDL_AUDIODRIVER']='dummy'
        with Harness(rom=Path(receipt['output']['path']),sav=f['battery'],out=out,verbose=False,emulator='desmume') as h,capture_failure(h,out):
            s=NativeSession(h,receipt,out);t=DoublesTrace(s,run);result['inputs']=s.inputs
            s.boot();run['options']=s.options(0);install_player(s,t,f);enemy_inputs(s,t,f)
            h.run_script(program=script_bytes(('LockAll',),('TrainerBattle',6,6,0,0),('ReleaseAll',),('End',)))
            play(s,t,run,flush);validate(run);s.resident();write_json(out/'doubles-trace.json',result)
            artifacts=[out/'doubles-trace.json',out/'items-fixture.json',out/'trainer-launch-diagnostic.json']
            artifacts += list(out.glob('enemy-owner*-before.bin'))+list(out.glob('double-*.png'))
            result['checkpoint_artifacts']=[dict(path=str(x),sha256=sha256(x)) for x in artifacts]
            result.update(status='passed',checkpoint='passed')
    except BaseException:result.update(status='failed',failure=traceback.format_exc())
    finally:result['finished_utc']=utc();flush()
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
