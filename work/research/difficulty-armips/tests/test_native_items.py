"""ITEMS infrastructure and oracle sensitivity; no emulator/native acceptance."""
import ast
import copy
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch
from support import ROOT, SOURCE, scratch, sha256, RECEIPT
from evidence import validate_native, write_json
from native_battle_helpers import NativeSession
from native_items_oracles import checkpoint


def finish_sample(row):
    def views(mon):
        if 'moves' not in mon:return
        mon.update(pp_max=[{0:0,82:10,150:40}[m] for m in mon['moves']],
                   original_moves=list(mon['moves']), original_pp=list(mon['pp']),
                   original_pp_max=[{0:0,82:10,150:40}[m] for m in mon['moves']],pp_linked=[1]*4)
    for state in (row['before'],row['after']):
        for mon in state['mons'].values():views(mon)
    for event in row['events']:
        for key in ('actor','before','after'):
            if isinstance(event.get(key),dict):views(event[key])
        if event['name']=='effect':
            event.update(actor=copy.deepcopy(row['before']['mons']['1']))
            event.setdefault('move_slot',0);event.setdefault('target_id',1)
    effects=[e for e in row['events'] if e['name']=='effect']
    if effects:
        row['events']=[e for e in row['events'] if e['name']!='outcome']
        effect=effects[0]
        from native_items_cases import case_for
        case=case_for(row)
        order=[1,3,2] if case['kind']=='revive' and not case['no_effect'] else [1,2,3]
        args=dict(address=4000,party=5000,owner=0,item=row['item'],category=row.get('category',case['category']),
                  target=0,move_slot=0)
        entries=[dict(ui_slot=i,mon=6000+rid*100,id=rid,hp=row['before']['mons'][str(rid)]['hp'],
                      maxhp=row['before']['mons'][str(rid)]['maxhp'],backing=7000+rid*236,
                      copied=5008+i*236,source_sha256=str(rid)*64,copy_sha256=str(rid)*64)
                 for i,rid in enumerate(order)]
        chosen=entries[case['ui_slot']]
        row['events']=[e for e in row['events'] if e['name'] not in ('party_mapping','target_resolved')]
        row['events'][0:0] = [dict(name='party_mapping',controller=100,roster=3000,count=3,args=args,entries=entries),
            dict(name='target_resolved',roster=3000,ui_slot=case['ui_slot'],id=chosen['id'],mon=chosen['mon'],
                 backing=chosen['backing'],hp=chosen['hp'])]
        target=next(e for e in row['events'] if e['name']=='commit_target')
        target.update(target=case['ui_slot'],result=case['ui_slot'])
        target['party']=dict(args,target=case['ui_slot'],move_slot=case['move_slot'])
        target['command']['controller']=100
        row['events'].insert(0,dict(name='outcome',item=row['item'],actor=copy.deepcopy(effect['actor']),
                                  move_slot=effect['move_slot'],target_id=effect['target_id'],words=[0,0 if case['no_effect'] else 1,0]))
    if effects and case['kind']=='revive':
        target=row['before']['mons'][str(case['target_slot']+1)]
        actor=row['before']['mons']['1'];hp=row['after']['mons'][str(case['target_slot']+1)]['hp']
        row['events'][0:0]=[dict(name='effect_attr',item=row['item'],attr=a,result=v,
            actor=actor['address'],target=target['address'],actor_id=1,target_id=target['id']) for a,v in ((23,1),(38,0))]
        if not case['no_effect']:
            row['events'][0:0]=[dict(name='revival_hp_add',mon=target['address'],lr=0x0222AE0F,hp=0,amount=hp,after_hp=hp),
                dict(name='revival_hp_call',recipient=target['id'],hp=0,amount=hp,after_hp=hp),dict(name='revival_dispatch')]
    return row


def sample(all_items):
    """Synthetic observations only: exercise oracle negatives, never evidence."""
    snap = dict(flags=4 if all_items else 0,cap=12,allowed=1,root=100,epoch=1)
    context = dict(root=100,setup=200,save=300,published_save=300,flags=1,control=0,
                   trainer_info=400,bag=500,options_copy=0x220 if all_items else 0x200)
    args = dict(owner=0,tutorial=0,trainer_info=400,bag=500,item=17,category=0)
    bag = bytearray(0x864); bag[0x5e8:0x5ec] = bytes([17,0,3,0])
    mons = {str(i):dict(id=i,address=1000+i*0x300,hp=1 if i==1 else 36,maxhp=36,
                          moves=[150,0,0,0],pp=[40,0,0,0],statuses=[0]*5) for i in (1,2,3,13)}
    before = dict(snapshot=snap,item=17,quantity=3,bag=bag.hex(),bag_address=500,item_offset=0x5e8,mons=mons)
    after = copy.deepcopy(before)
    rows = [dict(name='constructor',lr=0x020507AD,flags=1,control=0,setup=200),
            dict(name='enemy_fixture',frame=10,before_begin=True),dict(name='begin',frame=11),
            dict(name='captured',context=context,snapshot=snap,generation=1,setup_owner=200,save_owner=300),
            dict(name='mask',item=17,result=4 if all_items else 0),
            dict(name='lists',args=args,counts=[1,0,0,0,0] if all_items else [0]*5,
                 lists=[[dict(item=17,quantity=3)] if all_items else [],[],[],[],[]])]
    if all_items:
        bag[0x5ea:0x5ec] = bytes([2,0]); after.update(quantity=2,bag=bag.hex())
        after['mons']['1']['hp'] = 21; after['mons']['13']['pp'][0] = 39
        rows += [dict(name='accept',before=dict(args),after=dict(args),result=13),dict(name='commit_item',result=17),
                 dict(name='commit_target',target=0,result=0,command=dict(owner=0,slot=0,actor=1768,actor_id=1,destination=2000,command='00'*12)),
                 dict(name='command',item=17,target=1,move_slot=0,destination=2000,before='00'*12,after=(17*16+2).to_bytes(4,'little').hex()+'0100000001000000'),
                 dict(name='effect',item=17,actor=dict(id=1)),dict(name='consume',item=17,owner=0),
                 dict(name='action',actor=dict(id=13),move=150)]
    else:
        cancelled=dict(args,item=0,category=4)
        rows += [dict(name='fade_close_state13',args=cancelled),
                 dict(name='commit_item',before=cancelled,after=cancelled,result=0)]
    return finish_sample(dict(item=17,flags=snap['flags'],options=dict(after=context['options_copy']),events=rows,
                before=before,after=after,command_before_cancel=dict(slot=0,command='00'*12),
                command_after_cancel=dict(slot=0,command='00'*12)))


def antidote_sample(all_items):
    row = sample(all_items); row['item'] = 18
    for state in (row['before'],row['after']):
        state['item'] = 18
        raw = bytearray.fromhex(state['bag']);raw[0x5e8] = 18;state['bag'] = raw.hex()
        state['mons']['1']['hp'] = 36
        state['mons']['1']['statuses'] = [0,0,0,0,1]
    if all_items:row['after']['mons']['1']['statuses'] = [0]*5
    for event in row['events']:
        if event.get('item') == 17:event['item'] = 18
        if event['name'] == 'mask':event['result'] = 8 if all_items else 0
        if event['name'] == 'lists' and all_items:
            event['counts'] = [0,1,0,0,0]
            event['lists'] = [[],[dict(item=18,quantity=3)],[],[],[]]
        if event['name'] == 'commit_item' and all_items:event['result'] = 18
        if event['name'] == 'command':event['after'] = (18*16+2).to_bytes(4,'little').hex()+'0100000001000000'
        for key in ('args','before','after'):
            if isinstance(event.get(key),dict) and event[key].get('item') == 17:
                event[key].update(item=18,category=1)
        if event['name'] == 'effect':event['actor'] = copy.deepcopy(row['before']['mons']['1'])
    if all_items:
        row['events'].append(dict(name='status_effect',status_id=5,result=1,
            before=copy.deepcopy(row['before']['mons']['1']),after=copy.deepcopy(row['after']['mons']['1'])))
    return finish_sample(row)


def medicine_sample(item, category, all_items, condition="positive"):
    from native_items_cases import case_for
    case=case_for(dict(item=item,condition=condition));actual_all=all_items;all_items=all_items or case['restricted_allowed']
    row=sample(all_items);row.update(item=item,category=category,condition=condition)
    target_id=case['target_slot']+1; key=str(target_id)
    for state in (row['before'],row['after']):
        state['item']=item
        raw=bytearray.fromhex(state['bag']);quantity=state['quantity']
        raw[0x5e8:0x5ec]=bytes(4)
        offset={'medicine':0x5e8,'berries':0x688,'battle':0x7e8}[case['pocket']]
        raw[offset:offset+4]=item.to_bytes(2,'little')+quantity.to_bytes(2,'little')
        state.update(bag=raw.hex(),item_offset=offset)
        state['mons']['1'].update(hp=36,statuses=[0]*5)
        mon=state['mons'][key]
        mon.update(hp=case['hp'] if case['hp'] is not None else 36,
                   statuses=[int(i==case['status_id']) for i in range(1,6)])
        if case['kind'].startswith('pp-'):mon.update(moves=[82,150,0,0],pp=list(case['initial_pp']))
    if all_items:
        mon=row['after']['mons'][key]
        if case['no_effect']:pass
        elif case['kind']=='revive':mon['hp']=18 if item==28 else 36
        elif case['kind'].startswith('pp-'):
            mon['pp']={38:[4,17,0,0],39:[4,40,0,0],40:[10,17,0,0],41:[10,40,0,0],154:[4,17,0,0]}[item]
        else:mon.update(hp=min(36,mon['hp']+case['healing']),statuses=[0]*5)
    party=dict(target=case['target_slot'],item=item,owner=0,move_slot=case['move_slot'])
    for event in row['events']:
        if event.get('item') == 17:event['item']=item
        if event['name']=='mask':event['result']=case['mask'] if all_items else 0
        if event['name']=='lists' and all_items:
            event['lists']=[[dict(item=item,quantity=3)] if c in case['categories'] else [] for c in range(5)]
            event['counts']=[len(v) for v in event['lists']]
        if event['name']=='commit_item' and all_items:event['result']=item
        if event['name']=='commit_target':event.update(target=case['target_slot'],result=case['target_slot'],party=dict(party))
        if event['name']=='command':
            event.update(target=target_id,move_slot=case['move_slot'])
            event['after']=((case['move_slot']<<20)+item*16+2).to_bytes(4,'little').hex()+target_id.to_bytes(4,'little').hex()+'01000000'
        if event['name']=='effect':event.update(move_slot=case['move_slot'],target_id=target_id)
        for field in ('args','before','after'):
            if isinstance(event.get(field),dict) and event[field].get('item') == 17:
                event[field].update(item=item,category=category)
    if all_items and case['status_id']:
        before=copy.deepcopy(row['before']['mons'][key])
        row['events'].append(dict(name='status_effect',status_id=case['status_id'],result=1,
                                 before=before,after=dict(before,statuses=[0]*5)))
    callback={'pp-one':'pp_one','pp-all':'pp_all','revive':'revive'}.get(case['kind'])
    if all_items and callback:
        row['events'].append(dict(name=callback,item=item,move_slot=case['move_slot'],result=0 if case['no_effect'] else 1,
            before=copy.deepcopy(row['before']['mons'][key]),after=copy.deepcopy(row['after']['mons'][key])))
    if all_items and case['kind']=='pp-one':
        row['events'] += [dict(name='move_menu',party=dict(party)),
                          dict(name='move_selected',slot=case['move_slot'],party=dict(party))]
    if case['no_effect'] and all_items:
        row['after']['quantity']=3;row['after']['bag']=row['before']['bag']
        row['events']=[e for e in row['events'] if e['name']!='consume']
        row['events'].append(dict(name='failure_message',actor_id=1,message=0x3f))
        if item in (17,18):
            row['events'].append(dict(name='ordinary_hp' if item==17 else 'status_effect',status_id=5,result=0,
                before=copy.deepcopy(row['before']['mons'][key]),after=copy.deepcopy(row['before']['mons'][key])))
    row=finish_sample(row)
    if not actual_all and case['restricted_allowed']:
        row['flags']=0;row['options']['after']=0x200
        for state in (row['before'],row['after']):state['snapshot']['flags']=0
        capture=next(e for e in row['events'] if e['name']=='captured')
        capture['snapshot']['flags']=0;capture['context']['options_copy']=0x200
    return row


class NativeItemsFrameworkTests(unittest.TestCase):
    def test_pp_scope_excludes_all_pending_revival_and_eligible_modes_execute(self):
        from native_items_matrix import variants
        self.assertEqual(variants('pp-only',17),[(i,0) for i in (38,39,40,41)])
        self.assertEqual(variants('berry-flute-checkpoint',17),[(151,1),(65,1)])
        self.assertEqual(variants('berry-flute',17),[(151,1),(155,0),(154,0),(65,1)])
        self.assertEqual(len(variants('all-additions',17)),22)
        for item,category in variants('berry-flute',17):
            row=medicine_sample(item,category,False)
            self.assertTrue(checkpoint(row))
            for mutate in (lambda r:r['events'].pop(next(i for i,e in enumerate(r['events']) if e['name']=='consume')),
                           lambda r:r['after'].update(quantity=3),
                           lambda r:r['after'].update(item_offset=0x5e8),
                           lambda r:r['after']['mons']['13']['pp'].__setitem__(0,40)):
                bad=copy.deepcopy(row);mutate(bad)
                with self.assertRaises(AssertionError):checkpoint(bad)

    def test_eligible_fixtures_use_native_physical_pockets_and_dispatch(self):
        import save_core
        from emu_harness import SaveFile, POCKETS
        from native_items_fixture import prepare
        receipt=json.loads(RECEIPT.read_text())
        with scratch('eligible-items-fixtures-') as tmp:
            for item,pocket in ((151,'berries'),(155,'berries'),(154,'berries'),(65,'battle')):
                fixture=prepare(receipt,Path(tmp)/str(item),item)
                self.assertEqual(fixture['metadata']['pocket'],pocket)
                battery=SaveFile(fixture['battery'])
                for name in POCKETS:
                    self.assertEqual(battery.pocket(name),[(item,3)] if name==pocket else [])
                mon=save_core.request('decodePokemon',fixture['damaged'],diagnostic=False)
                self.assertTrue(mon['checksumOk']);self.assertEqual(mon['flags'],0)

    def test_revive_hp_watch_is_read_only_bounded_and_propagates_callback_errors(self):
        from native_items_trace import ItemsTrace
        from unittest.mock import Mock
        trace=ItemsTrace.__new__(ItemsTrace);trace.hp_watch=None
        trace.run=dict(item=28,flags=4,events=[])
        mon=0x02300000; regs=[0]*16;regs[13]=0x027e0000;regs[15]=0x0221783c
        memory=types.SimpleNamespace(register_write=Mock())
        trace.h=types.SimpleNamespace(emu=types.SimpleNamespace(memory=memory),reg=regs,
            frame=1,_hook_error=None,u16=lambda a:15,read=lambda a,n:bytes(n))
        before=dict(mons={'2':dict(address=mon)})
        trace.watch_revive_hp(before)
        memory.register_write.assert_called_once()
        args,kw=memory.register_write.call_args
        self.assertEqual(args[0],mon+0x1e);self.assertEqual(kw,dict(size=2))
        callback=args[1];callback(mon+0x1e,2)
        event=trace.run['events'][-1]
        self.assertEqual(event['name'],'revive_hp_write')
        self.assertEqual(event['registers'][15],regs[15]);self.assertEqual(event['observed_hp'],15)
        # Bad diagnostic reads must reach Harness.cycle's error bridge.
        trace.h.read=Mock(side_effect=ValueError('read failed'))
        callback(mon+0x1e,2)
        self.assertEqual(trace.h._hook_error[0],mon+0x1e)
        self.assertIsInstance(trace.h._hook_error[1],ValueError)
        trace.stop_hp_watch()
        memory.register_write.assert_called_with(mon+0x1e,None,size=2)
        self.assertIsNone(trace.hp_watch)
        trace.stop_hp_watch();self.assertEqual(memory.register_write.call_count,2)
        # Hidden-item path never registers a watch.
        trace.run['flags']=0;trace.watch_revive_hp(before)
        self.assertEqual(memory.register_write.call_count,2)

    def test_reordered_revive_menu_preserves_fixture_and_recipient_identity(self):
        from native_items_cases import CASES
        from native_items_oracles import selected_party_entry,events
        case=CASES[28];row=medicine_sample(28,0,True)
        mapping=events(row,'party_mapping')[0]
        self.assertEqual((case['target_slot'],case['ui_slot']),(1,2))
        self.assertEqual([e['id'] for e in mapping['entries']],[1,3,2])
        self.assertEqual(selected_party_entry(mapping,case,row['before'])['id'],2)
        self.assertTrue(checkpoint(row))
        with self.assertRaisesRegex(AssertionError,'wrong native recipient'):
            selected_party_entry(mapping,dict(case,ui_slot=1),row['before'])
        for change in (lambda r:events(r,'commit_target')[0].update(target=1,result=1),
                       lambda r:events(r,'target_resolved')[0].update(id=3),
                       lambda r:events(r,'target_resolved')[0].update(ui_slot=1),
                       lambda r:events(r,'party_mapping')[0]['entries'][2].update(copy_sha256='0'*64),
                       lambda r:events(r,'party_mapping')[0]['entries'][2].update(hp=31)):
            bad=medicine_sample(28,0,True);change(bad)
            with self.assertRaises(AssertionError):checkpoint(bad)
        for name in ('party_mapping','target_resolved'):
            bad=medicine_sample(28,0,True);bad['events']=[e for e in bad['events'] if e['name']!=name]
            with self.assertRaises(AssertionError):checkpoint(bad)

    def test_party_mapping_reads_native_roster_order_not_fixture_order(self):
        from native_items_trace import ItemsTrace
        base=0x02200000;data=bytearray(0x10000)
        def put(a,n,width=4):data[a-base:a-base+width]=n.to_bytes(width,'little')
        def read(a,n):return bytes(data[a-base:a-base+n])
        controller=base;args=base+0x1000;roster=base+0x2000;party=base+0x3000
        put(controller+0x1c,roster);put(controller+0x5c4,args)
        put(args,party);put(args+0x1e,28,2);put(party,6);put(party+4,3);put(roster+0x18,3,1)
        for slot,rid in enumerate((1,3,2)):
            mon=base+0x4000+rid*0x400;backing=base+0x6000+rid*236
            put(roster+4*slot,mon);put(mon+0x10,backing);put(mon+0x14,rid,1)
            put(mon+0x1e,0 if rid==2 else 31,2);put(mon+0x1c,31,2)
            raw=bytes([rid])*236;data[backing-base:backing-base+236]=raw
            copied=party+8+slot*236;data[copied-base:copied-base+236]=raw
        trace=ItemsTrace.__new__(ItemsTrace);trace.controller=controller
        trace.h=types.SimpleNamespace(read=read,u8=lambda a:int.from_bytes(read(a,1),'little'),
            u16=lambda a:int.from_bytes(read(a,2),'little'),u32=lambda a:int.from_bytes(read(a,4),'little'))
        trace.event=lambda name,**row:dict(name=name,**row)
        result=trace.party_mapping()
        self.assertEqual([e['id'] for e in result['entries']],[1,3,2])
        self.assertEqual([e['hp'] for e in result['entries']],[31,31,0])
        self.assertTrue(all(e['source_sha256']==e['copy_sha256'] for e in result['entries']))

    def test_pp_and_revive_reject_wrong_target_slot_view_and_outcome(self):
        def event(row,name):return next(e for e in row['events'] if e['name']==name)
        mutations=[
            (38,lambda r:event(r,'move_selected').update(slot=0)),
            (38,lambda r:event(r,'command').update(move_slot=0)),
            (38,lambda r:r['after']['mons']['1']['original_pp'].__setitem__(1,7)),
            (38,lambda r:r['after']['mons']['1']['pp'].__setitem__(0,10)),
            (38,lambda r:event(r,'pp_one')['before'].update(id=2)),
            (38,lambda r:event(r,'pp_one')['after']['pp'].__setitem__(1,41)),
            (28,lambda r:r['before']['mons']['2'].update(hp=1)),
            (28,lambda r:r['after']['mons']['2'].update(hp=36)),
            (28,lambda r:event(r,'effect').update(target_id=1)),
            (28,lambda r:event(r,'effect')['actor'].update(id=2)),
            (28,lambda r:event(r,'revive')['before'].update(id=1)),
            (28,lambda r:event(r,'commit_target').update(result=0)),
            (28,lambda r:event(r,'outcome').update(words=[0,0,0])),
            (38,lambda r:event(r,'outcome').update(move_slot=0)),
            (38,lambda r:r['after']['mons']['13']['original_pp'].__setitem__(0,40)),
        ]
        for item,mutate in mutations:
            row=medicine_sample(item,0,True);mutate(row)
            with self.subTest(item=item,mutate=mutate),self.assertRaises(AssertionError):checkpoint(row)
        for item in (38,28):
            for name in ('outcome','consume','action','commit_target'):
                row=medicine_sample(item,0,True);row['events']=[e for e in row['events'] if e['name']!=name]
                with self.assertRaises(AssertionError):checkpoint(row)

    def test_item_trace_reads_distinct_active_original_pp_offsets(self):
        from native_items_trace import mon_state
        address=0x02210000;raw=bytearray(0x400)
        raw[0x14]=1
        for offset,value in ((0x252,82),(0x25a,150),(0x254,4),(0x255,10),(0x25c,7),(0x25d,40)):
            raw[offset]=value
        h=types.SimpleNamespace(u8=lambda a:raw[a-address],
            u16=lambda a:int.from_bytes(raw[a-address:a-address+2],'little'),
            u32=lambda a:int.from_bytes(raw[a-address:a-address+4],'little'))
        mon=mon_state(h,address)
        self.assertEqual((mon['moves'][0],mon['pp'][0],mon['pp_max'][0]),(82,4,10))
        self.assertEqual((mon['original_moves'][0],mon['original_pp'][0],mon['original_pp_max'][0]),(150,7,40))
        self.assertEqual(mon['pp_linked'][0],0)

    def test_native_outcome_reads_sixth_argument_before_caller_frame_expires(self):
        from native_items_trace import ItemsTrace
        stack=0x027e3000;r=[0]*16;r[:4]=[0x02210000,38,1,1];r[13]=stack;r[14]=0x022216af
        words={stack+4:stack+0x14,stack+0x14:0,stack+0x18:1,stack+0x1c:0}
        reads=[];callbacks=[];rows=[]
        def read(a):reads.append(a);return words[a]
        trace=ItemsTrace.__new__(ItemsTrace)
        trace.h=types.SimpleNamespace(reg=types.SimpleNamespace(r=r),u32=read)
        trace.s=types.SimpleNamespace(returned=lambda f:callbacks.append(f))
        def event(name,**data):row=dict(name=name,**data);rows.append(row);return row
        trace.event=event
        with patch('native_items_trace.mon_state',return_value={'id':1}):trace.outcome()
        self.assertEqual(reads,[stack+4]);callbacks[0]()
        self.assertEqual(rows[0]['words'],[0,1,0]);self.assertEqual(rows[0]['move_slot'],1)
        words[stack+4]=0
        with self.assertRaisesRegex(AssertionError,'caller frame'):trace.outcome()

    def test_all_seven_new_fixtures_are_typed_and_four_boot_plan_is_bounded(self):
        import save_core
        from native_items_fixture import prepare,install_player
        from native_items_matrix import plan,variants
        receipt=json.loads(RECEIPT.read_text())
        with scratch('pp-revive-fixtures-') as tmp:
            jobs=plan(Path(tmp)/'matrix','pp-revive-checkpoint',17)
            self.assertEqual([(j['item'],j['mode']) for j in jobs],[(38,'all'),(38,'restricted'),(28,'all'),(28,'restricted')])
            self.assertEqual(len(variants('pp-revive',17)),7)
            self.assertEqual(len(variants('all-additions',17)),22)
            for item in (28,29,37,38,39,40,41):
                fixture=prepare(receipt,Path(tmp)/str(item),item)
                mon=save_core.request('decodePokemon',fixture['damaged'],diagnostic=False)
                self.assertTrue(mon['checksumOk']);self.assertEqual(mon['flags'],0)
                if item in (28,29,37):self.assertEqual(mon['party']['currentHp'],0)
                else:
                    self.assertEqual([(m['id'],m['pp']) for m in mon['moves']],[(82,4),(150,7),(0,0),(0,0)])
                    self.assertEqual(mon['party']['currentHp'],mon['party']['stats']['hp'])
                writes=[]
                h=types.SimpleNamespace(in_field=lambda:True,array=lambda i:0x02210000,u32=lambda a:6,
                    write=lambda a,b:writes.append((a,b)),w32=lambda a,v:None,frame=1)
                trace=types.SimpleNamespace(snapshot=lambda:{'epoch':0},run={'events':[]})
                install_player(types.SimpleNamespace(h=h),trace,fixture)
                slot=1 if item in (28,29,37) else 0
                self.assertEqual(writes[slot][1],fixture['damaged'])
                self.assertEqual(writes[1-slot][1],fixture['healthy'])

    def test_every_implemented_medicine_requires_correct_effect_and_list(self):
        from native_items_cases import CASES
        for item,case in CASES.items():
            for category in case['categories']:
                for mode in (False,True):
                    with self.subTest(item=item,category=category,all_items=mode):
                        row=medicine_sample(item,category,mode);self.assertTrue(checkpoint(row))
                        row['after']['quantity']=1
                        with self.assertRaises(AssertionError):checkpoint(row)
                row=medicine_sample(item,category,True)
                key=str(case['target_slot']+1)
                row['after']['mons'][key]=copy.deepcopy(row['before']['mons'][key])
                with self.assertRaises(AssertionError):checkpoint(row)
                row=medicine_sample(item,category,True)
                next(e for e in row['events'] if e['name']=='lists')['lists'][category]=[]
                with self.assertRaises(AssertionError):checkpoint(row)
        for item in (19,20,21,22,23,27,42,54):
            row=medicine_sample(item,CASES[item]['category'],True)
            row['events'][-1]['status_id']=6
            with self.assertRaises(AssertionError):checkpoint(row)
        row=medicine_sample(23,0,True)
        next(e for e in row['events'] if e['name']=='lists')['lists'][1]=[]
        with self.assertRaises(AssertionError):checkpoint(row)

    def test_matrix_retains_runs_and_invalidates_only_selected_variants(self):
        from native_items_matrix import plan,report_paths
        with scratch('items-matrix-plan-') as tmp:
            root=Path(tmp)
            first=plan(root,'hp-status',17)
            self.assertEqual(len(first),30)
            self.assertEqual(len(report_paths(root)),30)
            self.assertEqual(len({j['out'] for j in first}),30)
            full=[j for j in first if j['item']==23]
            self.assertEqual({(j['category'],j['mode']) for j in full},
                             {(0,'all'),(0,'restricted'),(1,'all'),(1,'restricted')})
            old=full[0]['out']/'result.json';old.write_text('retained prior artifact')
            second=plan(root,'single',23)
            self.assertEqual(len(second),4)
            self.assertEqual(old.read_text(),'retained prior artifact')
            indexed=report_paths(root)
            self.assertNotIn(old,indexed)
            self.assertTrue(all(j['out']/'result.json' in indexed for j in first if j['item']!=23))
            self.assertTrue(all(json.loads((j['out']/'result.json').read_text())['status']=='interrupted' for j in second))
            self.assertNotEqual(first[0]['pair'],second[0]['pair'])
            self.assertEqual(len({j['pair'] for j in second}),1)
            index=json.loads((root/'latest.json').read_text())
            index['cases']['item-023-category-0'][0]=str(root/'outside.json')
            write_json(root/'latest.json',index)
            with self.assertRaises(ValueError):report_paths(root)

    def test_full_restore_evidence_requires_both_lists_and_matching_fixture(self):
        from native_items_evidence import validate_item_pair
        binding={'sources':'current'}
        with scratch('full-restore-evidence-') as tmp:
            paths=[]
            for category in (0,1):
                for mode in ('all','restricted'):
                    out=Path(tmp)/f'{category}-{mode}';out.mkdir();path=out/'result.json';paths.append(path)
                    run=medicine_sample(23,category,mode=='all');run.update(name=mode,checkpoint='passed')
                    fixture={key:1 for key in ('candidate_sha256','source_battery_sha256','input_battery_sha256',
                        'trainer_id','trainer_sha256','enemy_record_sha256','item','payload','splash','target_slot','ui_slot','move_slot')}
                    fixture['records']=[{'sha256':'same'}]
                    write_json(out/'items-trace.json',dict(binding=binding,battle=run))
                    write_json(out/'items-fixture.json',fixture)
                    for name in ('trainer-menu.png','bag-categories.png','returned-menu.png'):(out/name).write_bytes(b'synthetic')
                    report=dict(status='passed',driver='native_items.py',layer='native ARM gameplay items',
                        nonce=out.name,binding=binding,old_state_loaded=False,items_pair='pair1',battle=run,fixture=fixture,
                        checkpoint_artifacts=[dict(path=str(p),sha256=sha256(p)) for p in out.iterdir()])
                    write_json(path,report);write_json(out/'process.json',dict(status='passed',nonce=out.name))
            self.assertEqual(validate_item_pair(paths,binding,23)['status'],'passed')
            for subset in (paths[:2],paths[:3],paths[1:]):
                self.assertEqual(validate_item_pair(subset,binding,23)['status'],'incomplete')
            path=paths[-1];report=json.loads(path.read_text())
            report['fixture']['records'][0]['sha256']='different'
            write_json(path.parent/'items-fixture.json',report['fixture'])
            for artifact in report['checkpoint_artifacts']:artifact['sha256']=sha256(artifact['path'])
            write_json(path,report)
            self.assertEqual(validate_item_pair(paths,binding,23)['status'],'incomplete')

    def test_candidate_payload_and_typed_status_fixtures_for_matrix(self):
        import save_core
        from ndspy.rom import NintendoDSRom
        from ndspy.narc import NARC
        from native_items_cases import CASES,ADDITIONS,PENDING_ADDITIONS
        from native_items_fixture import prepare
        receipt=json.loads(RECEIPT.read_text())
        archive=NARC(NintendoDSRom.fromFile(receipt['output']['path']).getFileByName('a/0/1/7'))
        self.assertEqual(len(ADDITIONS)+len(PENDING_ADDITIONS),20)
        for item,case in CASES.items():
            payload=bytes(archive.files[item])
            self.assertEqual((payload[14],payload[27]),(case['status_payload'],case['healing']))
            self.assertEqual(payload[11:13],bytes([case['dispatch'],1]))
        with scratch('matrix-typed-status-') as tmp:
            for item in (19,20,21,22,23):
                fixture=prepare(receipt,Path(tmp)/str(item),item)
                mon=save_core.request('decodePokemon',fixture['damaged'],diagnostic=False)
                self.assertTrue(mon['checksumOk']);self.assertEqual(mon['flags'],0)
                self.assertEqual(mon['party']['status'],CASES[item]['status'])
                self.assertEqual(mon['party']['currentHp'],CASES[item]['hp'] or mon['party']['stats']['hp'])

    def test_antidote_oracle_rejects_uncured_wrong_target_and_fake_handler(self):
        self.assertTrue(checkpoint(antidote_sample(True)))
        self.assertTrue(checkpoint(antidote_sample(False)))
        changes = [lambda r:r['after']['mons']['1'].update(statuses=[0,0,0,0,1]),
                   lambda r:r['before']['mons']['1'].update(statuses=[0]*5),
                   lambda r:r['after']['mons']['2'].update(statuses=[0,0,0,0,1]),
                   lambda r:r['after'].update(quantity=3),
                   lambda r:r['events'].pop(),
                   lambda r:r['events'][-1].update(result=0),
                   lambda r:r['events'][-1]['after'].update(hp=35),
                   lambda r:r['events'][-1]['before'].update(id=2)]
        for change in changes:
            row=antidote_sample(True);change(row)
            with self.assertRaises(AssertionError):checkpoint(row)
        row=antidote_sample(False);row['after']['mons']['1']['statuses']=[0]*5
        with self.assertRaises(AssertionError):checkpoint(row)

    def test_antidote_pair_requires_both_fresh_modes_and_identical_inputs(self):
        from native_items_evidence import validate_antidote_pair
        binding={'sources':'current'}
        with scratch('antidote-pair-evidence-') as tmp:
            paths=[]
            for mode in ('all','restricted'):
                out=Path(tmp)/mode;out.mkdir();path=out/'result.json';paths.append(path)
                run=antidote_sample(mode=='all');run.update(name=mode,checkpoint='passed')
                fixture={key:1 for key in ('candidate_sha256','source_battery_sha256','input_battery_sha256',
                    'trainer_id','trainer_sha256','enemy_record_sha256','item','payload','splash','target_slot','ui_slot','move_slot')}
                fixture['records']=[{'sha256':'same'}]
                write_json(out/'items-trace.json',dict(binding=binding,battle=run))
                write_json(out/'items-fixture.json',fixture)
                for name in ('trainer-menu.png','bag-categories.png','returned-menu.png'):(out/name).write_bytes(b'synthetic oracle input')
                report=dict(status='passed',driver='native_items.py',layer='native ARM gameplay items',
                    nonce=mode,binding=binding,old_state_loaded=False,items_pair='pair1',battle=run,fixture=fixture,
                    checkpoint_artifacts=[dict(path=str(p),sha256=sha256(p)) for p in out.iterdir()])
                write_json(path,report);write_json(out/'process.json',dict(status='passed',nonce=mode))
            self.assertEqual(validate_antidote_pair(paths,binding)['status'],'passed')
            self.assertEqual(validate_antidote_pair(paths[:1],binding)['status'],'incomplete')
            self.assertEqual(validate_antidote_pair(paths,{'sources':'stale'})['status'],'incomplete')
            original=paths[1].read_text()
            for key,value in (('items_pair','other'),('nonce','old'),('old_state_loaded',True),('status','failed')):
                row=json.loads(original);row[key]=value;write_json(paths[1],row)
                self.assertEqual(validate_antidote_pair(paths,binding)['status'],'incomplete')
            paths[1].write_text(original)
            (paths[1].parent/'returned-menu.png').write_bytes(b'changed')
            self.assertEqual(validate_antidote_pair(paths,binding)['status'],'incomplete')

    def test_antidote_typed_fixture_preserves_poison_and_full_hp(self):
        import save_core
        from native_items_fixture import prepare
        receipt=json.loads(RECEIPT.read_text())
        with scratch('antidote-fixture-') as tmp:
            fixture=prepare(receipt,Path(tmp),18)
            for key,status in (('damaged',8),('healthy',0)):
                mon=save_core.request('decodePokemon',fixture[key],diagnostic=False)
                self.assertTrue(mon['checksumOk']);self.assertEqual(mon['flags'],0)
                self.assertEqual(mon['party']['status'],status)
                self.assertEqual(mon['party']['currentHp'],mon['party']['stats']['hp'])
            battery=save_core.request('inspectSave',fixture['battery'].read_bytes())
            self.assertEqual(battery['pockets']['medicine'],[[18,3]])

    def test_typed_fixture_valid_repeatable_and_battery_owned(self):
        import save_core
        from native_items_fixture import prepare
        receipt = json.loads(RECEIPT.read_text())
        source = ROOT/'work/build/memcheck/trainer.sav'; original_hash = sha256(source)
        with scratch('typed-items-fixture-') as tmp:
            a,b = [prepare(receipt,Path(tmp)/n) for n in ('a','b')]
            self.assertEqual(a['damaged'],b['damaged']); self.assertEqual(a['healthy'],b['healthy'])
            for raw, hp in ((a['damaged'],1),(a['healthy'],None)):
                mon = save_core.request('decodePokemon',raw,diagnostic=False)
                self.assertEqual(mon['flags'],0); self.assertTrue(mon['checksumOk'])
                self.assertEqual(mon['party']['currentHp'], hp or mon['party']['stats']['hp'])
                self.assertEqual([(m['id'],m['pp']) for m in mon['moves']],[(150,40),(0,0),(0,0),(0,0)])
            battery = save_core.request('inspectSave',a['battery'].read_bytes())
            self.assertEqual(battery['pockets']['medicine'],[[17,3]])
            self.assertTrue(all(not value for key,value in battery['pockets'].items() if key!='medicine'))
        self.assertEqual(sha256(source),original_hash)

    def test_prepare_twice_in_same_out_retains_prior_batteries_and_provenance(self):
        import save_core
        from emu_harness import SaveFile
        from native_items_fixture import prepare
        receipt=json.loads(RECEIPT.read_text())
        source=ROOT/'work/build/memcheck/trainer.sav'; source_bytes=source.read_bytes()
        with scratch('items-repeated-out-') as tmp:
            out=Path(tmp)
            # Model an existing output from the original fixed-name driver.
            legacy=out/'items-input.sav'; legacy.write_bytes(source_bytes)
            first=prepare(receipt,out)
            first_bytes=first['battery'].read_bytes()
            provenance=first['battery'].parent/'provenance.json'
            first_provenance=provenance.read_bytes()
            second=prepare(receipt,out)  # same directory, real save-core path
            self.assertNotEqual(first['battery'],second['battery'])
            self.assertNotEqual(first['battery'].parent,second['battery'].parent)
            self.assertEqual(first['battery'].read_bytes(),first_bytes)
            self.assertEqual(provenance.read_bytes(),first_provenance)
            self.assertEqual(legacy.read_bytes(),source_bytes)
            self.assertEqual(second['battery'].read_bytes(),first_bytes)
            for fixture in (first,second):
                target=fixture['battery']
                self.assertTrue(target.resolve().is_relative_to(out.resolve()))
                self.assertEqual(fixture['metadata']['input_battery_path'],str(target))
                self.assertEqual(fixture['metadata']['input_battery_sha256'],sha256(target))
                self.assertEqual(json.loads((target.parent/'provenance.json').read_text()),fixture['metadata'])
                decoded=save_core.request('inspectSave',target.read_bytes())
                self.assertEqual(decoded['pockets']['medicine'],[[17,3]])
            # The fix allocates new paths; it does not relax save-core safety.
            with self.assertRaises(FileExistsError):SaveFile(source).write(first['battery'])
            self.assertEqual(first['battery'].read_bytes(),first_bytes)
        self.assertEqual(source.read_bytes(),source_bytes)

    def test_late_enemy_fixture_rejected_before_reads_or_writes(self):
        from native_items_fixture import install_enemy_at_launch
        callbacks = {}
        r = [0]*16; r[1]=200; r[14]=0x02050815
        h = types.SimpleNamespace(reg=types.SimpleNamespace(r=r),write=lambda *a:self.fail('late write'))
        s = types.SimpleNamespace(h=h,hook=lambda a,f:callbacks.__setitem__(a,f))
        run = dict(events=[dict(name='constructor',lr=0x020507AD,setup=200,flags=1,control=0),dict(name='begin')])
        trace = types.SimpleNamespace(run=run,snapshot=lambda:dict(epoch=1))
        install_enemy_at_launch(s,trace,{})
        with patch('native_items_fixture.launch_diagnostic') as diagnostic:
            with self.assertRaisesRegex(AssertionError,'late enemy fixture'):
                callbacks[0x0204FCE4]()
            diagnostic.assert_called_once()  # even rejected entry is observable

    def test_inventory_reader_rejects_null_and_invalid_range_before_memory_read(self):
        from native_items_trace import read_inventory
        calls=[]
        h=types.SimpleNamespace(read=lambda *args:calls.append(args))
        for address in (0,4,0x01fffffc,0x02200001,0x023DC000-0x860,0xffffffff):
            with self.subTest(address=address),self.assertRaisesRegex(AssertionError,'battle Bag pointer'):
                read_inventory(h,address)
        self.assertEqual(calls,[])

    def test_inventory_reader_checks_pockets_and_retains_native_tail(self):
        from native_items_trace import read_inventory
        raw=bytearray(0x864);raw[0x5e8:0x5ec]=bytes([17,0,3,0]);raw[-4:]=b'tail'
        h=types.SimpleNamespace(read=lambda a,n:bytes(raw[:n]))
        row=read_inventory(h,0x02200000)
        self.assertEqual((row['item'],row['quantity']),(17,3))
        self.assertEqual(bytes.fromhex(row['bag'])[-4:],b'tail')
        self.assertEqual(len(bytes.fromhex(row['bag'])),0x864)
        raw[0x5ea:0x5ec]=(57732).to_bytes(2,'little')
        with self.assertRaisesRegex(AssertionError,'invalid medicine'):read_inventory(h,0x02200000)
        raw[0x5ea:0x5ec]=bytes([3,0]);raw[0x5ec:0x5f0]=raw[0x5e8:0x5ec]
        with self.assertRaisesRegex(AssertionError,'duplicate'):read_inventory(h,0x02200000)

    def test_state_and_capture_use_battle_clone108_and_trainer_info(self):
        from native_items_trace import ItemsTrace
        root,setup,bag,info,options=0x02200000,0x02201000,0x02203000,0x02205000,0x02206000
        labels=dict(snapshot=0x023dc100,generation=0x023dc120,setup_owner=0x023dc124,save_owner=0x023dc128)
        words={0x02255bac:root,root+0x10:setup,setup:1,setup+0x18c:0,
               setup+0x108:bag,setup+0xf8:info,setup+0x130:options,setup+0x1c0:0x02207000,
               labels['generation']:1,labels['setup_owner']:setup,labels['save_owner']:0x02207000}
        for i in (1,2,3,13):words[root+0x1d0+4*i]=0x02208000+i*0x500
        raw=bytearray(0x864);raw[0x5e8:0x5ec]=bytes([17,0,3,0])
        reads=[]
        def read(address,size):
            reads.append((address,size));self.assertEqual(address,bag);return bytes(raw[:size])
        h=types.SimpleNamespace(u32=lambda a:words[a],u16=lambda a:0x220,read=read,save=0x02207000)
        t=ItemsTrace.__new__(ItemsTrace);t.run={'item':17};t.h=h;t.s=types.SimpleNamespace(labels=labels)
        snap=dict(root=root,epoch=1,flags=4,cap=12,allowed=1)
        t.snapshot=lambda:snap;rows=[];t.event=lambda name,**data:rows.append(dict(name=name,**data))
        t.captured()
        context=rows[-1]['context']
        self.assertEqual((context['bag'],context['trainer_info']),(bag,info));self.assertNotIn('party',context)
        with patch('native_items_trace.mon_state',return_value={}):row=t.state()
        self.assertEqual((row['bag_address'],row['item'],row['quantity']),(bag,17,3))
        self.assertEqual(reads,[(bag,0x864)])
        # Reproduce the former ITCM bug: never read the null pointer even with
        # a live snapshot. setup+168 is deliberately absent from this memory.
        words[setup+0x108]=0;reads.clear()
        with self.assertRaisesRegex(AssertionError,'battle Bag pointer'):t.state()
        self.assertEqual(reads,[])

    def test_launch_records_both_pointer_families_before_capacity_failure(self):
        from native_items_fixture import install_enemy_at_launch
        setup,party,info,save = 0x02100000,0x02110000,0x02120000,0x02130000
        memory = bytearray(0x400000); base=0x02000000
        def put(address,value):memory[address-base:address-base+4]=value.to_bytes(4,'little')
        def read(address,size):return bytes(memory[address-base:address-base+size])
        put(setup,1);put(setup+8,party);put(setup+0xfc,info);put(setup+0x1c0,save)
        put(party,6);put(party+4,0)  # deliberate unpopulated actual party
        put(info,6);put(info+4,1)    # old wrong offset would wrongly look valid
        callbacks={};r=[0]*16;r[1]=setup;r[14]=0x02050815
        h=types.SimpleNamespace(reg=types.SimpleNamespace(r=r),read=read,save=save,
            u32=lambda a:int.from_bytes(read(a,4),'little'),in_field=lambda:True,
            write=lambda *a:self.fail('fixture wrote before party validation'))
        run=dict(events=[dict(name='constructor',lr=0x020507AD,setup=setup,flags=1,control=0)])
        def event(name,**data):
            row=dict(name=name,**data);run['events'].append(row);return row
        trace=types.SimpleNamespace(run=run,snapshot=lambda:dict(epoch=0),event=event)
        with scratch('items-launch-observation-') as tmp:
            session=types.SimpleNamespace(h=h,out=Path(tmp),hook=lambda a,f:callbacks.__setitem__(a,f))
            install_enemy_at_launch(session,trace,{})
            with self.assertRaisesRegex(AssertionError,'capacity=6, count=0'):
                callbacks[0x0204FCE4]()
            diagnostic=json.loads((Path(tmp)/'trainer-launch-diagnostic.json').read_text())
            self.assertEqual(diagnostic['selected_party_offset'],8)
            self.assertEqual(bytes.fromhex(diagnostic['setup_bytes']),read(setup,0x1d4))
            rows={row['offset']:row for row in diagnostic['pointers']}
            self.assertEqual((rows[8]['address'],rows[8]['capacity'],rows[8]['count']),(party,6,0))
            self.assertEqual((rows[0xfc]['address'],rows[0xfc]['kind']),(info,'trainer_info'))
            self.assertEqual(rows[0xfc]['word1'],1)
            self.assertEqual(run['events'][-1],diagnostic)

    def test_all_checkpoint_rejects_missing_effect_target_quantity_and_turn(self):
        self.assertTrue(checkpoint(sample(True)))
        changes = [lambda r:r['after'].update(quantity=3),
                   lambda r:r['after']['mons']['1'].update(hp=1),
                   lambda r:r['after']['mons']['2'].update(hp=35),
                   lambda r:r['after']['mons']['13'].update(pp=[40,0,0,0],statuses=[0]*5),
                   lambda r:r['events'].append(dict(name='action',actor=dict(id=13),move=150))]
        for change in changes:
            row = sample(True); change(row)
            with self.assertRaises(AssertionError): checkpoint(row)
        for name in ('accept','commit_item','commit_target','command','effect','consume','action','mask','lists'):
            row = sample(True); row['events'] = [e for e in row['events'] if e['name'] != name]
            with self.subTest(missing=name),self.assertRaises(AssertionError): checkpoint(row)
        for name,key,value in (('mask','result',0),('commit_target','result',1),('consume','owner',1),
                               ('accept','result',0),('command','after','00'*12)):
            row = sample(True)
            next(e for e in row['events'] if e['name']==name)[key] = value
            with self.subTest(name=name),self.assertRaises(AssertionError): checkpoint(row)

    def test_restricted_checkpoint_rejects_visibility_command_and_turn_bypasses(self):
        self.assertTrue(checkpoint(antidote_sample(False)))
        for name in ('accept','command','effect','consume','action'):
            row=antidote_sample(False);row['events'].append(dict(name=name))
            with self.subTest(name=name),self.assertRaises(AssertionError):checkpoint(row)
        for key in ('command_before_cancel','command_after_cancel'):
            row=antidote_sample(False);row[key]['slot']=1
            with self.assertRaises(AssertionError):checkpoint(row)
        row=antidote_sample(False);next(e for e in row['events'] if e['name']=='mask')['result']=8
        with self.assertRaises(AssertionError):checkpoint(row)
        row=antidote_sample(False);row['after']['mons']['1']['hp']=2
        with self.assertRaises(AssertionError):checkpoint(row)

    @staticmethod
    def _set_visibility(row, item, category, visible):
        """Rewrite only the mask and Bag-list observations of a synthetic run."""
        from native_items_cases import CASES
        for event in row['events']:
            if event['name']=='mask':event['result']=CASES[item]['mask'] if visible else 0
            if event['name']=='lists':
                event['lists']=[[dict(item=item,quantity=3)] if visible and c==category else [] for c in range(5)]
                event['counts']=[len(v) for v in event['lists']]
        return row

    def test_default_and_all_visibility_contrast(self):
        # Potion is allowed by the Chinese rules (DEFAULT) and by ALL; an addition
        # (Antidote) is hidden in DEFAULT and visible in ALL (D-2412).
        for mode in (False,True):
            self.assertTrue(checkpoint(medicine_sample(17,0,mode)),mode)
        self.assertTrue(checkpoint(medicine_sample(18,1,True)))
        self.assertTrue(checkpoint(medicine_sample(18,1,False)))
        # A DEFAULT-allowed item hidden in DEFAULT must fail.
        row=self._set_visibility(medicine_sample(17,0,False),17,0,False)
        with self.assertRaisesRegex(AssertionError,'did not expose exactly selected item'):checkpoint(row)
        # An addition visible in DEFAULT must fail.
        row=self._set_visibility(medicine_sample(18,1,False),18,1,True)
        with self.assertRaisesRegex(AssertionError,'restricted selected item visible'):checkpoint(row)
        # An addition hidden in ALL must fail.
        row=self._set_visibility(medicine_sample(18,1,True),18,1,False)
        with self.assertRaisesRegex(AssertionError,'did not expose exactly selected item'):checkpoint(row)
        # Potion hidden in ALL must also fail.
        row=self._set_visibility(medicine_sample(17,0,True),17,0,False)
        with self.assertRaisesRegex(AssertionError,'did not expose exactly selected item'):checkpoint(row)

    def test_default_allowed_flag_matches_untouched_chinese_item_metadata(self):
        from native_items_cases import CASES, ADDITIONS, GATE_ITEM, usable
        from support import CN, load_rom
        if not CN.is_file():self.skipTest('Local untouched Chinese ROM unavailable')
        from ndspy.narc import NARC
        narc=NARC(load_rom().getFileByName('a/0/1/7'))
        for item,case in CASES.items():
            mask=(int.from_bytes(narc.files[item][8:10],'little')>>11)&31
            with self.subTest(item=item,name=case['name']):
                # CN battle mask nonzero <=> DEFAULT keeps the item usable.
                self.assertEqual(bool(mask),case['restricted_allowed'])
                if mask:self.assertEqual(mask,case['mask'])
                self.assertEqual(usable(dict(item=item,flags=0)),bool(mask))
                self.assertTrue(usable(dict(item=item,flags=4)))
        self.assertEqual(len(ADDITIONS),20)
        self.assertTrue(all(not CASES[i]['restricted_allowed'] for i in ADDITIONS))
        self.assertIn(GATE_ITEM,ADDITIONS)

    def test_fade13_neither_proves_denial_nor_invalidates_success(self):
        self.assertTrue(checkpoint(sample(True)))  # native success also returns13
        for field,value in (('item',0),('category',4)):
            row=sample(True)
            next(e for e in row['events'] if e['name']=='accept')['after'][field]=value
            with self.assertRaises(AssertionError):checkpoint(row)
        for field,value in (('item',18),('category',1)):
            row=antidote_sample(False)
            next(e for e in row['events'] if e['name']=='fade_close_state13')['args'][field]=value
            with self.assertRaises(AssertionError):checkpoint(row)
        row=antidote_sample(False)
        next(e for e in row['events'] if e['name']=='commit_item')['result']=18
        with self.assertRaises(AssertionError):checkpoint(row)

    def test_trainer_entry_requires_actual_control_and_owner_capture(self):
        for key,value in (('control',8),('flags',0),('published_save',301)):
            row=sample(True);next(e for e in row['events'] if e['name']=='captured')['context'][key]=value
            with self.assertRaises(AssertionError):checkpoint(row)
        for name in ('constructor','captured','begin','enemy_fixture'):
            row=sample(True);row['events']=[e for e in row['events'] if e['name']!=name]
            with self.assertRaises(AssertionError):checkpoint(row)

    def test_explicit_overlay9_guard_rejects_reused_options_code(self):
        a=0x021EC2CC;memory={a:b'bag-code'};callbacks={};seen=[]
        s=NativeSession.__new__(NativeSession)
        s.payload=b'';s.callbacks={};s.reused_addresses={}
        s.overlays={9:types.SimpleNamespace(ramAddress=a,data=b'bag-code'),
                    14:types.SimpleNamespace(ramAddress=0x022007e0,data=b'battle'),
                    50:types.SimpleNamespace(ramAddress=a,data=b'options!')}
        s.h=types.SimpleNamespace(read=lambda a,n:memory[a][:n],on_exec=lambda a,f:callbacks.__setitem__(a,f))
        s.hook(a,lambda:seen.append('bag'),overlay=9)
        s.hook(a,lambda:seen.append('options'),overlay=50)
        callbacks[a](s.h);self.assertEqual(seen,['bag'])
        memory[a]=b'options!';callbacks[a](s.h);self.assertEqual(seen,['bag','options'])
        with self.assertRaises(ValueError):s.code(0x2202954,overlay=9)

    def test_items_evidence_registered_without_cross_feature_or_stale_acceptance(self):
        manifest=json.loads((SOURCE/'tests/required_native.json').read_text())
        definitions={r['id']:r for r in manifest['cases']}
        self.assertEqual(definitions['items.restricted']['driver'],'native_items.py')
        self.assertEqual(definitions['runtime.ordinary_1']['driver'],'native_items.py')
        self.assertEqual(definitions['items.addition_18']['driver'],'native_items.py')
        with scratch('items-evidence-') as tmp:
            out=Path(tmp);a=out/'trace.json';a.write_text('{}')
            case=dict(status='passed',artifacts=[dict(path=str(a),sha256=sha256(a))])
            row=dict(status='passed',driver='native_items.py',layer='native ARM gameplay items',
                     nonce='new',old_state_loaded=False,binding={'sources':'current'},
                     cases={'runtime.ordinary_1':case,'growth.two_participants':case})
            write_json(out/'process.json',dict(status='passed',nonce='new'))
            write_json(out/'result.json',row)
            got=validate_native(manifest,[out/'result.json'],row['binding'])
            self.assertEqual(got['runtime.ordinary_1']['status'],'passed')
            self.assertEqual(got['growth.two_participants']['status'],'incomplete')
            got=validate_native(manifest,[out/'result.json'],{'sources':'changed'})
            self.assertEqual(got['runtime.ordinary_1']['status'],'incomplete')

    def test_native_driver_and_trace_never_force_outcomes_or_restore_state(self):
        for name in ('native_items.py','native_items_trace.py'):
            tree=ast.parse((SOURCE/'tests'/name).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                    self.assertNotIn(node.func.attr,{'write','w8','w16','w32','load_state','load_file',
                                                     'set_cpu_reg','generate_pokemon','battle_turn'})


if __name__ == '__main__':unittest.main()
