#!/usr/bin/env python3
"""First bounded trainer ITEMS checkpoint. Parent owns all emulator launches.

Each mode has a separate cold-boot process. No battle is finished/forced; the
checkpoint ends at the next native command menu. Full ITEMS matrix is pending.
"""
import argparse
import os
from pathlib import Path
import traceback
import sys
from support import ROOT, OUTPUT, sha256, RECEIPT
from evidence import write_json, utc
from native_ui import candidate_binding
from native_battle_helpers import NativeSession, capture_failure
from native_battle_oracles import require
from native_items_fixture import prepare, install_player, install_enemy_at_launch, TRAINER
from native_items_trace import ItemsTrace
from native_items_cases import CASES, category_for, usable, case_for
from native_items_oracles import checkpoint, trainer_entry, events, input_fixture, selected_party_entry
from emu_harness import Harness, BATTLE_BUTTONS, PARTY_SLOTS


def play(session, trace, run, flush):
    h = session.h
    def point(name):
        session.checkpoint(name, run); flush()
    require(h.wait_screen('battle_menu', 1800), 'trainer constructor did not reach native command menu')
    trainer_entry(run)
    run['before'] = trace.state()
    case = case_for(run)
    input_fixture(run['before'],case)
    trace.watch_revive_hp(run['before'])
    point('trainer-menu')
    session.touch(*BATTLE_BUTTONS['bag'], after=180)
    require(events(run,'lists'), 'native battle Bag list construction not observed')
    point('bag-categories')
    if usable(run):
        # Read-only disassembly of ov9 touch tables: categories at021EE220,
        # list entries at021EE23C, Use/Cancel at021EE1B0. Field Bag coordinates
        # differ; row0 here is y8..55, not the field helper's y56.
        session.touch(64,40 if category_for(run) == 0 else 112,after=90)
        point('item-list')
        session.touch(64,32,after=60)
        point('item-detail')
        session.touch(100,170,after=180)
        require(events(run,'accept') and events(run,'commit_item'), 'native Use did not return selected item')
        point('party-targets')
        mapping = trace.party_mapping()
        selected_party_entry(mapping,case,run['before'])
        flush()
        session.touch(*PARTY_SLOTS[case['ui_slot']],after=120)
        point('party-selected')
        if case['kind'] == 'pp-one':
            for _ in range(60):
                if events(run,'move_menu'):break
                h.step(5)
            else:raise AssertionError('native Ether move-choice menu not observed')
            point('move-choices')
            # Native ov9 table021ED568; choose second move, not first/default.
            session.touch(192,72,after=120)
            require(events(run,'move_selected'), 'native move-choice selection not observed')
            point('move-selected')
        # Advance a possible native confirmation/text, bounded by actual effect
        # and command hooks. A menu pixel match alone cannot count as a turn.
        for elapsed in range(0, 2400, 15):
            h.step(15)
            if events(run,'effect') and h.on_screen('battle_menu'):
                break
            require(not h.in_field(), 'item checkpoint unexpectedly ended battle')
            if elapsed % 120 == 105:
                session.press('A',after=0)
        else:
            point('item-timeout')
            raise AssertionError('Item did not finish within bounded input wait')
    else:
        run['command_before_cancel'] = trace.command_state()
        # Parent's category-screen capture shows the blue bottom-right Back
        # button. B in that touch context did not leave the menu.
        session.touch(236,170,after=180)
        require(h.wait_screen('battle_menu',600), 'restricted Bag did not return through native cancel')
        run['command_after_cancel'] = trace.command_state()
    run['after'] = trace.state()
    trace.stop_hp_watch()
    point('returned-menu')
    checkpoint(run)
    run['checkpoint'] = 'passed'
    point('checkpoint-passed')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--receipt', type=Path, default=RECEIPT)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--item', type=int, choices=tuple(CASES), default=17)
    p.add_argument('--category', type=int, choices=(0,1))
    p.add_argument('--condition', choices=('positive','no-effect'), default='positive')
    p.add_argument('--mode', choices=('all','restricted'), required=True)
    args = p.parse_args()
    if Path.cwd().resolve() != ROOT: p.error('Run from repository root')
    if sys.flags.optimize: p.error('Assertions must remain enabled')
    out = args.out.resolve()
    if not out.is_relative_to(OUTPUT): p.error('Output must remain within owned tests directory')
    out.mkdir(parents=True,exist_ok=True)
    run = dict(name=args.mode, item=args.item, condition=args.condition, flags=4 if args.mode == 'all' else 0, events=[])
    run['category'] = CASES[args.item]['category'] if args.category is None else args.category
    category_for(run)
    result = dict(status='running', driver='native_items.py', layer='native ARM gameplay items',
                  started_utc=utc(), nonce=os.environ.get('DG_TEST_NONCE'), old_state_loaded=False,
                  cases={}, battle=run, items_pair=os.environ.get('DG_ITEMS_PAIR'), scope='Bounded item checkpoint; no full ITEMS acceptance')
    def flush(): write_json(out/'result.json',result)
    flush()
    try:
        receipt, binding = candidate_binding(args.receipt); result['binding'] = binding
        fixture = prepare(receipt,out,args.item,args.condition)
        result['fixture'] = fixture['metadata']; flush()
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
        with Harness(rom=Path(receipt['output']['path']), sav=fixture['battery'], out=out,
                     verbose=False, emulator='desmume') as h, capture_failure(h,out):
            session = NativeSession(h,receipt,out); trace = ItemsTrace(session,run)
            result['inputs'] = session.inputs
            session.boot()
            run['options'] = session.options(run['flags'])
            install_player(session,trace,fixture)
            installed = install_enemy_at_launch(session,trace,fixture)
            h.trainer_battle(TRAINER)
            session.checkpoint('pre-menu',run); flush()
            try:
                play(session,trace,run,flush)
            finally:
                trace.stop_hp_watch()
            require(len(installed) == 1, 'native trainer launch fixture callback not reached')
            result['overlay_address_reuse'] = session.reused_addresses
            session.resident()
            write_json(out/'items-trace.json',dict(binding=binding,battle=run,inputs=session.inputs,
                overlay_address_reuse=session.reused_addresses))
            # Do not promote broad restricted/effect/gate cases from this narrow
            # checkpoint. The real trainer entry does satisfy ordinary_1.
            artifacts = [out/'items-trace.json',out/'items-fixture.json',out/'fixture-templates.json',
                         out/'fixture-seed.bin',out/'damaged.bin',out/'healthy.bin',
                         out/'enemy-native-before.bin',out/'trainer-menu.png',
                         out/'trainer-launch-diagnostic.json',
                         out/'bag-categories.png',out/'returned-menu.png']
            if usable(run):
                artifacts += [out/'party-targets.png',out/'party-selected.png']
                if CASES[args.item]['kind'] == 'pp-one':
                    artifacts += [out/'move-choices.png',out/'move-selected.png']
            result['checkpoint_artifacts'] = [dict(path=str(a),sha256=sha256(a)) for a in artifacts]
            result['cases']['runtime.ordinary_1'] = dict(status='passed',
                artifacts=[dict(path=str(a),sha256=sha256(a)) for a in artifacts])
            result['cases']['items.restricted'] = dict(status='incomplete',
                reason='Single-item visibility/cancel checkpoint only; berry/flute effects and held/field-only exclusions pending')
        require(candidate_binding(args.receipt)[1] == binding, 'source/input changed during ITEMS run')
        result['status'] = 'passed'
    except BaseException:
        result.update(status='failed',failure=traceback.format_exc())
        print(result['failure'],flush=True)
    finally:
        result['finished_utc'] = utc(); flush()
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
