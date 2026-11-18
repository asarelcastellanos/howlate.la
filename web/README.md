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
(`/lines/* /200 200`) sends every line path to it. The Lines section has the
details.

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
production, so nothing uses it. For offline work, set `PUBLIC_DATA_BASE=/data`
and put a copy of the bucket's `site/` folder in `web/static/data/`.

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

`static/_redirects` holds the rule `/lines/* /200 200`, which answers every
`/lines/*` path with `200.html`, the app shell that adapter-static writes, and
keeps the address. The target has no `.html` because Cloudflare Pages redirects
a `.html` target to the clean URL, which changes the address and breaks the
route. Without it, Cloudflare Pages serves the prerendered home
page for a path it did not build. A rail line page hides the on-time share while
`SHOW_RAIL_ONTIME` in `src/lib/config.ts` is false (issue #133).

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

## Ranking

`/ranking` is prerendered, and the browser loads `index.json` with
`readRankingIndex`. The page ranks bus lines by the share of measured arrivals
from 1 minute early to 5 minutes late, counted at every stop. It is not Metro's
published figure, and the page says so. Two panels list the top and bottom five.
The table below has every ranked line, and its three metric headers are buttons
that sort it. Headers sort best first (the highest on-time share, the lowest
median delay or 90th percentile) and a second click reverses. Lines with equal
values share a rank and keep line-id order in both directions. A line that ties
with the fifth line of a panel is shown too, so a panel can hold six.

`rankLines` in `src/lib/ranking.ts` holds the logic, and `tests/ranking.test.ts`
checks the order against a plain sort on the real index when `static/data` exists.

- `MIN_RANKED_ARRIVALS` is 500. A line under it is listed under "Not ranked"
  with its arrival count. In the 2026-11-16 run (90 days) one of 109 bus lines
  was under it, line 697 at 202 arrivals, and the next smallest was 18,078. Below
  500 arrivals, five arrivals changing move a share by more than a point. The
  comment on the constant has the arithmetic.
- Rail is never ranked. A small rail table shows median and 90th percentile
  only, and `rankLines` also drops rail from an on-time ranking while
  `SHOW_RAIL_ONTIME` in `src/lib/config.ts` is false (issue #133).
- Until the daily run after a release, the live bucket's `index.json` has no
  `n`, `med`, `p90`, `pct5` or `ontime`. `checkRankingIndex` turns that into a
  `shape` error, and the page shows "This page needs newer data than the site has
  yet. Try again in a few minutes." with a retry button. `ResultView`'s boundary
  covers a throw while the page draws.
- Table delays show minutes with one decimal, such as "1.3 min late". Seconds
  under two minutes and whole minutes above would not read as sorted.

Known limits of the ranking. Neither shows in the 2026-11-16 run, which has 108
ranked bus lines and no bus median below 19 seconds.

- With 10 or fewer ranked lines, the "Least reliable" panel is short or empty
  while its caption still promises five lines, because the panel leaves out any
  line the "Most reliable" panel already shows.
- Sorting by median delay or 90th percentile puts the smallest number first, so
  a line with a negative median (early on average) ranks above a line that is
  on time.

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
  (`pacificToday` in `src/routes/behind-the-scenes/StatusPanel.svelte`), so a
  device with a wrong clock shows a wrong warning. It is accepted because
  `health.json` has no generation timestamp to compare against, and the miss
  affects only a device with a wrong clock. A test in `tests/behind.test.ts`
  records the current behavior.
- The public line, index and network JSON still carry rail `ontime` values. The
  pipeline writes them (`ONTIME` in `pipeline/src/howlate_pipeline/aggregate.py`)
  and the site hides them with `SHOW_RAIL_ONTIME` in `src/lib/config.ts`.
  Stripping them waits for issue #157, because that decision may turn rail
  on-time back on, and a strip needs a schema change and regenerated types.

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
