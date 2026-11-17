// The line page's helpers, and the page rendered on the server. Fixtures are
// built from the generated types. The components import $app/paths and
// $app/navigation, which exist only inside SvelteKit, so small stand-ins are
// registered first.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { test } from 'node:test';
import { createRawSnippet } from 'svelte';
import { render } from 'svelte/server';
import { fixtureProfile, fixtureStops } from '../src/lib/charts/fixtures.ts';
import type { Direction, LineFile } from '../src/lib/data/types.ts';
import { longDate } from '../src/lib/date.ts';
import {
	RAIL_HOLD_NOTE,
	bulletProps,
	delayWords,
	findEntry,
	hasDirectionSwitch,
	headline,
	lineName,
	lineResult,
	pageDescription,
	shortVia,
	showsOntime
} from '../src/lib/linePage.ts';

registerHooks({
	resolve(specifier, context, nextResolve) {
		const stubs: Record<string, string> = {
			'$app/paths':
				'export const resolve = (path, params) => path.replace(/\\[(\\w+)\\]/g, (_, k) => params[k]);',
			'$app/navigation': 'export const goto = () => Promise.resolve();',
			'$app/state':
				"export const page = { params: { line: '720' }, route: { id: '/lines/[line]' } };",
			'$app/env/public': "export const PUBLIC_DATA_BASE = '/data';"
		};
		if (!(specifier in stubs)) return nextResolve(specifier, context);
		return {
			url: `data:text/javascript,${encodeURIComponent(stubs[specifier])}`,
			shortCircuit: true
		};
	}
});

// A static import would load the page before the stand-ins are registered.
const { default: LineView } = await import('../src/lib/line/LineView.svelte');
const { default: LineNotFound } = await import('../src/lib/line/LineNotFound.svelte');
const { default: LineRoute } = await import('../src/routes/lines/[line]/+page.svelte');
const { default: ResultView } = await import('../src/lib/charts/ResultView.svelte');

const direction = (id: 0 | 1, to: string, all: Partial<Direction['all']> = {}): Direction => ({
	id,
	to,
	n: 345_123,
	sched: 400_000,
	all: { n: 345_123, med: 55, p90: 479, pct5: 19.3, ontime: 56.5, ...all },
	profile: fixtureProfile() as Direction['profile'],
	stops: fixtureStops() as Direction['stops']
});
const lineFile = (mode: 'bus' | 'rail', directions: LineFile['directions']): LineFile => ({
	line: mode === 'rail' ? '801' : '720',
	agency: mode === 'rail' ? 'LACMTA_Rail' : 'LACMTA',
	label: mode === 'rail' ? 'Metro A Line' : '720',
	via: mode === 'rail' ? '' : 'Santa Monica-Downtown LA via Wilshire Blvd',
	mode,
	first_day: '2026-08-18',
	last_day: '2026-11-15',
	days: 90,
	directions
});
const two = [direction(0, 'Downtown LA'), direction(1, 'Santa Monica')] as LineFile['directions'];
const one = [direction(0, 'Downtown LA')] as LineFile['directions'];
const text = (html: string) =>
	html
		.replace(/<!--.*?-->/g, '')
		.replace(/<[^>]+>/g, ' ')
		.replace(/\s+/g, ' ');

test('delays read in words, in seconds under two minutes', () => {
	assert.equal(delayWords(0), 'on time');
	assert.equal(delayWords(1), '1 second late');
	assert.equal(delayWords(-88), '88 seconds early');
	assert.equal(delayWords(119), '119 seconds late');
	assert.equal(delayWords(120), '2 minutes late');
	assert.equal(delayWords(614), '10 minutes late');
	assert.equal(delayWords(-3600), '60 minutes early');
});

test('a bus headline has the median, the 90th percentile, the count and the on-time share', () => {
	assert.equal(
		headline(direction(0, 'Santa Monica'), 0, 'bus'),
		'Toward Santa Monica, the median arrival is 55 seconds late and the 90th percentile is 8 minutes late, and 56.5 percent of 345,123 measured arrivals were on time.'
	);
});

test('a direction with no name and one arrival still reads as a sentence', () => {
	const sentence = headline(direction(1, '', { n: 1, med: -30, p90: 0, ontime: 100 }), 1, 'bus');
	assert.equal(
		sentence,
		'Direction 2, the median arrival is 30 seconds early and the 90th percentile is on time, and 100.0 percent of 1 measured arrival were on time.'
	);
});

test('the rail gate hides the on-time share when it is off and shows it when it is on', () => {
	const rail = direction(0, 'Pomona Station');
	assert.equal(showsOntime('rail'), false);
	assert.equal(showsOntime('rail', true), true);
	assert.equal(showsOntime('bus'), true);
	assert.doesNotMatch(headline(rail, 0, 'rail'), /on time|percent of/);
	assert.match(headline(rail, 0, 'rail'), /across 345,123 measured arrivals\.$/);
	assert.match(
		headline(rail, 0, 'rail', true),
		/56\.5 percent of 345,123 measured arrivals were on time\.$/
	);
});

test('a bus page shows the on-time share, its window and the small print', () => {
	const page = text(render(LineView, { props: { line: lineFile('bus', two) } }).body);
	assert.match(page, /56\.5 percent of 345,123 measured arrivals were on time/);
	assert.match(page, /On time means 1 minute early to 5 minutes late, at every stop\./);
	assert.match(page, /Not Metro's published figure\./);
	assert.ok(!page.includes(RAIL_HOLD_NOTE));
});

test('a rail page holds the on-time share back and says why', () => {
	const page = text(render(LineView, { props: { line: lineFile('rail', two) } }).body);
	assert.ok(page.includes(RAIL_HOLD_NOTE));
	assert.match(page, /the 90th percentile is 8 minutes late, across 345,123 measured arrivals\./);
	assert.doesNotMatch(page, /percent of|on time means|Not Metro's published/i);
});

test('a rail page shows the share once the gate is open', () => {
	const props = { line: lineFile('rail', two), showRailOntime: true };
	const page = text(render(LineView, { props }).body);
	assert.ok(!page.includes(RAIL_HOLD_NOTE));
	assert.match(page, /56\.5 percent of 345,123 measured arrivals were on time/);
});

test('a line page has four figures, and the route chart is the last one', () => {
	const { body } = render(LineView, { props: { line: lineFile('bus', two) } });
	assert.equal(body.match(/<figure/g)?.length, 4);
	const captions = [...body.matchAll(/<figcaption[\s\S]*?<\/figcaption>/g)].map((m) => text(m[0]));
	assert.match(
		captions[3],
		/^ Median delay at each stop in route order, Route 720 toward Downtown LA\. Stops are evenly spaced, not to distance\./
	);
	// The one-direction case draws the same four, without the switch.
	assert.equal(
		render(LineView, { props: { line: lineFile('bus', one) } }).body.match(/<figure/g)?.length,
		4
	);
});

test('a rail page hands the heatmap no on-time share and a bus page does', () => {
	const readout = (line: LineFile) =>
		text(render(LineView, { props: { line } }).body).match(
			/Friday 5 pm\. Median[^.]*\.[^.]*\.[^.]*\./
		)?.[0];
	assert.match(readout(lineFile('bus', two))!, /percent on time/);
	assert.doesNotMatch(readout(lineFile('rail', two))!, /percent on time/);
});

test('two directions get a switch and one direction does not', () => {
	assert.equal(hasDirectionSwitch(lineFile('bus', two)), true);
	assert.equal(hasDirectionSwitch(lineFile('bus', one)), false);
	const radios = (line: LineFile) =>
		render(LineView, { props: { line } }).body.match(/type="radio"/g)?.length ?? 0;
	assert.equal(radios(lineFile('bus', two)), 2);
	assert.equal(radios(lineFile('bus', one)), 0);
});

test('the page has one h1 and names the line in its title and description', () => {
	const { head, body } = render(LineView, { props: { line: lineFile('bus', two) } });
	assert.equal(body.match(/<h1[\s>]/g)?.length, 1);
	assert.match(head, /<title>Route 720 · HowLate<\/title>/);
	assert.match(head, /<meta name="description" content="How late Route 720 runs/);
	assert.doesNotMatch(head + body, /[—–]/);
});

test('names and bullets follow the index', () => {
	assert.equal(lineName({ label: '10/48', mode: 'bus' }), 'Route 10/48');
	assert.equal(lineName({ label: 'SoFi Stadium Express', mode: 'bus' }), 'SoFi Stadium Express');
	assert.deepEqual(bulletProps({ line: '801', label: 'Metro A Line', mode: 'rail' }), {
		line: 'a'
	});
	assert.deepEqual(bulletProps({ line: '901', label: '901', mode: 'bus' }), { line: 'g' });
	assert.deepEqual(bulletProps({ line: '720', label: '720', mode: 'bus' }), {
		service: 'rapid',
		route: '720'
	});
	assert.deepEqual(bulletProps({ line: '697', label: 'LAX / Metro Transit Center', mode: 'bus' }), {
		service: undefined,
		route: '697'
	});
});

test('a service day reads as a date in UTC, whatever the time zone', () => {
	assert.equal(longDate('2026-11-15'), 'November 15, 2026');
	assert.equal(longDate('2026-01-01'), 'January 1, 2026');
});

test('a long via note is cut at its first sentence', () => {
	const note =
		'The Express Shuttle Will Operate Between A And B. Shuttle Service Will Run Every 5 Minutes.';
	assert.equal(shortVia(note, 60), 'The Express Shuttle Will Operate Between A And B.');
	assert.equal(shortVia('Short note'), 'Short note');
	assert.match(shortVia('x'.repeat(300)), /^x{120}…$/);
});

test('an id the index lacks is not found, and a 404 line file is not found', () => {
	const index = { first_day: '', last_day: '', days: 90, lines: [{ line: '720' }] } as never;
	assert.equal(findEntry(index, '720')?.line, '720');
	assert.equal(findEntry(index, 'zzz'), undefined);
	assert.equal(findEntry(index, '72'), undefined);
	const url = 'x/lines/720.json';
	assert.deepEqual(lineResult({ ok: false, error: { kind: 'status', url, status: 404 } }), {
		ok: true,
		data: { kind: 'missing' }
	});
});

test('a broken line file is an error, never a missing line', () => {
	const url = 'x/lines/720.json';
	for (const error of [
		{ kind: 'status', url, status: 500 },
		{ kind: 'status', url, status: 403 },
		{ kind: 'network', url },
		{ kind: 'json', url }
	] as const) {
		assert.deepEqual(lineResult({ ok: false, error }), { ok: false, error });
	}
	const file = lineFile('bus', one);
	assert.deepEqual(lineResult({ ok: true, data: file }), {
		ok: true,
		data: { kind: 'found', line: file }
	});
});

test('every state of the line page has exactly one h1', () => {
	const h1s = (html: string) => html.match(/<h1[\s>]/g)?.length ?? 0;
	// The route renders on the server before any data arrives, so this is the loading state.
	const loading = render(LineRoute).body;
	assert.equal(h1s(loading), 1);
	assert.match(text(loading), /Line 720/);
	assert.match(loading, /role="status"/);

	const heading = createRawSnippet(() => ({ render: () => '<h1>Line 720</h1>' }));
	const children = createRawSnippet(() => ({ render: () => '<p>data</p>' }));
	const error = { kind: 'network', url: 'x/lines/720.json' } as const;
	const failed = render(ResultView, { props: { result: { ok: false, error }, heading, children } });
	assert.equal(h1s(failed.body), 1);
	assert.match(failed.body, /role="alert"/);

	assert.equal(h1s(render(LineView, { props: { line: lineFile('bus', two) } }).body), 1);
	assert.equal(h1s(render(LineNotFound, { props: { id: 'zzz' } }).body), 1);
});

// head.ts allows 160 characters, and search results cut a longer one. The label
// of line 697 is a sentence, so the description has to fit around any label.
test('a line description is 40 to 160 characters for every label in the fixture index', () => {
	const runs = new URL('../e2e/fixture/site/runs/', import.meta.url);
	const labels = readdirSync(runs).flatMap(
		(run) =>
			(
				JSON.parse(readFileSync(new URL(`${run}/index.json`, runs), 'utf8')) as {
					lines: { label: string; mode: 'bus' | 'rail' }[];
				}
			).lines
	);
	labels.push({ label: 'LAX / Metro Transit Center -  SoFi Stadium Express', mode: 'bus' });
	assert.ok(labels.length >= 8);
	for (const { label, mode } of labels) {
		const text = pageDescription({ label, mode, last_day: '2026-09-30' });
		assert.ok(text.length >= 40 && text.length <= 160, `${label}: ${text.length}`);
		assert.match(text, /^How late /);
		assert.match(text, /Data through September 30, 2026\.$/);
	}
});

test('a short label is kept whole, and a long one is cut at a word with an ellipsis', () => {
	const short = pageDescription({ label: '720', mode: 'bus', last_day: '2026-11-14' });
	assert.ok(short.startsWith('How late Route 720 runs by hour of the week'));
	const long = pageDescription({
		label: 'LAX / Metro Transit Center -  SoFi Stadium Express',
		mode: 'bus',
		last_day: '2026-09-30'
	});
	assert.match(long, /^How late LAX \/ Metro Transit Center - SoFi Stadium… runs by hour/);
	const huge = pageDescription({
		label: 'word '.repeat(60).trim(),
		mode: 'bus',
		last_day: '2026-09-30'
	});
	assert.ok(huge.length <= 160);
	assert.match(huge, /^How late word( word)*… runs by hour of the week/);
});
