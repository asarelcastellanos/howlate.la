<script lang="ts">
	import { resolve } from '$app/paths';
	import { DATA_BASE } from '#lib/data/base.ts';
	import Remote from '#lib/charts/Remote.svelte';
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import SearchBox from '#lib/design/SearchBox.svelte';
	import StatusStrip from '#lib/design/StatusStrip.svelte';
	import { loadHome } from '#lib/home.ts';
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
	<!-- One Remote reads the status and the index from one run, so the strip and the
	     search list never come from two different daily runs. The "Find a line" links
	     point at #search, so the loading and error states carry an empty anchor and
	     the prerendered page has the id before the data arrives. -->
	<Remote load={() => loadHome(DATA_BASE)}>
		{#snippet heading()}<div id="search" class="mt-10 scroll-mt-6"></div>{/snippet}
		{#snippet children({ status, index })}
			<div class="wide mt-10"><StatusStrip {status} /></div>
			<div id="search" class="mt-10 scroll-mt-6"><SearchBox entries={index.lines} /></div>
		{/snippet}
	</Remote>
	<p class="mt-10"><a href={resolve('/methods')}>How HowLate measures delay</a></p>
</main>
