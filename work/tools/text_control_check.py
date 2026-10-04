#!/usr/bin/env python3
"""Source-relative message control contracts, without encoding or changing text.

Only newline/scroll/clear are translation layout exceptions. Substitutions may
move while preserving effective formatting state and non-format barriers. Engine arity is NOT
inferred from a source example: contracts need argc and an evidence label.
No command argument is treated as a message ID without an explicit reference
contract. This module does not prove native handlers or script reachability.
"""
from collections import Counter

LAYOUT = {0xE000, 0x25BC, 0x25BD}
SUBSTITUTION_FAMILIES = {0x01, 0x03, 0x04, 0x34}


def _parse(units):
    errors, commands = [], []
    if not isinstance(units, (list, tuple)) or any(type(x) is not int or not 0 <= x <= 65535 for x in units):
        return [], ['invalid_u16_sequence'], False
    if units and units[0] == 0xF100:
        # Compression contains 9-bit glyphs only. Verify termination/padding;
        # never interpret packed storage words as command markers.
        acc = bits = 0
        for i, word in enumerate(units[1:], 1):
            if word & 0x8000 and word != 65535:
                return [], ['compressed_high_bit'], False
            acc |= (word & 0x7fff) << bits
            bits += 15
            while bits >= 9:
                glyph = acc & 511
                acc >>= 9
                bits -= 9
                if glyph == 511:
                    if acc != (1 << bits) - 1 or any(v != 65535 for v in units[i+1:]):
                        errors.append('compressed_trailing_payload')
                    if units[-1] != 65535:
                        errors.append('missing_storage_terminator')
                    return [], errors, True
        return [], ['unterminated_compression'], False
    i = 0
    while i < len(units):
        code = units[i]
        if code == 65535:
            if any(v != 65535 for v in units[i+1:]):
                errors.append('trailing_payload')
            return commands, errors, True
        if code == 0xF100:
            errors.append('misplaced_compression_header')
        if code == 65534:
            if i + 3 > len(units):
                return commands, errors + ['truncated_command_header'], False
            opcode, argc = units[i+1:i+3]
            if argc > len(units) - i - 3:
                return commands, errors + ['command_arguments_overrun'], False
            commands.append((opcode, tuple(units[i+3:i+3+argc])))
            i += 3 + argc
        else:
            i += 1
    return commands, errors + ['missing_terminator'], False


def _signature(commands):
    """Track effective formatting, allowing movement across restored colors.

    COLOR 0 and SIZE 100 are the normal defaults used by existing QA's text
    renderer model. Other stateful commands are barriers, never guessed resets.
    """
    variables, stateful, state, barrier = Counter(), [], {0xFF00: 0, 0xFF01: 100}, 0
    for opcode, args in commands:
        if opcode >> 8 in SUBSTITUTION_FAMILIES:
            variables[(opcode, args, tuple(sorted(state.items())), barrier)] += 1
        else:
            stateful.append((opcode, args))
            if opcode in state and len(args) == 1:
                state[opcode] = args[0]
            else:
                barrier += 1
    return variables, stateful


def check_controls(source_units, candidate_units, ref, contracts=None):
    """Return failures, source baseline defects, and explicit semantic gaps.

    contracts maps integer opcode to {argc: int, evidence: str, references?:
    [{arg: int, count: int, evidence: str}]}. Reference count describes a proven
    zero-based inventory. An absent contract is incomplete, not guessed.
    """
    contracts = contracts or {}
    source, source_errors, _ = _parse(source_units)
    candidate, candidate_errors, _ = _parse(candidate_units)
    out = dict(ref=ref, status='passed', findings=[], gaps=[], baseline_findings=[],
               counts=dict(source_commands=len(source), candidate_commands=len(candidate)))
    for error in source_errors:
        out['baseline_findings'].append(dict(code=error, side='source'))
    for error in candidate_errors:
        if source_units == candidate_units and error in source_errors:
            out['gaps'].append(dict(code='unchanged_source_structure', detail=error))
        else:
            out['findings'].append(dict(code=error, side='candidate'))
    if source_errors:
        out['gaps'].append(dict(code='source_contract_unavailable'))
    if not source_errors and not candidate_errors:
        ss, sc = _signature(source)
        cs, cc = _signature(candidate)
        if sc != cc:
            out['findings'].append(dict(code='stateful_command_sequence_changed', source=sc, candidate=cc))
        if Counter((op, args) for op, args in source if op >> 8 in SUBSTITUTION_FAMILIES) != Counter((op, args) for op, args in candidate if op >> 8 in SUBSTITUTION_FAMILIES):
            out['findings'].append(dict(code='substitution_contract_changed',
                                       source=source, candidate=candidate))
        elif sc == cc and ss != cs:
            out['findings'].append(dict(code='substitution_crossed_control_boundary'))
    for opcode in sorted({op for op, _ in source + candidate}):
        contract = contracts.get(opcode)
        if not isinstance(contract, dict) or type(contract.get('argc')) is not int or contract['argc'] < 0 or not contract.get('evidence'):
            out['gaps'].append(dict(code='command_arity_unproven', opcode=opcode))
            continue
        for side, commands in [('source', source), ('candidate', candidate)]:
            for op, args in commands:
                if op != opcode:
                    continue
                issues = []
                if len(args) != contract['argc']:
                    issues.append(dict(code='command_arity_mismatch', opcode=op,
                                       expected=contract['argc'], actual=len(args)))
                for reference in contract.get('references', []):
                    index, count = reference.get('arg'), reference.get('count')
                    if type(index) is not int or type(count) is not int or index < 0 or count < 0 or not reference.get('evidence'):
                        out['gaps'].append(dict(code='invalid_reference_contract', opcode=op))
                    elif index >= len(args) or not 0 <= args[index] < count:
                        issues.append(dict(code='reference_out_of_range', opcode=op, arg=index, count=count))
                for issue in issues:
                    issue['side'] = side
                    if side == 'source':
                        out['baseline_findings'].append(issue)
                    elif (op, args) in source:
                        out['gaps'].append(dict(code='unchanged_source_command_defect', detail=issue))
                    else:
                        out['findings'].append(issue)
    if out['findings']:
        out['status'] = 'failed'
    elif out['gaps'] or out['baseline_findings']:
        out['status'] = 'incomplete'
    return out


def summarize(results):
    """Retain every string result; no sampled coverage or successful omission."""
    results = list(results)
    counts = Counter(r['status'] for r in results)
    return dict(status='failed' if counts['failed'] else 'incomplete' if counts['incomplete'] or not results else 'passed',
                counts=dict(strings=len(results), **counts), records=results)
