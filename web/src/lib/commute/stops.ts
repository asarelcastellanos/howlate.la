import { getJson, openRun, type Result } from '../data/load.ts';

export type Stop = { id: string; name: string; lat: number; lon: number };

const MAX_QUERY = 80;
const DEFAULT_LIMIT = 8;
const EARTH_RADIUS_M = 6_371_000;
const MAX_NEAREST_M = 5000;

type StopRow = [string | number, string, number, number];

function isStopRow(row: unknown): row is StopRow {
	return (
		Array.isArray(row) &&
		row.length >= 4 &&
		(typeof row[0] === 'string' || typeof row[0] === 'number') &&
		typeof row[1] === 'string' &&
		Number.isFinite(row[2]) &&
		Number.isFinite(row[3])
	);
}

function isStopList(body: unknown): body is StopRow[] {
	return Array.isArray(body) && body.every(isStopRow);
}

export function toStops(rows: StopRow[]): Stop[] {
	return rows.map(([id, name, lat, lon]) => ({ id: String(id), name, lat, lon }));
}

export async function loadStops(
	base: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<Stop[]>> {
	const run = await openRun(base, fetchFn);
	if (!run.ok) return run;
	const root = base.replace(/\/+$/, '');
	const url = `${root}/${run.data.pointer.prefix}commute/stops.json`;
	const rows = await getJson<StopRow[]>(url, fetchFn, isStopList);
	return rows.ok ? { ok: true, data: toStops(rows.data) } : rows;
}

function words(text: string): string[] {
	return text
		.normalize('NFKD')
		.replace(/[̀-ͯ]/g, '')
		.toLowerCase()
		.split(/[^a-z0-9]+/)
		.filter(Boolean);
}

function score(name: string[], tokens: string[]): number {
	const joined = name.join(' ');
	const phrase = tokens.join(' ');
	let total = 0;
	for (const token of tokens) {
		if (name.includes(token)) total += 10;
		else if (name.some((word) => word.startsWith(token))) total += 5;
		else return 0;
	}
	if (joined === phrase) total += 1000;
	else if (joined.startsWith(phrase)) total += 400;
	else if (` ${joined}`.includes(` ${phrase}`)) total += 200;
	return total;
}

/**
 * The stops whose name has every word of the query as a word or a word start,
 * best first. Case, accents, punctuation and "/" against " / " do not matter.
 * Ties keep the list order. An empty query matches nothing.
 */
export function searchStops(stops: readonly Stop[], query: string, limit = DEFAULT_LIMIT): Stop[] {
	const tokens = words(query.slice(0, MAX_QUERY));
	if (tokens.length === 0) return [];
	const ranked: { stop: Stop; points: number; order: number }[] = [];
	stops.forEach((stop, order) => {
		const points = score(words(stop.name), tokens);
		if (points > 0) ranked.push({ stop, points, order });
	});
	ranked.sort((a, b) => b.points - a.points || a.order - b.order);
	return ranked.slice(0, limit).map((r) => r.stop);
}

function distanceMeters(aLat: number, aLon: number, bLat: number, bLon: number): number {
	const rad = Math.PI / 180;
	const dLat = (bLat - aLat) * rad;
	const dLon = (bLon - aLon) * rad;
	const h =
		Math.sin(dLat / 2) ** 2 + Math.cos(aLat * rad) * Math.cos(bLat * rad) * Math.sin(dLon / 2) ** 2;
	return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
}

/** The closest stop within `maxMeters`, or undefined when none is that close. */
export function nearestStop(
	stops: readonly Stop[],
	lat: number,
	lon: number,
	maxMeters = MAX_NEAREST_M
): Stop | undefined {
	let best: Stop | undefined;
	let bestMeters = maxMeters;
	for (const stop of stops) {
		const meters = distanceMeters(lat, lon, stop.lat, stop.lon);
		if (meters <= bestMeters) {
			best = stop;
			bestMeters = meters;
		}
	}
	return best;
}

/**
 * The stops a route serves in one direction, in the route file's stop order.
 * `routeStopIds` is the `stops` array of that direction's commute file, so a
 * stop that only the other direction's file lists is never returned.
 */
export function stopsInDirection(stops: readonly Stop[], routeStopIds: readonly string[]): Stop[] {
	const byId = new Map(stops.map((stop) => [stop.id, stop]));
	const seen = new Set<string>();
	const out: Stop[] = [];
	for (const id of routeStopIds) {
		const stop = byId.get(String(id));
		if (stop && !seen.has(stop.id)) {
			seen.add(stop.id);
			out.push(stop);
		}
	}
	return out;
}
