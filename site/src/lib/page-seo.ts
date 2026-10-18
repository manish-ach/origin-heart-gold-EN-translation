// Unique search titles and descriptions for the generated reference pages (W-014, W-015).
// The page part only: the route middleware adds " · Origin HeartGold English".
// Records with the same name get the context that tells them apart (a form, a battle place, "(item)" / "(move)").
import { species, items, moves, abilities, trainers, areas, moveLearners, abilityHolders, type Species, type Item, type Move, type Ability, type Area, type Trainer } from './data';
import { playerMoveDescription, playerAbilityDescription, playerItemDescription } from './reference-format.mjs';
import { trainerProfileById } from './trainer-profiles';
import { teamLevelRange, inactiveEncounter } from './trainer-encounters.mjs';
import { clampDescription } from './site-meta';

export interface PageSeo { title: string; description: string; canonical?: string }

const count = (names: string[]) => names.reduce((m, n) => m.set(n, (m.get(n) ?? 0) + 1), new Map<string, number>());
const speciesNames = count(species.map((s) => s.name));
const itemNames = count(items.map((i) => i.name));
const moveNames = count(moves.map((m) => m.name));
const abilityNames = count(abilities.map((a) => a.name));
const firstSentence = (text: string) => (text.match(/^.*?[.!?](?=\s|$)/)?.[0] ?? text).trim();
const dex = (s: Species) => String(s.baseSpeciesId).padStart(4, '0');
const list = (xs: string[]) => xs.length <= 1 ? xs.join('') : `${xs.slice(0, -1).join(', ')} and ${xs[xs.length - 1]}`;

export function pokemonSeo(s: Species): PageSeo {
	const title = (speciesNames.get(s.name) ?? 0) > 1 ? `${s.name} (#${dex(s)}, form ${s.formId})` : `${s.name} (#${dex(s)})`;
	const bst = s.stats.reduce((a, b) => a + b, 0);
	const places = new Set(s.wildEncounters.map((w) => w.area)).size;
	const where = s.unavailableReason ? 'Not available in normal play.'
		: places ? `Found in ${places} ${places === 1 ? 'location' : 'locations'}.`
		: s.acquisitions.length ? 'Gift, trade or one-time encounter.' : '';
	const abil = [...new Set([...s.abilities, ...(s.hidden ? [s.hidden] : [])])];
	const description = clampDescription(`${s.name} (#${dex(s)}${(speciesNames.get(s.name) ?? 0) > 1 ? `, form ${s.formId}` : ''}) in Pokémon Origin HeartGold: ${s.types.join('/')} type, ${abil.length === 1 ? 'ability' : 'abilities'} ${abil.join(', ')}, base stat total ${bst}. ${where} Moves and evolutions.`);
	return { title, description };
}

const sourceKind: Record<string, string> = {
	'item ball': 'item balls', hidden: 'hidden spots', gift: 'gifts', prize: 'prizes', 'bought/exchanged': 'exchanges', shop: 'shops',
	automatic: 'automatic', 'savings reward': 'savings rewards', 'minigame prize': 'minigame prizes', 'held by wild Pokémon': 'wild Pokémon',
	Pickup: 'Pickup', tree: 'trees', stolen: 'stealing in battle',
};
const sameName = (pool: Map<string, number>, name: string) => (pool.get(name) ?? 0) > 0;
const nth = <T extends { id: number; name: string }>(pool: T[], x: T) => pool.filter((p) => p.name === x.name).sort((a, b) => a.id - b.id).indexOf(x) + 1;

export function itemSeo(i: Item): PageSeo {
	let title = i.name;
	if ((itemNames.get(i.name) ?? 0) > 1) title += ` (variant ${nth(items, i)})`;
	else if (sameName(moveNames, i.name) || sameName(abilityNames, i.name)) title += ' (item)';
	const kinds = [...new Set(i.sources.map((s) => sourceKind[s.kind] ?? s.kind))];
	if (i.wildHeld?.length && !kinds.includes('wild Pokémon')) kinds.push('wild Pokémon');
	const where = i.unavailableReason ? 'Not available in normal play.'
		: kinds.length ? `Where to get it: ${list(kinds)}.` : 'No known source in normal play.';
	const price = (itemNames.get(i.name) ?? 0) > 1 && i.price ? ` Sells for $${Math.floor(i.price / 2).toLocaleString('en-US')}.` : '';
	const effect = firstSentence(playerItemDescription(i));
	return { title, description: clampDescription(`${i.name} in Origin HeartGold (${i.pocket} pocket). ${where}${price} ${effect}`) };
}

export function moveSeo(m: Move): PageSeo {
	let title = m.name;
	if ((moveNames.get(m.name) ?? 0) > 1) title += ` (variant ${nth(moves, m)})`;
	else if (sameName(itemNames, m.name) || sameName(abilityNames, m.name) || trainerLabels.has(m.name)) title += ' (move)';
	const stats = [m.power !== '—' && `power ${m.power}`, m.acc !== '—' && `accuracy ${m.acc}${/^\d+$/.test(m.acc) ? '%' : ''}`, `PP ${m.pp}`].filter(Boolean).join(', ');
	const learners = moveLearners.get(m.id)?.length ?? 0;
	const effect = firstSentence(playerMoveDescription(m) || '');
	return { title, description: clampDescription(`${m.name}, a ${m.type}-type ${m.cat.toLowerCase()} move in Origin HeartGold: ${stats}. ${learners} Pokémon can learn it. ${effect}`) };
}

export function abilitySeo(a: Ability): PageSeo {
	let title = a.name;
	if ((abilityNames.get(a.name) ?? 0) > 1) {
		const mask = a.description?.text.match(/Its (.+?) shines/)?.[1];
		title += mask ? ` (${mask})` : ` (variant ${nth(abilities, a)})`;
	} else if (sameName(moveNames, a.name) || sameName(itemNames, a.name)) title += ' (ability)';
	const holders = abilityHolders.get(a.id)?.length ?? 0;
	const effect = firstSentence(playerAbilityDescription(a) || 'No effect description is available.');
	return { title, description: clampDescription(`${title.includes('(') ? title : `${a.name} (ability)`} in Origin HeartGold: ${effect} ${holders ? `${holders} Pokémon can have it.` : 'No Pokémon has it.'}`) };
}

export function locationSeo(a: Area): PageSeo {
	const wild = new Set(a.encounters.flatMap((e) => e.sections.flatMap((s) => s.rows.map((r) => r.id)))).size;
	const parts = [
		wild && `${wild} wild Pokémon`, a.trainers.length && `${a.trainers.length} ${a.trainers.length === 1 ? 'trainer' : 'trainers'}`,
		(a.items.length + a.gifts.length) && `${a.items.length + a.gifts.length} items`, a.shops.length && 'shops',
	].filter(Boolean) as string[];
	const what = parts.length ? list(parts) : 'quests and events';
	return { title: a.name, description: clampDescription(`${a.name} in Origin HeartGold: ${what}, with the quests that happen there.`) };
}

// Trainers: records of one character share a profile page; every record but the first points its canonical to it.
const trainerSeoById = new Map<number, PageSeo>();
const trainerLabels = new Set<string>();
{
	const placeOf = (t: Trainer) => t.places.find((p) => p.map && !inactiveEncounter(p))?.map ?? t.places.find((p) => p.map)?.map ?? null;
	const lead = (t: Trainer) => t.team[0]?.name;
	const singles = new Map<string, Trainer[]>();
	for (const t of trainers) {
		const profile = trainerProfileById.get(t.id)!;
		trainerLabels.add(profile.label);
		if (profile.teams.length === 1) singles.set(profile.label, [...(singles.get(profile.label) ?? []), t]);
	}
	const profileLabels = count([...new Set(trainers.map((t) => trainerProfileById.get(t.id)!))].map((p) => p.label));
	// Narrow a group of same-label records step by step until each title is unique.
	const shortPlace = (t: Trainer) => placeOf(t)?.replace(/ \(.*\)$/, '') ?? null;
	const steps: ((t: Trainer) => string | null)[] = [shortPlace, (t) => lead(t) ? `with ${lead(t)}` : null, (t) => teamLevelRange(t), (t) => `record ${t.id}`];
	const titles = new Map<number, string>();
	for (const [label, group] of singles) {
		const clash = group.length > 1 || (profileLabels.get(label) ?? 0) > 1 || moveNames.has(label) || itemNames.has(label);
		let names = new Map(group.map((t) => [t.id, label]));
		if (clash) {
			let si = 0;
			const extra = new Map<number, string[]>(group.map((t) => [t.id, []]));
			const render = () => new Map(group.map((t) => [t.id, extra.get(t.id)!.length ? `${label}, ${extra.get(t.id)!.join(', ')}` : `${label} (trainer)`]));
			names = render();
			while (si < steps.length && (group.length === 1 ? false : new Set(names.values()).size < group.length || si === 0)) {
				const dupes = count([...names.values()]);
				for (const t of group) {
					if (si > 0 && (dupes.get(names.get(t.id)!) ?? 0) < 2) continue;
					const v = steps[si](t);
					if (v) extra.get(t.id)!.push(v);
				}
				names = render();
				si++;
			}
			if (group.length === 1 && shortPlace(group[0])) names = new Map([[group[0].id, `${label}, ${shortPlace(group[0])}`]]);
		}
		for (const [id, n] of names) titles.set(id, n);
	}
	for (const t of trainers) {
		const profile = trainerProfileById.get(t.id)!;
		const place = placeOf(t);
		const teams = profile.teams.length;
		const title = titles.get(t.id) ?? ((profileLabels.get(profile.label) ?? 0) > 1 || moveNames.has(profile.label) || itemNames.has(profile.label) ? `${profile.label} (trainer)` : profile.label);
		const first = teamLevelRange(profile.teams[0]), last = teamLevelRange(profile.teams[teams - 1]);
		const description = teams === 1
			? (title !== profile.label && !title.endsWith('(trainer)')
				? `${title}: a trainer in Origin HeartGold with ${t.team.length} Pokémon (${teamLevelRange(t)})${lead(t) ? ` led by ${lead(t)}` : ''}. Full team with moves, abilities and held items${place && !title.includes(place.replace(/ \(.*\)$/, '')) ? `, battled at ${place}` : ''}.`
				: `${profile.label} in Origin HeartGold${place ? `, battled at ${place}` : ''}: ${t.team.length} Pokémon (${teamLevelRange(t)})${lead(t) ? ` led by ${lead(t)}` : ''}, with moves, abilities and held items.`)
			: `${profile.label} in Origin HeartGold: all ${teams} teams, ${first === last ? `all at ${first}` : `from ${first} to ${last}`}, with battle places, rematches and partner appearances.`;
		trainerSeoById.set(t.id, { title, description: clampDescription(description), canonical: profile.id === t.id ? undefined : `/trainers/records/${profile.id}/` });
	}
}
export const trainerSeo = (t: Trainer) => trainerSeoById.get(t.id)!;
