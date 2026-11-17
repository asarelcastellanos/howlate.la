<script lang="ts">
	import {
		buildStrip,
		checkRow,
		failedLabel,
		freshness,
		newestDay,
		STALE_AFTER_DAYS
	} from '#lib/behind.ts';
	import Notice from '#lib/charts/Notice.svelte';
	import type { Result } from '#lib/data/load.ts';
	import type { HealthFile } from '#lib/data/types.ts';
	import { longDate, pacificToday } from '#lib/date.ts';
	import HealthStrip from './HealthStrip.svelte';

	// `today` is a prop so a test can set it. The page gets it from the browser's
	// clock, read in Los Angeles. It never runs on the server, because the data
	// loads in the browser.
	let { result, today = pacificToday(new Date()) }: { result: Result<HealthFile>; today?: string } =
		$props();

	// A missing file or an old shape is expected between a release and the next
	// daily run, so it gets a plain message and not the site's error box. Only a
	// failed request says so, because then the file may exist.
	const missing = $derived(
		!result.ok && (result.error.kind === 'status' || result.error.kind === 'shape')
	);
</script>

{#if !result.ok}
	<Notice role="status">
		{#if missing}
			<p>Status data is not published yet. It appears after the next daily run.</p>
		{:else}
			<p>Status data could not be loaded right now. Reload the page to try again.</p>
		{/if}
	</Notice>
{:else}
	{@const health = result.data}
	{@const report = newestDay(health)}
	{@const age = freshness(health.last_day, today)}
	{@const failed = report?.failed ?? []}
	<div class={age.stale ? 'border-destructive border-2 p-4' : ''}>
		{#if age.stale}
			<p data-warning class="text-destructive font-sans text-data font-semibold">
				<svg viewBox="0 0 24 24" class="mr-1 inline h-4 w-4 align-text-bottom" aria-hidden="true">
					<path d="M12 2.5L22.5 21h-21z" class="fill-destructive" />
					<path
						d="M12 9v6M12 17.5v1"
						class="stroke-paper"
						stroke-width="2.4"
						stroke-linecap="round"
					/>
				</svg>
				Warning. The newest graded day is {age.daysOld} days before today in Los Angeles.
			</p>
			<p class="caption text-ink-muted mt-1">
				The daily job grades up to {STALE_AFTER_DAYS} days back, so a gap of {STALE_AFTER_DAYS} days is
				normal. A longer gap means the job has not finished lately.
			</p>
		{/if}

		<p class="kicker text-ink-muted mt-3">Newest graded day</p>
		<p class="headline mt-1">{longDate(health.last_day)}</p>
		<p class="caption text-ink-muted mt-1">
			Checked {longDate(today)} against today's date in Los Angeles. Built by pipeline {health.pipeline_version}.
		</p>

		{#if report}
			<p class="data mt-4 font-semibold">
				{failed.length === 0
					? 'All checks passed.'
					: `${failed.length} ${failed.length === 1 ? 'check' : 'checks'} failed.`}
			</p>
			{#if failed.length > 0}
				<ul class="data mt-1 list-disc pl-6">
					{#each failed as name (name)}<li>{failedLabel(health, name)}</li>{/each}
				</ul>
			{/if}
			<p class="mt-2">
				<span class="font-bold tabular-nums">{report.coverage_pct}%</span> of scheduled stops measured
				on that day.
			</p>
		{:else}
			<p class="mt-4">No report is saved for this day.</p>
		{/if}

		<div class="mt-6">
			<h3 class="kicker text-ink-muted mb-2">The last 14 days</h3>
			<HealthStrip cells={buildStrip(health.recent, health.last_day)} />
		</div>

		{#if health.checks.length > 0}
			<div class="mt-6">
				<h3 class="kicker text-ink-muted mb-2">What was checked on the newest day</h3>
				<ul class="data border-t">
					{#each health.checks as check (check.name)}
						{@const row = checkRow(check)}
						<li
							data-check={check.name}
							class="flex flex-col gap-1 border-b py-2 sm:flex-row sm:justify-between sm:gap-4"
						>
							<span>{row.label}</span>
							<span class="sm:text-right">
								<span class="tabular-nums">{row.measured}, {row.rule}.</span>
								<strong class={row.ok ? '' : 'text-destructive'}
									>{row.ok ? 'Passed' : 'Failed'}</strong
								>
							</span>
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	</div>
{/if}
