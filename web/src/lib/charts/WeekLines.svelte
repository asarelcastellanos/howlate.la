<script lang="ts">
	import type { Hour } from '#lib/data/types.ts';
	import ChartFigure from './ChartFigure.svelte';
	import { weekLines, weekLinesLabel } from './lineChart.ts';
	import { trusted } from './theme.ts';

	let { profile, caption, source }: { profile: Hour[]; caption: string; source: string } = $props();
</script>

<ChartFigure
	empty={trusted(profile).length === 0}
	render={(width) => weekLines(profile, { width })}
	label={weekLinesLabel(profile)}
	{caption}
	source={trusted(profile).length < 168
		? `${source} Gaps are hours with too few arrivals or none measured.`
		: source}
/>
