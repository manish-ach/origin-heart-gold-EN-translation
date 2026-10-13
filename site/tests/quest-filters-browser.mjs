// Run from the repo root against a built site served locally. Uses an existing Playwright install.
// PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs GUIDE_PREVIEW_URL=http://127.0.0.1:4337/ node site/tests/quest-filters-browser.mjs
import assert from 'node:assert/strict';
import { mkdirSync } from 'node:fs';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4337/';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
await context.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
const page = await context.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const go = path => page.goto(new URL(`guide/${path}/`, base).href, { waitUntil: 'networkidle' });
const CH1 = 'ch01-first-badge';
const visible = () => page.locator('section.quest:not(.is-hidden)').evaluateAll(quests => quests.map(q => ({ id: q.querySelector('h2').id, ...q.dataset })));
const choose = (name, value) => page.locator(`.game-setup [name=${name}]`).selectOption(value);
const output = 'work/build/quest-tags-qa';
mkdirSync(output, { recursive: true });
try {
  // Chapter 1: every quest has a type tag, and the filters combine and persist.
  await go(CH1);
  const total = (await visible()).length;
  assert.ok(total >= 15);
  assert.equal(await page.locator('section.quest .tag-main, section.quest .tag-side').count(), total);
  assert.equal(await page.locator('[name=progress]').count(), 0); // chapters replaced the Progress filter
  await choose('kind', 'side');
  assert.ok((await visible()).every(q => q.kind === 'side'));
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await page.locator('[name=kind]').inputValue(), 'side');
  await choose('kind', '');
  await choose('starter', 'Pikachu');
  let quests = await visible();
  assert.ok(quests.length > 0 && quests.every(q => !q.starter || q.starter.includes('Pikachu')));
  await choose('starter', '');

  // The warning box lists what the step closes; ticking the quest done hides the box.
  const warning = page.locator('.chapter-warning', { has: page.locator('li[data-quest-id="q-0001"]') }).first();
  assert.equal(await warning.isVisible(), true);
  await page.locator('section.quest[data-quest-id="q-0001"] .quest-tools input').check();
  assert.equal(await warning.isVisible(), false);
  assert.equal(await page.locator('li.chapter-quest[data-quest-id="q-0001"].is-done').count() > 0, true);
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal(await warning.isVisible(), false); // remembered
  await page.locator('section.quest[data-quest-id="q-0001"] .quest-tools input').uncheck();
  assert.equal(await warning.isVisible(), true);
  // A warning about a quest the player's starter can't get also disappears.
  const thief = page.locator('.chapter-warning li[data-starter]').first();
  if (await thief.count()) {
    const starter = (await thief.getAttribute('data-starter')).split(',')[0];
    const other = ['Charmander', 'Pikachu', 'Bulbasaur'].find(x => x !== starter);
    await choose('starter', other);
    assert.equal(await thief.isVisible(), (await thief.getAttribute('data-starter')).split(',').includes(other));
    await choose('starter', '');
  }

  // Done ticks and Hide finished.
  const first = page.locator('section.quest:not(.is-hidden)').first();
  const doneId = await first.locator('h2').getAttribute('id');
  await first.locator('.quest-tools input').check();
  await page.locator('[name=hidedone]').check();
  assert.ok(!(await visible()).some(q => q.id === doneId));
  await page.reload({ waitUntil: 'networkidle' });
  assert.ok(!(await visible()).some(q => q.id === doneId));
  await page.locator('[name=hidedone]').uncheck();

  // A direct link overrides every filter, and hash changes reapply filters.
  await choose('kind', 'main');
  const sideId = await page.locator('section.quest[data-kind=side] h2').first().getAttribute('id');
  await page.evaluate(id => { location.hash = id; }, sideId);
  await page.waitForFunction(id => !document.getElementById(id).closest('section').classList.contains('is-hidden'), sideId);
  assert.match(await page.locator('.hidden-count').innerText(), /linked quest stays visible/);
  await page.evaluate(() => { location.hash = ''; });
  await page.waitForFunction(id => document.getElementById(id).closest('section').classList.contains('is-hidden'), sideId);
  await choose('kind', '');

  // Malformed saved values fall back to all quests; the old Progress setting is ignored.
  await page.evaluate(() => localStorage.setItem('ohg:setup', JSON.stringify({ kind: 'invalid', progress: 'postgame', postgame: false })));
  await page.reload({ waitUntil: 'networkidle' });
  assert.equal((await visible()).length, total);
  assert.equal(await page.locator('[name=kind]').inputValue(), '');

  // Post-game chapters carry the Post-game tag.
  await go('ch33-postgame-lances-visit-seized-items');
  assert.ok(await page.locator('.tag-postgame').count() > 0);

  // Old region URLs forward to the chapter that now holds the quest, anchor included.
  await page.goto(new URL('guide/pallet-to-pewter/#viridian-forest-the-honey-tree-weekday-bug-pokémon', base).href, { waitUntil: 'networkidle' });
  await page.waitForURL(/ch\d\d-[a-z0-9-]+\/#viridian-forest-the-honey-tree/);

  // Mobile controls in both themes.
  await go(CH1);
  for (const [width, theme] of [[1440, 'dark'], [390, 'light'], [390, 'dark']]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.evaluate(theme => { document.documentElement.dataset.theme = theme; }, theme);
    await page.locator('.game-setup').scrollIntoViewIfNeeded();
    const layout = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth,
      controls: [...document.querySelectorAll('.game-setup select')].map(e => ({ left: e.getBoundingClientRect().left, right: e.getBoundingClientRect().right })) }));
    assert.ok(layout.scroll <= width + 1, JSON.stringify(layout));
    assert.ok(layout.controls.every(c => c.left >= 0 && c.right <= width));
    await page.screenshot({ path: `${output}/chapter-${width}-${theme}.png` });
  }
  // The Forest of Time route remains reachable from side-quest links under filters.
  await go('ch29-hq-rounds-2-and-3');
  await choose('kind', 'side');
  const route = page.locator('#forest-of-time-route');
  assert.ok(await route.evaluate(el => el.closest('section.quest').classList.contains('is-hidden')));
  await page.evaluate(() => { location.hash = 'forest-of-time-route'; });
  await page.waitForFunction(() => !document.getElementById('forest-of-time-route').closest('section.quest').classList.contains('is-hidden'));
  await page.locator('.forest-route-viewer[data-ready]').waitFor();
  for (let step = 1; step < 5; step++) await route.locator('[data-next]').click();
  assert.equal(await route.locator('.forest-viewer-status').innerText(), 'Step 5 of 5');
  assert.equal(await route.locator('[data-next]').isDisabled(), true);
  await route.locator('[data-select="0"]').click();
  assert.equal(await route.locator('.forest-viewer-status').innerText(), 'Step 1 of 5');
  // No-JS readers still see every entry, the walkthrough and the warnings.
  const nojs = await browser.newContext({ javaScriptEnabled: false });
  await nojs.route('**/*', route => new URL(route.request().url()).origin === new URL(base).origin ? route.continue() : route.abort());
  const staticPage = await nojs.newPage();
  await staticPage.goto(new URL(`guide/${CH1}/`, base).href);
  assert.equal(await staticPage.locator('section.quest').count(), total);
  assert.equal(await staticPage.locator('section.quest.is-hidden').count(), 0);
  assert.ok(await staticPage.locator('.chapter-warning').count() > 0);
  assert.equal(await staticPage.locator('.chapter-warning').first().isVisible(), true);
  await nojs.close();
  assert.deepEqual(errors, []);
  console.log('Quest filters: chapters, combined filters, persistence, completion, warning boxes, direct links, legacy forwarding, mobile themes, forest route and no-JS checks passed.');
} finally {
  await browser.close();
}
