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

Source Serif 4 sets headlines and article text. Inter sets kickers, captions,
labels and every number, with `tabular-nums`. Both are self-hosted, latin only,
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
`source` snippets), `Rule`, `LineBullet` and `LineChip`.

## Charts

Charts read CSS variables, so the theme applies without a rebuild. In Observable
Plot, pass `"var(--chart-ink)"` as a color. Use `--chart-grid` for grid lines,
`--chart-axis` for tick labels, `--chart-annotation` for direct labels, and
`var(--line-a)` for a line's marks. Do not copy hex values into chart code.

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
3:1 for bullet letters and for marks that carry meaning. Hairlines and grid
lines are decoration and are not checked. It needs Node 22.18 or newer, which
runs `.ts` files without a flag.
