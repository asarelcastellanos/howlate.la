import type { Hour } from '../data/types';
import { delayWords } from '../linePage.ts';
import { DAY_NAMES, MIN_ARRIVALS, hourLabel, trusted } from './theme.ts';
import { worstHour } from './heatmap.ts';

const HOURS = 168;

/**
 * The hour after a key press, or undefined when the grid does not use the key,
 * so the caller can leave Tab and the rest to the browser. Every move stops at
 * the edge of the week and never wraps. Left from Monday 12 am stays there, and
 * Down from Sunday stays on Sunday. Left and Right do cross from one day to the
 * next, because the hours of the week are one row of 168 in the data. Home and
 * End stay in the current day.
 */
export function nextHour(h: number, key: string): number | undefined {
	const clamp = (value: number) => Math.min(HOURS - 1, Math.max(0, value));
	const dayStart = h - (h % 24);
	switch (key) {
		case 'ArrowLeft':
			return clamp(h - 1);
		case 'ArrowRight':
			return clamp(h + 1);
		case 'ArrowUp':
			return h >= 24 ? h - 24 : h;
		case 'ArrowDown':
			return h + 24 < HOURS ? h + 24 : h;
		case 'Home':
			return dayStart;
		case 'End':
			return dayStart + 23;
		default:
			return undefined;
	}
}

/** An hour of the week, with the numbers when the profile has an entry for it. */
export type ReadoutEntry = { h: number } & Partial<Pick<Hour, 'n' | 'med' | 'ontime'>>;

const plural = (n: number, word: string) =>
	`${n.toLocaleString('en-US')} ${word}${n === 1 ? '' : 's'}`;

/**
 * The hour in plain words for the line under the heatmap. A measured hour gives
 * the median, the on-time share when the line shows one, and the count. A thin
 * hour gives only the count, because its median is the one the heatmap hatches.
 */
export function readoutText(entry: ReadoutEntry, { showOntime }: { showOntime: boolean }): string {
	const when = `${DAY_NAMES[Math.floor(entry.h / 24)]} ${hourLabel(entry.h % 24)}.`;
	const { n, med, ontime } = entry;
	if (n === undefined || med === undefined || ontime === undefined)
		return `${when} Nothing measured.`;
	if (n < MIN_ARRIVALS) return `${when} Only ${plural(n, 'arrival')} measured, too few to judge.`;
	const share = showOntime ? ` ${Math.round(ontime)} percent on time.` : '';
	return `${when} Median ${delayWords(med)}.${share} ${plural(n, 'arrival')} measured.`;
}

/**
 * Where the selection starts, which is the worst hour. When no hour ran late
 * there is no worst, so it starts on the hour with the highest median that has
 * enough arrivals, and the chart draws no "worst" outline.
 */
export function startHour(profile: Hour[]): number {
	const worst = worstHour(profile);
	if (worst) return worst.h;
	let top: Hour | undefined;
	for (const hour of trusted(profile)) if (!top || hour.med > top.med) top = hour;
	return top?.h ?? 0;
}
