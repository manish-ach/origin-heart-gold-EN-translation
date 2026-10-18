// Accessibility regressions in the built site (website audit bucket B). A static scan of every page in dist/, run after
// the build with GUIDE_TEST_DIST=1; the helpers are tested on their own without a build.
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cjkLang, splitCjk } from '../src/lib/rehype-a11y.mjs';
import { navCurrent } from '../src/lib/primary-nav.ts';

const built = process.env.GUIDE_TEST_DIST === '1';
const dist = fileURLToPath(new URL('../dist/', import.meta.url));
function* pages(dir = dist) {
	for (const name of readdirSync(dir)) {
		const p = join(dir, name);
		if (statSync(p).isDirectory()) { if (!['_astro', 'pagefind', 'preview'].includes(name)) yield* pages(p); }
		else if (name.endsWith('.html')) yield p;
	}
}
const CJK = /[぀-ヿ㐀-鿿豈-﫿]/;
const relOf = (file) => file.slice(dist.length - 1).replace(/index\.html$/, '');
/** The page body without scripts, styles, code and the head. */
const bodyOf = (html) => html.replace(/<head>[\s\S]*?<\/head>/, '')
	.replace(/<(script|style|template)\b[\s\S]*?<\/\1>/g, '');
const isRedirect = (html) => /<meta http-equiv="refresh"/.test(html);

/** Problems on one page; each entry is "<check>: <detail>". */
export function scan(html) {
	const out = [];
	const body = bodyOf(html);
	if (!/^<!DOCTYPE html><html lang="en"/i.test(html)) out.push('lang: <html lang="en"> missing');
	for (const img of body.match(/<img\b[^>]*>/g) ?? []) if (!/\salt(=|[\s>/])/.test(img)) out.push(`img-alt: ${img.slice(0, 80)}`);
	// aria-label/labelledby are not allowed on elements without a role that supports a name (div, span, p, pre…).
	for (const m of body.matchAll(/<(div|span|p|pre|code|b|i|em|strong|small)\b([^>]*)>/g)) {
		if (/\saria-label(ledby)?=/.test(m[2]) && !/\srole=/.test(m[2])) out.push(`aria-prohibited: <${m[1]}${m[2].slice(0, 70)}>`);
	}
	const ids = new Map();
	for (const m of body.matchAll(/\sid="([^"]+)"/g)) ids.set(m[1], (ids.get(m[1]) ?? 0) + 1);
	for (const [id, n] of ids) if (n > 1) out.push(`duplicate-id: ${id} ×${n}`);
	for (const m of body.matchAll(/<table\b([^>]*)>([\s\S]*?)<\/table>/g)) {
		const named = /\saria-label(ledby)?="[^"]+"/.test(m[1]) || /^\s*<caption\b[^>]*>\s*[^<\s]/.test(m[2]) || /^\s*<caption\b[^>]*>\s*<[^/]/.test(m[2]);
		if (!named) out.push(`table-name: <table${m[1].slice(0, 60)}> ${m[2].replace(/<[^>]+>/g, ' ').trim().slice(0, 40)}`);
		const tbody = m[2].match(/<tbody\b[\s\S]*?<\/tbody>/)?.[0] ?? '';
		for (const th of tbody.match(/<th\b[^>]*>/g) ?? []) if (!/\sscope=/.test(th)) out.push('th-scope: row header without scope');
	}
	// Chinese or Japanese text must sit inside an element with lang="zh…" or "ja" (code blocks excepted).
	const text = body.replace(/<(pre|code)\b[\s\S]*?<\/\1>/g, '')
		.replace(/<(\w+)\b[^>]*\slang="(?:zh[^"]*|ja)"[^>]*>[\s\S]*?<\/\1>/g, '')
		.replace(/<[^>]+>/g, ' ');
	const cjk = text.match(new RegExp(`.{0,20}${CJK.source}+.{0,10}`));
	if (cjk) out.push(`cjk-lang: "${cjk[0].trim()}"`);
	// The ↗ arrow means "leaves the site": never on a link to one of our own pages.
	for (const m of body.matchAll(/<a\b[^>]*href="(\/[^"]*|\.\.?\/[^"]*|[a-z-]+\/[^"]*)"[^>]*>([\s\S]*?)<\/a>/g)) {
		if (m[2].includes('↗')) out.push(`internal-arrow: ${m[1]}`);
	}
	return out;
}

test('scan flags the problems it is meant to catch', () => {
	const page = (body) => `<!DOCTYPE html><html lang="en"><head><title>x</title></head><body>${body}</body></html>`;
	assert.deepEqual(scan(page('<p>Origin HeartGold (<span lang="zh-Hans">起源心金</span>)</p><table aria-label="Moves"><tbody><tr><th scope="row">HP</th></tr></tbody></table><img src="a.png" alt="">')), []);
	const bad = scan(page('<p>起源心金</p><div class="table-scroll" aria-label="x"></div><table><tbody><tr><th>HP</th></tr></tbody></table><img src="a.png"><i id="a"></i><i id="a"></i><a href="/save-editor/">Save editor ↗</a>'));
	for (const check of ['cjk-lang', 'aria-prohibited', 'table-name', 'th-scope', 'img-alt', 'duplicate-id', 'internal-arrow']) {
		assert.ok(bad.some((p) => p.startsWith(check)), check);
	}
	assert.deepEqual(scan(page('<table><caption class="sr-only">Arceus’s team</caption><tr><td>1</td></tr></table>')), []);
});

test('Chinese and Japanese runs get the right lang', () => {
	assert.equal(cjkLang('起源心金'), 'zh-Hans');
	assert.equal(cjkLang('かわいい沙織'), 'ja');
	assert.equal(cjkLang('Origin'), undefined);
	assert.deepEqual(splitCjk('Origin HeartGold (起源心金) v4.0.3'), ['Origin HeartGold (', { lang: 'zh-Hans', text: '起源心金' }, ') v4.0.3']);
	assert.deepEqual(splitCjk('雁南飞TB, かわいい沙織'), [{ lang: 'zh-Hans', text: '雁南飞' }, 'TB, ', { lang: 'ja', text: 'かわいい沙織' }]);
});

test('the main navigation marks the current section', () => {
	assert.equal(navCurrent('/pokemon/', '/', '/pokemon/'), 'page');
	assert.equal(navCurrent('/pokemon/cyndaquil/', '/', '/pokemon/'), 'true');
	assert.equal(navCurrent('/preview/guide/ch01-first-badge/', '/preview/', '/guide/'), 'true');
	assert.equal(navCurrent('/', '/', '/guide/'), undefined);
	assert.equal(navCurrent('/404.html', '/', '/faq/'), undefined);
});

test('every built page passes the static accessibility scan', { skip: !built }, () => {
	const problems = [];
	let checked = 0;
	for (const file of pages()) {
		const html = readFileSync(file, 'utf8');
		if (isRedirect(html)) continue;
		checked++;
		for (const p of scan(html)) problems.push(`${relOf(file)} ${p}`);
	}
	assert.ok(checked > 1000, `scanned ${checked} pages`);
	assert.deepEqual(problems.slice(0, 25), [], `${problems.length} problems`);
});

test('every page has one h1, the main navigation and a way to open it on phones', { skip: !built }, () => {
	for (const rel of ['', 'patch/', 'faq/', 'guide/', 'pokemon/cyndaquil/', 'trainers/', 'team-builder/', 'changelog/', '404.html', 'save-editor/']) {
		const html = readFileSync(join(dist, rel.endsWith('.html') ? rel : `${rel}index.html`), 'utf8');
		assert.equal((html.match(/<h1\b/g) ?? []).length, 1, `${rel}: one h1`);
		if (rel === 'save-editor/') continue;
		assert.match(html, /<nav class="primary-nav primary-nav-bar[^"]*"[^>]*aria-label="Main"/, `${rel}: main navigation`);
		const sidebar = html.includes('id="starlight__sidebar"');
		// Pages with a sidebar open it as the phone drawer (with the main links on top); the others get a Menu button.
		if (sidebar) assert.match(html, /primary-nav-drawer/, `${rel}: main links in the drawer`);
		else assert.match(html, /class="primary-menu-button[^"]*"[^>]*popovertarget="primary-menu"/, `${rel}: Menu button`);
	}
});
