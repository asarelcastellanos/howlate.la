// Rewrites src/lib/data/lines.json from the published index, and the line rules in
// static/_redirects from the same list. Run `npm run lines:refresh` when Metro adds a
// line, then commit both files. The build never fetches the index,
// so it cannot fail on an unreachable one. A line missing from the list gets no
// preview in the served HTML until this runs, and it still works in the browser.
// PUBLIC_DATA_BASE picks another bucket, as it does for the site.
import { readFileSync, writeFileSync } from 'node:fs';
import { openRun } from '../src/lib/data/load.ts';
import { DEFAULT_DATA_BASE } from '../src/env.ts';
import { toListEntry } from '../src/lib/lineHead.ts';
import { withLineRules } from '../src/lib/lineRedirects.ts';

const OUTPUT = new URL('../src/lib/data/lines.json', import.meta.url);
const REDIRECTS = new URL('../static/_redirects', import.meta.url);

const base = process.env.PUBLIC_DATA_BASE ?? DEFAULT_DATA_BASE;
const run = await openRun(base);
const index = run.ok ? await run.data.index() : run;
if (!index.ok) {
	console.error(`Could not read the index from ${index.error.url} (${index.error.kind}).`);
	process.exit(1);
}

const lines = index.data.lines.map(toListEntry);
const ids = lines.map((entry) => entry.line);
const repeated = ids.filter((id, i) => ids.indexOf(id) !== i);
if (lines.length === 0 || repeated.length > 0) {
	console.error(
		`The index has ${lines.length} lines and repeats ${repeated.join(', ') || 'none'}.`
	);
	process.exit(1);
}

// Built before either write, so an id that cannot go in _redirects or a file that lost its
// markers stops the run with both files untouched.
let redirects: string;
try {
	redirects = withLineRules(readFileSync(REDIRECTS, 'utf8'), lines);
} catch (error) {
	console.error(error instanceof Error ? error.message : error);
	process.exit(1);
}

writeFileSync(OUTPUT, `${JSON.stringify(lines, null, '\t')}\n`);
writeFileSync(REDIRECTS, redirects);
console.log(
	`Wrote ${lines.length} lines from ${base} to src/lib/data/lines.json and static/_redirects`
);
