import { LINE_LIST } from '#lib/data/lines.ts';

// The layout prerenders every page, and the line ids come from the daily data. A
// committed list (src/lib/data/lines.json, refreshed by `npm run lines:refresh`)
// gives the build its ids, so a line page's title and link preview are in the served
// HTML. The build must not fetch the index, so an unreachable index cannot fail it.
// An id outside the list is not built, and Cloudflare serves the app shell for it,
// which still shows the not-found message.
export const prerender = true;

export function entries() {
	return LINE_LIST.map(({ line }) => ({ line }));
}
