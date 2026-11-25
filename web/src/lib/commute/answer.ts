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
			scheduledArriveMinute: number;
			nineInTenMinute: number;
			spareMinutes: number | null;
			arriveByMinute: number | null;
			medianLateMinutes: number;
			badLateMinutes: number;
			rideMinutes: number;
			days: number;
	  }
	| { kind: 'not-enough-data'; line: string; start: number; departMinute: number; days: number }
	| { kind: 'no-bus'; mode: Mode };

type Candidate = {
	start: number;
	departSeconds: number;
	scheduledArriveSeconds: number;
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

function scheduledOffset(pattern: Pattern, stop: number): number {
	return pattern.scheduled.slice(0, stop + 1).reduce((sum, units) => sum + units, 0) * UNIT;
}

export type Spread = {
	scheduled: number;
	nineInTen: number;
	arrivals: number[];
};

export function arrivalSpread(
	file: CommuteFile,
	start: number,
	from: string,
	to: string
): Spread | null {
	const pattern = file.patterns.find((p) => p.start === start);
	if (!pattern) return null;
	const order = pattern.stopIndexes.map((i) => file.stops[i]);
	const a = order.indexOf(from);
	const b = order.indexOf(to, a + 1);
	if (a < 0 || b < 0) return null;
	const arrivals: number[] = [];
	pattern.dayIndexes.forEach((_, column) => {
		const times = columnTimes(pattern, column);
		if (times[a] === null || times[b] === null) return;
		arrivals.push(start + (times[b] as number) * UNIT);
	});
	if (arrivals.length === 0) return null;
	return {
		scheduled: start + scheduledOffset(pattern, b),
		nineInTen: nearestRank90(arrivals),
		arrivals
	};
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
	const scheduledA = scheduledOffset(pattern, a);
	const scheduledB = scheduledOffset(pattern, b);
	const lates = atB.map((t) => t - scheduledB);
	return {
		start: pattern.start,
		departSeconds: pattern.start + scheduledA,
		scheduledArriveSeconds: pattern.start + scheduledB,
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
			.filter((c) => c.departSeconds >= minute * 60)
			.sort((x, y) => x.departSeconds - y.departSeconds)[0];
	} else {
		chosen = found
			.filter((c) => c.arrive90Minute <= minute)
			.sort((x, y) => y.departSeconds - x.departSeconds)[0];
	}
	if (!chosen) return { kind: 'no-bus', mode };
	const departMinute = Math.floor(chosen.departSeconds / 60);
	const base = { line: file.line, start: chosen.start, departMinute };
	if (chosen.days < MIN_DAYS) return { kind: 'not-enough-data', ...base, days: chosen.days };
	return {
		kind: 'answer',
		...base,
		scheduledArriveMinute: Math.floor(chosen.scheduledArriveSeconds / 60),
		nineInTenMinute: chosen.arrive90Minute,
		spareMinutes: mode === 'arrive' ? minute - chosen.arrive90Minute : null,
		arriveByMinute: mode === 'arrive' ? minute : null,
		medianLateMinutes: Math.round(chosen.medianLateSeconds / 60),
		badLateMinutes: Math.round(chosen.badLateSeconds / 60),
		rideMinutes: Math.round(chosen.rideSeconds / 60),
		days: chosen.days
	};
}

export function clock(minute: number): string {
	const h = Math.floor(minute / 60) % 24;
	const mm = String(minute % 60).padStart(2, '0');
	return `${h % 12 || 12}:${mm}\u00a0${h < 12 ? 'am' : 'pm'}`;
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
		return `Not enough data for ${bus}. It has run on ${result.days} days, and an answer needs ${MIN_DAYS}. Try another time or day.`;
	}
	const late = result.medianLateMinutes;
	const usually =
		late === 0 ? 'on time' : late > 0 ? `${minutes(late)} late` : `${minutes(-late)} early`;
	const worst =
		result.badLateMinutes <= 0
			? 'on time or early'
			: `no more than ${minutes(result.badLateMinutes)} late`;
	const lead =
		result.spareMinutes === null || result.arriveByMinute === null
			? ''
			: ` It reaches the To stop by ${clock(result.nineInTenMinute)} on 9 days in 10, ` +
				(result.spareMinutes === 0
					? `right at your ${clock(result.arriveByMinute)} deadline.`
					: `${minutes(result.spareMinutes)} before your ${clock(result.arriveByMinute)} deadline.`);
	return (
		`Catch ${bus}.${lead} The timetable has it at the To stop at ${clock(result.scheduledArriveMinute)}. ` +
		`It is usually ${usually}, and 9 days in 10 it is ${worst}. ` +
		`The ride takes ${minutes(result.rideMinutes)}. This rests on ${result.days} days.`
	);
}
