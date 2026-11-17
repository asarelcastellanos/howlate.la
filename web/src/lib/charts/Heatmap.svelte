<script lang="ts">
	import type { Hour } from '#lib/data/types.ts';
	import ChartFigure from './ChartFigure.svelte';
	import { DOTTED, DOTTED_WIDTH, HATCH, heatmap, heatmapLabel, hourlyGrid } from './heatmap.ts';
	import { DAY_NAMES, MIN_ARRIVALS, QUIET, RAMP, RAMP_STEPS, hourLabel, trusted } from './theme.ts';

	let { profile, caption, source }: { profile: Hour[]; caption: string; source: string } = $props();

	const grid = $derived(hourlyGrid(profile));
	const hours = Array.from({ length: 24 }, (_, hour) => hour);
</script>

<ChartFigure
	empty={trusted(profile).length === 0}
	render={(width) => heatmap(profile, { width })}
	label={heatmapLabel(profile)}
	{caption}
	{source}
>
	{#snippet extra()}
		<div
			class="caption text-ink-muted mt-2 flex flex-wrap items-center gap-x-4 gap-y-1"
			aria-hidden="true"
		>
			<span class="flex items-center gap-2">
				on time
				<span class="flex">
					{#each RAMP as color (color)}<span class="h-3 w-6" style:background={color}></span>{/each}
				</span>
				very late
			</span>
			<span class="flex items-center gap-2">
				<svg width="24" height="12" class="border">
					<defs>
						<pattern
							id="{HATCH.id}-key"
							width={HATCH.size}
							height={HATCH.size}
							patternUnits="userSpaceOnUse"
							patternTransform="rotate({HATCH.angle})"
						>
							<line
								x1={HATCH.size / 2}
								y1="0"
								x2={HATCH.size / 2}
								y2={HATCH.size}
								stroke={QUIET}
								stroke-width={HATCH.width}
							/>
						</pattern>
					</defs>
					<rect width="24" height="12" fill="url(#{HATCH.id}-key)" />
				</svg>
				too few arrivals
			</span>
			<span class="flex items-center gap-2">
				<svg width="24" height="12">
					<rect
						x="0.5"
						y="0.5"
						width="23"
						height="11"
						fill="none"
						stroke={QUIET}
						stroke-dasharray={DOTTED}
						stroke-width={DOTTED_WIDTH}
					/>
				</svg>
				none measured
			</span>
			<span
				>Ramp steps at {RAMP_STEPS.map((s) => s / 60).join(', ')} minutes. Too few is under {MIN_ARRIVALS}.</span
			>
		</div>
		<!-- sr-only goes on a wrapper, because a table grows past a 1 px width. -->
		<div class="sr-only">
			<table>
				<caption>
					Median delay in minutes for each hour of the week. No data means fewer than {MIN_ARRIVALS} measured
					arrivals.
				</caption>
				<thead>
					<tr>
						<th scope="col">Day</th>
						{#each hours as hour (hour)}<th scope="col">{hourLabel(hour)}</th>{/each}
					</tr>
				</thead>
				<tbody>
					{#each grid as row, day (day)}
						<tr>
							<th scope="row">{DAY_NAMES[day]}</th>
							{#each row as slot, hour (hour)}
								<td>
									{#if slot.state === 'ok'}
										{(slot.med / 60).toFixed(1)}
									{:else if slot.state === 'thin'}
										too few arrivals: {slot.n} of {MIN_ARRIVALS} needed
									{:else}
										no service or nothing measured
									{/if}
								</td>
							{/each}
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/snippet}
</ChartFigure>
