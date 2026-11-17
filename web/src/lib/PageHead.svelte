<script lang="ts">
	import { OG_IMAGE, SITE_NAME, absoluteUrl, fullTitle } from '#lib/head.ts';

	// Every page calls this once, so no page writes its own title or description.
	// `path` starts with a slash, has no base, and names the page's public address.
	let {
		title,
		description,
		path,
		noindex = false
	}: { title: string; description: string; path: string; noindex?: boolean } = $props();

	const heading = $derived(fullTitle(title, path));
	const url = $derived(absoluteUrl(path));
</script>

<svelte:head>
	<title>{heading}</title>
	<meta name="description" content={description} />
	<link rel="canonical" href={url} />
	<meta property="og:type" content="website" />
	<meta property="og:site_name" content={SITE_NAME} />
	<meta property="og:title" content={heading} />
	<meta property="og:description" content={description} />
	<meta property="og:url" content={url} />
	<meta property="og:image" content={OG_IMAGE} />
	<meta name="twitter:card" content="summary_large_image" />
	<meta name="twitter:title" content={heading} />
	<meta name="twitter:description" content={description} />
	<meta name="twitter:image" content={OG_IMAGE} />
	{#if noindex}
		<meta name="robots" content="noindex" />
	{/if}
</svelte:head>
