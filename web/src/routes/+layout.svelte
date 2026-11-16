<script lang="ts">
	import './layout.css';
	import favicon from '#lib/assets/favicon.svg';
	import serif from '@fontsource-variable/source-serif-4/files/source-serif-4-latin-opsz-normal.woff2?url';
	import sans from '@fontsource-variable/inter/files/inter-latin-wght-normal.woff2?url';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
	<!-- The headline and the first line of text both need a font, so load both early. -->
	<link rel="preload" href={serif} as="font" type="font/woff2" crossorigin="anonymous" />
	<link rel="preload" href={sans} as="font" type="font/woff2" crossorigin="anonymous" />
	<!-- These match --paper in layout.css for each scheme. -->
	<meta name="theme-color" content="#fbf8f1" media="(prefers-color-scheme: light)" />
	<meta name="theme-color" content="#151412" media="(prefers-color-scheme: dark)" />
</svelte:head>

{@render children()}
