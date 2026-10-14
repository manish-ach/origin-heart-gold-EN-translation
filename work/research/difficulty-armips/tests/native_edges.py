#!/usr/bin/env python3
"""Two battles per cold boot; parent alone runs each bounded edge control."""
import argparse,hashlib,json,os,shutil,struct,sys,traceback
from pathlib import Path
from support import ROOT,OUTPUT,sha256,RECEIPT
from evidence import write_json,utc
from native_ui import candidate_binding
from native_battle import play_battle
from native_progression import ProgressionTrace
from native_battle_helpers import NativeSession,party_summary,capture_failure
from native_battle_fixture import prepare_fixture_templates
from native_progression_fixture import install
from native_caprise_fixture import field_state,advance_badge
from native_edges_oracles import CASES,specs,validate
from native_battle_oracles import require
from emu_harness import Harness,encode_pokemon,decode_pokemon


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',choices=tuple(CASES),required=True)
    p.add_argument('--receipt',type=Path,default=RECEIPT)
    p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    if Path.cwd().resolve()!=ROOT or sys.flags.optimize:p.error('Run at root with assertions enabled')
    out=args.out.resolve()
    if not out.is_relative_to(OUTPUT):p.error('Output outside tests directory')
    out.mkdir(parents=True,exist_ok=True)
    report=dict(status='running',driver='native_edges.py',layer='native ARM gameplay growth edges',
                case=args.case,old_state_loaded=False,nonce=os.environ.get('DG_TEST_NONCE'),
                started_utc=utc(),cases={CASES[args.case]:dict(status='incomplete')},battles=[],field_states={})
    def flush():write_json(out/'result.json',report)
    flush()
    try:
        receipt,binding=candidate_binding(args.receipt);report['binding']=binding
        source=ROOT/'work/build/memcheck/trainer.sav';save=out/'trainer.sav';shutil.copyfile(source,save)
        case=args.case;stages=specs(case)
        levels=(8,55) if case=='gap' else (8,20) if case=='overlevel' else (8,11,12)
        templates=prepare_fixture_templates(receipt,out,levels=levels,species=1 if case=='curve' else 19)
        meta=json.loads((out/'fixture-templates.json').read_text());report['metadata']=meta
        evolved=None
        if case=='overlevel':
            evolved=prepare_fixture_templates(receipt,out/'level100',levels=(100,),species=20)[100]
            report['level100_input']=json.loads((out/'level100/fixture-templates.json').read_text())
        from ndspy.rom import NintendoDSRom
        from ndspy.narc import NARC
        rom=NintendoDSRom.fromFile(receipt['output']['path'])
        personal=NARC(rom.getFileByName('a/0/0/2')).files
        growth=NARC(rom.getFileByName('a/0/0/3')).files
        report['reference_growth_rate']=personal[19][19]
        # Native victory evolution may change the carried species. Preserve it;
        # archive exact candidate tables for each actual pre-entry recipient.
        report['recipient_growth']={}
        os.environ['SDL_AUDIODRIVER']='dummy'
        with Harness(rom=Path(receipt['output']['path']),sav=save,out=out,verbose=False,
                     emulator='desmume') as h,capture_failure(h,out):
            s=NativeSession(h,receipt,out);t=ProgressionTrace(s)
            s.hook(0x0221F778,lambda:setattr(t,'phase','first'))
            s.hook(0x0221F83E,lambda:setattr(t,'phase','deferred'))
            report['inputs']=s.inputs;s.boot();s.checkpoint('cold-field',dict(snapshot=t.snapshot()))
            options=None
            for index,spec in enumerate(stages):
                flags=2 if case=='gap' or index else 0
                if case=='gap' and index:
                    entry=field_state(s,t,options);report['field_states']['entry']=entry
                    require(entry==report['field_states']['after'],'state drift after Koga badge edit')
                    fixture=dict(spec=spec,save=h.save,profile=entry['profile'],vars=entry['vars'],
                                 note='Same native party/inventory; only Koga badge changed between battles')
                else:
                    options=s.options(flags);fixture=install(s,t,templates,spec)
                    if case in ('curve','overlevel'):
                        slot=0 if case=='curve' else 1
                        raw=encode_pokemon(templates[11],exp=meta['thresholds'][12]-7) if case=='curve' else evolved
                        require(decode_pokemon(raw)['checksum_ok'],'invalid edge typed input')
                        require(t.run is None and t.snapshot()['epoch']==0 and h.in_field(),'late edge input')
                        h.write(h.array(2)+8+236*slot,raw)
                        require(h.read(h.array(2)+8+236*slot,236)==raw,'edge input readback mismatch')
                        fixture['party_sha256'][slot]=__import__('hashlib').sha256(raw).hexdigest()
                        (out/f'input-{index}-slot{slot}.bin').write_bytes(raw)
                run=dict(name=f'{case}-{index}',flags=flags,expected_cap=spec['cap'],
                         threshold=meta['thresholds'][spec['cap']],fixture=fixture,options=options,
                         before=party_summary(h),events=[])
                for mon in run['before']:
                    species=mon['species'];pbytes=bytes(personal[species]);gbytes=bytes(growth[pbytes[19]])
                    report['recipient_growth'][str(species)]=dict(species=species,growth_rate=pbytes[19],
                        personal_sha256=hashlib.sha256(pbytes).hexdigest(),growth_sha256=hashlib.sha256(gbytes).hexdigest(),
                        thresholds=list(struct.unpack('<101I',gbytes)),candidate_sha256=receipt['output']['sha256'])
                report['battles'].append(run);flush()
                try:play_battle(s,t,run)
                finally:flush()
                if case=='gap' and index==0:
                    before=field_state(s,t,options)
                    report['field_states']['before']=before
                    report['field_states']['after']=advance_badge(s,t,options,before,old_badges=0xffdf,new_badges=0xffff)
                    s.checkpoint('gap-badge-only',report)
            validate(report);s.resident();report['overlay_address_reuse']=s.reused_addresses
            path=out/'edges-trace.json';write_json(path,report)
            artifacts=[path,out/'fixture-templates.json',out/'fixture-seed.bin']
            artifacts += [out/f'fixture-level-{level}.bin' for level in templates]
            artifacts += list(out.glob('input-*-slot*.bin'))
            if case=='overlevel':
                artifacts += [out/'level100'/name for name in ('fixture-templates.json','fixture-seed.bin','fixture-level-100.bin')]
            if case=='gap':artifacts.append(out/'gap-badge-only.png')
            for run in report['battles']:
                artifacts.append(out/(run['name']+'-finished.png'))
                for record in run['opponent']['hp_fixture']['records']:
                    artifacts.extend(Path(record[k]) for k in ('before_path','after_path'))
            report['cases'][CASES[case]]=dict(status='passed',artifacts=[dict(path=str(a),sha256=sha256(a)) for a in artifacts])
        require(candidate_binding(args.receipt)[1]==binding,'sources changed during edges run')
        require(sha256(source)==binding['battery_source_sha256'],'source battery changed')
        report['status']='passed'
    except BaseException:
        report.update(status='failed',failure=traceback.format_exc());print(report['failure'],flush=True)
    finally:report['finished_utc']=utc();flush()
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
