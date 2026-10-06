# Native crates

SQLBuild's native code is a Cargo workspace that builds one Python extension module,
`sqlbuild._native`. Only `sqlbuild-python` knows about Python; every other crate is plain Rust
that can be tested and benchmarked with `cargo test` alone.

| Crate | Responsibility |
|---|---|
| `sqlbuild-core` | Constants shared by several crates and the panic boundary that turns an unwinding native failure into a named compiler error. |
| `sqlbuild-sqltext` | Lexical SQL text without polyglot: comment, quote and parenthesis scanning, the rules quote policy, model header tokenization and matching, static variable substitution and static reference extraction. |
| `sqlbuild-analysis` | SQL analysis over polyglot: SQL tokens, query analysis, the binding catalog, semantic validation and usage, column references, and SQL-test extraction, planning and rendering. |
| `sqlbuild-rules` | Built-in rules and the rules engine, the custom-rule host, SQL lint, quality checks and formatting, rules configuration and the request models. It also owns the build identity script. |
| `sqlbuild-python` | The only PyO3 crate: the `_native` module, its Python classes and functions, conversions from Python objects, and the process allocator. |

## Layering

Dependencies point one way, from the top of this graph to the bottom:

```text
sqlbuild-python
  -> sqlbuild-rules -> sqlbuild-analysis -> sqlbuild-sqltext -> sqlbuild-core
```

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

## Working on the crates

- Tests live next to the module they cover; run them for one crate with
  `cargo test -p <crate>` or for all crates with `cargo test --workspace`.
- `sqlbuild-analysis` has a `test-support` feature that exposes test-only helpers to the tests of
  dependent crates. Enable it only from `[dev-dependencies]`.
- The build identity (`sqlbuild._native.BUILD_IDENTITY`) hashes the sources of every crate in
  this directory, so editing any crate invalidates the native caches keyed on it.
- maturin builds `crates/sqlbuild-python`; the release version lives in
  `[workspace.package]` and is shared by every crate.
