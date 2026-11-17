import type { CurrentPointer, LineFile, NetworkFile, SiteIndex, SiteStatus } from './types';

/** Why a file did not load. The caller shows an error state, never a blank page. */
export type LoadError = {
	kind: 'network' | 'status' | 'json' | 'shape';
	url: string;
	/** The HTTP status, set when kind is 'status'. */
	status?: number;
};

/**
 * What a reader shows for a `shape` error: the file loaded, but a field the
 * page reads is missing. The bucket holds the old shape until the daily run
 * after a release, so this is a wait, not a fault.
 */
export const SHAPE_MESSAGE =
	'This page needs newer data than the site has yet. Try again in a few minutes.';

export type Result<T> = { ok: true; data: T } | { ok: false; error: LoadError };

export type Run = {
	pointer: CurrentPointer;
	index: () => Promise<Result<SiteIndex>>;
	status: () => Promise<Result<SiteStatus>>;
	line: (line: string) => Promise<Result<LineFile>>;
	network: () => Promise<Result<NetworkFile>>;
};

type Fetch = typeof fetch;

// The shape is checked by the pipeline's contract test and by the generated
// types, so the body is not validated again here. Every failure becomes a
// value, because a throw in a load function leaves the page blank.
export async function getJson<T>(url: string, fetchFn: Fetch = fetch): Promise<Result<T>> {
	let response: Response;
	try {
		response = await fetchFn(url);
	} catch {
		return { ok: false, error: { kind: 'network', url } };
	}
	if (response.status !== 200) {
		return { ok: false, error: { kind: 'status', url, status: response.status } };
	}
	try {
		return { ok: true, data: (await response.json()) as T };
	} catch {
		return { ok: false, error: { kind: 'json', url } };
	}
}

/**
 * Fetches current.json, then returns readers that all use the run it names.
 * Reading every file from one pointer means the page never mixes two runs, even
 * if the pointer moves while the page is open. `base` is the bucket root, so
 * the pointer is at <base>/site/current.json.
 */
export async function openRun(base: string, fetchFn: Fetch = fetch): Promise<Result<Run>> {
	const root = base.replace(/\/+$/, '');
	const pointer = await getJson<CurrentPointer>(`${root}/site/current.json`, fetchFn);
	if (!pointer.ok) return pointer;
	// The prefix is relative to the bucket root and ends in a slash.
	const file = <T>(path: string) => getJson<T>(`${root}/${pointer.data.prefix}${path}`, fetchFn);
	return {
		ok: true,
		data: {
			pointer: pointer.data,
			index: () => file<SiteIndex>('index.json'),
			status: () => file<SiteStatus>('status.json'),
			line: (line) => file<LineFile>(`lines/${encodeURIComponent(line)}.json`),
			network: () => file<NetworkFile>('network.json')
		}
	};
}
