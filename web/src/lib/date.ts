/** "2026-11-15" as "November 15, 2026". It reads the day as UTC so no time zone shifts it. */
export function longDate(day: string): string {
	return new Date(`${day}T00:00:00Z`).toLocaleDateString('en-US', {
		month: 'long',
		day: 'numeric',
		year: 'numeric',
		timeZone: 'UTC'
	});
}

const DAY_MS = 86_400_000;
/** A service day is a calendar date in Los Angeles, so it counts days, not hours. Reading it as UTC keeps a time zone from shifting it. */
const dayNumber = (day: string): number => Date.parse(`${day}T00:00:00Z`) / DAY_MS;

/**
 * The date in Los Angeles at `now`, as YYYY-MM-DD. Between 4 pm and midnight
 * Pacific the UTC date is already tomorrow's, so `toISOString` would name the
 * wrong day for eight hours of every evening.
 */
export function pacificToday(now: Date): string {
	const parts = new Intl.DateTimeFormat('en-US', {
		timeZone: 'America/Los_Angeles',
		year: 'numeric',
		month: '2-digit',
		day: '2-digit'
	}).formatToParts(now);
	const part = (type: string) => parts.find((p) => p.type === type)!.value;
	return `${part('year')}-${part('month')}-${part('day')}`;
}

/** The date `count` days after `day`. A negative count goes back. */
export const addDays = (day: string, count: number): string =>
	new Date((dayNumber(day) + count) * DAY_MS).toISOString().slice(0, 10);

/** Whole days from `from` to `to`. It is negative when `to` is earlier. */
export const daysBetween = (from: string, to: string): number => dayNumber(to) - dayNumber(from);

/** "2026-11-15" as "Nov 15". */
export function shortDate(day: string): string {
	return new Date(`${day}T00:00:00Z`).toLocaleDateString('en-US', {
		month: 'short',
		day: 'numeric',
		timeZone: 'UTC'
	});
}
