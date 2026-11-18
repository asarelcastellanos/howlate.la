// The methods page reads the network-wide shares from the published files, so no
// figure is typed into its copy. Fetch is stubbed, with the shapes in pipeline/schemas.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadShares, sharesText } from '../src/lib/methodsShares.ts';

const BASE = 'https://data.example';
const PREFIX = 'site/runs/20261115T100000Z-a1b2c3/';

const pointer = { run: '20261115T100000Z-a1b2c3', prefix: PREFIX, files: 4, previous: [] };
const status = {
	first_day: '2026-08-18',
	last_day: '2026-11-15',
	days: 90,
	scheduled_stops: 2000,
	measured_arrivals: 1200,
	coverage_pct: 60,
	lines: 114,
	trips: 900
};
const scope = (ontime: number | null) => ({ all: { n: 10, ontime }, profile: [] });
const network = (bus: unknown, rail: unknown) => ({ network: scope(62), bus, rail });

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
function serve(files: Record<string, unknown>) {
	const answers: Record<string, Response> = {
		[`${BASE}/site/current.json`]: json(pointer),
		...Object.fromEntries(
			Object.entries(files).map(([name, body]) => [`${BASE}/${PREFIX}${name}`, json(body)])
		)
	};
	return async (url: string | URL | Request) =>
		answers[String(url)]?.clone() ?? new Response('not found', { status: 404 });
}

test('reads both shares and the days from one run', async () => {
	const fetchFn = serve({
		'network.json': network(scope(60.4), scope(64.4)),
		'status.json': status
	});
	const result = await loadShares(BASE, fetchFn);
	assert.deepEqual(result, {
		ok: true,
		data: { bus: 60.4, rail: 64.4, days: 90, last_day: '2026-11-15' }
	});
});

test('the sentence names both modes, the date and the days, and has no dash', () => {
	const text = sharesText({ bus: 60.4, rail: 64.4, days: 90, last_day: '2026-11-15' });
	assert.equal(
		text,
		'As of November 15, 2026, over 90 days of data, HowLate scored 60.4 percent of measured bus arrivals and 64.4 percent of measured rail arrivals as on time. These shares change every day. Each line page has its own.'
	);
	assert.doesNotMatch(text!, /[—–]/);
});

test('a share under 100 never prints as 100.0', () => {
	const text = sharesText({ bus: 99.96, rail: 100, days: 1, last_day: '2026-11-15' });
	assert.ok(text!.includes('99.9 percent of measured bus'));
	assert.ok(text!.includes('100.0 percent of measured rail'));
});

test('a mode with nothing measured is left out, and no mode gives no sentence', () => {
	const text = sharesText({ bus: 60.4, rail: null, days: 90, last_day: '2026-11-15' });
	assert.ok(text!.includes('60.4 percent of measured bus arrivals as on time'));
	assert.ok(!text!.includes('rail'));
	assert.equal(sharesText({ bus: null, rail: null, days: 0, last_day: '2026-11-15' }), undefined);
});

test('a network file without a share is a shape error, not a throw', async () => {
	for (const bad of [{}, null, { all: {} }, { all: { ontime: 'high' } }]) {
		const fetchFn = serve({ 'network.json': network(scope(60.4), bad), 'status.json': status });
		const result = await loadShares(BASE, fetchFn);
		assert.ok(!result.ok, JSON.stringify(bad));
		assert.equal(!result.ok && result.error.kind, 'shape');
	}
});

test('a missing file or pointer is an error value', async () => {
	const noStatus = serve({ 'network.json': network(scope(60.4), scope(64.4)) });
	const missing = await loadShares(BASE, noStatus);
	assert.ok(!missing.ok && missing.error.kind === 'status');
	const nothing = await loadShares(BASE, async () => new Response('no', { status: 404 }));
	assert.ok(!nothing.ok);
	const offline = await loadShares(BASE, async () => {
		throw new Error('offline');
	});
	assert.ok(!offline.ok && offline.error.kind === 'network');
});

test('a network.json body that is not an object with both scopes is a shape error, not a throw', async () => {
	for (const bad of [null, [], {}, { bus: null }, 5, 'x']) {
		const fetchFn = serve({ 'network.json': bad, 'status.json': status });
		const result = await loadShares(BASE, fetchFn);
		assert.ok(!result.ok, JSON.stringify(bad));
		assert.equal(!result.ok && result.error.kind, 'shape', JSON.stringify(bad));
	}
});

test('with the rail gate closed the sentence names no rail share', () => {
	const shares = { bus: 60.4, rail: 64.4, days: 90, last_day: '2026-11-15' };
	assert.equal(
		sharesText(shares, false),
		'As of November 15, 2026, over 90 days of data, HowLate scored 60.4 percent of measured bus arrivals as on time. These shares change every day. Each line page has its own.'
	);
	assert.doesNotMatch(sharesText(shares, false)!, /rail|64\.4/);
	// A closed gate with no bus share has nothing to say.
	assert.equal(sharesText({ ...shares, bus: null }, false), undefined);
	// The gate defaults to SHOW_RAIL_ONTIME, which is open.
	assert.equal(sharesText(shares), sharesText(shares, true));
	assert.match(sharesText(shares)!, /64\.4 percent of measured rail arrivals/);
});
