<script lang="ts">
	import { moveActive } from '../search.ts';
	import { nearestStop, searchStops, type Stop } from './stops.ts';

	let { stops, selected = $bindable() }: { stops: Stop[]; selected?: Stop } = $props();

	const uid = $props.id();
	let query = $state('');
	let open = $state(false);
	let active = $state(0);
	let root = $state<HTMLDivElement>();
	let input = $state<HTMLInputElement>();
	let phase = $state<'idle' | 'locating' | 'found' | 'none'>('idle');

	const results = $derived(searchStops(stops, query));
	const showList = $derived(open && results.length > 0);
	const noMatch = $derived(query.trim() !== '' && results.length === 0);
	const optionId = (i: number) => `${uid}-option-${i}`;

	function pick(stop: Stop) {
		selected = stop;
		phase = 'idle';
		query = '';
		open = false;
	}

	function noLocation() {
		phase = 'none';
		input?.focus();
	}

	function findNearest() {
		if (!('geolocation' in navigator)) return noLocation();
		phase = 'locating';
		navigator.geolocation.getCurrentPosition(
			(position) => {
				const stop = nearestStop(stops, position.coords.latitude, position.coords.longitude);
				if (!stop) return noLocation();
				pick(stop);
				phase = 'found';
			},
			noLocation,
			{ timeout: 10_000, maximumAge: 300_000 }
		);
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			if (!open) open = true;
			else active = moveActive(active, event.key, results.length);
		} else if (event.key === 'Enter' && showList) {
			event.preventDefault();
			pick(results[active]);
		} else if (event.key === 'Escape') {
			if (open) open = false;
			else query = '';
		}
	}

	$effect(() => {
		if (showList) document.getElementById(optionId(active))?.scrollIntoView({ block: 'nearest' });
	});
</script>

<div
	bind:this={root}
	role="search"
	onfocusout={(event) => {
		if (!root?.contains(event.relatedTarget as Node | null)) open = false;
	}}
>
	<button
		type="button"
		onclick={findNearest}
		disabled={phase === 'locating'}
		class="border-ink bg-paper text-ink font-sans hover:bg-sunk mb-4 min-h-12 border px-4 py-2 text-body disabled:cursor-wait disabled:opacity-60"
	>
		{phase === 'locating' ? 'Finding your location' : 'Use my location'}
	</button>
	<label for="{uid}-input" class="kicker text-ink-muted block">Find a stop</label>
	<input
		bind:this={input}
		id="{uid}-input"
		type="text"
		role="combobox"
		aria-expanded={showList}
		aria-controls="{uid}-list"
		aria-autocomplete="list"
		aria-activedescendant={showList ? optionId(active) : undefined}
		autocomplete="off"
		autocapitalize="off"
		spellcheck="false"
		enterkeyhint="go"
		placeholder="Wilshire / Vermont"
		bind:value={query}
		oninput={() => {
			open = true;
			active = 0;
		}}
		onfocus={() => (open = true)}
		{onkeydown}
		class="border-ink bg-paper text-ink font-sans mt-2 block min-h-12 w-full border px-4 py-2 text-body"
	/>
	<ul
		id="{uid}-list"
		role="listbox"
		aria-label="Matching stops"
		hidden={!showList}
		class="border-ink bg-paper font-sans border border-t-0"
	>
		{#each results as stop, i (stop.id)}
			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<li
				id={optionId(i)}
				role="option"
				aria-selected={i === active}
				onmousedown={(event) => event.preventDefault()}
				onclick={() => pick(stop)}
				class="flex min-h-14 cursor-pointer items-center gap-3 border-b border-l-4 px-3 py-2 last:border-b-0 {i ===
				active
					? 'bg-sunk border-l-ink'
					: 'border-l-transparent'}"
			>
				<span class="min-w-0">
					<span class="data block font-semibold">{stop.name}</span>
					<span class="caption text-ink-muted block">Stop {stop.id}</span>
				</span>
			</li>
		{/each}
	</ul>
	<p role="status" class={noMatch || phase !== 'idle' || selected ? 'data mt-3' : 'sr-only'}>
		{#if noMatch}
			No stop matches that. Try part of a street name, like Wilshire.
		{:else if showList}
			{results.length === 1 ? '1 stop matches' : `${results.length} stops match`}. Use the up and
			down arrow keys, then Enter.
		{:else if phase === 'locating'}
			Finding the stop nearest you.
		{:else if selected}
			{phase === 'found' ? 'Nearest stop' : 'Chosen stop'}: {selected.name}, stop {selected.id}.
		{:else if phase === 'none'}
			We could not get your location. Type part of a stop name to search.
		{/if}
	</p>
</div>
