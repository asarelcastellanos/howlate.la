<script lang="ts">
	import { tick } from 'svelte';
	import LineBullet from '#lib/design/LineBullet.svelte';
	import { bulletProps, lineName, shortVia } from '#lib/linePage.ts';
	import { moveActive, searchLines, type Searchable } from '#lib/search.ts';

	type Option = Searchable;

	let {
		options,
		selected,
		onselect
	}: { options: Option[]; selected: string; onselect: (line: string) => void } = $props();

	const uid = $props.id();
	let query = $state('');
	let open = $state(false);
	let active = $state(0);
	let root = $state<HTMLDivElement>();
	let input = $state<HTMLInputElement>();
	let change = $state<HTMLButtonElement>();

	const chosen = $derived(options.find((o) => o.line === selected));
	const results = $derived(searchLines(options, query));
	const showList = $derived(open && results.length > 0);
	const none = $derived(query.trim() !== '' && results.length === 0);
	const optionId = (i: number) => `${uid}-option-${i}`;

	async function pick(option: Option) {
		const refocus = document.activeElement === input;
		query = '';
		open = false;
		onselect(option.line);
		if (refocus) {
			await tick();
			change?.focus();
		}
	}

	async function clear() {
		onselect('');
		await tick();
		input?.focus();
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
			event.preventDefault();
			if (!open) open = true;
			else active = moveActive(active, event.key, results.length);
		} else if (event.key === 'Enter' && showList) {
			event.preventDefault();
			void pick(results[active]);
		} else if (event.key === 'Escape') {
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
	{#if chosen}
		<p class="kicker text-ink-muted mb-2">Bus line</p>
		<div class="border-ink bg-sunk font-sans flex items-center gap-3 border py-1 pr-1 pl-3">
			<span aria-hidden="true"><LineBullet {...bulletProps(chosen)} /></span>
			<span class="data min-w-0 flex-1 font-semibold">{lineName(chosen)}</span>
			<button
				type="button"
				bind:this={change}
				aria-label="Change line"
				onclick={clear}
				class="border-ink bg-paper text-ink hover:bg-sunk data min-h-12 shrink-0 border px-3 py-2"
			>
				Change
			</button>
		</div>
	{:else}
		<label for="{uid}-input" class="kicker text-ink-muted mb-2 block">Bus line</label>
		<input
			bind:this={input}
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
			placeholder="720, 4, Wilshire"
			bind:value={query}
			oninput={() => {
				open = true;
				active = 0;
			}}
			onfocus={() => (open = true)}
			{onkeydown}
			class="border-ink bg-paper text-ink font-sans block min-h-12 w-full border px-4 py-2 text-body"
		/>
		<ul
			id="{uid}-list"
			role="listbox"
			aria-label="Matching lines"
			hidden={!showList}
			class="border-ink bg-paper font-sans max-h-64 overflow-y-auto border border-t-0"
		>
			{#each results as option, i (option.line)}
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<li
					id={optionId(i)}
					role="option"
					aria-selected={i === active}
					onmousedown={(event) => event.preventDefault()}
					onclick={() => pick(option)}
					class="flex min-h-14 cursor-pointer items-center gap-3 border-b border-l-4 px-3 py-2 last:border-b-0 {i ===
					active
						? 'bg-sunk border-l-ink'
						: 'border-l-transparent'}"
				>
					<span aria-hidden="true"><LineBullet {...bulletProps(option)} /></span>
					<span class="min-w-0">
						<span class="data block font-semibold">{lineName(option)}</span>
						{#if option.via}
							<span class="caption text-ink-muted block truncate">{shortVia(option.via)}</span>
						{/if}
					</span>
				</li>
			{/each}
		</ul>
	{/if}
	<p class={none ? 'data mt-3' : 'sr-only'} role="status">
		{#if none}
			No bus line matches that. Try a route number like 720.
		{:else if showList}
			{results.length} lines match. Use the up and down arrow keys, then Enter.
		{/if}
	</p>
</div>
