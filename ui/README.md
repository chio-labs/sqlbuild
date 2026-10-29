# SQLBuild UI

The SQLBuild orchestration web UI: a SvelteKit single-page app built to static
assets (`adapter-static`, SPA fallback, no SSR).

This is an early, preliminary version. Pages read from a typed data layer in
`src/lib/api/`; until the server API exists, that layer is backed by an
in-memory mock client with neutral example data.

## Develop

```sh
npm ci
npm run dev
```

## Check and build

```sh
npm run check
npm run build   # writes static assets to build/
```
