"""Fresh assembled candidate and guarded installer on disposable artifacts only."""
import copy
import io
import hashlib
import os
import sys
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import ndspy.rom
from candidate_tools import assembled, build, install, INPUT, RECEIPT
from support import SOURCE, command, sha256, scratch

class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        (cls.stage,cls.rom,cls.arm,cls.overlays,cls.raw,cls.staged,cls.payload,cls.report)=assembled()
        cls.comp,cls.hooks,cls.edits=install.contracts()

    def test_fresh_payload_reproduces_current_candidate(self):
        receipt=json.loads(RECEIPT.read_text())
        self.assertEqual(sha256(INPUT),receipt['input']['sha256'])
        candidate=ndspy.rom.NintendoDSRom.fromFile(receipt['output']['path'])
        self.assertEqual(sha256(receipt['output']['path']),receipt['output']['sha256'])
        self.assertEqual(bytes(candidate.loadArm9().sections[3].data),self.payload)
        result=install.verify_rom(self.rom,candidate,self.raw,self.staged,self.payload,self.report)
        self.assertTrue(result['all_other_logical_payloads_unchanged'])
        self.assertEqual(self.report['undefined_symbols'],[])
        self.assertEqual(self.report['relocations'],[])

    def test_source_pins_checked_and_tools_pinned_per_mode(self):
        # Release: every tool equals its pin. Development: each is recorded with its release pin.
        sources,tools=install.source_tools()
        self.assertGreater(len(sources),30);self.assertIn('clang_real',tools)
        pinned=json.loads((SOURCE/'research/options-source-pins.json').read_text())['tools']
        for name,p in pinned.items():
            with self.subTest(tool=name):
                if build.dev_tools():self.assertEqual(tools[name]['release_sha256'],p['sha256'])
                else:self.assertEqual((tools[name]['sha256'],tools[name]['version']),(p['sha256'],p['version']))
        with patch.object(install,'sha',return_value='0'*64):
            with self.assertRaisesRegex(ValueError,'source guard|protected provenance'):
                install.source_tools()

    def test_every_guard_and_whole_file_mutation_is_rejected(self):
        candidate=ndspy.rom.NintendoDSRom.fromFile(json.loads(RECEIPT.read_text())['output']['path'])
        result=install.negative_checks(self.raw,self.comp,self.hooks,self.edits,self.arm,self.overlays,candidate)
        self.assertEqual(result['rejections'],len(self.hooks)+len(self.edits)+len(self.raw)+2)

    def test_item_binding_dependencies_independently_reject_corruption(self):
        rows=install.validate_item_binding(self.raw)
        self.assertEqual(len(rows),10)
        for row in rows:
            bad=dict(self.raw);data=bytearray(bad[row['file']])
            data[int(row['start'],16)-install.BASES[row['file']]]^=1
            bad[row['file']]=bytes(data)
            with self.subTest(label=row['label']),self.assertRaisesRegex(ValueError,'item ownership dependency'):
                install.validate_item_binding(bad)

    def test_declared_bounds_overlap_and_unlisted_byte_rejected(self):
        for alter in ('size','address','overlap'):
            bad=copy.deepcopy(self.hooks)
            if alter=='size':bad[0]['size']=0x10000000
            elif alter=='address':bad[0]['address']='0xFFFFFFFF'
            else:bad.append(bad[0])
            with self.subTest(alter=alter),self.assertRaises(ValueError):install.validate_sections(self.raw,self.comp,bad,self.edits)
        for name in self.staged:
            bad=dict(self.staged);data=bytearray(bad[name]);data[-1]^=1;bad[name]=bytes(data)
            with self.subTest(file=name),self.assertRaisesRegex(ValueError,'undeclared ASM write'):
                install.verify_stage(self.raw,bad,self.hooks,self.edits,self.report,self.comp)

    def test_late_exp_seams_ev_and_field_exceptions(self):
        base=install.BASES['overlay14.bin'];before=self.raw['overlay14.bin'];after=self.staged['overlay14.bin']
        from capstone import Cs,CS_ARCH_ARM,CS_MODE_THUMB
        md=Cs(CS_ARCH_ARM,CS_MODE_THUMB);md.detail=True
        for address in (0x0221F778,0x0221F83E,0x022289EA):
            off=address-base
            self.assertNotEqual(before[off:off+4],after[off:off+4])
            ins=next(md.disasm(after[off:off+4],address));self.assertEqual(ins.mnemonic,'bl')
            self.assertTrue(build.BASE<=ins.operands[0].imm<build.LIMIT)
        # EV pass original helper and actual message/apply sites never changed.
        for start,end in [(0x0221F650,0x0221F6EC),(0x0221F7B0,0x0221F7E0),(0x0222AC30,0x0222ACB0)]:
            self.assertEqual(before[start-base:end-base],after[start-base:end-base])
        # Installer logical diff rejects every undeclared field change. Spot-check
        # both known Candy effect/consumption seams; Day Care receives no hook.
        for address in (0x0207A8FA,0x020804EC):
            off=address-0x02000000
            self.assertEqual(self.raw['arm9.bin'][off:off+16],self.staged['arm9.bin'][off:off+16])

    def test_reopened_rom_rejects_unrelated_changes_and_resident_bss(self):
        receipt=json.loads(RECEIPT.read_text())
        for kind in ('arm7','item_archive','resident','bss'):
            candidate=ndspy.rom.NintendoDSRom.fromFile(receipt['output']['path'])
            if kind=='arm7':candidate.arm7=bytes([candidate.arm7[0]^1])+candidate.arm7[1:]
            elif kind=='item_archive':
                i=candidate.filenames.idOf('a/0/1/7');d=bytearray(candidate.files[i]);d[-1]^=1;candidate.files[i]=d
            else:
                arm=candidate.loadArm9();d=bytearray(arm.sections[3].data)
                off=0 if kind=='resident' else self.report['zero_ranges'][0][0]-build.BASE
                d[off]^=1;arm.sections[3].data=d;candidate.arm9=arm.save(compress=False)
            with self.subTest(kind=kind),self.assertRaises(ValueError):
                install.verify_rom(self.rom,candidate,self.raw,self.staged,self.payload,self.report)

    def test_isolated_install_and_atomic_failure_no_promotion(self):
        # Scope only output destination to owned test scratch; run real execute,
        # including actual compilation/assembly/install/reopen/hash rechecks.
        with scratch('installer-') as temp:
            dest=Path(temp);stage=dest/'success';stage.mkdir()
            with patch.object(install,'OUTPUT',dest):install.execute(INPUT,stage)
            receipt=json.loads((dest/'receipt.json').read_text())
            self.assertEqual(receipt['tool_mode'],build.tool_mode())
            self.assertEqual(receipt['status'].startswith(build.DEV_LABEL),build.dev_tools())
            promoted={name:sha256(dest/name) for name in ('candidate.nds','receipt.json')}
            for mode in ('late_verify','source_changed','bad_input'):
                stage=dest/mode;stage.mkdir()
                def fail(*a,**k):raise ValueError('injected final verification rejection')
                original_pins=install.source_tools
                def stale_pins():
                    sources,tools=original_pins();sources=copy.deepcopy(sources)
                    next(iter(sources.values()))['sha256']='0'*64
                    return sources,tools
                with patch.object(install,'OUTPUT',dest):
                    if mode=='late_verify':
                        with patch.object(install,'verify_rom',side_effect=fail),self.assertRaisesRegex(ValueError,'injected'):
                            install.execute(INPUT,stage)
                    elif mode=='source_changed':
                        with patch.object(install,'source_tools',side_effect=stale_pins),self.assertRaisesRegex(ValueError,'build input changed'):
                            install.execute(INPUT,stage)
                    else:
                        bad=dest/'bad.nds';bad.write_bytes(b'not a ROM')
                        with self.assertRaises(ValueError):install.execute(bad,stage)
                self.assertEqual(promoted,{name:sha256(dest/name) for name in promoted})
        command([__import__('sys').executable,SOURCE/'build.py','--input',INPUT],success=False)

    def test_assembled_abi_models(self):
        import items_abi_model
        self.assertEqual(items_abi_model.cases,1792)
        import compat_abi_model
        self.assertEqual(len(compat_abi_model.getters),5)

    def test_every_armips_guard_fails_atomically(self):
        # Every hook/edit independently corrupted in real staged input bytes;
        # actual armips must reject without partial section/stub writes.
        groups=[('native/options.asm',self.hooks[:9]),
                ('native/runtime.asm',json.loads((SOURCE/'native/runtime_hooks.json').read_text())['hooks']+json.loads((SOURCE/'native/runtime_hooks.json').read_text())['edits']),
                ('compatibility.asm',self.comp['edits']),
                ('native/items.asm',[dict(h,file=h['file'],address=h['address']) for h in json.loads((SOURCE/'native/items_hooks.json').read_text())])]
        commands=self.report['commands']
        for asm,records in groups:
            name=Path(asm).name
            cmd=next(c['argv'] for c in commands if c['argv'][0]==build.ARMIPS and any(Path(a).name==name for a in c['argv'][1:]))
            for record in records:
                for f,data in self.raw.items():(self.stage/f).write_bytes(data)
                # Stub files start as sentinel bytes; failed assembly must leave them.
                for span in self.report['stub_spans']:(self.stage/span['file']).write_bytes(bytes([0xA5])*(span['end']-span['start']))
                f=record['file'];data=bytearray(self.raw[f]);data[int(record['address'],16)-install.BASES[f]]^=1;(self.stage/f).write_bytes(data)
                names=list(self.raw)+[s['file'] for s in self.report['stub_spans']]
                before={f:(self.stage/f).read_bytes() for f in names}
                with self.subTest(source=asm,address=record['address']):
                    result=command(cmd,success=False);self.assertIn('guard failed',result.stdout+result.stderr)
                    self.assertEqual(before,{f:(self.stage/f).read_bytes() for f in names})
        # Restore cached assembled fixture for following tests/models.
        for f,data in self.staged.items():(self.stage/f).write_bytes(data)
        for span in self.report['stub_spans']:(self.stage/span['file']).write_bytes(self.payload[span['start']-build.BASE:span['end']-build.BASE])


class ToolModeTests(unittest.TestCase):
    """Release compares every tool with its pin; only DIFFICULTY_DEV_TOOLS=1 records instead."""
    def test_release_rejects_and_development_records_a_changed_tool(self):
        with scratch('tools-') as tmp:
            tool=Path(tmp)/'armips';tool.write_text('#!/bin/sh\necho "armips assembler local"\n');tool.chmod(0o755)
            pins={'armips':{'path':str(tool),'sha256':'0'*64,'version':'pinned'}}
            for value in ('','0','true','yes'):
                with self.subTest(value=value),patch.dict(os.environ,{build.DEV_ENV:value}):
                    self.assertEqual(build.tool_mode(),'release')
                    with self.assertRaisesRegex(ValueError,'tool guard armips'):install.check_tools(pins)
            with patch.dict(os.environ,{build.DEV_ENV:'1'}):
                row=install.check_tools(pins)['armips']
            self.assertEqual((row['sha256'],row['release_sha256'],row['matches_release_pin']),(sha256(tool),'0'*64,False))
            self.assertEqual((row['version'],row['release_version']),('armips assembler local','pinned'))
            tool.write_text('#!/bin/sh\n');tool.chmod(0o755)
            with patch.dict(os.environ,{build.DEV_ENV:'1'}),self.assertRaisesRegex(ValueError,'printed no version line'):
                install.check_tools(pins)
            pins['armips']['sha256']=sha256(tool)
            with patch.dict(os.environ,{build.DEV_ENV:''}):
                self.assertEqual(install.check_tools(pins)['armips'],
                                 dict(path=str(tool),bytes=tool.stat().st_size,sha256=sha256(tool),version='pinned'))

    def test_candidate_binding_takes_the_mode_from_the_receipt(self):
        from native_ui import candidate_binding
        self.assertEqual(build.OUTPUT.name=='integration-impl-dev',build.dev_tools())  # own folder per mode
        with scratch('binding-mode-') as tmp:
            path=Path(tmp)/'receipt.json'
            for env,mode in (('','development'),('1','release'),('1',None)):
                path.write_text(json.dumps({} if mode is None else {'tool_mode':mode}))
                with self.subTest(env=env,mode=mode),patch.dict(os.environ,{build.DEV_ENV:env}):
                    with self.assertRaisesRegex(ValueError,'tool mode'):candidate_binding(path)
            for env,mode in (('','release'),('',None),('1','development')):
                path.write_text(json.dumps({} if mode is None else {'tool_mode':mode}))
                with self.subTest(env=env,mode=mode),patch.dict(os.environ,{build.DEV_ENV:env}):
                    with self.assertRaises(KeyError):candidate_binding(path)  # past the mode check


class PublicationTests(unittest.TestCase):
    """Real shipping publication helper with text payloads, no ARM build/ROM."""
    def setUp(self):
        import publication
        self.pub = publication
        self.temp = scratch('publication-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root/'public'; self.output.mkdir()
        self.staged = self.root/'staged'; self.staged.mkdir()
        self.write_pair(self.output, b'OLD')
        self.write_pair(self.staged, b'NEW')
        self.old = self.pair()

    def write_pair(self, directory, data):
        (directory/'candidate.nds').write_bytes(data)
        (directory/'receipt.json').write_text(json.dumps({'output':{
            'path':str(self.output/'candidate.nds'), 'bytes':len(data),
            'sha256':hashlib.sha256(data).hexdigest()}}))

    def pair(self):
        return {name:(self.output/name).read_bytes() for name in self.pub.NAMES}

    def publish(self):
        # install.execute calls this imported helper, not a test-only analogue.
        self.assertIs(install.publish_pair, self.pub.publish_pair)
        return install.publish_pair(self.staged/'candidate.nds',self.staged/'receipt.json',self.output)

    def assert_old(self):
        self.assertEqual(self.old,self.pair())
        self.assertFalse((self.output/self.pub.JOURNAL).exists())

    def test_success_commits_coherent_new_pair_and_preserves_staged_inputs(self):
        self.publish()
        self.assertEqual(self.pair(),{n:(self.staged/n).read_bytes() for n in self.pub.NAMES})
        self.pub._verify_pair(self.output/'candidate.nds',self.output/'receipt.json')
        self.assertFalse(self.pub.recover_publication(self.output))

    def test_receipt_write_failure_leaves_previous_pair_untouched(self):
        original = Path.write_bytes
        def fail(path,data):
            if path.name=='receipt.json' and path.parent.parent==self.output:
                raise OSError('injected receipt write')
            return original(path,data)
        with patch.object(Path,'write_bytes',fail),self.assertRaisesRegex(self.pub.PublicationRejected,'receipt write'):
            self.publish()
        self.assert_old()

    def test_second_public_rename_failure_rolls_back_and_command_reports_rejection(self):
        original = os.replace; promotions=[]
        def fail(source,target):
            target=Path(target);source=Path(source)
            if target.parent==self.output and source.name in self.pub.NAMES:
                promotions.append(target.name)
                if target.name=='receipt.json':raise OSError('injected second rename')
            return original(source,target)
        with patch.object(self.pub.os,'replace',fail),patch.object(build,'OUTPUT',self.output), \
             patch.object(install,'execute',side_effect=lambda *_:self.publish()), \
             patch.object(sys,'argv',['build.py','--enable-difficulty','--input',str(self.staged/'candidate.nds')]), \
             patch('sys.stderr',new_callable=io.StringIO) as stderr:
            self.assertEqual(build.main(),1)
        self.assertEqual(promotions,['candidate.nds','receipt.json'])
        self.assertIn('REJECTED:',stderr.getvalue())
        self.assertIn('previous pair unchanged/restored',stderr.getvalue())
        self.assert_old()

    def test_first_rename_failure_restores_previous_pair(self):
        original=os.replace
        def fail(source,target):
            if Path(source).name=='candidate.nds' and Path(target)==self.output/'candidate.nds':
                raise OSError('injected first rename')
            return original(source,target)
        with patch.object(self.pub.os,'replace',fail),self.assertRaises(self.pub.PublicationRejected):self.publish()
        self.assert_old()

    def test_rollback_failure_reports_recovery_required_and_retry_restores_pair(self):
        original=os.replace
        def fail(source,target):
            source=Path(source)
            if source.name in ('receipt.json','restore-candidate.nds'):
                raise OSError('injected publication and recovery failure')
            return original(source,target)
        with patch.object(self.pub.os,'replace',fail),patch.object(build,'OUTPUT',self.output), \
             patch.object(install,'execute',side_effect=lambda *_:self.publish()), \
             patch.object(sys,'argv',['build.py','--enable-difficulty','--input',str(self.staged/'candidate.nds')]), \
             patch('sys.stderr',new_callable=io.StringIO) as stderr:
            self.assertEqual(build.main(),1)
        self.assertIn('RECOVERY REQUIRED:',stderr.getvalue())
        self.assertNotIn('REJECTED:',stderr.getvalue())
        self.assertTrue((self.output/self.pub.JOURNAL).exists())
        self.assertEqual((self.output/'candidate.nds').read_bytes(),b'NEW')
        self.assertEqual((self.output/'receipt.json').read_bytes(),self.old['receipt.json'])
        self.assertTrue(self.pub.recover_publication(self.output))
        self.assert_old()
        self.assertFalse(self.pub.recover_publication(self.output))

    def test_process_interruption_before_each_rename_and_commit_recovers_previous(self):
        class Interrupted(BaseException):pass  # bypass ordinary error rollback
        original_replace=os.replace;original_unlink=Path.unlink
        for point in ('candidate.nds','receipt.json','commit'):
            def replace(source,target):
                if Path(target)==self.output/point and Path(source).name==point:
                    raise Interrupted()
                return original_replace(source,target)
            def unlink(path,*args,**kwargs):
                if point=='commit' and path==self.output/self.pub.JOURNAL:raise Interrupted()
                return original_unlink(path,*args,**kwargs)
            with self.subTest(point=point):
                with patch.object(self.pub.os,'replace',replace),patch.object(Path,'unlink',unlink),self.assertRaises(Interrupted):
                    self.publish()
                self.assertTrue((self.output/self.pub.JOURNAL).exists())
                self.assertTrue(self.pub.recover_publication(self.output))
                self.assert_old()

    def test_interrupted_recovery_is_repeatable_and_next_publish_recovers_first(self):
        class Interrupted(BaseException):pass
        original=os.replace
        def crash(source,target):
            if Path(source).name=='receipt.json' and Path(target)==self.output/'receipt.json':raise Interrupted()
            return original(source,target)
        with patch.object(self.pub.os,'replace',crash),self.assertRaises(Interrupted):self.publish()
        def recovery_crash(source,target):
            if Path(source).name=='restore-receipt.json':raise Interrupted()
            return original(source,target)
        with patch.object(self.pub.os,'replace',recovery_crash),self.assertRaises(Interrupted):
            self.pub.recover_publication(self.output)
        self.assertTrue((self.output/self.pub.JOURNAL).exists())
        # Next invocation must recover even when its new input is invalid.
        (self.staged/'candidate.nds').write_bytes(b'INVALID')
        with self.assertRaisesRegex(ValueError,'mismatch'):self.publish()
        self.assert_old()

    def test_first_publication_failure_and_crash_restore_absence(self):
        for name in self.pub.NAMES:(self.output/name).unlink()
        class Interrupted(BaseException):pass
        original=os.replace
        for failure in (OSError,Interrupted):
            def fail(source,target):
                if Path(source).name=='receipt.json' and Path(target)==self.output/'receipt.json':raise failure('injected')
                return original(source,target)
            expected=self.pub.PublicationRejected if failure is OSError else Interrupted
            with self.subTest(failure=failure),patch.object(self.pub.os,'replace',fail),self.assertRaises(expected):self.publish()
            self.pub.recover_publication(self.output)
            self.assertFalse(any((self.output/n).exists() for n in self.pub.NAMES))
        self.publish()
        self.pub._verify_pair(self.output/'candidate.nds',self.output/'receipt.json')

    def test_existing_unjournaled_mismatch_is_rejected_without_changes(self):
        (self.output/'candidate.nds').write_bytes(b'CORRUPT')
        before=self.pair()
        with self.assertRaisesRegex(ValueError,'mismatch'):self.publish()
        self.assertEqual(self.pair(),before)
        (self.output/'receipt.json').unlink()
        with self.assertRaisesRegex(ValueError,'incomplete existing'):self.publish()
        self.assertEqual((self.output/'candidate.nds').read_bytes(),b'CORRUPT')

    def test_execute_recovers_before_input_validation(self):
        with patch.object(install,'OUTPUT',self.output),patch.object(install,'recover_publication') as recover:
            with self.assertRaises(ValueError):install.execute(self.staged/'candidate.nds',self.staged)
        recover.assert_called_once_with(self.output)

    def test_committed_publication_is_not_reported_rejected_on_stdout_failure(self):
        with patch.object(build,'OUTPUT',self.output), \
             patch.object(install,'execute',side_effect=lambda *_:(self.publish() or {'published':True})), \
             patch.object(sys,'argv',['build.py','--enable-difficulty','--input',str(self.staged/'candidate.nds')]), \
             patch('builtins.print',side_effect=BrokenPipeError):
            self.assertEqual(build.main(),0)
        self.pub._verify_pair(self.output/'candidate.nds',self.output/'receipt.json')
        self.assertEqual((self.output/'candidate.nds').read_bytes(),b'NEW')
