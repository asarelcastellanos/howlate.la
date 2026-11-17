import type { Page } from '@playwright/test';

/** Every console error and warning and every uncaught exception, as the page raises them. */
export function watchConsole(page: Page): string[] {
	const problems: string[] = [];
	page.on('console', (message) => {
		if (message.type() === 'error' || message.type() === 'warning') {
			problems.push(`${message.type()}: ${message.text()}`);
		}
	});
	page.on('pageerror', (error) => problems.push(`uncaught: ${error.message}`));
	return problems;
}

/** The first chart on a line page that loaded its data, or the error box that replaced it. */
export const lineLoaded = (page: Page) => page.locator('figure, [role="alert"]').first();
