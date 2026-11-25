import type { IndexEntry } from './data/types';
import { serviceOf } from './design/service.ts';

// The index never says "Expo" for the E Line, which Metro renamed from the Expo
// Line in 2020, and riders still search for it. This is the only alias, keyed
// by the line id in index.json (804 is the E Line).
const ALIASES: Record<string, string[]> = { '804': ['expo'] };

/** A query longer than this is cut. No line name is near it. */
const MAX_QUERY = 80;
const DEFAULT_LIMIT = 8;

// Lowercase words with accents removed, so "Cañon" matches "canon".
function words(text: string): string[] {
	return text
		.normalize('NFKD')
		.replace(/[\u0300-\u036f]/g, '')
		.toLowerCase()
		.split(/[^a-z0-9]+/)
		.filter(Boolean);
}

export type Searchable = Pick<IndexEntry, 'line' | 'label' | 'mode' | 'via' | 'agency'> & {
	to: readonly string[];
};

type Fields = {
	id: string;
	label: string[];
	alias: string[];
	via: string[];
	to: string[];
	kind: string[];
};

function fieldsOf(entry: Searchable): Fields {
	const alias = [...(ALIASES[entry.line] ?? [])];
	// The index has no service word. The table of known lines is the only source.
	const service = entry.mode === 'bus' ? serviceOf(entry.line) : undefined;
	if (service) alias.push('metro', service);
	return {
		id: entry.line.toLowerCase(),
		label: words(entry.label),
		alias,
		via: words(entry.via),
		to: entry.to.flatMap(words),
		kind: [entry.mode, ...words(entry.agency)]
	};
}

// A route number or name the rider typed beats a word that appears in a
// destination, so the weights fall from the line id to the destinations. A
// one-letter token must equal a whole word, or "e" would match every word that
// starts with e.
function tokenScore(token: string, f: Fields): number {
	const prefix = token.length > 1;
	const best = (list: string[], exact: number, start: number) => {
		let score = 0;
		for (const word of list) {
			if (word === token) score = Math.max(score, exact);
			else if (prefix && word.startsWith(token)) score = Math.max(score, start);
		}
		return score;
	};
	return Math.max(
		f.id === token ? 100 : prefix && f.id.startsWith(token) ? 60 : 0,
		best(f.label, 90, 55),
		best(f.alias, 80, 50),
		best(f.via, 40, 30),
		best(f.to, 30, 20),
		best(f.kind, 10, 0)
	);
}

/**
 * The lines that match every word of the query, best first. A word matches the
 * line id, the label, the via text, the destinations, the mode or the agency.
 * Ties keep the index order. An empty query matches nothing.
 */
export function searchLines<T extends Searchable>(
	entries: T[],
	query: string,
	limit = DEFAULT_LIMIT
): T[] {
	const tokens = words(query.slice(0, MAX_QUERY));
	if (tokens.length === 0) return [];
	const ranked: { entry: T; score: number; order: number }[] = [];
	entries.forEach((entry, order) => {
		const f = fieldsOf(entry);
		let score = 0;
		for (const token of tokens) {
			const found = tokenScore(token, f);
			if (found === 0) return;
			score += found;
		}
		ranked.push({ entry, score, order });
	});
	ranked.sort((a, b) => b.score - a.score || a.order - b.order);
	return ranked.slice(0, limit).map((r) => r.entry);
}

/** The option that arrow keys move to, wrapping at both ends. */
export function moveActive(active: number, key: 'ArrowDown' | 'ArrowUp', count: number): number {
	if (count === 0) return 0;
	return (active + (key === 'ArrowDown' ? 1 : count - 1)) % count;
}
