// Starlight route middleware: search titles, social cards, canonical/noindex rules and one JSON-LD block per page.
// Registered with `routeMiddleware` in astro.config.mjs. It runs for content pages and for <StarlightPage> templates.
import { defineRouteMiddleware } from '@astrojs/starlight/route-data';
import type { HeadConfig } from '@astrojs/starlight/types';
import { PREVIEW, SITE_URL } from '../site.config.mjs';
import {
	HOME_TITLE, SITE_NAME, ORG_NAME, OFFICIAL_LINE, DISCORD_URL, GITHUB_URL, SOCIAL_IMAGE, latestRelease, releaseUrl, RELEASES_URL,
	composeTitle, breadcrumbs,
} from './lib/site-meta';

type Head = HeadConfig;
const base = import.meta.env.BASE_URL.endsWith('/') ? import.meta.env.BASE_URL : import.meta.env.BASE_URL + '/';
/** Production base: the preview's canonicals point to the released pages (W-022). */
const prodBase = PREVIEW ? base.replace(/preview\/$/, '') : base;
const abs = (path: string) => new URL(path, SITE_URL).href;
const homeUrl = abs(prodBase);

function setMeta(head: Head, key: 'name' | 'property', value: string, content: string) {
	const i = head.findIndex((e) => e.tag === 'meta' && e.attrs?.[key] === value);
	const entry = { tag: 'meta' as const, attrs: { [key]: value, content } };
	if (i >= 0) head[i] = entry; else head.push(entry);
}
const removeWhere = (head: Head, test: (e: Head[number]) => boolean) => {
	for (let i = head.length - 1; i >= 0; i--) if (test(head[i])) head.splice(i, 1);
};

export const organization = {
	'@type': 'Organization', '@id': `${homeUrl}#organization`, name: ORG_NAME, url: homeUrl,
	logo: { '@type': 'ImageObject', url: abs(`${prodBase}favicon-512.png`), width: 512, height: 512 },
	sameAs: [GITHUB_URL, DISCORD_URL],
};
export const website = {
	'@type': 'WebSite', '@id': `${homeUrl}#website`, name: SITE_NAME, url: homeUrl, inLanguage: 'en',
	alternateName: ['Pokémon Origin HeartGold English', 'Origin HeartGold English translation', '起源心金 English patch'],
	description: OFFICIAL_LINE, publisher: { '@id': `${homeUrl}#organization` },
};
/** The English patch: a VideoGame (a SoftwareApplication in schema.org) by the hack's authors, translated by the team. */
export function patchGame() {
	const url = releaseUrl(latestRelease) ?? RELEASES_URL;
	return {
		'@type': 'VideoGame', '@id': `${homeUrl}#game`,
		name: 'Pokémon Origin HeartGold (English translation)',
		alternateName: ['Origin HeartGold', '起源心金', 'Pokémon Origin HeartGold English patch'],
		url: homeUrl, inLanguage: 'en', gamePlatform: 'Nintendo DS', operatingSystem: 'Nintendo DS',
		applicationCategory: 'GameApplication',
		description: 'A free English translation patch for Origin HeartGold (起源心金) v4.0.3, a Chinese fan game built on Pokémon HeartGold. Apply it to your own Pokémon HeartGold Version (USA).',
		softwareVersion: latestRelease.version, datePublished: latestRelease.date,
		downloadUrl: url, installUrl: abs(`${prodBase}patch/`),
		offers: { '@type': 'Offer', price: 0, priceCurrency: 'USD', availability: 'https://schema.org/InStock', url },
		creator: [
			{ '@type': 'Person', name: '雁南飞TB', alternateName: 'Yannanfei TB' },
			{ '@type': 'Person', name: 'Alex' },
		],
		translator: { '@id': `${homeUrl}#organization` },
		isBasedOn: { '@type': 'VideoGame', name: 'Pokémon HeartGold Version', gamePlatform: 'Nintendo DS' },
	};
}

/** "### Question" sections of the FAQ as question/answer pairs, in plain text. */
function faqEntries(body: string) {
	const plain = (md: string) => md
		.replace(/<[^>]+>/g, '')
		.replace(/!?\[([^\]]*)\]\([^)]*\)/g, '$1')
		.replace(/[*_`]+/g, '')
		.replace(/^\s*[-\d.]+\s+/gm, '')
		.replace(/\s+/g, ' ').trim();
	return [...body.matchAll(/^### (.+)\n([\s\S]*?)(?=^#{2,3} |(?![\s\S]))/gm)].map(([, q, a]) => ({
		'@type': 'Question', name: plain(q), acceptedAnswer: { '@type': 'Answer', text: plain(a) },
	})).filter((q) => q.acceptedAnswer.text);
}

export const onRequest = defineRouteMiddleware((context) => {
	const route = context.locals.starlightRoute;
	const head = route.head;
	const data = route.entry.data as typeof route.entry.data & { seo?: { title?: string; canonical?: string } };
	const rel = context.url.pathname.slice(base.length - 1);
	const isHome = rel === '/';
	const is404 = route.entry.id === '404' || rel === '/404/' || rel === '/404.html';
	const pagePart = data.seo?.title ?? data.title;
	const title = isHome ? HOME_TITLE : composeTitle(pagePart);
	// <title> content is written as HTML (set:html): escape it.
	const titleHtml = title.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
	const titleEntry = head.find((e) => e.tag === 'title');
	if (titleEntry) titleEntry.content = titleHtml; else head.push({ tag: 'title', content: titleHtml });
	setMeta(head, 'property', 'og:title', isHome ? HOME_TITLE : pagePart);
	setMeta(head, 'property', 'og:type', isHome ? 'website' : 'article');
	setMeta(head, 'property', 'og:locale', 'en_US');
	setMeta(head, 'property', 'og:site_name', SITE_NAME);
	const image = abs(`${prodBase}${SOCIAL_IMAGE.path}`);
	setMeta(head, 'property', 'og:image', image);
	setMeta(head, 'property', 'og:image:width', String(SOCIAL_IMAGE.width));
	setMeta(head, 'property', 'og:image:height', String(SOCIAL_IMAGE.height));
	setMeta(head, 'property', 'og:image:alt', SOCIAL_IMAGE.alt);
	setMeta(head, 'name', 'twitter:image', image);
	setMeta(head, 'name', 'twitter:image:alt', SOCIAL_IMAGE.alt);

	// Canonical: a page that duplicates another names it; previews point at production; the 404 page has none.
	const canonical = head.find((e) => e.tag === 'link' && e.attrs?.rel === 'canonical');
	let canonicalHref = canonical?.attrs?.href as string | undefined;
	if (canonicalHref && data.seo?.canonical) canonicalHref = abs(prodBase + data.seo.canonical.replace(/^\//, ''));
	else if (canonicalHref && PREVIEW) canonicalHref = canonicalHref.replace(new URL(base, SITE_URL).href, new URL(prodBase, SITE_URL).href);
	if (canonical && canonicalHref) canonical.attrs!.href = canonicalHref;
	const ogUrl = head.find((e) => e.tag === 'meta' && e.attrs?.property === 'og:url');
	if (ogUrl && canonicalHref) ogUrl.attrs!.content = canonicalHref;
	if (is404) {
		removeWhere(head, (e) => (e.tag === 'link' && e.attrs?.rel === 'canonical') || (e.tag === 'meta' && e.attrs?.property === 'og:url'));
		if (!PREVIEW) setMeta(head, 'name', 'robots', 'noindex, follow');
	}

	// JSON-LD: the organization and site on every page, plus what this page is.
	const graph: object[] = [organization, website];
	if (!is404) {
		const url = canonicalHref ?? abs(context.url.pathname);
		const crumbs = breadcrumbs(context.url.pathname, base, data.title); // as shown on the page (PageTitle.astro)
		const page: Record<string, unknown> = {
			'@type': rel === '/faq/' ? ['WebPage', 'FAQPage'] : rel.startsWith('/changelog/') ? ['WebPage', 'CollectionPage'] : 'WebPage',
			'@id': `${url}#webpage`, url, name: isHome ? HOME_TITLE : pagePart, inLanguage: 'en',
			isPartOf: { '@id': `${homeUrl}#website` }, publisher: { '@id': `${homeUrl}#organization` },
		};
		if (data.description) page.description = data.description;
		if (crumbs.length > 1) {
			page.breadcrumb = {
				'@type': 'BreadcrumbList',
				itemListElement: crumbs.map((c, i) => ({ '@type': 'ListItem', position: i + 1, name: c.name, item: abs(c.href.replace(base, prodBase)) })),
			};
		}
		if (rel === '/faq/') page.mainEntity = faqEntries(route.entry.body ?? '');
		if (isHome || rel === '/patch/' || rel === '/changelog/') {
			graph.push(patchGame());
			page.about = { '@id': `${homeUrl}#game` };
		}
		graph.push(page);
	}
	head.push({
		tag: 'script', attrs: { type: 'application/ld+json' },
		content: JSON.stringify({ '@context': 'https://schema.org', '@graph': graph }).replace(/</g, '\\u003c'),
	});
});
