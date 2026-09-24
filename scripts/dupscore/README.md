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
- Token streams are normalised: local names, parameters, receivers, and plain attribute reads
  become one placeholder, literals one placeholder per kind, and keywords and operators stay.
  Call targets keep their names, so two functions with the same layout that call different
  helpers do not look identical: Python `f(...)` and `obj.f(...)` keep `f`; Rust keeps any
  identifier directly followed by `(` or `!` (functions, methods, tuple constructors, macros)
  except the name after `fn`. Comments, Python docstrings, annotations, and `->` are dropped.
- Candidates come from MOSS-style winnowed fingerprints: 12-token k-grams, minimum of every
  window of 6 k-grams, so any shared run of 17 or more normalised tokens yields a shared
  fingerprint. Fingerprints present in more than 25 units are boilerplate and ignored. Pairs
  sharing fingerprints with a Jaccard index of at least 0.2 are scored with the `difflib`
  ratio of their normalised streams.
- Categories: `exact` (identical tokens after dropping comments, docstrings, and annotations),
  `renamed` (identical normalised stream, so only abstracted names and literals differ),
  `near-miss` (ratio at or above `--min-similarity`, default 0.8). Units under `--min-tokens`
  normalised tokens (default 60) are ignored. A near-miss pair whose smaller unit has fewer
  than 80 tokens must reach a ratio of at least 0.9: short wrappers share most of their
  skeleton by idiom, so this removes a noisy low end without affecting exact or renamed pairs.
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

Contract methods that every implementation must define itself are declared once:

```toml
[[contract_exemption]]
contract = "src/sqlbuild/adapter/contract/classes/strict_adapter.py:StrictAdapter"
paths = ["src/sqlbuild/adapter/contract/classes/*", "src/sqlbuild/adapters/*/classes/*"]
forbidden_owners = ["src/sqlbuild/adapter/contract/classes/base_adapter.py:BaseAdapter"]
reason = "The strict adapter contract test requires each adapter to define every method."
```

The contract method names are the class's abstract methods (`@abstractmethod` or
`@abc.abstractmethod`, including those inherited from resolvable bases and not overridden),
parsed with `ast` from the analysed worktree; nothing is imported. A method is a forced override
when its top-level class lies under `paths`, derives from the contract class, and would
otherwise inherit that method from the contract, a `forbidden_owners` class, or nowhere. Links
between two forced overrides are hidden and clusters left without links disappear; links from
a forced override to any other unit (a private helper copy, or an override that could have been
inherited instead) are still reported. The summary counts forced overrides hidden this way.
Forced overrides that remain in a reported cluster are marked `[forced]` in text output
(`"forced_override": true` in JSON) and listed after the other members, so a cluster's first
lines show what to fix. They also add nothing to the duplicated-token estimate that ranks
clusters: a forced override already serves as the copy that must stay.
An entry whose contract file is absent from the analysed tree is inactive; a missing class in an
existing file is a configuration error.

## `dupscore report` and `dupscore pair A B`

The package-pair ranking fused from call-graph, state fan-in, dataclass overlap, same-name, and
co-change signals, and drill-down evidence for one package pair.
