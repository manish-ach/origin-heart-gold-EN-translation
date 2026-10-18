// The changelog page (src/pages/changelog/) and the home release strip read src/data/releases.json, written by hand
// from CHANGELOG.md. Every version in CHANGELOG.md must be there, or folded into a public release (rc1 and rc2 were
// never released; rc3 includes them).
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';

const changelog = readFileSync(new URL('../../CHANGELOG.md', import.meta.url), 'utf8');
const { releases } = JSON.parse(readFileSync(new URL('../src/data/releases.json', import.meta.url), 'utf8'));
const contributors = JSON.parse(readFileSync(new URL('../src/data/contributors.json', import.meta.url), 'utf8'));
const versions = [...changelog.matchAll(/^## \[(\d+\.\d+\.\d+(?:-rc\d+)?)\] - (\d{4}-\d{2}-\d{2})$/gm)].map(([, version, date]) => ({ version, date }));

test('every released version in CHANGELOG.md has a changelog entry or is folded into one', () => {
	assert.ok(versions.length >= 8);
	const folded = new Map(releases.flatMap((r) => (r.includes ?? []).map((v) => [v, r.version])));
	for (const { version, date } of versions) {
		const entry = releases.find((r) => r.version === version);
		if (entry) assert.equal(entry.date, date, `${version}: date`);
		else assert.ok(folded.has(version), `${version} is in CHANGELOG.md but not in src/data/releases.json`);
	}
	for (const r of releases) assert.ok(versions.some((v) => v.version === r.version), `${r.version} is not in CHANGELOG.md`);
});

test('releases are newest first, complete and player-facing', () => {
	const order = releases.map((r) => versions.findIndex((v) => v.version === r.version));
	assert.deepEqual(order, [...order].sort((a, b) => a - b));
	for (const r of releases) {
		assert.equal(r.tag, `v${r.version}`);
		assert.equal(typeof r.github, 'boolean');
		if (!r.github) assert.ok(r.note, `${r.version}: a release without a GitHub page needs a note`);
		assert.ok(r.summary && r.changes.length, r.version);
		for (const text of [r.summary, ...r.changes]) {
			assert.doesNotMatch(text, /\bD-\d{4}\b|work\/|\.py\b|a027\//, `${r.version}: no decision ids or tooling in player text`);
		}
	}
});

test('contributors belong to listed releases', () => {
	for (const version of Object.keys(contributors)) assert.ok(releases.some((r) => r.version === version), version);
	assert.equal(contributors['1.0.0-rc8'].at(-1), 'frake');
	assert.ok(contributors['1.0.0-rc7'].includes('astronzo.'));
});

const dist = new URL('../dist/', import.meta.url);
test('built changelog, home release strip, llms files and 404 page', { skip: process.env.GUIDE_TEST_DIST !== '1' }, () => {
	const page = readFileSync(new URL('changelog/index.html', dist), 'utf8');
	for (const r of releases) assert.match(page, new RegExp(`id="v${r.version.replace(/\./g, '-')}"`));
	assert.match(page, /Thanks to<\/strong> Touya, issacrojas15/);
	assert.doesNotMatch(page, /releases\/tag\/v1\.0\.0-rc[34]"/);
	const home = readFileSync(new URL('index.html', dist), 'utf8');
	assert.match(home, /<title>Pokémon Origin HeartGold English Patch &amp; Guide<\/title>/);
	assert.match(home, /class="home-hero/);
	assert.match(home, /<h1 id="_top"[^>]*>[^]*?English translation<\/span><\/h1>/);
	assert.ok(home.includes(`v${releases[0].version}`));
	const llms = readFileSync(new URL('llms.txt', dist), 'utf8');
	assert.match(llms, /^# /);
	assert.match(llms, /discord\.gg/);
	assert.match(llms, /changelog/);
	assert.ok(existsSync(new URL('llms-full.txt', dist)));
	// A /preview/ build's llms files name the production pages (they can't carry noindex).
	for (const f of ['llms.txt', 'llms-full.txt']) assert.doesNotMatch(readFileSync(new URL(f, dist), 'utf8'), /github\.io\/preview\//, f);
	const notFound = readFileSync(new URL('404.html', dist), 'utf8');
	// A /preview/ build (GUIDE_PREVIEW=1) keeps search engines off every page, the 404 included.
	assert.match(notFound, /<meta name="robots" content="noindex, (follow|nofollow)"/);
	if (/content="noindex, nofollow"/.test(notFound)) assert.match(home, /<meta name="robots" content="noindex, nofollow"/, 'nofollow only in a preview build');
	assert.doesNotMatch(notFound, /rel="canonical"/);
	assert.doesNotMatch(notFound, /home-hero/);
});
