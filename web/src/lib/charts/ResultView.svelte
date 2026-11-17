<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import type { Result } from '#lib/data/load.ts';
	import ErrorState from './ErrorState.svelte';
	import LoadingState from './LoadingState.svelte';

	// Undefined means the request is still running. A failed result is shown as
	// an error, so no data file can leave a blank area.
	let {
		result,
		onretry,
		children
	}: { result: Result<T> | undefined; onretry?: () => void; children: Snippet<[T]> } = $props();
</script>

{#if !result}
	<LoadingState />
{:else if !result.ok}
	<ErrorState {onretry} />
{:else}
	{@render children(result.data)}
{/if}
