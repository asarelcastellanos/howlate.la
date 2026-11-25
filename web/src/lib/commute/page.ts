import { openCommute } from '../data/commute.ts';
import type { CommuteRun } from '../data/commute.ts';
import type { Result } from '../data/load.ts';
import type { LineListEntry } from '../lineHead.ts';
import type { CommuteIndex, CommuteStop, DayType } from './file.ts';
import type { Mode } from './answer.ts';

export type CommutePageData = { run: CommuteRun; index: CommuteIndex; stops: CommuteStop[] };

export async function loadCommutePage(
	base: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<CommutePageData>> {
	const opened = await openCommute(base, fetchFn);
	if (!opened.ok) return opened;
	const run = opened.data;
	const [index, stops] = await Promise.all([run.index(), run.stops()]);
	if (!index.ok) return index;
	if (!stops.ok) return stops;
	return { ok: true, data: { run, index: index.data, stops: stops.data } };
}

export type Query = {
	line?: string;
	direction?: number;
	dayType?: DayType;
	from?: string;
	to?: string;
	mode?: Mode;
	time?: string;
};

const TIME = /^([01]\d|2[0-3]):([0-5]\d)$/;

export const directionsOf = (index: CommuteIndex, line: string): number[] =>
	[...new Set(index.files.filter((f) => f.line === line).map((f) => f.direction))].sort(
		(a, b) => a - b
	);

export const linesOf = (index: CommuteIndex): string[] => [
	...new Set(index.files.map((f) => f.line))
];

export function minuteOf(time: string): number | null {
	const m = TIME.exec(time);
	return m ? Number(m[1]) * 60 + Number(m[2]) : null;
}

export function readQuery(search: string, index: CommuteIndex): Query {
	const params = new URLSearchParams(search);
	const out: Query = {};
	const line = params.get('line');
	if (line !== null && linesOf(index).includes(line)) {
		out.line = line;
		const directions = directionsOf(index, line);
		const raw = params.get('dir');
		const wanted = raw !== null && /^\d+$/.test(raw) ? Number(raw) : NaN;
		if (directions.includes(wanted)) out.direction = wanted;
		else if (directions.length === 1) out.direction = directions[0];
		if (out.direction !== undefined) {
			const from = params.get('from');
			const to = params.get('to');
			if (from) out.from = from;
			if (to) out.to = to;
		}
	}
	const day = params.get('day');
	if (day === 'weekday' || day === 'saturday' || day === 'sunday') out.dayType = day;
	const mode = params.get('mode');
	if (mode === 'leave' || mode === 'arrive') out.mode = mode;
	const time = params.get('time');
	if (time !== null && TIME.test(time)) out.time = time;
	return out;
}

export function writeQuery(query: Query): string {
	const params = new URLSearchParams();
	if (query.line) params.set('line', query.line);
	if (query.direction !== undefined) params.set('dir', String(query.direction));
	if (query.dayType) params.set('day', query.dayType);
	if (query.from) params.set('from', query.from);
	if (query.to) params.set('to', query.to);
	if (query.mode) params.set('mode', query.mode);
	if (query.time) params.set('time', query.time);
	return params.toString().replaceAll('%3A', ':');
}

export function directionLabel(
	listed: LineListEntry | undefined,
	directions: number[],
	id: number
): string {
	const position = directions.indexOf(id);
	const name = listed && listed.to.length === directions.length ? listed.to[position] : '';
	return name ? `Toward ${name}` : `Direction ${position + 1}`;
}
