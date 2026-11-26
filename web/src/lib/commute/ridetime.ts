import { UNIT, type CommuteFile, type Pattern } from './file.ts';

export type RideTime = {
	day: string;
	/** Each stop time is rounded to 10 s, so this is off by up to 10 s (ADR-0004, A2). */
	seconds: number;
};

export type RideError =
	| { kind: 'no-pattern' }
	| { kind: 'stop-not-served'; stop: string }
	| { kind: 'to-not-after-from' };

export type RideResult = { ok: true; data: RideTime[] } | { ok: false; error: RideError };

export function columnTimes(pattern: Pattern, column: number): (number | null)[] {
	let total = 0;
	return pattern.rows.map((row) => {
		const value = row[column];
		if (value === null) return null;
		total += value;
		return total;
	});
}

// A day appears once for each kind of trip the pattern ran that day, so a day with
// two columns that both have a time at A and at B counts once, at its earliest time
// at each stop. A column missing either stop counts for nothing, so A and B never
// come from two different trips.
export function dayTimes(
	pattern: Pattern,
	a: number,
	b: number
): { dayIndex: number; atA: number; atB: number }[] {
	const found = new Map<number, { dayIndex: number; atA: number; atB: number }>();
	pattern.dayIndexes.forEach((dayIndex, column) => {
		const times = columnTimes(pattern, column);
		const atA = times[a];
		const atB = times[b];
		if (atA === null || atB === null) return;
		const seen = found.get(dayIndex);
		found.set(dayIndex, {
			dayIndex,
			atA: seen ? Math.min(seen.atA, atA) : atA,
			atB: seen ? Math.min(seen.atB, atB) : atB
		});
	});
	return [...found.values()];
}

export function rideTimes(file: CommuteFile, start: number, from: string, to: string): RideResult {
	const pattern = file.patterns.find((p) => p.start === start);
	if (!pattern) return { ok: false, error: { kind: 'no-pattern' } };
	const order = pattern.stopIndexes.map((i) => file.stops[i]);
	const a = order.indexOf(from);
	if (a < 0) return { ok: false, error: { kind: 'stop-not-served', stop: from } };
	if (!order.includes(to)) return { ok: false, error: { kind: 'stop-not-served', stop: to } };
	const b = order.indexOf(to, a + 1);
	if (b < 0) return { ok: false, error: { kind: 'to-not-after-from' } };
	const data = dayTimes(pattern, a, b).map(({ dayIndex, atA, atB }) => ({
		day: file.days[dayIndex],
		seconds: (atB - atA) * UNIT
	}));
	return { ok: true, data };
}
