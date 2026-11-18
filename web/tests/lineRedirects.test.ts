// The line rules in static/_redirects. Pages takes the first rule that matches, so a
// rule that lands after `/lines/* /200 200` never runs and the line page loses its title.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { LINE_LIST } from '../src/lib/data/lines.ts';
import type { LineListEntry } from '../src/lib/lineHead.ts';
import { BEGIN, END, lineRule, withLineRules } from '../src/lib/lineRedirects.ts';

const WILDCARD = '/lines/* /200 200';
const REDIRECTS = new URL('../static/_redirects', import.meta.url);

const entry = (line: string): LineListEntry => ({
	line,
	label: line,
	mode: 'bus',
	to: ['Santa Monica'],
	via: 'Wilshire'
});
const file = ['# top', BEGIN, '/lines/old /lines/old 200', END, '# shell', WILDCARD, ''].join('\n');

test('a rule rewrites a line to its own path, with no .html target', () => {
	assert.equal(lineRule('720'), '/lines/720 /lines/720 200');
});

test('the rules replace what was between the markers and sit before the wildcard', () => {
	const out = withLineRules(file, [entry('2'), entry('720')]).split('\n');
	assert.deepEqual(out, [
		'# top',
		BEGIN,
		'/lines/2 /lines/2 200',
		'/lines/720 /lines/720 200',
		END,
		'# shell',
		WILDCARD,
		''
	]);
});

test('an empty list leaves the markers with nothing between them', () => {
	const out = withLineRules(file, []).split('\n');
	assert.equal(out.indexOf(END) - out.indexOf(BEGIN), 1);
});

test('rewriting twice gives the same file', () => {
	const once = withLineRules(file, [entry('2'), entry('720')]);
	assert.equal(withLineRules(once, [entry('2'), entry('720')]), once);
});

test('an id that _redirects would read as a pattern or a comment throws', () => {
	for (const id of ['7 20', '72*', ':id', '#7', '7/20', '']) {
		assert.throws(
			() => withLineRules(file, [entry('2'), entry(id)]),
			/cannot go in _redirects/,
			id
		);
	}
});

test('a file without both markers, or with them swapped, throws', () => {
	for (const bad of ['', WILDCARD, `${BEGIN}\n${WILDCARD}`, `${END}\n${BEGIN}\n${WILDCARD}`]) {
		assert.throws(() => withLineRules(bad, [entry('2')]), /needs the lines/);
	}
});

test('the committed _redirects has a rule for every line in lines.json, before the wildcard', () => {
	const lines = readFileSync(REDIRECTS, 'utf8').split('\n');
	const wildcard = lines.indexOf(WILDCARD);
	assert.ok(wildcard > lines.indexOf(END), 'the wildcard must come after the line rules');
	for (const { line } of LINE_LIST) {
		const at = lines.indexOf(lineRule(line));
		assert.ok(at > lines.indexOf(BEGIN) && at < lines.indexOf(END), `no rule for line ${line}`);
	}
});

test('the committed _redirects matches lines.json, so run `npm run lines:refresh` after a change', () => {
	const committed = readFileSync(REDIRECTS, 'utf8');
	assert.equal(withLineRules(committed, LINE_LIST), committed);
});
