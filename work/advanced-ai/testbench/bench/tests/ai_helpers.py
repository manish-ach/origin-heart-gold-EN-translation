"""Helpers shared by tests/ai_scenarios.py and the batch files in tests/ai_batches/ (see AUTHORING.md there)."""


def mon(species, moves, ability='Run Away', **kw):
    m = {'species': species, 'moves': moves, 'ability': ability}
    m.update(kw)
    return m


def S(sid, cat, desc, player, enemy, best, ok=(), bad=(), checks=(), items=(), double=False):
    return {'id': sid, 'cat': cat, 'desc': desc, 'player': player, 'enemy': enemy, 'items': list(items),
            'expect': {'best': list(best), 'ok': list(ok), 'bad': list(bad)}, 'checks': list(checks), 'double': double}


PLAIN = ['Tackle']
