"""Native heap transitions and native Save/reset/Continue lifecycle witnesses."""
import argparse
import os
import shutil
import sys
import traceback
from pathlib import Path
from support import ROOT, OUTPUT, sha256, RECEIPT
from evidence import utc, write_json
from native_ui import candidate_binding, inspect_battery
from native_battle_helpers import NativeSession, capture_failure, registers, prepare_templates, install_fixture, party_summary
from native_battle import BattleTrace, play_battle
from native_battle_oracles import require
from native_lifecycle_oracles import CASES, validate
from emu_harness import Harness

def arena(session, trace, report, flush):
    h, receipt = session.h, session.receipt
    from ndspy.rom import NintendoDSRom
    # Allocations can return into field, Options or battle overlays. Each return
    # is guarded against the actual candidate overlay bytes at its caller.
    overlays = NintendoDSRom.fromFile(receipt['output']['path']).loadArm9Overlays()
    session.overlays.update(overlays)
    def stack():
        sp = registers(h)[13]
        physical = 0x02000000 + (sp & 0x003fffff)
        require(0x02000000 <= sp < 0x02800000 and 0x023e0000 <= physical < 0x02400000,
                'native stack overlaps resident reservation or leaves main-RAM stack mirror')
        report['stack_samples'].append(dict(frame=h.frame, sp=sp, physical=physical))
    def allocated():
        stack()
        regs = registers(h)
        row = dict(frame=h.frame, heap=regs[0], size=regs[1])
        require(len(report['allocations']) < 24000, 'allocation trace overflow')
        report['allocations'].append(row)
        def returned():
            address = registers(h)[0]
            row['address'] = address
            if address:
                require(0x02000000 <= address < 0x023dc000 and
                        row['size'] <= 0x023dc000 - address, 'native allocation overlaps resident reservation')
        lr = regs[14] & ~1
        overlay = None
        if 0x02100000 <= lr < 0x023DC000:
            candidates = [i for i,o in overlays.items() if o.ramAddress <= lr <= o.ramAddress+len(o.data)-8
                          and bytes(o.data[lr-o.ramAddress:lr-o.ramAddress+8]) == h.read(lr,8)]
            require(bool(candidates), 'allocation caller is not candidate overlay code')
            overlay = candidates[0]
        session.returned(returned, overlay=overlay)
    def destroyed():
        stack()
        report['destroyed_heaps'].append(dict(frame=h.frame, heap=registers(h)[0]))
    def menu():
        stack()
        state = registers(h)[0]
        row = dict(state=state, heap=h.u32(state))
        if row not in report['menu_owners']:
            report['menu_owners'].append(row)
    session.hook(0x0201b2ac, allocated)  # native general allocation
    session.hook(0x0201b2fc, allocated)  # native allocation from heap end
    session.hook(0x0201b1e4, destroyed)
    session.hook(session.labels['dg_menu_input'] & ~1, menu)
    session.hook(session.labels['dg_battle_begin'] & ~1, stack)
    session.hook(session.labels['dg_growth_eligible'] & ~1, stack)
    session.hook(0x0221F778, lambda: setattr(trace, 'phase', 'first'))
    session.hook(0x0221F83E, lambda: setattr(trace, 'phase', 'deferred'))
    session.boot()
    templates = prepare_templates(session)
    for flags in (0, 3):
        options = session.options(flags)
        fixture = install_fixture(session, templates, False)
        run = dict(name=f'arena-{flags}', flags=flags, threshold=fixture['threshold'], fixture=fixture,
                   options=options, before=party_summary(h), events=[])
        report['battles'].append(run)
        try:
            play_battle(session, trace, run)
        finally:
            flush()
    session.options(0)
    session.resident()
    owners = {r['heap'] for r in report['menu_owners']}
    destroyed_ids = {r['heap'] for r in report['destroyed_heaps']}
    require(owners and owners <= destroyed_ids, 'native Options heap lifecycle not observed')
    require(len(report['allocations']) > 20 and all('address' in r for r in report['allocations']),
            'native allocation return trace incomplete')
    require(len(report['stack_samples']) > 20, 'native stack witness incomplete')
    report['inputs'] = session.inputs

def load_identity(session, trace, report, flush):
    h, receipt, out = session.h, session.receipt, session.out
    save = out / 'trainer.sav'
    session.hook(0x0221F778, lambda: setattr(trace, 'phase', 'first'))
    session.hook(0x0221F83E, lambda: setattr(trace, 'phase', 'deferred'))
    session.boot()
    templates = prepare_templates(session)
    def battle(name, flags):
        options = session.options(flags)
        fixture = install_fixture(session, templates, False)
        run = dict(name=name, flags=flags, threshold=fixture['threshold'], fixture=fixture,
                   options=options, before=party_summary(h), events=[])
        report['battles'].append(run)
        try:
            play_battle(session, trace, run)
        finally:
            flush()
        return run
    first = battle('before-reset', 0)
    selected = session.options(3)
    report['selected_options'] = selected
    report['save_owner_before_reset'] = h.save
    offset = selected['address'] - h.save - 0x10
    previous = inspect_battery(save, offset)
    report['previous_battery'] = previous
    session.touch(123, 73, after=120)
    for _ in range(3):
        session.press('A', after=180)
    h.step(1200)
    battery = out / 'native-saved.sav'
    require(h.emu.backup.export_file(str(battery)), 'native battery export failed')
    persisted = inspect_battery(battery, offset)
    require(persisted['options'] == selected['after'] and persisted['counter'] != previous['counter'],
            'native Save did not persist changed settings and advance generation')
    report['native_battery'] = persisted
    report['before_reset_bss'] = [h.read(a, z-a).hex() for a, z in receipt['build']['zero_ranges']]
    require(any(any(bytes.fromhex(v)) for v in report['before_reset_bss']), 'reset witness lacks live BSS')
    session.inputs.append(dict(frame=h.frame, held_reset_chord=['L', 'R', 'START', 'SELECT']))
    h.hold('L', 'R', 'START', 'SELECT')
    h.step(30)
    h.release()
    h.step(360)
    report['reset_zero_ranges'] = receipt['build']['zero_ranges']
    report['reset_loader_bss'] = [h.read(a, z-a).hex() for a, z in receipt['build']['zero_ranges']]
    require(not any(any(bytes.fromhex(v)) for v in report['reset_loader_bss']), 'native reset did not clear all resident BSS')
    session.checkpoint('native-reset-loader', report)
    h.step(2040)
    session.press('START', after=700)
    session.press('A', after=200)
    session.press('A', after=900)
    require(h.in_field() and h.u16(h.array(1)) == selected['after'], 'Continue did not load native saved settings')
    report['save_owner_after_reset'] = h.save
    report['loaded_snapshot'] = trace.snapshot()
    report['loaded_options'] = h.u16(h.array(1))
    require(trace.snapshot()['epoch'] == 0, 'load retained an old battle epoch')
    second = battle('after-reset', 3)
    first_capture = next(e for e in first['events'] if e['name'] == 'captured')
    second_capture = next(e for e in second['events'] if e['name'] == 'captured')
    require(first_capture['snapshot']['flags'] == 0 and second_capture['snapshot']['flags'] == 3,
            'new battle reused pre-reset settings')
    require(second_capture['save_owner'] == second_capture['context']['save'] == h.save,
            'post-load battle did not bind current native SaveData owner')
    report['inputs'] = session.inputs

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case', choices=tuple(CASES), required=True)
    p.add_argument('--receipt', type=Path, default=RECEIPT)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if Path.cwd().resolve() != ROOT or sys.flags.optimize: p.error('Run at repository root with assertions enabled')
    out = args.out.resolve()
    if not out.is_relative_to(OUTPUT): p.error('Output outside owned tests directory')
    out.mkdir(parents=True, exist_ok=True)
    report = dict(status='running', driver='native_lifecycle.py', layer='native ARM gameplay lifecycle',
                  old_state_loaded=False, nonce=os.environ.get('DG_TEST_NONCE'), started_utc=utc(),
                  case=args.case, battles=[], allocations=[], destroyed_heaps=[], menu_owners=[], stack_samples=[],
                  cases={CASES[args.case]:dict(status='incomplete')})
    def flush(): write_json(out/'result.json', report)
    flush()
    try:
        receipt, binding = candidate_binding(args.receipt); report['binding'] = binding
        source = ROOT/'work/build/memcheck/trainer.sav'; save = out/'trainer.sav'
        shutil.copyfile(source, save)
        with Harness(rom=Path(receipt['output']['path']), sav=save, out=out,
                     verbose=False, emulator='desmume') as h, capture_failure(h, out):
            session = NativeSession(h, receipt, out); trace = BattleTrace(session)
            globals()[args.case](session, trace, report, flush)
            validate(report, out); session.resident()
            write_json(out/'lifecycle-trace.json', {k:v for k,v in report.items() if k not in ('cases','status','finished_utc')})
            artifacts = [a for a in sorted(out.rglob('*')) if a.is_file() and a.name not in
                         ('result.json','process.json','process.log','trainer.sav')]
            report['cases'][CASES[args.case]] = dict(status='passed', artifacts=[dict(path=str(a),sha256=sha256(a)) for a in artifacts])
        require(candidate_binding(args.receipt)[1] == binding, 'source identity changed')
        require(sha256(source) == binding['battery_source_sha256'], 'source battery changed')
        report['status'] = 'passed'
    except BaseException:
        report.update(status='failed', failure=traceback.format_exc()); print(report['failure'], flush=True)
    finally:
        report['finished_utc'] = utc(); flush()
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
