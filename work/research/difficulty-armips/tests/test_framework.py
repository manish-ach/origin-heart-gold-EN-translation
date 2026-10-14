"""Evidence/timeout/register-adapter regressions. Never opens an emulator."""
import ast
import inspect
import json
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch
from support import SOURCE, FOCUS_COUNT, scratch, sha256
from evidence import bound_process, write_json, register_values, validate_native, record_focus_review

class FrameworkTests(unittest.TestCase):
    def test_preview_session_survives_exit_body_but_not_return_or_native_reset(self):
        tree=ast.parse((SOURCE/'tests/native_ui.py').read_text())
        helpers=[next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==name)
                 for name in ('end_options_session','event','preview_event')]
        from collections import Counter
        hooks={};events=[];state={'in_options':True,'mode':'custom'};preview=[]
        h=types.SimpleNamespace(frame=10,reg=types.SimpleNamespace(r=[1,0,0,0],lr=0x2001001,pc=1,sp=2),
                                read=lambda a,n:b'Options-code',u32=lambda a:1,
                                on_exec=lambda a,fn:hooks.__setitem__(a,fn))
        ns={'h':h,'last_input':state,'events':events,'counts':Counter(),'preview':preview,
            'result':{},'labels':{'page':0},'overlay_probe':b'Options-code','register_values':register_values}
        exec(compile(ast.Module(body=helpers,type_ignores=[]),'native-preview-lifecycle','exec'),ns)
        callback=ns['preview_event']('title')
        callback(h);self.assertEqual(len(preview),1)
        self.assertEqual(preview[-1]['mode'],'custom')
        ns['event']('dg_menu_exit')(h)
        callback(h);self.assertEqual(len(preview),2)  # keep native Cancel restoration observable
        self.assertEqual(preview[-1]['mode'],'exit')
        hooks[0x2001000](h)
        callback(h);self.assertEqual(len(preview),2)
        self.assertIsNone(state['mode'])
        state.update(in_options=True,mode='custom')
        ns['end_options_session']('native-save-publication')
        callback(h);self.assertEqual(len(preview),2)  # old bytes still in RAM
        self.assertIsNone(state['mode'])

    def test_manual_focus_review_is_narrow_and_source_nonce_image_bound(self):
        with scratch('manual-focus-') as tmp:
            out=Path(tmp);p=out/'result.json';binding={'candidate':'one','test_sources':'current'}
            manifest={'cases':[{'id':'ui.visible_glyphs','driver':'native_ui.py'},
                               {'id':'ui.dpad_apply','driver':'native_ui.py'}]}
            report={'status':'failed','binding':binding,'nonce':'one','old_state_loaded':False,
                    'focus_regions':[{'focus':i} for i in range(FOCUS_COUNT)],'cases':{}}
            process={'status':'failed','nonce':'one','returncode':1,'finished_utc':'now'}
            for i in range(FOCUS_COUNT):(out/f'focus-{i}.png').write_bytes(bytes([i]))
            write_json(p,report);write_json(out/'process.json',process)
            record_focus_review(p,binding,'parent','All focus images reviewed')
            got=validate_native(manifest,[p],binding)
            self.assertEqual(got['ui.visible_glyphs']['status'],'passed')
            self.assertEqual(got['ui.dpad_apply']['status'],'missing')
            for change in ({'binding':{'candidate':'other'}},{'nonce':'other'},{'old_state_loaded':True},{'focus_regions':[]}):
                write_json(p,dict(report,**change))
                self.assertNotEqual(validate_native(manifest,[p],binding)['ui.visible_glyphs']['status'],'passed')
            write_json(p,report)
            write_json(out/'process.json',dict(process,status='running'))
            self.assertNotEqual(validate_native(manifest,[p],binding)['ui.visible_glyphs']['status'],'passed')
            write_json(out/'process.json',process);(out/'focus-2.png').write_bytes(b'changed')
            self.assertNotEqual(validate_native(manifest,[p],binding)['ui.visible_glyphs']['status'],'passed')

    def test_native_dpad_sequence_does_not_shadow_input_helper(self):
        # Execute the actual driver helper and sequence with an input recorder,
        # without constructing an emulator. Catches the observed str-call crash.
        tree=ast.parse((SOURCE/'tests/native_ui.py').read_text())
        helper=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='press_key')
        loop=next(n for n in ast.walk(tree) if isinstance(n,ast.For)
                  and isinstance(n.target,ast.Name) and n.target.id=='button')
        calls=[]
        h=types.SimpleNamespace(frame=17,press=lambda button,**kw:calls.append((button,kw)))
        ns={'h':h,'inputs':[]}
        exec(compile(ast.Module(body=[helper,loop],type_ignores=[]),'native-input-sequence','exec'),ns)
        self.assertEqual([c[0] for c in calls],['RIGHT','DOWN','RIGHT','DOWN','RIGHT','DOWN','DOWN','DOWN','A'])
        self.assertEqual(len(ns['inputs']),9)
        self.assertTrue(all(c[1]=={'after':20} for c in calls))

    def test_bounded_child_exit_abort_timeout_and_missing_executable(self):
        with scratch('supervisor-') as tmp:
            for tag,argv,timeout,want in [
                ('ok',[sys.executable,'-c','print("ok")'],10,'passed'),
                ('exit',[sys.executable,'-c','raise SystemExit(7)'],10,'failed'),
                ('signal',[sys.executable,'-c','import os,signal;os.kill(os.getpid(),signal.SIGTERM)'],10,'failed'),
                ('timeout',[sys.executable,'-c','import time;time.sleep(20)'],0.05,'failed'),
                ('missing',['/no/such/program'],10,'failed')]:
                with self.subTest(tag=tag):
                    out=Path(tmp)/tag
                    row=bound_process(argv,out,timeout)
                    self.assertEqual(row['status'],want)
                    self.assertEqual(json.loads((out/'process.json').read_text())['status'],want)
                    self.assertIn('finished_utc',row)
            out=Path(tmp)/'prior';out.mkdir();write_json(out/'process.json',{'status':'running'})
            bound_process([sys.executable,'-c','pass'],out,10)
            self.assertEqual(json.loads((out/'previous-interrupted.json').read_text())['status'],'interrupted')

    def test_interrupted_supervisor_finalizes(self):
        with scratch('interrupt-') as tmp,patch('evidence.subprocess.Popen',side_effect=KeyboardInterrupt):
            row=bound_process(['unused'],Path(tmp),1)
            self.assertEqual(row['status'],'interrupted')

    def test_missing_stale_failed_and_host_evidence_cannot_complete(self):
        with scratch('evidence-') as tmp:
            out=Path(tmp);p=out/'result.json';artifact=out/'trace.json';artifact.write_text('{}')
            binding={'receipt':'current'};manifest={'cases':[{'id':'ui.dpad_apply','driver':'native_ui.py'},{'id':'growth.two_participants','driver':None}]}
            valid={'status':'passed','layer':'native ARM gameplay UI','nonce':'one','old_state_loaded':False,'binding':binding,
                   'cases':{'ui.dpad_apply':{'status':'passed','artifacts':[{'path':str(artifact),'sha256':sha256(artifact)}]}}}
            write_json(out/'process.json',{'status':'passed','nonce':'one'})
            write_json(p,valid)
            status=validate_native(manifest,[p],binding)
            self.assertEqual(status['ui.dpad_apply']['status'],'passed')
            self.assertEqual(status['growth.two_participants']['status'],'missing')
            for change in [{'status':'running'},{'status':'failed'},{'nonce':'old'},{'binding':{'receipt':'old'}},
                           {'layer':'host C'},{'old_state_loaded':True},{'cases':{'ui.dpad_apply':{'status':'passed'}}}]:
                write_json(p,dict(valid,**change))
                self.assertNotEqual(validate_native(manifest,[p],binding)['ui.dpad_apply']['status'],'passed')
            write_json(p,valid);artifact.write_text('changed')
            self.assertNotEqual(validate_native(manifest,[p],binding)['ui.dpad_apply']['status'],'passed')
            self.assertTrue(all(v['status']!='passed' for v in validate_native(manifest,[],binding).values()))
            p.write_text('{truncated')
            self.assertTrue(all(v['status']!='passed' for v in validate_native(manifest,[p],binding).values()))

    def test_required_manifest_explicit_granular_cases_and_deferrals(self):
        manifest=json.loads((SOURCE/'tests/required_native.json').read_text());ids=[c['id'] for c in manifest['cases']]
        self.assertEqual(len(ids),len(set(ids)));self.assertGreaterEqual(len(ids),60)
        for case in ('growth.two_participants','growth.partial_messages','growth.bench_share_off','runtime.root_reuse','ui.save_reload','items.doubles_slot2'):
            self.assertIn(case,ids)
        self.assertEqual(sum(i.startswith('items.addition_') for i in ids),20)
        self.assertEqual({c['feature'] for c in manifest['exceptions']},{'Rare Candy','Day Care'})

    def test_actual_installed_register_api_without_emulator(self):
        # Reads real installed accessor code against a tiny library primitive;
        # no DeSmuME instance or native library is constructed.
        from desmume.emulator import RegisterAccessor
        class Library:
            def desmume_memory_read_register(self,name):return int(name.value.decode().split('.r')[1])-2
        accessor=RegisterAccessor('arm9.',types.SimpleNamespace(emu=types.SimpleNamespace(lib=Library())))
        self.assertEqual(register_values(accessor),[0xFFFFFFFE,0xFFFFFFFF,0,1])
        self.assertEqual(register_values(types.SimpleNamespace(r=[1,2,3,4])),[1,2,3,4])

    def test_native_driver_interfaces_and_no_old_state_load(self):
        import native_ui
        from emu_harness import Harness
        for name,kwargs in [('touch',dict(x=1,y=1,frames=6,after=20)),('press',dict(key='A',after=20)),
                            ('on_exec',dict(addr=1,fn=lambda h:None)),('screenshot',dict(name='test'))]:
            inspect.signature(getattr(Harness,name)).bind(None,**kwargs)
        text=(SOURCE/'tests/native_ui.py').read_text();tree=ast.parse(text)
        calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)]
        forbidden={'write','w8','w16','w32','load_file','set_cpu_reg'}
        self.assertFalse(any(isinstance(c.func,ast.Attribute) and c.func.attr in forbidden for c in calls))
        self.assertIn("register_values(h.reg)",text)
        self.assertNotIn("getattr(h.reg,'r'",text)
        with scratch('bad-binding-') as tmp:
            p=Path(tmp)/'receipt.json';fake=Path(tmp)/'rom.nds';fake.write_bytes(b'fixture')
            from build import tool_mode  # the mode check precedes the ROM check
            p.write_text(json.dumps({'tool_mode':tool_mode(),'input':{'path':str(fake),'sha256':'wrong'},'output':{}}))
            with self.assertRaisesRegex(ValueError,'Stale ROM'):native_ui.candidate_binding(p)
