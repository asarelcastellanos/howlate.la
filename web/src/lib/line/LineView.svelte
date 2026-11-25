<script module lang="ts">
	import type LineCharts from '#lib/charts/LineCharts.svelte';

	type ChartsComponent = typeof LineCharts;

	// Set once the chart code has loaded, so a second line page in the same visit
	// draws its charts with the headline and does not wait again.
	let drawn: ChartsComponent | undefined;
</script>

<script lang="ts">
	import { resolve } from '$app/paths';
	import { SHOW_RAIL_ONTIME } from '#lib/config.ts';
	import ErrorState from '#lib/charts/ErrorState.svelte';
	import LoadingState from '#lib/charts/LoadingState.svelte';
	import { LINE_LIST } from '#lib/data/lines.ts';
	import type { LineFile } from '#lib/data/types.ts';
	import Headline from '#lib/design/Headline.svelte';
	import EstimatedNote from '#lib/design/EstimatedNote.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import LineBullet from '#lib/design/LineBullet.svelte';
	import OntimeMark from '#lib/design/OntimeMark.svelte';
	import OntimeNote from '#lib/design/OntimeNote.svelte';
	import Rule from '#lib/design/Rule.svelte';
	import { findListed, lineHead, listEntryOfFile } from '#lib/lineHead.ts';
	import PageHead from '#lib/PageHead.svelte';
	import {
		RAIL_HOLD_NOTE,
		bulletProps,
		hasDirectionSwitch,
		headline,
		lineName,
		shortVia,
		showsOntime,
		sourceNote
	} from '#lib/linePage.ts';
	import DirectionSwitch from './DirectionSwitch.svelte';

	// The gate and `charts` are props so a test can set them. The route sets neither.
	// A test passes the chart component, which the page otherwise loads after it paints.
	let {
		line,
		showRailOntime = SHOW_RAIL_ONTIME,
		charts
	}: { line: LineFile; showRailOntime?: boolean; charts?: ChartsComponent } = $props();

	let selected = $state(0);
	const direction = $derived(line.directions[selected]);
	const name = $derived(lineName(line));
	const ontime = $derived(showsOntime(line.mode, showRailOntime));
	// A listed line gets the head its prerendered file has, so the title does not change when
	// the data arrives. A line the list lacks is described from the file it just loaded.
	const head = $derived(
		lineHead(findListed(LINE_LIST, line.line) ?? listEntryOfFile(line), line.line)
	);

	// The charts are 97 KB with Observable Plot in it, and the headline needs none of
	// it. Lighthouse counts every request that finishes before the headline paints
	// toward the page's largest contentful paint (LCP). One frame after the headline
	// mounted, the chunk still finished before that paint in 3 of 3 runs, and LCP on
	// the throttled mobile profile was 3.16 s. 100 ms later it finished after the
	// paint in every run, and LCP was 2.71 s in the 13 of 20 runs that did not
	// already paint the headline in the first frame, and 0.75 s in the rest. Both
	// are on a Mac. The charts are below the first screen on a phone, so the wait
	// is not seen.
	const CHART_DELAY_MS = 100;
	let loaded = $state.raw<ChartsComponent | undefined>(drawn);
	let chartsFailed = $state(false);
	const Charts = $derived(charts ?? loaded);
	$effect(() => {
		if (Charts) return;
		let timer: ReturnType<typeof setTimeout>;
		const frame = requestAnimationFrame(() => {
			timer = setTimeout(() => {
				import('#lib/charts/LineCharts.svelte').then(
					(module) => (loaded = drawn = module.default),
					() => (chartsFailed = true)
				);
			}, CHART_DELAY_MS);
		});
		return () => {
			cancelAnimationFrame(frame);
			clearTimeout(timer);
		};
	});
</script>

<PageHead
	title={head.title}
	description={head.description}
	path="/lines/{encodeURIComponent(line.line)}"
/>

<section class="pt-10 pb-6">
	<div class="mb-4"><LineBullet {...bulletProps(line)} size="lg" /></div>
	<Kicker>{line.mode === 'rail' ? 'Rail line' : 'Bus route'}</Kicker>
	<Headline dek={line.via ? shortVia(line.via) : undefined}>{name}</Headline>
</section>

<Rule weight="thick" />
<section class="my-8">
	<Headline level={2} size="md">How late it runs</Headline>
	<ul class="mt-4">
		{#each line.directions as d, i (d.id)}
			<li class="border-t py-4">
				{headline(d, i, line.mode, showRailOntime)}{#if ontime}<OntimeMark />{/if}
				<EstimatedNote n={d.all.n} est={d.all.est} class="mt-1" />
			</li>
		{/each}
	</ul>
	{#if ontime}
		<OntimeNote class="mt-2" />
	{:else}
		<p class="mt-2">{RAIL_HOLD_NOTE}</p>
	{/if}
</section>

{#if line.mode === 'bus'}
	<p class="mb-8">
		<a href="{resolve('/commute')}?line={encodeURIComponent(line.line)}"
			>Plan a commute on this bus</a
		>
	</p>
{/if}
<Rule />
{#if hasDirectionSwitch(line)}<DirectionSwitch
		directions={line.directions}
		bind:value={selected}
	/>{/if}
<section class="wide">
	{#if Charts}
		<Charts
			{name}
			to={direction.to}
			profile={direction.profile}
			showOntime={ontime}
			stops={direction.stops}
			source={sourceNote(line)}
		/>
	{:else if chartsFailed}
		<!-- A chunk that failed to load is not retried by the browser, so the retry reloads the page. -->
		<ErrorState onretry={() => location.reload()} />
	{:else}
		<LoadingState />
	{/if}
</section>
