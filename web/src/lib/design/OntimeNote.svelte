<script lang="ts">
	import { MEASURE_HREF } from '#lib/ontimeNote.ts';

	// The footnote for every on-time share. The asterisk is decoration and is hidden
	// from a screen reader, so the words and the link carry the meaning. A phone gets
	// the short form, which keeps the Metro caveat, and the methods section has the rest.
	let { class: className = '' }: { class?: string } = $props();
</script>

<p class="caption text-ink-muted {className}">
	<span aria-hidden="true">*</span>
	<span class="sm:hidden"
		>On time means 1 minute early to 5 minutes late. Metro reports on-time performance differently.</span
	>
	<span class="hidden sm:inline"
		>On time means arriving 1 minute early to 5 minutes late against the timetable. We score every
		measured stop after the first. Metro reports on-time performance differently.</span
	>
	<!-- A plain link, not `resolve`, because the charts import this and the chart tests run outside SvelteKit. The site is served from the domain root. -->
	<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
	<a href={MEASURE_HREF}>How we measure</a>
</p>
