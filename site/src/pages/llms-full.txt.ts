// /llms-full.txt: the start-here pages, the FAQ and each walkthrough chapter's overview as clean Markdown.
import type { APIRoute } from 'astro';
import { intro, docs, cleanMarkdown, chapterOverview, pageUrl } from '../lib/llms';

const START = ['patch', 'faq', 'about', 'difficulty', 'mechanics', 'guide'];

export const GET: APIRoute = async () => {
	const { by, chapters } = await docs();
	const page = (id: string, text: string) => {
		const d = by.get(id)!;
		return `## ${d.data.title}\n\nSource: ${pageUrl(id)}\n\n${text.replace(/^(#{1,5}) /gm, '#$1 ')}`;
	};
	const parts = [
		intro().join('\n'),
		...START.filter((id) => by.has(id)).map((id) => page(id, cleanMarkdown(by.get(id)!.body ?? '', id))),
		...chapters.map((d) => page(d.id, chapterOverview(d))),
	];
	return new Response(parts.join('\n\n---\n\n') + '\n', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
