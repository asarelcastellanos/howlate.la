import type { CommuteStop } from './file.ts';

const MAX_QUERY = 80;
const DEFAULT_LIMIT = 8;
const EARTH_RADIUS_M = 6_371_000;
export const MAX_NEAREST_M = 5000;

function words(text: string): string[] {
	return text
		.normalize('NFKD')
		.replace(/[̀-ͯ]/g, '')
		.toLowerCase()
		.split(/[^a-z0-9]+/)
		.filter(Boolean);
}

type Match = { stop: CommuteStop; points: number; tier: number; order: number };

function score(name: string[], tokens: string[]): { points: number; tier: number } {
	const joined = name.join(' ');
	const phrase = tokens.join(' ');
	let total = 0;
	let whole = true;
	for (const token of tokens) {
		if (name.includes(token)) total += 10;
		else if (name.some((word) => word.startsWith(token))) {
			total += 5;
			whole = false;
		} else return { points: 0, tier: 0 };
	}
	if (joined === phrase) total += 1000;
	else if (joined.startsWith(phrase)) total += 400;
	else if (` ${joined}`.includes(` ${phrase}`)) total += 200;
	return { points: total, tier: joined === phrase ? 2 : whole ? 1 : 0 };
}

function matches(stops: readonly CommuteStop[], query: string): Match[] {
	const tokens = words(query.slice(0, MAX_QUERY));
	if (tokens.length === 0) return [];
	const found: Match[] = [];
	stops.forEach((stop, order) => {
		const { points, tier } = score(words(stop[1]), tokens);
		if (points > 0) found.push({ stop, points, tier, order });
	});
	return found;
}

/**
 * The stops whose name has every word of the query as a word or a word start,
 * best first. Case, accents, punctuation and "/" against " / " do not matter.
 * Ties keep the list order. An empty query matches nothing.
 */
export function searchStops(
	stops: readonly CommuteStop[],
	query: string,
	limit = DEFAULT_LIMIT
): CommuteStop[] {
	return matches(stops, query)
		.sort((a, b) => b.points - a.points || a.order - b.order)
		.slice(0, limit)
		.map((r) => r.stop);
}

/**
 * The same matches ordered by name tier first (the whole name, then every
 * query word as a whole word, then a word start), then by distance from the
 * rider in 10 m steps, then by name.
 */
export function searchStopsNear(
	stops: readonly CommuteStop[],
	query: string,
	lat: number,
	lon: number,
	limit = DEFAULT_LIMIT
): CommuteStop[] {
	return matches(stops, query)
		.map((m) => ({ ...m, tens: Math.round(distanceMeters(m.stop, lat, lon) / 10) }))
		.sort((a, b) => b.tier - a.tier || a.tens - b.tens || a.stop[1].localeCompare(b.stop[1]))
		.slice(0, limit)
		.map((r) => r.stop);
}

export function distanceMeters(stop: CommuteStop, lat: number, lon: number): number {
	const rad = Math.PI / 180;
	const dLat = (lat - stop[2]) * rad;
	const dLon = (lon - stop[3]) * rad;
	const h =
		Math.sin(dLat / 2) ** 2 +
		Math.cos(stop[2] * rad) * Math.cos(lat * rad) * Math.sin(dLon / 2) ** 2;
	return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
}

/** The closest stop within `maxMeters`, or undefined when none is that close. */
export function nearestStop(
	stops: readonly CommuteStop[],
	lat: number,
	lon: number,
	maxMeters = MAX_NEAREST_M
): CommuteStop | undefined {
	let best: CommuteStop | undefined;
	let bestMeters = maxMeters;
	for (const stop of stops) {
		const meters = distanceMeters(stop, lat, lon);
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
export function stopsInDirection(
	stops: readonly CommuteStop[],
	routeStopIds: readonly string[]
): CommuteStop[] {
	const byId = new Map(stops.map((stop) => [stop[0], stop]));
	const seen = new Set<string>();
	const out: CommuteStop[] = [];
	for (const id of routeStopIds) {
		const stop = byId.get(id);
		if (stop && !seen.has(id)) {
			seen.add(id);
			out.push(stop);
		}
	}
	return out;
}
