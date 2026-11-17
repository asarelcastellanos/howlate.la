<script lang="ts">
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import Rule from '#lib/design/Rule.svelte';

	const standards =
		'https://busstophub.metro.net/wp-content/uploads/2025/10/TSP-2025-Adopted-7-17-2025.pdf';
	const repository = 'https://github.com/asarelcastellanos/howlate.la';
</script>

<svelte:head>
	<title>Methods · HowLate</title>
	<meta
		name="description"
		content="How HowLate measures how late LA Metro buses and trains run, what counts as on time, and why some stops have no number."
	/>
</svelte:head>

<Masthead dateline="Methods" />

<main class="page pb-16">
	<section class="pt-10 pb-6">
		<Kicker>Methods</Kicker>
		<Headline dek="What we count, what we estimate, and why some stops have no number.">
			How HowLate measures delay
		</Headline>
	</section>

	<Rule weight="thick" />
	<section class="my-8">
		<Headline level={2} size="md">What HowLate measures</Headline>
		<p class="mt-4">
			Each Metro bus and train reports its position about every 6 seconds. HowLate records those
			reports and compares the time the timetable gives for each scheduled stop with the time the
			vehicle actually reached it. The difference is the delay. A late arrival is a positive number
			and an early one is negative.
		</p>
		<p class="mt-4">
			Most pages show the median delay, the middle value. Some charts also show the 90th percentile,
			the delay that nine in ten arrivals stayed under. "Stops graded" counts the scheduled stops
			that have a measured delay.
		</p>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">How an arrival is timed</Headline>
		<p class="mt-4">
			If a vehicle reported that it was stopped at the stop, HowLate uses the first time it said so.
			If it never did, HowLate uses the last time it said it was heading there, and marks the
			arrival as an estimate. Only about half of scheduled stops get a stopped report, because a bus
			with nobody waiting often rolls past without one.
		</p>
		<p class="mt-4">
			We checked the estimate on 42,313 stops where the vehicle did report stopping, so the true
			time was known. The estimate was off by a median of 7 seconds, and the 90th percentile of the
			error was 26 seconds. 90.5 percent were within half a minute. These stops did not need an
			estimate, so the figures may not hold for the rest.
		</p>
		<p class="mt-4">
			Trip starts are left out of every number. A vehicle waits at the first stop, so that time
			measures a departure and not an arrival.
		</p>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">What counts as on time</Headline>
		<p class="mt-4">
			Metro counts a bus or train as on time when it is no more than 1 minute early and no more than
			5 minutes late. The standard is in Metro's
			<a href={standards} rel="noreferrer">2025 Transit Service Policies and Standards</a>, adopted
			in July 2025, section 3.3. HowLate scores arrivals by the same window.
		</p>
		<p class="mt-4">
			Metro and HowLate do not score the same stops. Metro measures buses at timepoints, the stops
			where the schedule is checked, and trains at the end terminals. HowLate scores every stop. Our
			numbers are not Metro's published on-time performance, so do not compare them one to one.
		</p>
		<p class="mt-4">
			For reference, Metro's board report 2025-0860 gives 78.2 percent on time for buses and 99.4
			percent for rail, for July to September 2025. Rail is near 99 percent for Metro because Metro
			scores terminals only.
		</p>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">Why some stops have no number</Headline>
		<p class="mt-4">
			As of November 15, 2026, HowLate had measured 71.9 percent of scheduled stops over 90 days.
			The rest have no number, for four reasons.
		</p>
		<p class="mt-4">
			<strong>Nobody was waiting.</strong> A vehicle with no one waiting does not always report stopping.
			The estimate fills many of these gaps, but not all.
		</p>
		<p class="mt-4">
			<strong>The trip never showed up.</strong> Some scheduled trips never appear in the vehicle feed.
			On 18, 19 and 20 August, 235 to 268 trips a day, 1.6 to 1.8 percent, were never seen. Metro's feed
			never marks a trip as cancelled, so HowLate cannot say why. The same goes for lines 9 and 22, which
			the timetable scheduled on 24 days through November 10 and the feed never reported.
		</p>
		<p class="mt-4">
			<strong>The trip belongs to a later service.</strong> Rail vehicles sometimes report trips that
			Metro's timetable lists under a service starting on a later date. HowLate grades each day against
			the services running that day, so these trips have no scheduled stops. There were 214 on November
			7, 244 on November 13 and 338 on November 14. HowLate shows these as a count and does not grade
			them.
		</p>
		<p class="mt-4">
			<strong>We were not listening.</strong> On August 21, 2026, Metro kept a connection open for 16
			hours and sent nothing. The collector now replaces a silent connection. That day is still in the
			data, with fewer measured stops. Data missed while the collector or a feed is down cannot be recovered.
		</p>
		<p class="mt-4">
			A cell with fewer than 5 arrivals is shown hatched and is not used to rank anything. A dotted
			cell has nothing measured.
		</p>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">How we check ourselves</Headline>
		<p class="mt-4">
			After each day is graded, the daily job runs 15 checks against ranges measured across the
			whole network on August 18, 2026. A day outside a range means Metro's feed, the timetable or
			our code changed. Three examples follow.
		</p>
		<ul class="mt-4 list-disc space-y-3 pl-6">
			<li>
				<code>matched_rate</code> needs at least 99.9 percent of vehicle reports to match a scheduled
				stop.
			</li>
			<li>
				<code>explained_pct</code> caps the reports excused for a later service at 5 percent of the day.
			</li>
			<li>The silent lines check fails when a scheduled line has no report all day.</li>
		</ul>
		<p class="mt-4">
			A failed check does not delete the day. The numbers are still written, and that day's report
			records the failure.
		</p>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">What we do not know</Headline>
		<ul class="mt-4 list-disc space-y-3 pl-6">
			<li>HowLate does not know why a vehicle was late. It records where the vehicle was.</li>
			<li>
				Bus bunching is not separated from lateness. A bus that runs close behind another counts as
				late like any other.
			</li>
			<li>Estimated arrivals carry a bias of about 7 seconds, and we do not correct it.</li>
			<li>
				Metro changes its timetables, and a change to one agency's schedule can move a number.
			</li>
		</ul>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">Data and code</Headline>
		<p class="mt-4">
			The data comes from Metro's real-time vehicle positions and Metro's timetable files. The code
			is in the <a href={repository} rel="noreferrer">HowLate repository</a>
			on GitHub. A daily job runs at 5 am Pacific, and the newest day on the site trails the calendar
			by two days.
		</p>
	</section>
</main>
