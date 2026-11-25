<script lang="ts">
	import { onDestroy, tick } from 'svelte';
	import { moveActive } from '../search.ts';
	import type { CommuteStop } from './file.ts';
	import {
		MAX_NEAREST_M,
		distanceMeters,
		nearestStop,
		searchStops,
		searchStopsNear
	} from './stops.ts';

	let { stops, selected = $bindable() }: { stops: CommuteStop[]; selected?: CommuteStop } =
		$props();

	const MAX_AGE_MS = 300_000;
	const uid = $props.id();
	let query = $state('');
	let open = $state(false);
	let active = $state(0);
	let root = $state<HTMLDivElement>();
	let input = $state<HTMLInputElement>();
	let button = $state<HTMLButtonElement>();
	let change = $state<HTMLButtonElement>();
	let here = $state<{ lat: number; lon: number }>();
	let expiry: ReturnType<typeof setTimeout> | undefined;
	let phase = $state<
		'idle' | 'locating' | 'found' | 'denied' | 'unavailable' | 'unsupported' | 'far'
	>('idle');

	const results = $derived(
		here ? searchStopsNear(stops, query, here.lat, here.lon) : searchStops(stops, query)
	);
	const showList = $derived(open && results.length > 0);
	const noMatch = $derived(query.trim() !== '' && results.length === 0);
	const optionId = (i: number) => `${uid}-option-${i}`;

	const away = (stop: CommuteStop) => {
		if (!here) return '';
		const meters = Math.round(distanceMeters(stop, here.lat, here.lon) / 10) * 10;
		return meters < 1000 ? `, ${meters} m away` : `, ${(meters / 1000).toFixed(1)} km away`;
	};

	const message = $derived(
		noMatch
			? 'No stop matches that. Try part of a street name, like Wilshire.'
			: phase === 'locating'
				? 'Finding the stop nearest you.'
				: phase === 'denied'
					? 'Location is off for this site. Search by name.'
					: phase === 'unavailable'
						? 'We could not find your location. Search by name.'
						: phase === 'unsupported'
							? 'This browser cannot share a location. Search by name.'
							: phase === 'far'
								? `No stop within ${MAX_NEAREST_M / 1000} km of you. Search by name.`
								: ''
	);
	const announcement = $derived(
		message ||
			(showList
				? `${results.length} ${results.length === 1 ? 'stop matches' : 'stops match'}.`
				: selected
					? `${phase === 'found' ? 'Nearest stop' : 'Chosen stop'}: ${selected[1]}, stop ${selected[0]}.`
					: '')
	);

	async function pick(stop: CommuteStop) {
		const refocus = document.activeElement === input || document.activeElement === button;
		selected = stop;
		phase = 'idle';
		query = '';
		open = false;
		if (refocus) {
			await tick();
			change?.focus();
		}
	}

	async function clear() {
		selected = undefined;
		phase = 'idle';
		await tick();
		input?.focus();
	}

	function fail(next: 'denied' | 'unavailable' | 'unsupported' | 'far') {
		if (phase !== 'locating') return;
		phase = next;
		if (document.activeElement === button) input?.focus();
	}

	function remember(lat: number, lon: number, timestamp: number) {
		clearTimeout(expiry);
		const left = timestamp + MAX_AGE_MS - Date.now();
		if (left <= 0) {
			here = undefined;
			return;
		}
		here = { lat, lon };
		expiry = setTimeout(() => (here = undefined), left);
	}

	onDestroy(() => clearTimeout(expiry));

	function findNearest() {
		if (phase === 'locating') return;
		if (!('geolocation' in navigator)) {
			phase = 'unsupported';
			input?.focus();
			return;
		}
		phase = 'locating';
		navigator.geolocation.getCurrentPosition(
			(position) => {
				if (phase !== 'locating') return;
				const { latitude, longitude } = position.coords;
				const stop = nearestStop(stops, latitude, longitude);
				if (!stop) return fail('far');
				remember(latitude, longitude, position.timestamp);
				void pick(stop);
				phase = 'found';
			},
			(error) => fail(error.code === error.PERMISSION_DENIED ? 'denied' : 'unavailable'),
			{ timeout: 10_000, maximumAge: MAX_AGE_MS }
		);
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			if (!open) open = true;
			else active = moveActive(active, event.key, results.length);
		} else if (event.key === 'Enter' && showList) {
			event.preventDefault();
			void pick(results[active]);
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
	{#if !selected}
		<button
			type="button"
			bind:this={button}
			onclick={findNearest}
			aria-disabled={phase === 'locating'}
			class="border-ink bg-paper text-ink font-sans hover:bg-sunk mb-4 min-h-12 border px-4 py-2 text-body aria-disabled:cursor-wait aria-disabled:opacity-60"
		>
			{phase === 'locating' ? 'Finding your location' : 'Use my location'}
		</button>
	{/if}

	{#if selected}
		<p class="kicker text-ink-muted">Your stop</p>
		<div
			class="border-ink bg-sunk font-sans mt-2 flex flex-col gap-3 border px-4 py-2 min-[30rem]:flex-row min-[30rem]:items-center"
		>
			<div class="min-w-0 flex-1">
				<span class="data block font-semibold">{selected[1]}</span>
				<span class="caption text-ink-muted block">
					Stop {selected[0]}{away(selected)}
				</span>
			</div>
			<button
				type="button"
				bind:this={change}
				onclick={clear}
				class="border-ink bg-paper text-ink hover:bg-sunk min-h-12 border px-4 py-2 text-body"
			>
				Change stop
			</button>
		</div>
	{:else}
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
			placeholder="Street or intersection"
			bind:value={query}
			oninput={() => {
				if (phase === 'locating') phase = 'idle';
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
			class="border-ink bg-paper font-sans max-h-64 overflow-y-auto border border-t-0"
		>
			{#each results as stop, i (stop[0])}
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
						<span class="data block font-semibold">{stop[1]}</span>
						<span class="caption text-ink-muted block">
							Stop {stop[0]}{away(stop)}
						</span>
					</span>
				</li>
			{/each}
		</ul>
	{/if}
	<p class={message ? 'data mt-3' : 'sr-only'} aria-hidden="true">{message}</p>
	<p class="sr-only" role="status">{announcement}</p>
</div>
