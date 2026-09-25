# sqlbuild.com

The SQLBuild website: the homepage at `/` and the documentation at `/docs/`, built as one [Astro Starlight](https://starlight.astro.build) site and styled to match the SQLBuild UI.

- `public/index.html` and `public/styles.css`: the homepage, plain static HTML and CSS. Its terminal examples come from `sqb playground waffle-shop` output, trimmed to the relevant lines. Step 01's compile output is a placeholder until compile reports unknown columns and type mismatches.
- `src/content/docs/docs/`: the documentation pages (MDX), first ported from the Mintlify docs and now edited here. `src/navigation.mjs` holds the sidebar and redirects.
- `src/components/`: the page layout, header and page title, replacing Starlight's defaults. `src/components/mintlify/` has drop-in versions of the Mintlify components the pages use (`Card`, `CardGroup`, `Frame`, `Note`, `Warning`).
- `public/fonts/`: self-hosted fonts, each with its licence.

Search uses Pagefind, and `llms.txt`, `llms-small.txt` and `llms-full.txt` are generated at build time.

Requires Node 22.12 or newer.

```bash
npm install
npm run dev      # live preview
npm run build    # static site in dist/, including the search index
npm run preview  # serve dist/
```

Search only works on a built site (`npm run build`, then `npm run preview`).
