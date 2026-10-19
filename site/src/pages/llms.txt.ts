// /llms.txt (llmstxt.org): the site summary and its main links for AI assistants and search crawlers.
import type { APIRoute } from 'astro';
import { intro, docs, pageUrl, abs } from '../lib/llms';

export const GET: APIRoute = async () => {
	const { by, chapters } = await docs();
	const link = (id: string, label?: string) => {
		const d = by.get(id);
		const text = d?.data.description?.replace(/^Origin HeartGold walkthrough, chapter \d+: /, '');
		return `- [${label ?? d?.data.title ?? id}](${pageUrl(id)})${text ? `: ${text}` : ''}`;
	};
	const ref = (path: string, label: string, text: string) => `- [${label}](${abs(path)}): ${text}`;
	const lines = [
		...intro(),
		'',
		'## Start here',
		'',
		link('patch', 'Download the English patch'),
		link('faq', 'FAQ'),
		link('about', 'How to play and how to use the guide'),
		link('difficulty'),
		link('mechanics'),
		'',
		'## Walkthrough (quest guide)',
		'',
		link('guide', 'Walkthrough overview'),
		...chapters.map((d) => link(d.id)),
		link('guide/known-issues'),
		link('guide/hidden-items'),
		'',
		'## Reference',
		'',
		ref('/pokemon/', 'Pokémon', 'every Pokémon with types, abilities, base stats, moves, evolutions and where to catch it'),
		ref('/locations/', 'Locations', 'wild Pokémon, trainers, items, shops and quests for every place'),
		ref('/items/', 'Items', 'every item and where to get it'),
		ref('/moves/', 'Moves', 'move stats, effects, changes in this hack and who learns them'),
		ref('/trainers/', 'Trainers', 'Gym Leaders, rivals and every other trainer team'),
		ref('/abilities/', 'Abilities', 'ability effects and the Pokémon that have them'),
		ref('/tms/', 'TMs and HMs', 'every TM and HM, where to get it and compatible Pokémon'),
		ref('/tutors/', 'Move tutors', 'who teaches which move, where and for what'),
		ref('/team-builder/', 'Team Builder', 'plan a team of six with catch locations and a damage calculator'),
		ref('/damage-calc/', 'Damage calculator', 'your team against every trainer in route order, with editable sets on both sides'),
		ref('/save-editor/', 'Save editor', 'edit a save file in the browser'),
		'',
		'## Project',
		'',
		ref('/changelog/', 'Changelog and contributors', 'what changed in each release, and who helped'),
		ref('/about/#credits', 'Credits', 'the original hack, v4, the Chinese patches, the v3 English and graphics sources'),
		ref('/about/#licence', 'Licence', 'guide text all rights reserved; linking and short quotes welcome'),
		ref('/contribute/', 'Report a problem or contribute', 'how to report mistakes'),
		'',
		'## Optional',
		'',
		`- [Full text](${abs('/llms-full.txt')}): the start-here pages, the FAQ and every walkthrough chapter's overview in one Markdown file`,
		'',
	];
	return new Response(lines.join('\n'), { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
