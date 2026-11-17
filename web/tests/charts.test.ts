// The chart builders drawn without a browser. Plot gets linkedom's document, so
// each test reads attributes off the SVG that a visitor would see.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseHTML } from 'linkedom';
import { createRawSnippet } from 'svelte';
import { render } from 'svelte/server';
import ErrorState from '../src/lib/charts/ErrorState.svelte';
import Heatmap from '../src/lib/charts/Heatmap.svelte';
import ResultView from '../src/lib/charts/ResultView.svelte';
import WeekLines from '../src/lib/charts/WeekLines.svelte';
import { HOT_HOUR, THIN_HOUR, fixtureProfile, fixtureStops } from '../src/lib/charts/fixtures.ts';
import { heatmap, heatmapLabel, worstHour } from '../src/lib/charts/heatmap.ts';
import { weekLines } from '../src/lib/charts/lineChart.ts';
import { stopStrip } from '../src/lib/charts/strip.ts';
import { MIN_ARRIVALS, RAMP } from '../src/lib/charts/theme.ts';
import type { Hour } from '../src/lib/data/types.ts';
import { collisions, textBoxes } from './svgText.ts';

const { document } = parseHTML('<!doctype html><html><body></body></html>');
const draw = { width: 800, document };
const marks = (svg: Element, name: string) =>
	[...svg.querySelectorAll(`g[aria-label="${name}"]`)].map((g) => [...g.children]);
const num = (el: Element, attr: string) => Number(el.getAttribute(attr));

// Plot puts a constant paint on the group and a per-cell paint on each rect, so
// the four cell marks are told apart by their group's attributes.
function cellGroups(svg: Element) {
	const groups = [...svg.querySelectorAll('g[aria-label="cell"]')];
	const rects = (test: (g: Element) => boolean) =>
		groups.filter(test).flatMap((g) => [...g.children]);
	const paint = (g: Element) => g.getAttribute('fill');
	return {
		ramp: rects((g) => paint(g) === null),
		thin: rects((g) => paint(g)?.startsWith('url(#') === true),
		absent: rects((g) => paint(g) === 'none' && g.hasAttribute('stroke-dasharray')),
		outline: rects((g) => paint(g) === 'none' && g.getAttribute('stroke') === 'var(--chart-ink)')
	};
}
const withHour = (h: number, change: Partial<Hour>) =>
	fixtureProfile().map((hour) => (hour.h === h ? { ...hour, ...change } : hour));
const center = (rect: Element, a: string, size: string) => num(rect, a) + num(rect, size) / 2;

test('the hot cell is at Friday 17:00 with the top color and the rest are lower', () => {
	const profile = fixtureProfile();
	const svg = heatmap(profile, draw);
	const { ramp: cells, outline } = cellGroups(svg);
	// The thin hour is hatched, so it is not one of the ramp cells.
	const measured = profile.filter((hour) => hour.n >= MIN_ARRIVALS);
	assert.equal(cells.length, measured.length);

	const fills = cells.map((rect) => rect.getAttribute('fill'));
	const top = RAMP.length - 1;
	assert.equal(fills.filter((fill) => fill === RAMP[top]).length, 1);
	assert.ok(fills.every((fill) => RAMP.includes(fill!)));
	assert.ok(fills.filter((fill) => fill !== RAMP[top]).every((fill) => RAMP.indexOf(fill!) < top));

	// Rows and columns are the distinct y and x values, sorted. The fixture has
	// data in every row and column, so the index is the day and the hour.
	const hot = cells[measured.findIndex((hour) => hour.h === HOT_HOUR)];
	const sorted = (attr: string) =>
		[...new Set(cells.map((rect) => num(rect, attr)))].sort((a, b) => a - b);
	assert.equal(sorted('y').indexOf(num(hot, 'y')), 4);
	assert.equal(sorted('x').indexOf(num(hot, 'x')), 17);
	assert.equal(hot.getAttribute('fill'), RAMP[top]);

	// The outline and the label sit on the same cell. The cells are inset by half
	// a pixel and the outline is not, so compare centers.
	assert.equal(outline.length, 1);
	assert.equal(center(outline[0], 'x', 'width'), center(hot, 'x', 'width'));
	assert.equal(center(outline[0], 'y', 'height'), center(hot, 'y', 'height'));
	assert.match(svg.textContent!, /Worst: 12 min late/);
});

test('an hour with too few arrivals is hatched, not a ramp color', () => {
	const svg = heatmap(fixtureProfile(), draw);
	const { thin, ramp } = cellGroups(svg);
	assert.equal(thin.length, 1);
	const pattern = svg.querySelector('defs pattern')!;
	assert.equal(thin[0].parentElement!.getAttribute('fill'), `url(#${pattern.getAttribute('id')})`);
	assert.equal(pattern.querySelector('line')!.getAttribute('stroke'), 'var(--chart-quiet)');
	assert.match(thin[0].querySelector('title')!.textContent!, /Too few arrivals: 2 of 5 needed/);
	// The thin hour sits at Tuesday 06:00, a cell no ramp rect occupies.
	const at = (rect: Element) => `${num(rect, 'x')},${num(rect, 'y')}`;
	assert.ok(!ramp.map(at).includes(at(thin[0])));
});

test('an hour with no profile entry is a dotted outline with no fill', () => {
	const profile = fixtureProfile();
	const svg = heatmap(profile, draw);
	const { absent } = cellGroups(svg);
	assert.equal(absent.length, 168 - profile.length);
	const group = absent[0].parentElement!;
	assert.equal(group.getAttribute('fill'), 'none');
	assert.equal(group.getAttribute('stroke'), 'var(--chart-quiet)');
	assert.ok(group.getAttribute('stroke-dasharray'));
	assert.match(absent[0].querySelector('title')!.textContent!, /No service or nothing measured/);
});

test('neither a thin hour nor an absent hour can be the worst cell', () => {
	assert.equal(worstHour(fixtureProfile())?.h, HOT_HOUR);
	// Make the thin hour the biggest median in the week. It still does not rank.
	assert.equal(worstHour(withHour(THIN_HOUR, { med: 99999 }))?.h, HOT_HOUR);
	// With the hot hour thin too, the worst falls to a measured hour, never a gap.
	const rest = withHour(HOT_HOUR, { n: 3 });
	const worst = worstHour(rest)!;
	assert.ok(worst.n >= MIN_ARRIVALS && worst.h !== HOT_HOUR && worst.h !== THIN_HOUR);
	const { outline, thin } = cellGroups(heatmap(rest, draw));
	assert.equal(outline.length, 1);
	assert.equal(thin.length, 2);
	const at = (rect: Element) => `${center(rect, 'x', 'width')},${center(rect, 'y', 'height')}`;
	assert.ok(!thin.map(at).includes(at(outline[0])));
});

test('when no hour ran late there is no worst cell and the label says so', () => {
	const early = fixtureProfile().map((hour) => ({ ...hour, med: -60 - (hour.h % 5) * 10 }));
	assert.equal(worstHour(early), undefined);
	const { outline } = cellGroups(heatmap(early, draw));
	assert.equal(outline.length, 0);
	assert.doesNotMatch(heatmap(early, draw).textContent!, /Worst/);
	assert.match(heatmapLabel(early), /No hour ran late\./);
	assert.doesNotMatch(heatmapLabel(early), /worst hour/);
	// A largest median of exactly zero is on time, not late.
	const zero = early.map((hour) => (hour.h === 10 ? { ...hour, med: 0 } : hour));
	assert.equal(worstHour(zero), undefined);
	// One late hour brings the worst cell back.
	assert.equal(
		worstHour(withHour(10, { med: 1 }).map((hour) => ({ ...hour, med: hour.h === 10 ? 1 : -60 })))
			?.h,
		10
	);
});

test('the line chart draws two series of at most 168 points', () => {
	const svg = weekLines(fixtureProfile(), draw);
	const lines = marks(svg, 'line');
	assert.equal(lines.length, 2);
	for (const [path] of lines) {
		const points = path.getAttribute('d')!.match(/[ML]/g)!.length;
		assert.ok(points > 1 && points <= 168, `${points} points`);
	}
});

// The two end labels as [top, bottom] pixel spans. Plot puts the offset on the
// group and the data position on the text, and the x axis labels start 9 px
// under the plot's bottom edge.
function endLabels(svg: Element) {
	const groups = [...svg.querySelectorAll('g[aria-label="text"]')];
	const span = (name: string) => {
		const group = groups.find((g) => g.textContent === name)!;
		const dy = Number(
			/translate\(-?[\d.]+,(-?[\d.]+)\)/.exec(group.getAttribute('transform')!)![1]
		);
		const y = Number(/,(-?[\d.]+)\)/.exec(group.children[0].getAttribute('transform')!)![1]);
		return [y + dy - 7, y + dy + 7];
	};
	return { median: span('Median'), p90: span('90th percentile') };
}
const hoursOf = (rows: [number, number, number][]): Hour[] =>
	rows.map(([h, med, p90]) => ({ h, n: 40, sched: 50, med, p90, pct5: 10, ontime: 80 }));

test('the end labels never overlap each other or the axis labels', () => {
	const bottom = 230;
	const cases: Record<string, Hour[]> = {
		'full week': fixtureProfile(),
		// A line with little data, such as the 697. The last trusted hour is Sunday noon.
		'little data': hoursOf([
			[7, 60, 840],
			[8, 90, 900],
			[130, 60, 400],
			[156, 85, 280]
		]),
		// The median is on the zero line and the 90th percentile is close above it.
		'both near zero': hoursOf([
			[7, 60, 840],
			[156, 5, 20]
		]),
		'median under zero': hoursOf([
			[7, 60, 840],
			[156, -90, -20]
		])
	};
	for (const [name, profile] of Object.entries(cases)) {
		for (const width of [343, 800]) {
			const { median, p90 } = endLabels(weekLines(profile, { width, document }));
			assert.ok(median[1] <= bottom, `${name} ${width}: the median label ends at ${median[1]}`);
			assert.ok(p90[1] <= bottom, `${name} ${width}: the 90th percentile label ends at ${p90[1]}`);
			const apart = median[0] >= p90[1] || p90[0] >= median[1];
			assert.ok(apart, `${name} ${width}: labels overlap, ${median} and ${p90}`);
		}
	}
});

test('the strip draws a dot per stop with data, and hollow dots for thin stops', () => {
	const stops = fixtureStops();
	const withData = stops.filter((stop) => stop.cells.length > 0);
	const thin = withData.filter((stop) => stop.cells[0].n < 5);
	// Plot puts fill on the group, so the hollow dots are the group with fill none.
	const groups = [...stopStrip(stops, 'wk-pm', draw).querySelectorAll('g[aria-label="dot"]')];
	const hollow = groups.filter((g) => g.getAttribute('fill') === 'none');
	const solid = groups.filter((g) => g.getAttribute('fill') !== 'none');
	assert.equal(hollow.length, 1);
	assert.equal(hollow[0].children.length, thin.length);
	assert.equal(solid[0].children.length, withData.length - thin.length);
	assert.ok(thin.length > 0);
});

test('the strip keeps the on-time rule inside the plot when every stop runs early', () => {
	const early = [-300, -240, -200].map((med, i) => ({
		...fixtureStops()[0],
		id: `E${i}`,
		name: `Early ${i}`,
		cells: [{ d: 'wk-pm', n: 300, sched: 340, med, p90: med, pct5: 0 }]
	}));
	const svg = stopStrip(early, 'wk-pm', draw);
	// The zero rule is the one ruleX group stroked in ink. Plot puts the stroke on the group.
	const group = [...svg.querySelectorAll('g[aria-label="rule"]')].find(
		(g) => g.getAttribute('stroke') === 'var(--chart-ink)'
	);
	assert.ok(group, 'the zero rule is drawn');
	const rule = group.children[0];
	const x = num(rule, 'x1');
	assert.ok(x > 0 && x < draw.width, `the rule at zero is at ${x}`);
	// The latest dot still sits left of the rule, and none leaves the plot.
	for (const dot of marks(svg, 'dot').flat()) assert.ok(num(dot, 'cx') <= x);
});

test('every color is a CSS variable, so both themes work', () => {
	const profile = fixtureProfile();
	const outputs = [
		heatmap(profile, draw),
		weekLines(profile, draw),
		stopStrip(fixtureStops(), 'wk-pm', draw)
		// Plot's own <style> block sets --plot-background to white. Nothing here uses it.
	].map((svg) => svg.outerHTML.replace(/<style>[\s\S]*?<\/style>/g, ''));
	for (const html of outputs) {
		assert.doesNotMatch(html, /#[0-9a-f]{3,8}\b|rgba?\(|hsla?\(|oklch\(/i);
		const values = [...html.matchAll(/\b(?:fill|stroke|color|background)[:=]"?([^;"]+)/g)];
		assert.ok(values.length > 3, 'the pattern found the colors');
		for (const [, value] of values) {
			assert.match(
				value,
				/^(none|currentColor|transparent|var\(--[a-z0-9-]+\)|url\(#howlate-thin\))$/,
				value
			);
		}
	}
});

test('a missing, errored or unreachable file renders the error state', () => {
	const children = createRawSnippet(() => ({ render: () => '<p>chart</p>' }));
	const failures = [
		{ kind: 'status', url: 'x/lines/801.json', status: 404 },
		{ kind: 'network', url: 'x/site/current.json' },
		{ kind: 'json', url: 'x/status.json' }
	] as const;
	for (const error of failures) {
		const { body } = render(ResultView, { props: { result: { ok: false, error }, children } });
		assert.match(body, /role="alert"/);
		assert.match(body, /We couldn't load this data\./);
		assert.doesNotMatch(body, /chart/);
	}
	assert.match(
		render(ErrorState, { props: { onretry: () => {} } }).body,
		/<button[^>]*>\s*Try again/
	);
});

test('a loaded result renders the chart and a pending one renders loading', () => {
	const children = createRawSnippet(() => ({ render: () => '<p>chart</p>' }));
	assert.match(
		render(ResultView, { props: { result: { ok: true, data: 1 }, children } }).body,
		/chart/
	);
	assert.match(
		render(ResultView, { props: { result: undefined, children } }).body,
		/role="status"/
	);
});

test('an empty profile renders the empty message, not a chart', () => {
	const { body } = render(Heatmap, {
		props: { profile: [], caption: 'c', source: 's', showOntime: true }
	});
	assert.match(body, /Not enough measured arrivals yet\./);
	assert.doesNotMatch(body, /role="img"/);
});

test('the heatmap has a table fallback with one row per day', () => {
	const { body } = render(Heatmap, {
		props: { profile: fixtureProfile(), caption: 'c', source: 's', showOntime: true }
	});
	assert.equal(body.match(/<tr>/g)?.length, 8);
	assert.match(body, /too few arrivals: 2 of 5 needed/);
	assert.match(body, /no service or nothing measured/);
});

test('the key shows the hatch and the dotted outline in words, drawn from the same paint', () => {
	const { body } = render(Heatmap, {
		props: { profile: fixtureProfile(), caption: 'c', source: 's', showOntime: true }
	});
	assert.match(body, /too few arrivals/);
	assert.match(body, /none measured/);
	assert.doesNotMatch(body, /no service</);
	assert.match(body, /<pattern[^>]*id="howlate-thin-key"/);
	assert.match(body, /<line[^>]*stroke="var\(--chart-quiet\)"/);
	assert.match(body, /stroke="var\(--chart-quiet\)"[^>]*stroke-dasharray="1.5 3"/);
	assert.doesNotMatch(body, /Blank hours/);
});

test('the heatmap label says how many hours are hatched', () => {
	assert.match(
		heatmapLabel(fixtureProfile()),
		/1 hour has too few arrivals to judge and is hatched/
	);
	assert.doesNotMatch(heatmapLabel(fixtureProfile().filter((h) => h.h !== THIN_HOUR)), /hatched/);
});

test('the line chart note explains gaps only when hours are missing', () => {
	const note = /Gaps are hours with too few arrivals or none measured\./;
	const props = { caption: 'c', source: 's', showOntime: true };
	assert.match(render(WeekLines, { props: { ...props, profile: fixtureProfile() } }).body, note);
	const full = fixtureProfile().map((h) => ({ ...h, n: 400 }));
	const all = Array.from({ length: 168 }, (_, h) => ({ ...full[0], h }));
	assert.doesNotMatch(render(WeekLines, { props: { ...props, profile: all } }).body, note);
});

test('a shape error says the site needs newer data, with a retry button', () => {
	const children = createRawSnippet(() => ({ render: () => '<p>chart</p>' }));
	const error = { kind: 'shape', url: 'x/lines/720.json' } as const;
	const { body } = render(ResultView, {
		props: { result: { ok: false, error }, onretry: () => {}, children }
	});
	assert.match(body, /role="alert"/);
	assert.match(
		body,
		/This page needs newer data than the site has yet\. Try again in a few minutes\./
	);
	assert.match(body, /Try again<\/button>/);
	assert.doesNotMatch(body, /chart/);
});

test('the week chart axis label clears the top tick label, at the top of the plot', () => {
	// The top tick sits at the plot's top edge when the largest delay is a tick value,
	// which is the case for the fixture and for any line with large delays.
	const cases = [fixtureProfile(), fixtureProfile().map((h) => ({ ...h, p90: 1500 }))];
	for (const profile of cases) {
		for (const width of [343, 800]) {
			const boxes = textBoxes(weekLines(profile, { width, document }));
			const label = boxes.find((b) => b.text.includes('Minutes late'))!;
			assert.ok(label, 'the axis label is drawn');
			assert.ok(label.top >= 0, `the label starts at ${label.top}`);
			assert.deepEqual(collisions(boxes), [], `${width}`);
		}
	}
});
