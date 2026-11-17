<script lang="ts">
	import { resolve } from '$app/paths';
	import { DATA_BASE } from '#lib/data/base.ts';
	import { readIndex, readStatus } from '#lib/data/read.ts';
	import Remote from '#lib/charts/Remote.svelte';
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import SearchBox from '#lib/design/SearchBox.svelte';
	import StatusStrip from '#lib/design/StatusStrip.svelte';
	import PageHead from '#lib/PageHead.svelte';
</script>

<PageHead
	title="HowLate · How late is LA Metro?"
	description="How late LA Metro buses and trains run, stop by stop, measured against the timetable."
	path="/"
/>

<Masthead dateline="LA Metro bus and rail" />

<main id="main" class="page py-12">
	<Kicker>Coming soon</Kicker>
	<Headline>How late is LA Metro?</Headline>
	<p class="mt-6">
		HowLate will show how late every LA Metro bus and train runs, stop by stop, measured against the
		timetable.
	</p>
	<div class="wide mt-10">
		<Remote load={() => readStatus(DATA_BASE)}>
			{#snippet children(status)}<StatusStrip {status} />{/snippet}
		</Remote>
	</div>
	<div id="search" class="mt-10 scroll-mt-6">
		<Remote load={() => readIndex(DATA_BASE)}>
			{#snippet children(index)}<SearchBox entries={index.lines} />{/snippet}
		</Remote>
	</div>
	<p class="mt-10"><a href={resolve('/methods')}>How HowLate measures delay</a></p>
</main>
