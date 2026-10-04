# Chinese-source review: common mechanics and evidence quality

2026-10-04. Findings only. Reviewed guide/README.md, chapter 13, known-issues.md, and pertinent existing runtime notes. No gameplay, documentation, translation, or tool changes. Archive paths below are relative to `work/research/chinese_sources/2026-10-04/`.

The principal external source is [Alex's v4.0 announcement](https://tiebac.baidu.com/p/10981775037?fr=good), preserved in `search-0.txt:219–281`. It establishes advertised intent for 4.0, not exhaustive runtime proof for 4.0.3. The guide describes its scope as quests; broader mechanics omissions below are proposed resource improvements, not automatically errors in that scope.

## COM-01 — HM-free intent has stronger evidence than the current caveat suggests

**Locations:** `guide/13-dungeons-and-common.md:114`; `guide/known-issues.md:1235`. **Status:** known topic, new primary-source corroboration; confidence high about intent, limited about individual commands at runtime.

The guide says the no-learned-move behavior “may be” intended, and known issues says “possibly” intended. Alex explicitly advertises badge-gated field moves without learning them (`search-0.txt:265`). A future edit can distinguish confirmed design intent from remaining runtime uncertainty. Preserve the precise script-derived table, healthy-party checks and party-menu exceptions: the announcement's broad Fly/Surf wording does not resolve every dispatch path. The playthrough description adds move compatibility, which likewise must not override local handler evidence. No behavior fix is appropriate.

## COM-02 — Party-wide EXP/EV sharing needs an accessible explanation; reject the toggle claim

**Locations:** guide README/common-mechanics coverage; `work/notes/exp_share_research.md:5–25`, runtime results later in that note. **Status:** new player-resource coverage gap; high confidence within audited battle conditions.

Alex advertises party-wide EXP and EV awards (`search-0.txt:244`). The archived [34-part playthrough](https://www.bilibili.com/video/BV1Mx8S6eEL8/) description (`videos.md:313`) claims an option to disable sharing. Existing local research is stronger: the untouched Chinese eligibility function unconditionally returns true, and the normal calculation does not consult an option, flag, item or button. Its controlled battle reproduced participant +26 EXP / 1 EV and benched +13 EXP / 1 EV. The ordinary Options screen has no sharing row.

Future documentation should explain automatic sharing and the observed nonparticipant half-EXP behavior, with limits for untested fainted/egg/doubles cases. Do not advertise a native toggle, silently apply an optional patch, or infer that the older held Exp. Share quest reward disappears.

## COM-03 — Chain Logger and training controls are absent from the quest guide

**Locations:** guide README/chapter 13; `work/notes/in_game_shortcuts.md:13–21` and its EV Allocator section; `work/translate/banks/a027/0814.json` and `0815.json`. **Status:** new coverage proposal, partly verified; overlaps REF-01 automatic item grants.

The announcement describes initial Chain Logger access, starter-time EV Allocator access, capture-chain bonuses applying even to static encounters, and resets after catching another species or any shiny; fleeing/defeating neither advances nor resets the chain (`search-0.txt:258–264`). UI bank 0814 corroborates chain-related fields but is not an implementation audit. Its threshold labels overlap at 10 (`#10` 6–10, `#11` 10–20): do not silently turn this into an exact 11–20 rule. Treat that boundary as a runtime/code verification question.

Existing Chinese-ROM controls research already verifies **L on the summary stats/moves page** opens IV/EV information, and L/B closes it. R did nothing in the tested normal-button mode despite the source tip (D-1458). Bank 0815 supplies allocator button text, but text alone does not prove normal acquisition or every control path. A future mechanics/controls link can reuse the tested findings and clearly mark source-only rules. Generator controls, if covered, should be explained separately because they create Pokémon.

## COM-04 — Visible encounter and shiny persistence rules deserve a scoped explanation

**Locations:** guide README/chapter 13, `work/docs/encounters.md:5–7`; overlaps REF-07. **Status:** source-backed coverage lead; medium confidence as v4 intent, unverified here in v4.0.3 runtime.

Alex describes up to six visible wild Pokémon, repel suppression, reduced ordinary encounter frequency while visible spawns exist, a shiny sound, and re-entry relocation of an inaccessible shiny. Crucially, the announcement says only one visible shiny is retained and restarting/closing loses that retained information (`search-0.txt:270–277`). This is potentially useful player advice, but must not become a guarantee about saves or every map without verification.

Future work should distinguish the extracted encounter tables from the overworld spawn system and verify persistence/restart behavior in an isolated save. The author also mentions date-specific mythical encounters (`:279`) without providing a calendar: do not invent dates, species or locations, or assume existing encounter tables describe that system.

## COM-05 — Other advertised v4 mechanics are research leads, not verified corrections

**Locations:** common mechanics coverage; generated item/ability descriptions. **Status:** optional coverage expansion; medium confidence in advertised intent, implementation pending.

Release lines 245–249 describe automatic Pickup deposits, restoration of most consumed/knocked-off held items, and Y battle information with conditional opponent-ability visibility. Line 280 describes accelerated Flame Body hatching, five-IV Destiny Knot inheritance and Everstone nature inheritance. Source descriptions in banks (including 0712#49/#53 and 0218#219) do not fully explain those engine additions. Faithful translation of those descriptions is not an error and must not be rewritten to add mechanics.

Before a player guide addition, check exceptions and actual input context, especially “most” restored items and opponent information reveal conditions. Other release features (box capacity, music-speed settings, backgrounds, detailed Pokédex and fishing changes) are navigation/test leads rather than confirmed defects in a quest walkthrough. Forms, charms, species typing and trainer EV scope are covered separately in REF-01/04/05/09.

## ARCH-01 — Derived search excerpt file silently omits the primary announcement

**Location:** archived `index_archive.py:12`, generated `search-extracts.txt`. **Status:** new confirmed archive indexing defect; high confidence. No script edited during this findings-only review.

The index tests the first line of each separator-delimited block before stripping leading whitespace. Blocks beginning with a newline fail the title check, dropping relevant hits including the primary release. The full saved `search-0.txt` and JSON response retain the evidence. Reviewers were directed to those originals. A future archive-only fix should strip each block before selecting its first line and verify that the Alex announcement survives regeneration. This is an incomplete derivative, not evidence that the source was absent.

## Chapter 13 and known-issues coverage limits

| Section | Result |
|---|---|
| Clefairy/Mt. Moon, Ruins panels, Forest maze | No sufficiently detailed archived evidence to adjudicate the current flags, rewards or route instructions. No new correction established. |
| Lake trio/Wednesday | Legacy comment corroborates weekday only; see GJ-06. Numeric answers and re-entry details still require current local evidence. |
| Field moves | COM-01; preserve current per-path distinctions. |
| Other small dungeon items | No new source-based correction established. |
| Known issues | Checked field-move classification and romance source conflict (GJ-01/K05). External comments do not independently reproduce the many script-derived warnings. This was not a new full audit of every listed issue. |
| README/common mechanics | COM-02–05 are resource-expansion proposals given the explicitly quest-oriented current guide. |

No fresh emulator tests were run for this report. Prior runtime results are attributed to their existing notes. All external evidence is version-qualified; no source-only claim should replace current original-ROM behavior.
