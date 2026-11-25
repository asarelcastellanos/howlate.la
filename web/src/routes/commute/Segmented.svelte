<script lang="ts">
	let {
		legend,
		options,
		value,
		onchange,
		stack = false
	}: {
		legend: string;
		options: { value: string; label: string }[];
		value: string;
		onchange: (value: string) => void;
		stack?: boolean;
	} = $props();

	const name = $props.id();
</script>

<fieldset class="mt-6 min-w-0">
	<legend class="kicker text-ink-muted mb-2">{legend}</legend>
	<div class="flex {stack ? 'flex-col' : 'flex-row'}">
		{#each options as option (option.value)}
			<label class="min-w-0 flex-1">
				<input
					type="radio"
					{name}
					value={option.value}
					checked={value === option.value}
					onchange={() => onchange(option.value)}
					class="peer sr-only"
				/>
				<span
					class="border-ink data peer-checked:bg-ink peer-checked:text-paper peer-focus-visible:outline-focus block min-h-12 cursor-pointer border px-3 py-3 text-center font-semibold peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 {stack
						? '-mt-px first:mt-0'
						: '-ml-px first:ml-0'}"
				>
					{option.label}
				</span>
			</label>
		{/each}
	</div>
</fieldset>
