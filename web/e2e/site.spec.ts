import { readFileSync } from 'node:fs';
import { expect, test, type Page } from '@playwright/test';
import { MIN_RANKED_ARRIVALS } from '../src/lib/ranking.ts';
import { longDate } from '../src/lib/date.ts';
import { shareText } from '../src/lib/share.ts';
import { health, index, network, readLine, status } from './fixture.ts';
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

// Each file on the home page has its own error state. Both must offer Try again,
// and the retry must load the file that failed.
for (const file of ['status.json', 'index.json']) {
	test(`a failed ${file} on the home page shows Try again, and the retry loads it`, async ({
		page
	}) => {
		let failures = 0;
		await page.route(`**/${file}`, (route) => {
			if (failures++ === 0) return route.fulfill({ status: 500, body: '' });
			return route.continue();
		});
		await page.goto('/');
		const retry = page.getByRole('button', { name: 'Try again' });
		await expect(page.getByRole('alert')).toContainText("We couldn't load this data");
		await expect(retry).toHaveCount(1);
		await retry.click();
		await expect(retry).toHaveCount(0);
		await expect(page.getByRole('alert')).toHaveCount(0);
		await expect(page.getByRole('combobox', { name: 'Find a line' })).toBeVisible();
	});
}

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
	// The trailing asterisk points to the on-time note under the readout.
	const expected = `Friday 5 pm. Median ${delay(hour.med)}. ${Math.round(hour.ontime)} percent on time. ${hour.n.toLocaleString('en-US')} arrivals measured.*`;

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

test('a rail page shows the on-time sentence like a bus page', async ({ page }) => {
	const sentences = /percent of [\d,]+ measured arrivals were on time|On time means/;
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
		await expect(page.locator('main')).toContainText(sentences);
		await expect(page.locator('main')).not.toContainText('on hold');
	}
});

// The asterisk is hidden from a screen reader, so the tests find it by its test id.
const MARK = 'ontime-mark';
const SHORT_NOTE =
	'On time means 1 minute early to 5 minutes late. Metro reports on-time performance differently.';
const LONG_NOTE =
	'On time means arriving 1 minute early to 5 minutes late against the timetable. We score every measured stop after the first. Metro reports on-time performance differently.';

// At 375 px the note is the short form. The full text is for wider screens, and the
// asterisk is hidden from a screen reader, so the link carries the meaning.
test('every line page has the on-time note, and its link opens the methods section', async ({
	page
}) => {
	for (const entry of entries.filter((e) => e.mode === 'rail' || e.n >= MIN_RANKED_ARRIVALS)) {
		await page.goto(`/lines/${entry.line}`);
		await expect(lineLoaded(page)).toBeVisible();
		const notes = page.locator('main p', { hasText: 'On time means' });
		// One under the headline, one under the heatmap readout.
		await expect(notes).toHaveCount(2);
		for (const note of await notes.all()) {
			await expect(note.getByText(SHORT_NOTE, { exact: true })).toBeVisible();
			await expect(note.getByText(LONG_NOTE, { exact: true })).toBeHidden();
			await expect(note.getByRole('link', { name: 'How we measure' })).toHaveAttribute(
				'href',
				'/methods#how-we-measure-on-time'
			);
		}
		// Each direction's headline share has its own asterisk.
		const headlines = page.locator('main li', { hasText: /measured arrivals were on time/ });
		expect(await headlines.count()).toBeGreaterThan(0);
		for (const headline of await headlines.all()) {
			await expect(headline.getByTestId(MARK)).toHaveCount(1);
		}
	}

	const rail = entries.find((e) => e.mode === 'rail')!;
	await page.goto(`/lines/${rail.line}`);
	await expect(lineLoaded(page)).toBeVisible();
	await page.getByRole('link', { name: 'How we measure' }).first().click();
	await expect(page).toHaveURL(/\/methods#how-we-measure-on-time$/);
	const heading = page.getByRole('heading', { level: 2, name: 'How we measure on-time' });
	await expect(heading).toBeInViewport();
});

test('from 640 px up the note is the full form and the short one is hidden', async ({ page }) => {
	await page.setViewportSize({ width: 1024, height: 800 });
	for (const mode of ['bus', 'rail'] as const) {
		const entry = entries.find(
			(e) => e.mode === mode && (mode === 'rail' || e.n >= MIN_RANKED_ARRIVALS)
		)!;
		await page.goto(`/lines/${entry.line}`);
		await expect(lineLoaded(page)).toBeVisible();
		const notes = page.locator('main p', { hasText: 'On time means' });
		await expect(notes).toHaveCount(2);
		for (const note of await notes.all()) {
			await expect(note.getByText(LONG_NOTE, { exact: true })).toBeVisible();
			await expect(note.getByText(SHORT_NOTE, { exact: true })).toBeHidden();
		}
	}
});

test('the methods page shows the live bus and rail shares from the published files', async ({
	page
}) => {
	await page.goto('/methods');
	const bus = shareText(network.bus.all.ontime!);
	const rail = shareText(network.rail.all.ontime!);
	await expect(page.locator('#how-we-measure-on-time')).toContainText(
		`HowLate scored ${bus} percent of measured bus arrivals and ${rail} percent of measured rail arrivals as on time`
	);
	await expect(page.locator('#how-we-measure-on-time')).toContainText(
		`over ${status.days} days of data`
	);
});

test('the ranking marks each share and lists the rail on-time share', async ({ page }) => {
	await page.goto('/ranking');
	const table = page.getByRole('region', { name: /Ranked bus lines/ });
	await expect(table.locator('tbody tr').first()).toBeVisible();
	await expect(page.locator('main p', { hasText: 'On time means' })).toHaveCount(3);
	const rail = page.getByRole('region', { name: /Rail lines/ });
	await expect(rail.getByRole('columnheader', { name: /On time/ })).toBeVisible();
	// An asterisk beside every share: each Extremes row, and the On time heading of
	// the bus table and the rail table.
	const extremes = page.locator('ol.data > li');
	expect(await extremes.count()).toBeGreaterThan(0);
	for (const row of await extremes.all()) await expect(row.getByTestId(MARK)).toHaveCount(1);
	for (const region of [table, rail]) {
		const heading = region.getByRole('columnheader', { name: /On time/ });
		await expect(heading.getByTestId(MARK)).toHaveCount(1);
	}
	const railEntries = entries.filter((e) => e.mode === 'rail');
	for (const entry of railEntries) {
		await expect(rail.locator('tbody tr', { hasText: entry.label })).toContainText(
			`${shareText(entry.ontime)}%`
		);
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

test('a newest day 3 days old shows the warning, and 2 days old does not', async ({ page }) => {
	await openWithLag(page, 3);
	const warning = page.locator('[data-warning]');
	await expect(warning).toBeVisible();
	await expect(warning).toContainText('3 days before today');
	await page.unrouteAll();
	await openWithLag(page, 2);
	await expect(page.locator('[data-warning]')).toHaveCount(0);
});
