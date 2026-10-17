// Origin HeartGold's base stat and type changes, computed at build time from the game data
// (src/data/species.json) and the official values in src/data/official_species.json.
// official_species.json lists only entries whose official stats or types differ from the hack;
// work/tools/site/species_comparisons.py checks it (README: "Base stat and type changes").
import officialData from '../data/official_species.json';
import { species, availabilityToken, STAT_NAMES, type Species } from './data';

interface OfficialEntry { stats?: number[]; types?: string[]; comparedWith?: string; source?: string }
const official = (officialData as { species: Record<string, OfficialEntry> }).species;
const bySlug = new Map(species.map((s) => [s.slug, s]));

export interface SpeciesChange {
	s: Species;
	/** Official stats and types; for custom forms those of the ordinary species. */
	officialStats: number[];
	officialTypes: string[];
	/** Custom form compared with its ordinary species (the slug of that species). */
	comparedWith?: Species;
	statsChanged: boolean;
	typesChanged: boolean;
	officialTotal: number;
	total: number;
	/** 'documented' when the site lists a way to get it in normal play. */
	availability: ReturnType<typeof availabilityToken>;
}

const sum = (a: number[]) => a.reduce((x, y) => x + y, 0);
const sameTypes = (a: string[], b: string[]) => [...a].sort().join('/') === [...b].sort().join('/');

function officialOf(slug: string): { stats: number[]; types: string[] } | undefined {
	const entry = official[slug];
	if (entry?.comparedWith) return officialOf(entry.comparedWith);
	const s = bySlug.get(slug);
	if (!s) return undefined;
	return { stats: entry?.stats ?? s.stats, types: entry?.types ?? s.types };
}

export const speciesChanges: SpeciesChange[] = species.flatMap((s) => {
	const entry = official[s.slug];
	const o = entry && officialOf(s.slug);
	if (!entry || !o) return [];
	const statsChanged = o.stats.some((v, i) => v !== s.stats[i]);
	const typesChanged = !sameTypes(o.types, s.types);
	if (!statsChanged && !typesChanged) return [];
	return [{ s, officialStats: o.stats, officialTypes: o.types, comparedWith: entry.comparedWith ? bySlug.get(entry.comparedWith) : undefined,
		statsChanged, typesChanged, officialTotal: sum(o.stats), total: sum(s.stats), availability: availabilityToken(s) }];
});
export const changeBySlug = new Map(speciesChanges.map((c) => [c.s.slug, c]));

/** "Attack 80 → 90, Speed 60 → 50" */
export function statDiffText(c: SpeciesChange) {
	return c.officialStats.flatMap((v, i) => (v === c.s.stats[i] ? [] : [`${STAT_NAMES[i]} ${v} → ${c.s.stats[i]}`])).join(', ');
}

export function signed(n: number) {
	return n > 0 ? `+${n}` : n < 0 ? `−${-n}` : '±0';
}

/** Sections in Pokédex order: regions of the base species, then official forms, then the hack's own forms. */
export const SECTIONS = ['Kanto', 'Johto', 'Hoenn', 'Sinnoh', 'Unova', 'Kalos', 'Alola', 'Galar and Hisui', 'Paldea'] as const;
export function sectionOf(c: SpeciesChange) {
	if (c.comparedWith) return 'Custom forms';
	return c.s.formId > 0 || !SECTIONS.includes(c.s.region as (typeof SECTIONS)[number]) ? 'Official forms' : c.s.region;
}
export function grouped(list: SpeciesChange[]) {
	const order = [...SECTIONS, 'Official forms', 'Custom forms'];
	return order.map((name) => ({ name, rows: list.filter((c) => sectionOf(c) === name) })).filter((g) => g.rows.length);
}
export const slugOf = (name: string) => name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
