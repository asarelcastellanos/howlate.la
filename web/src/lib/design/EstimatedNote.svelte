<script lang="ts">
	import { ESTIMATE_HREF, estimatedNote } from '#lib/estimated.ts';

	// Says how much of a figure was placed between two reports of the same bus. It draws
	// nothing when none was, or when the published file has no count yet. A plain link, as
	// in OntimeNote, because the chart tests import design components outside SvelteKit.
	let {
		n,
		est,
		what,
		class: className = ''
	}: { n: number; est: number | undefined; what?: string; class?: string } = $props();
	const note = $derived(estimatedNote(n, est, what));
</script>

{#if note}
	<p class="caption text-ink-muted {className}">
		{note}
		<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
		<a href={ESTIMATE_HREF}>How we estimate</a>
	</p>
{/if}
