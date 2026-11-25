// A route file built by hand in the format of pipeline/src/howlate_pipeline/commute.py.
// Entries are 10 second units, each the change from the same day's time at the
// last earlier stop that has one. Times in seconds are worked by hand below.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { decodeCommuteFile } from '../src/lib/commute/file.ts';
import { rideTimes } from '../src/lib/commute/ridetime.ts';

// Pattern 21600 (06:00) runs on days 0 and 1.
//   day 0: S1 60 s (6 units), S2 300 s (6+24=30), S3 600 s (30+30=60)
//   day 1: S1 70 s (7), S2 none, S3 380 s (7+31=38)
// Pattern 25200 (07:00) runs on day 0 only, the same day as the first.
//   day 0: S1 100 s (10), S2 600 s (10+50=60), S3 800 s (60+20=80)
const body = {
	line: '4',
	direction: 0,
	day_type: 'weekday',
	days: ['20261109', '20261110'],
	stops: ['S1', 'S2', 'S3'],
	patterns: [
		[
			21600,
			[0, 1],
			[0, 1, 2],
			[
				[6, 7],
				[24, null],
				[30, 31]
			]
		],
		[25200, [0], [0, 1, 2], [[10], [50], [20]]]
	]
};

const file = decodeCommuteFile(body, { line: '4', direction: 0, dayType: 'weekday' });
assert.ok(file);

test('C7: each ride time comes from one trip, never mixed across trips of a day', () => {
	// Trip 06:00 on day 0: S3 600 - S1 60 = 540. On day 1: 380 - 70 = 310.
	assert.deepEqual(rideTimes(file, 21600, 'S1', 'S3'), {
		ok: true,
		data: [
			{ day: '20261109', seconds: 540 },
			{ day: '20261110', seconds: 310 }
		]
	});
	// Trip 07:00 on day 0: 800 - 100 = 700. Mixing the trips would give 740 or 500.
	assert.deepEqual(rideTimes(file, 25200, 'S1', 'S3'), {
		ok: true,
		data: [{ day: '20261109', seconds: 700 }]
	});
});

test('C7: a day with no time at either stop is skipped', () => {
	// Day 1 has no time at S2, so only day 0 remains: 300 - 60 = 240.
	assert.deepEqual(rideTimes(file, 21600, 'S1', 'S2'), {
		ok: true,
		data: [{ day: '20261109', seconds: 240 }]
	});
});

test('C8: a "to" stop before the "from" stop is refused', () => {
	assert.deepEqual(rideTimes(file, 21600, 'S3', 'S1'), {
		ok: false,
		error: { kind: 'to-not-after-from' }
	});
	assert.deepEqual(rideTimes(file, 21600, 'S2', 'S1'), {
		ok: false,
		error: { kind: 'to-not-after-from' }
	});
	assert.deepEqual(rideTimes(file, 21600, 'S2', 'S2'), {
		ok: false,
		error: { kind: 'to-not-after-from' }
	});
});
