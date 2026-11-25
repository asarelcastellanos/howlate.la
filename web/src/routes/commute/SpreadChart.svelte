<script lang="ts">
	import Figure from '#lib/design/Figure.svelte';
	import { clock, type Spread } from '#lib/commute/answer.ts';

	let { spread, deadline }: { spread: Spread; deadline?: number } = $props();

	const PAD = 16;
	const ROW = 16;
	const STEP = 9;
	const AXIS_ROOM = 28;

	let width = $state(0);

	const minute = (seconds: number) => seconds / 60;
	const dots = $derived.by(() => {
		const seen: Record<number, number> = {};
		return spread.arrivals
			.map((seconds) => Math.round(minute(seconds)))
			.sort((p, q) => p - q)
			.map((m) => {
				seen[m] = (seen[m] ?? -1) + 1;
				return { m, level: seen[m] };
			});
	});
	const minutes = $derived(dots.map((d) => d.m));
	const labelRows = $derived((deadline === undefined ? 2 : 3) * ROW + 12);
	const marks = $derived([
		minute(spread.scheduled),
		minute(spread.nineInTen),
		...(deadline === undefined ? [] : [deadline])
	]);
	const taller = $derived(Math.max(...dots.map((d) => d.level)) + 1);
	const low = $derived(Math.floor(Math.min(...marks, ...minutes) - 1));
	const high = $derived(Math.ceil(Math.max(...marks, ...minutes) + 1));
	const inner = $derived(Math.max(width - 2 * PAD, 1));
	const perMinute = $derived(inner / (high - low));
	const radius = $derived(Math.max(2, Math.min(4, perMinute / 2 - 0.5)));
	const plotHeight = $derived(taller * STEP + 8);
	const height = $derived(labelRows + plotHeight + AXIS_ROOM);
	const axisY = $derived(labelRows + plotHeight);
	const x = (m: number) => PAD + (m - low) * perMinute;

	const tickStep = $derived(
		[1, 2, 5, 10, 15, 30].find((s) => (high - low) / s <= Math.max(2, Math.floor(inner / 70))) ?? 60
	);
	const ticks = $derived.by(() => {
		const out: number[] = [];
		for (let m = Math.ceil(low / tickStep) * tickStep; m <= high; m += tickStep) out.push(m);
		return out;
	});

	const scheduledMinute = $derived(minute(spread.scheduled));
	const nineMinute = $derived(minute(spread.nineInTen));
	const earliest = $derived(Math.min(...spread.arrivals));
	const latest = $derived(Math.max(...spread.arrivals));
	const label = $derived(
		`Arrival at the To stop on ${spread.arrivals.length} days, one dot each. ` +
			`Scheduled for ${clock(Math.floor(scheduledMinute))}. ` +
			`Nine days in ten it is there by ${clock(Math.ceil(nineMinute))}. ` +
			(deadline === undefined ? '' : `Your deadline is ${clock(deadline)}. `) +
			`The earliest was ${clock(Math.round(minute(earliest)))} and the latest ${clock(Math.round(minute(latest)))}.`
	);
	const anchor = (m: number) => (x(m) > width * 0.55 ? 'end' : 'start');
	const nudge = (m: number) => (anchor(m) === 'end' ? -6 : 6);
	const stackOf = (level: number) => axisY - 6 - level * STEP;
</script>

{#snippet caption()}When the bus reached the To stop, on each of {spread.arrivals.length} days.{/snippet}
{#snippet source()}Each dot is one day. Dots in the same minute stack. Times are rounded to the
	minute.{/snippet}

<Figure {caption} {source} width="text">
	<div bind:clientWidth={width} data-testid="spread-chart">
		{#if width > 0}
			<svg {width} {height} role="img" aria-label={label} class="data block overflow-visible">
				<line
					x1={PAD}
					x2={PAD + inner}
					y1={axisY}
					y2={axisY}
					class="stroke-chart-ink"
					stroke-width="1"
				/>
				{#each ticks as tick (tick)}
					<line
						x1={x(tick)}
						x2={x(tick)}
						y1={axisY}
						y2={axisY + 5}
						class="stroke-chart-ink"
						stroke-width="1"
					/>
					<text
						x={x(tick)}
						y={axisY + 20}
						text-anchor="middle"
						class="fill-chart-axis"
						font-size="12">{clock(tick)}</text
					>
				{/each}
				<line
					x1={x(scheduledMinute)}
					x2={x(scheduledMinute)}
					y1={ROW - 1}
					y2={axisY}
					class="stroke-chart-ink"
					stroke-width="2"
				/>
				<line
					x1={x(nineMinute)}
					x2={x(nineMinute)}
					y1={2 * ROW - 1}
					y2={axisY}
					class="stroke-chart-annotation"
					stroke-width="2"
					stroke-dasharray="5 3"
				/>
				{#if deadline !== undefined}
					<line
						x1={x(deadline)}
						x2={x(deadline)}
						y1={3 * ROW - 1}
						y2={axisY}
						class="stroke-chart-axis"
						stroke-width="2"
						stroke-dasharray="1 4"
						stroke-linecap="round"
					/>
					<text
						x={x(deadline) + nudge(deadline)}
						y={3 * ROW - 3}
						text-anchor={anchor(deadline)}
						class="fill-chart-axis stroke-paper"
						font-size="12"
						font-weight="600"
						stroke-width="3"
						style="paint-order: stroke">Your deadline {clock(deadline)}</text
					>
				{/if}
				<text
					x={x(scheduledMinute) + nudge(scheduledMinute)}
					y={ROW - 3}
					text-anchor={anchor(scheduledMinute)}
					class="fill-chart-ink stroke-paper"
					font-size="12"
					font-weight="600"
					stroke-width="3"
					style="paint-order: stroke">Scheduled {clock(Math.floor(scheduledMinute))}</text
				>
				<text
					x={x(nineMinute) + nudge(nineMinute)}
					y={2 * ROW - 3}
					text-anchor={anchor(nineMinute)}
					class="fill-chart-annotation stroke-paper"
					font-size="12"
					font-weight="600"
					stroke-width="3"
					style="paint-order: stroke">9 days in 10 by {clock(Math.ceil(nineMinute))}</text
				>
				{#each dots as dot, i (i)}
					<circle
						cx={x(dot.m)}
						cy={stackOf(dot.level)}
						r={radius}
						class="fill-chart-ink stroke-paper"
						stroke-width="1"
					/>
				{/each}
			</svg>
		{/if}
	</div>
</Figure>
