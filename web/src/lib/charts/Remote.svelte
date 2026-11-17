<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import type { Result } from '#lib/data/load.ts';
	import ResultView from './ResultView.svelte';

	// Loads in the browser only, because effects do not run during prerender. The
	// static HTML therefore holds the loading state. A retry runs the load again.
	let {
		load,
		heading,
		children
	}: { load: () => Promise<Result<T>>; heading?: Snippet; children: Snippet<[T]> } = $props();

	let result = $state<Result<T>>();
	let attempt = $state(0);

	$effect(() => {
		void attempt;
		let current = true;
		result = undefined;
		load().then((loaded) => {
			if (current) result = loaded;
		});
		return () => {
			current = false;
		};
	});
</script>

<ResultView {result} onretry={() => attempt++} {heading} {children} />
