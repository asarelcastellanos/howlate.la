<script lang="ts">
	import type { Snippet } from 'svelte';

	// A chart or table, then a caption, then the source note. Charts break out
	// of the reading column by default.
	let {
		width = 'wide',
		caption,
		source,
		children
	}: {
		width?: 'text' | 'wide' | 'full';
		caption?: Snippet;
		source?: Snippet;
		children: Snippet;
	} = $props();
</script>

<figure class="my-10 {width === 'wide' ? 'wide' : width === 'full' ? 'full' : ''}">
	{@render children()}
	{#if caption || source}
		<figcaption class="caption mt-3 border-t pt-2">
			{#if caption}<p class="text-ink">{@render caption()}</p>{/if}
			{#if source}<p class="text-ink-muted mt-1">{@render source()}</p>{/if}
		</figcaption>
	{/if}
</figure>
