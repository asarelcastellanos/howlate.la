<script lang="ts">
	import Notice from './Notice.svelte';

	import type { LoadError } from '#lib/data/load.ts';

	let { onretry, error }: { onretry?: () => void; error?: LoadError } = $props();
</script>

<Notice role="alert">
	{#if error?.kind === 'shape'}
		<p>This page needs newer data than the site has yet. Try again in a few minutes.</p>
	{:else}
		<p>We couldn't load this data.</p>
	{/if}
	{#if onretry}
		<button
			type="button"
			onclick={onretry}
			class="border-ink hover:bg-ink hover:text-paper cursor-pointer border px-4 py-2 font-semibold"
		>
			Try again
		</button>
	{/if}
</Notice>
