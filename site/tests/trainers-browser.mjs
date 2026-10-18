// /trainers/ regression (W-051): the directory draws its cards from the A–Z list, filters and pages work, battle guide
// cards load their team table from the profile page, images fall back to placeholders, and the page works without
// JavaScript. Run from the repository root against a built site:
// PLAYWRIGHT_MODULE=/path/to/playwright/index.mjs GUIDE_PREVIEW_URL=http://127.0.0.1:4338/ node site/tests/trainers-browser.mjs
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const {chromium} = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.GUIDE_PREVIEW_URL || 'http://127.0.0.1:4338/';
const trainers = JSON.parse(readFileSync(new URL('../src/data/trainers.json', import.meta.url), 'utf8'));
const brockTeam = trainers.find(t => t.id === 253).team.length;
const browser = await chromium.launch({headless: true});
let assertions = 0;
const ok = (value, message) => { assert.ok(value, message); assertions++; };
const errors = [];
const cardCount = page => page.evaluate(() => document.querySelectorAll('#trainer-directory .trainer-profile-card').length);
try {
  for (const viewport of [{width: 1280, height: 900}, {width: 390, height: 844}]) {
    const context = await browser.newContext({viewport});
    // External requests (PokéAPI images) are blocked: images must fall back to placeholders without errors.
    await context.route('**/*', r => new URL(r.request().url()).origin === new URL(base).origin ? r.continue() : r.abort());
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(new URL('trainers/', base).href, {waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => document.querySelectorAll('#trainer-directory .trainer-profile-card').length > 0);
    const total = await page.locator('#trainer-index > li').count();
    ok(total > 700, `${total} profiles in the A–Z list`);
    ok(await page.locator('#trainer-index').isHidden(), 'A–Z list hidden once cards are drawn');
    ok(await cardCount(page) === 18, 'first page has 18 cards');
    ok((await page.locator('#trainer-results').innerText()).includes(`of ${total} trainers`), 'status counts every profile');
    const first = page.locator('#trainer-directory .trainer-profile-card').first();
    ok(/\/trainers\/records\/\d+\/$/.test(await first.locator('h3 a').getAttribute('href')), 'card links to a profile');
    ok(await first.locator('.team-preview .preview-mon').count() > 0, 'card shows the team preview');
    await page.waitForFunction(() => document.querySelectorAll('#trainer-directory img').length === 0 || document.querySelectorAll('#trainer-directory .art-placeholder').length > 0);
    ok(await page.locator('#trainer-directory .art-placeholder').count() > 0, 'blocked images become placeholders');
    await page.locator('#trainer-search').fill('pikachu');
    ok(await cardCount(page) === 11, 'search narrows the directory');
    ok(new URL(page.url()).searchParams.get('q') === 'pikachu', 'search is kept in the URL');
    await page.locator('#trainer-category').selectOption('0');
    ok(await page.locator('.trainer-empty').isVisible(), 'no Kanto Gym trainer uses Pikachu: empty message');
    await page.locator('#trainer-reset').click();
    ok(await cardCount(page) === 18 && await page.locator('#trainer-search').inputValue() === '', 'reset');
    await page.locator('#trainer-next').click();
    ok((await page.locator('#trainer-page').innerText()).startsWith('Page 2'), 'next page');
    ok(new URL(page.url()).searchParams.get('page') === '2', 'page in the URL');
    await page.goto(new URL('trainers/?group=0', base).href, {waitUntil: 'domcontentloaded'});
    await page.waitForFunction(() => document.querySelectorAll('#trainer-directory .trainer-profile-card').length > 0);
    ok(await page.locator('#trainer-category').inputValue() === '0', 'group restored from the URL');
    ok((await page.locator('#trainer-directory').innerText()).includes('Brock'), 'Kanto Gyms group lists Brock');
    // Battle guide card: opening it loads the full team from the profile page.
    const brock = page.locator('details#trainer-253');
    ok(await brock.locator('table').count() === 0, 'guide card ships without the team table');
    await brock.locator('summary').click();
    await brock.locator('table tbody tr').first().waitFor();
    ok(await brock.locator('table tbody tr').count() === brockTeam, 'opened card shows the whole team');
    ok(await brock.locator('.table-scroll table').count() === 1, 'loaded table sits in the scroll panel');
    ok(await brock.locator('a[href*="/moves/"]').count() > 0, 'loaded team links its moves');
    ok(/\/trainers\/records\/253\/#trainer-253$/.test(await brock.locator('a', {hasText: 'View all encounters and teams'}).getAttribute('href')), 'profile link');
    const scroll = await page.evaluate(() => document.documentElement.scrollWidth - innerWidth);
    ok(scroll <= 1, `no sideways page scroll at ${viewport.width} px`);
    await context.close();
  }
  // Without JavaScript the A–Z list is the directory and guide cards link to the profile pages.
  const plain = await browser.newContext({javaScriptEnabled: false});
  await plain.route('**/*', r => new URL(r.request().url()).origin === new URL(base).origin ? r.continue() : r.abort());
  const page = await plain.newPage();
  await page.goto(new URL('trainers/', base).href, {waitUntil: 'domcontentloaded'});
  ok(await page.locator('#trainer-index').isVisible(), 'A–Z list visible without JavaScript');
  ok(await page.locator('#trainer-index a').count() > 700, 'every profile linked without JavaScript');
  await page.locator('details#trainer-253 summary').click();
  ok(await page.locator('details#trainer-253 .trainer-team-detail a').isVisible(), 'guide card links to the full team');
  await plain.close();
  ok(errors.length === 0, JSON.stringify(errors));
  console.log(JSON.stringify({assertions, errors}));
} finally {
  await browser.close();
}
