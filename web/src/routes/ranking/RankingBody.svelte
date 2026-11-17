<script lang="ts">
	import Notice from '#lib/charts/Notice.svelte';
	import type { SiteIndex } from '#lib/data/types.ts';
	import Headline from '#lib/design/Headline.svelte';
	import Rule from '#lib/design/Rule.svelte';
	import { longDate } from '#lib/date.ts';
	import { MIN_RANKED_ARRIVALS, count, ends, rankLines } from '#lib/ranking.ts';
	import Extremes from './Extremes.svelte';
	import LineCell from './LineCell.svelte';
	import RailTable from './RailTable.svelte';
	import RankedTable from './RankedTable.svelte';

	let { index }: { index: SiteIndex } = $props();

	const EDGE = 5;
	// The page ranks buses only. Rail has its own table, so it never reaches rankLines.
	const bus = $derived(index.lines.filter((line) => line.mode === 'bus'));
	const rail = $derived(index.lines.filter((line) => line.mode === 'rail'));
	const result = $derived(rankLines(bus, 'ontime'));
	const edges = $derived(ends(result.ranked, EDGE));
	// Fewer than 2 * EDGE ranked lines leave the bottom panel short or empty, so
	// the caption counts the lines it lists.
	const caption = (shown: unknown[], which: 'highest' | 'lowest') => {
		const listed = Math.min(shown.length, EDGE);
		const tieNote = shown.length > EDGE ? ', plus any line that ties with the fifth' : '';
		return `The ${listed} bus ${listed === 1 ? 'line' : 'lines'} with the ${which} on-time share${tieNote}.`;
	};
</script>

<p class="kicker text-ink-muted">
	{index.days} days of data, {longDate(index.first_day)} to {longDate(index.last_day)}
</p>

{#if result.ranked.length === 0}
	<div class="mt-6">
		<Notice role="status"><p>No bus line has enough measured arrivals to rank yet.</p></Notice>
	</div>
{:else}
	<div class="mt-6 grid gap-x-10 gap-y-8 md:grid-cols-2">
		<Extremes title="Most reliable" lines={edges.top} caption={caption(edges.top, 'highest')} />
		{#if edges.bottom.length > 0}
			<Extremes
				title="Least reliable"
				lines={edges.bottom}
				caption={caption(edges.bottom, 'lowest')}
			/>
		{/if}
	</div>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">All bus lines</Headline>
		<p class="caption text-ink-muted mt-2 mb-4">
			Ranked by on-time share, the share of measured arrivals from 1 minute early to 5 minutes late.
			Median delay and 90th percentile are in minutes. Click a heading to sort by it. For median
			delay and 90th percentile, a line closer to on time ranks higher, whether it runs early or
			late, and inside the on-time window the smaller delay ranks higher.
		</p>
		<RankedTable entries={bus} />
	</section>
{/if}

{#if result.unranked.length > 0}
	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">Not ranked</Headline>
		<p class="mt-2">
			These bus lines have fewer than {count(MIN_RANKED_ARRIVALS)} measured arrivals. A handful of arrivals
			changing would move their on-time share by more than a point, so they are not ranked.
		</p>
		<ul class="data mt-4 border-t">
			{#each result.unranked as entry (entry.line)}
				<li
					class="flex flex-col gap-1 border-b py-2 sm:flex-row sm:items-center sm:justify-between sm:gap-4"
				>
					<LineCell {entry} />
					<span class="whitespace-nowrap">{count(entry.n)} arrivals measured</span>
				</li>
			{/each}
		</ul>
	</section>
{/if}

{#if rail.length > 0}
	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">Rail lines</Headline>
		<div class="mt-2"><RailTable entries={rail} /></div>
	</section>
{/if}
