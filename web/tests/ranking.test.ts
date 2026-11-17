// The ranking helpers on a fixture and on the real index, and the page's static
// copy. The real index lives in static/data, which is git-ignored, so CI has no
// copy and that test is skipped only when the whole folder is absent.
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { before, test } from 'node:test';
import { render } from 'svelte/server';
import type { IndexEntry, SiteIndex } from '../src/lib/data/types.ts';
import { shortVia } from '../src/lib/linePage.ts';
import {
	MIN_RANKED_ARRIVALS,
	ariaSort,
	compareIds,
	delayText,
	ends,
	nextSort,
	rankLines,
	type Metric,
	type Sort
} from '../src/lib/ranking.ts';

// The page imports $app modules that exist only inside SvelteKit.
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

const BIG = MIN_RANKED_ARRIVALS * 100;

function entry(line: string, over: Partial<IndexEntry> = {}): IndexEntry {
	return {
		line,
		agency: 'LACMTA',
		label: line,
		via: '',
		mode: 'bus',
		n: BIG,
		sched: BIG,
		med: 60,
		p90: 400,
		pct5: 20,
		ontime: 60,
		to: ['A'],
		...over
	};
}

const ids = (list: { entry: IndexEntry }[]) => list.map((r) => r.entry.line);

function realIndex(): IndexEntry[] | undefined {
	const dir = new URL('../static/data/', import.meta.url);
	if (!existsSync(dir)) return undefined;
	const pointer = JSON.parse(readFileSync(new URL('site/current.json', dir), 'utf8'));
	const index: SiteIndex = JSON.parse(
		readFileSync(new URL(`${pointer.prefix}index.json`, dir), 'utf8')
	);
	return index.lines;
}

const better = (metric: Metric, a: IndexEntry, b: IndexEntry) =>
	metric === 'ontime' ? b.ontime - a.ontime : a[metric] - b[metric];

test('on the real index, every metric orders lines by its value, then by line id', (t) => {
	const lines = realIndex();
	if (!lines) return t.skip('static/data is absent');
	const bus = lines.filter((l) => l.mode === 'bus');
	for (const metric of ['ontime', 'med', 'p90'] as const) {
		for (const order of ['best', 'worst'] as const) {
			const { ranked, unranked } = rankLines(bus, metric, order);
			const sign = order === 'best' ? 1 : -1;
			const entries = ranked.map((r) => r.entry);
			for (let i = 1; i < entries.length; i++) {
				const gap = sign * better(metric, entries[i - 1], entries[i]);
				assert.ok(gap <= 0, `${metric} ${order}: ${entries[i - 1].line} before ${entries[i].line}`);
				if (gap === 0) assert.ok(compareIds(entries[i - 1].line, entries[i].line) < 0);
			}
			const enough = bus.filter((l) => l.n >= MIN_RANKED_ARRIVALS);
			assert.equal(ranked.length, enough.length);
			assert.equal(ranked.length + unranked.length, bus.length);
		}
	}
});

test('on the real index, rail never reaches the on-time ranking', (t) => {
	const lines = realIndex();
	if (!lines) return t.skip('static/data is absent');
	const { ranked, unranked } = rankLines(lines, 'ontime');
	assert.ok(lines.some((l) => l.mode === 'rail'));
	assert.ok([...ranked.map((r) => r.entry), ...unranked].every((l) => l.mode === 'bus'));
});

test('lines with equal values keep line-id order, in both directions', () => {
	const lines = [
		entry('b', { ontime: 70 }),
		entry('10', { ontime: 70 }),
		entry('9', { ontime: 70 })
	];
	lines.push(entry('a', { ontime: 70 }), entry('z', { ontime: 80 }));
	for (const order of ['best', 'worst'] as const) {
		const { ranked } = rankLines(lines, 'ontime', order);
		const tied = ids(ranked).filter((id) => id !== 'z');
		assert.deepEqual(tied, ['9', '10', 'a', 'b'], order);
	}
	assert.deepEqual(ids(rankLines(lines, 'ontime').ranked)[0], 'z');
});

test('numeric ids sort before the others, in numeric order', () => {
	assert.deepEqual(['a', '10', '2', 'B', '9'].sort(compareIds), ['2', '9', '10', 'B', 'a']);
});

test('equal values share a rank and the next rank skips', () => {
	const lines = [
		entry('1', { ontime: 80 }),
		entry('2', { ontime: 70 }),
		entry('3', { ontime: 70 })
	];
	lines.push(entry('4', { ontime: 60 }));
	assert.deepEqual(
		rankLines(lines, 'ontime').ranked.map((r) => r.rank),
		[1, 2, 2, 4]
	);
	assert.deepEqual(
		rankLines(lines, 'ontime', 'worst').ranked.map((r) => r.rank),
		[4, 2, 2, 1]
	);
});

test('lower-is-better metrics sort ascending', () => {
	const lines = [
		entry('1', { med: 90, p90: 300 }),
		entry('2', { med: 10, p90: 900 }),
		entry('3', { med: 50, p90: 100 })
	];
	assert.deepEqual(ids(rankLines(lines, 'med').ranked), ['2', '3', '1']);
	assert.deepEqual(ids(rankLines(lines, 'p90').ranked), ['3', '1', '2']);
	assert.deepEqual(ids(rankLines(lines, 'med', 'worst').ranked), ['1', '3', '2']);
	assert.deepEqual(ids(rankLines(lines, 'ontime').ranked), ['1', '2', '3']);
});

test('a line under the threshold is unranked with its n, and never ranked', () => {
	const thin = entry('99', { n: MIN_RANKED_ARRIVALS - 1, ontime: 99.9, med: -5, p90: 1 });
	const edge = entry('98', { n: MIN_RANKED_ARRIVALS, ontime: 50 });
	for (const metric of ['ontime', 'med', 'p90'] as const) {
		const { ranked, unranked } = rankLines([thin, edge, entry('1')], metric);
		assert.deepEqual(ids(ranked).sort(), ['1', '98']);
		assert.deepEqual(
			unranked.map((e) => [e.line, e.n]),
			[['99', MIN_RANKED_ARRIVALS - 1]]
		);
	}
});

// The constant's own value is written out here on purpose. A test that reads
// MIN_RANKED_ARRIVALS passes when someone changes it.
test('the floor is 500 arrivals, so 499 is unranked and 500 is ranked', () => {
	const { ranked, unranked } = rankLines(
		[entry('1', { n: 499 }), entry('2', { n: 500 }), entry('3', { n: 501 })],
		'ontime'
	);
	assert.deepEqual(ids(ranked).sort(), ['2', '3']);
	assert.deepEqual(
		unranked.map((e) => e.line),
		['1']
	);
	assert.equal(MIN_RANKED_ARRIVALS, 500);
});

test('the Not ranked copy says 500', async () => {
	const RankingBody = (await import('../src/routes/ranking/RankingBody.svelte')).default;
	const index: SiteIndex = {
		first_day: '2026-08-18',
		last_day: '2026-11-15',
		days: 90,
		lines: [entry('697', { n: 202 }), entry('1'), entry('2')]
	};
	const text = render(RankingBody, { props: { index } })
		.body.replace(/<!--.*?-->/g, '')
		.replace(/<[^>]+>/g, ' ')
		.replace(/\s+/g, ' ');
	assert.ok(text.includes('fewer than 500 measured arrivals'), text);
	assert.ok(text.includes('202 arrivals measured'));
});

test('rail is left out of the on-time ranking and the unranked list, but not of median', () => {
	const rail = entry('801', { mode: 'rail', ontime: 99, med: 1, n: 10 });
	const lines = [rail, entry('1')];
	const byOntime = rankLines(lines, 'ontime');
	assert.deepEqual(ids(byOntime.ranked), ['1']);
	assert.deepEqual(byOntime.unranked, []);
	assert.deepEqual(
		ids(rankLines([entry('801', { mode: 'rail', med: 1 }), entry('1')], 'med').ranked),
		['801', '1']
	);
});

test('rankLines leaves its input alone', () => {
	const lines = [entry('2', { ontime: 10 }), entry('1', { ontime: 20 })];
	const before = JSON.stringify(lines);
	rankLines(lines, 'ontime');
	assert.equal(JSON.stringify(lines), before);
});

test('a header toggles direction on the active column and starts at best on another', () => {
	const start: Sort = { metric: 'ontime', order: 'best' };
	const flipped = nextSort(start, 'ontime');
	assert.deepEqual(flipped, { metric: 'ontime', order: 'worst' });
	assert.deepEqual(nextSort(flipped, 'ontime'), start);
	assert.deepEqual(nextSort(flipped, 'p90'), { metric: 'p90', order: 'best' });
	assert.equal(ariaSort(start, 'ontime'), 'descending');
	assert.equal(ariaSort(flipped, 'ontime'), 'ascending');
	assert.equal(ariaSort(nextSort(start, 'med'), 'med'), 'ascending');
	assert.equal(ariaSort(nextSort(nextSort(start, 'med'), 'med'), 'med'), 'descending');
	assert.equal(ariaSort(start, 'med'), undefined);
});

test('after a toggle, ties keep their order and the rest reverse', () => {
	const lines = [
		entry('3', { ontime: 70 }),
		entry('1', { ontime: 70 }),
		entry('2', { ontime: 50 }),
		entry('4', { ontime: 90 })
	];
	const sort = nextSort({ metric: 'ontime', order: 'best' }, 'ontime');
	assert.deepEqual(ids(rankLines(lines, sort.metric, sort.order).ranked), ['2', '1', '3', '4']);
});

test('the top and bottom lists never overlap and keep lines that tie at the edge', () => {
	const share = [90, 80, 70, 60, 50, 50, 40, 30];
	const ranked = rankLines(
		share.map((ontime, i) => entry(String(i + 1), { ontime })),
		'ontime'
	).ranked;
	const { top, bottom } = ends(ranked, 3);
	assert.deepEqual(ids(top), ['1', '2', '3']);
	assert.deepEqual(ids(bottom), ['8', '7', '6', '5']);
	const short = ends(ranked.slice(0, 4), 3);
	assert.deepEqual(ids(short.top), ['1', '2', '3']);
	assert.deepEqual(ids(short.bottom), ['4']);
	assert.deepEqual(ends([], 3), { top: [], bottom: [] });
});

test('text helpers', () => {
	assert.equal(delayText(270), '4.5 min late');
	assert.equal(delayText(-45), '0.8 min early');
	assert.equal(delayText(0), 'on time');
	// The table cuts the corridor text at 60 characters, shorter than a line page.
	assert.ok(shortVia('x'.repeat(200), 60).length <= 61);
});

test('table bullets follow the service table, never a number range', async () => {
	const RankedTable = (await import('../src/routes/ranking/RankedTable.svelte')).default;
	// 720 is in the table. 799, 350 and 450 sit in the old range guesses and are not.
	const lines = ['720', '799', '350', '450', '4', '901'].map((id, i) =>
		entry(id, { ontime: 70 - i, via: `Corridor ${id}` })
	);
	const html = render(RankedTable, { props: { entries: lines } }).body;
	const names = [...html.matchAll(/role="img" aria-label="([^"]*)"/g)].map((m) => m[1]);
	assert.deepEqual(names, [
		'Rapid route 720',
		'Route 799',
		'Route 350',
		'Route 450',
		'Route 4',
		'G Line'
	]);
	for (const id of ['720', '799', '350', '450', '4', '901']) {
		assert.ok(html.includes(`href="/lines/${id}"`), id);
	}
});

let head = '';
let body = '';
let copy = '';

before(async () => {
	const page = (await import('../src/routes/ranking/+page.svelte')).default;
	({ head, body } = render(page));
	copy = body
		.replace(/<!--.*?-->/g, '')
		.replace(/<[^>]+>/g, ' ')
		.replace(/\s+/g, ' ');
});

test('the page has one h1, a title and a description', () => {
	assert.equal(body.match(/<h1[\s>]/g)?.length, 1);
	assert.match(head, /<title>Line reliability ranking · HowLate<\/title>/);
	assert.match(head, /<meta name="description" content="[^"]{40,170}"/);
});

test('the static copy has no em dash, en dash or curly quote, and states the window', () => {
	assert.doesNotMatch(head + body, /[—–‘’“”]/);
	assert.ok(copy.includes('1 minute'));
	assert.ok(copy.includes('5 minutes'));
	assert.ok(copy.includes("Not Metro's published figure"));
	assert.ok(copy.includes('not only at timepoints'));
	assert.match(body, /href="\/methods"/);
});
