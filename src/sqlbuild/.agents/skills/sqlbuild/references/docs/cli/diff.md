<!-- generated-by: sqlbuild skills -->

# diff

> Compare schemas and data between targets.

Online: https://sqlbuild.com/docs/cli/diff/

Compares schemas and optionally row-level data between two targets (e.g. `prod:dev`). See [Data Diffs](../concepts/diff.md) for detailed usage.

## Usage

```bash
sqb diff <FROM>:<TO> <mode> [flags]
```

The first argument is a positional `FROM:TO` range. Exactly one mode is required: `--full`, `--schema-only`, or `--bounded <duration>`.

`FROM` and `TO` are configured target names. Their database/schema namespaces remain
authoritative, while the `TO` target's named connection executes the complete comparison and must
be able to read both namespaces.

Full and bounded row comparisons require the model to define `unique_key`. Bounded mode uses the model's cursor and falls back to a full row comparison when no cursor is configured.

## Flags

| Flag | Description |
|------|-------------|
| `--full` | Compare both schema and all row data |
| `--schema-only` | Compare column names and types only |
| `--bounded` | Compare row data within a recent window (e.g. `14d`, `6h`) |
| `--verbose`, `-v` | Show more example rows (default: 3, verbose: 10) |
| `--max-column-examples` | Override maximum examples per changed column |
| `--max-row-only-examples` | Override maximum examples for side-only rows |
| `--sample-rows` | Override the deterministic unique-key sample size |
| `--sample-seed` | Override the deterministic sample seed |
| `--exhaustive` | Disable inherited sampling for this invocation |
| `--json-output` | Write structured comparison scope, coverage, and results to a JSON file |
| `--max-models` | Fail when the selected scope contains more models than this limit |
| `--max-columns` | Fail when either side of a model has more columns than this limit |
| `--no-sql-analysis` | Disable compile-time SQL analysis (`--no-sql-validation` is an alias) |
| `--key` | Row key column; repeat for a composite key. Overrides the model's `unique_key` |
| `--unkeyed` | Compare exact full-row multisets when there is no stable row key |
| `--exclude-column` | Leave a column out of the comparison; repeatable |
| `--tolerance` | Numeric tolerance such as `amount:absolute=1` or `rate:relative=0.001`; repeatable |
| `--left-query`, `--right-query` | Compare two read-only SQL queries instead of models |
| `--left-query-file`, `--right-query-file` | Read each query from a UTF-8 file |
| `--left-label`, `--right-label` | Names for the two query sides in the output |
| `--target` | Target whose connection runs both queries |
| `--max-value-length` | Maximum characters shown per example value (default 160) |
| `--no-example-values` | Keep keys and counts but hide example values |
| `--full-example-values` | Show complete example values |
| `--json` | Print one JSON document to stdout |
| `--select`, `-s` | Select specific models to diff (required in v1) |
| `--exclude` | Exclude specific models from diffing |

## Examples

```bash
# Full diff of a specific model
sqb diff prod:dev --full --select customer_status_snapshot

# Schema-only diff of all marts
sqb diff prod:dev --schema-only --select path:models/marts

# Bounded diff of last 14 days
sqb diff prod:dev --bounded 14d --select hourly_order_activity

# Deterministic bounded sample
sqb diff prod:dev --bounded 14d --sample-rows 50000 --sample-seed 7 --select order_lines

# Force exhaustive comparison despite inherited sampling defaults
sqb diff prod:dev --bounded 14d --exhaustive --select order_lines
```

## Exit codes

Returns `0` when all selected models have no differences, `1` when any model has schema or row differences.
