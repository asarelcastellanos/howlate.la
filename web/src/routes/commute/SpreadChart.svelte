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
	const markList = $derived(
		[
			{
				key: 'scheduled',
				m: minute(spread.scheduled),
				text: `Scheduled ${clock(Math.floor(minute(spread.scheduled)))}`,
				line: 'stroke-chart-ink',
				fill: 'fill-chart-ink',
				dash: undefined
			},
			{
				key: 'nine',
				m: minute(spread.nineInTen),
				text: `9 days in 10 by ${clock(Math.ceil(minute(spread.nineInTen)))}`,
				line: 'stroke-chart-annotation',
				fill: 'fill-chart-annotation',
				dash: '5 3'
			},
			...(deadline === undefined
				? []
				: [
						{
							key: 'deadline',
							m: deadline,
							text: `Your deadline ${clock(deadline)}`,
							line: 'stroke-chart-axis',
							fill: 'fill-chart-axis',
							dash: '1 4'
						}
					])
		].sort((a, b) => a.m - b.m)
	);
	const taller = $derived(Math.max(...dots.map((d) => d.level)) + 1);
	const low = $derived(Math.floor(Math.min(...marks, ...minutes) - 1));
	const high = $derived(Math.ceil(Math.max(...marks, ...minutes) + 1));
	const CHAR = 7;
	const reserve = $derived(
		Math.min(Math.max(...markList.map((k) => k.text.length)) * CHAR + 12, width * 0.5)
	);
	const inner = $derived(Math.max(width - 2 * PAD - reserve, 1));
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

	const nineMinute = $derived(minute(spread.nineInTen));
	const scheduledMinute = $derived(minute(spread.scheduled));
	const earliest = $derived(Math.min(...spread.arrivals));
	const latest = $derived(Math.max(...spread.arrivals));
	const label = $derived(
		`Arrival at the To stop on ${spread.arrivals.length} days, one dot each. ` +
			`Scheduled for ${clock(Math.floor(scheduledMinute))}. ` +
			`Nine days in ten it is there by ${clock(Math.ceil(nineMinute))}. ` +
			(deadline === undefined ? '' : `Your deadline is ${clock(deadline)}. `) +
			`The earliest was ${clock(Math.round(minute(earliest)))} and the latest ${clock(Math.round(minute(latest)))}.`
	);
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
				{#each markList as mark, i (mark.key)}
					<line
						x1={x(mark.m)}
						x2={x(mark.m)}
						y1={(i + 1) * ROW - 1}
						y2={axisY}
						class={mark.line}
						stroke-width="2"
						stroke-dasharray={mark.dash}
						stroke-linecap={mark.key === 'deadline' ? 'round' : 'butt'}
					/>
					<text
						x={x(mark.m) + 6}
						y={(i + 1) * ROW - 3}
						class="{mark.fill} stroke-paper"
						font-size="12"
						font-weight="600"
						stroke-width="3"
						style="paint-order: stroke">{mark.text}</text
					>
				{/each}
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
