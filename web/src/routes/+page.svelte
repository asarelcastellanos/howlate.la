<script lang="ts">
	import { DATA_BASE } from '#lib/data/base.ts';
	import { readStatus } from '#lib/data/read.ts';
	import Remote from '#lib/charts/Remote.svelte';
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import StatusStrip from '#lib/design/StatusStrip.svelte';
</script>

<svelte:head>
	<title>HowLate</title>
</svelte:head>

<Masthead dateline="LA Metro bus and rail" />

<main class="page py-12">
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
</main>
