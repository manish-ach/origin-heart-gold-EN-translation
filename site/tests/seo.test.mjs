// Search and sharing metadata of the built site (src/routeData.ts, src/lib/page-seo.ts, sitemap-config.mjs).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const built = process.env.GUIDE_TEST_DIST === '1';
const dist = fileURLToPath(new URL('../dist/', import.meta.url));
function* pages(dir = dist) {
	for (const name of readdirSync(dir)) {
		const p = join(dir, name);
		if (statSync(p).isDirectory()) { if (!['_astro', 'pagefind', 'preview'].includes(name)) yield* pages(p); }
		else if (name.endsWith('.html')) yield p;
	}
}
const unescape = (s) => s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");

test('indexable pages have unique titles and descriptions, valid JSON-LD and a social card', { skip: !built }, (t) => {
	const titles = new Map(), descriptions = new Map();
	let checked = 0, seen = 0;
	for (const file of pages()) {
		const html = readFileSync(file, 'utf8');
		const rel = file.slice(dist.length - 1).replace(/index\.html$/, '');
		seen++;
		if (/<meta name="robots" content="noindex/.test(html)) continue;
		const canonical = html.match(/<link rel="canonical" href="([^"]+)"/)?.[1];
		assert.ok(canonical, `${rel}: canonical`);
		const blocks = [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)];
		assert.equal(blocks.length, 1, `${rel}: one JSON-LD block`);
		const graph = JSON.parse(blocks[0][1])['@graph'];
		assert.ok(graph.some((n) => n['@type'] === 'Organization') && graph.some((n) => n['@type'] === 'WebSite'), rel);
		assert.match(html, /<meta property="og:image" content="https:\/\/[^"]+\/og\/default\.png"/, rel);
		assert.match(html, /<meta property="og:locale" content="en_US"/, rel);
		checked++;
		if (!canonical.endsWith(rel)) continue; // a duplicate that names its main page
		const title = unescape(html.match(/<title>([^<]*)<\/title>/)[1]);
		const description = unescape(html.match(/<meta name="description" content="([^"]*)"/)?.[1] ?? '');
		assert.ok(!titles.has(title), `${rel}: title "${title}" also on ${titles.get(title)}`);
		assert.ok(description && !descriptions.has(description), `${rel}: description also on ${descriptions.get(description)}`);
		assert.doesNotMatch(description, /\bD-\d{4}\b/, rel);
		titles.set(title, rel); descriptions.set(description, rel);
	}
	// A /preview/ build (GUIDE_PREVIEW=1) marks every page noindex: there is nothing indexable to check.
	if (checked === 0 && seen > 0) { t.skip('preview build: every page is noindex'); return; }
	assert.ok(checked > 4000, `${checked} pages`);
	assert.equal(titles.get('Pokémon Origin HeartGold English Patch & Guide'), '/');
});

test('home, patch and FAQ structured data', { skip: !built }, () => {
	const ld = (path) => JSON.parse(readFileSync(join(dist, path), 'utf8').match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)[1])['@graph'];
	for (const path of ['index.html', 'patch/index.html']) {
		const game = ld(path).find((n) => n['@type'] === 'VideoGame');
		assert.ok(game?.softwareVersion && game.offers.price === 0 && game.creator.length === 2, path);
	}
	const faq = ld('faq/index.html').find((n) => [].concat(n['@type']).includes('FAQPage'));
	assert.ok(faq.mainEntity.length >= 10 && faq.mainEntity.every((q) => q.name && q.acceptedAnswer.text));
	const crumbs = ld('pokemon/cyndaquil/index.html').find((n) => n.breadcrumb).breadcrumb.itemListElement.map((i) => i.name);
	assert.deepEqual(crumbs, ['Home', 'Pokémon', '#0155 Cyndaquil']);
});

test('sitemap leaves out noindex and duplicate pages; icons and llms files exist', { skip: !built }, () => {
	const sitemap = readFileSync(join(dist, 'sitemap-0.xml'), 'utf8');
	assert.doesNotMatch(sitemap, /<loc>[^<]*\/guide\/pallet-to-pewter\/<\/loc>/);
	assert.doesNotMatch(sitemap, /<loc>https:\/\/[^/<]+\/404\/<\/loc>/);
	for (const file of ['favicon.svg', 'favicon.ico', 'favicon-48.png', 'favicon-96.png', 'favicon-192.png', 'favicon-512.png', 'maskable-512.png', 'apple-touch-icon.png', 'site.webmanifest', 'og/default.png', 'llms.txt', 'llms-full.txt'])
		assert.ok(existsSync(join(dist, file)), file);
	assert.ok(statSync(join(dist, 'llms-full.txt')).size < 1.5e6);
	const legacy = readFileSync(join(dist, 'guide/pallet-to-pewter/index.html'), 'utf8');
	assert.match(legacy, /<link rel="canonical" href="https:\/\/[^"]+\/guide\/ch\d+[^"]*\/"/);
});
