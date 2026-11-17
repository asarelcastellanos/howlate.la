import { readFileSync } from 'node:fs';
import type { CurrentPointer, LineFile, SiteIndex } from '../src/lib/data/types.ts';

// The fixture folder stands in for the bucket root, so the pointer's prefix is
// read the way the site reads it. Tests take every expected value from here.
const root = new URL('./fixture/', import.meta.url);
const read = <T>(path: string): T => JSON.parse(readFileSync(new URL(path, root), 'utf8'));

const pointer = read<CurrentPointer>('site/current.json');

export const index = read<SiteIndex>(`${pointer.prefix}index.json`);
export const readLine = (id: string) => read<LineFile>(`${pointer.prefix}lines/${id}.json`);
