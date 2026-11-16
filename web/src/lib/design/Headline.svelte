<script lang="ts">
	import type { Snippet } from 'svelte';

	let {
		level = 1,
		size = 'xl',
		dek,
		children
	}: { level?: 1 | 2 | 3; size?: 'xl' | 'md'; dek?: string; children: Snippet } = $props();
</script>

<svelte:element this={`h${level}`} class={size === 'xl' ? 'headline-xl' : 'headline'}>
	{@render children()}
</svelte:element>
{#if dek}
	<p class="dek mt-3">{dek}</p>
{/if}
