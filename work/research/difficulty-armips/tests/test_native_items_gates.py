"""Adversarial gate oracle/fixture/index tests; never native acceptance."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from support import scratch, RECEIPT
from test_native_items import sample
from native_items_cases import GATE_ITEM
from native_items_gates_oracles import GATES, continued, injection
from native_items_gates_matrix import plan, report_paths


def gate_sample(gate,item=GATE_ITEM):
    r=sample(False);r.update(gate=gate,fault_item=item)
    r['events']=[e for e in r['events'] if e['name'] in ('constructor','enemy_fixture','begin','captured')]
    engine=r['before']['mons']['1'];ui=engine['address']+0x10000
    command=dict(controller=100,actor=ui,actor_id=1,
                 owner=0,slot=0,destination=200,command='00'*12)
    binding=dict(root=r['before']['snapshot']['root'],view=r['before']['snapshot']['root']+0x54,
        roster=r['before']['snapshot']['root']+0x60,count=3,owner=0,slot=0,ui=ui,ui_table=ui,
        engine=engine['address'],id=1,ui_backing=0x02290000,engine_backing=0x022a0000,
        ui_backing_sha256='a'*64,engine_backing_sha256='a'*64,
        ui_state=dict(deepcopy(engine),address=ui),engine_state=deepcopy(engine))
    args=bytearray(0x30);args[0x18:0x1a]=(0 if gate=='item' else 151).to_bytes(2,'little')
    args[0x1a]=4 if gate=='item' else 1
    changed=bytearray(args);changed[0x18:0x1b]=item.to_bytes(2,'little')+b'\0'
    row=dict(name='fault_input',kind='nativeFaultInput',gate=gate,item=item,address=0x02280000,
        before=args.hex(),after=changed.hex(),registers_before=[0]*16,registers_after=[0]*16,
        command_before=deepcopy(command),command_after=deepcopy(command),command_return=deepcopy(command),
        snapshot=deepcopy(r['before']['snapshot']),frame=10,target=0,result=GATES[gate][1],
        args_after=dict(item=0,category=4,address=0x02280000),actor_binding=binding)
    lists=dict(name='lists',frame=5,lists=[[],[dict(item=151,quantity=3)],[],[],[]])
    r['events'] += [dict(name='controller_actor_lookup',view=binding['view'],owner=0,slot=0,result=ui),
                    lists,row,dict(name='schedule',handler=0x02202445)]
    if gate=='target':
        r['events'] += [dict(lists,frame=20),dict(name='accept',after=dict(item=151)),dict(name='commit_item',result=151)]
        r['target_command']=deepcopy(command);r['target_actor_binding']=deepcopy(binding);r['selected_ui_slot']=0
        r['party_mapping']=dict(controller=command['controller'],count=3,entries=[dict(ui_slot=0,id=1,mon=ui,
            backing=binding['ui_backing'],source_sha256='a'*64,copy_sha256='a'*64,hp=engine['hp'],maxhp=engine['maxhp'])])
    r['denied']=deepcopy(r['before']);r['command_denied']=command
    r['denied_event_count']=len(r['events']);r['after']=deepcopy(r['denied'])
    for rid in ('1','13'):
        r['after']['mons'][rid]['pp'][0]-=1;r['after']['mons'][rid]['original_pp'][0]-=1
        r['events'].append(dict(name='action',actor=dict(id=int(rid)),move=150))
    return r


class GateTests(unittest.TestCase):
    def test_three_gates_deny_real_and_invalid_selected_inputs(self):
        for gate in GATES:
            for item in (GATE_ITEM,791,65535):continued(gate_sample(gate,item))

    def test_input_contract_rejects_register_command_and_outside_byte_writes(self):
        for gate in GATES:
            base=next(e for e in gate_sample(gate)['events'] if e['name']=='fault_input')
            for change in ('register','command','outside','original','cancel'):
                r=deepcopy(base)
                if change=='register':r['registers_after'][0]=13
                elif change=='command':r['command_after']['command']='01'*12
                elif change=='outside':
                    b=bytearray.fromhex(r['after']);b[4]=1;r['after']=b.hex()
                elif change=='original':
                    b=bytearray.fromhex(r['before']);b[0x18]=28;r['before']=b.hex()
                else:
                    b=bytearray.fromhex(r['after']);b[0x18]=0;r['after']=b.hex()
                with self.subTest(gate=gate,change=change),self.assertRaises(AssertionError):injection(r,gate,GATE_ITEM)

    def test_denial_and_continuation_cannot_hide_effect_turn_slot_or_metadata(self):
        for gate in GATES:
            for change in ('hp','inventory','slot','result','category','advance','effect','turn','continuation','metadata','schedule'):
                r=gate_sample(gate,791);fault=next(e for e in r['events'] if e['name']=='fault_input')
                if change=='hp':r['denied']['mons']['1']['hp']+=1
                elif change=='inventory':r['denied']['bag']='00'*0x864
                elif change=='slot':r['command_denied']['slot']=1
                elif change=='result':fault['result']=0xdead
                elif change=='category':fault['args_after']['category']=0
                elif change=='continuation':r['after']['mons']['13']['pp'][0]+=1
                elif change=='schedule':r['events']=[e for e in r['events'] if e['name']!='schedule'];r['denied_event_count']-=1
                else:
                    name={'advance':'slot_advance','effect':'effect','turn':'action','metadata':'fault_metadata'}[change]
                    r['events'].insert(0,dict(name=name));r['denied_event_count']+=1
                with self.subTest(gate=gate,change=change),self.assertRaises(AssertionError):continued(r)
        r=gate_sample('target');r['events']=[e for e in r['events'] if not(e['name']=='lists' and e['frame']==20)]
        r['denied_event_count']-=1
        with self.assertRaises(AssertionError):continued(r)

    def test_distinct_native_views_require_resolver_backing_and_state_identity(self):
        base=gate_sample('target');continued(base)
        binding=base['target_actor_binding']
        self.assertNotEqual(binding['ui'],binding['engine'])
        for change in ('view','owner','slot','table','engine','id','backing','state','lookup','party_mon','party_copy'):
            r=deepcopy(base);row=next(e for e in r['events'] if e['name']=='fault_input');b=row['actor_binding']
            if change=='view':b['view']+=4
            elif change=='owner':b['owner']=1
            elif change=='slot':b['slot']=1
            elif change=='table':b['ui_table']+=4
            elif change=='engine':b['engine']+=4
            elif change=='id':b['id']=2
            elif change=='backing':b['ui_backing_sha256']='b'*64
            elif change=='state':b['ui_state']['hp']+=1
            elif change=='lookup':next(e for e in r['events'] if e['name']=='controller_actor_lookup')['result']+=4
            elif change=='party_mon':r['party_mapping']['entries'][0]['mon']=binding['engine']
            else:r['party_mapping']['entries'][0]['copy_sha256']='b'*64
            with self.subTest(change=change),self.assertRaises(AssertionError):continued(r)

    def test_gate_index_retains_distinct_invalid_jobs_and_replaces_selected_invocation(self):
        with scratch('gates-index-') as tmp:
            first=plan(tmp);invalid=plan(tmp,791);second=plan(tmp)
            self.assertEqual(len(report_paths(tmp)),6)
            self.assertTrue(all(j['out']!=k['out'] for j,k in zip(first,second)))
            self.assertTrue(all((j['out']/'result.json').exists() for j in first+invalid))
            p=Path(tmp)/'latest.json';d=json.loads(p.read_text());d['cases']['bad']='/tmp/result.json';p.write_text(json.dumps(d))
            with self.assertRaises(ValueError):report_paths(tmp)

    def test_evidence_replays_gate_oracle_and_rejects_cross_gate_claim(self):
        from evidence import validate_native
        from composite_fixtures import BINDING,report_for,write_report
        with scratch('gates-evidence-') as tmp:
            out=Path(tmp)
            manifest=dict(cases=[dict(id=GATES[g][2],driver='native_items_gates.py') for g in GATES])
            report=report_for(f'gate-accept-item-{GATE_ITEM:05d}')
            report['cases']={'items.accept':dict(status='passed')}
            def check(row):
                path=write_report(out,row)
                return validate_native(manifest,[path],BINDING)
            self.assertEqual(check(report)['items.accept']['status'],'passed')
            wrong=deepcopy(report);wrong['battle']['after']['mons']['13']['pp'][0]+=1
            self.assertEqual(check(wrong)['items.accept']['status'],'incomplete')
            wrong=deepcopy(report);wrong['battle']['gate']='target'
            self.assertEqual(check(wrong)['items.accept']['status'],'incomplete')
            wrong=deepcopy(report);wrong['binding']={'source':'old'}
            self.assertEqual(check(wrong)['items.accept']['status'],'incomplete')

    def test_typed_gate_fixture_keeps_valid_records_and_two_physical_pockets(self):
        from native_items_gates import fixture
        from emu_harness import SaveFile
        receipt=json.loads(RECEIPT.read_text())
        with scratch('gates-fixture-') as tmp:
            f=fixture(receipt,Path(tmp))
            self.assertEqual(f['metadata']['stock'],[[GATE_ITEM,3],[151,3]])
            self.assertTrue(all(r['decoded']['flags']==0 and r['decoded']['checksumOk'] for r in f['metadata']['records']))
            # Reopen via strict native save-core parser; no raw battery edits.
            s=SaveFile(f['battery'])
            self.assertEqual(s.pocket('medicine'),[(GATE_ITEM,3)])
            self.assertEqual(s.pocket('berries'),[(151,3)])
            again=fixture(receipt,Path(tmp))
            self.assertNotEqual(f['battery'],again['battery'])
            self.assertTrue(f['battery'].exists())


if __name__=='__main__':unittest.main()
