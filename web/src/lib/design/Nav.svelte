<script lang="ts">
	import { resolve } from '$app/paths';
	import { NAV, isCurrent, type NavItem } from '#lib/nav.ts';

	// The route id is a prop so a test can set it. Masthead reads it from the router.
	let { route, items = NAV }: { route: string | null; items?: readonly NavItem[] } = $props();

	// The list holds paths as strings, and a page that is not built yet is not a
	// route, so the typed resolve() would reject it. The casts only satisfy the types.
</script>

<!-- Each link is 44 px tall, the smallest touch target. The row wraps, and
     the current page is bold and underlined so color is not the only mark. -->
<nav aria-label="Main">
	<ul class="flex flex-wrap justify-center gap-x-6">
		{#each items.filter((item) => item.ready) as item (item.label)}
			<li>
				<a
					href="{resolve(item.path as '/')}{item.hash ?? ''}"
					aria-current={isCurrent(item, route) ? 'page' : undefined}
					class="kicker inline-flex min-h-11 items-center no-underline hover:underline aria-[current=page]:font-bold aria-[current=page]:underline aria-[current=page]:decoration-2"
				>
					{item.label}
				</a>
			</li>
		{/each}
	</ul>
</nav>
