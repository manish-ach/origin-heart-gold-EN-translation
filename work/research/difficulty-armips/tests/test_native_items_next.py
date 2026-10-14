"""Adversarial aggregation, no-effect and non-clipping revival regressions."""
import copy
import json
from pathlib import Path
import unittest
from support import scratch, sha256, RECEIPT
from evidence import validate_native, write_json
from native_items_cases import NO_EFFECT, case_for
from native_items_oracles import checkpoint
from native_items_matrix import plan, variants, report_paths
from native_items_evidence import validate_item_pair, validate_no_effect
from test_native_items import medicine_sample


class NextItemsTests(unittest.TestCase):
    def test_aggregator_is_order_independent_and_current_failures_still_veto(self):
        binding={'current':True};manifest={'cases':[{'id':k,'driver':'native_items.py'} for k in ('a','b')]}
        with scratch('mixed-native-evidence-') as tmp:
            root=Path(tmp)
            def report(name,bind=binding,key='a',mutate=None):
                out=root/name;out.mkdir();artifact=out/'trace.json';artifact.write_text('{}')
                row=dict(status='passed',driver='native_items.py',layer='native ARM gameplay items',binding=bind,
                         nonce=name,old_state_loaded=False,cases={key:dict(status='passed',artifacts=[dict(path=str(artifact),sha256=sha256(artifact))])})
                process=dict(status='passed',nonce=name)
                if mutate:mutate(row,process,artifact)
                write_json(out/'result.json',row);write_json(out/'process.json',process)
                return out/'result.json'
            fresh=report('fresh');stale=report('stale',{'current':False})
            for paths in ([fresh,stale],[stale,fresh]):
                self.assertEqual(validate_native(manifest,paths,binding)['a']['status'],'passed')
            self.assertEqual(validate_native(manifest,[stale],binding)['a']['status'],'incomplete')
            mutations=[lambda r,p,a:p.update(nonce='wrong'),lambda r,p,a:p.update(status='failed'),
                       lambda r,p,a:p.update(status='running'),lambda r,p,a:r.update(old_state_loaded=True),
                       lambda r,p,a:r.update(driver='native_battle.py',layer='native ARM gameplay battle'),
                       lambda r,p,a:r['cases']['a'].update(status='incomplete'),
                       lambda r,p,a:a.write_text('tampered'),lambda r,p,a:r['cases']['a'].update(artifacts=[])]
            for i,mutate in enumerate(mutations):
                bad=report('bad'+str(i),mutate=mutate)
                for paths in ([bad],[fresh,bad],[bad,fresh]):
                    self.assertEqual(validate_native(manifest,paths,binding)['a']['status'],'incomplete')
            other=report('other',key='b',mutate=lambda r,p,a:p.update(status='failed'))
            for paths in ([fresh,other],[other,fresh]):
                result=validate_native(manifest,paths,binding)
                self.assertEqual(result['a']['status'],'passed');self.assertEqual(result['b']['status'],'incomplete')

    def test_no_effect_requires_native_failure_no_consumption_and_one_enemy_turn(self):
        for item in NO_EFFECT:
            category=case_for(dict(item=item))['category']
            for mode in (True,False):self.assertTrue(checkpoint(medicine_sample(item,category,mode,'no-effect')))
            original=medicine_sample(item,category,True,'no-effect')
            changes=[lambda r:r['after'].update(quantity=2),
                     lambda r:r['events'].append(dict(name='consume',owner=0,item=item)),
                     lambda r:r['events'].pop(next(i for i,e in enumerate(r['events']) if e['name']=='failure_message')),
                     lambda r:next(e for e in r['events'] if e['name']=='outcome').update(words=[0,1,0]),
                     lambda r:r['after']['mons']['13']['pp'].__setitem__(0,40)]
            for mutate in changes:
                row=copy.deepcopy(original);mutate(row)
                with self.assertRaises(AssertionError):checkpoint(row)
        # Injured living Revive must stay injured; ordinary healing cannot hide.
        row=medicine_sample(28,0,True,'no-effect')
        self.assertEqual(row['before']['mons']['2']['hp'],1)
        self.assertEqual(row['before']['mons']['2']['maxhp'],36)
        row['after']['mons']['2']['hp']=19
        with self.assertRaises(AssertionError):checkpoint(row)

    def test_full_revive_cannot_hide_duplicate_callback_or_clipped_hp_add(self):
        for item in (28,29,37):
            original=medicine_sample(item,0,True);self.assertTrue(checkpoint(original))
            mutations=[lambda r:r['events'].append(dict(name='ordinary_hp')),
                       lambda r:r['events'].append(copy.deepcopy(next(e for e in r['events'] if e['name']=='revival_hp_add'))),
                       lambda r:r['events'].append(dict(name='revival_adjust')),
                       lambda r:next(e for e in r['events'] if e['name']=='effect_attr' and e['attr']==38).update(result=1),
                       lambda r:next(e for e in r['events'] if e['name']=='effect_attr' and e['attr']==23).update(result=0),
                       lambda r:next(e for e in r['events'] if e['name']=='effect_attr').update(target_id=3),
                       lambda r:next(e for e in r['events'] if e['name']=='revival_hp_add').update(lr=0x0222A0C7)]
            for mutate in mutations:
                row=copy.deepcopy(original);mutate(row)
                with self.assertRaises(AssertionError):checkpoint(row)

    def test_no_effect_scope_retains_positive_inputs_and_index(self):
        from native_items_fixture import prepare
        import save_core
        receipt=json.loads(RECEIPT.read_text())
        with scratch('no-effect-inputs-') as tmp:
            root=Path(tmp);positives=plan(root/'runs','single',28);negative=plan(root/'runs','no-effect',17)
            self.assertEqual(len(negative),8);self.assertEqual(len(report_paths(root/'runs')),10)
            self.assertEqual(variants('oran-leppa',17),[(155,0),(154,0)])
            self.assertTrue(all(j['condition']=='no-effect' and j['out'] not in [p['out'] for p in positives] for j in negative))
            for item in NO_EFFECT:
                fixture=prepare(receipt,root/str(item),item,'no-effect')
                mon=save_core.request('decodePokemon',fixture['damaged'],diagnostic=False)
                self.assertTrue(mon['checksumOk']);self.assertEqual(mon['flags'],0)
                self.assertEqual(mon['party']['status'],0)
                self.assertEqual(mon['party']['currentHp'],1 if item==28 else mon['party']['stats']['hp'])
                if item==38:self.assertEqual([m['pp'] for m in mon['moves']],[10,40,0,0])
                self.assertEqual(fixture['metadata']['condition'],'no-effect')

    def test_no_effect_acceptance_needs_all_four_paired_conditions_and_current_binding(self):
        binding={'current':True}
        with scratch('no-effect-evidence-') as tmp:
            root=Path(tmp);paths=[]
            for item in NO_EFFECT:
                category=case_for(dict(item=item))['category']
                for mode in ('all','restricted'):
                    out=root/f'{item}-{mode}';out.mkdir();run=medicine_sample(item,category,mode=='all','no-effect')
                    run.update(name=mode,checkpoint='passed')
                    fixture={k:1 for k in ('candidate_sha256','source_battery_sha256','input_battery_sha256','trainer_id',
                        'trainer_sha256','enemy_record_sha256','payload','splash','target_slot','ui_slot','move_slot')}
                    fixture.update(item=item,condition='no-effect',records=[dict(sha256='typed-input')])
                    write_json(out/'items-trace.json',dict(binding=binding,battle=run))
                    write_json(out/'items-fixture.json',fixture)
                    for n in ('trainer-menu.png','bag-categories.png','returned-menu.png'):(out/n).write_bytes(b'synthetic host data')
                    artifacts=[dict(path=str(p),sha256=sha256(p)) for p in out.iterdir()]
                    row=dict(status='passed',driver='native_items.py',layer='native ARM gameplay items',binding=binding,
                        nonce=out.name,old_state_loaded=False,items_pair='pair',battle=run,fixture=fixture,checkpoint_artifacts=artifacts)
                    write_json(out/'result.json',row);write_json(out/'process.json',dict(status='passed',nonce=out.name));paths.append(out/'result.json')
            self.assertEqual(validate_no_effect(paths,binding)['status'],'passed')
            self.assertEqual(validate_no_effect(paths[:-1],binding)['status'],'incomplete')
            self.assertEqual(validate_no_effect(paths,{'other':True})['status'],'incomplete')
            self.assertEqual(validate_item_pair(paths,binding,28)['status'],'incomplete')
            # No-effect input must not be substituted with an ordinary positive fixture.
            row=json.loads(paths[0].read_text());row['fixture']['condition']='positive'
            write_json(paths[0],row)
            self.assertEqual(validate_no_effect(paths,binding)['status'],'incomplete')
