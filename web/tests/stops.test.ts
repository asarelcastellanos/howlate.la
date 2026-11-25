import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
	loadStops,
	nearestStop,
	searchStops,
	stopsInDirection,
	toStops,
	type Stop
} from '../src/lib/commute/stops.ts';

const ROWS: [string | number, string, number, number][] = [
	['100', 'Wilshire / Vermont', 34.0617, -118.2915],
	['101', 'Wilshire / Vermont Station', 34.0619, -118.2917],
	['102', 'Wilshire / Western', 34.0617, -118.3092],
	['103', 'Vermont / Wilshire', 34.0615, -118.2913],
	['104', 'Cañon Dr / Wilshire Bl', 34.0674, -118.4001],
	['105', 'Santa Monica / Vermont', 34.0905, -118.2915],
	[106, 'Venice / Vermont', 34.0272, -118.2915]
];
const STOPS: Stop[] = toStops(ROWS);
const ids = (list: Stop[]) => list.map((s) => s.id);

test('finds a stop by part of its name, tolerant of case, punctuation and spacing', () => {
	for (const q of [
		'Wilshire / Vermont',
		'wilshire/vermont',
		'WILSHIRE  VERMONT',
		'wilshire, vermont'
	]) {
		assert.deepEqual(ids(searchStops(STOPS, q)).slice(0, 2), ['100', '101'], q);
	}
});

test('matches word starts and ignores accents', () => {
	assert.deepEqual(ids(searchStops(STOPS, 'canon')), ['104']);
	assert.deepEqual(ids(searchStops(STOPS, 'wilsh verm')).slice(0, 2), ['100', '101']);
});

test('ranks an exact name first and the reversed name after the phrase', () => {
	assert.deepEqual(ids(searchStops(STOPS, 'wilshire / vermont')), ['100', '101', '103']);
});

test('an empty or unmatched query returns nothing', () => {
	assert.deepEqual(searchStops(STOPS, '  / '), []);
	assert.deepEqual(searchStops(STOPS, 'zzzz'), []);
});

test('numeric stop ids become strings', () => {
	assert.equal(STOPS[6].id, '106');
});

test('nearest stop is the closest one, and none when all are far', () => {
	assert.equal(nearestStop(STOPS, 34.0905, -118.2916)?.id, '105');
	assert.equal(nearestStop(STOPS, 40.7128, -74.006), undefined);
	assert.equal(nearestStop([], 34, -118), undefined);
});

test('nearest stop searches only the stops it is given', () => {
	const east = stopsInDirection(STOPS, ['102', '104']);
	assert.equal(nearestStop(east, 34.0617, -118.2915)?.id, '102');
});

test('a stop in one direction file is not offered in the other', () => {
	const outbound = ['100', '102', '105'];
	const inbound = ['106', '102', '100'];
	const north = stopsInDirection(STOPS, outbound);
	const south = stopsInDirection(STOPS, inbound);
	assert.deepEqual(ids(north), outbound);
	assert.ok(!ids(south).includes('105'));
	assert.ok(!ids(north).includes('106'));
	assert.deepEqual(ids(searchStops(south, 'santa monica')), []);
	assert.deepEqual(ids(searchStops(north, 'santa monica')), ['105']);
});

test('stopsInDirection skips unknown ids and repeats', () => {
	assert.deepEqual(ids(stopsInDirection(STOPS, ['100', '999', '100', '102'])), ['100', '102']);
});

const BASE = 'https://data.example';
const PREFIX = 'site/runs/20261124T100000Z-a1b2c3/';

function stubFetch(stopsBody: unknown, stopsStatus = 200): typeof fetch {
	return (async (url: string) => {
		if (url === `${BASE}/site/current.json`) {
			return Response.json({ run: 'r', prefix: PREFIX, files: 1, previous: [] });
		}
		if (url === `${BASE}/${PREFIX}commute/stops.json`) {
			return new Response(JSON.stringify(stopsBody), { status: stopsStatus });
		}
		return new Response('', { status: 404 });
	}) as typeof fetch;
}

test('loadStops reads commute/stops.json from the current run', async () => {
	const result = await loadStops(`${BASE}/`, stubFetch(ROWS));
	assert.ok(result.ok);
	assert.equal(result.data.length, ROWS.length);
	assert.deepEqual(result.data[0], {
		id: '100',
		name: 'Wilshire / Vermont',
		lat: 34.0617,
		lon: -118.2915
	});
});

test('loadStops returns an error value for a bad shape and a missing file', async () => {
	const bad = await loadStops(BASE, stubFetch([['100', 'x']]));
	assert.ok(!bad.ok && bad.error.kind === 'shape');
	const missing = await loadStops(BASE, stubFetch([], 404));
	assert.ok(!missing.ok && missing.error.kind === 'status');
});
