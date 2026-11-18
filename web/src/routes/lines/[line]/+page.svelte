<script lang="ts">
	import { page } from '$app/state';
	import Remote from '#lib/charts/Remote.svelte';
	import { DATA_BASE } from '#lib/data/base.ts';
	import { LINE_LIST } from '#lib/data/lines.ts';
	import Headline from '#lib/design/Headline.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import LineNotFound from '#lib/line/LineNotFound.svelte';
	import LineView from '#lib/line/LineView.svelte';
	import { lineHead, findListed } from '#lib/lineHead.ts';
	import PageHead from '#lib/PageHead.svelte';
	import { loadLinePage } from '#lib/linePage.ts';

	const id = $derived(page.params.line ?? '');
	// The prerendered HTML and the first browser render both read the committed list,
	// so they agree and hydration does not rewrite the head.
	const head = $derived(lineHead(findListed(LINE_LIST, id), id));
</script>

<Masthead dateline="LA Metro bus and rail" />

<main id="main" class="page pb-16">
	<!-- A new id starts a new load, so a client-side move between lines never shows the old one. -->
	{#key id}
		<Remote load={() => loadLinePage(DATA_BASE, id)}>
			<!-- Every state has one h1. The label replaces this one when the data arrives. The
			     head follows the same split. LineView and LineNotFound set theirs, and this
			     one covers loading and failed loads, so one title is in the head at a time. -->
			{#snippet heading()}
				<PageHead
					title={head.title}
					description={head.description}
					path="/lines/{encodeURIComponent(id)}"
				/>
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
