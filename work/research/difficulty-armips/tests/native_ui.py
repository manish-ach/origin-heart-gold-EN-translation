#!/usr/bin/env python3
"""Bounded real-candidate native Options replay; no old states or outcome writes.
Run from repo root. Harness copies/isolates emulator writes. Inputs are read only.
"""
import argparse
from collections import Counter
import datetime
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from support import ROOT, OUTPUT, SOURCE, FOCUS_COUNT, sha256, RECEIPT
from evidence import register_values, write_json
from native_ui_oracles import focus_regions, inspect_battery, validate_page_navigation
sys.path.insert(0, str(ROOT / 'work/tools'))
from emu_harness import Harness


def candidate_binding(receipt_path):
    receipt = json.loads(receipt_path.read_text())
    # The receipt says which tools built the candidate; a development candidate
    # binds only in development mode and a release one only in release mode.
    from build import DEV_ENV, tool_mode
    mode = receipt.get('tool_mode', 'release')
    if mode != tool_mode():
        raise ValueError(f'Receipt tool mode {mode} differs from this run ({tool_mode()}, {DEV_ENV}): '+str(receipt_path))
    for item in [receipt['input'], receipt['output']]:
        if sha256(item['path']) != item['sha256']:
            raise ValueError('Stale ROM binding: ' + item['path'])
    # Test files can change without changing ARM code. Bind every build/native/
    # compatibility/contract input recorded by the installer; bind tests separately.
    current = {}
    for name, item in receipt['sources'].items():
        rel = Path(name).relative_to(SOURCE.relative_to(ROOT)) if name.startswith(str(SOURCE.relative_to(ROOT))) else None
        if rel is not None and rel.parts[0] == 'tests':
            continue
        if Path(name).suffix == '.md':
            continue
        current[name] = sha256(ROOT / name)
        if current[name] != item['sha256']:
            raise ValueError('Candidate source changed: ' + name)
    for name,item in receipt['build_artifacts'].items():
        if sha256(item['path'])!=item['sha256']:
            raise ValueError('Candidate build artifact changed: '+name)
    return receipt, {'tool_mode': mode, 'receipt_sha256': sha256(receipt_path), 'candidate_sha256': receipt['output']['sha256'],
                     'input_sha256': receipt['input']['sha256'], 'implementation_sources': current,
                     'script_commands_sha256':sha256(ROOT/'work/tools/docs/script_cmds.json'),
                     'driver_sha256': sha256(__file__), 'harness_sha256':sha256(ROOT/'work/tools/emu_harness.py'), 'test_sources':{str(p.relative_to(ROOT)):sha256(p) for p in sorted((SOURCE/'tests').rglob('*')) if p.is_file() and p.suffix in ('.py','.c','.h','.asm','.ld','.json','.toml','.md') and '__pycache__' not in p.parts}, 'battery_source_sha256':sha256(ROOT/'work/build/memcheck/trainer.sav'), 'negative_seed_save_sha256':sha256(ROOT/'work/build/memcheck/full_bag_6mons.sav'),
                     'save_oracle_sources':{str(p.relative_to(ROOT)):sha256(p) for p in [ROOT/'work/tools/save_core.py',ROOT/'work/save-core/dist/build-identity.json',ROOT/'work/save-core/cli/worker.mjs']}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    p.add_argument('--out',type=Path,default=OUTPUT/'native-tests/ui')
    p.add_argument('--phase',choices=('ui','reload','cold0','newgame'),default='ui')
    args=p.parse_args(); out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    if not out.is_relative_to(OUTPUT):p.error('Output must remain within owned tests directory')
    if args.phase!='ui':
        from native_persistence import run
        return run(args)
    result={'status':'running','layer':'native ARM gameplay UI','started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cases':{},'old_state_loaded':False,'nonce':os.environ.get('DG_TEST_NONCE')}
    report=out/'result.json'
    def flush():write_json(report,result)
    flush()
    try:
        receipt,binding=candidate_binding(args.receipt);result['binding']=binding
        source_save=ROOT/'work/build/memcheck/trainer.sav'; save=out/'trainer.sav'
        save_hash=sha256(source_save);shutil.copyfile(source_save,save)
        result['battery_source_sha256']=save_hash
        os.environ['SDL_AUDIODRIVER']='dummy'
        events=[];counts=Counter();points=[];last_input={};preview=[];inputs=[]
        result['preview']=preview;result['inputs']=inputs;result['events']=events;result['points']=points
        with Harness(rom=Path(receipt['output']['path']),sav=save,out=out,verbose=False,emulator='desmume') as h:
            from ndspy.rom import NintendoDSRom
            overlay= NintendoDSRom.fromFile(receipt['output']['path']).loadArm9Overlays([50])[50]
            overlay_probe=bytes(overlay.data[0x021e53ec-overlay.ramAddress:0x021e53ec-overlay.ramAddress+16])
            result['preview_code_identity']={'address':0x021e53ec,'overlay':50,'bytes':overlay_probe.hex()}
            labels=receipt['build']['elf_labels']; payload=(Path(receipt['artifacts'])/'resident.bin').read_bytes()
            def end_options_session(reason):
                last_input.update(in_options=False,in_exit=False,mode=None)
                events.append({'name':'probe-session-end','frame':h.frame,'reason':reason})
            # Publication runs on native cold boot AND the actual in-game reset
            # path, before startup title selection. Stale overlay bytes alone
            # cannot establish an active Options session after a reset.
            h.on_exec(0x02000cdc,lambda h:end_options_session('native-save-publication'))
            def event(name):
                def record(h):
                    counts[name]+=1
                    if name=='dg_menu_input':last_input['state']=register_values(h.reg)[0]
                    if name=='dg_menu_exit':
                        last_input['in_exit']=True
                        # Keep monitoring THROUGH native exit (including Cancel
                        # preview restoration), then retire the session at its
                        # actual return to the overlay manager.
                        return_pc=h.reg.lr&~1
                        def returned(h):
                            end_options_session('native-menu-exit-return')
                            h.on_exec(return_pc,None)
                        h.on_exec(return_pc,returned)

                    if name!='dg_menu_input' and len(events)<3000:
                        events.append({'name':name,'frame':h.frame,'pc':h.reg.pc&0xffffffff,'lr':h.reg.lr&0xffffffff,'sp':h.reg.sp&0xffffffff,'args':register_values(h.reg)})
                return record
            for name,address in labels.items():
                if name.startswith('dg_menu_') or name in ('dg_options_apply','dg_battle_begin','dg_battle_root_free'):
                    h.on_exec(address&~1,event(name))
            for address in (0xFFFF0004,0xFFFF000C,0xFFFF0010):h.on_exec(address,event('exception_'+hex(address)))
            def preview_event(name):
                def record(h):
                    # Overlay1 replaces overlay50 at the same address on return
                    # to field. Require the actual loaded code, not an address hit.
                    code=h.read(0x021e53ec,16)
                    if code!=overlay_probe:
                        if name=='row':
                            result.setdefault('overlay_address_reuse',[]).append({'frame':h.frame,'bytes':code.hex(),
                                'args':register_values(h.reg),'lr':h.reg.lr&0xffffffff})
                        return
                    if last_input.get('in_options'):
                        preview.append({'name':name,'frame':h.frame,'args':register_values(h.reg),
                                        'lr':h.reg.lr&0xffffffff,
                                        'mode':'exit' if last_input.get('in_exit') else
                                        'custom' if h.u32(labels['page']+48) else 'normal'})
                return record
            for name,address in [('row',0x021e53ec),('title',0x0200589c),('background',0x0202b1b4)]:
                h.on_exec(address,preview_event(name))
            def press_key(button,**kw):
                inputs.append({'frame':h.frame,'key':button,**kw});h.press(button,**kw)
            def touch(x,y,**kw):
                inputs.append({'frame':h.frame,'touch':[x,y],**kw});h.touch(x,y,**kw)
            def resident():
                actual=bytearray(h.read(0x023DC000,len(payload)))
                for a,z in receipt['build']['zero_ranges']:actual[a-0x023DC000:z-0x023DC000]=payload[a-0x023DC000:z-0x023DC000]
                assert actual==payload,'candidate resident immutable bytes changed'
            def passed(case):
                trace=out/(case+'.trace.json')
                data={'events':events,'points':points,'counts':dict(counts),'inputs':inputs,'preview':preview}
                if case=='ui.page_navigation':data['page_navigation']=result['page_navigation']
                write_json(trace,data)
                pic=out/(points[-1]['name']+'.png')
                result['cases'][case]={'status':'passed','artifacts':[{'path':str(p),'sha256':sha256(p)} for p in (trace,pic)]}
                flush()
            def point(name):
                resident();h.screenshot(name)
                item={'name':name,'frame':h.frame,'counts':dict(counts),'pc':h.reg.pc&0xffffffff,'cpsr':h.reg.cpsr&0xffffffff}
                points.append(item);result['counts']=dict(counts);flush();print(json.dumps(item),flush=True)
                assert not any(k.startswith('exception_') for k in counts),'native exception vector'
            # Same bounded progression as the freshly established baseline, no .dst.
            h.step(2400);press_key('START',after=700);press_key('A',after=200);press_key('A',after=900)
            assert h.in_field(),'fresh boot did not reach field'
            point('field')
            def open_options(custom=True):
                before=counts['dg_menu_input'];last_input['in_options']=True;last_input['in_exit']=False;last_input['mode']='custom' if custom else 'normal'
                if custom:h.hold('L');h.step(2)
                touch(123,113,frames=6,after=240)
                if custom:h.release('L')
                h.step(60)
                assert counts['dg_menu_input']>before,'Options input callback did not execute'
                state=last_input['state']
                active=h.u32(labels['page']+24)==state and h.u32(labels['page']+48)==1
                assert active==custom,'native page mode disagrees with requested entry'
                point(('difficulty-' if custom else 'normal-options-')+str(counts['dg_menu_init']))
                return state
            navigation={'points':[],'inputs_start':len(inputs)}
            result['page_navigation']=navigation
            def navpoint(name):
                state=h.u32(labels['page']+24)
                row=dict(name=name,frame=h.frame,state=state,mode=h.u32(labels['page']+48),
                         nav_live=h.u32(labels['page']+52),word=h.u16(h.array(1)),
                         field=h.in_field(),options_owner=h.array(1))
                if state:
                    row.update(choices=[h.u16(state+0x86+0x54*i) for i in range(7)],
                               counts=[h.u16(state+0x84+0x54*i) for i in range(7)],
                               nav=h.read(labels['page']+336,16).hex())
                navigation['points'].append(row);point('page-'+name)
            d=open_options(False);navpoint('normal-entry')
            nav_original=h.u16(h.array(1));press_key('RIGHT',after=30);navpoint('normal-draft')
            touch(89,180,after=30);navpoint('difficulty-entry')
            press_key('RIGHT',after=30);navpoint('difficulty-draft')
            press_key('L',after=30);navpoint('normal-retained')
            touch(149,180,after=240);navpoint('confirmed')
            open_options(False);press_key('RIGHT',after=30);press_key('R',after=30)
            press_key('RIGHT',after=30);touch(18,180,after=30);navpoint('cancel-drafts')
            touch(200,180,after=240);navpoint('cancelled')
            # Restore through actual native controls before the existing matrix.
            d=open_options(False)
            for _ in range(3):
                if h.u16(d+0x86)==(nav_original&3):break
                press_key('RIGHT',after=10)
            press_key('R',after=30)
            touch(200 if nav_original&0x20 else 128,35,after=10)
            touch(149,180,after=240);navpoint('restored')
            navigation['inputs']=inputs[navigation['inputs_start']:]
            validate_page_navigation(navigation)
            passed('ui.page_navigation')
            result['cases']['ui.page_navigation']['artifacts'] += [
                {'path':str(out/('page-'+row['name']+'.png')),
                 'sha256':sha256(out/('page-'+row['name']+'.png'))}
                for row in navigation['points'] if row['name']!='restored']
            open_options()
            visual=[]
            for focus in range(FOCUS_COUNT):
                assert h.u32(labels['page']+36)==focus, 'custom focus did not follow D-pad'
                point('focus-'+str(focus))
                visual.append(focus_regions(out/('focus-'+str(focus)+'.png'),focus))
                if focus<FOCUS_COUNT-1:press_key('DOWN',after=30)
            press_key('DOWN',after=30)
            assert h.u32(labels['page']+36)==0
            result['focus_regions']=visual
            result['cases']['ui.visible_glyphs']={'status':'incomplete','reason':f'{FOCUS_COUNT} fresh focus captures require matching source-bound manual visual review; no automatic readability claim.',
                'artifacts':[{'path':str(out/('focus-'+str(i)+'.png')),'sha256':sha256(out/('focus-'+str(i)+'.png'))} for i in range(FOCUS_COUNT)]}
            # Native callback's state argument exposes live Options identity;
            # read only. No injection of page/transaction/settings outcome.
            assert 'state' in last_input,'missing native input trace'
            state=last_input['state'];options=h.u32(state+0x24)
            # ARM32 page.txn is 20 bytes; manager/state follow it.
            assert h.u32(labels['page']+24)==state,'held-L route did not activate custom page'
            original=h.u16(options);result['options_address']=options;result['options_before']=original
            press_key('RIGHT',after=20);point('items-toggled')
            assert h.u16(options)==original,'draft wrote live Options before Apply'
            press_key('B',after=240);point('cancelled-B')
            assert h.u16(options)==original,'B failed to cancel'
            assert counts['dg_menu_exit']>0,'native exit not reached'
            passed('ui.b_cancel');flush()
            # Selection persists in the field menu; reopen with a direct touch.
            open_options()
            # ITEMS, SHARE, CAP toggled; DOWN past TRAINER AI and CANCEL to APPLY.
            for button in ('RIGHT','DOWN','RIGHT','DOWN','RIGHT','DOWN','DOWN','DOWN','A'):press_key(button,after=20)
            h.step(240);point('applied-dpad')
            expected=original^0x8028
            assert h.u16(options)==expected,('D-pad Apply mismatch',hex(original),hex(h.u16(options)),hex(expected))
            passed('ui.dpad_apply');flush()
            open_options();press_key('RIGHT',after=20);touch(200,180,after=240);point('cancelled-touch')
            assert h.u16(options)==expected,'touch Cancel changed saved options'
            passed('ui.touch_cancel');flush()
            open_options()
            for x,y in [(128,35),(128,55),(128,75),(149,180)]:touch(x,y,after=30)
            h.step(240);point('applied-touch')
            assert h.u16(options)==original&~0x8028,'touch Apply did not clear all flags'
            passed('ui.touch_apply');flush()
            assert not [v for v in preview if v['mode']=='custom' and v['name']!='row'], 'difficulty page executed title/background preview'
            open_options(False);press_key('B',after=240);point('normal-options-cancel')
            assert h.u16(options)==original&~0x8028,'ordinary Options Cancel changed settings'
            passed('ui.normal_reentry')
            # Enable all difficulty bits through UI before testing every normal row.
            open_options()
            for x,y in [(200,35),(200,55),(200,75),(149,180)]:touch(x,y,after=30)
            h.step(240)
            assert h.u16(options)&0x8028==0x8028
            row_specs=[('music',3,0),('scene',0x80,7),('style',0x40,6),('title',0x10,4),
                       ('background',0x300,8),('frame',0x7c00,10),('textspeed',4,2)]
            normal=[];result['normal_rows']=normal
            for row,(name,mask,shift) in enumerate(row_specs):
                for apply in (False,True):
                    d=open_options(False);before=h.u16(options)
                    for _ in range(row):press_key('DOWN',after=4)
                    assert (h.u32(d+16)>>2)&7==row
                    old=h.u16(d+0x86+0x54*row);n=h.u16(d+0x84+0x54*row)
                    assert old==(before&mask)>>shift,(name,old,hex(before))
                    press_key('RIGHT',after=30)
                    choice=h.u16(d+0x86+0x54*row)
                    assert choice==(old+1)%n and choice!=old,(name,old,choice,n)
                    assert h.u16(options)==before,'normal draft wrote live word'
                    point('normal-'+name+('-apply' if apply else '-cancel'))
                    if apply:touch(149,180,after=240)
                    else:press_key('B',after=240)
                    expected=(before&~mask)|(choice<<shift) if apply else before
                    actual=h.u16(options)
                    normal.append({'row':row,'name':name,'apply':apply,'before':before,'choice':choice,'after':actual,'expected':expected})
                    assert actual==expected,normal[-1]
            assert any(v['name']=='title' and v['mode']=='normal' for v in preview),'native title preview never executed'
            assert any(v['name']=='background' and v['mode']=='normal' for v in preview),'native background preview never executed'
            assert {v['args'][1] for v in preview if v['name']=='row' and v['mode']=='normal'} >= set(range(6)), 'normal row render/preview coverage missing'
            assert not [v for v in preview if v['mode']=='custom' and v['name']!='row'],'custom preview bleed'
            point('seven-settings-done');passed('ui.seven_settings')
            # Exercise every difficulty/title/TEXT SPEED combination using inputs.
            permutations=[];result['permutations']=permutations
            for flags in range(8):
                open_options()
                for row,bit in enumerate((4,1,2)):
                    touch(200 if flags&bit else 128,35+20*row,after=10)
                touch(149,180,after=240)
                stored=((flags&1)<<15)|((flags&2)<<2)|((flags&4)<<3)
                assert h.u16(options)&0x8028==stored
                for title,speed in ((0,0),(0,1),(1,0),(1,1)):
                    d=open_options(False);before=h.u16(options)
                    # Actual D-pad focus, then native Right only if needed.
                    for _ in range(3):press_key('DOWN',after=12)
                    assert (h.u32(d+16)>>2)&7==3
                    if h.u16(d+0x86+3*0x54)!=title:press_key('RIGHT',after=12)
                    for _ in range(3):press_key('DOWN',after=12)
                    assert (h.u32(d+16)>>2)&7==6
                    if h.u16(d+0x27e)!=speed:press_key('RIGHT',after=12)
                    assert h.u16(d+0x86+3*0x54)==title and h.u16(d+0x27e)==speed
                    assert h.u16(options)==before
                    touch(149,180,after=240)
                    expected=(before&~0x14)|(title<<4)|(speed<<2)
                    assert h.u16(options)==expected and expected&0x8028==stored
                    d=open_options(False)
                    assert h.u16(d+0x86+3*0x54)==title and h.u16(d+0x27e)==speed
                    point('permutation-%d-%d-%d'%(flags,title,speed))
                    press_key('B',after=240)
                    assert h.u16(options)==expected
                    permutations.append({'flags':flags,'title':title,'speed':speed,'word':expected})
                    if (flags,title,speed)==(7,0,0):
                        # A second battery is generated ONLY by real Options and
                        # Save input. Its checkpoint is reloaded in another OS
                        # process; no host-written title/textspeed bits.
                        offset=options-h.save-0x10
                        before_save=inspect_battery(save,offset)
                        last_input['in_options']=False
                        touch(123,73,after=120)
                        for _ in range(3):press_key('A',after=180)
                        h.step(1200);point('title-zero-native-save')
                        zero_battery=out/'title-zero.sav'
                        assert h.emu.backup.export_file(str(zero_battery))
                        inspected=inspect_battery(zero_battery,offset)
                        assert inspected['options']==expected and inspected['counter']!=before_save['counter']
                        assert all(v['coherent'] for v in inspected['slots'])
                        zero_checkpoint=dict(result,status='save-checkpoint',save_expected=expected,
                            save_options_offset=offset,battery_before=before_save,battery_inspection=inspected,
                            saved_battery={'path':str(zero_battery),'sha256':sha256(zero_battery)})
                        write_json(out/'title-zero.json',zero_checkpoint)

            assert len(permutations)==32
            assert not [v for v in preview if v['mode']=='custom' and v['name']!='row'],'custom preview bleed in permutations'
            # Read/write/selection/previews are traced; actual title cold startup
            # and field printer execution are verified by persistence phase.
            result.setdefault('pending_phases',{})['ui.title_textspeed']={'phase':'cold0','reason':'32 native UI permutations prepared; awaits native startup and text-printer read proof'}

            result['save_expected']=h.u16(options)
            result['save_options_offset']=options-h.save-0x10
            result['battery_before']=inspect_battery(save,result['save_options_offset'])
            assert result['battery_before']['options']==original,'source save slot/Options offset disagrees with native RAM'
            last_input['in_options']=False
            touch(123,73,after=120);point('save-prompt-0')
            for n in range(3):
                press_key('A',after=180);point('save-prompt-'+str(n+1))
            h.step(1200);point('save-wait')
            battery=out/'native-saved.sav'
            assert h.emu.backup.export_file(str(battery)),'battery export failed'
            result['battery_inspection']=inspect_battery(battery,result['save_options_offset'])
            assert result['battery_inspection']['options']==result['save_expected'],'native Save did not persist Options'
            assert result['battery_inspection']['counter']!=result['battery_before']['counter'],'native Save generation did not advance'
            result['saved_battery']={'path':str(battery),'sha256':sha256(battery)}
            write_json(out/'persistence.json',dict(result,status='save-checkpoint'))
            flush()
            # Actual in-game chord, with a nonempty custom transaction. No movie
            # clock, emulator reset, memory poison or .dst participates here.
            open_options();press_key('RIGHT',after=20);point('before-softreset')
            assert h.u32(labels['page']+24)!=0
            result['pre_reset_bss']=[h.read(a,z-a).hex() for a,z in receipt['build']['zero_ranges']]
            assert any(any(bytes.fromhex(v)) for v in result['pre_reset_bss'])
            inputs.append({'frame':h.frame,'held_reset_chord':['L','R','START','SELECT']})
            h.hold('L','R','START','SELECT');h.step(30);h.release();h.step(360)
            result['post_reset_bss']=[h.read(a,z-a).hex() for a,z in receipt['build']['zero_ranges']]
            assert not any(any(bytes.fromhex(v)) for v in result['post_reset_bss']),'native soft reset did not clear resident BSS'
            point('softreset-loader')
            last_input['in_options']=False
            h.step(2040);press_key('START',after=700);press_key('A',after=200);press_key('A',after=900)
            assert h.in_field(),'native reset did not return to field'
            options=h.array(1)
            assert h.u16(options)==result['save_expected'],'saved settings lost after native reset'
            point('softreset-field');open_options()
            assert h.u32(labels['page']+24)==last_input['state']
            assert h.u16(options)==result['save_expected']
            press_key('B',after=240);point('softreset-reopened');passed('ui.softreset')
            result.setdefault('pending_phases',{})['ui.save_reload']={'phase':'reload','reason':'Native Save and reset checked; fresh process battery reload still required'}



        assert sha256(source_save)==save_hash,'original battery changed'
        _,after_binding=candidate_binding(args.receipt)
        assert after_binding==binding,'source/input/receipt changed during native replay'
        result['status']='passed'
    except BaseException:
        result['status']='failed';result['failure']=traceback.format_exc();flush();raise
    finally:
        result['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();flush()
    return 0
if __name__=='__main__':raise SystemExit(main())
