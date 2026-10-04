# Chinese sources: independent checks for our documentation

Researched 2026-10-04. Scope: public Chinese release information compared with our existing references. No downloads, ROM builds, tool changes or translation changes. The four Reddit workbooks are already present at the repository root; this review adds evidence beyond those workbooks.

## Sources and access limits

- **S1: Alex's original 4.0 release announcement**, [Tieba thread 10981775037](https://tiebac.baidu.com/p/10981775037?fr=good). Search-indexed body was readable; direct opening failed. Primary author statement about 4.0 intent, not a runtime test of our particular 4.0.3 binary.
- **S2: Alex's profile / release history**, [Alex's Baidu profile](https://youhua.baidu.com/home/main?lp=home_follow_main&un=chendelpiero). Indexed profile includes a September 5, 2026 4.02 update excerpt; direct opening failed. The excerpt is incomplete, so do not reconstruct missing changes.
- **S3: older walkthrough collection**, [StrugglingTom](https://www.bilibili.com/list/ml2287243592?bvid=BV1Ba411L7FD&oid=214880374). Predates v4. Useful for finding scenes, not for validating current mechanics. Video footage was not inspected.
- **S4: example of unreliable secondary advice**, a 4.0 article on an app download portal (link not kept). Its starter advice names the Johto trio, while its own walkthrough describes the Pallet opening and Pikachu replacing Squirtle. Reject it as an independent authority.

## Highest-value findings

### 1. Script absence is incorrectly presented as item unavailability

`work/docs/items.md:181` says a list of key items is “not in the game”; `work/notes/docs_crossref.md:87` calls the same list dead data. Both include Chain Logger. The wording originates in `work/tools/docs/gen_docs.py:1621` and `:2020`, so editing generated Markdown alone would not persist.

Our own `work/notes/graphics_layout_audit.md` documents opening Chain Logger from the bag and verifying its graphics in a local test ROM. That independently disproves the blanket claim that the item is absent, although it does not establish its normal acquisition path.

S1 describes automatic grants: Chain Logger at the start, EV Allocator after receiving a starter, and charms through the mother's savings rewards.

**Recommended correction:** distinguish “no source found by the current extractor” from “unavailable”. Trace initialization, engine hooks and non-map-script rewards before deciding availability. Keep the whole list provisional; this evidence does not prove every listed item is obtainable. Prioritize items 744/745 (ids recorded in `work/notes/text_metrics.md`) and the four listed charms.

### 2. HM-free intent is now supported by the author

S1 explicitly describes badge-gated field moves without teaching HMs.

`guide/known-issues.md:1237` and `guide/13-dungeons-and-common.md:114` still describe the intention as uncertain. The existing D-1428 code analysis and author statement support each other. A documentation revision can distinguish **author-confirmed intent** from **runtime verification still pending**.

Do not generalize the statement into a claim about every access path: our guide distinguishes obstacle interaction from the party menu. Fly/Flash access and badge-specific details still require targeted checks against this binary.

### 3. A dated explanation for two spreadsheet mismatches

S2's 4.02 excerpt explicitly changes Staraptor to Flying/Fighting and Serperior to Grass/Dragon.

Our independently parsed ROM already has those type combinations. `work/notes/sheet_mismatch_verification.md` identifies Staraptor's sheet row 418 as outdated, but groups Servine/Serperior rows 528/529 as undetermined. The author statement strengthens the stale-sheet explanation for **Serperior**. It does not explicitly cover Servine; keep that distinction when revising the audit.

The generated Pokémon pages need no typing correction. This is stronger provenance for the existing values, not a reason to modify game data.

## Mechanics worth targeted verification

S1 supplies these test leads:

| Topic | Author-stated behavior |
|---|---|
| Capture chains | Bonuses also affect static encounters; catching another species or a shiny resets the chain; defeating/fleeing does not. |
| Shiny overworld encounters | One is retained across map re-entry, but lost on restart. |
| Pickup | Items go directly into the bag. |
| Breeding | Flame Body: eightfold hatching speed; Destiny Knot: five IVs; Everstone: nature inheritance. |

These are leads for a mechanics page, not newly verified 4.0.3 behavior. The searched guide has detailed quest coverage but no central explanation of these systems. Useful validation cases include chain reset boundaries, static encounters after chaining, leaving/re-entering a map versus restarting, and item acquisition with full pockets. Do not publish exact probabilities without checking the implementation or measuring it.

## Source selection and follow-up order

1. Correct the generator's unsupported availability wording, then audit automatic item grants. This addresses a demonstrated inconsistency within our own resources.
2. Add author provenance to the HM discussion and the Serperior audit, preserving the runtime caveats and Servine distinction.
3. Verify the mechanics above on the untouched Chinese binary, then compare the English build. Follow D-1002/D-1337: original-hack behavior is documented, not repaired.
4. Locate stable direct Bilibili video URLs for the v4 playthrough by 小林今天不想上班. S1 names this creator as a distribution channel; indexed listings show a v4 series, but no footage was verified here. Capture version, episode and timestamp before using video as evidence.

For ongoing discovery, Alex's profile and 起源心金吧 are the most useful public leads. The existing credits note records QQ group 1055021987 from the game's intro; its private files/announcements were not inspected. Search both dotted and compact version spellings. Do not treat copied release text on several download sites as independent corroboration.

No new complete v4.0.3 manual or verified newer workbook was found. The useful gain is author intent, version-specific explanations, and a concrete gap in our extraction coverage. Existing historical audits and decision records remain unchanged; this note is supplementary evidence for their next revision.
