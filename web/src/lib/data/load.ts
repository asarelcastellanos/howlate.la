import { isHealthFile, isLineFile, isSiteIndex, isSiteStatus } from './shape.ts';
import type {
	CurrentPointer,
	HealthFile,
	LineFile,
	NetworkFile,
	SiteIndex,
	SiteStatus
} from './types';

/** Why a file did not load. The caller shows an error state, never a blank page. */
export type LoadError = {
	/** 'shape' means the body is JSON but lacks a field the page reads. */
	kind: 'network' | 'status' | 'json' | 'shape';
	url: string;
	/** The HTTP status, set when kind is 'status'. */
	status?: number;
};

export type Result<T> = { ok: true; data: T } | { ok: false; error: LoadError };

export type Run = {
	pointer: CurrentPointer;
	index: () => Promise<Result<SiteIndex>>;
	status: () => Promise<Result<SiteStatus>>;
	line: (line: string) => Promise<Result<LineFile>>;
	network: () => Promise<Result<NetworkFile>>;
	health: () => Promise<Result<HealthFile>>;
};

type Fetch = typeof fetch;

// The pipeline's contract test and the generated types cover the full shape.
// `check` only reads the fields a page uses, so a file from an older run
// becomes an error value. Every failure becomes a value, because a throw in a
// load function leaves the page blank.
export async function getJson<T>(
	url: string,
	fetchFn: Fetch = fetch,
	check?: (body: unknown) => body is T
): Promise<Result<T>> {
	let response: Response;
	try {
		response = await fetchFn(url);
	} catch {
		return { ok: false, error: { kind: 'network', url } };
	}
	if (response.status !== 200) {
		return { ok: false, error: { kind: 'status', url, status: response.status } };
	}
	let body: unknown;
	try {
		body = await response.json();
	} catch {
		return { ok: false, error: { kind: 'json', url } };
	}
	if (check && !check(body)) return { ok: false, error: { kind: 'shape', url } };
	return { ok: true, data: body as T };
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
	const file = <T>(path: string, check?: (body: unknown) => body is T) =>
		getJson<T>(`${root}/${pointer.data.prefix}${path}`, fetchFn, check);
	return {
		ok: true,
		data: {
			pointer: pointer.data,
			index: () => file<SiteIndex>('index.json', isSiteIndex),
			status: () => file<SiteStatus>('status.json', isSiteStatus),
			line: (line) => file<LineFile>(`lines/${encodeURIComponent(line)}.json`, isLineFile),
			network: () => file<NetworkFile>('network.json'),
			health: () => file<HealthFile>('health.json', isHealthFile)
		}
	};
}
