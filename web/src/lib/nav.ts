/** One entry in the main navigation. `path` is a route, and `hash` jumps to a place on it. */
export type NavItem = { label: string; path: string; hash?: string; ready: boolean };

/**
 * The main navigation, in the order it shows. An entry with `ready: false` is
 * not drawn, so a page's link can be listed before the page exists. The PR that
 * adds the page flips the flag.
 */
export const NAV: readonly NavItem[] = [
	{ label: 'Find a line', path: '/', hash: '#search', ready: true },
	{ label: 'Ranking', path: '/ranking', ready: true },
	{ label: 'Methods', path: '/methods', ready: true },
	{ label: 'Behind the scenes', path: '/behind-the-scenes', ready: false }
];

/**
 * Whether an entry is the page being shown. `route` is the router's route id,
 * which has no base path and is known while the page prerenders. A link's
 * resolved address cannot stand in for it, because resolve() returns a
 * relative address during prerender.
 */
export const isCurrent = (item: NavItem, route: string | null): boolean => item.path === route;
