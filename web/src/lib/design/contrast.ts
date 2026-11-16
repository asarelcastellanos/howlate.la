// WCAG contrast math and the list of color pairs the site uses. The test in
// tests/contrast.test.ts and the specimen page both read this file, so a pair
// added here is checked and shown in one step.

import type { Line } from './lines';

export type Theme = 'light' | 'dark';
export type Tokens = Record<Theme, Record<string, string>>;
// The WCAG AA minimum for each kind of pair.
export const MINIMUM = { text: 4.5, large: 3, mark: 3 } as const;
export type Kind = keyof typeof MINIMUM;
export type Pair = { name: string; kind: Kind; theme: Theme | 'both'; fg: string; bg: string };
export type Result = Pair & { ratio: number; pass: boolean };

function block(css: string, header: string): string {
	const start = css.indexOf(header);
	if (start < 0) throw new Error(`layout.css has no "${header}" block`);
	let depth = 0;
	for (let i = css.indexOf('{', start); i < css.length; i++) {
		if (css[i] === '{') depth++;
		if (css[i] === '}' && --depth === 0) return css.slice(css.indexOf('{', start) + 1, i);
	}
	throw new Error(`"${header}" block is not closed`);
}

function declarations(body: string): Record<string, string> {
	const found = body.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g);
	return Object.fromEntries([...found].map(([, name, value]) => [name, value.trim()]));
}

/** Reads the two token blocks in layout.css and resolves var() references. */
export function parseTokens(css: string): Tokens {
	const light = declarations(block(css, ':root {'));
	const dark = {
		...light,
		...declarations(block(block(css, '@media (prefers-color-scheme: dark) {'), ':root {'))
	};
	const resolve = (all: Record<string, string>) =>
		Object.fromEntries(
			Object.keys(all).map((name) => {
				let value = all[name];
				for (
					let m = value.match(/^var\((--[\w-]+)\)$/);
					m;
					m = value.match(/^var\((--[\w-]+)\)$/)
				) {
					value = all[m[1]];
				}
				return [name, value];
			})
		);
	return { light: resolve(light), dark: resolve(dark) };
}

function luminance(hex: string): number {
	const [r, g, b] = [1, 3, 5].map((i) => {
		const v = parseInt(hex.slice(i, i + 2), 16) / 255;
		return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
	});
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function ratio(a: string, b: string): number {
	const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
}

export const RAMP = ['--delay-1', '--delay-2', '--delay-3', '--delay-4', '--delay-5'];

/** Every pair the site uses, in both themes. */
export function pairs(tokens: Tokens, lines: readonly Line[]): Result[] {
	const out: Pair[] = [];
	for (const theme of ['light', 'dark'] as const) {
		const t = tokens[theme];
		const on = (name: string, kind: Kind, fg: string, bg = t['--paper']) =>
			out.push({ name, kind, theme, fg, bg });
		on('Body text on paper', 'text', t['--ink']);
		on('Muted text on paper', 'text', t['--ink-muted']);
		on('Link on paper', 'text', t['--link']);
		on('Chart axis labels on paper', 'text', t['--chart-axis']);
		on('Chart ink on paper', 'text', t['--chart-ink']);
		on('Chart annotation on paper', 'text', t['--chart-annotation']);
		on('Focus ring on paper', 'mark', t['--focus']);
		on('Rapid bus bullet letter, paper on ink', 'large', t['--paper'], t['--ink']);
		for (const line of lines) {
			on(`${line.name} mark on paper`, 'mark', t[`--line-${line.id}`]);
		}
		RAMP.forEach((name, i) => on(`Delay step ${i + 1} on paper`, 'mark', t[name]));
	}
	// The bullet keeps Metro's raw colors in both themes.
	for (const line of lines) {
		out.push({
			name: `${line.name} bullet letter`,
			kind: 'large',
			theme: 'both',
			fg: line.textColor,
			bg: line.color
		});
	}
	return out.map((p) => {
		const r = ratio(p.fg, p.bg);
		return { ...p, ratio: r, pass: r >= MINIMUM[p.kind] };
	});
}
