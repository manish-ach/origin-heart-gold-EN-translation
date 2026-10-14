"""Host fixture/oracle sensitivity only; never substitutes for native edge proof."""
import copy,json,unittest
from pathlib import Path
from unittest.mock import patch
from support import scratch,RECEIPT
from native_edges_oracles import validate,validate_boundary


class EdgeTests(unittest.TestCase):
    def test_native_evolved_recipient_uses_own_species_even_when_curves_match(self):
        from native_edges_oracles import validate_recipient_thresholds
        thresholds=[0]*101;thresholds[100]=1000000
        tables={str(i):dict(species=i,thresholds=list(thresholds)) for i in (19,20)}
        run=dict(before=[dict(species=20),dict(species=19),dict(species=19)],
                 expected_cap=100,threshold=1000000,events=[dict(name='eligible',id=i,
                 threshold_species=20 if i==1 else 19,threshold=1000000) for i in (1,2,3)])
        validate_recipient_thresholds(run,tables)
        for mutation in ('initial_species','other_recipient','table','threshold','missing'):
            bad=copy.deepcopy(run);metadata=copy.deepcopy(tables)
            if mutation=='initial_species':bad['events'][0]['threshold_species']=19
            elif mutation=='other_recipient':bad['events'][1]['threshold_species']=20
            elif mutation=='table':metadata['20']['thresholds'][100]-=1
            elif mutation=='threshold':bad['events'][0]['threshold']-=1
            else:del metadata['20']
            with self.subTest(mutation=mutation),self.assertRaises(AssertionError):
                validate_recipient_thresholds(bad,metadata)

    def test_gap_boundary_rejects_party_reset_later_badge_loss_and_extra_flag(self):
        raw=bytearray(32);raw[28]=0xdf;raw[31]=0xff
        before=dict(profile_raw=raw.hex(),party_raw='carried',bag_raw='unchanged',
                    progression=dict(badges=0xffdf,erika=False))
        raw[28]=0xff
        after=dict(before,profile_raw=raw.hex(),progression=dict(before['progression'],badges=0xffff))
        validate_boundary(before,after)
        for key,value in [('party_raw','reset'),('bag_raw','reset'),
                          ('progression',dict(badges=0xffff,erika=True)),('profile_raw',bytes(32).hex())]:
            with self.subTest(key=key),self.assertRaises(AssertionError):
                validate_boundary(before,dict(after,**{key:value}))

    def test_real_candidate_other_curve_and_level100_typed_fixtures(self):
        from native_battle_fixture import prepare_fixture_templates
        from emu_harness import decode_pokemon,encode_pokemon
        receipt=json.loads(RECEIPT.read_text())
        with scratch('growth-edges-') as tmp:
            a=Path(tmp)/'rattata';b=Path(tmp)/'bulbasaur'
            first=prepare_fixture_templates(receipt,a,levels=(100,),species=20)
            other=prepare_fixture_templates(receipt,b,levels=(8,11,12),species=1)
            ma=json.loads((a/'fixture-templates.json').read_text());mb=json.loads((b/'fixture-templates.json').read_text())
            self.assertNotEqual(ma['personal']['growthRate'],mb['personal']['growthRate'])
            self.assertEqual(decode_pokemon(first[100])['exp'],ma['thresholds'][100])
            self.assertEqual(decode_pokemon(first[100])['species'],20)
            self.assertEqual(decode_pokemon(first[100])['level'],100)
            raw=encode_pokemon(other[11],exp=mb['thresholds'][12]-7);d=decode_pokemon(raw)
            self.assertTrue(d['checksum_ok']);self.assertEqual((d['species'],d['level']),(1,11))
            self.assertGreaterEqual(d['exp'],mb['thresholds'][11])
            self.assertLess(d['exp'],mb['thresholds'][12])

    def test_overlevel_requires_native_level100_boolean_and_preserved_ev(self):
        thresholds=[0]*101;thresholds[12]=1728;thresholds[100]=1000000
        before=[dict(species=20 if l==100 else 19,level=l,exp=e,evs=[0]*6) for l,e in ((20,8000),(100,1000000),(8,512))]
        runs=[]
        for flags in (0,2):
            after=copy.deepcopy(before)
            for i in (0,1,2):
                after[i]['evs'][3]=1
                after[i]['exp']+=10 if i==2 or i==0 and flags==0 else 0
            events=[]
            for i in (1,2,3):
                amount=0 if i==2 else 10
                events.append(dict(name='eligible',id=i,phase='first',raw_before='native',
                    native_amount=amount,amount=0 if flags and i==1 else amount,
                    native_result=1,result=1,native_deferred=0))
                if amount and (i!=1 or flags==0):events.append(dict(name='apply',id=i,amount=amount))
            runs.append(dict(flags=flags,threshold=1728,before=copy.deepcopy(before),after=after,events=events))
        report=dict(case='overlevel',metadata=dict(species=19,thresholds=thresholds),battles=runs)
        with patch('native_edges_oracles.validate_readers'),patch('native_edges_oracles.root_reuse'):
            validate(report)
            for mutation in ('native_boolean','level100_exp','unevolved_input','overcap_downlevel','ev','other_award'):
                bad=copy.deepcopy(report);on=bad['battles'][1]
                if mutation=='native_boolean':on['events'][1]['native_result']=0
                elif mutation=='level100_exp':on['after'][1]['exp']+=1
                elif mutation=='unevolved_input':on['before'][1]['species']=19
                elif mutation=='overcap_downlevel':on['after'][0]['level']=12
                elif mutation=='ev':on['after'][0]['evs']=[0]*6
                else:on['events'].append(dict(name='apply',id=3,amount=1))
                with self.subTest(mutation=mutation),self.assertRaises(AssertionError):validate(bad)
