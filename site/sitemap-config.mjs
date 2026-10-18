// Sitemap rules (W-012): leave out pages that are not meant to be indexed, and give each page a <lastmod> from the
// git history of the files it is built from. Used by astro.config.mjs.
import { execFileSync } from 'node:child_process';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { buildTrainerProfiles } from './src/lib/trainer-encounters.mjs';

const SITE_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO = path.resolve(SITE_DIR, '..');
const readJson = (p) => JSON.parse(readFileSync(path.join(SITE_DIR, p), 'utf8'));

/** Paths (without the base, with slashes) that must not be in the sitemap. */
export function excludedPaths() {
	const out = new Set(['/404/']);
	// "Guide moved" forwarding stubs (noindex).
	for (const slug of Object.keys(readJson('src/generated/guide_legacy.json'))) out.add(`/guide/${slug}/`);
	// Trainer records that show another record's profile page (their canonical points there).
	const { profiles } = buildTrainerProfiles(readJson('src/data/trainers.json'));
	for (const p of profiles) for (const t of p.teams) if (t.id !== p.id) out.add(`/trainers/records/${t.id}/`);
	return out;
}

let shallow;
/** Newest commit date (ISO) of any of these repo paths; undefined in a shallow clone, where every file would look new. */
function gitDate(paths) {
	try {
		shallow ??= execFileSync('git', ['rev-parse', '--is-shallow-repository'], { cwd: REPO, encoding: 'utf8' }).trim() === 'true';
		if (shallow) return undefined;
		const out = execFileSync('git', ['log', '-1', '--format=%cI', '--', ...paths], { cwd: REPO, encoding: 'utf8' }).trim();
		return out || undefined;
	} catch {
		return undefined;
	}
}
const newest = (...dates) => dates.filter(Boolean).sort().at(-1);

/** path (without the base) -> lastmod, for the pages whose sources are known. Other pages get no lastmod. */
export function lastmodByPath() {
	const map = new Map();
	const data = gitDate(['site/src/data', 'site/src/lib']);
	for (const section of ['pokemon', 'items', 'moves', 'abilities', 'locations', 'trainers', 'tms', 'tutors', 'type-changes', 'stat-changes', 'team-builder', 'reference-sources'])
		map.set(`/${section}/`, data);
	const docs = path.join(SITE_DIR, 'src/content/docs');
	for (const f of readdirSync(docs)) {
		const m = f.match(/^(.+)\.mdx?$/);
		if (!m || m[1] === '404') continue;
		map.set(m[1] === 'index' ? '/' : `/${m[1]}/`, gitDate([`site/src/content/docs/${f}`]));
	}
	map.set('/', newest(map.get('/'), gitDate(['site/src/data/releases.json', 'site/src/components/Hero.astro'])));
	map.set('/save-editor/', gitDate(['work/save-editor', 'work/save-core', 'site/src/pages/save-editor']));
	map.set('/changelog/', gitDate(['site/src/data/releases.json', 'site/src/data/contributors.json', 'site/src/pages/changelog']));
	// Guide: a chapter is built from its TOML and the quest files that hold its quests (guide_legacy.json says which).
	const legacy = readJson('src/generated/guide_legacy.json');
	const questFiles = new Map();
	const guideDir = path.join(REPO, 'guide');
	if (existsSync(guideDir)) {
		const files = readdirSync(guideDir);
		for (const [slug, entry] of Object.entries(legacy)) {
			const file = files.find((f) => f.replace(/^\d+-/, '').replace(/\.md$/, '') === slug);
			if (!file) continue;
			for (const ch of new Set([entry.default, ...Object.values(entry.anchors)])) {
				if (!questFiles.has(ch)) questFiles.set(ch, []);
				questFiles.get(ch).push(`guide/${file}`);
			}
		}
		for (const f of readdirSync(path.join(guideDir, 'chapters'))) {
			const m = f.match(/^(\d+)-(.+)\.toml$/);
			if (!m) continue;
			const id = `ch${m[1]}-${m[2]}`;
			map.set(`/guide/${id}/`, gitDate([`guide/chapters/${f}`, ...(questFiles.get(id) ?? [])]));
		}
		map.set('/guide/', gitDate(['guide/README.md', 'guide/chapters']));
		map.set('/guide/known-issues/', gitDate(['guide/known-issues.md']));
		map.set('/guide/hidden-items/', gitDate(['guide/hidden-items.md']));
		map.set('/guide/ruins-of-alph-silver/', gitDate(['guide/08-ruins-of-alph-silver.md']));
	}
	return map;
}

/** For a page path (without the base): its own entry, or its section's. */
export function lastmodFor(map, p) {
	if (map.has(p)) return map.get(p);
	const section = `/${p.split('/').filter(Boolean)[0]}/`;
	return ['/pokemon/', '/items/', '/moves/', '/abilities/', '/locations/', '/trainers/'].includes(section) ? map.get(section) : undefined;
}
