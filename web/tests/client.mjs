// Like register.mjs, but compiles .svelte files for the browser. A test that
// mounts a component needs it, because the server build has no boundary that
// catches a render error. Run it with --conditions=browser so `svelte` resolves
// to its client build.
import { readFileSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { fileURLToPath } from 'node:url';
import { compile } from 'svelte/compiler';

registerHooks({
	load(url, context, nextLoad) {
		if (!url.endsWith('.svelte')) return nextLoad(url, context);
		const filename = fileURLToPath(url);
		const { js } = compile(readFileSync(filename, 'utf8'), {
			filename,
			generate: 'client',
			runes: true
		});
		return { format: 'module', source: js.code, shortCircuit: true };
	}
});
