<script lang="ts">
	import ResultView from '../../src/lib/charts/ResultView.svelte';
	import Throws from './Throws.svelte';
</script>

<ResultView result={{ ok: true, data: 1 }}>
	<Throws />
</ResultView>
