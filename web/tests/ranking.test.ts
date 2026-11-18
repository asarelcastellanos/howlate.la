// The ranking helpers on a fixture and on the real index, and the page's static
// copy. The real index lives in static/data, which is git-ignored, so CI has no
// copy and that test is skipped only when the whole folder is absent.
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { before, test } from 'node:test';
import { render } from 'svelte/server';
import type { IndexEntry, SiteIndex } from '../src/lib/data/types.ts';
import { RAIL_HOLD_NOTE, headline, shortVia } from '../src/lib/linePage.ts';
import {
	MIN_RANKED_ARRIVALS,
	ariaSort,
	compareIds,
	delayText,
	distanceFromWindow,
	ends,
	nextSort,
	percent,
	rankLines,
	type Metric,
	type Sort
} from '../src/lib/ranking.ts';
import { shareText } from '../src/lib/share.ts';

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
	metric === 'ontime'
		? b.ontime - a.ontime
		: distanceFromWindow(a[metric]) - distanceFromWindow(b[metric]) ||
			Math.abs(a[metric]) - Math.abs(b[metric]);

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

test('on the real index, rail stays out of the on-time ranking while the gate is closed', (t) => {
	const lines = realIndex();
	if (!lines) return t.skip('static/data is absent');
	const { ranked, unranked } = rankLines(lines, 'ontime', 'best', false);
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

test('a delay farther outside the window sorts lower', () => {
	// Distances from the window: median 600, 100, 300 and p90 1200, 1800, 500.
	const lines = [
		entry('1', { med: 900, p90: 1500 }),
		entry('2', { med: 400, p90: 2100 }),
		entry('3', { med: 600, p90: 800 })
	];
	assert.deepEqual(ids(rankLines(lines, 'med').ranked), ['2', '3', '1']);
	assert.deepEqual(ids(rankLines(lines, 'p90').ranked), ['3', '1', '2']);
	assert.deepEqual(ids(rankLines(lines, 'med', 'worst').ranked), ['1', '3', '2']);
	assert.deepEqual(ids(rankLines(lines, 'ontime').ranked), ['1', '2', '3']);
});

test('median and p90 rank by distance from the on-time window, early or late', () => {
	// The window is -60 s to +300 s. -120 is 60 s outside it and 10 is inside.
	assert.equal(distanceFromWindow(-120), 60);
	assert.equal(distanceFromWindow(-60), 0);
	assert.equal(distanceFromWindow(0), 0);
	assert.equal(distanceFromWindow(10), 0);
	assert.equal(distanceFromWindow(300), 0);
	assert.equal(distanceFromWindow(301), 1);
	assert.equal(distanceFromWindow(420), 120);
	const lines = [
		entry('1', { med: -120, p90: 700 }),
		entry('2', { med: 10, p90: -200 }),
		entry('3', { med: 400, p90: 310 })
	];
	// Median: line 2 is inside (0), line 1 is 60 out, line 3 is 100 out.
	assert.deepEqual(ids(rankLines(lines, 'med').ranked), ['2', '1', '3']);
	assert.deepEqual(ids(rankLines(lines, 'med', 'worst').ranked), ['3', '1', '2']);
	// P90: line 3 is 10 out, line 2 is 140 out, line 1 is 400 out.
	assert.deepEqual(ids(rankLines(lines, 'p90').ranked), ['3', '2', '1']);
});

test('inside the window the smaller delay ranks higher', () => {
	const lines = [entry('1', { med: 194 }), entry('2', { med: 19 }), entry('3', { med: -45 })];
	assert.deepEqual(ids(rankLines(lines, 'med').ranked), ['2', '3', '1']);
	assert.deepEqual(ids(rankLines(lines, 'med', 'worst').ranked), ['1', '3', '2']);
	const p90 = [entry('1', { p90: 280 }), entry('2', { p90: 15 })];
	assert.deepEqual(ids(rankLines(p90, 'p90').ranked), ['2', '1']);
});

test('a tie on distance and on size shares a rank and sorts by line id', () => {
	// -30 and 30 are both inside the window and both 30 s from on time.
	const lines = [
		entry('3', { med: 250 }),
		entry('2', { med: 30 }),
		entry('1', { med: -30 }),
		entry('4', { med: 301 })
	];
	const { ranked } = rankLines(lines, 'med');
	assert.deepEqual(ids(ranked), ['1', '2', '3', '4']);
	assert.deepEqual(
		ranked.map((r) => r.rank),
		[1, 1, 3, 4]
	);
	// The same two lines keep id order when the table is reversed.
	assert.deepEqual(ids(rankLines(lines, 'med', 'worst').ranked), ['4', '3', '1', '2']);
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

test('a closed rail gate leaves rail out of the on-time ranking and the unranked list, but not of median', () => {
	const rail = entry('801', { mode: 'rail', ontime: 99, med: 1, n: 10 });
	const lines = [rail, entry('1')];
	const byOntime = rankLines(lines, 'ontime', 'best', false);
	assert.deepEqual(ids(byOntime.ranked), ['1']);
	assert.deepEqual(byOntime.unranked, []);
	assert.deepEqual(
		ids(
			rankLines([entry('801', { mode: 'rail', med: 1 }), entry('1', { med: 500 })], 'med').ranked
		),
		['801', '1']
	);
});

test('an open rail gate, the default, ranks rail by on-time share like a bus line', () => {
	const rail = entry('801', { mode: 'rail', ontime: 99 });
	const lines = [rail, entry('1', { ontime: 60 })];
	assert.deepEqual(ids(rankLines(lines, 'ontime').ranked), ['801', '1']);
	const thin = entry('804', { mode: 'rail', n: 10 });
	assert.deepEqual(
		rankLines([thin], 'ontime').unranked.map((e) => e.line),
		['804']
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

// Line i has the share 90 - 5 * i, so every line has its own rank.
function bodyText(lines: number): string {
	const RankingBody = bodyComponent;
	const index: SiteIndex = {
		first_day: '2026-08-18',
		last_day: '2026-11-15',
		days: 90,
		lines: Array.from({ length: lines }, (_, i) => entry(String(i + 1), { ontime: 90 - i * 5 }))
	};
	return render(RankingBody, { props: { index } })
		.body.replace(/<!--.*?-->/g, '')
		.replace(/<[^>]+>/g, ' ')
		.replace(/\s+/g, ' ');
}

let bodyComponent: typeof import('../src/routes/ranking/RankingBody.svelte').default;

before(async () => {
	bodyComponent = (await import('../src/routes/ranking/RankingBody.svelte')).default;
});

test('the Least reliable panel counts the lines it lists and hides when empty', () => {
	// With N ranked lines the top block takes 5 and the bottom has N - 5.
	const three = bodyText(3);
	assert.ok(three.includes('The 3 bus lines with the highest on-time share.'), three);
	assert.ok(!three.includes('Least reliable'));
	assert.ok(!three.includes('lowest on-time share'));

	const five = bodyText(5);
	assert.ok(five.includes('The 5 bus lines with the highest on-time share.'), five);
	assert.ok(!five.includes('Least reliable'));

	const six = bodyText(6);
	assert.ok(six.includes('The 5 bus lines with the highest on-time share.'), six);
	assert.ok(six.includes('Least reliable'));
	assert.ok(six.includes('The 1 bus line with the lowest on-time share.'), six);

	const nine = bodyText(9);
	assert.ok(nine.includes('The 4 bus lines with the lowest on-time share.'), nine);

	const ten = bodyText(10);
	assert.ok(ten.includes('The 5 bus lines with the highest on-time share.'), ten);
	assert.ok(ten.includes('The 5 bus lines with the lowest on-time share.'), ten);
	assert.ok(!ten.includes('The 5 bus lines with the lowest on-time share, plus'));
});

test('on-time share prints one decimal and says 100.0 only for exactly 100', () => {
	assert.equal(shareText(99.96), '99.9');
	assert.equal(shareText(99.95), '99.9');
	assert.equal(shareText(99.94), '99.9');
	assert.equal(shareText(100), '100.0');
	assert.equal(shareText(85.25), '85.3');
	assert.equal(shareText(85.24), '85.2');
	assert.equal(shareText(0), '0.0');
	assert.equal(percent(99.96), '99.9%');
	assert.equal(percent(100), '100.0%');
	assert.equal(percent(85.25), '85.3%');
});

test('the line headline never says 100.0 percent unless the share is exactly 100', () => {
	const all = (ontime: number) => ({
		to: 'Downtown',
		all: { n: 1000, med: 30, p90: 200, ontime } as never
	});
	assert.match(headline(all(99.96), 0, 'bus'), /and 99\.9 percent of 1,000 measured arrivals/);
	assert.match(headline(all(100), 0, 'bus'), /and 100\.0 percent of 1,000 measured arrivals/);
	assert.match(headline(all(85.25), 0, 'bus'), /and 85\.3 percent of/);
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

test('the rail table lists the on-time share by default and not when the gate is closed', async () => {
	const RailTable = (await import('../src/routes/ranking/RailTable.svelte')).default;
	const entries = [entry('801', { mode: 'rail', label: 'Metro A Line', ontime: 56.4 })];
	const flat = (html: string) =>
		html
			.replace(/<!--.*?-->/g, '')
			.replace(/<[^>]+>/g, ' ')
			.replace(/\s+/g, ' ');
	const open = flat(render(RailTable, { props: { entries } }).body);
	assert.ok(open.includes('On time'));
	assert.ok(open.includes('56.4%'));
	assert.ok(!open.includes(RAIL_HOLD_NOTE));
	const closed = flat(render(RailTable, { props: { entries, showRailOntime: false } }).body);
	assert.ok(closed.includes(RAIL_HOLD_NOTE));
	assert.ok(!closed.includes('56.4%'));
});
