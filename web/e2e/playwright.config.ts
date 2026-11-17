import { defineConfig } from '@playwright/test';

// The tests expect a server that is already running, so no webServer block starts one
// here. CI serves the preview on port 4173 (see .github/workflows/checks.yml) and sets
// no E2E_BASE_URL, because the default below matches that port. Set it to test another
// address or port.
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
