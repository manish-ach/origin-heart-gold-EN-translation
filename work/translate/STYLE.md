# Translation style guide: 起源心金 (Origin HeartGold) v4.0.3 → English

## Source of truth, in order
1. `work/glossary/*.json`: official English names for Pokémon, moves, items, abilities, types, natures and locations. Always use these, even where the US ROM or the v3 translation says otherwise.
2. Official US HeartGold text (origin "us" in the banks, seeded from the local-only `us_reuse.jsonl`, verdict "likely"): use it for unchanged vanilla lines, but modernise names to the glossary and use mixed case (e.g. BULBASAUR becomes Bulbasaur, POKé BALL becomes Poké Ball).
3. v3 fan translation (origin "tm_v3" in the banks, seeded from the local-only `tm_v4_matches.jsonl`): a draft only. Fix mistranslations, typos and overflow; don't keep its wording just because it exists.

## Voice
- **Faithful tone, never toned down (user decision D-0627).** Keep the hack's own voice: crude language, insults, swearing, innuendo, dark or political jokes and adult (21+) content stay at the same strength in English. Don't soften or sanitise, and don't add crudeness that isn't there.
- Natural, idiomatic English in the tone of official Pokémon localisation: friendly and concise, with no translationese.
- The hack draws on Pokémon Origins, the anime and Pokémon Adventures (Special manga). When a line references one of these, use the official English character names: Red, Blue, Green (the Origins/Adventures sense), Ash, Misty, Brock, Professor Oak, Giovanni and so on. If you're unsure of a reference, add a note rather than inventing a name.
- **Canon English wording (user decision D-1436).** Where the Chinese quotes the Chinese dub of the anime or the Chinese manga (Team Rocket's motto, "blasting off again", attack calls, famous lines), use the official English dub/manga wording (D-1437, D-1438). Only use canon wording you can verify; otherwise translate the Chinese and add a question. The hack's own variations and parodies are translated from the Chinese, echoing the canon wording where they riff on it. Song lyrics are still never quoted (D-0368).
- Mixed case for all names (Pokémon, types, items). Keep "Pokémon" with the é. Use "PC", "TM" and "HM" in capitals.
- Numbers, money and variables: never change `{...}` tags. Keep every one, in an order that makes sense for English. Money: keep the source tag if there is one; otherwise write "$" before the amount, as the US ROM does (D-0008).

## Formatting (enforced by `work/tools/qa.py`)
- Dialogue box: 216 px per line, 2 lines per page. Write plain prose, then run `python3 work/tools/qa.py wrap --in-place --mode scroll --which max <bank>` (see AGENTS.md) to insert `{NEWLINE}`/`{SCROLL}` breaks. Hand-adjust only when wrap can't solve it.
- `{SCROLL}` = new page (the box clears). `{CLEAR}` = scroll one line.
- Name limits (`qa_config.json`): species 10, moves/items/abilities 12, types and natures 8, trainer names 10 (bank 0719, stored compressed), Battle Frontier trainer names 7; locations warn above 18 (the US maximum is 16).
- No ASCII quotes (the font lacks them): `wrap` converts them to ‘ ’ “ ”.
- Every translated string must pass `qa.py check` with 0 errors before a batch counts as done.

## Workflow per string
- Set `en`, and set `status` to "draft" (translator) or "reviewed" (reviewer). Set `origin` to "agent", "tm_v3", "us" or "glossary".
- Use `notes` for anything uncertain: a reference you couldn't identify, a pun, or a glossary term that looks wrong. Unsure names go to notes, not guesses.
- Keep consistency within a map: look at neighbouring strings in the same bank for speaker names and context.
