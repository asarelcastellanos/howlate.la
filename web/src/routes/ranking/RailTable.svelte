<script lang="ts">
	import type { IndexEntry } from '#lib/data/types.ts';
	import { RAIL_HOLD_NOTE } from '#lib/linePage.ts';
	import { count, delayText } from '#lib/ranking.ts';
	import LineCell from './LineCell.svelte';

	let { entries }: { entries: IndexEntry[] } = $props();
</script>

<p>{RAIL_HOLD_NOTE} Rail lines are not ranked.</p>
<p class="caption text-ink-muted mt-2 md:hidden">Scroll the table sideways to see every column.</p>
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="mt-2 overflow-x-auto border-y"
	role="region"
	aria-label="Rail lines. Scrolls sideways on a narrow screen."
	tabindex="0"
>
	<table class="data-table min-w-[32rem]">
		<thead>
			<tr>
				<th scope="col" class="align-bottom">Line</th>
				<th scope="col" class="align-bottom">Median delay</th>
				<th scope="col" class="align-bottom">90th percentile</th>
				<th scope="col" class="align-bottom">Arrivals measured</th>
			</tr>
		</thead>
		<tbody>
			{#each entries as entry (entry.line)}
				<tr>
					<td class="min-w-[11rem]"><LineCell {entry} /></td>
					<td class="whitespace-nowrap">{delayText(entry.med)}</td>
					<td class="whitespace-nowrap">{delayText(entry.p90)}</td>
					<td class="whitespace-nowrap">{count(entry.n)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
