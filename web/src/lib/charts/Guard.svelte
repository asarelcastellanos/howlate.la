<script lang="ts">
	import type { Snippet } from 'svelte';
	import ErrorState from './ErrorState.svelte';

	// A throw while a page draws would otherwise end in the host's own 500 page.
	// This shows the same error box as a failed load, and retry draws it again.
	let { children }: { children: Snippet } = $props();
</script>

<svelte:boundary>
	{@render children()}
	<!-- The snippet's first argument is the error, and the box does not show it. -->
	<!-- eslint-disable-next-line @typescript-eslint/no-unused-vars -->
	{#snippet failed(error, reset)}
		<ErrorState onretry={reset} />
	{/snippet}
</svelte:boundary>
