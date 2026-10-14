"""Host-only progression infrastructure and oracle negatives, never native proof."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from support import SOURCE, scratch, RECEIPT
from native_progression_cases import CASES, plan
from native_progression_oracles import validate


class NativeProgressionTests(unittest.TestCase):
    def test_six_isolated_checkpoints_and_valid_high_level_growth_fixtures(self):
        from native_battle_fixture import prepare_fixture_templates
        levels={8}|{s['level'] for s in CASES.values()}
        receipt=json.loads(RECEIPT.read_text())
        with scratch('progression-fixture-') as tmp:
            prepare_fixture_templates(receipt,Path(tmp),levels=levels)
            meta=json.loads((Path(tmp)/'fixture-templates.json').read_text())
            self.assertEqual(set(map(int,meta['templates'])),levels)
            for level in levels:
                mon=meta['templates'][str(level)]['decoded']
                self.assertTrue(mon['checksumOk']);self.assertEqual(mon['flags'],0)
                self.assertEqual(mon['experience'],meta['thresholds'][level])
                self.assertEqual(mon['party']['level'],level)
                self.assertEqual(mon['party']['currentHp'],mon['party']['stats']['hp'])
            self.assertGreater(meta['thresholds'][81],meta['thresholds'][80])
            self.assertGreater(meta['thresholds'][89],meta['thresholds'][88])
        jobs=plan(Path('/unused'))
        self.assertEqual(len(jobs),6);self.assertEqual(len({j['out'] for j in jobs}),6)

    @staticmethod
    def sample(name):
        # Synthetic observations test ONLY new predicate checks. validate_run is
        # patched by these unit tests; the real evidence gate always calls it.
        spec=CASES[name]
        fixture=dict(spec=spec.copy(),save=1,profile=2,vars=3)
        before=[dict(species=19,level=spec['level'],exp=1000,evs=[0]*6),
                dict(evs=[0]*6),dict(evs=[0]*6)]
        for mon in before:mon.update(checksum_ok=False,bad_egg=False)  # deliberately not real native data
        after=copy.deepcopy(before)
        for mon in after:mon['evs'][0]=1
        gain=0 if spec['cap']==spec['level'] else 10
        after[0]['exp']+=gain
        reader=dict(name='cap_reader',save=1,result=spec['cap'],
                    profile=[dict(arg=1,result=2)],vars=[dict(arg=1,result=3)],
                    badge=[dict(owner=2,id=i,result=(spec['badges']>>i)&1) for i in range(16)],
                    flag=[dict(owner=3,id=1220,result=int(spec['erika'])),dict(owner=3,id=209,result=0)])
        rows=[dict(name='original_begin'),reader,dict(name='captured'),
              dict(name='eligible',id=1,native_result=1,native_amount=10,amount=gain),
              dict(name='apply',id=2,amount=10),dict(name='apply',id=3,amount=10)]
        if gain:rows.append(dict(name='apply',id=1,amount=gain))
        return dict(name=name,fixture=fixture,expected_cap=spec['cap'],flags=2,threshold=1000,
                    obsolete_threshold=999,before=before,after=after,events=rows)

    def test_reader_wrong_predicates_owners_missing_callbacks_or_cap_rejected(self):
        for name in CASES:
            with patch('native_progression_oracles.validate_run'):
                validate(self.sample(name))
                for mutation in ('badge','badge_owner','flag','missing','save','cap','expected','order'):
                    run=self.sample(name);reader=run['events'][1]
                    if mutation=='badge':reader['badge'][0]['result']^=1
                    elif mutation=='badge_owner':reader['badge'][0]['owner']=4
                    elif mutation=='flag':reader['flag'][0]['id']=1173
                    elif mutation=='missing':reader['badge'].pop()
                    elif mutation=='save':reader['save']=4
                    elif mutation=='cap':reader['result']=12
                    elif mutation=='expected':run['expected_cap']=12
                    elif mutation=='order':run['events'][:2]=run['events'][1::-1]
                    with self.subTest(name=name,mutation=mutation),self.assertRaises(AssertionError):validate(run)

    def test_plateau_and_zero_require_actual_result_change_and_native_controls(self):
        with patch('native_progression_oracles.validate_run'):
            for name in CASES:
                run=self.sample(name)
                run['events']=[e for e in run['events'] if e['name']!='eligible']
                with self.assertRaises(AssertionError):validate(run)
            for name in ('plateau-81','plateau-89'):
                run=self.sample(name);run['after'][0]['exp']=run['before'][0]['exp']
                with self.assertRaises(AssertionError):validate(run)
            run=self.sample('erika-win');run['events'].append(dict(name='message',id=1,amount=10))
            with self.assertRaises(AssertionError):validate(run)
        with self.assertRaises(AssertionError):validate(self.sample('prefix'))  # cannot bypass base gameplay oracle

    def test_optional_research_cannot_satisfy_functional_gaps(self):
        manifest=json.loads((SOURCE/'tests/required_native.json').read_text())
        required={c['id']:c for c in manifest['cases']}
        self.assertNotIn('progression.clair',required)
        self.assertIn('progression.clair',{c['id'] for c in manifest['optional_research']})
        self.assertIsNone(required['progression.erika_routes']['driver'])
        from evidence import validate_native
        for key in ('progression.skipped_decreases','growth.no_banking'):
            self.assertEqual(required[key]['driver'],'native_composites.py')
            self.assertNotEqual(validate_native(manifest,[],{})[key]['status'],'passed')
        for name in CASES:self.assertEqual(required['progression.fixture_'+name]['driver'],'native_progression.py')
