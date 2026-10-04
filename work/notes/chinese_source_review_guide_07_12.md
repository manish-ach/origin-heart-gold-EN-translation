# Archived Chinese source review: guide chapters 07–12

Review date: 2026-10-04. Findings only; no guide, documentation, game, script or decision-register changes. References use current guide text, after the earlier guide-review corrections.

## Result and evidence limits

No new gameplay error in these chapters was established by the archived external evidence. The useful findings are a high-priority romance runtime contradiction, three obsolete Gym-rule conflicts, independent password/weekday corroboration, and better targeted external-test leads. An external discrepancy is not sufficient grounds to replace the current v4.0.3 script-derived instructions.

Archive root throughout: `work/research/chinese_sources/2026-10-04/`. Read the actual archived article bodies, relevant video descriptions and episode lists, public comment bodies, and full release search snapshot; these are not watched videos. Inspected `images/65d3cdac47a98813.jpg` with view_image: it is a generic title-screen illustration with emulator controls, not a Gym-rule screenshot. It supplies no proof for the article's Gym requirements. No full video, gameplay capture, private QQ material or runtime replay was available in this review.

Existing static audits consulted: `work/notes/guide_review_2026-10-04_part2.md`, `...part3.md`, `...part4.md`, and relevant part5 findings. Script/flag references below are corroborating references from the current guide and those audits, not a claim of a fresh full disassembly audit.

## GJ-01 — Romance release claims and player report conflict with the universal moving-in block

- **Location:** `guide/09-ilex-goldenrod.md:468`, heading “Romance route”; `:520`, “Confession, dates, moving in”; `guide/08-cherrygrove-to-azalea.md:716`, “Green's (or Red's) dates”.
- **Issue:** the guide says moving in appears unreachable for everyone, based on starter flag 106. The author explicitly lists romance bug fixes for v4.0, while a modern public commenter reports that female-player partners turn into another character when brought home, and that an earlier love-letter scene did not trigger. The latter implies some home sequence was observed on some build, but does not identify the build, save provenance, exact partner or progression. It does not prove our untouched v4.0.3 script reading wrong.
- **Archived evidence:** `search-0.txt:218–235`, Alex's release announcement, https://tiebac.baidu.com/p/10981775037?fr=good (v4.0, indexed excerpt); `comments.md`, comment **314633041953**, https://www.bilibili.com/video/BV1xNej6CEGE/ (4.1-discussion context, played version unspecified). The archive records a request to fix partner swaps and letter triggering, not a demonstrated fix or a complete reproduction.
- **Local corroboration:** current chapter 09 source note identifies file 843 scripts 1/4 checking flag 106 before partner checks, D-1391. Current guide already acknowledges female Red's lock error and reversed Green/Red dating condition; these are not new discoveries.
- **Classification/status:** **new external contradiction / runtime lead**, not verified documentation error. High confidence in the source mismatch; low confidence it applies to a clean v4.0.3 playthrough.
- **Future action:** prioritize a clean Chinese v4.0.3 female-player romance test, record selected partner and save provenance, trace flag 106 and date counter at the home event, compare map-init and interaction paths, then test the English build. Keep the current uncertainty wording pending that test. Do not adopt the release claim as proof all romance bugs were fixed.

## GJ-02 — Legacy Falkner rules should not replace the v4.0.3 party limit

- **Location:** `guide/08-cherrygrove-to-azalea.md:303`, “Violet Gym: Falkner's rules”.
- **Issue:** the Chinese article says three Flying Pokémon; the guide says four or fewer and documents later-species loopholes.
- **Evidence:** `pages/2a8484e73abfbc22/text.txt`, https://www.9game.cn/news/8291958.html, publication **2023-06-29** (pre-v4; exact build unstated). The same list is copied by 233leyuan/PHP pages in `search-1.txt:301–386`; these are not independent corroboration. The article image was inspected and contains only a title screen.
- **Local corroboration:** chapter 08 source note, script 856 party checks L14796/L14807 and D-1426.
- **Classification/status:** **new source-version conflict**, high confidence that the text differs, no established error in our guide.
- **Future action:** quarantine this legacy table in source provenance. A future Gym smoke test should include parties of 3, 4 and 5, with eligible species; preserve the current four-Pokémon limit unless that test contradicts it.

## GJ-03 — Legacy Morty table conflicts with both the current six-member gate and expanded team

- **Location:** `guide/10-ecruteak-olivine.md:236`, “Ecruteak Gym: Morty's Ghost challenge”.
- **Issue:** the same 2023 article describes Gengar, Mismagius and Dusclops and a 3v3 match. Current instructions require six eligible party members and list the expanded trainer, including three Lv. 1 later-generation members. The old wording must not be used to remove the guide's six-member requirement.
- **Evidence:** same archived article/URL/date as GJ-02; `videos.md`, BV1Mx8S6eEL8 part 22 (v4.0 title; uploader confirms 4.0.3 in comments 313547556481/317025190368) identifies the relevant Gym episode but contains no party-count or opponent detail.
- **Local corroboration:** current source note cites file 918 L1055–L1133 and trainer 31. Earlier part3 proposed a duplicated-opponent description; current text has since changed. This external archive cannot adjudicate the battle-engine presentation, so do not mechanically reapply that older proposal.
- **Classification/status:** **new source-version conflict**, high confidence in mismatch; numerical in-battle presentation remains an external-video/runtime lead, not a new proven error.
- **Future action:** test the six-member gate and capture the full opponent roster in clean v4.0.3; use part 22 as a targeted comparison if video access is authorized later.

## GJ-04 — Legacy Jasmine threshold is not the current rule

- **Location:** `guide/10-ecruteak-olivine.md:574`, “Olivine Gym: Jasmine's rule”.
- **Issue:** the 2023 article says three Pokémon with base Defense greater than 100; the guide says 130+ and explains that enforcement is a fixed species list with exceptions. Importing the old threshold would weaken an already more precise guide.
- **Evidence:** same archived article/URL/date as GJ-02. `videos.md`, BV1Mx8S6eEL8 part 23 explicitly covers Olivine and its Steel Gym but supplies no threshold in its description.
- **Local corroboration:** current source note file 909 L839–L14930; the current paragraph already includes the loophole examples identified by the earlier audit.
- **Classification/status:** **new source-version conflict**, high confidence; existing exceptions **resolved/already documented**.
- **Future action:** retain the version-specific list; include one 101–129 Defense species and one accepted 130+ species in a runtime Gym check rather than accepting the legacy article's summary.

## GJ-05 — Modern episode metadata independently corroborates Boot Camp password

- **Location:** `guide/11-cianwood-mahogany.md:325`, “Boot Camp Ruins: the Team Rocket PC password”.
- **Evidence:** `videos.md`, BV1Mx8S6eEL8, part **25**, cid **42115992368**, explicitly gives **14246**; source https://www.bilibili.com/video/BV1Mx8S6eEL8/?p=25. Title says v4.0, uploader answers yes to “is this 4.0.3?” in `comments.md` IDs 313547556481 and 317025190368. This is self-reported version evidence, not a ROM hash.
- **Local corroboration:** current guide's 1 4 2 4 6 and script 881 L2424–L3662.
- **Classification/status:** **already-known, independently corroborated**; high confidence, no edit needed.
- **Related caution:** `pages/62ad69e6aeff3ee1/text.txt`, https://www.9game.cn/news/8284061.html (2023-06-28), describes a dynamic Morse/color password puzzle. It should not replace the fixed Boot Camp number merely because both pages say “Rocket password”; it refers to another puzzle. The guide already distinguishes the encounters.

## GJ-06 — Lake trio Wednesday condition corroborated; numeric answer shortcut remains unverified

- **Location:** `guide/12-lake-of-rage-to-sinjoh.md:403`, “Uxie, Mesprit and Azelf”; `:419`, Wednesday appearance.
- **Evidence:** `comments.md`, comment **207831877392**, https://www.bilibili.com/video/BV1pp421R78c/. Raw archived comment timestamp is 1707800711 (2024; legacy complete-version release). It gives the sequence 31224 and says the trio can be caught Wednesday. The guide gives answer text and also says Wednesday.
- **Local corroboration:** chapter source notes files 934/935 and Wednesday variable 0x4037. The current guide additionally explains leaving and re-entering when Wednesday begins; the comment does not cover that edge case.
- **Classification/status:** Wednesday **already-known corroboration** (medium confidence for version applicability); 31224 **lead only** (not checked against current menu ordering).
- **Future action:** no correction to weekday instructions. If a numeric shortcut is desired later, compare each current menu position before publishing 31224; translated text answers remain safer.

## GJ-07 — Legacy traversal advice is stale for several v4 field moves

- **Location:** `guide/11-cianwood-mahogany.md:281`, Mt. Mortar expedition; `guide/12-lake-of-rage-to-sinjoh.md:292`, Dragon's Den Whirlpool; `:442`, Reversal Cave.
- **Evidence:** legacy comment 207831877392 instructs carrying Pokémon that know Whirlpool/Flash/Strength/Rock Climb. Alex's v4.0 release excerpt `search-0.txt:265` describes badge-gated field use without learning moves; `videos.md` BV1Mx8S6eEL8 description item 7 describes the same feature but adds compatibility language. These general descriptions are not exact per-command specifications.
- **Local corroboration:** current chapter 12 already explicitly says no learned Whirlpool needed and links to the field-move table. Prior part4 traces `GetPartySlotWithMove` selecting a healthy non-Egg Pokémon; it also distinguishes learned Fly/Flash/menu use from obstacle interaction.
- **Classification/status:** **already-known / resolved** version conflict, high confidence for the existing Whirlpool correction. No fresh error demonstrated.
- **Future action:** preserve the precise local table and its runtime caveat. Do not reintroduce an HM-mule checklist from the legacy comment or infer that every move has identical checks from the author summary.

## GJ-08 — Route 38 reward and new mechanics leads are already covered or need video, not speculative additions

- **Location:** `guide/10-ecruteak-olivine.md:416`, Murkrow coin quest; `guide/07-league-to-cherrygrove.md:29`, Giovanni/Charizardite.
- **Evidence:** `pages/7445464f8da6b32a/text.txt`, https://www.9game.cn/news/8298850.html (2023-07-01), says the Route 38 Murkrow drops an Amulet Coin. Current guide already covers the coin plus the consequential return/keep choices: no omission. `videos.md` BV1Mx8S6eEL8 parts 17–18 mention a Greninja transformation item and special form near the early Johto episodes; the metadata does not establish where obtained. Our guide already lists the Ninja Scroll at `guide/06-sevii-islands-indigo.md:60`; do not invent a New Bark grant from episode order.
- **Classification/status:** **already-known**, high confidence for coin coverage; Greninja episode **lead** for presentation/usage only.
- **Future action:** no chapter edit from these sources. If recording a form-transformation demonstration later, target those episodes and verify exact item/form against current game data.

## Section coverage and no-findings areas

| Chapter | External coverage checked | Outcome / limits |
|---|---|---|
| 07 League–Cherrygrove | v4 episode 17–18 descriptions; legacy release description; late-quest comment; current headings and pertinent route entries | No new proven error. No external bodies provide detailed evidence for most sidequests, rehabilitation counters or League report gates. Existing Giovanni heading fix is present. |
| 08 Cherrygrove–Azalea | v4 episodes 19–21 descriptions; legacy eight-Gym table; romance report | Falkner source conflict above. No external proof to reopen existing Bugsy uncertainty, gift quantities or deadline conditions. |
| 09 Ilex–Goldenrod | romance release claim/comment; v4 episode 21–22 descriptions; current romance section | Romance is the important new test priority. Previous reading timing, Crystal recovery caveat, Misty timing and one-time shrine-gift corrections are already in current text; do not count them as new. No external detailed Ilex/shrine route evidence. |
| 10 Ecruteak–Olivine | 2023 Gym table; Murkrow article; v4 episodes 22–23; late-quest comment; tutor metadata | Three Gym conflicts isolated above; Murkrow already covered. Current Dream World re-entry and Jasmine exceptions incorporate earlier audit work. |
| 11 Cianwood–Mahogany | v4 episodes 24–26, direct password metadata, modern comment asking whether Rocket HQ freezing persists, legacy traversal notes | Password corroborated. Comment 317678159344 asks about freezing; it is not an observed bug report with a reproduction and should not create a new known issue. |
| 12 Lake–Sinjoh | v4 episodes 27–34 titles; legacy late-quest comment; current trio/Den/legendary entries | Wednesday corroborated; no external full encounter-result evidence to replace current one-chance warnings or establish Azure Flute accessibility. |

Targeted later viewing can use the v4 tutor-series metadata: BV12re268En2 (28–31), BV1cQe269E6T (32–35), BV1Eueh6TEMz (36–40), BV1Gneh6fETs (41–44), BV13re864EDz (45–46), BV1Zehi6CEVN (final Gyms), plus trainer-held-item episodes BV1w4ep6XEKm/BV1xieH6oEqn/BV1foeA68EqJ/BV1WKeA6vEm9/BV1dueK6FEpR/BV1soeu6RED5. Their archived descriptions are only a dash and generic video filename: they identify useful targets but establish no tutor payment, move, held item or runtime result. No such claims were inferred from them.

This is an archive-driven comparison, not exhaustive verification of every guide statement. Preserve those limits in any combined findings register.
