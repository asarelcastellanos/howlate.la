import {
	decodeCommuteFile,
	isCommuteIndex,
	isCommuteStops,
	type CommuteFile,
	type CommuteIndex,
	type CommuteStop,
	type DayType
} from '../commute/file.ts';
import { getJson, openRun, type Result } from './load.ts';

export type CommuteRun = {
	index: () => Promise<Result<CommuteIndex>>;
	stops: () => Promise<Result<CommuteStop[]>>;
	route: (line: string, direction: number, dayType: DayType) => Promise<Result<CommuteFile>>;
};

// One openRun result serves all three readers, so the index, the stop list and
// a route file always come from the run that current.json named at that moment.
export async function openCommute(
	base: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<CommuteRun>> {
	const run = await openRun(base, fetchFn);
	if (!run.ok) return run;
	const root = `${base.replace(/\/+$/, '')}/${run.data.pointer.prefix}`;
	return {
		ok: true,
		data: {
			index: () => getJson(`${root}commute/index.json`, fetchFn, isCommuteIndex),
			stops: () => getJson(`${root}commute/stops.json`, fetchFn, isCommuteStops),
			route: async (line, direction, dayType) => {
				const url = `${root}commute/${encodeURIComponent(line)}-${direction}-${dayType}.json`;
				const raw = await getJson<unknown>(url, fetchFn);
				if (!raw.ok) return raw;
				const file = decodeCommuteFile(raw.data, { line, direction, dayType });
				return file ? { ok: true, data: file } : { ok: false, error: { kind: 'shape', url } };
			}
		}
	};
}
