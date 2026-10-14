"""Authentic persistence evidence rejects reseeding and lifecycle shortcuts."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from support import scratch, RECEIPT
from test_native_items import sample, medicine_sample
from native_items_cases import GATE_ITEM
from native_items_persistence import validate, fixture
from native_items_gates_matrix import plan, plan_remembered, plan_persistence, report_paths


def evidence():
    first=medicine_sample(GATE_ITEM,0,True)
    for state in (first['before'],first['after']):state['mons']['13']['hp']=1
    first['after_potion']=first.pop('after')
    first['events'].append(dict(name='remember_set',item=GATE_ITEM,stored_item=GATE_ITEM,category=0,stored_category=0))
    first['potion_event_count']=len(first['events'])
    first['events'] += [dict(name='move_verified',actor=1,move=82),dict(name='award_actor',enemy=dict(hp=0)),
        dict(name='teardown'),dict(name='root_free',root=first['before']['snapshot']['root'],after=dict(epoch=0))]
    second=sample(False)
    second['events']=[e for e in second['events'] if e['name'] in ('constructor','begin','captured','lists')]
    for state in (second['before'],second['after']):
        state['quantity']=2;state['snapshot']['epoch']=3
        bag=bytearray.fromhex(state['bag']);bag[state['item_offset']+2:state['item_offset']+4]=(2).to_bytes(2,'little');state['bag']=bag.hex()
    for e in second['events']:
        if e['name']=='captured':e['generation']=3;e['snapshot']['epoch']=3
        if e['name']=='lists':e['args']['remembered']=0
    before=bytearray(0x30);before[0x1c]=GATE_ITEM
    second['events'] += [dict(name='remember_check',before=dict(remembered=GATE_ITEM,bag=500),after=dict(remembered=0),
        result=0,raw_before=before.hex(),raw_after=bytes(0x30).hex()),
        dict(name='remembered',item=GATE_ITEM,quantity=1,result=0,bag=500)]
    second['command_before']=second['command_after']=dict(slot=0,command='00'*12)
    hashes=['a'*64,'b'*64,'c'*64];second['player_backing_hashes']=hashes
    field=dict(hashes=hashes,inventory=dict(quantity=2,bag=second['before']['bag']))
    return dict(battles=[first,second],boundary=dict(after_ko=deepcopy(field),after_options=deepcopy(field),
        before_second=deepcopy(field),snapshot=dict(epoch=0)))


class PersistenceTests(unittest.TestCase):
    def test_authentic_route_requires_all_boundaries_and_no_shortcuts(self):
        validate(evidence())
        for mutation in ('remember_set','ko','free','options_party','options_bag','import','epoch','flags',
                         'remembered_input','remembered_result','category_clear','second_turn','reseed','fault'):
            r=evidence();a,b=r['battles']
            if mutation=='remember_set':next(e for e in a['events'] if e['name']=='remember_set')['stored_item']=0
            elif mutation=='ko':next(e for e in a['events'] if e['name']=='award_actor')['enemy']['hp']=1
            elif mutation=='free':next(e for e in a['events'] if e['name']=='root_free')['after']['epoch']=1
            elif mutation=='options_party':r['boundary']['after_options']['hashes'][0]='d'*64
            elif mutation=='options_bag':r['boundary']['after_options']['inventory']['quantity']=3
            elif mutation=='import':b['player_backing_hashes']=['d'*64]*3
            elif mutation=='epoch':next(e for e in b['events'] if e['name']=='captured')['snapshot']['epoch']=1
            elif mutation=='flags':next(e for e in b['events'] if e['name']=='captured')['snapshot']['flags']=4
            elif mutation=='remembered_input':next(e for e in b['events'] if e['name']=='remember_check')['before']['remembered']=0
            elif mutation=='remembered_result':next(e for e in b['events'] if e['name']=='remembered')['result']=1
            elif mutation=='category_clear':
                check=next(e for e in b['events'] if e['name']=='remember_check');raw=bytearray.fromhex(check['raw_after']);raw[0x1b]=1;check['raw_after']=raw.hex()
            else:b['events'].append(dict(name={'second_turn':'action','reseed':'enemy_fixture','fault':'remembered_fault_input'}[mutation]))
            with self.subTest(mutation=mutation),self.assertRaises(AssertionError):validate(r)

    def test_initial_fixture_uses_strict_typed_hp1_enemy_and_dragon_rage_actor(self):
        receipt=json.loads(RECEIPT.read_text())
        import save_core
        with scratch('persistence-fixture-') as tmp:
            f,enemy=fixture(receipt,Path(tmp))
            actor=save_core.request('decodePokemon',f['damaged'],diagnostic=False)
            target=save_core.request('decodePokemon',enemy['healthy'],diagnostic=False)
            self.assertEqual(actor['party']['currentHp'],1)
            self.assertEqual(target['party']['currentHp'],1)
            self.assertNotEqual(enemy['healthy'],f['healthy'])
            self.assertEqual(f['metadata']['records'][0]['sha256'],f['metadata']['damaged']['sha256'])
            self.assertTrue(actor['checksumOk'] and target['checksumOk'])

    def test_persistence_index_is_one_boot_separate_from_injected_remembered_jobs(self):
        with scratch('persistence-index-') as tmp:
            plan(tmp);plan_remembered(tmp);jobs=plan_persistence(tmp)
            self.assertEqual(len(jobs),1);self.assertTrue(jobs[0]['persistence'])
            self.assertEqual(len(report_paths(tmp)),6)
            again=plan_persistence(tmp);self.assertNotEqual(jobs[0]['out'],again[0]['out'])
            self.assertEqual(len(report_paths(tmp)),6)


if __name__=='__main__':unittest.main()
