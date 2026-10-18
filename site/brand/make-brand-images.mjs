// Renders the site's icons and social card from text set in Inter (SIL Open Font License 1.1), outlined to SVG paths
// so nothing depends on the viewer's fonts. Plain typography in the site's gold colours: no game or Pokémon art.
// Run by hand after changing the design (needs the Inter TTFs, e.g. from https://rsms.me/inter/):
//   node site/brand/make-brand-images.mjs <folder with Inter_24pt-ExtraBold.ttf, Inter_24pt-SemiBold.ttf, Inter_18pt-Medium.ttf>
// Writes the committed sources site/brand/*.svg and the served files in site/public/.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { create } from 'fontkitten';
import sharp from 'sharp';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC = path.join(HERE, '..', 'public');
const fontDir = process.argv[2];
if (!fontDir) throw new Error('usage: node make-brand-images.mjs <Inter font folder>');
const font = (name) => create(readFileSync(path.join(fontDir, name)));
const extraBold = font('Inter_24pt-ExtraBold.ttf');
const semiBold = font('Inter_24pt-SemiBold.ttf');
const medium = font('Inter_18pt-Medium.ttf');

const GOLD = '#c9971c', GOLD_LIGHT = '#d7ad51', INK = '#1b1b1b', NAVY = '#111923', WHITE = '#f3f5f7', GREY = '#b9c2cc';

/** Text as one SVG path: baseline at (x, y), size in px, tracking in em. Returns { d, width }. */
function textPath(f, text, x, y, size, tracking = 0) {
	const scale = size / f.unitsPerEm;
	let pen = 0;
	const parts = [];
	for (const g of f.glyphsForString(text)) {
		const cmds = g.path.commands.map(({ command, args }) => {
			const pts = [];
			for (let i = 0; i < args.length; i += 2) pts.push(`${+(x + (pen + args[i]) * scale).toFixed(2)} ${+(y - args[i + 1] * scale).toFixed(2)}`);
			return { moveTo: 'M', lineTo: 'L', quadraticCurveTo: 'Q', bezierCurveTo: 'C', closePath: 'Z' }[command] + pts.join(' ');
		});
		parts.push(cmds.join(''));
		pen += g.advanceWidth + tracking * f.unitsPerEm;
	}
	return { d: parts.join(''), width: (pen - tracking * f.unitsPerEm) * scale };
}
const centred = (f, text, cx, y, size, tracking) => {
	const w = textPath(f, text, 0, 0, size, tracking).width;
	return textPath(f, text, cx - w / 2, y, size, tracking).d;
};

/** The OHG monogram on a gold tile, in a 64-unit box. `pad` shrinks the tile for maskable icons. */
function monogram({ pad = 0, radius = 12, bg = null } = {}) {
	const s = 64 - 2 * pad, k = s / 64;
	const letters = centred(extraBold, 'OHG', 32, 32 + 9.6 * k, 26 * k, -0.04);
	return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<!-- "OHG" monogram on the site's gold accent (text set in Inter, outlined); no game or Pokémon art. Made by site/brand/make-brand-images.mjs. -->
${bg ? `<rect width="64" height="64" fill="${bg}"/>` : ''}<rect x="${pad}" y="${pad}" width="${s}" height="${s}" rx="${radius * k}" fill="${GOLD}"/>
<path fill="${INK}" d="${letters}"/>
</svg>
`;
}

function socialCard() {
	const W = 1200, H = 630, tile = 200, tx = 96, ty = 118;
	const tileLetters = centred(extraBold, 'OHG', tx + tile / 2, ty + tile / 2 + 30, 82, -0.04);
	const x = 96;
	const origin = textPath(extraBold, 'Origin ', x, 446, 104, -0.03);
	const heartgold = textPath(extraBold, 'HeartGold', x + origin.width, 446, 104, -0.03);
	const sub = textPath(semiBold, 'English translation · Patch & Guide', x, 522, 46, -0.01);
	const url = textPath(medium, 'originheartgold.github.io', x, 580, 28, 0);
	return `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}">
<!-- Social card (og:image): "Origin HeartGold — English translation · Patch & Guide". Text set in Inter (OFL 1.1), outlined.
     Plain typography in the site's colours, no game or Pokémon art. Made by site/brand/make-brand-images.mjs. -->
<rect width="${W}" height="${H}" fill="${NAVY}"/>
<rect x="0" y="0" width="${W}" height="10" fill="${GOLD}"/>
<rect x="${tx}" y="${ty}" width="${tile}" height="${tile}" rx="${tile * 12 / 64}" fill="${GOLD}"/>
<path fill="${INK}" d="${tileLetters}"/>
<path fill="${WHITE}" d="${origin.d}"/>
<path fill="${GOLD_LIGHT}" d="${heartgold.d}"/>
<path fill="${GREY}" d="${sub.d}"/>
<path fill="${GOLD_LIGHT}" d="${url.d}"/>
</svg>
`;
}

/** A .ico holding PNG images (supported by every current browser). */
function ico(pngs) {
	const header = Buffer.alloc(6 + 16 * pngs.length);
	header.writeUInt16LE(0, 0); header.writeUInt16LE(1, 2); header.writeUInt16LE(pngs.length, 4);
	let offset = header.length;
	pngs.forEach(({ size, data }, i) => {
		const o = 6 + 16 * i;
		header.writeUInt8(size >= 256 ? 0 : size, o); header.writeUInt8(size >= 256 ? 0 : size, o + 1);
		header.writeUInt16LE(1, o + 4); header.writeUInt16LE(32, o + 6);
		header.writeUInt32LE(data.length, o + 8); header.writeUInt32LE(offset, o + 12);
		offset += data.length;
	});
	return Buffer.concat([header, ...pngs.map((p) => p.data)]);
}

const png = (svg, size, h = size) => sharp(Buffer.from(svg), { density: 72 * Math.max(size, h) / 64 }).resize(size, h).png({ compressionLevel: 9 }).toBuffer();

const favicon = monogram();
const maskable = monogram({ pad: 8, radius: 0, bg: GOLD });
const card = socialCard();
writeFileSync(path.join(HERE, 'monogram.svg'), favicon);
writeFileSync(path.join(HERE, 'monogram-maskable.svg'), maskable);
writeFileSync(path.join(HERE, 'social-card.svg'), card);
writeFileSync(path.join(PUBLIC, 'favicon.svg'), favicon);
for (const size of [48, 96, 192, 512]) writeFileSync(path.join(PUBLIC, `favicon-${size}.png`), await png(favicon, size));
writeFileSync(path.join(PUBLIC, 'maskable-512.png'), await png(maskable, 512));
// Apple draws its own rounded corners: a full-bleed tile.
writeFileSync(path.join(PUBLIC, 'apple-touch-icon.png'), await png(monogram({ radius: 0 }), 180));
writeFileSync(path.join(PUBLIC, 'favicon.ico'), ico([{ size: 16, data: await png(favicon, 16) }, { size: 32, data: await png(favicon, 32) }, { size: 48, data: await png(favicon, 48) }]));
mkdirSync(path.join(PUBLIC, 'og'), { recursive: true });
writeFileSync(path.join(PUBLIC, 'og', 'default.png'), await sharp(Buffer.from(card)).png({ compressionLevel: 9 }).toBuffer());
console.log('wrote brand/*.svg, public/favicon.*, favicon-*.png, maskable-512.png, apple-touch-icon.png, og/default.png');
