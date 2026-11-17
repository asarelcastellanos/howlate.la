<script lang="ts">
	import type { Hour, Stop } from '#lib/data/types.ts';
	import Heatmap from './Heatmap.svelte';
	import RouteChart from './RouteChart.svelte';
	import StopStrip from './StopStrip.svelte';
	import WeekLines from './WeekLines.svelte';

	// The four charts for one direction of one line, with captions that name it.
	let {
		name,
		to,
		profile,
		stops,
		source,
		showOntime
	}: {
		name: string;
		to: string;
		profile: Hour[];
		stops: Stop[];
		source: string;
		showOntime: boolean;
	} = $props();
	const where = $derived(`${name}${to ? ` toward ${to}` : ''}`);
</script>

<Heatmap {profile} {source} {showOntime} caption="Median delay by day and hour, {where}." />
<WeekLines
	{profile}
	{source}
	caption="Median and 90th percentile delay across the week, {where}."
/>
<StopStrip {stops} {to} {source} caption="Median delay at each stop, {where}." />
<RouteChart
	{stops}
	{to}
	{source}
	caption="Median delay at each stop in route order, {where}. Stops are evenly spaced, not to distance."
/>
