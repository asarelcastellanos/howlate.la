// Made-up data in the shapes of pipeline/schemas/line.schema.json. The specimen
// page and the tests draw from it, so a chart can be checked without the network.
import type { Hour, Stop } from '../data/types';

/** Friday 17:00, the hour the heatmap test expects to be the worst. */
export const HOT_HOUR = 4 * 24 + 17;

/** Tuesday 06:00, an hour with 2 arrivals and a huge median, which must never rank as worst. */
export const THIN_HOUR = 24 + 6;

/**
 * Every hour of the week with a gentle morning and evening bump, except
 * Saturday 02:00 to 03:59 and Sunday before 05:00, which have no data. One hot
 * hour at Friday 17:00 is far above the rest, and Tuesday 06:00 has too few
 * arrivals to judge.
 */
export function fixtureProfile(): Hour[] {
	const profile: Hour[] = [];
	for (let h = 0; h < 168; h++) {
		const hour = h % 24;
		const thin = h === THIN_HOUR;
		const gap = (h >= 122 && h <= 123) || (h >= 144 && h < 149);
		if (gap) continue;
		const rush = hour >= 7 && hour <= 9 ? 1 : hour >= 15 && hour <= 18 ? 2 : 0;
		const med = h === HOT_HOUR ? 720 : thin ? 1500 : 20 + rush * 35 + (h % 7) * 3;
		const p90 = h === HOT_HOUR ? 1500 : thin ? 2400 : med * 4 + 90;
		const n = thin ? 2 : 400 + rush * 200;
		const pct5 = h === HOT_HOUR ? 62.5 : 4 + rush * 6;
		profile.push({ h, n, sched: n + 90, med, p90, pct5, ontime: 90 - pct5 });
	}
	return profile;
}

/**
 * 36 stops in route order with a weekday evening cell, a delay that grows along
 * the route, three stops with 3 arrivals (hollow dots), and two stops with no
 * weekday evening cell at all (no dot).
 */
export function fixtureStops(): Stop[] {
	return Array.from({ length: 36 }, (_, i) => {
		const thin = i % 12 === 5;
		const n = thin ? 3 : 200 + ((i * 37) % 300);
		const med = 30 + i * 11 + ((i * 53) % 90);
		const cell = { d: 'wk-pm', n, sched: n + 40, med, p90: med * 3, pct5: 10 };
		return {
			id: `S${i + 1}`,
			name: `Example Station ${i + 1}`,
			lat: null,
			lon: null,
			seq: i + 1,
			n,
			est: 0,
			sched: n + 40,
			all: { med, p90: med * 3, pct5: 10, ontime: 80 },
			cells: i === 7 || i === 20 ? [] : [cell]
		};
	});
}
