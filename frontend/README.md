# cuttlefish-crew dashboard

The plain (non-pixel-art) frontend for slice D1 (ADR-0009) — a portfolio view across
every registered project and a per-project detail view with a working steer-chat
panel. Talks to a running `cuttlefish serve`'s HTTP surface
(`cuttlefish.fleet.server`); see `docs/adr/0009-*.md` for the full design.
D2 (the pixel-art office view) renders against this exact same API.

TypeScript + Svelte + Vite — this repo's first non-Python build pipeline, and, so
far, the only part of it that needs `npm`.

## Develop

```sh
npm install
npm run dev
```

Then start a fleet daemon in another terminal (`cuttlefish serve`) and paste its
printed base URL/token into the app's connect screen. The dev server and the daemon
run on different ports, so this exercises the real CORS path
(`cuttlefish.fleet.server`'s `CORSMiddleware`, loopback-origin-only) exactly as a
real browser session would.

## Check / build

```sh
npm run check   # svelte-check + tsc, no build step -- what `make frontend-check` runs
npm run build   # production build to dist/ -- what `make frontend-build` runs
```

Both are gated by `make ci` alongside the Python suite.
