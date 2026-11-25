// The estimate notes. A line page, the home page strip and the methods page say how much of a
// figure was placed between two reports, and a published file from before the count existed
// must say nothing.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { render } from 'svelte/server';
import EstimatedNote from '../src/lib/design/EstimatedNote.svelte';
import StatusStrip from '../src/lib/design/StatusStrip.svelte';
import {
	ESTIMATE_ANCHOR,
	ESTIMATE_HREF,
	estimatedNote,
	estimatedShare
} from '../src/lib/estimated.ts';

test('the share is a whole percent of the arrivals', () => {
	assert.equal(estimatedShare(1000, 234), '23');
	assert.equal(estimatedShare(1000, 235), '24');
	assert.equal(estimatedShare(10, 10), '100');
});

test('a few estimates read as fewer than 1 percent, never 0', () => {
	assert.equal(estimatedShare(1000, 4), 'fewer than 1');
	assert.equal(estimatedShare(1000, 5), '1');
});

test('no estimates, no arrivals, or no count in the file give no sentence', () => {
	assert.equal(estimatedShare(1000, 0), undefined);
	assert.equal(estimatedShare(0, 0), undefined);
	assert.equal(estimatedShare(1000, undefined), undefined);
	assert.equal(estimatedNote(1000, undefined), undefined);
	assert.equal(estimatedNote(1000, 0), undefined);
});

test('the sentence names the method and has no dash', () => {
	const text = estimatedNote(1000, 234)!;
	assert.equal(
		text,
		'23 percent of these arrivals were estimated from where the bus was between two reports.'
	);
	assert.equal(
		estimatedNote(1000, 4),
		'Fewer than 1 percent of these arrivals were estimated from where the bus was between two reports.'
	);
	assert.doesNotMatch(text, /[—–]/);
});

test('the subject can change', () => {
	assert.equal(
		estimatedNote(200, 50, 'the stops graded'),
		'25 percent of the stops graded were estimated from where the bus was between two reports.'
	);
});

test('the link opens the methods section about timing an arrival', () => {
	assert.equal(ESTIMATE_HREF, `/methods#${ESTIMATE_ANCHOR}`);
});

const plain = (html: string) =>
	html
		.replace(/<!--.*?-->/g, '')
		.replace(/<[^>]+>/g, ' ')
		.replace(/\s+/g, ' ');

test('the note draws the sentence and the link, or nothing', () => {
	const { body } = render(EstimatedNote, { props: { n: 1000, est: 234 } });
	assert.ok(plain(body).includes('23 percent of these arrivals were estimated'));
	assert.match(body, /<a href="\/methods#how-an-arrival-is-timed">How we estimate<\/a>/);
	assert.equal(plain(render(EstimatedNote, { props: { n: 1000, est: 0 } }).body).trim(), '');
	assert.equal(
		plain(render(EstimatedNote, { props: { n: 1000, est: undefined } }).body).trim(),
		''
	);
});

const status = {
	first_day: '2026-08-18',
	last_day: '2026-11-15',
	days: 90,
	scheduled_stops: 2000,
	measured_arrivals: 1800,
	estimated_arrivals: 450,
	coverage_pct: 90,
	lines: 114,
	trips: 900
};

test('the home page strip says how much of the graded stops were estimated', () => {
	const text = plain(render(StatusStrip, { props: { status } }).body);
	assert.ok(text.includes('90%'));
	assert.ok(text.includes('of scheduled stops graded'));
	assert.ok(text.includes('25 percent of the stops graded were estimated'));
});

test('a status file from before the count shows the strip without the sentence', () => {
	const old: Partial<typeof status> = { ...status };
	delete old.estimated_arrivals;
	const text = plain(render(StatusStrip, { props: { status: old as typeof status } }).body);
	assert.ok(text.includes('stops graded'));
	assert.ok(!text.includes('estimated'));
});
