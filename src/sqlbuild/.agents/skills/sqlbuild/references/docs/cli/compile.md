<!-- generated-by: sqlbuild skills -->

# sqb compile

> Compile models into resolved SQL, validate contracts, and write target artifacts - fully offline.

Online: https://sqlbuild.com/docs/cli/compile/

## Contents

- Usage
- Flags
- What compile does
- Focused compilation
- Reusing an unchanged compile
- Static analysis
- Output
- Column lineage modes
- Examples

Discovers the complete project, resolves references, expands macros, validates SQL, checks column contracts, computes column lineage, and writes compiled artifacts to `target/`. The compile command is fully offline—it does not connect to the warehouse.

## Usage

```bash
sqb compile [SELECTOR ...] [flags]
```

Positional `SELECTOR` arguments work like `--select`, and both forms can be combined. `--project-dir <path>`, `--no-color`, and `--debug` can go before or after the command name.

## Flags

| Flag | Description |
|------|-------------|
| `--no-sql-analysis` | Disable SQL syntax, binding, type inference, and semantic validation (`--no-sql-validation` remains an alias) |
| `--no-cache` | Bypass the reusable compile-analysis cache for this invocation |
| `--defer-to` | Resolve unselected model references against another target |
| `--json` | Output the full compile report as JSON |
| `--manifest` | Generate `target/manifest.json` with project metadata |
| `--lineage-mode` | Column lineage mode: `fast` (default), `rich` (slower, more detail), or `none` |
| `SELECTOR ...` | Positional selectors, the same as `--select` |
| `--select`, `-s` | Analyze and report selected resources |
| `--select-file` | Read selectors from a file, one selector per line |
| `--exclude` | Remove resources from the selected scope |

## What compile does

1. **Discovery** - finds `sqlbuild_project.toml`, scans for models, sources, seeds, functions, audits, tests, and macros
2. **Graph resolution** - resolves `__ref()`, `__source()`, and `__seed()` references, expands macros, orders models by dependency
3. **SQL validation** - validates SQL syntax (when SQL analysis is enabled)
4. **Column lineage** - analyzes column-level dependencies across models (fast mode by default)
5. **Contract validation** - checks declared column contracts against inferred query output
6. **Rules** - evaluates selected native built-ins, then selected custom Python Rules. Rules that
   need inferred type proofs, such as `SQBRCONTRACT105`, are skipped when SQL analysis is disabled,
   and compile prints one note naming them
7. **Artifact write** - writes compiled SQL to `target/compiled/` when Rules pass

## Focused compilation

Use normal selectors to limit expensive analysis and reporting while retaining complete project
discovery and reference integrity:

```bash
sqb compile fact_orders daily_revenue
sqb compile --select-file selected-models.txt
sqb compile --exclude deprecated_model
```

SQLBuild deeply analyzes the selected resources and the upstream closure needed to understand them.
The text report contains only the selected scope. Project totals remain available in JSON, together
with selected model, seed, and function counts.

Manifest and DAG outputs remain full-project artifacts. Focused compilation changes analysis and
reporting scope; it does not produce a partial project graph.

## Reusing an unchanged compile

When nothing that can change the result has changed since the last compile, `sqb compile` replays
that result instead of compiling again. It prints one line to stderr, for example
`Inputs unchanged; reused the previous compile (0.1 s)`, then the same report and exit code as the
previous run. Failed compiles are replayed too, with the same diagnostics.

A compile is reused only when all of these match the stored run:

- Every file and directory under the project, compared by type, size, modification and change
  times, and inode. When those differ, SQLBuild compares content only for files whose content
  digest it already knows; otherwise the compile runs in full. Digests are recorded for files that
  changed within two seconds of a compile and for files whose timestamps moved since the previous
  compile, so large unchanged files are never read. After a checkout that only moves timestamps,
  the next compile runs in full once, and later timestamp-only changes are reused.
- The command line: project directory, working directory, flags, selectors, `--vars`, target, and
  whether color output is active.
- Environment variables that SQLBuild reads: every `SQLBUILD_*` and `SQB_*` variable, every
  variable that a template or `@@ENV` read during the stored compile, and every variable a
  provider's settings can read, including `env_prefix`, aliases, and nested-delimiter variables.
  Values are stored only as hashes.
- The contents of each provider settings `env_file` and `secrets_dir`.
- The Python interpreter, the SQLBuild version and native extension, `sys.path` entries, and every
  loaded Python module file outside the project.
- Every artifact the stored compile wrote under `target/compiled/`, and the `--dag` file. If one is
  missing or changed, compile runs in full and rewrites it. A compile is stored only when these
  artifacts still hold the bytes it wrote, so a concurrent compile cannot leave another compile's
  artifacts behind a reused result.

These project paths are not inputs: `target/`, `logs/`, `venv/`, `.git/` and `__pycache__/`
anywhere, and these folders at the project root: `.cache`, `.fensu`, `.hg`, `.idea`,
`.mypy_cache`, `.nox`, `.pytest_cache`, `.ruff_cache`, `.sqlbuild`, `.svn`, `.tox`, `.venv`, and
`.vscode`. Other hidden folders are inputs, because custom rules can read them. DuckDB database
files count only by presence.

Reuse assumes macros, hooks, providers, adapters, and custom rules are deterministic: the same inputs
must produce the same output. Macro results are also reused within a compile and may be kept between
compiles; see [Macros must be deterministic](../concepts/macros.md#macros-must-be-deterministic). A
compile whose templates read `run.id` is never reused.

Compile always runs in full with `--no-cache`, `--manifest`, `--debug`, or a profiling flag, when
`SQLBUILD_DISABLE_COMPILE_CACHE=1` or `SQLBUILD_DISABLE_COMPILE_REUSE=1` is set, when the project has
no `sqlbuild_project.toml` or `sqlbuild_project.yml`, when the target sets `compile_cache = false`,
and when a provider's settings use sources SQLBuild cannot list exactly, such as a custom
`settings_customise_sources` or command-line parsing. The reason is logged at debug level.

SQLBuild keeps one stored result per project and target under
`target/cache/compiler-native-v1/project-reuse-v1/`. It is replaced atomically; a damaged or unreadable entry is
ignored and compile runs in full. Storing a result normally takes a fraction of a second after the
report is ready. When it has to hash a lot of data or the project has very many files, compile
prints `Recording compile for reuse...` and a completion line to stderr before the report.

### Compiling after an edit

Any change runs the whole compile again: every model, test, and audit is rendered again, and
contracts and semantic validation run for the whole project. No render is carried over from the
previous compile. A few caches under `target/cache/` still apply: an unchanged model takes its
column analysis from the analysis cache when its query and the analyses of its upstream models are
unchanged, rule results are reused for unchanged inputs, and macro call results may be reused as
described in [Macros must be deterministic](../concepts/macros.md#macros-must-be-deterministic).
Until the native compiler ships, editing one model therefore costs close to a full compile. The
output is byte-identical to `sqb compile --no-cache`.

Known limits:

- Python packages outside the project are checked by the stamps of the module files the compile
  loaded. A newly added submodule or package data file that the compile reads without importing it
  first is not tracked.
- On network filesystems that cache file attributes, or when clocks differ between machines,
  timestamps may not reflect a recent edit.
- On Windows, a file's change time is its creation time. An in-place rewrite that keeps the same
  size and restores the previous modification time, such as `touch -r`, `rsync -t`, or
  `robocopy /COPY:T`, is not detected unless the file changed within two seconds of the stored
  compile. The same applies to filesystems without a real change time, such as some FUSE, SMB, and
  exFAT mounts.
- In these cases, or whenever a result looks stale, run `sqb compile --no-cache` or set
  `SQLBUILD_DISABLE_COMPILE_REUSE=1`.

A replayed JSON report is byte-identical to the previous one except for `compile_timings`, which
holds `project_reuse_hits`, `project_reuse_misses`, `project_reuse_bypasses`,
`project_reuse_check_ms`, and `total_ms`. Full compiles report the same reuse counters alongside
the phase timings. In text mode, a replayed compile does not print the per-phase progress lines.
Lifecycle sinks receive only the invocation events for a replayed compile; per-phase `operation`
events are not emitted because no compile phase runs.

## Static analysis

When SQL analysis is enabled (default), compile performs static analysis on your models without connecting to the warehouse:

- **Column inference**: Infers output columns from each model's SQL, including through CTEs, subqueries, and JOINs
- **Column contract validation**: Under the default `settings.column_contract_mode = "implicit"`, a model with declared columns and no model-level `contract` declaration checks that every declared column exists in the statically inferred query output. `explicit` mode requires `contract enforced` to activate shape checks. Explicit type enforcement remains independent and verifies inferred types when possible
- **Column lineage**: Traces which source columns flow into each output column, including transform classification. See [Column Lineage](../concepts/column-lineage.md) for details

`sqb compile` is authoritative for mandatory correctness, contracts, lineage, and configured Rules.
Rules findings block artifact completion. Use [`sqb rules run`](rules.md) to focus on one exact
code or family without changing project configuration.

### Contract diagnostics

When a contract violation is found, compile reports it with source-annotated diagnostics:

```
error[K001]: declared column 'total_cents' was not found in statically inferred output for model 'fact_orders'
  model: fact_orders
  --> models/marts/fact_orders.sql:6:5
  6 |     total_cents (),
    |     ^^^^^^^^^^^
  = help: add total_cents to the SELECT list or correct/remove MODEL(columns (...)); MODEL(columns (...)) is validated using static SQL analysis because settings.column_contract_mode is "implicit" (the default). If this project intentionally uses columns only for metadata and audits, set [settings] column_contract_mode = "explicit"; models with contract enforced remain validated
```

The configuration guidance is an intentional project-policy choice, not a general error suppression. Fix the query or declaration when the model is intended to have a column contract. Diagnostics for `contract enforced` models do not recommend changing the project mode because explicit model contracts remain authoritative.

Diagnostic codes:

| Code | Meaning |
|------|---------|
| `K001` | A declared column is missing from the model's query output |
| `K002` | A column's inferred type does not match the declared type |
| `K003` | A column's type could not be proven (with `type_enforcement` enabled) |

Compile returns exit code `1` when any error-severity diagnostic is found, making it suitable for CI checks.

## Output

### Text output (default)

```bash
sqb compile
```

```
Compile ready  12 models

├── daily_revenue                      OK   6 columns
├── dim_customers                      OK   7 columns
├── fact_orders                        OK   13 columns
├── stg_customers                      OK   5 columns
├── stg_orders                         OK   6 columns
└── stg_payments                       OK   6 columns
...

✓ Project compiled  12 models, 1 seed, 2 functions, 0 errors, 0 warnings
  Wrote: target/compiled/
```

Each model shows its name, status (OK or FAIL), and column count. Models with contract errors are marked FAIL.

### JSON output

```bash
sqb compile --json
```

Returns a structured report including:

- `summary` - model, seed, function, audit, test, error, and warning counts
- `resources` - per-model details including column count, dependencies, lineage summary, and compiled SQL
- `diagnostics` - all contract violations with source locations
- `compile_timings` - timing breakdown for discovery, graph, lineage, contracts, and write phases
- `lineage_mode` - which lineage mode was used
- `artifacts` - paths to written files

If compile stops on an error before it can build the report, such as a model header that does not
parse, `--json` still prints one JSON document. It has `command`, `has_errors: true`,
`stopped: true`, and a `diagnostics` list with that error's `code`, `message`, and `help`, the same
text the error shows on stderr. The exit code is still 1, and progress stays on stderr.

## Column lineage modes

The `--lineage-mode` flag controls how column lineage is computed during compile:

| Mode | Description |
|------|-------------|
| `fast` | Default. Lightweight column extraction using SQL model metadata. |
| `rich` | Full SQL analysis with transform classification and deeper tracing. Slower on large projects. |
| `none` | Skip column lineage entirely. |

The JSON compile report includes a lineage summary for each model, not the full column graph. Use `sqb lineage <model>[.<column>]` to inspect lineage as a tree, edge list, or JSON. See [Column Lineage](../concepts/column-lineage.md) for details on analysis modes and transform types.

## Examples

```bash
# Basic compile
sqb compile

# Compile with full JSON report
sqb compile --json

# Compile with rich column lineage
sqb compile --lineage-mode rich

# Skip column lineage
sqb compile --lineage-mode none

# Generate manifest
sqb compile --manifest

# Compile only selected models
sqb compile fact_orders daily_revenue

# Disable SQL analysis
sqb compile --no-sql-analysis
```
