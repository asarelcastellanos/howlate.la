<script lang="ts">
	import type { StripCell } from '#lib/behind.ts';
	import { longDate, shortDate } from '#lib/date.ts';

	let { cells }: { cells: StripCell[] } = $props();

	const words = { ok: 'passed', failed: 'failed a check', none: 'no report' } as const;
	const legend = ['ok', 'failed', 'none'] as const;
</script>

<!-- A cell says its state three ways. The shape differs (a check, a cross, a dashed
     outline), the color differs, and the legend and the hidden text use words. -->
{#snippet glyph(state: StripCell['state'])}
	<svg viewBox="0 0 24 24" class="w-full" aria-hidden="true">
		{#if state === 'ok'}
			<rect x="1.5" y="1.5" width="21" height="21" rx="3" class="fill-ink" />
			<path
				d="M6 12.5l4 4 8-9"
				class="stroke-paper fill-none"
				stroke-width="3"
				stroke-linecap="round"
				stroke-linejoin="round"
			/>
		{:else if state === 'failed'}
			<rect
				x="2"
				y="2"
				width="20"
				height="20"
				rx="3"
				class="fill-paper stroke-destructive"
				stroke-width="3"
			/>
			<path
				d="M7.5 7.5l9 9M16.5 7.5l-9 9"
				class="stroke-destructive"
				stroke-width="3"
				stroke-linecap="round"
			/>
		{:else}
			<rect
				x="2"
				y="2"
				width="20"
				height="20"
				rx="3"
				class="stroke-chart-quiet fill-none"
				stroke-width="2"
				stroke-dasharray="3 3"
			/>
		{/if}
	</svg>
{/snippet}

<p class="kicker text-ink-muted flex justify-between">
	<span>{shortDate(cells[0].day)}</span>
	<span>{shortDate(cells[cells.length - 1].day)}</span>
</p>
<ol class="mt-2 grid grid-cols-14 gap-1">
	{#each cells as cell (cell.day)}
		<li data-cell={cell.state} class="flex flex-col items-center gap-1">
			<span class="block w-full max-w-7">{@render glyph(cell.state)}</span>
			<span class="caption text-ink-muted text-[0.6875rem] leading-none" aria-hidden="true"
				>{Number(cell.day.slice(8))}</span
			>
			<span class="sr-only">{longDate(cell.day)}: {words[cell.state]}</span>
		</li>
	{/each}
</ol>
<ul class="caption text-ink-muted mt-3 flex flex-wrap gap-x-5 gap-y-1">
	{#each legend as state (state)}
		<li class="flex items-center gap-2">
			<span class="block w-4">{@render glyph(state)}</span>
			{state === 'ok' ? 'Passed' : state === 'failed' ? 'Failed a check' : 'No report'}
		</li>
	{/each}
</ul>
