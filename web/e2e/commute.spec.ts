import { expect, test, type Page } from '@playwright/test';
import { watchConsole } from './helpers.ts';

async function pick(page: Page, group: string, query: string, name: string) {
	const box = page.getByRole('group', { name: group }).getByRole('combobox');
	await box.fill(query);
	await page
		.getByRole('option', { name: new RegExp(name) })
		.first()
		.click();
}

for (const [w, h] of [[390, 844]]) {
	for (const scheme of ['light'] as const) {
		test(`commute ${w} ${scheme}`, async ({ browser }) => {
			const context = await browser.newContext({
				viewport: { width: w, height: h },
				colorScheme: scheme
			});
			const page = await context.newPage();
			const problems = watchConsole(page);
			await page.goto('/commute');
			await expect(page.getByTestId('rail-note')).toBeVisible();
			await page.getByLabel('Bus line').selectOption('720');
			await expect(page.getByRole('group', { name: 'From' })).toBeVisible();
			await pick(page, 'From', 'westwood', 'Wilshire / Westwood');
			const to = page.getByRole('group', { name: 'To' });
			await to.getByRole('combobox').fill('wilshire');
			const names = await page.getByRole('option').allTextContents();
			expect(names.join('|')).not.toContain('Westwood');
			await page
				.getByRole('option', { name: /Vermont/ })
				.first()
				.click();
			await page.getByText('Arrive by').first().click();
			await page.getByLabel('Time', { exact: true }).fill('09:00');
			const answer = page.getByTestId('commute-answer');
			await expect(answer).toContainText('Catch the');
			const sentence = (await answer.textContent())!.trim();
			await expect(page.getByTestId('spread-chart').locator('svg')).toBeVisible();
			expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
				true
			);
			const live = await page.getByTestId('commute-answer').evaluate((el) => ({
				role: el.getAttribute('role'),
				live: el.getAttribute('aria-live')
			}));
			expect(live).toEqual({ role: 'status', live: 'polite' });

			const url = page.url();
			const fresh = await browser.newContext({
				viewport: { width: w, height: h },
				colorScheme: scheme
			});
			const second = await fresh.newPage();
			await second.goto(url);
			await expect(second.getByTestId('commute-answer')).toContainText('Catch the');
			expect((await second.getByTestId('commute-answer').textContent())!.trim()).toBe(sentence);
			await fresh.close();

			await page.getByText('Leave at').first().click();
			await expect(page.getByRole('group', { name: 'From' })).toContainText('Westwood');
			await expect(page.getByRole('group', { name: 'To' })).toContainText('Vermont');
			expect(page.url()).toContain('mode=leave');
			await expect(answer).toContainText('line 720 bus');

			await page.getByText('Toward', { exact: false }).nth(1).click();
			await expect(page.getByRole('group', { name: 'From' }).getByRole('combobox')).toBeVisible();
			await expect(answer).toHaveText('');
			expect(page.url()).not.toContain('from=');
			expect(problems).toEqual([]);
			await context.close();
		});
	}
}

test('links, bad query, not enough data', async ({ page }) => {
	const problems = watchConsole(page);
	await page.goto('/');
	await page.getByRole('link', { name: 'Plan a bus commute' }).click();
	await expect(page).toHaveURL(/\/commute/);
	await page.goto('/lines/720');
	await page.getByRole('link', { name: /Plan a commute/ }).click();
	await expect(page).toHaveURL(/\/commute\?.*line=720/);
	await expect(page.getByLabel('Bus line')).toHaveValue('720');
	await page.goto('/lines/801');
	await expect(page.getByRole('link', { name: /Plan a commute/ })).toHaveCount(0);
	await page.goto('/commute?line=zzz&dir=9&day=funday&mode=sideways&time=25:99&from=nope');
	await expect(page.getByLabel('Bus line')).toHaveValue('');
	await page.goto('/commute?line=720&dir=0&day=weekday&from=10001&to=10006&mode=leave&time=09:30');
	await expect(page.getByTestId('commute-answer')).toContainText('Not enough data');
	await page.goto('/commute?line=720&dir=0&day=sunday');
	await expect(page.getByText('No Sunday timetable')).toBeVisible();
	await page.goto('/commute?line=720&dir=0&day=weekday&from=10003&to=10002&mode=leave&time=08:00');
	await expect(page.getByRole('group', { name: 'From' })).toContainText('Bundy');
	await expect(page.getByRole('group', { name: 'To' }).getByRole('combobox')).toBeVisible();
	expect(problems).toEqual([]);
});
