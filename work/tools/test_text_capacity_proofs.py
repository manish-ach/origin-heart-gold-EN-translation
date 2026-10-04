"""Boundary checks and native dataflow mutation counterexamples."""
from pathlib import Path
from types import SimpleNamespace
import unittest

import msgtool
import text_capacity_proofs as p
from text_consumer_check import check_entries
from text_expansion_check import measure_contract_expansion
from text_safety_check import apply_capacities
from text_expansion_check import measure_expansion

ROM = Path(__file__).resolve().parents[1] / 'rom/origin_v4.0.3_cn.nds'


class BoundaryTests(unittest.TestCase):
    def contract(self, stage='stored'):
        return dict(id='boundary', bank='a027/0000', ids=None, stage=stage,
                    capacity_units=256, status='passed', evidence_level='rom_guarded',
                    expansion_bounds={'308': dict(semantics='replace', max_units=4,
                        args=[0], recursive=False, evidence='test numeric producer')})

    def test_description_exact_then_one_over(self):
        for count, status in [(255, 'passed'), (256, 'failed')]:
            self.assertEqual(check_entries([[1]*count+[65535]], self.contract())[0]['status'], status)

    def test_expansion_exact_then_one_over_in_both_ledgers(self):
        c = self.contract('expanded')
        for count, status in [(251, 'passed'), (252, 'failed')]:
            units = [1]*count+[65534, 308, 1, 0, 65535]
            self.assertEqual(check_entries([units], c)[0]['status'], status)
            row = apply_capacities(units, measure_expansion(units), [c], c['bank'], 0)[0]
            self.assertEqual(row['status'], status)
            self.assertEqual(row['measured_units'], count+5)

    def test_substitution_has_exact_slot_requirement(self):
        r = measure_contract_expansion([65534, 308, 1, 1, 65535], self.contract('expanded'))
        self.assertEqual(r['status'], 'incomplete')
        self.assertIsNone(r['expanded_units'])

    def test_unknown_producer_cannot_borrow_numeric_bound(self):
        r = measure_contract_expansion([65534, 259, 1, 0, 65535], self.contract('expanded'))
        self.assertEqual(r['status'], 'incomplete')

    def test_bad_guard_does_not_supply_bounds(self):
        c = self.contract('expanded'); c['status'] = 'incomplete'
        self.assertIsNone(measure_contract_expansion([65534, 308, 1, 0, 65535], c)['expanded_units'])

    def test_compressed_template_not_certified_by_plain_template_path(self):
        r = measure_contract_expansion(msgtool.compress_codes([1]*10), self.contract('expanded'))
        self.assertEqual(r['status'], 'incomplete')

    def test_multiple_numeric_references_each_counted(self):
        units = [65534, 308, 1, 0]*3+[65535]
        self.assertEqual(measure_contract_expansion(units, self.contract('expanded'))['expanded_units'], 13)

    def test_serialized_contract_keeps_bound(self):
        import json
        c = json.loads(json.dumps(self.contract('expanded')))
        self.assertEqual(measure_contract_expansion([65534, 308, 1, 0, 65535], c)['expanded_units'], 5)


@unittest.skipUnless(ROM.exists(), 'Local Chinese ROM required for native guard mutation checks')
class NativeMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ndspy.rom
        r = ndspy.rom.NintendoDSRom.fromFile(str(ROM))
        cls.arm = r.loadArm9().sections[0]
        cls.overlays = r.loadArm9Overlays()

    def inspect_mutation(self, section, address):
        arm = SimpleNamespace(ramAddress=self.arm.ramAddress, data=bytearray(self.arm.data))
        overlays = {k: SimpleNamespace(ramAddress=v.ramAddress, data=bytearray(v.data))
                    for k, v in self.overlays.items()}
        target = arm if section == 'arm' else overlays[section]
        target.data[address-target.ramAddress] ^= 1
        return {c['id']: c for c in p.inspect_proofs(arm, overlays)}

    def test_original_native_paths_pass(self):
        self.assertTrue(all(c['status'] == 'passed' for c in p.inspect_proofs(self.arm, self.overlays)))

    def test_certificate_bank_allocations_destinations_and_ids_are_guarded(self):
        for address in [0x021E4E38, 0x021E4E3E, 0x021E50EE, 0x021E5116,
                        0x021E513E, 0x021E51B6, 0x021E51BA, 0x021E51FC]:
            with self.subTest(address=hex(address)):
                self.assertEqual(self.inspect_mutation(75, address)
                                 ['certificate-stored-text']['status'], 'incomplete')

    def test_certificate_capacity_boundary_and_scope(self):
        contract = next(c for c in p.inspect_proofs(self.arm, self.overlays)
                        if c['id'] == 'certificate-stored-text')
        self.assertEqual(contract['stage'], 'stored')
        self.assertEqual(contract['ids'], list(range(6)))
        for count, status in [(511, 'passed'), (512, 'failed')]:
            checks = check_entries([[1] * count + [65535]] * 6, contract)
            self.assertEqual(len(checks), 6)
            self.assertTrue(all(c['status'] == status for c in checks))

    def test_allocator_immediate_field_read_and_call_target_mutations(self):
        for address in [0x021E4F60, 0x021E4F6E, 0x021E5A1A, 0x021E5A20, 0x021E5AA4]:
            with self.subTest(address=hex(address)):
                c = self.inspect_mutation(65, address)['move-description-relearner']
                self.assertEqual(c['status'], 'incomplete')
                self.assertEqual(c['evidence_level'], 'unverified')

    def test_dex_selector_allocation_and_pointer_transfer_mutations(self):
        for address in [0x021E4A60, 0x021E4A80, 0x021E4A92, 0x021E4A94]:
            with self.subTest(address=hex(address)):
                self.assertEqual(self.inspect_mutation(5, address)['pokedex-description-reader']['status'], 'incomplete')

    def test_numeric_bound_guard_mutations(self):
        for section, address in [(65, 0x021E59AE), (65, 0x021E5368), (65, 0x021E5386),
                                 ('arm', 0x020F2F98), ('arm', 0x020269E4),
                                 ('arm', 0x0200C782), ('arm', 0x0200BCAE),
                                 ('arm', 0x0200BB62), ('arm', 0x0200BA9A),
                                 ('arm', 0x020202D8)]:
            with self.subTest(section=section, address=hex(address)):
                self.assertEqual(self.inspect_mutation(section, address)['move-relearner-numeric-expansion']['status'], 'incomplete')

    def test_copy_guard_mutation_invalidates_direct_capacity_proofs(self):
        for address in [0x02026ED8, 0x0200B700]:
            contracts = self.inspect_mutation('arm', address)
            for name in ['move-description-relearner', 'pokedex-description-reader']:
                self.assertEqual(contracts[name]['status'], 'incomplete')

    def test_missing_overlay_does_not_grant_proof(self):
        results = p.inspect_proofs(self.arm, {})
        self.assertTrue(all(c['status'] == 'incomplete' for c in results))

@unittest.skipUnless(ROM.exists(), 'Local Chinese ROM required for field binding mutation checks')
class FieldNpcProofTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import ndspy.rom
        r = ndspy.rom.NintendoDSRom.fromFile(str(ROM))
        cls.arm = r.loadArm9().sections[0]
        cls.overlays = r.loadArm9Overlays()
        cls.scripts = msgtool.Narc.parse(r.getFileByName('a/0/1/2')).files

    def test_source_and_candidate_proofs_and_exact_capacity(self):
        contracts = p.inspect_field_proofs(self.arm, self.overlays, self.scripts)
        self.assertEqual(len(contracts), 3)
        self.assertTrue(all(c['status'] == 'passed' for c in contracts))
        for c in contracts:
            self.assertEqual(c['stage'], 'stored')
            self.assertFalse(c['exhaustive_consumers'])
            for count, status in [(1023, 'passed'), (1024, 'failed')]:
                strings = [[65535]] * (c['ids'][0] + 1)
                strings[c['ids'][0]] = [1] * count + [65535]
                self.assertEqual(check_entries(strings, c)[0]['status'], status)
        candidate = ROM.parents[1] / 'build/approved-warning-followup/candidate/origin_hg_v4.0.3_en_wip.nds'
        if candidate.exists():
            import ndspy.rom
            r = ndspy.rom.NintendoDSRom.fromFile(str(candidate))
            actual = p.inspect_field_proofs(r.loadArm9().sections[0],r.loadArm9Overlays(),msgtool.Narc.parse(r.getFileByName('a/0/1/2')).files)
            self.assertTrue(all(c['status'] == 'passed' for c in actual))

    def test_field_code_mutations_fail_closed(self):
        for section, address in [('arm',0x0203F686),('arm',0x0203F692),
                ('arm',0x0203F69A),('arm',0x0203F9BA),('arm',0x0203FA4E),
                ('arm',0x020F79F0),('arm',0x0203F4D2),('arm',0x0203F8EC),
                ('arm',0x0203A738),('arm',0x0203A750),('arm',0x0203FAAC),
                (1,0x021EE29A),(1,0x021EE29C),(1,0x021EE472),
                (1,0x021EE59A),(1,0x021EE5A8),(1,0x021EE660),(1,0x021EE662)]:
            with self.subTest(section=section,address=hex(address)):
                arm=SimpleNamespace(ramAddress=self.arm.ramAddress,data=bytearray(self.arm.data))
                overlays=dict(self.overlays)
                if section=='arm':target=arm
                else:
                    old=overlays[section]
                    target=SimpleNamespace(ramAddress=old.ramAddress,data=bytearray(old.data));overlays[section]=target
                target.data[address-target.ramAddress]^=1
                self.assertTrue(all(c['status']=='incomplete' for c in p.inspect_field_proofs(arm,overlays,self.scripts)))

    def test_script_opcode_id_hash_and_map_binding_fail_closed(self):
        for binding in p.FIELD_BINDINGS:
            for offset in [0,binding['offsets'][0],binding['offsets'][0]+2]:
                scripts=list(self.scripts);raw=bytearray(scripts[binding['script']]);raw[offset]^=1;scripts[binding['script']]=bytes(raw)
                c=next(c for c in p.inspect_field_proofs(self.arm,self.overlays,scripts) if c['bank']==f"a027/{binding['bank']:04d}")
                self.assertEqual(c['status'],'incomplete')
            for field in (6,10):
                arm=SimpleNamespace(ramAddress=self.arm.ramAddress,data=bytearray(self.arm.data))
                offset=0x020F37C4+24*binding['zone']+field-arm.ramAddress;arm.data[offset]^=1
                c=next(c for c in p.inspect_field_proofs(arm,self.overlays,self.scripts) if c['bank']==f"a027/{binding['bank']:04d}")
                self.assertEqual(c['status'],'incomplete')
        self.assertTrue(all(c['status']=='incomplete' for c in p.inspect_field_proofs(self.arm,{},self.scripts)))
        self.assertTrue(all(c['status']=='incomplete' for c in p.inspect_field_proofs(self.arm,self.overlays,[])))
