"""Fail-closed evidence validation and bounded subprocess supervision."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import uuid
from support import ROOT, OUTPUT, FOCUS_COUNT, sha256


def utc(): return datetime.now(timezone.utc).isoformat()


def write_json(path, data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.pending')
    temp.write_text(json.dumps(data,indent=2)+'\n');os.replace(temp,path)


def register_values(reg):
    # Harness/melonDS exposes .r[i]. Installed py-desmume RegisterAccessor instead
    # implements __getitem__; do not assume dynamic r0 attributes or .r exists.
    bank=getattr(reg,'r',reg)
    return [bank[i]&0xFFFFFFFF for i in range(4)]


def bound_process(argv, out, timeout, env=None, *, nonce=None, invocation=None, job_id=None):
    """Parent owns terminal report even if a native library aborts child Python.

    Each invocation has a nonce and log; an earlier successful report cannot be
    reused. A supervisor SIGKILL cannot be caught: its running record remains
    explicitly unacceptable to the gate, and is marked interrupted on next run.
    """
    out=Path(out).resolve()
    if not out.is_relative_to(OUTPUT): raise ValueError('Outputs outside owned tests directory')
    out.mkdir(parents=True,exist_ok=True);path=out/'process.json'
    if path.exists():
        old=json.loads(path.read_text())
        if old.get('status')=='running':
            old.update(status='interrupted',reason='prior supervisor did not finalize',finished_utc=utc())
            write_json(out/'previous-interrupted.json',old)
    nonce=nonce or uuid.uuid4().hex
    row={'status':'running','started_utc':utc(),'nonce':nonce,'argv':list(map(str,argv)),
         'timeout_seconds':timeout,'pid':None}
    if invocation is not None:row.update(invocation=invocation,job_id=job_id)
    write_json(path,row);proc=None
    def interrupted(signum,frame): raise KeyboardInterrupt(f'signal {signum}')
    previous={sig:signal.signal(sig,interrupted) for sig in (signal.SIGTERM,signal.SIGINT)}
    try:
        with (out/'process.log').open('w') as log:
            childenv=dict(os.environ,**(env or {}),DG_TEST_NONCE=nonce,PYTHONDONTWRITEBYTECODE='1')
            proc=subprocess.Popen(list(map(str,argv)),cwd=ROOT,env=childenv,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            row['pid']=proc.pid;write_json(path,row)
            try:code=proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                row.update(status='failed',reason='timeout')
            else:
                row.update(status='passed' if code==0 else 'failed',returncode=code)
                if code<0:row['reason']='child terminated by signal '+str(-code)
    except KeyboardInterrupt as exc:
        row.update(status='interrupted',reason=str(exc))
    except BaseException as exc:
        row.update(status='failed',reason=f'{type(exc).__name__}: {exc}')
    finally:
        if proc is not None and proc.poll() is None:
            os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
        for sig,handler in previous.items():signal.signal(sig,handler)
        row['finished_utc']=utc();write_json(path,row)
    return row


def validate_native(manifest, report_paths, binding, expected=None):
    """Require a declared case, terminal current execution, exact source/input/
    receipt binding, and existing hashed artifacts. Host rows cannot satisfy it.
    """
    report_paths=list(report_paths)
    definitions={case['id']:case for case in manifest['cases']}
    statuses={case['id']:{'status':'missing','reason':'no current native evidence'} for case in manifest['cases']}
    ranks={key:0 for key in statuses}
    def record(key,row,current):
        # Obsolete reports never demote current evidence. A current failure
        # claiming the same case still vetoes a pass, regardless of order.
        rank=(3 if row['status']!='passed' else 2) if current else 1
        if rank>ranks[key] or (rank==ranks[key] and json.dumps(row,sort_keys=True)<json.dumps(statuses[key],sort_keys=True)):
            statuses[key]=row;ranks[key]=rank
    for path in report_paths:
        path=Path(path)
        if not path.is_file(): continue
        report={}
        try:
            report=json.loads(path.read_text()); process=json.loads((path.parent/'process.json').read_text())
            if expected is not None:
                from native_composites import validate_slice
                if str(path.resolve()) not in expected:raise ValueError('report outside current invocation')
                validate_slice(path,binding,expected[str(path.resolve())])
            if report.get('status')!='passed' or process.get('status')!='passed': raise ValueError('nonpassing or interrupted process/report')
            if report.get('nonce')!=process.get('nonce') or not report.get('nonce'): raise ValueError('stale invocation nonce')
            if report.get('binding')!=binding: raise ValueError('stale source/input/receipt/driver binding')
            driver_layers={'native_exclusions.py':'native ARM gameplay recipient exclusions',
                           'native_special.py':'native ARM gameplay excluded special context',
                           'native_lifecycle.py':'native ARM gameplay lifecycle',
                           'native_entries.py':'native ARM gameplay entry constructors',
                           'native_ui.py':'native ARM gameplay UI',
                           'native_battle.py':'native ARM gameplay battle',
                           'native_progression.py':'native ARM gameplay progression',
                           'native_caprise.py':'native ARM gameplay cap rise',
                           'native_multiko.py':'native ARM gameplay multiple KOs',
                           'native_edges.py':'native ARM gameplay growth edges',
                           'native_items.py':'native ARM gameplay items',
                           'native_items_gates.py':'native ARM gameplay item gates',
                           'native_items_doubles.py':'native ARM gameplay doubles diagnostic',
                           'native_items_persistence.py':'native ARM gameplay remembered persistence'}
            driver=report.get('driver','native_ui.py')
            if driver not in driver_layers or report.get('layer')!=driver_layers[driver]:
                raise ValueError('not recognized native execution layer/driver')
            if report.get('old_state_loaded') is not False: raise ValueError('old state/no fresh-boot declaration')
            for key,value in report.get('cases',{}).items():
                if key not in statuses: continue
                try:
                    if not definitions[key].get('driver'): raise ValueError('required native driver not implemented')
                    if definitions[key]['driver']!=driver: raise ValueError('case belongs to a different native driver')
                    if value.get('status')!='passed': raise ValueError('case did not pass')
                    artifacts=value.get('artifacts',[])
                    if not artifacts: raise ValueError('case lacks trace/screenshot artifacts')
                    for artifact in artifacts:
                        a=Path(artifact['path']).resolve()
                        if not a.is_relative_to(path.parent.resolve()) or sha256(a)!=artifact['sha256']:
                            raise ValueError('missing/changed/outside evidence artifact')
                    if driver=='native_lifecycle.py':
                        from native_lifecycle_oracles import validate as validate_lifecycle
                        try:
                            if key != validate_lifecycle(report,path.parent): raise ValueError('lifecycle report claimed another case')
                        except AssertionError as exc: raise ValueError(str(exc)) from exc
                    if driver=='native_ui.py' and key=='ui.page_navigation':
                        from native_ui_oracles import validate_page_navigation
                        try:validate_page_navigation(report['page_navigation'])
                        except AssertionError as exc:raise ValueError(str(exc)) from exc
                    if driver=='native_exclusions.py':
                        from native_exclusions_oracles import validate_report as validate_exclusions
                        try:
                            if key not in validate_exclusions(report,path.parent):raise ValueError('recipient report claimed another case')
                        except AssertionError as exc:raise ValueError(str(exc)) from exc
                    if driver=='native_special.py':
                        from native_special_oracles import validate as validate_special
                        try:
                            if key not in validate_special(report['battles'],path.parent):raise ValueError('special report claimed another case')
                        except AssertionError as exc:raise ValueError(str(exc)) from exc
                    if driver=='native_entries.py':
                        from native_entries_oracles import validate as validate_entries
                        try:
                            if key not in validate_entries(report): raise ValueError('entry report claimed another case')
                        except AssertionError as exc: raise ValueError(str(exc)) from exc
                    if driver=='native_edges.py':
                        from native_edges_oracles import validate as validate_edges, CASES
                        if key!=CASES.get(report.get('case')):raise ValueError('edge report claimed another case')
                        try:validate_edges(report)
                        except AssertionError as exc:raise ValueError(str(exc)) from exc
                    if driver=='native_multiko.py':
                        from native_multiko_oracles import validate_matrix as validate_multiko, CASE_IDS
                        if key not in CASE_IDS:raise ValueError('multiple-KO report claimed another case')
                        try:validate_multiko(report['battles'])
                        except AssertionError as exc:raise ValueError(str(exc)) from exc
                    if driver=='native_caprise.py':
                        from native_caprise_oracles import validate as validate_caprise, CASE_IDS
                        if key not in CASE_IDS:raise ValueError('cap-rise report claimed another case')
                        try:validate_caprise(report)
                        except AssertionError as exc:raise ValueError(str(exc)) from exc
                    if driver=='native_progression.py':
                        from native_progression_oracles import validate as validate_progression
                        if key!='progression.fixture_'+report['battle']['name']:
                            raise ValueError('progression report claimed another case')
                        try:validate_progression(report['battle'])
                        except AssertionError as exc:raise ValueError(str(exc)) from exc
                    if driver=='native_items_gates.py':
                        from native_items_gates_oracles import continued, GATES
                        from native_items_cases import GATE_ITEM
                        run=report['battle']
                        if run['fault_item']!=GATE_ITEM or key!=GATES[run['gate']][2]:
                            raise ValueError('gate report claimed another case')
                        try:continued(run)
                        except AssertionError as exc:raise ValueError(str(exc)) from exc
                    record(key,{'status':'passed','report':str(path)},True)
                except (ValueError,KeyError,OSError) as exc: record(key,{'status':'incomplete','reason':str(exc)},True)
        except (ValueError,KeyError,OSError) as exc:
            for key in report.get('cases',{}) if 'report' in locals() else []:
                if key in statuses:record(key,{'status':'incomplete','reason':str(exc)},report.get('binding')==binding)
    # A reviewed visual slice can be valid even if a later independent driver
    # assertion failed. It never promotes the rest of that failed execution.
    for path in map(Path,report_paths):
        review_path=path.parent/'visual-review.json'
        if 'ui.visible_glyphs' not in statuses or not review_path.exists():continue
        try:
            review=json.loads(review_path.read_text());report=json.loads(path.read_text())
            process=json.loads((path.parent/'process.json').read_text())
            if expected is not None:
                entry=expected.get(str(path.resolve()))
                if not entry or entry['id']!='ui' or entry['nonce']!=report.get('nonce') or process.get('invocation')!=entry['invocation']:
                    raise ValueError('visual review outside selected invocation')
            if review.get('status')!='passed' or not review.get('reviewer') or not review.get('attestation'):raise ValueError('missing manual visual attestation')
            if review.get('binding')!=binding or report.get('binding')!=binding:raise ValueError('stale visual source binding')
            if not review.get('nonce') or review['nonce']!=report.get('nonce') or review['nonce']!=process.get('nonce'):raise ValueError('stale visual invocation')
            if process.get('status') not in ('passed','failed') or process.get('returncode',-1)<0 or not process.get('finished_utc'):raise ValueError('visual execution did not finalize normally')
            if report.get('old_state_loaded') is not False:raise ValueError('visual evidence used old state')
            artifacts=review.get('artifacts',[])
            names=[f'focus-{i}.png' for i in range(FOCUS_COUNT)]
            if report.get('page_navigation'):
                names += ['page-'+p['name']+'.png' for p in report['page_navigation']['points']]
            if len(artifacts)!=len(names):raise ValueError('review must cover all focus and page-navigation captures')
            for name,a in zip(names,artifacts):
                target=(path.parent/name).resolve()
                if Path(a['path']).resolve()!=target or sha256(target)!=a['sha256']:raise ValueError('changed focus capture')
            if {p.get('focus') for p in report.get('focus_regions',[])}!=set(range(FOCUS_COUNT)):raise ValueError('native focus trace incomplete')
            statuses['ui.visible_glyphs']={'status':'passed','report':str(review_path),'scope':'manually reviewed visual slice only'}
        except (ValueError,KeyError,OSError) as exc:
            statuses['ui.visible_glyphs']={'status':'incomplete','reason':str(exc)}
    from native_composites import compose
    statuses.update(compose(manifest,report_paths,binding,expected))
    return statuses


def record_focus_review(path,binding,reviewer,attestation):
    """Called only after explicit visual review of current focus and page captures."""
    path=Path(path);report=json.loads(path.read_text())
    if report.get('binding')!=binding:raise ValueError('Cannot attest stale test sources; rerun native captures first')
    names=[f'focus-{i}.png' for i in range(FOCUS_COUNT)]
    if report.get('page_navigation'):
        names += ['page-'+p['name']+'.png' for p in report['page_navigation']['points']]
    review={'status':'passed','scope':'visual slice only; native process status unchanged',
            'reviewer':reviewer,'attestation':attestation,'binding':binding,'nonce':report['nonce'],
            'artifacts':[{'path':str((path.parent/name).resolve()),'sha256':sha256(path.parent/name)} for name in names]}
    write_json(path.parent/'visual-review.json',review)
