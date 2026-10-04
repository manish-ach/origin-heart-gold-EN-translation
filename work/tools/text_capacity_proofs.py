"""Reviewed native consumer dataflow fingerprints, not universal text safety.

Ranges cover allocations, bank selectors, field/argument transfers, native read
and formatter implementations. Changed code invalidates the entire affected
contract. See work/notes/text_buffer_verification.md for the derivations.
"""
import hashlib
import struct
from text_expansion_check import inspect_formatter_engine

GUARDS = {
    'field_manager_init': ('arm', 0x0203F64C, 0x0203F71E, '327618a0e4cba12ef56ee76dc1f292811ef5a592f3f6bcb82cecc31523c3397c'),
    'field_manager_getter': ('arm', 0x0204FAD4, 0x0204FADC, 'e777ca5564a66a27c64283fab4fee8810b682ce2b5847607a9baab2b9bb5d4d2'),
    'field_attr_accessor': ('arm', 0x0203FA2C, 0x0203FA58, '09bbadb64440da34743eef8ba652ed7e7329c2e9cbd595cda919455642f5759b'),
    'field_attr_members': ('arm', 0x0203F8F0, 0x0203FA2C, '99c80bb21a9f2d5c4813d50512f97132439ce55d30abfd9792a9675994f3fb46'),
    'field_context_create': ('arm', 0x0203F7B4, 0x0203F8F0, 'bb5d763bebe60eb2fdf38325d22c637adac7ecce5bd50ae2ba3c233f99d71d6c'),
    'field_context_init': ('arm', 0x0203F420, 0x0203F454, 'd22943ac871042957bdff29e561d94e1d62716215c9c0ec237abc8019067d18a'),
    'field_dispatch': ('arm', 0x0203F474, 0x0203F4E0, '79072acc344ed2abcbbd7071553f318e195deac8fa0b98faddf9f0d7132a5273'),
    'field_read_opcode': ('arm', 0x0203F534, 0x0203F54C, 'c5d49b18f38dbe417a8bbc6ac7e8d6503b0373a83a4524d0ce99aac92852d3fd'),
    'field_command_table_npc': ('arm', 0x020F79F0, 0x020F79F4, '3b93cbc9ee01de5a5f7a6d621fd9392c457f66a3e5edc944b87d0e0b0147fa92'),
    'field_map_getters': ('arm', 0x0203A6D4, 0x0203A754, 'f712c4ca7656cd69b2cd2ef556be520824ad0c0e2cf325bbe4558531ea568fbb'),
    'field_bank_getters': ('arm', 0x0203FA94, 0x0203FAB0, '5233232e27b87f9696328a348f259707127b4d76306e30d030fa610c25a71271'),
    'field_npc_handler': (1, 0x021EE288, 0x021EE2B4, 'd63453353fae4ef99b33df02c76a95286add2cddffc4c8a5e721c8ee3452b050'),
    'field_message_dispatch': (1, 0x021EE448, 0x021EE49C, '85215ec9bc437db374c8650b0886998ec52b7674435500514ead830832be4cf8'),
    'field_message_members': (1, 0x021EE58C, 0x021EE5D4, '6c08da4d6e548885d942f877062a2ba7086374ca3941b8bcc3ae013d4b8e6f51'),
    'field_window_prepare': (1, 0x021EE614, 0x021EE658, '8c9cb330e6a4b9ab9f705683fac4c8133fbddef715f0f66559c33fd21de373e5'),
    'field_message_read_format': (1, 0x021EE658, 0x021EE674, '3063e88526dd71acaca734fb7cf5403bcaa71a5c9a84f22185b5610da2fe0a96'),
    'field_map_187': ('arm', 0x020F494C, 0x020F4964, '907e7ea1432276c392f5c40f39c6879daf7567ff23864957016ace8887c4fc24'),
    'field_map_398': ('arm', 0x020F5D14, 0x020F5D2C, '59180c111df7d6ee616eb38e0fcff98361e536961e944fa98edfd89522a07675'),
    'field_map_43': ('arm', 0x020F3BCC, 0x020F3BE4, '6a369411b8207733d573c634c41e96e118ada37ea17fda57553a3b58776de6dc'),
    'certificate_init': (75, 0x021E4E14, 0x021E4EA4, '001165d6d1f2ff48a9451562ed9237fec2da12d6c64c149264c2d309a9286c1a'),
    'certificate_consumer': (75, 0x021E50E8, 0x021E5244, '09c7cc339732597e0089a869fb1e1c1026e6f535954fbf732081c7576753e131'),
    'eager_into': ('arm', 0x0200B700, 0x0200B7B0, '6a830f91adbe14c57418f85fa7fc3e3c13d3b6237d1b25ec95a88ed7cf732aed'),
    'message_constructor': ('arm', 0x0200BA98, 0x0200BAE4, ('5c06084ce7a5878e14fe04f1333447e00d95be7bfa81846330e5d69753ffc0d7', '5059ab6ce4be9964a9e76de3609077454c0d9cef59da6b6f0831e66aba920b4a')),
    'allocating_read': ('arm', 0x0200BB40, 0x0200BB6C, '85ca94426c04a3e028b59484052523979a84e1931cf4edc03e4a1e872dcdfc22'),
    'eager_read': ('arm', 0x0200B7B0, 0x0200B89C, '569fd7dcb0d99305eb4b07c4bc1805d8b8466f6d2f90e91fa06919dcae2bc29c'),
    'ondemand_read': ('arm', 0x0200B998, 0x0200BA74, 'bed662788e9bdf8d5b1604f229be2e43db35c5b274009fffc572f859dc28f2f7'),
    'command_skip': ('arm', 0x0202026C, 0x020202AC, '34c0b52e857694fbbf8bfe7a5c06a8e780aad03c9ff508fd77280cd37fcb18fa'),
    'command_argument': ('arm', 0x020202D8, 0x020202FC, 'a48f60269bdce6a404a0f319c73762e5b61d06cdbed1f59dfba94571b66ce7ec'),
    'string_data': ('arm', 0x02026F58, 0x02026F78, 'cb5a0f92e7080189541254998105266e1149a4ca178cf34658913ec63b58455a'),
    'string_new': ('arm', 0x02026864, 0x02026890, '7f4698480a0ea155b51aba23f3e469490e07f15ede986259421294b722929d6d'),
    'read_into': ('arm', 0x0200BB0C, 0x0200BB40, '4c7f1a931d1b91a96f1466e23a0256935edf23fe195f3650d78bec202840a423'),
    'ondemand_into': ('arm', 0x0200B89C, 0x0200B964, '2d1c356ecdc6edadd15b3c9d8d4d05f2dcf5f6688c8b6049ef7a1b103fa802e5'),
    'copy_bounded': ('arm', 0x02026EB8, 0x02026F1C, '1e3205281e541f0f6eff317849f404bffdd6e8b9e3efebbef523231750a8c218'),
    'move_init': (65, 0x021E4F3C, 0x021E4F96, 'dff4efc82b46f9079c3d33b974b1e5af3e9122e86b7fca65e7cdb2d08d5a14a8'),
    'move_consumer': (65, 0x021E594C, 0x021E5AA8, 'd38405ebce2737df2ad2ee3a3b75105b47a8b7926649a240e8f8169e806b8dd7'),
    'dex_selector': (5, 0x021E4A14, 0x021E4A68, '458bd3e78dededed98e9bef1364e68c77402db2c013d0fc14038474b8ddfd7ff'),
    'dex_receiver': (5, 0x021E4A68, 0x021E4AA8, 'e15946d69b24c976c90a1cfa3e60551f18301abf724959374e2748c9e8035e3b'),
    'move_numeric': (65, 0x021E5350, 0x021E5398, '700b13bdda9613d9a573d1fba0c188390b50d3345bc66fbe2184a56c185b22e4'),
    'numeric_slot': ('arm', 0x0200BF1C, 0x0200BF40, '84642617607eaa1031618495ae3d3e13dc982ef201fb9764be7cff98bda97a80'),
    'numeric_convert': ('arm', 0x02026974, 0x02026AA8, '764b0bd6bbed8e06bf1413f2efee106cd2e17ac7a82e271e59f3936dda059acb'),
    'numeric_divide': ('arm', 0x020F1424, 0x020F1608, '3b0403581ea03e86bdfc0cde00ea2ca13f522291aec399b93ecdf2fef57944eb'),
    'numeric_powers': ('arm', 0x020F2F90, 0x020F2F9C, '599482e5f89f66b0e40412404029d9d6723d398bb7b844e20cec1c936d0abd24'),
    'slot_copy': ('arm', 0x0200BD98, 0x0200BDDC, '49d807351fdc07126f8a0df64f6c6e669e3db558c862482e13ab2ef4ea3c722d'),
    'string_copy': ('arm', 0x020268E4, 0x02026928, 'b20372418803080db52f3489215407601f6889ad3c11fc1ac5006ebedda71e8a'),
    'string_reset': ('arm', 0x020268BC, 0x020268E4, '55353dde1e3dabe6fce2487533b3421aed7ff5504dcd5b811c72b076a48622c0'),
    'string_append': ('arm', 0x02026FDC, 0x02027024, '0bf3f584f4b05617c6a4768134fbbfc4f5cbb429d2e1ad146a831199aa36a3bf'),
    'string_concat': ('arm', 0x02026F78, 0x02026FDC, '9e1ea98234683113a53bae95f1d67507681d2b5dbfa95373637ef461ff57d985'),
}

DIRECT = ('eager_into', 'message_constructor', 'string_new', 'read_into', 'ondemand_into', 'copy_bounded')
NUMERIC = ('message_constructor', 'allocating_read', 'eager_read', 'ondemand_read',
           'command_skip', 'command_argument', 'string_data', 'move_init', 'move_consumer', 'move_numeric', 'numeric_slot',
           'numeric_convert', 'numeric_divide', 'numeric_powers', 'slot_copy',
           'string_copy', 'string_reset', 'string_append', 'string_concat', 'string_new')


def validate_ranges(sections, names):
    evidence = []
    for name in names:
        section, start, end, expected = GUARDS[name]
        if section not in sections:
            raise ValueError(f'Missing consumer section {section}')
        base, data = sections[section]
        lo, hi = start - base, end - base
        actual = hashlib.sha256(data[lo:hi]).hexdigest() if 0 <= lo < hi <= len(data) else None
        if actual not in (expected if isinstance(expected, tuple) else (expected,)):
            raise ValueError(f'Consumer dataflow guard changed: {name} at {start:08X}')
        evidence.append(dict(name=name, section=section, start=start, end_exclusive=end, sha256=actual))
    return evidence


def inspect_proofs(arm, overlays):
    sections = {'arm': (arm.ramAddress, bytes(arm.data))}
    sections.update({k: (v.ramAddress, bytes(v.data)) for k, v in overlays.items()})
    specs = [
        dict(id='certificate-stored-text', bank='a027/0004', ids=list(range(6)),
             stage='stored', capacity_units=512,
             guards=DIRECT + ('certificate_init', 'certificate_consumer'),
             evidence='Overlay75: bank4 handle at object+0x38; two String_New(512) destinations receive IDs0..5. Header formatting has separate, unproven expansion bounds; this contract covers stored reads only.'),
        dict(id='move-description-relearner', bank='a027/0738', ids=None,
             stage='stored', capacity_units=256,
             guards=DIRECT + ('move_init', 'move_consumer'),
             evidence='Overlay65: String_New(256) stored at object+0x100; bank738 read into same field; native bounded copy. All IDs checked conservatively.'),
        dict(id='pokedex-description-reader', bank='a027/0791', ids=None,
             stage='stored', capacity_units=256,
             guards=DIRECT + ('dex_selector', 'dex_receiver'),
             evidence='Overlay5: bank791 selected then helper021E4A68 allocates String_New(256), forwards that exact pointer to ReadMsgDataIntoString.'),
        dict(id='move-relearner-numeric-expansion', bank='a027/0736', ids=[29, 30],
             stage='expanded', capacity_units=256, guards=NUMERIC,
             expansion_bounds={'308': dict(semantics='replace', max_units=4, args=[0],
                 recursive=False, evidence='Guarded overlay65 numeric producer: three decimal positions plus optional sign; default formatter slot0, 32-unit scratch/slot; 256-unit receiving field.')},
             evidence='Overlay65 init, callers and numeric helper prove bank736 IDs29/30, slot0, three numeric positions plus optional sign, and 256-unit formatter destination. Other substitutions remain unproven.'),
    ]
    for spec in specs:
        names = spec.pop('guards')
        spec.update(evidence_level='rom_guarded', status='passed', includes_terminator=True,
                    exhaustive_consumers=False,
                    overflow_behavior='assert_and_skip_copy' if spec['stage']=='stored' else 'must_fit_before_formatter')
        try:
            spec['code_evidence'] = validate_ranges(sections, names)
            if spec['stage'] == 'expanded':
                engine = inspect_formatter_engine(arm.data, arm.ramAddress)
                if engine['status'] != 'passed':
                    raise ValueError('Formatter engine identity unproven')
                spec['formatter_evidence'] = engine['guards']
        except ValueError as exc:
            spec.update(status='incomplete', evidence_level='unverified', reason=str(exc))
    return specs


FIELD_COMMON = DIRECT + ('field_map_getters', 'field_manager_init', 'field_manager_getter', 'field_attr_accessor', 'field_attr_members', 'field_context_create', 'field_context_init', 'field_dispatch', 'field_read_opcode', 'field_command_table_npc', 'field_bank_getters', 'field_npc_handler', 'field_message_dispatch', 'field_message_members', 'field_window_prepare', 'field_message_read_format')
FIELD_BINDINGS = [{'bank': 65, 'index': 60, 'script': 31, 'zone': 187, 'offsets': [2026, 4464, 4504], 'sha256': '66e639727d15c36c32e2ec6a8b9280b39aa7165def7381893c2d826cbb430f1c'}, {'bank': 525, 'index': 57, 'script': 829, 'zone': 398, 'offsets': [3353], 'sha256': 'abcf06254b06dea67e193eb4758d12291b508eb505b1434d28ac88cb98f8e214'}, {'bank': 389, 'index': 56, 'script': 249, 'zone': 43, 'offsets': [2587], 'sha256': 'dd86e26cb0ae01aee39ee103a86344d01079f63ebfa585712a0a6ff2c742ef0d'}]


def inspect_field_proofs(arm, overlays, scripts):
    """Three reviewed original NPCMsg bindings; never a universal dialogue bound.

    Full original script hashes plus exact opcode operands and native map rows
    bind these IDs to the ordinary field consumer. A changed script is unresolved
    until its control flow is reviewed, even if the old bytes occur elsewhere.
    """
    sections = {'arm': (arm.ramAddress, bytes(arm.data))}
    sections.update({k: (v.ramAddress, bytes(v.data)) for k, v in overlays.items()})
    contracts = []
    for binding in FIELD_BINDINGS:
        bank, index, script, zone = (binding[k] for k in ('bank', 'index', 'script', 'zone'))
        c = dict(id=f'field-npc-message-{bank:04d}-{index}', bank=f'a027/{bank:04d}',
                 ids=[index], stage='stored', capacity_units=1024,
                 includes_terminator=True, exhaustive_consumers=False,
                 status='passed', evidence_level='rom_guarded',
                 overflow_behavior='assert_and_skip_copy',
                 evidence='Original NPCMsg script/map binding -> overlay1 native reader -> manager+0x4C String_New(1024). Expanded text in manager+0x48 remains a separate proof obligation.',
                 script_binding=dict(binding))
        try:
            c['code_evidence'] = validate_ranges(sections, FIELD_COMMON + (f'field_map_{zone}',))
            raw = bytes(scripts[script])
            if hashlib.sha256(raw).hexdigest() != binding['sha256']:
                raise ValueError('Original NPCMsg script identity changed')
            for offset in binding['offsets']:
                if raw[offset:offset+3] != struct.pack('<HB',45,index):
                    raise ValueError('Original NPCMsg opcode or message ID changed')
            header = 0x020F37C4 + 24*zone - arm.ramAddress
            if (struct.unpack_from('<H',arm.data,header+6)[0],
                struct.unpack_from('<H',arm.data,header+10)[0]) != (script,bank):
                raise ValueError('Original NPCMsg map script/bank binding changed')
        except (ValueError, IndexError, KeyError, TypeError) as exc:
            c.update(status='incomplete', evidence_level='unverified', reason=str(exc))
        contracts.append(c)
    return contracts
