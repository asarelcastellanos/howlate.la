<script lang="ts">
	import { resolve } from '$app/paths';
	import Guard from '#lib/charts/Guard.svelte';
	import Remote from '#lib/charts/Remote.svelte';
	import { DATA_BASE } from '#lib/data/base.ts';
	import { readRankingIndex } from '#lib/data/read.ts';
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import Rule from '#lib/design/Rule.svelte';
	import RankingBody from './RankingBody.svelte';
</script>

<svelte:head>
	<title>Line reliability ranking · HowLate</title>
	<meta
		name="description"
		content="LA Metro bus lines in order of the share of measured arrivals that came from 1 minute early to 5 minutes late, with median delay and 90th percentile."
	/>
</svelte:head>

<Masthead dateline="Ranking" />

<main class="page pb-16">
	<section class="pt-10 pb-6">
		<Kicker>Ranking</Kicker>
		<Headline dek="Metro bus lines in order of the share of measured arrivals that were on time.">
			Line reliability ranking
		</Headline>
	</section>

	<Rule weight="thick" />
	<section class="my-8">
		<Headline level={2} size="md">How lines are ranked</Headline>
		<p class="mt-4">
			HowLate ranks a bus line by its on-time share. That is the share of measured arrivals that
			came from 1 minute early to 5 minutes late, counted at every stop. Lines with a higher share
			rank higher. <a href={resolve('/methods')}>How HowLate measures delay</a>
		</p>
		<p class="mt-4">
			Lines are scored at every stop, not only at timepoints, so the numbers differ from Metro's
			published on-time performance.
		</p>
		<p class="caption text-ink-muted mt-2">Not Metro's published figure.</p>
	</section>

	<Rule />
	<div class="wide mt-8">
		<Guard>
			<Remote load={() => readRankingIndex(DATA_BASE)}>
				{#snippet children(index)}<RankingBody {index} />{/snippet}
			</Remote>
		</Guard>
	</div>
</main>
