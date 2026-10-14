#!/usr/bin/env python3
"""Native special encounter paired against default difficulty settings."""
import argparse,os,sys,shutil,json
from pathlib import Path
from support import ROOT,OUTPUT,sha256,RECEIPT
from evidence import write_json,utc
from native_ui import candidate_binding
from native_battle_helpers import NativeSession,capture_failure,registers,party_summary
from native_battle import BattleTrace
from native_battle_oracles import require
from emu_harness import Harness,script_bytes,encode_pokemon,BATTLE_BUTTONS,MOVE_BUTTONS
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--receipt',type=Path,default=RECEIPT)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--flags',type=int,choices=(0,7))
args=p.parse_args()
if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run from repository root with assertions enabled')
parent=args.out.resolve()
if not parent.is_relative_to(OUTPUT):p.error('Output outside owned tests directory')
parent.mkdir(parents=True,exist_ok=True)
receipt, binding = candidate_binding(args.receipt)
results = []
if args.flags is None:
    import subprocess
    for flags in (0,7):
        child=parent/f'special-{flags}'
        child.mkdir(parents=True,exist_ok=True)
        with (child/'child.log').open('w') as log:
            completed=subprocess.run([sys.executable,__file__,'--flags',str(flags),'--receipt',str(args.receipt.resolve()),'--out',str(child)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,timeout=600,env={**os.environ,'PYTHONPATH':os.pathsep.join(sys.path)})
        require(completed.returncode==0,'native special child failed')
        results.append(json.loads((child/'result.json').read_text()))
    from native_special_oracles import validate
    validate(results,parent)
    require(all(r['binding']==binding and r['status']=='passed' and r.get('nonce')==os.environ.get('DG_TEST_NONCE') and r.get('old_state_loaded') is False for r in results),'special child source/boot/invocation mismatch')
    write_json(parent/'special-trace.json',dict(binding=binding,battles=results))
    artifacts=[dict(path=str(q.resolve()),sha256=sha256(q)) for q in [parent/'special-trace.json',*sorted(parent.rglob('*.png')),*sorted(parent.rglob('*.bin'))]]
    write_json(parent/'result.json',dict(status='passed',finished_utc=utc(),driver='native_special.py',layer='native ARM gameplay excluded special context',nonce=os.environ.get('DG_TEST_NONCE'),old_state_loaded=False,binding=binding,battles=results,cases={'runtime.exclude_special':dict(status='passed',artifacts=artifacts)}))
    raise SystemExit(0)
for flags in (args.flags,):
    expected = 0
    out = parent
    out.mkdir(parents=True, exist_ok=True)
    save = out / 'trainer.sav'
    shutil.copyfile(ROOT / 'work/build/memcheck/trainer.sav', save)
    report = dict(status='running', started_utc=utc(),scope='fresh native excluded special context', nonce=os.environ.get('DG_TEST_NONCE'),old_state_loaded=False, binding=binding,
                  flags=flags, command=['ScrCmd_250', 19, 5], events=[], control_trace=[])
    def flush():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    flush()
    with Harness(rom=Path(receipt['output']['path']), sav=save, out=out,
                 verbose=False, emulator='desmume') as h, capture_failure(h, out):
        session = NativeSession(h, receipt, out)
        trace = BattleTrace(session)
        session.boot()
        report['options'] = session.options(flags)
        generated=h.generate_pokemon(20,level=20)
        party=h.array(2);raw=h.read(party+8+236*generated['slot'],236)
        require(encode_pokemon(raw)==raw,'invalid native lead')
        h.write(party+8,raw);h.write(party+4,(1).to_bytes(4,'little'))
        h.edit_party_mon(0,moves=[82,0,0,0],pp=[40,0,0,0])
        report['before']=party_summary(h)
        report['pp_before']=h.party()[0]['pp']
        (out/'native-lead.bin').write_bytes(h.read(party+8,236))
        trace.run = report
        h.run_script(program=script_bytes(('LockAll',), tuple(report['command']), ('ReleaseAll',), ('End',)))
        require(h.wait_screen('battle_menu', 3600), 'native trainer command menu absent')
        captures = [e for e in report['events'] if e['name'] == 'captured']
        require(len(captures) == 1, 'native capture missing or duplicated')
        flush()
        capture = captures[0]
        context = capture['context']
        snap = capture['snapshot']
        require(context['flags'] == 0 and context['control'] == 1, 'wrong real constructor branch')
        require(snap['allowed'] == 0 and snap['epoch'] == 0, 'ordinary trainer snapshot absent')
        require(context['save'] == context['published_save'], 'native setup/save ownership mismatch')
        require(capture['save_owner'] == 0 and capture['setup_owner'] == 0 and snap['root'] == 0, 'excluded entry published ownership')
        for _ in range(5):
            session.resident()
            report['control_trace'].append(dict(frame=h.frame, control=h.u32(context['setup'] + 0x18c),
                                               snapshot=trace.snapshot(), sp=registers(h)[13]))
            h.step(20)
        session.checkpoint('native-entry-menu', report)
        session.touch(*BATTLE_BUTTONS['fight'],after=60)
        session.touch(*MOVE_BUTTONS[0],after=80)
        ui=h.u32(0x02255b94)
        report['target_request']=h.u32(ui+0x3ec) if ui else None
        if ui and report['target_request']:
            session.press('R',after=40)
            session.press('A',after=50)
            if h.u32(ui+0x3ec):session.press('A',after=50)
        for elapsed in range(0,3600,10):
            h.step(10)
            if h.in_field():break
            if h.on_screen('battle_menu'):break
            if elapsed%120==110:session.press('A',after=0)
        if h.on_screen('battle_menu'):
            require(h.flee(max_tries=20),'special encounter did not flee natively')
        flush()
        require(h.in_field(),'special battle did not finish natively')
        h.step(120);report['after']=party_summary(h)
        report['pp_after']=h.party()[0]['pp']
        report['inputs']=session.inputs
        report['after_snapshot']=trace.snapshot()
        session.checkpoint('native-special-field',report)
        require(candidate_binding(args.receipt)[1] == binding,
                'source identity changed')
    report['status'] = 'passed'
    report['finished_utc'] = utc()
    flush()
    results.append(report)
raise SystemExit(0)
