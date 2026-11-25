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

export function rideTimes(file: CommuteFile, start: number, from: string, to: string): RideResult {
	const pattern = file.patterns.find((p) => p.start === start);
	if (!pattern) return { ok: false, error: { kind: 'no-pattern' } };
	const order = pattern.stopIndexes.map((i) => file.stops[i]);
	const a = order.indexOf(from);
	if (a < 0) return { ok: false, error: { kind: 'stop-not-served', stop: from } };
	if (!order.includes(to)) return { ok: false, error: { kind: 'stop-not-served', stop: to } };
	const b = order.indexOf(to, a + 1);
	if (b < 0) return { ok: false, error: { kind: 'to-not-after-from' } };
	const data: RideTime[] = [];
	pattern.dayIndexes.forEach((dayIndex, column) => {
		const times = columnTimes(pattern, column);
		const atA = times[a];
		const atB = times[b];
		if (atA === null || atB === null) return;
		data.push({ day: file.days[dayIndex], seconds: (atB - atA) * UNIT });
	});
	return { ok: true, data };
}
