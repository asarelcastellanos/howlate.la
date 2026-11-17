// searchLines over entries copied from the real index.json (90 days to
// 2026-11-15). Only the fields the search reads are kept.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { IndexEntry } from '../src/lib/data/types.ts';
import { moveActive, searchLines } from '../src/lib/search.ts';

const entry = (
	line: string,
	label: string,
	via: string,
	to: [string, string],
	mode: 'bus' | 'rail' = 'bus'
): IndexEntry => ({
	line,
	label,
	via,
	to,
	mode,
	agency: mode === 'rail' ? 'LACMTA_Rail' : 'LACMTA',
	n: 1000,
	sched: 1200,
	med: 60,
	p90: 400,
	pct5: 15,
	ontime: 60
});

const INDEX: IndexEntry[] = [
	entry('2', '2', 'Westwood - Exposition Park via Sunset-Alvarado', [
		'Expo Park / USC Station',
		'Westwood / UCLA'
	]),
	entry('4', '4', 'Downtown LA - Santa Monica via Santa Monica Bl', [
		'Downtown LA - Broadway - Venice',
		'Santa Monica'
	]),
	entry('10', '10/48', 'W Hollywood-Dtwn LA -Avalon Sta via Melrose-Avalon', [
		'Avalon Station',
		'West Hollywood'
	]),
	entry('70', '70', 'Downtown LA - El Monte via Cesar Chavez-Garvey Avs', [
		'El Monte Station',
		'Downtown LA - Grand - Venice'
	]),
	entry('209', '209', 'Expo/Crenshaw Sta- Gardena via Arlngtn - Van Ness', [
		'Expo / Crenshaw Station',
		'Crenshaw - Rosecrans'
	]),
	entry('550', '550', 'Jefferson Prk - Harbor Gatwy Tc via Harbr Trans Wy', [
		'Expo Park / USC Station',
		'Harbor Gateway Transit Center'
	]),
	entry('720', '720', 'Santa Monica-Downtown LA via Wilshire Blvd', [
		'Downtown LA - 6th - Central',
		'Santa Monica (Rapid)'
	]),
	entry('754', '754', 'Hollywood - Athens via Vermont Av', [
		'Vermont / Sunset Station',
		'Vermont / Athens Station'
	]),
	entry('901', '901', 'Metro G Line', [
		'North Hollywood Station G Line',
		'Chatsworth Station / G Line'
	]),
	entry('801', 'Metro A Line', '', ['Pomona Station', 'Downtown Long Beach Station'], 'rail'),
	entry('804', 'Metro E Line', '', ['Atlantic Station', 'Downtown Santa Monica Station'], 'rail'),
	entry('807', 'Metro K Line', '', ['Expo / Crenshaw Station', 'Redondo Beach Station'], 'rail')
];
const ids = (query: string) => searchLines(INDEX, query).map((e) => e.line);

test('"720" finds the 720 first', () => {
	assert.deepEqual(ids('720'), ['720']);
});

test('"720 rapid" finds the 720 first', () => {
	assert.equal(ids('720 rapid')[0], '720');
});

test('"rapid" finds the 7xx lines and no local line', () => {
	assert.deepEqual(ids('rapid'), ['720', '754']);
});

test('"rapid", "express" and "limited" use the service table, not the route number', () => {
	const row = (line: string) => entry(line, line, '', ['A', 'B']);
	const lines = [
		'344',
		'460',
		'487',
		'501',
		'550',
		'577',
		'720',
		'754',
		'761',
		'799',
		'350',
		'450'
	].map(row);
	const found = (query: string) => searchLines(lines, query).map((e) => e.line);
	assert.deepEqual(found('rapid').sort(), ['720', '754', '761']);
	assert.deepEqual(found('express').sort(), ['460', '487', '501', '550', '577']);
	assert.deepEqual(found('limited'), ['344']);
	assert.equal(found('720 metro rapid')[0], '720');
});

test('"e line" and "expo" find the E Line first', () => {
	assert.equal(ids('e line')[0], '804');
	assert.deepEqual(ids('e line'), ['804']);
	// Lines 2, 209, 550 and the K Line all have "Expo" in a destination or via.
	assert.equal(ids('expo')[0], '804');
	assert.ok(ids('expo').length > 1);
});

test('"a line" finds the A Line and "g line" finds the busway through its via text', () => {
	assert.equal(ids('a line')[0], '801');
	assert.equal(ids('g line')[0], '901');
});

test('a label with a slash matches either number', () => {
	assert.equal(ids('48')[0], '10');
	assert.equal(ids('10/48')[0], '10');
});

test('an exact id ranks above a longer id that starts with it', () => {
	const more = [entry('720', '720', '', ['A', 'B']), entry('72', '72', '', ['A', 'B']), ...INDEX];
	assert.deepEqual(
		searchLines(more, '72').map((e) => e.line),
		['72', '720', '720']
	);
	assert.deepEqual(ids('72'), ['720']);
});

test('case and extra spaces do not matter', () => {
	assert.deepEqual(ids('  720   RAPID '), ids('720 rapid'));
	assert.deepEqual(ids('E LINE'), ids('e line'));
});

test('text that matches nothing returns an empty list', () => {
	assert.deepEqual(ids('zzzz'), []);
	assert.deepEqual(ids('720 zzzz'), []);
});

test('an empty or blank query returns an empty list', () => {
	assert.deepEqual(ids(''), []);
	assert.deepEqual(ids('   '), []);
	assert.deepEqual(ids('---'), []);
});

test('a very long query returns quickly and matches nothing', () => {
	const started = performance.now();
	assert.deepEqual(ids('x'.repeat(100_000)), []);
	assert.deepEqual(ids('720 '.repeat(5_000)).slice(0, 1), ['720']);
	assert.ok(performance.now() - started < 200);
});

test('the result list is capped', () => {
	const many = Array.from({ length: 50 }, (_, i) =>
		entry(`${900 + i}`, `${900 + i}`, '', ['A', 'B'])
	);
	assert.equal(searchLines(many, 'bus').length, 8);
	assert.equal(searchLines(many, 'bus', 3).length, 3);
});

test('the arrow keys wrap around the options', () => {
	assert.equal(moveActive(0, 'ArrowDown', 3), 1);
	assert.equal(moveActive(2, 'ArrowDown', 3), 0);
	assert.equal(moveActive(0, 'ArrowUp', 3), 2);
	assert.equal(moveActive(0, 'ArrowDown', 0), 0);
});
