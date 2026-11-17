import { defineConfig } from '@playwright/test';

// CI builds the site, serves it and sets E2E_BASE_URL (see .github/workflows/checks.yml),
// so no webServer block starts a second server here.
export default defineConfig({
	testDir: '.',
	testMatch: '*.spec.ts',
	outputDir: 'reports/results',
	reporter: [['list'], ['html', { outputFolder: 'reports/playwright', open: 'never' }]],
	forbidOnly: !!process.env.CI,
	// A flaky retry would hide a real console error that only shows on some loads.
	retries: 0,
	use: {
		baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:4173',
		// A phone width, but desktop Chromium, so the page's own layout decides whether it
		// overflows. isMobile would zoom out to fit a wide page and hide sideways scroll.
		browserName: 'chromium',
		viewport: { width: 375, height: 812 },
		hasTouch: true
	},
	projects: [{ name: 'chromium' }]
});
