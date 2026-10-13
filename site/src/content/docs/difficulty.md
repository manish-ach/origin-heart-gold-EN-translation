---
title: Difficulty settings
description: The optional level cap, the EXP sharing switch and the battle-item limit added to the English patch in rc7 (updated in rc8), and exactly when the level cap goes up.
---

From **rc7**, the English patch adds three optional difficulty settings: a **level cap** that follows your Gym progress, a switch that turns off **EXP sharing** for benched Pokémon, and a **battle-item limit** for Trainer battles. The original Chinese hack has none of them; they're extras of the English patch. With the level cap off and sharing on, EXP works exactly as in the original hack. The item setting starts on DEFAULT, which keeps the original hack's battle-item rules; ALL adds more medicine (see [Battle items](#battle-items-items)). In rc7 this setting was called LIMITED and was stricter than the original hack; rc8 renamed it and gave it the original rules.

## Turning the settings on

1. Open the menu in the field (X) and choose **OPTIONS**.
2. Press **L** or **R**, or tap the arrows at the bottom of the screen, to go to page **2/2**, headed **DIFFICULTY**. Holding **L** while you choose OPTIONS opens this page straight away.
3. Choose a value for each row:
   - **ITEMS:** DEFAULT or ALL (called LIMITED or ALL in rc7).
   - **SHARE:** ON or OFF.
   - **CAP:** OFF or ON.
4. Choose **CONFIRM** to apply your changes (on both Options pages), or **QUIT** or press **B** to throw them away.
5. **Save the game** to keep the settings. Confirming only changes them until you turn the game off; nothing is saved for you.

A new game, and a save from before rc7, starts with **ITEMS DEFAULT, SHARE ON, CAP OFF**. You can change any setting whenever you like outside battle. A battle that has already started keeps the settings and the cap it started with.

## The level cap (CAP)

With **CAP ON**, your Pokémon stop gaining EXP from battles, wild and Trainer alike, once they reach the level of the current cap. The cap depends on which Gyms you've beaten and is shown in the table below.

- **A Pokémon can reach the cap level, but not pass it.** At the cap it gets no more EXP from battles, and the game doesn't show an EXP message for it.
- **EXP over the cap is lost.** It isn't saved for later, and it doesn't go to your other Pokémon. When the cap goes up, a Pokémon starts again from where it stopped.
- **Nothing is taken away.** Pokémon already above the cap (for example one you caught, were given or raised before turning CAP ON) keep their level and EXP, and you can still use them in battle. They just don't gain any more EXP until the cap passes them.
- **EVs are still awarded.** A Pokémon at the cap still gets its EVs from the battle.
- **In battles with a partner,** the cap only applies to your own Pokémon.

### When the cap goes up

The cap is set by the **first Gym in this list that you haven't beaten yet**. The list follows the order you meet the Gym Leaders in this hack, which starts in Kanto with Brock.

| Next Gym you haven't beaten | Where | Level cap |
|---|---|---:|
| Brock (Boulder Badge) | Pewter City | **12** |
| Misty (Cascade Badge) | Cerulean City | **20** |
| Lt. Surge (Thunder Badge) | Vermilion City | **25** |
| Erika (Rainbow Badge) | Celadon City | **38** |
| Koga (Soul Badge) | Fuchsia City | **55** |
| Blaine (Volcano Badge) | Cinnabar Island | **65** |
| Sabrina (Marsh Badge) | Saffron City | **80** |
| Giovanni (Earth Badge) | Viridian City | **100** |
| Every Johto Gym, and after all Gyms | Johto | **100** |

In practice, **the cap stops limiting you once you've beaten Sabrina** (with every Kanto Gym before her also beaten): from then on it is 100, the normal maximum, for the rest of the game, all through Johto included.

- **The cap goes up after the Gym battle.** The battle against the Gym Leader still uses the old cap, so a Pokémon already at the cap gets no EXP from it. The new cap applies from your next battle.
- **Erika counts as beaten as soon as you win the battle against her in the Celadon Gym.** In this hack she hands over the Rainbow Badge only later, at a ceremony after the [stolen Gloom story](../guide/ch08-celadon/#celadon-city-the-stolen-gloom-story-chain-easy-to-get-stuck), but the cap rises to 55 right after your win.
- **The earliest Gym you haven't beaten decides.** Beating a later Gym first doesn't raise the cap past a Gym you skipped. For example, if you start the Saffron City takeover before you've beaten Koga, the cap stays at **55** until you go back and beat him, whatever else you beat in the meantime. Once you beat Koga, the cap jumps straight to the level for the next Gym you still haven't beaten.
- **The cap never goes down.** Beating more Gyms can only keep it the same or raise it.

### What the cap doesn't limit

- **Rare Candies** still raise a Pokémon's level as normal, even above the cap.
- **The Day Care** still raises the level of the Pokémon you leave there as normal, even above the cap.
- **Some battles aren't affected** by the cap or by the SHARE setting: the Safari Zone, the Bug-Catching Contest, the catching demonstration, battles in the Battle Frontier facilities, link battles with other players, and recorded battles you watch again. They keep the original rules.

## EXP sharing (SHARE)

In the original hack your whole party shares the EXP from every battle: the Pokémon that took part get the full amount, and Pokémon that stayed on the bench get half (see [Mechanics and controls](../mechanics/#automatic-exp-and-ev-sharing)).

- **SHARE ON** (the default) keeps that sharing.
- **SHARE OFF** gives **benched Pokémon no EXP and no EVs**, except a Pokémon holding an Exp. Share (see below). Only the Pokémon that took part in the battle gain anything, and each one still gets the same amount as before: switching sharing off doesn't hand the bench's share to the Pokémon that fought.
- A Pokémon **holding an Exp. Share** still shares with SHARE OFF: it gets the same EXP and EVs as it would with SHARE ON, whether or not it took part. The other benched Pokémon get nothing. (In rc7, SHARE OFF also switched the item off; this was fixed in rc8.)
- With **CAP ON** too, the Pokémon that took part, and an Exp. Share holder, still stop at the cap.

## Battle items (ITEMS)

- **DEFAULT** (the default): Trainer battles allow the same Bag items as the original Chinese hack: Berries, the Blue, Yellow and Red Flutes, and also Potion, Super Potion, the drinks, Heal Powder and Berry Juice. Other medicine is left out, as in the original.
- **ALL**: Trainer battles let you use a wider choice of battle items from the Bag, twenty more medicines than DEFAULT, including medicine the original hack doesn't offer in battle (see [Status medicine in battle](../guide/known-issues/#status-medicine-in-battle)).

In rc7 the first choice was called **LIMITED** and allowed only Berries and Flutes. That was stricter than the original hack, so rc8 renamed it DEFAULT and restored the original rules. The rule applies to Trainer battles only; the Safari Zone, the Bug-Catching Contest and the other special battles listed above keep their own rules.

Either way, held items, items your opponent uses, wild battles and using items outside battle work as in the original hack.

## Fixed in rc8

Two problems in rc7 are gone in rc8:

- **Story battles you're allowed to lose** (the ones where losing continues the story instead of sending you back to a Pokémon Center) now follow all three settings. In rc7 they ignored CAP and SHARE OFF: every Pokémon got EXP as if CAP were OFF and SHARE were ON, so your Pokémon could pass the cap, and the ITEMS setting did not apply either. Examples: Blue in **Pewter City**, just before Brock's Gym (and his battles in Oak's Lab, Cerulean City and on the S.S. Anne); Misty on Route 3, Red and Green, Bruno in the Pewter City Pokémon Center; several Team Rocket Executive and Giovanni battles, the Celadon Restaurant challengers and the Slowpoke Well battle against Jessie and James. Losing them still continues the story as before.
- **SHARE OFF no longer switches off a held Exp. Share.** The holder shares as with SHARE ON, and everyone else on the bench still gets nothing.

<details class="tech" data-pagefind-ignore="all">
<summary>Technical source (implementation and research files)</summary>

work/research/difficulty-armips/: IMPLEMENTATION.md; native/caps.c (dg_cap_resolve: guide-order badge ids 0,1,2,3,5,6,4,7,8,9,10,11,13,12,14,15; gym maxima 12,20,25,38,55,65,80,100,80,80,88,80,80,80,85,85; running maximum through the first unfinished row, 100 after all 16; Erika = badge 3 or flag 1220, Clair = badge 15 or flag 209); native/runtime.c (dg_battle_begin resolves the cap and copies the settings once per battle; dg_runtime_ordinary accepts setup flags 0, 1, 3, 0x13, 0x4A, 0x4B, 0x100 and, after rc7, 0x801 (loss-allowed trainer battles) with control 0, and scripted wild flags 0 / control 8; Safari 0x20, contest 0x1000, 0x200, tutorial 0x400, link 4, facility 0x80, replay control 0x10/0x18 and special control 1 are excluded); native/growth.c and research/growth.md (late per-recipient clamp to the species EXP threshold of the cap level, no banking, EVs unchanged, SHARE OFF zeroes benched EXP and EVs, local party IDs only); native/options.c (page labels, defaults, help text); native/settings.c (Options bits 15/3/5); research/progression.md, research/gym_schedule.json (D-2312); research/options-two-pages.md; research/items.md. CHANGELOG.md rc7. Rare Candy and Day Care exceptions: D-2304/D-2307.

</details>
