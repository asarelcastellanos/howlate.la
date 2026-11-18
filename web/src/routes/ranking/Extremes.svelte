<script lang="ts">
	import Headline from '#lib/design/Headline.svelte';
	import OntimeMark from '#lib/design/OntimeMark.svelte';
	import { percent, type RankedLine } from '#lib/ranking.ts';
	import LineCell from './LineCell.svelte';

	let { title, lines, caption }: { title: string; lines: RankedLine[]; caption: string } = $props();
</script>

<section>
	<Headline level={2} size="md">{title}</Headline>
	<p class="caption text-ink-muted mt-1">{caption}</p>
	<ol class="data mt-3 border-t">
		{#each lines as { entry, rank } (entry.line)}
			<li
				class="grid grid-cols-[2rem_1fr] items-center gap-x-3 gap-y-1 border-b py-2 sm:grid-cols-[2rem_1fr_auto]"
			>
				<span class="font-semibold">{rank}</span>
				<span class="min-w-0"><LineCell {entry} /></span>
				<span class="col-start-2 font-semibold whitespace-nowrap sm:col-start-3"
					>{percent(entry.ontime)} on time<OntimeMark /></span
				>
			</li>
		{/each}
	</ol>
</section>
