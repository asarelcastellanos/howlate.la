<script lang="ts">
	import { SHOW_RAIL_ONTIME } from '#lib/config.ts';
	import { DATA_BASE } from '#lib/data/base.ts';
	import { loadShares, sharesText } from '#lib/methodsShares.ts';

	// Loads in the browser only, like Remote, so the prerendered page has no figure
	// in it. A failed load shows nothing, because the page reads the same without the
	// sentence and every line page has its own share. With the rail gate closed the
	// sentence names no rail share.
	let { railGate = SHOW_RAIL_ONTIME }: { railGate?: boolean } = $props();
	let text = $state<string>();

	$effect(() => {
		let current = true;
		loadShares(DATA_BASE).then((result) => {
			if (current && result.ok) text = sharesText(result.data, railGate);
		});
		return () => {
			current = false;
		};
	});
</script>

{#if text}<p class="mt-4">{text}</p>{/if}
