#!/usr/bin/env python3
"""Fresh native local/remote recipient exclusions, with paired Share controls."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from support import ROOT, OUTPUT, sha256, RECEIPT
from evidence import utc, write_json
from native_ui import candidate_binding
from native_battle_oracles import require
from native_exclusions_oracles import validate_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt',type=Path,default=RECEIPT)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize:
        parser.error('Run from repository root with assertions enabled')
    out=args.out.resolve()
    if not out.is_relative_to(OUTPUT):parser.error('Output outside owned tests directory')
    out.mkdir(parents=True,exist_ok=True)
    _,binding=candidate_binding(args.receipt)
    seeds=ROOT/'work/build/memcheck/full_bag_6mons.sav'
    input_binding=dict(negative_seed_save_sha256=sha256(seeds))
    report=dict(status='running',started_utc=utc(),driver='native_exclusions.py',
        layer='native ARM gameplay recipient exclusions',nonce=os.environ.get('DG_TEST_NONCE'),
        old_state_loaded=False,binding=binding,input_binding=input_binding,local=[],remote=[],cases={})
    write_json(out/'result.json',report)
    for kind in ('local','remote'):
        for flags in (0,1):
            child=out/f'{kind}-{flags}'
            child.mkdir(parents=True,exist_ok=True)
            driver=Path(__file__).with_name(f'native_exclusions_{kind}.py')
            with (child/'child.log').open('w') as log:
                process=subprocess.run([sys.executable,str(driver),'--receipt',str(args.receipt.resolve()),
                    '--flags',str(flags),'--out',str(child)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                    timeout=600,env={**os.environ,'PYTHONPATH':os.pathsep.join(sys.path)})
            require(process.returncode==0,f'native {kind} exclusion child failed: exit {process.returncode}')
            row=json.loads((child/'result.json').read_text())
            require(row.get('status')=='passed' and row.get('finished_utc')
                    and row.get('binding')==binding and row.get('nonce')==report['nonce']
                    and row.get('old_state_loaded') is False,'foreign/nonterminal exclusion child')
            report[kind].append(row)
            write_json(out/'result.json',report)
    require(sha256(seeds)==input_binding['negative_seed_save_sha256'],'negative fixture source changed')
    require(candidate_binding(args.receipt)[1]==binding,'candidate source changed')
    validate_report(report,out)
    trace=out/'exclusions-trace.json'
    write_json(trace,{k:report[k] for k in ('binding','input_binding','local','remote')})
    artifacts=[dict(path=str(p.resolve()),sha256=sha256(p))
               for p in [trace,*sorted(out.rglob('*.bin')),*sorted(out.rglob('*.png')),
                         *sorted(out.rglob('fixture-templates.json')),*sorted(out.glob('*/result.json'))]]
    report.update(status='passed',finished_utc=utc(),
        cases={'growth.native_exclusions':dict(status='passed',artifacts=artifacts)})
    write_json(out/'result.json',report)


if __name__=='__main__':main()
