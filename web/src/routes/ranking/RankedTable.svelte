<script lang="ts">
	import type { IndexEntry } from '#lib/data/types.ts';
	import {
		DEFAULT_SORT,
		METRICS,
		ariaSort,
		count,
		delayText,
		nextSort,
		percent,
		rankLines,
		type Metric
	} from '#lib/ranking.ts';
	import LineCell from './LineCell.svelte';

	let { entries }: { entries: IndexEntry[] } = $props();

	let sort = $state(DEFAULT_SORT);
	const ranked = $derived(rankLines(entries, sort.metric, sort.order).ranked);
	const label = $derived(METRICS.find((m) => m.id === sort.metric)!.label);
	const direction = (metric: Metric) => {
		const value = ariaSort(sort, metric);
		return value === 'ascending' ? '↑' : value === 'descending' ? '↓' : '';
	};
</script>

<p class="sr-only" role="status">
	Sorted by {label}, {sort.order === 'best' ? 'best first' : 'worst first'}.
</p>
<p class="caption text-ink-muted mb-2 md:hidden">Scroll the table sideways to see every column.</p>
<!-- A scrollable region needs a tab stop, or a keyboard user cannot reach the far columns. -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="overflow-x-auto border-y"
	role="region"
	aria-label="Ranked bus lines. Scrolls sideways on a narrow screen."
	tabindex="0"
>
	<table class="data-table min-w-[44rem]">
		<thead>
			<tr>
				<th scope="col" class="align-bottom">Rank</th>
				<th scope="col" class="!text-left align-bottom">Line</th>
				{#each METRICS as metric (metric.id)}
					<th scope="col" class="align-bottom" aria-sort={ariaSort(sort, metric.id)}>
						<button
							type="button"
							class="cursor-pointer font-[inherit] uppercase hover:underline"
							onclick={() => (sort = nextSort(sort, metric.id))}
						>
							{metric.label}
							<span aria-hidden="true" class="inline-block w-3">{direction(metric.id)}</span>
						</button>
					</th>
				{/each}
				<th scope="col" class="align-bottom">Arrivals measured</th>
			</tr>
		</thead>
		<tbody>
			{#each ranked as { entry, rank } (entry.line)}
				<tr>
					<td class="font-semibold">{rank}</td>
					<td class="!text-left sm:min-w-[16rem]"><LineCell {entry} compact /></td>
					<td>
						<span class="inline-flex items-center justify-end gap-2">
							<!-- The bar repeats the number, which is always printed beside it. -->
							<span aria-hidden="true" class="bg-chart-grid inline-block h-1.5 w-6 sm:w-16">
								<span class="bg-chart-ink block h-full" style="width:{entry.ontime}%"></span>
							</span>
							<span class="w-11">{percent(entry.ontime)}</span>
						</span>
					</td>
					<td class="whitespace-nowrap">{delayText(entry.med)}</td>
					<td class="whitespace-nowrap">{delayText(entry.p90)}</td>
					<td class="whitespace-nowrap">{count(entry.n)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
