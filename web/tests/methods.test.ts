// Renders the methodology page on the server and checks what a reader and a
// search engine get. The Masthead imports $app/paths, which exists only inside
// SvelteKit, so this test stands in a one-line replacement for it.
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { before, test } from 'node:test';
import { render } from 'svelte/server';

registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier !== '$app/paths') return nextResolve(specifier, context);
		return {
			url: 'data:text/javascript,export const resolve = (path) => path;',
			shortCircuit: true
		};
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

test('stays short enough to read in four minutes', () => {
	const words = copy.split(' ').length;
	assert.ok(words <= 900, `${words} words`);
});

test('says Metro scores rail at the end terminals', () => {
	assert.ok(text.includes('Metro scores rail at the end terminals.'));
	assert.ok(!text.includes('near 99 percent'));
});
