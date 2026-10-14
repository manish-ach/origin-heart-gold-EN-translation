"""Development witness for unequal-trainer native constructor branches.

No setup flags, controls, instruction bytes, or outcomes are written in battle.
"""
import os
import sys
import shutil
import json
from pathlib import Path
from support import ROOT,OUTPUT,RECEIPT
import argparse,hashlib
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--flags',type=int,choices=(0,1),required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--receipt',type=Path,default=RECEIPT)
args=p.parse_args()
if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run at repository root with assertions enabled')
if not args.out.resolve().is_relative_to(OUTPUT):p.error('Output outside owned tests directory')
from evidence import utc
from native_ui import candidate_binding
from native_battle_helpers import NativeSession, capture_failure, prepare_templates, install_fixture, party_summary
from native_battle import BattleTrace
from native_battle_oracles import require
from emu_harness import Harness, script_bytes, decode_party_pokemon, encode_pokemon, BATTLE_BUTTONS, MOVE_BUTTONS

receipt, binding = candidate_binding(args.receipt)
for third, expected in ((1, 0x4b),):
    flags = args.flags
    require(flags in (0,1), 'bounded share selector')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    save = out / 'trainer.sav'
    shutil.copyfile(ROOT / 'work/build/memcheck/trainer.sav', save)
    report = dict(status='running', started_utc=utc(),old_state_loaded=False,nonce=os.environ.get('DG_TEST_NONCE'),flags=flags,scope='native remote recipient exclusions', binding=binding,
                  command=['TrainerBattle', 6, 8, 0, third], events=[], control_trace=[])
    def flush():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    flush()
    with Harness(rom=Path(receipt['output']['path']), sav=save, out=out,
                 verbose=False, emulator='desmume') as h, capture_failure(h, out):
        session = NativeSession(h, receipt, out)
        trace = BattleTrace(session)
        session.boot()
        session.hook(0x0221F778, lambda: setattr(trace, 'phase', 'first'))
        session.hook(0x0221F83E, lambda: setattr(trace, 'phase', 'deferred'))
        templates = prepare_templates(session)
        report['options'] = session.options(flags)
        report['fixture'] = install_fixture(session, templates, False)
        report['before'] = party_summary(h)
        trace.run = report
        prefix = (('SetFlag', 0x961), ('SetVar', 0x403f, 385)) if expected == 0x4b else ()
        h.run_script(program=script_bytes(('LockAll',), *prefix, tuple(report['command']), ('ReleaseAll',), ('End',)))
        require(h.wait_screen('battle_menu', 3600), 'native trainer command menu absent')
        captures = [e for e in report['events'] if e['name'] == 'captured']
        require(len(captures) == 1, 'native capture missing or duplicated')
        flush()
        capture = captures[0]
        context = capture['context']
        snap = capture['snapshot']
        require(context['flags'] == expected and context['control'] == 0, 'wrong real constructor branch')
        require(snap['allowed'] == 1 and snap['epoch'] > 0, 'ordinary trainer snapshot absent')
        require(capture['save_owner'] == context['save'] == context['published_save'], 'save ownership mismatch')
        require(capture['setup_owner'] == context['setup'] and snap['root'] == context['root'], 'setup/root ownership mismatch')
        def remote(phase):
            root = capture['context']['root']
            rows=[]
            for rid in range(7,13):
                mon = h.u32(root+0x1d0+4*rid)
                require(mon != 0 and h.u8(mon+0x14)==rid, 'native partner recipient missing')
                backing = h.u32(mon+0x10)
                raw = h.read(backing,236)
                require(encode_pokemon(raw)==raw,'invalid native remote recipient record')
                path=out/f'remote-{phase}-{rid}.bin';path.write_bytes(raw)
                state = decode_party_pokemon(raw)
                rows.append(dict(id=rid,mon=mon,backing=backing,pid=state['pid'],species=state['species'],exp=state['exp'],evs=state['evs'],raw=raw.hex(),path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest()))
            return rows
        report['remote_before'] = remote('before')
        def teardown():
            if trace.run is report:
                report['remote_after'] = remote('after')
        session.hook(0x02214d14, teardown)
        report['turns'] = []
        for turn in range(20):
            require(h.on_screen('battle_menu'), 'native partner local command menu absent')
            session.touch(*BATTLE_BUTTONS['fight'], after=60)
            session.touch(*MOVE_BUTTONS[0], after=80)
            for elapsed in range(0,3600,10):
                h.step(10)
                if h.in_field(): break
                if h.on_screen('battle_menu'): break
                if elapsed%120==110: session.press('A',after=0)
            else: raise AssertionError('partner native turn did not finish')
            report['turns'].append(dict(turn=turn,frame=h.frame,field=h.in_field()))
            flush()
            if h.in_field(): break
        require(h.in_field(), 'native partner battle did not finish')
        h.step(120)
        report['after'] = party_summary(h)
        require('remote_after' in report, 'partner teardown recipient observations absent')
        for old,new in zip(report['remote_before'], report['remote_after']):
            require(all(old[k]==new[k] for k in ('id','pid','species','exp','evs')), 'remote recipient gained EXP/EV')
        require(not any(e.get('id') in range(7,13) for e in report['events'] if e['name'] in ('apply','ev')), 'remote recipient awarded growth')
        require(report['after'][0]['exp']>report['before'][0]['exp'], 'positive local fighter gained no EXP')
        for slot in (1,2):
            if flags==0:require(report['after'][slot]['exp']>report['before'][slot]['exp'], 'Share ON local bench gained no EXP')
            else:require(report['after'][slot]['exp']==report['before'][slot]['exp'], 'Share OFF local bench gained EXP')
        require(trace.snapshot()['epoch']==0, 'partner battle teardown retained ownership')
        session.checkpoint('remote-growth-field', report)
        require(candidate_binding(args.receipt)[1] == binding,
                'source identity changed')
    report['status'] = 'passed'
    report['finished_utc'] = utc()
    flush()
    print(f'PASS native partner rewards exclude remote recipients; flags={flags}', flush=True)
