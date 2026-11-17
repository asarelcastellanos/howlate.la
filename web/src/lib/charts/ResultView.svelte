<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import type { Result } from '#lib/data/load.ts';
	import ErrorState from './ErrorState.svelte';
	import LoadingState from './LoadingState.svelte';

	// Undefined means the request is still running. A failed result is shown as
	// an error, so no data file can leave a blank area. `heading` is drawn above
	// the loading and error states, for a page that needs its h1 before the data
	// arrives.
	let {
		result,
		onretry,
		heading,
		children
	}: {
		result: Result<T> | undefined;
		onretry?: () => void;
		heading?: Snippet;
		children: Snippet<[T]>;
	} = $props();
</script>

{#if !result}
	{@render heading?.()}
	<LoadingState />
{:else if !result.ok}
	{@render heading?.()}
	<ErrorState {onretry} error={result.error} />
{:else}
	<!-- A render error inside the data views, such as a chart that meets a field it
	     cannot read, shows the error box and not the framework's 500 page. -->
	<svelte:boundary onerror={(error) => console.error('The page could not draw this data.', error)}>
		{@render children(result.data)}
		<!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
		{#snippet failed(error, reset)}
			{@render heading?.()}
			<ErrorState onretry={onretry ?? reset} />
		{/snippet}
	</svelte:boundary>
{/if}
