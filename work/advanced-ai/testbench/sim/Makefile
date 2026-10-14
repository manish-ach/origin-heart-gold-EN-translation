# The battle simulator (README.md): the engine, the ROM's data, and the host build of the advanced AI.
#   make ROM=<rom>                  B/sim; B/simdata.c and B/sim_ids.h are remade when gen_simdata.py or the ROM changes
#   make ROM=<rom> OPT=-O0          a debug build
#   make ROM=<rom> AI_DEFS=-D...    the builder's compile-time switches for the AI (e.g. the English build's)
#   make ROM=<rom> B/protect_check  the Protect streak against the DS traces (protect_check.c)
# B defaults to work/build/advanced-ai/sim/<ROM's file name without .nds>; ROM to the untouched Chinese hack.
# The Spanish drama observer (battle experience, not ported) is drama_off.c's no-op stand-in.
AI := ../../src
HOSTAI := ../hostai
OUT := ../../../build/advanced-ai/sim
ROM ?= ../../../rom/origin_v4.0.3_cn.nds
TAG ?= $(basename $(notdir $(ROM)))
B ?= $(OUT)/$(TAG)
PY := ../../../../.venv/bin/python
CC := clang
OPT ?= -O2
AI_DEFS ?=
WARN := -Wall -Wno-unused-parameter -Wno-unknown-attributes -Wno-ignored-attributes -Wno-unused-function \
        -Wno-void-pointer-to-int-cast -Wno-pointer-to-int-cast
BASE_CFLAGS := $(OPT) -g -std=gnu11 $(WARN) -fno-strict-aliasing
CFLAGS := $(BASE_CFLAGS) $(AI_DEFS)
SIM := main damage battle move policy play bench validate origbot cf lapol leaf drama_off
GEN := $(B)/simdata.c $(B)/sim_ids.h

.DEFAULT_GOAL := all

# rewritten only when AI_DEFS changes, so the objects rebuild then and only then
$(B)/ai_defs: FORCE
	@mkdir -p $(B)
	@echo '$(AI_DEFS)' | cmp -s - $@ || echo '$(AI_DEFS)' > $@

FORCE:

all: $(B)/sim

$(GEN) &: gen_simdata.py $(ROM)
	@mkdir -p $(B)
	$(PY) gen_simdata.py --rom $(ROM) --out $(B)

$(B)/ai.o: ai_sim.c $(HOSTAI)/ai_unit.c $(HOSTAI)/host_engine.h $(HOSTAI)/host.h $(AI)/advai.c $(AI)/replace.c \
           $(wildcard $(AI)/lead.c) $(AI)/engine.h $(AI)/tune.h $(AI)/ids.h $(B)/ai_defs
	$(CC) $(CFLAGS) -include $(HOSTAI)/host_engine.h -I $(AI) -I $(HOSTAI) -c ai_sim.c -o $@

$(B)/bridge.o: bridge.c sim.h policy.h $(HOSTAI)/host_engine.h $(AI)/engine.h $(B)/ai_defs
	$(CC) $(CFLAGS) -I $(AI) -c bridge.c -o $@

$(B)/simdata.o: $(B)/simdata.c sim.h
	$(CC) $(CFLAGS) -I . -c $< -o $@

$(B)/%.o: %.c sim.h internal.h policy.h origbot.h lapol.h leaf.h $(B)/sim_ids.h $(AI)/ids.h $(B)/ai_defs
	$(CC) $(CFLAGS) -I $(B) -I $(AI) -c $< -o $@

$(B)/sim: $(SIM:%=$(B)/%.o) $(B)/bridge.o $(B)/ai.o $(B)/simdata.o
	$(CC) $^ -o $@

$(B)/protect_check: protect_check.c $(filter-out $(B)/main.o,$(SIM:%=$(B)/%.o)) $(B)/bridge.o $(B)/ai.o $(B)/simdata.o
	$(CC) $(CFLAGS) -I $(B) -I $(AI) $^ -o $@

clean:
	rm -rf $(B)

.PHONY: all clean FORCE

$(B)/origbot.o: origmodel.h origmodel_rand.h
