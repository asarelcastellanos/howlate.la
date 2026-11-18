<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import type { Result } from '#lib/data/load.ts';
	import ResultView from './ResultView.svelte';

	// Loads in the browser only, because effects do not run during prerender. The
	// static HTML therefore holds the loading state. A retry runs the load again.
	// The children get that retry as a second argument, for a page that shows its
	// own ResultView per part of the data and needs a Try again button on each.
	let {
		load,
		heading,
		children: render
	}: {
		load: () => Promise<Result<T>>;
		heading?: Snippet;
		children: Snippet<[T, () => void]>;
	} = $props();

	let result = $state<Result<T>>();
	let attempt = $state(0);

	const retry = () => attempt++;

	$effect(() => {
		void attempt;
		let current = true;
		result = undefined;
		// The loaders return errors as values, so a rejection means something else
		// threw. It gets the same error state and retry, not a spinner that never ends.
		load()
			.catch((): Result<T> => ({ ok: false, error: { kind: 'network', url: '' } }))
			.then((loaded) => {
				if (current) result = loaded;
			});
		return () => {
			current = false;
		};
	});
</script>

<ResultView {result} onretry={retry} {heading}>
	{#snippet children(data)}{@render render(data, retry)}{/snippet}
</ResultView>
