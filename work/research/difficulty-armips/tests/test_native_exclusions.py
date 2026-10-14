"""Excluded-recipient oracle mutation tests; no native acceptance claims."""
import copy
import types
import sys
import unittest
from unittest.mock import patch
from native_exclusions_oracles import FIELDS,validate_local,validate_remote,record,fixture_metadata
from support import scratch,ROOT,RECEIPT
from pathlib import Path
from native_exclusion_snapshot import wait_closed_party
sys.path.insert(0,str(ROOT/"work/tools"))


def local_fixture():
    mons=[dict(pid=i+1,species=19,exp=100,evs=[0]*6,level=8,
               checksum_ok=True,bad_egg=False,isEgg=False,hp=20) for i in range(5)]
    mons[3].update(exp=0,level=1,isEgg=True)
    mons[4]['hp']=0
    observed=[{k:m[k] for k in FIELDS} for m in mons]
    raw={f'{phase}-{slot}':copy.deepcopy(mons[slot]) for phase in ('before','after') for slot in (3,4)}
    import hashlib
    snapshot=[dict(frame=1,pc=0x02001000,owner=0x02200000,closed=True,record_sha256=[hashlib.sha256(b'A'*236).hexdigest()]*5)]
    run=dict(flags=0,before=copy.deepcopy(observed),after=copy.deepcopy(observed),record_stabilization=snapshot,
        empty_slot=dict(root=0x022B0000,resolver=0),
        negative_records=[dict(slot=s,before_path=f'before-{s}',after_path=f'after-{s}') for s in (3,4)],
        events=[dict(name='eligible',id=i,native_amount=0,amount=0,native_result=0,result=0,
                     raw_before='00',raw_after='00') for i in (4,5)])
    return dict(old_state_loaded=False,battles=[run]),raw


def remote_fixture():
    raw=b'A'*236
    import hashlib
    mons=[dict(pid=i,species=19,exp=100,evs=[0]*6) for i in range(7,13)]
    records={}
    rows={}
    for phase in ('before','after'):
        rows[phase]=[]
        for m in mons:
            path=f"{phase}-{m['pid']}"
            records[path]=dict(m)
            rows[phase].append(dict(m,id=m['pid'],mon=0x022A0000+m['pid']*512,
                backing=0x022C0000+m['pid']*512,path=path,raw=raw.hex(),sha256=hashlib.sha256(raw).hexdigest()))
    context=dict(flags=0x4B,control=0,setup=0x02280000,save=0x02200000,
                 published_save=0x02200000,root=0x022B0000)
    before=[dict(pid=i,species=19,exp=100,evs=[0]*6,level=8,
                 checksum_ok=True,bad_egg=False) for i in range(1,4)]
    after=copy.deepcopy(before)
    events=[dict(name='constructor',lr=0x020507AD,args=[11,0x4B,8,385],
                 setup=context['setup'],flags=0x4B,control=0),
        dict(name='original_begin',frame=2),dict(name='captured',frame=2,context=context,
             snapshot=dict(flags=0,allowed=1,epoch=1,root=context['root']),
             save_owner=context['save'],setup_owner=context['setup']),
        dict(name='action',actor=dict(id=1),selected=82,move=82),
        dict(name='teardown',frame=10),dict(name='free',frame=11),
        dict(name='original_free',root=context['root'],snapshot=dict(epoch=0))]
    for i in range(3):
        after[i]['exp']+=1;after[i]['evs'][3]+=1
        events += [dict(name='apply',id=i+1,amount=1),dict(name='ev',id=i+1,values=[0,0,0,0,0,1])]
    return dict(flags=0,old_state_loaded=False,command=['TrainerBattle',6,8,0,1],
        events=events,remote_before=rows['before'],remote_after=rows['after'],
        before=before,after=after,turns=[dict(field=True)]),records


class ExclusionAcceptance(unittest.TestCase):
    def snapshot_harness(self,pc=0x02020692):
        h=types.SimpleNamespace(frame=0,owner=0x02200000,pc=pc,steps=0)
        h.array=lambda index:h.owner
        h.in_field=lambda:True
        h.u32=lambda address:6 if address==h.owner else 5
        h.read=lambda address,size:b'a'*size
        def step(frames):h.frame+=frames;h.steps+=frames;h.pc=0x02001000
        h.step=step
        h.write=lambda *args:self.fail('snapshot acquisition must never write')
        return h

    def test_native_crypto_frame_is_advanced_without_decoding_or_writing(self):
        h=self.snapshot_harness();run={}
        with patch('native_exclusion_snapshot.registers',side_effect=lambda h:[0]*15+[h.pc]), \
             patch('save_core.request',return_value=dict(flags=0,checksumOk=True,party=dict(level=8))) as decode:
            self.assertEqual(wait_closed_party(types.SimpleNamespace(h=h),run),h.owner)
        self.assertEqual(h.steps,1);self.assertEqual(decode.call_count,5)
        self.assertEqual([r['closed'] for r in run['record_stabilization']],[False,True])

    def test_temporary_checksum_is_read_only_wait_but_permanent_corruption_fails(self):
        h=self.snapshot_harness(pc=0x02001000);run={}
        calls=[ValueError('native body not closed')]+[dict(flags=0,checksumOk=True,party=dict(level=8))]*5
        with patch('native_exclusion_snapshot.registers',side_effect=lambda h:[0]*15+[h.pc]), \
             patch('save_core.request',side_effect=calls):wait_closed_party(types.SimpleNamespace(h=h),run)
        self.assertEqual(h.steps,1)
        h=self.snapshot_harness(pc=0x02001000)
        with patch('native_exclusion_snapshot.registers',side_effect=lambda h:[0]*15+[h.pc]), \
             patch('save_core.request',side_effect=ValueError('permanently corrupt')):
            with self.assertRaises(AssertionError):wait_closed_party(types.SimpleNamespace(h=h),{},limit=2)
        self.assertEqual(h.steps,2)

    def test_open_context_and_owner_change_do_not_pass_quiescence(self):
        h=self.snapshot_harness(pc=0x02001000)
        with patch('native_exclusion_snapshot.registers',side_effect=lambda h:[0]*15+[h.pc]), \
             patch('save_core.request',return_value=dict(flags=2,checksumOk=True,party=dict(level=8))):
            with self.assertRaises(AssertionError):wait_closed_party(types.SimpleNamespace(h=h),{},limit=2)
        h=self.snapshot_harness()
        def moved(frames):h.owner+=4
        h.step=moved
        with patch('native_exclusion_snapshot.registers',side_effect=lambda h:[0]*15+[h.pc]):
            with self.assertRaises(AssertionError):wait_closed_party(types.SimpleNamespace(h=h),{})

    def test_distinct_strict_seed_provenance_and_mutated_metadata(self):
        import json
        from native_exclusion_fixture import prepare_fixture_templates
        receipt=json.loads(RECEIPT.read_text())
        with scratch('exclusion-input-provenance-') as tmp:
            base=Path(tmp)
            egg=prepare_fixture_templates(receipt,base/'egg-fixture',levels=(1,),seed_slot=1)[1]
            fainted=prepare_fixture_templates(receipt,base/'fainted-fixture',levels=(8,),seed_slot=2)[8]
            (base/'egg.bin').write_bytes(egg);(base/'fainted.bin').write_bytes(fainted)
            _,a=record(base/'egg.bin',base);_,b=record(base/'fainted.bin',base)
            self.assertNotEqual(a['pid'],b['pid'])
            run=dict(before=[dict(pid=a['pid']-1),{}, {},dict(pid=a['pid']),dict(pid=b['pid'])],
                     negative_records=[dict(before_path=str(base/'egg.bin'))])
            report=dict(binding=dict(candidate_sha256=receipt['output']['sha256']))
            fixture_metadata(report,run,base)
            path=base/'egg-fixture/fixture-templates.json';meta=json.loads(path.read_text());meta['seed_slot']=0
            path.write_text(json.dumps(meta))
            with self.assertRaises(AssertionError):fixture_metadata(report,run,base)

    def local(self,report,records):
        with patch('native_exclusions_oracles.record',side_effect=lambda p,d:(b'A'*236,records[p])), \
             patch('native_exclusions_oracles.validate_run') as positive, \
             patch('native_exclusions_oracles.fixture_metadata'):
            result=validate_local(report,'.')
            self.assertEqual(len(positive.call_args.args[0]['before']),3)
            return result

    def remote(self,report,records):
        with patch('native_exclusions_oracles.record',side_effect=lambda p,d:(b'A'*236,records[p])):
            return validate_remote(report,'.')

    def test_local_exclusions_and_independent_positive_oracle(self):
        report,records=local_fixture();self.local(report,records)

    def test_excluded_native_award_or_eligibility_change_rejected(self):
        for recipient in (4,5):
            for name in ('apply','ev'):
                report,records=local_fixture();report['battles'][0]['events'].append(dict(name=name,id=recipient))
                with self.subTest(recipient=recipient,name=name),self.assertRaises(AssertionError):self.local(report,records)
            for key in ('native_amount','amount','native_result','result'):
                report,records=local_fixture();report['battles'][0]['events'][recipient-4][key]=1
                with self.subTest(recipient=recipient,key=key),self.assertRaises(AssertionError):self.local(report,records)

    def test_empty_backing_or_empty_reward_operation_rejected(self):
        report,records=local_fixture();report['battles'][0]['empty_slot']['resolver']=0x022A0000
        with self.assertRaises(AssertionError):self.local(report,records)
        for name in ('calculate','eligible','apply','ev'):
            report,records=local_fixture();report['battles'][0]['events'].append(dict(name=name,id=6))
            with self.subTest(name=name),self.assertRaises(AssertionError):self.local(report,records)

    def test_raw_and_report_growth_change_cannot_hide_in_matching_observations(self):
        report,records=local_fixture();report['battles'][0]['after'][3]['exp']=1;records['after-3']['exp']=1
        with self.assertRaises(AssertionError):self.local(report,records)
        report,records=local_fixture();records['after-4']['hp']=1
        with self.assertRaises(AssertionError):self.local(report,records)

    def test_invalid_party_checksum_cannot_be_a_native_exclusion_pass(self):
        report,records=local_fixture();report['battles'][0]['after'][3]['checksum_ok']=False
        with self.assertRaises(AssertionError):self.local(report,records)
        with scratch('excluded-raw-invalid-') as tmp:
            p=Path(tmp)/'invalid.bin';p.write_bytes(b'z'*236)
            with self.assertRaises(ValueError):record(p,tmp)

    def test_remote_control_and_native_ev_order(self):
        report,records=remote_fixture();self.remote(report,records)

    def test_remote_missing_recipient_changed_growth_or_award_rejected(self):
        report,records=remote_fixture();report['remote_after'].pop()
        with self.assertRaises(AssertionError):self.remote(report,records)
        report,records=remote_fixture();report['remote_after'][0]['exp']+=1;records['after-7']['exp']+=1
        with self.assertRaises(AssertionError):self.remote(report,records)
        for name in ('apply','ev'):
            report,records=remote_fixture();report['events'].append(dict(name=name,id=7))
            with self.subTest(name=name),self.assertRaises(AssertionError):self.remote(report,records)

    def test_remote_native_constructor_hash_action_and_application_rejected(self):
        for kind in ('constructor','hash','action','application'):
            report,records=remote_fixture()
            if kind=='constructor':report['events'][0]['args'][1]=1
            elif kind=='hash':report['remote_after'][0]['sha256']='0'*64
            elif kind=='action':report['events'][3]['move']=150
            else:report['after'][0]['exp']+=1
            with self.subTest(kind=kind),self.assertRaises(AssertionError):self.remote(report,records)
