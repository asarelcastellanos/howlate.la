<script lang="ts">
	import type { Snippet } from 'svelte';

	// The box every chart area falls back to, so a chart that cannot draw leaves a
	// message and not a blank gap. It keeps the chart's height to avoid a jump.
	let { role, children }: { role?: 'alert' | 'status'; children: Snippet } = $props();
</script>

<div
	{role}
	class="bg-sunk text-ink font-sans flex min-h-48 flex-col items-center justify-center gap-3 border p-6 text-center text-data"
>
	{@render children()}
</div>
