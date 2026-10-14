"""Independent native lifecycle acceptance; the ordinary battle oracle still applies."""
import json
from support import ROOT, RECEIPT
from native_battle_oracles import require, validate_run

CASES = {'arena': 'runtime.arena', 'load_identity': 'runtime.load_identity'}


def validate(report, out=None):
    case = report['case']
    require(case in CASES and len(report['battles']) == 2, 'incomplete lifecycle battle pair')
    captures = []
    for run, flags in zip(report['battles'], (0, 3)):
        require(run['flags'] == flags, 'wrong lifecycle settings sequence')
        validate_run(run)
        capture = next(e for e in run['events'] if e['name'] == 'captured')
        require(capture['snapshot']['flags'] == flags, 'stale captured settings')
        captures.append(capture)
    if case == 'arena':
        allocations = report['allocations']
        require(20 < len(allocations) < 24000, 'incomplete/unbounded native allocation trace')
        for row in allocations:
            require(isinstance(row['address'], int) and row['size'] >= 0, 'allocation return missing')
            if row['address']:
                require(0x02000000 <= row['address'] < 0x023DC000 and
                        row['size'] <= 0x023DC000-row['address'], 'allocation overlaps resident reservation')
        samples = report['stack_samples']
        require(len(samples) > 20, 'native stack transition witness incomplete')
        for row in samples:
            require(0x02000000 <= row['sp'] < 0x02800000 and
                    row['physical'] == 0x02000000 + (row['sp'] & 0x003fffff) and
                    0x023e0000 <= row['physical'] < 0x02400000, 'stack overlaps resident reservation')
        owners = {r['heap'] for r in report['menu_owners']}
        require(owners and owners <= {r['heap'] for r in report['destroyed_heaps']},
                'Options native heap destruction absent')
        require(owners <= {r['heap'] for r in allocations if r['address']},
                'native Options allocations absent')
        require(len([i for i in report['inputs'] if i.get('hold') == 'L']) == 3,
                'Options/battle/reopen lifecycle incomplete')
    else:
        ranges = json.loads(RECEIPT.read_text())['build']['zero_ranges']
        require(report['reset_zero_ranges'] == ranges, 'wrong reset BSS observation ranges')
        before, after = report['before_reset_bss'], report['reset_loader_bss']
        require(len(before) == len(after) == len(ranges) and bool(ranges), 'incomplete reset BSS observations')
        for (a, z), old, new in zip(ranges, before, after):
            require(len(bytes.fromhex(old)) == len(bytes.fromhex(new)) == z-a and not any(bytes.fromhex(new)),
                    'native reset retained resident BSS')
        require(any(any(bytes.fromhex(v)) for v in before), 'no live pre-reset BSS witness')
        require(report['loaded_snapshot']['epoch'] == 0 and report['loaded_options'] == report['selected_options']['after'],
                'Continue retained a snapshot or lost native saved options')
        saved, previous = report['native_battery'], report['previous_battery']
        require(saved['options_offset'] == report['selected_options']['address']-
                report['save_owner_before_reset']-0x10, 'saved options inspection belongs to another owner')
        if out is not None:
            from native_ui_oracles import inspect_battery
            require(inspect_battery(out/'native-saved.sav',saved['options_offset']) == saved,
                    'native saved battery differs from observed generation')
            require(inspect_battery(ROOT/'work/build/memcheck/trainer.sav',saved['options_offset']) == previous,
                    'original battery generation differs from source fixture')
        require(saved['options'] == report['selected_options']['after'] and saved['counter'] != previous['counter'],
                'native Save not committed')
        slot = next(s for s in saved['slots'] if s['base'] == saved['selected_base'])
        require(slot['coherent'] and all(b['valid'] and b['counter'] == saved['counter'] for b in slot['blocks']),
                'incoherent native battery generation')
        require(any(i.get('held_reset_chord') == ['L', 'R', 'START', 'SELECT'] for i in report['inputs']),
                'native in-game reset absent')
        for capture, owner in zip(captures, (report['save_owner_before_reset'], report['save_owner_after_reset'])):
            require(capture['context']['save'] == capture['save_owner'] == owner != 0,
                    'battle belongs to a stale SaveData owner')
    return CASES[case]
