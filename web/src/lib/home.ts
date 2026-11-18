import { openRun, type Result } from './data/load.ts';
import type { SiteIndex, SiteStatus } from './data/types';

/** One result per file, so a failed status file does not hide the line list. */
export type HomeData = { status: Result<SiteStatus>; index: Result<SiteIndex> };

/**
 * The home page's status strip and search list, read from one run. Two separate
 * reads each fetch current.json, so a daily run that lands between them gives
 * the page a strip from one run and a line list from another. Each file keeps
 * its own result, because the search box does not need the status file. Only a
 * failed pointer read fails the whole load, since without it no file has a path.
 */
export async function loadHome(
	base: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<HomeData>> {
	const run = await openRun(base, fetchFn);
	if (!run.ok) return run;
	const [status, index] = await Promise.all([run.data.status(), run.data.index()]);
	return { ok: true, data: { status, index } };
}
