<script lang="ts">
	// One column of boxes, 340 units wide, so it scales down to a phone with no
	// second layout. The list below it holds the same flow in words, and the
	// image is hidden from screen readers except for its title and description.
	type Box = { n: number; x: number; y: number; w: number; title: string; sub: string };
	const H = 56;
	const STEP = 88;
	const boxes: Box[] = [
		{ n: 1, x: 0, y: 0, w: 162, title: 'Bus feed', sub: 'from Metro' },
		{ n: 1, x: 178, y: 0, w: 162, title: 'Rail feed', sub: 'from Metro' },
		{ n: 2, x: 0, y: STEP, w: 340, title: 'Collector', sub: 'One small VM, always on' },
		{ n: 3, x: 0, y: STEP * 2, w: 340, title: 'Raw archive', sub: 'Append-only cloud storage' },
		{
			n: 4,
			x: 0,
			y: STEP * 3,
			w: 340,
			title: 'Daily pipeline',
			sub: 'Grades each stop against the timetable'
		},
		{
			n: 5,
			x: 0,
			y: STEP * 4,
			w: 340,
			title: 'Derived data',
			sub: 'Site JSON, rebuilt from the raw archive'
		},
		{ n: 6, x: 0, y: STEP * 5, w: 340, title: 'R2', sub: 'Public copy the browser reads' },
		{ n: 7, x: 0, y: STEP * 6, w: 340, title: 'This site', sub: 'Static pages on Cloudflare Pages' }
	];
	// Each arrow starts at the bottom of a box and ends at the top of the next row.
	const arrows = [
		{ x: 81, y: H },
		{ x: 259, y: H },
		...[1, 2, 3, 4, 5].map((row) => ({ x: 170, y: STEP * row + H }))
	];
	const steps = [
		[
			"Metro's two live feeds",
			"One carries bus positions and one carries rail. A vehicle's distinct reports are a median 5 to 6 seconds apart (8 to 14 November 2026)."
		],
		[
			'Collector',
			"A program on one small virtual machine holds both feeds open and writes down every update. It also keeps a copy of Metro's timetable when the timetable changes."
		],
		[
			'Raw archive',
			'Every update goes into cloud storage. By rule only the collector writes to it, and nothing deletes from it.'
		],
		[
			'Daily pipeline',
			'A Cloud Run job starts at 5 am Pacific. It grades each scheduled stop against the timetable in force that day, then runs its checks.'
		],
		[
			'Derived data',
			"The graded days and the site's JSON files. The raw archive can rebuild them, so rerunning a day replaces only that day."
		],
		[
			'R2',
			'The job copies each finished run to Cloudflare R2 and moves a pointer file to the new run last, so a reader never sees half a run. R2 charges no fee for data leaving it.'
		],
		[
			'This site',
			'Static pages on Cloudflare Pages. Your browser fetches the JSON from R2 when the page opens, so a new day of data needs no rebuild.'
		]
	];
</script>

<figure class="my-6">
	<svg
		viewBox="0 0 340 {STEP * 6 + H}"
		role="img"
		aria-labelledby="architecture-title architecture-desc"
		class="mx-auto h-auto w-full max-w-md"
	>
		<title id="architecture-title">How HowLate gets data to this site</title>
		<desc id="architecture-desc"
			>Seven steps from top to bottom. Metro's bus and rail feeds go to the collector. The collector
			writes the raw archive. The daily pipeline reads it and writes derived data. The job copies
			that to R2, and this site reads it from R2.</desc
		>
		<defs>
			<marker
				id="arrowhead"
				viewBox="0 0 10 10"
				refX="9"
				refY="5"
				markerWidth="8"
				markerHeight="8"
				orient="auto"
			>
				<path d="M0 0L10 5L0 10z" class="fill-ink" />
			</marker>
		</defs>
		{#each arrows as arrow (`${arrow.x}-${arrow.y}`)}
			<line
				x1={arrow.x}
				y1={arrow.y}
				x2={arrow.x}
				y2={arrow.y + STEP - H}
				class="stroke-ink"
				stroke-width="1.5"
				marker-end="url(#arrowhead)"
			/>
		{/each}
		{#each boxes as box (box.title)}
			<!-- Metro's boxes are dashed, because HowLate does not run them. -->
			<rect
				x={box.x + 0.75}
				y={box.y + 0.75}
				width={box.w - 1.5}
				height={H - 1.5}
				rx="4"
				class="stroke-ink {box.n === 1 ? 'fill-paper' : 'fill-sunk'}"
				stroke-width="1.5"
				stroke-dasharray={box.n === 1 ? '5 4' : undefined}
			/>
			<circle cx={box.x + 22} cy={box.y + H / 2} r="11" class="fill-ink" />
			<text
				x={box.x + 22}
				y={box.y + H / 2 + 4.5}
				text-anchor="middle"
				font-size="13"
				class="fill-paper font-sans font-bold">{box.n}</text
			>
			<text x={box.x + 42} y={box.y + 24} font-size="16" class="fill-ink font-sans font-bold"
				>{box.title}</text
			>
			<text x={box.x + 42} y={box.y + 43} font-size="13" class="fill-ink-muted font-sans"
				>{box.sub}</text
			>
		{/each}
	</svg>
	<figcaption class="caption text-ink-muted mt-3 border-t pt-2">
		Dashed boxes belong to Metro. Arrows show where the data goes.
	</figcaption>
</figure>

<ol data-flow class="mt-4 list-decimal space-y-3 pl-6">
	{#each steps as [title, body] (title)}
		<li><strong>{title}.</strong> {body}</li>
	{/each}
</ol>
