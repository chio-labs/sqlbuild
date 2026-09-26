<!-- generated-by: sqlbuild skills -->

# sqb compile

> Compile models into resolved SQL, validate contracts, and write target artifacts - fully offline.

Online: https://sqlbuild.com/docs/cli/compile/

## Contents

- Usage
- Flags
- What compile does
- Focused compilation
- Static analysis
- Output
- Column lineage modes
- Examples

Discovers the complete project, resolves references, expands macros, validates SQL, checks column contracts, computes column lineage, and writes compiled artifacts to `target/`. The compile command is fully offline—it does not connect to the warehouse.

## Usage

```bash
sqb --project-dir <path> compile [flags]
```

## Flags

| Flag | Description |
|------|-------------|
| `--no-sql-analysis` | Disable SQL syntax, binding, type inference, and semantic validation (`--no-sql-validation` remains an alias) |
| `--no-cache` | Bypass the reusable compile-analysis cache for this invocation |
| `--defer-to` | Resolve unselected model references against another target |
| `--json` | Output the full compile report as JSON |
| `--manifest` | Generate `target/manifest.json` with project metadata |
| `--lineage-mode` | Column lineage mode: `fast` (default), `rich` (slower, more detail), or `none` |
| `--select`, `-s` | Analyze and report selected resources |
| `--select-file` | Read selectors from a file, one selector per line |
| `--exclude` | Remove resources from the selected scope |

## What compile does

1. **Discovery** - finds `sqlbuild_project.toml`, scans for models, sources, seeds, functions, audits, tests, and macros
2. **Graph resolution** - resolves `ref()` and `source()` calls, expands macros, orders models by dependency
3. **SQL validation** - validates SQL syntax (when SQL analysis is enabled)
4. **Column lineage** - analyzes column-level dependencies across models (fast mode by default)
5. **Contract validation** - checks declared column contracts against inferred query output
6. **Rules** - evaluates selected native built-ins, then selected custom Python Rules
7. **Artifact write** - writes compiled SQL to `target/compiled/` when Rules pass

## Focused compilation

Use normal selectors to limit expensive analysis and reporting while retaining complete project
discovery and reference integrity:

```bash
sqb compile --select fact_orders daily_revenue
sqb compile --select-file selected-models.txt
sqb compile --exclude deprecated_model
```

SQLBuild deeply analyzes the selected resources and the upstream closure needed to understand them.
The text report contains only the selected scope. Project totals remain available in JSON, together
with selected model, seed, and function counts.

Manifest and DAG outputs remain full-project artifacts. Focused compilation changes analysis and
reporting scope; it does not produce a partial project graph.

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
Compile ready (12 models)

  stg_customers              OK  3 columns
  stg_orders                 OK  5 columns
  stg_payments               OK  4 columns
  fact_orders                OK  6 columns
  dim_customers              OK  4 columns
  daily_revenue              OK  3 columns
  ...

  Compiled: 12 models, 1 seed, 5 functions, 0 errors, 0 warnings
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
sqb compile --select fact_orders daily_revenue

# Disable SQL analysis
sqb compile --no-sql-analysis
```
