// The line files of the local copy of the site's data, for tests that check a
// chart against real numbers. The copy is git-ignored (see web/README.md), so a
// checkout without it skips those tests. A copy that is present but incomplete
// fails them.
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import type { LineFile } from '../src/lib/data/types.ts';

const root = new URL('../static/data/', import.meta.url);

export const hasRealData = existsSync(new URL('site/current.json', root));

const read = (path: string) => JSON.parse(readFileSync(new URL(path, root), 'utf8'));

export function realLines(): Map<string, LineFile> {
	const { prefix } = read('site/current.json') as { prefix: string };
	const dir = new URL(`${prefix}lines/`, root);
	return new Map(
		readdirSync(dir).map((name) => [name.replace(/\.json$/, ''), read(`${prefix}lines/${name}`)])
	);
}
