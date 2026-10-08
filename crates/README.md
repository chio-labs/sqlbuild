# Native crates

SQLBuild's native code is a Cargo workspace that builds one Python extension module,
`sqlbuild._native`. Only `sqlbuild-python` knows about Python; every other crate is plain Rust
that can be tested and benchmarked with `cargo test` alone.

| Crate | Responsibility |
|---|---|
| `sqlbuild-core` | Constants shared by several crates, the panic boundary that turns an unwinding native failure into a named compiler error, passive identity, diagnostic and SQL value types, text positions, and a JSON emitter whose output matches Python's `json.dumps` and `orjson` byte for byte. |
| `sqlbuild-cache` | The shared native store every native cache uses (one atomically replaced, checksummed file per cache kind, keyed by content digests) and the one fingerprinting scheme for cache keys: the content digest and the project file fingerprint. |
| `sqlbuild-sqltext` | Lexical SQL text without polyglot: comment, quote and parenthesis scanning, the rules quote policy, model header tokenization and matching, static variable substitution, static reference extraction, and the general reference scan with table-function call arguments under each adapter's lexical rules. |
| `sqlbuild-config` | Configuration file reading without Python: `tomllib`-compatible TOML, PyYAML `safe_load`-compatible YAML 1.1, and typed project and local config readers for the fields discovery needs. Errors carry their kind and position; YAML outside the supported subset is an `Unsupported` error. |
| `sqlbuild-discovery` | Native project discovery and the only implementation of the model, SQL test, scenario, source and schema file collections and the declaration layout: the shared directory walk with Python's glob and sort semantics, file reading with Python's newline handling and read errors, and parsing of authored files with Python's exact discovery messages. Results are plain data the Python discovery facade materialises. |
| `sqlbuild-scopes` | Declaration scopes: the scope index with Python's record orders and diagnostics, declaration visibility, relationship grants, the scope lookup groups, and the dialect-aware scan of SQL tests and scenarios for their expected models. Anything it cannot reproduce exactly defers to Python. |
| `sqlbuild-model-config` | Model configuration: MODEL header columns and audits, `${...}` template expansion with its environment and context reads, and the template and macro presence scans over authored config values, all read through a trait over the caller's values. Anything it cannot reproduce exactly defers to Python, which also raises every model config error. |
| `sqlbuild-render` | Native rendering: the macro call scanner (a byte-for-byte port of Python's), splicing of rendered calls with code-point spans, and the in-compile memo of recorded macro calls and their replayable events, which can carry results across compiles through the shared native store. Anything it cannot reproduce exactly defers to Python. |
| `sqlbuild-attachments` | Compile attachments for tests, audits, sources, functions, scenarios and seeds: attached generic audit argument merge, raw and quoted argument rendering, and severity and run scope resolution. Anything it cannot reproduce exactly defers to Python, which also raises every attachment error. |
| `sqlbuild-analysis` | SQL analysis over polyglot: SQL tokens, query analysis, the binding catalog, semantic validation and usage, column references, type normalization, and SQL-test extraction, planning and rendering. Type normalization defers to Python for anything it cannot reproduce exactly. |
| `sqlbuild-rules` | Built-in rules and the rules engine, the custom-rule host, SQL lint, quality checks and formatting, rules configuration and the request models. It also owns the build identity script. |
| `sqlbuild-python` | The only PyO3 crate: the `_native` module, its Python classes and functions, conversions from Python objects, and the process allocator. |

## Layering

Dependencies point one way, from the top of this graph to the bottom:

```text
sqlbuild-python
  -> sqlbuild-rules -> sqlbuild-analysis -> sqlbuild-attachments -> sqlbuild-render
  -> sqlbuild-model-config -> sqlbuild-scopes -> sqlbuild-discovery -> sqlbuild-config
  -> sqlbuild-sqltext -> sqlbuild-cache -> sqlbuild-core
```

`sqlbuild-config` and `sqlbuild-model-config` do not depend on the crates below them today, and
`sqlbuild-scopes` uses only `sqlbuild-sqltext`; their place in the order fixes which crates may
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
| `python` | The Python compiler only. It is the oracle every native stage must match byte for byte. |
| `native` | The default: native stages that passed their flip gate (`shipped` tier). |
| `native-preview` | Opt-in: shipped stages plus stages still in development (`preview` tier). |

The shipped tier covers discovery and rendering: declaration files and scopes, model config,
reference extraction, the model loop, macro calls and the macro-call store, and attachments. SQL
analysis, contracts, lineage, SQL-test glue and project assembly are still `preview`. When a
native render stage fails, the compile runs the Python stage again so the error is exactly
Python's; native error messages replace that re-run later. Because the macro-call store is
shipped, the [macro determinism contract](../website/src/content/docs/docs/concepts/macros.mdx)
applies to every default compile; `SQLBUILD_COMPILER_ENGINE=python` runs every macro call each
time.

Each native stage declares its tier once, in `NATIVE_STAGE_TIERS` in
`src/sqlbuild/compiler/frontier/constants.py`. A stage moves from `preview` to `shipped` by
changing that line, after its flip gate passes: a byte-identical real project, a green
differential, and no measured slowdown on cold, edit and no-change compiles. Every engine keeps
its own compiler, Rules and compile-reuse stores, so preview output is never reused by `native`.

`make compiler-differential` compares `python` with `native-preview` on the full per-PR corpus.
`make compiler-differential-shipped` compares `python` with `native` on the generated seeds and
the failure corpus, so the shipped default stays covered on its own; CI runs it with stage
captures and requires full discovery and render coverage. CI runs both, compares `python` with
`native` and `native-preview` on Python 3.13 and 3.14 as well, and on Windows checks that the
default compiles a playground project to the same files as `python`.

## Working on the crates

- Tests live next to the module they cover; run them for one crate with
  `cargo test -p <crate>` or for all crates with `cargo test --workspace`.
- `sqlbuild-analysis` has a `test-support` feature that exposes test-only helpers to the tests of
  dependent crates. Enable it only from `[dev-dependencies]`.
- The build identity (`sqlbuild._native.BUILD_IDENTITY`) hashes the sources of every crate in
  this directory, so editing any crate invalidates the native caches keyed on it.
- maturin builds `crates/sqlbuild-python`; the release version lives in
  `[workspace.package]` and is shared by every crate.
