// The loader with fetch stubbed. Fixtures follow the shapes in pipeline/schemas.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { openRun, type Result } from '../src/lib/data/load.ts';
import { loadLinePage } from '../src/lib/linePage.ts';
import { readNetwork } from '../src/lib/data/read.ts';
import type {
	CurrentPointer,
	LineFile,
	NetworkFile,
	SiteIndex,
	SiteStatus
} from '../src/lib/data/types.ts';

const BASE = 'https://data.example/';
const PREFIX = 'site/runs/20261115T100000Z-a1b2c3/';

const pointer: CurrentPointer = {
	run: '20261115T100000Z-a1b2c3',
	prefix: PREFIX,
	files: 4,
	previous: ['20261114T100000Z-d4e5f6']
};
const index: SiteIndex = {
	first_day: '2026-08-18',
	last_day: '2026-11-14',
	days: 53,
	lines: [
		{
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
		}
	]
};
const status: SiteStatus = {
	first_day: '2026-08-18',
	last_day: '2026-11-14',
	days: 53,
	scheduled_stops: 2000,
	measured_arrivals: 1200,
	coverage_pct: 60,
	lines: 114,
	trips: 900
};
const line: LineFile = {
	line: '720',
	agency: 'LACMTA',
	label: '720',
	via: 'Wilshire Blvd',
	mode: 'bus',
	first_day: '2026-08-18',
	last_day: '2026-11-14',
	days: 53,
	directions: [
		{
			id: 0,
			to: 'Santa Monica',
			n: 600,
			sched: 1000,
			all: { n: 600, med: 80, p90: 420, pct5: 14.2, ontime: 70.5 },
			profile: [{ h: 8, n: 50, sched: 80, med: 60, p90: 400, pct5: 12.5, ontime: 75 }],
			stops: [
				{
					id: '100',
					name: 'Wilshire / Vermont',
					lat: null,
					lon: null,
					seq: 1,
					n: 10,
					sched: 20,
					all: { med: 30, p90: 300, pct5: 5, ontime: 80 },
					cells: [{ d: 'wk-am', n: 10, sched: 20, med: 30, p90: 300, pct5: 5 }]
				}
			]
		}
	]
};

// Rail has no measured arrival here, which is how the file shows an empty mode.
const empty = { n: 0, med: null, p90: null, pct5: null, ontime: null };
const network: NetworkFile = {
	network: {
		all: { n: 1200, med: 90, p90: 540, pct5: 21.4, ontime: 61.2 },
		profile: [{ h: 8, n: 50, sched: 80, med: 60, p90: 400, pct5: 12.5, ontime: 75 }]
	},
	bus: {
		all: { n: 1200, med: 90, p90: 540, pct5: 21.4, ontime: 61.2 },
		profile: [{ h: 8, n: 50, sched: 80, med: 60, p90: 400, pct5: 12.5, ontime: 75 }]
	},
	rail: { all: empty, profile: [] }
};

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200 });

// Answers each URL from `files`, and 404 for any other.
const stub =
	(files: Record<string, Response>) =>
	async (url: string | URL | Request): Promise<Response> =>
		files[String(url)]?.clone() ?? new Response('not found', { status: 404 });

const published = (): Record<string, Response> => ({
	'https://data.example/site/current.json': json(pointer),
	[`https://data.example/${PREFIX}index.json`]: json(index),
	[`https://data.example/${PREFIX}status.json`]: json(status),
	[`https://data.example/${PREFIX}lines/720.json`]: json(line),
	[`https://data.example/${PREFIX}network.json`]: json(network)
});

function unwrap<T>(result: Result<T>): T {
	assert.ok(result.ok, `expected data, got ${JSON.stringify(!result.ok && result.error)}`);
	return result.data;
}

test('reads the pointer first, then every file from the run it names', async () => {
	const urls: string[] = [];
	const files = published();
	const fetchFn = async (url: string | URL | Request) => {
		urls.push(String(url));
		return stub(files)(url);
	};
	const run = unwrap(await openRun(BASE, fetchFn));
	assert.deepEqual(run.pointer, pointer);
	assert.deepEqual(unwrap(await run.index()), index);
	assert.deepEqual(unwrap(await run.status()), status);
	assert.deepEqual(unwrap(await run.line('720')), line);
	assert.deepEqual(unwrap(await run.network()), network);
	assert.deepEqual(urls, [
		'https://data.example/site/current.json',
		`https://data.example/${PREFIX}index.json`,
		`https://data.example/${PREFIX}status.json`,
		`https://data.example/${PREFIX}lines/720.json`,
		`https://data.example/${PREFIX}network.json`
	]);
});

test('a 404 for the pointer is an error result', async () => {
	const result = await openRun(BASE, stub({}));
	assert.deepEqual(result, {
		ok: false,
		error: { kind: 'status', url: 'https://data.example/site/current.json', status: 404 }
	});
});

test('a 404 for a run file is an error result, and the pointer still loads', async () => {
	const files = published();
	delete files[`https://data.example/${PREFIX}status.json`];
	const run = unwrap(await openRun(BASE, stub(files)));
	const result = await run.status();
	assert.ok(!result.ok && result.error.kind === 'status' && result.error.status === 404);
	assert.ok((await run.index()).ok);
});

test('a network failure is an error result, not a throw', async () => {
	const fetchFn = async () => {
		throw new TypeError('Failed to fetch');
	};
	const result = await openRun(BASE, fetchFn);
	assert.ok(!result.ok && result.error.kind === 'network');
});

test('a body that is not JSON is an error result', async () => {
	const files = published();
	files[`https://data.example/${PREFIX}index.json`] = new Response('<html>oops</html>', {
		status: 200
	});
	const run = unwrap(await openRun(BASE, stub(files)));
	const result = await run.index();
	assert.ok(!result.ok && result.error.kind === 'json');
});

test('a pointer that is not JSON is an error result', async () => {
	const files = published();
	files['https://data.example/site/current.json'] = new Response('', { status: 200 });
	const result = await openRun(BASE, stub(files));
	assert.ok(!result.ok && result.error.kind === 'json');
});

test('network.json errors are values too', async () => {
	const files = published();
	delete files[`https://data.example/${PREFIX}network.json`];
	const run = unwrap(await openRun(BASE, stub(files)));
	const missing = await run.network();
	assert.ok(!missing.ok && missing.error.kind === 'status' && missing.error.status === 404);

	files[`https://data.example/${PREFIX}network.json`] = new Response('<html>', { status: 200 });
	const broken = await unwrap(await openRun(BASE, stub(files))).network();
	assert.ok(!broken.ok && broken.error.kind === 'json');
});

test('readNetwork opens the run, then reads network.json from it', async () => {
	const realFetch = globalThis.fetch;
	globalThis.fetch = stub(published()) as typeof fetch;
	try {
		assert.deepEqual(unwrap(await readNetwork(BASE)), network);
	} finally {
		globalThis.fetch = realFetch;
	}
});

// The live bucket holds the old line shape until the first daily run after a
// release, so a page can meet files without the new fields. The loader must
// turn that into a value the page can show, never data the page then trips on.
const clone = <T>(value: T): T => structuredClone(value);
const oldLine = (): unknown => {
	const file = clone(line) as unknown as {
		directions: { all?: unknown; profile: { ontime?: number }[] }[];
	};
	for (const direction of file.directions) {
		delete direction.all;
		for (const hour of direction.profile) delete hour.ontime;
	}
	return file;
};
const lineUrl = `https://data.example/${PREFIX}lines/720.json`;
const withLine = (body: unknown) => ({ ...published(), [lineUrl]: json(body) });

test('a line file in the old shape is a shape error, not data and not a throw', async () => {
	const run = unwrap(await openRun(BASE, stub(withLine(oldLine()))));
	assert.deepEqual(await run.line('720'), { ok: false, error: { kind: 'shape', url: lineUrl } });
});

test('a line file that is missing a field the page reads is a shape error', async () => {
	const edits: [string, (file: LineFile) => void][] = [
		['no directions', (f) => (f.directions = [])],
		['no all', (f) => delete f.directions[0].all],
		['med is text', (f) => (f.directions[0].all.med = '80')],
		['no p90', (f) => delete f.directions[0].all.p90],
		['no n', (f) => delete f.directions[0].all.n],
		['no ontime in all', (f) => delete f.directions[0].all.ontime],
		['no profile', (f) => delete f.directions[0].profile],
		['an hour without ontime', (f) => delete f.directions[0].profile[0].ontime],
		['no stops', (f) => delete f.directions[0].stops],
		['a stop without all', (f) => delete f.directions[0].stops[0].all],
		['a stop without cells', (f) => delete f.directions[0].stops[0].cells],
		['no label', (f) => delete f.label]
	];
	for (const [name, edit] of edits) {
		const file = clone(line);
		edit(file);
		const run = unwrap(await openRun(BASE, stub(withLine(file))));
		const result = await run.line('720');
		assert.ok(!result.ok && result.error.kind === 'shape', name);
	}
	for (const body of [null, [], 7, 'text', {}]) {
		const run = unwrap(await openRun(BASE, stub(withLine(body))));
		const result = await run.line('720');
		assert.ok(!result.ok && result.error.kind === 'shape', JSON.stringify(body));
	}
});

test('a stop with no measured arrival keeps null numbers and still passes', async () => {
	const file = clone(line);
	file.directions[0].stops[0].all = { med: null, p90: null, pct5: null, ontime: null };
	const run = unwrap(await openRun(BASE, stub(withLine(file))));
	assert.ok((await run.line('720')).ok);
});

test('an index or status file that lacks what the pages read is a shape error', async () => {
	const files = published();
	const noTo = clone(index) as unknown as { lines: Record<string, unknown>[] };
	delete noTo.lines[0].to;
	files[`https://data.example/${PREFIX}index.json`] = json(noTo);
	files[`https://data.example/${PREFIX}status.json`] = json({ days: 53 });
	const run = unwrap(await openRun(BASE, stub(files)));
	const bad = await run.index();
	assert.ok(!bad.ok && bad.error.kind === 'shape');
	const badStatus = await run.status();
	assert.ok(!badStatus.ok && badStatus.error.kind === 'shape');
});

test('the line page load returns the shape error for an old file, and still finds a missing line', async () => {
	const old = await loadLinePage(BASE, '720', stub(withLine(oldLine())));
	assert.deepEqual(old, { ok: false, error: { kind: 'shape', url: lineUrl } });
	// Not found keeps working: an id the index lacks, and a line file that is 404.
	assert.deepEqual(await loadLinePage(BASE, 'zzz', stub(published())), {
		ok: true,
		data: { kind: 'missing' }
	});
	const gone = published();
	delete gone[lineUrl];
	assert.deepEqual(await loadLinePage(BASE, '720', stub(gone)), {
		ok: true,
		data: { kind: 'missing' }
	});
	const good = await loadLinePage(BASE, '720', stub(published()));
	assert.ok(good.ok && good.data.kind === 'found');
});
