#!/usr/bin/env python3
"""One fresh-boot functional progression battle; parent owns emulator launch."""
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
from native_battle import BattleTrace, play_battle
from native_battle_helpers import NativeSession, registers, party_summary, capture_failure
from native_battle_fixture import prepare_fixture_templates
from native_battle_oracles import require
from native_progression_cases import CASES
from native_progression_fixture import install
from native_progression_oracles import validate
from emu_harness import Harness


class ProgressionTrace(BattleTrace):
    def __init__(self,session):
        super().__init__(session)
        self.reading=None
        session.hook(session.labels['dg_cap_for_save']&~1,self.cap)
        for address,name in ((0x0202933c,'profile'),(0x0204f858,'vars'),
                             (0x02029428,'badge'),(0x0204f864,'flag')):
            session.hook(address,lambda name=name:self.reader(name))

    def cap(self):
        if self.run is None:return
        require(self.reading is None,'nested native cap read')
        row=self.event('cap_reader',save=registers(self.h)[0],profile=[],vars=[],badge=[],flag=[])
        self.reading=row
        def finish():
            row['result']=registers(self.h)[0]
            self.reading=None
        self.s.returned(finish)

    def reader(self,name):
        if self.reading is None:return
        r=registers(self.h)
        row=dict(arg=r[0]) if name in ('profile','vars') else dict(owner=r[0],id=r[1])
        self.reading[name].append(row)
        self.s.returned(lambda:row.update(result=registers(self.h)[0]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=tuple(CASES),required=True)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run at repository root with assertions enabled')
    out=args.out.resolve()
    if not out.is_relative_to(OUTPUT):p.error('Output outside owned tests directory')
    out.mkdir(parents=True,exist_ok=True)
    key='progression.fixture_'+args.case
    result=dict(status='running',driver='native_progression.py',layer='native ARM gameplay progression',
                old_state_loaded=False,nonce=os.environ.get('DG_TEST_NONCE'),started_utc=utc(),
                cases={key:dict(status='incomplete')})
    def flush():write_json(out/'result.json',result)
    flush()
    try:
        receipt,binding=candidate_binding(args.receipt);result['binding']=binding
        source=ROOT/'work/build/memcheck/trainer.sav';save=out/'trainer.sav';shutil.copyfile(source,save)
        spec=CASES[args.case]
        templates=prepare_fixture_templates(receipt,out,levels=(8,spec['level']))
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
            fixture=install(session,trace,templates,spec)
            run=dict(name=args.case,flags=2,expected_cap=spec['cap'],threshold=metadata['thresholds'][spec['cap']],
                     obsolete_threshold=metadata['thresholds'][88 if spec['level']==89 else 80],
                     fixture=fixture,options=options,before=party_summary(h),events=[])
            result['battle']=run;flush()
            try:play_battle(session,trace,run)
            finally:flush()
            validate(run);session.resident()
            result['overlay_address_reuse']=session.reused_addresses
            trace_path=out/'progression-trace.json'
            write_json(trace_path,dict(binding=binding,battle=run,inputs=session.inputs))
            artifacts=[trace_path,out/'fixture-templates.json',out/'fixture-seed.bin',out/(args.case+'-finished.png')]
            artifacts += [out/f'fixture-level-{level}.bin' for level in templates]
            for record in run['opponent']['hp_fixture']['records']:
                artifacts.extend(Path(record[k]) for k in ('before_path','after_path'))
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
