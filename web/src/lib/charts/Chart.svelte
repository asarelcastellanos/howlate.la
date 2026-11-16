<script lang="ts">
	// Draws a Plot chart at the width of its container and again whenever that
	// width changes. The label states the finding, because Plot's SVG is not
	// readable by a screen reader.
	let { render, label }: { render: (width: number) => Element; label: string } = $props();

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
		// eslint-disable-next-line svelte/no-dom-manipulating
		if (host && width > 0) host.replaceChildren(render(width));
	});
</script>

<div bind:this={host} role="img" aria-label={label} class="w-full overflow-x-clip"></div>
