import { defineEnvVars } from '@sveltejs/kit/env';

/**
 * The custom domain on the howlate R2 bucket. It is the stable public address
 * for the site's data. The bucket's r2.dev address is rate limited by
 * Cloudflare and not meant for production, so nothing here points at it. The
 * domain answers with `access-control-allow-origin: *` and a 60 second cache
 * on the pointer. PUBLIC_DATA_BASE overrides it at build time.
 */
export const DEFAULT_DATA_BASE = 'https://data.howlate.la';

export const variables = defineEnvVars({
	PUBLIC_DATA_BASE: {
		public: true,
		static: true,
		schema: (value) => value ?? DEFAULT_DATA_BASE,
		description:
			'Where the site JSON lives. The pointer is at <base>/site/current.json. Defaults to https://data.howlate.la.'
	}
});
