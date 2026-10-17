// Compact data for the damage calculator, fetched lazily by the Team Builder (see src/lib/calc/index.ts).
import species from '../../data/species.json';
import moves from '../../data/moves.json';
import abilities from '../../data/abilities.json';
import items from '../../data/items.json';
import trainers from '../../data/trainers.json';
import { formChanges } from '../../lib/verified-mechanics';
import { buildCalcData } from '../../lib/calc/data-projection.ts';

const body = JSON.stringify(buildCalcData({ species, moves, abilities, items, trainers, formChanges }));

export function GET() {
  return new Response(body, { headers: { 'Content-Type': 'application/json' } });
}
