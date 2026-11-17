# Design system

HowLate reads like a newspaper data desk. The tokens live in
`src/routes/layout.css`, the line data in `src/lib/design/lines.ts`, and the
components in `src/lib/design/`. `/design` is the specimen page and the visual
test surface. It is marked noindex.

## Palette

Paper is a warm off-white and ink is near black. The dark theme swaps them. The
theme follows `prefers-color-scheme` through one `@media` block in
`layout.css`, with no JavaScript and no toggle. The shadcn-svelte variable
names (`--background`, `--primary` and the rest) still work and point at these
tokens. Tailwind utilities exist for each token, such as `bg-paper`, `text-ink`,
`text-ink-muted`, `border-rule` and `text-line-a`.

The delay ramp (`--delay-1` to `--delay-5`) runs from on time to very late. A
later step has more contrast with the page, so it is darker on paper and
brighter on the dark theme.

## Type

Source Serif 4 sets headlines and article text. Inter sets labels, captions, kickers and the
numbers in tables and charts, with `tabular-nums`. The three large headline
figures on the home page (`StatusStrip`) use the serif face by design. Both are self-hosted, latin only,
through exact-pinned `@fontsource-variable` packages. The scale is a set of
`@theme` sizes, `text-kicker`, `text-headline-xl`, `text-headline`, `text-dek`,
`text-body`, `text-caption` and `text-data`. The two headline sizes are fluid.

## Layout

A page is a `.page` grid. Children sit in the 38rem reading column. Add `.wide`
for a figure up to about 70rem, or `.full` for edge to edge. The side gutters
are 16 px on a phone. For 12 columns, use `grid md:grid-cols-12` inside a
`.wide` element. `.rule`, `.rule-thick` and `.rule-double` draw the rules.

## Components

`Masthead` (takes a `dateline` prop, because a build date would go stale),
`Kicker`, `Headline` (with an optional `dek`), `Figure` (children, `caption` and
`source` snippets), `Rule`, `LineBullet`, `LineChip` and `StatusStrip` (the
network totals from `status.json`).

The ranking page's pieces sit beside its route in `src/routes/ranking/`, because
no other page uses them. Its on-time bar is plain HTML, not Plot. The fill is
`bg-chart-ink` on a `bg-chart-grid` track, and the number always prints beside
it.

## Charts

Charts are Observable Plot, in `src/lib/charts/`. They read CSS variables, so
the theme applies without a rebuild or any JavaScript. Every color is a string
from `charts/theme.ts`, such as `var(--chart-ink)`. The delay ramp goes to Plot
as a threshold color scale whose range is `var(--delay-1)` to `var(--delay-5)`.
`--chart-grid` draws grid lines, `--chart-quiet` draws the heatmap hatch and
dotted outline, `--chart-axis` draws tick labels,
`--chart-annotation` draws direct labels, and `--paper` draws the halo behind
a label. Never copy a hex value into chart code. `tests/charts.test.ts` fails
on one.

There is no legend box. Labels sit on the data, and the heatmap has a short key
built from the same ramp. A chart states its finding in its `aria-label`, and
the heatmap also has a hidden table.

To add a chart:

1. Write a pure function in `charts/<name>.ts` that takes data and
   `{ width, document }` and returns the Plot element. Pass `document` to
   `Plot.plot`, so a test can draw it without a browser.
2. Wrap it in a small `.svelte` file with `ChartFigure`, which sizes the chart to
   its container, shows the empty message, and adds the caption and source.
3. Load its data with `Remote`, which shows the loading and error states.
4. Add a test that draws it from `charts/fixtures.ts` and checks its marks.

A median from fewer than `MIN_ARRIVALS` arrivals is never a ramp color and is
never labelled as the worst. The heatmap hatches the hour, the strip draws a
hollow dot, and the line chart breaks the line. The reason is in `theme.ts`.
When no hour has a median above zero, the heatmap marks no worst hour and its
`aria-label` says no hour ran late.

## Lines

The bullet always shows Metro's raw color. Chips and chart marks use `--line-*`,
which is a darker or lighter variant where the raw color is under 3:1 on that
theme. Bus routes with no color in `routes.txt` get a neutral bullet by service
type, and Rapid uses ink and paper.

To add a line, add a row to `LINES` with its color and text color from
`routes.txt`, then add `--line-<id>` to both token blocks and a
`--color-line-<id>` entry in `layout.css`. Run `npm test`. It fails if the CSS
and `lines.ts` disagree, or if any pair drops under WCAG AA.

## Contrast test

`npm test` reads the tokens from `layout.css`. It checks 4.5:1 for text, and
3:1 for bullet letters and for marks that carry meaning. That includes the
heatmap hatch ("too few arrivals") and dotted outline ("nothing measured"),
which use `--chart-quiet`. Hairlines and grid lines are decoration and are not
checked. It needs Node 22.18 or newer, which
runs `.ts` files without a flag.
