# Writing AI bench scenarios

You write test positions for a trainer AI in a Pokémon HeartGold ROM hack (Origin HeartGold v4.0.3,
a Gen 5-style battle engine with Gen 9 species and moves). Each scenario is one decision: the
trainer's turn-1 action in a battle set up exactly as you describe, graded against your answer key.

The tests must be **genuine and hard**: positions where a strong human player knows the right play
and a weak AI goes wrong. You never look at the AI. You do not know how it decides, and you must not
find out, so the tests measure it instead of flattering it.

## What you must not read or run

- Do not open anything under `tools/ai/`, `tools/asm/aiselect.s`, `qa/aibench/`, `qa/ai_research/`,
  `qa/advanced_ai_plan.md`, `qa/advanced_ai_report.md`, `qa/advanced_ai_research.md`,
  `qa/decisions.tsv`, `qa/todo.md`.
- Do not run `tools/aibench.py` without `--check`, and never run `tools/aifuzz.py`. Both would show
  you how the AI plays.
- Do not edit anything outside `tests/ai_batches/batch_NN.py` (your batch) and `tests/ai_checks.py`.

## What you may use

- `tests/ai_helpers.py` (the `mon` and `S` helpers), `tests/ai_scenarios.py` (the original 114
  scenarios: the format, and situations you must not repeat), earlier `tests/ai_batches/batch_*.py`.
- `tools/aidata.py`, the ROM's own data. From `work_es/`:
  `.venv/bin/python tools/aidata.py Garchomp "Dragon Claw" Levitate` prints types, base stats and
  abilities, or a move's type, class, power, accuracy, priority and effect. In Python,
  `Data('rom/origin_es.nds')` gives `species()`, `move()`, `stats(name, level, evs)`,
  `effectiveness(move, view)` and `damage(move, attacker_view, defender_view)`.
- `docs/*.md` (generated from the hack's data: species, moves, abilities). They are large: grep for
  a heading and read that range.
- `tools/aicalc.py` (or `from aicalc import Calc`) to size a key's margins:
  `.venv/bin/python tools/aicalc.py --level 50 ATTACKER MOVE DEFENDER --a-ability ... --d-item ...`. It models items,
  abilities, weather, terrain and screens, with each factor labeled measured, official or hack (`--modifiers`).
  The key must still be proved by a check op. `qa/aivsai/ENGINE_FACTS.md` lists what this hack's engine really does.
- `tools/aibench.py`: read `mon_view`, `build_mon`, `run_check`, `grade` and `check` to see exactly
  what the bench builds and checks. Do not edit it.

**Items.** A few item names exist twice in the ROM (Rocky Helmet, Eviolite, Weakness Policy, Air Balloon).
`aidata` resolves the name to the id the battle engine actually handles: a Rocky Helmet test showed id 590
dealing a sixth to the attacker and id 324 doing nothing. Byte 2 of the item data (`a/0/1/7`) does not tell
whether an item works (590 has 0 there), so do not refuse an item for that reason. Soul Dew does nothing in
this ROM: a Latios with and without it dealt and took the same damage in the same battle. When a key
depends on an item or ability doing what the official games say, and you are not sure the hack implements
it, say so in your report so it can be measured.

**The hack changed official data.** Types, base stats and move power, type, class and accuracy
differ from the official games (for example, Blastoise is Water/Steel and Flame Wheel has 80 power).
Check every fact you rely on with `aidata.py`. Never trust memory.

## What the bench can set up

Each Pokémon is `mon(species, moves, ability='Run Away', **kw)`:
- `moves`: 1 to 4 move names, all at full PP.
- `ability`: any ability the ROM has. Without one it is Run Away, which does nothing here, so no
  hidden ability changes the answer by accident.
- `level=` (default 50), `item=`, `hp=` (a fraction like `0.35`, or an exact number like `40`),
  `status=` (`'slp'` with `sleep=` turns left, default 3; `'psn'`, `'tox'`, `'brn'`, `'frz'`,
  `'par'`), `evs={'atk': 252, 'spe': 252, ...}`. IVs are 31 and natures neutral.

A scenario is `S(id, category, description, player, enemy, best, ok=(), bad=(), checks=(),
items=(), double=False)`:
- **Singles.** `enemy[0]` is the AI's Pokémon on the field, `enemy[1:]` its bench. `player[0]` is
  the player's active Pokémon, `player[1:]` the player's bench. The AI sees the player's whole team.
- **Doubles** (`double=True`, one trainer). `enemy[0]` and `enemy[1]` are out, and only `enemy[0]`'s
  decision is graded (`enemy[1]` also acts). `player[0]` and `player[1]` are out. An answer
  `'Move>Species'` names the target, one of the player's two actives. A bare move matches any target.
- `items`: up to 4 items in the trainer's bag (for example `'Hyper Potion'`, `'Full Restore'`,
  `'Full Heal'`, `'X Attack'`).
- It is always **turn 1**. No stat stages, screens, hazards, Trick Room or move history. Weather
  and terrain only come from abilities on entry (Drizzle, Drought, Sand Stream, Snow Warning, and any
  terrain-setting ability the ROM has). Intimidate and other entry abilities trigger.
- The answer key judges the AI's action assuming the player then answers with its best move.

## The answer key

- `best`: the right action, or several that are equally right. A best answer scores 1.
- `ok`: reasonable but weaker. It scores 0.5.
- `bad`: a clear mistake that throws away the turn or the Pokémon. Examples: a move that cannot
  work, staying in to be knocked out for nothing when a safe switch exists, healing when a sure KO
  was available. It counts as a blunder. Do not list an action as bad unless it is clearly wrong.
- Anything you do not list scores 0 (a miss).
- Answers use the ROM's names: a move of `enemy[0]`, `'switch:Species'` (a bench member),
  `'item:Name'` (a bag item).

## Every key must be provable

`checks` are claims the bench verifies against the ROM before any run. Refs are `e0`, `e1`... (the
AI's Pokémon, `e0` active) and `p0`, `p1`... (the player's).

| Check | Claim |
|---|---|
| `('eff', 'e0', move, 'p0', 2.0)` | the move's effectiveness on p0 (0, 0.25, 0.5, 1, 2, 4), with type-immune abilities |
| `('ko', 'p0', move, 'e0')` | a sure KO: minimum damage × 0.9 ≥ current HP |
| `('noko', 'p0', move, 'e0')` | cannot KO: maximum damage × 1.1 < current HP |
| `('noko_at', 'p0', move, 'e0', 0.75)` | cannot KO from that HP fraction |
| `('beats', 'e0', m1, m2, 'p0')` | m1's minimum beats m2's maximum by 5% |
| `('faster', 'p0', 'e0')` | p0 outspeeds e0 (paralysis and Choice Scarf counted) |
| `('cls', move, 'physical')`, `('pri', move, 1)`, `('acc_lt', move, 100)`, `('type', 'e0', 'Steel')` | move class, priority, accuracy under, a type |

The built-in damage check models the Gen 5 formula, the same-type bonus, Adaptability, the type
chart, type-immune abilities (Levitate, Flash Fire, Water Absorb, Volt Absorb, ...) and burn (Guts
excepted). It does **not** model held items, other damage-changing abilities (Huge Power,
Technician, Thick Fat, Multiscale, Filter, Sturdy...), Focus Sash, multi-hit moves, weather, crits
or priority from abilities.

If a key depends on any of those, write a check op for it in `tests/ai_checks.py`
(`CHECKS['op'] = fn(d, views, c, ref)`, raising AssertionError when false). It must follow the
Gen 5 rule faithfully on top of the hack's data, with the rule stated in its docstring. Then use it
in your scenarios. Mechanics nobody can check by number (Sucker Punch failing against a status move,
Fake Out flinching only on turn 1, Dream Eater on an awake target) must be stated in the
description and must be unambiguous.

Design with margins, not knife edges. The data check approximates the engine, and the battle rolls
85-100% damage. Avoid keys that hinge on a single accuracy roll or crit unless the gap is large.

## What makes a good batch

- **Hard.** At least 60% of the scenarios combine two or more factors, for example a resisted STAB
  attack against a super effective weak move under a damage-changing ability, or a speed order
  flipped by Choice Scarf or paralysis next to a priority threat. Include traps where the obvious
  move is wrong.
- **Both directions.** Staying in when switching is wrong, and switching when staying in is wrong.
  Attacking when setup is wrong, and setup when attacking is wrong. Healing and not healing.
- **Unique.** No situation already in the bench, and no clone of one with cosmetic changes. Each
  scenario tests its own idea or its own combination. The bench rejects exact duplicates.
- **Real.** Plausible teams and levels, not contrived nonsense. Different species across the batch.
- **Categories.** Use the existing ones (immunity, ability, effective, damage, ko, priority, status,
  recovery, setup, switch, item, weather, rules, doubles) or a new lowercase word when none fits.
- **Ids.** `bNN_short_name`, unique, for example `b03_band_vs_multiscale`.

## Deliverable

1. `tests/ai_batches/batch_NN.py`:
   ```python
   from ai_helpers import PLAIN, S, mon  # noqa: F401

   SCENARIOS = [
       S('b01_...', 'switch', 'One sentence: the position and why the best answer is right',
         [mon(...)], [mon(...), mon(...)],
         best=[...], ok=[...], bad=[...], checks=[...]),
       ...
   ]
   ```
2. From `work_es/`, run `.venv/bin/python tools/aibench.py --check` until it prints
   `all N scenarios check out`.
3. Report back with:
   - the file and the count per category;
   - the new check ops, with the rule each one models;
   - any scenario whose key you are less than sure of, and why;
   - a statement that you read and ran none of the forbidden things.
