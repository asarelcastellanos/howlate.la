import * as Plot from '@observablehq/plot';
import type { Hour } from '../data/types';
import {
	ANNOTATION,
	DAYS,
	DAY_NAMES,
	GRID,
	INK,
	MIN_ARRIVALS,
	PAPER,
	PLOT_STYLE,
	RAMP,
	RAMP_STEPS,
	delayLabel,
	hourLabel,
	trusted,
	type DrawOptions
} from './theme.ts';

const ROW = 26;
const HOURS = Array.from({ length: 24 }, (_, hour) => hour);
const day = (h: number) => Math.floor(h / 24);
const hourOfDay = (h: number) => h % 24;

/** The hour with the highest median among hours with enough arrivals. */
export function worstHour(profile: Hour[]): Hour | undefined {
	let worst: Hour | undefined;
	for (const hour of trusted(profile)) if (!worst || hour.med > worst.med) worst = hour;
	return worst;
}

/**
 * The hatch for hours with a profile entry but too few arrivals. The chart and
 * the key under it both draw from these numbers, in the same CSS variable.
 */
export const HATCH = { id: 'howlate-thin', size: 5, width: 2, angle: 45 };
/** The dash pattern of the outline on hours with no profile entry. */
export const DOTTED = '1.5 3';
export const DOTTED_WIDTH = 1.5;

export type Slot = { state: 'ok'; med: number } | { state: 'thin'; n: number } | { state: 'none' };

/** The seven rows by 24 columns. An hour is measured, too thin to judge, or absent. */
export function hourlyGrid(profile: Hour[]): Slot[][] {
	const grid = DAYS.map(() => HOURS.map((): Slot => ({ state: 'none' })));
	for (const hour of profile) {
		grid[day(hour.h)][hourOfDay(hour.h)] =
			hour.n >= MIN_ARRIVALS ? { state: 'ok', med: hour.med } : { state: 'thin', n: hour.n };
	}
	return grid;
}

function hatchDefs(document: Document) {
	const svg = (name: string, attrs: Record<string, string | number>) => {
		const el = document.createElementNS('http://www.w3.org/2000/svg', name);
		for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, String(value));
		return el;
	};
	const pattern = svg('pattern', {
		id: HATCH.id,
		width: HATCH.size,
		height: HATCH.size,
		patternUnits: 'userSpaceOnUse',
		patternTransform: `rotate(${HATCH.angle})`
	});
	pattern.append(
		svg('line', {
			x1: HATCH.size / 2,
			y1: 0,
			x2: HATCH.size / 2,
			y2: HATCH.size,
			stroke: GRID,
			'stroke-width': HATCH.width
		})
	);
	const defs = svg('defs', {});
	defs.append(pattern);
	return defs;
}

export function heatmapLabel(profile: Hour[]): string {
	const worst = worstHour(profile);
	const lead = 'Heatmap of median delay for each hour of the week.';
	if (!worst) return `${lead} No hour has enough arrivals to rank.`;
	const when = `${DAY_NAMES[day(worst.h)]} ${hourLabel(hourOfDay(worst.h))}`;
	const thin = profile.filter((hour) => hour.n < MIN_ARRIVALS).length;
	const note = thin
		? ` ${thin} ${thin === 1 ? 'hour has' : 'hours have'} too few arrivals to judge and ${thin === 1 ? 'is' : 'are'} hatched.`
		: '';
	return `${lead} ${when} is the worst hour, at ${delayLabel(worst.med)}.${note}`;
}

export function heatmap(profile: Hour[], { width, document }: DrawOptions) {
	const worst = worstHour(profile);
	// Accessors, not constants, so Plot puts the band scale to work on them.
	const pos = { x: (d: { h: number }) => hourOfDay(d.h), y: (d: { h: number }) => DAYS[day(d.h)] };
	const present = new Set(profile.map((hour) => hour.h));
	const absent = Array.from({ length: 168 }, (_, h) => ({ h })).filter(({ h }) => !present.has(h));
	const when = (h: number) => `${DAY_NAMES[day(h)]} ${hourLabel(hourOfDay(h))}`;
	const marks: Plot.Markish[] = [
		Plot.cell(trusted(profile), {
			...pos,
			fill: 'med',
			inset: 0.5,
			title: (d) => `${when(d.h)}, ${delayLabel(d.med)}, ${d.n} arrivals`
		}),
		// Too few arrivals to judge. Hatch, never a ramp color.
		Plot.cell(
			profile.filter((hour) => hour.n < MIN_ARRIVALS),
			{
				...pos,
				fill: `url(#${HATCH.id})`,
				inset: 0.5,
				title: (d) => `${when(d.h)}. Too few arrivals: ${d.n} of ${MIN_ARRIVALS} needed`
			}
		),
		// No profile entry at all, so no service or nothing measured. Outline only.
		Plot.cell(absent, {
			...pos,
			fill: 'none',
			stroke: GRID,
			strokeDasharray: DOTTED,
			strokeWidth: DOTTED_WIDTH,
			inset: 0.5,
			title: (d) => `${when(d.h)}. No service or nothing measured`
		}),
		Plot.text([0, 6, 12, 18], {
			x: (hour) => hour,
			text: hourLabel,
			frameAnchor: 'top',
			textAnchor: 'start',
			dy: -12,
			dx: -ROW / 4
		})
	];
	if (worst) {
		// The label sits above its row, except on Monday where it would run into
		// the hour labels, so it drops below.
		const above = day(worst.h) > 0;
		const late = hourOfDay(worst.h) > 12;
		marks.push(
			Plot.cell([worst], { ...pos, fill: 'none', stroke: INK, strokeWidth: 2 }),
			Plot.text([worst], {
				...pos,
				text: () => `Worst: ${delayLabel(worst.med)}`,
				dy: above ? -(ROW / 2 + 9) : ROW / 2 + 9,
				textAnchor: late ? 'end' : 'start',
				dx: late ? 8 : -8,
				fill: ANNOTATION,
				stroke: PAPER,
				strokeWidth: 4,
				fontWeight: 600
			})
		);
	}
	const svg = Plot.plot({
		document,
		width,
		height: 7 * ROW + 26,
		marginTop: 22,
		marginBottom: 4,
		marginLeft: 36,
		marginRight: 4,
		style: PLOT_STYLE,
		x: { type: 'band', domain: HOURS, axis: null, padding: 0 },
		y: { type: 'band', domain: DAYS, label: null, tickSize: 0, padding: 0 },
		color: { type: 'threshold', domain: RAMP_STEPS, range: RAMP },
		marks
	});
	svg.insertBefore(hatchDefs(document ?? globalThis.document), svg.firstChild);
	return svg;
}
