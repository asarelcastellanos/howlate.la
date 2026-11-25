// Renders the methodology page on the server and checks what a reader and a
// search engine get. The Masthead imports $app/paths, which exists only inside
// SvelteKit, so this test stands in a short replacement for each one.
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { before, test } from 'node:test';
import { render } from 'svelte/server';
import { MEASURE_ANCHOR } from '../src/lib/ontimeNote.ts';

registerHooks({
	resolve(specifier, context, nextResolve) {
		const stubs: Record<string, string> = {
			'$app/paths': 'export const resolve = (path) => path;',
			'$app/state': 'export const page = { route: { id: "/methods" } };',
			'$app/env/public': 'export const PUBLIC_DATA_BASE = "/data";'
		};
		if (!(specifier in stubs)) return nextResolve(specifier, context);
		return { url: `data:text/javascript,${stubs[specifier]}`, shortCircuit: true };
	}
});

let head = '';
let body = '';
let text = '';
let copy = '';
let MeasureOnTime: typeof import('../src/routes/methods/MeasureOnTime.svelte').default;
const plain = (html: string) =>
	html
		.replace(/<!--.*?-->/g, '')
		.replace(/<[^>]+>/g, ' ')
		.replace(/&[a-z]+;|&#\d+;/g, ' ')
		.replace(/\s+/g, ' ')
		.trim();

before(async () => {
	const page = (await import('../src/routes/methods/+page.svelte')).default;
	({ head, body } = render(page));
	MeasureOnTime = (await import('../src/routes/methods/MeasureOnTime.svelte')).default;
	text = plain(body);
	copy = plain(body.slice(body.indexOf('<main')));
});

test('has one h1, a title and a description', () => {
	assert.equal(body.match(/<h1[\s>]/g)?.length, 1);
	assert.match(head, /<title>Methods · HowLate<\/title>/);
	assert.match(head, /<meta name="description" content="[^"]{40,160}"/);
});

test('headings never skip a level', () => {
	const levels = [...body.matchAll(/<h([1-6])[\s>]/g)].map((m) => Number(m[1]));
	assert.equal(levels[0], 1);
	assert.ok(levels.length >= 7, `found only ${levels.length} headings`);
	levels.forEach((level, i) => {
		if (i > 0) assert.ok(level <= levels[i - 1] + 1, `h${level} follows h${levels[i - 1]}`);
	});
});

test('uses no em dash, en dash or curly quote', () => {
	assert.doesNotMatch(head + body, /[—–‘’“”]/);
});

test('states the on-time window and the three explained-trip counts', () => {
	for (const phrase of ['1 minute', '5 minutes', '214', '244', '338']) {
		assert.ok(text.includes(phrase), `missing "${phrase}"`);
	}
});

// The longer on-time section took the page past 1,000 words, so the limit moved
// from four minutes to five. How skipped bus stops are estimated, with its check,
// took it from about 1,250 words to 1,402, so the limit is 1,410, under 5.7 minutes.
test('stays short enough to read in under six minutes at about 250 words a minute', () => {
	const words = copy.split(' ').length;
	assert.ok(words <= 1410, `${words} words`);
});

test('says how a skipped bus stop is estimated, with the check, and links the section', () => {
	assert.match(body, /<section id="how-an-arrival-is-timed"/);
	for (const phrase of [
		'HowLate places these between two reports of the same bus',
		'only when the two reports are 5 minutes apart or less, and never for rail',
		'We checked this by hiding 3.1 million bus stops from 10 to 16 November 2026',
		'a median 2 seconds early and 9 in 10 were within 28 seconds. 3.0 percent landed on the other side of the on-time window',
		'so these figures may not hold for it',
		'Estimates fill some of the rest',
		'We do not correct estimated bus stops either'
	]) {
		assert.ok(text.includes(phrase), `missing "${phrase}"`);
	}
});

test('has a how-we-measure-on-time section for the footnote to link to', () => {
	assert.match(body, /<section id="how-we-measure-on-time"/);
	assert.equal(MEASURE_ANCHOR, 'how-we-measure-on-time');
	assert.match(body.replace(/<!--.*?-->/g, ''), /<h2[^>]*>How we measure on-time<\/h2>/);
	assert.ok(text.includes('What we measure.'));
	assert.ok(text.includes('Why every measured stop.'));
	assert.ok(text.includes('What Metro reports.'));
	assert.ok(text.includes('What the feed gives us.'));
	assert.ok(text.includes('What we cannot explain.'));
});

test('gives Metro bus and rail figures with their sources and the different question they answer', () => {
	for (const phrase of [
		'2025 Transit Service Policies and Standards',
		'section 3.3, state how bus and rail on-time performance are measured',
		'Bus is measured at all timepoints along a route, and rail at the end terminal on arrival',
		'File 2025-0860',
		'Operations, Safety, and Customer Experience Committee',
		'20 November 2025',
		'gives the figures for July to September 2025, 78.2 percent for buses and 99.4 percent for rail',
		"Metro's definitions ask a different question than ours, and its figures cover a different period"
	]) {
		assert.ok(text.includes(phrase), `missing "${phrase}"`);
	}
	assert.match(
		body,
		/href="https:\/\/busstophub\.metro\.net\/wp-content\/uploads\/2025\/10\/TSP-2025-Adopted-7-17-2025\.pdf"/
	);
	assert.match(
		body,
		/href="https:\/\/metro\.legistar\.com\/ViewReport\.ashx\?M=R&amp;N=TextL5&amp;GID=557&amp;ID=11879&amp;GUID=LATEST&amp;G=A5FAA737-A54D-4A6C-B1E8-FF70F765FA94&amp;Title=Board\+Report"/
	);
});

test('says the rail last-stop figures come from issue 133 for one period', () => {
	for (const phrase of [
		'From 18 August to 15 November 2026',
		'93,955 of 93,956 measured rail last stops',
		'about 5 percent of the rail stops we score',
		'about 1 percent of the bus stops we score',
		'cover that period only',
		'53.7 percent over the same period',
		'lower than our all-stops share, not higher',
		'We have not been able to confirm how Metro times a terminal arrival'
	]) {
		assert.ok(text.includes(phrase), `missing "${phrase}"`);
	}
	assert.match(body, /href="https:\/\/github\.com\/asarelcastellanos\/howlate\.la\/issues\/133"/);
});

test('types no current bus or rail share into the copy, because the live sentence carries them', () => {
	// The prerendered page has no network figure. The browser adds one from network.json.
	assert.doesNotMatch(text, /As of .* HowLate scored/);
	assert.doesNotMatch(text, /\b6[0-9]\.\d percent of measured/);
});

test('no longer says the rail on-time share is not shown', () => {
	assert.doesNotMatch(text, /does not show an on-time share/);
	assert.doesNotMatch(text, /Rail lines show median and 90th percentile delay/);
	const section = text.slice(text.indexOf('What we do not know'));
	assert.ok(section.includes('does not know how Metro times a rail terminal arrival'));
	assert.ok(section.includes('Last-stop arrivals are estimates, and many read early.'));
});

test('says lines B and D ran slow on 13 of 26 weekend days without naming a cause', () => {
	const section = text.slice(text.indexOf('What we do not know'));
	assert.ok(
		section.includes(
			'On 13 of the 26 weekend days from 18 August to 15 November 2026, their timetable allowed no more running time than on a weekday while the median trip took about 6 minutes longer, and we do not know why.'
		)
	);
});

test('keeps all three health-check examples and the timetable-change limit', () => {
	assert.ok(text.includes('Three examples follow.'));
	assert.ok(
		text.includes('The silent lines check fails when a scheduled line has no report all day.')
	);
	assert.ok(text.includes('a change to one agency'));
});

test('claims no more than the measurements show', () => {
	assert.doesNotMatch(text, /adopted/i);
	assert.doesNotMatch(text, /about every 6 seconds/);
	assert.doesNotMatch(text, /those estimates read early|they read early/);
	assert.ok(
		text.includes(
			"A vehicle's distinct reports are a median 5 to 6 seconds apart (5 for rail, 6 for bus, measured over 8 to 14 November 2026)"
		)
	);
	assert.ok(text.includes('and many read early'));
	assert.ok(
		text.includes(
			"Metro's standards state an on-time window of 1 minute early to 5 minutes late for buses and do not state one for rail"
		)
	);
	assert.doesNotMatch(text, /It does not publish one for rail/);
});

// The copy is written for the open gate. Closing it must remove every sentence
// that states a rail on-time share, and the section must still read.
const RAIL_SHARE = /53\.7 percent|67 percent|55 percent|rail share|rail on-time share/;

test('with the rail gate open the section states the rail last-stop share', () => {
	const open = plain(render(MeasureOnTime, { props: { railGate: true } }).body);
	assert.match(open, RAIL_SHARE);
	assert.ok(open.includes('our rail share is 53.7 percent'));
});

test('with the rail gate closed the section states no rail share', () => {
	const closed = plain(render(MeasureOnTime, { props: { railGate: false } }).body);
	assert.doesNotMatch(closed, RAIL_SHARE);
	assert.ok(
		closed.includes('We have not been able to confirm how Metro times a terminal arrival.')
	);
	assert.ok(closed.includes('93,955 of 93,956 measured rail last stops'));
});

test('the page states no rail on-time share outside the section that is gated', () => {
	assert.doesNotMatch(text.slice(text.indexOf('Why some stops have no number')), RAIL_SHARE);
});
