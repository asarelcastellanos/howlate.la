<script lang="ts">
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import Rule from '#lib/design/Rule.svelte';
	import { ESTIMATE_ANCHOR } from '#lib/estimated.ts';
	import PageHead from '#lib/PageHead.svelte';
	import MeasureOnTime from './MeasureOnTime.svelte';

	const repository = 'https://github.com/asarelcastellanos/howlate.la';
</script>

<PageHead
	title="Methods"
	description="How HowLate measures how late LA Metro buses and trains run, what counts as on time, and why some stops have no number."
	path="/methods"
/>

<Masthead dateline="Methods" />

<main id="main" class="page pb-16">
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
			Each Metro bus and train reports its position. A vehicle's distinct reports are a median 5 to
			6 seconds apart (5 for rail, 6 for bus, measured over 8 to 14 November 2026). HowLate records
			those reports and compares the time the timetable gives for each scheduled stop with the time
			the vehicle actually reached it. The difference is the delay. A late arrival is a positive
			number and an early one is negative.
		</p>
		<p class="mt-4">
			Most pages show the median delay, the middle value. Some charts also show the 90th percentile,
			the delay that nine in ten arrivals stayed under. "Stops graded" counts the scheduled stops
			that have a measured delay.
		</p>
	</section>

	<Rule />
	<section id={ESTIMATE_ANCHOR} class="my-8 scroll-mt-6">
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
			For some bus stops the feed has no report at all. HowLate places these between two reports of
			the same bus, by where the stop sits between the two positions. It does this only when the two
			reports are 5 minutes apart or less, and never for rail.
		</p>
		<p class="mt-4">
			We checked this by hiding 3.1 million bus stops from 10 to 16 November 2026 that did have a
			stopped report. Where the bus waited 10 seconds or less, the closest match to a stop it rolled
			past, the estimate was a median 2 seconds early and 9 in 10 were within 28 seconds. 3.0
			percent landed on the other side of the on-time window. A skipped stop has no real time to
			check against, so these figures may not hold for it.
		</p>
		<p class="mt-4">
			Trip starts are left out of every number. A vehicle waits at the first stop, so that time
			measures a departure and not an arrival.
		</p>
	</section>

	<Rule />
	<MeasureOnTime />

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">Why some stops have no number</Headline>
		<p class="mt-4">
			As of November 15, 2026, vehicles had reported 71.9 percent of scheduled stops over 90 days.
			Estimates fill some of the rest. The others have no number, for four reasons.
		</p>
		<p class="mt-4">
			<strong>Nobody was waiting.</strong> A vehicle with no one waiting does not always report stopping.
			The estimate fills many of these gaps, but not where the reports on either side are missing or more
			than 5 minutes apart.
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
			<li>
				Arrivals timed from an approach report carry a bias of about 7 seconds, and we do not
				correct it. We do not correct estimated bus stops either.
			</li>
			<li>
				Metro changes its timetables, and a change to one agency's schedule can move a number.
			</li>
			<li>
				HowLate does not know how Metro times a rail terminal arrival. Last-stop arrivals are
				estimates, and many read early.
			</li>
			<li>
				Lines B and D show large delays on some weekends. On 13 of the 26 weekend days from 18
				August to 15 November 2026, their timetable allowed no more running time than on a weekday
				while the median trip took about 6 minutes longer, and we do not know why.
			</li>
		</ul>
	</section>

	<Rule />
	<section class="my-8">
		<Headline level={2} size="md">Data and code</Headline>
		<p class="mt-4">
			The data comes from Metro's real-time vehicle positions and Metro's timetable files. The code
			is in the <a href={repository} rel="noreferrer">HowLate repository</a>
			on GitHub. A daily job runs at 8 am Pacific and grades the day before. Until it runs, the newest
			day on the site is two days old, and after it runs the newest day is yesterday.
		</p>
	</section>
</main>
