<script lang="ts">
	import { resolve } from '$app/paths';
	import LineCharts from '#lib/charts/LineCharts.svelte';
	import { SHOW_RAIL_ONTIME } from '#lib/config.ts';
	import type { LineFile } from '#lib/data/types.ts';
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import LineBullet from '#lib/design/LineBullet.svelte';
	import Rule from '#lib/design/Rule.svelte';
	import PageHead from '#lib/PageHead.svelte';
	import {
		ONTIME_WINDOW,
		RAIL_HOLD_NOTE,
		bulletProps,
		hasDirectionSwitch,
		headline,
		lineName,
		pageDescription,
		shortVia,
		showsOntime,
		sourceNote
	} from '#lib/linePage.ts';
	import DirectionSwitch from './DirectionSwitch.svelte';

	// The gate is a prop so a test can open it. The route never sets it.
	let { line, showRailOntime = SHOW_RAIL_ONTIME }: { line: LineFile; showRailOntime?: boolean } =
		$props();

	let selected = $state(0);
	const direction = $derived(line.directions[selected]);
	const name = $derived(lineName(line));
	const ontime = $derived(showsOntime(line.mode, showRailOntime));
</script>

<PageHead
	title={name}
	description={pageDescription(line)}
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
			<li class="border-t py-4">{headline(d, i, line.mode, showRailOntime)}</li>
		{/each}
	</ul>
	{#if ontime}
		<p class="caption text-ink-muted mt-2">
			On time means {ONTIME_WINDOW}.
			<a href={resolve('/methods')}>How HowLate measures delay</a>
		</p>
		<p class="caption text-ink-muted mt-1">Not Metro's published figure.</p>
	{:else}
		<p class="mt-2">{RAIL_HOLD_NOTE}</p>
	{/if}
</section>

<Rule />
{#if hasDirectionSwitch(line)}<DirectionSwitch
		directions={line.directions}
		bind:value={selected}
	/>{/if}
<section class="wide">
	<LineCharts
		{name}
		to={direction.to}
		profile={direction.profile}
		showOntime={ontime}
		stops={direction.stops}
		source={sourceNote(line)}
	/>
</section>
