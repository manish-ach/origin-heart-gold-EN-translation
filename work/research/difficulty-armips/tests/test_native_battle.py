"""Battle driver infrastructure negatives; never emulator/native acceptance."""
import ast
import copy
import json
from pathlib import Path
import types
import unittest
from unittest.mock import patch
from support import SOURCE, scratch, sha256, RECEIPT
from evidence import validate_native, write_json
from native_battle_helpers import NativeSession
from native_battle_oracles import compare_caps, validate_run, root_reuse, holder_verdict


class NativeBattleFrameworkTests(unittest.TestCase):
    def test_opponent_hp_fixture_rejects_live_battle_before_any_write(self):
        from native_battle_helpers import prepare_opponent
        run={'events':[dict(name='constructor',flags=0,control=0),dict(name='begin')]}
        h=types.SimpleNamespace(write=lambda *args:self.fail('late fixture write'))
        session=types.SimpleNamespace(h=h)
        with patch('emu_harness.wild_battle',return_value=dict(pid=7,copies=['0x02300000'])):
            with self.assertRaisesRegex(AssertionError,'after native battle entry'):
                prepare_opponent(session,types.SimpleNamespace(),run)

    def test_typed_fixture_is_repeatable_and_uses_valid_recalculated_records(self):
        from native_battle_fixture import prepare_fixture_templates
        receipt=json.loads(RECEIPT.read_text())
        with scratch('typed-battle-fixture-') as tmp:
            out=Path(tmp)
            first=prepare_fixture_templates(receipt,out/'first')
            second=prepare_fixture_templates(receipt,out/'second')
            self.assertEqual(first,second)
            report=json.loads((out/'first/fixture-templates.json').read_text())
            for level in (8,11,12):
                mon=report['templates'][str(level)]['decoded']
                self.assertTrue(mon['checksumOk']);self.assertEqual(mon['flags'],0)
                self.assertEqual(mon['speciesId'],19);self.assertFalse(mon['isEgg'])
                self.assertEqual(mon['party']['level'],level)
                self.assertEqual(mon['experience'],report['thresholds'][level])
                self.assertEqual(mon['party']['currentHp'],mon['party']['stats']['hp'])
                self.assertEqual(list(mon['evs'].values()),[0]*6)
                self.assertEqual([(m['id'],m['pp'],m['ppUps']) for m in mon['moves']],
                                 [(82,30,0),(150,30,0),(0,0,0),(0,0,0)])
        self.assertNotIn('.generate_pokemon(', (SOURCE/'tests/native_battle_helpers.py').read_text())

    def test_transition_null_active_and_observed_teardown_keep_final_checks_strict(self):
        from native_battle_input import BattleInput
        root,ui=0x022c0000,0x022e0000
        memory={0x02255bac:root,0x02255b94:ui,ui+0x1f4:0,ui+0x3ec:0}
        for i in (1,2,3,13):memory[root+0x1d0+4*i]=0x02300000+i*0x300
        h=types.SimpleNamespace(frame=1,in_field=lambda:False,u32=lambda a:memory[a],
                                u8=lambda a:2,on_screen=lambda name:False)
        captures=[];run={'name':'test','events':[]}
        inp=BattleInput(types.SimpleNamespace(h=h,checkpoint=lambda n,r:captures.append(copy.deepcopy(r))),
                        types.SimpleNamespace(snapshot=lambda:dict(root=root)),run)
        with patch('native_battle_input.mon_state',side_effect=lambda h,a:dict(id=(a-0x02300000)//0x300)):
            row=inp.point('switch-shift',allow_absent_ui=True)
            self.assertEqual(row['phase'],'ui_not_ready');self.assertEqual(row['active_address'],0)
            self.assertIsNone(row['active']);self.assertEqual(row['mons']['2']['id'],2)
            with self.assertRaises(AssertionError):inp.state()
            h.on_screen=lambda name:True
            with self.assertRaises(AssertionError):inp.state(allow_absent_ui=True)
            memory[ui+0x1f4]=memory[root+0x1d0+8]
            self.assertEqual(inp.state()['active']['id'],2)  # real returned command object
            h.on_screen=lambda name:False
            for bad in (1,0xffffffff,0x02300001):
                memory[ui+0x1f4]=bad
                with self.assertRaises(AssertionError):inp.point('bad',allow_absent_ui=True)
                self.assertEqual(captures[-1]['input_states'][-1]['active_address'],bad)
                self.assertIn('probe_error',captures[-1]['input_states'][-1])
            run['events'].append({'name':'teardown'})
            # Native teardown has released objects: no dereference of the stale
            # active address or roster, but no final command-menu pass either.
            row=inp.state(allow_absent_ui=True)
            self.assertEqual(row['phase'],'teardown');self.assertIsNone(row['mons'])
            with self.assertRaises(AssertionError):inp.state()
            h.on_screen=lambda name:True
            with self.assertRaises(AssertionError):inp.state(allow_absent_ui=True)

    def test_party_overlay_can_drop_ui_but_not_battle_owner_or_switch_proof(self):
        from native_battle_input import BattleInput
        root=0x022c0000
        memory={0x02255bac:root,0x02255b94:0}
        for i in (1,2,3,13):memory[root+0x1d0+4*i]=0x02300000+i*0x300
        h=types.SimpleNamespace(in_field=lambda:False,u32=lambda a:memory[a],on_screen=lambda name:False)
        trace=types.SimpleNamespace(snapshot=lambda:dict(root=root))
        inp=BattleInput(types.SimpleNamespace(h=h),trace,{})
        with patch('native_battle_input.mon_state',side_effect=lambda h,a:dict(id=(a-0x02300000)//0x300)):
            got=inp.state(allow_absent_ui=True)
            self.assertFalse(got['ui_available']);self.assertIsNone(got['active'])
            self.assertEqual(got['mons']['2']['id'],2)
            with self.assertRaises(AssertionError):inp.state()  # strict command-menu return
            h.on_screen=lambda name:True
            with self.assertRaises(AssertionError):inp.state(allow_absent_ui=True)
            h.on_screen=lambda name:False
            memory[0x02255bac]=root+4
            with self.assertRaises(AssertionError):inp.state(allow_absent_ui=True)

    def test_cancelled_or_wrong_move_cannot_count_as_a_turn(self):
        from native_battle_input import assert_move
        before=dict(id=1,moves=[82,150,0,0],pp=[30,30,0,0])
        after=dict(before,pp=[30,29,0,0])
        actions=[dict(actor=dict(id=1),move=150)]
        assert_move(before,after,actions,1,150)
        for changed,rows in ((before,actions),(after,[]),
                             (after,[dict(actor=dict(id=2),move=150)]),
                             (after,[dict(actor=dict(id=1),move=82)]),
                             (dict(after,id=2),actions)):
            with self.assertRaises(AssertionError):assert_move(before,changed,rows,1,150)

    def test_overlay_reuse_and_nested_returns_do_not_count_wrong_code(self):
        # Exercise the actual hook multiplexer without constructing Harness.
        callbacks = {}; memory = {0x2201000:b'right123'}
        r = [0]*16; r[13] = 0x2301000; r[14] = 0x2201001
        fake = types.SimpleNamespace(reg=types.SimpleNamespace(r=r),
            read=lambda a,n:memory[a], on_exec=lambda a,fn:callbacks.__setitem__(a,fn))
        s = NativeSession.__new__(NativeSession)
        s.h=fake; s.callbacks={}; s.reused_addresses={}; s.code=lambda a:b'right123'
        seen=[]
        s.hook(0x2201000, lambda:seen.append('base'))
        s.returned(lambda:seen.append('return'))
        memory[0x2201000]=b'wrong123';callbacks[0x2201000](fake)
        self.assertEqual(seen,[])
        memory[0x2201000]=b'right123';r[13]-=8;callbacks[0x2201000](fake)
        self.assertEqual(seen,['base'])
        r[13]+=8;callbacks[0x2201000](fake);callbacks[0x2201000](fake)
        self.assertEqual(seen,['base','base','return','base'])

    def test_battle_evidence_cannot_satisfy_ui_or_accept_stale_source(self):
        with scratch('battle-evidence-') as tmp:
            out=Path(tmp);artifact=out/'trace.json';artifact.write_text('{}')
            manifest={'cases':[{'id':'growth.two_participants','driver':'native_battle.py'},
                               {'id':'ui.dpad_apply','driver':'native_ui.py'}]}
            case={'status':'passed','artifacts':[{'path':str(artifact),'sha256':sha256(artifact)}]}
            binding={'current':'sources'}
            report={'status':'passed','driver':'native_battle.py','layer':'native ARM gameplay battle',
                    'nonce':'fresh','old_state_loaded':False,'binding':binding,
                    'cases':{'growth.two_participants':case,'ui.dpad_apply':case}}
            path=out/'result.json'
            write_json(out/'process.json',{'status':'passed','nonce':'fresh'})
            write_json(path,report)
            got=validate_native(manifest,[path],binding)
            self.assertEqual(got['growth.two_participants']['status'],'incomplete')  # no real trace/oracle proof
            self.assertEqual(got['ui.dpad_apply']['status'],'incomplete')
            for change in ({'binding':{}},{'status':'failed'},{'old_state_loaded':True},
                           {'layer':'native ARM gameplay UI'},{'nonce':'old'}):
                write_json(path,dict(report,**change))
                self.assertNotEqual(validate_native(manifest,[path],binding)['growth.two_participants']['status'],'passed')

    def test_battle_driver_no_state_restore_or_outcome_register_writes(self):
        forbidden={'write','w8','w16','w32','load_state','load_file','set_cpu_reg'}
        for name in ('native_battle.py','native_battle_input.py'):
            tree=ast.parse((SOURCE/'tests'/name).read_text())
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                    self.assertNotIn(node.func.attr,forbidden|{'battle_turn'})
        # All fixture writes remain in named input helpers, never execution hooks.
        helper=ast.parse((SOURCE/'tests/native_battle_helpers.py').read_text())
        for node in ast.walk(helper):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute):
                self.assertNotIn(node.func.attr,{'load_state','load_file','set_cpu_reg'})

    def test_pair_comparison_detects_redistribution_and_ev_loss(self):
        # Deliberately synthetic summaries test comparison sensitivity only.
        # validate_run is isolated here; separate missing-trace test below ensures
        # these summaries are never accepted as native observations.
        def sample(cap):
            before=[dict(exp=100,evs=[0]*6,level=12)]*3
            after=[dict(exp=100+(0 if cap else 20),evs=[0,0,0,1,0,0],level=12),
                   dict(exp=120,evs=[0,0,0,1,0,0],level=12),
                   dict(exp=110,evs=[0,0,0,1,0,0],level=12)]
            ev=[dict(name='apply',id=i,amount=n) for i,n in ((1,0 if cap else 20),(2,20),(3,10)) if n]
            return dict(flags=2 if cap else 0,before=before,after=after,events=ev)
        off,on=sample(False),sample(True)
        with patch('native_battle_oracles.validate_run'):
            compare_caps(off,on)
            for mutate in ('redistribution','ev','positive_zero','input'):
                bad=copy.deepcopy(on)
                if mutate=='redistribution':bad['events'][0]['amount']+=20
                if mutate=='ev':bad['after'][0]['evs']=[0]*6
                if mutate=='positive_zero':bad['events'].append(dict(name='message',id=1,amount=20))
                if mutate=='input':bad['before'][0]['exp']+=1
                with self.subTest(mutate=mutate),self.assertRaises(AssertionError):compare_caps(off,bad)

    @staticmethod
    def lifecycle_run(root, epoch, flags):
        # Synthetic seam observations exercise the shipping oracle, never count
        # as native evidence and contain no reward/application substitutions.
        empty = dict(flags=0, cap=0, allowed=0, root=0, epoch=0)
        snap = dict(flags=flags, cap=12, allowed=1, root=root, epoch=epoch)
        start = epoch-1
        end = 1 if epoch == 0xFFFFFFFF else epoch+1
        return dict(flags=flags, final_snapshot=empty.copy(), events=[
            dict(name='begin', snapshot=empty.copy(), generation=start),
            dict(name='original_begin'),
            dict(name='captured', snapshot=snap.copy(), generation=epoch),
            dict(name='free', snapshot=snap.copy(), generation=epoch, root=root),
            dict(name='original_free', snapshot=empty.copy(), generation=end, root=root)])

    def test_missing_trace_and_pointer_only_reuse_are_not_passes(self):
        with self.assertRaises(AssertionError):validate_run(dict(before=[],after=[],events=[]))
        run = self.lifecycle_run
        self.assertFalse(root_reuse([]))
        self.assertFalse(root_reuse([run(1,1,0),run(2,3,2),run(3,5,0)]))
        self.assertFalse(root_reuse([run(1,1,0),run(1,3,0),run(1,5,0)]))
        self.assertTrue(root_reuse([run(1,1,0),run(1,3,2),run(1,5,0)]))
        with self.assertRaises(AssertionError):
            root_reuse([{'events':[dict(name='captured',snapshot=dict(root=1,epoch=1,flags=0))]}])

    def test_root_reuse_checks_third_and_later_runs_for_immediate_and_older_epochs(self):
        run = self.lifecycle_run
        valid = [run(1,1,0),run(1,3,2),run(1,5,0),run(1,7,2)]
        self.assertTrue(root_reuse(valid))
        for index, epoch in ((2,3),(2,1),(3,5),(3,1)):
            bad = copy.deepcopy(valid)
            # Entire local lifetime is coherent, so only the cross-run check
            # catches rollback to an immediately prior OR historical lifetime.
            bad[index] = run(1,epoch,bad[index]['flags'])
            with self.subTest(index=index,epoch=epoch),self.assertRaises(AssertionError):
                root_reuse(bad)
        # Reuse need not be adjacent, and a later different root is still checked.
        valid[1] = run(2,3,0);valid[2] = run(1,5,2)
        self.assertTrue(root_reuse(valid))
        valid[3] = run(3,3,2)
        with self.assertRaises(AssertionError):root_reuse(valid)

    def test_root_reuse_validates_all_seams_after_successful_first_pair(self):
        run = self.lifecycle_run
        mutations = ('zero_capture','begin_skip','free_skip','free_zero','free_snapshot',
                     'final_snapshot','free_owner','duplicate_begin','missing_free',
                     'order','capture_provider','begin_snapshot','cap_change')
        for mutation in mutations:
            rows = [run(1,1,0),run(1,3,2),run(1,5,0)]
            bad = rows[2]; begin,_,capture,free,released = bad['events']
            if mutation=='zero_capture':capture['snapshot']['epoch']=capture['generation']=0
            elif mutation=='begin_skip':begin['generation']=3
            elif mutation=='free_skip':released['generation']=7
            elif mutation=='free_zero':released['generation']=0
            elif mutation=='free_snapshot':free['snapshot']['flags']=2
            elif mutation=='final_snapshot':bad['final_snapshot']=capture['snapshot'].copy()
            elif mutation=='free_owner':released['root']=2
            elif mutation=='duplicate_begin':bad['events'].insert(0,begin.copy())
            elif mutation=='missing_free':bad['events'].remove(free)
            elif mutation=='order':bad['events'][3:]=[released,free]
            elif mutation=='capture_provider':capture['generation']=7
            elif mutation=='begin_snapshot':begin['snapshot']['epoch']=3
            elif mutation=='cap_change':capture['snapshot']['cap']=free['snapshot']['cap']=20
            with self.subTest(mutation=mutation),self.assertRaises(AssertionError):root_reuse(rows)

    def test_root_reuse_nonzero_uint32_wrap_at_begin_and_free(self):
        run = self.lifecycle_run
        # Free wraps FFFFFFFF -> 1, following begin advances 1 -> 2.
        rows = [run(1,0xFFFFFFFD,0),run(1,0xFFFFFFFF,2),run(1,2,0),run(1,4,2)]
        self.assertTrue(root_reuse(rows))
        # Begin wraps FFFFFFFF -> 1 (not zero), then free advances to 2.
        rows = [run(1,0xFFFFFFFE,0),run(1,1,2),run(1,3,0)]
        rows[1]['events'][0]['generation']=0xFFFFFFFF
        self.assertTrue(root_reuse(rows))
        for invalid in (0,-1,0x100000000):
            bad=copy.deepcopy(rows)
            bad[1]['events'][2]['snapshot']['epoch']=bad[1]['events'][2]['generation']=invalid
            with self.subTest(epoch=invalid),self.assertRaises(AssertionError):root_reuse(bad)
        rows[1]['events'][0]['generation']=0
        with self.assertRaises(AssertionError):root_reuse(rows)  # illicit reset at wrap


class ExpShareHolderOracleTests(unittest.TestCase):
    """The holder verdict accepts exactly the fixed behaviour (D-2403) and the rc7 baseline."""
    @staticmethod
    def run_with(exp, ev3=0):
        mon = lambda e, v: dict(exp=e, evs=[0, 0, 0, v, 0, 0])
        return dict(before=[mon(1728, 0), mon(512, 0), mon(1725, 0)], after=[mon(1900, 1), mon(700, 1), mon(1725+exp, ev3)])

    def runs(self, holder_off=95, holder_cap=3, plain_off=0):
        return {'share-on-holder': self.run_with(95, 1), 'share-off-holder': self.run_with(holder_off, 1 if holder_off else 0),
                'share-off-plain': self.run_with(plain_off, 1 if plain_off else 0),
                'share-off-cap-holder': self.run_with(holder_cap, 1 if holder_cap else 0),
                'share-off-cap-plain': self.run_with(0)}

    def test_fixed_behaviour_passes_and_baseline_behaviour_fails_it(self):
        failed, gains = holder_verdict(self.runs(), 'fixed')
        self.assertEqual(failed, []); self.assertEqual(gains['share-off-holder'], (95, [0, 0, 0, 1, 0, 0]))
        baseline = self.runs(holder_off=0, holder_cap=0)
        self.assertTrue(holder_verdict(baseline, 'fixed')[0])
        self.assertEqual(holder_verdict(baseline, 'baseline')[0], [])

    def test_each_regression_is_caught(self):
        self.assertTrue(holder_verdict(self.runs(plain_off=95), 'fixed')[0])    # non-holder shares with SHARE OFF
        self.assertTrue(holder_verdict(self.runs(holder_off=40), 'fixed')[0])   # holder gets another amount
        self.assertTrue(holder_verdict(self.runs(holder_cap=95), 'fixed')[0])   # CAP clamp lost for the holder
        self.assertTrue(holder_verdict(self.runs(holder_cap=0), 'fixed')[0])    # holder blocked by CAP completely
