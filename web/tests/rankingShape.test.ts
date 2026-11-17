// The live bucket holds the old index shape until the next daily run after
// release. A page that reads a missing field throws, and Cloudflare then shows
// its own 500 page. These tests hold the page to the site's error box instead.
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { before, test } from 'node:test';
import { render } from 'svelte/server';
import { openRun } from '../src/lib/data/load.ts';
import type { IndexEntry, SiteIndex } from '../src/lib/data/types.ts';
import { readRankingIndex } from '../src/lib/data/read.ts';
import { checkRankingIndex } from '../src/lib/ranking.ts';

registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier !== '$app/paths') return nextResolve(specifier, context);
		return {
			url: 'data:text/javascript,export const resolve = (path) => path;',
			shortCircuit: true
		};
	}
});

const entry: IndexEntry = {
	line: '720',
	agency: 'LACMTA',
	label: '720',
	via: 'Wilshire Blvd',
	mode: 'bus',
	n: 1200,
	sched: 2000,
	med: 90,
	p90: 540,
	pct5: 21.4,
	ontime: 61.2,
	to: ['Santa Monica', 'Commerce']
};
const index: SiteIndex = {
	first_day: '2026-08-18',
	last_day: '2026-11-14',
	days: 89,
	lines: [entry]
};

// The shape the bucket holds today: no n, med, p90, pct5 or ontime.
function oldShape(): unknown {
	const { line, agency, label, via, mode, sched, to } = entry;
	return { ...index, lines: [{ line, agency, label, via, mode, sched, to }] };
}

const URL_ = 'https://data.example/site/runs/r1/index.json';

test('a current index passes the check unchanged', () => {
	assert.deepEqual(checkRankingIndex(index, URL_), { ok: true, data: index });
});

test('an index in the old shape is a shape error, not a throw', () => {
	const result = checkRankingIndex(oldShape(), URL_);
	assert.deepEqual(result, { ok: false, error: { kind: 'shape', url: URL_ } });
});

test('each field the page reads is checked on its own', () => {
	for (const field of ['n', 'med', 'p90', 'pct5', 'ontime'] as const) {
		const missing = { ...index, lines: [{ ...entry, [field]: undefined }] };
		assert.equal(checkRankingIndex(missing, URL_).ok, false, `${field} missing`);
		const text = { ...index, lines: [{ ...entry, [field]: '61.2' }] };
		assert.equal(checkRankingIndex(text, URL_).ok, false, `${field} as text`);
	}
	const second = { ...index, lines: [entry, { ...entry, line: '4', ontime: null }] };
	assert.equal(checkRankingIndex(second, URL_).ok, false, 'a later entry');
});

test('a body that is not an index never throws', () => {
	for (const body of [
		null,
		undefined,
		7,
		'text',
		[],
		{},
		{ lines: null },
		{ ...index, lines: [null] }
	]) {
		assert.deepEqual(checkRankingIndex(body, URL_), {
			ok: false,
			error: { kind: 'shape', url: URL_ }
		});
	}
});

function stubFetch(indexBody: unknown): typeof fetch {
	return async (input) => {
		const url = String(input);
		const body = url.endsWith('current.json')
			? { run: 'r1', prefix: 'site/runs/r1/', files: 1, previous: [] }
			: indexBody;
		return new Response(JSON.stringify(body), { status: 200 });
	};
}

test('reading an old-shape index through the loader gives the shape error', async () => {
	const result = await readRankingIndex('https://data.example/', stubFetch(oldShape()));
	assert.deepEqual(result, { ok: false, error: { kind: 'shape', url: URL_ } });
	const good = await readRankingIndex('https://data.example/', stubFetch(index));
	assert.equal(good.ok, true);
});

test('a failed request still comes back as its own error kind', async () => {
	const result = await readRankingIndex(
		'https://data.example/',
		async () => new Response('', { status: 404 })
	);
	assert.equal(!result.ok && result.error.kind, 'status');
	assert.equal((await openRun('https://data.example/', stubFetch(index))).ok, true);
});

let shapeView = '';

before(async () => {
	const ResultView = (await import('../src/lib/charts/ResultView.svelte')).default;
	const error = { kind: 'shape', url: URL_ } as const;
	shapeView = render(ResultView, {
		props: { result: { ok: false, error }, onretry: () => {}, children: () => {} }
	}).body;
});

test('the shape error shows the newer-data message with a retry button', () => {
	assert.match(
		shapeView,
		/This page needs newer data than the site has yet\. Try again in a few minutes\./
	);
	assert.match(shapeView, /role="alert"/);
	assert.match(shapeView, /Try again<\/button>/);
});
