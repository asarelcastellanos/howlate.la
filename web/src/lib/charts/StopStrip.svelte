<script lang="ts">
	import type { Stop } from '#lib/data/types.ts';
	import ChartFigure from './ChartFigure.svelte';
	import { DEFAULT_DAYPART, daypartName, stopStrip, stripDots, stripLabel } from './strip.ts';
	import { MIN_ARRIVALS } from './theme.ts';

	let {
		stops,
		to,
		daypart = DEFAULT_DAYPART,
		caption,
		source
	}: { stops: Stop[]; to: string; daypart?: string; caption: string; source: string } = $props();
</script>

<ChartFigure
	empty={stripDots(stops, daypart, 600).length === 0}
	render={(width) => stopStrip(stops, daypart, { width })}
	label={stripLabel(stops, daypart, to)}
	{caption}
	{source}
>
	{#snippet extra()}
		<p class="caption text-ink-muted mt-2">
			{daypartName(daypart)}. Larger dots have more arrivals. A hollow dot has too few arrivals to
			judge, under {MIN_ARRIVALS}.
		</p>
	{/snippet}
</ChartFigure>
