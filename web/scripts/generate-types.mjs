// Writes src/lib/data/types.ts from the JSON Schemas in ../pipeline/schemas.
// Run `npm run types`. tests/types.test.ts imports generate() and fails when
// the committed file differs from what this produces.
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { compile } from 'json-schema-to-typescript';

const SCHEMAS = new URL('../../pipeline/schemas/', import.meta.url);
export const OUTPUT = new URL('../src/lib/data/types.ts', import.meta.url);

// The type each schema file becomes, and a name for each $defs entry whose key
// is too vague to read on its own in the site code.
const ROOTS = {
	'current.schema.json': 'CurrentPointer',
	'index.schema.json': 'SiteIndex',
	'line.schema.json': 'LineFile',
	'status.schema.json': 'SiteStatus'
};
const DEFS = { entry: 'IndexEntry' };

const HEADER = `// Generated from ../../../../pipeline/schemas by scripts/generate-types.mjs.
// Do not edit. Run \`npm run types\` in web/ to regenerate it, and commit the
// result in the same PR as the schema change.
`;

// The library names a type after the schema title and takes its comment from
// the description. Fold the title and $id into the description so the
// JSDoc keeps them, and put the wanted type name in the title.
function prepare(schema, name) {
	const { title, $id, description, $defs = {} } = schema;
	const defs = Object.fromEntries(
		Object.entries($defs).map(([key, def]) => [
			key,
			{ ...def, title: DEFS[key] ?? capitalise(key) }
		])
	);
	return {
		...schema,
		title: name,
		description: `${title}. ${description}\n\n@see ${$id}`,
		$defs: defs
	};
}

const capitalise = (key) => key[0].toUpperCase() + key.slice(1);

export async function generate() {
	// A schema with no entry in ROOTS would get no type and break nothing, so
	// fail here instead.
	const files = readdirSync(SCHEMAS).filter((f) => f.endsWith('.schema.json'));
	const missing = files.filter((f) => !(f in ROOTS));
	if (missing.length) throw new Error(`Name a type for ${missing.join(', ')} in ROOTS.`);
	const parts = [HEADER];
	for (const file of Object.keys(ROOTS).sort()) {
		const schema = JSON.parse(readFileSync(new URL(file, SCHEMAS), 'utf8'));
		parts.push(
			await compile(prepare(schema, ROOTS[file]), ROOTS[file], {
				bannerComment: '',
				additionalProperties: false,
				// Matches .prettierrc, so `npm run lint` accepts the output.
				style: { useTabs: true, singleQuote: true, trailingComma: 'none', printWidth: 100 }
			})
		);
	}
	return parts.join('\n');
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
	writeFileSync(OUTPUT, await generate());
}
