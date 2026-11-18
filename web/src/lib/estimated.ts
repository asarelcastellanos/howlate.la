/** The id of the methods section that says how an arrival is timed and estimated. */
export const ESTIMATE_ANCHOR = 'how-an-arrival-is-timed';

/** Where the estimate notes link. The site is served from the domain root, so the path has no base. */
export const ESTIMATE_HREF = `/methods#${ESTIMATE_ANCHOR}`;

/** What the pipeline did to an estimated arrival, in the words every note uses. */
export const ESTIMATED_WORDS = 'estimated from where the bus was between two reports';

/**
 * The share of `n` arrivals that were placed between two reports of the same bus, as a
 * whole percent in words: "23", or "fewer than 1" because a few estimates are not none.
 * Undefined when there were none, and when the file has no count. Between a release and
 * the first daily run after it the published files have no `est`, and a missing count
 * must say nothing, never "0 percent".
 */
export function estimatedShare(n: number, est: number | undefined): string | undefined {
	if (est === undefined || n <= 0 || est <= 0) return undefined;
	const percent = (100 * est) / n;
	return percent < 0.5 ? 'fewer than 1' : String(Math.round(percent));
}

/**
 * One sentence about a total, such as the arrivals in one direction of a line. `what` is
 * the subject of the sentence and must be a plural noun phrase.
 */
export function estimatedNote(
	n: number,
	est: number | undefined,
	what = 'these arrivals'
): string | undefined {
	const share = estimatedShare(n, est);
	if (share === undefined) return undefined;
	return `${share.charAt(0).toUpperCase()}${share.slice(1)} percent of ${what} were ${ESTIMATED_WORDS}.`;
}
