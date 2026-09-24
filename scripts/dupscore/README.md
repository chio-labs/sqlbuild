# dupscore

Duplication advisory tool for the SQLBuild repository. `make dupscore` runs the default
`clones` mode.

## `dupscore clones` (default)

Reports concrete function-level clones:

- Units are Python functions and methods under `src/sqlbuild` (via `ast`; decorators are outside
  the line range) and Rust `fn` items with bodies under `crates/*/src` (free functions, impl and
  trait methods; via a small lexer that handles nested block comments, raw and byte strings, and
  chars versus lifetimes). Test code is skipped by default: Python `tests/`, Rust `tests/` and
  `benches/` directories, `#[cfg(test)]` items and modules, and `#[test]` functions.
  `--include-tests` analyzes them too. The dbt integration is included, unlike in `report`.
- Token streams are normalised: identifiers become one placeholder, literals one placeholder per
  kind, keywords and operators stay. Comments, Python docstrings, annotations, and `->` are
  dropped.
- Candidates come from MOSS-style winnowed fingerprints: 12-token k-grams, minimum of every
  window of 6 k-grams, so any shared run of 17 or more normalised tokens yields a shared
  fingerprint. Fingerprints present in more than 25 units are boilerplate and ignored. Pairs
  sharing fingerprints with a Jaccard index of at least 0.2 are scored with the `difflib`
  ratio of their normalised streams.
- Categories: `exact` (identical tokens after dropping comments, docstrings, and annotations),
  `renamed` (identical normalised stream), `near-miss` (ratio at or above `--min-similarity`,
  default 0.8). Units under `--min-tokens` normalised tokens (default 60) are ignored.
- Similar pairs are grouped into transitive clusters and ranked by estimated duplicated tokens.

Useful options:

```bash
uv run dupscore clones --since origin/main   # only clusters touching lines changed since a rev
uv run dupscore clones --lang rust --top 10
uv run dupscore clones --path 'src/sqlbuild/compiler/*' --json
```

`--since` diffs the worktree against the revision, so uncommitted edits and untracked files count.
Changed members are marked `[new]` or `[changed]`.

Intentional mirrors can be suppressed in `dupscore.toml`:

```toml
[[clone_allowlist]]
paths = ["src/sqlbuild/example/backends/*"]
reason = "Backends intentionally mirror one protocol."
```

A pair is suppressed when both sides match the entry's globs (`*` also matches `/`).

## `dupscore report` and `dupscore pair A B`

The package-pair ranking fused from call-graph, state fan-in, dataclass overlap, same-name, and
co-change signals, and drill-down evidence for one package pair.
