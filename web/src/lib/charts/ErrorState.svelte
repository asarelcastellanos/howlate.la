<script lang="ts">
	import Notice from './Notice.svelte';

	let { onretry }: { onretry?: () => void } = $props();
</script>

<Notice role="alert">
	<p>We couldn't load this data.</p>
	{#if onretry}
		<button
			type="button"
			onclick={onretry}
			class="border-ink hover:bg-ink hover:text-paper cursor-pointer border px-4 py-2 font-semibold"
		>
			Try again
		</button>
	{/if}
</Notice>
