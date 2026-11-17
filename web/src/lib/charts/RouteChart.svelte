<script lang="ts">
	import type { Stop } from '#lib/data/types.ts';
	import ChartFigure from './ChartFigure.svelte';
	import { routeChart, routeChartLabel, routeStops } from './routeChart.ts';
	import { MIN_ARRIVALS } from './theme.ts';

	let {
		stops,
		to,
		caption,
		source
	}: { stops: Stop[]; to: string; caption: string; source: string } = $props();

	const rows = $derived(routeStops(stops));
	const trusted = (stop: Stop) => stop.all.med !== null && stop.n >= MIN_ARRIVALS;
	const minutes = (stop: Stop, key: 'med' | 'p90') =>
		stop.n === 0 || stop.all[key] === null
			? 'not measured'
			: stop.n < MIN_ARRIVALS
				? `too few arrivals: ${stop.n} of ${MIN_ARRIVALS} needed`
				: (stop.all[key]! / 60).toFixed(1);
</script>

<ChartFigure
	empty={!rows.some(trusted)}
	render={(width) => routeChart(stops, { width })}
	label={routeChartLabel(stops, to)}
	{caption}
	source={rows.every(trusted)
		? source
		: `${source} Gaps are stops with too few arrivals or none measured.`}
>
	{#snippet extra()}
		<p class="caption text-ink-muted mt-2">
			The dark line is the median. The lighter line is the 90th percentile, which one arrival in ten
			was later than.
		</p>
		<div class="sr-only">
			<table>
				<caption>
					Median and 90th percentile delay in minutes at each stop, in route order. No data means
					fewer than {MIN_ARRIVALS} measured arrivals.
				</caption>
				<thead>
					<tr>
						<th scope="col">Stop</th>
						<th scope="col">Median delay (minutes)</th>
						<th scope="col">90th percentile (minutes)</th>
					</tr>
				</thead>
				<tbody>
					{#each rows as stop (stop.id + stop.seq)}
						<tr>
							<th scope="row">{stop.name}</th>
							<td>{minutes(stop, 'med')}</td>
							<td>{minutes(stop, 'p90')}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/snippet}
</ChartFigure>
