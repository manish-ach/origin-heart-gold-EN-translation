import { decodePokemon, isPokerusStatus, type PokerusStatus } from './pokemon.js';

export interface TraitDrafts { shiny?: boolean; pokerus?: PokerusStatus }
interface Options {
  record: Uint8Array; drafts: TraitDrafts; onDirty(): void;
  onShiny(value: boolean): void; onPokerus(value: PokerusStatus): void;
  onDiscard(group: keyof TraitDrafts): void;
}
function text<K extends keyof HTMLElementTagNameMap>(tag: K, value: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag); node.textContent = value; return node;
}
export function renderTraitEditor(options: Options): HTMLElement {
  const pokemon = decodePokemon(options.record);
  const section = document.createElement('section'); section.className = 'stats-editor';
  section.setAttribute('aria-label', 'Shiny and Pokérus');
  section.append(text('h3', 'Shiny & Pokérus'));
  for (const group of ['shiny', 'pokerus'] as const) {
    const label = group === 'shiny' ? 'Shiny' : 'Pokérus';
    const form = document.createElement('form'); form.setAttribute('aria-label', label);
    const select = document.createElement('select'); select.id = `trait-${group}`;
    const choices = group === 'shiny' ? [['false', 'Not shiny'], ['true', 'Shiny']] as const :
      [['none', 'None'], ['infected', 'Infected'], ['cured', 'Cured']] as const;
    for (const [value, caption] of choices) {
      const option = text('option', caption); option.value = value;
      if (group === 'shiny' && value === 'false' && pokemon.naturalShiny) option.disabled = true;
      select.append(option);
    }
    select.value = group === 'shiny' ? String(options.drafts.shiny ?? pokemon.shiny) : options.drafts.pokerus ?? pokemon.pokerus.status;
    const caption = text('label', label); caption.htmlFor = select.id;
    const description = text('p', group === 'shiny' ? (pokemon.naturalShiny ?
      'This Pokémon is naturally shiny. Turning it off would change its identity, so that is not supported.' :
      'Uses Origin’s shiny setting. Nature, gender, ability and Pokémon identity stay unchanged.') :
      `Current status: ${pokemon.pokerus.status === 'infected' ? `infected · ${pokemon.pokerus.days} day${pokemon.pokerus.days === 1 ? '' : 's'} remaining` : pokemon.pokerus.status}. A new infection starts with one day remaining. If time has passed since your last save, the game may cure it on load. Cured keeps the infection history.`);
    description.className = 'small';
    select.addEventListener('change', () => {
      if (group === 'shiny') {
        if (select.value !== 'true' && select.value !== 'false') return;
        options.drafts.shiny = select.value === 'true';
      } else {
        if (!isPokerusStatus(select.value)) return;
        options.drafts.pokerus = select.value;
      }
      options.onDirty();
    });
    const actions = document.createElement('div'); actions.className = 'actions';
    const apply = text('button', `Apply ${label}`); apply.type = 'submit'; apply.className = 'primary';
    const discard = text('button', 'Discard'); discard.type = 'button'; discard.className = 'secondary';
    discard.addEventListener('click', () => options.onDiscard(group));
    actions.append(apply, discard); form.append(caption, select, description, actions);
    form.addEventListener('submit', event => {
      event.preventDefault();
      if (group === 'shiny') {
        if (select.value === 'true' || select.value === 'false') options.onShiny(select.value === 'true');
      } else if (isPokerusStatus(select.value)) options.onPokerus(select.value);
    });
    section.append(form);
  }
  return section;
}
