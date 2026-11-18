// The title and description of a line page, and the committed list that gives the
// build its line ids.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { LINE_LIST } from '../src/lib/data/lines.ts';
import { DESCRIPTION_LENGTH } from '../src/lib/head.ts';
import {
	GENERIC_LINE_DESCRIPTION,
	findListed,
	isLineList,
	lineHead,
	toListEntry
} from '../src/lib/lineHead.ts';
import type { IndexEntry } from '../src/lib/data/types.ts';

const bus = {
	line: '720',
	label: '720',
	mode: 'bus',
	to: ['Santa Monica'],
	via: 'Wilshire'
} as const;

test('a bus line names its end and its corridor', () => {
	assert.deepEqual(lineHead(bus, '720'), {
		title: 'Line 720',
		description:
			'Line 720 (bus line to Santa Monica, Wilshire): how late it runs by hour of the week and by stop, against the timetable.'
	});
});

test('a line with no corridor text leaves the corridor out', () => {
	const head = lineHead({ ...bus, via: '' }, '720');
	assert.equal(
		head.description,
		'Line 720 (bus line to Santa Monica): how late it runs by hour of the week and by stop, against the timetable.'
	);
});

test('both ends are joined, and a pair label keeps its slash', () => {
	const head = lineHead(
		{ line: '10', label: '10/48', mode: 'bus', to: ['Avalon Station', 'West Hollywood'], via: '' },
		'10'
	);
	assert.equal(head.title, 'Line 10/48');
	assert.match(
		head.description,
		/^Line 10\/48 \(bus line to Avalon Station and West Hollywood\): /
	);
});

test('a corridor too long for the description is dropped and both ends stay', () => {
	const head = lineHead(
		{ ...bus, to: ['Santa Monica', 'Downtown LA'], via: 'W'.repeat(100) },
		'720'
	);
	assert.equal(
		head.description,
		'Line 720 (bus line to Santa Monica and Downtown LA): how late it runs by hour of the week and by stop, against the timetable.'
	);
});

test('ends too long for the description fall back to the first end, then to the mode alone', () => {
	const ends = ['Downtown Inglewood K Line Station', 'Redondo Beach Transit Center'];
	assert.equal(
		lineHead({ ...bus, to: ends, via: '' }, '720').description,
		'Line 720 (bus line to Downtown Inglewood K Line Station): how late it runs by hour of the week and by stop, against the timetable.'
	);
	const huge = ['A'.repeat(90), 'B'.repeat(90)];
	assert.equal(
		lineHead({ ...bus, to: huge, via: '' }, '720').description,
		'Line 720 (bus line): how late it runs by hour of the week and by stop, against the timetable.'
	);
});

test('a label that is a sentence is cut at a word and still fits', () => {
	const label =
		'The Express Shuttle Will Operate Between The Metro LAX Transit Center And SoFi Stadium On Event Days Only';
	const { title, description } = lineHead(
		{ line: '697', label, mode: 'bus', to: ['SoFi Stadium'], via: '' },
		'697'
	);
	assert.equal(title, label);
	assert.equal(
		description,
		'The Express Shuttle Will Operate Between The Metro LAX Transit Center And…' +
			' (bus line): how late it runs by hour of the week and by stop, against the timetable.'
	);
	assert.ok(description.length <= DESCRIPTION_LENGTH.max);
});

test('a rail line says rail line, keeps its own name, and says nothing about on-time share', () => {
	const head = lineHead(
		{
			line: '801',
			label: 'Metro A Line',
			mode: 'rail',
			to: ['Pomona Station', 'Downtown Long Beach Station'],
			via: ''
		},
		'801'
	);
	assert.equal(head.title, 'Metro A Line');
	assert.equal(
		head.description,
		'Metro A Line (rail line to Pomona Station and Downtown Long Beach Station): how late it runs by hour of the week and by stop, against the timetable.'
	);
	assert.doesNotMatch(head.description, /on.time/i);
});

test('an id that is not in the list gets the generic head', () => {
	assert.deepEqual(lineHead(undefined, 'zzz'), {
		title: 'Line zzz',
		description:
			'How late this LA Metro line runs by hour of the week and by stop, measured against the timetable.'
	});
	assert.equal(lineHead(undefined, 'zzz').description, GENERIC_LINE_DESCRIPTION);
});

test('findListed matches on the id and returns nothing for a stranger', () => {
	assert.equal(findListed([bus], '720'), bus);
	assert.equal(findListed([bus], '72'), undefined);
});

test('toListEntry keeps five fields and drops every metric', () => {
	const entry: IndexEntry = {
		line: '801',
		agency: 'LACMTA_Rail',
		label: 'Metro A Line',
		via: '',
		mode: 'rail',
		n: 762089,
		sched: 909287,
		med: 88,
		p90: 614,
		pct5: 24.4,
		ontime: 56.4,
		to: ['Pomona Station', 'Downtown Long Beach Station']
	};
	assert.deepEqual(toListEntry(entry), {
		line: '801',
		label: 'Metro A Line',
		mode: 'rail',
		to: ['Pomona Station', 'Downtown Long Beach Station'],
		via: ''
	});
});

test('isLineList rejects an entry with a wrong field', () => {
	assert.equal(isLineList([bus]), true);
	assert.equal(isLineList([{ ...bus, mode: 'ferry' }]), false);
	assert.equal(isLineList([{ ...bus, to: 'Santa Monica' }]), false);
	assert.equal(isLineList([{ line: '720' }]), false);
	assert.equal(isLineList({}), false);
});

// 115 lines in the 2026-11-17 index. Run `npm run lines:refresh` after Metro adds one.
test('every line in lines.json has a unique id and a unique description of 40 to 160 characters', () => {
	assert.ok(LINE_LIST.length >= 100, `${LINE_LIST.length} lines`);
	const ids = LINE_LIST.map((entry) => entry.line);
	assert.equal(new Set(ids).size, ids.length, 'ids repeat');
	assert.ok(ids.includes('720'));
	assert.ok(ids.includes('801'));

	const descriptions = new Set<string>();
	for (const entry of LINE_LIST) {
		const { title, description } = lineHead(entry, entry.line);
		assert.ok(title.length > 0, entry.line);
		assert.ok(
			description.length >= DESCRIPTION_LENGTH.min && description.length <= DESCRIPTION_LENGTH.max,
			`${entry.line}: ${description.length} characters`
		);
		descriptions.add(description);
	}
	assert.equal(descriptions.size, LINE_LIST.length, 'two lines share a description');
});

test('lines.json holds only the five fields the head reads', () => {
	for (const entry of LINE_LIST) {
		assert.deepEqual(Object.keys(entry).sort(), ['label', 'line', 'mode', 'to', 'via']);
	}
});

test('rail lines in lines.json are never described with an on-time share', () => {
	const rail = LINE_LIST.filter((entry) => entry.mode === 'rail');
	assert.ok(rail.length > 0);
	for (const entry of rail) {
		const { description } = lineHead(entry, entry.line);
		assert.match(description, /\(rail line/, entry.line);
		assert.doesNotMatch(description, /on.time|percent|%/i, entry.line);
	}
});
