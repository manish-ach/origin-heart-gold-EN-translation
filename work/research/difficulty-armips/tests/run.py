#!/usr/bin/env python3
"""Durable suite of host C, assembly, ROM data, installer and evidence gates.

Default runs no emulator. --native additionally launches bounded fresh-boot
drivers; --native-phase battle isolates battle iteration. --require-complete fails for any missing/stale/failed required native
case, even if every host test passes. It never promotes a ROM or edits sources.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback
import unittest
from native_items_cases import CASES, GATE_ITEM
from native_plan import selected as select_jobs
from native_suite import create as create_suite, resume as resume_suite, execute as execute_suite, evidence_selection
from support import OUTPUT, ROOT, SOURCE, source_hashes, RECEIPT
from evidence import write_json, utc, validate_native
sys.path.insert(0, str(SOURCE))
from build import DEV_LABEL, tool_mode

class RecordingResult(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self.passed=[]
    def addSuccess(self,test):super().addSuccess(test);self.passed.append(test.id())


def without_rom_build(suite):
    kept=[];excluded=[]
    def visit(node):
        if isinstance(node,unittest.TestSuite):
            for test in node:visit(test)
        elif node.id()=='test_installer.InstallerTests.test_isolated_install_and_atomic_failure_no_promotion':
            excluded.append(node.id())
        else:kept.append(node)
    visit(suite)
    return unittest.TestSuite(kept),excluded


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-complete',action='store_true')
    parser.add_argument('--native',action='store_true',help='Execute selected sequential plan (parent emulator permission required)')
    parser.add_argument('--native-plan',choices=('targeted','comprehensive'),default='targeted',help='Comprehensive selects every implemented slice; targeted preserves checkpoints')
    parser.add_argument('--dry-run',action='store_true',help='Print deterministic inventory only: no host tests, files, subprocesses or emulator')
    parser.add_argument('--resume-suite',type=Path,help='Use a retained invocation under exactly unchanged binding; no repeat host checks')
    parser.add_argument('--retry-jobs',nargs='+',help='Retry only named failed/unstarted jobs of --resume-suite; default retries all remaining')
    parser.add_argument('--host-no-rom-build',action='store_true',help='Explicitly exclude isolated installer ROM construction; report reduced host scope')
    parser.add_argument('--native-phase',choices=('all','battle','ui','items'),default='all',help='Target battle or ITEMS without rerunning UI; all still validates every required case')
    parser.add_argument('--battle-scope',choices=('pair','matrix','progression','caprise','multiko','edges'),default='pair',help='Pair, Share/partial matrix, six cold-boot progression fixtures, or two uninterrupted cap-rise battles')
    parser.add_argument('--edge-cases',nargs='+',choices=('gap','overlevel','curve'),default=('gap','overlevel','curve'),help='Target edge jobs without overwriting unselected reports; full phase retains all jobs')
    parser.add_argument('--items-item',type=int,choices=tuple(CASES),default=17,help='Bounded item positive/restricted pair')
    parser.add_argument('--items-scope',choices=('single','hp-status','pp-revive-checkpoint','pp-revive','pp-only','berry-flute-checkpoint','berry-flute','oran-leppa','no-effect','all-additions','gates','remembered-invalid','remembered-persistence','doubles-checkpoint','doubles-gates'),default='single',help='One item pair, or implemented HP/status matrix including both Full Restore lists')
    parser.add_argument('--items-gate-item',type=int,choices=(GATE_ITEM,791,65535),default=GATE_ITEM,help='Selected input for all three singles gate probes; invalid IDs are separate safety slices')
    parser.add_argument('--native-timeout',type=int,default=240)
    parser.add_argument('--record-focus-review',metavar='ATTESTATION',help='Record explicit completed visual review (identify the assistant or human reviewer with --reviewer) of all five current focus PNGs; does not launch native code')
    parser.add_argument('--reviewer',default='parent')
    args=parser.parse_args()
    if args.native_phase!='all' and not (args.native or args.dry_run):parser.error('--native-phase requires --native')
    if args.record_focus_review and args.native:parser.error('Record review separately after native captures finish')
    if Path.cwd().resolve()!=ROOT:parser.error('Run from repository root')
    if sys.flags.optimize:parser.error('Do not disable assertions with Python optimization')
    if not 1<=args.native_timeout<=600:parser.error('Native timeout must be 1..600 seconds')
    if args.retry_jobs and (not args.resume_suite or not args.native):parser.error('--retry-jobs requires --native --resume-suite')
    if args.dry_run:
        if args.resume_suite:parser.error('dry inventory uses plan selectors, not a retained invocation')
        jobs=select_jobs(args)
        print(json.dumps(dict(format=1,plan=args.native_plan,host_checks='once before native jobs',
            planned=len(jobs),completed=[],failed=[],unstarted=[j['id'] for j in jobs],jobs=jobs),indent=2))
        return 0
    OUTPUT.mkdir(parents=True,exist_ok=True)
    os.environ.setdefault('ARMIPS',str(Path.home()/'Developer/armips/build/armips'))
    report={'format':2,'scope':'Host/static tests and explicit native acceptance gate','status':'running','started_utc':utc(),'command':[sys.executable,*sys.argv],
            'complete':False,'success':False,'native_requested':args.native,'sources_before':source_hashes(),
            # tool_mode comes from the bound candidate receipt; host tests build in host_build_mode.
            'tool_mode':None,'host_build_mode':tool_mode()}
    path=OUTPUT/'report.json';write_json(path,report)
    try:
        from native_ui import candidate_binding
        binding=None
        try:_,binding=candidate_binding(RECEIPT);report['tool_mode']=binding['tool_mode']
        except Exception as exc:report['binding_error']=str(exc)
        invocation=None;invocation_path=None
        if args.resume_suite:
            invocation_path=args.resume_suite.resolve()
            invocation=resume_suite(invocation_path,binding)
            report['host_static']=invocation['host_static']
            report['host_reused_from']=str(invocation_path)
        else:
            suite=unittest.defaultTestLoader.discover(str(SOURCE/'tests'),pattern='test_*.py')
            if args.host_no_rom_build:
                suite,excluded=without_rom_build(suite)
                report['excluded_host_tests']=excluded
            result=unittest.TextTestRunner(verbosity=2,resultclass=RecordingResult).run(suite)
            report['host_static']={'tests_run':result.testsRun,'passed':result.passed,
              'failures':[{'test':str(t),'traceback':e} for t,e in result.failures],
              'errors':[{'test':str(t),'traceback':e} for t,e in result.errors],
              'skips':[{'test':str(t),'reason':e} for t,e in result.skipped],
              'success':result.wasSuccessful() and not result.skipped,
              'layers':{'test_host':'shipping host C + ASan/UBSan, native primitives mocked',
                        'test_policy':'shipping C host FFI','test_data':'fresh ROM numeric data vs schedule/site',
                        'test_installer':'fresh ARM compile/link/armips + isolated installer; ABI models are not ARM execution',
                        'test_assembly':'historical foundation actual assembly preserved',
                        'test_abi':'fresh ARM layouts and bounded adapter instruction models, not ARM CPU proof',
                        'test_mutations':'deliberate scratch regressions rejected by shipping-C drivers',
                        'test_source':'fresh source ROM guards','test_framework':'runner/interface negative tests; no emulator'}}
            write_json(path,report)
        if report.get('excluded_host_tests'):report['host_static']['excluded_tests']=report['excluded_host_tests']
        if args.native and invocation is None:
            invocation,invocation_path=create_suite(select_jobs(args),binding,report['host_static'])
        if invocation is not None:report['native_invocation']=str(invocation_path)
        if args.record_focus_review:
            if binding is None:raise ValueError('No current binding for visual attestation')
            from evidence import record_focus_review
            ui_path=OUTPUT/'native-tests/ui/result.json'
            if invocation is not None:
                ui=next(j for j in invocation['jobs'] if j['id']=='ui')
                if not ui['attempts']:raise ValueError('UI job has not started')
                ui_path=Path(ui['attempts'][-1]['out'])/'result.json'
            record_focus_review(ui_path,binding,args.reviewer,args.record_focus_review)
        if args.native and report['host_static']['success'] and binding is not None:
            execute_suite(invocation,invocation_path,args.native_timeout,args.retry_jobs)
        manifest=json.loads((SOURCE/'tests/required_native.json').read_text())
        if invocation is not None:
            native_paths,expected=evidence_selection(invocation)
            report['native_jobs']=invocation['inventory']
            report['native_processes']={j['id']:j['attempts'][-1].get('process',{}) for j in invocation['jobs'] if j['attempts']}
        else:
            # Host-only evaluation may inspect legacy targeted reports, never
            # import them into a newly planned invocation.
            from native_progression_cases import report_paths as progression_paths
            from native_items_matrix import report_paths as item_paths
            from native_items_gates_matrix import report_paths as gate_paths
            native_paths=[OUTPUT/'native-tests'/phase/'result.json' for phase in ('ui','reload','cold0','newgame','battle','caprise','multiko')]
            native_paths += [OUTPUT/'native-tests/edges'/case/'result.json' for case in ('gap','overlevel','curve')]
            native_paths += progression_paths(OUTPUT/'native-tests/progression')+item_paths(OUTPUT/'native-tests/items')+gate_paths(OUTPUT/'native-tests/items-gates')
            expected=None
        native=validate_native(manifest,native_paths,binding,expected) if binding is not None else {
            case['id']:{'status':'incomplete','reason':report.get('binding_error','binding unavailable')} for case in manifest['cases']}
        report['native']={'required':len(native),'passed':sum(v['status']=='passed' for v in native.values()),'cases':native}
        report['sources_after']=source_hashes();report['sources_stable']=report['sources_after']==report['sources_before']
        report['complete']=not report.get('excluded_host_tests') and not report['host_static'].get('excluded_tests') and report['host_static']['success'] and report['sources_stable'] and all(v['status']=='passed' for v in native.values())
        native_run_ok=not args.native or (invocation is not None and bool(binding) and
            all(j['status']=='passed' for j in invocation['jobs']))
        report['success']=report['host_static']['success'] and report['sources_stable'] and native_run_ok and (not args.require_complete or report['complete'])
        report['status']='passed' if report['success'] else 'incomplete' if report['host_static']['success'] and native_run_ok else 'failed'
    except KeyboardInterrupt:
        report.update(status='interrupted',success=False,complete=False,failure='runner interrupted')
    except BaseException:
        report.update(status='failed',success=False,complete=False,failure=traceback.format_exc())
    finally:
        report['finished_utc']=utc();write_json(path,report)
    print(f"Host/static: {report.get('host_static',{}).get('tests_run',0)} tests; native: {report.get('native',{}).get('passed',0)}/{report.get('native',{}).get('required','?')}; complete={report['complete']}"
          +(f'; {DEV_LABEL}' if 'development' in (report['tool_mode'],report['host_build_mode']) else ''))
    print(f'Report: {path}')
    return 0 if report['success'] else 1

if __name__=='__main__':raise SystemExit(main())
