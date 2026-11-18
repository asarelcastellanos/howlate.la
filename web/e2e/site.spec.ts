import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';
import { MIN_RANKED_ARRIVALS } from '../src/lib/ranking.ts';
import { longDate } from '../src/lib/date.ts';
import { health, index, readLine } from './fixture.ts';
import { lineLoaded, watchConsole } from './helpers.ts';

// A fixture that lost its lines would let every loop below pass without a visit.
const MIN_LINES = 8;
const entries = index.lines;
const FRIDAY_5PM = 4 * 24 + 17;

test('the fixture holds the shapes the release plan names', () => {
	expect(entries.length).toBeGreaterThanOrEqual(MIN_LINES);
	const directions = entries.map((entry) => readLine(entry.line).directions.length);
	expect(directions).toContain(1);
	expect(directions).toContain(2);
	expect(entries.some((entry) => entry.mode === 'rail')).toBe(true);
	expect(entries.some((entry) => entry.mode === 'bus' && entry.n < MIN_RANKED_ARRIVALS)).toBe(true);
	// 720 is the line the search, ranking and Friday 5 pm tests below name.
	expect(entries.map((entry) => entry.line)).toContain('720');
});

for (const entry of entries) {
	test(`line ${entry.line} loads at 375 px without errors`, async ({ page }) => {
		const line = readLine(entry.line);
		const problems = watchConsole(page);
		await page.goto(`/lines/${entry.line}`);
		await expect(lineLoaded(page)).toBeVisible();
		await page.waitForLoadState('networkidle');

		const text = await page.locator('body').innerText();
		for (const message of ["We couldn't load", 'needs newer data', 'We could not find']) {
			expect(text, `the page shows "${message}"`).not.toContain(message);
		}
		await expect(page.locator('h1')).toHaveCount(1);
		await expect(page.locator('h1')).toContainText(entry.label);
		await expect.poll(() => page.locator('figure').count()).toBeGreaterThanOrEqual(4);

		// The switch exists only when there is a second direction to switch to.
		const switchGroup = page.getByRole('group', { name: 'Show the charts for' });
		await expect(switchGroup).toHaveCount(line.directions.length === 2 ? 1 : 0);
		if (line.directions.length === 2) await expect(switchGroup.getByRole('radio')).toHaveCount(2);

		const { scrollWidth, clientWidth } = await page.evaluate(() => ({
			scrollWidth: document.documentElement.scrollWidth,
			clientWidth: document.documentElement.clientWidth
		}));
		expect(scrollWidth, 'the page scrolls sideways').toBeLessThanOrEqual(clientWidth);
		expect(problems).toEqual([]);
	});
}

// A line outside src/lib/data/lines.json is not prerendered, so `vite preview` answers 404 for
// it. Cloudflare Pages answers with the app shell instead, and this route does the same.
test('an unknown line shows the not-found message', async ({ page }) => {
	const shell = readFileSync(new URL('../build/200.html', import.meta.url), 'utf8');
	await page.route('**/lines/zzz', (route) =>
		route.request().resourceType() === 'document'
			? route.fulfill({ status: 200, contentType: 'text/html', body: shell })
			: route.continue()
	);
	await page.goto('/lines/zzz');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('We could not find that line');
});

test('typing 720 in the search lists it and Enter opens its page', async ({ page }) => {
	const entry = entries.find((e) => e.line === '720')!;
	await page.goto('/');
	const search = page.getByRole('combobox', { name: 'Find a line' });
	await search.fill(entry.line);
	await expect(page.getByRole('option', { name: new RegExp(entry.label) })).toBeVisible();
	await search.press('Enter');
	await expect(page).toHaveURL(`/lines/${entry.line}`);
});

test('the ranking links every ranked bus line and the unranked and rail lines', async ({
	page
}) => {
	await page.goto('/ranking');
	const ranked = new Set(
		entries
			.filter((e) => e.mode === 'bus' && e.n >= MIN_RANKED_ARRIVALS)
			.map((e) => `/lines/${e.line}`)
	);
	const rows = page.getByRole('region', { name: /Ranked bus lines/ }).locator('tbody tr a');
	await expect(rows.first()).toBeVisible();
	const inTable = await rows.evaluateAll((links) => links.map((a) => a.getAttribute('href')));
	expect(new Set(inTable)).toEqual(ranked);
	expect(inTable).toHaveLength(ranked.size);

	const everyLink = await page
		.locator('main a[href^="/lines/"]')
		.evaluateAll((links) => links.map((a) => a.getAttribute('href')));
	expect(new Set(everyLink)).toEqual(new Set(entries.map((e) => `/lines/${e.line}`)));
});

// The readout words a delay in seconds under two minutes and in whole minutes above.
const delay = (seconds: number) => {
	const size = Math.abs(seconds);
	const [amount, unit] = size < 120 ? [size, 'second'] : [Math.round(size / 60), 'minute'];
	return `${amount} ${unit}${amount === 1 ? '' : 's'} ${seconds < 0 ? 'early' : 'late'}`;
};

test('three taps from the home page reach the Friday 5 pm readout on line 720', async ({
	page
}) => {
	const entry = entries.find((e) => e.line === '720')!;
	const hour = readLine(entry.line).directions[0].profile.find((h) => h.h === FRIDAY_5PM)!;
	expect(hour, 'the fixture has no Friday 5 pm entry for 720').toBeTruthy();
	const expected = `Friday 5 pm. Median ${delay(hour.med)}. ${Math.round(hour.ontime)} percent on time. ${hour.n.toLocaleString('en-US')} arrivals measured.`;

	await page.goto('/');
	await page.getByRole('combobox', { name: 'Find a line' }).tap(); // tap 1
	await page.keyboard.type(entry.line);
	await page.getByRole('option', { name: new RegExp(entry.label) }).tap(); // tap 2
	await expect(page).toHaveURL(`/lines/${entry.line}`);

	const readout = page.locator('[id$="-readout"]');
	await expect(readout).toContainText('Median');
	// The page opens on the worst hour. If that were Friday 5 pm the tap would prove nothing.
	await expect(readout).not.toHaveText(expected);
	await page.locator(`[data-hour="${FRIDAY_5PM}"]`).tap(); // tap 3
	await expect(readout).toHaveText(expected);
});

test('a rail page shows no on-time sentence and a bus page does', async ({ page }) => {
	const sentences = /percent on time|On time means/;
	const bus = entries.find((e) => e.mode === 'bus' && e.n >= MIN_RANKED_ARRIVALS)!;
	await page.goto(`/lines/${bus.line}`);
	await expect(lineLoaded(page)).toBeVisible();
	await expect(page.locator('main')).toContainText(sentences);

	const rail = entries.filter((e) => e.mode === 'rail');
	expect(rail.length).toBeGreaterThan(0);
	for (const entry of rail) {
		await page.goto(`/lines/${entry.line}`);
		await expect(lineLoaded(page)).toBeVisible();
		await expect(page.locator('figure').first()).toBeVisible();
		await expect(page.locator('main')).not.toContainText(sentences);
	}
});

// The panel compares last_day with the browser's date, so each test sets the
// clock. Without that, the fixture would turn stale as the real date moved on.
const AFTERNOON_UTC = 'T20:00:00Z';
const daysAfter = (day: string, count: number) =>
	new Date(Date.parse(`${day}T00:00:00Z`) + count * 86_400_000).toISOString().slice(0, 10);

test('the behind-the-scenes page shows the newest graded day and a 14-day strip at 375 px', async ({
	page
}) => {
	await page.clock.setFixedTime(new Date(`${daysAfter(health.last_day, 1)}${AFTERNOON_UTC}`));
	const problems = watchConsole(page);
	await page.goto('/behind-the-scenes');
	await expect(page.locator('h1')).toHaveCount(1);
	const cells = page.locator('[data-cell]');
	await expect(cells).toHaveCount(14);
	await page.waitForLoadState('networkidle');

	await expect(page.getByText('Newest graded day', { exact: true })).toBeVisible();
	await expect(page.locator('p.headline')).toHaveText(longDate(health.last_day));
	await expect(page.locator('[data-warning]')).toHaveCount(0);

	// The failed days come from the fixture file, so the test and the page agree
	// on which day to mark.
	const failedDays = health.recent.filter((day) => !day.ok);
	expect(failedDays.length, 'the fixture has no failed day').toBeGreaterThan(0);
	await expect(page.locator('[data-cell="failed"]')).toHaveCount(failedDays.length);
	for (const day of failedDays) {
		await expect(page.getByText(`${longDate(day.service_date)}: failed a check`)).toHaveCount(1);
	}
	const missing =
		14 - health.recent.filter((day) => day.service_date > daysAfter(health.last_day, -14)).length;
	expect(missing, 'the fixture has no missing day').toBeGreaterThan(0);
	await expect(page.locator('[data-cell="none"]')).toHaveCount(missing);
	await expect(page.locator('[data-check]')).toHaveCount(health.checks.length);

	const { scrollWidth, clientWidth } = await page.evaluate(() => ({
		scrollWidth: document.documentElement.scrollWidth,
		clientWidth: document.documentElement.clientWidth
	}));
	expect(scrollWidth, 'the page scrolls sideways').toBeLessThanOrEqual(clientWidth);
	expect(problems).toEqual([]);
});

// A copy of health.json whose newest day is `lag` days before the fixed date.
async function openWithLag(page: Page, lag: number) {
	const today = '2026-11-16';
	await page.clock.setFixedTime(new Date(`${today}${AFTERNOON_UTC}`));
	await page.route('**/health.json', (route) =>
		route.fulfill({ json: { ...health, last_day: daysAfter(today, -lag) } })
	);
	await page.goto('/behind-the-scenes');
	await expect(page.locator('[data-cell]')).toHaveCount(14);
}

test('a newest day 4 days old shows the warning, and 3 days old does not', async ({ page }) => {
	await openWithLag(page, 4);
	const warning = page.locator('[data-warning]');
	await expect(warning).toBeVisible();
	await expect(warning).toContainText('4 days before today');
	await page.unrouteAll();
	await openWithLag(page, 3);
	await expect(page.locator('[data-warning]')).toHaveCount(0);
});
