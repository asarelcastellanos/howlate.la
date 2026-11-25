import { UNIT, type CommuteFile, type DayType, type Pattern } from './file.ts';
import { columnTimes, rideTimes } from './ridetime.ts';

export const MIN_DAYS = 8;
const NEAREST_RANK = 0.9;

export type Mode = 'leave' | 'arrive';

export type Answer =
	| {
			kind: 'answer';
			line: string;
			start: number;
			departMinute: number;
			medianLateMinutes: number;
			badLateMinutes: number;
			rideMinutes: number;
			days: number;
	  }
	| { kind: 'not-enough-data'; line: string; start: number; departMinute: number; days: number }
	| { kind: 'no-bus'; mode: Mode };

type Candidate = {
	start: number;
	departMinute: number;
	arrive90Minute: number;
	medianLateSeconds: number;
	badLateSeconds: number;
	rideSeconds: number;
	days: number;
};

const DAY_TYPES: DayType[] = ['weekday', 'saturday', 'sunday'];

export function dayTypeFor(choice: string): DayType | null {
	const named = DAY_TYPES.find((d) => d === choice);
	if (named) return named;
	const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(choice);
	if (!m) return null;
	const date = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
	if (date.toISOString().slice(0, 10) !== choice) return null;
	const dow = date.getUTCDay();
	return dow === 0 ? 'sunday' : dow === 6 ? 'saturday' : 'weekday';
}

export function todayDayType(now: Date): DayType {
	const la = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Los_Angeles' }).format(now);
	return dayTypeFor(la) as DayType;
}

export function pickFile<T>(files: Record<DayType, T>, choice: string): T | null {
	const kind = dayTypeFor(choice);
	return kind ? files[kind] : null;
}

// Nearest rank: the value at rank ceil(0.9 n) of the sorted list. With 8 days that
// is the 8th, the latest day, and with 10 days it is the 9th, so 9 of 10 days
// are at or before it.
export function nearestRank90(values: number[]): number {
	const sorted = [...values].sort((a, b) => a - b);
	return sorted[Math.ceil(NEAREST_RANK * sorted.length) - 1];
}

export function median(values: number[]): number {
	const sorted = [...values].sort((a, b) => a - b);
	const mid = sorted.length >> 1;
	return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

// A delay is the day's actual time at B minus the timetable's time at B, both as
// seconds after the pattern's scheduled start. Only days with a time at both stops count.
function candidate(
	file: CommuteFile,
	pattern: Pattern,
	from: string,
	to: string
): Candidate | null {
	const ride = rideTimes(file, pattern.start, from, to);
	if (!ride.ok || ride.data.length === 0) return null;
	const order = pattern.stopIndexes.map((i) => file.stops[i]);
	const a = order.indexOf(from);
	const b = order.indexOf(to, a + 1);
	const atB: number[] = [];
	pattern.dayIndexes.forEach((_, column) => {
		const times = columnTimes(pattern, column);
		const ta = times[a];
		const tb = times[b];
		if (ta === null || tb === null) return;
		atB.push(tb * UNIT);
	});
	const scheduledAt = (stop: number) =>
		pattern.scheduled.slice(0, stop + 1).reduce((sum, units) => sum + units, 0) * UNIT;
	const scheduledA = scheduledAt(a);
	const scheduledB = scheduledAt(b);
	const lates = atB.map((t) => t - scheduledB);
	return {
		start: pattern.start,
		departMinute: Math.round((pattern.start + scheduledA) / 60),
		arrive90Minute: Math.ceil((pattern.start + nearestRank90(atB)) / 60),
		medianLateSeconds: median(lates),
		badLateSeconds: nearestRank90(lates),
		rideSeconds: median(ride.data.map((r) => r.seconds)),
		days: atB.length
	};
}

export function answer(
	file: CommuteFile,
	from: string,
	to: string,
	mode: Mode,
	minute: number
): Answer {
	const found = file.patterns
		.map((p) => candidate(file, p, from, to))
		.filter((c): c is Candidate => c !== null);
	let chosen: Candidate | undefined;
	if (mode === 'leave') {
		chosen = found
			.filter((c) => c.departMinute >= minute)
			.sort((x, y) => x.departMinute - y.departMinute)[0];
	} else {
		chosen = found
			.filter((c) => c.arrive90Minute <= minute)
			.sort((x, y) => y.departMinute - x.departMinute)[0];
	}
	if (!chosen) return { kind: 'no-bus', mode };
	const base = { line: file.line, start: chosen.start, departMinute: chosen.departMinute };
	if (chosen.days < MIN_DAYS) return { kind: 'not-enough-data', ...base, days: chosen.days };
	return {
		kind: 'answer',
		...base,
		medianLateMinutes: Math.round(chosen.medianLateSeconds / 60),
		badLateMinutes: Math.round(chosen.badLateSeconds / 60),
		rideMinutes: Math.round(chosen.rideSeconds / 60),
		days: chosen.days
	};
}

export function clock(minute: number): string {
	const h = Math.floor(minute / 60) % 24;
	const mm = String(minute % 60).padStart(2, '0');
	return `${h % 12 || 12}:${mm} ${h < 12 ? 'am' : 'pm'}`;
}

const minutes = (n: number) => `${n} ${n === 1 ? 'minute' : 'minutes'}`;

export function sentence(result: Answer): string {
	if (result.kind === 'no-bus') {
		return result.mode === 'leave'
			? 'No bus leaves at or after that time.'
			: 'No bus is likely to arrive by that time.';
	}
	const bus = `the ${clock(result.departMinute)} line ${result.line} bus`;
	if (result.kind === 'not-enough-data') {
		return `Not enough data for ${bus}. It has run on ${result.days} days, and an answer needs ${MIN_DAYS}.`;
	}
	const late = result.medianLateMinutes;
	const usually =
		late === 0 ? 'on time' : late > 0 ? `${minutes(late)} late` : `${minutes(-late)} early`;
	return (
		`Catch ${bus}. It is usually ${usually}, and 9 days in 10 it is no more than ` +
		`${minutes(result.badLateMinutes)} late. The ride takes ${minutes(result.rideMinutes)}. ` +
		`This rests on ${result.days} days.`
	);
}
