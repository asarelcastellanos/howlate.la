import * as Plot from '@observablehq/plot';
import type { Hour } from '../data/types';
import {
	ANNOTATION,
	DAYS,
	DAY_NAMES,
	GRID,
	INK,
	PAPER,
	PLOT_STYLE,
	delayLabel,
	hourLabel,
	trusted,
	type DrawOptions
} from './theme.ts';

const WEEK = Array.from({ length: 168 }, (_, h) => h);
const when = (h: number) => `${DAY_NAMES[Math.floor(h / 24)]} ${hourLabel(h % 24)}`;

function peak(rows: Hour[], key: 'med' | 'p90'): Hour | undefined {
	let top: Hour | undefined;
	for (const row of rows) if (!top || row[key] > top[key]) top = row;
	return top;
}

export function weekLinesLabel(profile: Hour[]): string {
	const rows = trusted(profile);
	const med = peak(rows, 'med');
	const p90 = peak(rows, 'p90');
	if (!med || !p90) return 'Delay by hour of the week. No hour has enough arrivals to draw.';
	return (
		'Median and 90th percentile delay for each hour of the week. ' +
		`The median peaks at ${delayLabel(med.med)} on ${when(med.h)}. ` +
		`The 90th percentile peaks at ${delayLabel(p90.p90)} on ${when(p90.h)}.`
	);
}

const HEIGHT = 260;
const MARGIN_TOP = 8;
/** Text height in pixels, and the space kept between a label and its line. */
const LABEL = 14;
const GAP = 4;

/**
 * Vertical offsets, in pixels, for the two labels at the end of the lines. `medY`
 * and `p90Y` are the line ends in pixels from the top, and `bottom` is the plot's
 * bottom edge, above which the x axis labels start. A label sits above its line.
 * The median label goes below its line when the 90th percentile line is too
 * close above it, and stays above the plot's bottom edge. The 90th percentile
 * label moves up when it would touch the median label. The old fixed offsets put
 * "Median" on top of "Sun" whenever the median ran near zero.
 */
export function endLabelOffsets(medY: number, p90Y: number, bottom: number) {
	const up = -(LABEL / 2 + GAP);
	const fitsAbove = medY + up - LABEL / 2 > p90Y + 2;
	const fitsBelow = medY - up + LABEL / 2 <= bottom;
	const med = fitsAbove || !fitsBelow ? up : -up;
	// A label above the median line needs the 90th percentile label to clear it.
	const p90 = med < 0 ? Math.min(up, medY + med - LABEL - 1 - p90Y) : up;
	return { med, p90 };
}

export function weekLines(profile: Hour[], { width, document }: DrawOptions) {
	const byHour = new Map(trusted(profile).map((row) => [row.h, row]));
	// One slot per hour of the week. A missing hour is NaN, which Plot draws as a
	// gap, not as a line through zero.
	const series = (key: 'med' | 'p90') => (h: number) => (byHour.get(h)?.[key] ?? NaN) / 60;
	const last = [...byHour.values()].at(-1);
	const label = (text: string, key: 'med' | 'p90', fill: string, dy: number) =>
		Plot.text(last ? [last] : [], {
			x: (d: Hour) => d.h,
			y: (d: Hour) => d[key] / 60,
			text: () => text,
			textAnchor: 'end',
			dy,
			fill,
			stroke: PAPER,
			strokeWidth: 4,
			fontWeight: 600
		});
	const draw = (dy: { med: number; p90: number }) =>
		Plot.plot({
			document,
			width,
			height: HEIGHT,
			marginTop: MARGIN_TOP,
			marginLeft: 52,
			marginRight: 8,
			style: PLOT_STYLE,
			x: {
				domain: [0, 167],
				ticks: DAYS.map((_, i) => i * 24 + 12),
				tickFormat: (h: number) => DAYS[Math.floor(h / 24)],
				tickSize: 0,
				label: null
			},
			y: {
				label: 'Minutes late',
				labelAnchor: 'top',
				labelArrow: 'up',
				// The zero line is the timetable, so the axis says so.
				tickFormat: (m: number) => (m === 0 ? 'on time' : String(m))
			},
			marks: [
				Plot.gridY({ stroke: GRID, strokeOpacity: 1 }),
				Plot.ruleX([24, 48, 72, 96, 120, 144], { stroke: GRID }),
				Plot.ruleY([0], { stroke: INK }),
				Plot.lineY(WEEK, {
					x: (h: number) => h,
					y: series('p90'),
					stroke: ANNOTATION,
					strokeWidth: 2
				}),
				Plot.lineY(WEEK, { x: (h: number) => h, y: series('med'), stroke: INK, strokeWidth: 2 }),
				label('90th percentile', 'p90', ANNOTATION, dy.p90),
				label('Median', 'med', INK, dy.med)
			]
		});
	// The labels do not change the scales, so one draw gives the pixel positions
	// that the second draw needs.
	const first = draw({ med: -(LABEL / 2 + GAP), p90: -(LABEL / 2 + GAP) });
	if (!last) return first;
	const y = (
		first as unknown as { scale(name: 'y'): { range: number[]; apply(v: number): number } }
	).scale('y');
	return draw(endLabelOffsets(y.apply(last.med / 60), y.apply(last.p90 / 60), y.range[0]));
}
