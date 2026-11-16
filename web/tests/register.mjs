// Lets node:test import .svelte files by compiling them for the server, so a
// test can render a component to a string without a browser or a bundler.
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
			generate: 'server',
			runes: true
		});
		return { format: 'module', source: js.code, shortCircuit: true };
	}
});
