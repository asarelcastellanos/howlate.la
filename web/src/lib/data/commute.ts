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

// Each read opens the run first, as read.ts does, so the files come from the
// run that current.json names.
async function inRun<T>(
	base: string,
	fetchFn: typeof fetch,
	path: string,
	check?: (body: unknown) => body is T
): Promise<Result<T>> {
	const run = await openRun(base, fetchFn);
	if (!run.ok) return run;
	const root = base.replace(/\/+$/, '');
	return getJson<T>(`${root}/${run.data.pointer.prefix}${path}`, fetchFn, check);
}

export const readCommuteIndex = (
	base: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<CommuteIndex>> => inRun(base, fetchFn, 'commute/index.json', isCommuteIndex);

export const readCommuteStops = (
	base: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<CommuteStop[]>> => inRun(base, fetchFn, 'commute/stops.json', isCommuteStops);

export async function readCommuteRoute(
	base: string,
	line: string,
	direction: number,
	dayType: DayType,
	fetchFn: typeof fetch = fetch
): Promise<Result<CommuteFile>> {
	const path = `commute/${encodeURIComponent(line)}-${direction}-${dayType}.json`;
	const raw = await inRun<unknown>(base, fetchFn, path);
	if (!raw.ok) return raw;
	const file = decodeCommuteFile(raw.data);
	if (!file) {
		return { ok: false, error: { kind: 'shape', url: path } };
	}
	return { ok: true, data: file };
}
