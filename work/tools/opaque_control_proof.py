"""Narrow source-preserved FFFF argument proof; not caller or renderer coverage."""
import hashlib
import struct
from text_expansion_check import inspect_formatter_engine
from text_capacity_proofs import validate_ranges

REFS = frozenset(('a027/0763#66', 'a027/0763#80'))
PAYLOAD = (0xfffe, 0x0129, 2, 0, 0xffff, 0xffff)
PAYLOAD_HASH = hashlib.sha256(struct.pack('<6H', *PAYLOAD)).hexdigest()
RANGES = ('copy_bounded', 'command_skip', 'command_argument', 'string_data',
          'allocating_read', 'ondemand_read', 'eager_read', 'string_new')


def inspect_code(code, base=0x02000000):
    engine = inspect_formatter_engine(code, base)
    try:
        evidence = validate_ranges({'arm': (base, code)}, RANGES)
    except ValueError as exc:
        return {'status': 'incomplete', 'reason': str(exc)}
    return {'status': engine['status'], 'guards': evidence + engine['guards'],
            'scope': 'Full six-unit copy retains true EOS; formatter uses slot0 and skips two arguments. Actual caller capacities and rendering remain separate.'}


def eligible(ref, raw_hash, reference_hash, proof):
    return ref in REFS and raw_hash == reference_hash == PAYLOAD_HASH and proof.get('status') == 'passed'


def native_evidence_ok(cases, cleanup):
    wanted = {(ref, count) for ref in REFS for count in (0, 7, 31)}
    observed = [(c.get('ref'), c.get('slot_units')) for c in cases]
    return (len(observed) == len(set(observed)) and set(observed) == wanted and
            all(c.get('full_copied_payload') == list(PAYLOAD) and
                c.get('source_string_length') == 4 and c.get('source_capacity', 0) >= 6 and
                c.get('actual_units') == [0x012b] * c['slot_units'] and
                c.get('terminator') == 65535 and c.get('native_call_completed') is True
                for c in cases) and bool(cleanup.get('before')) and
            cleanup.get('before') == cleanup.get('after'))
