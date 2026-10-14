"""Host-only fixture and reward-oracle sensitivity, never native acceptance."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from support import scratch,RECEIPT
from native_multiko_oracles import aggregate_bytes,compare,validate_run


class MultiKOTests(unittest.TestCase):
    def test_ev_native_gate_branch_and_battlemon_application_are_not_raw_yield(self):
        from native_multiko_oracles import validate_ev_group
        for participants in ([1,2],[2]):
            rows={};proofs=[];calls=[];before=[];after=[];snapshot=dict(flags=3,epoch=1)
            for slot,i in enumerate((2,1,3)):
                enabled=i in participants;raw=bytearray(16);raw[7]=1;raw[0]=20 if enabled else 0
                rows[i]=dict(slot=slot,mon=100+i,raw=raw.hex())
                proofs.append(dict(name='ev_eligible',id=i,lr=0x0221F687,mon=100+i,snapshot=snapshot,
                    raw_address=2000+slot*16,raw_before=raw.hex(),raw_after=raw.hex(),
                    result=int(enabled),branch='apply' if enabled else 'skip',calls=int(enabled)))
                old=dict(total=0,values=[0]*6);new=dict(total=int(enabled),values=[0,0,0,int(enabled),0,0])
                before.append(dict(id=i,ev_storage=old));after.append(dict(id=i,ev_storage=new))
                if enabled:calls.append(dict(name='ev',id=i,mon=100+i,lr=0x0221F6AB,
                    values=[0,0,0,0,0,1],before=old,after=new))
            def check(events,people=participants,post=after):
                validate_ev_group(dict(events=events),rows,before,post,people,True,snapshot,2000)
            check(proofs+calls)
            for mutation in ('bench_call','result','branch','caller','raw_pointer','participation','storage','missing'):
                events=copy.deepcopy(proofs+calls);people=participants;post=after
                if mutation=='bench_call':events.append(dict(calls[0],id=3,mon=103))
                elif mutation=='result':events[2]['result']=1
                elif mutation=='branch':events[2]['branch']='apply'
                elif mutation=='caller':events[0]['lr']=0x0221F779
                elif mutation=='raw_pointer':events[0]['raw_address']+=16
                elif mutation=='participation':people=[3]
                elif mutation=='storage':post=copy.deepcopy(after);post[0]['ev_storage']['values']=[0]*6
                else:events.pop()
                with self.subTest(participants=participants,mutation=mutation),self.assertRaises(AssertionError):
                    check(events,people,post)

    def test_share_matrix_binds_per_opponent_participation_exp_and_ev(self):
        from native_multiko_oracles import compare_share,validate_matrix
        def fixture(flags):
            result=dict(flags=flags,before=[dict(exp=512,evs=[0]*6)]*3,
                        after=[dict(exp=512,evs=[0]*6)]*3,enemy_input='same',events=[])
            for op,participants in ((13,[1,2]),(14,[2])):
                temporary=bytearray(96)
                for slot,i in enumerate((2,1,3)):
                    enabled=not flags&1 or i in participants
                    raw=bytearray(16);raw[:4]=(20 if enabled else 0).to_bytes(4,'little')
                    result['events'].append(dict(name='calculate',opponent_id=op,id=i,
                        participants=participants,raw_calculated=raw.hex(),raw_address=1000+slot*16))
                    raw[7]=1;temporary[slot*16:slot*16+16]=raw
                result['events'].append(dict(name='aggregate',opponent_id=op,
                    temporary_address=1000,temporary=temporary.hex()))
            return result
        on,off=fixture(0),fixture(1)
        compare_share(on,off)
        for mutation in ('bench_exp','bench_ev','participant_ev','pointer','participants','missing'):
            bad=copy.deepcopy(off)
            calc=next(e for e in bad['events'] if e['name']=='calculate' and e['id']==3)
            if mutation=='bench_exp':calc['raw_calculated']='01000000'+calc['raw_calculated'][8:]
            elif mutation in ('bench_ev','participant_ev'):
                aggregate=next(e for e in bad['events'] if e['name']=='aggregate')
                raw=bytearray.fromhex(aggregate['temporary'])
                raw[39 if mutation=='bench_ev' else 7]=0
                aggregate['temporary']=raw.hex()
            elif mutation=='pointer':calc['raw_address']+=1
            elif mutation=='participants':calc['participants']=[3]
            else:bad['events'].remove(calc)
            with self.subTest(mutation=mutation),self.assertRaises(AssertionError):compare_share(on,bad)
        with self.assertRaises(AssertionError):validate_matrix([on,fixture(2)])

    def test_native_deferred_messages_require_exact_direct_awards_only(self):
        from native_multiko_oracles import validate_messages
        rows={i:dict(raw=(bytes(11)+bytes([1])+bytes(4)).hex()) for i in (1,2,3)}
        for amounts,deferred in [((30,43,22),(0,0,1)),((14,43,22),(1,0,1)),
                                 ((0,43,22),(1,0,1))]:
            elig=[dict(id=i,phase=phase,result=1,amount=amounts[i-1],deferred=deferred[i-1])
                  for phase in ('first','deferred') for i in (1,2,3)]
            messages=[dict(name='message',id=i,amount=amounts[i-1],message=0x1e,lr=0x0221F7BD)
                      for i in (1,2,3) if amounts[i-1]>0 and not deferred[i-1]]
            validate_messages(dict(events=messages),elig,rows)
            for mutation in ('missing','extra_deferred','zero','amount','type','caller','unknown'):
                bad=copy.deepcopy(messages)
                if mutation=='missing':bad.pop()
                elif mutation=='extra_deferred':bad.append(dict(messages[0],id=3,amount=22))
                elif mutation=='zero':bad.append(dict(messages[0],id=1,amount=0))
                elif mutation=='amount':bad[0]['amount']+=1
                elif mutation=='type':bad[0]['message']=0x1d
                elif mutation=='caller':bad[0]['lr']=0x0221F85F
                else:bad.append(dict(messages[0],id=99))
                with self.subTest(amounts=amounts,mutation=mutation),self.assertRaises(AssertionError):
                    validate_messages(dict(events=bad),elig,rows)
        # The alternate native raw-byte11 branch is also exact, not ignored.
        rows[2]['raw']=bytes(16).hex()
        messages=[dict(name='message',id=2,amount=43,message=0x1d,lr=0x0221F7D7)]
        validate_messages(dict(events=messages),elig,rows)

    def test_two_member_roster_requires_current_native_active_position_proof(self):
        from native_multiko_trace import opponent_binding
        snapshot=dict(root=0x022c0000,epoch=1,allowed=1,cap=12,flags=0)
        view=snapshot['root']+0x54;pointer=0x02300000
        for rid in (13,14):
            proof=dict(snapshot=snapshot,view=view,position=1,owner=1,slot=0,result=pointer,id=rid)
            opponent_binding(proof,snapshot,view,2,pointer,rid)
            for key,value in [('snapshot',dict(snapshot,epoch=2)),('view',view+0xf0),
                              ('position',0),('owner',0),('slot',1),('result',pointer+4),('id',99)]:
                with self.subTest(id=rid,key=key),self.assertRaises(AssertionError):
                    opponent_binding(dict(proof,**{key:value}),snapshot,view,2,pointer,rid)
            for count in (0,1,3,6):
                with self.subTest(count=count),self.assertRaises(AssertionError):
                    opponent_binding(proof,snapshot,view,count,pointer,rid)
            with self.assertRaises(AssertionError):opponent_binding(None,snapshot,view,2,pointer,rid)

    def test_position_mapping_is_bound_to_resolver_callsite_and_return(self):
        from types import SimpleNamespace
        from native_multiko_trace import MultiTrace
        trace=object.__new__(MultiTrace);row=dict(position=1);callbacks=[]
        trace.position_scope=row
        trace.h=SimpleNamespace(u8=lambda address:{100:1,101:0}[address])
        trace.s=SimpleNamespace(returned=callbacks.append)
        regs=[1,100,101]+[0]*13
        with patch('native_multiko_trace.registers',return_value=regs):
            regs[14]=0x02026505;trace.position_mapping()
            self.assertEqual(callbacks,[]);self.assertNotIn('owner',row)
            regs[14]=0x022151E3;trace.position_mapping()
            self.assertEqual(len(callbacks),1);self.assertNotIn('owner',row)
            callbacks.pop()()
            self.assertEqual((row['owner'],row['slot']),(1,0))
            trace.position_scope=None;trace.position_mapping();self.assertEqual(callbacks,[])

    def test_native_aggregate_arithmetic_preserves_last_record_and_byte_semantics(self):
        a=bytearray(96);b=bytearray(96)
        a[:4]=(0xffffffff).to_bytes(4,'little');b[:4]=(2).to_bytes(4,'little')
        a[4]=255;b[4]=2;a[11]=3;b[11]=7;a[12]=1;b[12]=0;a[13]=99
        b[16:20]=(17).to_bytes(4,'little');b[27]=2;b[28]=1
        out=aggregate_bytes(a,b)
        self.assertEqual(int.from_bytes(out[:4],'little'),1)
        self.assertEqual((out[4],out[11],out[12],out[13]),(1,3,0,99))
        self.assertEqual(int.from_bytes(out[16:20],'little'),17)
        self.assertEqual((out[27],out[28]),(2,1))
        with self.assertRaises(AssertionError):aggregate_bytes(a[:-1],b)

    def test_trainer6_input_is_valid_typed_hp1_splash_without_native_generator(self):
        from native_battle_fixture import prepare_fixture_templates
        from native_multiko_fixture import prepare_enemy
        receipt=json.loads(RECEIPT.read_text())
        with scratch('multiko-input-') as tmp:
            out=Path(tmp);templates=prepare_fixture_templates(receipt,out,levels=(5,8,12))
            a,meta=prepare_enemy(receipt,out,templates);b,_=prepare_enemy(receipt,out,templates)
            self.assertEqual(a,b);self.assertEqual(len(a),236)
            mon=meta['decoded'];self.assertEqual(mon['party']['level'],5)
            self.assertEqual(mon['party']['currentHp'],1);self.assertEqual(mon['flags'],0)
            self.assertTrue(mon['checksumOk']);self.assertEqual(mon['experience'],125)
            self.assertEqual([(m['id'],m['pp']) for m in mon['moves']],[(150,40),(0,0),(0,0),(0,0)])

    def test_pair_detects_native_distribution_and_other_recipient_or_ev_changes(self):
        def run(cap):
            before=[dict(exp=100,level=12,evs=[0]*6) for _ in range(3)]
            after=[dict(exp=100+(0 if cap and i==0 else 10),level=12,evs=[0,0,0,1,0,0]) for i in range(3)]
            rows=[]
            for i in (1,2,3):
                rows += [dict(name='eligible',group=1,id=i,phase='first',raw_before='native',
                              native_amount=10,native_deferred=0,native_result=1),
                         dict(name='ev',id=i,values=[0,0,0,0,0,1])]
                if not cap or i!=1:rows.append(dict(name='apply',id=i,amount=10))
            return dict(flags=2 if cap else 0,before=before,after=after,enemy_input='same',events=rows)
        off,on=run(False),run(True)
        with patch('native_multiko_oracles.validate_run'),patch('native_multiko_oracles.root_reuse'):
            compare([off,on])
            for mutation in ('native','recipient','ev','fixture','level'):
                bad=copy.deepcopy(on)
                if mutation=='native':bad['events'][0]['native_amount']+=10
                elif mutation=='recipient':next(e for e in bad['events'] if e['name']=='apply')['amount']+=10
                elif mutation=='ev':bad['after'][0]['evs']=[0]*6
                elif mutation=='fixture':bad['enemy_input']='different'
                else:bad['before'][0]['level']=13
                with self.subTest(mutation=mutation),self.assertRaises(AssertionError):compare([off,bad])
        with self.assertRaises(AssertionError):validate_run(off)  # synthetic data cannot pass real lifecycle
