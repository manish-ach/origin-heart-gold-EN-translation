#!/usr/bin/env python3
"""Parent-only, two cold-boot Revive reachability diagnostics; never suite passes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
import uuid
from support import ROOT, OUTPUT, CN, CN_SHA256, sha256, source_hashes, arm9_main, RECEIPT
from evidence import write_json, utc, bound_process
from native_ui import candidate_binding
from native_battle_helpers import NativeSession, registers, capture_failure
from native_battle_oracles import require
from native_items_fixture import prepare
from native_items_trace import ItemsTrace, ram_pointer, mon_state, read_inventory
from native_items_oracles import events, input_fixture, selected_party_entry
from native_items_cases import CASES
from emu_harness import Harness, BATTLE_BUTTONS, PARTY_SLOTS, script_bytes


class OriginalSession(NativeSession):
    """Same input/return-hook helpers, bound to CN bytes with no DG symbols."""
    def __init__(self,h,rom,out):
        from ndspy.rom import NintendoDSRom
        self.h,self.out=h,Path(out)
        self.rom= NintendoDSRom.fromFile(str(rom))
        self.overlays=self.rom.loadArm9Overlays([9,14])
        self.arm9=arm9_main(self.rom)
        self.callbacks,self.inputs,self.reused_addresses={},[],{}

    def code(self,address,size=8,overlay=None):
        if 0x02000000 <= address <= 0x02000000+len(self.arm9)-size:
            return self.arm9[address-0x02000000:address-0x02000000+size]
        o=self.overlays[14 if overlay is None else overlay]
        require(o.ramAddress <= address <= o.ramAddress+len(o.data)-size,'unbound CN hook')
        return bytes(o.data[address-o.ramAddress:address-o.ramAddress+size])

    def resident(self):pass  # CN has no installed resident; hook bytes/ROM are independently bound.


class ControlTrace(ItemsTrace):
    def __init__(self,session,run):
        self.s,self.h,self.run=session,session.h,run
        self.controller=self.move_ui=self.hp_watch=None
        self.capture=None
        for address,name in ((0x02050C34,'constructor'),(0x02076410,'native_attr'),(0x02214CA6,'captured'),
            (0x02202954,'parent'),(0x02200A30,'command'),(0x02221674,'effect'),
            (0x02215A2C,'consume'),(0x0221D7A8,'action'),(0x022217C8,'outcome'),
            (0x02221E30,'revive'),(0x022151A0,'target_resolver'),
            (0x02223610,'revival_dispatch'),(0x0222ADFC,'revival_hp_call'),
            (0x02217834,'revival_hp_add'),(0x0222A0A0,'revival_adjust'),(0x02224BF8,'revival_event')):
            session.hook(address,getattr(self,name))
        session.hook(0x021EC2CC,self.list_build,overlay=9)

    def native_attr(self):
        r=registers(self.h)
        if r[0]!=28 or r[1]!=13:return
        row=self.event('native_item_mask',item=r[0],attr=r[1],heap=r[2])
        # Original ov9 list builder BL02076410 at021EC308 returns021EC30D.
        # Candidate wrappers instead return into their bound resident payload.
        # Select ov9 only for this verified caller, never by overlapping range.
        overlay = None
        if r[14] == 0x021EC30D:
            require(self.h.read(0x021EC308,4) == bytes.fromhex('8af682f8'),
                    'original list attribute caller changed')
            overlay = 9
        self.s.returned(lambda:row.update(result=registers(self.h)[0]),overlay=overlay)

    def state(self):
        require(self.capture is not None,'no native wild capture')
        h=self.h;root=h.u32(0x02255BAC)
        require(root==self.capture['root'] and h.u32(root+0x10)==self.capture['setup'],
                'wild root/setup changed')
        setup=self.capture['setup']
        require(h.u32(setup+0x1c0)==h.save==self.capture['save'],'wild save owner changed')
        return dict(mons={str(i):mon_state(h,h.u32(root+0x1d0+4*i)) for i in (1,2,3,13)},
                    **read_inventory(h,h.u32(setup+0x108),28),native_context=dict(self.capture))

    def captured(self):
        require(self.capture is None,'duplicate wild capture')
        h=self.h;root=ram_pointer(h.u32(0x02255BAC),0x274,'wild root')
        setup=ram_pointer(h.u32(root+0x10),0x1d4,'wild setup')
        self.capture=dict(root=root,setup=setup,flags=h.u32(setup),control=h.u32(setup+0x18c),
                          save=h.u32(setup+0x1c0),bag=h.u32(setup+0x108))
        require(self.capture['flags']==0 and self.capture['control']==8 and self.capture['save']==h.save,
                'scripted wild context/owner mismatch')
        self.event('wild_captured',context=self.capture)


def install_inputs(session,trace,fixture):
    """Closed typed records only, all writes strictly before native capture."""
    import save_core
    h=session.h
    require(h.in_field() and not trace.run['events'],'late player fixture')
    party=ram_pointer(h.array(2),8+6*236,'player party')
    require(h.u32(party)==6,'player capacity changed')
    raws=[fixture['healthy'],fixture['damaged'],fixture['healthy']]
    for i,raw in enumerate(raws):h.write(party+8+i*236,raw)
    h.w32(party+4,3)
    trace.run['player_fixture']=dict(frame=h.frame,hashes=[hashlib.sha256(v).hexdigest() for v in raws])
    def launch():
        r=registers(h);setup=r[1]
        require(trace.capture is None and not events(trace.run,'enemy_fixture') and h.in_field(),'late/duplicate wild fixture')
        ctor=events(trace.run,'constructor')
        require(len(ctor)==1 and ctor[0]['lr']==0x02050433 and ctor[0]['setup']==setup and
                ctor[0]['flags']==ctor[0]['control']==0 and r[14]==0x02050483,'wrong native WildBattle caller')
        require(h.u32(setup)==0 and h.u32(setup+0x18c)==8 and h.u32(setup+0x1c0)==h.save,'wild setup mismatch')
        enemy=ram_pointer(h.u32(setup+8),8+6*236,'wild enemy party')
        require(h.u32(enemy)==6 and h.u32(enemy+4)==1,'wild party allocation mismatch')
        old=h.read(enemy+8,236)
        (session.out/'enemy-native-before.bin').write_bytes(old)
        decoded=save_core.request('decodePokemon',old,diagnostic=False)
        require(decoded['flags']==0 and decoded['checksumOk'] and not decoded['isEgg'],'invalid native wild mon; no repair')
        h.write(enemy+8,fixture['healthy'])
        require(h.read(enemy+8,236)==fixture['healthy'],'pre-entry enemy fixture mismatch')
        trace.event('enemy_fixture',setup=setup,party=enemy,before_sha256=hashlib.sha256(old).hexdigest(),
                    after_sha256=hashlib.sha256(fixture['healthy']).hexdigest(),before_capture=True)
    session.hook(0x0204FCE4,launch)


def visible_categories(run):
    lists=events(run,'lists')
    require(lists,'no native list construction')
    require(events(run,'native_item_mask'),'native Revive attribute was never observed')
    categories=[]
    for row in lists:
        found=[]
        require(row['args']['owner']==row['args']['tutorial']==0,'wrong wild Bag owner')
        for category,items in enumerate(row['lists']):
            require(all(x==dict(item=28,quantity=3) for x in items),'unexpected wild inventory list')
            require(len(items)<=1,'duplicate visible Revive')
            if items:found.append(category)
        categories.append(found)
    require(all(c==categories[0] for c in categories),'unstable native visible lists')
    return categories[0]


def play_control(session,trace,run,flush):
    h=session.h
    def point(name):session.checkpoint(name,run);flush()
    require(h.wait_screen('battle_menu',1800),'wild command menu not reached')
    require(trace.capture is not None and len(events(run,'enemy_fixture'))==1,'missing wild fixture/capture')
    run['before']=trace.state();input_fixture(run['before'],CASES[28]);trace.watch_revive_hp(run['before'])
    point('wild-menu')
    session.touch(*BATTLE_BUTTONS['bag'],after=180);point('wild-bag')
    run['visible_categories']=visible_categories(run)
    if not run['visible_categories']:
        run['command_before_cancel']=trace.command_state()
        session.touch(236,170,after=180)
        require(h.wait_screen('battle_menu',600),'hidden-item Bag cancel did not return')
        run['command_after_cancel']=trace.command_state()
        run['after']=trace.state()
        require(run['before']==run['after'] and run['command_before_cancel']==run['command_after_cancel'],
                'hidden-item cancel changed native state/command')
        require(not any(events(run,n) for n in ('command','effect','revive','consume','action')),
                'hidden item unexpectedly executed an action')
        run['finding']='native_ui_unreachable'
    else:
        require(run['visible_categories']==[0],'unresearched native category for Revive')
        session.touch(64,40,after=90);point('wild-item-list')
        session.touch(64,32,after=60);point('wild-item-detail')
        session.touch(100,170,after=180);point('wild-party-targets')
        mapping=trace.party_mapping();selected_party_entry(mapping,CASES[28],run['before']);flush()
        session.touch(*PARTY_SLOTS[CASES[28]['ui_slot']],after=120)
        for elapsed in range(0,2400,15):
            h.step(15)
            if events(run,'effect') and h.on_screen('battle_menu'):break
            require(not h.in_field(),'wild battle unexpectedly ended')
            if elapsed%120==105:session.press('A',after=0)
        else:raise AssertionError('wild item did not return within bounded wait')
        run['after']=trace.state()
        require(len(events(run,'command'))==len(events(run,'effect'))==len(events(run,'revive'))==1,
                'missing/duplicate native wild item action')
        command=events(run,'command')[0];effect=events(run,'effect')[0]
        require(command['item']==28 and command['target']==2 and effect['target_id']==2 and effect['actor']['id']==1,
                'wild item actor/target mismatch')
        resolution=events(run,'target_resolved')
        require(len(resolution)==1 and resolution[0]['id']==2 and resolution[0]['ui_slot']==2 and
                resolution[0]['mon']==mapping['entries'][2]['mon'],'wild target resolver mismatch')
        require(run['after']['mons']['1']==run['before']['mons']['1'] and
                run['after']['mons']['3']==run['before']['mons']['3'],'wild item changed other players')
        run['finding']='native_ui_reachable_effect_observed'
        # Deliberately record rather than bless final HP: ordinary oracle stays15.
        run['observation']=dict(final_hp=run['after']['mons']['2']['hp'],
            final_quantity=run['after']['quantity'],revive=events(run,'revive'),
            outcomes=events(run,'outcome'),consumes=events(run,'consume'),actions=events(run,'action'))
    trace.stop_hp_watch();point('wild-returned-menu')


def identity(receipt_path):
    receipt,binding=candidate_binding(receipt_path)
    require(sha256(CN)==CN_SHA256,'untouched CN pin mismatch')
    from ndspy.rom import NintendoDSRom
    from ndspy.narc import NARC
    roms=[NintendoDSRom.fromFile(receipt['output']['path']),NintendoDSRom.fromFile(str(CN))]
    metadata={}
    for name,member in (('a/0/0/2',19),('a/0/1/7',28),('a/0/1/1',150)):
        data=[bytes(NARC(r.getFileByName(name)).files[member]) for r in roms]
        require(data[0]==data[1],'candidate/CN fixture numeric data differ')
        metadata[f'{name}:{member}']=hashlib.sha256(data[0]).hexdigest()
    # Growth bytes too: same fixture is candidate-derived and valid on both ROMs.
    personal=bytes(NARC(roms[0].getFileByName('a/0/0/2')).files[19])
    growth=[bytes(NARC(r.getFileByName('a/0/0/3')).files[personal[19]]) for r in roms]
    require(growth[0]==growth[1],'candidate/CN growth data differ')
    metadata['growth']=hashlib.sha256(growth[0]).hexdigest()
    return receipt,dict(candidate=binding,cn_sha256=CN_SHA256,sources=source_hashes(),numeric=metadata)


def child(args):
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    run=dict(item=28,flags=4,events=[],variant=args.child)
    result=dict(status='running',diagnostic_only=True,cases={},old_state_loaded=False,battle=run,
                nonce=os.environ.get('DG_TEST_NONCE'),pair=os.environ.get('DG_ITEMS_CONTROL_PAIR'),started_utc=utc())
    def flush():write_json(out/'result.json',result)
    flush()
    try:
        receipt,binding=identity(args.receipt);result['binding']=binding
        fixture=prepare(receipt,out,28);result['fixture']=fixture['metadata'];flush()
        rom=Path(receipt['output']['path']) if args.child=='candidate-all-wild' else CN
        result['executed_rom']=dict(path=str(rom),sha256=sha256(rom))
        os.environ['SDL_AUDIODRIVER']='dummy'
        with Harness(rom=rom,sav=fixture['battery'],out=out,verbose=False,emulator='desmume') as h, capture_failure(h,out):
            session=NativeSession(h,receipt,out) if args.child=='candidate-all-wild' else OriginalSession(h,rom,out)
            trace=ControlTrace(session,run);result['inputs']=session.inputs
            session.boot()
            if args.child=='candidate-all-wild':run['options']=session.options(4)
            install_inputs(session,trace,fixture)
            h.run_script(program=script_bytes(('LockAll',),('WildBattle',129,15,0),('ReleaseAll',),('End',)))
            try:play_control(session,trace,run,flush)
            finally:trace.stop_hp_watch()
            result['overlay_address_reuse']=session.reused_addresses
        require(identity(args.receipt)[1]==binding,'control sources/inputs changed during run')
        result['artifacts']=[dict(path=str(p),sha256=sha256(p)) for p in sorted(out.rglob('*'))
                             if p.is_file() and p.suffix in ('.png','.bin','.sav','.json') and p.name!='result.json']
        result.update(status='passed',diagnostic_complete=True,
                      note='Observed reachability only; no gameplay expected-value or required-case acceptance')
    except BaseException:
        result.update(status='failed',failure=traceback.format_exc());print(result['failure'],flush=True)
    finally:result['finished_utc']=utc();flush()
    return 0 if result['status']=='passed' else 1


def validate_pair(rows,pair):
    require(len(rows)==2 and all(r['status']=='passed' and r.get('diagnostic_only') and not r.get('cases') for r in rows),
            'both control observations must finish, without acceptance claims')
    require(all(r['pair']==pair and r['old_state_loaded'] is False for r in rows) and
            all(r.get('nonce') for r in rows) and rows[0]['nonce']!=rows[1]['nonce'],'control invocation binding mismatch')
    require(rows[0]['binding']==rows[1]['binding'],'control source/ROM bindings differ')
    require([r['battle']['variant'] for r in rows]==['candidate-all-wild','cn-wild'],'wrong control variants')
    require(rows[0]['executed_rom']['sha256']==rows[0]['binding']['candidate']['candidate_sha256'] and
            rows[1]['executed_rom']['sha256']==CN_SHA256,'wrong executed ROM')
    for key in ('input_battery_sha256','source_battery_sha256','payload','splash','target_slot','ui_slot'):
        require(rows[0]['fixture'][key]==rows[1]['fixture'][key],'control fixture mismatch: '+key)
    require([r['sha256'] for r in rows[0]['fixture']['records']]==[r['sha256'] for r in rows[1]['fixture']['records']],
            'control party records differ')
    require(rows[0]['battle']['player_fixture']['hashes']==rows[1]['battle']['player_fixture']['hashes'],
            'control installed party inputs differ')
    require([events(r['battle'],'enemy_fixture')[0]['after_sha256'] for r in rows]==
            [rows[0]['fixture']['records'][1]['sha256']]*2,'control enemy inputs differ')
    return dict(findings={r['battle']['variant']:r['battle']['finding'] for r in rows},
                effect_equivalence_proven=False,note='Reachability/observations only; requires trace review')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    p.add_argument('--native-timeout',type=int,default=180)
    p.add_argument('--child',choices=('candidate-all-wild','cn-wild'))
    p.add_argument('--out',type=Path)
    args=p.parse_args()
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run from root with assertions enabled')
    if not 1<=args.native_timeout<=600:p.error('Timeout must be1..600')
    if args.child:
        if args.out is None or not args.out.resolve().is_relative_to(OUTPUT):p.error('Child OUT must be owned tests output')
        return child(args)
    receipt,binding=identity(args.receipt)
    pair=uuid.uuid4().hex;root=OUTPUT/'native-tests/items-controls'/pair;root.mkdir(parents=True,exist_ok=False)
    report=dict(status='running',diagnostic_only=True,cases={},pair=pair,binding=binding,processes={},results=[])
    write_json(root.parent/'latest.json',dict(pair=pair,report=str(root/'report.json')))
    try:
        for variant in ('candidate-all-wild','cn-wild'):
            out=root/variant;out.mkdir()
            process=bound_process([sys.executable,Path(__file__),'--child',variant,'--receipt',args.receipt,'--out',out],
                                  out,args.native_timeout,env={'DG_ITEMS_CONTROL_PAIR':pair})
            report['processes'][variant]=process;report['results'].append(str(out/'result.json'))
            write_json(root/'report.json',report)
        require(all(v['status']=='passed' for v in report['processes'].values()),'control child failed; inspect retained results')
        rows=[json.loads(Path(path).read_text()) for path in report['results']]
        report['comparison']=validate_pair(rows,pair)
        require(identity(args.receipt)[1]==binding,'control sources changed')
        report['status']='passed'
    except BaseException:report.update(status='failed',failure=traceback.format_exc())
    finally:write_json(root/'report.json',report)
    print('Diagnostic report:',root/'report.json',flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
