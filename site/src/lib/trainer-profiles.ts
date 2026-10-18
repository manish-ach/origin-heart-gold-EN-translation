import { trainers, url } from './data';
import { buildTrainerProfiles, trainerProfilePath } from './trainer-encounters.mjs';

export const { profiles: trainerProfiles, byId: trainerProfileById } = buildTrainerProfiles(trainers);

/** A trainer team's canonical link: its character's main record page, at that team's card. Every record of one
 * character renders the same profile, and the other records' pages are canonical to the main one. */
export const trainerTeamUrl = (id: number) => url(trainerProfilePath(trainerProfileById.get(id)?.id ?? id, id));
/** A character's main record page. */
export const trainerProfileUrl = (id: number) => url(trainerProfilePath(trainerProfileById.get(id)?.id ?? id));
