// Route files built by hand in the format of pipeline/src/howlate_pipeline/commute.py.
// An entry is a change in 10 second units, and stop A is always the first stop at
// 0 s, so stop B's entry is B's time after the start divided by 10.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { answer, dayTypeFor, pickFile, sentence } from '../src/lib/commute/answer.ts';
import type { CommuteFile, DayType } from '../src/lib/commute/file.ts';

const days = (n: number) =>
	Array.from({ length: n }, (_, i) => `202611${String(i + 1).padStart(2, '0')}`);
const indexes = (n: number) => Array.from({ length: n }, (_, i) => i);

function file(dayType: DayType, n: number, patterns: [number, number[]][]): CommuteFile {
	return {
		line: '4',
		direction: 0,
		dayType,
		days: days(n),
		stops: ['A', 'B'],
		patterns: patterns.map(([start, units]) => ({
			start,
			dayIndexes: indexes(n),
			stopIndexes: [0, 1],
			rows: [units.map(() => 0), units]
		}))
	};
}

const same = (n: number, units: number) => Array<number>(n).fill(units);

// 7:59 = 28740 s, 8:00 = 28800 s, 8:07 = 29220 s. Leave at 8:00 is minute 480.
test('C14 leave at picks the first departure at or after the time', () => {
	const f = file('weekday', 8, [
		[28740, same(8, 60)],
		[28800, same(8, 60)],
		[29220, same(8, 60)]
	]);
	const at800 = answer(f, 'A', 'B', 'leave', 480);
	const at801 = answer(f, 'A', 'B', 'leave', 481);
	assert.equal(at800.kind === 'no-bus' ? null : at800.start, 28800);
	assert.equal(at801.kind === 'no-bus' ? null : at801.start, 29220);
	assert.equal(answer(f, 'A', 'B', 'leave', 488).kind, 'no-bus');
});

// Eight days a pattern, so the 9-in-10 value is the 8th ranked, the latest day.
// Pattern 28800 (8:00): seven days reach B at 3000 s, one at 3600 s, so 9-in-10 is 8:00 + 3600 s = 9:00.
// Pattern 28860 (8:01): the same days, so 9-in-10 is 8:01 + 3600 s = 9:01.
test('C15 arrive by picks the latest departure that arrives in time', () => {
	const units = [...same(7, 300), 360];
	const f = file('weekday', 8, [
		[28800, units],
		[28860, units]
	]);
	const by900 = answer(f, 'A', 'B', 'arrive', 540);
	const by901 = answer(f, 'A', 'B', 'arrive', 541);
	assert.equal(by900.kind === 'no-bus' ? null : by900.start, 28800);
	assert.equal(by901.kind === 'no-bus' ? null : by901.start, 28860);
	assert.equal(answer(f, 'A', 'B', 'arrive', 539).kind, 'no-bus');
});

test('C18 fewer than 8 days reads not enough data and 8 days says 8', () => {
	const seven = answer(file('weekday', 7, [[28800, same(7, 60)]]), 'A', 'B', 'leave', 480);
	assert.equal(seven.kind, 'not-enough-data');
	assert.match(sentence(seven), /^Not enough data/);
	const eight = answer(file('weekday', 8, [[28800, same(8, 60)]]), 'A', 'B', 'leave', 480);
	assert.equal(eight.kind, 'answer');
	assert.equal(eight.kind === 'answer' ? eight.days : 0, 8);
	assert.match(sentence(eight), /This rests on 8 days\./);
});

// 7:42 = 27720 s. Rides: weekday 600 s, Saturday 900 s, Sunday 1200 s.
test('C19 each day type uses its own patterns', () => {
	const files: Record<DayType, CommuteFile> = {
		weekday: file('weekday', 8, [[27720, same(8, 60)]]),
		saturday: file('saturday', 8, [[27720, same(8, 90)]]),
		sunday: file('sunday', 8, [[27720, same(8, 120)]])
	};
	const ride = (choice: string) => {
		const f = pickFile(files, choice);
		assert.ok(f);
		const a = answer(f, 'A', 'B', 'leave', 462);
		return a.kind === 'answer' ? a.rideMinutes : null;
	};
	assert.equal(ride('weekday'), 10);
	assert.equal(ride('saturday'), 15);
	assert.equal(ride('sunday'), 20);
	assert.equal(ride('2026-11-28'), 15);
	assert.equal(ride('2026-11-29'), 20);
	assert.equal(ride('2026-11-30'), 10);
	assert.equal(dayTypeFor('2026-02-30'), null);
});
