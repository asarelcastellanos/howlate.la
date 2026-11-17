// The route chart drawn without a browser, on the made-up stops and on the
// real line files in static/data when they are present.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseHTML } from 'linkedom';
import { render } from 'svelte/server';
import { fixtureStops } from '../src/lib/charts/fixtures.ts';
import RouteChart from '../src/lib/charts/RouteChart.svelte';
import {
	routeChart,
	routeChartLabel,
	routeStops,
	worstStops
} from '../src/lib/charts/routeChart.ts';
import { MIN_ARRIVALS, delayLabel } from '../src/lib/charts/theme.ts';
import type { Stop } from '../src/lib/data/types.ts';
import { hasRealData, realLines } from './realData.ts';
import { collisions, textBoxes } from './svgText.ts';

const { document } = parseHTML('<!doctype html><html><body></body></html>');
const draw = { width: 800, document };
const unmeasured = (stop: Stop): Stop => ({
	...stop,
	n: 0,
	all: { med: null, p90: null, pct5: null, ontime: null }
});
const shuffled = (stops: Stop[]) =>
	[...stops].sort((a, b) => ((a.seq * 7919) % 13) - ((b.seq * 7919) % 13));
const trustedMed = (stop: Stop) => stop.n >= MIN_ARRIVALS && stop.all.med !== null;

// The independent version of the rule, for the tests to compare against.
const threeWorst = (stops: Stop[]) =>
	stops
		.filter((stop) => trustedMed(stop) && stop.all.med! > 0)
		.sort((a, b) => b.all.med! - a.all.med! || a.seq - b.seq)
		.slice(0, 3)
		.map((stop) => stop.id);

const medianPath = (svg: Element) =>
	[...svg.querySelectorAll('g[aria-label="line"]')]
		.find((g) => g.getAttribute('stroke') === 'var(--chart-ink)')!
		.children[0].getAttribute('d')!;
const vertices = (d: string) =>
	[...d.matchAll(/([ML])(-?[\d.e+-]+),(-?[\d.e+-]+)/g)].map((m) => ({
		start: m[1] === 'M',
		x: Number(m[2]),
		y: Number(m[3])
	}));
const xScale = (svg: Element) =>
	(svg as unknown as { scale(name: 'x'): { apply(v: number): number } }).scale('x');

test('stops are drawn in seq order, whatever order the file lists them in', () => {
	const stops = fixtureStops();
	assert.deepEqual(
		routeStops(shuffled(stops)).map((s) => s.seq),
		stops.map((s) => s.seq)
	);
	// Equal spacing: the vertices of the median line are evenly spaced in x.
	const reversed = [...stops].reverse().map((s) => ({ ...s, n: 400 }));
	const xs = vertices(medianPath(routeChart(reversed, draw))).map((v) => v.x);
	assert.equal(xs.length, stops.length);
	const step = xs[1] - xs[0];
	assert.ok(step > 0);
	for (let i = 1; i < xs.length; i++) assert.ok(Math.abs(xs[i] - xs[i - 1] - step) < 0.01);
	// The ends read in route order too.
	const boxes = textBoxes(routeChart(reversed, draw));
	const at = (name: string) => boxes.find((b) => b.text === name)!;
	assert.ok(at('Example Station 1').left < at('Example Station 36').left);
});

test('a stop with no measured median breaks the line and is never drawn at zero', () => {
	const stops = fixtureStops()
		.map((stop) => ({ ...stop, n: 400 }))
		.map((stop, i) => (i === 10 || i === 11 || i === 20 ? unmeasured(stop) : stop));
	const svg = routeChart(stops, draw);
	const path = vertices(medianPath(svg));
	assert.equal(path.length, stops.length - 3);
	assert.equal(path.filter((v) => v.start).length, 3);
	const x = xScale(svg);
	for (const i of [10, 11, 20]) {
		assert.ok(
			path.every((v) => Math.abs(v.x - x.apply(i)) > 0.01),
			`stop ${i} has no vertex`
		);
	}
});

test('a stop with too few arrivals breaks the line like an unmeasured one', () => {
	const stops = fixtureStops();
	const thin = stops.filter((s) => s.n < MIN_ARRIVALS);
	assert.ok(thin.length >= 3);
	const path = vertices(medianPath(routeChart(stops, draw)));
	assert.equal(path.length, stops.length - thin.length);
	assert.equal(path.filter((v) => v.start).length, thin.length + 1);
});

test('a lone measured stop between gaps still shows as a dot', () => {
	const stops = fixtureStops()
		.map((s) => ({ ...s, n: 400 }))
		.map((s, i) => (i === 14 || i === 16 ? unmeasured(s) : s));
	const solid = [...routeChart(stops, draw).querySelectorAll('g[aria-label="dot"] > *')];
	// One dot for the lone stop and one for each labelled stop.
	assert.equal(solid.length, 1 + worstStops(stops).length);
});

test('the labelled stops are the three highest medians among trusted stops', () => {
	const stops = fixtureStops();
	// A thin stop with the biggest median of all, and a stop with no median, never rank.
	const loud = {
		...stops[3],
		id: 'LOUD',
		name: 'Loud Thin Stop',
		n: 3,
		all: { ...stops[3].all, med: 99999 }
	};
	const field = [
		...stops.slice(0, 3),
		loud,
		...stops.slice(4, 30),
		unmeasured(stops[30]),
		...stops.slice(31)
	];
	const want = threeWorst(field);
	assert.equal(want.length, 3);
	assert.ok(!want.includes('LOUD'));
	assert.deepEqual(
		worstStops(shuffled(field)).map((s) => s.id),
		want
	);
	const texts = textBoxes(routeChart(field, draw)).map((b) => b.text);
	for (const stop of field.filter((s) => want.includes(s.id))) {
		assert.ok(texts.includes(stop.name), stop.name);
		assert.ok(texts.includes(delayLabel(stop.all.med!)), stop.name);
	}
	assert.equal(texts.filter((t) => /^\d+ min late$/.test(t)).length, 3);
	assert.ok(!texts.includes('Loud Thin Stop'));
	assert.ok(!texts.includes(field[30].name));
});

test('no stop is called the worst when none ran late', () => {
	const early = fixtureStops().map((s) => ({
		...s,
		n: 400,
		all: { ...s.all, med: -90, p90: -10 }
	}));
	assert.deepEqual(worstStops(early), []);
	assert.match(routeChartLabel(early, 'X'), /No stop ran late\./);
});

test('labels never overlap each other or the axis labels, at phone and desktop width', () => {
	const cases: Record<string, Stop[]> = {
		'36 stops': fixtureStops(),
		// The worst stops sit side by side, so their labels would collide without a second row.
		'worst stops adjacent': fixtureStops().map((s, i) => ({
			...s,
			n: 400,
			all: {
				...s.all,
				med: i >= 20 && i <= 22 ? 900 + i : 60,
				p90: i >= 20 && i <= 22 ? 1500 : 200
			}
		})),
		'one stop': fixtureStops().slice(0, 1),
		'two stops': fixtureStops().slice(0, 2),
		'all early': fixtureStops().map((s) => ({
			...s,
			n: 400,
			all: { ...s.all, med: -120, p90: -30 }
		}))
	};
	for (const [name, stops] of Object.entries(cases)) {
		for (const width of [343, 800]) {
			const boxes = textBoxes(routeChart(stops, { width, document }));
			assert.deepEqual(collisions(boxes), [], `${name} at ${width}`);
			for (const b of boxes)
				assert.ok(b.left >= 0 && b.right <= width, `${name} at ${width}: "${b.text}"`);
		}
	}
});

test('the zero line is labelled on time', () => {
	const svg = routeChart(fixtureStops(), draw);
	assert.ok(textBoxes(svg).some((b) => b.text === 'on time'));
	// The zero line stays in the plot when every stop runs late.
	const late = fixtureStops().map((s) => ({ ...s, n: 400, all: { ...s.all, med: 600, p90: 900 } }));
	assert.ok(textBoxes(routeChart(late, draw)).some((b) => b.text === 'on time'));
});

test('the label states the worst stop, the ends and the count', () => {
	const stops = fixtureStops();
	const worst = stops.find((s) => s.id === threeWorst(stops)[0])!;
	const label = routeChartLabel(stops, 'Example Station 36');
	assert.match(label, /36 stops/);
	assert.ok(label.includes(`${worst.name}, at ${delayLabel(worst.all.med!)}`));
	assert.ok(label.includes('Example Station 1'));
	assert.ok(label.includes('Example Station 36'));
	assert.match(label, /toward Example Station 36/);
	assert.doesNotMatch(label, /[—–]/);
});

test('every stop is in the hidden table with its median and 90th percentile', () => {
	const stops = fixtureStops();
	const field = [unmeasured(stops[0]), ...stops.slice(1)];
	const { body } = render(RouteChart, {
		props: { stops: field, to: 'X', caption: 'c', source: 's' }
	});
	assert.equal(body.match(/<tr>/g)?.length, stops.length + 1);
	assert.match(body, /<th scope="col">90th percentile \(minutes\)<\/th>/);
	assert.match(body, /not measured/);
	assert.match(body, /too few arrivals: 3 of 5 needed/);
	assert.match(body, /Gaps are stops with too few arrivals or none measured\./);
	const row = (s: Stop) => `<th scope="row">${s.name}</th>`;
	assert.ok(body.includes(row(stops[35])));
	assert.match(
		body,
		new RegExp(`${row(stops[35])}\\s*<td>${(stops[35].all.med! / 60).toFixed(1)}</td>`)
	);
});

test('an unmeasured route renders the empty message, not a chart', () => {
	const stops = fixtureStops().map(unmeasured);
	const { body } = render(RouteChart, { props: { stops, to: 'X', caption: 'c', source: 's' } });
	assert.match(body, /Not enough measured arrivals yet\./);
	assert.doesNotMatch(body, /<table/);
});

test(
	'real lines draw in seq order with the three worst stops labelled and nothing colliding',
	{ skip: !hasRealData },
	() => {
		const lines = realLines();
		assert.ok(lines.size >= 100, `${lines.size} lines`);
		for (const [id, line] of lines) {
			for (const direction of line.directions) {
				const stops = direction.stops;
				const sorted = routeStops(stops);
				assert.ok(
					sorted.every((s, i) => i === 0 || sorted[i - 1].seq <= s.seq),
					`${id} seq order`
				);
				assert.deepEqual(
					worstStops(stops).map((s) => s.id),
					threeWorst(stops),
					`${id} worst`
				);
				for (const width of [343, 800]) {
					const svg = routeChart(stops, { width, document });
					assert.deepEqual(collisions(textBoxes(svg)), [], `${id} at ${width}`);
					const measured = sorted.filter(trustedMed).length;
					assert.equal(vertices(medianPath(svg)).length, measured, `${id} line vertices`);
				}
			}
		}
	}
);

test('the 720 toward Santa Monica labels its real worst stops', { skip: !hasRealData }, () => {
	const stops = realLines().get('720')!.directions[1].stops;
	const names = stops.filter((s) => threeWorst(stops).includes(s.id)).map((s) => s.name);
	const text = routeChart(stops, draw).textContent!;
	for (const name of names) assert.ok(text.includes(name), name);
});
