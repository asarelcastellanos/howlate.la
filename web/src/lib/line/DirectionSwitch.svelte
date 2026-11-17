<script lang="ts">
	import { directionName } from '#lib/linePage.ts';
	import type { Direction } from '#lib/data/types.ts';

	// A segmented control made of radio buttons. The browser gives it the arrow
	// keys and the checked state, and the label is the visible segment.
	let {
		directions,
		value = $bindable(0)
	}: { directions: Pick<Direction, 'to'>[]; value?: number } = $props();

	const name = $props.id();
</script>

<fieldset class="mt-8">
	<legend class="kicker text-ink-muted mb-2">Show the charts for</legend>
	<div class="flex flex-col sm:flex-row">
		{#each directions as direction, i (i)}
			<label class="flex-1">
				<input type="radio" {name} value={i} bind:group={value} class="peer sr-only" />
				<span
					class="border-ink data peer-checked:bg-ink peer-checked:text-paper peer-focus-visible:outline-focus block min-h-12 cursor-pointer border px-4 py-3 font-semibold peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 sm:-ml-px sm:first:ml-0"
				>
					{directionName(direction, i)}
				</span>
			</label>
		{/each}
	</div>
</fieldset>
