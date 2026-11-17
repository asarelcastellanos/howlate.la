<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import Nav from './Nav.svelte';

	// The dateline is a prop because the site is static. A date computed at
	// build time would go stale between deploys, so pages pass the date of
	// their data, or a place, instead.
	let { dateline }: { dateline: string } = $props();
</script>

<header class="page">
	<div class="wide pt-4">
		<!-- The first Tab stop on every page. It jumps to the <main id="main"> each page sets. -->
		<a
			href="#main"
			class="bg-paper text-ink border-ink kicker absolute top-2 left-4 z-10 -translate-y-24 border px-3 py-2 no-underline focus:translate-y-0"
		>
			Skip to content
		</a>
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
		<Nav route={page.route.id} />
		<hr class="rule" />
	</div>
</header>
