<script lang="ts">
	import { BUS_SERVICES, lineById, type BusService, type LineId } from './lines.ts';

	// Rail and busway lines pass `line`. Other bus routes pass `service` and the
	// route number.
	type Props = ({ line: LineId } | { service: BusService; route: string }) & {
		size?: 'sm' | 'md' | 'lg';
	};
	let { size = 'md', ...props }: Props = $props();

	const px = $derived({ sm: 20, md: 28, lg: 40 }[size]);

	// A rail bullet keeps Metro's true color in both themes. The letter inside
	// identifies the line, so the circle's own contrast with the page does not
	// carry the meaning. Bus styles use only the page's ink and paper.
	const look = $derived.by(() => {
		if ('line' in props) {
			const line = lineById(props.line);
			return {
				symbol: line.symbol,
				name: line.name,
				pill: false,
				css: `background:${line.color};color:${line.textColor}`
			};
		}
		const service = BUS_SERVICES[props.service];
		return {
			symbol: props.route,
			name: `${service.name} route ${props.route}`,
			pill: service.shape === 'pill' || props.route.length > 2,
			css: service.fill
				? 'background:var(--ink);color:var(--paper)'
				: `border:2px ${service.dashed ? 'dashed' : 'solid'} var(--ink)`
		};
	});
</script>

<span
	role="img"
	aria-label={look.name}
	class="data inline-flex shrink-0 items-center justify-center rounded-full font-bold {look.pill
		? 'px-2.5'
		: ''}"
	style="{look.css};min-width:{px}px;height:{px}px;font-size:{px * 0.5}px"
>
	{look.symbol}
</span>
