import type { LineListEntry } from './lineHead.ts';

export const BEGIN = '# BEGIN line pages (written by npm run lines:refresh, do not edit)';
export const END = '# END line pages';

// A _redirects rule is split on spaces, and `*`, `:` and `#` mean something in it. Every
// id in the 2026-11-17 index is letters and digits. Anything else would need quoting
// that Pages does not offer, so the refresh stops and says which id.
const SAFE_ID = /^[A-Za-z0-9_-]+$/;

/** One proxy rule per line, to the file the build wrote for it. */
export const lineRule = (id: string): string => `/lines/${id} /lines/${id}.html 200`;

/**
 * Puts one rule per listed line between the markers in `_redirects` and leaves every
 * other line alone. Cloudflare Pages follows a redirect rule even when a file matches
 * the path, so the wildcard `/lines/* /200 200` alone sends a prerendered line to the
 * app shell (a preview served /lines/720 and /lines/zzz the same 1,508 bytes, no
 * title). The first matching rule wins and a proxy target is not matched again, so
 * these rules have to come before the wildcard.
 */
export function withLineRules(file: string, list: readonly LineListEntry[]): string {
	const unsafe = list.filter((entry) => !SAFE_ID.test(entry.line));
	if (unsafe.length > 0) {
		throw new Error(
			`These line ids cannot go in _redirects: ${unsafe.map((e) => e.line).join(', ')}`
		);
	}
	const lines = file.split('\n');
	const begin = lines.indexOf(BEGIN);
	const end = lines.indexOf(END);
	if (begin === -1 || end < begin) {
		throw new Error(`static/_redirects needs the lines "${BEGIN}" and "${END}"`);
	}
	return [
		...lines.slice(0, begin + 1),
		...list.map((entry) => lineRule(entry.line)),
		...lines.slice(end)
	].join('\n');
}
