import { bundledReference } from './generated-reference.js';
import { extras } from './generated-extras.js';
/** Types and abilities from the ROM's personal table, keyed through Origin's form lookup. */
export interface SpeciesInfo {
  types: [number, number]; abilities: [number, number, number];
  /** 0 always male, 254 always female, 255 genderless, otherwise female when (PID & 0xff) < ratio. */
  genderRatio: number; baseFriendship: number;
  /** Level-up moves as [level, move] pairs; level 0 means learned on evolution. */
  learnset: [number, number][];
}
const forms = new Map<string, number>();
for (const [species, index, form] of bundledReference.payload.forms) {
  const key = `${species}/${form}`;
  if (!forms.has(key)) forms.set(key, index!);
}
export function personalIndex(speciesId: number, form: number): number {
  return form === 0 ? speciesId : forms.get(`${speciesId}/${form}`) ?? speciesId;
}
export function speciesInfo(speciesId: number, form: number): SpeciesInfo | undefined {
  const row = extras.payload.personal[personalIndex(speciesId, form)];
  if (!row) return undefined;
  const flat = extras.payload.learnsets[personalIndex(speciesId, form)] ?? [];
  const learnset: [number, number][] = [];
  for (let i = 0; i + 1 < flat.length; i += 2) learnset.push([flat[i]!, flat[i + 1]!]);
  return {types: [row[0], row[1]], abilities: [row[2], row[3], row[4]], genderRatio: row[5], baseFriendship: row[6], learnset};
}
export const TYPE_NAMES: readonly string[] = extras.payload.types;
export function typeName(id: number): string { return TYPE_NAMES[id] ?? '???'; }
export interface AbilityChoice { id: number; name: string; description: string }
export const ABILITIES: readonly AbilityChoice[] = extras.payload.abilities.flatMap((entry, id) =>
  entry ? [{id, name: entry[0], description: entry[1]}] : []);
const abilityMap = new Map(ABILITIES.map(a => [a.id, a]));
export function getAbility(id: number): AbilityChoice | undefined { return abilityMap.get(id); }

/** The last four distinct moves learned by level-up at or below `level`, like a wild Pokémon. */
export function defaultMoves(info: SpeciesInfo, level: number): number[] {
  const moves: number[] = [];
  for (const [learnLevel, move] of info.learnset) {
    if (learnLevel > level || !move) continue;
    const existing = moves.indexOf(move);
    if (existing >= 0) moves.splice(existing, 1);
    moves.push(move);
  }
  return moves.slice(-4);
}
export type Gender = 'male' | 'female' | 'genderless';
export function possibleGenders(ratio: number): Gender[] {
  if (ratio === 255) return ['genderless'];
  if (ratio === 254) return ['female'];
  if (ratio === 0) return ['male'];
  return ['male', 'female'];
}
