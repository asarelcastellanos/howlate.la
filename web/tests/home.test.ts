// The home page reads the status strip and the search list. Both must come
// from the run that one current.json read names, even if the pointer moves.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { loadHome } from '../src/lib/home.ts';

const BASE = 'https://data.example';
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });
const run = (name: string) => `site/runs/${name}/`;

// Serves current.json from `pointers` in order, one per request, and each run's
// files tagged with the run's name so a mix shows in the result.
function moving(pointers: string[], missing: string[] = []) {
	const urls: string[] = [];
	let reads = 0;
	const fetchFn = async (input: string | URL | Request) => {
		const url = String(input);
		urls.push(url);
		if (url === `${BASE}/site/current.json`) {
			const name = pointers[Math.min(reads++, pointers.length - 1)];
			return json({ run: name, prefix: run(name), files: 4, previous: [] });
		}
		const [, name, file] = /site\/runs\/([^/]+)\/(.+)$/.exec(url) ?? [];
		if (missing.includes(file)) return new Response('', { status: 404 });
		return json(
			file === 'status.json'
				? { run: name, last_day: '2026-11-14', days: 1, measured_arrivals: 5, coverage_pct: 50 }
				: { run: name, lines: [] }
		);
	};
	return { fetchFn: fetchFn as typeof fetch, urls };
}

test('the status and the index come from one run when the pointer moves between reads', async () => {
	const { fetchFn, urls } = moving(['run-a', 'run-b']);
	const result = await loadHome(BASE, fetchFn);
	assert.ok(result.ok);
	assert.deepEqual(
		{
			status: (result.data.status as { run?: string }).run,
			index: (result.data.index as { run?: string }).run
		},
		{ status: 'run-a', index: 'run-a' }
	);
	assert.equal(urls.filter((url) => url.endsWith('/site/current.json')).length, 1);
	assert.deepEqual(urls.slice(1).sort(), [
		`${BASE}/site/runs/run-a/index.json`,
		`${BASE}/site/runs/run-a/status.json`
	]);
});

test('a missing file in the run is an error value, not a throw', async () => {
	const { fetchFn } = moving(['run-a'], ['status.json']);
	const result = await loadHome(BASE, fetchFn);
	assert.ok(!result.ok && result.error.kind === 'status');
});
