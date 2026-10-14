"""Batch 06: one isolated author on round S2's self-play patterns (batch_06a-c.py): the move that also hurts the foe's
switch-in, Counter, Mirror Coat and Metal Burst, Shadow Tag, setup (Shell Smash, Calm Mind, Trick Room), and rules
(powder, Motor Drive, Endeavor, Sucker Punch, Glaive Rush, Skill Link)."""
import importlib.util
import os

SCENARIOS = []
_here = os.path.dirname(os.path.abspath(__file__))
for _part in 'abc':
    _spec = importlib.util.spec_from_file_location('ai_batch_06' + _part, os.path.join(_here, 'batch_06%s.py' % _part))
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    SCENARIOS += _mod.SCENARIOS
