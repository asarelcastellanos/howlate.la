<script lang="ts">
	import { SHOW_RAIL_ONTIME } from '#lib/config.ts';
	import Headline from '#lib/design/Headline.svelte';
	import { MEASURE_ANCHOR } from '#lib/ontimeNote.ts';
	import { showsOntime } from '#lib/linePage.ts';
	import NetworkShares from './NetworkShares.svelte';

	// The copy is written for the open gate. With the gate closed, the sentences that
	// state a rail share are left out, and the rest still reads true. `railGate` is a prop
	// so a test can close it.
	let { railGate = SHOW_RAIL_ONTIME }: { railGate?: boolean } = $props();
	const railShare = $derived(showsOntime('rail', railGate));

	const standards =
		'https://busstophub.metro.net/wp-content/uploads/2025/10/TSP-2025-Adopted-7-17-2025.pdf';
	const boardReport =
		'https://metro.legistar.com/ViewReport.ashx?M=R&N=TextL5&GID=557&ID=11879&GUID=LATEST&G=A5FAA737-A54D-4A6C-B1E8-FF70F765FA94&Title=Board+Report';
	const issue133 = 'https://github.com/asarelcastellanos/howlate.la/issues/133';
</script>

<section id={MEASURE_ANCHOR} class="my-8 scroll-mt-6">
	<Headline level={2} size="md">How we measure on-time</Headline>
	<p class="mt-4">
		<strong>What we measure.</strong> For each scheduled stop, we compare the time the vehicle was reported
		there with the timetable. Metro's standards state an on-time window of 1 minute early to 5 minutes
		late for buses and do not state one for rail. We use the same window for rail.
	</p>
	<p class="mt-4">
		<strong>Why every measured stop.</strong> Riders board and leave at every stop, not only at the end
		of the line. We score every measured stop after the first, because a vehicle waits at the first stop
		and that time measures a departure.
	</p>
	<p class="mt-4">
		<strong>What Metro reports.</strong> Its
		<a href={standards} rel="noreferrer">2025 Transit Service Policies and Standards</a>, section
		3.3, state how bus and rail on-time performance are measured. Bus is measured at all timepoints
		along a route, and rail at the end terminal on arrival. Metro's board report
		<a href={boardReport} rel="noreferrer">File 2025-0860</a>, to the Operations, Safety, and
		Customer Experience Committee on 20 November 2025, gives the figures for July to September 2025,
		78.2 percent for buses and 99.4 percent for rail. Metro's definitions ask a different question
		than ours, and its figures cover a different period.
	</p>
	<p class="mt-4">
		<strong>What the feed gives us.</strong> A vehicle's distinct reports are a median 5 to 6
		seconds apart (5 for rail, 6 for bus, measured over 8 to 14 November 2026), but a vehicle
		usually stops reporting its trip before it reaches the last stop. We estimate last-stop times
		from the last report before arrival, and many read early. From 18 August to 15 November 2026,
		93,955 of 93,956 measured rail last stops were timed this way. That is about 5 percent of the
		rail stops we score, and about 1 percent of the bus stops we score. These counts come from the
		<a href={issue133} rel="noreferrer">issue 133 analysis</a> and cover that period only.
		{#if railShare}In the same analysis, on 87,326 rail trips where the previous stop had a stopped
			report, the share on time fell from about 67 percent at that stop to about 55 percent at the
			last stop, mostly into early arrivals.{/if}
	</p>
	<p class="mt-4">
		<strong>What we cannot explain.</strong>
		{#if railShare}Scoring only last stops, our rail share is 53.7 percent over the same period.
			That is lower than our all-stops share, not higher, so the different question does not account
			for the whole gap with Metro's 99.4 percent.{/if}
		We have not been able to confirm how Metro times a terminal arrival.
	</p>
	<NetworkShares {railGate} />
</section>
