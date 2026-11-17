import { SHOW_RAIL_ONTIME } from './config.ts';
import type { Result } from './data/load.ts';
import type { IndexEntry, SiteIndex } from './data/types';
import { LINES, type BusService, type LineId } from './design/lines.ts';

export type Metric = 'ontime' | 'med' | 'p90';

/** "best" puts the best line first. "worst" reverses that. */
export type Order = 'best' | 'worst';

export type Sort = { metric: Metric; order: Order };

export const DEFAULT_SORT: Sort = { metric: 'ontime', order: 'best' };

export const METRICS: { id: Metric; label: string }[] = [
	{ id: 'ontime', label: 'On time' },
	{ id: 'med', label: 'Median delay' },
	{ id: 'p90', label: '90th percentile' }
];

/**
 * A line with fewer measured arrivals than this is listed but not ranked.
 *
 * In the 2026-11-16 run (90 days, 2026-08-18 to 2026-11-15) the index holds
 * 109 bus lines. The smallest n is 202, line 697, the SoFi Stadium shuttle. The next
 * smallest is 18,078 and the largest is 1,392,514, line 4. So exactly one bus
 * line falls below 500, and any threshold from 203 to 18,078 would split
 * today's data the same way.
 *
 * 500 comes from how far a share moves. One arrival is 100 / n points of the
 * share. At n = 500, five arrivals moving change the share by exactly 1 point.
 * Under 500 the same five move it by more than a point. At 202 they move it by
 * 2.5 points, and 47 of the 108 ranked bus lines sit within 2.5 points of line
 * 697's 60.4 percent, so a handful of arrivals could move it past dozens of
 * lines. At 18,078 five arrivals move a share by 0.03 points, less than the
 * 0.1 point the table shows.
 */
export const MIN_RANKED_ARRIVALS = 500;

export const RAIL_HOLD_NOTE =
	"The on-time share for rail is on hold while we check how it compares with Metro's.";

export type RankedLine = {
	entry: IndexEntry;
	/** Lines with an equal value share a rank, so 1, 2, 2, 4. A tie never claims an order. */
	rank: number;
};

export type Ranking = {
	ranked: RankedLine[];
	/** Entries under MIN_RANKED_ARRIVALS, by line id. Their `n` is on the entry. */
	unranked: IndexEntry[];
};

/**
 * Line ids in a fixed order: numeric ids in numeric order, then the others
 * alphabetically. The order never depends on the data, so a tie sorts the same
 * on every load and in both directions.
 */
export function compareIds(a: string, b: string): number {
	const aNumber = /^\d+$/.test(a);
	const bNumber = /^\d+$/.test(b);
	if (aNumber && bNumber) return Number(a) - Number(b) || (a < b ? -1 : a > b ? 1 : 0);
	if (aNumber !== bNumber) return aNumber ? -1 : 1;
	return a < b ? -1 : a > b ? 1 : 0;
}

/** Negative when `a` is the better line on this metric. */
function compareBest(metric: Metric, a: IndexEntry, b: IndexEntry): number {
	return metric === 'ontime' ? b.ontime - a.ontime : a[metric] - b[metric];
}

/**
 * Sorts lines by one metric and returns a new array, never the input. A higher
 * on-time share is better. A lower median or 90th percentile delay is better.
 * Ties break by line id, in the same order for both `order` values, so reversing
 * a table never reshuffles lines that share a value.
 *
 * Rail never enters an on-time ranking while SHOW_RAIL_ONTIME is false, and it
 * is dropped, not listed as unranked, because the reason is not its arrivals.
 */
export function rankLines(
	entries: readonly IndexEntry[],
	metric: Metric,
	order: Order = 'best'
): Ranking {
	const gated = (e: IndexEntry) => metric === 'ontime' && e.mode === 'rail' && !SHOW_RAIL_ONTIME;
	const candidates = entries.filter((e) => !gated(e));
	const enough = candidates.filter((e) => e.n >= MIN_RANKED_ARRIVALS);
	const unranked = candidates
		.filter((e) => e.n < MIN_RANKED_ARRIVALS)
		.sort((a, b) => compareIds(a.line, b.line));

	const sorted = (sign: 1 | -1) =>
		[...enough].sort((a, b) => sign * compareBest(metric, a, b) || compareIds(a.line, b.line));
	const best = sorted(1);
	const rankOf = new Map<string, number>();
	best.forEach((e, i) => {
		const tied = i > 0 && compareBest(metric, best[i - 1], e) === 0;
		rankOf.set(e.line, tied ? rankOf.get(best[i - 1].line)! : i + 1);
	});

	const ordered = order === 'best' ? best : sorted(-1);
	return {
		ranked: ordered.map((entry) => ({ entry, rank: rankOf.get(entry.line)! })),
		unranked
	};
}

/** What a click on a column header does. The active header flips the order. Another one starts at its best. */
export function nextSort(current: Sort, metric: Metric): Sort {
	if (current.metric !== metric) return { metric, order: 'best' };
	return { metric, order: current.order === 'best' ? 'worst' : 'best' };
}

/** The `aria-sort` value for a header, or undefined when it is not the sorted column. */
export function ariaSort(sort: Sort, metric: Metric): 'ascending' | 'descending' | undefined {
	if (sort.metric !== metric) return undefined;
	const highFirst = (metric === 'ontime') === (sort.order === 'best');
	return highFirst ? 'descending' : 'ascending';
}

/**
 * The first `count` lines of a best-first ranking, and the last `count` with
 * the worst first. A line that ties with the last one shown is shown too, so
 * the cut never picks between lines with the same share. In the 2026-11-16 run
 * lines 2 and 4 both have 54.9 percent and sit at the edge of the bottom five.
 */
export function ends(
	ranked: readonly RankedLine[],
	count: number
): { top: RankedLine[]; bottom: RankedLine[] } {
	const topCut = ranked[Math.min(count, ranked.length) - 1]?.rank;
	const bottomCut = ranked[Math.max(ranked.length - count, 0)]?.rank;
	if (topCut === undefined || bottomCut === undefined) return { top: [], bottom: [] };
	return {
		top: ranked.filter((r) => r.rank <= topCut),
		// Past the top block, so a short list never shows one line in both panels.
		bottom: ranked.filter((r) => r.rank >= bottomCut && r.rank > topCut).reverse()
	};
}

/** "Route 720" for a number. A rail label already says "Metro A Line" and a shuttle's label is a name. */
export function lineName(line: Pick<IndexEntry, 'label' | 'mode'>): string {
	return line.mode === 'bus' && /^[\d/]+$/.test(line.label) ? `Route ${line.label}` : line.label;
}

/** The index text in front of a rider. One timetable note runs to several sentences. */
export function shortVia(via: string, max = 60): string {
	if (via.length <= max) return via;
	const sentence = via.split('. ')[0];
	if (sentence.length <= max) return sentence;
	return `${via.slice(0, max).trimEnd()}…`;
}

// The index has no service type, so the bullet style follows Metro's route
// numbers. The same ranges appear in the /design specimen.
function busService(id: string): BusService {
	if (/^7\d\d$/.test(id)) return 'rapid';
	if (/^3\d\d$/.test(id)) return 'limited';
	if (/^[45]\d\d$/.test(id)) return 'express';
	return 'local';
}

/** Props for LineBullet. Rail and the G and J busways use Metro's letter bullet. */
export function bulletProps(
	entry: Pick<IndexEntry, 'line' | 'label' | 'mode'>
): { line: LineId } | { service: BusService; route: string } {
	// routes.txt names the busways "901-13201" and "910-13201", and the index uses "901".
	const letter = LINES.find((l) => l.routeId.split('-')[0] === entry.line);
	if (letter && (entry.mode === 'rail' || entry.line === '901' || entry.line === '910')) {
		return { line: letter.id };
	}
	// A shuttle's label is a sentence, which does not fit in a bullet.
	return {
		service: busService(entry.line),
		route: entry.label.length <= 7 ? entry.label : entry.line
	};
}

export const percent = (value: number) => `${value.toFixed(1)}%`;

export const count = (n: number) => n.toLocaleString('en-US');

/**
 * A delay in seconds as minutes with one decimal, such as "4.5 min late".
 * Whole minutes would give the 28, 37 and 44 second medians in the rail table
 * the same "1 min", so the table could not be read in sorted order.
 */
export function delayText(seconds: number): string {
	const minutes = (Math.abs(seconds) / 60).toFixed(1);
	if (minutes === '0.0') return 'on time';
	return `${minutes} min ${seconds > 0 ? 'late' : 'early'}`;
}

/** "2026-11-15" as "November 15, 2026". It reads the day as UTC so no time zone shifts it. */
export function longDate(day: string): string {
	return new Date(`${day}T00:00:00Z`).toLocaleDateString('en-US', {
		month: 'long',
		day: 'numeric',
		year: 'numeric',
		timeZone: 'UTC'
	});
}

const isNumber = (value: unknown) => typeof value === 'number' && Number.isFinite(value);

/**
 * Checks the fields the page reads, because the loader does not validate. The
 * bucket's index has no n, med, p90, pct5 or ontime until the daily run after a
 * release, and a page that reads them from the old shape throws. This turns
 * that into a `shape` error, which the page shows as its error box. It takes
 * `unknown` and never throws, whatever the body is.
 */
export function checkRankingIndex(body: unknown, url: string): Result<SiteIndex> {
	const bad: Result<SiteIndex> = { ok: false, error: { kind: 'shape', url } };
	const index = body as Partial<SiteIndex> | null;
	if (typeof index !== 'object' || index === null || !Array.isArray(index.lines)) return bad;
	if (typeof index.first_day !== 'string' || typeof index.last_day !== 'string') return bad;
	if (!isNumber(index.days)) return bad;
	for (const line of index.lines as Partial<IndexEntry>[]) {
		if (typeof line !== 'object' || line === null) return bad;
		const text = [line.line, line.label, line.via].every((v) => typeof v === 'string');
		const numbers = [line.n, line.med, line.p90, line.pct5, line.ontime].every(isNumber);
		if (!text || !numbers || (line.mode !== 'bus' && line.mode !== 'rail')) return bad;
	}
	return { ok: true, data: index as SiteIndex };
}
