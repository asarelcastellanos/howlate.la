import * as Plot from '@observablehq/plot';
import type { Stop } from '../data/types';
import {
	ANNOTATION,
	INK,
	MIN_ARRIVALS,
	PAPER,
	PLOT_STYLE,
	delayLabel,
	type DrawOptions
} from './theme.ts';

/** The weekday evening rush, 3 to 7 pm (15:00 to 18:59). */
export const DEFAULT_DAYPART = 'wk-pm';

const KINDS: Record<string, string> = { wk: 'Weekdays', sa: 'Saturdays', su: 'Sundays' };
const PARTS: Record<string, string> = {
	early: 'midnight to 6 am',
	am: '6 to 9 am',
	mid: '9 am to 3 pm',
	pm: '3 to 7 pm',
	eve: '7 to 10 pm',
	late: '10 pm to midnight'
};

/** Reads a cell label such as "wk-pm" using the ranges in line.schema.json. */
export function daypartName(daypart: string): string {
	const [kind, part] = daypart.split('-');
	return `${KINDS[kind]} ${PARTS[part]}`;
}

export type Dot = { name: string; med: number; n: number; r: number; y: number; hollow: boolean };

const MARGIN_X = 12;
const R_MIN = 3;
const R_MAX = 11;
const LABELS = 3;

/**
 * One dot per stop that has a cell for the daypart, given a radius of
 * R_MIN plus a share of the rest that grows with sqrt(n), so a dot with more
 * arrivals is larger, but its area is not proportional to n. Dots that would overlap are pushed up or down, so
 * `y` is a pixel offset from the strip's center line.
 */
export function stripDots(stops: Stop[], daypart: string, width: number): Dot[] {
	const cells = stops.flatMap((stop) => {
		const cell = stop.cells.find((c) => c.d === daypart);
		return cell ? [{ name: stop.name, med: cell.med, n: cell.n }] : [];
	});
	if (!cells.length) return [];
	const [lo, hi] = extent(cells.map((c) => c.med));
	const maxN = Math.max(...cells.map((c) => c.n));
	const px = (med: number) => MARGIN_X + ((med / 60 - lo) / (hi - lo)) * (width - 2 * MARGIN_X);
	const placed: { x: number; y: number; r: number }[] = [];
	return cells.map((c) => {
		const r = R_MIN + (R_MAX - R_MIN) * Math.sqrt(c.n / maxN);
		const x = px(c.med);
		// Try 0, +1, -1, +2, -2 and so on until the dot clears the ones placed.
		let y = 0;
		for (let k = 1; placed.some((p) => Math.hypot(p.x - x, p.y - y) < p.r + r + 1); k++) {
			y = k % 2 ? (k + 1) / 2 : -k / 2;
		}
		placed.push({ x, y, r });
		return { ...c, r, y, hollow: c.n < MIN_ARRIVALS };
	});
}

const toPx = (med: number, lo: number, hi: number, width: number) =>
	MARGIN_X + ((med / 60 - lo) / (hi - lo)) * (width - 2 * MARGIN_X);

function extent(seconds: number[]): [number, number] {
	// Zero stays inside the domain on both sides, so the "on time" rule is
	// drawn even when every stop is early or every stop is late.
	const lo = Math.floor(Math.min(0, ...seconds) / 60) - 1;
	const hi = Math.ceil(Math.max(0, ...seconds) / 60) + 1;
	return [lo, hi];
}

export function stripLabel(stops: Stop[], daypart: string, to: string): string {
	const dots = stripDots(stops, daypart, 600);
	const latest = latestStops(dots)[0];
	const lead = `One dot per stop toward ${to || 'the end of the line'}, at its median delay on ${daypartName(daypart).toLowerCase()}.`;
	return latest ? `${lead} The latest stop is ${latest.name}, at ${delayLabel(latest.med)}.` : lead;
}

/** The stops with the highest median among dots with enough arrivals, latest first. */
function latestStops(dots: Dot[]): Dot[] {
	return dots
		.filter((d) => !d.hollow)
		.sort((a, b) => b.med - a.med)
		.slice(0, LABELS);
}

const CHAR_PX = 7;

/**
 * A label ends at its dot and reads leftward. When that would run off the edge
 * it takes the wider side instead, and shortens the stop name with an ellipsis
 * until it fits. The delay stays, because it is the finding.
 */
function fitLabel(d: Dot, lo: number, hi: number, width: number) {
	const x = toPx(d.med, lo, hi, width);
	const anchor = x >= width - x ? ('end' as const) : ('start' as const);
	const room = Math.floor((Math.max(x, width - x) - MARGIN_X) / CHAR_PX);
	const tail = `, ${delayLabel(d.med)}`;
	const keep = Math.max(room - tail.length, 3);
	const name = d.name.length + tail.length <= room ? d.name : `${d.name.slice(0, keep - 1)}…`;
	return { ...d, anchor, text: name + tail };
}

export function stopStrip(stops: Stop[], daypart: string, { width, document }: DrawOptions) {
	const dots = stripDots(stops, daypart, width);
	const [lo, hi] = extent(dots.map((d) => d.med));
	// Labels stack above the swarm, the latest stop highest, each joined to its dot
	// by a leader. A label ends at its dot and reads leftward, so a higher label
	// never lies across a lower dot's leader.
	const named = latestStops(dots)
		.sort((a, b) => a.med - b.med)
		.map((d, level) => ({ ...fitLabel(d, lo, hi, width), level }));
	const above = Math.max(24, ...dots.map((d) => d.y + d.r));
	const below = Math.max(24, ...dots.map((d) => -d.y + d.r));
	const labelY = (i: number) => above + 14 + i * 16;
	const top = labelY(Math.max(named.length - 1, 0)) + 10;
	const common = { x: (d: Dot) => d.med / 60, y: (d: Dot) => d.y, r: (d: Dot) => d.r };
	return Plot.plot({
		document,
		width,
		height: top + below + 40,
		marginTop: 0,
		marginBottom: 40,
		marginLeft: MARGIN_X,
		marginRight: MARGIN_X,
		style: PLOT_STYLE,
		// One y unit is one pixel, so the dot offsets from stripDots land as computed.
		y: { axis: null, domain: [-below, top] },
		r: { type: 'identity' },
		x: {
			domain: [lo, hi],
			label: 'Median delay in minutes',
			labelAnchor: 'center',
			tickFormat: (m: number) => (m === 0 ? 'on time' : String(m)),
			tickSize: 4
		},
		marks: [
			Plot.ruleX([0], { stroke: INK }),
			Plot.dot(
				dots.filter((d) => !d.hollow),
				{ ...common, fill: INK, stroke: PAPER, strokeWidth: 1 }
			),
			Plot.dot(
				dots.filter((d) => d.hollow),
				{ ...common, fill: 'none', stroke: INK, strokeWidth: 1.5 }
			),
			Plot.ruleX(named, {
				x: common.x,
				y1: (d: Dot) => d.y + d.r,
				y2: (_: Dot, i: number) => labelY(i) - 6,
				stroke: ANNOTATION
			}),
			...(['end', 'start'] as const).map((anchor) =>
				Plot.text(
					named.filter((d) => d.anchor === anchor),
					{
						x: common.x,
						y: (d: (typeof named)[number]) => labelY(d.level),
						text: 'text',
						textAnchor: anchor,
						dx: anchor === 'end' ? 4 : -4,
						fill: ANNOTATION,
						stroke: PAPER,
						strokeWidth: 4,
						fontWeight: 600
					}
				)
			)
		]
	});
}
