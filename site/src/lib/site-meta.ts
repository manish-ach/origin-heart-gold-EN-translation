// Who we are and what the site is called: one place for titles, the official statement, the official channels,
// release data and breadcrumbs. Used by the route middleware (src/routeData.ts), the hero, footer, changelog and llms.txt.
import { REPO_URL, SITE_URL } from '../../site.config.mjs';
import releasesJson from '../data/releases.json';
import contributorsJson from '../data/contributors.json';

export const SITE_NAME = 'Origin HeartGold English';
export const HOME_TITLE = 'Pokémon Origin HeartGold English Patch & Guide';
export const ORG_NAME = 'Origin HeartGold English translation team';
export const OFFICIAL_LINE = 'The official site of the Origin HeartGold English translation. Patches are published only on our GitHub releases.';
export const DISCORD_URL = 'https://discord.gg/sQY2udrQS';
export const GITHUB_URL = REPO_URL;
export const RELEASES_URL = `${REPO_URL}/releases`;
export const SOCIAL_IMAGE = { path: 'og/default.png', width: 1200, height: 630, alt: 'Origin HeartGold — English translation · Patch & Guide' };
/** Titles longer than this drop the site suffix (or use the short one), so search results show the page part. */
export const TITLE_MAX = 60;

/** One public release. `github: false`: shared as a patch file before GitHub releases (no tag); `includes`: earlier, never
 * released versions folded into this one. */
export interface Release { version: string; tag: string; date: string; summary: string; changes: string[]; github: boolean; note?: string; includes?: string[] }
export const releases = (releasesJson as { releases: Release[] }).releases;
export const latestRelease = releases[0];
export const contributors = contributorsJson as Record<string, string[]>;
export const releaseUrl = (r: Release) => r.github ? `${REPO_URL}/releases/tag/${r.tag}` : undefined;
export function formatDate(iso: string) {
	return new Date(iso + 'T12:00:00Z').toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
}

/** "<page> · Origin HeartGold English", shortened when it gets too long. */
export function composeTitle(page: string) {
	const full = `${page} · ${SITE_NAME}`;
	if (full.length <= TITLE_MAX) return full;
	const short = `${page} · Origin HeartGold`;
	return short.length <= TITLE_MAX ? short : page;
}

/** Trim a description to about 160 characters at a word boundary. */
export function clampDescription(text: string, max = 160) {
	const t = text.replace(/\s+/g, ' ').trim();
	if (t.length <= max) return t;
	const cut = t.slice(0, max - 1);
	return cut.slice(0, cut.lastIndexOf(' ')).replace(/[,;:·—-]+$/, '') + '…';
}

/** The site's sections, by first path segment: the breadcrumb label and the decorative Pokémon of the index page. */
export const SECTIONS: Record<string, { label: string; mon: number }> = {
	'team-builder': { label: 'Team Builder', mon: 133 },
	pokemon: { label: 'Pokémon', mon: 151 }, locations: { label: 'Locations', mon: 149 },
	items: { label: 'Items', mon: 52 }, moves: { label: 'Moves', mon: 448 },
	abilities: { label: 'Abilities', mon: 197 }, tms: { label: 'TMs and HMs', mon: 137 },
	tutors: { label: 'Move tutors', mon: 65 }, trainers: { label: 'Trainers', mon: 6 },
	guide: { label: 'Quest guide', mon: 133 }, calendar: { label: 'Calendar encounters', mon: 251 },
	mechanics: { label: 'Mechanics and controls', mon: 25 }, faq: { label: 'FAQ', mon: 175 },
	patch: { label: 'English patch', mon: 250 }, 'save-editor': { label: 'Save editor', mon: 233 },
	about: { label: 'About', mon: 154 }, contribute: { label: 'Contribute', mon: 152 },
	'camera-codes': { label: 'Camera codes', mon: 164 }, 'reference-sources': { label: 'Reference sources', mon: 201 },
	changelog: { label: 'Changelog', mon: 143 },
};

export interface Crumb { name: string; href: string }
/** Home / Section / Page, as root-relative paths (with the base). The last crumb is the page itself. */
export function breadcrumbs(pathname: string, base: string, pageTitle: string): Crumb[] {
	const root = base.endsWith('/') ? base : base + '/';
	const parts = pathname.slice(root.length - 1).split('/').filter(Boolean);
	const out: Crumb[] = [{ name: 'Home', href: root }];
	if (!parts.length) return out;
	const section = SECTIONS[parts[0]];
	if (parts.length > 1 && section) out.push({ name: section.label, href: `${root}${parts[0]}/` });
	out.push({ name: parts.length === 1 && section ? section.label : pageTitle, href: `${root}${parts.join('/')}/` });
	return out;
}

export const absoluteUrl = (path: string) => new URL(path, SITE_URL).href;
