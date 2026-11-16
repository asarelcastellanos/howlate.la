import { defineEnvVars } from '@sveltejs/kit/env';

export const variables = defineEnvVars({
	PUBLIC_DATA_BASE: {
		public: true,
		static: true,
		// The default is a same-origin path, so local dev needs no CORS setup.
		schema: (value) => value ?? '/data',
		description:
			'Where the site JSON lives. The pointer is at <base>/site/current.json. Set it to the R2 URL in production.'
	}
});
