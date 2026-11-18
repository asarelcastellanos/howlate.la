# Web

The public site for howlate.la. It builds to static files. Right now it is a
placeholder home page with a live status strip and line search, a page for each
line at `/lines/<line>`, a ranking at `/ranking`, a methodology page at `/methods`, a behind-the-scenes
page at `/behind-the-scenes`, and a design specimen with the chart components.

The design system exists. `DESIGN.md` documents it, and the `/design` page
shows every piece in the theme your device is using.

## Run it

Use Node 22.18 or newer. Run every command in `web/`.

```bash
npm ci               # install the exact versions in package-lock.json
npm run dev          # dev server with hot reload
npm run check        # svelte-check, the type check CI runs
npm run lint         # prettier and eslint
npm run types        # regenerate src/lib/data/types.ts from pipeline/schemas
npm test             # contrast, generated types, data loader and chart tests
npm run build        # writes the static site to build/, then runs tests/built.test.ts on it
npm run preview      # serves build/ on http://localhost:4173
npm run e2e          # Playwright and axe, against a running preview
npm run lighthouse   # Lighthouse on mobile, against a running preview
```

To run against local data, set `PUBLIC_DATA_BASE=/data` when you build or start
the dev server. Put a copy of the bucket's `site/` folder in `web/static/data/`,
which git ignores.

## Navigation and page head

The main navigation is `src/lib/design/Nav.svelte`, and `Masthead` draws it, so
every page has it with no per-page code. It also draws a "Skip to content" link
that jumps to the `<main id="main">` each page sets. The links come from one
list, `NAV` in `src/lib/nav.ts`. An entry with `ready: false` is not drawn. A PR
that adds a page flips its flag. The current page gets `aria-current="page"`
from the route id.

Every page calls `PageHead` (`src/lib/PageHead.svelte`) once with a `title`,
a `description` of 40 to 160 characters, a `path` and optionally `noindex`. It
writes the title, the description, the canonical link and the Open Graph and
Twitter tags. Only the home page keeps its whole title. Any other title gets
" · HowLate" added. A page never writes its own `<title>`, because two tags in
one head leave the browser to pick one.

`SITE_URL` in `src/lib/config.ts` builds the canonical and preview addresses. It
is `https://howlate.la`, with no trailing slash. The custom domain replaced the
pages.dev address in 0.5.0 (issue #32). Cloudflare redirects www.howlate.la to
it with a redirect rule in the dashboard, so no code handles `www`.

The preview image is `static/og.png`, made from `scripts/og.html`.
`scripts/README-og.md` has the steps to remake it. `tests/built.test.ts` runs
after `npm run build`. It reads every prerendered page and fails on a missing
nav, a missing or shared title or description, a page without one h1, or a
preview image of the wrong size.

## Browser checks

`e2e/` holds the Playwright, axe and Lighthouse checks that the `browser` job
runs in CI. They read a small committed copy of the data in `e2e/fixture/`, not
the live bucket. `e2e/README.md` says how to run them and how the fixture was
made.

## Decisions

The 0.4.0 section of `docs/release-plan.md` records the stack.

### SvelteKit with adapter-static

The site is static files. `npm run build` writes them to `build/`, and every
page is prerendered (`src/routes/+layout.ts`). No server runs in front of them.
The data does not need a server either. Per the release plan, the browser
fetches JSON from R2 at runtime, so a new day of data needs no rebuild.

The adapter also writes `build/200.html`, the app shell, so the client router
can handle a path that was not prerendered, such as a line missing from
`src/lib/data/lines.json`. Pages does not
pick that file by itself for an unknown path. The rule in `static/_redirects`
(`/lines/* /200 200`) sends a line path to it when no per-line rule matches first,
which means an id that is not in `src/lib/data/lines.json`. The Lines section has
the details.

### Tailwind CSS v4 with shadcn-svelte

Tailwind v4 loads through its Vite plugin in `vite.config.ts`, with no
`tailwind.config.js`. The color tokens are in `src/routes/layout.css`, exposed
through a Tailwind `@theme` block. The charts read them as CSS variables.

shadcn-svelte is initialised, with `components.json`, the `cn` helper in
`src/lib/utils.ts`, and its base CSS variables in `src/routes/layout.css`. No
component is installed. Add one only when a page needs it.

HeroUI is a React library, so it does not fit a Svelte site.

### Observable Plot for charts

The release plan names Observable Plot for the heatmap, the line chart, and the
distribution strip. The charts must read the same CSS variables as the rest of
the site, so they follow the light and dark themes. Plot is installed, and
`src/lib/charts/` holds the three charts. `DESIGN.md` says how they read the
tokens. Only the specimen route imports Plot, so the home page does not load it.

Tests draw the charts without a browser. Plot takes a `document` option, and
`linkedom` supplies one. `tests/register.mjs` compiles `.svelte` files for
`node:test`, so a test can render a component to a string.

Recharts is a React library, so it does not fit a Svelte site.

### Cloudflare R2 for data

The daily job copies each published run to R2, and `current.json` is written
last. The browser fetches the JSON at runtime. `gs://howlate-derived` never
serves the site, because Cloud Storage egress costs $0.12/GB.

## Data

The types in `src/lib/data/types.ts` are generated from the JSON Schemas in
`pipeline/schemas/`, never written by hand. Run `npm run types` after a schema
change and commit the result in the same PR. CI runs it and fails on any diff,
and `tests/types.test.ts` fails when the committed file is stale. A renamed
field then breaks `npm run check` where the site reads it.

`src/lib/data/load.ts` loads the files. `openRun(base)` fetches
`<base>/site/current.json`, then returns readers for `index.json`,
`status.json`, `network.json`, `health.json` and `lines/<line>.json` from the run's `prefix`,
so a page never mixes two runs. A failed request, a status other than 200, or a body that is not
JSON comes back as `{ ok: false, error }`, never a throw, so a page can show an
error state. The pipeline's contract test covers the full shape. The loader
checks only the fields the pages read (`src/lib/data/shape.ts`) for `current.json`,
`index.json`, `status.json`, `health.json` and the line files. A file that fails comes back with the error
kind `shape`. The bucket holds the previous shape from a release until the next
daily run, and the page then shows "This page needs newer data than the site has
yet" with a retry button. `ResultView` also wraps the data views in a
`<svelte:boundary>`, so a render error shows the error box and not a 500 page. `Remote` also turns a load that rejects into the same error state, with its
retry button, so a bug outside the loader never leaves the loading line up.

`PUBLIC_DATA_BASE` sets `base` and is inlined at build time. SvelteKit 3 reads
it from `src/env.ts` and exposes it through `$app/env/public`, which
`src/lib/data/base.ts` re-exports as `DATA_BASE`. It defaults to
`DEFAULT_DATA_BASE` in `src/env.ts`, which is `https://data.howlate.la`, the
custom domain on the R2 bucket, so local development and every preview read the
real published data. The r2.dev address of the bucket is rate limited and not for
production, so nothing uses it. The Cloudflare Pages project must not set
`PUBLIC_DATA_BASE` for production, because it overrides the default in
`src/env.ts`. It did once, and it pointed at the old address. For offline work,
set `PUBLIC_DATA_BASE=/data` and put a copy of the bucket's `site/` folder in `web/static/data/`.

CORS on the data domain stays `*`. The data is public and read-only, and preview
deployments on pages.dev subdomains, which change with every branch, must be
able to read it.

## Versions

Every version in `package.json` is exact, with no `^` or `~`, and
`package-lock.json` is committed. CI runs `npm ci`, which fails when the two
disagree.

- TypeScript is 6.0.3, not the newest 7.x. `@sveltejs/kit` 3.2.0 declares
  `typescript@^6.0.0` as a peer dependency.
- Imports use `#lib`, the alias SvelteKit 3 scaffolds through `package.json`
  `imports`, not `$lib`. The shadcn-svelte 1.8.1 CLI rejected the `$lib`
  aliases because it found no matching path in `tsconfig.json`, and it accepted
  the `#lib` aliases.

## Deploys

Previews and production deploys come from a Cloudflare Pages project connected
to this repo through Git, so no deploy config or secret lives in the repo.
Nothing in this folder holds Cloudflare config. The project is created in the
Cloudflare dashboard with these settings.

- Framework preset: None
- Root directory: `web`
- Build command: `npm run build`
- Output directory: `build`
- Environment variable: `NODE_VERSION=22`
- Production branch: `main`
- Preview deployments: on for all branches

## Lines

The home page loads `status.json` and `index.json` with `loadHome`
(`src/lib/home.ts`), which opens one run and reads both from it. It shows the
status strip and a search box (`SearchBox.svelte`, ranked by `searchLines` in
`src/lib/search.ts`). Choosing a result opens
`/lines/<line>`. That route renders in the browser, and the build also prerenders
a page for each line in `src/lib/data/lines.json` (see "Line page head" below). It reads
`index.json` and `lines/<line>.json` from one run, then shows a headline for each
direction, a switch between directions, and the three charts. An id that is not
in the index, or a line file that returns 404, shows a "We could not find that
line" message. A failed load shows the error state with a retry button. The site
is static, so both answer with status 200.

The line page is the slowest page to paint, because its headline needs three
files before it draws. `LineView` loads the chart code, which holds Observable
Plot, about 100 ms after the headline mounts, so the chart chunk is not part of
what Lighthouse counts toward the headline's paint. That kept the page above
the 0.9 gate. A test that needs the charts passes the component in as `charts`.
Starting the data fetch earlier from an inline script in `src/app.html` was
measured at about +0.01 and left out, because it repeated the loader's URL
logic in a script.

`static/_redirects` holds the rule `/lines/* /200 200`. The 115 per-line rules
come before it and serve a listed line its own prerendered file, so the wildcard
answers only a path with no rule, such as an unlisted id, with `200.html`, the
app shell that adapter-static writes, and keeps the address. The target has no
`.html` because Cloudflare Pages redirects a `.html` target to the clean URL,
which changes the address and breaks the route. Without it, Cloudflare Pages serves the prerendered home
page for a path it did not build. A rail line page shows the on-time share like a
bus page, because `SHOW_RAIL_ONTIME` in `src/lib/config.ts` is true (see "The
on-time share and its note").

### Line page head

`src/routes/lines/[line]/+page.ts` sets `prerender = true`, and `entries()` returns
every id in `src/lib/data/lines.json`. `Remote` renders its loading state at build
time, so each `build/lines/<id>.html` holds the title, a description, the canonical
link and `og:image` without JavaScript. `lineHead` (`src/lib/lineHead.ts`) builds
the title and a description that is different for every line, from the line's label,
mode, ends and corridor, and the page and the prerendered file both call it, so the
browser's head matches the served one. An id that is not in the list is not built.
Pages serves `200.html` for it, and the page shows the not-found message.

The build does not fetch the index, so an unreachable index cannot fail it. The list
is committed instead. It keeps `line`, `label`, `mode`, `to` and `via` for each line
and no metric. Run `npm run lines:refresh` when Metro adds a line, then commit
`lines.json`. The script reads the index from `PUBLIC_DATA_BASE` (default
`https://data.howlate.la`). A line missing from the list gets no title or preview in
the served HTML until the list is refreshed, and it still works in the browser.
`tests/built.test.ts` checks that every id in the list has a built file with a title,
a description of 40 to 160 characters, a canonical link and `og:image`.

`lines:refresh` also rewrites the block between the `# BEGIN line pages` and
`# END line pages` lines in `static/_redirects`, one rule per id
(`/lines/720 /lines/720 200`). Do not edit that block by hand. Pages follows a
redirect rule even when a file matches the path, and the first matching rule wins, so
the wildcard `/lines/* /200 200` alone sends every line to the app shell. A preview
served `/lines/720` and `/lines/zzz` as the same 1,508 bytes with no title. The
per-line rules sit before the wildcard so the prerendered files are served. Each rule
rewrites the path to itself and has no `.html` target. A preview with `.html` targets
answered `/lines/720` with 308 and `location: /lines/720`, an endless loop, because
Pages redirects a `.html` target to the clean URL and that URL matched the rule again.
`tests/lineRedirects.test.ts` fails when the committed file no longer matches
`lines.json`.

A line removed from the live index keeps its prerendered, indexable page and its
per-line rule until someone reruns `npm run lines:refresh` and commits. A renamed
line keeps its old title the same way. `scripts/refresh-lines.ts` rejects only an
empty list or a duplicate id, so check the diff of `lines.json` before committing.

A trailing slash, `/lines/720/`, does not match the per-line rule, so Pages
answers it with the app shell and no title. A preview on 2026-11-17 measured
1,506 bytes and no title tag. Nothing on the site links with a trailing slash, so
this stays as an accepted limit.

## Ranking

`/ranking` is prerendered, and the browser loads `index.json` with
`readRankingIndex`. The page ranks bus lines by the share of measured arrivals
from 1 minute early to 5 minutes late, counted at every measured stop. It is not Metro's
published figure, and the page says so. Two panels list the top and bottom five.
The table below has every ranked line, and its three metric headers are buttons
that sort it. Headers sort best first and a second click reverses. The on-time
share sorts highest first. The median delay and the 90th percentile sort by
distance from the on-time window (60 seconds early to 300 seconds late), then by
the size of the delay, so a median of 30 seconds early and one of 30 seconds
late tie. Lines with equal values share a rank and keep line-id order in both
directions. A line that ties with the fifth line of a panel is shown too, so a
panel can hold six.

`rankLines` in `src/lib/ranking.ts` holds the logic, and `tests/ranking.test.ts`
checks the order against a plain sort on the real index when `static/data` exists.

- `MIN_RANKED_ARRIVALS` is 500. A line under it is listed under "Not ranked"
  with its arrival count. In the 2026-11-16 run (90 days) one of 109 bus lines
  was under it, line 697 at 202 arrivals, and the next smallest was 18,078. Below
  500 arrivals, five arrivals changing move a share by more than a point. The
  comment on the constant has the arithmetic.
- Rail is never ranked against buses. A small rail table lists its on-time
  share, median and 90th percentile, and the page passes `rankLines` bus lines
  only. `rankLines` also drops rail from an on-time ranking when its `railGate`
  argument, which defaults to `SHOW_RAIL_ONTIME`, is false.
- Until the daily run after a release, the live bucket's `index.json` has no
  `n`, `med`, `p90`, `pct5` or `ontime`. `checkRankingIndex` turns that into a
  `shape` error, and the page shows "This page needs newer data than the site has
  yet. Try again in a few minutes." with a retry button. `ResultView`'s boundary
  covers a throw while the page draws.
- The on-time share prints to one decimal, and `shareText` in `src/lib/share.ts`
  caps a value below 100 at 99.9. The cap guards unrounded input only. The
  pipeline already rounds the share to one decimal and the published files carry
  no on-time count, so a true 99.96 is published as 100.0 and prints as "100.0".
  The site cannot tell it from a line that is exactly 100. No published line is
  near it today. In run 20261117T130127Z-b2b787 the best line was 80.6 percent.
  47 hour cells read exactly 100.0, and all have `n` of 207 or fewer.
- Table delays show minutes with one decimal, such as "1.3 min late". Seconds
  under two minutes and whole minutes above would not read as sorted.

Known limit of the ranking. It does not show in the 2026-11-16 run, which has
108 ranked bus lines.

- With 10 or fewer ranked lines, the "Least reliable" panel is short or empty,
  because the panel leaves out any line the "Most reliable" panel already shows.
  Its caption counts the lines it lists, so it does not promise five.

## The on-time share and its note

Since 0.5.1 rail shows its on-time share like a bus line. The owner decided that
on 2026-11-17, after issue #133 found no cause for the gap with Metro. Nothing in
the pipeline or the published data changed.

- `SHOW_RAIL_ONTIME` in `src/lib/config.ts` is true. `showsOntime`, `headline`,
  `rankLines`, `LineView`, `sharesText` and the methods section
  (`MeasureOnTime.svelte` and `NetworkShares.svelte`) read it, each through a
  `railGate` argument or prop, so a test covers the closed gate too.
  `RailTable` gets the gate through `showRailOntime`, which defaults to
  `showsOntime('rail')`. Setting the constant to false brings the old rail hold
  back.
- The methods copy is written for the open gate. With the gate closed, the live
  sentence and the section leave out every sentence that states a rail share,
  and the rest still reads. Nothing else on the methods page states one. Reopen
  the copy if the gate closes for good.
- Every on-time share has a note, `OntimeNote`, and an asterisk, `OntimeMark`,
  beside the figure. They appear under each direction's headline on a line page,
  under the heatmap's hour readout, under the two ranking panels, over the
  ranking table, and in the rail table. The home page shows no share. The live
  sentence on the methods page sits inside the section the note links to, so it
  has no note of its own. A new place that shows a share must render the note.
- The asterisk is hidden from screen readers. The words and the "How we measure"
  link carry the meaning. Under 640 px (`sm`) the note shortens to the window, the
  Metro caveat and the link.
- The link is `MEASURE_HREF` in `src/lib/ontimeNote.ts`, a plain path, because
  the chart components import the note and their tests run outside SvelteKit.
  `MeasureOnTime.svelte` uses `MEASURE_ANCHOR` as the id of the "How we
  measure on-time" section, and `tests/methods.test.ts` checks that the page
  renders it.
- That section's figures for last stops (93,955 of 93,956, 53.7 percent, about
  5 and 1 percent) come from the issue #133 analysis of 18 August to 15 November
  2026 and say so. They are fixed. The current bus and rail shares are not typed
  in. `NetworkShares.svelte` reads them from `network.json` and `status.json`
  with `loadShares` after the page loads, and shows nothing if the load fails.

## Behind the scenes

`/behind-the-scenes` is prerendered. The browser loads `health.json` with
`readStatusReport` in `src/lib/behind.ts`, which hands the page the loader's
result as data. A missing file (a 404) or an old shape shows "Status data is not
published yet", and a failed request shows a separate "could not be loaded"
message. Neither uses the site's error box. `Remote` still wraps the panel in
its `<svelte:boundary>`, so a render error shows the error box.

- The panel compares `last_day` with today's date in Los Angeles
  (`pacificToday` in `src/lib/date.ts`, read in the browser). It turns to a
  warning when the gap is more than `STALE_AFTER_DAYS` (3). The daily job
  runs at 05:00 Pacific and grades today minus 2, so from midnight until the run
  finishes the newest day is 3 days old and a gap of 3 is normal. The
  pipeline's own alarm allows 4 (`MAX_LAG_DAYS` in `r2.py`). A future date is
  not a warning.
- The 14-day strip (`buildStrip`) has one cell per day ending on `last_day`.
  A day with no report is an empty dashed cell, not a failed one. Each cell
  has a shape, a color and hidden text.
- The check list comes from `health.json`, with the pipeline's own labels and
  values rounded for display. The page hard-codes no check names. A label does
  not say its unit, so the list shows no units.
- The diagram (`Architecture.svelte`) is one inline SVG, a single column that
  scales to a phone, with the same flow as a numbered list under it. It names
  no bucket, host or account.
- The cost section gives only the owner's budget, labelled as an estimate, and
  the archive's growth of about 1 GB a day. It promises no breakdown.
- `tests/built.test.ts` counts the `<title>` in the head only, because the
  diagram's SVG has its own `<title>`.

To see it with local data, build with `PUBLIC_DATA_BASE=/data` and put the
files in `static/data/site/<run>/` with a `current.json` that names the run.
Only `health.json` is needed for this page.

## Accepted limits

Known issues from 0.5.0 that stay as they are, with the reason.

- The behind-the-scenes warning reads today from the browser clock
  (`pacificToday` in `src/lib/date.ts`), so a device with a wrong clock shows a
  wrong warning. It is accepted because
  `health.json` has no generation timestamp to compare against, and the miss
  affects only a device with a wrong clock. A test in `tests/behind.test.ts`
  records the current behavior.
- The site shows the rail on-time share although HowLate's 64.4 percent over 18
  August to 15 November 2026 is far from Metro's 99.4 percent for July to
  September 2025, and the cause is not known (issues #133 and #157).
  The note beside each share and the methods section say so. The public JSON
  carries the rail values, as the pipeline writes them (`ONTIME` in
  `pipeline/src/howlate_pipeline/aggregate.py`).

## Not done yet

- Screenshot comparison. The release plan asks for it, but a baseline image
  from macOS differs from one made on the Linux CI runner, so no baseline is
  committed and CI has no screenshot gate.

## Reasons still to record

The release plan decides these but does not give the reason.

- SvelteKit over Astro and a Vite React app.
- shadcn-svelte over HeroUI, beyond HeroUI being React-only.
- Observable Plot over ECharts.
- R2 over a Worker, and what R2 costs.
