// The heatmap's selection, as pure functions and as drawn. Keys and wording are
// tested on numbers. The cell tagging and the selection outline are tested on
// the SVG that Plot draws.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseHTML } from 'linkedom';
import { render } from 'svelte/server';
import { HOT_HOUR, THIN_HOUR, fixtureProfile } from '../src/lib/charts/fixtures.ts';
import Heatmap from '../src/lib/charts/Heatmap.svelte';
import { heatmap, selectHour } from '../src/lib/charts/heatmap.ts';
import { nextHour, readoutText, startHour } from '../src/lib/charts/readout.ts';
import type { Hour } from '../src/lib/data/types.ts';
import { hasRealData, realLines } from './realData.ts';

const { document } = parseHTML('<!doctype html><html><body></body></html>');
const hour = (h: number, change: Partial<Hour> = {}): Hour => ({
	h,
	n: 312,
	sched: 400,
	med: 240,
	p90: 900,
	pct5: 30,
	ontime: 56.4,
	...change
});
const FRIDAY_5PM = 4 * 24 + 17;
const MONDAY = 0;
const SUNDAY = 6 * 24;

test('Left and Right move one hour and stop at the edges of the week', () => {
	assert.equal(nextHour(FRIDAY_5PM, 'ArrowRight'), FRIDAY_5PM + 1);
	assert.equal(nextHour(FRIDAY_5PM, 'ArrowLeft'), FRIDAY_5PM - 1);
	// The hour after Monday 11 pm is Tuesday 12 am, so the key moves across the day edge.
	assert.equal(nextHour(23, 'ArrowRight'), 24);
	assert.equal(nextHour(24, 'ArrowLeft'), 23);
	// The first and last hours of the week have no neighbor, so the selection stays.
	assert.equal(nextHour(0, 'ArrowLeft'), 0);
	assert.equal(nextHour(167, 'ArrowRight'), 167);
});

test('Up and Down move one day at the same hour and stop at Monday and Sunday', () => {
	assert.equal(nextHour(FRIDAY_5PM, 'ArrowUp'), FRIDAY_5PM - 24);
	assert.equal(nextHour(FRIDAY_5PM, 'ArrowDown'), FRIDAY_5PM + 24);
	assert.equal(nextHour(17, 'ArrowUp'), 17);
	assert.equal(nextHour(SUNDAY + 17, 'ArrowDown'), SUNDAY + 17);
});

test('Home and End go to the first and last hour of the same day', () => {
	assert.equal(nextHour(FRIDAY_5PM, 'Home'), 4 * 24);
	assert.equal(nextHour(FRIDAY_5PM, 'End'), 4 * 24 + 23);
	assert.equal(nextHour(MONDAY, 'Home'), 0);
	assert.equal(nextHour(167, 'End'), 167);
});

test('a key the grid does not use returns nothing, so the page keeps it', () => {
	for (const key of ['Tab', 'Enter', ' ', 'a', 'PageDown', 'Escape', 'Shift']) {
		assert.equal(nextHour(FRIDAY_5PM, key), undefined, key);
	}
});

test('every hour of the week stays inside the week under every key', () => {
	for (let h = 0; h < 168; h++) {
		for (const key of ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End']) {
			const next = nextHour(h, key)!;
			assert.ok(Number.isInteger(next) && next >= 0 && next < 168, `${h} ${key} gave ${next}`);
		}
	}
});

test('a measured hour reads as day, hour, median, on-time share and count', () => {
	assert.equal(
		readoutText(hour(FRIDAY_5PM), { showOntime: true }),
		'Friday 5 pm. Median 4 minutes late. 56 percent on time. 312 arrivals measured.'
	);
});

test('the median keeps seconds under two minutes and says early and on time in words', () => {
	const say = (med: number) => readoutText(hour(FRIDAY_5PM, { med }), { showOntime: false });
	assert.match(say(64), /^Friday 5 pm\. Median 64 seconds late\./);
	assert.match(say(120), /Median 2 minutes late\./);
	assert.match(say(-300), /Median 5 minutes early\./);
	assert.match(say(0), /Median on time\./);
	assert.match(say(1), /Median 1 second late\./);
});

test('a rail line leaves out the on-time sentence', () => {
	const text = readoutText(hour(FRIDAY_5PM), { showOntime: false });
	assert.equal(text, 'Friday 5 pm. Median 4 minutes late. 312 arrivals measured.');
	assert.doesNotMatch(text, /percent|on time/);
});

test('an hour with too few arrivals says so and gives no median', () => {
	const text = readoutText(hour(FRIDAY_5PM, { n: 3, med: 1500 }), { showOntime: true });
	assert.equal(text, 'Friday 5 pm. Only 3 arrivals measured, too few to judge.');
	assert.equal(
		readoutText(hour(FRIDAY_5PM, { n: 1 }), { showOntime: true }),
		'Friday 5 pm. Only 1 arrival measured, too few to judge.'
	);
});

test('an hour with no entry says nothing was measured', () => {
	assert.equal(
		readoutText({ h: 4 * 24 + 3 }, { showOntime: true }),
		'Friday 3 am. Nothing measured.'
	);
});

test('hours read as 12 am, noon, 12 pm hours as noon and 11 pm', () => {
	const at = (h: number) => readoutText({ h }, { showOntime: true });
	assert.equal(at(0), 'Monday 12 am. Nothing measured.');
	assert.equal(at(12), 'Monday noon. Nothing measured.');
	assert.equal(at(23), 'Monday 11 pm. Nothing measured.');
	assert.equal(at(SUNDAY + 5), 'Sunday 5 am. Nothing measured.');
});

test('large counts get a thousands separator and units stay words', () => {
	const text = readoutText(hour(FRIDAY_5PM, { n: 3759, ontime: 47.9 }), { showOntime: true });
	assert.match(text, /48 percent on time\. 3,759 arrivals measured\.$/);
	assert.doesNotMatch(text, /%|\bmin\b|\bs\b|\bn=/);
});

test('the heatmap starts on the worst hour, and on the top hour when none ran late', () => {
	assert.equal(startHour(fixtureProfile()), HOT_HOUR);
	// The thin hour has the biggest median but never starts the selection.
	assert.notEqual(startHour(fixtureProfile()), THIN_HOUR);
	const early = fixtureProfile().map((h) => ({ ...h, med: -60 - (h.h % 5) * 10 }));
	assert.equal(startHour(early), early.find((h) => h.med === -60 && h.n >= 5)!.h);
});

test('every cell carries its hour, once, and the worst outline carries none', () => {
	const profile = fixtureProfile();
	const svg = heatmap(profile, { width: 800, document });
	const tagged = [...svg.querySelectorAll('[data-hour]')];
	assert.equal(tagged.length, 168);
	assert.deepEqual(
		tagged.map((el) => Number(el.getAttribute('data-hour'))).sort((a, b) => a - b),
		Array.from({ length: 168 }, (_, h) => h)
	);
	// The hot hour's rect is the ramp rect on Friday 17:00, and the thin hour's is hatched.
	const fill = (h: number) => svg.querySelector(`[data-hour="${h}"]`)!.getAttribute('fill');
	assert.equal(fill(HOT_HOUR), 'var(--delay-5)');
	assert.ok(
		svg
			.querySelector(`[data-hour="${THIN_HOUR}"]`)!
			.parentElement!.getAttribute('fill')!
			.startsWith('url(#')
	);
	assert.equal(
		svg.querySelector('g[aria-label="cell"][pointer-events="none"]')?.children.length,
		1
	);
});

test('a cell with no data takes a tap on its inside, not only on its outline', () => {
	const svg = heatmap(fixtureProfile(), { width: 800, document });
	const rect = svg.querySelector('[data-hour="122"]');
	assert.ok(rect, 'Saturday 2 am is tagged');
	assert.equal(rect.parentElement!.getAttribute('fill'), 'none');
	assert.equal(rect.parentElement!.getAttribute('pointer-events'), 'all');
});

test('tagging survives a profile with no thin hour and no gap', () => {
	const full = Array.from({ length: 168 }, (_, h) => hour(h));
	const svg = heatmap(full, { width: 343, document });
	assert.equal(svg.querySelectorAll('[data-hour]').length, 168);
});

// With a gap but no thin hour, the thin list is empty and Plot leaves out its
// group. The absent hours then line up with the second group, not the third.
test('tagging survives a profile with gaps and no thin hour', () => {
	const gaps = Array.from({ length: 168 }, (_, h) => h)
		.filter((h) => h % 10 !== 0)
		.map((h) => hour(h));
	assert.ok(
		gaps.every((entry) => entry.n >= 5),
		'no hour is thin'
	);
	const svg = heatmap(gaps, { width: 800, document });
	assert.equal(svg.querySelectorAll('[data-hour]').length, 168);
	assert.deepEqual(
		[...svg.querySelectorAll('[data-hour]')]
			.map((el) => Number(el.getAttribute('data-hour')))
			.sort((a, b) => a - b),
		Array.from({ length: 168 }, (_, h) => h)
	);
	// An absent hour is the dotted outline with no fill, and a measured one is not.
	const fill = (h: number) =>
		svg.querySelector(`[data-hour="${h}"]`)!.parentElement!.getAttribute('fill');
	assert.equal(fill(10), 'none');
	assert.equal(fill(20), 'none');
	assert.notEqual(fill(11), 'none');
});

test('the readout never says 100 percent unless the share is exactly 100', () => {
	const share = (ontime: number) =>
		readoutText(hour(30, { ontime }), { showOntime: true }).match(/(\d+) percent on time/)?.[1];
	assert.equal(share(99.4), '99');
	assert.equal(share(99.5), '99');
	assert.equal(share(99.9), '99');
	assert.equal(share(99.99), '99');
	assert.equal(share(100), '100');
	assert.equal(share(56.5), '57');
	assert.equal(share(0.4), '0');
});

test('selectHour puts one outline on the chosen cell and moves it', () => {
	const svg = heatmap(fixtureProfile(), { width: 800, document });
	selectHour(svg, FRIDAY_5PM - 24);
	const marks = () => [...svg.querySelectorAll('.howlate-selected')];
	assert.equal(marks().length, 1);
	const cell = svg.querySelector(`[data-hour="${FRIDAY_5PM - 24}"]`)!;
	const [group] = marks();
	const outline = group.children[0];
	const center = (el: Element, a: string, s: string) =>
		Number(el.getAttribute(a)) + Number(el.getAttribute(s)) / 2;
	assert.equal(center(outline, 'x', 'width'), center(cell, 'x', 'width'));
	assert.equal(center(outline, 'y', 'height'), center(cell, 'y', 'height'));
	// The outline is a shape, not a color change. It is thicker than the worst-hour outline and has a paper keyline.
	assert.equal(outline.getAttribute('fill'), 'none');
	assert.ok(Number(outline.getAttribute('stroke-width')) > 2);
	assert.equal(group.getAttribute('pointer-events'), 'none');
	assert.equal(group.children[1].getAttribute('stroke'), 'var(--paper)');
	selectHour(svg, 3);
	assert.equal(marks().length, 1);
	assert.equal(
		center(marks()[0].children[0], 'x', 'width'),
		center(svg.querySelector('[data-hour="3"]')!, 'x', 'width')
	);
	assert.doesNotMatch(
		svg.outerHTML.replace(/<style>[\s\S]*?<\/style>/g, ''),
		/#[0-9a-f]{3,8}\b|rgba?\(/i
	);
});

test('the heatmap renders a readout line that reads out the worst hour first', () => {
	const props = { profile: fixtureProfile(), caption: 'c', source: 's', showOntime: true };
	const { body } = render(Heatmap, { props });
	assert.match(body, /<p[^>]*aria-live="polite"[^>]*>\s*Friday 5 pm\. Median 12 minutes late\./);
	assert.match(body, /\d+ percent on time\./);
	const rail = render(Heatmap, { props: { ...props, showOntime: false } }).body;
	assert.match(
		rail,
		/aria-live="polite"[^>]*>\s*Friday 5 pm\. Median 12 minutes late\. 800 arrivals measured\./
	);
	assert.doesNotMatch(rail.replace(/<table[\s\S]*<\/table>/, ''), /percent on time/);
});

test('the real 720 Friday 5 pm entry reads as the profile says', { skip: !hasRealData }, () => {
	const entry = realLines()
		.get('720')!
		.directions[0].profile.find((h) => h.h === FRIDAY_5PM)!;
	const text = readoutText(entry, { showOntime: true });
	assert.ok(text.includes(`${entry.n.toLocaleString('en-US')} arrivals measured`));
	assert.ok(text.includes(`${Math.round(entry.ontime)} percent on time`));
	assert.match(text, /^Friday 5 pm\. Median \d+ (seconds|minutes) late\./);
});
