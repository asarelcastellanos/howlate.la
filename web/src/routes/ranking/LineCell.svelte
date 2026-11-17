<script lang="ts">
	import type { IndexEntry } from '#lib/data/types.ts';
	import LineBullet from '#lib/design/LineBullet.svelte';
	import { bulletProps, lineName, shortVia } from '#lib/linePage.ts';

	// `compact` hides the corridor on a phone, so a table row stays one line and
	// the next column shows without scrolling far. Bus bullets share one width,
	// because a pill is wider than a circle and the names should line up.
	let { entry, compact = false }: { entry: IndexEntry; compact?: boolean } = $props();
	const via = $derived(shortVia(entry.via, 60));
</script>

<!-- The line page is built on another branch, so this is a plain link. -->
<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
<a href="/lines/{encodeURIComponent(entry.line)}" class="flex items-center gap-3 no-underline">
	<span aria-hidden="true" class="flex shrink-0 {entry.mode === 'bus' ? 'w-[3.75rem]' : 'w-8'}"
		><LineBullet {...bulletProps(entry)} size="sm" /></span
	>
	<span class="min-w-0">
		<span class="block font-semibold underline">{lineName(entry)}</span>
		{#if via}<span
				class="text-ink-muted caption font-normal {compact ? 'hidden sm:block' : 'block'}"
				>{via}</span
			>{/if}
	</span>
</a>
