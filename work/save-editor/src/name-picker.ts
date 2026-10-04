export interface NamedChoice { id: number; name: string }
export function searchChoices(choices: readonly NamedChoice[], query: string): NamedChoice[] {
  const normalize = (value: string) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase().replace(/[’']/g, '');
  const terms = normalize(query).trim().split(/\s+/).filter(Boolean);
  return choices.filter(choice => terms.every(term => normalize(choice.name).includes(term)));
}
/** Search changes visible options; only explicit selection edits a save draft. */
export function createNamePicker(options: {label: string; choices: readonly NamedChoice[]; value: number; onChange(id: number): void}) {
  let selected = options.value;
  const counts = new Map<string, number>();
  for (const choice of options.choices) counts.set(choice.name, (counts.get(choice.name) ?? 0) + 1);
  const root = document.createElement('div'); root.className = 'name-picker';
  const search = document.createElement('input'); search.type = 'search'; search.placeholder = 'Search by name…'; search.setAttribute('aria-label', `Search ${options.label.toLowerCase()}`);
  const select = document.createElement('select'); select.setAttribute('aria-label', options.label);
  const current = document.createElement('p'); current.className = 'small';
  const diagnostic = document.createElement('details'); const summary = document.createElement('summary'); summary.textContent = 'Identifier';
  const identifier = document.createElement('span'); diagnostic.append(summary, identifier);
  const count = document.createElement('p'); count.className = 'small'; count.setAttribute('role', 'status');
  const name = () => options.choices.find(choice => choice.id === selected)?.name ?? 'Name unavailable';
  const refresh = () => {
    const matches = searchChoices(options.choices, search.value);
    select.replaceChildren();
    const placeholder = document.createElement('option'); placeholder.value = ''; placeholder.textContent = search.value ? 'Choose a result…' : 'Choose by name…'; select.append(placeholder);
    for (const choice of matches) { const option = document.createElement('option'); option.value = String(choice.id); option.textContent = (counts.get(choice.name) ?? 0) > 1 ? `${choice.name} (variant ${choice.id})` : choice.name; select.append(option); }
    select.value = matches.some(choice => choice.id === selected) ? String(selected) : '';
    current.textContent = `Selected: ${name()}`;
    identifier.textContent = String(selected);
    count.textContent = search.value ? `${matches.length} matching ${matches.length === 1 ? 'name' : 'names'}` : '';
  };
  search.addEventListener('input', refresh);
  select.addEventListener('change', () => { if (select.value === '') return; const next = Number(select.value); if (next === selected) { search.value = ''; refresh(); return; } selected = next; search.value = ''; refresh(); options.onChange(selected); });
  root.append(search, select, current, count, diagnostic); refresh();
  return {root, value: () => selected, setValue(id: number) { selected = id; search.value = ''; refresh(); }};
}
