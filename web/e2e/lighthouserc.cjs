// lhci loads this file with require(), so it stays CommonJS.
// eslint-disable-next-line @typescript-eslint/no-require-imports
const { chromium } = require('@playwright/test');

const base = process.env.E2E_BASE_URL ?? 'http://localhost:4173';

module.exports = {
	ci: {
		collect: {
			url: [`${base}/`, `${base}/lines/720`, `${base}/ranking`, `${base}/behind-the-scenes`],
			numberOfRuns: 3,
			// The Chromium that Playwright installs, so package-lock.json pins its
			// version and the runner image cannot change it. No preset is set, so
			// Lighthouse uses its default, which is mobile.
			chromePath: chromium.executablePath(),
			settings: { chromeFlags: '--no-sandbox --headless' }
		},
		assert: {
			// The median of the three runs, so one slow run neither fails nor rescues a page.
			aggregationMethod: 'median-run',
			assertions: {
				'categories:performance': ['error', { minScore: 0.9 }],
				'categories:accessibility': ['error', { minScore: 0.95 }]
			}
		},
		// Files only. Nothing leaves the machine.
		upload: { target: 'filesystem', outputDir: 'reports/lighthouse' }
	}
};
