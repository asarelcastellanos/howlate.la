// Fails when src/lib/data/types.ts no longer matches pipeline/schemas. Fix it
// with `npm run types`.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { OUTPUT, generate } from '../scripts/generate-types.mjs';

test('types.ts matches what the schemas generate', async () => {
	assert.equal(
		readFileSync(OUTPUT, 'utf8'),
		await generate(),
		'src/lib/data/types.ts is stale. Run `npm run types` and commit the result.'
	);
});

// The fields the on-time work added. A schema that lost one would still
// generate, so each must be named in the type it belongs to.
const typeBody = (name: string) => {
	const text = readFileSync(OUTPUT, 'utf8');
	const start = text.indexOf(`export interface ${name} {`);
	assert.notEqual(start, -1, `types.ts has no interface ${name}`);
	return text.slice(start, text.indexOf('\n}\n', start));
};

test('the generated types carry the on-time fields', () => {
	for (const name of ['IndexEntry', 'Hour', 'Delays', 'StopDelays', 'NetworkHour']) {
		assert.match(typeBody(name), /\bontime\b/, `${name} has no ontime`);
	}
	// Cells and a stop's all are cut for size, so the types must not bring them back.
	assert.doesNotMatch(typeBody('Cell'), /\bontime\b/, 'Cell has ontime');
	assert.doesNotMatch(typeBody('StopDelays'), /\bn:/, 'StopDelays has n');
	for (const name of ['Direction', 'Stop']) {
		assert.match(typeBody(name), /\ball\b/, `${name} has no all`);
	}
	for (const key of ['network', 'bus', 'rail']) {
		assert.match(typeBody('NetworkFile'), new RegExp(`\\b${key}\\b`), `NetworkFile has no ${key}`);
	}
});
