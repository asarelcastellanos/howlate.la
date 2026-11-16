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
