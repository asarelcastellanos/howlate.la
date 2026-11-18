import { openRun, type Result } from './data/load.ts';
import { longDate } from './date.ts';
import { estimatedNote } from './estimated.ts';
import { SHOW_RAIL_ONTIME } from './config.ts';
import { showsOntime } from './linePage.ts';
import { shareText } from './share.ts';

/** The network-wide on-time share for buses and for rail, over the days the site holds. */
export type NetworkShares = {
	bus: number | null;
	rail: number | null;
	/** Bus arrivals with a delay and how many of them were estimated. Absent in a file from before the count. */
	busArrivals?: { n: number; est: number };
	days: number;
	last_day: string;
};

/**
 * The share in one scope of network.json: a number, null when nothing was
 * measured, or undefined when the field is not there. The loader does not check
 * network.json's shape, so this reads it as unknown.
 */
function shareOf(scope: unknown): number | null | undefined {
	const ontime = (scope as { all?: { ontime?: unknown } } | null)?.all?.ontime;
	if (ontime === null) return null;
	return typeof ontime === 'number' && Number.isFinite(ontime) ? ontime : undefined;
}

/** The arrival count and the estimated count of one scope, or undefined when either is missing. */
function arrivalsOf(scope: unknown): { n: number; est: number } | undefined {
	const all = (scope as { all?: { n?: unknown; est?: unknown } } | null)?.all;
	return typeof all?.n === 'number' && typeof all.est === 'number'
		? { n: all.n, est: all.est }
		: undefined;
}

/**
 * Reads network.json and status.json from one run, for the methods page. The page
 * shows the shares live because they change every day, so no figure is typed
 * into its copy. Any failure is an error value, and the page then leaves the
 * sentence out.
 */
export async function loadShares(
	base: string,
	fetchFn: typeof fetch = fetch
): Promise<Result<NetworkShares>> {
	const run = await openRun(base, fetchFn);
	if (!run.ok) return run;
	const [network, status] = await Promise.all([run.data.network(), run.data.status()]);
	if (!network.ok) return network;
	if (!status.ok) return status;
	// The body can be any JSON, so read it as unknown. `null` has no `.bus`.
	const body = network.data as unknown;
	const scopes = typeof body === 'object' && body !== null ? (body as Record<string, unknown>) : {};
	const bus = shareOf(scopes.bus);
	const rail = shareOf(scopes.rail);
	if (bus === undefined || rail === undefined) {
		const url = `${base.replace(/\/+$/, '')}/${run.data.pointer.prefix}network.json`;
		return { ok: false, error: { kind: 'shape', url } };
	}
	const busArrivals = arrivalsOf(scopes.bus);
	return {
		ok: true,
		data: {
			bus,
			rail,
			...(busArrivals && { busArrivals }),
			days: status.data.days,
			last_day: status.data.last_day
		}
	};
}

/**
 * The sentence for the methods page, or undefined when no mode that may show a
 * share has one. Rail is left out while `railGate` (SHOW_RAIL_ONTIME) is false.
 */
export function sharesText(
	{ bus, rail, busArrivals, days, last_day }: NetworkShares,
	railGate: boolean = SHOW_RAIL_ONTIME
): string | undefined {
	const parts = [
		bus === null ? undefined : `${shareText(bus)} percent of measured bus arrivals`,
		rail === null || !showsOntime('rail', railGate)
			? undefined
			: `${shareText(rail)} percent of measured rail arrivals`
	].filter((part) => part !== undefined);
	if (parts.length === 0) return undefined;
	const shares = `As of ${longDate(last_day)}, over ${days} days of data, HowLate scored ${parts.join(' and ')} as on time. These shares change every day. Each line page has its own.`;
	const estimated =
		bus === null || !busArrivals
			? undefined
			: estimatedNote(busArrivals.n, busArrivals.est, 'the measured bus arrivals');
	return estimated ? `${shares} ${estimated}` : shares;
}
