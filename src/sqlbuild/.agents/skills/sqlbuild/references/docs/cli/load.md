<!-- generated-by: sqlbuild skills -->

# sqb load

> Load managed sources into the warehouse.

Online: https://sqlbuild.com/docs/cli/load/

Runs source loader functions and writes data into their target tables using the configured write strategy.

## Usage

```bash
sqb --project-dir <path> load [flags]
```

## Flags

| Flag | Description |
|------|-------------|
| `--select`, `-s` | Select specific sources or loaders by name |
| `--exclude` | Exclude specific sources or loaders |
| `--reload` | Pass `is_reload=True` to loader functions |
| `--concurrency` | Number of worker connections (default: from settings or 1) |
| `--start-cursor-ts` | Override start cursor for timestamp-based loaders (ISO format) |
| `--end-cursor-ts` | Override end cursor for timestamp-based loaders (ISO format) |
| `--start-cursor-int` | Override start cursor for integer-based loaders |
| `--end-cursor-int` | Override end cursor for integer-based loaders |
| `--json` | Output results as JSON |
| `--json-output` | Write JSON results to a file path |
| `--var` | Set project variables (`--var key=value`) |

## Examples

```bash
# Load all managed sources
sqb load

# Load a specific source
sqb load --select raw_customers

# Load with concurrency
sqb load --concurrency 4

# Reload all sources (full refresh behavior)
sqb load --reload

# Override cursor bounds
sqb load --start-cursor-ts "2026-05-01T00:00:00"
```

## Execution order

Loaders are executed in DAG topological order based on `depends_on` declarations. Independent loaders run concurrently when `--concurrency` is greater than 1.

Intermediate loaders (those referenced only via `depends_on` without a direct source binding) run first, followed by the source-bound loaders that depend on them.

## Output

```
Load ready (3 selected)

Sources (3)
  raw_customers
  raw_orders
  raw_payments

Execution  sqb load  (concurrency: 1)

  1/3  source    raw_customers                  OK     0.05s  rows=5
  2/3  source    raw_orders                     OK     0.03s  rows=10
  3/3  source    raw_payments                   OK     0.02s  rows=8

Completed successfully.
PASS=3  WARN=0  FAIL=0  SKIP=0  TOTAL=3  (0.12s)
```

## Auto-load during builds

`sqb build` automatically loads managed sources before building dependent models. This is controlled by the `auto_load_sources` setting (default: `true`) and the `--load` / `--no-load` / `--reload` flags:

```bash
# Default: auto-load is on
sqb build

# Explicitly skip loading
sqb build --no-load

# Force reload
sqb build --reload
```

See [Loaders](../concepts/python-nodes/loaders.md) for full documentation on write strategies, the loader context API, and source deferral.
