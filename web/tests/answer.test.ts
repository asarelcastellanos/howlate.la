// Route files built by hand in the format of pipeline/src/howlate_pipeline/commute.py.
// Times are 10 second units after the pattern's start. A pattern is built from the
// timetable's units at A and at B, and the units each day's bus actually reached B.
// The bus is at A exactly on the timetable.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { answer, dayTypeFor, pickFile, sentence } from '../src/lib/commute/answer.ts';
import type { CommuteFile, DayType } from '../src/lib/commute/file.ts';

const days = (n: number) =>
	Array.from({ length: n }, (_, i) => `202611${String(i + 1).padStart(2, '0')}`);
const indexes = (n: number) => Array.from({ length: n }, (_, i) => i);

type Spec = { start: number; schedA: number; schedB: number; actualB: number[] };

function file(dayType: DayType, n: number, specs: Spec[]): CommuteFile {
	return {
		line: '4',
		direction: 0,
		dayType,
		days: days(n),
		stops: ['A', 'B'],
		patterns: specs.map(({ start, schedA, schedB, actualB }) => ({
			start,
			dayIndexes: indexes(n),
			stopIndexes: [0, 1],
			rows: [same(n, schedA), actualB.map((b) => b - schedA)],
			scheduled: [schedA, schedB - schedA]
		}))
	};
}

function same(n: number, units: number) {
	return Array<number>(n).fill(units);
}

const spec = (start: number, schedA: number, schedB: number, actualB = same(8, schedB)): Spec => ({
	start,
	schedA,
	schedB,
	actualB
});

// Each pattern is timetabled 9 minutes (54 units) after its start at A.
// 28200 + 540 = 28740 s (7:59), 28260 + 540 = 28800 s (8:00), 28680 + 540 = 29220 s (8:07).
// Leave at 8:00 is minute 480.
test('C14 leave at picks the first departure at or after the time', () => {
	const f = file('weekday', 8, [spec(28200, 54, 114), spec(28260, 54, 114), spec(28680, 54, 114)]);
	const at800 = answer(f, 'A', 'B', 'leave', 480);
	const at801 = answer(f, 'A', 'B', 'leave', 481);
	assert.equal(at800.kind === 'no-bus' ? null : at800.start, 28260);
	assert.equal(at801.kind === 'no-bus' ? null : at801.start, 28680);
	assert.equal(answer(f, 'A', 'B', 'leave', 488).kind, 'no-bus');
});

// Eight days a pattern, so the 9-in-10 value is the 8th ranked, the latest day.
// Pattern 28800 (8:00): B is timetabled at 3000 s (300 units). Seven days reach B at 3000 s and
// one at 3600 s (360 units), so 9-in-10 is 8:00 + 3600 s = 9:00, and the worst day is 600 s late.
// Pattern 28860 (8:01): the same days, so 9-in-10 is 8:01 + 3600 s = 9:01.
test('C15 arrive by picks the latest departure that arrives in time', () => {
	const actual = [...same(7, 300), 360];
	const f = file('weekday', 8, [spec(28800, 0, 300, actual), spec(28860, 0, 300, actual)]);
	const by900 = answer(f, 'A', 'B', 'arrive', 540);
	const by901 = answer(f, 'A', 'B', 'arrive', 541);
	assert.equal(by900.kind === 'no-bus' ? null : by900.start, 28800);
	assert.equal(by901.kind === 'no-bus' ? null : by901.start, 28860);
	assert.equal(answer(f, 'A', 'B', 'arrive', 539).kind, 'no-bus');
	assert.equal(by900.kind === 'answer' ? by900.badLateMinutes : null, 10);
	assert.equal(by900.kind === 'answer' ? by900.medianLateMinutes : null, 0);
});

// Timetabled 600 s from A to B, reached in 660 s every day, so it is 1 minute late.
test('C18 fewer than 8 days reads not enough data and 8 days says 8', () => {
	const seven = answer(
		file('weekday', 7, [spec(28800, 0, 60, same(7, 66))]),
		'A',
		'B',
		'leave',
		480
	);
	assert.equal(seven.kind, 'not-enough-data');
	assert.match(sentence(seven), /^Not enough data/);
	const eight = answer(
		file('weekday', 8, [spec(28800, 0, 60, same(8, 66))]),
		'A',
		'B',
		'leave',
		480
	);
	assert.equal(eight.kind, 'answer');
	assert.equal(eight.kind === 'answer' ? eight.days : 0, 8);
	assert.equal(eight.kind === 'answer' ? eight.medianLateMinutes : null, 1);
	assert.match(sentence(eight), /usually 1 minute late/);
	assert.match(sentence(eight), /This rests on 8 days\./);
});

// 7:42 = 27720 s. Rides: weekday 600 s, Saturday 900 s, Sunday 1200 s.
test('C19 each day type uses its own patterns', () => {
	const files: Record<DayType, CommuteFile> = {
		weekday: file('weekday', 8, [spec(27720, 0, 60)]),
		saturday: file('saturday', 8, [spec(27720, 0, 90)]),
		sunday: file('sunday', 8, [spec(27720, 0, 120)])
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
