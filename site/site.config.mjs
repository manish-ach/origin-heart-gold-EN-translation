// One place for the public project details. CI sets these from the GitHub repository;
// locally they fall back to the placeholders below.
export const REPO_URL = process.env.GUIDE_REPO_URL || 'https://github.com/OWNER/REPO';
// Site URL and base path. GitHub Pages project sites live under /<repo>/.
export const SITE_URL = process.env.GUIDE_SITE_URL || 'https://example.github.io';
export const BASE = process.env.GUIDE_BASE || '/';
export const GAME = 'Origin HeartGold';
export const GAME_VERSION = 'v4.0.3';
