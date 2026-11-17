<script lang="ts">
	import Remote from '../../src/lib/charts/Remote.svelte';
	import type { Result } from '../../src/lib/data/load.ts';

	let { load }: { load: () => Promise<Result<string>> } = $props();
</script>

<Remote {load}>
	{#snippet children(text)}<p data-loaded>{text}</p>{/snippet}
</Remote>
