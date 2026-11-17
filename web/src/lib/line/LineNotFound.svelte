<script lang="ts">
	import { resolve } from '$app/paths';
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import PageHead from '#lib/PageHead.svelte';

	let { id }: { id: string } = $props();
</script>

<PageHead
	title="Line not found"
	description="HowLate has no line with this name. Search for a line by its number or its name to find the page you wanted."
	path="/lines/{encodeURIComponent(id)}"
	noindex
/>

<!-- The site is static, so the server answers 200 for any /lines/ path and this
     message cannot change that. The robots tag keeps the page out of search
     results for crawlers that run the script. -->
<section class="pt-10 pb-6">
	<Kicker>Not found</Kicker>
	<Headline>We could not find that line</Headline>
	<p class="mt-6 break-words">Nothing in the data is called "{id}".</p>
	<p class="mt-4"><a href="{resolve('/')}#search">Search for a line</a></p>
</section>
