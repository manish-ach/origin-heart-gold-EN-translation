#!/usr/bin/env python3
"""Bounded current-candidate native growth trial. Parent must own emulator launch.

--scope pair is the first checkpoint: fresh boot, two real fighter+bench wild
battles, Cap OFF/ON. --scope matrix adds Share OFF and partial-cap pairs. Nothing
here proves replay/link/facility, aggregate KOs, no-banking, or item effects.
"""
import argparse
import os
from pathlib import Path
import shutil
import sys
import traceback
from support import ROOT, OUTPUT, sha256, RECEIPT
from evidence import write_json, utc
from native_ui import candidate_binding
from native_battle_helpers import NativeSession, registers, party_summary, prepare_templates, install_fixture, capture_failure, prepare_opponent, native_free_callsite, TrainerLaunch, TRAINER_SINGLES, TRAINER_DOUBLES
from native_battle_oracles import require, validate_run, compare_caps, compare_share, validate_double, holder_verdict, root_reuse
from emu_harness import Harness, decode_pokemon
from native_battle_input import BattleInput, mon_state


class BattleTrace:
    def __init__(self, session):
        self.s, self.h, self.run = session, session.h, None
        self.pending = None
        self.recipient = None
        self.free_scope = None
        self.free_site = native_free_callsite(session)
        for name in ('dg_battle_begin', 'dg_battle_root_free', 'dg_growth_eligible', 'dg_growth_share_enabled'):
            session.hook(session.labels[name] & ~1, getattr(self, name))
        for address, method in ((0x02050C34, self.constructor),
                                (0x02214D14, lambda: self.event('teardown')),
                                (0x02215D14, self.original_begin), (0x02214CA6, self.captured),
                                (0x0201B33C, self.original_free), (0x022289B4, self.calculate),
                                (0x0221F6EC, self.native_eligible), (0x0206F09C, self.threshold),
                                (0x02224C50, self.message), (0x0222AC30, self.apply),
                                (0x02224BF8, self.command), (0x0222AC50, self.ev),
                                (0x0221D7A8, self.action)):
            session.hook(address, method)
        for address in (0xffff0004, 0xffff000c, 0xffff0010):
            session.hook(address, lambda: self.event('exception'))

    def snapshot(self):
        a = self.s.labels['snapshot']
        return dict(zip(('flags', 'cap', 'allowed', 'root', 'epoch'),
                        [self.h.u32(a+4*i) for i in range(5)]))

    def event(self, name, **data):
        if self.run is None:
            return None
        require(len(self.run['events']) < 12000, 'bounded trace overflow')
        r = registers(self.h)
        row = dict(name=name, frame=self.h.frame, lr=r[14], sp=r[13], **data)
        self.run['events'].append(row)
        return row

    def dg_battle_begin(self):
        self.event('begin', snapshot=self.snapshot(),
                   generation=self.h.u32(self.s.labels['generation']))

    def constructor(self):
        if self.run is None: return
        row = self.event('constructor', args=registers(self.h)[:4])
        def finish():
            setup = registers(self.h)[0]
            row.update(setup=setup, flags=self.h.u32(setup), control=self.h.u32(setup+0x18c))
        self.s.returned(finish)

    def original_begin(self):
        self.event('original_begin')

    def captured(self):
        if self.run is None: return
        h = self.h; labels = self.s.labels
        root = h.u32(0x02255BAC); setup = h.u32(root+0x10)
        self.event('captured', snapshot=self.snapshot(), generation=h.u32(labels['generation']),
                   setup_owner=h.u32(labels['setup_owner']), save_owner=h.u32(labels['save_owner']),
                   context=dict(root=root, setup=setup, flags=h.u32(setup), control=h.u32(setup+0x18c),
                                save=h.u32(setup+0x1c0), published_save=h.save,
                                options_copy=h.u16(h.u32(setup+0x130))))

    def dg_battle_root_free(self):
        if self.run is None:return
        require(self.free_scope is None,'nested root-free wrapper')
        row=self.event('free',root=registers(self.h)[0],snapshot=self.snapshot(),
                       generation=self.h.u32(self.s.labels['generation']))
        scope=dict(root=row['root'],calls=0,run=self.run)
        self.free_scope=scope
        def finish():
            require(self.free_scope is scope and self.run is scope['run'], 'root-free lifetime changed')
            require(scope['calls']==1,'wrapper did not call original free exactly once')
            self.event('free_return',root=scope['root'],snapshot=self.snapshot(),
                       generation=self.h.u32(self.s.labels['generation']))
            self.free_scope=None
        self.s.returned(finish)

    def original_free(self):
        if self.run is None:return
        r=registers(self.h);scope=self.free_scope;site=self.free_site
        if r[14]==site['lr']:
            require(scope is not None and scope['run'] is self.run, 'original free outside wrapper lifetime')
            require(self.h.read(site['address'],4)==site['code'],'original free callsite code changed')
            require(r[0]==scope['root'],'original free changed wrapper root argument')
            scope['calls']+=1
            require(scope['calls']==1,'duplicate original free within wrapper')
            self.event('original_free',root=r[0],snapshot=self.snapshot(),
                       generation=self.h.u32(self.s.labels['generation']),
                       callsite=site['address'],wrapper_active=True)
            return
        require(scope is None,'unexpected allocator call during root-free wrapper')
        # Retain later frees of allocations reusing the historical root address;
        # pointer equality after wrapper return is not battle-root ownership.
        if any(e['name']=='free' and e['root']==r[0] for e in self.run['events']):
            self.event('allocator_reuse',root=r[0],snapshot=self.snapshot(),
                       generation=self.h.u32(self.s.labels['generation']),wrapper_active=False)

    def calculate(self):
        if self.run is None: return
        _, mon, opponent = registers(self.h)[:3]
        self.recipient = self.h.u8(mon+0x14)
        count = self.h.u8(opponent+0x1f1)
        require(count <= 6, 'unexpected participation list length')
        self.event('calculate', id=self.h.u8(mon+0x14), mon=mon, opponent=opponent,
                   opponent_hp=self.h.u16(opponent+0x1e),
                   participants=list(self.h.read(opponent+0x1f2, count)))

    def dg_growth_share_enabled(self):
        if self.run is not None:
            # Recipient comes from the native routine's own argument (set in
            # calculate); the installed C also receives its BattleMon in r0.
            arg = registers(self.h)[0]
            row = dict(id=self.recipient, arg_mon=arg, arg_id=self.h.u8(arg+0x14) if 0x02000000 <= arg < 0x023DC000 else None)
            self.s.returned(lambda: self.event('share', result=registers(self.h)[0], **row))

    def dg_growth_eligible(self):
        if self.run is None: return
        r = registers(self.h); amount, deferred, mon, raw = r[:4]
        require(self.pending is None, 'unexpected nested eligibility')
        # Installed C returns through a resident ARM adapter; caller phase is
        # captured at the two real BL seams below, never guessed from C LR.
        row = self.event('eligible', id=self.h.u8(mon+0x14), mon=mon,
                         resolved=self.h.u32(self.h.u32(0x02255BAC)+0x1d0+4*self.h.u8(mon+0x14)),
                         phase=self.phase, raw_before=self.h.read(raw, 16).hex(),
                         cache_before=self.h.u32(mon+0x18), snapshot=self.snapshot())
        self.pending = row
        def finish():
            row.update(amount=self.h.u32(amount), deferred=self.h.u32(deferred), result=registers(self.h)[0],
                       raw_after=self.h.read(raw, 16).hex())
            self.pending = None
        self.s.returned(finish)

    def native_eligible(self):
        if self.pending is None: return  # EV eligibility stays native and unhooked
        amount, deferred = registers(self.h)[:2]; row = self.pending
        def finish():
            row.update(native_amount=self.h.u32(amount), native_deferred=self.h.u32(deferred),
                       native_result=registers(self.h)[0])
        self.s.returned(finish)

    def threshold(self):
        if self.pending is None: return
        species, level = registers(self.h)[:2]; row = self.pending
        require(level == self.run.get('expected_cap',12), 'cap wrapper requested unexpected threshold')
        self.s.returned(lambda: row.update(threshold=registers(self.h)[0], threshold_species=species))

    def message(self):
        if self.run is None: return
        r = registers(self.h)
        if r[2] in (0x1d, 0x1e):
            self.event('message', id=r[3], message=r[2], amount=self.h.u32(r[13]))

    def apply(self):
        if self.run is None: return
        i, amount = registers(self.h)[:2]
        root = self.h.u32(0x02255BAC); mon = self.h.u32(root+0x1d0+4*i)
        self.event('apply', id=i, amount=amount, cache=self.h.u32(mon+0x18))
        def finish():
            backing = decode_pokemon(self.h.read(self.h.u32(mon+0x10), 236))
            self.event('cache_backing', id=i, cache=self.h.u32(mon+0x18),
                       backing={k: backing[k] for k in ('exp', 'level', 'evs', 'checksum_ok')})
        self.s.returned(finish)

    def command(self):
        if self.run is None: return
        r = registers(self.h)
        if r[0] == 0x1f:
            self.event('command', id=r[1], amount=r[2])
            root=self.h.u32(0x02255bac)
            self.event('award_actor',actor=mon_state(self.h,self.h.u32(root+0x1d0+4*2)))

    def action(self):
        if self.run is None: return
        r=registers(self.h)
        self.event('action', actor=mon_state(self.h,r[0]), move=self.h.u16(r[1]),
                   selected=self.h.u16(r[1]+2), record=self.h.read(r[1],16).hex())

    def ev(self):
        if self.run is None: return
        r = registers(self.h)
        self.event('ev', id=r[0], values=r[1:4]+[self.h.u32(r[13]+i) for i in (0, 4, 8)])


def play_double(session, trace, run, launcher):
    """Doubles: fighter1 Swift (hits both foes), fighter2 Splash, repeated until the field."""
    from emu_harness import BATTLE_BUTTONS, MOVE_BUTTONS, script_bytes
    h = session.h
    trace.run = run
    launcher.arm(run, (1, 3), 3)
    h.run_script(program=script_bytes(('LockAll',), ('TrainerBattle', TRAINER_DOUBLES, TRAINER_DOUBLES, 0, 0),
                                      ('ReleaseAll',), ('End',)))
    require(h.wait_screen('battle_menu', 1800), 'doubles constructor did not reach command menu')
    session.checkpoint(run['name']+'-menu', run)
    snap = trace.snapshot()
    require(snap['allowed'] == 1 and snap['epoch'] > 0 and snap['cap'] == run.get('expected_cap', 12) and
            snap['flags'] == run['flags'], 'installed native entry did not publish the expected snapshot')
    commands = 0
    for _ in range(400):
        if h.in_field():
            break
        if h.on_screen('battle_menu'):
            h.step(20)
            if not h.on_screen('battle_menu'):
                continue
            slot = commands % 2          # 0: fighter1 Swift, 1: fighter2 Splash
            session.touch(*BATTLE_BUTTONS['fight'], after=60)
            session.touch(*MOVE_BUTTONS[slot], after=80)
            run.setdefault('commands', []).append(dict(frame=h.frame, actor=slot+1, move=(129, 150)[slot]))
            commands += 1
            require(commands <= 12, 'doubles battle did not end within twelve commands')
            for _ in range(30):
                if not h.on_screen('battle_menu'): break
                h.step(10)
        else:
            h.step(15)
            if _ % 8 == 7:
                session.press('A', after=0)
    require(h.in_field(), 'doubles battle did not return to the field')
    h.step(900)
    party = h.array(2)
    run.update(after=party_summary(h), final_snapshot=trace.snapshot(),
               after_raw=[h.read(party+8+236*i, 236).hex() for i in range(3)])
    session.checkpoint(run['name']+'-finished', run)
    validate_double(run)
    trace.run = None


def play_battle(session, trace, run, launcher=None):
    h = session.h
    trace.run = run
    if run.get('kind', 'wild') == 'wild':
        run['opponent'] = prepare_opponent(session,trace,run)
    else:
        launcher.arm(run, (1,), 1)
        h.trainer_battle(TRAINER_SINGLES)
    require(h.wait_screen('battle_menu', 1800), 'wild constructor did not reach command menu')
    session.checkpoint(run['name']+'-menu', run)
    # Fail on missing accepted entry before consuming any battle inputs.
    snap=trace.snapshot()
    require(snap['allowed']==1 and snap['epoch']>0 and snap['cap']==run.get('expected_cap',12) and snap['flags']==run['flags'],
            'installed native entry did not publish the accepted expected-cap snapshot')
    inputs=BattleInput(session,trace,run)
    require(inputs.move(1,150,1,'splash')=='menu', 'Splash unexpectedly ended battle')
    inputs.switch()
    require(inputs.move(0,82,2,'dragon-1')=='field', 'native attack did not KO the pre-entry HP1 opponent')
    h.step(180)
    party = h.array(2)
    run.update(after=party_summary(h), final_snapshot=trace.snapshot(),
               after_raw=[h.read(party+8+236*i, 236).hex() for i in range(run.get('slots', 3))])
    session.checkpoint(run['name']+'-finished', run)
    validate_run(run)
    trace.run = None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt', type=Path, default=RECEIPT)
    p.add_argument('--out', type=Path, default=OUTPUT/'native-tests/battle')
    p.add_argument('--scope', choices=('pair', 'matrix', 'holder'), default='pair')
    p.add_argument('--kind', choices=('wild', 'trainer', 'double'), default='wild',
                   help='holder scope: wild encounter, singles trainer battle or doubles trainer battle')
    p.add_argument('--expect', choices=('fixed', 'baseline'), default='fixed',
                   help='holder scope: expected SHARE OFF behaviour of an Exp. Share holder')
    args = p.parse_args()
    if Path.cwd().resolve() != ROOT: p.error('Run from repository root')
    if sys.flags.optimize: p.error('Assertions must remain enabled')
    out = args.out.resolve()
    if not out.is_relative_to(OUTPUT): p.error('Output must remain within owned tests directory')
    out.mkdir(parents=True, exist_ok=True)
    result = dict(status='running', layer='native ARM gameplay battle', driver='native_battle.py',
                  old_state_loaded=False, nonce=os.environ.get('DG_TEST_NONCE'), started_utc=utc(),
                  scope=args.scope, cases={}, battles=[])
    def flush(): write_json(out/'result.json', result)
    flush()
    try:
        receipt, binding = candidate_binding(args.receipt); result['binding'] = binding
        source = ROOT/'work/build/memcheck/trainer.sav'; save = out/'trainer.sav'
        shutil.copyfile(source, save)
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        with Harness(rom=Path(receipt['output']['path']), sav=save, out=out, verbose=False,
                     emulator='desmume') as h, capture_failure(h, out):
            session = NativeSession(h, receipt, out); trace = BattleTrace(session)
            session.hook(0x0221F778, lambda: setattr(trace, 'phase', 'first'))
            session.hook(0x0221F83E, lambda: setattr(trace, 'phase', 'deferred'))
            result['inputs'] = session.inputs
            session.boot(); session.checkpoint('cold-field', dict(snapshot=trace.snapshot()))
            templates = prepare_templates(session)
            specs = [('zero-off', 0, False), ('zero-on', 2, False)]
            launcher = TrainerLaunch(session, trace, templates) if args.kind in ('trainer', 'double') else None
            benches = ((8, 0),)
            holder_runs = {}
            if args.scope == 'holder':
                # One level-11 bench slot 3 EXP below the cap-12 threshold; it holds an
                # Exp. Share (216) or nothing. Only the SHARE/CAP flags and the item differ.
                specs = [('share-on-holder', 0, False, 216), ('share-off-holder', 1, False, 216),
                         ('share-off-plain', 1, False, 0), ('share-off-cap-holder', 3, False, 216),
                         ('share-off-cap-plain', 3, False, 0)]
            if args.scope == 'matrix':
                specs += [('share-off-cap-off', 1, False), ('share-off-cap-on', 3, False),
                          ('partial-off', 0, True), ('partial-on', 2, True)]
            for spec in specs:
                name, flags, partial = spec[:3]
                if args.scope == 'holder':
                    benches = ((11, spec[3]),)
                options = session.options(flags)
                fixture = install_fixture(session, templates, partial, benches,
                                          ([129, 150, 0, 0], [20, 40, 0, 0]) if args.kind == 'double' else None)
                run = dict(name=name, flags=flags, threshold=fixture['threshold'], fixture=fixture,
                           options=options, before=party_summary(h), events=[])
                if args.scope == 'holder':
                    run.update(kind=args.kind, bench_item=spec[3], holders=[3] if spec[3] and args.expect == 'fixed' else [])
                    holder_runs[name] = run
                result['battles'].append(run); flush()
                try:
                    if args.kind == 'double': play_double(session, trace, run, launcher)
                    else: play_battle(session, trace, run, launcher)
                finally: flush()
            if args.scope == 'holder':
                failed, gains = holder_verdict(holder_runs, args.expect)
                result['holder_gains'] = gains; result['holder_failed'] = failed; result['holder_expect'] = args.expect
                print('HOLDER', args.expect, gains, failed, flush=True)
                require(not failed, 'holder verdict failed: ' + '; '.join(failed))
                passed = []   # reported under holder_*; not a required_native.json case
            else:
                zero_off, zero_on = result['battles'][:2]
                compare_caps(zero_off, zero_on)
                passed = ['runtime.begin_free', 'growth.two_participants',
                          'growth.zero_messages', 'growth.bench_share_on']
                # The native grass entry driver owns ordinary_0; this scripted
                # control8 fixture does not claim that distinct requirement.
                # A real positive bench control is mandatory even in pair mode.
                require(zero_on['after'][2]['exp'] > zero_on['before'][2]['exp'], 'bench ON EXP absent')
                require(any(b > a for a, b in zip(zero_on['before'][2]['evs'], zero_on['after'][2]['evs'])),
                        'bench ON EV absent')
                if args.scope == 'matrix':
                    share_off, share_cap, partial_off, partial_on = result['battles'][2:]
                    compare_caps(share_off, share_cap)
                    compare_share(zero_off, share_off); compare_share(zero_on, share_cap)
                    compare_caps(partial_off, partial_on, partial=True)
                    passed += ['growth.bench_share_off', 'growth.partial_messages']
            if args.scope == 'holder': pass
            elif root_reuse(result['battles']): passed.append('runtime.root_reuse')
            else: result['cases']['runtime.root_reuse'] = dict(status='incomplete', reason='no observed same-root reuse with changed settings')
            result['overlay_address_reuse'] = session.reused_addresses
            session.resident()
            trace_path = out/'battle-trace.json'
            write_json(trace_path, dict(binding=binding, battles=result['battles'], inputs=session.inputs,
                                       scope=args.scope, overlay_address_reuse=session.reused_addresses))
            artifacts = [trace_path,out/'fixture-templates.json',out/'fixture-seed.bin'] + \
                [out/f'fixture-level-{level}.bin' for level in (8,11,12)] + \
                [out/(r['name']+'-finished.png') for r in result['battles']]
            for battle in result['battles']:
                for record in battle['opponent']['hp_fixture']['records']:
                    artifacts.extend(Path(record[key]) for key in ('before_path','after_path'))
            for case in passed:
                result['cases'][case] = dict(status='passed', artifacts=[dict(path=str(a), sha256=sha256(a)) for a in artifacts])
        require(candidate_binding(args.receipt)[1] == binding, 'sources/inputs changed during native run')
        require(sha256(source) == binding['battery_source_sha256'], 'source battery changed')
        result['status'] = 'passed'
    except BaseException:
        result.update(status='failed', failure=traceback.format_exc())
        print(result['failure'], flush=True)
    finally:
        result['finished_utc'] = utc(); flush()
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
