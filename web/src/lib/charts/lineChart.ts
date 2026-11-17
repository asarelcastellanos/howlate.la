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
	return Plot.plot({
		document,
		width,
		height: 260,
		marginTop: 8,
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
			label('90th percentile', 'p90', ANNOTATION, -8),
			label('Median', 'med', INK, 16)
		]
	});
}
