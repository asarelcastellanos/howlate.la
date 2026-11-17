<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import type { IndexEntry } from '#lib/data/types.ts';
	import { bulletProps, lineName, shortVia } from '#lib/linePage.ts';
	import { moveActive, searchLines } from '#lib/search.ts';
	import LineBullet from './LineBullet.svelte';

	// The ARIA combobox pattern with a listbox popup. Focus stays in the input
	// and aria-activedescendant names the highlighted option, so a screen reader
	// follows the arrow keys. The first result is highlighted as soon as there
	// is one, so typing "720" and pressing Enter opens the 720.
	let { entries }: { entries: IndexEntry[] } = $props();

	const uid = $props.id();
	let query = $state('');
	let open = $state(false);
	let active = $state(0);
	let root = $state<HTMLDivElement>();

	const results = $derived(searchLines(entries, query));
	const showList = $derived(open && results.length > 0);
	const none = $derived(query.trim() !== '' && results.length === 0);
	const optionId = (i: number) => `${uid}-option-${i}`;

	function go(entry: IndexEntry) {
		open = false;
		void goto(resolve('/lines/[line]', { line: entry.line }));
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			if (!open) open = true;
			else active = moveActive(active, event.key, results.length);
		} else if (event.key === 'Enter' && showList) {
			event.preventDefault();
			go(results[active]);
		} else if (event.key === 'Escape') {
			// The first press closes the list. A second press clears the text.
			if (open) open = false;
			else query = '';
		}
	}

	$effect(() => {
		if (showList) document.getElementById(optionId(active))?.scrollIntoView({ block: 'nearest' });
	});
</script>

<div
	bind:this={root}
	role="search"
	onfocusout={(event) => {
		if (!root?.contains(event.relatedTarget as Node | null)) open = false;
	}}
>
	<label for="{uid}-input" class="kicker text-ink-muted block">Find a line</label>
	<input
		id="{uid}-input"
		type="text"
		role="combobox"
		aria-expanded={showList}
		aria-controls="{uid}-list"
		aria-autocomplete="list"
		aria-activedescendant={showList ? optionId(active) : undefined}
		autocomplete="off"
		autocapitalize="off"
		spellcheck="false"
		enterkeyhint="go"
		placeholder="720, E Line, Wilshire"
		bind:value={query}
		oninput={() => {
			open = true;
			active = 0;
		}}
		onfocus={() => (open = true)}
		{onkeydown}
		class="border-ink bg-paper text-ink font-sans mt-2 block min-h-12 w-full border px-4 py-2 text-body"
	/>
	<ul
		id="{uid}-list"
		role="listbox"
		aria-label="Matching lines"
		hidden={!showList}
		class="border-ink bg-paper font-sans border border-t-0"
	>
		{#each results as entry, i (entry.line)}
			<!-- The input handles every key, as the pattern requires. The option only needs a pointer. -->
			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<li
				id={optionId(i)}
				role="option"
				aria-selected={i === active}
				onmousedown={(event) => event.preventDefault()}
				onclick={() => go(entry)}
				class="flex min-h-14 cursor-pointer items-center gap-3 border-b border-l-4 px-3 py-2 last:border-b-0 {i ===
				active
					? 'bg-sunk border-l-ink'
					: 'border-l-transparent'}"
			>
				<span aria-hidden="true"><LineBullet {...bulletProps(entry)} /></span>
				<span class="min-w-0">
					<span class="data block font-semibold">{lineName(entry)}</span>
					{#if entry.via}
						<span class="caption text-ink-muted block truncate">{shortVia(entry.via)}</span>
					{/if}
				</span>
			</li>
		{/each}
	</ul>
	<p role="status" class={none ? 'data mt-3' : 'sr-only'}>
		{#if none}
			No line matches that. Try a route number like 720 or a name like E Line.
		{:else if showList}
			{results.length} lines match. Use the up and down arrow keys, then Enter.
		{/if}
	</p>
</div>
