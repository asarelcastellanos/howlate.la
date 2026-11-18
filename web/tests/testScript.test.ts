// A typo in the `test` script once fused two filenames, and node skipped both
// files without a word. This holds the script to the folder, in both directions.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { test } from 'node:test';

const root = new URL('../', import.meta.url);
const { scripts } = JSON.parse(readFileSync(new URL('package.json', root), 'utf8')) as {
	scripts: Record<string, string>;
};
const named = `${scripts.test} ${scripts.postbuild}`
	.split(/\s+/)
	.filter((word) => word.startsWith('tests/'));

test('every test file the scripts name exists', () => {
	const onDisk = new Set(readdirSync(new URL('tests/', root)).map((name) => `tests/${name}`));
	for (const file of named) assert.ok(onDisk.has(file), `${file} is named but does not exist`);
});

test('every test file in the folder is named by a script', () => {
	const listed = new Set(named);
	const tests = readdirSync(new URL('tests/', root)).filter((name) => name.endsWith('.test.ts'));
	for (const name of tests) assert.ok(listed.has(`tests/${name}`), `tests/${name} never runs`);
});
