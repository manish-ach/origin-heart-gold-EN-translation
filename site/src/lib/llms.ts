// llms.txt and llms-full.txt (W-009): what the site is, the official links, and the start-here text in plain Markdown.
// Built from the content collection at build time (src/pages/llms.txt.ts, src/pages/llms-full.txt.ts).
import { getCollection, type CollectionEntry } from 'astro:content';
import { SITE_URL, PREVIEW } from '../../site.config.mjs';
import { OFFICIAL_LINE, DISCORD_URL, GITHUB_URL, RELEASES_URL, latestRelease, formatDate, releaseUrl } from './site-meta';

// Links name the production pages, also in a /preview/ build (like its canonicals, W-022): the preview's llms files can't
// carry noindex, so they must not send crawlers into the preview.
const siteBase = import.meta.env.BASE_URL.replace(/\/?$/, '/');
const base = PREVIEW ? siteBase.replace(/preview\/$/, '') : siteBase;
export const abs = (path: string) => new URL(base + path.replace(/^\//, ''), SITE_URL).href;

export const LICENCE_NOTE = '© 2026 Origin HeartGold English translation team. The guide and website text is all rights reserved: linking to any page and short quotes with a link back are welcome. Facts and game data are not ours to claim. Full terms: ' + `${GITHUB_URL}/blob/main/LICENSE-GUIDE`;

export function intro() {
	return [
		'# Pokémon Origin HeartGold English translation',
		'',
		`> ${OFFICIAL_LINE} Origin HeartGold (起源心金) v4.0.3 is a Chinese fan game built on Pokémon HeartGold, by 雁南飞TB (Yannanfei TB), with v4 by Alex. The English translation is a free patch for your own Pokémon HeartGold Version (USA) ROM (CRC32 C180A0E9); no ROMs are provided. The current English patch is v${latestRelease.version}, released ${formatDate(latestRelease.date)}. This site also has a walkthrough (quest guide), a Pokédex and reference pages for locations, items, moves, abilities, TMs and trainers.`,
		'',
		LICENCE_NOTE,
		'',
		'Official links:',
		'',
		`- Website: ${abs('/')}`,
		`- Download and patch in the browser: ${abs('/patch/')}`,
		`- GitHub releases (the only place patches are published): ${RELEASES_URL}`,
		`- Latest release notes: ${releaseUrl(latestRelease) ?? RELEASES_URL}`,
		`- GitHub repository: ${GITHUB_URL}`,
		`- Discord (official community): ${DISCORD_URL}`,
	];
}

export type Doc = CollectionEntry<'docs'>;
export async function docs() {
	const all = await getCollection('docs');
	const by = new Map(all.map((d) => [d.id, d]));
	const chapters = all.filter((d) => /^guide\/ch\d+/.test(d.id)).sort((a, b) => (a.data.sidebar.order ?? 0) - (b.data.sidebar.order ?? 0));
	return { by, chapters };
}
export const pageUrl = (id: string) => abs(id === 'index' ? '/' : `/${id}/`);

/** Content Markdown/MDX made readable as plain Markdown: no imports, components, HTML or relative links. */
export function cleanMarkdown(body: string, id: string) {
	let s = body;
	s = s.replace(/^(import|export) .*$/gm, '');
	s = s.replace(/\{\/\*[\s\S]*?\*\/\}/g, '');
	// Values the pages compute at build time: fill in the ones worth keeping, drop the rest.
	s = s.replace(/<p class="patch-official">[\s\S]*?<\/p>/, `**${OFFICIAL_LINE}** Current English patch: **v${latestRelease.version}**, released ${formatDate(latestRelease.date)} ([release notes](${releaseUrl(latestRelease) ?? RELEASES_URL}), [all changes](${abs('/changelog/')})).`);
	s = s.replace(/^.*\{coverageTotals[^\n]*\n/gm, '');
	s = s.replace(/\{\w+ && [\s\S]*?\}(?=\n)/g, '');
	s = s.replace(/<details\b[\s\S]*?<\/details>/g, '');
	s = s.replace(/<aside class="chapter-warning"[\s\S]*?<\/aside>/g, '');
	s = s.replace(/<Aside[^>]*title="([^"]*)"[^>]*>/g, '> **$1:** ').replace(/<\/Aside>/g, '');
	s = s.replace(/<a href=\{REPO_URL(?: \+ '([^']*)')?\}>([^<]*)<\/a>/g, (_, p, t) => `[${t}](${GITHUB_URL}${p ?? ''})`);
	s = s.replace(/<a href=\{DISCORD_URL\}>([^<]*)<\/a>/g, `[$1](${DISCORD_URL})`);
	s = s.replace(/<a href="([^"]*)"[^>]*>([\s\S]*?)<\/a>/g, '[$2]($1)');
	s = s.replace(/<strong>\{OFFICIAL_LINE\}<\/strong>/g, `**${OFFICIAL_LINE}**`);
	s = s.replace(/<li\b[^>]*>/g, '- ').replace(/<\/li>/g, '');
	s = s.replace(/<strong>([^<]*)<\/strong>/g, '**$1**');
	s = s.replace(/<[A-Za-z/][^>]*>/g, '');
	s = s.replace(/\{[^{}\n]*\}/g, '');
	// Relative links become absolute: "../faq/#x" from page "about" -> <site>/faq/#x; "#x" -> this page.
	const here = pageUrl(id);
	s = s.replace(/\]\((?!https?:|mailto:)([^)\s]+)\)/g, (_, href: string) => `](${new URL(href, here).href})`);
	return s.replace(/^[ \t]+$/gm, '').replace(/\n{3,}/g, '\n\n').trim();
}

/** A chapter's walkthrough part (before the quest entries), plus the list of its quests. */
export function chapterOverview(d: Doc) {
	const body = d.body ?? '';
	const cut = body.indexOf('## Quests in this chapter');
	const quests = [...body.slice(cut >= 0 ? cut : body.length).matchAll(/^## (.+)$/gm)].map((m) => m[1]).filter((h) => h !== 'Quests in this chapter');
	let text = cleanMarkdown(cut >= 0 ? body.slice(0, cut) : body, d.id);
	if (quests.length) text += '\n\nQuests in this chapter:\n\n' + quests.map((q) => `- ${q}`).join('\n');
	return text;
}
