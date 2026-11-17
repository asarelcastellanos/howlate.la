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
