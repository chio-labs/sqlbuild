# Native crates

SQLBuild's native code is a Cargo workspace that builds one Python extension module,
`sqlbuild._native`, and the `sqb`/`sqlbuild` executables in the `sqlbuild-cli` wheel. Only `sqlbuild-python` knows about Python; every other crate is plain Rust
that can be tested and benchmarked with `cargo test` alone.

| Crate | Responsibility |
|---|---|
| `sqlbuild-core` | Constants shared by several crates, the panic boundary that turns an unwinding native failure into a named compiler error, passive identity, diagnostic and SQL value types, text positions, and a JSON emitter whose output matches Python's `json.dumps` and `orjson` byte for byte. |
| `sqlbuild-cache` | The shared native store every native cache uses (one atomically replaced, checksummed file per cache kind, keyed by content digests) and the one fingerprinting scheme for cache keys: the content digest and the project file fingerprint. |
| `sqlbuild-sqltext` | Lexical SQL text without polyglot: comment, quote and parenthesis scanning, the rules quote policy, model header tokenization and matching, static variable substitution, static reference extraction, and the general reference scan with table-function call arguments under each adapter's lexical rules. |
| `sqlbuild-config` | Configuration file reading without Python: `tomllib`-compatible TOML, PyYAML `safe_load`-compatible YAML 1.1, and typed project and local config readers for the fields discovery needs. Errors carry their kind and position; YAML outside the supported subset is an `Unsupported` error. |
| `sqlbuild-discovery` | Native project discovery and the only implementation of the model, SQL test, scenario, source and schema file collections and the declaration layout: the shared directory walk with Python's glob and sort semantics, file reading with Python's newline handling and read errors, and parsing of authored files with Python's exact discovery messages. Results are plain data the Python discovery facade materialises. |
| `sqlbuild-scopes` | Declaration scopes, visibility, relationship grants, placement, report queries and the offline scope cache, including dialect-aware SQL-test and scenario scans. |
| `sqlbuild-model-config` | MODEL configuration, columns and audits, template expansion over caller values, and dynamic-column name patterns using Rust regex syntax. |
| `sqlbuild-render` | Macro call scanning, argument evaluation, expansion, splicing, memoisation and persistent call-store keys. Python executes user macro bodies at the extension boundary. |
| `sqlbuild-attachments` | Native attachment of tests, audits, sources, functions, scenarios and seeds, including argument merging, validation and audit policy resolution. Adapter value rendering remains an extension boundary. |
| `sqlbuild-analysis` | SQL analysis over polyglot: query analysis, binding, semantic validation and usage, column references, type normalization, FAST/RICH lineage, and SQL-test/scenario extraction and compiler-side assembly. |
| `sqlbuild-rules` | Built-in rules and the rules engine, the custom-rule host, SQL lint, quality checks and formatting, rules configuration and the request models. It also owns the build identity script. |
| `sqlbuild-refactor` | Native rename/move plans, contract-adoption edits, MODEL/SCHEMA/YAML text edits and atomic staging/commit with rollback. Shared scope placement delegates to the native scope implementation; user Python source inspection remains at the Python AST boundary. |
| `sqlbuild-cli` | The `sqb` and `sqlbuild` executables: `--version`, unchanged compiles replayed from the shared reuse store with Python's exact streams, exit code and compute log capture, and a handoff of every other invocation to the installed `sqlbuild-python` script. Built as its own wheel (`crates/sqlbuild-cli/pyproject.toml`). |
| `sqlbuild-python` | The only PyO3 crate: the `_native` module, its Python classes and functions, conversions from Python objects, and the process allocator. |

## Layering

Dependencies point one way, from the top of this graph to the bottom:

```text
sqlbuild-python
  -> sqlbuild-refactor -> sqlbuild-rules -> sqlbuild-analysis -> sqlbuild-attachments
  -> sqlbuild-model-config -> sqlbuild-scopes -> sqlbuild-render -> sqlbuild-discovery -> sqlbuild-config
  -> sqlbuild-sqltext -> sqlbuild-cache -> sqlbuild-core
sqlbuild-cli -> sqlbuild-cache, sqlbuild-core
```

`sqlbuild-scopes` reuses the macro scanner in `sqlbuild-render`; render itself depends only on
`sqlbuild-cache` and `sqlbuild-core`. Their place in the order fixes which crates may
use them. The JSON emitter
lives in `sqlbuild-core` so that any layer can produce text that must equal Python's
`json.dumps` output.

Each crate may depend only on crates below it, and may also skip layers. The order is declared
in `[workspace.metadata.native-layers]` in the workspace `Cargo.toml`, and
`make check-native-layering` (part of `make check-ci`) fails when:

- a crate depends on a crate that is not in an earlier layer, or a workspace crate is missing
  from the order;
- any crate other than `sqlbuild-python` reaches `pyo3`, directly or through another package;
- a crate below `sqlbuild-analysis` reaches polyglot.

The same check fails when the workspace version, the `pyproject.toml` version and
`.release-please-manifest.json` disagree, because the version is part of the build identity.

`fensu check` applies the Rust structure rules inside each crate: other crates use items through
`main/` entry points, `models.rs`, `types.rs` and `constants.rs`, not through `_helpers/`.

## Compiler engines

`SQLBUILD_COMPILER_ENGINE` (or the hidden `--compiler-engine` flag) selects which compiler
stages run natively:

| Engine | Runs |
|---|---|
| `native` | The default: discovery, rendering and analysis, and every native stage that passed its flip gate (`shipped` tier). |
| `native-preview` | Opt-in: shipped stages plus stages still in development (`preview` tier). |

The Python compiler and its `python` engine were removed once discovery, rendering and analysis
shipped natively; setting `python` is an error that says so. Generic compiler stages do not
rescue native failures through a Python implementation. User macros, custom rules and adapter
callbacks retain their explicit Python boundaries. The recorder in
`scripts/compiler_differential/native_fallbacks.toml` tracks native answers and the remaining
extension/test-mock callbacks. A failing render raises its first error directly and runs each macro call at most
once; a divergence the bridge detects is reported as a native stage mismatch. Because the
macro-call store is always on, the
[macro determinism contract](../website/src/content/docs/docs/concepts/macros.mdx) applies to
every compile.

Each native stage declares its tier once, in `NATIVE_STAGE_TIERS` in
`src/sqlbuild/compiler/frontier/constants.py`. A stage moves from `preview` to `shipped` by
changing that line, after its flip gate passes: a byte-identical real project, a green
differential, and no measured slowdown on cold, edit and no-change compiles. Every engine keeps
its own compiler, Rules and compile-reuse stores, so preview output is never reused by `native`.

`make compiler-differential` compares `native` with `native-preview` on the full per-PR corpus
and checks both against the goldens in `tests/goldens/compiler`, with stage captures and full
discovery, render and analysis coverage required. CI also runs it on Python 3.13 and 3.14, and
on Windows checks that both engines compile a playground project to the same files.

## Working on the crates

- Tests live next to the module they cover; run them for one crate with
  `cargo test -p <crate>` or for all crates with `cargo test --workspace`.
- `sqlbuild-analysis` has a `test-support` feature that exposes test-only helpers to the tests of
  dependent crates. Enable it only from `[dev-dependencies]`.
- The build identity (`sqlbuild._native.BUILD_IDENTITY`) hashes the sources of every crate in
  this directory, so editing any crate invalidates the native caches keyed on it.
- maturin builds `crates/sqlbuild-python`; the release version lives in
  `[workspace.package]` and is shared by every crate.
