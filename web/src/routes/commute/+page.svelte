<script lang="ts">
	import Remote from '#lib/charts/Remote.svelte';
	import { loadCommutePage } from '#lib/commute/page.ts';
	import { DATA_BASE } from '#lib/data/base.ts';
	import Headline from '#lib/design/Headline.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import PageHead from '#lib/PageHead.svelte';
	import CommuteTool from './CommuteTool.svelte';
</script>

<PageHead
	title="Plan a bus commute"
	description="Pick two stops on a bus line and a time. HowLate says which bus to catch, how late it usually is and how bad it gets."
	path="/commute"
/>

<Masthead dateline="LA Metro bus" />

<main id="main" class="page pt-10 pb-16">
	<Headline
		dek="Pick a bus line, two stops and a time. The answer comes from the days the bus has run."
	>
		Which bus should I catch?
	</Headline>
	<p class="text-ink-muted mt-4" data-testid="rail-note">
		Rail lines are not covered yet. This page answers for bus lines only.
	</p>
	<Remote load={() => loadCommutePage(DATA_BASE)}>
		{#snippet children(data)}
			<CommuteTool {data} />
		{/snippet}
	</Remote>
</main>
