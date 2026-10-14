#!/usr/bin/env python3
"""Bounded native trainer6 two-KO Share/Cap four-battle matrix; parent alone launches."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import traceback
from support import ROOT,OUTPUT,sha256,RECEIPT
from evidence import write_json,utc
from native_ui import candidate_binding
from native_battle_helpers import NativeSession,party_summary,install_fixture,capture_failure
from native_battle_fixture import prepare_fixture_templates
from native_battle_oracles import require
from native_multiko_fixture import set_style,prepare_enemy,install_launch_hook
from native_multiko_trace import MultiTrace,MultiInput
from native_multiko_oracles import CASE_IDS,validate_run,validate_matrix
from emu_harness import Harness


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    p.add_argument('--out',type=Path,default=OUTPUT/'native-tests/multiko')
    args=p.parse_args()
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run at repository root with assertions enabled')
    out=args.out.resolve()
    if not out.is_relative_to(OUTPUT):p.error('Output outside owned tests directory')
    out.mkdir(parents=True,exist_ok=True)
    result=dict(status='running',driver='native_multiko.py',layer='native ARM gameplay multiple KOs',
                old_state_loaded=False,nonce=os.environ.get('DG_TEST_NONCE'),started_utc=utc(),
                cases={key:dict(status='incomplete') for key in CASE_IDS},battles=[])
    def flush():write_json(out/'result.json',result)
    flush()
    try:
        receipt,binding=candidate_binding(args.receipt);result['binding']=binding
        source=ROOT/'work/build/memcheck/trainer.sav';save=out/'trainer.sav';shutil.copyfile(source,save)
        templates=prepare_fixture_templates(receipt,out,levels=(5,8,12))
        enemy,enemy_meta=prepare_enemy(receipt,out,templates);result['enemy_input']=enemy_meta
        os.environ['SDL_AUDIODRIVER']='dummy'
        with Harness(rom=Path(receipt['output']['path']),sav=save,out=out,verbose=False,
                     emulator='desmume') as h,capture_failure(h,out):
            s=NativeSession(h,receipt,out);t=MultiTrace(s)
            s.hook(0x0221F778,lambda:setattr(t,'phase','first'))
            s.hook(0x0221F83E,lambda:setattr(t,'phase','deferred'))
            install_launch_hook(s,t,enemy)
            result['inputs']=s.inputs
            s.boot();s.checkpoint('cold-field',dict(snapshot=t.snapshot()))
            result['style']=set_style(s)
            for flags in (0,2,1,3):
                options=s.options(flags);fixture=install_fixture(s,templates,False)
                run=dict(name=f'multi-flags{flags}',flags=flags,expected_cap=12,
                         threshold=fixture['threshold'],fixture=fixture,options=options,
                         enemy_input=enemy_meta['sha256'],before=party_summary(h),events=[])
                result['battles'].append(run);t.reset();t.run=run;flush()
                try:
                    h.trainer_battle(6)
                    require(h.wait_screen('battle_menu',1800),'trainer6 did not reach native command menu')
                    s.checkpoint(run['name']+'-menu',run)
                    require(t.snapshot()['allowed']==1 and t.snapshot()['cap']==12 and t.snapshot()['flags']==flags,
                            'native trainer entry snapshot missing')
                    inputs=MultiInput(s,t,run)
                    require(inputs.move(1,150,1,'splash')=='menu','Splash unexpectedly ended battle')
                    inputs.switch()
                    inputs.move(0,82,2,'ko13')
                    inputs.opponent_id=14
                    inputs.move(0,82,2,'ko14')
                    h.step(180)
                    run.update(after=party_summary(h),final_snapshot=t.snapshot())
                    s.checkpoint(run['name']+'-finished',run)
                    validate_run(run);t.run=None
                finally:flush()
            validate_matrix(result['battles']);s.resident()
            result['overlay_address_reuse']=s.reused_addresses
            path=out/'multiko-trace.json'
            write_json(path,dict(binding=binding,battles=result['battles'],inputs=s.inputs,enemy_input=enemy_meta))
            artifacts=[path,out/'enemy-input.bin',out/'enemy-input.json',out/'fixture-templates.json',out/'fixture-seed.bin',
                       out/'native-style-set-draft.png']+[out/f'fixture-level-{level}.bin' for level in templates]
            for run in result['battles']:
                artifacts.append(out/(run['name']+'-finished.png'))
                for e in run['events']:
                    if e['name']=='trainer_fixture':artifacts.extend(Path(r['before_path']) for r in e['records'])
            for key in CASE_IDS:
                result['cases'][key]=dict(status='passed',artifacts=[dict(path=str(a),sha256=sha256(a)) for a in artifacts])
        require(candidate_binding(args.receipt)[1]==binding,'sources/inputs changed during run')
        require(sha256(source)==binding['battery_source_sha256'],'source battery changed')
        result['status']='passed'
    except BaseException:
        result.update(status='failed',failure=traceback.format_exc());print(result['failure'],flush=True)
    finally:
        result['finished_utc']=utc();flush()
    return 0 if result['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
