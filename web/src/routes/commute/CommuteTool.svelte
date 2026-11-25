<script lang="ts">
	import { untrack } from 'svelte';
	import { replaceState } from '$app/navigation';
	import ErrorState from '#lib/charts/ErrorState.svelte';
	import LoadingState from '#lib/charts/LoadingState.svelte';
	import Notice from '#lib/charts/Notice.svelte';
	import { arrivalSpread, answer, sentence, todayDayType, type Mode } from '#lib/commute/answer.ts';
	import type { CommuteFile, CommuteStop, DayType } from '#lib/commute/file.ts';
	import {
		directionLabel,
		directionsOf,
		linesOf,
		minuteOf,
		readQuery,
		writeQuery,
		type CommutePageData
	} from '#lib/commute/page.ts';
	import StopPicker from '#lib/commute/StopPicker.svelte';
	import { stopsInDirection } from '#lib/commute/stops.ts';
	import type { LoadError } from '#lib/data/load.ts';
	import { LINE_LIST } from '#lib/data/lines.ts';
	import Headline from '#lib/design/Headline.svelte';
	import { findListed } from '#lib/lineHead.ts';
	import { lineName } from '#lib/linePage.ts';
	import Segmented from './Segmented.svelte';
	import SpreadChart from './SpreadChart.svelte';

	let { data }: { data: CommutePageData } = $props();

	type FileState =
		| { kind: 'idle' }
		| { kind: 'loading' }
		| { kind: 'none' }
		| { kind: 'error'; error: LoadError }
		| { kind: 'ready'; file: CommuteFile };

	const DAY_OPTIONS: { value: DayType; label: string }[] = [
		{ value: 'weekday', label: 'Weekday' },
		{ value: 'saturday', label: 'Saturday' },
		{ value: 'sunday', label: 'Sunday' }
	];
	const MODE_OPTIONS: { value: Mode; label: string }[] = [
		{ value: 'leave', label: 'Leave at' },
		{ value: 'arrive', label: 'Arrive by' }
	];
	const DAY_NAMES: Record<DayType, string> = {
		weekday: 'weekday',
		saturday: 'Saturday',
		sunday: 'Sunday'
	};

	// The address is read once, when the form first draws. It is read from the
	// browser's location and not from the router, because the page is prerendered
	// and the router has no query string at build time.
	const start = untrack(() => readQuery(location.search, data.index));
	let line = $state(start.line ?? '');
	let direction = $state<number | undefined>(start.direction);
	let dayType = $state<DayType>(start.dayType ?? todayDayType(new Date()));
	let mode = $state<Mode>(start.mode ?? 'leave');
	let time = $state(start.time ?? '08:00');
	let fromId = $state<string | undefined>(start.from);
	let toId = $state<string | undefined>(start.to);
	let fileState = $state.raw<FileState>({ kind: 'idle' });
	let attempt = $state(0);

	const lines = $derived(linesOf(data.index));
	const directions = $derived(line ? directionsOf(data.index, line) : []);
	const listed = $derived(findListed(LINE_LIST, line));
	const minute = $derived(minuteOf(time));

	const routeStops = $derived(
		fileState.kind === 'ready' ? stopsInDirection(data.stops, fileState.file.stops) : []
	);
	const fromAt = $derived(routeStops.findIndex((s) => s[0] === fromId));
	const toChoices = $derived(fromAt < 0 ? [] : routeStops.slice(fromAt + 1));
	const fromStop = $derived(fromAt < 0 ? undefined : routeStops[fromAt]);
	const toStop = $derived(toChoices.find((s) => s[0] === toId));

	$effect(() => {
		void attempt;
		if (!line || direction === undefined) {
			fileState = { kind: 'idle' };
			return;
		}
		const wanted = direction;
		const there = data.index.files.some(
			(f) => f.line === line && f.direction === wanted && f.day_type === dayType
		);
		if (!there) {
			fileState = { kind: 'none' };
			return;
		}
		let current = true;
		fileState = { kind: 'loading' };
		data.run
			.route(line, wanted, dayType)
			.catch((): { ok: false; error: LoadError } => ({
				ok: false,
				error: { kind: 'network', url: '' }
			}))
			.then((result) => {
				if (!current) return;
				fileState = result.ok
					? { kind: 'ready', file: result.data }
					: { kind: 'error', error: result.error };
			});
		return () => {
			current = false;
		};
	});

	// A stop from the address, or one kept across a day type, may not be served by
	// the file that just loaded. It is dropped, so the picker never shows a stop the
	// answer cannot use.
	$effect(() => {
		if (fileState.kind !== 'ready') return;
		if (fromId && !fromStop) fromId = undefined;
		if (toId && !toStop) toId = undefined;
	});

	$effect(() => {
		const query = writeQuery({ line, direction, dayType, from: fromId, to: toId, mode, time });
		// The address stays on this page and only its query changes, so the lint rule's
		// resolve() has nothing to resolve. A bare query keeps the page's own path.
		// eslint-disable-next-line svelte/no-navigation-without-resolve
		replaceState(`?${query}`, {});
	});

	const result = $derived(
		fileState.kind === 'ready' && fromStop && toStop && minute !== null
			? answer(fileState.file, fromStop[0], toStop[0], mode, minute)
			: undefined
	);
	const text = $derived(result ? sentence(result) : '');
	const spread = $derived(
		fileState.kind === 'ready' && fromStop && toStop && result?.kind === 'answer'
			? arrivalSpread(fileState.file, result.start, fromStop[0], toStop[0])
			: null
	);

	function chooseLine(next: string) {
		line = next;
		direction = next ? directionsOf(data.index, next)[0] : undefined;
		fromId = toId = undefined;
	}

	function chooseDirection(next: string) {
		direction = Number(next);
		fromId = toId = undefined;
	}

	const field =
		'border-ink bg-paper text-ink font-sans block min-h-12 w-full border px-4 py-2 text-body';
	const pickerKey = $derived(`${line}-${direction}-${dayType}`);
</script>

<form class="mt-8" onsubmit={(event) => event.preventDefault()}>
	<div>
		<label for="commute-line" class="kicker text-ink-muted mb-2 block">Bus line</label>
		<select
			id="commute-line"
			class={field}
			value={line}
			onchange={(event) => chooseLine(event.currentTarget.value)}
		>
			<option value="">Choose a line</option>
			{#each lines as id (id)}
				{@const entry = findListed(LINE_LIST, id)}
				<option value={id}>{entry ? lineName(entry) : `Route ${id}`}</option>
			{/each}
		</select>
	</div>

	{#if directions.length > 0 && direction !== undefined}
		<Segmented
			legend="Direction"
			stack
			value={String(direction)}
			options={directions.map((id) => ({
				value: String(id),
				label: directionLabel(listed, directions, id)
			}))}
			onchange={chooseDirection}
		/>
		<Segmented
			legend="Day"
			value={dayType}
			options={DAY_OPTIONS}
			onchange={(value) => (dayType = value as DayType)}
		/>

		{#if fileState.kind === 'loading'}
			<div class="mt-6"><LoadingState /></div>
		{:else if fileState.kind === 'error'}
			<div class="mt-6">
				<ErrorState error={fileState.error} onretry={() => attempt++} />
			</div>
		{:else if fileState.kind === 'none'}
			<div class="mt-6">
				<Notice role="status">
					<p>No {DAY_NAMES[dayType]} timetable for this direction. Try another day.</p>
				</Notice>
			</div>
		{:else if fileState.kind === 'ready'}
			{#key pickerKey}
				<fieldset class="mt-6 min-w-0">
					<legend class="kicker text-ink-muted mb-2">From</legend>
					<StopPicker
						stops={routeStops}
						bind:selected={
							() => fromStop,
							(stop: CommuteStop | undefined) => {
								fromId = stop?.[0];
								toId = undefined;
							}
						}
					/>
				</fieldset>
			{/key}
			<fieldset class="mt-6 min-w-0">
				<legend class="kicker text-ink-muted mb-2">To</legend>
				{#if fromStop}
					{#key `${pickerKey}-${fromId}`}
						<StopPicker
							stops={toChoices}
							bind:selected={() => toStop, (stop: CommuteStop | undefined) => (toId = stop?.[0])}
						/>
					{/key}
				{:else}
					<p class="text-ink-muted">Choose a From stop first. The To stop comes after it.</p>
				{/if}
			</fieldset>

			<Segmented
				legend="Plan by"
				value={mode}
				options={MODE_OPTIONS}
				onchange={(value) => (mode = value as Mode)}
			/>
			<div class="mt-6">
				<label for="commute-time" class="kicker text-ink-muted mb-2 block">Time</label>
				<input
					id="commute-time"
					type="time"
					required
					bind:value={time}
					aria-invalid={minute === null}
					class="{field} sm:w-48"
				/>
			</div>
		{/if}
	{/if}
</form>

<section class="mt-10" aria-labelledby="commute-answer">
	<Headline level={2} size="md"><span id="commute-answer">Your bus</span></Headline>
	<p
		role="status"
		aria-live="polite"
		aria-atomic="true"
		data-testid="commute-answer"
		class="mt-4 text-dek"
	>
		{text}
	</p>
	{#if !result}
		<p class="text-ink-muted mt-4">
			{#if !line}
				Choose a bus line, a direction, and two stops. The answer appears here.
			{:else if fileState.kind === 'ready' && minute === null}
				Enter a time to get an answer.
			{:else if fileState.kind === 'ready'}
				Choose both stops. The answer appears here.
			{/if}
		</p>
	{/if}
	{#if spread}
		<SpreadChart {spread} />
	{/if}
</section>
