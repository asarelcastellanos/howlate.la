// The footnote that goes with every on-time share, and every place that share
// is drawn. A share without the note would read as Metro's own figure.
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { before, test } from 'node:test';
import { render } from 'svelte/server';
import { fixtureProfile } from '../src/lib/charts/fixtures.ts';
import Heatmap from '../src/lib/charts/Heatmap.svelte';
import { readoutHasShare } from '../src/lib/charts/readout.ts';
import type { IndexEntry, SiteIndex } from '../src/lib/data/types.ts';
import OntimeNote from '../src/lib/design/OntimeNote.svelte';
import { MEASURE_ANCHOR, MEASURE_HREF } from '../src/lib/ontimeNote.ts';

// The ranking components import $app modules that exist only inside SvelteKit.
registerHooks({
	resolve(specifier, context, nextResolve) {
		const stubs: Record<string, string> = {
			'$app/paths': 'export const resolve = (path) => path;',
			'$app/state': 'export const page = { route: { id: "/ranking" } };',
			'$app/env/public': 'export const PUBLIC_DATA_BASE = "/data";'
		};
		if (!(specifier in stubs)) return nextResolve(specifier, context);
		return { url: `data:text/javascript,${stubs[specifier]}`, shortCircuit: true };
	}
});

const NOTES = /<p class="caption text-ink-muted[^"]*">\s*<span aria-hidden="true">\*<\/span>/g;
// OntimeMark's own markup. The note's asterisk is plain and has no test id.
const MARK = '<span aria-hidden="true" data-testid="ontime-mark">\\*</span>';
const bare = (html: string) => html.replace(/<!--.*?-->/g, '');
const notes = (html: string) => bare(html).match(NOTES)?.length ?? 0;
const plain = (html: string) =>
	html
		.replace(/<!--.*?-->/g, '')
		.replace(/<[^>]+>/g, ' ')
		.replace(/\s+/g, ' ');

const entry = (line: string, over: Partial<IndexEntry> = {}): IndexEntry => ({
	line,
	agency: 'LACMTA',
	label: line,
	via: '',
	mode: 'bus',
	n: 50_000,
	sched: 50_000,
	med: 60,
	p90: 400,
	pct5: 20,
	ontime: 60,
	to: ['A'],
	...over
});

test('the note says how on time is measured and links to the methods section', () => {
	const { body } = render(OntimeNote);
	const text = plain(body);
	assert.ok(
		text.includes(
			'On time means arriving 1 minute early to 5 minutes late against the timetable. We score every measured stop after the first. Metro reports on-time performance differently.'
		)
	);
	assert.match(body, /<a href="\/methods#how-we-measure-on-time">How we measure<\/a>/);
	assert.equal(MEASURE_HREF, `/methods#${MEASURE_ANCHOR}`);
	assert.doesNotMatch(body, /[—–‘’“”]/);
});

test('the asterisk is hidden from a screen reader and the words and link are not', () => {
	const { body } = render(OntimeNote);
	assert.match(body, /<span aria-hidden="true">\*<\/span>/);
	// Everything outside the asterisk and the two length variants is a plain, readable link.
	assert.doesNotMatch(body.replace(/<span aria-hidden="true">\*<\/span>/, ''), /aria-hidden/);
	assert.match(body, /<span class="sm:hidden">On time means 1 minute early to 5 minutes late\./);
});

test('a phone gets the short form and wider screens get the full one', () => {
	const { body } = render(OntimeNote);
	assert.match(body, /class="sm:hidden"/);
	assert.match(body, /class="hidden sm:inline"/);
	// The phone form keeps the Metro caveat.
	assert.ok(
		plain(body).includes(
			'On time means 1 minute early to 5 minutes late. Metro reports on-time performance differently.'
		)
	);
	const short = body.match(/<span class="sm:hidden">([^<]*)<\/span>/)![1];
	assert.match(short, /Metro reports on-time performance differently\.$/);
});

test('the heatmap has the note when it shows a share and not when it does not', () => {
	const props = { profile: fixtureProfile(), caption: 'c', source: 's', showOntime: true };
	assert.equal(notes(render(Heatmap, { props }).body), 1);
	assert.equal(notes(render(Heatmap, { props: { ...props, showOntime: false } }).body), 0);
});

test('the heatmap readout marks an hour that has a share, and only then', () => {
	const hour = { h: 41, n: 312, med: 240, ontime: 56 };
	assert.equal(readoutHasShare(hour, { showOntime: true }), true);
	assert.equal(readoutHasShare(hour, { showOntime: false }), false);
	assert.equal(readoutHasShare({ ...hour, n: 3 }, { showOntime: true }), false);
	assert.equal(readoutHasShare({ h: 41 }, { showOntime: true }), false);
	const props = { profile: fixtureProfile(), caption: 'c', source: 's', showOntime: true };
	const readout = render(Heatmap, { props }).body.match(/aria-live="polite"[^>]*>([\s\S]*?)<\/p>/);
	assert.match(readout![1], new RegExp(`percent on time\\.[\\s\\S]*${MARK}`));
});

let RankingBody: typeof import('../src/routes/ranking/RankingBody.svelte').default;
let RailTable: typeof import('../src/routes/ranking/RailTable.svelte').default;

before(async () => {
	RankingBody = (await import('../src/routes/ranking/RankingBody.svelte')).default;
	RailTable = (await import('../src/routes/ranking/RailTable.svelte')).default;
});

test('the ranking page has a note under the two panels and another over the table', () => {
	const lines = Array.from({ length: 12 }, (_, i) => entry(String(i + 1), { ontime: 90 - i * 5 }));
	const index: SiteIndex = { first_day: '2026-08-18', last_day: '2026-11-15', days: 90, lines };
	const body = bare(render(RankingBody, { props: { index } }).body);
	assert.equal(notes(body), 2);
	// The panels mark each share, and the table marks its column heading.
	assert.equal(body.match(new RegExp(`% on time${MARK}`, 'g'))?.length, 10);
	assert.match(body, new RegExp(`On time${MARK}`));
});

test('the rail table has the note when it lists a share', () => {
	const entries = [entry('801', { mode: 'rail', label: 'Metro A Line', ontime: 56.4 })];
	const open = bare(render(RailTable, { props: { entries } }).body);
	assert.equal(notes(open), 1);
	assert.match(open, new RegExp(`On time${MARK}`));
	assert.equal(notes(render(RailTable, { props: { entries, showRailOntime: false } }).body), 0);
});
