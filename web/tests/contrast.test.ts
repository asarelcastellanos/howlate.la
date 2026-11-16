// Run with `npm test`. Node 22.18 or newer runs the .ts files directly.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { RAMP, pairs, parseTokens, ratio } from '../src/lib/design/contrast.ts';
import { LINES } from '../src/lib/design/lines.ts';

const css = readFileSync(new URL('../src/routes/layout.css', import.meta.url), 'utf8');
const tokens = parseTokens(css);
const results = pairs(tokens, LINES);

test('every color pair the site uses meets WCAG AA', () => {
	const report = results.map((r) => ({
		pair: r.name,
		theme: r.theme,
		need: r.kind,
		ratio: r.ratio.toFixed(2),
		pass: r.pass
	}));
	console.table(report);
	const failed = results.filter((r) => !r.pass);
	assert.deepEqual(
		failed.map((r) => `${r.name} (${r.theme}) ${r.ratio.toFixed(2)}:1 needs ${r.kind}`),
		[]
	);
});

test('every pair is made of hex colors, so none was silently skipped', () => {
	for (const r of results) {
		assert.match(r.fg, /^#[0-9a-f]{6}$/i, `${r.name} foreground is ${r.fg}`);
		assert.match(r.bg, /^#[0-9a-f]{6}$/i, `${r.name} background is ${r.bg}`);
	}
});

test('--line-* in layout.css matches the mark colors in lines.ts', () => {
	for (const theme of ['light', 'dark'] as const) {
		for (const line of LINES) {
			assert.equal(
				tokens[theme][`--line-${line.id}`]?.toLowerCase(),
				line.mark[theme].toLowerCase(),
				`${line.name} ${theme}`
			);
		}
	}
});

test('the delay ramp gets stronger against the page at every step', () => {
	for (const theme of ['light', 'dark'] as const) {
		const steps = RAMP.map((name) => ratio(tokens[theme][name], tokens[theme]['--paper']));
		steps.slice(1).forEach((step, i) => assert.ok(step > steps[i], `${theme} step ${i + 2}`));
	}
});
