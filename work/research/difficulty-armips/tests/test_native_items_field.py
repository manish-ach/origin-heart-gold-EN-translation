"""Field baseline observations remain separate from battle expected effects."""
import copy
import unittest
from native_items_field import observe, compare, HP_OFFSET, FieldTrace
from support import CN_SHA256, load_rom, arm9_main, RECEIPT


def sample(hp=15):
    party=0x02220000;bag=0x02230000
    records=[]
    for i in range(3):
        raw=bytearray(236);raw[0]=i
        raw[HP_OFFSET:HP_OFFSET+2]=(0 if i==1 else 31).to_bytes(2,'little')
        records.append(dict(slot=i,address=party+8+236*i,raw=raw.hex(),
                            decoded=dict(party=dict(currentHp=0 if i==1 else 31,stats=dict(hp=31)))))
    inventory=bytearray(0x864);inventory[0x5e8:0x5ec]=bytes([28,0,3,0])
    before=dict(party=party,save=123,records=records,inventory=dict(bag_address=bag,item=28,item_offset=0x5e8,
                                                                   quantity=3,bag=inventory.hex()))
    after=copy.deepcopy(before);after['records'][1]['decoded']['party']['currentHp']=hp
    raw=bytearray.fromhex(after['records'][1]['raw']);raw[HP_OFFSET:HP_OFFSET+2]=hp.to_bytes(2,'little')
    after['records'][1]['raw']=raw.hex();inventory[0x5ea]=2
    after['inventory'].update(quantity=2,bag=inventory.hex());target=party+8+236
    return dict(variant='cn-field',before=before,after=after,player_fixture=dict(hashes=['a','b','a']),events=[
        dict(name='field_select',party=party,item=28,slot=1,result=1),
        dict(name='field_apply',mon=target,item=28,result=1,hp=0,after_hp=hp),
        dict(name='field_consume',bag=bag,item=28,quantity=1,result=1),
        dict(name='field_hp_get',mon=target,attr=0xa3,value=0),
        dict(name='field_hp_get',mon=target,attr=0xa4,value=31),
        dict(name='field_heal',mon=target,hp_argument=0,maxhp_argument=31,amount=254,returned=True),
        dict(name='field_hp_set',mon=target,value=hp,returned=True)])


class FieldBaselineTests(unittest.TestCase):
    def test_records_observation_without_blessing_battle_hp(self):
        for hp in (15,30):
            result=observe(sample(hp));self.assertEqual(result['final_hp'],hp)
            self.assertFalse(result['battle_equivalence_proven'])
        for mutate in (lambda r:r['after']['records'][0].update(raw='01'*236),
                       lambda r:r['after']['inventory'].update(quantity=3),
                       lambda r:r['events'][0].update(slot=2),
                       lambda r:r['events'][1].update(mon=0x02220008),
                       lambda r:r['events'][2].update(quantity=2),
                       lambda r:r['events'][-1].update(value=30),
                       lambda r:r['events'].pop(0)):
            bad=sample();mutate(bad)
            with self.assertRaises(AssertionError):observe(bad)

    def test_sealed_state_and_oracle_use_real_encrypted_typed_records(self):
        import json
        from pathlib import Path
        from types import SimpleNamespace
        from support import scratch
        from native_items_fixture import prepare
        from native_items_field import sealed_state
        from emu_harness import encode_pokemon
        import save_core
        receipt=json.loads(RECEIPT.read_text())
        with scratch('field-encrypted-regression-') as tmp:
            out=Path(tmp);fixture=prepare(receipt,out,28)
            row=sample();party=row['before']['party'];bag=row['before']['inventory']['bag_address']
            data=bytearray(0x20000)
            data[:8]=(6).to_bytes(4,'little')+(3).to_bytes(4,'little')
            for i,raw in enumerate((fixture['healthy'],fixture['damaged'],fixture['healthy'])):
                data[8+236*i:8+236*(i+1)]=raw
            data[bag-party:bag-party+0x864]=bytes.fromhex(row['before']['inventory']['bag'])
            read=lambda a,n:bytes(data[a-party:a-party+n])
            h=SimpleNamespace(array=lambda i:party if i==2 else bag,save=123,read=read,
                u32=lambda a:int.from_bytes(read(a,4),'little'))
            before=sealed_state(h,out,'encrypted-before')
            sealed_hp=int.from_bytes(fixture['damaged'][HP_OFFSET:HP_OFFSET+2],'little')
            self.assertNotEqual(sealed_hp,0)  # old numeric ciphertext assertion fails on real input
            self.assertEqual(before['records'][1]['decoded']['party']['currentHp'],0)
            # Typed HOST fixture only, never an emulator outcome write.
            healed=encode_pokemon(fixture['damaged'],currentHp=15)
            data[8+236:8+472]=healed;data[bag-party+0x5ea:bag-party+0x5ec]=(2).to_bytes(2,'little')
            after=sealed_state(h,out,'encrypted-after')
            row.update(before=before,after=after)
            self.assertEqual(observe(row)['final_hp'],15)
            bad=copy.deepcopy(row);bad['after']['records'][1]['decoded']['party']['status']=8
            with self.assertRaises(AssertionError):observe(bad)
            # No repair of open or checksum-invalid native records.
            data[8+236+4]=1
            with self.assertRaises(save_core.CoreError):sealed_state(h,out,'open-rejected')
            data[8+236+4]=0;data[8+236+8]^=1
            with self.assertRaises(save_core.CoreError):sealed_state(h,out,'corrupt-rejected')

    def test_field_pair_requires_matching_inputs_fresh_processes_and_original_rom(self):
        rows=[]
        for i,variant in enumerate(('cn-field','candidate-field')):
            field=sample();field['variant']=variant
            rows.append(dict(status='passed',diagnostic_only=True,cases={},pair='pair',old_state_loaded=False,
                nonce=str(i),binding=dict(candidate=dict(candidate_sha256='candidate')),
                executed_rom=dict(sha256=CN_SHA256 if i==0 else 'candidate'),field=field,
                fixture=dict(input_battery_sha256='a',source_battery_sha256='b',payload=[1],splash=[2])))
        result=compare(rows,'pair');self.assertTrue(result['same_field_observation'])
        self.assertFalse(result['battle_equivalence_proven'])
        for mutate in (lambda r:r[1].update(nonce='0'),lambda r:r[0]['executed_rom'].update(sha256='candidate'),
                       lambda r:r[1]['fixture'].update(input_battery_sha256='changed'),
                       lambda r:r[1]['cases'].update({'items.addition_28':dict(status='passed')})):
            bad=copy.deepcopy(rows);mutate(bad)
            with self.assertRaises(AssertionError):compare(bad,'pair')

    def test_native_field_wrapper_passes_selected_slot_and_item_to_effect(self):
        # Actual original static source: wrapper resolves r2 slot through
        # Party_GetMonByIndex, then invokes field effect0208FA50.
        from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
        raw=arm9_main(load_rom());address=0x0209002c
        calls=[i.op_str for i in Cs(CS_ARCH_ARM,CS_MODE_THUMB).disasm(raw[0x9002c:0x9004c],address)
               if i.mnemonic=='bl']
        self.assertEqual(calls,['#0x207339c','#0x208fa50'])
        from types import SimpleNamespace
        from unittest.mock import Mock
        regs=[0x02220000,28,1,0]+[0]*12
        h=SimpleNamespace(reg=regs,frame=1)
        trace=FieldTrace.__new__(FieldTrace);trace.h=h;trace.party=regs[0];trace.armed=True
        trace.run=dict(events=[]);trace.s=SimpleNamespace(returned=Mock())
        trace.select();self.assertEqual(trace.run['events'][0]['slot'],1)
        regs[2]=2
        with self.assertRaises(AssertionError):trace.select()
