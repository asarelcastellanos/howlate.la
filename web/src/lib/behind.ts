import { readHealth } from './data/read.ts';
import type { Result } from './data/load.ts';
import type { HealthDay, HealthFile } from './data/types';
import { addDays, daysBetween } from './date.ts';

/**
 * The daily job runs at 08:00 Pacific and grades yesterday. From 00:00 until
 * that run finishes, about 8 hours every night, the newest graded day is 2 days
 * old. A gap of 2 is therefore normal and the panel warns from 3, after one
 * missed run. The pipeline's own alarm is `MAX_LAG_DAYS = 3` in r2.py. It runs
 * only right after a run, when the normal gap is 1, and forgives two failed days.
 */
export const STALE_AFTER_DAYS = 2;

/** The strip shows as many days as health.json lists at most. */
export const STRIP_DAYS = 14;

export type Freshness = {
	/** Days from the newest graded day to today. Negative when the day is in the future. */
	daysOld: number;
	stale: boolean;
};

/** Both arguments are Los Angeles dates. A future day is not stale, because it is not old. */
export function freshness(lastDay: string, today: string): Freshness {
	const daysOld = daysBetween(lastDay, today);
	return { daysOld, stale: daysOld > STALE_AFTER_DAYS };
}

export type StripCell = { day: string; state: 'ok' | 'failed' | 'none' };

/**
 * One cell for each of the last `STRIP_DAYS` days up to `lastDay`, oldest
 * first, so the newest sits on the right. A day with no report is its own
 * state. health.json leaves such a day out, and calling it failed would claim a
 * check ran.
 */
export function buildStrip(
	recent: readonly HealthDay[],
	lastDay: string,
	days = STRIP_DAYS
): StripCell[] {
	const reports = new Map(recent.map((day) => [day.service_date, day]));
	return Array.from({ length: days }, (_, i) => {
		const day = addDays(lastDay, i - (days - 1));
		const report = reports.get(day);
		return { day, state: report ? (report.ok ? 'ok' : 'failed') : 'none' };
	});
}

/** The newest day's report. It is missing when the run was built without reports. */
export const newestDay = (health: HealthFile): HealthDay | undefined =>
	health.recent.find((day) => day.service_date === health.last_day);

export type CheckRow = { label: string; ok: boolean; measured: string; rule: string };

// A value has many decimal places. Under 1, a second decimal keeps 0.01 from reading as 0.
const round = (value: number): string => String(Number(value.toFixed(Math.abs(value) < 1 ? 2 : 1)));

/** One check in plain words. The label is the pipeline's, so a renamed check needs no change here. */
export function checkRow(check: HealthFile['checks'][number]): CheckRow {
	return {
		label: check.label.charAt(0).toUpperCase() + check.label.slice(1),
		ok: check.ok,
		measured: round(check.value),
		rule:
			check.kind === 'range'
				? `passes from ${round(check.low)} to ${round(check.high)}`
				: `passes at ${check.expected}`
	};
}

/** A failed check's plain label. A day graded by an older version can name a check the file no longer lists. */
export const failedLabel = (health: HealthFile, name: string): string =>
	health.checks.find((check) => check.name === name)?.label ?? name;

/**
 * Reads health.json and hands the page the outcome as data. The page shows a
 * missing or old-shape file as a calm message, not as the site's error box, so
 * the load always succeeds and the outcome is what the page reads.
 */
export const readStatusReport = async (base: string): Promise<Result<Result<HealthFile>>> => ({
	ok: true,
	data: await readHealth(base)
});
