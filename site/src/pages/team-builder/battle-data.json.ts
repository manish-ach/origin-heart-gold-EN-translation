// Trainer teams (in play order) and learnsets for the Team Builder's Battle check, fetched only when it opens.
import species from '../../data/species.json';
import areas from '../../data/areas.json';
import trainers from '../../data/trainers.json';
import guide from '../../data/trainer_guide.json';
import tms from '../../data/tms.json';
import { buildBattleData } from '../../lib/battle-check-data.mjs';

const body = JSON.stringify(buildBattleData({ species, areas, trainers, guide, tms } as any));

export function GET() {
  return new Response(body, { headers: { 'Content-Type': 'application/json' } });
}
