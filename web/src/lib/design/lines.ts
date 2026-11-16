// Line colors come from Metro's own GTFS routes.txt (the rail feed for A to K,
// the bus feed for G and J). The bullet always uses the raw color. `mark` is
// what charts and chips draw with, per theme. It equals the raw color unless
// the raw color is under 3:1 against that theme's page. src/routes/layout.css
// holds the same values as --line-*, and tests/contrast.test.ts checks that the
// two agree.

export type Line = {
	/** Lowercase letter. Also the suffix of the --line-* CSS variable. */
	id: string;
	/** route_id in routes.txt. */
	routeId: string;
	/** The accessible name, for example "A Line". */
	name: string;
	/** What the bullet shows. */
	symbol: string;
	color: string;
	textColor: string;
	mark: { light: string; dark: string };
};

// prettier-ignore
export const LINES = [
	{ id: 'a', routeId: '801', name: 'A Line', symbol: 'A', color: '#0072BC', textColor: '#FFFFFF', mark: { light: '#0072BC', dark: '#0072BC' } },
	{ id: 'b', routeId: '802', name: 'B Line', symbol: 'B', color: '#EB131B', textColor: '#FFFFFF', mark: { light: '#EB131B', dark: '#EB131B' } },
	{ id: 'c', routeId: '803', name: 'C Line', symbol: 'C', color: '#58A738', textColor: '#FFFFFF', mark: { light: '#4B8B2F', dark: '#58A738' } },
	{ id: 'd', routeId: '805', name: 'D Line', symbol: 'D', color: '#A05DA5', textColor: '#FFFFFF', mark: { light: '#A05DA5', dark: '#A05DA5' } },
	{ id: 'e', routeId: '804', name: 'E Line', symbol: 'E', color: '#FDB913', textColor: '#000000', mark: { light: '#A87D00', dark: '#FDB913' } },
	{ id: 'k', routeId: '807', name: 'K Line', symbol: 'K', color: '#E56DB1', textColor: '#000000', mark: { light: '#D24A9B', dark: '#E56DB1' } },
	{ id: 'g', routeId: '901-13201', name: 'G Line', symbol: 'G', color: '#FC4C02', textColor: '#FFFFFF', mark: { light: '#FC4C02', dark: '#FC4C02' } },
	{ id: 'j', routeId: '910-13201', name: 'J Line', symbol: 'J', color: '#ADB8BF', textColor: '#000000', mark: { light: '#7D888F', dark: '#ADB8BF' } }
] as const satisfies readonly Line[];

export type LineId = (typeof LINES)[number]['id'];

export function lineById(id: LineId): Line {
	return LINES.find((line) => line.id === id)!;
}

// The bus feed gives no color to Local, Express or Limited routes, and gives
// the three Rapid routes black on white. These styles invent no color. Rapid
// uses the page's ink and paper tokens, which is black on white in the light
// theme and keeps the bullet visible in the dark one.
export const BUS_SERVICES = {
	local: { name: 'Local', shape: 'circle', fill: false, dashed: false },
	rapid: { name: 'Rapid', shape: 'circle', fill: true, dashed: false },
	limited: { name: 'Limited', shape: 'circle', fill: false, dashed: true },
	express: { name: 'Express', shape: 'pill', fill: false, dashed: false }
} as const;

export type BusService = keyof typeof BUS_SERVICES;
