/* lathumb.py's entry: one lookahead decision from a root battle the host dumped (sim cf la --dump) */
#include <stddef.h>
#include "sim.h"
#include "lapol.h"
#include "layout.h"

typedef struct {
    LaCfg c;
    s32 nalt;
    Action alt[12];
    s32 w[12];
    LaWork cnt;
} LaJob;

__attribute__((section(".text.entry"))) void la_entry(const Battle *root, LaJob *job, Battle *work)
{
    job->cnt.turns = job->cnt.calls = 0;
    la_decide(root, job->alt, job->nalt, &job->c, la_policy(job->c.pol), la_policy(job->c.pol), work, job->w, &job->cnt);
}
