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
	assert.equal(pattern.querySelector('line')!.getAttribute('stroke'), 'var(--chart-grid)');
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
	assert.equal(group.getAttribute('stroke'), 'var(--chart-grid)');
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

test('the line chart draws two series of at most 168 points', () => {
	const svg = weekLines(fixtureProfile(), draw);
	const lines = marks(svg, 'line');
	assert.equal(lines.length, 2);
	for (const [path] of lines) {
		const points = path.getAttribute('d')!.match(/[ML]/g)!.length;
		assert.ok(points > 1 && points <= 168, `${points} points`);
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
	const { body } = render(Heatmap, { props: { profile: [], caption: 'c', source: 's' } });
	assert.match(body, /Not enough measured arrivals yet\./);
	assert.doesNotMatch(body, /role="img"/);
});

test('the heatmap has a table fallback with one row per day', () => {
	const { body } = render(Heatmap, {
		props: { profile: fixtureProfile(), caption: 'c', source: 's' }
	});
	assert.equal(body.match(/<tr>/g)?.length, 8);
	assert.match(body, /too few arrivals: 2 of 5 needed/);
	assert.match(body, /no service or nothing measured/);
});

test('the key shows the hatch and the dotted outline in words, drawn from the same paint', () => {
	const { body } = render(Heatmap, {
		props: { profile: fixtureProfile(), caption: 'c', source: 's' }
	});
	assert.match(body, /too few arrivals/);
	assert.match(body, /no service/);
	assert.match(body, /<pattern[^>]*id="howlate-thin-key"/);
	assert.match(body, /stroke="var\(--chart-grid\)"[^>]*stroke-dasharray="1.5 3"/);
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
	const note = /Gaps are hours with too few arrivals or no service\./;
	const props = { caption: 'c', source: 's' };
	assert.match(render(WeekLines, { props: { ...props, profile: fixtureProfile() } }).body, note);
	const full = fixtureProfile().map((h) => ({ ...h, n: 400 }));
	const all = Array.from({ length: 168 }, (_, h) => ({ ...full[0], h }));
	assert.doesNotMatch(render(WeekLines, { props: { ...props, profile: all } }).body, note);
});
