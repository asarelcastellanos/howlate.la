# Web

The public site for howlate.la. It builds to static files. Right now it is one
placeholder page and a design specimen. The chart pieces and the data loading
come in later 0.4.0 issues.

The design system exists. `DESIGN.md` documents it, and the `/design` page
shows every piece in the theme your device is using.

## Run it

Use Node 22.18 or newer. Run every command in `web/`.

```bash
npm ci               # install the exact versions in package-lock.json
npm run dev          # dev server with hot reload
npm run check        # svelte-check, the type check CI runs
npm run lint         # prettier and eslint
npm test             # contrast test, checks every color pair against WCAG AA
npm run build        # writes the static site to build/
npm run preview      # serves build/ on http://localhost:4173
```

## Decisions

The 0.4.0 section of `docs/release-plan.md` records the stack.

### SvelteKit with adapter-static

The site is static files. `npm run build` writes them to `build/`, and every
page is prerendered (`src/routes/+layout.ts`). No server runs in front of them.
The data does not need a server either. Per the release plan, the browser
fetches JSON from R2 at runtime, so a new day of data needs no rebuild.

The adapter also writes `build/200.html` as a fallback, so a path that was not
prerendered still loads the app and the client router handles it. Check on the
first preview whether Cloudflare Pages needs a different fallback name.

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
the site, so they follow the light and dark themes. Plot is not installed yet,
because issue #25 adds it with the first chart.

Recharts is a React library, so it does not fit a Svelte site.

### Cloudflare R2 for data

The daily job copies each published run to R2, and `current.json` is written
last. The browser fetches the JSON at runtime. `gs://howlate-derived` never
serves the site, because Cloud Storage egress costs $0.12/GB.

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

The first build should pass once this PR is in.

## Not done yet

- Data loading and charts.

## Reasons still to record

The release plan decides these but does not give the reason.

- SvelteKit over Astro and a Vite React app.
- shadcn-svelte over HeroUI, beyond HeroUI being React-only.
- Observable Plot over ECharts.
- R2 over a Worker, and what R2 costs.
