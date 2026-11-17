<script lang="ts">
	import type { Snippet } from 'svelte';
	import Figure from '#lib/design/Figure.svelte';
	import Chart from './Chart.svelte';
	import Notice from './Notice.svelte';

	let {
		empty,
		render,
		label,
		onrender,
		caption,
		source,
		extra
	}: {
		empty: boolean;
		render: (width: number) => Element;
		label: string;
		onrender?: (svg: Element) => void | (() => void);
		caption: string;
		source: string;
		extra?: Snippet;
	} = $props();
</script>

{#snippet captionText()}{caption}{/snippet}
{#snippet sourceText()}{source}{/snippet}

<Figure caption={captionText} source={sourceText}>
	{#if empty}
		<Notice><p>Not enough measured arrivals yet.</p></Notice>
	{:else}
		<Chart {render} {label} {onrender} />
		{@render extra?.()}
	{/if}
</Figure>
