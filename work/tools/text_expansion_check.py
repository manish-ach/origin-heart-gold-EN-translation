"""Conservative u16 bounds for message expansion, never pixel estimates.

All lengths include one terminator. Stored length also includes storage padding.
Command bounds are caller-supplied proof obligations: no command-kind defaults
are inferred from informal names, rendering widths, or vanilla game behaviour.
"""
from __future__ import annotations

import text_binary_check
import hashlib


# Source and candidate match these independently reviewed ARM9 routines. These
# fingerprints establish engine identity, never which consumers call the engine.
FORMATTER_GUARDS = {
    'formatter': (0x0200C738, 0x0200C7CC, '0cc847de45932e94989249dff07a479deebc0320b2c70c3140cf09f0b4b075a5'),
    'is_substitution': (0x020202AC, 0x020202D8, 'ff1adf002ac90ae4f2a608d34a61cb89b95f4b881caf4c0f173f6d4cd48493f7'),
    'default_constructor': (0x0200BCA8, 0x0200BCB8, '8b03b54f7b13eaafabdb61eb711ad4cf44ee41d728cec6df980bc5053c922a97'),
    'parameterized_constructor': (0x0200BCB8, 0x0200BD40, '0e168d2852c3d82d5833f10cfbd0440f98fe95787037baea3eab504c9bae3e72'),
    'append_compressed': (0x0202703C, 0x020270B8, '23345c6dbe2c8a4c00239d051dfcddd2a4a1e0d6f696b71c5c29c148c0f06f85'),
}


def inspect_formatter_engine(data, base=0x02000000):
    """Guard reviewed native engine identity, without granting message bounds.

    The low byte of a placeholder is not a source-bank selector. The first
    argument indexes a runtime slot. Each consumer needs constructor, slot
    producer, decompression and destination-capacity proofs. In particular the
    default 32-unit slot allocation is not a bound on custom formatter objects
    or on the expanded size of compressed slot contents.
    """
    guards, gaps = [], []
    for name, (start, end, expected) in FORMATTER_GUARDS.items():
        offset = start - base
        digest = hashlib.sha256(data[offset:end-base]).hexdigest() if 0 <= offset < end-base <= len(data) else None
        matched = digest == expected
        guards.append(dict(name=name, start=start, end_exclusive=end, sha256=digest, matched=matched))
        if not matched:
            gaps.append(dict(code='formatter_engine_guard_unproven', routine=name))
    return dict(status='incomplete' if gaps else 'passed', scope='engine_identity_only',
                guards=guards, gaps=gaps, message_bounds={},
                semantics=None if gaps else dict(substitution_high_bytes=[1, 3, 4],
                    slot_argument=0, other_commands='retained_verbatim',
                    default_slots=8, default_slot_capacity_units=32,
                    custom_constructor=True, compressed_append_capacity_guard=False),
                required_proofs=['consumer_calls_this_engine', 'constructor_and_slot_count',
                                 'slot_producers_and_expanded_bounds', 'destination_capacity'])


def measure_expansion(units, bounds=None):
    """Measure a decrypted message record without mutating it.

    ``bounds`` maps full integer command IDs to dictionaries with ``evidence``
    (nonempty provenance), ``recursive=False`` and ``semantics``. ``replace``
    requires a nonnegative ``max_units`` excluding the replacement terminator;
    ``retain`` preserves the whole command record. Optional ``args`` restricts
    a bound to one exact argument list. The caller must verify the cited proof
    against the ROM/context; this function does not certify supplied evidence.
    An unresolved command makes expanded_units None, never a guessed maximum.
    """
    out = dict(status="passed", stored_units=len(units), decoded_units=None,
               expanded_units=None, errors=[], gaps=[], commands=[])
    if any(type(v) is not int or not 0 <= v <= 0xffff for v in units):
        out.update(status="failed", errors=[dict(code="invalid_u16")])
        return out
    record = dict(id=0)
    grammar = dict(status="passed", errors=[], gaps=[])
    text_binary_check._record(units, record, grammar)
    if grammar["errors"]:
        out.update(status="failed", errors=grammar["errors"])
        return out
    out["decoded_units"] = record["decoded_units"] + 1
    out["compressed"] = record["compressed"]
    if record["compressed"]:
        out["expanded_units"] = out["decoded_units"]
        return out
    total = out["decoded_units"]
    bounds = bounds or {}
    for command in record["commands"]:
        cid, args = command["command"], command["args"]
        spec = bounds.get(cid)
        reason = None
        if not isinstance(spec, dict):
            reason = "unknown_command_expansion"
        elif not isinstance(spec.get("evidence"), str) or not spec["evidence"].strip():
            reason = "missing_bound_evidence"
        elif spec.get("recursive") is not False:
            reason = "recursive_expansion_unresolved"
        elif "args" in spec and spec["args"] != args:
            reason = "command_arguments_unproven"
        elif spec.get("semantics") not in ("replace", "retain"):
            reason = "unknown_formatter_semantics"
        elif spec["semantics"] == "replace":
            maximum = spec.get("max_units")
            if type(maximum) is not int or maximum < 0:
                reason = "invalid_expansion_bound"
            else:
                total += maximum - (3 + len(args))
        out["commands"].append(dict(**command, evidence=spec.get("evidence")
                                    if isinstance(spec, dict) else None))
        if reason:
            out["gaps"].append(dict(code=reason, command=cid, unit=command["unit"], args=args))
    if out["gaps"]:
        out["status"] = "incomplete"
    else:
        out["expanded_units"] = total
    return out


def check_capacity(measurement, capacity):
    """Compare a proven expansion bound with a u16 capacity including EOS."""
    if type(capacity) is not int or capacity <= 0:
        raise ValueError("capacity must be a positive integer of u16 units")
    result = dict(status=measurement["status"], capacity_units=capacity,
                  required_units=measurement["expanded_units"], excess_units=None)
    if measurement["status"] == "passed":
        excess = measurement["expanded_units"] - capacity
        result.update(status="failed" if excess > 0 else "passed", excess_units=max(0, excess))
    return result


def measure_contract_expansion(units, contract):
    """Apply only a ROM-validated consumer's bounds, with exact slot arguments.

    This remains a per-consumer result; it must not become a global expansion
    bound for the entry. Compressed templates need a separate consumer proof.
    """
    proven = (contract.get('status') == 'passed' and
              contract.get('evidence_level') == 'rom_guarded')
    raw = contract.get('expansion_bounds', {}) if proven else {}
    bounds = {int(cid): spec for cid, spec in raw.items()}
    result = measure_expansion(units, bounds)
    if result.get('compressed'):
        result.update(status='incomplete', expanded_units=None)
        result['gaps'].append(dict(code='compressed_template_consumer_unproven'))
    return result
