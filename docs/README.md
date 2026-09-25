# SQLBuild documentation site

The docs site, built with [Astro Starlight](https://starlight.astro.build) and styled to match the SQLBuild UI and sqlbuild.com. Search uses Pagefind, and `llms.txt`, `llms-small.txt` and `llms-full.txt` are generated at build time.

This is a pilot with a few pages ported from the Mintlify docs. Mintlify's `Card`, `CardGroup`, `Frame`, `Note` and `Warning` components have drop-in versions under `src/components/mintlify/`.

Requires Node 22.12 or newer.

```bash
npm install
npm run dev      # live preview
npm run build    # static site in dist/, including the search index
npm run preview  # serve dist/
```

Search only works on a built site (`npm run build`, then `npm run preview`).
