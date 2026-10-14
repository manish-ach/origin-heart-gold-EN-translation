# Host build of the advanced AI (../../src: advai.c, replace.c and lead.c, unchanged) and its replay driver.
#   make ROM=<rom>                 B/replay (timing) and B/replay_count (call counts, -finstrument-functions)
#   make ROM=<rom> OPT=-Os B=<dir> the DS build's optimization level instead of -O2, in its own directory
#   make ROM=<rom> AI_DEFS=-D...   the builder's compile-time switches for the AI (e.g. the English build's)
# B defaults to work/build/advanced-ai/hostai/<ROM's file name without .nds>; ROM to the untouched Chinese hack.
# The data (B/hostdata.c) comes from the ROM: it is remade when gen_data.py or the ROM changes.
AI := ../../src
OUT := ../../../build/advanced-ai/hostai
ROM ?= ../../../rom/origin_v4.0.3_cn.nds
TAG ?= $(basename $(notdir $(ROM)))
B ?= $(OUT)/$(TAG)
PY := ../../../../.venv/bin/python
CC := clang
OPT ?= -O2
AI_DEFS ?=
WARN := -Wall -Wno-unused-parameter -Wno-unknown-attributes -Wno-ignored-attributes -Wno-unused-function \
        -Wno-void-pointer-to-int-cast -Wno-pointer-to-int-cast
CFLAGS := $(OPT) -std=gnu11 $(WARN) -fno-strict-aliasing $(AI_DEFS)
AI_FLAGS := -include host_engine.h -I $(AI)
AI_SRC := ai_unit.c host_engine.h $(AI)/advai.c $(AI)/replace.c $(wildcard $(AI)/lead.c) $(AI)/engine.h $(AI)/tune.h \
          $(AI)/ids.h $(B)/ai_defs

.DEFAULT_GOAL := all

# rewritten only when AI_DEFS changes, so the objects rebuild then and only then
$(B)/ai_defs: FORCE
	@mkdir -p $(B)
	@echo '$(AI_DEFS)' | cmp -s - $@ || echo '$(AI_DEFS)' > $@

FORCE:

all: $(B)/replay $(B)/replay_count

$(B)/hostdata.c: gen_data.py $(ROM) | $(B)
	$(PY) gen_data.py --rom $(ROM) --out $(B)

$(B)/ai.o: $(AI_SRC) | $(B)
	$(CC) $(CFLAGS) $(AI_FLAGS) -c ai_unit.c -o $@

$(B)/ai_count.o: $(AI_SRC) | $(B)
	$(CC) $(CFLAGS) $(AI_FLAGS) -finstrument-functions -c ai_unit.c -o $@

$(B)/%.o: %.c host.h host_engine.h $(AI)/engine.h $(B)/ai_defs | $(B)
	$(CC) $(CFLAGS) -I $(AI) -c $< -o $@

$(B)/hostdata.o: $(B)/hostdata.c | $(B)
	$(CC) $(CFLAGS) -c $< -o $@

HOST_OBJ := $(B)/engine.o $(B)/replay.o $(B)/hostdata.o

$(B)/replay: $(B)/ai.o $(HOST_OBJ)
	$(CC) $^ -o $@

$(B)/replay_count: $(B)/ai_count.o $(HOST_OBJ)
	$(CC) $^ -o $@

$(B):
	mkdir -p $@

clean:
	rm -rf $(B)

.PHONY: all clean FORCE
