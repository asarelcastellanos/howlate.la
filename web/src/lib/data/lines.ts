import { isLineList } from '../lineHead.ts';
import list from './lines.json' with { type: 'json' };

// Refreshed by `npm run lines:refresh`. A file that stopped matching the shape fails
// the build here, not as a blank title on a page.
if (!isLineList(list)) throw new Error('src/lib/data/lines.json is not a list of lines');

/** Every line in the published index when the file was last refreshed. */
export const LINE_LIST = list;
