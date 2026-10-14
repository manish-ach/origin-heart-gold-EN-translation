"""Batch 04: five isolated authors at once, one theme each (batch_04a-e.py): doubles, the trainer's bag items,
setup and its answers, recovery and attrition, utility moves."""
import importlib.util
import os

SCENARIOS = []
_here = os.path.dirname(os.path.abspath(__file__))
for _part in 'abcde':
    _spec = importlib.util.spec_from_file_location('ai_batch_04' + _part, os.path.join(_here, 'batch_04%s.py' % _part))
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    SCENARIOS += _mod.SCENARIOS
