#!/usr/bin/env python3
"""Fresh native grass and unequal-trainer entry constructors. Hooks only read."""
import argparse
import os
from pathlib import Path
import shutil
import sys
import traceback
from support import ROOT, OUTPUT, sha256, RECEIPT
from evidence import write_json, utc
from native_ui import candidate_binding
from native_battle_helpers import NativeSession, capture_failure, registers
from native_battle import BattleTrace
from native_battle_oracles import require
from native_entries_oracles import CASES, validate
from emu_harness import Harness, encode_pokemon, script_bytes


class EntryTrace(BattleTrace):
    def __init__(self, session, family):
        self.family = family
        if family in ('grass', 'roamer'):
            from ndspy.rom import NintendoDSRom
            session.overlays.update(NintendoDSRom.fromFile(session.receipt['output']['path']).loadArm9Overlays([2]))
        super().__init__(session)

    def constructor(self):
        if self.run is None: return
        row = self.event('constructor', args=registers(self.h)[:4])
        def finish():
            setup = registers(self.h)[0]
            row.update(setup=setup, flags=self.h.u32(setup), control=self.h.u32(setup+0x18c))
        # Natural encounters return into field overlay2. Its address overlaps
        # battle overlay14; guarding with overlay14 would discard the return.
        self.s.returned(finish, overlay=2 if self.family in ('grass', 'roamer') else None)


def observed_menu(session, trace, run):
    h = session.h
    require(h.wait_screen('battle_menu', 3600), 'native command menu absent')
    captures = [e for e in run['events'] if e['name'] == 'captured']
    require(len(captures) == 1, 'native capture absent or duplicated')
    setup = captures[0]['context']['setup']
    for _ in range(5):
        session.resident()
        run['control_trace'].append(dict(frame=h.frame, control=h.u32(setup + 0x18c),
                                        snapshot=trace.snapshot(), sp=registers(h)[13]))
        h.step(20)
    session.checkpoint(run['name'] + '-menu', run)


def exercise(session, trace, report):
    h = session.h
    if report['case'] == 'roamer':
        return exercise_roamer(session, trace, report)
    if report['case'] != 'grass':
        partner = report['case'] == 'trainer4b'
        prefix = [('SetFlag', 0x961), ('SetVar', 0x403f, 385)] if partner else []
        if report['case'] == 'trainer13':
            # A scripted double battle (entry type 0x13) started with fewer than two Pokemon freezes the original game on hardware;
            # the enabled double-battle-single-fallback fix turns it into a single battle (entry type 1). Give the fixture the
            # two-Pokemon party the native double-battle entry needs, so this job still exercises entry type 0x13.
            while len(h.party()) < 2:
                h.generate_pokemon(19, level=5)
        commands = [('LockAll',), *prefix, ('TrainerBattle', 6, 8, 0, int(partner)), ('ReleaseAll',), ('End',)]
        report['script'] = [list(c) for c in commands]
        run = dict(name=report['case'], events=[], control_trace=[])
        report['battles'].append(run); trace.run = run
        h.run_script(program=script_bytes(*commands))
        observed_menu(session, trace, run)
        return
    generated = h.generate_pokemon(20, level=100)
    party = h.array(2)
    raw = h.read(party + 8 + 236 * generated['slot'], 236)
    require(encode_pokemon(raw) == raw, 'invalid native generator output')
    (session.out / 'native-lead.bin').write_bytes(raw)
    report['lead_fixture'] = dict(species=20, level=100, sha256=sha256(session.out / 'native-lead.bin'))
    h.write(party + 8, raw)
    h.edit_party_mon(0, moves=[82, 0, 0, 0], pp=[40, 0, 0, 0])
    h.warp(9, 1047, 332)
    seen = set()
    for attempt in range(24):
        require(h.in_field(), 'natural encounter trial outside field')
        run = dict(name=f'grass-{attempt}', events=[], control_trace=[])
        report['battles'].append(run); trace.run = run
        run['walk_positions']=[]
        for step in range(240):
            position=h.position()
            require(position[0]==9,'grass trial left its native map')
            # Encounter timing can interrupt a relative left/right cycle and
            # drift onto the road. Navigate from the live tile instead; every
            # step still goes through the native field input/encounter code.
            _,x,z=position
            direction=('DOWN' if z<333 else 'UP' if z>333 else
                       'RIGHT' if x<=1046 else 'LEFT')
            row=dict(frame=h.frame,before=list(position),direction=direction)
            run['walk_positions'].append(row)
            h.step_dir(direction)
            row['after']=list(h.position())
            if any(e['name'] == 'constructor' for e in run['events']): break
        require(any(e['name'] == 'constructor' for e in run['events']), 'natural encounter absent')
        observed_menu(session, trace, run)
        capture = next(e for e in run['events'] if e['name'] == 'captured')
        require(h.flee(max_tries=20), 'natural encounter did not return to field')
        h.step(120)
        run.update(returned_to_field=h.in_field(), after_snapshot=trace.snapshot())
        session.checkpoint(run['name'] + '-field', run)
        seen.add(capture['context']['flags']); trace.run = None
        if seen == {0, 0x4a}: break


def exercise_roamer(session, trace, report):
    """Native-created Raikou, coherent location input, natural grass entry."""
    h = session.h
    generated = h.generate_pokemon(20, level=100)
    party = h.array(2)
    raw = h.read(party + 8 + 236 * generated['slot'], 236)
    require(encode_pokemon(raw) == raw, 'invalid native generator output')
    (session.out / 'native-lead.bin').write_bytes(raw)
    h.write(party + 8, raw)
    h.edit_party_mon(0, moves=[82, 0, 0, 0], pp=[40, 0, 0, 0])
    h.warp(41, 392, 203)
    writes = []
    observing = [True]
    def created():
        if observing[0]:
            r = registers(h)
            writes.append(dict(pointer=r[0], field=r[1], value=r[2]))
    session.hook(0x0202dcdc, created)
    h.run_script(program=script_bytes(('LockAll',), ('CreateRoamer', 0),
                                     ('ReleaseAll',), ('End',)), settle=240)
    observing[0] = False
    require(writes, 'native CreateRoamer did not initialize a record')
    array = h.array(21); pointer = writes[0]['pointer']
    native = h.read(pointer, 20)
    require(pointer == array + 0x10, 'foreign native roamer record')
    require(h.position() == (41, 392, 203) and h.grid().tile(392, 203) == (2, False),
            'roamer fixture is not walkable Route37 grass')
    # Separate native location byte is mapped by the unchanged native table.
    table = h.read(0x020fb2cc + 8 * 4, 4)
    require(int.from_bytes(table, 'little') == 41, 'native roamer location table changed')
    report['roamer_fixture'] = dict(pointer=pointer, array=array, native=native.hex(),
                                   writes=writes, position=[41,392,203], tile=[2,False],
                                   location_table=table.hex())
    for attempt in range(24):
        require(h.in_field() and trace.snapshot()['epoch'] == 0, 'location input after entry')
        before = h.read(pointer, 20)
        require(before[4:] == native[4:], 'native roamer identity changed before input')
        h.write(pointer, (41).to_bytes(4, 'little') + before[4:])
        h.write(array + 0x60, bytes([8]))
        run = dict(name=f'roamer-{attempt}', events=[], control_trace=[],
                   location_input=dict(map=41, index=8, before=before.hex(),
                                       after=h.read(pointer,20).hex(), before_entry=True))
        report['battles'].append(run); trace.run = run
        run['walk_positions']=[]
        for step in range(240):
            position=h.position()
            require(position[0]==41,'roamer trial left Route37')
            # Encounter timing can interrupt a relative left/right cycle and
            # drift onto the road. Navigate from the live tile instead; every
            # step still goes through the native field input/encounter code.
            _,x,z=position
            direction=('DOWN' if z<203 else 'UP' if z>203 else
                       'RIGHT' if x<=391 else 'LEFT')
            row=dict(frame=h.frame,before=list(position),direction=direction)
            run['walk_positions'].append(row)
            h.step_dir(direction)
            row['after']=list(h.position())
            if any(e['name'] == 'constructor' for e in run['events']): break
        require(any(e['name'] == 'constructor' for e in run['events']), 'natural roamer trial absent')
        observed_menu(session, trace, run)
        capture = next(e for e in run['events'] if e['name'] == 'captured')
        require(h.flee(max_tries=20), 'roamer trial did not return to field')
        h.step(120)
        run.update(returned_to_field=h.in_field(), after_snapshot=trace.snapshot())
        session.checkpoint(run['name'] + '-field', run); trace.run = None
        if capture['context']['flags'] == 0x100: break


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
    report = dict(status='running', driver='native_entries.py', layer='native ARM gameplay entry constructors',
                  old_state_loaded=False, nonce=os.environ.get('DG_TEST_NONCE'), started_utc=utc(),
                  case=args.case, battles=[], cases={key:dict(status='incomplete') for key in CASES[args.case]})
    try:
        receipt, binding = candidate_binding(args.receipt); report['binding'] = binding
        save = out/'trainer.sav'; source = ROOT/'work/build/memcheck/trainer.sav'
        shutil.copyfile(source, save)
        with Harness(rom=Path(receipt['output']['path']), sav=save, out=out,
                     verbose=False, emulator='desmume') as h, capture_failure(h, out):
            session = NativeSession(h, receipt, out); trace = EntryTrace(session, args.case)
            session.boot(); report['options'] = session.options(0)
            exercise(session, trace, report)
            report['inputs'] = session.inputs
            validate(report); session.resident()
            write_json(out/'entries-trace.json', {k:report[k] for k in
                       ('binding','case','battles','inputs','roamer_fixture') if k in report})
            artifacts = [out/'entries-trace.json', *sorted(out.glob('*.png'))]
            if args.case in ('grass', 'roamer'): artifacts.append(out/'native-lead.bin')
            rows = [dict(path=str(a), sha256=sha256(a)) for a in artifacts]
            for key in CASES[args.case]: report['cases'][key] = dict(status='passed', artifacts=rows)
        require(candidate_binding(args.receipt)[1] == binding, 'source identity changed')
        require(sha256(source) == binding['battery_source_sha256'], 'source battery changed')
        report['status'] = 'passed'
    except BaseException:
        report.update(status='failed', failure=traceback.format_exc()); print(report['failure'], flush=True)
    finally:
        report['finished_utc'] = utc(); write_json(out/'result.json', report)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__': raise SystemExit(main())
