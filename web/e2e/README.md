# Browser checks

Playwright, axe and Lighthouse open the built site in Chromium at 375 px and
check it against a small committed copy of the data in `fixture/`. The CI job
`browser` in `.github/workflows/checks.yml` runs them on every pull request, and
`all-checks` waits for it.

## What runs

- `site.spec.ts` opens `/lines/<id>` for every line in the fixture index. A line
  fails on any console error or warning, an error state, a missing or second h1,
  fewer than four figures, sideways scroll, or a direction switch that does not
  match the line's direction count. It also checks the not-found message, the
  home page search, the ranking links, the three-tap path from the home page to
  the Friday 5 pm readout on line 720, and that a rail page shows no on-time
  sentence. It also opens `/behind-the-scenes` at 375 px and checks one h1, the
  newest graded day, the 14-day strip with its failed and missing days, the
  check list, no console error and no sideways scroll. A second test serves a
  copy of `health.json` through `page.route` and checks that a newest day 4 days
  old shows the warning and 3 days old does not. Both set the browser clock, so
  the fixture does not turn stale as the real date moves on. Expected values come
  from the fixture files, never from numbers typed into a test.
- `axe.spec.ts` runs axe on the home page, `/lines/720`, `/ranking`, `/methods`
  and `/behind-the-scenes`, each in light and dark. It fails on any serious or critical
  violation and prints the rule and the elements.
- `lighthouserc.cjs` runs Lighthouse three times on the home page, `/lines/720`,
  `/ranking` and `/behind-the-scenes` with its default mobile settings. The median run must score at
  least 0.9 for performance and 0.95 for accessibility. Reports stay on disk in
  `reports/lighthouse`, and nothing is uploaded.

## Run it locally

Run these in `web/`. The first two commands are the same ones the CI job runs.

```bash
npm ci && npx playwright install chromium
PUBLIC_DATA_BASE=/data npm run build && npm run e2e:stage
npm run preview -- --port 4173 &
npm run e2e && npm run lighthouse
```

Stop the preview with `kill %1`. Set `E2E_BASE_URL` to test another address or
port. `npm run e2e:stage` copies the fixture into `.svelte-kit/output/client/data`,
because `vite preview` serves that folder and not `build/`. A fresh `npm run
build` removes it, so stage again after every build. The reports go to
`reports/`, which git ignores.

`/lines/<id>` is not prerendered. In production Cloudflare Pages answers it with
`200.html`, and `vite preview` renders it on the server instead. The browser
loads the data the same way in both.

## The fixture

`fixture/site/` has the layout the site's loader reads. `current.json` names the
run folder `site/runs/<run>/`, and that folder holds `index.json`, `status.json`,
`network.json`, `health.json` and `lines/<id>.json`. The pointer's `files` is the
number of lines plus 4. `fixture/.gitignore` re-includes `site/`,
which the repository's `.gitignore` ignores for pipeline output.

It is real data with two edits, plus a `health.json` that is not copied from a
run. Eight lines come from a full `aggregate` output
over the 90 service days from 2026-08-18 to 2026-11-15.

| Line | Why it is there                                                           |
| ---- | ------------------------------------------------------------------------- |
| 720  | Two directions, Rapid bus                                                 |
| 761  | Rapid bus                                                                 |
| 4    | Two directions                                                            |
| 901  | G Line busway                                                             |
| 697  | Little data, 202 arrivals in the full data and one stop in each direction |
| 801  | Rail, the A Line                                                          |
| 804  | Rail, the E Line                                                          |
| 550  | One direction                                                             |

- **Trimmed.** Each direction keeps at most 10 stops, spread evenly along the
  route with the first and last kept, with each kept stop's cells. The profile
  is whole. The 10-stop limit keeps the fixture at 421 KB. 14 stops came to
  about 500 KB. The index and each line's totals still describe the full data, so they
  do not match the stops that remain. `status.json` and `network.json` are
  copied unchanged and describe all 117 lines, while the index lists 8.
- **One direction.** Real data has no line with one direction, because all 115
  lines in the source have two. Line 550 is a small real line with direction 0
  removed, so only direction 1 stays. Its index entry takes that direction's
  numbers.
- **health.json.** `make_fixture.py` writes 13 saved daily reports in the shape
  `report.py` writes and builds the file with the pipeline's own
  `health.document`. The 14 days end on 2026-11-15, the `last_day` in
  `status.json`. 2026-11-12 has no report, and 2026-11-10 fails its coverage
  check. The newest day lists five checks with the pipeline's labels. Three are
  ranges (`matched_rate`, `coverage`, `absurd_pct`) and two are counts (`feeds`,
  which expects 2, and `silent_lines`). The numbers are made up. The tests
  read the expected values from this file, so they stay true when the numbers
  change.
- **Source shape.** The source predates two removals, so each cell's `ontime`
  and each stop's `all.n` are deleted. `pipeline/tests/test_web_fixture.py`
  validates every file against the strict schemas in `pipeline/schemas`, so the
  fixture cannot drift from the contract.

To refresh it, run an `aggregate` build with `--no-upload` over the days you
want, then run these from the repository root.

```bash
python3 web/e2e/make_fixture.py <aggregate output folder> web/e2e/fixture
cd web && npx prettier --write e2e/fixture   # optional, the folder is not checked
.venv/bin/python -m pytest pipeline/tests/test_web_fixture.py
```

To change only `health.json` and the pointer's file count, run
`python3 web/e2e/make_fixture.py --health web/e2e/fixture`. It reads the existing
`status.json` and needs no aggregate output. Both commands import the pipeline's
`health` module from `pipeline/src`, which uses only the standard library.

Edit `RUN` in `make_fixture.py` first if the run name should change. A change to
the line list or the shapes it covers also needs the checks in `site.spec.ts`
to stay true.
