<script lang="ts">
	import { lineById, type LineId } from './lines';

	// Inline form. The dot uses the theme-safe mark color and the words stay in
	// the page's ink, so the label passes text contrast on its own.
	let { line }: { line: LineId } = $props();
	const name = $derived(lineById(line).name);
</script>

<span class="data inline-flex items-center gap-1.5 whitespace-nowrap font-semibold">
	<span class="size-2.5 rounded-full" style="background:var(--line-{line})" aria-hidden="true"
	></span>
	{name}
</span>
