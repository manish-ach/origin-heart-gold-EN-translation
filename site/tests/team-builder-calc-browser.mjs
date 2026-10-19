// Damage calculator smoke flow (the Team Builder's calculator view and /damage-calc/). Same setup as
// team-builder-browser.mjs: run from the repo root with an existing Playwright installation and a built preview.
// Optional TEAM_BUILDER_SHOTS sets the screenshot folder.
import assert from 'node:assert/strict';
import { mkdirSync, writeFileSync } from 'node:fs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4346/poke/';
const output = process.env.TEAM_BUILDER_SHOTS || 'work/build/team-builder-qa';
mkdirSync(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
let checks = 0;
const check = (actual, expected, message) => { assert.deepEqual(actual, expected, message); checks++; };
const settleOn = page => page.evaluate(() => new Promise(resolve => setTimeout(resolve, 0)));
const lazy = /calc-data\.json|battle-data\.json|battle-check\./;
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
  const page = await context.newPage();
  const errors = [], requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('request', request => requests.push(request.url()));
  // Typed fields re-render just after focus moves on (setTimeout 0); wait for that before reading.
  const settle = () => page.evaluate(() => new Promise(resolve => setTimeout(resolve, 0)));
  const goto = async hash => {
    const response = await page.goto(new URL(`team-builder/${hash}`, base).href);
    if (response) check(response.status(), 200, 'planner loads');
    await page.locator('#team-builder[data-ready=true]').waitFor();
  };

  // The planner alone never requests the calculator's code or data.
  await goto('#team=3,94,196,6,25,149');
  await page.waitForLoadState('networkidle');
  check(requests.filter(url => lazy.test(url)), [], 'no calc bundle or data before the calculator opens');
  await page.locator('.tb-battle-entry').click();
  await page.locator('#tb-bc-query').waitFor();
  for (const file of ['calc-data.json', 'battle-data.json']) check(requests.some(url => url.includes(file)), true, `${file} loaded on open`);
  check(await page.locator('.tb-browse').isVisible(), false, 'battle view replaces the catalog');
  assert.match(page.url(), /&battle=$/); checks++;
  check(await page.locator('#tb-battle-body').getAttribute('aria-live'), null, 'the re-rendered panel is not a live region');

  // Route order: Pallet Town opens with early teams; rematches and post-game teams come later, by level.
  const groups = await page.locator('.tb-bc-group').allTextContents();
  check(groups[0], 'Pallet Town', 'first group');
  const firstLevels = await page.locator('.tb-bc-trainers li').evaluateAll(items => {
    const out = []; let group = 0;
    for (const li of items) { if (li.classList.contains('tb-bc-group')) { group++; continue; } if (group === 1) out.push(li.textContent); }
    return out;
  });
  check(firstLevels.every(text => [...text.matchAll(/Lv\. (\d+)/g)].every(m => Number(m[1]) <= 10)), true, 'Pallet Town has no high-level teams');

  // Typing in the search keeps focus and the caret; the count is announced by its own status line.
  await page.locator('#tb-bc-query').click();
  await page.keyboard.type('brock', { delay: 20 });
  check(await page.evaluate(() => document.activeElement?.id), 'tb-bc-query', 'focus stays in the search while typing');
  check(await page.locator('#tb-bc-query').inputValue(), 'brock', 'every keystroke kept');
  const brockGroups = await page.locator('.tb-bc-group').allTextContents();
  check(brockGroups[0], 'Pewter City', 'Brock’s first team is under Pewter City');
  check(brockGroups.includes('Rematches and later battles'), true, 'rematches in their own group');
  check(await page.locator('.tb-bc-trainer').first().getAttribute('data-bc-trainer'), '253', 'the Lv. 12 challenge comes first');
  await page.locator('#tb-bc-query').fill('');

  // Pick a trainer by search; route order puts Brock's challenge in Pewter City.
  await page.locator('#tb-bc-query').fill('brock pewter');
  assert.match(await page.locator('#tb-bc-count').textContent(), /teams? in route order/); checks++;
  await page.locator('[data-bc-trainer="253"]').click();
  assert.match(await page.locator('.tb-bc-foe-name').textContent(), /Brock/); checks++;
  assert.match(await page.locator('#tb-status').textContent(), /^Opponent: Leader Brock, Lv\. 12, 4 Pokémon\.$/); checks++;
  check(await page.locator('.tb-bc-foe-mon').count(), 4, 'Brock’s four Pokémon');
  assert.match(await page.locator('.tb-bc-foe-mon').first().textContent(), /Lv\. 12/); checks++;
  check(await page.locator('.tb-bc-grid tbody tr').count(), 6, 'overview: one row per team member');
  check(await page.locator('.tb-bc-cell').count(), 24, 'overview: 6 × 4 cells');
  const numbers = await page.locator('#tb-bc-matchup .tb-bc-numbers strong').first().textContent();
  assert.match(numbers, /^(\d+(\.\d)?–\d+(\.\d)?|>100)%$/); checks++;
  check((await page.locator('.tb-bc-cell strong').allTextContents()).every(text => /^(\d{1,3}(\.\d)?|>100)%$|^—$/.test(text)), true, 'grid percentages capped at >100%');
  const panelText = await page.locator('#tb-battle-body').textContent();
  check(/10\+ hits|more than 9 hits/.test(panelText), false, 'one no-KO phrase');
  assert.match(await page.locator('.tb-bc-suggested').first().textContent(), /strongest attacks by this level/); checks++;
  assert.match(await page.locator('.tb-bc-speed').textContent(), /moves first · Speed \d+ vs \d+/); checks++;
  check(await page.locator('#tb-bc-matchup .is-best').count() >= 1, true, 'best move highlighted');
  check(await page.locator('#tb-bc-matchup .is-unmodelled').count() >= 1, true, 'Magnitude shown as not calculated');
  assert.match(page.url(), /&battle=253$/); checks++;

  // A row reveals the description and 16 rolls.
  const row = page.locator('#tb-bc-matchup [data-bc-move]').first();
  await row.click();
  check(await row.getAttribute('aria-expanded'), 'true', 'row expands');
  const rolls = await page.locator('#tb-bc-matchup .tb-bc-rolls').first().textContent();
  check(rolls.replace(/^.*HP\)\s*/, '').split(',').length, 16, '16 damage rolls');

  // A grid cell opens that matchup and announces it.
  await page.locator('[data-bc-cell="94:3"]').click();
  check(await page.locator('[data-bc-cell="94:3"]').getAttribute('aria-pressed'), 'true', 'cell selected');
  assert.match(await page.locator('.tb-bc-versus').textContent(), /Gengar[\s\S]*Onix/); checks++;
  check(await page.locator('#tb-status').textContent(), 'Matchup: your Gengar against Onix.', 'matchup announced');

  // Opponent condition: Onix at half HP takes the same damage but is closer to a KO.
  const koBefore = await page.locator('#tb-bc-matchup .tb-bc-numbers span').first().textContent();
  await page.locator('.tb-bc-condition > summary').click();
  await page.locator('[data-bc-field="tfoe:hp"]').fill('20');
  await page.locator('[data-bc-field="tfoe:hp"]').press('Tab'); await settle();
  assert.match(await page.locator('.tb-bc-condition > summary').textContent(), /20% HP/); checks++;
  check(await page.locator('.tb-bc-condition').evaluate(d => d.open), true, 'condition panel stays open after the change');
  check(await page.evaluate(() => document.activeElement?.dataset?.bcField), 'tfoe:status', 'Tab moved on to the next field');
  check((await page.locator('#tb-bc-matchup .tb-bc-numbers span').first().textContent()) !== koBefore, true, 'KO chance follows the opponent’s HP');
  await page.locator('[data-bc-field="tfoe:boost:def"]').selectOption('2');
  assert.match(await page.locator('.tb-bc-condition > summary').textContent(), /Def \+2/); checks++;
  await page.locator('[data-bc-field="tfoe:hp"]').fill('100'); await page.locator('[data-bc-field="tfoe:hp"]').press('Tab'); await settle();
  await page.locator('[data-bc-field="tfoe:boost:def"]').selectOption('0');
  await page.locator('.tb-bc-condition > summary').click();

  // Default level 12 for Gengar: the set summary says when it usually evolves.
  assert.match(await page.locator('#tb-bc-set > summary').textContent(), /Gengar usually evolves at Lv\. 25 or later/); checks++;

  // Edit set: level and a move; saved in the link.
  await page.locator('#tb-bc-set > summary').click();
  // An EV field keeps focus across the re-render (Tab moves on normally); more than 510 in total is refused.
  await page.locator('[data-bc-details="mine-advanced"] > summary').click();
  await page.locator('[data-bc-field="mine:ev:atk"]').fill('252');
  await page.locator('[data-bc-field="mine:ev:atk"]').press('Tab'); await settle();
  check(await page.evaluate(() => document.activeElement?.dataset?.bcField), 'mine:ev:def', 'focus moves to the next EV field');
  check(await page.locator('[data-bc-details="mine-advanced"]').evaluate(d => d.open), true, 'Advanced stays open');
  await page.locator('[data-bc-field="mine:ev:spa"]').fill('252');
  await page.locator('[data-bc-field="mine:ev:spa"]').press('Tab'); await settle();
  await page.locator('[data-bc-field="mine:ev:spe"]').fill('252');
  await page.locator('[data-bc-field="mine:ev:spe"]').press('Tab'); await settle();
  check(await page.locator('[data-bc-field="mine:ev:spe"]').getAttribute('aria-invalid'), 'true', 'EV total over 510 refused');
  await page.locator('[data-bc-field="mine:ev:atk"]').fill('0'); await page.locator('[data-bc-field="mine:ev:atk"]').press('Tab'); await settle();
  await page.locator('[data-bc-field="mine:ev:spa"]').fill('0'); await page.locator('[data-bc-field="mine:ev:spa"]').press('Tab'); await settle();
  await page.locator('[data-bc-details="mine-advanced"] > summary').click();
  await page.locator('[data-bc-field="mine:level"]').fill('40');
  await page.locator('[data-bc-field="mine:level"]').press('Tab'); await settle();
  assert.match(await page.locator('.tb-bc-versus').textContent(), /Lv\. 40/); checks++;
  await page.locator('[data-bc-field="mine:move0"]').fill('Thunderbolt');
  await page.locator('[data-bc-field="mine:move0"]').press('Tab'); await settle();
  assert.match(await page.locator('#tb-bc-matchup').textContent(), /Thunderbolt/); checks++;
  assert.match(page.url(), /sets=94\.L40\.M85/); checks++;
  await page.locator('[data-bc-field="mine:move1"]').fill('Fly');
  await page.locator('[data-bc-field="mine:move1"]').press('Tab'); await settle();
  check(await page.locator('[data-bc-field="mine:move1"]').getAttribute('aria-invalid'), 'true', 'unlearnable move rejected');

  // Field: forcing critical hits changes the numbers.
  // (Compared on the exact damage in the move details: Lv. 40 Gengar against Lv. 12 Onix shows ">100%" either way.)
  const exact = () => page.locator('#tb-bc-matchup .is-best .tb-bc-move-detail').first().textContent();
  const before = await exact();
  assert.match(before, /Damage: \d+–\d+ HP of \d+/); checks++;
  await page.locator('#tb-bc-field > summary').click();
  await page.locator('[data-bc-global="crit"]').check();
  check((await exact()) !== before, true, 'crit toggle recalculates');
  check(await page.evaluate(() => document.activeElement?.dataset?.bcGlobal), 'crit', 'focus kept on the checkbox');
  await page.locator('[data-bc-global="crit"]').uncheck();
  // Spread moves: only for double battles.
  check(await page.locator('[data-bc-global="spread"]').isDisabled(), true, 'spread control off in a single battle');
  await page.locator('[data-bc-global="format"]').selectOption('Doubles');
  check(await page.locator('[data-bc-global="spread"]').isDisabled(), false, 'spread control in a double battle');
  await page.locator('[data-bc-global="spread"]').selectOption('1');
  assert.match(await page.locator('#tb-bc-field > summary').textContent(), /spread moves hit one/); checks++;
  await page.locator('[data-bc-global="spread"]').selectOption('');
  await page.locator('[data-bc-global="format"]').selectOption('');
  // Hail: the "checked in game" note is listed in each move's details.
  await page.locator('[data-bc-global="weather"]').selectOption('Hail');
  await page.locator('#tb-bc-matchup [data-bc-move]').first().click();
  assert.match(await page.locator('#tb-bc-matchup .tb-bc-move-detail:not([hidden]) .tb-bc-notes').first().textContent(), /Hail here works like Snow.*checked in game/); checks++;
  await page.locator('[data-bc-global="weather"]').selectOption('');

  // Showdown export then import of the whole team.
  await page.locator('#tb-bc-io > summary').click();
  await page.locator('#tb-bc-import').fill('Sparky (Raichu-Alola) @ Life Orb\nLevel: 20\nTimid Nature\n- Thunderbolt\n\nPikachoo\n- Tackle');
  await page.locator('[data-bc-import]').click();
  assert.match(await page.locator('#tb-bc-io-result').textContent(), /Unknown Pokémon “Pikachoo”/); checks++;
  check(await page.locator('#tb-slots [data-select]').count(), 6, 'a failed import changes nothing');

  // Custom opponent: changing its level updates its suggested moves at once.
  await page.locator('#tb-bc-foe [data-bc-change]').click();
  await page.locator('[data-bc-any]').click();
  await page.locator('[data-bc-foe-species]').fill('Charizard');
  await page.locator('[data-bc-foe-species]').press('Tab'); await settle();
  check(await page.locator('#tb-status').textContent(), 'Opponent: Charizard.', 'custom opponent announced');
  await page.locator('[data-bc-field="foe:level"]').fill('5');
  await page.locator('[data-bc-field="foe:level"]').press('Tab'); await settle();
  const low = await page.locator('[data-bc-field="foe:move0"]').inputValue();
  await page.locator('[data-bc-field="foe:level"]').fill('60');
  await page.locator('[data-bc-field="foe:level"]').press('Tab'); await settle();
  check((await page.locator('[data-bc-field="foe:move0"]').inputValue()) !== low, true, 'opponent moves follow its level');
  check(await page.evaluate(() => document.activeElement?.dataset?.bcField), 'foe:nature', 'focus kept after the re-render');
  assert.match(await page.locator('.tb-bc-versus').textContent(), /Charizard\s*Lv\. 60/); checks++;
  // Unknown species in a link: a message and the picker, not a blank opponent.
  await page.evaluate(() => { location.hash = '#battle=free&foe=99999'; });
  await page.locator('#tb-bc-query').waitFor();
  check(await page.locator('#tb-status').textContent(), 'That Pokémon couldn’t be found. Pick an opponent below.', 'unknown species reported');
  await page.locator('[data-bc-trainer="253"]').click();

  // Reload keeps the state; a deep link selects another trainer.
  await page.reload(); await page.locator('.tb-bc-foe-name').waitFor();
  assert.match(await page.locator('.tb-bc-foe-name').textContent(), /Brock/); checks++;
  await goto('#battle=255'); await page.locator('.tb-bc-foe-name').waitFor();
  assert.match(await page.locator('.tb-bc-foe-name').textContent(), /Surge/); checks++;
  check(await page.locator('#tb-slots [data-select]').count(), 6, 'deep link keeps the saved team');

  // Trainer pages link to the standalone calculator, which shows the Team Builder's saved team.
  await page.goto(new URL('trainers/records/253/', base).href);
  const calcLink = page.locator('a.calc-link[href$="damage-calc/#battle=253"]').first();
  check((await calcLink.textContent()).replace(/\s+/g, ' ').trim(), 'Damage calc →', 'trainer page link text');
  await calcLink.click();
  await page.locator('.tb-bc-foe-name').waitFor();
  assert.match(await page.locator('.tb-bc-foe-name').textContent(), /Brock/); checks++;
  check(await page.locator('.tb-bc-member-pick').count(), 6, 'the same team as the Team Builder');
  check(await page.locator('.tb-credit a[href$="licenses/smogon-damage-calc.txt"]').count(), 1, 'licence linked on the calculator page');
  await page.goto(new URL('team-builder/', base).href); await page.locator('#team-builder[data-ready=true]').waitFor();

  // The MIT licence is linked from the credit line.
  const licence = await page.locator('.tb-credit a[href$="licenses/smogon-damage-calc.txt"]').getAttribute('href');
  check((await page.request.get(new URL(licence, page.url()).href)).status(), 200, 'licence file served');

  // Screenshots and layout with the default sets (fresh browser): Brock's first team and Whitney, desktop and
  // mobile (390 and 360 px), light and dark.
  const shots = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await shots.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
  const shot = await shots.newPage();
  shot.on('pageerror', error => errors.push(error.message));
  for (const [trainer, name] of [[253, 'brock'], [714, 'whitney']]) {
    await shot.setViewportSize({ width: 1440, height: 1000 });
    await shot.goto(new URL(`team-builder/#team=3,94,196,6,25,149&battle=${trainer}`, base).href);
    await shot.locator('.tb-bc-foe-name').waitFor();
    for (const [width, height] of [[1440, 1000], [390, 844], [360, 740]]) for (const theme of ['light', 'dark']) {
      await shot.setViewportSize({ width, height });
      await shot.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
      if (width < 1184) await shot.locator('.tb-mobile-nav [data-view="battle"]').click();
      check(await shot.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `${name} ${width}px ${theme}: no page overflow`);
      await shot.locator('.tb-battle').scrollIntoViewIfNeeded();
      await shot.locator('.tb-battle').screenshot({ path: `${output}/battle-${name}-${width < 1184 ? `mobile${width}` : 'desktop'}-${theme}.png` });
    }
  }
  await shots.close();

  // Slamanander's prep loop (Discord, 2026-10-19): open Falkner from his trainer page, then change the team and
  // both sides' sets without ever leaving the fight. Desktop and phone width, on /damage-calc/ and the Team Builder.
  for (const [width, height] of [[1440, 1000], [390, 844]]) {
    const tag = width < 1184 ? 'mobile' : 'desktop';
    const ctx = await browser.newContext({ viewport: { width, height } });
    await ctx.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
    const p = await ctx.newPage();
    p.on('pageerror', error => errors.push(error.message));
    const wait = () => p.evaluate(() => new Promise(resolve => setTimeout(resolve, 0)));
    const typeIn = async (selector, value) => { await p.locator(selector).fill(value); await p.locator(selector).press('Tab'); await wait(); };
    const foeName = () => p.locator('.tb-bc-foe-name').textContent();
    // Venusaur, Butterfree, Espeon, Charizard: saved by the Team Builder.
    await p.goto(new URL('team-builder/#team=3,12,196,6', base).href); await p.locator('#team-builder[data-ready=true]').waitFor();
    await p.goto(new URL('trainers/records/20/', base).href);
    await p.locator('details:has(a.calc-link[href$="damage-calc/#battle=20"])').first().evaluate(d => { d.open = true; });
    await p.locator('a.calc-link[href$="damage-calc/#battle=20"]').first().click();
    await p.locator('.tb-bc-foe-name').waitFor();
    assert.match(await foeName(), /Falkner/); checks++;
    const trainerPage = new URL('trainers/records/20/', base).href;

    // Swap Butterfree for Gyarados: same slot, Falkner stays, Gyarados is selected with its set editor open.
    await p.locator('[data-bc-swap="12"]').click();
    check(await p.evaluate(() => document.activeElement?.id), 'tb-bc-member-query', `${tag}: the swap search has focus`);
    await p.locator('#tb-bc-member-query').fill('gyara');
    await p.locator('[data-bc-join="130"]').click();
    assert.match(await foeName(), /Falkner/); checks++;
    check(await p.locator('[data-bc-member="130"]').getAttribute('aria-pressed'), 'true', `${tag}: Gyarados selected`);
    check(await p.locator('#tb-bc-set').evaluate(d => !d.hidden && d.open), true, `${tag}: Gyarados’s set editor is open`);
    assert.match(await p.locator('#tb-bc-set > summary').textContent(), /Edit Gyarados’s set/); checks++;
    assert.match(p.url(), /#team=3,130,196,6&battle=20$/); checks++;
    check(await p.locator('#tb-status').textContent(), 'Butterfree swapped for Gyarados. The opponent is unchanged.', `${tag}: swap announced`);

    // Add a fifth (Lapras) and give it Leftovers: saved in the link, still against Falkner.
    await p.locator('[data-bc-add]').click();
    await p.locator('#tb-bc-member-query').fill('lapras');
    await p.locator('[data-bc-join="131"]').click();
    check(await p.locator('.tb-bc-member-pick').count(), 5, `${tag}: five members`);
    check(await p.locator('.tb-bc-grid tbody tr').count(), 5, `${tag}: the overview follows`);
    await typeIn('[data-bc-field="mine:item"]', 'Leftovers');
    assert.match(await p.locator('#tb-bc-set > summary').textContent(), /Edit Lapras’s set[\s\S]*Leftovers/); checks++;
    assert.match(p.url(), /#team=3,130,196,6,131&sets=131\.I\d+&battle=20$/); checks++;
    assert.match(await foeName(), /Falkner/); checks++;

    // Edit Falkner's Staraptor: Life Orb instead of Choice Band changes its damage; this visit only, not in the link.
    const theirs = () => p.locator('#tb-bc-matchup section[aria-label="Their moves"]').textContent();
    const before = await theirs();
    await p.locator('[data-bc-details="tfoe-set"] > summary').click();
    await typeIn('[data-bc-field="tfoe:item"]', 'Life Orb');
    check(await p.locator('[data-bc-field="tfoe:item"]').getAttribute('aria-invalid') !== 'true', true, `${tag}: item accepted`);
    assert.match(await p.locator('[data-bc-foe="0"].tb-bc-foe-mon').textContent(), /Staraptor\s*Edited[\s\S]*Life Orb/); checks++;
    check(await p.locator('.tb-bc-colhead[data-bc-foe="0"] .tb-bc-edited').count(), 1, `${tag}: Edited in the overview`);
    check((await theirs()) !== before, true, `${tag}: Staraptor’s damage follows its item`);
    check(await p.locator('[data-bc-details="tfoe-set"]').evaluate(d => d.open), true, `${tag}: the foe editor stays open`);
    // A move outside its learnset and EVs above 510 are accepted (trainers have both), with a note.
    await typeIn('[data-bc-field="tfoe:move3"]', 'Earthquake');
    check(await p.locator('[data-bc-field="tfoe:move3"]').getAttribute('aria-invalid') !== 'true', true, `${tag}: any move for a trainer`);
    assert.match(await p.locator('[data-bc-details="tfoe-set"] .tb-bc-moves-edit small').textContent(), /Outside its usual learnset: .*Earthquake/); checks++;
    assert.match(await theirs(), /Earthquake/); checks++;
    await typeIn('[data-bc-field="tfoe:move3"]', 'U-turn');
    assert.match(p.url(), /&battle=20$/); checks++;
    check(await p.locator('#tb-bc-set').isVisible(), true, `${tag}: your set editor is still there`);
    // Reset restores the game data; then edit again for the history check below.
    await p.locator('[data-bc-reset-foe]').click();
    check(await p.locator('.tb-bc-foe .tb-bc-edited, #tb-bc-foe .tb-bc-edited').count(), 0, `${tag}: reset clears Edited`);
    assert.match(await p.locator('[data-bc-foe="0"].tb-bc-foe-mon').textContent(), /Choice Band/); checks++;
    await p.locator('[data-bc-details="tfoe-set"] > summary').evaluate(s => { s.parentElement.open = true; });
    await typeIn('[data-bc-field="tfoe:item"]', 'Life Orb');

    // Another opponent adds a history entry: Back returns to Falkner (edits kept for this visit), not the trainer page.
    await p.locator('#tb-bc-foe [data-bc-change]').click();
    await p.locator('#tb-bc-query').fill('bugsy azalea');
    await p.locator('.tb-bc-trainer').first().click();
    assert.match(await foeName(), /Bugsy/); checks++;
    await p.goBack(); await p.waitForFunction(() => /Falkner/.test(document.querySelector('.tb-bc-foe-name')?.textContent ?? ''));
    assert.match(p.url(), /damage-calc\/#team=3,130,196,6,131&sets=131\.I\d+&battle=20$/); checks++;
    check(await p.locator('.tb-bc-member-pick').count(), 5, `${tag}: Back keeps the current team`);
    assert.match(await p.locator('[data-bc-foe="0"].tb-bc-foe-mon').textContent(), /Edited[\s\S]*Life Orb/); checks++;
    await p.goBack(); await p.waitForURL(trainerPage);
    checks++;

    // The same loop in the Team Builder: its empty slot fills from the calculator's picker, and Back goes back
    // through the opponents to the planner view the calculator was opened from.
    // (Starting without a saved opponent, so the calculator opens on the trainer picker.)
    await p.evaluate(() => { const v = JSON.parse(localStorage.getItem('ohg-team-builder-v2')); v.opponent = null; localStorage.setItem('ohg-team-builder-v2', JSON.stringify(v)); });
    await p.goto(new URL('team-builder/#team=3,12,196,6', base).href); await p.locator('#team-builder[data-ready=true]').waitFor();
    await p.locator(width < 1184 ? '.tb-mobile-nav [data-view="battle"]' : '.tb-battle-entry').click();
    await p.locator('#tb-bc-query').fill('falkner violet');
    await p.locator('[data-bc-trainer="20"]').click();
    assert.match(await foeName(), /Falkner/); checks++;
    await p.locator('#tb-slots [data-empty]').first().click();
    check(await p.locator('#team-builder').getAttribute('data-view'), 'battle', `${tag}: an empty slot keeps the calculator open`);
    check(await p.evaluate(() => document.activeElement?.id), 'tb-bc-member-query', `${tag}: and opens its picker`);
    await p.locator('#tb-bc-member-query').fill('lapras');
    await p.locator('[data-bc-join="131"]').click();
    await p.locator('[data-bc-swap="12"]').click();
    await p.locator('#tb-bc-member-query').fill('gyara');
    await p.locator('[data-bc-join="130"]').click();
    check(await p.locator('#tb-slots [data-select]').count(), 5, `${tag}: the planner’s slots follow`);
    check(await p.locator('#tb-bc-set').evaluate(d => !d.hidden && d.open), true, `${tag}: set editor open after the swap`);
    assert.match(p.url(), /team-builder\/#team=3,130,196,6,131&battle=20$/); checks++;
    await p.goBack(); await p.locator('#tb-bc-query').waitFor();
    assert.match(p.url(), /#team=3,130,196,6,131&battle=$/); checks++;
    await p.goBack(); await p.waitForFunction(() => document.querySelector('#team-builder')?.dataset.view === 'browse');
    assert.match(p.url(), /team-builder\/#team=3,130,196,6,131$/); checks++;
    check(await p.locator('#tb-slots [data-select]').count(), 5, `${tag}: Back keeps the team`);
    await ctx.close();
  }

  // Both pages share the saved team. Back, reload and a second tab never bring an older team back.
  {
    const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await ctx.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
    const p = await ctx.newPage();
    p.on('pageerror', error => errors.push(error.message));
    const stored = page => page.evaluate(() => JSON.parse(localStorage.getItem('ohg-team-builder-v2')).team);
    const slots = page => page.locator('#tb-slots [data-select]').evaluateAll(b => b.map(x => Number(x.dataset.select)));
    const members = page => page.locator('.tb-bc-member-pick').evaluateAll(b => b.map(x => Number(x.dataset.bcMember)));
    await p.goto(new URL('team-builder/#team=3,12,196,6', base).href); await p.locator('#team-builder[data-ready=true]').waitFor();
    await p.locator('.tb-battle-entry').click();
    await p.locator('#tb-bc-query').fill('falkner violet'); await p.locator('[data-bc-trainer="20"]').click();
    assert.match(await p.locator('#tb-open-calc').getAttribute('href'), /damage-calc\/#battle=20$/); checks++;
    await p.locator('#tb-open-calc').click(); await p.locator('.tb-bc-foe-name').waitFor();
    await p.locator('[data-bc-swap="12"]').click(); await p.locator('#tb-bc-member-query').fill('gyara'); await p.locator('[data-bc-join="130"]').click();
    check(await p.locator('#tb-builder-link').getAttribute('href'), '/poke/team-builder/', 'the Team Builder link relies on the saved team');
    await p.goBack(); await p.locator('#team-builder[data-ready=true]').waitFor();
    await p.waitForFunction(() => document.querySelector('[data-select="130"]'));
    check(await slots(p), [3, 130, 196, 6], 'Back to the Team Builder shows the swap made in the calculator');
    check(await stored(p), [3, 130, 196, 6], 'and storage keeps it');
    assert.match(p.url(), /#team=3,130,196,6/); checks++;
    await p.reload(); await p.locator('#team-builder[data-ready=true]').waitFor();
    check(await slots(p), [3, 130, 196, 6], 'reload keeps the newest team');
    // A shared link still wins over the saved team.
    await p.goto('about:blank'); await p.goto(new URL('team-builder/#team=25,6', base).href); await p.locator('#team-builder[data-ready=true]').waitFor();
    check(await slots(p), [25, 6], 'a newly opened shared link wins');
    // Two tabs: a change in one shows in the other (team, link), and the other doesn't write its old team back.
    await p.goto('about:blank'); await p.goto(new URL('team-builder/#team=3,12,196,6', base).href); await p.locator('#team-builder[data-ready=true]').waitFor();
    const q = await ctx.newPage();
    q.on('pageerror', error => errors.push(error.message));
    await q.goto(new URL('damage-calc/#battle=20', base).href); await q.locator('.tb-bc-foe-name').waitFor();
    await q.locator('[data-bc-remove="12"]').click();
    await p.waitForFunction(() => !document.querySelector('#tb-slots [data-select="12"]'));
    check(await slots(p), [3, 196, 6], 'the other tab’s Team Builder follows');
    assert.match(p.url(), /#team=3,196,6$/); checks++;
    await p.locator('.tb-battle-entry').click(); await p.locator('#tb-bc-team').waitFor();
    check(await stored(q), [3, 196, 6], 'opening its calculator doesn’t write the old team back');
    await p.locator('#tb-slots [data-remove="196"]').click();
    await q.waitForFunction(() => !document.querySelector('[data-bc-member="196"]'));
    check(await members(q), [3, 6], 'the calculator tab follows');
    assert.match(q.url(), /damage-calc\/#team=3,6&battle=20$/); checks++;
    await q.close();
    // A swap picker whose member leaves the team elsewhere turns into "Add".
    await p.goto(new URL('team-builder/#team=3,12,196,6&battle=20', base).href); await p.locator('.tb-bc-foe-name').waitFor();
    await p.locator('[data-bc-swap="12"]').click();
    await p.locator('#tb-slots [data-remove="12"]').click();
    check(await p.locator('#tb-bc-member-query').getAttribute('placeholder'), 'Add a Pokémon…', 'the swap picker becomes an add picker');
    await p.locator('#tb-bc-member-query').fill('gyara'); await p.locator('[data-bc-join="130"]').click();
    check(await p.locator('#tb-status').textContent(), 'Gyarados added. 4 of 6 slots filled.', 'no swap announced');
    // The search count is announced through the status line.
    await p.locator('[data-bc-add]').click(); await p.locator('#tb-bc-member-query').fill('pikach');
    assert.match(await p.locator('#tb-status').textContent(), /^\d+ Pokémon you can get in this game$/); checks++;
    await p.locator('[data-bc-member-cancel]').click();
    // A move it already knows is refused, in both editors.
    await p.locator('#tb-bc-set').evaluate(d => { d.open = true; });
    const known = await p.locator('[data-bc-field="mine:move0"]').inputValue();
    await p.locator('[data-bc-field="mine:move1"]').fill(known); await p.locator('[data-bc-field="mine:move1"]').press('Tab'); await settleOn(p);
    check(await p.locator('[data-bc-field="mine:move1"]').getAttribute('aria-invalid'), 'true', 'duplicate own move refused');
    assert.match(await p.locator('#tb-status').textContent(), /already knows/); checks++;
    await p.locator('[data-bc-details="tfoe-set"] > summary').click();
    const theirMove = await p.locator('[data-bc-field="tfoe:move0"]').inputValue();
    await p.locator('[data-bc-field="tfoe:move1"]').fill(theirMove); await p.locator('[data-bc-field="tfoe:move1"]').press('Tab'); await settleOn(p);
    check(await p.locator('[data-bc-field="tfoe:move1"]').getAttribute('aria-invalid'), 'true', 'duplicate foe move refused');
    check(await p.locator('#tb-status').textContent(), `Staraptor already knows ${theirMove}.`, 'duplicate foe move announced');
    await ctx.close();
  }

  // Screenshots: /damage-calc/ (opponent picker and Falkner) and the Team Builder's calculator, desktop and 390 px.
  const calcShots = process.env.DAMAGE_CALC_SHOTS || output;
  mkdirSync(calcShots, { recursive: true });
  for (const [width, height] of [[1440, 1000], [390, 844]]) {
    const tag = width < 1184 ? 'mobile390' : 'desktop';
    const ctx = await browser.newContext({ viewport: { width, height } });
    await ctx.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
    const p = await ctx.newPage();
    p.on('pageerror', error => errors.push(error.message));
    await p.goto(new URL('damage-calc/#team=3,12,196,6', base).href);
    await p.locator('#tb-bc-query').waitFor();
    check(await p.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `damage-calc ${tag}: no page overflow`);
    await p.screenshot({ path: `${calcShots}/damage-calc-picker-${tag}.png`, fullPage: true });
    await p.locator('#tb-bc-query').fill('falkner violet');
    await p.locator('[data-bc-trainer="20"]').click();
    await p.locator('[data-bc-swap="12"]').click();
    await p.locator('#tb-bc-member-query').fill('gy');
    check(await p.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `damage-calc ${tag}: no overflow with the member picker`);
    await p.screenshot({ path: `${calcShots}/damage-calc-falkner-swap-${tag}.png`, fullPage: true });
    await p.locator('[data-bc-join="130"]').click();
    await p.locator('[data-bc-details="tfoe-set"] > summary').click();
    await p.locator('[data-bc-field="tfoe:item"]').fill('Life Orb'); await p.locator('[data-bc-field="tfoe:item"]').press('Tab');
    await p.evaluate(() => new Promise(resolve => setTimeout(resolve, 0)));
    check(await p.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false, `damage-calc ${tag}: no overflow with the foe editor`);
    await p.screenshot({ path: `${calcShots}/damage-calc-falkner-edited-${tag}.png`, fullPage: true });
    await p.goto(new URL('team-builder/#team=3,130,196,6&battle=20', base).href);
    await p.locator('.tb-bc-foe-name').waitFor();
    await p.locator('.tb-battle').screenshot({ path: `${calcShots}/team-builder-battle-${tag}.png` });
    await p.screenshot({ path: `${calcShots}/team-builder-battle-page-${tag}.png`, fullPage: true });
    await ctx.close();
  }

  // Old v1 storage still loads.
  const old = await browser.newContext();
  await old.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
  await old.addInitScript(() => { if (!sessionStorage.getItem('seeded')) { localStorage.clear(); localStorage.setItem('ohg-team-builder-v1', '[3,94]'); sessionStorage.setItem('seeded', '1'); } });
  const op = await old.newPage(); await op.goto(new URL('team-builder/', base).href);
  await op.locator('#team-builder[data-ready=true]').waitFor();
  check(await op.locator('#tb-slots [data-select]').count(), 2, 'v1 saved team migrates');
  check(JSON.parse(await op.evaluate(() => localStorage.getItem('ohg-team-builder-v2'))).team, [3, 94], 'saved as v2');
  await old.close();

  check(errors, [], 'no uncaught errors');
  writeFileSync(`${output}/battle-check-results.json`, JSON.stringify({ checks, errors }, null, 2));
  console.log(`Damage calculator: ${checks} browser checks passed.`);
} finally { await browser.close(); }
