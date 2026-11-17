<script lang="ts">
	// Draws a Plot chart at the width of its container and again whenever that
	// width changes. The label states the finding, because Plot's SVG is not
	// readable by a screen reader. A chart with `onrender` takes input, so it
	// cannot sit inside an image role. It gets each fresh SVG to wire up and
	// labels it there, and the page's other charts keep the image role.
	let {
		render,
		label,
		onrender
	}: {
		render: (width: number) => Element;
		label: string;
		onrender?: (svg: Element) => void | (() => void);
	} = $props();

	let host = $state<HTMLDivElement>();
	let width = $state(0);

	$effect(() => {
		if (!host) return;
		const watch = new ResizeObserver(([entry]) => {
			width = Math.floor(entry.contentRect.width);
		});
		watch.observe(host);
		return () => watch.disconnect();
	});

	$effect(() => {
		// Plot returns a finished SVG element, so there is nothing for Svelte to render.
		if (!host || width <= 0) return;
		const svg = render(width);
		// A redraw drops the old SVG, so a keyboard user would lose their place.
		const hadFocus = host.contains(document.activeElement);
		// eslint-disable-next-line svelte/no-dom-manipulating
		host.replaceChildren(svg);
		const cleanup = onrender?.(svg);
		if (hadFocus) (svg as SVGElement).focus({ preventScroll: true });
		return cleanup;
	});
</script>

<div
	bind:this={host}
	role={onrender ? undefined : 'img'}
	aria-label={onrender ? undefined : label}
	class="w-full overflow-x-clip"
></div>
