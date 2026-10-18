// The site's main destinations, shown in the header on wide screens, in the Menu panel on pages without a sidebar
// (home, 404) and at the top of the mobile navigation drawer. One list, so every page offers the same choices.
export interface NavItem { label: string; href: string; cta?: boolean }
export const PRIMARY_NAV: NavItem[] = [
	{ label: 'Walkthrough', href: '/guide/' },
	{ label: 'Pokédex', href: '/pokemon/' },
	{ label: 'Trainers', href: '/trainers/' },
	{ label: 'FAQ', href: '/faq/' },
	{ label: 'Save editor', href: '/save-editor/' },
	{ label: 'Get the patch', href: '/patch/', cta: true },
];

/** 'page' on the item's own page, 'true' inside its section (a Pokémon page under Pokédex), else undefined. */
export function navCurrent(pathname: string, base: string, href: string): 'page' | 'true' | undefined {
	const root = base.replace(/\/?$/, '');
	const path = pathname.replace(/index\.html$/, '').replace(/\/?$/, '/');
	const target = root + href;
	if (path === target) return 'page';
	return path.startsWith(target) ? 'true' : undefined;
}
