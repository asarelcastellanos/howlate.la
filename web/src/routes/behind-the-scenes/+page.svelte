<script lang="ts">
	import { readStatusReport } from '#lib/behind.ts';
	import Remote from '#lib/charts/Remote.svelte';
	import { DATA_BASE } from '#lib/data/base.ts';
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import Rule from '#lib/design/Rule.svelte';
	import PageHead from '#lib/PageHead.svelte';
	import Architecture from './Architecture.svelte';
	import StatusPanel from './StatusPanel.svelte';

	const repository = 'https://github.com/asarelcastellanos/howlate.la';
</script>

<PageHead
	title="Behind the scenes"
	description="How HowLate records LA Metro vehicles, grades them against the timetable and checks its own work each day, with what it cost to run."
	path="/behind-the-scenes"
/>

<Masthead dateline="Behind the scenes" />

<main id="main" class="page pb-16">
	<section class="pt-10 pb-6">
		<Kicker>Behind the scenes</Kicker>
		<Headline dek="What runs every day, what broke along the way, and what it costs.">
			How HowLate is built and checked
		</Headline>
	</section>

	<Rule weight="thick" />
	<section class="my-8">
		<Headline level={2} size="md">Is the data current?</Headline>
		<p class="mt-4">
			This panel reads the report the daily job saves for each graded day. It shows the newest day
			HowLate has graded, not a live feed.
		</p>
		<div class="mt-6">
			<Remote load={() => readStatusReport(DATA_BASE)}>
				{#snippet children(result)}<StatusPanel {result} />{/snippet}
			</Remote>
		</div>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">How it works</Headline>
		<p class="mt-4">
			Data moves one way, from Metro to your browser. The diagram shows each step, and the list
			under it says what the step does.
		</p>
		<Architecture />
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">Problems we solved</Headline>
		<p class="mt-4">
			<strong>A silent connection.</strong> On August 21, 2026, Metro kept a feed connection open for
			16 hours and sent nothing. Those hours cannot be recovered. The collector now replaces a connection
			that is open but silent, and an alarm fires when either feed stops delivering.
		</p>
		<p class="mt-4">
			<strong>Clocks and days.</strong> On the two days a year when the clocks change, every scheduled
			time was an hour off, so every delay was wrong by 3,600 seconds. No published number was affected.
			A later bug read "yesterday" from the server's UTC clock, so a run started between 16:00 and 24:00
			Pacific saw the next date. Every date now goes through one Pacific-time helper.
		</p>
		<p class="mt-4">
			<strong>The wrong timetable.</strong> The collector keeps a copy of Metro's timetable only when
			it changes. On September 10, 2026, the copy in force at midnight matched 1,002 of the 1,413 rail
			trips that vehicles reported, 70.9 percent. The copy fetched at 05:28 that morning matched all 1,413.
			Each day is now graded against the copy that matches the trips reported.
		</p>
		<p class="mt-4">
			<strong>Trips with no timetable.</strong> Rail vehicles reported trips that Metro lists under a
			service starting on a later date, 338 of them on November 14, 2026. The daily check failed. Those
			trips are now counted as explained and not graded. A check fails when more than 5 percent of a day's
			observations are explained, so a calendar bug cannot hide behind it. A second check fails when a
			line has at least 5 observed trips and every one is explained.
		</p>
		<p class="mt-4">
			<strong>Old files published again.</strong> The upload step published every JSON file in its output
			folder. On a reused disk, a line that Metro had dropped came back from an old file. The build now
			returns the names of the files it wrote, and only those upload.
		</p>
		<p class="mt-4">
			<strong>An alarm that could not fire.</strong> The first freshness check compared the newest graded
			day with the site the same job had just built, so the gap was always 0. A review caught it. The
			check now compares with today's date in Los Angeles, and the daily run fails when the newest day
			is more than 4 days old.
		</p>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">What it costs</Headline>
		<p class="mt-4">
			HowLate runs on one small virtual machine, Cloud Run jobs, Cloud Storage, Cloudflare Pages and
			R2. The owner's budget is about $5 a month. That is an estimate, not a bill.
		</p>
		<p class="mt-4">
			The archive grows by about 1 GB a day, so storage costs grow too. A breakdown will be
			published once billing is reviewed.
		</p>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">Where to look</Headline>
		<p class="mt-4">
			The code, the changelog and the release plan are in the
			<a href={repository} rel="noreferrer">HowLate repository</a> on GitHub.
		</p>
	</section>
</main>
