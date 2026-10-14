"""Batch 05: one isolated author on round S1's self-play patterns (batch_05a-c.py): covering the foe's switch-in,
choosing switch-ins, the doomed active, the only answer, faster sleep moves, absorbing abilities, rules."""
import importlib.util
import os

SCENARIOS = []
_here = os.path.dirname(os.path.abspath(__file__))
for _part in 'abc':
    _spec = importlib.util.spec_from_file_location('ai_batch_05' + _part, os.path.join(_here, 'batch_05%s.py' % _part))
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    SCENARIOS += _mod.SCENARIOS
