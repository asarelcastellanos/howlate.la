<script lang="ts">
	import { pairs, parseTokens } from '#lib/design/contrast.ts';
	import Figure from '#lib/design/Figure.svelte';
	import Headline from '#lib/design/Headline.svelte';
	import Kicker from '#lib/design/Kicker.svelte';
	import LineBullet from '#lib/design/LineBullet.svelte';
	import LineChip from '#lib/design/LineChip.svelte';
	import Masthead from '#lib/design/Masthead.svelte';
	import Rule from '#lib/design/Rule.svelte';
	import { BUS_SERVICES, LINES, type BusService } from '#lib/design/lines.ts';
	import css from '../layout.css?raw';

	// The same pair list the contrast test checks, one row per pair.
	const rows = new Map<string, { kind: string; light: number; dark: number; pass: boolean }>();
	for (const r of pairs(parseTokens(css), LINES)) {
		const row = rows.get(r.name) ?? { kind: r.kind, light: 0, dark: 0, pass: true };
		if (r.theme !== 'dark') row.light = r.ratio;
		if (r.theme !== 'light') row.dark = r.ratio;
		rows.set(r.name, { ...row, pass: row.pass && r.pass });
	}
	const scale = [
		['kicker', 'kicker', 'Kicker above a headline'],
		['headline-xl', 'headline-xl', 'Headline, extra large'],
		['headline', 'headline', 'Headline for a section'],
		['dek', 'dek', 'Dek, the one sentence under a headline'],
		['body', '', 'Body text in the reading column is 18 px Source Serif 4.'],
		['caption', 'caption', 'Caption and source note, 13 px Inter'],
		['data', 'data', '1,284 stops, 6.4 min median, 92.0%']
	];
	const swatches = ['paper', 'ink', 'ink-muted', 'rule', 'sunk', 'focus'];
	const ramp = ['On time', '', '', '', 'Very late'];
	const buses: [BusService, string][] = [
		['local', '4'],
		['rapid', '720'],
		['limited', '344'],
		['express', '487/489']
	];
</script>

<svelte:head>
	<title>Design specimen · HowLate</title>
	<meta name="robots" content="noindex" />
</svelte:head>

<Masthead dateline="Specimen, not data" />

<main class="page pb-16">
	<section class="pt-10 pb-6">
		<Kicker>Design system</Kicker>
		<Headline dek="Every piece of the visual foundation, in the theme your device is using.">
			Specimen
		</Headline>
	</section>

	<Rule weight="thick" />
	<section class="my-8">
		<Kicker>Type scale</Kicker>
		{#each scale as [name, cls, sample] (name)}
			<div class="border-t py-3">
				<p class="kicker text-ink-muted mb-1">{name}</p>
				<p class={cls}>{sample}</p>
			</div>
		{/each}
	</section>

	<Rule />
	<section class="wide my-8">
		<Kicker>Palette and contrast</Kicker>
		<div class="mb-6 flex flex-wrap gap-4">
			{#each swatches as name (name)}
				<div class="caption w-20">
					<div class="mb-1 h-10 border" style="background:var(--{name})"></div>
					{name}
				</div>
			{/each}
		</div>
		<table class="data-table">
			<thead>
				<tr
					><th>Pair</th><th class="hidden sm:table-cell">Needs</th><th>Light</th><th>Dark</th><th
						>AA</th
					></tr
				>
			</thead>
			<tbody>
				{#each rows as [name, row] (name)}
					<tr>
						<td>{name}</td>
						<td class="hidden sm:table-cell">{row.kind}</td>
						<td>{row.light ? `${row.light.toFixed(2)}:1` : ''}</td>
						<td>{row.dark ? `${row.dark.toFixed(2)}:1` : ''}</td>
						<td>{row.pass ? 'Pass' : 'Fail'}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</section>

	<Rule />
	<section class="my-8">
		<Kicker>Lines</Kicker>
		<div class="mb-4 flex flex-wrap items-center gap-3">
			{#each LINES as line (line.id)}<LineBullet line={line.id} size="lg" />{/each}
		</div>
		<div class="mb-4 flex flex-wrap items-center gap-3">
			{#each LINES as line (line.id)}<LineBullet line={line.id} size="sm" />{/each}
		</div>
		<div class="mb-4 flex flex-wrap items-center gap-3">
			{#each buses as [service, route] (service)}
				<LineBullet {service} {route} size="lg" />
			{/each}
		</div>
		<p class="caption text-ink-muted mb-4">
			{buses.map(([service]) => BUS_SERVICES[service].name).join(', ')} bus routes. Metro's feed gives
			no color to Local, Express or Limited routes, so these bullets are neutral.
		</p>
		<p>
			Inline, <LineChip line="a" /> and <LineChip line="e" /> share a platform at 7th Street/Metro Center.
		</p>
	</section>

	<Rule />
	<section class="wide my-8">
		<Kicker>Delay ramp</Kicker>
		<div class="grid grid-cols-5 gap-1">
			{#each ramp as label, i (i)}
				<div>
					<div class="h-12" style="background:var(--delay-{i + 1})"></div>
					<p class="caption text-ink-muted mt-1">{label || `Step ${i + 1}`}</p>
				</div>
			{/each}
		</div>
	</section>

	<Rule />
	<section class="wide my-8">
		<Kicker>Grid</Kicker>
		<div class="grid grid-cols-12 gap-1 md:gap-4">
			{#each Array.from({ length: 12 }, (_, i) => i + 1) as n (n)}
				<div class="bg-sunk data border py-2 text-center">{n}</div>
			{/each}
		</div>
		<p class="caption text-ink-muted mt-2">
			Twelve columns from 768 px up, with 16 px gutters. The reading column is 38rem.
		</p>
	</section>

	<Rule />
	<article class="my-8">
		<Kicker>Sample article</Kicker>
		<Headline size="md" dek="The answer comes first, in plain words. The figure comes second.">
			A headline states the finding
		</Headline>
		<p class="caption text-ink-muted mt-3">Placeholder text. Nothing here is measured.</p>
		<p class="mt-6">
			This paragraph shows body text at the reading width. It is about 38rem wide, which keeps lines
			near 70 characters. A figure can break out wider than the text above and below it.
		</p>
	</article>

	<Figure>
		<div class="flex h-16">
			{#each [1, 2, 3, 4, 5] as step (step)}
				<div class="flex-1" style="background:var(--delay-{step})"></div>
			{/each}
		</div>
		<div class="caption text-chart-annotation mt-1 flex justify-between font-semibold">
			<span>On time</span><span>Very late</span>
		</div>
		{#snippet caption()}Figure: a placeholder strip that shows the caption position.{/snippet}
		{#snippet source()}Source: none, layout sample only.{/snippet}
	</Figure>

	<Figure>
		<table class="data-table">
			<thead>
				<tr><th>Line</th><th>Stops</th><th>Median</th><th>Share late</th></tr>
			</thead>
			<tbody>
				{#each LINES.slice(0, 3) as line, i (line.id)}
					<tr>
						<td><LineChip line={line.id} /></td>
						<td>{(1200 + i * 310).toLocaleString('en-US')}</td>
						<td>{(1.5 + i).toFixed(1)} min</td>
						<td>{(8 + i * 3.5).toFixed(1)}%</td>
					</tr>
				{/each}
			</tbody>
		</table>
		{#snippet caption()}Hairline rules, right-aligned tabular numbers.{/snippet}
		{#snippet source()}Source: placeholder values for layout only.{/snippet}
	</Figure>
</main>
