// Renders the methodology page on the server and checks what a reader and a
// search engine get. The Masthead imports $app/paths, which exists only inside
// SvelteKit, so this test stands in a short replacement for each one.
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { before, test } from 'node:test';
import { render } from 'svelte/server';

registerHooks({
	resolve(specifier, context, nextResolve) {
		const stubs: Record<string, string> = {
			'$app/paths': 'export const resolve = (path) => path;',
			'$app/state': 'export const page = { route: { id: "/methods" } };'
		};
		if (!(specifier in stubs)) return nextResolve(specifier, context);
		return { url: `data:text/javascript,${stubs[specifier]}`, shortCircuit: true };
	}
});

let head = '';
let body = '';
let text = '';
let copy = '';

before(async () => {
	const page = (await import('../src/routes/methods/+page.svelte')).default;
	({ head, body } = render(page));
	const plain = (html: string) =>
		html
			.replace(/<!--.*?-->/g, '')
			.replace(/<[^>]+>/g, ' ')
			.replace(/&[a-z]+;|&#\d+;/g, ' ')
			.replace(/\s+/g, ' ')
			.trim();
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

test('stays short enough to read in four minutes at about 250 words a minute', () => {
	const words = copy.split(' ').length;
	assert.ok(words <= 1000, `${words} words`);
});

test('does not compare rail with Metro 99.4 percent and says why', () => {
	assert.ok(!text.includes('99.4'));
	assert.ok(text.includes('84 percent'));
	assert.ok(text.includes('Metro measures buses at timepoints'));
	assert.ok(text.includes('HowLate does not show an on-time share'));
});

test('keeps the Metro bus figure with its source and says it is not comparable', () => {
	assert.ok(text.includes('78.2 percent'));
	assert.ok(text.includes('2025-0860'));
	assert.ok(text.includes('July to September 2025'));
	assert.ok(text.includes('not comparable'));
});

test('lists the rail limit under what we do not know', () => {
	const section = text.slice(text.indexOf('What we do not know'));
	assert.ok(section.includes('does not yet know how Metro times a terminal arrival'));
	assert.ok(section.includes('Rail lines show median and 90th percentile delay.'));
});

test('keeps all three health-check examples and the timetable-change limit', () => {
	assert.ok(text.includes('Three examples follow.'));
	assert.ok(
		text.includes('The silent lines check fails when a scheduled line has no report all day.')
	);
	assert.ok(text.includes('a change to one agency'));
});
