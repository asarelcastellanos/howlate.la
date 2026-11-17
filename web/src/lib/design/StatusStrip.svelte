<script lang="ts">
	import type { SiteStatus } from '#lib/data/types.ts';

	let { status }: { status: SiteStatus } = $props();

	// Parsed as UTC and formatted as UTC, so the service day never shifts with the
	// reader's time zone.
	const through = $derived(
		new Date(`${status.last_day}T00:00:00Z`).toLocaleDateString('en-US', {
			month: 'long',
			day: 'numeric',
			year: 'numeric',
			timeZone: 'UTC'
		})
	);
	const count = (n: number) => n.toLocaleString('en-US');
	const stats = $derived([
		{ value: count(status.days), label: 'days of data' },
		{ value: count(status.measured_arrivals), label: 'stops graded' },
		{ value: `${status.coverage_pct}%`, label: 'of scheduled stops measured' }
	]);
</script>

<section class="my-10" aria-label="Data status">
	<p class="kicker text-ink-muted">Data through {through}</p>
	<hr class="rule rule-thick mt-2" />
	<dl class="grid grid-cols-1 sm:grid-cols-3">
		{#each stats as stat (stat.label)}
			<!-- The label comes first in the markup and shows second. -->
			<div
				class="flex flex-col-reverse justify-end border-b py-4 sm:border-r sm:border-b-0 sm:px-6 sm:first:pl-0 sm:last:border-r-0"
			>
				<dt class="kicker text-ink-muted mt-2">{stat.label}</dt>
				<dd class="text-headline-xl font-serif leading-none font-bold tabular-nums">
					{stat.value}
				</dd>
			</div>
		{/each}
	</dl>
	<hr class="rule" />
</section>
