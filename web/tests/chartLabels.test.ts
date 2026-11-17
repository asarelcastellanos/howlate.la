// Plot labels its mark groups (aria-label="cell", "rule", "dot") but gives them
// no role, and axe fails the page on aria-prohibited-attr for each one. Chart.svelte
// drops those labels after a draw, so each chart is drawn here and run through the
// same function, with the heatmap checked to still find its cells afterwards.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseHTML } from 'linkedom';
import { fixtureProfile, fixtureStops } from '../src/lib/charts/fixtures.ts';
import { CELL_CLASS, heatmap, selectHour } from '../src/lib/charts/heatmap.ts';
import { weekLines } from '../src/lib/charts/lineChart.ts';
import { dropGroupLabels } from '../src/lib/charts/plotLabels.ts';
import { routeChart } from '../src/lib/charts/routeChart.ts';
import { stopStrip } from '../src/lib/charts/strip.ts';

const { document } = parseHTML('<!doctype html><html><body></body></html>');
const draw = { width: 800, document };
const charts: Record<string, () => Element> = {
	heatmap: () => heatmap(fixtureProfile(), draw),
	'line chart': () => weekLines(fixtureProfile(), draw),
	strip: () => stopStrip(fixtureStops(), 'wk-pm', draw),
	'route chart': () => routeChart(fixtureStops(), draw)
};
const labelled = (svg: Element) => svg.querySelectorAll('g[aria-label]:not([role])');

for (const [name, drawChart] of Object.entries(charts)) {
	test(`${name}: no group without a role keeps its aria-label`, () => {
		const svg = drawChart();
		assert.ok(
			labelled(svg).length > 0,
			'Plot labels its groups, so the test has something to remove'
		);
		dropGroupLabels(svg);
		assert.equal(labelled(svg).length, 0);
	});
}

test('a label on the svg itself, or on a group with a role, stays', () => {
	const svg = heatmap(fixtureProfile(), draw);
	svg.setAttribute('aria-label', 'Heatmap of median delay');
	const group = svg.querySelector('g[aria-label]')!;
	group.setAttribute('role', 'img');
	const name = group.getAttribute('aria-label');
	dropGroupLabels(svg);
	assert.equal(svg.getAttribute('aria-label'), 'Heatmap of median delay');
	assert.equal(group.getAttribute('aria-label'), name);
});

test('the heatmap still finds every cell once its labels are gone', () => {
	const svg = heatmap(fixtureProfile(), draw);
	dropGroupLabels(svg);
	// The profile has 168 entries and gaps, so the three cell marks hold 168 rects
	// between them, whether the hour is measured, too thin or absent.
	assert.equal(svg.querySelectorAll(`g.${CELL_CLASS} > rect`).length, 168);
	const hours = [...svg.querySelectorAll(`g.${CELL_CLASS} > rect`)].map((rect) =>
		Number(rect.getAttribute('data-hour'))
	);
	assert.deepEqual(
		hours.sort((a, b) => a - b),
		Array.from({ length: 168 }, (_, h) => h)
	);
	selectHour(svg, 100);
	assert.equal(svg.querySelectorAll('.howlate-selected').length, 1);
});
