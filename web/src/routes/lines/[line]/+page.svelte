<script lang="ts">
	import { page } from '$app/state';
	import Remote from '#lib/charts/Remote.svelte';
	import { DATA_BASE } from '#lib/data/base.ts';
	import Headline from '#lib/design/Headline.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import LineNotFound from '#lib/line/LineNotFound.svelte';
	import LineView from '#lib/line/LineView.svelte';
	import { loadLinePage } from '#lib/linePage.ts';

	const id = $derived(page.params.line ?? '');
</script>

<svelte:head>
	<title>Line {id} · HowLate</title>
</svelte:head>

<Masthead dateline="LA Metro bus and rail" />

<main class="page pb-16">
	<!-- A new id starts a new load, so a client-side move between lines never shows the old one. -->
	{#key id}
		<Remote load={() => loadLinePage(DATA_BASE, id)}>
			<!-- Every state has one h1. The label replaces this one when the data arrives. -->
			{#snippet heading()}
				<section class="pt-10 pb-6"><Headline>Line {id}</Headline></section>
			{/snippet}
			{#snippet children(result)}
				{#if result.kind === 'found'}
					<LineView line={result.line} />
				{:else}
					<LineNotFound {id} />
				{/if}
			{/snippet}
		</Remote>
	{/key}
</main>
