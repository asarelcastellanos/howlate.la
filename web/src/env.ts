import { defineEnvVars } from '@sveltejs/kit/env';

/**
 * The development address of the howlate R2 bucket. It is public, and its CORS
 * policy allows any origin. PUBLIC_DATA_BASE overrides it at build time. Replace
 * it with the custom data domain when there is one.
 */
export const DEFAULT_DATA_BASE = 'https://pub-4b142eaaa0dc461aa668b007c9f14299.r2.dev';

export const variables = defineEnvVars({
	PUBLIC_DATA_BASE: {
		public: true,
		static: true,
		schema: (value) => value ?? DEFAULT_DATA_BASE,
		description:
			'Where the site JSON lives. The pointer is at <base>/site/current.json. Defaults to the R2 development address.'
	}
});
