export const UNIT = 10;

export type DayType = 'weekday' | 'saturday' | 'sunday';

export type Pattern = {
	start: number;
	dayIndexes: number[];
	stopIndexes: number[];
	rows: (number | null)[][];
	scheduled: number[];
};

export type CommuteFile = {
	line: string;
	direction: number;
	dayType: DayType;
	days: string[];
	stops: string[];
	patterns: Pattern[];
};

type Obj = Record<string, unknown>;
const isObj = (v: unknown): v is Obj => typeof v === 'object' && v !== null && !Array.isArray(v);
const isInt = (v: unknown): v is number => Number.isInteger(v);
const isStr = (v: unknown): v is string => typeof v === 'string';
const ints = (v: unknown): v is number[] => Array.isArray(v) && v.every(isInt);
const isDayType = (v: unknown): v is DayType =>
	v === 'weekday' || v === 'saturday' || v === 'sunday';

function decodePattern(raw: unknown, days: number, stops: number): Pattern | null {
	if (!Array.isArray(raw) || raw.length !== 5) return null;
	const [start, dayIndexes, stopIndexes, rows, scheduled] = raw;
	if (!isInt(start) || start < 0 || !ints(dayIndexes) || !ints(stopIndexes) || !Array.isArray(rows))
		return null;
	if (!ints(scheduled) || scheduled.length !== stopIndexes.length) return null;
	if (dayIndexes.some((d) => d < 0 || d >= days)) return null;
	if (stopIndexes.some((s) => s < 0 || s >= stops)) return null;
	if (rows.length !== stopIndexes.length) return null;
	for (const row of rows) {
		if (!Array.isArray(row) || row.length !== dayIndexes.length) return null;
		if (!row.every((v) => v === null || isInt(v))) return null;
	}
	return { start, dayIndexes, stopIndexes, rows, scheduled };
}

export type Wanted = { line: string; direction: number; dayType: DayType };

export function decodeCommuteFile(body: unknown, wanted: Wanted): CommuteFile | null {
	if (!isObj(body)) return null;
	const { line, direction, day_type: dayType, days, stops, patterns } = body;
	if (line !== wanted.line || direction !== wanted.direction || dayType !== wanted.dayType)
		return null;
	if (!Array.isArray(days) || !days.every((d) => isStr(d) && /^\d{8}$/.test(d))) return null;
	if (!Array.isArray(stops) || !stops.every(isStr)) return null;
	if (!Array.isArray(patterns)) return null;
	const decoded: Pattern[] = [];
	for (const raw of patterns) {
		const pattern = decodePattern(raw, days.length, stops.length);
		if (!pattern) return null;
		decoded.push(pattern);
	}
	return { ...wanted, days, stops, patterns: decoded };
}

export type CommuteIndexEntry = {
	line: string;
	direction: number;
	day_type: DayType;
	file: string;
	patterns: number;
	days: number;
};

export type CommuteIndex = {
	first_day: string;
	last_day: string;
	days: number;
	unit: number;
	stops: string;
	files: CommuteIndexEntry[];
};

const isEntry = (v: unknown): v is CommuteIndexEntry =>
	isObj(v) &&
	isStr(v.line) &&
	isInt(v.direction) &&
	isDayType(v.day_type) &&
	isStr(v.file) &&
	isInt(v.patterns) &&
	isInt(v.days);

export const isCommuteIndex = (v: unknown): v is CommuteIndex =>
	isObj(v) &&
	isStr(v.first_day) &&
	isStr(v.last_day) &&
	isInt(v.days) &&
	v.unit === UNIT &&
	isStr(v.stops) &&
	Array.isArray(v.files) &&
	v.files.every(isEntry);

export type CommuteStop = [string, string, number, number];

export const isCommuteStops = (v: unknown): v is CommuteStop[] =>
	Array.isArray(v) &&
	v.every(
		(s) =>
			Array.isArray(s) &&
			s.length === 4 &&
			isStr(s[0]) &&
			isStr(s[1]) &&
			typeof s[2] === 'number' &&
			typeof s[3] === 'number'
	);
