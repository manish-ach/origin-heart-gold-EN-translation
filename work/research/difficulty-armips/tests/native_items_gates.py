#!/usr/bin/env python3
"""Parent-supervised singles native fault-input checkpoint; no emulator on import."""
import argparse
import os
from pathlib import Path
import sys
import traceback
from support import ROOT, OUTPUT, sha256, RECEIPT
from evidence import write_json, utc
from native_ui import candidate_binding
from native_battle_helpers import NativeSession, capture_failure
from native_battle_oracles import require
from native_items_fixture import prepare, install_player, install_enemy_at_launch, TRAINER
from native_items_oracles import events, trainer_entry, input_fixture
from native_items_cases import CASES, GATE_ITEM
from native_items_gates_oracles import GATES, denied, continued, selected_target
from native_items_gates_trace import GateTrace


def fixture(receipt,out):
    from emu_harness import SaveFile
    from ndspy.rom import NintendoDSRom
    from ndspy.narc import NARC
    f=prepare(receipt,out,GATE_ITEM)
    r=NintendoDSRom.fromFile(receipt['output']['path'])
    berry=bytes(NARC(r.getFileByName('a/0/1/7')).files[151])
    bits=int.from_bytes(berry[8:10],'little')
    require((bits>>7)&15==4 and (bits>>11)&31==8,'Pecha native pocket/mask changed')
    battery=SaveFile(f['battery']);battery.transaction([dict(type='setPocket',name='berries',items=[[151,3]])])
    target=f['battery'].parent/'gates-input.sav';battery.write(target)
    f['metadata'].update(input_battery_path=str(target),input_battery_sha256=sha256(target),
        fault_fixture=True,stock=[[GATE_ITEM,3],[151,3]],pecha_payload=list(berry))
    f['battery']=target
    write_json(out/'items-fixture.json',f['metadata']);write_json(target.parent/'provenance.json',f['metadata'])
    return f


def play(s,t,run,flush):
    from emu_harness import BATTLE_BUTTONS, PARTY_SLOTS, MOVE_BUTTONS
    h=s.h
    deny_oracle,continue_oracle=denied,continued
    if run['gate']=='remembered':
        from native_items_remembered import denied as deny_oracle, continued as continue_oracle
    def point(label):s.checkpoint(label,run);flush()
    require(h.wait_screen('battle_menu',1800),'trainer menu not reached')
    trainer_entry(run);run['before']=t.state();input_fixture(run['before'],CASES[GATE_ITEM]);point('trainer-menu')
    if run['gate']=='remembered':t.armed=True
    s.touch(*BATTLE_BUTTONS['bag'],after=180)
    require(events(run,'lists'),'Bag list missing');point('bag-categories')
    lists=events(run,'lists')[-1]['lists']
    require(lists[1]==[dict(item=151,quantity=3)] and not any(e['item']==GATE_ITEM for ls in lists for e in ls),
            'unexpected restricted list; refusing blind selection')
    if run['gate']=='remembered':
        require(t.injected and not t.in_gate,'native remembered input check did not complete')
        point('remembered-cleared');s.touch(236,170,after=180)
    elif run['gate']=='item':
        t.armed=True;s.touch(236,170,after=180)
    else:
        s.touch(64,112,after=90);point('berry-list')
        s.touch(64,32,after=60);point('berry-detail')
        if run['gate']=='accept':t.armed=True
        s.touch(100,170,after=180)
        if run['gate']=='target':
            require(events(run,'accept') and events(run,'commit_item'),'allowed Use missing')
            run['party_mapping']=t.party_mapping();point('party-targets')
            mapping=run['party_mapping']['entries']
            run['target_command']=t.command_state();run['target_actor_binding']=t.actor_binding()
            targets=[e for e in mapping if e['id']==1 and e['mon']==run['target_actor_binding']['ui']]
            require(len(targets)==1 and targets[0]['source_sha256']==targets[0]['copy_sha256'],
                    'actual party target identity/copy mismatch')
            run['selected_ui_slot']=targets[0]['ui_slot'];selected_target(run)
            count=len(events(run,'lists'));t.armed=True
            s.touch(*PARTY_SLOTS[run['selected_ui_slot']],after=120)
            for _ in range(120):
                if len(events(run,'lists'))>count:break
                h.step(5)
            else:raise AssertionError('target denial did not rebuild Bag')
            point('bag-reopened');s.touch(236,170,after=180)
    require(t.injected and not t.armed and not t.in_gate,'fault gate not completed')
    require(h.wait_screen('battle_menu',600),'gate did not return to native command menu')
    run['denied']=t.state();run['command_denied']=t.command_state()
    run['denied_event_count']=len(run['events']);deny_oracle(run);point('denied-menu')
    # A healthy Splash-only enemy avoids damage/status interference. Actual
    # actions plus both PP views, not a menu pixel, establish turn completion.
    s.touch(*BATTLE_BUTTONS['fight'],after=60);point('continuation-moves')
    s.touch(*MOVE_BUTTONS[0],after=80)
    for elapsed in range(0,2400,15):
        h.step(15)
        if len(events(run,'action'))>=2 and h.on_screen('battle_menu'):break
        require(not h.in_field(),'continuation unexpectedly ended battle')
        if elapsed%120==105:s.press('A',after=0)
    else:raise AssertionError('native Fight continuation did not finish')
    run['after']=t.state();continue_oracle(run);point('continued-menu')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--gate',choices=(*GATES,'remembered'),required=True)
    p.add_argument('--fault-item',type=int,choices=(GATE_ITEM,791,65535),default=GATE_ITEM)
    args=p.parse_args()
    if args.gate=='remembered' and args.fault_item not in (791,65535):
        p.error('remembered input scope accepts only malformed IDs; authentic Potion persistence is separate')
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run repo root with assertions enabled')
    out=args.out.resolve()
    if not out.is_relative_to(OUTPUT):p.error('Output outside owned tests directory')
    out.mkdir(parents=True,exist_ok=True)
    run=dict(name='gate-'+args.gate,gate=args.gate,fault_item=args.fault_item,item=GATE_ITEM,flags=0,events=[])
    result=dict(status='running',driver='native_items_gates.py',layer='native ARM gameplay item gates',
        started_utc=utc(),nonce=os.environ.get('DG_TEST_NONCE'),old_state_loaded=False,cases={},battle=run,
        scope='Singles nativeFaultInput; no doubles or remembered-item acceptance')
    def flush():write_json(out/'result.json',result)
    flush()
    try:
        receipt,binding=candidate_binding(args.receipt);result['binding']=binding
        f=fixture(receipt,out);result['fixture']=f['metadata'];flush()
        from emu_harness import Harness
        os.environ['SDL_AUDIODRIVER']='dummy'
        with Harness(rom=Path(receipt['output']['path']),sav=f['battery'],out=out,verbose=False,
                     emulator='desmume') as h,capture_failure(h,out):
            from native_items_remembered import RememberedTrace
            s=NativeSession(h,receipt,out)
            t=(RememberedTrace if args.gate=='remembered' else GateTrace)(s,run);result['inputs']=s.inputs
            s.boot();run['options']=s.options(0)
            install_player(s,t,f);installed=install_enemy_at_launch(s,t,f)
            h.trainer_battle(TRAINER);play(s,t,run,flush)
            require(len(installed)==1,'enemy fixture missing');s.resident()
            result['overlay_address_reuse']=s.reused_addresses
            write_json(out/'gate-trace.json',dict(binding=binding,battle=run,inputs=s.inputs,fixture=f['metadata']))
            artifacts=[out/n for n in ('gate-trace.json','items-fixture.json','fixture-templates.json',
                'fixture-seed.bin','damaged.bin','healthy.bin','enemy-native-before.bin',
                'trainer-launch-diagnostic.json','trainer-menu.png','bag-categories.png',
                'denied-menu.png','continued-menu.png')]
            if args.gate=='remembered':artifacts.append(out/'remembered-cleared.png')
            if args.gate=='target':artifacts.extend([out/'party-targets.png',out/'bag-reopened.png'])
            result['checkpoint_artifacts']=[dict(path=str(a),sha256=sha256(a)) for a in artifacts]
            # Invalid selected IDs are additional safety slices, not substitute
            # evidence for the real restricted (DEFAULT-denied) item at each gate.
            if args.fault_item==GATE_ITEM:
                result['cases'][GATES[args.gate][2]]=dict(status='passed',artifacts=result['checkpoint_artifacts'])
            result.update(status='passed',checkpoint='passed')
    except BaseException:
        result.update(status='failed',failure=traceback.format_exc())
    finally:result['finished_utc']=utc();flush()
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
