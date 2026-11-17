<script lang="ts">
	import { resolve } from '$app/paths';

	// The dateline is a prop because the site is static. A date computed at
	// build time would go stale between deploys, so pages pass the date of
	// their data, or a place, instead.
	let { dateline }: { dateline: string } = $props();
</script>

<header class="page">
	<div class="wide pt-4">
		<p class="kicker text-ink-muted flex justify-between gap-4">
			<span>Los Angeles</span>
			<span>{dateline}</span>
		</p>
		<p
			class="my-3 text-center font-serif text-[clamp(2.75rem,2rem+4vw,4.5rem)] leading-none font-bold tracking-tight"
		>
			<a href={resolve('/')} class="no-underline">HowLate</a>
		</p>
		<hr class="rule rule-double" />
	</div>
</header>
