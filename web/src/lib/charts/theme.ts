// Every color a chart draws is a CSS variable string, so the SVG follows the
// theme through prefers-color-scheme with no JavaScript. Never put a hex value
// here. tests/charts.test.ts fails on one.

export const INK = 'var(--chart-ink)';
export const GRID = 'var(--chart-grid)';
/** The hatch and the dotted outline. Held to 3:1 on paper, unlike the grid. */
export const QUIET = 'var(--chart-quiet)';
export const AXIS = 'var(--chart-axis)';
export const ANNOTATION = 'var(--chart-annotation)';
export const PAPER = 'var(--paper)';

/** The five delay steps, from on time to very late. */
export const RAMP = [1, 2, 3, 4, 5].map((step) => `var(--delay-${step})`);

/**
 * Where the ramp steps, in seconds of median delay. 300 s is Metro's line
 * between on time and late. The other three split the minutes below it, because
 * in the 2026-11-16 run (89 days) 131 of the A Line's 161 hourly medians toward
 * Pomona are under 180 s, and one step for all of them would show no pattern.
 */
export const RAMP_STEPS = [60, 120, 180, 300];

/**
 * A median from fewer arrivals than this is never drawn as a ramp color or
 * named the "worst" cell. The heatmap hatches the hour, the strip draws a
 * hollow dot, and the line chart breaks the line. With 4 arrivals one late
 * train moves the median a whole step. In five lines checked on the same run
 * (720, 4, 204, 901 and 70), no weekday evening or Saturday late cell had
 * fewer than 5 arrivals, so hollow dots are rare on today's data. The worst A Line hour toward Long Beach has 2 arrivals,
 * which is why the label skips thin cells.
 */
export const MIN_ARRIVALS = 5;

/** Rows with enough arrivals to trust. Thin hours are left out, so they show as gaps. */
export const trusted = <T extends { n: number }>(rows: T[]): T[] =>
	rows.filter((row) => row.n >= MIN_ARRIVALS);

export const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
export const DAY_NAMES = [
	'Monday',
	'Tuesday',
	'Wednesday',
	'Thursday',
	'Friday',
	'Saturday',
	'Sunday'
];

/** Options every chart builder takes. `document` is set only when rendering without a browser. */
export type DrawOptions = { width: number; document?: Document };

/** Plot style shared by every chart. Plot draws SVG text with this font and color. */
export const PLOT_STYLE = {
	fontFamily: 'var(--font-sans, Inter Variable, system-ui, sans-serif)',
	fontSize: '12px',
	color: AXIS,
	background: 'transparent',
	overflow: 'visible'
};

export function hourLabel(hour: number): string {
	if (hour === 0) return '12 am';
	if (hour === 12) return 'noon';
	return hour < 12 ? `${hour} am` : `${hour - 12} pm`;
}

/** "12 min late", "1 min early" or "on time" for a delay in seconds. */
export function delayLabel(seconds: number): string {
	const minutes = Math.round(Math.abs(seconds) / 60);
	if (minutes === 0) return 'on time';
	return `${minutes} min ${seconds > 0 ? 'late' : 'early'}`;
}
