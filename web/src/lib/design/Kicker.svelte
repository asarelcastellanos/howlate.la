<script lang="ts">
	import type { Snippet } from 'svelte';

	let { children }: { children: Snippet } = $props();
</script>

<p class="kicker text-ink-muted mb-2">{@render children()}</p>
