#!/bin/sh
# The simulator gate on any pairs file (rc31_merge/gate.sh's legs with the pool as an argument).
#   sh tools/sim/gate.sh SIM PAIRS SEED REPS OUT [bot|h2h|both]
# SIM: a dual binary (Makefile.dual: adv = the candidate, advb = the base). PAIRS: pairs80, or counterfactual.py
# pairs --pool random after gen_simdata.py --extra-teams (the dual build must hold the same simdata). The bot leg pairs
# adv with advb on the same games against the original-AI bot; h2h plays REPS/2 a side order. Reading and foresight on
# the trainer side as the DS plays; extra env (AI_X, SIM_STEER_*, ...) passes through. One line per leg in OUT/gate.txt.
# Run from work_es. At most 3 simulator processes (simpool).
set -e
SIM=$1; P=$2; S=$3; R=$4; O=$5; MODE=${6:-both}
TAG=${TAG:-$(basename $P .txt)}
CF=".venv/bin/python tools/sim/counterfactual.py --sim $SIM"
PAIRED=qa/aivsai/rc31_plan/cens_inputs/paired.py
export SIM_READ_SIDE=1 SIM_FS=2 SIM_FS_SIDE=1
mkdir -p $O
if [ "$MODE" != h2h ]; then
  B=$O/orig_base_${TAG}_r${R}_s$S.txt
  [ -s $B ] || $CF rate --pairs $P --reps $R --seed $S --p0 orig --p1 advb --workers 3 --per-game -o $B
  $CF rate --pairs $P --reps $R --seed $S --p0 orig --p1 adv --workers 3 --per-game -o $O/orig_${TAG}_r${R}_s$S.txt
  echo "$(date +%T) $TAG s$S r$R vs bot: $(python3 $PAIRED $O/orig_${TAG}_r${R}_s$S.txt $B)" >> $O/gate.txt
fi
if [ "$MODE" != bot ]; then
  H=$(( R / 2 > 0 ? R / 2 : 1 ))
  $CF rate --pairs $P --reps $H --seed $S --p0 advb --p1 adv --workers 3 --per-game -o $O/h2h_${TAG}_s${S}_1.txt
  $CF rate --pairs $P --reps $H --seed $S --p0 adv --p1 advb --workers 3 --per-game -o $O/h2h_${TAG}_s${S}_2.txt
  echo "$(date +%T) $TAG s$S r$R h2h: $(python3 $PAIRED --h2h $O/h2h_${TAG}_s${S}_1.txt $O/h2h_${TAG}_s${S}_2.txt)" >> $O/gate.txt
fi
