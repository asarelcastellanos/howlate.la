import * as Plot from '@observablehq/plot';
import type { Stop } from '../data/types';
import {
	ANNOTATION,
	GRID,
	INK,
	MIN_ARRIVALS,
	PAPER,
	PLOT_STYLE,
	delayLabel,
	type DrawOptions
} from './theme.ts';

/** The stops from the start of the route to the end. `seq` is a median over trips, so ties are possible and keep the file's order. */
export const routeStops = (stops: Stop[]): Stop[] => [...stops].sort((a, b) => a.seq - b.seq);

/** A stop whose median can be drawn. A median from fewer than MIN_ARRIVALS arrivals breaks the line, as in the week chart. */
const measured = (stop: Stop) => stop.all.med !== null && stop.n >= MIN_ARRIVALS;

const LABELS = 3;

/**
 * The stops that get a direct label: the three highest medians among stops with
 * enough arrivals, and only those that ran late. When every median is on time
 * or early, no stop is "the worst", the same rule the heatmap follows.
 */
export function worstStops(stops: Stop[]): Stop[] {
	return routeStops(stops)
		.filter((stop) => measured(stop) && stop.all.med! > 0)
		.sort((a, b) => b.all.med! - a.all.med!)
		.slice(0, LABELS);
}

export function routeChartLabel(stops: Stop[], to: string): string {
	const route = routeStops(stops);
	const lead = `Median delay at each stop, in route order${to ? ` toward ${to}` : ''}.`;
	const ends = `${route.length} ${route.length === 1 ? 'stop' : 'stops'}, from ${route[0].name} to ${route.at(-1)!.name}.`;
	if (!route.some(measured)) return `${lead} ${ends} No stop has enough arrivals to rank.`;
	const worst = worstStops(stops)[0];
	if (!worst) return `${lead} ${ends} No stop ran late.`;
	return `${lead} ${ends} The worst stop is ${worst.name}, at ${delayLabel(worst.all.med!)}.`;
}

const HEIGHT = 240;
const MARGIN_LEFT = 60;
const MARGIN_RIGHT = 8;
const MARGIN_TOP = 8;
const MARGIN_BOTTOM = 34;
/** Text height in pixels, the gap between a label and its stop, and the gap between stacked labels. */
const LINE = 14;
const GAP = 6;
const STACK_GAP = 6;
const CHAR_PX = 7;
const DX = 4;
/** A worst-stop label has two lines, the name over the delay. */
const BLOCK = 2 * LINE;

const clip = (text: string, chars: number) =>
	text.length <= chars ? text : `${text.slice(0, Math.max(chars - 1, 1)).trimEnd()}…`;

export type Placed = {
	name: string;
	delay: string;
	anchor: 'start' | 'end';
	/** Pixels from the stop to the label's anchor edge, and up to the bottom of its block. */
	dx: number;
	lift: number;
	/** The block's [left, right, top, bottom] in pixels from the chart's top left, for the overlap check. */
	box: [number, number, number, number];
};

/**
 * Places the labels of the worst stops, worst first. `y` is the pixel row of the
 * stop's top mark, which is its 90th percentile, because that line runs above
 * the median and a label on the median would sit on it. A label reads away from
 * the stop toward the side with more room, so it stays inside the plot, and
 * its name is cut with an ellipsis when even that side is too narrow. A label
 * that would touch one placed before it moves up one block at a time.
 */
export function placeLabels(
	worst: { name: string; med: number; x: number; y: number }[],
	left: number,
	right: number
): Placed[] {
	const placed: Placed[] = [];
	for (const stop of worst) {
		const anchor = stop.x - left >= right - stop.x ? ('end' as const) : ('start' as const);
		const room = anchor === 'end' ? stop.x + DX - left : right - (stop.x - DX);
		const delay = delayLabel(stop.med);
		const name = clip(stop.name, Math.max(Math.floor(room / CHAR_PX), 3));
		const width = Math.max(name.length, delay.length) * CHAR_PX;
		const from = anchor === 'end' ? stop.x + DX - width : stop.x - DX;
		for (let level = 0; ; level++) {
			const lift = GAP + BLOCK + level * (BLOCK + STACK_GAP);
			const box: Placed['box'] = [from, from + width, stop.y - lift, stop.y - lift + BLOCK];
			const clear = placed.every(
				(p) => box[0] >= p.box[1] || p.box[0] >= box[1] || box[2] >= p.box[3] || p.box[2] >= box[3]
			);
			if (clear || level > worst.length) {
				placed.push({ name, delay, anchor, dx: anchor === 'end' ? DX : -DX, lift, box });
				break;
			}
		}
	}
	return placed;
}

/**
 * Whole-minute ticks that include zero, at about six or fewer. Plot's own ticks
 * would label a small range in halves, such as "-1.5 min", which is wider than
 * the margin the labels are laid out against.
 */
export function minuteAxis(lo: number, hi: number) {
	const step = [1, 2, 5, 10, 15, 30, 60, 120].find((s) => (hi - lo) / s <= 6) ?? 240;
	const from = Math.floor(lo / step);
	const to = Math.ceil(hi / step);
	return {
		domain: [from * step, to * step],
		ticks: Array.from({ length: to - from + 1 }, (_, k) => (from + k) * step)
	};
}

export function routeChart(stops: Stop[], { width, document }: DrawOptions) {
	const route = routeStops(stops);
	const rows = route.map((stop, i) => ({
		i,
		stop,
		// NaN is a gap in a Plot line, so an unmeasured stop is never drawn at zero.
		med: measured(stop) ? stop.all.med! / 60 : NaN,
		p90: measured(stop) ? stop.all.p90! / 60 : NaN
	}));
	const has = (i: number) => i >= 0 && i < rows.length && !Number.isNaN(rows[i].med);
	// A stop with a gap on both sides has no line to show it, so it gets a dot.
	const lone = rows.filter((row) => has(row.i) && !has(row.i - 1) && !has(row.i + 1));
	const values = rows.flatMap((row) => [row.med, row.p90]).filter((v) => !Number.isNaN(v));
	const { domain, ticks } = minuteAxis(Math.min(0, ...values), Math.max(0, ...values, 1));
	const worst = worstStops(stops).map((stop) => rows[route.indexOf(stop)]);
	const common = { x: (d: (typeof rows)[number]) => d.i };

	const draw = (labels: Placed[], extraTop: number) => {
		const lastRow = rows.length - 1;
		const room = Math.floor((width - MARGIN_LEFT - MARGIN_RIGHT - 12) / 2 / CHAR_PX);
		const end = (text: string, anchor: 'left' | 'right', side: 'start' | 'end') =>
			Plot.text([text], {
				frameAnchor: `bottom-${anchor}`,
				textAnchor: side,
				lineAnchor: 'middle',
				dy: 18,
				text: (t: string) => clip(t, room),
				fill: ANNOTATION
			});
		return Plot.plot({
			document,
			width,
			height: HEIGHT + extraTop,
			marginTop: MARGIN_TOP + extraTop,
			marginLeft: MARGIN_LEFT,
			marginRight: MARGIN_RIGHT,
			marginBottom: MARGIN_BOTTOM,
			style: PLOT_STYLE,
			x: { domain: [0, Math.max(lastRow, 1)], axis: null },
			y: {
				domain,
				ticks,
				label: null,
				// The zero line is the timetable, so the axis says so.
				tickFormat: (m: number) => (m === 0 ? 'on time' : `${m} min`)
			},
			marks: [
				Plot.gridY({ stroke: GRID, strokeOpacity: 1 }),
				Plot.ruleY([0], { stroke: INK }),
				Plot.lineY(rows, { ...common, y: 'p90', stroke: ANNOTATION, strokeWidth: 1.5 }),
				Plot.lineY(rows, { ...common, y: 'med', stroke: INK, strokeWidth: 2 }),
				Plot.dot(lone, { ...common, y: 'med', r: 3, fill: INK, stroke: PAPER, strokeWidth: 1 }),
				// A stem from the median to the 90th percentile ties the label, which
				// sits above the 90th percentile line, to its stop.
				Plot.ruleX(worst, { ...common, y1: 'med', y2: 'p90', stroke: ANNOTATION }),
				Plot.dot(worst, { ...common, y: 'med', r: 4, fill: INK, stroke: PAPER, strokeWidth: 1.5 }),
				end(route[0].name, 'left', 'start'),
				...(route.length > 1 ? [end(route[lastRow].name, 'right', 'end')] : []),
				...labels.flatMap((label, k) =>
					(
						[
							[label.name, LINE / 2 - label.lift],
							[label.delay, (3 * LINE) / 2 - label.lift]
						] as const
					).map(([text, dy]) =>
						Plot.text([worst[k]], {
							...common,
							y: 'p90',
							text: () => text,
							textAnchor: label.anchor,
							dx: label.dx,
							dy,
							fill: ANNOTATION,
							stroke: PAPER,
							strokeWidth: 4,
							fontWeight: 600
						})
					)
				)
			]
		});
	};

	// The labels do not change the scales, so one draw gives the pixel positions
	// that the second draw needs. A stack that rises above the plot adds that
	// much to the top margin and the height, which moves every mark down by the
	// same amount and keeps each label where it was placed.
	const first = draw([], 0);
	if (worst.length === 0) return first;
	const scale = first as unknown as {
		scale(name: 'x' | 'y'): { apply(v: number): number; range: number[] };
	};
	const xs = scale.scale('x');
	const ys = scale.scale('y');
	const labels = placeLabels(
		worst.map((row) => ({
			name: row.stop.name,
			med: row.stop.all.med!,
			x: xs.apply(row.i),
			y: ys.apply(row.p90)
		})),
		MARGIN_LEFT,
		width - MARGIN_RIGHT
	);
	const top = Math.min(...labels.map((label) => label.box[2]));
	return draw(labels, Math.max(0, Math.ceil(2 - top)));
}
