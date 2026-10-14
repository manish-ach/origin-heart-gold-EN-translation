"""Development: native egg/fainted/empty exclusion with positive recipients."""
import os
import sys
import json
import shutil
import hashlib
import datetime
from pathlib import Path
from support import ROOT, OUTPUT, RECEIPT
import argparse
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--flags',type=int,choices=(0,1),required=True)
p.add_argument('--receipt',type=Path,default=RECEIPT)
args=p.parse_args()
if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run at repository root with assertions enabled')
from native_ui import candidate_binding
from native_battle_helpers import NativeSession, capture_failure, install_fixture, party_summary
from native_battle import BattleTrace
from native_exclusion_play import play_battle
from native_battle_oracles import require
from emu_harness import Harness, encode_pokemon
import save_core
from evidence import utc

receipt, binding = candidate_binding(args.receipt)
out = args.out.resolve()
if not out.is_relative_to(OUTPUT):p.error('Output outside owned tests directory')
out.mkdir(parents=True, exist_ok=True)
save = out / 'trainer.sav'
shutil.copyfile(ROOT / 'work/build/memcheck/trainer.sav', save)
report = dict(status='running',started_utc=utc(), binding=binding, scope='native local recipient exclusions',old_state_loaded=False,nonce=os.environ.get('DG_TEST_NONCE'), battles=[])
def flush():
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
flush()
with Harness(rom=Path(receipt['output']['path']), sav=save, out=out,
             verbose=False, emulator='desmume') as h, capture_failure(h, out):
    session = NativeSession(h, receipt, out)
    trace = BattleTrace(session)
    session.hook(0x0221F778, lambda: setattr(trace, 'phase', 'first'))
    session.hook(0x0221F83E, lambda: setattr(trace, 'phase', 'deferred'))
    h.set_clock(datetime.datetime(2026,10,9,12))
    session.boot()
    from native_battle_fixture import prepare_fixture_templates
    templates = prepare_fixture_templates(receipt,out,levels=(1,8,11,12))
    for flags in (args.flags,):
        options = session.options(flags)
        fixture = install_fixture(session, templates, False)
        party = h.array(2)
        # Held Share is covered separately; this fixture isolates recipient exclusions.
        h.edit_party_mon(2,item=0)
        fixture["party_sha256"][2]=hashlib.sha256(h.read(party+8+2*236,236)).hexdigest()
        from native_exclusion_fixture import prepare_fixture_templates as exclusion_templates
        egg_seed=exclusion_templates(receipt,out/'egg-fixture',levels=(1,),seed_slot=1)[1]
        fainted_seed=exclusion_templates(receipt,out/'fainted-fixture',levels=(8,),seed_slot=2)[8]
        egg = encode_pokemon(egg_seed,egg=True,exp=0,friendship=20,moves=[0,0,0,0],pp=[0,0,0,0])
        fainted = encode_pokemon(fainted_seed, currentHp=0)
        require(encode_pokemon(egg) == egg and encode_pokemon(fainted) == fainted, 'invalid exclusion inputs')
        for slot, raw in ((3, egg), (4, fainted)):
            h.write(party + 8 + 236 * slot, raw)
            fixture['party_sha256'].append(hashlib.sha256(raw).hexdigest())
        h.w32(party + 4, 5)
        run = dict(name=f'exclusions-share-{flags}', flags=flags, threshold=fixture['threshold'],
                   fixture=fixture, options=options, before=party_summary(h), events=[])
        run['negative_records']=[]
        for slot in (3,4):
            path=out/f'share-{flags}-slot-{slot}-before.bin'
            path.write_bytes(h.read(party+8+236*slot,236))
            run['negative_records'].append(dict(slot=slot,before_path=str(path.resolve())))
        run['egg_input_method']='typed closed egg fixture through sealed save-core; no native generator or GiveEgg'
        def empty_slot():
            root = h.u32(0x02255bac)
            run['empty_slot'] = dict(root=root, resolver=h.u32(root + 0x1d0 + 4 * 6))
        session.hook(0x02214ca6, empty_slot)
        report['battles'].append(run)
        flush()
        try:
            play_battle(session, trace, run)
        finally:
            flush()
        require(run['empty_slot']['resolver'] == 0, 'empty recipient acquired a BattleMon')
        require(not any(e.get('id') == 6 and e['name'] in ('calculate', 'eligible', 'apply', 'ev')
                        for e in run['events']), 'empty recipient received a native reward operation')
        egg_after=h.read(party+8+3*236,236)
        egg_before=save_core.request('decodePokemon',egg,diagnostic=False)
        decoded=save_core.request('decodePokemon',egg_after,diagnostic=False)
        require(all(decoded[k]==egg_before[k] for k in ('pid','speciesId','experience','evs','isEgg')),
                'native egg EXP/EV or identity changed')
        run['egg_output_format']=dict(closed_checksum_ok=decoded['checksumOk'],
            closed_growth_identity_unchanged=True,original_control_required=False)
        before,after=run['before'][4],run['after'][4]
        require(before['exp']==after['exp'] and before['evs']==after['evs'],'fainted recipient gained EXP or EVs')
        for slot in (3,4):
            require(not any(e.get('id') == slot + 1 and e['name'] in ('apply', 'ev')
                            for e in run['events']), 'excluded recipient received an award callback')
        require(run['after'][1]['exp'] > run['before'][1]['exp'], 'positive fighter reward absent')
        if flags == 0:
            require(run['after'][2]['exp'] > run['before'][2]['exp'], 'positive bench control absent')
        for row in run['negative_records']:
            path=out/f'share-{flags}-slot-{row['slot']}-after.bin'
            path.write_bytes(h.read(party+8+236*row['slot'],236))
            row['after_path']=str(path.resolve())
        flush()
    require(candidate_binding(args.receipt)[1] == binding,
            'source identity changed')
report['status'] = 'passed'
report['finished_utc']=utc()
flush()
print('PASS native egg/fainted/empty exclusions with Share ON/OFF and positive reward controls', flush=True)
