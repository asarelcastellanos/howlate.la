<script lang="ts">
	import type { Hour } from '#lib/data/types.ts';
	import ChartFigure from './ChartFigure.svelte';
	import {
		DOTTED,
		DOTTED_WIDTH,
		HATCH,
		heatmap,
		heatmapLabel,
		hourlyGrid,
		selectHour
	} from './heatmap.ts';
	import { nextHour, readoutText, startHour } from './readout.ts';
	import { DAY_NAMES, MIN_ARRIVALS, QUIET, RAMP, RAMP_STEPS, hourLabel, trusted } from './theme.ts';

	// `showOntime` is false for a rail line when SHOW_RAIL_ONTIME is off.
	let {
		profile,
		caption,
		source,
		showOntime
	}: { profile: Hour[]; caption: string; source: string; showOntime: boolean } = $props();

	const uid = $props.id();
	const grid = $derived(hourlyGrid(profile));
	const hours = Array.from({ length: 24 }, (_, hour) => hour);
	const label = $derived(heatmapLabel(profile));

	// The pick remembers its profile, so switching direction starts on that
	// direction's worst hour. A resize redraws the SVG and keeps the pick.
	let picked = $state.raw<{ profile: Hour[]; h: number }>();
	const selected = $derived(picked?.profile === profile ? picked.h : startHour(profile));
	const readout = $derived(
		readoutText(profile.find((hour) => hour.h === selected) ?? { h: selected }, { showOntime })
	);
	let svg = $state.raw<Element>();
	$effect(() => {
		if (svg) selectHour(svg, selected);
	});

	const choose = (h: number) => (picked = { profile, h });
	const hourOf = (target: EventTarget | null) => {
		const value = (target as Element | null)?.closest('[data-hour]')?.getAttribute('data-hour');
		return value === null || value === undefined ? undefined : Number(value);
	};

	// Plot hands back a finished SVG, so the events attach to it after each draw.
	function wire(svgEl: Element) {
		const el = svgEl as SVGElement;
		const onclick = (event: Event) => {
			const h = hourOf(event.target);
			if (h !== undefined) choose(h);
		};
		const onover = (event: PointerEvent) => {
			const h = event.pointerType === 'mouse' ? hourOf(event.target) : undefined;
			if (h !== undefined && h !== selected) choose(h);
		};
		const onkey = (event: KeyboardEvent) => {
			if (event.altKey || event.ctrlKey || event.metaKey) return;
			const next = nextHour(selected, event.key);
			if (next === undefined) return;
			// The arrow keys and Home and End scroll the page unless they are stopped here.
			event.preventDefault();
			choose(next);
		};
		el.setAttribute('tabindex', '0');
		el.setAttribute('role', 'img');
		el.setAttribute('aria-label', `${label} Use the arrow keys to choose an hour.`);
		el.setAttribute('aria-describedby', `${uid}-readout`);
		el.addEventListener('click', onclick);
		el.addEventListener('pointerover', onover);
		el.addEventListener('keydown', onkey);
		svg = el;
		return () => {
			if (svg === el) svg = undefined;
		};
	}
</script>

<ChartFigure
	empty={trusted(profile).length === 0}
	render={(width) => heatmap(profile, { width })}
	{label}
	onrender={wire}
	{caption}
	{source}
>
	{#snippet extra()}
		<p id="{uid}-readout" aria-live="polite" class="data mt-3 min-h-[2lh]">{readout}</p>
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
			<span>Tap a cell or use the arrow keys to read an hour.</span>
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
