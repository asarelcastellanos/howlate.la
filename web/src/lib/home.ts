import { openRun, type Result } from './data/load.ts';
import type { SiteIndex, SiteStatus } from './data/types';

export type HomeData = { status: SiteStatus; index: SiteIndex };

/**
 * The home page's status strip and search list, read from one run. Two separate
 * reads each fetch current.json, so a daily run that lands between them gives
 * the page a strip from one run and a line list from another.
 */
export async function loadHome(
	base: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<HomeData>> {
	const run = await openRun(base, fetchFn);
	if (!run.ok) return run;
	const [status, index] = await Promise.all([run.data.status(), run.data.index()]);
	if (!status.ok) return status;
	if (!index.ok) return index;
	return { ok: true, data: { status: status.data, index: index.data } };
}
