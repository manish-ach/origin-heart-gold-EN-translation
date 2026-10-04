import { editorErrorMessage } from './errors.js';
import { decodePokemon, type PokemonStatChanges } from './pokemon.js';
import { mapStats, calculateStats, adjustCurrentHp, type StatValues } from './stats.js';
import type { OriginData } from './rom.js';

export const STAT_KEYS = ['hp', 'attack', 'defense', 'spAttack', 'spDefense', 'speed'] as const;
const LABELS: Record<keyof StatValues, string> = { hp: 'HP', attack: 'Attack', defense: 'Defense', speed: 'Speed', spAttack: 'Sp. Atk', spDefense: 'Sp. Def' };
const NATURES = ['Hardy','Lonely','Brave','Adamant','Naughty','Bold','Docile','Relaxed','Impish','Lax','Timid','Hasty','Serious','Jolly','Naive','Modest','Mild','Quiet','Bashful','Rash','Calm','Gentle','Sassy','Careful','Quirky'];
export type StatGroup = 'ivs' | 'evs' | 'training';
type ValueDraft = Record<keyof StatValues, string>;
export interface StatDrafts { ivs?: ValueDraft; evs?: ValueDraft; training?: {level: string; nature: string} }
interface Options {
  record: Uint8Array;
  data?: OriginData | undefined;
  drafts: StatDrafts;
  onDirty(): void;
  onApply(changes: PokemonStatChanges, group: StatGroup): void;
  onDiscard(group: StatGroup): void;
}
function text<K extends keyof HTMLElementTagNameMap>(tag: K, value: string): HTMLElementTagNameMap[K] {
  const result = document.createElement(tag); result.textContent = value; return result;
}
function values(draft: ValueDraft | undefined, fallback: StatValues): StatValues {
  return mapStats(key => draft ? (draft[key].trim() === '' ? NaN : Number(draft[key])) : fallback[key]);
}
function draftValues(current: StatValues): ValueDraft {
  return mapStats(key => String(current[key]));
}
function actions(form: HTMLFormElement, label: string, discard: () => void): void {
  const row = document.createElement('div'); row.className = 'actions';
  const apply = text('button', label); apply.type = 'submit'; apply.className = 'primary';
  const reset = text('button', 'Discard'); reset.type = 'button'; reset.className = 'secondary';
  reset.addEventListener('click', discard); row.append(apply, reset); form.append(row);
}

export function renderStatEditor(options: Options): HTMLElement {
  const { record, data, drafts } = options;
  const pokemon = decodePokemon(record);
  const section = document.createElement('section'); section.className = 'stats-editor';
  section.setAttribute('aria-label', 'Stats editor');
  section.append(text('h3', 'Stats'));
  if (!pokemon.party) { section.append(text('p', 'Party statistics are unavailable.')); return section; }
  const party = pokemon.party;
  section.append(text('p', `Level ${party.level} · ${NATURES[pokemon.nature] ?? 'Unknown nature'}`));
  const preview = document.createElement('div'); preview.className = 'stat-preview'; preview.setAttribute('aria-label', 'Battle stats');
  const health = text('p', `Current HP: ${party.currentHp} / ${party.stats.hp}`); health.className = 'small';
  const previewStatus = text('p', ''); previewStatus.className = 'small'; previewStatus.setAttribute('role', 'status');
  section.append(preview, health, previewStatus);
  let personal: ReturnType<OriginData['getPersonal']> | undefined;
  let blocked = !data || pokemon.isEgg;
  if (data) {
    try { personal = data.getPersonal(pokemon.speciesId, pokemon.form); }
    catch (error) { blocked = true; section.append(text('p', editorErrorMessage(error))); }
  }
  if (pokemon.isEgg) section.append(text('p', 'Egg stat editing is not supported yet.'));
  else if (!data) section.append(text('p', 'Reference data unavailable. Reload the editor to enable stat changes.'));
  else section.append(text('p', 'Battle stats update from level, nature, IVs and EVs. IV and EV changes are applied separately.'));

  function refreshPreview(): void {
    preview.replaceChildren();
    let result = party.stats;
    let nextHp = party.currentHp;
    const changed = Boolean(drafts.ivs || drafts.evs || drafts.training);
    previewStatus.textContent = '';
    previewStatus.className = 'small';
    if (changed && personal) {
      try {
        result = calculateStats(personal.baseStats, values(drafts.ivs, pokemon.ivs), values(drafts.evs, pokemon.evs),
          drafts.training ? Number(drafts.training.level) : party.level,
          drafts.training ? (drafts.training.nature === '' ? NaN : Number(drafts.training.nature)) : pokemon.nature, pokemon.speciesId);
        nextHp = adjustCurrentHp(party.currentHp, party.stats.hp, result.hp, pokemon.speciesId);
        previewStatus.textContent = 'Preview includes all pending stat changes. Each Apply button saves only its section.';
      } catch (error) {
        previewStatus.textContent = editorErrorMessage(error);
        previewStatus.className = 'small stat-error';
      }
    }
    for (const key of STAT_KEYS) {
      const item = document.createElement('div');
      item.append(text('span', LABELS[key]), text('strong', result[key] === party.stats[key] ? String(result[key]) : `${party.stats[key]} → ${result[key]}`));
      preview.append(item);
    }
    health.textContent = `Current HP: ${nextHp} / ${result.hp}${changed ? ' (preview)' : ''}`;
  }
  const training = document.createElement('form'); training.className = 'training-form'; training.setAttribute('aria-label', 'Level and nature');
  const trainingSet = document.createElement('fieldset'); trainingSet.disabled = blocked;
  trainingSet.append(text('legend', 'Level & nature'));
  const levelLabel = text('label', 'Level'); levelLabel.htmlFor = 'stat-level';
  const level = document.createElement('input'); level.id = 'stat-level'; level.type = 'number'; level.min = '1'; level.max = '100'; level.step = '1'; level.required = true;
  level.value = drafts.training?.level ?? String(party.level);
  const natureLabel = text('label', 'Nature'); natureLabel.htmlFor = 'stat-nature';
  const nature = document.createElement('select'); nature.id = 'stat-nature'; nature.required = true;
  NATURES.forEach((name, id) => { const option = text('option', name); option.value = String(id); nature.append(option); });
  nature.value = drafts.training?.nature ?? String(pokemon.nature);
  const trainingChanged = () => { drafts.training = { level: level.value, nature: nature.value }; options.onDirty(); refreshPreview(); };
  level.addEventListener('input', trainingChanged); nature.addEventListener('change', trainingChanged);
  trainingSet.append(levelLabel, level, natureLabel, nature); training.append(trainingSet);
  actions(training, 'Apply level & nature', () => options.onDiscard('training'));
  for (const button of training.querySelectorAll('button')) button.disabled = blocked;
  training.addEventListener('submit', event => {
    event.preventDefault();
    if (blocked || !training.reportValidity()) return;
    options.onApply({level: Number(level.value), nature: Number(nature.value)}, 'training');
  });
  section.append(training);
  const columns = document.createElement('div'); columns.className = 'iv-ev-columns';
  for (const group of ['ivs', 'evs'] as const) {
    const isIv = group === 'ivs';
    const form = document.createElement('form'); form.className = 'stat-group'; form.setAttribute('aria-label', isIv ? 'Individual values' : 'Effort values');
    const fieldset = document.createElement('fieldset'); fieldset.disabled = blocked;
    fieldset.append(text('legend', isIv ? 'Individual values (IVs)' : 'Effort values (EVs)'));
    const inputs = mapStats(() => document.createElement('input'));
    const total = text('p', ''); total.className = 'small';
    const refreshTotal = () => {
      if (isIv) { total.textContent = '0–31 per stat'; return; }
      const sum = STAT_KEYS.reduce((sum, key) => sum + (inputs[key].value === '' ? NaN : Number(inputs[key].value)), 0);
      total.textContent = `EV total: ${Number.isFinite(sum) ? sum : '—'} / 510 · 0–255 per stat`;
      total.className = sum > 510 ? 'small stat-error' : 'small';
    };
    for (const key of STAT_KEYS) {
      const row = document.createElement('div'); row.className = 'stat-field';
      const label = text('label', LABELS[key]); label.htmlFor = `${group}-${key}`;
      const input = inputs[key]; input.type = 'number'; input.id = `${group}-${key}`;
      input.setAttribute('aria-label', `${isIv ? 'IV' : 'EV'} ${LABELS[key]}`);
      input.min = '0'; input.max = isIv ? '31' : '255'; input.step = '1'; input.required = true;
      input.value = drafts[group]?.[key] ?? String(pokemon[group][key]); inputs[key] = input;
      input.addEventListener('input', () => {
        const draft = drafts[group] ?? draftValues(pokemon[group]);
        draft[key] = input.value; drafts[group] = draft; options.onDirty(); refreshTotal(); refreshPreview();
      });
      row.append(label, input); fieldset.append(row);
    }
    fieldset.append(total); form.append(fieldset);
    actions(form, isIv ? 'Apply IVs' : 'Apply EVs', () => options.onDiscard(group));
    for (const button of form.querySelectorAll('button')) button.disabled = blocked;
    form.addEventListener('submit', event => {
      event.preventDefault(); if (blocked || !form.reportValidity()) return;
      const edited = mapStats(key => Number(inputs[key].value));
      options.onApply({[group]: edited}, group);
    });
    refreshTotal(); columns.append(form);
  }
  section.append(columns); refreshPreview();
  return section;
}
