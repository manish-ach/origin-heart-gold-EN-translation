# sim/la: lookahead on the DS (research)

The Spanish AI work's measurement of DS-affordable lookahead: `la_run.py` runs the paired simulator measurements of
the lookahead variants (`sim cf la`: greedy playouts, truncated depth with a leaf, N playouts per action, an override
margin) by band of the level-80 pool; `ds/` compiles the turn engine and the lookahead for the DS and counts their
instructions in unicorn; `ds_cost.py` turns the counts into ideal DS time per decision. No tier runs them.

Ported from the Spanish workspace's `tools/sim/la/` (commit `dc8577c`, by luisvent, reused with their permission;
the Spanish `qa/simulator_feasibility.md` section 17 has the results). Changes: the test bench's imports and paths,
the simulator from `sim/simbuild.py` (`LA_SIM` overrides it), runs under `work/build/advanced-ai/runs/sim/la/`.

```
.venv/bin/python work/advanced-ai/testbench/sim/la/la_run.py sample --rates RATES -o SAMPLE
.venv/bin/python work/advanced-ai/testbench/sim/la/la_run.py run --sample SAMPLE --name NAME [--foe orig|adv] -- <sim cf la options>
.venv/bin/python work/advanced-ai/testbench/sim/la/la_run.py report NAME [NAME ...]
```
