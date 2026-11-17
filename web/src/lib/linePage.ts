import { SHOW_RAIL_ONTIME } from './config.ts';
import { openRun, type Result } from './data/load.ts';
import { longDate } from './date.ts';
import type { Direction, IndexEntry, LineFile, SiteIndex } from './data/types';
import { LINES, type BusService, type LineId } from './design/lines.ts';
import { serviceOf } from './design/service.ts';

/** How the methodology page words the on-time window. */
export const ONTIME_WINDOW = '1 minute early to 5 minutes late, at every stop';

/** Shown in place of the on-time share on a rail line while #133 is open. */
export const RAIL_HOLD_NOTE =
	"The on-time share for rail is on hold while we check how it compares with Metro's.";

export type Mode = LineFile['mode'];

/** Bus lines always show the share. Rail shows it only when the gate is open. */
export function showsOntime(mode: Mode, railGate: boolean = SHOW_RAIL_ONTIME): boolean {
	return mode === 'bus' || railGate;
}

/** A rail label already says "Metro A Line", and a shuttle's label is a name. Only a number needs "Route". */
export function lineName(line: Pick<IndexEntry, 'label' | 'mode'>): string {
	return line.mode === 'bus' && /^[\d/]+$/.test(line.label) ? `Route ${line.label}` : line.label;
}

/** The index text in front of a rider. One timetable note runs to several sentences. */
export function shortVia(via: string, max = 120): string {
	if (via.length <= max) return via;
	const sentence = via.split('. ')[0];
	if (sentence.length <= max) return `${sentence}.`;
	return `${via.slice(0, max).trimEnd()}…`;
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

/** A delay in seconds as words. Under two minutes it stays in seconds. */
export function delayWords(seconds: number): string {
	if (seconds === 0) return 'on time';
	const when = seconds < 0 ? 'early' : 'late';
	const size = Math.abs(seconds);
	if (size < 120) return `${plural(size, 'second')} ${when}`;
	return `${plural(Math.round(size / 60), 'minute')} ${when}`;
}

export function directionName(direction: Pick<Direction, 'to'>, index: number): string {
	return direction.to ? `Toward ${direction.to}` : `Direction ${index + 1}`;
}

/** One sentence for one direction. It leaves out the on-time share when the gate says so. */
export function headline(
	direction: Pick<Direction, 'to' | 'all'>,
	index: number,
	mode: Mode,
	railGate: boolean = SHOW_RAIL_ONTIME
): string {
	const { n, med, p90, ontime } = direction.all;
	const arrivals = `${n.toLocaleString('en-US')} measured ${n === 1 ? 'arrival' : 'arrivals'}`;
	const start = `${directionName(direction, index)}, the median arrival is ${delayWords(med)} and the 90th percentile is ${delayWords(p90)}`;
	if (!showsOntime(mode, railGate)) return `${start}, across ${arrivals}.`;
	return `${start}, and ${ontime.toFixed(1)} percent of ${arrivals} were on time.`;
}

export const hasDirectionSwitch = (line: Pick<LineFile, 'directions'>) =>
	line.directions.length > 1;

export function sourceNote(line: Pick<LineFile, 'days' | 'last_day'>): string {
	return `Source: Metro's real-time feeds and timetable, graded by HowLate. ${line.days} days of data, through ${longDate(line.last_day)}.`;
}

export function pageDescription(line: Pick<LineFile, 'label' | 'mode' | 'last_day'>): string {
	return `How late ${lineName(line)} runs by hour of the week and by stop, measured against the timetable. Data through ${longDate(line.last_day)}.`;
}

/** Props for LineBullet. Rail and the G and J busways use Metro's letter bullet. */
export function bulletProps(
	entry: Pick<IndexEntry, 'line' | 'label' | 'mode'>
): { line: LineId } | { service: BusService | undefined; route: string } {
	// routes.txt names the busways "901-13201" and "910-13201", and the index uses "901".
	const letter = LINES.find((l) => l.routeId.split('-')[0] === entry.line);
	if (letter && (entry.mode === 'rail' || entry.line === '901' || entry.line === '910')) {
		return { line: letter.id };
	}
	// A shuttle's label is a sentence, which does not fit in a bullet.
	return {
		service: serviceOf(entry.line),
		route: entry.label.length <= 7 ? entry.label : entry.line
	};
}

export const findEntry = (index: SiteIndex, id: string): IndexEntry | undefined =>
	index.lines.find((entry) => entry.line === id);

export type LinePage = { kind: 'found'; line: LineFile } | { kind: 'missing' };

// R2 answers 404 for a file that does not exist, which means no such line. Any
// other failure is a broken load, so the page shows the error state and retry.
export function lineResult(file: Result<LineFile>): Result<LinePage> {
	if (file.ok) return { ok: true, data: { kind: 'found', line: file.data } };
	if (file.error.kind === 'status' && file.error.status === 404) {
		return { ok: true, data: { kind: 'missing' } };
	}
	return file;
}

/** Reads the index and the line from one run. An id the index lacks never asks for a file. */
export async function loadLinePage(
	base: string,
	id: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<LinePage>> {
	const run = await openRun(base, fetchFn);
	if (!run.ok) return run;
	const index = await run.data.index();
	if (!index.ok) return index;
	if (!findEntry(index.data, id)) return { ok: true, data: { kind: 'missing' } };
	return lineResult(await run.data.line(id));
}
