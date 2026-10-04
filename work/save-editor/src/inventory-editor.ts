import { MONEY_MAX, POCKETS, type ItemStack, type PocketId, isPocketId, readInventory } from './inventory.js';
import { usableName } from './catalog.js';
import { createNamePicker } from './name-picker.js';
import type { OriginData } from './rom.js';

export interface InventoryDrafts {
  money?: string;
  pockets: Partial<Record<PocketId, { id: string; quantity: string }[]>>;
  selectedPocket?: PocketId;
}
interface Options {
  bytes: Uint8Array;
  data?: OriginData | undefined;
  drafts: InventoryDrafts;
  onDirty(): void;
  onMoney(money: number): void;
  onPocket(pocket: PocketId, items: ItemStack[]): void;
  onDiscard(pocket?: PocketId): void;
  onSelect(pocket: PocketId): void;
}
function label(text: string, control: HTMLElement): HTMLLabelElement {
  const result = document.createElement('label'); result.append(text, control); return result;
}
function button(text: string, action: () => void): HTMLButtonElement {
  const result = document.createElement('button'); result.type = 'button'; result.className = 'secondary'; result.textContent = text;
  result.addEventListener('click', action); return result;
}
function number(value: string, min: number, max: number): HTMLInputElement {
  const result = document.createElement('input'); result.type = 'number'; result.value = value;
  result.min = String(min); result.max = String(max); result.step = '1'; result.required = true; return result;
}
export function renderInventoryEditor(options: Options): HTMLElement {
  const { bytes, data, drafts } = options;
  const inventory = readInventory(bytes);
  const root = document.createElement('div'); root.className = 'inventory-forms';
  const moneyForm = document.createElement('form'); moneyForm.setAttribute('aria-label', 'Money');
  const money = number(drafts.money ?? String(inventory.money), 0, MONEY_MAX);
  money.addEventListener('input', () => { drafts.money = money.value; options.onDirty(); });
  const moneyApply = document.createElement('button'); moneyApply.type = 'submit'; moneyApply.className = 'primary'; moneyApply.textContent = 'Apply money';
  const moneyActions = document.createElement('div'); moneyActions.className = 'actions';
  moneyActions.append(moneyApply, button('Discard money changes', () => options.onDiscard()));
  moneyForm.append(label('Money', money), moneyActions);
  moneyForm.addEventListener('submit', event => { event.preventDefault(); if (moneyForm.reportValidity()) options.onMoney(Number(money.value)); });
  root.append(moneyForm);

  const pocketForm = document.createElement('form'); pocketForm.setAttribute('aria-label', 'Bag inventory');
  const pocketSelect = document.createElement('select'); pocketSelect.setAttribute('aria-label', 'Bag pocket');
  const pocket = POCKETS.find(p => p.id === drafts.selectedPocket) ?? POCKETS[0]!;
  for (const p of POCKETS) { const option = document.createElement('option'); option.value = p.id; option.textContent = p.label; pocketSelect.append(option); }
  pocketSelect.value = pocket.id;
  pocketSelect.addEventListener('change', () => { if (isPocketId(pocketSelect.value)) options.onSelect(pocketSelect.value); });
  pocketForm.append(label('Bag pocket', pocketSelect));
  const note = document.createElement('p'); note.className = 'small';
  note.textContent = data?.inventory ? 'Search items by name; choices match the selected pocket. Apply each pocket separately. Pending changes in other pockets are retained. Use Remove to delete a stack; quantity starts at 1. Removing a registered item also clears its shortcut.' : 'Reference data unavailable. Reload the editor to enable item changes.';
  pocketForm.append(note);
  const fieldset = document.createElement('fieldset'); fieldset.disabled = !data?.inventory;
  const stacks = drafts.pockets[pocket.id] ?? inventory.pockets[pocket.id]!.map(item => ({ id: String(item.id), quantity: String(item.quantity) }));
  const fields: { id: ReturnType<typeof createNamePicker>; quantity: HTMLInputElement }[] = [];
  const capture = () => { drafts.pockets[pocket.id] = fields.map(f => ({ id: String(f.id.value()), quantity: f.quantity.value })); options.onDirty(); };
  const available = data?.inventory?.items.filter(item => item.pocket === pocket.id && !/^Item #/.test(item.name) && usableName(item.name)) ?? [];
  const rows = document.createElement('div'); rows.className = 'inventory-rows';
  stacks.forEach((item, index) => {
    const row = document.createElement('div'); row.className = 'inventory-row';
    const select = createNamePicker({ label: `Item ${index + 1}`, choices: available, value: Number(item.id), onChange: capture });
    const quantity = number(item.quantity, 1, pocket.maxQuantity); quantity.addEventListener('input', capture);
    fields.push({ id: select, quantity });
    const remove = button('Remove', () => { capture(); drafts.pockets[pocket.id]!.splice(index, 1); options.onSelect(pocket.id); }); remove.setAttribute('aria-label', `Remove item ${index + 1}`);
    row.append(select.root, label(`Quantity ${index + 1}`, quantity), remove); rows.append(row);
  });
  let addChoice = available.find(item => !stacks.some(stack => Number(stack.id) === item.id))?.id ?? 0;
  const addPicker = createNamePicker({ label: 'New item', choices: available.filter(item => !stacks.some(stack => Number(stack.id) === item.id)), value: addChoice, onChange(id) { addChoice = id; } });
  const add = button('Add item', () => {
    capture(); const used = new Set(drafts.pockets[pocket.id]!.map(item => Number(item.id)));
    const item = available.find(item => item.id === addChoice && !used.has(item.id));
    if (item) { drafts.pockets[pocket.id]!.push({ id: String(item.id), quantity: '1' }); options.onSelect(pocket.id); }
  });
  add.disabled = stacks.length >= pocket.capacity || !available.some(item => !stacks.some(stack => Number(stack.id) === item.id));
  const apply = document.createElement('button'); apply.type = 'submit'; apply.className = 'primary'; apply.textContent = 'Apply pocket';
  const actions = document.createElement('div'); actions.className = 'actions'; actions.append(add, apply, button('Discard pocket changes', () => options.onDiscard(pocket.id)));
  const capacity = document.createElement('p'); capacity.className = 'small'; capacity.textContent = `${stacks.length} / ${pocket.capacity} slots · Maximum quantity ${pocket.maxQuantity}`;
  fieldset.append(rows, capacity, addPicker.root, actions); pocketForm.append(fieldset);
  pocketForm.addEventListener('submit', event => { event.preventDefault(); if (data?.inventory && pocketForm.reportValidity()) options.onPocket(pocket.id, fields.map(f => ({ id: f.id.value(), quantity: Number(f.quantity.value) }))); });
  root.append(pocketForm); return root;
}
