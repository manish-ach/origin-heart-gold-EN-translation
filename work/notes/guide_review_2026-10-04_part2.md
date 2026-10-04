# Guide review, part 2: late Kanto, Sevii Islands and the League

Date: 2026-10-04. Scope: all 2,008 lines of guide chapters 04–07, read for accuracy, clear instructions, repetition and cross-references. Review only; guide, game and tools unchanged.

## Method and limits

Read the current guide, applicable repository/style decisions, part 1 and the editorial review. Used `work/tools/docs/scriptdump.py` and `romdata.py` against the untouched Chinese v4.0.3 ROM; script numbers below mean files in `a/0/1/2`, and `@` means byte offsets. Current English banks supply dialogue labels; ROM control flow and trainer data supply the behavioral evidence. Old `guide_errata.md` was a lead list, not proof. Most older corrections for these four chapters are already present. This is static review, not a playthrough. I did not retrace all map collision, engine behavior, trainers, prices or party-selection restrictions.

## Corrections to prioritize

### 1. Five Island instructions put the Elder's trial after the event it unlocks

**P2; high confidence.** `guide/05-saffron-cinnabar.md:495–496` sends the player to ask for the disciple's release, then says the Elder's quiz/battle follow. Chapter 06 correctly states the opposite. File 737 checks victory flag 2175 @587; only the completed-trial branch @1943–1954 or the immediate victory branch @3503–3518 reaches the mountain-disciple menu @3416. Its release scene sets quest stage 9 @4517.

**Short correction:** “Pass the Elder's quiz and battle first [exact chapter 06 anchor]. Then ask about the man on the snowy mountain and return to the disciple.” Change the reward sentence to distinguish the trial pass from this optional Mew continuation. One canonical quiz/battle entry is enough.

### 2. Mr. Mime's alleged shortcut points to the wrong Tohjo Falls event

**P2; high confidence.** `guide/05-saffron-cinnabar.md:189` says the ordinary hermit battle removes Mr. Mime and links to chapter 07's TM52 quest. That battle is file 114 @890 (`TrainerBattle 275`), awards the TM and sets 1635 @945; its rematch is @960. Neither sets 771. The cited writes to 771 @320/@646 belong to the separate Celebi/time-travel scene, involving trainer 700 @260 and Lyra's dialogue, not the linked hermit encounter. This is an error inherited from the earlier errata.

**Short correction:** delete the hermit shortcut sentence. Keep the straightforward “battle Mr. Mime, then talk to its trainer” instructions. If retaining the shared-flag detail, put it in technical notes and explicitly call it the separate time-travel event; normal access to that event was not established here.

### 3. The Latias fountain scene requires a later return

**P2; high confidence.** `guide/05-saffron-cinnabar.md:586` says the final Hall of Fame condition is “already” met when obtaining Latios/Latias. The gift completes One Island's pilgrimage trial before the final League storyline. File 239 checks 2261 @3564 before the Latias lead check @3575–3591; that flag is only set in the final Hall of Fame block, file 822 @2458. The gift branch itself requires two empty slots (@2558–2568) and does not need 2261.

**Short correction:** “Return after the final Hall of Fame with Latias as your first healthy Pokémon for an extra fountain scene.” Link to the precise chapter 07 Hall of Fame explanation.

### 4. The Six Island quest deadline is described too broadly

**P2; high confidence.** `guide/05-saffron-cinnabar.md:436` and `guide/06-sevii-islands-indigo.md:358` say the forest/wallet quests end when the Lucky Meowth God arrives. Chapter 06's detailed ending correctly distinguishes the branches: Meowth stays in the chief's house in the arrest endings too, without the island transformation. File 894's “let them stay” ending sets stage `0x40af = 14` @4761; arrest instead finishes @5007–5017 without that write. File 55's forest-entry scene then clears 2180 @1295, ending the old forest quests.

**Short correction:** “Finish these quests before leaving Jessie, James and Meowth on Six Island and entering the Island Forest.” Link directly to the ending choice, and use the same condition in the wallet entry. Preserve the fuller chapter 06 explanation rather than repeating it.

### 5. Victory Road unnecessarily sends players after a fake password

**P2; high confidence.** `guide/06-sevii-islands-indigo.md:119` presents Damon's fake password as a numbered step after beating Janine on 2F. For some branches Damon is Janine: after the 1924 check @4490–4494, the matching condition reaches @9340, battles @9358 and reveals Janine @10147. The fake-password branch is the separate ordinary fight @9300–9332. The existing disguise table already tells the player whom to visit.

**Short correction:** remove the fake-password detour from the numbered route; make it a brief optional warning: “Damon may give a fake password. Use the table to find the disguised Janine.” This avoids suggesting a needless fight and a branch-specific result as universal.

Also shorten `06:116`: the Trainer Card statement is the MC's story explanation (763 @753), not a generated password mechanic. The exit dialogue always supplies 570819 (110 @1014/@5049/@5143), while the guards gate passage on learning it (1496 @869/@921, set @10157). Say **“You must uncover Janine to advance; knowing the number alone does not skip the trial.”** No new hack-bug record is warranted for this narrative framing.

### 6. Casey's battle can be lost; the reward still follows

**P2; high confidence.** `guide/07-league-to-cherrygrove.md:94` calls it a friendly battle “you can't lose.” File 225 @4135 uses `TrainerBattle [608,0,1,0]` and proceeds directly to the gift message @4143 and Electirizer item 322 @4148, without checking victory.

**Short correction:** “A friendly battle; win or lose, you receive an Electirizer. Losing does not white you out.” This matches the guide's language for other no-penalty battles.

### 7. Cerulean Cave's rematch description conflicts with its actual trainer data

**P2; high confidence for the configured teams.** `guide/07-league-to-cherrygrove.md:38` says Giovanni sends out Tyranitar and Mewtwo together, then correctly calls this two copies of his team. File 912 @2559 calls trainers 402+402. Trainer 402's first record in `a/0/5/6` is Mewtwo (species 150), followed by Tyranitar (248); both copies have the same ordering. The old errata explicitly mentioned two Mewtwo, but this sentence retained the earlier description.

**Short correction:** “Rematch: a Double Battle against two copies of Giovanni's team.” This avoids adding another team list and preserves the important loss/retry warning. No fresh runtime opening-battle capture was made.

### 8. The Saffron takeover checklist is incomplete and stronger than its detailed entries

**P2; high confidence for the omission; conditional wording already acknowledged by the guide.** `guide/04-celadon-fuchsia-saffron.md:535–540` omits Cerulean's burglary case. The takeover sets case-closed flag 1024 and grunt hide flag 1033, file 17 @12111/@12115; part 1 independently traced the consequences. Add a linked “Cerulean burglary case” deadline to this checklist, using part 1's wording.

The same list calls Cynthia/Steven's disappearance permanent without the qualification present at `04:284` (Soul Badge scene can clear their hide flag). Use **“Fuchsia Cynthia/Steven battles—finish these first; see their entry”**, or make the entire list a practical “Before making Sabrina laugh” checklist rather than a claim that every listed branch is irrevocably closed under every possible order.

## Earlier errata: current status and direct spot-checks

These corrections are already in the guide. Do not present them as outstanding defects or expand them further.

| Topic | Current status / evidence checked in this review |
|---|---|
| Tony/Mary loss completion | Present. Quest stage becomes 2 at 792 @1530, before the Rocket battle. Full price/retry routing was not re-proved. |
| Grandma's Master Ball deadline | Present. Saffron liberation unconditionally writes stage 5 at 834 @5994. |
| Dragonair delivery | Paxton victory requirement and two-road-biker threshold are present. Read the pairwise flag checks in 211 @519–1468 and Paxton's 1801 clear/set at 210 @1368/@1397. The delivery also checks 1689 @530; I did not establish normal-play relevance of this extra trainer flag, so do not claim the simplified condition is exhaustive. |
| Fuchsia trial, rangers' house, marathon, White Flute, Milotic, Super Rod | Old corrections are visibly incorporated: correct Maxie outcome, house, lineups, completion reward and trades. These whole chains were not independently retraced in this pass. |
| Silph employee's Lapras | Gift directly verified: 755 @3200 checks party capacity, @3245 gives species 131 at level 70. The current missability warning remains useful. |
| Articuno TM14 cutoff | Warning present. Rocket scene hides Articuno at 195 @957; later catch branch sets its hide flag at @2696. Full object/engine persistence proof inherited, not repeated. |
| Cinnabar lab route / Rotom-room guards / Three Island choice | Old corrections present. Collision route, all enemy parties and the full biker branching were not re-derived. |
| Graffiti couple loss | Present; irreversible flag 1742 is set at 812 @3390 before battle @3394. |
| Crystal Onix | One-chance warning present and supported: 24 @84 sets 2912 before WildBattle @88, loss branches to white-out @972. |
| Granny Mae's consecutive battles | No-heal warning present; Blue @782:4615 → Multi Battle @5001 → heal @5164. The quiz/reset instructions are incorporated; not all were re-traced. |
| Victory Road disguise table | Read all five relevant starter/gender branches and sampled their Route 11/ship checks; existing branch structure fits the table. No exhaustive emulator check or automated matrix test was run. Keep the table; simplify the instructions around it. |
| Shipyard Protector deadline | Present. Gauntlet completion clears rebuild NPC hide flag 2020 at 879 @2428. Dragon's Den disappearance reference retained from existing audit; not freshly map-tested. |
| Six Island trial / pilgrimage omission | Location and battle order are corrected. The final Seven Island check at 870 @1303–1370 really omits the Six Island trial counter, as the guide notes. |
| Deoxys / Kyogre retry | Current loss retry claims agree with battle checks: 943 @5002–5026 and 195 @2851–2879 set completion only after the loss branch. Do not confuse these with Crystal Onix's pre-battle flag. |
| Azure Flute blocker | Existing cautious warning supported: 942 @104 checks story stage >=4 before checking final-clear flag @117; HQ sets stage 4 at 31 @3316. Full normal-story reachability remains a runtime follow-up. |
| Final Hall of Fame / Mewtwo deadline | Existing distinction is correct and valuable. 822 @2458 sets 2261, @2470 hides Mewtwo, @2474/@2478 clear Moltres/Zapdos once in that block. No claim of repeated resets should return. |
| Rehabilitation, Momo, Nugget, Elm, confession conditions, photographers, Berry Pots | Earlier errata visibly incorporated. Not all behavior revalidated independently; retain existing evidence/limitations. |

## Cross-reference and concision recommendations

- Link the Five Island field trials directly to the Elder's quiz, then link the release to the Mew hunt. These three entries should form one clear sequence, not mutually contradictory “continued” chapters.
- Use the central romance entry in chapter 09 from chapters 04/06/07; the chapter 01 introduction is not the authoritative route description. Preserve local confession location and timing, and avoid repeating the entire partner-lock rules.
- Add a canonical Lance-at-home gift entry, shared with part 1. `06:412` links to chapter 01 for Jade Orb acquisition, but chapter 01 has no such entry; linking to a merely related chapter is insufficient.
- Make every row of the pilgrimage table (`06:244` onward) link to its exact trial. Replace “below” and whole-chapter links; no extra narrative is needed.
- Replace `06:336`'s “Ruins of Alph (another page)” with the actual continuation. Link the League HQ investigation table's leads (`07:255` onward) to their exact quest headings. This table is an excellent concise navigation hub once linked.
- Standardize “first Hall of Fame,” “post-Silver-Conference investigation,” and “final Hall of Fame.” Generic “post-game” currently describes several distinct story phases, notably the Seafoam investigation versus catching its legends.
- Remove maintenance history such as “Correction: the guide earlier…” from source paragraphs; put dated history in the errata. Keep the actual evidence offsets. Do not repeat coordinate proofs in player instructions.
- Shorten headings containing entire other chapter titles (“continues Saffron City to Cinnabar Island's…”). Put one precise continuation link in the opening sentence. Keep named rewards and missable warnings.
- The Three Island Protector reward is repeated at length in chapters 05 and 06. Retain the cutoff warning in both, but keep the full gauntlet/reward account in chapter 06.
- Consider making the fake-password anecdote, harmless shared-flag explanations and rhetorical battle dialogue folded context. Preserve all irreversible-choice warnings and party requirements.

## Remaining uncertainty

Not freshly resolved: Misty's post-date object visibility, the lab Mewtwo/Granny Mae story-counter interaction, exact reachability of Birch before the Rainbow Badge, pre-Soul-Badge Saffron takeover ordering, the clover scene's shared-flag reachability, the unusable Azure Flute branch in a full normal run, and the extra delivery check on flag 1689. Full map/collision, engine escape handling and all trainer teams remain outside this pass. No genuinely new suspected hack bug was established; findings above correct guide interpretation or inconsistent instructions, so no decision-register entries were added.
