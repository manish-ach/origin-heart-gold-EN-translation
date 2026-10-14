#!/usr/bin/env python3
"""One cold boot, two actual wild KOs, one badge-only cap12 -> cap20 boundary."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from support import ROOT, OUTPUT, sha256, RECEIPT
from evidence import write_json, utc
from native_ui import candidate_binding
from native_battle import play_battle
from native_progression import ProgressionTrace
from native_battle_helpers import NativeSession, party_summary, capture_failure
from native_battle_fixture import prepare_fixture_templates
from native_progression_fixture import install
from native_caprise_fixture import field_state, advance_badge
from native_caprise_oracles import STAGES, CASE_IDS, validate
from native_battle_oracles import require
from emu_harness import Harness


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    p.add_argument('--out',type=Path,default=OUTPUT/'native-tests/caprise')
    args=p.parse_args()
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run at repository root with assertions enabled')
    out=args.out.resolve()
    if not out.is_relative_to(OUTPUT):p.error('Output outside owned tests directory')
    out.mkdir(parents=True,exist_ok=True)
    result=dict(status='running',driver='native_caprise.py',layer='native ARM gameplay cap rise',
                old_state_loaded=False,nonce=os.environ.get('DG_TEST_NONCE'),started_utc=utc(),
                cases={key:dict(status='incomplete') for key in CASE_IDS},battles=[],field_states={})
    def flush():write_json(out/'result.json',result)
    flush()
    try:
        receipt,binding=candidate_binding(args.receipt);result['binding']=binding
        source=ROOT/'work/build/memcheck/trainer.sav';save=out/'trainer.sav';shutil.copyfile(source,save)
        templates=prepare_fixture_templates(receipt,out,levels=(8,12))
        metadata=json.loads((out/'fixture-templates.json').read_text())
        os.environ['SDL_AUDIODRIVER']='dummy'
        with Harness(rom=Path(receipt['output']['path']),sav=save,out=out,verbose=False,
                     emulator='desmume') as h,capture_failure(h,out):
            session=NativeSession(h,receipt,out);trace=ProgressionTrace(session)
            session.hook(0x0221F778,lambda:setattr(trace,'phase','first'))
            session.hook(0x0221F83E,lambda:setattr(trace,'phase','deferred'))
            result['inputs']=session.inputs
            session.boot();session.checkpoint('cold-field',dict(snapshot=trace.snapshot()))
            options=session.options(2)
            fixture=install(session,trace,templates,STAGES[0])  # sole party fixture installation
            states=result['field_states']
            states['initial']=field_state(session,trace,options)
            for index,spec in enumerate(STAGES):
                if index:
                    states['before_second']=field_state(session,trace,options)
                    require(states['before_second']==states['after_badge'],'field state changed before next entry')
                    fixture=dict(spec=dict(spec),save=h.save,profile=states['before_second']['profile'],
                                 vars=states['before_second']['vars'],note='Carried native party; badge0-only field edit')
                run=dict(name='cap12' if index==0 else 'cap20',flags=2,expected_cap=spec['cap'],
                         threshold=metadata['thresholds'][spec['cap']],fixture=fixture,
                         options=options,before=party_summary(h),events=[])
                result['battles'].append(run);flush()
                try:play_battle(session,trace,run)
                finally:flush()
                states['after_first' if index==0 else 'after_second']=field_state(session,trace,options)
                if index==0:
                    states['after_badge']=advance_badge(session,trace,options,states['after_first'])
                    session.checkpoint('badge-only-boundary',result)
                flush()
            validate(result);session.resident()
            result['overlay_address_reuse']=session.reused_addresses
            result['same_root_observed']=len({e['snapshot']['root'] for r in result['battles']
                for e in r['events'] if e['name']=='captured'})==1
            trace_path=out/'caprise-trace.json'
            write_json(trace_path,dict(binding=binding,battles=result['battles'],field_states=states,inputs=session.inputs))
            artifacts=[trace_path,out/'fixture-templates.json',out/'fixture-seed.bin',out/'badge-only-boundary.png']
            artifacts += [out/f'fixture-level-{level}.bin' for level in templates]
            for run in result['battles']:
                artifacts.append(out/(run['name']+'-finished.png'))
                for record in run['opponent']['hp_fixture']['records']:
                    artifacts.extend(Path(record[k]) for k in ('before_path','after_path'))
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
