// One place for the public project details. CI sets these from the GitHub repository;
// locally they fall back to the placeholders below.
export const REPO_URL = process.env.GUIDE_REPO_URL || 'https://github.com/OWNER/REPO';
// Site URL and base path. Production is the host root https://originheartgold.github.io/ (base /);
// the tester preview is built with base /preview/.
export const SITE_URL = process.env.GUIDE_SITE_URL || 'https://example.github.io';
export const BASE = process.env.GUIDE_BASE || '/';
// Preview builds (GUIDE_PREVIEW=1, published under /preview/ by the site workflow) show a banner,
// ask search engines not to index them and load no analytics.
export const PREVIEW = process.env.GUIDE_PREVIEW === '1';
export const GAME = 'Origin HeartGold';
export const GAME_VERSION = 'v4.0.3';
// Search engine ownership tokens (W-011), from the repository variables of the same name; production builds only.
// The content value of Google Search Console's "HTML tag" and of Bing Webmaster Tools' msvalidate.01 tag.
export const GOOGLE_VERIFICATION = process.env.GUIDE_GOOGLE_VERIFICATION || '';
export const BING_VERIFICATION = process.env.GUIDE_BING_VERIFICATION || '';
