<script lang="ts">
	let { weight = 'hairline' }: { weight?: 'hairline' | 'thick' | 'double' } = $props();
</script>

<hr class="rule" class:rule-thick={weight === 'thick'} class:rule-double={weight === 'double'} />
