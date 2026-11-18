<script lang="ts">
	import type { IndexEntry } from '#lib/data/types.ts';
	import OntimeMark from '#lib/design/OntimeMark.svelte';
	import OntimeNote from '#lib/design/OntimeNote.svelte';
	import { RAIL_HOLD_NOTE, showsOntime } from '#lib/linePage.ts';
	import { count, delayText, percent } from '#lib/ranking.ts';
	import LineCell from './LineCell.svelte';

	// The gate is a prop so a test can close it. The page sets nothing.
	let {
		entries,
		showRailOntime = showsOntime('rail')
	}: { entries: IndexEntry[]; showRailOntime?: boolean } = $props();
</script>

<p>
	{#if !showRailOntime}{RAIL_HOLD_NOTE}{/if}
	Rail lines are listed here and are not ranked against buses.
</p>
{#if showRailOntime}<OntimeNote class="mt-2" />{/if}
<p class="caption text-ink-muted mt-2 md:hidden">Scroll the table sideways to see every column.</p>
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="mt-2 overflow-x-auto border-y"
	role="region"
	aria-label="Rail lines. Scrolls sideways on a narrow screen."
	tabindex="0"
>
	<table class="data-table min-w-[36rem]">
		<thead>
			<tr>
				<th scope="col" class="align-bottom">Line</th>
				{#if showRailOntime}<th scope="col" class="align-bottom">On time<OntimeMark /></th>{/if}
				<th scope="col" class="align-bottom">Median delay</th>
				<th scope="col" class="align-bottom">90th percentile</th>
				<th scope="col" class="align-bottom">Arrivals measured</th>
			</tr>
		</thead>
		<tbody>
			{#each entries as entry (entry.line)}
				<tr>
					<td class="min-w-[11rem]"><LineCell {entry} /></td>
					{#if showRailOntime}<td class="whitespace-nowrap">{percent(entry.ontime)}</td>{/if}
					<td class="whitespace-nowrap">{delayText(entry.med)}</td>
					<td class="whitespace-nowrap">{delayText(entry.p90)}</td>
					<td class="whitespace-nowrap">{count(entry.n)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
