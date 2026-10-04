# Side-content batches (R042–R059): prompt addendum

> Historical (reviewed 2026-09-29): the side-content batches (R042–R059) are all done; kept as a record of the prompt they used.

Read `AGENTS.md` in the repo root and follow it exactly. All standing rules live there.

Context: the whole main story (Kanto, the island cluster, Johto through the Sinjoh Ruins) is translated. These batches are text not tied to a map: common script text, TV and radio shows, Pokégear phone calls, the Battle Frontier (rules, facility text, trainer lines), the Pokéathlon, minigames, mail and Easy Chat words.

- **Phone calls:** each caller is a trainer from bank 0719 (names decided there) or a story character with a voice record in the digest (Gold, Crystal, Silver, Mom, Prof. Elm, Prof. Oak, Bill, Jasmine and so on). Keep their voice. Callers use `{VAR}` tags for Pokémon, routes and items: keep them all, and keep sentences grammatical for any likely value.
- **TV and radio:** official US lines (origin "us") survive only where the hack's Chinese still says the same thing. Radio shows may contain jingles or songs; apply the song rule (no lyrics; a hum or description line, recorded).
- **Battle Frontier:** facility names, the Brains (Palmer, Argenta, Thorton, Dahlia, Darach, Caitlin), the Judge and the BP terms are decided. Keep rules text concise and consistent with the already translated Frontier banks (0094–0108).
- **Pokéathlon:** official US course and event names (see the digest). The SWITCH wording matches the graphic.
- **Easy Chat words and mail:** single words or short phrases in fixed-width slots. Keep them short (compare the US bank for the same slot), in the US capitalisation style for that list. Words that are Pokémon, moves, items or types use the glossary.
- **Unused or leftover text:** still translate it. Keep it faithful and don't overthink it; note "probably unused" in the string notes when bank_maps.json or the content suggests so.

Report: counts (translated / accepted US / accepted v3 / rewritten), what the banks contain, 3 sample lines (zh → en), the decision ids you added, and any open questions. If a batch runs long, finish whole banks and report exactly which ids remain.
