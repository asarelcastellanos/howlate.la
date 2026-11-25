<script lang="ts">
	import Figure from '#lib/design/Figure.svelte';
	import { clock, type Spread } from '#lib/commute/answer.ts';

	let { spread }: { spread: Spread } = $props();

	const PAD = 16;
	const LABEL_ROWS = 44;
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
	const taller = $derived(Math.max(...dots.map((d) => d.level)) + 1);
	const low = $derived(
		Math.floor(Math.min(minute(spread.scheduled), minute(spread.nineInTen), ...minutes) - 1)
	);
	const high = $derived(
		Math.ceil(Math.max(minute(spread.scheduled), minute(spread.nineInTen), ...minutes) + 1)
	);
	const inner = $derived(Math.max(width - 2 * PAD, 1));
	const perMinute = $derived(inner / (high - low));
	const radius = $derived(Math.max(2, Math.min(4, perMinute / 2 - 0.5)));
	const plotHeight = $derived(taller * STEP + 8);
	const height = $derived(LABEL_ROWS + plotHeight + AXIS_ROOM);
	const axisY = $derived(LABEL_ROWS + plotHeight);
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
			`Scheduled for ${clock(Math.round(scheduledMinute))}. ` +
			`Nine days in ten it is there by ${clock(Math.ceil(nineMinute))}. ` +
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
			<svg {width} {height} role="img" aria-label={label} class="block overflow-visible">
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
					y1={20}
					y2={axisY}
					class="stroke-chart-ink"
					stroke-width="2"
				/>
				<line
					x1={x(nineMinute)}
					x2={x(nineMinute)}
					y1={38}
					y2={axisY}
					class="stroke-chart-annotation"
					stroke-width="2"
					stroke-dasharray="5 3"
				/>
				<text
					x={x(scheduledMinute) + nudge(scheduledMinute)}
					y={14}
					text-anchor={anchor(scheduledMinute)}
					class="fill-chart-ink"
					font-size="12"
					font-weight="600">Scheduled {clock(Math.round(scheduledMinute))}</text
				>
				<text
					x={x(nineMinute) + nudge(nineMinute)}
					y={LABEL_ROWS - 2}
					text-anchor={anchor(nineMinute)}
					class="fill-chart-annotation"
					font-size="12"
					font-weight="600">9 days in 10 by {clock(Math.ceil(nineMinute))}</text
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
