// The behind-the-scenes page. The pure parts (the stale rule, the 14-day strip,
// the check rows) run first. The rest renders the status panel and the page on
// the server. The page imports $app modules that exist only inside SvelteKit,
// so this test stands in a short replacement for each one.
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { before, describe, test } from 'node:test';
import { render } from 'svelte/server';
import { buildStrip, checkRow, failedLabel, freshness, newestDay } from '../src/lib/behind.ts';
import type { Result } from '../src/lib/data/load.ts';
import type { HealthDay, HealthFile } from '../src/lib/data/types.ts';
import { addDays, daysBetween, pacificToday, shortDate } from '../src/lib/date.ts';
import { NAV } from '../src/lib/nav.ts';

registerHooks({
	resolve(specifier, context, nextResolve) {
		const stubs: Record<string, string> = {
			'$app/paths': 'export const resolve = (path) => path;',
			'$app/state': 'export const page = { route: { id: "/behind-the-scenes" } };',
			'$app/env/public': "export const PUBLIC_DATA_BASE = '/data';"
		};
		if (!(specifier in stubs)) return nextResolve(specifier, context);
		return { url: `data:text/javascript,${stubs[specifier]}`, shortCircuit: true };
	}
});

const day = (service_date: string, ok = true, failed: string[] = []): HealthDay => ({
	service_date,
	ok,
	failed,
	coverage_pct: 81.1,
	explained_trips: 337,
	explained_pct: 1.1,
	observations: 526528
});

const health = (recent: HealthDay[], last_day = '2026-11-15'): HealthFile => ({
	pipeline_version: '0.4.1',
	last_day,
	days: 90,
	recent,
	checks: [
		{
			name: 'matched_rate',
			kind: 'range',
			label: 'observations matching a scheduled stop',
			ok: true,
			value: 99.98765,
			low: 99.9,
			high: 100
		},
		{
			name: 'absurd_pct',
			kind: 'range',
			label: 'delays beyond an hour',
			ok: false,
			value: 0.014781,
			low: 0,
			high: 0.5
		},
		{
			name: 'silent_lines',
			kind: 'count',
			label: 'lines scheduled today but never seen',
			ok: true,
			value: 0,
			expected: 0
		}
	]
});

describe('Los Angeles dates', () => {
	test('pacificToday follows the Pacific clock, not the UTC date', () => {
		assert.equal(pacificToday(new Date('2026-11-16T07:59:00Z')), '2026-11-15');
		assert.equal(pacificToday(new Date('2026-11-16T08:00:00Z')), '2026-11-16');
		// 23:59 Pacific in summer is 06:59 UTC the next day.
		assert.equal(pacificToday(new Date('2026-07-05T06:59:00Z')), '2026-07-04');
		assert.equal(pacificToday(new Date('2026-07-05T07:00:00Z')), '2026-07-05');
	});

	test('day arithmetic crosses months and a clock change', () => {
		assert.equal(addDays('2026-11-02', -13), '2026-10-20');
		assert.equal(addDays('2026-02-28', 1), '2026-03-01');
		assert.equal(daysBetween('2026-10-31', '2026-11-02'), 2);
		assert.equal(daysBetween('2026-11-02', '2026-10-31'), -2);
		assert.equal(shortDate('2026-11-05'), 'Nov 5');
	});
});

describe('the stale rule', () => {
	const today = '2026-11-16';
	test('a day graded today or yesterday is fresh', () => {
		assert.deepEqual(freshness('2026-11-16', today), { daysOld: 0, stale: false });
		assert.deepEqual(freshness('2026-11-15', today), { daysOld: 1, stale: false });
	});
	test('exactly 2 days old is normal, so it is not a warning', () => {
		assert.deepEqual(freshness('2026-11-14', today), { daysOld: 2, stale: false });
	});
	test('3 days old is a warning', () => {
		assert.deepEqual(freshness('2026-11-13', today), { daysOld: 3, stale: true });
	});
	test('a day after today is not stale', () => {
		assert.deepEqual(freshness('2026-11-17', today), { daysOld: -1, stale: false });
	});
	test('the count follows Pacific dates across a month end and a clock change', () => {
		assert.equal(freshness('2026-10-31', '2026-11-03').stale, true);
		assert.equal(freshness('2026-10-31', '2026-11-02').stale, false);
		assert.equal(freshness('2026-03-07', '2026-03-10').stale, true);
		assert.equal(freshness('2026-03-08', '2026-03-10').stale, false);
	});
});

describe('the 14-day strip', () => {
	test('has 14 cells, oldest first, ending on the newest graded day', () => {
		const recent = Array.from({ length: 14 }, (_, i) => day(addDays('2026-11-15', -i)));
		const strip = buildStrip(recent, '2026-11-15');
		assert.equal(strip.length, 14);
		assert.equal(strip[0].day, '2026-11-02');
		assert.equal(strip[13].day, '2026-11-15');
		assert.ok(strip.every((cell) => cell.state === 'ok'));
	});

	test('a day with no report is its own state, and a failed day is not missing', () => {
		const recent = [
			day('2026-11-15'),
			day('2026-11-14', false, ['absurd_pct']),
			// 11-13 and 11-12 have no report.
			day('2026-11-11')
		];
		const strip = buildStrip(recent, '2026-11-15');
		assert.equal(strip.length, 14);
		const state = (d: string) => strip.find((cell) => cell.day === d)!.state;
		assert.equal(state('2026-11-15'), 'ok');
		assert.equal(state('2026-11-14'), 'failed');
		assert.equal(state('2026-11-13'), 'none');
		assert.equal(state('2026-11-12'), 'none');
		assert.equal(state('2026-11-11'), 'ok');
		assert.equal(strip.filter((cell) => cell.state === 'none').length, 11);
	});

	test('a run with no reports is 14 empty cells', () => {
		const strip = buildStrip([], '2026-11-15');
		assert.equal(strip.length, 14);
		assert.ok(strip.every((cell) => cell.state === 'none'));
	});

	test('a report older than the window adds no cell', () => {
		const strip = buildStrip([day('2026-11-15'), day('2026-10-01')], '2026-11-15');
		assert.equal(strip.length, 14);
		assert.equal(strip.filter((cell) => cell.state !== 'none').length, 1);
	});
});

describe('check rows', () => {
	const file = health([day('2026-11-15', false, ['absurd_pct'])]);
	test('round the value, keep the label and say pass or fail', () => {
		assert.deepEqual(checkRow(file.checks[0]), {
			label: 'Observations matching a scheduled stop',
			ok: true,
			measured: '100',
			rule: 'passes from 99.9 to 100'
		});
		const small = checkRow(file.checks[1]);
		assert.equal(small.measured, '0.01');
		assert.equal(small.ok, false);
		assert.deepEqual(checkRow(file.checks[2]).rule, 'passes at 0');
	});
	test('a failed name that the file no longer lists is shown as it is', () => {
		assert.equal(failedLabel(file, 'absurd_pct'), 'delays beyond an hour');
		assert.equal(failedLabel(file, 'join_rate'), 'join_rate');
	});
	test('the newest day is the report for last_day, or nothing', () => {
		assert.equal(newestDay(file)?.service_date, '2026-11-15');
		assert.equal(newestDay(health([], '2026-11-15')), undefined);
		assert.equal(newestDay(health([day('2026-11-14')], '2026-11-15')), undefined);
	});
});

const plain = (html: string) =>
	html
		.replace(/<!--.*?-->/g, '')
		.replace(/<[^>]+>/g, ' ')
		.replace(/&[a-z]+;|&#\d+;/g, ' ')
		.replace(/\s+/g, ' ')
		.trim();

describe('the status panel', () => {
	let StatusPanel: typeof import('../src/routes/behind-the-scenes/StatusPanel.svelte').default;
	before(async () => {
		StatusPanel = (await import('../src/routes/behind-the-scenes/StatusPanel.svelte')).default;
	});
	const show = (result: Result<HealthFile>, today = '2026-11-16') =>
		render(StatusPanel, { props: { result, today } }).body;
	const ok = (file: HealthFile): Result<HealthFile> => ({ ok: true, data: file });
	const url = 'https://data.example/site/run/health.json';

	test('a file with the old shape shows the calm message, not an alert', () => {
		const html = show({ ok: false, error: { kind: 'shape', url } });
		assert.ok(plain(html).includes('Status data is not published yet.'));
		assert.doesNotMatch(html, /role="alert"/);
		assert.doesNotMatch(html, /couldn't load/);
	});

	test('a missing file shows the same calm message', () => {
		const html = show({ ok: false, error: { kind: 'status', url, status: 404 } });
		assert.ok(plain(html).includes('Status data is not published yet.'));
	});

	test('a network failure does not claim the data is unpublished', () => {
		const text = plain(show({ ok: false, error: { kind: 'network', url } }));
		assert.ok(text.includes('Status data could not be loaded'));
		assert.ok(!text.includes('not published yet'));
	});

	test('a fresh day shows the date, the result, the coverage and every check', () => {
		const recent = [day('2026-11-15'), day('2026-11-14')];
		const html = show(ok(health(recent)));
		const text = plain(html);
		assert.ok(text.includes('Newest graded day'));
		assert.ok(text.includes('November 15, 2026'));
		assert.ok(text.includes('Checked November 16, 2026'));
		assert.ok(text.includes('81.1% of scheduled stops measured'));
		assert.ok(text.includes('Observations matching a scheduled stop'));
		assert.ok(text.includes('passes from 99.9 to 100'));
		assert.equal(html.match(/data-check="/g)?.length, 3);
		assert.doesNotMatch(html, /data-warning/);
		assert.doesNotMatch(text, /\blive\b/i);
	});

	test('the strip has 14 cells, each with words, and the empty days are labelled', () => {
		const html = show(ok(health([day('2026-11-15'), day('2026-11-14', false, ['absurd_pct'])])));
		assert.equal(html.match(/data-cell="/g)?.length, 14);
		assert.equal(html.match(/data-cell="none"/g)?.length, 12);
		const text = plain(html);
		assert.ok(text.includes('November 15, 2026: passed'));
		assert.ok(text.includes('November 14, 2026: failed a check'));
		assert.ok(text.includes('November 13, 2026: no report'));
	});

	test('a failed day names its failed check in words', () => {
		const text = plain(show(ok(health([day('2026-11-15', false, ['absurd_pct'])]))));
		assert.ok(text.includes('1 check failed'));
		assert.ok(text.includes('delays beyond an hour'));
		assert.ok(!text.includes('All checks passed'));
	});

	test('2 days old shows no warning and 3 days old does', () => {
		const file = health([day('2026-11-15')]);
		assert.doesNotMatch(show(ok(file), '2026-11-17'), /data-warning/);
		const html = show(ok(file), '2026-11-18');
		assert.match(html, /data-warning/);
		const text = plain(html);
		assert.ok(text.includes('Warning'));
		assert.ok(text.includes('3 days before today'));
	});

	test('a run with no reports says so and has no checks to list', () => {
		const html = show(ok({ ...health([]), checks: [] }));
		assert.ok(plain(html).includes('No report is saved for this day.'));
		assert.equal(html.match(/data-cell="none"/g)?.length, 14);
		assert.doesNotMatch(html, /data-check="/);
	});
});

describe('the page', () => {
	let head = '';
	let body = '';
	let text = '';
	let copy = '';

	before(async () => {
		const page = (await import('../src/routes/behind-the-scenes/+page.svelte')).default;
		({ head, body } = render(page));
		text = plain(body);
		// The status panel loads in the browser, so the server renders only its
		// loading line. The count therefore holds the page's own copy.
		copy = plain(body.slice(body.indexOf('<main')));
	});

	test('has one h1, a title and a description', () => {
		assert.equal(body.match(/<h1[\s>]/g)?.length, 1);
		assert.match(head, /<title>Behind the scenes · HowLate<\/title>/);
		assert.match(head, /<meta name="description" content="[^"]{40,160}"/);
	});

	test('has an h2 for each section and no heading skips a level', () => {
		const levels = [...body.matchAll(/<h([1-6])[\s>]/g)].map((m) => Number(m[1]));
		assert.equal(levels[0], 1);
		levels.forEach((level, i) => {
			if (i > 0) assert.ok(level <= levels[i - 1] + 1, `h${level} follows h${levels[i - 1]}`);
		});
		const h2 = [...body.matchAll(/<h2[^>]*>(.*?)<\/h2>/gs)].map((m) => plain(m[1]));
		assert.deepEqual(h2, [
			'Is the data current?',
			'How it works',
			'Problems we solved',
			'What it costs',
			'Where to look'
		]);
	});

	test('uses no em dash, en dash or curly quote', () => {
		assert.doesNotMatch(head + body, /[—–‘’“”]/);
	});

	test('stays under 900 words, not counting the status panel', () => {
		const words = copy.split(' ').length;
		assert.ok(words < 900, `${words} words`);
	});

	test('the nav marks this page and the status panel starts as a loading line', () => {
		assert.match(body, /<a[^>]*aria-current="page"[^>]*>\s*Behind the scenes/);
		assert.ok(text.includes('Loading the data.'));
	});

	test('draws the architecture as a labelled image with the same flow as a list', () => {
		const svg = body.match(/<svg[^>]*role="img"[^>]*>.*?<\/svg>/s)?.[0] ?? '';
		assert.match(svg, /aria-labelledby="architecture-title architecture-desc"/);
		assert.match(svg, /<title id="architecture-title">[^<]+<\/title>/);
		assert.match(svg, /<desc id="architecture-desc">[^<]+<\/desc>/);
		const list = body.match(/<ol[^>]*data-flow[^>]*>(.*?)<\/ol>/s)?.[1] ?? '';
		assert.equal(list.match(/<li/g)?.length, 7);
		for (const label of ['Metro', 'Collector', 'Raw archive', 'Daily pipeline', 'R2']) {
			assert.ok(plain(svg).includes(label), `the image lacks ${label}`);
			assert.ok(plain(list).includes(label), `the list lacks ${label}`);
		}
	});

	test('names no bucket, host or account', () => {
		assert.doesNotMatch(body, /gs:\/\/|howlate-(raw|derived)|r2\.dev|pages\.dev|@/);
	});

	test('lists four to six problems', () => {
		const section = body.slice(body.indexOf('Problems we solved'), body.indexOf('What it costs'));
		const items = section.match(/<p[^>]*>\s*<strong>.*?<\/p>/gs) ?? [];
		assert.ok(items.length >= 4 && items.length <= 6, `${items.length} problems`);
	});

	test('gives the budget as an estimate, with no $2 and no invented breakdown', () => {
		const section = plain(body.slice(body.indexOf('What it costs'), body.indexOf('Where to look')));
		assert.ok(section.includes('about $5 a month'));
		assert.ok(section.includes('estimate, not a bill'));
		assert.ok(section.includes('once billing is reviewed'));
		assert.doesNotMatch(text, /\$2\b/);
		assert.equal(section.match(/\$\d/g)?.length, 1);
	});

	test('links the repository', () => {
		assert.match(body, /href="https:\/\/github\.com\/asarelcastellanos\/howlate\.la"/);
	});
});

describe('the navigation', () => {
	test('lists Behind the scenes as ready, so it is drawn', () => {
		const entry = NAV.find((item) => item.path === '/behind-the-scenes');
		assert.equal(entry?.ready, true);
		assert.ok(NAV.every((item) => item.ready));
	});
});
