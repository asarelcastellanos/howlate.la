import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { lineLoaded } from './helpers.ts';

// One page of each kind, loaded to the point where its data is on screen. An
// axe run on a loading state would pass without testing the page.
const pages: { path: string; ready: (page: Page) => Promise<void> }[] = [
	{
		path: '/',
		ready: (page) => expect(page.getByRole('combobox', { name: 'Find a line' })).toBeVisible()
	},
	{
		path: '/lines/720',
		ready: async (page) => {
			await expect(lineLoaded(page)).toBeVisible();
			await expect.poll(() => page.locator('figure').count()).toBeGreaterThanOrEqual(4);
		}
	},
	{
		path: '/ranking',
		ready: (page) => expect(page.getByRole('table').first()).toBeVisible()
	},
	{ path: '/methods', ready: (page) => expect(page.locator('h1')).toBeVisible() }
];

for (const scheme of ['light', 'dark'] as const) {
	test.describe(`${scheme} scheme`, () => {
		test.use({ colorScheme: scheme });

		for (const { path, ready } of pages) {
			test(`${path} has no serious or critical axe violation`, async ({ page }) => {
				await page.goto(path);
				await ready(page);
				await page.waitForLoadState('networkidle');

				const { violations } = await new AxeBuilder({ page }).analyze();
				const blocking = violations
					.filter((v) => v.impact === 'serious' || v.impact === 'critical')
					.map((v) => ({
						rule: v.id,
						impact: v.impact,
						help: v.help,
						nodes: v.nodes.map((node) => node.target.join(' '))
					}));
				expect(blocking).toEqual([]);
			});
		}
	});
}
