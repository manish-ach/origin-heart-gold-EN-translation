// Markdown/MDX accessibility pass, a Sätteri hast plugin (astro.config.mjs → markdown.processor), no dependencies:
// - every table without a caption or ARIA name gets aria-label = the text of the nearest heading before it (W-033);
// - runs of Chinese or Japanese text get <span lang="zh-Hans"> or <span lang="ja">, so screen readers switch voice.
// Code blocks and elements that already carry a lang are left alone.

const HAN = /[㐀-鿿豈-﫿]/;
const KANA = /[぀-ヿ]/;
/** A run of CJK characters, with CJK punctuation or single spaces between them. */
const RUN = /[぀-ヿ㐀-鿿豈-﫿](?:[぀-ヿ㐀-鿿豈-﫿　-〿＀-￯]| (?=[぀-ヿ㐀-鿿豈-﫿]))*/g;
const SKIP = new Set(['code', 'pre', 'script', 'style', 'svg', 'math', 'textarea', 'title']);

/** "ja" for text with kana, "zh-Hans" for other Han text, else undefined. */
export function cjkLang(text) {
	if (KANA.test(text)) return 'ja';
	return HAN.test(text) ? 'zh-Hans' : undefined;
}

/** Split text into plain strings and { lang, text } runs. */
export function splitCjk(text) {
	const out = [];
	let last = 0;
	for (const m of text.matchAll(RUN)) {
		if (m.index > last) out.push(text.slice(last, m.index));
		out.push({ lang: cjkLang(m[0]), text: m[0] });
		last = m.index + m[0].length;
	}
	if (last < text.length) out.push(text.slice(last));
	return out;
}

const tagOf = (node) => node.tagName ?? node.name;
const langOf = (node) => node.properties?.lang ?? node.attributes?.find?.((a) => a.name === 'lang')?.value;

/** A plugin factory: Sätteri calls it once per document, so the "last heading" state never leaks between pages. */
export default function ohgA11y() {
	let heading = '';
	return {
		name: 'ohg-a11y',
		element: {
			filter: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table'],
			visit(node, ctx) {
				if (node.tagName !== 'table') { heading = ctx.textContent(node).replace(/\s+/g, ' ').trim(); return; }
				const p = node.properties ?? {};
				const caption = (node.children ?? []).some((c) => c.type === 'element' && c.tagName === 'caption');
				if (!caption && !p.ariaLabel && !p.ariaLabelledBy && heading) ctx.setProperty(node, 'ariaLabel', heading);
			},
		},
		text(node, ctx) {
			if (!HAN.test(node.value) && !KANA.test(node.value)) return;
			for (let p = ctx.parent(node); p; p = ctx.parent(p)) {
				if (SKIP.has(tagOf(p)) || langOf(p)) return;
			}
			const parts = splitCjk(node.value);
			if (parts.every((part) => typeof part === 'string')) return;
			ctx.replaceNode(node, parts.map((part) => typeof part === 'string'
				? { type: 'text', value: part }
				: { type: 'element', tagName: 'span', properties: { lang: part.lang }, children: [{ type: 'text', value: part.text }] }));
		},
	};
}
