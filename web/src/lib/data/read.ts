import { checkRankingIndex } from '../ranking.ts';
import { openRun, type Result } from './load.ts';
import type { LineFile, NetworkFile, SiteIndex, SiteStatus } from './types';

// Each read opens the run first, so the file always comes from the run that
// current.json names. A failure at either step is the same kind of value.
export async function readStatus(base: string): Promise<Result<SiteStatus>> {
	const run = await openRun(base);
	return run.ok ? run.data.status() : run;
}

export async function readIndex(base: string): Promise<Result<SiteIndex>> {
	const run = await openRun(base);
	return run.ok ? run.data.index() : run;
}

export async function readLine(base: string, line: string): Promise<Result<LineFile>> {
	const run = await openRun(base);
	return run.ok ? run.data.line(line) : run;
}

export async function readNetwork(base: string): Promise<Result<NetworkFile>> {
	const run = await openRun(base);
	return run.ok ? run.data.network() : run;
}

// The ranking page reads five numbers from every entry. Until the daily run
// after a release, the bucket's index has none of them, so this checks the body
// and returns a `shape` error the page can show.
export async function readRankingIndex(
	base: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<SiteIndex>> {
	const run = await openRun(base, fetchFn);
	if (!run.ok) return run;
	const index = await run.data.index();
	if (!index.ok) return index;
	const url = `${base.replace(/\/+$/, '')}/${run.data.pointer.prefix}index.json`;
	return checkRankingIndex(index.data, url);
}
