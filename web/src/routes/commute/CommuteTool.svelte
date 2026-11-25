<script lang="ts">
	import { untrack } from 'svelte';
	import { replaceState } from '$app/navigation';
	import ErrorState from '#lib/charts/ErrorState.svelte';
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
	import LinePicker from './LinePicker.svelte';
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

	const start = untrack(() => readQuery(location.search, data.index));
	let line = $state(start.line ?? '');
	let direction = $state<number | undefined>(start.direction);
	let dayType = $state<DayType>(start.dayType ?? todayDayType(new Date()));
	let mode = $state<Mode>(start.mode ?? 'leave');
	let time = $state(start.time ?? '');
	let fromId = $state<string | undefined>(start.from);
	let toId = $state<string | undefined>(start.to);
	let fileState = $state.raw<FileState>({ kind: 'idle' });
	let shown = $state.raw<CommuteFile>();
	let answerEl = $state<HTMLElement>();
	let scrolled = false;
	const fullLink = !!(start.from && start.to && start.time);
	let attempt = $state(0);

	const lines = $derived(linesOf(data.index));
	const directions = $derived(line ? directionsOf(data.index, line) : []);
	const listed = $derived(findListed(LINE_LIST, line));
	const minute = $derived(minuteOf(time));

	const lineOptions = $derived(
		lines.map((id) => {
			const entry = findListed(LINE_LIST, id);
			return {
				...(entry ?? { line: id, label: id, mode: 'bus' as const, to: [], via: '' }),
				agency: 'LACMTA' as const
			};
		})
	);
	const routeStops = $derived(shown ? stopsInDirection(data.stops, shown.stops) : []);
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
		data.run.route(line, wanted, dayType).then((result) => {
			if (!current) return;
			if (result.ok) {
				shown = result.data;
				fileState = { kind: 'ready', file: result.data };
			} else fileState = { kind: 'error', error: result.error };
		});
		return () => {
			current = false;
		};
	});

	$effect(() => {
		if (fileState.kind !== 'ready') return;
		if (fromId && !fromStop) fromId = undefined;
		if (toId && !toStop) toId = undefined;
	});

	$effect(() => {
		const query = writeQuery({ line, direction, dayType, from: fromId, to: toId, mode, time });
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
		const only = next ? directionsOf(data.index, next) : [];
		direction = only.length === 1 ? only[0] : undefined;
		fromId = toId = undefined;
		shown = undefined;
	}

	function chooseDirection(next: string) {
		direction = Number(next);
		fromId = toId = undefined;
		shown = undefined;
	}

	const field =
		'border-ink bg-paper text-ink font-sans block min-h-12 w-full border px-4 py-2 text-body';
	const pickerKey = $derived(`${line}-${direction}`);
	const other = $derived(
		directions.length === 2 ? directions.find((d) => d !== direction) : undefined
	);
	const behind = $derived(
		fromStop
			? {
					stops: routeStops.slice(0, fromAt),
					note: (stop: CommuteStop) => `${stop[1]} comes before ${fromStop[1]} in this direction.`,
					action:
						other === undefined
							? undefined
							: {
									label: `Go the other way: ${directionLabel(listed, directions, other)}`,
									run: () => chooseDirection(String(other))
								}
				}
			: undefined
	);
	const hint = $derived(
		!line
			? 'Choose a bus line to start.'
			: direction === undefined
				? 'Choose a direction.'
				: fileState.kind === 'loading'
					? 'Loading the timetable for this route.'
					: fileState.kind === 'error'
						? 'The timetable did not load. Use Try again above.'
						: fileState.kind === 'none'
							? `No ${DAY_NAMES[dayType]} timetable for this direction. Try another day.`
							: !fromStop
								? 'Choose a From stop.'
								: !toStop
									? 'Choose a To stop.'
									: minute === null
										? 'Enter a time.'
										: ''
	);

	$effect(() => {
		if (scrolled || !fullLink || !result || !answerEl) return;
		scrolled = true;
		answerEl.scrollIntoView({ block: 'start' });
	});
</script>

<form class="mt-8" onsubmit={(event) => event.preventDefault()}>
	<LinePicker options={lineOptions} selected={line} onselect={chooseLine} />

	{#if directions.length > 0}
		<Segmented
			legend="Direction"
			stack
			value={direction === undefined ? '' : String(direction)}
			options={directions.map((id) => ({
				value: String(id),
				label: directionLabel(listed, directions, id)
			}))}
			onchange={chooseDirection}
		/>
	{/if}
	{#if directions.length > 0 && direction !== undefined}
		<Segmented
			legend="Day"
			value={dayType}
			options={DAY_OPTIONS}
			onchange={(value) => (dayType = value as DayType)}
		/>

		{#if fileState.kind === 'error'}
			<div class="mt-6">
				<ErrorState error={fileState.error} onretry={() => attempt++} />
			</div>
		{/if}
		{#if shown}
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
				<fieldset class="mt-6 min-w-0">
					<legend class="kicker text-ink-muted mb-2">To</legend>
					{#if fromStop}
						{#key fromId}
							<StopPicker
								stops={toChoices}
								{behind}
								bind:selected={() => toStop, (stop: CommuteStop | undefined) => (toId = stop?.[0])}
							/>
						{/key}
					{:else}
						<p class="text-ink-muted">Choose a From stop first. The To stop comes after it.</p>
					{/if}
				</fieldset>
			{/key}

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
					bind:value={time}
					aria-invalid={minute === null}
					class={field}
				/>
			</div>
		{:else if fileState.kind === 'loading'}
			<p class="text-ink-muted mt-6 min-h-40">Loading the stops.</p>
		{/if}
	{/if}
</form>

<section class="mt-10 scroll-mt-6" aria-labelledby="commute-answer" bind:this={answerEl}>
	<Headline level={2} size="md"><span id="commute-answer">Your bus</span></Headline>
	<p
		role="status"
		aria-live="polite"
		aria-atomic="true"
		data-testid="commute-answer"
		class="text-dek {text ? 'mt-4' : ''}"
	>
		{text}
	</p>
	{#if !result}
		<p class="text-ink-muted mt-4">{hint}</p>
	{/if}
	{#if spread && result?.kind === 'answer'}
		<SpreadChart {spread} deadline={result.arriveByMinute ?? undefined} />
	{/if}
</section>
