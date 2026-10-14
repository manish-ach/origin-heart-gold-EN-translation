/* The stand-in engine for the host build of the advanced AI (force-included before tools/ai/advai.c and replace.c,
   which stay unchanged). It takes tools/ai/engine.h as it is and redirects its three kinds of contact with the DS:

   - AT() reads the DS address space, here a host arena at HOST_BASE + DS address (engine.c maps the DS ranges).
     HOST_BASE has zero low 32 bits, so a host pointer into the arena cast to u32, as the AI does everywhere, is the
     DS address again, and OK_PTR() keeps working on it. Pointer fields are 4 bytes on the DS: AT(vptr/bptr, ...)
     read a u32 and widen it to a host pointer (NULL stays NULL).
   - CALL() resolves each engine entry point to the host function engine.c gives it (host_fn).
   - The few addresses the AI dereferences directly, outside AT(): the type chart, the Read and Replaced records, and
     the battle RNG word (sim_max adds MAIN_RNG to a u32, so MAIN_RNG carries HOST_BASE into the sum).

   The Read records hold a pointer, so they are larger on the host: READS_AT moves down to keep advai.c's static
   assert true; nothing else on the host lives at those addresses. */
#ifndef HOST_ENGINE_H
#define HOST_ENGINE_H

#include "engine.h"       /* ../../src, through -I */

typedef unsigned long long host_u64;
#define HOST_BASE 0x8000000000ull

#undef AT
#define AT(type, addr) AT_##type(addr)
#define AT_RAW(type, addr) (*(volatile type *)(HOST_BASE + (u32)(addr)))
#define AT_u8(addr) AT_RAW(u8, addr)
#define AT_s8(addr) AT_RAW(s8, addr)
#define AT_u16(addr) AT_RAW(u16, addr)
#define AT_s16(addr) AT_RAW(s16, addr)
#define AT_u32(addr) AT_RAW(u32, addr)
#define AT_s32(addr) AT_RAW(s32, addr)
#define AT_vptr(addr) ((void *)host_widen(AT_RAW(u32, addr)))
#define AT_bptr(addr) ((u8 *)host_widen(AT_RAW(u32, addr)))
static inline host_u64 host_widen(u32 v) { return v ? HOST_BASE + v : 0; }

typedef void (*host_fp)(void);
host_fp host_fn(u32 addr);
#undef CALL
#define CALL(addr, ret, ...) ((ret (*)(__VA_ARGS__))host_fn((u32)(addr)))

#undef TYPE_CHART
#define TYPE_CHART (HOST_BASE + 0x0224DA40u)
#undef READS_AT
#define READS_AT (HOST_BASE + 0x01FFFF00u)
#undef REPLACED_AT
#define REPLACED_AT (HOST_BASE + 0x01FFFF80u)
#undef MAIN_RNG
#define MAIN_RNG (HOST_BASE + 0x24C)

#endif
